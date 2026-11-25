# CHECK: group=engine
# Auto cash-out for combos when buyers back out (issue #372, #334-style back-off extended to combos): the success
# lead only on a real sale; a failed round sends a plain "nothing was sold, will retry" note at most once an hour per
# combo; after a failed round it waits for the game or the price to change (Pete, 2026-11-23: "It should retry based
# on changes in the game, not some arbitrary number of minutes"), asking Kalshi nothing while it waits; a sale resets it; an unknown outcome stays blocked (rule 8) and never starts a
# back-off; each round is logged with its tries, stop reason, offer, threshold and why. No real orders: every Kalshi
# call is faked here.
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
E.combo_live_fair = lambda legs, now=None: (None, "no live chance in this test")   # Flexible sell price (default on) reads live chances: none here, so it fails closed to the old rule
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


# ---- (1) a failed round: a plain note, never the success lead; logged richly
reset()
out = tick(0)
ok("failed round: 10 accepts, nothing sold", len(accepts) == 10, len(accepts))
ok("...the push is a plain 'nothing was sold' note, no success lead",
   len(out) == 1 and "nothing was sold" in out[0] and "Took the profit" not in out[0] and "locking it in" not in out[0]
   and "backed out 10 times" in out[0] and "try again" in out[0]
   and "Still holding, and we'll keep watching" in out[0], out)    # warmer words (#384)
ok("...the fallback note carries no raw error text",
   "Tap to retry" not in E.combo_fail_note("Combo 3", {}, "weird", True, "HTTP 503 upstream. Tap to retry")
   and "503" not in E.combo_fail_note("Combo 3", {}, "weird", True, "HTTP 503 upstream. Tap to retry"))
f = [r for r in logs if r.get("result") == "failed"]
ok("...one 'failed' line with round, tries, stop, offer, threshold, slip, why", len(f) == 1 and f[0]["round"] == 1
   and f[0]["stop"] == "cancelled" and f[0]["rounds"] == 10 and len(f[0]["tries"]) == 10 and f[0]["offer"] == 13.0
   and f[0]["cut_off"] == 12.0 and f[0]["why"] == "smart" and "slip" in f[0] and f[0]["agreed"] == 13.0, f)
line = open(E.SELL_LOG).read().splitlines()[-1]
ok("...written to the decision file, and a failed round is not counted as a sale today",
   '"stop": "cancelled"' in line and '"tries": [' in line and E.sold_today() == 0)
ok("...no keys or secrets in the line", "fake-key-id" not in line and "BEGIN" not in line and "secret" not in line.lower())

# ---- (2) after a failed round: no clock, it waits for the game or the price to change
out = tick(6)
ok("nothing changed: no offer asked, no accept, no push (and no minutes-long clock)", asks == [] and accepts == []
   and out == [], (asks, accepts, out))
ok("...logged once as 'waiting for the game or the price to change'",
   sum(1 for r in logs if r.get("result") == "skipped" and "game or the price" in r.get("why", "")) == 1, logs)
out = tick(1800)
ok("...still waiting 30 min later when nothing changed, and not logged again", asks == [] and accepts == [] and logs == [])
SC["sc"] = {"state": "in", "me": 24, "opp": 17, "brk": False}
out = tick(1800 + 30, script=["cancelled"] * 10)
f = [r for r in logs if r.get("result") == "failed"]
ok("a score change: it tries again (round 2), logged with why", len(accepts) == 10 and f and f[0]["round"] == 2
   and f[0]["retry_on"] == "the game changed", f)
ok("...rate limit: no second push within the hour", out == [], out)
out = tick(1800 + 40, p=0.72)
ok("a small chance move (under 5%): still waiting", accepts == [])
out = tick(1800 + 50, p=0.76, script=["cancelled"] * 10)
ok("a real chance move (5%+): tries again", len(accepts) == 10
   and [r["retry_on"] for r in logs if r.get("result") == "failed"] == ["the combo's chance moved"])
