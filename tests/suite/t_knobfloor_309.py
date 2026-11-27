# CHECK: group=engine
# Issue #309 (learn-c): the knobs' LOWEST allowed values, through a real auto_sell_now pass, must not loosen the two guards
# that matter: a profit-taking sale never goes under what was paid (even at auto_slip's floor, 0.90 of the line), and the
# daily cap of automatic sales still stops the next one. No real orders: every trading call is faked.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
T = "KXNBAGAME-26NOV19LALBOS-LAL"
lo = E.KNOB_BY["auto_slip"]["min"]
ok("auto_slip's lowest allowed value is 0.90 (the registry bound)", lo == 0.9)
ok("the lowest allowed cut_accept is above zero, and zero or below it is refused",
   E.KNOB_BY["cut_accept"]["min"] > 0 and not E._knob_valid("cut_accept", 0.0) and E._knob_valid("cut_accept", E.KNOB_BY["cut_accept"]["min"]))
ok("the lowest allowed auto_slip is accepted, below it is refused", E._knob_valid("auto_slip", lo) and not E._knob_valid("auto_slip", lo - 0.01))

E.CFG.update(smart_sell=True, auto_sell=True, auto_cap=1, stop_loss=False, auto_hedge=False)
E.can_trade = lambda: True
E.trading_paused = lambda: False
E.knob_auto_slip = lambda tks: lo                           # the knob stepper at its lowest allowed value
E.take_profit_reason = lambda t, h, cut=False: ("lock in", 10.0)    # profit rule says: sell at 10.00 or more
E.combo_wait_why = lambda *a, **k: None
E.wait_threshold = lambda t: 10.0
E.hands_off = lambda t: False
E.manual_selling = lambda t: False
E.hedge_unsure = lambda t: False
E.rfq_unsure = lambda t, s: False
E.real_ask_gate = lambda t, exempt=False: (True, "")
E.fetch_account = lambda **k: ([{"ticker": t, "status": "pending", "pays": 20} for t in ("C1", "C2")], 300.0, None)
state = {"sold": 0}
E.sold_today = lambda: state["sold"]
sells = []
def accept(t, floor=None):
    sells.append(t); state["sold"] += 1
    return "✅ sold"
E.accept_cash = accept
E.accept_once = lambda o, t=None: (sells.append(o.get("ticker") or t), "✅ sold")[1]
E.place_hedge = lambda *a, **k: "no"
E.hedge_for = lambda t: None

def hold(cost):
    return {"label": "Lakers combo", "need": [(("yes", T), "Lakers")], "pre_of": {T: 0.6}, "ch_of": {T: 0.9},
            "legs_left": [(0.9, False, 0)], "cost": cost, "p": 0.9, "pays": 20, "won_some": True, "left": 1}

def run(offer, ticks=("C1",)):
    sells.clear(); state["sold"] = 0
    E.MINE["busy"] = False
    E.MINE["hold"] = {t: hold(10.0) for t in ticks}
    E.MINE["cash"] = {t: {"offer": offer, "frac": 1.0, "rfq": "r", "quote": "q", "contracts": 20, "at": time.time()} for t in ticks}
    E.MINE["tp_asked"] = {}
    E.MINE.setdefault("selling", set())
    E.auto_sell_now({"acts": {}})
    return list(sells)

logs = []
real_log = E.log_decision
E.log_decision = lambda rec: (logs.append(rec), real_log(rec))
got = run(9.4)      # 94% of the 10.00 line: passes auto_slip's lowest bar (9.00) but is under the 10.00 cost
ok("a profit-taking offer under cost does not sell at auto_slip's lowest value", got == [])
ok("...and the log says it was held for being below what was paid", any(r.get("why") == "below what you paid" for r in logs))
logs.clear()
got = run(10.4, ("C1", "C2"))
ok("an offer over cost sells, once: the daily cap (1) stops the second combo", len(got) == 1)
ok("...and the cap is logged", any(r.get("why") == "daily cap reached" for r in logs))
