#!/usr/bin/env python3
"""Fee focus: what do fees really cost, and would fewer, bigger bets help? Read-only, no network, no keys.

Pete runs one command, from the app folder, on the machine that has the history file:

    python3 tools/fee_focus.py --out ~/fee_focus_summary.json

It opens combo_history.db READ-ONLY (sqlite URI mode=ro, the same helper as tools/exit_replay.py), never writes to it,
never starts the watcher, never places an order and makes no network call. It writes ONE small file of group aggregates
(counts, percentages, dollars per dollar staked, ranges) and prints the same numbers. There are no tickers, dates of
individual bets, order ids or balances in the output; any cell with fewer than 20 bets prints "n<20, hidden".

Part A, fees: (1) the fee actually recorded vs Kalshi's formula ceil(0.07 x n x p x (1-p)), by single vs combo (this
settles the open question of what combos pay); (2) fee as % of stake by stake size and by price, and the rounding excess
(the cent round-up) as % of stake; (3) the round-trip fee for bets sold early vs held to the end.
Part B, few strategic bets: net return per $ staked after fees by grade, expected-value band, stake size and bets per
day, with game-level 95% ranges, and a what-if: only the top N graded bets a day, at 2x and 3x the stake, fees
recomputed with rounding, the rule picked on the first 70% of days and scored on the last 30%.

These numbers DESCRIBE the past. They are not a decision and change nothing in the app.

Missing tables or columns never crash it: that part prints a clear "skipped: ..." line and the rest still runs.
"""
import argparse
import datetime as dt
import json
import math
import random
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import exit_replay as ER                                      # noqa: E402  (its read-only opener and the engine's fee rate)

HIDE_N = 20                  # a cell with fewer bets than this is never shown
FEE_RATE = ER.FEE_RATE
STAKE_B = ((0, 1, "$0-1"), (1, 2, "$1-2"), (2, 5, "$2-5"), (5, 10, "$5-10"), (10, 25, "$10-25"), (25, 1e12, "$25+"))
PRICE_B = ((0, 0.15, "<15c"), (0.15, 0.30, "15-30c"), (0.30, 0.60, "30-60c"), (0.60, 0.85, "60-85c"), (0.85, 1.01, "85c+"))
DAY_B = ((1, 2, "1-2 bets"), (3, 5, "3-5 bets"), (6, 10 ** 9, "6+ bets"))
TOP_N = (1, 2, 3, 5)
MULTS = (1, 2, 3)            # 1x is the reference; the question asks about 2x and 3x
REF_STAKE = 5.0              # the app's flat reference stake for scoring every checked bet (SB_STAKE)
HIDE_NOTE = f"n<{HIDE_N}, hidden"


# ---------------------------------------------------------------- small helpers
def pick(buckets, x):
    for lo, hi, name in buckets:
        if lo <= x < hi:
            return name
    return None


def cents_up(x):
    """Kalshi rounds an order's fee UP to the cent (the engine's single_fee rule)."""
    return math.ceil(round(x * 100, 6)) / 100


def pct(a, b, nd=2):
    return round(100.0 * a / b, nd) if b else None


def day_of(ts):
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.fromtimestamp(ts, ZoneInfo("America/Los_Angeles")).date().isoformat()
    except Exception:
        return dt.datetime.utcfromtimestamp(ts).date().isoformat()


def game_of(tickers):
    """The game(s) a bet is on, as one key (the engine's _sb_game: a spread or total counts as its game)."""
    return "+".join(sorted({re.sub(r"(SPREAD|TOTAL)-", "GAME-", t.rsplit("-", 1)[0]) for t in tickers or () if t}))


def legs_of(text):
    try:
        v = json.loads(text or "[]")
        return [str(x) for x in v] if isinstance(v, list) else []
    except ValueError:
        return []


def boot_ci(rows, boot, seed=7):
    """95% range of sum(net)/sum(staked) resampling whole games. rows: [(game, staked, net)]."""
    g = {}
    for k, s, n in rows:
        a = g.setdefault(k, [0.0, 0.0])
        a[0] += s
        a[1] += n
    games = list(g.values())
    if len(games) < 2:
        return None
    rng = random.Random(seed)
    out = []
    for _ in range(boot):
        s = n = 0.0
        for a in rng.choices(games, k=len(games)):
            s += a[0]
            n += a[1]
        if s > 0:
            out.append(n / s)
    if not out:
        return None
    out.sort()
    return [round(out[int(0.025 * (len(out) - 1))], 4), round(out[int(0.975 * (len(out) - 1))], 4)]


