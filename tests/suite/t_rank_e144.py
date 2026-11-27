# CHECK: group=engine
# rank-e-144: #287 (learned in-play green bar, paper only) and #243 (Best bets board age).
# Every Kalshi call is faked; nothing is sent.
# Combo cost floor counts Kalshi's selling fee (issues #382, #383), the way singles net it (`single_fee`): a combo
# cash-out offer exactly at cost no longer passes the floor, on the first offer or on a retry's fresh offer, and an
# unreadable offer (no contracts) is no sale. 20 contracts at $10 cost = 50 cents each: the fee is 35 cents.
# Every Kalshi call is faked.
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
E.CFG.update(flex_sell=False, auto_sell=True, auto_hedge=False, stop_loss=False, smart_sell=True, ride=2, take_profit=0,
             lock_trail=False, auto_cap=5)
h = {"label": "Combo 1", "need": [(("yes", T), "Lakers")], "pre_of": {T: 0.6}, "ch_of": {T: 0.7},
     "legs_left": [(0.7, True, 0)], "cost": 10, "p": 0.7, "pays": 20, "won_some": True, "left": 1}

E.can_trade = lambda: True
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 9.0)
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], None)
E.smart_sell_singles = lambda: []
E.haptic = E.loading = lambda *a: None
E.resting_sells = lambda: {}
E.drop_cash = lambda t: E.MINE["cash"].pop(t, None)
E._cash_pause = lambda s: None
SC = {"sc": {"state": "in", "me": 21, "opp": 17, "brk": False}}
E.leg_score = lambda l: dict(SC["sc"]) if SC["sc"] else None
asks, accepts, logs = [], [], []
OFFER = {"o": 13.0, "n": 20}
SCRIPT = {"s": []}
E.get_cash_offer = lambda t, f=1.0: (asks.append(t), {"offer": OFFER["o"], "frac": 1.0, "rfq": "x", "quote": "q",
                                                       "contracts": OFFER.get("n", 20), "at": E.time.time()})[1]


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
    E.MINE["tp_asked"] = {}; E.MINE.pop("real_asks", None); E.MINE["cash"] = {"C1": dict(cash, at=now + dt_)} if cash else {}; E.MINE["busy"] = False; E.MINE.setdefault("selling", set())
    asks.clear(); accepts.clear(); logs.clear()
    try:
        return E.auto_sell_now(plan)
    finally:
        E.time.time = _real_time


def reset():
    E.COMBO_WAIT.clear(); E.MINE["combo_fail_told"] = {}; SC["sc"] = {"state": "in", "me": 21, "opp": 17, "brk": False}
    E.save_json(E.ORDER_LEDGER, {}); E._ORDER_SHARED.unsure.clear()   # Pete cleared the order block



def run(offs, mode=None, script=("executed",), dt_=0, contracts=20, why="smart"):
    global offers
    reset()
    E.SELL_LOG = os.path.join(tempfile.mkdtemp(), "s.jsonl")   # a fresh decision log: the daily cap never interferes
    offers = iter(list(offs))
    OFFER["n"] = contracts
    E.CFG.update(stop_loss_mode=mode or "tune")
    E.take_profit_reason = lambda t, h, cut_ok=False: (why, 9.0)
    E.get_cash_offer = lambda t, f=1.0: (asks.append(t), {"offer": next(offers), "frac": 1.0, "rfq": "x", "quote": "q",
                                                          "contracts": OFFER["n"], "at": E.time.time()})[1]
    out = tick(dt_, script=list(script))
    return out, [r for r in logs if r.get("result") in ("failed", "sold", "skipped")]



# ---- #287: the learned in-play bar is paper: flat without a record, and never below the flat bar
b = E.live_single_bar("KXNBAGAME-26NOV19LALBOS-LAL")
ok("#287: no record = the flat bar (1.5 cents)", abs(b["v"] - E.SINGLE_MIN_EDGE * 0.6) < 1e-9 and b["src"] == "start")
E._live_fair_table()
for i in range(40):                                        # 40 settled games where the live model ran 10 points high
    tk = f"KXNBAGAME-26NOV19AA{i:02d}BB{i:02d}-AA{i:02d}"
    E.store_x("insert into live_fairs(ticker, ts, sport, fair, how, outcome) values(?,?,?,?,?,?)",
              (tk, now, "nba", 0.70, "live model", "yes" if i % 10 < 6 else "no"))
E.LIVE_BAR_CACHE["at"] = 0
b = E.live_single_bar("KXNBAGAME-26NOV19AA01BB01-AA01")
ok(f"#287: an over-confident live model asks a higher bar, capped ({b})", b["v"] > b["flat"] and b["v"] <= E.LIVE_BAR["max"] and b["n"] >= 30)
E.CFG["live_bar_learn"] = False
ok("#287: switch off = the flat bar", E.live_single_bar("KXNBAGAME-26NOV19AA01BB01-AA01")["v"] == b["flat"])
E.CFG["live_bar_learn"] = True
ok("#287: paper only: nothing but the quote's live_bar field reads it",
   open("wahome/engine.py", encoding="utf-8").read().count("live_single_bar(") == 2)

# ---- #243
W = open("wtest/combo_watcher.py", encoding="utf-8").read()
ok("#243: Best bets gets the board's age", "fair_at=BUILD.get(\"at\")" in W)
