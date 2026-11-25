# CHECK: group=engine
# Logging and display only (no buy, sell or size changes): #300 an automatic combo sale's log line carries the estimate
# smart sell held it against (disc, est); #316 a single's break episode is filed under the HELD market (not the
# game-winner stand-in used to find the score) and a full BRK_EP drops its oldest episode, not every open one.
# No real orders: every Kalshi call is faked here.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl"); E.HEDGES = os.path.join(E.HERE, "hedges.json")
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
_real_time = time.time
now = _real_time()
T = "KXNBAGAME-26NOV19LALBOS-LAL"
E.CFG.update(auto_sell=True, auto_hedge=False, stop_loss=False, smart_sell=True, ride=2, take_profit=0,
             lock_trail=False, auto_cap=5)
h = {"label": "Combo 1", "need": [(("yes", T), "Lakers")], "pre_of": {T: 0.6}, "ch_of": {T: 0.7},
     "legs_left": [(0.7, True, 0)], "cost": 10, "p": 0.7, "pays": 20, "won_some": True, "left": 1}

E.can_trade = lambda: True
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 12.0)
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], None)
E.smart_sell_singles = lambda: []
E.haptic = E.loading = lambda *a: None
E.resting_sells = lambda: {}
E.drop_cash = lambda t: E.MINE["cash"].pop(t, None)
E._cash_pause = lambda s: None
SC = {"sc": {"state": "in", "me": 21, "opp": 17, "brk": False}}
E.leg_score = lambda l: dict(SC["sc"]) if SC["sc"] else None
asks, accepts, logs = [], [], []
SCRIPT = {"s": []}
E.get_cash_offer = lambda t, f=1.0: (asks.append(t), {"offer": 13.0, "frac": 1.0, "rfq": "x", "quote": "q",
                                                       "contracts": 20, "at": E.time.time()})[1]


def fake_accept(o, t=None):
    accepts.append(o["offer"])
    st = SCRIPT["s"].pop(0) if SCRIPT["s"] else "cancelled"
    if st == "unknown":
        E.mark_rfq_unsure(t, "sell", "test")
    if st == "failed":
        E.ACCEPT_ERR[t] = "quote expired"
    return st


E.accept_once = fake_accept
real_log = E.log_decision
E.log_decision = lambda rec: (logs.append(rec), real_log(rec))
plan = {"acts": {}}


def tick(dt_, script=(), cash=None, **hold):
    SCRIPT["s"] = list(script)
    E.time.time = lambda: now + dt_
    E.MINE["hold"] = {"C1": dict(h, **hold)}
    E.MINE["tp_asked"] = {}; E.MINE["cash"] = {"C1": dict(cash, at=now + dt_)} if cash else {}; E.MINE["busy"] = False; E.MINE.setdefault("selling", set())
    asks.clear(); accepts.clear(); logs.clear()
    try:
        return E.auto_sell_now(plan)
    finally:
        E.time.time = _real_time


def reset():
    E.COMBO_WAIT.clear(); E.MINE["combo_fail_told"] = {}; SC["sc"] = {"state": "in", "me": 21, "opp": 17, "brk": False}
    E.save_json(E.ORDER_LEDGER, {}); E._ORDER_SHARED.unsure.clear()   # Pete cleared the order block



# ---- #300: the sale's estimate is on its log line
E.MINE["hold"] = {"C1": dict(h)}
E.time.time = lambda: now
E.MINE["tp_asked"] = {}; E.MINE["cash"] = {}; E.MINE["busy"] = False; E.MINE.setdefault("selling", set())
SCRIPT["s"] = ["executed"]
try:
    E.auto_sell_now(plan)
finally:
    E.time.time = _real_time
sold = [r for r in logs if r.get("result") == "sold"]
d = E.kalshi_discount(True)
ok("#300 a sale is logged with the discount and the estimate (disc x chance x pays x share)",
   len(sold) == 1 and abs(sold[0]["disc"] - round(d, 4)) < 1e-9 and abs(sold[0]["est"] - round(d * 0.7 * 20 * 1.0, 2)) < 0.006
   and sold[0]["offer"] == 13.0, sold)
ok("#300 ...the same offer and cut-off as before (logging only)", sold[0]["cut_off"] == 12.0 and sold[0]["why"] == "smart")

# ---- #316 item 1: a single's break episode is filed under the held market
SEEN = []
E.break_watch = lambda tk, side, sc, now=None: SEEN.append((tk, side))
E.fresh_live_score = lambda tk, side, now=None, loose=False: ({"state": "in", "brk": True, "frac": 0.2}, "")
E.single_pre = lambda x: 0.6
E.stoploss_params = lambda tks: {"prog": 0.0, "drop": 0.0}
E.sl_confirm_params = lambda tks: None
E._sl_confirm = lambda key, ok_, why, now, cf=None: (ok_, why)
SP = "KXNBASPREAD-26NOV19LALBOS-LAL5"
E.cut_loss_single_check({"t": SP, "kind": "spread", "side": "no", "chance": 0.3}, 0.2)
ok("#316 a held spread's break episode is recorded on the spread's ticker and side, not the game winner's",
   SEEN == [(SP, "no")], SEEN)
SEEN.clear()
E.stop_loss_leg("KXNBAGAME-26NOV19LALBOS-LAL", "yes", 0.6, 0.3, {"prog": 0.0, "drop": 0.0}, now)
ok("#316 a combo leg (no watch given) is unchanged: its own ticker and side", SEEN == [("KXNBAGAME-26NOV19LALBOS-LAL", "yes")], SEEN)

# ---- #316 item 2: a full BRK_EP drops its oldest episode only
import importlib.util as _u
spec2 = _u.spec_from_file_location("E2", "wahome/engine.py"); E2 = _u.module_from_spec(spec2); spec2.loader.exec_module(E2)
E2.store_open(os.path.join(tempfile.mkdtemp(), "h2.db"))
E2.BRK_EP.clear()
for i in range(401):
    E2.BRK_EP[(f"KXNBAGAME-26NOV19AAA{i:03d}-X", "yes")] = {"start": now, "reads": [], "news": False, "would": None}
E2._brk_news = lambda t, sc: False
E2.price_watch = lambda *a, **k: None
E2._brk_book = lambda t, s, n: None
E2.break_watch("KXNBAGAME-26NOV19NEW-X", "yes", {"state": "in", "brk": True}, now)
ok("#316 at 400 open episodes a new one drops only the oldest",
   len(E2.BRK_EP) == 401 and ("KXNBAGAME-26NOV19NEW-X", "yes") in E2.BRK_EP
   and ("KXNBAGAME-26NOV19AAA000-X", "yes") not in E2.BRK_EP and ("KXNBAGAME-26NOV19AAA400-X", "yes") in E2.BRK_EP, len(E2.BRK_EP))
