# CHECK: group=engine
# Auto cash-out's retries after a buyer backs out (issue #372; Pete, 2026-11-23: "let it retry 7, 8, 9 or even 10
# times"): up to 10 accepts a round, each on a fresh offer that must still clear the smart-sell line the sale was made
# on (Pete: "I don't think it needs to be within 97% of the first price, but it should definitely stay above the smart
# sell line") and, under Never sell at a loss, the cost; a short random pause (0.3-1 s) before each fresh offer; one more ask when none came in; an
# unknown outcome stops at once (rule 8); your own Cash out tap keeps 3 retries and no pause. No real orders: every
# Kalshi call is faked, and the pause only counts (nothing sleeps).
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))

pauses, asks, accepts = [], [], []
E._cash_pause = lambda s: pauses.append(s)
E.haptic = E.loading = lambda *a: None
E.resting_sells = lambda: {}
E.MINE["tp"] = {}
STATE = {"script": [], "offers": []}


def fake_accept(o, t=None):
    accepts.append(o["offer"])
    st = STATE["script"].pop(0) if STATE["script"] else "cancelled"
    if st == "failed":
        E.ACCEPT_ERR[t] = "quote no longer open"
    return st


def fake_offer(t, f=1.0):
    asks.append(t)
    v = STATE["offers"].pop(0) if STATE["offers"] else 10.0
    if v is None:
        return {"error": "No cash-out offers came in."}
    return {"rfq": "r", "quote": "q", "offer": v, "frac": 1.0, "contracts": 20, "at": time.time()}


E.accept_once = fake_accept
E.get_cash_offer = fake_offer


E.CFG["auto_sell"] = True
E.can_trade = lambda: True
PAUSED = {"on": False}
E.trading_paused = lambda: PAUSED["on"]


def run(script, offers=(), auto=True, floor=None, line=8.5, cost_floor=None):
    pauses.clear(); asks.clear(); accepts.clear()
    STATE["script"], STATE["offers"] = list(script), list(offers)
    E.MINE["hold"] = {"C1": {"label": "Combo 1", "pays": 20, "cost": 8}}
    E.MINE["cash"] = {"C1": {"rfq": "r", "quote": "q", "offer": 10.0, "frac": 1.0, "contracts": 20, "at": time.time()}}
    E._CASH_CTX.auto, E._CASH_CTX.line, E._CASH_CTX.cost_floor = auto, (line if auto else None), cost_floor
    try:
        msg = E.accept_cash("C1", floor=floor)
    finally:
        E._CASH_CTX.auto, E._CASH_CTX.line, E._CASH_CTX.cost_floor = False, None, None
    return msg, E.CASH_LAST.get("C1") or {}


# ---- the numbers Pete set
ok("auto cash-out: up to 10 accepts a round; your tap keeps 4", E.AUTO_CASH_RETRIES + 1 == 10 and E.CASH_RETRIES == 3)
ok("registry: both retry counts are invariants", E.KNOB_BY["auto_cash_retries"]["cls"] == "invariant"
   and E.KNOB_BY["auto_cash_retries"]["start"] == E.AUTO_CASH_RETRIES and E.KNOB_BY["cash_retries"]["start"] == 3)

# ---- the pause: random, inside 0.3-1 s, and injectable
g = [E.cash_gap() for _ in range(2000)]
ok("the pause is always 0.3-1 s", all(0.3 <= x <= 1.0 for x in g) and max(g) - min(g) > 0.4, (min(g), max(g)))
ok("the pause uses the random source it's given", E.cash_gap(rand=lambda a, b: b) == 1.0 and E.cash_gap(rand=lambda a, b: a) == 0.3)

# ---- succeeds on try 7
msg, info = run(["cancelled"] * 6 + ["executed"])
ok("10-try path: sold on the 7th accept", msg.startswith("✅") and len(accepts) == 7 and info["stop"] == "sold"
   and info["rounds"] == 7, (msg, len(accepts)))
ok("...a pause before each of the 6 fresh offers, none before the first accept", len(pauses) == 6 and len(asks) == 6)
ok("...each try logged with its quote status", [x["quote"] for x in info["tries"]] == ["cancelled"] * 6 + ["executed"]
   and [x["try"] for x in info["tries"]] == list(range(1, 8)))

# ---- gives up after 10
msg, info = run(["cancelled", "failed"] * 6)
ok("gives up after 10 accepts, nothing sold", len(accepts) == 10 and not msg.startswith("✅") and info["rounds"] == 10
   and info["stop"] == "failed" and "10 times" in msg, (len(accepts), msg))