def cell(rows, boot, ci=True):
    """rows: [(game, staked, net)] -> one aggregate cell, hidden under HIDE_N bets."""
    if len(rows) < HIDE_N:
        return {"n": len(rows), "note": HIDE_NOTE}
    st, nt = sum(r[1] for r in rows), sum(r[2] for r in rows)
    out = {"n": len(rows), "games": len({r[0] for r in rows}), "staked": round(st, 2), "net": round(nt, 2),
           "net_per_dollar": round(nt / st, 4) if st > 0 else None, "wins_pct": pct(sum(1 for r in rows if r[2] > 0), len(rows), 1)}
    if ci:
        out["range95_per_dollar"] = boot_ci(rows, boot)
    return out


def by_group(items, keyfn, order, mk):
    """items grouped by keyfn into the named buckets (in `order`); mk(list) builds each cell."""
    g = {}
    for it in items:
        k = keyfn(it)
        if k is not None:
            g.setdefault(k, []).append(it)
    return {name: mk(g[name]) for name in order if name in g}


# ---------------------------------------------------------------- Part A: fees from the ledger
def ledger_rows(db):
    """Every finished ledger row with the pieces both parts need. Nothing here is ever printed per row."""
    pays_by = {}
    if not ER.need(db, "sell_log", ["ticker", "pays"]):
        pays_by = {r["t"]: r["p"] for r in db.execute("select ticker t, max(pays) p from sell_log group by ticker")}
    nf_ok = "nf" in ER.columns(db, "ledger")
    out = []
    sql = ("select ticker, kind, cost, back, fees, sold_back, sell_fees, n_sold, status, opened, closed, legs"
           + (", nf" if nf_ok else "") + " from ledger where cost > 0")
    for r in db.execute(sql):
        fees, cost = r["fees"] or 0.0, r["cost"]
        sell = r["sell_fees"] or 0.0
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
        p = money / n if n and n > 0 and money > 0 else None
        legs = legs_of(r["legs"]) or [r["ticker"]]
        ts = r["opened"] or r["closed"]
        out.append({"kind": "combo" if r["kind"] == "combo" else "single", "kind_raw": r["kind"] or "?", "status": st,
                    "cost": cost, "back": r["back"] or 0.0, "fees": fees, "sell_fees": sell, "entry": fees - sell,
                    "money": money, "n": n if p else None, "p": p if p and 0 < p < 1 else None,
                    "nf": (r["nf"] if nf_ok else None), "day": day_of(ts) if ts else None, "ts": ts,
                    "legs": json.dumps(legs), "game": game_of(legs) or r["ticker"]})
    return out


