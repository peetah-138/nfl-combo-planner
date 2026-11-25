#!/usr/bin/env python3
"""ESPN win chance scorecard (issue #483): is ESPN's live win chance worth anything, per league? Read-only, no network,
no keys, no orders.

    python3 tools/espn_wp_scorecard.py --out ~/espn_wp_scorecard.json

It opens combo_history.db READ-ONLY (sqlite URI mode=ro) and reads the recorder's tables (wp_shadow, wp_outcome, and, for
coverage, wp_hist). It writes ONE small file of per-league aggregates and prints the same numbers: no tickers, game ids,
dates or dollar balances. Any group with fewer than 20 games prints "n<20, hidden".

For every league it compares four chances for the same rows and the same settled games: ESPN's own (wp), Kalshi's mid, our
pure model, and today's 50/50 blend of model and wp (before the live calibration):
  1. Brier score and log score against the final outcome (lower is better), with a game-level bootstrap 95% range.
  2. Net dollars per $1 staked, after the entry fee (the engine's FEE_RATE) and the spread (a buy fills at the ask), for one
     simple rule: buy a side once when its chance is at least X above the ask, hold to settlement. X is picked on the first
     70% of games by time and scored on the last 30% (out of sample). The bootstrap resamples whole games.
Pass bar (docs/EXIT_REPLAY.md style): a source passes in a league when, on the held-out 30%, it beats the blend by at least
1 cent per $1 staked, its own net is above 0 and its 95% range is above 0. It only counts when it passes in 2 or more
leagues. Coverage (does the league carry wp at all, how old its last play is) is reported too.
Missing tables or columns never crash it: that part prints "skipped: ..." and the rest still runs.
"""
import argparse
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exit_replay as X  # noqa: E402  (shares the read-only opener, the fee rate and the small statistics)

HIDE_N = X.HIDE_N
SOURCES = ("wp", "mid", "model", "blend")
GRID = (0.02, 0.04, 0.06, 0.08, 0.10, 0.15)       # "buy when it is this far above the ask"
PASS_CENTS = 0.01                                 # beats the blend by at least 1 cent per $1 staked
PASS_LEAGUES = 2
EPS = 1e-4


def fee(p):
    return X.FEE_RATE * p * (1 - p)


def game_of(ticker):
    """One game's two sides share this (the market's event part): rows in one game move together in the bootstrap."""
    return str(ticker).rsplit("-", 1)[0]


def load(db):
    """Rows with an outcome: dicts with game, ticker, ts, league, p (the four chances), ask, y, play_age."""
    why = X.need(db, "wp_shadow", ["ts", "ticker", "league", "wp", "model", "blend", "bid", "ask", "mid", "play_age"])
    if why:
        return None, why
    why = X.need(db, "wp_outcome", ["ticker", "outcome"])
    if why:
        return None, why
    out = []
    for r in db.execute("select s.ts, s.ticker, s.league, s.wp, s.model, s.blend, s.mid, s.ask, s.play_age, o.outcome "
                        "from wp_shadow s join wp_outcome o on o.ticker = s.ticker order by s.ts"):
        if r["outcome"] not in ("yes", "no"):
            continue
        out.append({"game": game_of(r["ticker"]), "ticker": r["ticker"], "ts": r["ts"], "league": r["league"],
                    "p": {"wp": r["wp"], "mid": r["mid"], "model": r["model"], "blend": r["blend"]},
                    "ask": r["ask"], "y": 1.0 if r["outcome"] == "yes" else 0.0, "age": r["play_age"]})
    return out, None


def common(rows):
    """Only rows where all four chances and the ask exist, so every source is scored on the same rows."""
    return [r for r in rows if r["ask"] and 0 < r["ask"] < 1 and all(r["p"][s] is not None for s in SOURCES)]


def bootstrap(games, stat, boot, seed=1):
    """95% range of stat(list of per-game records) resampling whole games, or None when there is too little to say."""
    n = len(games)
    if n < 2:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(boot):
        v = stat([games[i] for i in rng.choices(range(n), k=n)])
        if v is not None:
            vals.append(v)
    if len(vals) < 20:
        return None
    return [round(X.quantile(vals, 0.025), 4), round(X.quantile(vals, 0.975), 4)]


# ---------------------------------------------------------------- scores
def score_rows(rows, src):
    """Per game: [sum of squared error, sum of log loss, rows]."""
    g = {}
    for r in rows:
        p = min(max(r["p"][src], EPS), 1 - EPS)
        s = g.setdefault(r["game"], [0.0, 0.0, 0])
        s[0] += (p - r["y"]) ** 2
        s[1] += -math.log(p if r["y"] else 1 - p)
        s[2] += 1
    return list(g.values())


