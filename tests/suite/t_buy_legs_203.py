# CHECK: group=engine
# The combo Buy re-checks the page's legs (issue #203, rule 7): against the stored offer AND the combo now on the card,
# fail closed (nothing sent, reason logged, words for the page). A page that sends no legs is refused too.
import os, io, contextlib, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
from wsrc import watcher_text
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
W = watcher_text()
SENT = []
E.kalshi_send = lambda *a, **k: (SENT.append(a) or {})
E.week_spend = lambda: 0.0
E.hold_refusal = lambda *a, **k: (False, "")
E.trading_paused = lambda: False
E.rfq_unsure = lambda *a, **k: False
E.CFG["budget"] = 500
OLD, NEW = ["KXA-1", "KXB-2"], ["KXA-1", "KXC-3"]


def setup(offer_legs, card_legs):
    SENT.clear()
    E.CTX["combos"] = [{"legs": [{"ticker": t} for t in card_legs]}]
    E.CTX["offers"] = {1: {"rfq": "r", "quote": "q", "stake": 5.0, "pays": 20.0, "market": "M", "price": 0.25, "legs": list(offer_legs)}}


def buy(shown):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = E.accept_offer(1, expect_legs=shown)
    return r, buf.getvalue()


setup(OLD, OLD)
r, log = buy(["KXB-2", "KXA-1"])
ok("matching legs (any order) go on to the accept", not r.get("legs_mismatch") and any("/accept" in str(a) for a in SENT))
for name, shown in (("no legs sent", []), ("a non-list", "KXA-1")):
    setup(OLD, OLD)
    r, log = buy(shown)
    ok(f"{name}, offer = card: not refused for missing legs (never worse than before)",
       not r.get("legs_mismatch") and any("/accept" in str(a) for a in SENT))
    setup(OLD, NEW)
    r, log = buy(shown)
    ok(f"{name}, card changed under the offer: refused, nothing sent, reason logged, offer kept",
       r.get("legs_mismatch") and not SENT and "combo now on that card" in log and 1 in E.CTX["offers"])
setup(OLD, OLD)
r, log = buy(NEW)
ok("page shows other legs than the offer: refused, nothing sent", r.get("legs_mismatch") and not SENT and "differ from the offer" in log)
# a flip on the Mac that did not pop the offer: the card is NEW, the offer still OLD
setup(OLD, NEW)
r, log = buy(NEW)
ok("flip without popping the offer, page shows the new legs: refused", r.get("legs_mismatch") and not SENT and "differ from the offer" in log)
setup(OLD, NEW)
r, log = buy(OLD)
ok("...and the page matching the offer but not the card names the card", "combo now on that card" in log)
ok("flip without popping the offer, stale page shows the old legs: refused", r.get("legs_mismatch") and not SENT)
setup(OLD, [])
E.CTX["combos"] = []
r, log = buy(OLD)
ok("no combo on that card at all: refused", r.get("legs_mismatch") and not SENT)
setup(OLD, OLD)
r = E.accept_offer(1)
ok("panel/killer callers (no expect_legs) are unchanged", not r.get("legs_mismatch") and any("/accept" in str(a) for a in SENT))
i = W.index('if a == "buy":'); act = W[i:i + 1600]
ok("web app Buy passes the page's legs (none = []) to accept_offer, which checks offer = card either way", "expect_legs=shown" in act and "else []" in act)
