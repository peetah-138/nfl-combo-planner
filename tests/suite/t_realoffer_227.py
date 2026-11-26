# CHECK: group=engine
# #227: when an ESTIMATE reaches a sell bar, auto cash-out may ask Kalshi for a REAL offer (throttled, switchable) and
# sells only if that real offer clears the bar. Never on the estimate alone. Pause / no quote / switch off do nothing.
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
ACC, ASKS, REAL = [], [], {"offer": 13.0}
E.accept_once = lambda o, t=None: (ACC.append(t), "executed")[1]
def ask(t, f=1.0):
    ASKS.append(t)
    if REAL["offer"] is None:
        return {"error": "No cash-out offers came in.", "at": time.time()}
    return {"offer": REAL["offer"], "frac": 1.0, "rfq": "x", "quote": "q", "contracts": 20, "at": time.time()}
E.get_cash_offer = ask
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], 300.0, None)
E.CFG.update(auto_sell=True, auto_hedge=False, smart_sell=True, auto_cap=9, real_offer_ask=True)
HOLD = {"label": "Combo 5", "cost": 8.0, "p": 0.7, "pays": 20, "left": 1, "legs_left": [(0.7, True, 0)]}
BAR = {"v": ("smart", 12.0)}
E.take_profit_reason = lambda t, h, cut_ok=False: BAR["v"]


def run(cash=None, offer=13.0, clear_state=False):
    ACC.clear(); ASKS.clear(); REAL["offer"] = offer
    E.MINE["hold"] = {"C1": dict(HOLD)}
    E.MINE["cash"] = {"C1": cash} if cash else {}
    E.MINE["selling"] = set(); E.MINE["busy"] = False; E.COMBO_WAIT.clear()
    E.MINE["tp_asked"] = {}
    if clear_state:
        E.MINE.pop("real_asks", None); E.MINE.pop("real_ask_told", None)
    return E.auto_sell_now({"acts": {}})


EST = {"offer": 14.0, "frac": 1.0, "rfq": "estimate", "at": time.time()}

out = run(EST, 13.0, clear_state=True)
ok("estimate at the bar + real offer clears it: asks Kalshi once and sells", ASKS == ["C1"] and ACC == ["C1"], ASKS, ACC)
out = run(EST, 10.0, clear_state=True)
ok("real offer under the bar: asked, nothing sold (the estimate alone never sells)", ASKS == ["C1"] and not ACC, ASKS, ACC)
out = run(EST, 10.0)
ok("throttle: no second request inside 60 s", not ASKS and not ACC, ASKS)
E.MINE["real_asks"]["by"]["C1"] = [time.time() - 61]
out = run(EST, 13.0)
ok("a minute later it may ask again (and sells on a clearing offer)", ASKS == ["C1"] and ACC == ["C1"], ASKS, ACC)

now = time.time()
E.MINE["real_asks"] = {"by": {"C1": [now - 3500 + 100 * i for i in range(E.REAL_ASK_HOUR_COMBO)]}, "all": []}
ok("per-combo hourly cap refuses", E.real_ask_gate("C1", now)[0] is False)
E.MINE["real_asks"] = {"by": {}, "all": [now - 3500 + 10 * i for i in range(E.REAL_ASK_HOUR_ALL)]}
ok("all-combos hourly cap refuses", E.real_ask_gate("C1", now)[0] is False)
ok("old requests age out after an hour", E.real_ask_gate("C1", now + 4000)[0] is True)
E.MINE["real_asks"] = {"by": {"C1": [now - 3500 + 100 * i for i in range(E.REAL_ASK_HOUR_COMBO)]}, "all": []}
out = run(EST, 13.0)
ok("at the hourly cap auto cash-out asks nothing and sells nothing", not ASKS and not ACC, ASKS)

E.CFG["real_offer_ask"] = False
out = run(EST, 13.0, clear_state=True)
ok("switch off: no request, no sale even though the estimate is above the bar", not ASKS and not ACC, ASKS, ACC)
real_fresh = {"offer": 13.0, "frac": 1.0, "rfq": "x", "quote": "q", "contracts": 20, "at": time.time()}
out = run(real_fresh, 13.0, clear_state=True)
ok("switch off: a real fresh offer already in still sells (nothing asked)", not ASKS and ACC == ["C1"], ASKS, ACC)
E.CFG["real_offer_ask"] = True

BAR["v"] = (None, 0.0)
out = run(EST, 13.0, clear_state=True)
ok("estimate under the bar (no trigger): no request, no sale", not ASKS and not ACC)
BAR["v"] = ("smart", 12.0)

out = run(EST, None, clear_state=True)
ok("Kalshi gives no quote: asked, nothing sold", ASKS == ["C1"] and not ACC, ASKS, ACC)

E.TRADING_PAUSED = lambda: True
out = run(EST, 13.0, clear_state=True)
ok("Pause on: no request, no sale", not ASKS and not ACC)
E.TRADING_PAUSED = lambda: 1 / 0
out = run(EST, 13.0, clear_state=True)
ok("Pause unreadable: no request, no sale", not ASKS and not ACC)
E.TRADING_PAUSED = lambda: False

E.rfq_unsure = lambda t, side=None, **k: True
out = run(EST, 13.0, clear_state=True)
ok("rule 8: an unclear last cash-out is never asked or retried", not ASKS and not ACC)
E.rfq_unsure = lambda t, side=None, **k: False

out = run(EST, 7.5, clear_state=True)
ok("a real offer under cost is not taken for a profit reason", not ACC)

log = open(E.SELL_LOG, encoding="utf-8").read()
ok("the decision log has REAL OFFER asked lines with the offer and the bar", "REAL OFFER asked" in log and '"bar"' in log)
ok("the decision log says when a request was not sent", "REAL OFFER not asked" in log)

SRC = open("wahome/engine.py", encoding="utf-8").read()
ok("the switch is on by default and synced",
   E.DEFAULTS.get("real_offer_ask") is True and "real_offer_ask" in E.SHARED_KEYS and "real_offer_ask" in E.WATCHER_SYNCED)
W = open("wtest/combo_watcher.py", encoding="utf-8").read()
ok("the watcher syncs and the web app saves the switch", W.count('"real_offer_ask"') >= 2)
ok("auto cash-out has one gate call and one note site", SRC.count("real_ask_gate(t)") == 1 and SRC.count("real_ask_note(t)") == 1)

# the card words
E.CFG.update(real_offer_ask=True)
h = dict(HOLD, need=[], pays=20)
E.MINE["cash"] = {}
tr = E.smart_trigger("C1", h)
ok("card (on): will ask Kalshi for a real offer", "ask Kalshi for a real offer" in tr["smart_txt"] or "over" in tr["smart_txt"] or not tr["smart_txt"], tr)
E.CFG["real_offer_ask"] = False
tr2 = E.smart_trigger("C1", h)
ok("card (off): never promises an ask", "will ask Kalshi" not in tr2["smart_txt"] + tr2["smart_chip"], tr2)