def mean_of(idx):
    def f(gs):
        n = sum(g[2] for g in gs)
        return sum(g[idx] for g in gs) / n if n else None
    return f


def scores_section(rows, boot):
    out = {}
    for src in SOURCES:
        gs = score_rows(rows, src)
        out[src] = {"brier": round(mean_of(0)(gs), 4), "brier_range": bootstrap(gs, mean_of(0), boot),
                    "logscore": round(mean_of(1)(gs), 4), "log_range": bootstrap(gs, mean_of(1), boot)}
    return out


# ---------------------------------------------------------------- the buy rule
def bets(rows, src, x):
    """One bet per ticker: the first row where the source's chance is at least x above the ask. Per game:
    [profit, staked] in dollars for one contract each (stake = ask + entry fee, held to settlement)."""
    done, g = set(), {}
    for r in rows:
        if r["ticker"] in done or r["p"][src] - r["ask"] < x:
            continue
        done.add(r["ticker"])
        cost = r["ask"] + fee(r["ask"])
        s = g.setdefault(r["game"], [0.0, 0.0])
        s[0] += r["y"] - cost
        s[1] += cost
    return g


def per_dollar(gs):
    st = sum(g[1] for g in gs)
    return sum(g[0] for g in gs) / st if st > 0 else None


def rule_games(rows, src, x, games):
    """The per-game [profit, staked] list over exactly `games` (a game with no bet counts as [0, 0])."""
    b = bets(rows, src, x)
    return [b.get(g, [0.0, 0.0]) for g in games]


def split(rows):
    """Games by first row time; the first 70% train, the last 30% test."""
    first = {}
    for r in rows:
        first.setdefault(r["game"], r["ts"])
    order = sorted(first, key=lambda g: first[g])
    cut = int(len(order) * 0.7)
    return order[:cut], order[cut:]


def diff_range(a, b, boot, seed=2):
    """95% range of net-per-$1(a) minus net-per-$1(b) over the SAME resampled games."""
    n = len(a)
    if n < 2:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(boot):
        ix = rng.choices(range(n), k=n)
        ra, rb = per_dollar([a[i] for i in ix]), per_dollar([b[i] for i in ix])
        if ra is not None and rb is not None:
            vals.append(ra - rb)
    return [round(X.quantile(vals, 0.025), 4), round(X.quantile(vals, 0.975), 4)] if len(vals) >= 20 else None


def best_x(rows, src, games):
    best = None
    for x in GRID:
        v = per_dollar(rule_games(rows, src, x, games))
        if v is not None and (best is None or v > best[1]):
            best = (x, v)
    return best[0] if best else None


def trade_section(rows, boot):
    tr, te = split(rows)
    by_game = {}
    for r in rows:
        by_game.setdefault(r["game"], []).append(r)
    out = {"train_games": len(tr), "test_games": len(te), "rule": "buy once at the ask when the chance is X above it, "
           "hold to settlement; fee = engine fee on the ask; X chosen on the first 70% of games", "sources": {}}
    xb = best_x(rows, "blend", tr)
    base = rule_games(rows, "blend", xb, te) if xb is not None else None
    for src in ("wp", "mid", "model", "blend"):
        x = best_x(rows, src, tr)
        if x is None or base is None:
            out["sources"][src] = {"skipped": "no bet fired in the training games"}
            continue
        gs = rule_games(rows, src, x, te)
        net, rng = per_dollar(gs), bootstrap(gs, per_dollar, boot)
        d = diff_range(gs, base, boot) if src != "blend" else None
        bd = (net - per_dollar(base)) if (net is not None and per_dollar(base) is not None) else None
        nb = sum(1 for g in gs if g[1] > 0)
        enough = nb >= HIDE_N                  # too few bets: no number is shown and it cannot pass
        out["sources"][src] = {
            "x_cents": round(x * 100), "bets": nb if enough else "n<20, hidden", "net_per_dollar": None if net is None else round(net, 4),
            "range": rng, "vs_blend": None if bd is None or src == "blend" else round(bd, 4), "vs_blend_range": d,
            "passes": bool(src in ("wp", "model", "mid") and enough and d and d[0] > 0 and net is not None and net > 0 and rng and rng[0] > 0
                           and bd is not None and bd >= PASS_CENTS)}
    return out


