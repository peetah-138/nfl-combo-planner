# CHECK: group=engine
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
E.CFG.update(auto_sell=True, auto_hedge=False, stop_loss=False, smart_sell=True, ride=2, take_profit=0,
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
    E.MINE["tp_asked"] = {}; E.MINE["cash"] = {"C1": dict(cash, at=now + dt_)} if cash else {}; E.MINE["busy"] = False; E.MINE.setdefault("selling", set())
    asks.clear(); accepts.clear(); logs.clear()
    try:
        return E.auto_sell_now(plan)
    finally:
        E.time.time = _real_time


def reset():
    E.COMBO_WAIT.clear(); E.MINE["combo_fail_told"] = {}; SC["sc"] = {"state": "in", "me": 21, "opp": 17, "brk": False}
    E.save_json(E.ORDER_LEDGER, {}); E._ORDER_SHARED.unsure.clear()   # Pete cleared the order block



fee = E.combo_sale_net({"offer": 10.0, "contracts": 20})
ok("net of the selling fee: $10.00 on 20 contracts nets $9.65", abs(fee - 9.65) < 1e-9, fee)
ok("...the same fee the singles code uses", abs((10.0 - fee) - 20 * E.single_fee(0.5, 20)) < 1e-9)
ok("...no contracts / no offer / junk: None (fail closed)", E.combo_sale_net({"offer": 10.0}) is None
   and E.combo_sale_net({"contracts": 20}) is None and E.combo_sale_net({"offer": "x", "contracts": 20}) is None)


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


# ---- (1) the first offer
out, f = run([10.0])
ok("a profit-reason sale whose offer is exactly at cost (loses the fee) is not accepted", accepts == []
   and f and f[0]["result"] == "skipped" and f[0]["why"] == "below what you paid" and f[0]["net"] == 9.65, (accepts, f))
out, f = run([10.34])
ok("...one cent short of cost + fee: still no", accepts == [] and f and f[0]["result"] == "skipped", (accepts, f))
out, f = run([10.35])
ok("...cost + the fee: sold", accepts == [10.35] and f and f[0]["result"] == "sold", (accepts, f))
out, f = run([13.0])
ok("...a normal profit sale is unchanged", accepts == [13.0] and f[0]["result"] == "sold")
out, f = run([10.35], contracts=0)
ok("...an offer with no contracts: falls back to the gross offer (sold at 10.35, never blocks), net logged = gross, note logged",
   accepts == [10.35] and f and f[0]["result"] == "sold" and f[0]["net"] == 10.35 and "no contracts" in f[0]["fee_note"], (accepts, f))
out, f = run([10.0], contracts=0)
ok("...no contracts and the gross offer exactly at cost: judged on gross (not below), so it sells",
   accepts == [10.0] and f[0]["result"] == "sold", (accepts, f))
E.CFG["combo_sell_fee"] = False
out, f = run([10.0])
ok("switch combo_sell_fee OFF: the old gross comparison (offer at cost sells), fee_note logged",
   accepts == [10.0] and f[0]["result"] == "sold" and "fee model off" in f[0]["fee_note"], (accepts, f))
E.CFG["combo_sell_fee"] = True
out, f = run([10.0], mode="never")
ok("Never sell at a loss: an offer exactly at cost is no sale either", accepts == [] and f and f[0]["result"] == "skipped", (accepts, f))
out, f = run([10.35], mode="never")
ok("...and at cost + fee it sells", accepts == [10.35] and f[0]["result"] == "sold")

# ---- (2) a retry's fresh offer
out, f = run([13.0, 10.0, 10.2], script=["cancelled", "executed"])
ok("a retry's fresh offer exactly at cost is refused on a profit sale (stop: offer too low)",
   accepts == [13.0] and f and f[0]["stop"] == "offer too low" and f[0]["floor"] == 10.0, (accepts, f))
out, f = run([13.0, 10.34], script=["cancelled", "executed"])
ok("...and one cent under cost + fee too", accepts == [13.0], accepts)
out, f = run([13.0, 10.36, 10.4], script=["cancelled", "executed"])
ok("...cost + fee or more is taken", accepts == [13.0, 10.36] and f[0]["result"] == "sold", (accepts, f))
out, f = run([13.0, 10.0], mode="never", script=["cancelled", "executed"])
ok("Never sell at a loss: the same on a retry", accepts == [13.0] and f[0]["stop"] == "offer too low", (accepts, f))

# ---- (3) a loss cut (offer already below cost) is not held by the cost floor
out, f = run([9.6, 9.5], script=["cancelled", "executed"], why="cut loss")
ok("a loss cut below cost keeps its own rules (97% of its first offer, the line), unchanged", accepts == [9.6, 9.5]
   and f[0]["result"] == "sold" and f[0]["purpose"] == "cut a loss", (accepts, f))

# ---- (3b) coherence: a better offer never refuses where a worse one sells (cut-loss reason, cost $10, 20 contracts)
out, f = run([10.20], script=["executed"], why="cut loss")
ok("a cut-loss reason, offer $10.20 (above gross cost, under cost + fee): sells, but is NOT labelled a loss cut; net logged",
   accepts == [10.2] and f and f[0]["result"] == "sold" and f[0]["purpose"] == "take a profit" and f[0]["net"] == 9.85
   and not f[0].get("stop_loss"), (accepts, f))
out, f = run([9.90], script=["executed"], why="cut loss")
ok("...$9.90 sells too", accepts == [9.9] and f[0]["result"] == "sold" and f[0]["purpose"] == "cut a loss", (accepts, f))
out, f = run([10.20], why="smart")
ok("a profit reason at $10.20 (net under cost, no stop-loss ready) does not sell", accepts == [] and f and f[0]["result"] == "skipped", (accepts, f))

# ---- (4) the source: the other two noted gaps were not touched
src = open("wahome/engine.py", encoding="utf-8").read()
ok("the stop-loss classification of a below-cost first offer is as before",
   'if below and (mode == "never" or (why != "cut loss" and not sl_ready.get(t))):' in src
   and 'if below and why != "cut loss":\n                rec["stop_loss"] = True' in src
   and "below = net < h[" in src)
ok("a manual Cash out tap has no floor (its 97% rule is unchanged)", "accept_cash(ticker)\n" in src
   and "floor is not None and net_ < floor" in src)
