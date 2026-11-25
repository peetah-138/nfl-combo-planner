#!/usr/bin/env python3
"""News + game-context test: does Kalshi lag the books after injury news, and do context factors beat plain sharp fair?
Read-only, no network, no keys.

Pete runs one command, from the app folder, on the machine that has the history file:

    python3 tools/signal_events.py --out ~/signal_events_summary.json

It opens combo_history.db READ-ONLY (sqlite URI mode=ro), never writes to it, never starts the watcher, never places an
order and makes no network call. It reads only the three tables the news/context recorder fills (sig_news, sig_news_fu,
sig_ctx) and the closes table (how each game ended). It writes ONE small file of group aggregates and prints the same
numbers. There are no tickers, player or team names, game dates, ids or balances in the output; any group with fewer than
20 rows prints "n<20, hidden". When the file says "safe to send", it is.

Two questions (design: docs/EXIT_REPLAY.md, "News and context recorder"):

1. Event study. After an injury/lineup change, how far does Kalshi's bid move over the next 5/15/60 minutes, next to how
   far the sharp books' probability for the same game moved? The gap (books minus Kalshi) is the part of the news the
   market had not yet taken in. Reported by league, by "material" (an Out/Doubtful/Questionable/etc. status involved)
   and by horizon. The range is a bootstrap over whole games (news about one game moves together).
2. Residual test. Does a context factor (rest-day gap, back-to-back gap, games-in-7-days gap, travel miles, time zones
   crossed, dome, neutral site, wind, temperature, precipitation) explain what the sharp books' probability missed? For
   each factor, a one-step adjustment of the books' probability (in log-odds) is fitted on the first 70% of games by
   time and scored on the last 30%: Brier score of the plain books' probability minus the adjusted one (above 0 = the
   factor helped), with a game-level bootstrap range. A factor is only worth a look when that range is above 0 out of
   sample. Missing values (NULL) are skipped, never filled in.

Missing tables or columns never crash it: that part prints a clear "skipped: ..." line and the rest still runs.
"""
import argparse
import json
import math
import random
import sqlite3
import sys
from pathlib import Path

HIDE_N = 20                  # a group with fewer rows than this is never shown
HORIZONS = (5, 15, 60)
HERE = Path(__file__).resolve().parent
FACTORS = ("rest_diff", "b2b_diff", "g7_diff", "travel_k", "tz", "indoor", "neutral", "wind", "temp", "precip")


# ---------------------------------------------------------------- read-only helpers (same pattern as exit_replay.py)
def open_ro(path):
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError("history file not found")
    db = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def tables(db):
    return {r[0] for r in db.execute("select name from sqlite_master where type='table'")}


def columns(db, table):
    return {r[1] for r in db.execute(f"pragma table_info({table})")}


def need(db, table, cols):
    if table not in tables(db):
        return f"table {table} is missing"
    miss = [c for c in cols if c not in columns(db, table)]
    return f"table {table} lacks column(s) {', '.join(miss)}" if miss else None


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(q * len(xs))))]


def boot_mean(groups, boot, seed=1):
    """95% range of the mean of per-game (sum, count) pairs, resampling whole games."""
    n = len(groups)
    if n < 2:
        return None
    rng = random.Random(seed)
    idx = list(range(n))
    out = []
    for _ in range(boot):
        pick = rng.choices(idx, k=n)
        c = sum(groups[i][1] for i in pick)
        if c:
            out.append(sum(groups[i][0] for i in pick) / c)
    if len(out) < 20:
        return None
    return [round(quantile(out, 0.025), 4), round(quantile(out, 0.975), 4)]


def by_game(rows, val):
    g = {}
    for r in rows:
        s = g.setdefault(r["game"], [0.0, 0])
        s[0] += val(r)
        s[1] += 1
    return list(g.values())


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def r4(x):
    return None if x is None else round(x, 4)


