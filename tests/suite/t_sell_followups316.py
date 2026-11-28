# CHECK: group=engine
# #316 item 3 (release 134 review follow-up), fail-closed, adds no spending:
#  3. the replay that learns the loss cut (_cut_guard_ts, used by smart_tune and sim_exit) confirms with the SAME counts live
#     uses for the bet's league (sl_confirm_params), not the starting constants, so it never cuts where live would wait;
# No real orders: nothing here trades.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
S1 = "KXNBAGAME-26NOV19NYKMIA-NYK"

# ---- the replay's confirmation counts follow live
c = {"id": "x", "kind": "single", "legs": [{"ticker": S1, "p": 0.55}], "stake": 5.0, "paid": 0.5, "kick": now - 5000,
     "result": "lost", "pl": -5.0}
seq = [(0.55, ""), (0.4, "Q2 6:00"), (0.12, "Q2 3:00"), (0.11, "Q2 2:00"), (0.1, "Q2 1:00"), (0.1, "Q2 0:30"),
       (0.1, "Half"), (0.08, "Q3 10:00"), (0.07, "Q3 9:00"), (0.06, "Q3 8:00"), (0.05, "Q3 7:00"), (0.0, "Final")]
for k, (ch, sc) in enumerate(seq):
    E.store_x("insert into ticks values(?,?,?,?,?)", (now - 5000 + 60 * (k + 1), S1, ch, "live", ("NYK 40–60 MIA " + sc) if sc else ""))
slp = E._sl_paths(c)
base = E._cut_guard_ts(c, slp, 0.2, 0.5, 0.2)
ok("starting counts (3 checks, 180 s): the cut first holds at the 11th minute", min(base) == round(now - 5000 + 60 * 11))
E.sl_confirm_params = lambda tks: (4, 180, 200)          # live wants 4 checks in a row: the guards first hold on the 4th (minute 11) too
ok("live counts of 4 checks (held on 4 checks here): the cut still holds at the 11th minute only",
   E._cut_guard_ts(c, slp, 0.2, 0.5, 0.2) == base)
E.sl_confirm_params = lambda tks: (5, 180, 200)          # 5 checks in a row: the record only has 4 held checks, so live would wait
ok("live counts of 5 checks: the replay makes no cut (the constants would have cut)", E._cut_guard_ts(c, slp, 0.2, 0.5, 0.2) == set())
ok("...and an explicit cf still wins over the live counts", E._cut_guard_ts(c, slp, 0.2, 0.5, 0.2, (3, 180, 200)) == base)
E.sl_confirm_params = lambda tks: (3, 300, 200)          # a longer span: 3 checks over 5 minutes, but only 3 minutes held
ok("live span of 300 s: the replay makes no cut (the constants would have cut)", E._cut_guard_ts(c, slp, 0.2, 0.5, 0.2) == set())
E.sl_confirm_params = lambda tks: (99, 180, 200)         # more checks than the path has: never a cut
ok("live wants more checks than the record has: no cut at all", E._cut_guard_ts(c, slp, 0.2, 0.5, 0.2) == set())
del E.sl_confirm_params

