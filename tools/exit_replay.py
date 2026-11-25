#!/usr/bin/env python3
"""Early-exit value test, phase 1: replay exit rules on the app's own history. Read-only, no network, no keys.

Pete runs one command, from the app folder, on the machine that has the history file:

    python3 tools/exit_replay.py --out ~/exit_replay_summary.json

It opens combo_history.db READ-ONLY (sqlite URI mode=ro), never writes to it, never starts the watcher, never places
an order and makes no network call. It writes ONE small file of group aggregates (counts, averages, ranges) and prints
the same numbers. There are no tickers, game dates, ids, order numbers or balances in the output; any group with fewer
than 20 bets prints "n<20, hidden". When the file says "safe to send", it is.

Second mode, one question only (what do combos really pay in entry fees?):

    python3 tools/exit_replay.py --combo-fee

The question (design: docs/EXIT_REPLAY.md): for bets the app WOULD buy (price below its fair), how often and by how much
does selling at the bid before the end beat holding to settlement, AFTER the entry fee, the exit fee and the bid-ask
gap? Singles are replayed on price_path. Combos have no price path: they are measured from Kalshi's real buyback
offers (offers table) and reported apart, with their own confidence range. Exit rules are fixed in advance:
+3c / +5c / +10c over all-in cost, sell at our fair, sell at one hour or 15 minutes before the start if the bid is
above cost, or hold. The peak is never reported as a result. Ranges are a game-level bootstrap (rows in one game move
together); the best rule is picked on the first 70% of games by time and scored on the last 30%.

Missing tables or columns never crash it: that part prints a clear "skipped: ..." line and the rest still runs.
"""
import argparse
import json
import math
import random
import re
import sqlite3
import statistics
import sys
from pathlib import Path

HIDE_N = 20                  # a group with fewer bets than this is never shown
HIDE_FEE_N = 3               # --combo-fee: fewer fills than this per kind are never shown
BUCKETS = ((0.10, 0.30, "10-30c"), (0.30, 0.60, "30-60c"), (0.60, 0.90, "60-90c"))
RULES = ("+3c", "+5c", "+10c", "fair", "T-1h", "T-15m")
EXIT_FEE_N = 10              # contracts assumed for the per-order fee rounding (a typical $5 order)
HERE = Path(__file__).resolve().parent


def engine_fee_rate():
    """Kalshi's fee rate from the engine's own FEE_RATE line (read as text: importing the engine would run it)."""
    for src in (HERE.parent / "nfl_combo_planner.py", HERE / "nfl_combo_planner.py"):
        try:
            hit = re.search(r"^FEE_RATE\s*=\s*([0-9.]+)", src.read_text(errors="ignore"), re.M)
        except OSError:
            continue
        if hit:
            return float(hit.group(1))
    return None


FEE_RATE = engine_fee_rate()
FEE_NOTE = None
if FEE_RATE is None:                                         # no engine file beside the script: Kalshi's published 7%
    FEE_RATE, FEE_NOTE = 0.07, "engine file not found next to this script: used Kalshi's standard 0.07 fee rate"


def fee_per_contract(p, n=None):
    """The engine's single_fee: FEE_RATE x p x (1-p) a contract; with n, the order's fee rounded up to the cent."""
    f = FEE_RATE * p * (1 - p)
    if not n or n <= 0:
        return f
    return math.ceil(round(n * f * 100, 6)) / 100 / n


# ---------------------------------------------------------------- the database, read-only
def open_ro(path):
    """Open the history file read-only. A write through this connection fails: 'attempt to write a readonly database'."""
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
    """None when the table has all the columns, else a plain reason it can't be used."""
    if table not in tables(db):
        return f"table {table} is missing"
    miss = [c for c in cols if c not in columns(db, table)]
    return f"table {table} lacks column(s) {', '.join(miss)}" if miss else None


# ---------------------------------------------------------------- small statistics
def bucket(price):
    for lo, hi, name in BUCKETS:
        if lo <= price < hi:
            return name
    return None


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(q * len(xs))))]


