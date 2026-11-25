# CHECK: group=engine
# Pete, 2026-11-25 (profit review of release 507): under Flexible sell price an AUTOMATIC retry of a sale that began as
# profit-taking may not be accepted under 95% of cost (net of the combo selling fee), however far fair value slides.
# A genuine loss cut is not held to cost: it goes only through the loss guards (cut-off still holds, backstop, fresh
# live read). Manual taps, Pause, rule 8 and the stale-input fallback are unchanged. No real orders: Kalshi is faked.
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
E.CFG["flex_backstop"] = 50          # the backstop is not what is under test here
E.can_trade = lambda: True
E.trading_paused = lambda: False
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], 300.0, None)
E.accept_once = lambda o, t=None: (accepts.append(o["offer"]), STATE["script"].pop(0) if STATE["script"] else "cancelled")[1]
E.get_cash_offer = lambda t, f=1.0: {"rfq": "r", "quote": "q", "offer": STATE["offers"].pop(0) if STATE["offers"] else 10.0,
                                     "frac": 1.0, "contracts": 20, "at": time.time()}
LIVE = {"f": 0.3, "err": None}
E.started = lambda leg: True
E.combo_live_fair = lambda legs, now=None: ((None, LIVE["err"]) if LIVE["err"] else ([dict(legs[0], fair=LIVE["f"])], None))
E.leg_start = lambda l, s: None
E.smart_params = lambda tks: {"loss": 0.45}


def net(offer):
    return E.combo_sale_net({"offer": offer, "contracts": 20})


def run(offers, cost, cutting=False, auto=True, line=0.5):
    accepts.clear()
    STATE["script"], STATE["offers"] = ["cancelled", "executed"], list(offers)
    E.MINE["hold"] = {"C1": {"label": "Combo 1", "pays": 20, "cost": cost, "p": 0.6, "need": [(("yes", "KXNFLGAME-26-A-X"), "A")],
                             "ch_of": {"KXNFLGAME-26-A-X": 0.6}}}
    E.MINE["cash"] = {"C1": {"rfq": "r", "quote": "q", "offer": 10.0, "frac": 1.0, "contracts": 20, "at": time.time()}}
    E._CASH_CTX.auto, E._CASH_CTX.line = auto, (line if auto else None)
    E._CASH_CTX.cost_floor = None if (cutting or not auto) else cost       # as auto_sell_now sets it
    E._CASH_CTX.cutting = cutting
    try:
        msg = E.accept_cash("C1")
    finally:
        E._CASH_CTX.auto, E._CASH_CTX.line, E._CASH_CTX.cost_floor, E._CASH_CTX.cutting = False, None, None, False
    return msg, E.CASH_LAST.get("C1") or {}


# cost 7.00: 95% of cost is 6.65 NET of the selling fee. Fair now 0.30 x 20 = 6.00 (the buyer backed out of 10.00).
floor = 0.95 * 7
low, high = 6.7, 7.4                      # gross offers: low nets under 6.65, high nets over it
ok("test setup: the low offer nets under 95% of cost, the high one over", net(low) < floor <= net(high), (net(low), net(high), floor))
LIVE["f"] = 0.45                          # fair 9.00: both offers are over the (lowered) backstop
msg, info = run([low], cost=7)
ok("profit sale, buyer backs out, fair slid well below cost: a retry netting under 95% of cost is refused",
   accepts == [10.0] and info["stop"] == "offer too low" and info["flex"]["why"] == "under 95% of cost", (accepts, info))
LIVE["f"] = 0.3
msg, info = run([low], cost=7)
ok("...also at a much lower fair (6.00), even though it beats waiting there", accepts == [10.0] and info["flex"]["why"] == "under 95% of cost", (accepts, info))
msg, info = run([high], cost=7)
ok("a retry netting at least 95% of cost is accepted (still the flexible rule)", accepts == [10.0, high] and info["flex"]["mode"] == "flex", (accepts, info))
msg, info = run([net(high) and 7.0], cost=7)
ok("...and a plain profit-sized offer is of course accepted", accepts == [10.0, 7.0])

# the floor is on the NET: a fee the gross offer hides
ok("the floor uses the offer after the selling fee, not the gross offer", low >= floor and net(low) < floor)

# a manual tap is not an automatic retry: unchanged
msg, info = run([low], cost=7, auto=False)
ok("manual tap: unchanged (no 95% cost floor; the flexible rule alone)", "flex" in info and info["flex"]["why"] != "under 95% of cost", (accepts, info))

# stale live info: the old rules (the full cost floor) already bind and are stricter
LIVE["err"] = "no fresh live score"
msg, info = run([low], cost=7)
ok("stale live info: old rule and the full cost floor still refuse", accepts == [10.0] and info["flex"]["mode"] == "old", (accepts, info))
LIVE["err"] = None

# a genuine loss cut is not held to cost, only to the loss guards
LIVE["f"] = 0.3
msg, info = run([5.2], cost=12, cutting=True, line=0.0)
ok("loss cut (cost 12): taken at 5.20 while the learned cut-off holds (0.30 <= 0.45), no cost floor",
   accepts == [10.0, 5.2] and info["flex"]["why"] != "under 95% of cost", (accepts, info))
LIVE["f"] = 0.5
msg, info = run([6.0], cost=12, cutting=True, line=0.0)
ok("loss cut whose cut-off no longer holds (0.50 > 0.45): refused by the loss guards, not by the cost floor",
   accepts == [10.0] and info["flex"]["why"] == "waiting is worth more now", (accepts, info))
E.CFG["flex_backstop"] = 85
msg, info = run([4.0], cost=12, cutting=True, line=0.0)
ok("loss cut: the backstop still binds", accepts == [10.0] and info["flex"]["why"] == "under the safety backstop", (accepts, info))

# unreadable cost or net fails closed
ok("unreadable net with a cost floor refuses", E.flex_decide("C1", E.MINE["hold"]["C1"], 7.4, 1.0, 0.5, cost_floor=7, net=None)["ok"] is False)
ok("no cost floor passed (a tap or a cut): the argument changes nothing", E.flex_decide("C1", E.MINE["hold"]["C1"], 7.4, 1.0, 0.5)["why"] != "under 95% of cost")