def fee_formula_section(rows, fee_ratio_out):
    """(1) recorded entry fee vs the formula, per kind. Position-level: the ledger sums fills, so rows with more than
    one fill are split from single-fill rows (a single-fill row is exactly one order, the formula's own unit)."""
    out = {"standard_formula": f"ceil({FEE_RATE} x n x p x (1-p)) per order, to the cent",
           "reading": ("ratio near 1.0 = the standard taker fee applies (combos pay the same as singles); near 0 = no "
                       "entry fee; anything else = a different rate. 'matches_rounded_formula_pct' is the share of "
                       "single-fill rows whose recorded entry fee equals the rounded formula to the cent."),
           "kinds": {}}
    for kg in ("single", "combo"):
        use = [r for r in rows if r["kind"] == kg and r["p"] and r["entry"] > 0]
        sub = {"rows_with_size_and_entry_fee": len(use)}
        if len(use) < HIDE_N:
            sub["note"] = HIDE_NOTE
            out["kinds"][kg] = sub
            continue
        exp = [FEE_RATE * r["n"] * r["p"] * (1 - r["p"]) for r in use]
        sub["ratio_recorded_to_unrounded_formula"] = round(sum(r["entry"] for r in use) / sum(exp), 3)
        one = [(r, e) for r, e in zip(use, exp) if r["nf"] == 1]
        if len(one) >= HIDE_N:
            rr = [cents_up(e) for _, e in one]
            sub["single_fill_rows"] = len(one)
            sub["single_fill_ratio_to_unrounded"] = round(sum(r["entry"] for r, _ in one) / sum(e for _, e in one), 3)
            sub["single_fill_ratio_to_rounded"] = round(sum(r["entry"] for r, _ in one) / sum(rr), 3)
            sub["matches_rounded_formula_pct"] = pct(sum(1 for (r, _), x in zip(one, rr) if abs(r["entry"] - x) < 0.0051), len(one), 1)
        else:
            sub["single_fill_rows"] = f"{len(one)} (n<{HIDE_N}, hidden)"
        out["kinds"][kg] = sub
        if kg == "combo":
            fee_ratio_out.append(sub.get("single_fill_ratio_to_rounded") or sub["ratio_recorded_to_unrounded_formula"])
    zero = {kg: sum(1 for r in rows if r["kind"] == kg and r["entry"] <= 0) for kg in ("single", "combo")}
    neg = sum(1 for r in rows if r["fees"] < -0.004 or r["sell_fees"] < -0.004)
    out["rebates"] = {"rows_with_a_negative_fee_total": neg if neg >= HIDE_N or neg == 0 else f"{neg} (n<{HIDE_N}, hidden)",
                      "rows_with_zero_entry_fee": {k: (v if v >= HIDE_N or v == 0 else f"n<{HIDE_N}, hidden") for k, v in zero.items()},
                      "note": ("fee rebates or rounding refunds would show as negative fee totals or zero-fee rows; the "
                               "ledger only keeps fee totals per bet, so a refund netted inside a positive total is not visible")}
    return out


def fee_buckets_section(rows):
    """(2) fee as % of stake by stake size and by price; rounding excess as % of stake (single-fill rows only)."""
    res = {"fee_pct_of_stake": {}, "rounding_excess_pct_of_stake": {}}

    def agg(items, fe):
        if len(items) < HIDE_N:
            return {"n": len(items), "note": HIDE_NOTE}
        return {"n": len(items), "fee_pct_of_stake": pct(sum(fe(r) for r in items), sum(r["money"] for r in items))}

    for kg in ("single", "combo", "all"):
        pool = [r for r in rows if (kg == "all" or r["kind"] == kg) and r["money"] > 0]
        held = [r for r in pool if r["status"] != "sold"]
        res["fee_pct_of_stake"][kg] = {
            "by_stake": by_group(held, lambda r: pick(STAKE_B, r["money"]), [b[2] for b in STAKE_B], lambda g: agg(g, lambda r: r["entry"])),
            "by_price": by_group([r for r in held if r["p"]], lambda r: pick(PRICE_B, r["p"]), [b[2] for b in PRICE_B],
                                 lambda g: agg(g, lambda r: r["entry"])),
            "note": "entry fee only, bets held to the end; sold-early bets are in the round-trip section"}

        one = [r for r in pool if r["p"] and r["nf"] == 1]

        def exc(g):
            if len(g) < HIDE_N:
                return {"n": len(g), "note": HIDE_NOTE}
            un = [FEE_RATE * r["n"] * r["p"] * (1 - r["p"]) for r in g]
            money = sum(r["money"] for r in g)
            return {"n": len(g), "formula_rounding_excess_pct": pct(sum(cents_up(e) - e for e in un), money, 3),
                    "recorded_minus_unrounded_pct": pct(sum(r["entry"] - e for r, e in zip(g, un)), money, 3)}
        res["rounding_excess_pct_of_stake"][kg] = {
            "by_stake": by_group(one, lambda r: pick(STAKE_B, r["money"]), [b[2] for b in STAKE_B], exc),
            "by_price": by_group(one, lambda r: pick(PRICE_B, r["p"]), [b[2] for b in PRICE_B], exc),
            "note": "single-fill rows only; formula_rounding_excess = ceil(fee) - fee, recorded_minus_unrounded = what was really charged"}
    return res


