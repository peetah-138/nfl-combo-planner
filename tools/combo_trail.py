#!/usr/bin/env python3
"""Combo trail: what happened to the combos with a team in them, in plain English. Read-only, no network, no keys.

Pete runs one command, from the app folder, on the machine that has the history file:

    python3 tools/combo_trail.py --team nuggets --date 2026-11-23

It finds every combo (and single) whose legs mention the team text (case-insensitive) around that date, and prints for
each: the legs by name, cost, what it pays, when it was bought, a short timeline (at most ~60 lines: the combo's win
chance, Kalshi's buyback offer real or estimated, the smart-sell line when recorded, and every auto-sell decision with
its reason, the Let-it-ride setting), the final outcome, and a "peak offer vs cost vs sell line" summary. The same text is
saved to ~/combo_trail_summary.txt (change with --out).

It opens combo_history.db READ-ONLY (sqlite URI mode=ro), reads combo_autosell_log.jsonl (the decision log) read-only,
never writes to either, never starts the watcher, never places an order and makes no network call. Only a fixed list of
fields is ever printed: no tokens, keys, order ids or balances.

Missing tables, columns or files never crash it: that part prints a clear "skipped: ..." line and the rest still runs.
"""
import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
MAX_LINES = 60                     # timeline lines per combo
TICKER_RE = re.compile(r"KX[A-Z0-9]+-[0-9]{2}[A-Z]{3}[0-9]{2}[A-Z0-9]*-[A-Z0-9.\-]+")
LEG_RE = re.compile(r"^KX(NFL|NBA|NHL|MLB|NCAAF|NCAAB|[A-Z]+?)(GAME|SPREAD|TOTAL|WINNER|)-([0-9]{2})([A-Z]{3})([0-9]{2})([A-Z0-9]*)-(.+)$")
MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
SECRETISH = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[A-Za-z0-9_\-]{32,}")
SELL_FIELDS = ("offer", "line", "cost", "pays", "chance", "frac", "round")


def clean(s, n=140):
    """A line of text from the logs, with anything that looks like an id or key blanked out."""
    return SECRETISH.sub("[id]", str(s if s is not None else "")).replace("\n", " ")[:n]


def team_tables():
    """abbreviation -> team name per league, read as text from the engine's own tables (importing it would run it)."""
    out = {"NFL": {}, "NBA": {}, "NHL": {}}
    for src in (HERE.parent / "nfl_combo_planner.py", HERE / "nfl_combo_planner.py"):
        try:
            text = src.read_text(errors="ignore")
        except OSError:
            continue
        for var, lg in (("TEAMS", "NFL"), ("NBA_TEAMS", "NBA"), ("NHL_TEAMS", "NHL")):
            hit = re.search(r"^" + var + r"\s*=\s*\{(.*?)^\}", text, re.M | re.S)
            if hit:
                out[lg] = dict(re.findall(r'"([A-Z0-9]+)":\s*"([^"]+)"', hit.group(1)))
        if any(out.values()):
            break
    return out


class Namer:
    def __init__(self):
        self.t = team_tables()

    def leg(self, tk):
        """(plain-English leg name, game date or None) for a Kalshi leg ticker; the ticker itself if not understood."""
        m = LEG_RE.match(tk or "")
        if not m:
            return clean(tk, 60), None
        sport, kind, yy, mon, dd, _, pick = m.groups()
        try:
            day = dt.date(2000 + int(yy), MONTHS[mon], int(dd))
        except (KeyError, ValueError):
            day = None
        abbr = re.sub(r"[0-9.]+$", "", pick)
        num = pick[len(abbr):]
        team = self.t.get(sport, {}).get(abbr) or abbr
        if kind == "SPREAD":
            name = f"{team} wins by over {num}" if num else f"{team} spread"
        elif kind == "TOTAL":
            name = f"{'Over' if abbr in ('OVER', 'O', '') else abbr.title()} {num} total points"
        else:
            name = f"{team} to win"
        return name, day


