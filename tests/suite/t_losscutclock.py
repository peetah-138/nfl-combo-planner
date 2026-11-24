# CHECK: group=engine
# Loss-cut clock retry (issue #396, Pete's decision): a stuck combo LOSS CUT is retried every 5 minutes (a safety valve),
# bounded by Pause, rule 8 (unknown outcome = check, never retried), 97% of the FIRST offer across rounds, the smart-sell
# line, a per-position cap (LOSSCUT_CLOCK_MAX), and fail-closed on unreadable data. Profit-reason sales never use the
# clock. Every Kalshi call is faked.
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
E.take_profit_reason = lambda t, h, cut_ok=False: ("cut loss", 9.0)
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], None)
E.smart_sell_singles = lambda: []
E.haptic = E.loading = lambda *a: None
E.resting_sells = lambda: {}
E.drop_cash = lambda t: E.MINE["cash"].pop(t, None)
E._cash_pause = lambda s: None
SC = {"sc": {"state": "in", "me": 21, "opp": 17, "brk": False}}
E.leg_score = lambda l: dict(SC["sc"]) if SC["sc"] else None
asks, accepts, logs = [], [], []
OFFER = {"o": 9.6}
SCRIPT = {"s": []}
E.get_cash_offer = lambda t, f=1.0: (asks.append(t), {"offer": OFFER["o"], "frac": 1.0, "rfq": "x", "quote": "q",
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



S = E.LOSSCUT_CLOCK_SECS
fails = lambda: [r for r in logs if r.get("result") == "failed"]


def stuck(t0=0):
    """A loss cut whose round fails: returns the clock after the failed round."""
    reset(); OFFER["o"] = 9.6; E.take_profit_reason = lambda t, h, cut_ok=False: ("cut loss", 9.0)
    E.trading_paused = lambda: False
    tick(t0, script=["cancelled"] * 10)
    return t0


# ---- (1) a stuck loss cut: nothing for 5 minutes, then a clock try, logged with why
stuck(0)
ok("round 1 fails and is parked as a loss cut", E.COMBO_WAIT["C1"]["cutting"] is True and E.COMBO_WAIT["C1"]["first"] == 9.6
   and len(accepts) == 10, E.COMBO_WAIT)
tick(S - 30)
ok("under 5 minutes, nothing changed: no ask, no accept", asks == [] and accepts == [], (asks, accepts))
out = tick(S + 5, script=["cancelled"] * 10)
f = fails()
ok("after 5 minutes it tries again, logged as clock retry 1", len(accepts) == 10 and f and f[0]["retry_on"].startswith("loss-cut clock retry 1")
   and f[0]["clock_retry"] == 1 and f[0]["round"] == 2, f)
tick(S + 20)
ok("...the clock restarts from that try (15 s later: nothing)", accepts == [] and asks == [])

# ---- (2) per-position cap: LOSSCUT_CLOCK_MAX clock tries, then only a real change reopens it
stuck(0)
n = 0
for i in range(1, E.LOSSCUT_CLOCK_MAX + 3):
    tick(i * (S + 10), script=["cancelled"] * 10)
    n += 1 if accepts else 0
ok("exactly %d clock tries per position, then no more" % E.LOSSCUT_CLOCK_MAX, n == E.LOSSCUT_CLOCK_MAX, n)
tick(50 * S)
ok("...hours later still nothing on the clock", accepts == [] and asks == [])
SC["sc"] = {"state": "in", "me": 30, "opp": 17, "brk": False}
tick(60 * S, script=["cancelled"] * 10)
ok("...a real change (a score) still reopens it", len(accepts) == 10)
SC["sc"] = {"state": "in", "me": 21, "opp": 17, "brk": False}

# ---- (3) the 97% guard is kept across rounds (against the FIRST offer, not each round's)
stuck(0)
OFFER["o"] = 9.2          # under 97% of 9.6 = 9.312
tick(S + 5, script=["cancelled"] * 10)
sk = [r for r in logs if r.get("stop") == "below 97% of the first offer"]
ok("a clock try whose offer is under 97% of the first offer sends nothing", accepts == [] and len(sk) == 1 and sk[0]["first_offer"] == 9.6, (accepts, logs))
OFFER["o"] = 9.4          # above 97% of the first (9.312), below 97% of... nothing: allowed
tick(2 * S + 10, script=["cancelled"] * 10)
ok("...an offer above that line is tried (and its own retries stay at or above 97% of the FIRST offer)", len(accepts) == 10)
OFFER["o"] = 9.6

# ---- (4) Pause is respected
stuck(0)
E.trading_paused = lambda: True
tick(S + 5, script=["cancelled"] * 10)
ok("paused: no ask, no accept on the clock", accepts == [] and asks == [], (accepts, asks))
E.trading_paused = lambda: False

# ---- (5) rule 8: an unknown outcome is never retried, clock or not
reset(); OFFER["o"] = 9.6
tick(0, script=["cancelled", "unknown"])
ok("unknown outcome: check, no wait kept", "C1" not in E.COMBO_WAIT and any(r.get("result") == "check" for r in logs))
tick(S + 5, script=["cancelled"] * 10)
ok("...the clock never retries it", accepts == [] and asks == [])
tick(5 * S, script=["cancelled"] * 10)
ok("...even much later", accepts == [] and asks == [])
# an unknown outcome in the middle of a clock round stops that round
stuck(0)
tick(S + 5, script=["cancelled", "unknown"])
ok("unknown during a clock try: stops at once (2 accepts), parks as check", len(accepts) == 2 and "C1" not in E.COMBO_WAIT)
tick(3 * S, script=["cancelled"] * 10)
ok("...and is never retried", accepts == [])

# ---- (6) profit-reason sales never use the clock
reset(); OFFER["o"] = 13.0
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 12.0)
tick(0, script=["cancelled"] * 10)
ok("a profit sale fails and is parked as a profit sale", E.COMBO_WAIT["C1"]["cutting"] is False and len(accepts) == 10)
tick(S + 5, script=["cancelled"] * 10)
tick(3 * S, script=["cancelled"] * 10)
ok("...no clock retry, ever", accepts == [] and asks == [])
# a loss-cut wait whose combo turns into a profit sale (offer back above cost) is not clock-retried either
stuck(0)
OFFER["o"] = 13.0
tick(S + 5, script=["cancelled"] * 10)
ok("a clock try that would now be a profit sale (a cut-loss reason, offer above cost) sends nothing", accepts == []
   and any(r.get("stop") == "clock retry is for loss cuts only" for r in logs), (accepts, logs))
OFFER["o"] = 9.6
stuck(0)
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 9.0)
tick(S + 5, script=["cancelled"] * 10)
ok("a loss-cut wait that comes back as a profit reason gets no clock try", accepts == [] and asks == [], (accepts, asks))
E.take_profit_reason = lambda t, h, cut_ok=False: ("cut loss", 9.0)
# the plan path (a profit cash-out) is excluded
stuck(0)
ok("the wait helper refuses the clock for a plan sale", E._clock_due(E.COMBO_WAIT["C1"], "plan") == "")