def round_trip_section(rows):
    """(3) total fees (entry + exit) as % of stake for bets sold early, vs entry-only fees for the same bucket held."""
    out = {"note": "sold = entry fee + selling fee; held = entry fee (plus any settlement fee). Percent of the money put in."}

    def agg(g):
        if len(g) < HIDE_N:
            return {"n": len(g), "note": HIDE_NOTE}
        return {"n": len(g), "fee_pct_of_stake": pct(sum(r["fees"] for r in g), sum(r["money"] for r in g))}

    for kg in ("single", "combo"):
        pool = [r for r in rows if r["kind"] == kg and r["money"] > 0 and r["status"] in ("sold", "won", "lost")]
        cut = {}
        for dim, bk, key in (("by_stake", STAKE_B, lambda r: r["money"]), ("by_price", PRICE_B, lambda r: r["p"])):
            cut[dim] = {}
            for way, test in (("sold_early", lambda r: r["status"] == "sold"), ("held_to_end", lambda r: r["status"] != "sold")):
                cut[dim][way] = by_group([r for r in pool if test(r) and key(r) is not None], lambda r: pick(bk, key(r)),
                                         [b[2] for b in bk], agg)
        out[kg] = cut
    return out


# ---------------------------------------------------------------- Part B: few strategic bets
def ledger_cells(rows, boot, matched):
    """Actual bets: net = money back - money out (fees already inside cost). By stake and by bets that day."""
    fin = [r for r in rows if r["status"] in ("won", "lost", "sold") and r["cost"] > 0]
    per_day = {}
    for r in fin:
        if r["day"]:
            per_day[r["day"]] = per_day.get(r["day"], 0) + 1
    items = [(r["game"], r["cost"], r["back"] - r["cost"], r) for r in fin]

    def mk(g):
        return cell([(a, b, c) for a, b, c, _ in g], boot)
    out = {"rows": len(fin), "undated_rows": sum(1 for r in fin if not r["day"]),
           "net_is": "money back (sales + payout) minus money out including every fee",
           "all": mk(items),
           "by_stake": by_group(items, lambda t: pick(STAKE_B, t[3]["money"]) if t[3]["money"] > 0 else None, [b[2] for b in STAKE_B], mk),
           "by_bets_that_day": by_group([t for t in items if t[3]["day"]], lambda t: pick(DAY_B, per_day[t[3]["day"]]), [b[2] for b in DAY_B], mk)}
    out["matched_to_paper_book"] = {"rows": len(matched), "of": len(fin)}
    return out


def paper_rows(db, combo_ratio):
    """Settled sb_paper rows with the bet's win/loss, its price, and the fee-recomputed result at any stake."""
    out, skipped = [], 0
    for r in db.execute("select bet, day, kind, grade, role, price, ev, pays, stake, plain, game from sb_paper "
                        "where plain is not null and day is not null"):
        combo = r["kind"] not in ("single", "line")
        pays = r["pays"]
        p = (REF_STAKE / pays if pays and pays > 0 else None) if combo else r["price"]
        if not p or not 0 < p < 1 or r["ev"] is None:
            skipped += 1
            continue
        out.append({"bet": r["bet"], "day": r["day"], "combo": combo, "grade": r["grade"] or "none", "role": r["role"],
                    "p": p, "ev": r["ev"], "stake": r["stake"] or 0.0, "win": r["plain"] > 0, "recorded": r["plain"],
                    "game": r["game"] or r["bet"]})
    return out, skipped


def result_at(row, stake, combo_ratio):
    """(money out, net) for this paper bet at `stake`: whole contracts for a single, the fee rounded up to the cent."""
    p = row["p"]
    f = FEE_RATE * (combo_ratio if row["combo"] else 1.0) * p * (1 - p)
    n = stake / (p + f) if row["combo"] else math.floor(stake / (p + f))
    if n <= 0:
        return None
    cost = n * p + cents_up(n * f)
    return cost, (n if row["win"] else 0.0) - cost


def evaluate(pool, stake_of, combo_ratio):
    """[(game, staked, net)] for the pool at stake_of(row); bets too small to buy one contract are dropped."""
    out = []
    for r in pool:
        x = result_at(r, stake_of(r), combo_ratio)
        if x:
            out.append((r["game"], x[0], x[1]))
    return out


