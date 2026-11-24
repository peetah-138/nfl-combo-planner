# CHECK: group=engine
# #245: Pete's own Cash out tap on a combo works while Pause is on; every automatic sale still stops under Pause, and the
# tap path can never be reached by an automatic caller. Kalshi is faked; nothing is sent.
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
ACC = []
E.accept_once = lambda o, t=None: (ACC.append(t), "executed")[1]
E.TRADING_PAUSED = lambda: True                      # Pause on
E.CFG.update(auto_sell=True, auto_hedge=False, smart_sell=True, auto_cap=9)
HOLD = {"label": "Combo 5", "cost": 8.0, "p": 0.7, "pays": 20, "left": 1, "legs_left": [(0.7, True, 0)]}

def tap():
    ACC.clear()
    E.MINE["hold"] = {"C1": dict(HOLD)}
    E.MINE["cash"] = {"C1": {"offer": 13.0, "frac": 1.0, "rfq": "x", "quote": "q", "contracts": 20, "at": time.time()}}
    E.MINE["selling"] = set(); E.MINE["busy"] = False
    return E.accept_cash("C1")

E._CASH_CTX.auto = False
m = tap()
ok("Paused: your own combo Cash out still sells (one accept)", m.startswith("✅") and ACC == ["C1"], m)
E.TRADING_PAUSED = lambda: 1 / 0                     # a Pause that can't be read counts as paused
m = tap()
ok("Pause unreadable: your own tap still sells", m.startswith("✅") and ACC == ["C1"], m)
E.TRADING_PAUSED = lambda: True
E.rfq_unsure = lambda t, side=None, **k: True
m = tap()
ok("Paused + unknown outcome on file: your tap is still blocked (rule 8), nothing accepted", m.startswith("⚠️") and not ACC, m)
E.rfq_unsure = lambda t, side=None, **k: False

# automatic callers: nothing sells while paused, even with Auto cash-out still switched on in the settings
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 12.0)
E.get_cash_offer = lambda t, f=1.0: {"offer": 13.0, "frac": 1.0, "rfq": "x", "quote": "q", "contracts": 20, "at": time.time()}
E.smart_sell_singles = lambda: ["single sold"]
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], 300.0, None)
ACC.clear(); E.MINE["hold"] = {"C1": dict(HOLD)}; E.MINE["busy"] = False; E.MINE["selling"] = set()
out = E.auto_sell_now({"acts": {"C1": 1.0}})
ok("Paused: auto cash-out / smart sell does nothing (no singles pass, no accept)", out == [] and not ACC, out)
E.TRADING_PAUSED = lambda: False
E.COMBO_WAIT.clear(); E.MINE["cash"] = {"C1": dict(E.get_cash_offer("C1"))}
out = E.auto_sell_now({"acts": {"C1": 1.0}})
ok("control: not paused, the same call does run (the test can fail)", bool(out), out)

# a retry mid-round under Pause stops (auto only)
SRC = open("wahome/engine.py", encoding="utf-8").read()
ok("auto retries still stop on Pause; a tap's retries have no Pause check",
   'if auto and (trading_paused() or not CFG.get("auto_sell") or not can_trade()):' in SRC)
W = open("wtest/combo_watcher.py", encoding="utf-8").read()
i = W.index('if do == "sell":'); j = W.index("accept_cash(t)", i)
ok("the web cash-out calls accept_cash with no auto context; only auto_sell_now sets _CASH_CTX.auto",
   "_CASH_CTX" not in W[i - 1500:j] and SRC.count("_CASH_CTX.auto = True") == 1)
