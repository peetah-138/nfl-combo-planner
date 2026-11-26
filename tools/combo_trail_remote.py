#!/usr/bin/env python3
"""Combo trail from the dev Mac: `python3 tools/combo_trail.py --remote --team nuggets --date 2026-11-23`.
Pulls the rows it needs through the production Mac's read-only data window (tools/read_prod_logs.py: SELECT-only, token,
Tailscale only) plus the auto cash-out log, loads them into a throwaway in-memory database and runs the very same
build_report(). Nothing is written to the production Mac and no database file is copied."""
import datetime as dt
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from combo_trail import Namer, build_report, clean, gather, in_window, matches  # noqa: E402

SAFE_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")


def _load(mem, name, ans):
    """Put one answer of the read-only data window into an in-memory table of the same name."""
    cols = [c for c in ans.get("columns", []) if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(c))]
    if len(cols) != len(ans.get("columns", [])) or not cols:
        return
    mem.execute(f"create table if not exists {name}({', '.join(cols)})")
    mem.executemany(f"insert into {name} values({', '.join('?' * len(cols))})", [tuple(r) for r in ans.get("rows", [])])


def run_remote(team, date, out, get_db, get_log):
    """Same report, built from the production Mac's read-only data window instead of a local file.
    `get_db(**kw)` returns one db answer, `get_log()` the autosell records; nothing is written anywhere but `out`."""
    notes = []
    try:
        day = dt.date.fromisoformat(date)
    except ValueError:
        print("--date must look like 2026-11-23")
        return 2
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    for t in ("bets", "ledger", "sell_log"):
        ans = get_db(table=t)
        _load(mem, t, ans)
        if ans.get("truncated"):
            notes.append(f"note: only the newest {len(ans.get('rows', []))} rows of {t} were fetched")
    log = get_log()
    C = gather(mem, log, [])
    namer = Namer()
    hits = {t: c for t, c in C.items() if matches(c, team, namer) and in_window(c, namer, day, 2)}
    for t, c in hits.items():                                   # the detail tables, only for the combos that matched
        if not SAFE_ID.match(t):
            continue
        _load(mem, "offers", get_db(sql="select ts, combo, p, pays, hold, offer, real_offer, verdict from offers "
                                        f"where combo='{t}' order by ts desc limit 1000"))
        _load(mem, "events", get_db(sql="select ts, kind, combo, text from events "
                                        f"where combo='{t}' and kind in ('settled','won','lost','cashed') order by ts limit 200"))
        for tk in c["legs"][:12]:
            if SAFE_ID.match(str(tk)):
                _load(mem, "ticks", get_db(sql=f"select ts, ticker, chance, state from ticks where ticker='{tk}' order by ts desc limit 1"))
    text = build_report(mem, log, team, day, notes)
    mem.close()
    print(text)
    if out:
        try:
            Path(out).expanduser().write_text(text + "\n", encoding="utf-8")
            print(f"\nsaved to {Path(out).expanduser()}")
        except OSError as err:
            print(f"could not save the summary: {clean(err, 80)}")
    return 0


def remote_main(team, date, out):
    import read_prod_logs as R
    url, tok = R.settings()

    def get_db(**kw):
        try:
            return R.fetch_db(url, tok, limit=1000, **kw)
        except R.Failed as err:
            sys.exit(str(err))

    def get_log():
        try:
            ans = R.fetch(url, tok, "autosell", None, 500)
        except R.Failed as err:
            sys.exit(str(err))
        return [x["rec"] for x in ans.get("lines", []) if isinstance(x.get("rec"), dict)]
    return run_remote(team, date, out, get_db, get_log)
