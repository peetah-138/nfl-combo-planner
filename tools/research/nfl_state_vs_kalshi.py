#!/usr/bin/env python3
"""Air-side check: does the small state-only win-probability model beat Kalshi's live price? Read-only, no network, no keys.

Run from the app folder, on the machine that has the history file:

    python3 tools/research/nfl_state_vs_kalshi.py --model tools/research/nfl_state_model.json --out ~/nfl_state_vs_kalshi.json

It opens combo_history.db READ-ONLY (sqlite URI mode=ro), never writes to it, never starts the watcher, places no order and
makes no network call. Pure standard library (the model is a dozen coefficients). It prints and writes ONE small set of
aggregates: counts, log loss, Brier, average gaps and hypothetical per-contract results with game-clustered ranges. No
tickers, dates or ids; a group with fewer than 20 samples or 10 games prints "hidden".

The question: for the live NFL moments the watcher recorded (sig_state: score, share of game left, possession; price_path:
Kalshi bid/ask; closes: the pre-game chance and the final outcome), is the model's chance closer to what happened than
Kalshi's mid price, and would buying when the model sits above the ask have made money AFTER the fee? One sample per game
per 10 minutes, so the numbers are not inflated by near-identical rows. A positive result is a reason to test further,
not a trading rule: the model is fit on 1999-latest nflverse seasons and has never seen these games.
"""
import argparse
import bisect
import json
import math
import random
import re
import sqlite3
import sys
from pathlib import Path

HIDE_N = 20
HIDE_GAMES = 10
BUCKET_S = 600               # one sample per ticker per 10 minutes
MAX_GAP_S = 120              # a price must be within 2 minutes of the state row
EDGES = (0.03, 0.05, 0.08)   # buy when the model is this far above the ask
HERE = Path(__file__).resolve().parent


def engine_fee_rate():
    for src in (HERE.parent.parent / "nfl_combo_planner.py", HERE.parent / "nfl_combo_planner.py"):
        try:
            hit = re.search(r"^FEE_RATE\s*=\s*([0-9.]+)", src.read_text(errors="ignore"), re.M)
        except OSError:
            continue
        if hit:
            return float(hit.group(1))
    return 0.07


FEE_RATE = engine_fee_rate()


def open_ro(path):
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError("history file not found")
    db = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-max(min(x, 30.0), -30.0)))


def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def model_chance(doc, me, opp, frac_left, poss, pre_win):
    """The exported model, team-centric (see its 'recipe'): my chance to win."""
    t = min(max(frac_left, 0.0), 1.0)
    d = float(me - opp)
    pre = logit(pre_win)
    f = [d / math.sqrt(t + 0.02), d, pre, pre * t, pre * math.sqrt(t), poss, poss * t, poss * math.sqrt(t)]
    return sigmoid(sum(c * x for c, x in zip(doc["coef"], f)))


def load_model(path):
    doc = json.loads(Path(path).read_text())
    if doc.get("model") != "nfl_state_logistic_v1" or len(doc.get("coef", [])) != 8:
        raise ValueError("not an nfl_state_logistic_v1 model file")
    return doc


def table_cols(db, name):
    return {r["name"] for r in db.execute(f"pragma table_info({name})")}


def fee(p):
    return FEE_RATE * p * (1 - p)