def ratio_ci(games, a_idx, b_idx, d_idx, boot, seed=1):
    """95% range of 100*(sum a - sum b)/sum d, resampling whole games. games: list of per-game sum lists."""
    n = len(games)
    if n < 2:
        return None
    rng = random.Random(seed)
    out = []
    ar = list(range(n))
    for _ in range(boot):
        pick = rng.choices(ar, k=n)
        a = sum(games[i][a_idx] for i in pick)
        b = sum(games[i][b_idx] for i in pick) if b_idx is not None else 0.0
        d = sum(games[i][d_idx] for i in pick)
        if d > 0:
            out.append(100.0 * (a - b) / d)
    if len(out) < 20:
        return None
    return [round(quantile(out, 0.025), 2), round(quantile(out, 0.975), 2)]


def per_game(rows, keys):
    """Sum each of keys over a game's rows: [(sum of key1, sum of key2, ...)], one entry a game."""
    g = {}
    for r in rows:
        s = g.setdefault(r["game"], [0.0] * len(keys))
        for i, k in enumerate(keys):
            s[i] += r[k]
    return list(g.values())


# ---------------------------------------------------------------- singles: the replay
def load_buys(db, gates):
    """The singles the app would buy (ask below its fair): the paper book, then real ledger buys. Each is
    {game, ts, ask, fair, won, ticker, kind, league}. A void or half-paid result is left out."""
    buys, seen = [], set()
    why = need(db, "sb_paper", ["bet", "ts", "league", "kind", "price", "fair", "plain"])
    if why:
        gates["sb_paper"] = "skipped: " + why
    else:
        have_game = "game" in columns(db, "sb_paper")
        sel = "select bet, ts, league, kind, price, fair, plain" + (", game" if have_game else "") + \
              " from sb_paper where kind in ('single','line') and price is not null and fair is not null"
        for r in db.execute(sel):
            try:
                tk = json.loads(r["bet"])
                t = tk[0] if isinstance(tk, list) and tk else str(r["bet"])
            except (ValueError, TypeError):
                t = str(r["bet"])
            # `plain` is what the bet made held to the end at the flat $5 test stake: pays-5 if it won, -5 if it lost,
            # empty until settled (a void never gets a result). (`outcome` is scaled by the graduated stake and is 0
            # for every bet that was never staked, so it is NOT used: it would read those as losses.)
            p, f, o = r["price"], r["fair"], r["plain"]
            if not (0.01 < p < 0.99) or f is None or f <= p or o is None or o == 0:
                continue
            won = o > 0
            game = (r["game"] if have_game and r["game"] else None) or "-".join(t.split("-")[:2])
            buys.append({"game": game, "ts": r["ts"], "ask": p, "fair": f, "won": won, "ticker": t,
                         "kind": r["kind"], "league": r["league"] or "?"})
            seen.add(t)
    return buys


def load_ledger_buys(db, buys, gates):
    """Real single buys from the ledger: entry = the ask in price_path just before/after the buy (no stored price)."""
    why = need(db, "ledger", ["ticker", "kind", "league", "side", "opened", "status", "outcome"])
    if why or need(db, "price_path", ["ts", "ticker", "ask"]):
        gates["ledger"] = "skipped: " + (why or "price_path is missing")
        return
    seen = {b["ticker"] for b in buys}
    n = 0
    no_side = 0
    for r in db.execute("select ticker, kind, league, side, opened, status, outcome from ledger "
                        "where kind in ('win','spread','total') and opened is not null"):
        if r["ticker"] in seen:
            continue
        if (r["side"] or "yes") != "yes":                    # price_path holds the YES bid/ask: a NO position is left out
            no_side += 1
            continue
        res = r["outcome"] if r["outcome"] in ("won", "lost") else r["status"] if r["status"] in ("won", "lost") else None
        if not res:
            continue
        near = db.execute("select ask from price_path where ticker=? and ts between ? and ? and ask is not null "
                          "order by abs(ts-?) limit 1", (r["ticker"], r["opened"] - 600, r["opened"] + 600,
                                                        r["opened"])).fetchone()
        if not near or not 0.01 < near["ask"] < 0.99:
            continue
        buys.append({"game": "-".join(r["ticker"].split("-")[:2]), "ts": r["opened"], "ask": near["ask"],
                     "fair": None, "won": res == "won", "ticker": r["ticker"], "kind": "real " + (r["kind"] or ""),
                     "league": r["league"] or "?"})
        n += 1
    gates["real_buys_with_entry_price"] = n
    gates["real_no_side_buys_left_out"] = no_side


