# CHECK: group=engine
# Weigh a hedge before skipping a below-cost sale, PAPER ONLY (issue #312). When auto cash-out skips a sale because the
# offer is under what the combo cost, the moment's numbers are recorded in `hedge_skip` (selling now net of fees, what a
# hedge on the other side would lock in, the cost) and `hedge_skip_report` sums them against how the bet really ended.
# It never buys: no order is sent, the skip still happens, a broken recorder changes nothing, nothing reads the table
# to decide. No real orders: every trading call is faked here.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl"); E.HEDGES = os.path.join(E.HERE, "hedges.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
T = "KXNBAGAME-26NOV19LALBOS-LAL"
T2 = "KXNBAGAME-26NOV19LALBOS-BOS"
E.CFG.update(auto_sell=True, auto_hedge=True, prefer_hedge=True, hedge_cap=100, stop_loss=False, smart_sell=True,
             ride=2, take_profit=0, lock_trail=False, auto_cap=5)
E.MINE["all_games"] = {"g": [{"ticker": T, "pick": "Lakers", "p": 0.7}, {"ticker": T2, "pick": "Celtics", "p": 0.3}]}
h = {"label": "Combo 1", "need": [(("yes", T), "Lakers")], "pre_of": {T: 0.6}, "ch_of": {T: 0.7},
     "legs_left": [(0.7, True, 0)], "cost": 10, "p": 0.7, "pays": 20, "won_some": True, "left": 1}
E.leg_score = lambda l: None
sent, sold, logs = [], [], []
E.kalshi_send = lambda m, p, b=None, params=None: (sent.append((p, b)), {"fill_count": 1})[1]
E.can_trade = lambda: True
E.take_profit_reason = lambda t, hh, cut_ok=False: ("smart", 5.0)
OFFER = {"v": 8.0}
E.get_cash_offer = lambda t, f=1.0: {"offer": OFFER["v"], "frac": 1.0, "rfq": "x", "contracts": 20, "at": E.time.time()}
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], None)
E.sold_today = lambda: 0
E.smart_sell_singles = lambda: []
E.accept_cash = lambda t, floor=None: (sold.append(t), "sold")[1]
E.drop_cash = lambda t: E.MINE["cash"].pop(t, None)
E.haptic = lambda *a: None
real_log = E.log_decision
E.log_decision = lambda rec: (logs.append(rec), real_log(rec))
E.save_json(E.HEDGES, {})


def run(offer=8.0, **hx):
    OFFER["v"] = offer
    E.MINE["busy"] = False; E.MINE.setdefault("selling", set())
    E.MINE["hold"] = {"C1": dict(h, **hx)}; E.MINE["tp_asked"] = {}; E.MINE["cash"] = {}
    return E.auto_sell_now({"acts": {}})


def rows():
    return E.store_rows("select * from hedge_skip order by ts")


# ---- a below-cost offer is skipped as before, and the paper row has both sums
run(8.0)
sk = [r for r in logs if r.get("result") == "skipped" and r.get("why") == "below what you paid"]
ok("still skipped: below what you paid, nothing sold, no order sent", sk and not sold and not sent)
r = rows()
ok("one paper row", len(r) == 1 and r[0]["ticker"] == "C1" and r[0]["kind"] == "combo")
ok("selling now: $8 for a $10 combo", r and r[0]["whole"] == 8.0 and r[0]["cost"] == 10.0)
# 20 Celtics at 30c: cost 6.00 + fee, locks in 20 - cost; the lock beats the cost, so it meets auto-hedge's own guard
hg = E.hedge_for("C1") if E.MINE["hold"] else None
ok("hedge sums are hedge_for's, fee included", r and abs(r[0]["locked"] - hg["locked"]) < 0.005 and r[0]["hcost"] > 6.0)
ok("the hedge lock-in meets the guard (locks in 13.7 vs cost 10)", r and r[0]["hok"] == 1)
ok("the tuning switches and the auto-hedge setting stay as they were", E.CFG["auto_hedge"] is True and not sent)

# ---- a repeat inside 10 minutes adds no row; a hedge that would not lock in the cost is marked so
run(8.0)
ok("one row per bet per 10 minutes", len(rows()) == 1)
E.HEDGE_SKIP_SEEN.clear()
E.MINE["all_games"] = {"g": [{"ticker": T, "pick": "Lakers", "p": 0.7}, {"ticker": T2, "pick": "Celtics", "p": 0.6}]}
run(8.0, cost=15.0)
r = rows()
ok("a hedge locking in less than the cost is recorded but not ok", len(r) == 2 and r[1]["hok"] == 0 and r[1]["locked"] < 15.0)
E.MINE["all_games"] = {"g": [{"ticker": T, "pick": "Lakers", "p": 0.7}, {"ticker": T2, "pick": "Celtics", "p": 0.3}]}

