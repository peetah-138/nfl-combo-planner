# CHECK: group=engine
# Refs #514: a stored cash-out offer that is an ERROR dict (Kalshi said "no offers") has no 'offer' key. auto_sell_now
# must never raise KeyError on it: that combo is only an estimate (never sold on), and the rest of the pass still runs.
# Kalshi is faked; nothing is sent.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl"); E.HEDGES = os.path.join(E.HERE, "hedges.json")
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
E.can_trade = lambda: True
E.haptic = E.loading = lambda *a: None
E.resting_sells = lambda: {}
E.drop_cash = lambda t: E.MINE["cash"].pop(t, None)
E._cash_pause = lambda s: None
E.smart_sell_singles = lambda: []
E.TRADING_PAUSED = lambda: False
ACC, ASKS = [], []
E.accept_once = lambda o, t=None: (ACC.append(t), "executed")[1]
def ask(t, f=1.0):
    ASKS.append(t)
    if t == "C1":
        return {"error": "No cash-out offers came in.", "at": time.time()}
    return {"offer": 13.0, "frac": 1.0, "rfq": "x", "quote": "q", "contracts": 20, "at": time.time()}
E.get_cash_offer = ask
E.fetch_account = lambda **k: ([{"ticker": t, "status": "pending", "pays": 20} for t in ("C1", "C2", "C3")], 300.0, None)
E.CFG.update(auto_sell=True, auto_hedge=False, smart_sell=True, auto_cap=9, real_offer_ask=True)
HOLD = {"label": "Test", "cost": 8.0, "p": 0.7, "pays": 20, "left": 1, "legs_left": [(0.7, True, 0)]}
BARS = {"C1": ("smart", 12.0), "C2": ("cut loss", 5.0), "C3": ("smart", 12.0)}
E.take_profit_reason = lambda t, h, cut_ok=False: BARS.get(t, (None, 0.0))
now = time.time()
ERR = {"error": "No cash-out offers came in.", "at": now}
EST = {"offer": 14.0, "frac": 1.0, "rfq": "estimate", "at": now}
REAL = {"offer": 13.0, "frac": 1.0, "rfq": "x", "quote": "q", "contracts": 20, "at": now}


def run(cash, real_ask_off=False):
    ACC.clear(); ASKS.clear()
    E.MINE["hold"] = {t: dict(HOLD) for t in ("C1", "C2", "C3")}   # C1 first: the error combo comes before the others
    E.MINE["cash"] = dict(cash)
    E.MINE["selling"] = set(); E.MINE["busy"] = False; E.COMBO_WAIT.clear(); E.MINE["tp_asked"] = {}
    E.MINE.pop("real_asks", None); E.MINE.pop("real_ask_told", None)
    return E.auto_sell_now({"acts": {}})


for label, err in (("error dict with a stored 'at'", ERR), ("error dict, no 'rfq'", {"error": "x"}), ("offer None", {"offer": None, "rfq": "x", "at": now})):
    try:
        run({"C1": dict(err), "C2": dict(REAL), "C3": dict(EST)})
        raised = None
    except Exception as e:
        raised = repr(e)
    ok(f"{label}: the pass does not raise", raised is None, raised)
    ok(f"{label}: the stop-loss/cut-loss combo AFTER the error combo is still sold", "C2" in ACC, ACC)
    ok(f"{label}: the normal estimate combo AFTER it is still evaluated, asked and sold", "C3" in ASKS and "C3" in ACC, ASKS, ACC)
    ok(f"{label}: the error combo is never sold on a missing offer", "C1" not in ACC, ACC)

E.TRADING_PAUSED = lambda: True
run({"C1": dict(ERR), "C2": dict(REAL), "C3": dict(EST)})
ok("Pause on: nothing asked or sold, error combo or not", not ASKS and not ACC)
E.TRADING_PAUSED = lambda: False
E.CFG["real_offer_ask"] = False
run({"C1": dict(ERR), "C2": dict(REAL), "C3": dict(EST)})
ok("real-ask switch off: no request and no sale from an error dict (a real fresh one still sells)", "C1" not in ASKS and "C1" not in ACC and "C2" in ACC, ASKS, ACC)
E.CFG["real_offer_ask"] = True
E.rfq_unsure = lambda t, side=None, **k: t == "C1"
run({"C1": dict(ERR), "C2": dict(REAL), "C3": dict(EST)})
ok("rule 8: an unclear last cash-out on the error combo is never asked, others go on", "C1" not in ASKS and "C2" in ACC, ASKS, ACC)