def replay_buy(path, buy, kick):
    """Per-contract P&L of every rule for one buy. path: [(ts, bid, ask, score)] after the buy, in time order.
    Entry at the ask (all-in with the entry fee); exits at the bid less the exit fee; no trigger = settle."""
    c = buy["ask"] + fee_per_contract(buy["ask"], EXIT_FEE_N)
    hold = (1.0 if buy["won"] else 0.0) - c

    def sell(bid):
        return bid - fee_per_contract(bid, EXIT_FEE_N) - c
    res = {"hold": hold}
    for name, x in (("+3c", 0.03), ("+5c", 0.05), ("+10c", 0.10)):
        hit = next((r for r in path if r[1] is not None and r[1] >= c + x), None)
        res[name] = sell(hit[1]) if hit else hold
    if buy["fair"]:
        hit = next((r for r in path if r[1] is not None and r[1] >= buy["fair"]), None)
        res["fair"] = sell(hit[1]) if hit else hold
    else:
        res["fair"] = None                                   # a real buy: the fair then was not stored
    for name, lead in (("T-1h", 3600), ("T-15m", 900)):
        res[name] = hold
        if kick:
            hit = next((r for r in path if r[0] >= kick - lead), None)
            if hit and hit[0] <= kick and hit[1] is not None and hit[1] > c:
                res[name] = sell(hit[1])
    return c, res


def pre_kick_stats(path, buy, kick, acc):
    """Fills the measured replacements for the placeholders from one buy's path."""
    pre = [r for r in path if (kick and r[0] < kick) or (not kick and not r[3])]
    live = [r for r in path if (kick and r[0] >= kick) or (not kick and r[3])]
    for rows, key in ((pre, "gap_pre"), (live, "gap_live")):
        for _, bid, ask, _s in rows:
            if bid is not None and ask is not None and ask >= bid:
                acc[key].append(ask - bid)
    if pre and pre[-1][1] is not None:
        acc["drift"].append((pre[-1][1] - buy["ask"], (buy["fair"] - buy["ask"]) if buy["fair"] else None))
    mids = [(r[0], (r[1] + r[2]) / 2) for r in pre if r[1] is not None and r[2] is not None]
    nd = statistics.NormalDist()
    for (t0, m0), (t1, m1) in zip(mids, mids[1:]):
        dt = t1 - t0
        if 60 <= dt <= 6 * 3600:
            z0 = nd.inv_cdf(min(max(m0, 0.02), 0.98))
            z1 = nd.inv_cdf(min(max(m1, 0.02), 0.98))
            acc["dz"].append(((z1 - z0) / math.sqrt(dt / 86400.0), m1 - m0, dt))


def table_counts(db):
    out = {}
    for t in ("price_path", "sb_paper", "ledger", "sell_log", "offers", "exit_shadow", "closes", "close_mids", "quotes",
              "ticks", "fairs", "live_fairs", "comeback_shadow", "bets"):
        if t in tables(db):
            out[t] = db.execute(f"select count(*) from {t}").fetchone()[0]
        else:
            out[t] = "missing"
    return out