# ---- an offer at or above cost is not a skip: no row
E.HEDGE_SKIP_SEEN.clear()
n0 = len(rows())
run(12.0)
ok("a sale at/above cost writes no skip row", len(rows()) == n0)

# ---- a recorder that breaks changes nothing
E.HEDGE_SKIP_SEEN.clear(); logs.clear()
real_hf = E.hedge_for
calls = []
E.hedge_for = lambda t, price=None: (calls.append(1), (_ for _ in ()).throw(RuntimeError("boom")))[1] if len(calls) < 1 else real_hf(t, price)
try:
    E.hedge_skip_note("combo", {"ticker": "Z", "cost": 5, "pays": 10}, 3.0, dict(h))
    ok("a failing recorder never raises", True)
except Exception:
    ok("a failing recorder never raises", False)
E.hedge_for = real_hf
E.store_x("drop table hedge_skip"); E.STORE["hskip_ok"] = False; E.HEDGE_SKIP_SEEN.clear()
try:
    E.hedge_skip_note("single", {"ticker": "S1", "cost": 5, "pays": 10, "why": "x"}, 3.0)
    ok("a missing table is rebuilt, a single has no hedge", E.store_rows("select hcost, locked from hedge_skip")[0]["locked"] is None)
except Exception:
    ok("a missing table is rebuilt, a single has no hedge", False)
E.store_x("drop table hedge_skip"); E.STORE["hskip_ok"] = False
ok("report on a missing table is empty, never raises", E.hedge_skip_report() == {"n": 0})

# ---- the report: aggregates against what the bets really did
E.store_x("create table if not exists hedge_skip(ts real, ticker text, kind text, league text, why text, live int, "
          "cost real, pays real, whole real, hcost real, locked real, hok int, chance real)")
E.STORE["hskip_ok"] = True
E._ledger_table()
ins = "insert into hedge_skip values(?,?,?,?,?,?,?,?,?,?,?,?,?)"
t0 = time.time()
E.store_x(ins, (t0 - 900, "A", "combo", "nba", "below what you paid", 1, 10, 20, 9, 6, 14, 1, .7))   # older row of A: ignored
E.store_x(ins, (t0 - 100, "A", "combo", "nba", "below what you paid", 1, 10, 20, 8, 6, 13.7, 1, .7))  # A won: hold +10
E.store_x(ins, (t0 - 100, "B", "combo", "nba", "below what you paid", 1, 10, 20, 8, 6, 13.7, 1, .7))  # B lost: hold -10
E.store_x(ins, (t0 - 100, "C", "single", "nba", "below what you paid", 1, 10, 20, 7, None, None, 0, .5))  # C: open, no hedge
E.store_x(ins, (t0 - 90 * 86400, "D", "combo", "nba", "x", 1, 10, 20, 7, 6, 13, 1, .5))                # too old
for tk, oc in (("A", "won"), ("B", "lost")):
    E.store_x("insert into ledger(ticker, outcome) values(?,?)", (tk, oc))
rep = E.hedge_skip_report(30)
ok("counts each bet once, last moment, inside the window", rep["n"] == 3 and rep["hedge_n"] == 2 and rep["locks_cost_n"] == 2)
ok("sell now vs cost: -2 -2 -3", rep["sell_pnl"] == -7.0)
ok("hedge vs cost: +3.7 each", rep["hedge_pnl"] == 7.4)
ok("settled: 2 bets, holding paid +10 and -10", rep["settled_n"] == 2 and rep["hold_pnl"] == 0.0)
ok("hedge beat holding by 3.7-10 + 3.7+10", rep["hedge_beats_hold"] == 7.4 and rep["sell_beats_hold"] == -4.0)
ok("aggregates only: no tickers in the report", not any(isinstance(v, str) for v in rep.values()) and "A" not in str(rep))

# ---- never buys; no decision code reads the table (only the report function does)
src = open("wahome/engine.py").read()
import re
users = {m.group(1) for m in (re.search(r"def (\w+)\(", l) for l in src.split("\n\n\n") if "from hedge_skip" in l or "hedge_skip s" in l) if m}
ok("only the report (and the recorder's own pruning) touch the paper table", users <= {"hedge_skip_report", "hedge_skip_note"} and "hedge_skip_report" in users)
ok("no order was ever sent by any of this", not sent)