def paper_cells(prows, boot, combo_ratio):
    out = {"rows_settled": len(prows), "scoring": f"every checked bet scored at the app's flat ${REF_STAKE:.0f} stake held to the end, whole "
           "contracts, fee rounded up to the cent; 'recorded' is the app's own unrounded figure"}
    ref = [(r, result_at(r, REF_STAKE, combo_ratio)) for r in prows]
    ref = [(r, x) for r, x in ref if x]
    rows5 = [(r["game"], x[0], x[1]) for r, x in ref]

    def mk(g):
        c = cell([(r["game"], x[0], x[1]) for r, x in g], boot)
        if "net_per_dollar" in c:
            c["recorded_per_dollar"] = round(sum(r["recorded"] for r, _ in g) / (REF_STAKE * len(g)), 4)
        return c
    out["all"] = cell(rows5, boot)
    names = sorted({r["grade"] for r, _ in ref})
    out["by_grade"] = by_group(ref, lambda t: t[0]["grade"], names, mk)
    evs = sorted(r["ev"] for r, _ in ref)
    if len(evs) >= 4 * HIDE_N:
        e1, e2, e3 = (evs[int(q * (len(evs) - 1))] for q in (0.25, 0.5, 0.75))
        out["ev_quartile_edges"] = [round(e1, 4), round(e2, 4), round(e3, 4)]
        names = ["Q1 lowest ev", "Q2", "Q3", "Q4 highest ev"]
        out["by_ev_quartile"] = by_group(ref, lambda t: names[(t[0]["ev"] > e1) + (t[0]["ev"] > e2) + (t[0]["ev"] > e3)], names, mk)
    else:
        out["by_ev_quartile"] = {"note": f"fewer than {4 * HIDE_N} settled bets"}
    # the bets the paper book would really have staked, at their own stake
    staked = [r for r in prows if r["stake"] > 0]
    per_day = {}
    for r in staked:
        per_day[r["day"]] = per_day.get(r["day"], 0) + 1
    sx = [(r, result_at(r, r["stake"], combo_ratio)) for r in staked]
    sx = [(r, x) for r, x in sx if x]
    out["staked_rows"] = len(sx)
    out["by_stake"] = by_group(sx, lambda t: pick(STAKE_B, t[0]["stake"]), [b[2] for b in STAKE_B], mk)
    out["by_bets_that_day"] = by_group(sx, lambda t: pick(DAY_B, per_day[t[0]["day"]]), [b[2] for b in DAY_B], mk)
    return out


def simulate(prows, boot, combo_ratio):
    """Only the top N bets a day (best ev first) at m x the paper stake, vs what the paper book actually staked.
    Rule chosen on the first 70% of days, scored on the last 30%."""
    pool = [r for r in prows if r["stake"] > 0]
    days = sorted({r["day"] for r in pool})
    out = {"pool": "bets the paper book staked (stake > 0), settled; ranked by ev, best first, within each day",
           "staked_bets": len(pool), "days": len(days)}
    if len(days) < 10 or len(pool) < 2 * HIDE_N:
        out["note"] = "too few days or bets for a 70/30 split"
        return out
    cut = days[int(0.7 * len(days)) - 1]
    split = {"train": [r for r in pool if r["day"] <= cut], "test": [r for r in pool if r["day"] > cut]}
    out["days_train"], out["days_test"] = sum(1 for d in days if d <= cut), sum(1 for d in days if d > cut)
    by_day = {}
    for r in pool:
        by_day.setdefault(r["day"], []).append(r)
    for v in by_day.values():
        v.sort(key=lambda r: -r["ev"])
    res = {"actual": {}, "rules": {}}
    for part, rows in split.items():
        res["actual"][part] = cell(evaluate(rows, lambda r: r["stake"], combo_ratio), boot)
    best = None
    for n in TOP_N:
        for m in MULTS:
            key = f"top{n}_x{m}"
            res["rules"][key] = {}
            for part, rows in split.items():
                days_in = {r["day"] for r in rows}
                chosen = [r for d in sorted(days_in) for r in by_day[d][:n]]
                ev_rows = evaluate(chosen, lambda r, m=m: r["stake"] * m, combo_ratio)
                c = cell(ev_rows, boot)
                res["rules"][key][part] = c
            tr = res["rules"][key]["train"]
            if tr.get("net_per_dollar") is not None and m > 1 and (best is None or tr["net_per_dollar"] > best[0]):
                best = (tr["net_per_dollar"], key)
    res["rule_picked_on_train_by_net_per_dollar"] = best[1] if best else None
    res["picked_rule_scored_on_test"] = res["rules"][best[1]]["test"] if best else None
    res["note"] = ("the pick uses only the first 70% of days; 'test' cells are the last 30%. Compare each rule's net with "
                   "actual.test: a rule that keeps fewer bets bets less money, so look at per-dollar AND total.")
    out.update(res)
    return out