def group_result(rows, boot, train_frac=0.7):
    """One group's table: each rule's cents per dollar staked and its edge over hold, plus the out-of-sample score."""
    if len(rows) < HIDE_N:
        return {"n": len(rows), "note": "n<20, hidden"}
    names = ("hold",) + RULES
    usable = [r for r in rows if all(r["pnl"].get(k) is not None for k in names)]
    out = {"n": len(rows), "games": len({r["game"] for r in rows})}
    if len(usable) < HIDE_N:
        usable = rows
        names = ("hold",) + tuple(k for k in RULES if all(r["pnl"].get(k) is not None for r in rows))
    cells = {}
    for k in names:
        den = sum(r["cost"] for r in usable)
        cell = {"cents_per_dollar": round(100 * sum(r["pnl"][k] for r in usable) / den, 2)}
        if k != "hold":
            gm = per_game([dict(game=r["game"], a=r["pnl"][k], b=r["pnl"]["hold"], c=r["cost"]) for r in usable],
                          ("a", "b", "c"))
            cell["minus_hold"] = round(100 * (sum(r["pnl"][k] for r in usable) - sum(r["pnl"]["hold"] for r in usable))
                                       / den, 2)
            cell["minus_hold_95"] = ratio_ci(gm, 0, 1, 2, boot)
        cells[k] = cell
    out["rules"] = cells
    out["peak_note"] = "the peak is never reported as a result"
    # out-of-sample: choose the rule on the first 70% of games by time, score it on the last 30%
    first = {}
    for r in usable:
        first[r["game"]] = min(first.get(r["game"], r["ts"]), r["ts"])
    order = sorted(first, key=first.get)
    cut = int(len(order) * train_frac)
    train_g, test_g = set(order[:cut]), set(order[cut:])
    train = [r for r in usable if r["game"] in train_g]
    test = [r for r in usable if r["game"] in test_g]
    if len(train) >= HIDE_N and len(test) >= HIDE_N and len(test_g) >= 5:
        cand = [k for k in names if k != "hold"]
        best = max(cand, key=lambda k: sum(r["pnl"][k] for r in train) / sum(r["cost"] for r in train))
        den = sum(r["cost"] for r in test)
        gm = per_game([dict(game=r["game"], a=r["pnl"][best], b=r["pnl"]["hold"], c=r["cost"]) for r in test],
                      ("a", "b", "c"))
        out["out_of_sample"] = {
            "rule_chosen_on_first_70pct": best, "test_n": len(test), "test_games": len(test_g),
            "best_rule_cents_per_dollar": round(100 * sum(r["pnl"][best] for r in test) / den, 2),
            "hold_cents_per_dollar": round(100 * sum(r["pnl"]["hold"] for r in test) / den, 2),
            "best_minus_hold_cents_per_dollar": round(
                100 * (sum(r["pnl"][best] for r in test) - sum(r["pnl"]["hold"] for r in test)) / den, 2),
            "best_minus_hold_95": ratio_ci(gm, 0, 1, 2, boot, seed=2)}
    else:
        out["out_of_sample"] = "not enough bets or games in the last 30% to score a rule"
    return out


def singles_section(db, boot, gates):
    buys = load_buys(db, gates)
    load_ledger_buys(db, buys, gates)
    if need(db, "price_path", ["ts", "ticker", "bid", "ask"]):
        return {"skipped": "table price_path is missing or lacks bid/ask: no singles replay"}
    kicks = {}
    if not need(db, "closes", ["ticker", "kick"]):
        kicks = {r["ticker"]: r["kick"] for r in db.execute("select ticker, kick from closes where kick is not null")}
    has_score = "score" in columns(db, "price_path")
    rows, acc = [], {"gap_pre": [], "gap_live": [], "drift": [], "dz": []}
    with_path = with_spread = 0
    for b in buys:
        sel = "select ts, bid, ask" + (", score" if has_score else ", null as score") + \
              " from price_path where ticker=? and ts>? order by ts"
        path = [(r["ts"], r["bid"], r["ask"], r["score"]) for r in db.execute(sel, (b["ticker"], b["ts"]))]
        if len(path) >= 10:
            with_path += 1
        if any(p[1] is not None and p[2] is not None for p in path):
            with_spread += 1
        if not path:
            continue
        kick = kicks.get(b["ticker"])
        c, pnl = replay_buy(path, b, kick)
        pre_kick_stats(path, b, kick, acc)
        pb = bucket(b["ask"])
        if pb:
            rows.append({"game": b["game"], "ts": b["ts"], "cost": c, "pnl": pnl, "kind": b["kind"],
                         "league": b["league"], "bucket": pb})
    nb = len(buys)
    gates["buys_considered"] = nb
    gates["buys_with_a_path"] = len(rows)
    gates["pct_with_10_or_more_path_points_after_buy"] = round(100.0 * with_path / nb, 1) if nb else None
    gates["pct_with_spread_seen"] = round(100.0 * with_spread / nb, 1) if nb else None
    if not rows:
        return {"skipped": "no buy has a price path after it yet", "placeholders": measured(acc)}
    out = {"fee_note": f"fee = ceil({FEE_RATE} x n x p x (1-p)) per order, n={EXIT_FEE_N}, paid on entry and on exit; "
                       "entry at the ask, exit at the bid",
           "all": group_result(rows, boot), "by_kind": {}, "by_price_bucket": {}, "by_league": {},
           "placeholders": measured(acc)}
    for key, dest in (("kind", "by_kind"), ("bucket", "by_price_bucket"), ("league", "by_league")):
        for v in sorted({r[key] for r in rows}):
            out[dest][v] = group_result([r for r in rows if r[key] == v], boot)
    return out


