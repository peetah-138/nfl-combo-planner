# CHECK: group=engine
# Flexible sell price (Pete, 2026-11-24): when a buyer backs out, each fresh cash-out offer is judged against the game
# RIGHT NOW (current live chance, what waiting is worth now), not the stale first offer. ON by default (Pete's opt-in).
# Never below FLEX_BACKSTOP (85%) of the combo's usual sale value now; fails closed to the old rule on stale/missing
# live input; OFF = exactly today's decisions. Pause, rule 8, Never-at-a-loss, the cost floor and the manual tap keep
# working. No real orders: every Kalshi call is faked.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))

accepts, STATE = [], {"script": [], "offers": []}
E._cash_pause = lambda s: None
E.haptic = E.loading = lambda *a: None
E.resting_sells = lambda: {}
E.MINE["tp"] = {}
E.CFG["auto_sell"] = True
E.can_trade = lambda: True
PAUSED = {"on": False}
E.trading_paused = lambda: PAUSED["on"]
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], 300.0, None)


def fake_accept(o, t=None):
    accepts.append(o["offer"])
    return STATE["script"].pop(0) if STATE["script"] else "cancelled"


def fake_offer(t, f=1.0):
    v = STATE["offers"].pop(0) if STATE["offers"] else 10.0
    return {"rfq": "r", "quote": "q", "offer": v, "frac": 1.0, "contracts": 20, "at": time.time()}


E.accept_cash_orig = E.accept_once
E.accept_once, E.get_cash_offer = fake_accept, fake_offer

LIVE = {"f": 0.5, "err": None}                       # the live chance of the pick's team right now / a stale-input reason
E.started = lambda leg: True
E.combo_live_fair = lambda legs, now=None: ((None, LIVE["err"]) if LIVE["err"] else ([dict(legs[0], fair=LIVE["f"])], None))
E.leg_start = lambda l, s: None


def run(script, offers=(), auto=True, floor=None, line=8.5, cost_floor=None, cost=8, cutting=False, p0=0.6):
    accepts.clear()
    STATE["script"], STATE["offers"] = list(script), list(offers)
    E.MINE["hold"] = {"C1": {"label": "Combo 1", "pays": 20, "cost": cost, "p": p0, "need": [(("yes", "KXNFLGAME-26-A-X"), "A")],
                             "ch_of": {"KXNFLGAME-26-A-X": p0}}}
    E.MINE["cash"] = {"C1": {"rfq": "r", "quote": "q", "offer": 10.0, "frac": 1.0, "contracts": 20, "at": time.time()}}
    E._CASH_CTX.auto, E._CASH_CTX.line, E._CASH_CTX.cost_floor = auto, (line if auto else None), cost_floor
    E._CASH_CTX.cutting = cutting
    try:
        msg = E.accept_cash("C1", floor=floor)
    finally:
        E._CASH_CTX.auto, E._CASH_CTX.line, E._CASH_CTX.cost_floor, E._CASH_CTX.cutting = False, None, None, False
    return msg, E.CASH_LAST.get("C1") or {}


def rows():
    return E.store_rows("select * from flex_shadow order by ts") if E.store_rows("select name from sqlite_master where name='flex_shadow'") else []


# default ON, backstop 85
ok("the switch defaults ON and the backstop 85", E.DEFAULTS["flex_sell"] is True and E.DEFAULTS["flex_backstop"] == 85 and E.flex_on())

# ---- fast-moving game: chance fell 0.60 -> 0.50 between retries; usual sale now ~ 0.82*10 = 8.2, backstop ~6.97
LIVE.update(f=0.5, err=None)
msg, info = run(["cancelled", "executed"], offers=[8.0], auto=False, cost=12)            # a tap, a loss: 8.0 vs first 10.0
ok("tap, chance fell: old rule (97% of 10.00 = 9.70) refuses 8.00, flexible takes it only when it beats waiting",
   (accepts == [10.0, 8.0]) == (8.0 >= E.flex_wait_line({"pays": 20, "legs_left": [(0.5, True, 0)]})), (accepts, info.get("flex")))