# ---- (7) fail closed on unreadable data
stuck(0)
real_acct = E.fetch_account
E.fetch_account = lambda **k: (None, "boom")
tick(S + 5, script=["cancelled"] * 10)
ok("account unreadable on a clock try: no accept, logged", accepts == [] and any("account unreadable" in r.get("why", "") for r in logs), (accepts, logs))
E.fetch_account = real_acct
stuck(0)
E.COMBO_WAIT["C1"]["clock_at"] = "garbage"
tick(S + 5, script=["cancelled"] * 10)
ok("a damaged wait record: no clock retry", accepts == [])
stuck(0)
E.COMBO_WAIT["C1"].pop("first")
tick(S + 5, script=["cancelled"] * 10)
ok("a wait with no first offer recorded: no clock retry", accepts == [])

# ---- (8) the smart-sell line still applies to the clock try's retries
stuck(0)
offers = iter([9.6, 9.5, 9.4, 9.31])
E.get_cash_offer = lambda t, f=1.0: (asks.append(t), {"offer": next(offers, 9.0), "frac": 1.0, "rfq": "x", "quote": "q",
                                                       "contracts": 20, "at": E.time.time()})[1]
tick(S + 5, script=["cancelled"] * 10)
f = fails()
ok("inside a clock try the retries stay at or above 97% of the first offer (9.312): 9.31 is refused",
   accepts == [9.6, 9.5, 9.4] and f and f[0]["stop"] == "offer too low", (accepts, f))
E.get_cash_offer = lambda t, f=1.0: (asks.append(t), {"offer": OFFER["o"], "frac": 1.0, "rfq": "x", "quote": "q",
                                                       "contracts": 20, "at": E.time.time()})[1]

# ---- (9) a change-driven retry (a real score change) is exactly as before: the first-offer guard is for clock tries only
stuck(0)
OFFER["o"] = 9.2
SC["sc"] = {"state": "in", "me": 30, "opp": 17, "brk": False}
tick(60, script=["cancelled", "executed"])
ok("a change-driven try is not held to 97% of the first offer (as before #396)", accepts == [9.2, 9.2]
   and not any(r.get("stop") == "below 97% of the first offer" for r in logs), (accepts, logs))