def measured(acc):
    """Measured stand-ins for SB_PRE_CLOSE, SB_PRE_VOL, SB_SPREAD and SB_LIVE_WIDEN."""
    def hide(n):
        return n < HIDE_N
    out = {}
    d = acc["drift"]
    if hide(len(d)):
        out["pre_close_drift"] = {"n": len(d), "note": "n<20, hidden"}
    else:
        gap = [(x, g) for x, g in d if g and g > 0]
        out["pre_close_drift"] = {
            "n": len(d), "mean_cents_last_pre_start_bid_minus_ask_at_buy": round(100 * statistics.mean(x for x, _ in d), 2),
            "share_of_our_fair_gap_closed_before_start (SB_PRE_CLOSE)":
                round(sum(x for x, _ in gap) / sum(g for _, g in gap), 3) if len(gap) >= HIDE_N else "n<20, hidden"}
    dz = acc["dz"]
    out["pre_start_volatility"] = ({"n": len(dz), "note": "n<20, hidden"} if hide(len(dz)) else {
        "n": len(dz), "probit_units_per_day (SB_PRE_VOL)": round(math.sqrt(statistics.mean(x * x for x, _, _ in dz)), 4),
        "price_cents_per_sqrt_day": round(100 * math.sqrt(statistics.mean(m * m / (t / 86400.0) for _, m, t in dz)), 2)})
    gp, gl = acc["gap_pre"], acc["gap_live"]
    out["spread"] = {
        "pre_game_median_cents (SB_SPREAD[0])": round(100 * statistics.median(gp), 2) if not hide(len(gp)) else "n<20, hidden",
        "in_play_median_cents (SB_SPREAD[1])": round(100 * statistics.median(gl), 2) if not hide(len(gl)) else "n<20, hidden",
        "n_pre": len(gp), "n_in_play": len(gl)}
    if not hide(len(gp)) and not hide(len(gl)) and statistics.median(gp) > 0:
        out["spread"]["in_play_widening_x (SB_LIVE_WIDEN)"] = round(statistics.median(gl) / statistics.median(gp), 2)
    return out