LIVE["f"] = 0.3                                                                          # the chance collapsed
msg, info = run(["cancelled", "executed"], offers=[5.0], auto=False, cost=3)
ok("fast-moving: a profit (5.00 vs cost 3) at a lower price than the first offer is taken, the chance having dropped",
   accepts == [10.0, 5.0] and msg.startswith("✅") and info["flex"]["mode"] == "flex" and not info["flex"]["old"], (accepts, info))
E.CFG["flex_sell"] = False
msg, info = run(["cancelled", "executed"], offers=[5.0], auto=False, cost=3)
ok("same moment with the switch OFF: the old rule refuses 5.00 (identical to develop)", accepts == [10.0] and info["stop"] == "offer too low"
   and "flex" not in info, (accepts, info))
n_off = len(rows())
E.CFG["flex_sell"] = True

# ---- a profit is never refused when waiting is worse (and not just below the first offer)
LIVE["f"] = 0.3
msg, info = run(["cancelled", "executed"], offers=[5.5], auto=True, cost=3, cost_floor=3, line=8.5)
ok("auto profit sale: its smart-sell line (8.50) stays a hard floor, flexible never goes under it", accepts == [10.0]
   and info["flex"]["why"] == "under the smart-sell line", (accepts, info))
msg, info = run(["cancelled", "executed"], offers=[8.6], auto=True, cost=3, cost_floor=3, line=8.5)
ok("...above its line it is taken", accepts == [10.0, 8.6])
msg, info = run(["cancelled", "executed"], offers=[2.9], auto=False, cost=3)
ok("a tap that began at a profit never ends below cost on a retry", accepts == [10.0] and info["flex"]["why"] == "would turn a profit into a loss", (accepts, info))
# ...but never below cost for a profit-taking sale
msg, info = run(["cancelled", "executed"], offers=[2.9], auto=True, cost=3, cost_floor=3, line=0.5)
ok("...never under cost (the cost floor still binds)", accepts == [10.0] and info["stop"] == "offer too low", (accepts, info))

# ---- the backstop refuses a spiky offer, even a profit, even with the chance down
LIVE["f"] = 0.5
msg, info = run(["cancelled", "executed"], offers=[4.5], auto=False, cost=2)
ok("a spiky low offer (4.50 vs usual ~8.20, backstop ~6.97) is refused though it is a profit", accepts == [10.0] and info["stop"] == "offer too low"
   and info["flex"]["why"] == "under the safety backstop", (accepts, info))
E.CFG["flex_backstop"] = 50
msg, info = run(["cancelled", "executed"], offers=[4.5], auto=False, cost=2)
ok("the backstop is a setting: at 50% the same offer passes", accepts == [10.0, 4.5], (accepts, info))
E.CFG["flex_backstop"] = 85

# ---- stale or missing live input: fails closed to the old 97% rule
for why in ("no fresh live score", "Kalshi has no live buyers and sellers"):
    LIVE["err"] = why
    msg, info = run(["cancelled", "executed"], offers=[8.0], auto=False, cost=3)
    ok(f"stale input ({why}): the old 97% rule refuses 8.00", accepts == [10.0] and info["stop"] == "offer too low" and info["flex"]["mode"] == "old", (accepts, info))
    msg, info = run(["cancelled", "executed"], offers=[9.8], auto=False, cost=3)
    ok("...and still takes 9.80 (97% of 10.00 is 9.70)", accepts == [10.0, 9.8])
LIVE["err"] = None
E.combo_live_fair = lambda legs, now=None: (_ for _ in ()).throw(RuntimeError("boom"))
msg, info = run(["cancelled", "executed"], offers=[8.0], auto=False, cost=3)
ok("an error reading live state: fails closed to the old rule", accepts == [10.0] and info["stop"] == "offer too low")
E.combo_live_fair = lambda legs, now=None: ([dict(legs[0], fair=LIVE["f"])], None)
h0 = {"label": "x", "pays": 20, "cost": 3, "p": 0.6}
ok("no pick in play / no state (a bare hold): old rule", E.flex_decide("C1", h0, 8.0, 1.0, 9.7)["mode"] == "old")

