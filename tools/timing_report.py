#!/usr/bin/env python3
"""Buy-timing report (issue #8, autopilot step 8). READ-ONLY: opens the history file with mode=ro (or asks the production
Mac's read-only log window), never writes, never starts the watcher, never places an order, no other network call.

    python3 tools/timing_report.py --db ~/combowatch/combo_history.db      # a local copy of the history file
    python3 tools/timing_report.py --prod                                    # via tools/read_prod_logs.py (dev Mac)
    python3 tools/timing_report.py --db FILE --json                          # the same numbers as JSON

For real bets and paper bets apart, by hours-before-start bucket and by league: sample size, net dollars after fees
(Kalshi's own fills for real bets when known, else the held-to-the-end result, which already includes the fee), dollars
per dollar staked, and closing-line value (the game-time price against the price at build, as the scoreboard's CLV).
A group with fewer than MIN_N bets is flagged "too few"; the buy-timing decision needs 6 to 8 weeks of data, so the header
also shows how many days the data spans. It reads the `timing_log` table when it has rows, else it rebuilds the same
fields from the saved panel bets (`panel` table), so it works from day one.
"""
import argparse
import json
import math
import os
import sqlite3
import subprocess
import sys
from collections import defaultdict

MIN_N = 20                      # fewer bets than this in a group: shown, flagged "too few" (same as the scoreboard's BOARD_FEW)
BUCKETS = (("live", "During the game"), ("lt1h", "Under 1 hour before"), ("1-6h", "1-6 hours before"),
           ("6-24h", "6-24 hours before"), ("24h+", "A day or more before"), (None, "Unknown timing"))
FALLBACK_SQL = (
    "select panel.mode mode, panel.day day, json_extract(i.value,'$.id') id, json_extract(i.value,'$.kind') kind, "
    "json_extract(i.value,'$.league') league, json_extract(i.value,'$.kick') kick, "
    "coalesce(json_extract(i.value,'$.bought_at'), json_extract(i.value,'$.at')) bought_at, "
    "json_extract(i.value,'$.live') live, json_extract(i.value,'$.clv') clv, json_extract(i.value,'$.stake') stake, "
    "json_extract(i.value,'$.result') result, json_extract(i.value,'$.pl') pl, json_extract(i.value,'$.pl_real') pl_real "
    "from panel, json_each(panel.body,'$.items') i where (panel.mode in ('real','paper','lab') or panel.mode like 'real#%') "
    "and json_extract(i.value,'$.state') in ('bought','paper')")
TIMING_SQL = ("select mode, day, key id, kind, league, kick, bought_at, live, clv, stake, result, pl, pl_real, auto, bucket, "
              "hours, fees from timing_log")


def bucket_of(kick, bought_at, live=False):
    """Same cut-offs as the engine's timing_bucket (a test keeps the two equal)."""
    try:
        k, b = float(kick), float(bought_at)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(k) and math.isfinite(b)) or k <= 0 or b <= 0:
        return None
    h = (k - b) / 3600
    if live or h < 0:
        return "live"
    return "lt1h" if h < 1 else "1-6h" if h < 6 else "6-24h" if h < 24 else "24h+"


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None


def normalise(r):
    """One input row to what the report needs. Missing numbers stay None (never 0): a bet with no result adds no dollars."""
    net = _num(r.get("pl_real"))
    if net is None:
        net = _num(r.get("pl"))
    return {"mode": str(r.get("mode") or "").split("#")[0] or "?", "league": r.get("league") or "other",
            "bucket": bucket_of(r.get("kick"), r.get("bought_at"), bool(r.get("live"))), "stake": _num(r.get("stake")),
            "net": net if r.get("result") in ("won", "lost") else None, "clv": _num(r.get("clv")),
            "day": r.get("day"), "auto": r.get("auto")}