# ---------------------------------------------------------------- coverage
def coverage(db):
    """Per league: does it carry wp at all, and how old is the last play (median / 90th percentile of the seconds we had
    watched the play). Counts hidden under 20 games; the plain yes/no is always shown (it names no game)."""
    why = X.need(db, "wp_shadow", ["ts", "ticker", "league", "wp", "play_age"])
    if why:
        return {"skipped": why}
    leagues = {}
    for r in db.execute("select league, ticker, wp, play_age from wp_shadow"):
        s = leagues.setdefault(r["league"], {"games": set(), "wp_games": set(), "n": 0, "n_wp": 0, "ages": []})
        s["games"].add(game_of(r["ticker"]))
        s["n"] += 1
        if r["wp"] is not None:
            s["wp_games"].add(game_of(r["ticker"]))
            s["n_wp"] += 1
            if r["play_age"] is not None:
                s["ages"].append(r["play_age"])
    out = {}
    for lg, s in sorted(leagues.items()):
        row = {"has_wp": bool(s["n_wp"])}
        if len(s["games"]) < HIDE_N:
            row["detail"] = "n<20, hidden"
        else:
            row.update(games=len(s["games"]), share_rows_with_wp=round(s["n_wp"] / s["n"], 3))
            if s["ages"]:
                row.update(play_age_median_s=round(X.quantile(s["ages"], 0.5), 1), play_age_p90_s=round(X.quantile(s["ages"], 0.9), 1))
        out[lg] = row
    if "wp_hist" in X.tables(db) and not X.need(db, "wp_hist", ["league", "game"]):
        hist = {}
        for r in db.execute("select league, count(distinct game) g from wp_hist group by league"):
            hist[r["league"]] = {"has_history": True} if r["g"] < HIDE_N else {"has_history": True, "games": r["g"]}
        for lg, h in hist.items():
            out.setdefault(lg, {}).update(h)
    return out


# ---------------------------------------------------------------- the run
def run(path, out_path=None, boot=400):
    db = X.open_ro(path)
    res = {"note": "aggregates only; groups under 20 games hidden; read-only", "fee_rate": X.FEE_RATE,
           "pass_bar": f"beats the blend by >= {int(PASS_CENTS * 100)}c per $1, net > 0 with the 95% range above 0, "
                       f"in {PASS_LEAGUES}+ leagues (held-out last 30% of games)", "coverage": coverage(db), "leagues": {}}
    if X.FEE_NOTE:
        res["fee_note"] = X.FEE_NOTE
    rows, why = load(db)
    if why:
        res["skipped"] = why
    else:
        rows = common(rows)
        by = {}
        for r in rows:
            by.setdefault(r["league"], []).append(r)
        passing = {s: [] for s in ("wp", "mid", "model")}
        for lg, rs in sorted(by.items()):
            n_games = len({r["game"] for r in rs})
            if n_games < HIDE_N:
                res["leagues"][lg] = {"detail": "n<20, hidden"}
                continue
            sec = {"games": n_games, "scores": scores_section(rs, boot), "trade": trade_section(rs, boot)}
            if sec["trade"]["test_games"] < HIDE_N:
                sec["trade"] = {"detail": "held-out games n<20, hidden"}
            else:
                for s, v in sec["trade"]["sources"].items():
                    if v.get("passes"):
                        passing[s].append(lg)
            res["leagues"][lg] = sec
        res["verdict"] = {s: {"passes_in": v, "passes": len(v) >= PASS_LEAGUES} for s, v in passing.items()}
        names = {"wp": "ESPN win chance", "mid": "Kalshi mid", "model": "our model"}
        res["summary"] = [f"{names[s]}: " + (f"passes the bar in {', '.join(v['passes_in'])}: worth a separate, Pete-approved look"
                          if v["passes"] else "does NOT pass the bar" + (f" (only in {', '.join(v['passes_in'])})" if v["passes_in"] else ""))
                          for s, v in res["verdict"].items()]
        res["summary"].append("Kalshi mid can never fire a buy (it sits at or below the ask): that is expected, not a fault.")
    db.close()
    if out_path:
        Path(out_path).expanduser().write_text(json.dumps(res, indent=1))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="~/combowatch/combo_history.db", help="the history file (opened read-only)")
    ap.add_argument("--out", help="write the aggregates here")
    ap.add_argument("--boot", type=int, default=400, help="bootstrap rounds (default 400)")
    a = ap.parse_args(argv)
    try:
        res = run(a.db, a.out, a.boot)
    except FileNotFoundError as err:
        print(f"skipped: {err}")
        return 1
    X.show("espn wp scorecard", res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