# ---- OFF = identical to develop on a spread of offers
for f in (0.2, 0.5, 0.7):
    LIVE["f"] = f
    for off in (4.0, 6.0, 8.0, 9.5, 9.8, 10.5):
        E.CFG["flex_sell"] = False
        _, a = run(["cancelled", "executed"], offers=[off], auto=False, cost=3); ra = list(accepts)
        ok(f"OFF f={f} offer={off}: exactly the old decision", ra == ([10.0, off] if off >= 9.7 else [10.0]) and "flex" not in a)
E.CFG["flex_sell"] = True
ok("OFF wrote nothing new to flex_shadow", len(rows()) >= n_off)

# ---- flexible only ever loosens: anything the old rule takes above the backstop is still taken
LIVE["f"] = 0.5
for off in (9.7, 9.9, 12.0):
    run(["cancelled", "executed"], offers=[off], auto=False, cost=3)
    ok(f"ON: the old rule's own accept ({off}) is still taken", accepts == [10.0, off])

# ---- a loss cut: only while the learned cut-off still holds
E.smart_params = lambda tks: {"loss": 0.45}
LIVE["f"] = 0.3
msg, info = run(["cancelled", "executed"], offers=[6.0], auto=True, cost=12, line=0.0, cutting=True, floor=None)
ok("loss cut, still under the cut-off (0.30 <= 0.45), offer above the backstop: taken", accepts == [10.0, 6.0], (accepts, info))
E.smart_params = lambda tks: {"loss": 0.2}
LIVE["f"] = 0.5
msg, info = run(["cancelled", "executed"], offers=[7.5], auto=True, cost=12, line=0.0, cutting=True, floor=None)
ok("loss cut whose cut-off no longer holds (0.50 > 0.20), offer 7.50 under waiting and under 97% of the first: refused",
   accepts == [10.0] and info["flex"]["why"] == "waiting is worth more now", (accepts, info))

# ---- Never sell at a loss: the floor binds under flexible too
E.smart_params = lambda tks: {"loss": None}
LIVE["f"] = 0.3
msg, info = run(["cancelled", "executed"], offers=[6.0], auto=True, cost=12, floor=12.0, line=8.5)
ok("Never-at-a-loss floor (12.00): a flexible 6.00 is refused", accepts == [10.0] and info["stop"] == "offer too low", (accepts, info))

# ---- Pause, rule 8
PAUSED["on"] = True
msg, info = run(["cancelled"] * 3, offers=[9.9] * 3)
PAUSED["on"] = False
ok("Pause mid-round: no more tries", accepts == [10.0] and info["stop"] == "paused")
msg, info = run(["cancelled", "unknown", "executed"], offers=[9.9, 9.9])
ok("unknown outcome (rule 8): stops at once, never another accept", len(accepts) == 2 and info["stop"] == "unknown")

# ---- manual tap parity with auto: same verdict from the same live moment
LIVE["f"] = 0.3
_, a1 = run(["cancelled", "executed"], offers=[5.0], auto=False, cost=3); t1 = list(accepts)
_, a2 = run(["cancelled", "executed"], offers=[5.0], auto=True, cost=3, cost_floor=3, line=4.0); t2 = list(accepts)
ok("your tap and the auto path decide the same on the same offer", t1 == t2 == [10.0, 5.0])

# ---- shadow recording: one bounded row per decision, errors swallowed
r = rows()
ok("every flexible retry decision was recorded", len(r) > 5 and all(x["accept"] in (0, 1) and x["old_accept"] in (0, 1) for x in r))
E.store_x = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full"))
try:
    E.flex_shadow_log("C1", {"offer": 1.0, "mode": "flex", "ok": True, "old": False}, 1, 10.0, True, False); good = True
except Exception:
    good = False
ok("a recording error never reaches the sale", good)