def summarise(rows, key):
    """{group: {n, settled, staked, net, roi, clv, clv_n, few}} for the normalised rows, grouped by key(row)."""
    g = defaultdict(lambda: {"n": 0, "settled": 0, "staked": 0.0, "net": 0.0, "clv": [], "auto": 0})
    for r in rows:
        x = g[key(r)]
        x["n"] += 1
        x["auto"] += 1 if r.get("auto") else 0
        if r["net"] is not None and r["stake"]:
            x["settled"] += 1
            x["staked"] += r["stake"]
            x["net"] += r["net"]
        if r["clv"] is not None:
            x["clv"].append(r["clv"])
    return {k: {"n": v["n"], "settled": v["settled"], "staked": round(v["staked"], 2), "net": round(v["net"], 2),
                "roi": round(v["net"] / v["staked"], 4) if v["staked"] > 0 else None,
                "clv": round(sum(v["clv"]) / len(v["clv"]), 4) if v["clv"] else None, "clv_n": len(v["clv"]),
                "auto": v["auto"], "few": v["settled"] < MIN_N} for k, v in g.items()}


def build(raw):
    rows = [normalise(r) for r in raw]
    out = {"n": len(rows), "days": len({r["day"] for r in rows if r["day"]}), "modes": {}}
    for mode in sorted({r["mode"] for r in rows}):
        rs = [r for r in rows if r["mode"] == mode]
        out["modes"][mode] = {"bucket": summarise(rs, lambda r: r["bucket"]), "league": summarise(rs, lambda r: r["league"])}
    return out


def _pct(x):
    return "   n/a" if x is None else f"{x * 100:+5.1f}%"


def render(rep):
    lines = [f"Buy-timing report: {rep['n']} bought bets over {rep['days']} day(s) of data "
             f"(the decision needs 6 to 8 weeks; a group under {MIN_N} settled bets is flagged TOO FEW)."]
    names = dict(BUCKETS)
    for mode, sec in rep["modes"].items():
        for title, grp, order in (("hours before start", sec["bucket"], [k for k, _ in BUCKETS]),
                                  ("league", sec["league"], sorted(sec["league"], key=lambda k: -sec["league"][k]["n"]))):
            lines += ["", f"[{mode}] by {title}", f"  {'group':<24}{'bets':>5}{'settled':>8}{'net $':>9}{'ROI':>9}{'CLV':>8}{'CLV n':>6}  note"]
            for k in order:
                if k not in grp:
                    continue
                v = grp[k]
                label = names.get(k, str(k)) if title.startswith("hours") else str(k)
                lines.append(f"  {label:<24}{v['n']:>5}{v['settled']:>8}{v['net']:>9.2f}{_pct(v['roi']):>9}{_pct(v['clv']):>8}"
                             f"{v['clv_n']:>6}  {'TOO FEW' if v['few'] else ''}")
    if not rep["modes"]:
        lines.append("No bought bets found.")
    return "\n".join(lines)


def _query(con, sql):
    cur = con.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def from_db(path):
    con = sqlite3.connect(f"file:{os.path.expanduser(path)}?mode=ro", uri=True)
    try:
        try:
            rows = _query(con, TIMING_SQL)
        except sqlite3.Error:
            rows = []
        return rows or _query(con, FALLBACK_SQL)
    finally:
        con.close()


def from_prod():
    here = os.path.dirname(os.path.abspath(__file__))
    res = []
    for sql in (TIMING_SQL, FALLBACK_SQL):
        p = subprocess.run([sys.executable, os.path.join(here, "read_prod_logs.py"), "--source", "db", "--sql", sql, "--json"],
                           capture_output=True, text=True, timeout=120)
        res = [json.loads(line) for line in p.stdout.splitlines() if line.startswith("{") and '"error"' not in line]
        if res:
            return res
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", help="path to combo_history.db (opened read-only)")
    ap.add_argument("--prod", action="store_true", help="read through tools/read_prod_logs.py")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.db and not a.prod:
        ap.error("give --db FILE or --prod")
    try:
        raw = from_db(a.db) if a.db else from_prod()
    except (sqlite3.Error, OSError, ValueError, subprocess.SubprocessError) as err:
        print(f"skipped: could not read the data ({type(err).__name__}: {err})")
        return 1
    rep = build(raw)
    print(json.dumps(rep, indent=1) if a.json else render(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