# ---------------------------------------------------------------- combos: from Kalshi's real buyback offers
def combo_section(db, boot, gates):
    why = need(db, "offers", ["ts", "combo", "p", "pays", "hold", "offer", "real_offer"])
    if why:
        return {"skipped": why}
    rows = [dict(r) for r in db.execute("select ts, combo, p, pays, hold, offer from offers where real_offer=1 "
                                        "and offer > 0")]
    gates["real_combo_offers"] = len(rows)
    out = {"real_offer_rows": len(rows)}
    disc = [(r["offer"] / r["hold"], r["combo"]) for r in rows if r["hold"] and r["hold"] > 0]
    if len(disc) < HIDE_N:
        out["discount"] = {"n": len(disc), "note": "n<20, hidden"}
    else:
        by = {}
        for d, c in disc:
            by.setdefault(c, []).append(d)
        means = [statistics.mean(v) for v in by.values()]
        vals = [d for d, _ in disc]
        boots = []
        rng = random.Random(3)
        for _ in range(boot):
            pick = rng.choices(means, k=len(means))
            boots.append(statistics.mean(pick))
        out["discount"] = {
            "n_offers": len(disc), "n_combos": len(by),
            "median_offer_over_hold_value (the real DISC_PRE / DISC_LIVE)": round(statistics.median(vals), 3),
            "mean": round(statistics.mean(vals), 3),
            "p10_p90": [round(quantile(vals, 0.1), 3), round(quantile(vals, 0.9), 3)],
            "mean_95_by_combo": [round(quantile(boots, 0.025), 3), round(quantile(boots, 0.975), 3)] if len(means) >= 5 else
            "n<5 combos, no range"}
    # exit replay on the offer series of settled combos (their own confidence range; the weakest evidence)
    if need(db, "bets", ["combo", "first_seen", "cost", "pays", "status"]):
        out["exit_replay"] = {"skipped": "table bets is missing"}
        return out
    bets = {r["combo"]: dict(r) for r in db.execute("select combo, first_seen, cost, pays, status from bets "
                                                    "where status in ('won','lost') and cost>0 and pays>0")}
    series = {}
    for r in sorted(rows, key=lambda r: r["ts"]):
        if r["combo"] in bets and r["ts"] >= (bets[r["combo"]].get("first_seen") or 0):
            series.setdefault(r["combo"], []).append(r)
    res = []
    for cid, offs in series.items():
        b = bets[cid]
        won = b["status"] == "won"
        cost, pays = b["cost"], b["pays"]
        hold = (pays if won else 0.0) - cost

        def sell(o):
            po = min(max(o["offer"] / pays, 0.01), 0.99)
            return o["offer"] - fee_per_contract(po, pays) * pays - cost
        pnl = {"hold": hold}
        for name, x in (("+3c", 0.03), ("+5c", 0.05), ("+10c", 0.10)):
            hit = next((o for o in offs if o["offer"] / pays >= cost / pays + x), None)
            pnl[name] = sell(hit) if hit else hold
        for k in ("fair", "T-1h", "T-15m"):
            pnl[k] = hold
        res.append({"game": cid, "ts": offs[0]["ts"], "cost": cost, "pnl": pnl})
    if len(res) < HIDE_N:
        out["exit_replay"] = {"n_settled_combos_with_offers": len(res), "note": "n<20, hidden"}
    else:
        g = group_result(res, boot)
        for k in ("fair", "T-1h", "T-15m"):                  # a combo has no path or kick: only the cent rules apply
            g.get("rules", {}).pop(k, None)
        g["note"] = ("combos only have offer samples, not a price path; entry fee on the combo is not added "
                     "(see --combo-fee); the sale fee uses the standard taker formula. Weakest evidence.")
        out["exit_replay"] = g
    return out