# ---- (10) a profit REASON never uses the clock, even when its below-cost first offer sold as a guarded stop-loss (#382)
reset(); OFFER["o"] = 9.6
real_slc = E.stop_loss_check
E.stop_loss_check = lambda t, h, also=False, key=None: (True, "")
E.CFG.update(stop_loss_mode="allow")
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 9.0)
tick(0, script=["cancelled"] * 10)
ok("a profit reason with a ready stop-loss fails its round: parked, but not as a loss cut",
   len(accepts) == 10 and E.COMBO_WAIT["C1"]["cutting"] is False, E.COMBO_WAIT)
tick(S + 5, script=["cancelled"] * 10)
tick(4 * S, script=["cancelled"] * 10)
ok("...and no clock retry later", accepts == [] and asks == [])
E.stop_loss_check = real_slc
E.CFG.update(stop_loss_mode="tune")
E.take_profit_reason = lambda t, h, cut_ok=False: ("cut loss", 9.0)

# ---- (11) a clock try that stops before sending is logged with why
stuck(0)
OFFER["o"] = 8.0         # the smart-sell line for a cut at 9.0 x 97% = 8.73
tick(S + 5, script=["cancelled"] * 10)
ok("a clock try whose fresh offer is under the smart-sell line sends nothing and says so", accepts == []
   and any("smart-sell line" in r.get("why", "") and r.get("clock_retry") == 1 for r in logs), (accepts, logs))
OFFER["o"] = 9.6

# ---- (12) a clock try never places a hedge (a hedge is a BUY: no money movement on a timer), even with auto_hedge on
stuck(0)
hedge_asked, hedged = [], []
real_hf, real_ph = E.hedge_for, E.place_hedge
E.hedge_for = lambda t: (hedge_asked.append(t), None)[1]
E.place_hedge = lambda *a, **k: (hedged.append(a), "✅ x")[1]
E.CFG.update(auto_hedge=True)
tick(S + 5, script=["cancelled"] * 10)
ok("a clock try with auto_hedge on does not even look for a hedge, and places none", hedge_asked == [] and hedged == []
   and len(accepts) == 10, (hedge_asked, hedged, accepts))
reset(); OFFER["o"] = 9.6
tick(0, script=["cancelled"] * 10)
ok("(sanity) a normal first try with auto_hedge on does look for a hedge", hedge_asked == ["C1"], hedge_asked)
E.CFG.update(auto_hedge=False); E.hedge_for, E.place_hedge = real_hf, real_ph

# ---- (13) a profit-reason round that later flips to a loss cut: the 97% floor is measured from the loss cut's own first offer
reset(); OFFER["o"] = 12.0                                   # a profit round: offer above cost, first offer $12
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 9.0)
tick(0, script=["cancelled"] * 10)
ok("a failed profit round is parked with first = its own offer, not as a loss cut", E.COMBO_WAIT["C1"]["cutting"] is False
   and E.COMBO_WAIT["C1"]["first"] == 12.0, E.COMBO_WAIT)
OFFER["o"] = 9.6; E.take_profit_reason = lambda t, h, cut_ok=False: ("cut loss", 9.0)
SC["sc"] = {"state": "in", "me": 21, "opp": 17, "brk": True}   # a real change reopens it as a loss cut
tick(100, script=["cancelled"] * 10)
w = E.COMBO_WAIT.get("C1") or {}
ok("when it becomes a loss cut, first resets to the loss cut's offer (not the old profit $12)", w.get("cutting") is True
   and w.get("first") == 9.6, w)
SC["sc"] = {"state": "in", "me": 21, "opp": 17, "brk": False}
tick(100 + S + 5, script=["cancelled"] * 10)
ok("...so its clock try is attainable at $9.60 (>= 97% of 9.60)", len(accepts) == 10, accepts)

# ---- (14) the same ticker flipping reason (plan <-> loss cut) cannot reset the cap
stuck(0)
E.COMBO_WAIT["C1"]["clock_n"] = E.LOSSCUT_CLOCK_MAX - 1
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 9.0)
tick(S + 5, script=["cancelled"] * 10)                       # a profit reason: no clock try
ok("a profit-reason tick in between does not use the clock", accepts == [], accepts)
E.take_profit_reason = lambda t, h, cut_ok=False: ("cut loss", 9.0)
tick(S + 10, script=["cancelled"] * 10)
tick(3 * S, script=["cancelled"] * 10)
tick(6 * S, script=["cancelled"] * 10)
ok("flipping the reason never gives more than the cap in clock tries", (E.COMBO_WAIT.get("C1") or {}).get("clock_n", 0) <= E.LOSSCUT_CLOCK_MAX,
   E.COMBO_WAIT)
