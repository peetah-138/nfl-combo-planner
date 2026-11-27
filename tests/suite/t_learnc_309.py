# CHECK: group=engine
# Issue #309 (learn-c) nits, all read/record side (no buy, sell or size changes):
#  - _knob_items: a cashed combo's kick is its game start (recorded kickoff, else first in-play tick), not the buy time.
#  - sb_resolve: the second (universe) look does not repeat rows the first batch holds.
#  - _sb_results reads exit_shadow in pages (same rows, same order as one read), not one 200k-row read under the store lock.
import os, time, json, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
H = tempfile.mkdtemp()
E.store_open(os.path.join(H, "h.db")); E.HERE = H
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()

# --- kick
T = "KXNBAGAME-26NOV19LALBOS-LAL"
E.KICKOFF.pop("KXNBAGAME-26NOV19LALBOS", None)
buy = now - 5 * 3600
ok("no kickoff known: the buy time, as before", E._knob_game_kick([T], buy) == buy)
E.store_x("insert into ticks values(?,?,?,?,?)", (now - 3 * 3600, T, 0.5, "pre", ""))
E.store_x("insert into ticks values(?,?,?,?,?)", (now - 2 * 3600, T, 0.5, "live", "Q1"))
E.store_x("insert into ticks values(?,?,?,?,?)", (now - 1 * 3600, T, 0.5, "live", "Q2"))
ok("first in-play tick is used when no kickoff is known", abs(E._knob_game_kick([T], buy) - (now - 2 * 3600)) < 1)
E.KICKOFF["KXNBAGAME-26NOV19LALBOS"] = (E.dt.datetime.fromtimestamp(now - 2.5 * 3600, E.dt.timezone.utc)).isoformat()
ok("a recorded kickoff wins", abs(E._knob_game_kick([T], buy) - (now - 2.5 * 3600)) < 1)

# --- chunked read: same rows, same order, as one read
E._exit_shadow_table()
for i in range(25):
    E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, kick, price, fair, ev, route, old, new, ver, pays) "
              "values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (now - 100 + (i // 3), f"c{i}", "panel", "nhl", "single", json.dumps([f"KXNHLGAME-26NOV19G{i}-A"]), now - 50, 0.5, 0.55,
               0.1, "hold", 1, 1, 1, 9.0))
sql = "select rowid _rid, ts, tickers from exit_shadow where ts > ? order by ts"
whole = E.store_rows("select rowid _rid, ts, tickers from exit_shadow where ts > ? order by ts, rowid", (0,))
for chunk in (1, 4, 7, 25, 30):
    got = list(E._sb_rows_chunked(sql, 0, chunk))
    ok(f"chunk {chunk}: same rows in the same order", [r["_rid"] for r in got] == [r["_rid"] for r in whole] and len(got) == 25)
sql2 = "select rowid _rid, ts, tickers from exit_shadow where ts > ? and kind = 'single' order by ts"
ok("an extra where clause still pages", len(list(E._sb_rows_chunked(sql2, 0, 4))) == 25)

# --- sb_resolve: no repeated rows when the first batch is full
seen = []
real = E.store_rows
def spy(sql, args=()):
    r = real(sql, args)
    if "source='universe'" in sql:
        seen.append(r)
    return r
E.store_rows = spy
E.store_x("delete from exit_shadow")
for i in range(5):
    E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, kick, price, fair, ev, route, old, new, ver, pays) "
              "values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (now - 20000, f"u{i}", "universe", "nhl", "single", json.dumps([f"KXNHLGAME-26NOV19U{i}-A"]), now - 10 * 3600 + i, 0.5, 0.55,
               0.1, "hold", 1, 1, 1, 9.0))
asked = []
E.fetch_results = lambda tks: (asked.append(list(tks)), {})[1]
E.sb_resolve(now, limit=3)
ok("full first batch (3 of 5): the second look adds the other 2, not the same 3 again (all 5 looked up)",
   asked and len(asked[0]) == 5 and len(set(asked[0])) == 5)
E.store_rows = real