# ---------------------------------------------------------------- run
def data_quality(db, rows, prows):
    t = ER.tables(db)
    dq = {"ledger_rows": len(rows), "ledger_by_status": {}}
    for r in rows:
        dq["ledger_by_status"][r["status"]] = dq["ledger_by_status"].get(r["status"], 0) + 1
    ts = [r["ts"] for r in rows if r["ts"]]
    dq["ledger_span_days"] = round((max(ts) - min(ts)) / 86400.0, 1) if ts else 0
    dq["ledger_rows_with_size_known"] = sum(1 for r in rows if r["p"])
    dq["ledger_rows_single_fill"] = sum(1 for r in rows if r["nf"] == 1)
    if "sb_paper" in t:
        n, lo, hi, gm = db.execute("select count(*), min(ts), max(ts), count(distinct game) from sb_paper").fetchone()
        dq["sb_paper_rows"] = n
        dq["sb_paper_settled_rows_used"] = len(prows)
        dq["sb_paper_games"] = gm
        dq["sb_paper_span_days"] = round((hi - lo) / 86400.0, 1) if lo and hi else 0
    else:
        dq["sb_paper"] = "table missing"
    dq["caveat"] = ("lost bets have no recorded size unless a sell_log row exists, so the formula check covers fewer lost bets "
                    "than won or sold ones; ledger-wide fee-% rows use all bets")
    return dq


def show(label, obj, depth=0):
    ER.show(label, obj, depth)


def run(path, out_path, boot):
    try:
        db = ER.open_ro(path)
        db.execute("select count(*) from sqlite_master").fetchone()
    except (OSError, sqlite3.Error) as err:
        print(f"cannot open the history file read-only: {type(err).__name__}")
        return 2, None
    summary = {"what": "fee focus, aggregates only; descriptive, not a decision; changes nothing in the app", "fee_rate": FEE_RATE}
    if ER.FEE_NOTE:
        summary["fee_rate_note"] = ER.FEE_NOTE
    try:
        why = ER.need(db, "ledger", ["ticker", "kind", "cost", "back", "fees", "sold_back", "sell_fees", "n_sold", "status", "opened", "closed"])
        rows = [] if why else ledger_rows(db)
        ratio = []
        if why:
            summary["part_a_fees"] = {"skipped": why}
        else:
            a = {"formula_check": fee_formula_section(rows, ratio)}
            a.update(fee_buckets_section(rows))
            a["round_trip"] = round_trip_section(rows)
            summary["part_a_fees"] = a
        combo_ratio = ratio[0] if ratio and ratio[0] and 0.05 < ratio[0] < 3 else 1.0
        summary["combo_fee_ratio_used_in_part_b"] = combo_ratio
        pwhy = ER.need(db, "sb_paper", ["bet", "ts", "day", "kind", "grade", "role", "price", "ev", "pays", "stake", "plain", "game"])
        prows, pskip = ([], 0) if pwhy else paper_rows(db, combo_ratio)
        summary["data_quality"] = data_quality(db, rows, prows)
        b = {}
        if why:
            b["actual_bets"] = {"skipped": why}
        else:
            keys = {r["bet"] for r in prows}
            matched = [r for r in rows if r["legs"] in keys]
            b["actual_bets"] = ledger_cells(rows, boot, matched)
        if pwhy:
            b["paper_book"] = {"skipped": pwhy}
            b["top_n_per_day_what_if"] = {"skipped": pwhy}
        else:
            b["paper_book"] = paper_cells(prows, boot, combo_ratio)
            b["paper_book"]["rows_skipped_no_price"] = pskip
            b["top_n_per_day_what_if"] = simulate(prows, boot, combo_ratio)
        summary["part_b_few_strategic_bets"] = b
    except sqlite3.Error as err:
        summary["error"] = f"database error ({type(err).__name__}); is the file a combo history file?"
    finally:
        db.close()
    summary["reminder"] = "descriptive only: a past sample, not a decision; nothing in the app changed"
    for k, v in summary.items():
        show(k, v)
    if out_path:
        p = Path(out_path).expanduser()
        p.write_text(json.dumps(summary, indent=1))
        print(f"\nwrote {p}")
    print("safe to send: group totals only, no tickers, dates, ids or balances.")
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
