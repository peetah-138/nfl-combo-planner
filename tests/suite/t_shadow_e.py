# CHECK: group=engine
# Shadow batch E (paper / record only; nothing here buys, sells or sizes a real bet):
#  #291 the Smart Buy paper book chooses like the real panel: one straight bet per game and family, spreads/totals capped
#       near a third of the panel, at most the panel size a day, best expected dollars first.
#  #474 mkt_holdout_report: what the true oldest-70% / newest-30% holdout says, read from the cached mkt_learn result.
import os, time, json, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
H = tempfile.mkdtemp()
E.store_open(os.path.join(H, "h.db")); E.HERE = H
E.SIZING_FILE = os.path.join(H, "s.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
K = now - 2 * 86400
E.save_json(E.SIZING_FILE, {"base": 1000.0})
E.CFG["panel_budget"] = 10 ** 6          # budget never the limiter: the rules under test are the panel's overlap rules
E._exit_shadow_table()


def row(t, kind, ev, out=4.5, pays=9.5, fair=0.55):
    E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, kick, price, fair, ev, route, old, new, ver, pays, "
              "res, outcome, grade) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (K - 600, f"panel:{t}", "panel", "nhl", kind, json.dumps([t]), K, 0.5, fair, ev, "hold", 1, 1, 1, pays,
               "won" if out > 0 else "lost", out, None))


def staked():
    E.sb_paper_build(now=now, force=True)
    return {json.loads(r["bet"])[0]: r for r in E.store_rows("select * from sb_paper") if r["stake"]}


# --- #291: one straight bet per game and family. Winner and spread are one family (best expected dollars wins), a total is its own.
row("KXNHLGAME-26NOV19G1-A", "single", 0.30)
row("KXNHLSPREAD-26NOV19G1-A1", "line", 0.50)      # the same game, same family, better ev: this one is kept
row("KXNHLTOTAL-26NOV19G1-5", "line", 0.10)        # a total is its own family: also kept (2 on the game is the cap)
st = staked()
ok("#291 winner and spread on one game are one family: only the best-dollar one is staked",
   "KXNHLSPREAD-26NOV19G1-A1" in st and "KXNHLGAME-26NOV19G1-A" not in st)
ok("#291 a total on the same game is its own family and is still staked", "KXNHLTOTAL-26NOV19G1-5" in st)
rows = {json.loads(r["bet"])[0]: r for r in E.store_rows("select * from sb_paper")}
ok("#291 the dropped one is still scored on paper (a row, not staked)",
   "KXNHLGAME-26NOV19G1-A" in rows and rows["KXNHLGAME-26NOV19G1-A"]["stake"] == 0 and rows["KXNHLGAME-26NOV19G1-A"]["plain"] is not None)

# --- #291: spreads/totals at most max(2, 30% of the panel size) = 3 a day.
E.store_x("delete from exit_shadow"); E.store_x("delete from sb_paper")
for i in range(6):
    row(f"KXNHLSPREAD-26NOV19L{i}-A1", "line", 0.9 - i * 0.05)
for i in range(2):
    row(f"KXNHLGAME-26NOV19W{i}-A", "single", 0.1 + i * 0.01)
st = staked()
lines = [t for t in st if "SPREAD" in t]
ok(f"#291 at most {max(2, int(E.PANEL['size'] * E.PANEL['line_share']))} spreads/totals a day", len(lines) == 3)
ok("#291 the cap keeps the best-dollar lines", set(lines) == {f"KXNHLSPREAD-26NOV19L{i}-A1" for i in range(3)})
ok("#291 straight winners beyond the line cap are still staked", sum("GAME" in t for t in st) == 2)

# --- #291: at most the panel size (10) a day.
E.store_x("delete from exit_shadow"); E.store_x("delete from sb_paper")
for i in range(14):
    row(f"KXNHLGAME-26NOV19Z{i:02d}-A", "single", 0.9 - i * 0.01)
st = staked()
ok("#291 no more than the panel's size staked in a day", len(st) == E.PANEL["size"])
ok("#291 the ones kept are the best expected dollars", set(st) == {f"KXNHLGAME-26NOV19Z{i:02d}-A" for i in range(10)})

# --- #291: paper only: no panel/ledger rows, no settings file written.
ok("#291 the paper book writes no panel or ledger table",
   not E.store_rows("select name from sqlite_master where name in ('panel', 'ledger')"))
ok("#291 sizing file untouched", json.load(open(E.SIZING_FILE)) == {"base": 1000.0})

# --- #474: the report.
W = {"a": {"n": 300, "w": 0.5, "gain": 0.01, "se": 0.002, "hold_n": 90, "oos_w": 0.5, "oos_gain": 0.004, "vetoed": False},
     "b": {"n": 300, "w": 0.0, "gain": 0.01, "se": 0.002, "hold_n": 90, "oos_w": 0.0, "oos_gain": 0.0, "vetoed": True},
     "c": {"n": 300, "w": 0.0, "gain": 0.0, "se": 0.002, "hold_n": 90, "oos_w": 0.25, "oos_gain": 0.003, "vetoed": False},
     "d": {"n": 50, "w": 0.0, "gain": 0, "se": 1, "hold_n": 15, "oos_w": 0.0, "oos_gain": 0.0, "vetoed": False}}
r = E.mkt_holdout_report(W)
ok("#474 groups under min_n are not counted", r["groups"] == 3)
ok("#474 earned = kept or vetoed after the in-sample bar", r["earned"] == 2)
ok("#474 oos_pass counts groups whose oldest-70% weight gained on the newest 30%", r["oos_pass"] == 2)
ok("#474 the holdout refuses the earned group whose oldest-70% weight did not gain", r["oos_refuses"] == 1)
ok("#474 mean out-of-sample gain", abs(r["mean_oos_gain"] - round((0.004 + 0 + 0.003) / 3, 4)) < 1e-9)
ok("#474 empty input gives {}", E.mkt_holdout_report({}) == {})
before = dict(E.MKT_W["w"])
E.mkt_holdout_report(W)
ok("#474 the report changes no weight", E.MKT_W["w"] == before)