# ---------------------------------------------------------------- 1. event study
def event_section(db, boot):
    why = need(db, "sig_news", ["id", "league", "material", "game_event", "ticker", "bid", "fair_book"]) or \
        need(db, "sig_news_fu", ["news_id", "horizon", "bid", "fair_book"])
    if why:
        return {"skipped": why}
    news = db.execute("select count(*) from sig_news").fetchone()[0]
    out = {"news_events": news if news >= HIDE_N else "n<20, hidden"}
    rows = db.execute(
        "select n.league l, n.material m, coalesce(n.game_event, n.ticker) game, f.horizon h, "
        "f.bid - n.bid dk, f.fair_book - n.fair_book ds "
        "from sig_news n join sig_news_fu f on f.news_id = n.id "
        "where n.bid is not null and f.bid is not null and n.fair_book is not null and f.fair_book is not null").fetchall()
    rows = [dict(r) for r in rows]
    if not rows:
        out["note"] = "no news event has both a starting price and a follow-up sample yet"
        return out
    cells = {}
    for league in sorted({r["l"] for r in rows if r["l"]}):
        for mat in (1, 0):
            for h in HORIZONS:
                grp = [r for r in rows if r["l"] == league and r["m"] == mat and r["h"] == h]
                if not grp:
                    continue
                name = f"{league} {'material' if mat else 'other'} +{h}min"
                if len(grp) < HIDE_N:
                    cells[name] = {"n": len(grp), "note": "n<20, hidden"}
                    continue
                for r in grp:
                    r["gap"] = r["ds"] - r["dk"]
                cells[name] = {
                    "n": len(grp), "games": len({r["game"] for r in grp}),
                    "kalshi_bid_change": r4(mean([r["dk"] for r in grp])),
                    "sharp_prob_change": r4(mean([r["ds"] for r in grp])),
                    "gap_sharp_minus_kalshi": r4(mean([r["gap"] for r in grp])),
                    "gap_95": boot_mean(by_game(grp, lambda r: r["gap"]), boot, seed=h + mat)}
    out["cells"] = cells
    out["reading"] = ("gap above 0 with a range above 0 = the books moved more than Kalshi's bid did; it is evidence of a "
                      "lag only if it survives the bid-ask gap and fee, which this report does not test")
    return out


# ---------------------------------------------------------------- 2. residual test
def load_context(db):
    need_cols = ["ts", "phase", "league", "game_event", "home_ticker", "home_fair", "home_rest", "away_rest", "home_b2b",
                 "away_b2b", "home_g7", "away_g7", "away_travel_mi", "away_tz", "indoor", "neutral", "wx_wind", "wx_temp",
                 "wx_precip"]
    why = need(db, "sig_ctx", need_cols) or need(db, "closes", ["ticker", "outcome"])
    if why:
        return None, why
    rows = db.execute(
        "select c.ts ts, c.league l, c.game_event game, c.home_fair fair, cl.outcome oc, c.home_rest hr, c.away_rest ar, "
        "c.home_b2b hb, c.away_b2b ab, c.home_g7 hg, c.away_g7 ag, c.away_travel_mi tr, c.away_tz tz, c.indoor indoor, "
        "c.neutral neutral, c.wx_wind wind, c.wx_temp temp, c.wx_precip precip "
        "from sig_ctx c join closes cl on cl.ticker = c.home_ticker "
        "where c.phase = 'pre2h' and c.home_fair > 0 and c.home_fair < 1 and cl.outcome in ('yes', 'no')").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        diff = lambda a, b: None if d[a] is None or d[b] is None else d[a] - d[b]
        d["y"] = 1.0 if d["oc"] == "yes" else 0.0
        d["x"] = {"rest_diff": diff("hr", "ar"), "b2b_diff": diff("hb", "ab"), "g7_diff": diff("hg", "ag"),
                  "travel_k": None if d["tr"] is None else d["tr"] / 1000.0, "tz": d["tz"],
                  "indoor": d["indoor"], "neutral": d["neutral"], "wind": d["wind"], "temp": d["temp"],
                  "precip": d["precip"]}
        out.append(d)
    return out, None


def fit_step(train, f):
    """One Newton step from the plain books' probability: the slope of (y - p) on the factor, in log-odds."""
    num = sum(r["x"][f] * (r["y"] - r["fair"]) for r in train)
    den = sum(r["x"][f] ** 2 * r["fair"] * (1 - r["fair"]) for r in train)
    return num / den if den > 0 else 0.0


def adjusted(p, b, x):
    z = math.log(p / (1 - p)) + b * x
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