SC["sc"] = {"state": "in", "me": 24, "opp": 17, "brk": True}
out = tick(1800 + 52, p=0.76)
ok("...but never twice inside the courtesy gap (%d s)" % E.COMBO_RETRY_GAP, accepts == [] and asks == [])
out = tick(1800 + 60, p=0.76, script=["cancelled"] * 10)
ok("a break starting (a period change) counts as a game change", len(accepts) == 10)
SC["sc"] = {"state": "post", "me": 24, "opp": 17, "brk": False}
out = tick(1800 + 70, p=0.76, script=["cancelled"] * 10)
ok("the game going final counts too", len(accepts) == 10)
ok("...the note says it waits for a change, not a time", all("minute" not in m and " min " not in m for m in out))
out = tick(1870 + 3 * 3600, p=0.76)
ok("...and hours later with nothing changed it still asks Kalshi nothing", asks == [] and accepts == [] and out == [])
SC["sc"] = None
out = tick(1870 + 3 * 3600 + 10, p=0.76)
ok("a score that drops out of the feed is not a change (no retry on a flicker)", asks == [] and accepts == [])
SC["sc"] = {"state": "post", "me": 24, "opp": 17, "brk": False}
out = tick(1870 + 3 * 3600 + 20, p=0.76, cash={"offer": 13.1, "frac": 1.0, "rfq": "r", "contracts": 20})
ok("a newer real offer that barely moved (13.0 -> 13.1): still waiting", asks == [] and accepts == [])
out = tick(1870 + 3 * 3600 + 30, p=0.76, cash={"offer": 14.0, "frac": 1.0, "rfq": "r", "contracts": 20}, script=["cancelled"] * 10)
ok("a newer real offer 5%+ away: tries again", len(accepts) == 10
   and [r["retry_on"] for r in logs if r.get("result") == "failed"] == ["the offer moved"], logs)
out = tick(1870 + 3 * 3600 + 40, p=0.775)
ok("a chance move under the 2-point floor (0.76 -> 0.775): still waiting", accepts == [])
src = open("wahome/engine.py").read()
ok("no 10/60-minute clock for combos (singles' #334 back-off untouched)", 'sell_backoff_left(t, "combo"' not in src
   and 'sell_backoff_note(t, *bkey' not in src and "SELL_FAIL_WAITS = (600, 3600)" in src)

# ---- (4) a sale resets everything, with the real success lead
SC["sc"] = {"state": "in", "me": 30, "opp": 17, "brk": False}
out = tick(4 * 3600 + 3601, script=["cancelled", "executed"])
ok("a sale after a change: the success lead, sold on the 2nd accept", len(out) == 1 and out[0].startswith("🤖 Took the profit")
   and "✅" in out[0], out)
ok("...and the wait is reset", "C1" not in E.COMBO_WAIT)
out = tick(4 * 3600 + 3700)
ok("...so the next failure is round 1 again and is told", [r["round"] for r in logs if r.get("result") == "failed"] == [1]
   and len(out) == 1 and "when the game or the price changes" in out[0], out)

# ---- (5) unknown: blocked, never retried, never a back-off
reset()
out = tick(10000, script=["cancelled", "unknown"])
ok("unknown on the 2nd accept: stops, the cash-out 'check' message", len(accepts) == 2 and len(out) == 1
   and "may or may not" in out[0] and "nothing was sold" not in out[0], out)
ok("...logged as check with stop 'unknown', no back-off started", any(r.get("result") == "check" and r.get("stop") == "unknown"
                                                                     for r in logs) and "C1" not in E.COMBO_WAIT)
out = tick(10100)
ok("...the next pass leaves it alone (rule 8): nothing asked or accepted", asks == [] and accepts == [] and out == [])

# ---- (6) Kalshi's words for a refused accept are logged
reset()
out = tick(20000, script=["failed"] * 10)
f = [r for r in logs if r.get("result") == "failed"]
ok("a refused accept: Kalshi's words kept per try", len(f) == 1 and f[0]["tries"][0]["error"] == "quote expired"
   and f[0]["stop"] == "failed", f)