def collect(db, doc, tickers_like="KXNFL%"):
    """Samples: one per ticker per 10 minutes with all of: score state, a nearby bid/ask, the pre-game chance, the outcome."""
    need = {"sig_state": {"ts", "ticker", "me", "opp", "frac", "poss"}, "price_path": {"ts", "ticker", "bid", "ask"},
            "closes": {"ticker", "fair", "outcome"}}
    for t, cols in need.items():
        have = table_cols(db, t)
        if not have:
            return None, f"skipped: table {t} is missing"
        if not cols <= have:
            return None, f"skipped: table {t} lacks columns {sorted(cols - have)}"
    closes = {r["ticker"]: (r["fair"], r["outcome"]) for r in db.execute(
        "select ticker, fair, outcome from closes where ticker like ? and outcome in ('yes','no') and fair > 0", (tickers_like,))}
    if not closes:
        return None, "skipped: no settled NFL game in closes yet"
    paths = {}
    for r in db.execute("select ts, ticker, bid, ask from price_path where ticker like ? and bid is not null and ask is not null "
                        "order by ticker, ts", (tickers_like,)):
        if r["ticker"] in closes:
            paths.setdefault(r["ticker"], []).append((r["ts"], r["bid"], r["ask"]))
    out, last = [], {}
    for r in db.execute("select ts, ticker, me, opp, frac, poss from sig_state where ticker like ? and frac is not null "
                        "order by ticker, ts", (tickers_like,)):
        t = r["ticker"]
        if t not in closes or t not in paths:
            continue
        b = int(r["ts"] // BUCKET_S)
        if last.get(t) == b:
            continue
        pts = paths[t]
        i = bisect.bisect_left(pts, (r["ts"],))
        best = min((pts[j] for j in (i - 1, i) if 0 <= j < len(pts)), key=lambda x: abs(x[0] - r["ts"]), default=None)
        if best is None or abs(best[0] - r["ts"]) > MAX_GAP_S:
            continue
        bid, ask = best[1], best[2]
        if not (0 < bid < ask < 1):
            continue
        last[t] = b
        pre, outcome = closes[t]
        poss = 0 if r["poss"] is None else (1 if r["poss"] else -1)
        p = model_chance(doc, r["me"] or 0, r["opp"] or 0, r["frac"], poss, pre)
        out.append({"game": t.rsplit("-", 1)[0], "p": p, "mid": (bid + ask) / 2, "bid": bid, "ask": ask, "y": 1.0 if outcome == "yes" else 0.0})
    return out, None


def cluster_ci(rows, stat, n_boot=400, seed=0):
    """Mean of stat(row), 95% range from resampling whole games (rows of one game move together)."""
    by = {}
    for r in rows:
        by.setdefault(r["game"], []).append(stat(r))
    games = list(by.values())
    tot = sum(map(sum, games))
    n = sum(map(len, games))
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        pick = [games[rng.randrange(len(games))] for _ in games]
        vals.append(sum(map(sum, pick)) / max(1, sum(map(len, pick))))
    vals.sort()
    return tot / n, [vals[int(0.025 * n_boot)], vals[int(0.975 * n_boot) - 1]]


def ll(p, y):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def shown(rows):
    return len(rows) >= HIDE_N and len({r["game"] for r in rows}) >= HIDE_GAMES


def summarize(rows):
    res = {"samples": len(rows), "games": len({r["game"] for r in rows})}
    if not shown(rows):
        res["note"] = f"hidden: fewer than {HIDE_N} samples or {HIDE_GAMES} games"
        return res
    m_ll, m_ci = cluster_ci(rows, lambda r: ll(r["p"], r["y"]) - ll(r["mid"], r["y"]))
    res["logloss_model"] = round(sum(ll(r["p"], r["y"]) for r in rows) / len(rows), 5)
    res["logloss_kalshi_mid"] = round(sum(ll(r["mid"], r["y"]) for r in rows) / len(rows), 5)
    res["model_minus_kalshi_logloss"] = {"mean": round(m_ll, 5), "ci95": [round(m_ci[0], 5), round(m_ci[1], 5)],
                                         "reading": "negative means the model is closer to what happened"}
    res["brier_model"] = round(sum((r["p"] - r["y"]) ** 2 for r in rows) / len(rows), 5)
    res["brier_kalshi_mid"] = round(sum((r["mid"] - r["y"]) ** 2 for r in rows) / len(rows), 5)
    res["mean_model_minus_mid"] = round(sum(r["p"] - r["mid"] for r in rows) / len(rows), 4)
    buys = {}
    for e in EDGES:
        sub = [r for r in rows if r["p"] - r["ask"] >= e]
        key = f"buy_when_model_over_ask_by_{int(e * 100)}c"
        if not shown(sub):
            buys[key] = {"samples": len(sub), "games": len({r["game"] for r in sub}), "note": "hidden: too few"}
            continue
        mean, ci = cluster_ci(sub, lambda r: r["y"] - r["ask"] - fee(r["ask"]))
        buys[key] = {"samples": len(sub), "games": len({r["game"] for r in sub}), "mean_result_per_contract_after_fee": round(mean, 4),
                     "ci95": [round(ci[0], 4), round(ci[1], 4)]}
    res["hypothetical_buys"] = buys
    return res


def run(db_path, model_path):
    doc = load_model(model_path)
    db = open_ro(db_path)
    try:
        rows, why = collect(db, doc)
    finally:
        db.close()
    if rows is None:
        return {"status": why}
    out = {"status": "ok", "fee_rate": FEE_RATE, "model": doc["model"], "all": summarize(rows)}
    early = [r for r in rows if r["y"] in (0.0, 1.0)]
    mid_band = [r for r in early if 0.2 <= r["mid"] <= 0.8]
    out["kalshi_mid_between_20c_and_80c"] = summarize(mid_band)
    out["safe_to_send"] = "aggregates only: no tickers, dates, ids or balances"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="combo_history.db")
    ap.add_argument("--model", default=str(HERE / "nfl_state_model.json"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    try:
        res = run(a.db, a.model)
    except (FileNotFoundError, ValueError, sqlite3.Error) as err:
        print(f"skipped: {type(err).__name__}: {err}")
        return 1
    text = json.dumps(res, indent=1)
    print(text)
    if a.out:
        Path(a.out).expanduser().write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