ok("...Kalshi's words for a refused accept are kept", info["tries"][1]["error"] == "quote no longer open"
   and info["tries"][0]["error"] == "")
ok("...no nested 'result' key (sold_today counts lines by text)", '"result"' not in E.json.dumps(info))

# ---- unknown stops at once (rule 8)
msg, info = run(["cancelled", "cancelled", "unknown", "executed"])
ok("unknown on try 3: stops at once, never a 4th accept", len(accepts) == 3 and msg.startswith("⚠️")
   and info["stop"] == "unknown")

# ---- the bar for a fresh offer: the smart-sell line (not 97% of the first price), and cost under Never
msg, info = run(["cancelled", "executed"], offers=[8.6])
ok("a fresh offer well below the first price but above the smart-sell line is taken", msg.startswith("✅")
   and accepts == [10.0, 8.6] and info["line"] == 8.5 and info["slip"] is None, (msg, accepts))
msg, info = run(["cancelled"] * 3, offers=[9.0, 8.4])
ok("a fresh offer under the smart-sell line stops the round; nothing accepted at it", accepts == [10.0, 9.0]
   and info["stop"] == "offer too low" and info["low_offer"] == 8.4, (accepts, info.get("stop")))
msg, info = run(["cancelled"] * 3, offers=[9.9, 9.9, 8.8], floor=9.0)
ok("under Never sell at a loss, a fresh offer below cost stops it (even above the line)", len(accepts) == 3
   and 8.8 not in accepts and info["stop"] == "offer too low" and info["low_offer"] == 8.8 and info["floor"] == 9.0)
msg, info = run(["cancelled"] * 3, offers=[8.9], cost_floor=9.0)
ok("a profit-taking sale (cost floor): a fresh offer above the line but below cost stops it", accepts == [10.0]
   and info["stop"] == "offer too low" and info["floor"] == 9.0)
msg, info = run(["cancelled", "executed"], offers=[9.75], cost_floor=9.9, auto=False)
ok("...it only applies to auto cash-out (your tap keeps today's rule)", accepts == [10.0, 9.75] and msg.startswith("✅"))
PAUSED["on"] = True
msg, info = run(["cancelled"] * 5, offers=[9.9] * 5)
PAUSED["on"] = False
ok("Pause mid-round: no more tries (stop 'paused', not a back-off failure)", accepts == [10.0]
   and info["stop"] == "paused" and "paused" not in E.COMBO_BACKOFF_STOPS, (accepts, info.get("stop")))
msg, info = run(["cancelled"] * 3, offers=[9.8, 9.6], line=None)
ok("auto with no line given: the old 97%-of-first-price rule (never looser)", len(accepts) == 2
   and min(accepts) >= E.CASH_SLIP * 10.0 and info["stop"] == "offer too low", accepts)
msg, info = run(["cancelled"] * 3, offers=[9.8, 9.6], auto=False)
ok("your own tap: still 97% of the price you confirmed", len(accepts) == 2 and info["stop"] == "offer too low"
   and info["slip"] == E.CASH_SLIP and info["line"] is None)

# ---- one more ask when no fresh offer came in (auto only)
msg, info = run(["cancelled", "executed"], offers=[None, 10.0])
ok("no fresh offer: asks once more, then sells", msg.startswith("✅") and len(asks) == 2 and info.get("asked_again"))
msg, info = run(["cancelled"] * 5, offers=[None, None, 10.0])
ok("...only once: two empty asks stop the round", len(asks) == 2 and len(accepts) == 1 and info["stop"] == "no fresh offer")

# ---- your own tap: unchanged (3 retries, no pause, no extra ask)
msg, info = run(["cancelled"] * 12, auto=False)
ok("your Cash out tap: still 4 accepts, no pauses", len(accepts) == 4 and not pauses and "4 times" in msg)
msg, info = run(["cancelled"] * 3, offers=[None, 10.0], auto=False)
ok("...and no extra ask", len(asks) == 1 and info["stop"] == "no fresh offer")

# ---- the round's time budget
real = E.time.time
clock = {"t": real()}
E.time.time = lambda: clock["t"]
E.get_cash_offer = lambda t, f=1.0: (clock.__setitem__("t", clock["t"] + 50), fake_offer(t, f))[1]
msg, info = run(["cancelled"] * 10)
E.time.time = real
E.get_cash_offer = fake_offer
ok("no new try after the 120 s budget", info["stop"] == "out of time" and len(accepts) == 4, (info["stop"], len(accepts)))