# ---- (8) the retries' bar is the smart-sell line the sale was made on
reset()
offers = iter([13.0, 11.7, 11.6])
E.get_cash_offer = lambda t, f=1.0: (asks.append(t), {"offer": next(offers), "frac": 1.0, "rfq": "x", "quote": "q",
                                                       "contracts": 20, "at": E.time.time()})[1]
out = tick(30000, script=["cancelled", "cancelled", "executed"])
f = [r for r in logs if r.get("result") in ("failed", "sold")]
line = E.AUTO_CASH_SLIP * 12.0
ok("the line passed to the retries is the smart-sell line (threshold x slip)", f and abs(f[0]["line"] - round(line, 2)) < 0.006, f)
ok("...a fresh offer under it stops the round (11.6 < %.2f): nothing accepted at it" % line,
   accepts == [13.0, 11.7] and f[0]["stop"] == "offer too low" and f[0]["result"] == "failed", (accepts, f))

# ---- (9) the sale's purpose (Pete: "only sell at a loss if that's a way to try to minimize losses")
def purpose_run(why, dt_, offs=(13.0, 9.5, 9.4)):
    global offers
    reset()
    offers = iter(list(offs))
    E.take_profit_reason = lambda t, h, cut_ok=False: (why, 9.0)
    out = tick(dt_, script=["cancelled", "executed"])
    E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 12.0)
    return out, [r for r in logs if r.get("result") in ("failed", "sold")]


out, f = purpose_run("smart", 40000)
ok("profit-taking sale: a fresh offer below cost ($9.50 < $10) is not taken, even above the line",
   accepts == [13.0] and f and f[0]["stop"] == "offer too low" and f[0]["purpose"] == "take a profit"
   and f[0]["floor"] == 10.0, (accepts, f))
ok("...and the note says why in plain words", any("under the $10 you paid" in m for m in out), out)
out, f = purpose_run("lock in", 41000)
ok("...the same for lock in", accepts == [13.0] and f and f[0]["stop"] == "offer too low")
out, f = purpose_run("cut loss", 42000)
ok("a cut-loss reason with the offer still above cost is a profit sale: no fresh offer below cost",
   accepts == [13.0] and f and f[0]["purpose"] == "take a profit" and f[0]["stop"] == "offer too low", (accepts, f))
out, f = purpose_run("cut loss", 43000, offs=(9.6, 9.4))
ok("loss-cutting sale (already below cost): a fresh offer below cost, above the line, is taken",
   accepts == [9.6, 9.4] and f and f[0]["result"] == "sold" and f[0]["purpose"] == "cut a loss"
   and f[0]["offer"] == 9.4 and f[0]["agreed"] == 9.6, (accepts, f))
out, f = purpose_run("cut loss", 44000, offs=(9.6, 9.2))
ok("...but a loss cut never goes under 97% of its first offer (its line can be near 0)",
   accepts == [9.6] and f and f[0]["stop"] == "offer too low", (accepts, f))

# ---- (10) one pass stays short; no haptic or loading screen without a tap
src = open("wahome/engine.py").read()
ok("auto_sell_now stops starting sales once the pass is over AUTO_CASH_BUDGET",
   "if time.time() - began > AUTO_CASH_BUDGET:\n                break" in src)
ok("an auto round gives no haptic and no loading screen (no tap behind it)",
   'if not auto:\n                haptic("success")' in src and "if not auto:\n                loading(" in src)

# ---- (7) the source: the success lead only after a real sale
src = open("wahome/engine.py", encoding="utf-8").read()
i = src.index("def auto_sell_now(")
body = src[i:src.index("\ndef ", i + 10)]
ok("auto_sell_now builds the success lead only after the failed/check branches 'continue'",
   body.index('if result == "failed":') < body.index('"smart": "🤖 Took the profit'))
