# CHECK: group=engine
# Money-guard batch (issues #432, #498). Every change makes the app do LESS:
#  #432: "a profit" (flex retry, and the cash-out alert) is judged after Kalshi's selling fee, not on the gross offer.
#  #498: a combo Buy whose page sent a legs list that is EMPTY is refused (not the same as no legs sent), and the hub's
#        build-form Buy carries the card's legs and re-checks them (hard rule 7). Kalshi is faked; nothing is sent.
import os, io, time, tempfile, contextlib, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl")
from wsrc import watcher_text
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
W = watcher_text()

# ---- #432: flex_decide's "a profit" is net of the selling fee
E.CFG["flex_backstop"] = 0
E.CFG["flex_sell"] = True
E.started = lambda leg: True
E.combo_live_fair = lambda legs, now=None: ([dict(legs[0], fair=0.3)], None)
E.leg_start = lambda l, s: None
E.smart_params = lambda tks: {"loss": 0.45}
E.flex_wait_line = lambda hn: 1e9                 # waiting is never "worth more" here: only the profit rule can accept
h = {"label": "Combo 1", "pays": 20, "cost": 7.0, "p": 0.6, "need": [(("yes", "KXNFLGAME-26-A-X"), "A")],
     "ch_of": {"KXNFLGAME-26-A-X": 0.6}}
E.MINE["hold"] = {"C1": h}
gross = 7.05
net = E.combo_sale_net({"offer": gross, "contracts": 20})
ok("setup: gross is over cost, net after the fee is under cost but over 95% of cost", net < 7.0 <= gross and net >= 0.95 * 7, net)
fx = E.flex_decide("C1", h, gross, 1.0, 9.0, cost_floor=7.0, net=net)
ok("#432: gross over cost but net under it is NOT 'a profit' (the chance dropped branch refuses)", fx["ok"] is False, fx)
good = 7.6
fx = E.flex_decide("C1", h, good, 1.0, 9.0, cost_floor=7.0, net=E.combo_sale_net({"offer": good, "contracts": 20}))
ok("#432: net over cost with the chance dropped is still taken", fx["ok"] is True and "profit" in fx["why"], fx)
fx = E.flex_decide("C1", h, gross, 1.0, 9.0)
ok("#432: with no net passed it falls back to the offer (a manual tap is unchanged)", fx["ok"] is True, fx)

# ---- #432: the cash-out alert says 'at least what was paid' after the fee
T = "KXMVE-C1"
hc = dict(h, left=1, legs_left=[(0.7, True, 0)])
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 5.0)
E.fresh_offer = lambda t: True
for off, want in ((gross, None), (7.6, True)):
    E.MINE["cash"][T] = {"offer": off, "frac": 1.0, "contracts": 20, "rfq": "r", "at": time.time()}
    r = E.cash_nudge(T, hc)
    ok(f"#432: cash_nudge at offer {off}: {'quiet (net under cost)' if want is None else 'speaks'}", (r is None) == (want is None), r)

# ---- #498: a sent-but-empty legs list is refused
SENT = []
E.kalshi_send = lambda *a, **k: (SENT.append(a) or {})
E.week_spend = lambda: 0.0
E.hold_refusal = lambda *a, **k: (False, "")
E.trading_paused = lambda: False
E.rfq_unsure = lambda *a, **k: False
E.CFG["budget"] = 500
LEGS = ["KXA-1", "KXB-2"]


def setup():
    SENT.clear()
    E.CTX["combos"] = [{"legs": [{"ticker": t} for t in LEGS]}]
    E.CTX["offers"] = {1: {"rfq": "r", "quote": "q", "stake": 5.0, "pays": 20.0, "market": "M", "price": 0.25, "legs": list(LEGS)}}


def buy(**kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = E.accept_offer(1, **kw)
    return r, buf.getvalue()


setup()
r, log = buy(expect_legs=[], legs_sent_empty=True)
ok("#498: legs sent but empty: refused, nothing sent, offer kept, reason logged",
   r.get("legs_mismatch") and not SENT and 1 in E.CTX["offers"] and "empty legs list" in log, (r, log))
setup()
r, log = buy(expect_legs=[])
ok("#498: no legs sent at all is unchanged (held to offer = card, goes on)", not r.get("legs_mismatch") and any("/accept" in str(a) for a in SENT))
setup()
r, log = buy(expect_legs=LEGS, legs_sent_empty=False)
ok("#498: matching legs unchanged", not r.get("legs_mismatch") and any("/accept" in str(a) for a in SENT))
i = W.index('if a == "buy":'); act = W[i:i + 1800]
ok("#498: the web app's Buy flags a sent-but-empty list", "sent_empty" in act and "legs_sent_empty=sent_empty" in act)

# ---- #498: the hub build-form Buy, really called (WebBuild.buy on the watcher's class, faked Kalshi, nothing sent)
import sys, threading
sys.argv = ["combo_watcher.py"]
wspec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py"); WM = importlib.util.module_from_spec(wspec); wspec.loader.exec_module(WM)
E.set_league = lambda lg: None
E.money = lambda x: f"${x:.2f}"


class FakeOdds:
    lock = threading.RLock()
    engine = staticmethod(lambda: E)


def hub_buy(legs):
    SENT.clear()
    wb = WM.WebBuild(FakeOdds())
    off = {"rfq": "r", "quote": "q", "stake": 5.0, "pays": 20.0, "market": "M", "price": 0.25, "legs": list(LEGS), "got": time.time()}
    wb.cur = {"lg": "nfl", "combos": [{"legs": [{"ticker": t} for t in LEGS]}], "stake": 5.0, "offers": {1: off}}
    with contextlib.redirect_stdout(io.StringIO()):
        msg = wb.buy(1, legs)
    return msg, bool(any("/accept" in str(a) for a in SENT))


msg, sent = hub_buy(list(LEGS))
ok("#498: hub buy with matching legs is accepted (the accept went out; the fake Kalshi gives no confirmation)", sent and "different combo" not in msg and "out of date" not in msg, msg)
msg, sent = hub_buy(None)
ok("#498: hub buy with no legs is refused, nothing sent", not sent and "Nothing was bought" in msg, msg)
msg, sent = hub_buy([])
ok("#498: hub buy with an empty legs list is refused, nothing sent", not sent and "Nothing was bought" in msg, msg)
msg, sent = hub_buy(["KXA-1", "KXZ-9"])
ok("#498: hub buy with mismatched legs is refused, nothing sent", not sent and "Bought" not in msg and "different combo" in msg, msg)
ok("#498: the hub form carries the card's legs and the route passes them",
   "name='legs'" in W and 'builder.buy(' in W and 'form.get("legs")' in W)

# ---- #432 follow-up: a NaN or unreadable net fails closed (no "a profit" yes), a missing net is still the manual-tap fallback
for bad in (float("nan"), "junk"):
    fx = E.flex_decide("C1", h, 7.6, 1.0, 9.0, net=bad)
    ok(f"#432: net={bad!r} refuses the profit-retry yes", fx["ok"] is False, fx)
fx = E.flex_decide("C1", h, 7.6, 1.0, 9.0, net=7.5)
ok("#432: a readable net over cost is still taken", fx["ok"] is True, fx)