def residual_section(db, boot, train_frac=0.7):
    rows, why = load_context(db)
    if why:
        return {"skipped": why}
    out = {"rows_with_outcome": len(rows) if len(rows) >= HIDE_N else "n<20, hidden"}
    if len(rows) < HIDE_N:
        return out
    leagues = {}
    for league in sorted({r["l"] for r in rows if r["l"]}):
        grp = [r for r in rows if r["l"] == league]
        if len(grp) < HIDE_N:
            leagues[league] = {"n": len(grp), "note": "n<20, hidden"}
            continue
        first = {}
        for r in grp:
            first[r["game"]] = min(first.get(r["game"], r["ts"]), r["ts"])
        order = sorted(first, key=first.get)
        cut = int(len(order) * train_frac)
        train_g, test_g = set(order[:cut]), set(order[cut:])
        cells = {"n": len(grp), "games": len(order), "plain_brier": r4(mean([(r["y"] - r["fair"]) ** 2 for r in grp]))}
        fac = {}
        for f in FACTORS:
            have = [r for r in grp if r["x"][f] is not None]
            if len(have) < HIDE_N:
                fac[f] = {"n": len(have), "note": "n<20, hidden" if have else "no values recorded yet"}
                continue
            tr = [r for r in have if r["game"] in train_g]
            te = [r for r in have if r["game"] in test_g]
            if len(tr) < HIDE_N or len(te) < HIDE_N or len({r["game"] for r in te}) < 5:
                fac[f] = {"n": len(have), "note": "not enough rows in the first 70% / last 30% of games to score"}
                continue
            if len({r["x"][f] for r in tr}) < 2:
                fac[f] = {"n": len(have), "note": "factor never varies in the first 70%"}
                continue
            b = fit_step(tr, f)
            gain = lambda r: (r["y"] - r["fair"]) ** 2 - (r["y"] - adjusted(r["fair"], b, r["x"][f])) ** 2
            fac[f] = {"n": len(have), "test_n": len(te), "test_games": len({r["game"] for r in te}),
                      "slope_logodds_per_unit": round(b, 4),
                      "brier_gain_out_of_sample": r4(mean([gain(r) for r in te])),
                      "brier_gain_95": boot_mean(by_game([dict(r, g=gain(r)) for r in te], lambda r: r["g"]), boot, seed=3)}
        cells["factors"] = fac
        leagues[league] = cells
    out["leagues"] = leagues
    out["reading"] = ("a factor is worth a look only when brier_gain_95 is entirely above 0 on the last 30% of games; "
                      "many factors are tried, so one lone hit is more likely luck than signal")
    return out


# ---------------------------------------------------------------- output
def table_counts(db):
    out = {}
    for t in ("sig_news", "sig_news_fu", "sig_ctx", "closes"):
        out[t] = db.execute(f"select count(*) from {t}").fetchone()[0] if t in tables(db) else "missing"
    return out


def show(label, obj, depth=0):
    pad = "  " * depth
    if isinstance(obj, dict):
        print(f"{pad}{label}:")
        for k, v in obj.items():
            show(k, v, depth + 1)
    else:
        print(f"{pad}{label}: {obj}")


def run(path, out_path, boot):
    try:
        db = open_ro(path)
        db.execute("select count(*) from sqlite_master").fetchone()      # a file that is not a database fails here
    except (OSError, sqlite3.Error) as err:
        print(f"cannot open the history file read-only: {type(err).__name__}")
        return 2, None
    summary = {"what": "news + context test, aggregates only"}
    try:
        summary["table_rows"] = table_counts(db)
        for key, fn in (("event_study", event_section), ("residual_test", residual_section)):
            try:
                summary[key] = fn(db, boot)
            except sqlite3.Error as err:
                summary[key] = {"skipped": f"database error ({type(err).__name__}); is the file a combo history file?"}
    finally:
        db.close()
    for k, v in summary.items():
        show(k, v)
    if out_path:
        p = Path(out_path).expanduser()
        p.write_text(json.dumps(summary, indent=1))
        print(f"\nwrote {p}")
    print("safe to send: group totals only, no tickers, names, dates, ids or balances.")
    return 0, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=None, help="history file (default: combo_history.db next to this script or the app, then ~/combowatch)")
    ap.add_argument("--out", default=None, help="where to write the summary file")
    ap.add_argument("--boot", type=int, default=400, help="bootstrap rounds (default 400)")
    a = ap.parse_args(argv)
    path = a.db
    if not path:
        for cand in (HERE / "combo_history.db", HERE.parent / "combo_history.db", Path("~/combowatch/combo_history.db").expanduser(),
                     Path("combo_history.db")):
            if cand.is_file():
                path = str(cand)
                break
    if not path:
        print("no history file found: pass --db <file> (run this where the app's combo_history.db lives)")
        return 2
    code, _ = run(path, a.out, max(a.boot, 50))
    return code


if __name__ == "__main__":
    sys.exit(main())