def open_ro(path):
    db = sqlite3.connect("file:" + quote(str(path)) + "?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        db.execute("pragma query_only=1")
    except sqlite3.Error:
        pass
    return db


def rows(db, sql, args=(), notes=None, what=""):
    try:
        return [dict(r) for r in db.execute(sql, args).fetchall()]
    except sqlite3.Error as err:
        if notes is not None:
            notes.append(f"skipped: {what or sql.split()[3]} ({type(err).__name__}: {clean(err, 80)})")
        return []


def parse_legs(text):
    if not text:
        return []
    try:
        v = json.loads(text)
        if isinstance(v, list):
            return [x if isinstance(x, str) else (x.get("ticker") or "") for x in v if x]
    except (ValueError, AttributeError):
        pass
    return TICKER_RE.findall(str(text))


def read_log(paths, notes):
    out = []
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                for ln in f:
                    try:
                        r = json.loads(ln)
                    except ValueError:
                        continue
                    if isinstance(r, dict):
                        out.append(r)
            return out
        except OSError:
            continue
    notes.append("skipped: combo_autosell_log.jsonl not found (the skip reasons live there; pass --log <file>)")
    return out


def stamp(ts):
    try:
        return dt.datetime.fromtimestamp(float(ts)).strftime("%a %b %d %H:%M:%S")
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


def money(v):
    try:
        return "$%.2f" % float(v)
    except (TypeError, ValueError):
        return "?"


def pct(v):
    try:
        return "%.0f%%" % (100 * float(v))
    except (TypeError, ValueError):
        return "?"


def gather(db, log, notes):
    """ticker -> everything known about it."""
    C = {}

    def get(t):
        return C.setdefault(t, {"legs": [], "first": None, "cost": None, "pays": None, "status": None, "back": None,
                                "closed": None, "outcome": None, "label": None, "dec": []})
    for r in rows(db, "select * from bets", (), notes, "bets"):
        c = get(r["combo"])
        c["legs"] = c["legs"] or parse_legs(r.get("legs"))
        c.update(first=r.get("first_seen"), cost=r.get("cost"), pays=r.get("pays"), status=r.get("status"),
                 back=r.get("back"), closed=r.get("settled"))
    for r in rows(db, "select * from ledger", (), notes, "ledger"):
        c = get(r["ticker"])
        c["legs"] = c["legs"] or parse_legs(r.get("legs")) or [r["ticker"]]
        if c["first"] is None:
            c["first"] = r.get("opened")
        if c["cost"] is None:
            c["cost"] = r.get("cost")
        c["status"] = c["status"] or r.get("status")
        c["outcome"] = r.get("outcome")
        c["back"] = c["back"] if c["back"] is not None else r.get("back")
        c["closed"] = c["closed"] or r.get("closed")
        if r.get("sold_back"):
            c["sold_back"] = r["sold_back"]
    for r in rows(db, "select * from sell_log", (), notes, "sell_log"):
        c = get(r["ticker"])
        c["legs"] = c["legs"] or [r["ticker"]]
        if r.get("combo"):
            c["label"] = r["combo"]
        c["dec"].append({k: r.get(k) for k in ("ts", "result", "why", "ride") + SELL_FIELDS if k in r})
    for r in log:
        t = r.get("ticker")
        if not t:
            continue
        c = get(t)
        c["legs"] = c["legs"] or [t]
        if r.get("combo"):
            c["label"] = r["combo"]
        c["dec"].append({"ts": r.get("at"), "result": r.get("result"), "why": r.get("why"), "ride": r.get("ride"),
                         **{k: r.get(k) for k in SELL_FIELDS if k in r}})
    return C


def matches(c, team, namer):
    team = team.lower()
    for tk in c["legs"]:
        if team in tk.lower() or team in namer.leg(tk)[0].lower():
            return True
    return False


def in_window(c, namer, day, spread):
    lo, hi = day - dt.timedelta(days=spread), day + dt.timedelta(days=spread)
    for tk in c["legs"]:
        d = namer.leg(tk)[1]
        if d and lo <= d <= hi:
            return True
    for ts in [c["first"], c["closed"]] + [d.get("ts") for d in c["dec"]]:
        try:
            if lo <= dt.datetime.fromtimestamp(float(ts)).date() <= hi:
                return True
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    return False


def sample(items, k):
    """k items spread evenly over a list, always keeping the first and the last."""
    if len(items) <= k:
        return items
    idx = sorted({round(i * (len(items) - 1) / (k - 1)) for i in range(k)})
    return [items[i] for i in idx]


def decision_line(d):
    bits = [f"{(d.get('result') or '?').upper()}"]
    if d.get("offer") not in (None, ""):
        bits.append("offer " + money(d["offer"]))
    if d.get("line") not in (None, ""):
        bits.append("sell line " + money(d["line"]))
    if d.get("chance") not in (None, ""):
        bits.append("chance " + pct(d["chance"]))
    if d.get("ride") not in (None, ""):
        bits.append(f"ride={clean(d['ride'], 20)}")
    why = clean(d.get("why"), 150)
    return "auto-sell " + ", ".join(bits) + (f": {why}" if why else "")


def report_one(t, c, db, namer, notes):
    L = []
    names = [namer.leg(tk)[0] for tk in c["legs"]]
    title = c["label"] or "(no log name)"
    L.append("=" * 72)
    L.append(f"{' + '.join(names) or 'unknown legs'}")
    L.append(f"  the app's log calls it: {clean(title, 40)}  (id ...{t[-6:]})")
    L.append(f"  cost {money(c['cost'])}, pays {money(c['pays'])} if it all hits, bought {stamp(c['first'])}")
    for tk, n in zip(c["legs"], names):
        last = rows(db, "select ts, chance, state from ticks where ticker=? order by ts desc limit 1", (tk,), notes, "ticks")
        if last:
            L.append(f"  leg: {n}: last seen {pct(last[0]['chance'])} chance ({stamp(last[0]['ts'])}, {clean(last[0]['state'], 12) or 'n/a'})")
        else:
            L.append(f"  leg: {n}: no chance history recorded")
    offs = rows(db, "select ts, p, pays, hold, offer, real_offer, verdict from offers where combo=? order by ts", (t,), notes, "offers")
    decs, seen = [], set()
    for d in sorted(c["dec"], key=lambda d: d.get("ts") or 0):      # a sale is in both the log file and the history file
        key = (round(float(d.get("ts") or 0) / 5), d.get("result"))
        if key not in seen:
            seen.add(key)
            decs.append(d)
    events = rows(db, "select ts, kind, text from events where combo=? and kind in ('settled','won','lost','cashed') order by ts", (t,), notes, "events")
    tl = [(d["ts"], 0, decision_line(d)) for d in decs if d.get("ts")]
    room = max(MAX_LINES - len(tl) - 2, 10)
    peak = max(offs, key=lambda o: o["offer"] or 0) if offs else None
    pick = sample(offs, room)
    if peak and peak not in pick:
        pick.append(peak)
    for o in pick:
        kind = "REAL Kalshi offer" if o["real_offer"] else "estimate (no Kalshi quote)"
        line = f"combo chance {pct(o['p'])}, {kind} {money(o['offer'])}"
        if o.get("hold") is not None:
            line += f", holding worth {money(o['hold'])}"
        if o.get("verdict"):
            line += f", app said: {clean(o['verdict'], 40)}"
        tl.append((o["ts"], 1, line + ("   <- peak offer" if o is peak else "")))
    for e in events:
        tl.append((e["ts"], 2, "RESULT " + clean(e["kind"], 12) + ": " + clean(e["text"], 100)))
    tl.sort(key=lambda x: (x[0] or 0, x[1]))
    L.append("  timeline (sampled):")
    if not tl:
        L.append("    nothing recorded for this combo (no offers, decisions or results)")
    for ts, _, text in tl[:MAX_LINES]:
        L.append(f"    {stamp(ts)}  {text}")
    if len(tl) > MAX_LINES:
        L.append(f"    ... {len(tl) - MAX_LINES} more lines not shown")
    outcome = c["outcome"] or c["status"] or "not recorded"
    sold = [d for d in decs if d.get("result") in ("sold", "hedged")]
    L.append(f"  final outcome: {clean(outcome, 30)}; money back {money(c['back'])}" + ("; AUTO-SOLD by the app" if sold else "; never auto-sold"))
    # summary
    real = [o["offer"] for o in offs if o["real_offer"] and o["offer"] is not None]
    anyo = [o["offer"] for o in offs if o["offer"] is not None]
    lines = [d["line"] for d in decs if d.get("line") not in (None, "")]
    skips = {}
    for d in decs:
        if d.get("result") in ("skipped", "failed"):
            k = clean(d.get("why"), 70)
            skips[k] = skips.get(k, 0) + 1
    L.append("  peak offer vs cost vs sell line:")
    L.append(f"    peak real Kalshi offer {money(max(real)) if real else 'none recorded'}; peak offer incl. estimates "
             f"{money(max(anyo)) if anyo else 'none recorded'}; cost {money(c['cost'])}; "
             f"highest sell line {money(max(lines)) if lines else 'not recorded'}")
    if real and lines:
        L.append("    the real offer " + ("DID reach" if max(real) >= min(lines) else "never reached") + " the sell line")
    if c["cost"] and real:
        L.append("    best real offer was " + ("above" if max(real) > c["cost"] else "never above") + " what it cost")
    for k, n in sorted(skips.items(), key=lambda kv: -kv[1])[:4]:
        L.append(f"    held back {n}x: {k}")
    return L


def build_report(db, log, team, day, notes=None):
    """The whole report as text. `db` is any open sqlite connection (row_factory sqlite3.Row), `log` the decision-log
    records (list of dicts), `day` a datetime.date. Importable, so another front end (e.g. a remote read-only endpoint)
    can reuse it; it only ever reads."""
    notes = [] if notes is None else notes
    namer = Namer()
    C = gather(db, log, notes)
    hits = {t: c for t, c in C.items() if matches(c, team, namer) and in_window(c, namer, day, 2)}
    L = [f"Combo trail for '{team}' around {day.isoformat()} (read-only; nothing was changed or sent anywhere)"]
    if not hits:
        L.append(f"No combos or bets with '{team}' in a leg were found within 2 days of {day.isoformat()}.")
    for t, c in sorted(hits.items(), key=lambda kv: kv[1]["first"] or 0):
        L += report_one(t, c, db, namer, notes)
    L += sorted(set(notes))
    return "\n".join(L)


def run(db_path, log_paths, team, date, out):
    notes = []
    try:
        day = dt.date.fromisoformat(date)
    except ValueError:
        print("--date must look like 2026-11-23")
        return 2
    try:
        db = open_ro(db_path)
    except sqlite3.Error as err:
        print(f"cannot open the history file read-only: {clean(err, 100)}")
        return 2
    log = read_log(log_paths, notes)
    text = build_report(db, log, team, day, notes)
    db.close()
    print(text)
    if out:
        try:
            Path(out).expanduser().write_text(text + "\n", encoding="utf-8")
            print(f"\nsaved to {Path(out).expanduser()}")
        except OSError as err:
            print(f"could not save the summary: {clean(err, 80)}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--team", required=True, help="team text to look for in the legs, e.g. nuggets")
    ap.add_argument("--date", required=True, help="the game day, e.g. 2026-11-23 (combos within 2 days are shown)")
    ap.add_argument("--db", default=None, help="history file (default: combo_history.db next to this script or the app, then ~/combowatch)")
    ap.add_argument("--log", default=None, help="decision log (default: combo_autosell_log.jsonl in the same places)")
    ap.add_argument("--out", default="~/combo_trail_summary.txt", help="where to also save the text (default ~/combo_trail_summary.txt)")
    ap.add_argument("--remote", action="store_true", help="read the production Mac over the dev-Mac log window instead of a local file")
    a = ap.parse_args(argv)
    if a.remote:
        sys.path.insert(0, str(HERE))
        import combo_trail_remote
        return combo_trail_remote.remote_main(a.team, a.date, a.out)
    spots = (HERE, HERE.parent, Path("~/combowatch").expanduser(), Path("."))
    path = a.db or next((str(d / "combo_history.db") for d in spots if (d / "combo_history.db").is_file()), None)
    if not path:
        print("no history file found: pass --db <file> (run this where the app's combo_history.db lives)")
        return 2
    logs = [a.log] if a.log else [str(d / "combo_autosell_log.jsonl") for d in (Path(path).parent,) + spots]
    return run(path, logs, a.team, a.date, a.out)


if __name__ == "__main__":
    sys.exit(main())