# ---------------------------------------------------------------- the 4 numbers the design's section 5 asks for
def combo_fee_section(db):
    """Ratio of the entry fee actually recorded in the ledger to the standard taker formula, per kind.
    fees = every fee on the position, sell_fees = the closing fills' fees, cost = money opened + all fees."""
    why = need(db, "ledger", ["ticker", "kind", "cost", "back", "fees", "sold_back", "sell_fees", "n_sold", "status"])
    if why:
        return {"skipped": why}
    pays_by = {}
    if not need(db, "sell_log", ["ticker", "pays"]):
        pays_by = {r["t"]: r["p"] for r in db.execute("select ticker t, max(pays) p from sell_log group by ticker")}
    by, skipped = {}, 0
    for r in db.execute("select ticker, kind, cost, back, fees, sold_back, sell_fees, n_sold, status from ledger "
                        "where fees > 0 and cost > 0"):
        fees, cost = r["fees"] or 0.0, r["cost"] or 0.0
        entry = fees - (r["sell_fees"] or 0.0)
        money = cost - fees
        st = r["status"]
        if st == "sold":
            n = r["n_sold"]
        elif st == "won":
            n = (r["n_sold"] or 0.0) + max((r["back"] or 0.0) - (r["sold_back"] or 0.0), 0.0)
        elif st == "lost":
            n = pays_by.get(r["ticker"])
        else:
            n = None
        if not n or n <= 0 or entry <= 0 or money <= 0 or not 0 < money / n < 1:
            skipped += 1
            continue
        p = money / n
        exp = FEE_RATE * n * p * (1 - p)
        by.setdefault(r["kind"] or "?", []).append((entry, exp))
    out = {"standard_formula": f"{FEE_RATE} x n x p x (1-p)", "rows_skipped_no_size_or_fee": skipped, "kinds": {},
           "reading": "ratio near 1.0 = standard taker fee; near 0 = no entry fee; else a different rate. Indicative "
                      "only: confirm on 3+ fills before changing any code."}
    for kind, v in sorted(by.items()):
        if len(v) < HIDE_FEE_N:
            out["kinds"][kind] = {"n": len(v), "note": f"n<{HIDE_FEE_N}, hidden"}
            continue
        ratios = [e / x for e, x in v if x > 0]
        out["kinds"][kind] = {"n": len(v), "ratio_of_sums": round(sum(e for e, _ in v) / sum(x for _, x in v), 3),
                              "median_ratio": round(statistics.median(ratios), 3) if ratios else None}
    return out


# ---------------------------------------------------------------- run
def show(label, obj, depth=0):
    pad = "  " * depth
    if isinstance(obj, dict):
        print(f"{pad}{label}:")
        for k, v in obj.items():
            show(k, v, depth + 1)
    else:
        print(f"{pad}{label}: {obj}")


def run(path, out_path, boot, combo_fee=False):
    try:
        db = open_ro(path)
        db.execute("select count(*) from sqlite_master").fetchone()      # a file that is not a database fails here
    except (OSError, sqlite3.Error) as err:
        print(f"cannot open the history file read-only: {type(err).__name__}")
        return 2, None
    summary = {"what": "early-exit replay, aggregates only", "fee_rate": FEE_RATE}
    if FEE_NOTE:
        summary["fee_rate_note"] = FEE_NOTE
    try:
        if combo_fee:
            try:
                summary["combo_fee"] = combo_fee_section(db)
            except sqlite3.Error as err:
                summary["combo_fee"] = {"skipped": f"database error ({type(err).__name__})"}
        else:
            gates = {"table_rows": table_counts(db)}
            if "price_path" in tables(db) and not need(db, "price_path", ["ts"]):
                lo, hi, = db.execute("select min(ts), max(ts) from price_path").fetchone()
                gates["price_path_span_days"] = round((hi - lo) / 86400.0, 1) if lo and hi else 0
            summary["data_quality"] = gates
            for key, fn in (("singles", singles_section), ("combos", combo_section)):
                try:
                    summary[key] = fn(db, boot, gates)
                except sqlite3.Error as err:
                    summary[key] = {"skipped": f"database error ({type(err).__name__}); is the file a combo history file?"}
    finally:
        db.close()
    for k, v in summary.items():
        show(k, v)
    if out_path:
        p = Path(out_path).expanduser()
        p.write_text(json.dumps(summary, indent=1, sort_keys=False))
        print(f"\nwrote {p}")
    print("safe to send: group totals only, no tickers, dates, ids or balances.")
    return 0, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=None, help="history file (default: combo_history.db next to this script or the app, then ~/combowatch)")
    ap.add_argument("--out", default=None, help="where to write the summary file")
    ap.add_argument("--boot", type=int, default=400, help="bootstrap rounds (default 400)")
    ap.add_argument("--combo-fee", action="store_true", help="only report recorded combo entry fee vs the standard formula")
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
    code, _ = run(path, a.out, max(a.boot, 50), a.combo_fee)
    return code


if __name__ == "__main__":
    sys.exit(main())
