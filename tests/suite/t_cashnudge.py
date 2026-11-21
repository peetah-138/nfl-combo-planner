"""Issue #210: the repeated "Combo 24: time to cash out" toast, and alert taps that open the combo.

Pete's Combo 24 is a 12-pick NFL combo: 1 pick won, 11 still to play (next one Sunday), $4.99 paid, Live showing a
"≈ $4.14" estimate, HOLD, smart sell on. The toast came from record_view's "advice" event, which fired whenever the
older Let it ride cash-out plan (plan_cashout) flipped its verdict to "sell": that plan treats the watcher's estimated
offer as a real one, and its risk-averse sums prefer a sure $4.14 to a ~1% shot at a big payout, so it says "sell" on
a long shot that smart sell (exit_policy) would never sell. Now only `cash_nudge` (smart sell's rule says sell, on a
real offer at or above cost, a game under way) can raise the toast, the moment bar, a Do now card or the phone's push.
Alerts only: nothing here changes what auto cash-out sells (checked at the end)."""
import os, re, time, importlib.util, inspect
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))

E.DISCOUNT_FILE = os.path.abspath("wahome/_no_such_discount.json")    # Kalshi's usual discount: the defaults
E.store_open(os.path.abspath("wahome/t_cashnudge.db"))
E.CFG.update(bankroll=300, smart_sell=True, take_profit=0, auto_cash=True, ride=1)
T = "KXMVENFLMULTIGAMEEXTENDED-S2026COMBO24-ABC123"
LEGS = [(f"KXNFLGAME-26NOV29T{i:02d}-T{i:02d}", f"Team {i}") for i in range(11)]


def combo24(live=False, p_leg=0.67, mc=1.0):
    """Combo 24 as Live holds it: 11 picks left at ~67% each, none under way unless live=True. Its chance `p` comes
    from mine_page's Monte Carlo (8,000 runs while live, seeded, but any price move anywhere shifts the draws): at ~1%
    that's about +/-10% noise, so mc scales it the way one refresh's draw can."""
    chances = [p_leg] * 11
    p = mc
    for c in chances:
        p *= c
    pays = 330.0
    return {"label": "Combo 24", "p": p, "pays": pays, "cost": 4.99, "left": 11, "won_some": True,
            "hold": p * pays, "legs_left": [(c, live and i == 0, 0) for i, c in enumerate(chances)],
            "need": [(("yes", tk), nm) for tk, nm in LEGS]}


def estimate(h, live=False):
    price = min(E.kalshi_discount(live) * h["p"], 0.99)
    return {"offer": round(price * h["pays"], 2), "contracts": h["pays"], "price": price, "rfq": "estimate",
            "quote": None, "frac": 1.0, "at": time.time()}


def real(amount, h):
    return {"offer": amount, "contracts": h["pays"], "price": amount / h["pays"], "rfq": "rfq-1", "quote": "q-1",
            "frac": 1.0, "at": time.time()}


def setup(h, offer):
    E.MINE["hold"] = {T: h}
    E.MINE["cash"] = {T: offer}
    E.MINE["peak"] = {}
    E.MINE["advised"] = set()
    E.MINE["locked"] = 0
    E.MINE["patterns"] = {(T,): 1, (): 80}       # it wins about 1 time in 80 (the simulation's outcomes)


# ---- 1. the root cause, reproduced: the old plan says "sell" on an estimate below cost, games days away
h = combo24()
setup(h, estimate(h))
ok("on an average refresh the old plan says hold (its line, wait_threshold, is ~15% over the estimate)",
   (E.plan_cashout() or {}).get("acts", {}).get(T) == 0.0, E.wait_threshold(T))
h = combo24(mc=1.2)                                # a refresh whose Monte Carlo draw came out 20% high
setup(h, estimate(h))
ok("Combo 24's estimate is below what was paid (like Pete's ≈ $4.14 on $4.99)", E.MINE["cash"][T]["offer"] < h["cost"],
   E.MINE["cash"][T]["offer"])
ok("the watcher's estimate counts as a 'fresh offer' for the old plan (rfq='estimate' is truthy)", bool(E.fresh_offer(T)))
plan = E.plan_cashout()
ok("root cause: on a high draw the Let it ride plan flips to SELL on that estimate (a sure $4 beats a ~1.5% shot at $330 on a $300 bankroll)", bool(plan) and plan["acts"].get(T) == 1.0,
   plan and plan["acts"])
why, floor = E.take_profit_reason(T, h)
ok("smart sell's own rule (exit_policy) says hold Combo 24", why is None, (why, floor))
ok("so cash_nudge says nothing for Combo 24", E.cash_nudge(T, h) is None)

# ---- 2. the toast itself: a verdict flip with no nudge raises nothing (this failed before the fix)
E.STORE["last"] = {}


def view(verdict, nudge=None, auto=True, self_=False):
    return {"auto_sell": auto, "combos": [{"t": T, "label": "Combo 24", "group": "pending", "p": h["p"], "pays": h["pays"],
                                            "cost": h["cost"], "offer": 4.14, "offer_real": False, "verdict": verdict,
                                            "hold_value": h["hold"], "nudge": nudge, "self": self_, "legs": [],
                                            "sports": ["nfl"]}], "singles": []}


evs = []
for vd in ["hold", "sell", "hold", "sell", "hold", "sell"]:
    k = E.STORE["last"].get(("off", T))
    if k:
        E.STORE["last"][("off", T)] = (k[0] - 200, k[1])    # as if the passes were minutes apart
    evs += [e for e in E.record_view(view(vd)) if e["kind"] == "advice"]
ok("no 'time to cash out' toast while the verdict flips hold/sell but smart sell holds", not evs, evs)

# ---- 3. what still raises it: smart sell would really sell now, on a real offer above cost, a game under way
E.MINE["peak"] = {}
hp = combo24(live=True, p_leg=0.96)               # deep into the slate, every pick likely: smart sell takes the profit
setup(hp, real(round(0.9 * hp["p"] * hp["pays"], 2), hp))
why, floor = E.take_profit_reason(T, hp)
nd = E.cash_nudge(T, hp)
ok("a real offer above cost that smart sell would take, with a game under way, is a nudge", bool(why) and bool(nd), (why, floor, nd))
ok("the nudge carries the reason and the whole-combo offer", nd and nd["why"] == why and abs(nd["offer"] - E.MINE["cash"][T]["offer"]) < 0.01, nd)

E.MINE["cash"][T] = estimate(hp, True)
ok("the same combo on an estimate only: no nudge", E.cash_nudge(T, hp) is None)
E.MINE["cash"][T] = dict(real(round(0.9 * hp["p"] * hp["pays"], 2), hp), at=time.time() - E.offer_life() - 5)
ok("a real offer that has gone stale: no nudge", E.cash_nudge(T, hp) is None)
E.MINE["cash"][T] = real(4.50, hp)
ok("a real offer below what was paid: no nudge", E.cash_nudge(T, hp) is None)
E.MINE["cash"][T] = real(round(0.9 * hp["p"] * hp["pays"], 2), hp)
hq = dict(hp, legs_left=[(c, False, s) for c, _, s in hp["legs_left"]])
E.MINE["hold"][T] = hq
ok("no game under way (the rest haven't started): no nudge", E.cash_nudge(T, hq, ("smart", floor)) is None)
E.MINE["hold"][T] = hp
ok("an explicit 'hold' answer from smart sell: no nudge", E.cash_nudge(T, hp, (None, 0.0)) is None)
ok("a real offer under 97% of the line smart sell sells at: no nudge",
   E.cash_nudge(T, hp, ("smart", E.MINE["cash"][T]["offer"] / 0.96)) is None)

# the toast: once when the nudge turns on, never again within NUDGE_GAP, and its text
E.STORE["last"] = {}
n1 = E.nudge_event(T, view("sell", nd)["combos"][0], view("sell", nd), E.STORE["last"], 1000.0)
n2 = E.nudge_event(T, view("sell", nd)["combos"][0], view("sell", nd), E.STORE["last"], 1010.0)
E.nudge_event(T, view("hold")["combos"][0], view("hold"), E.STORE["last"], 1100.0)
n3 = E.nudge_event(T, view("sell", nd)["combos"][0], view("sell", nd), E.STORE["last"], 1200.0)
n4 = E.nudge_event(T, view("sell", nd)["combos"][0], view("sell", nd), E.STORE["last"], 1300.0)
E.nudge_event(T, view("hold")["combos"][0], view("hold"), E.STORE["last"], 1400.0)
n5 = E.nudge_event(T, view("sell", nd)["combos"][0], view("sell", nd), E.STORE["last"], 1000.0 + E.NUDGE_GAP + 1)
ok("the toast goes out once when the nudge turns on", len(n1) == 1 and n1[0]["combo"] == T and n1[0]["kind"] == "advice", n1)
ok("not again while it stays on", not n2 and not n4)
ok("not again within 10 minutes even if it flickers off and on", not n3)
ok("again after 10 minutes once it turned off and on", len(n5) == 1)
ok("with Auto cash-out on, the toast says smart sell is cashing out (and the amount)",
   "smart sell is cashing out at $" in n1[0]["text"] and n1[0]["text"].startswith("Combo 24"), n1[0]["text"])
E.STORE["last"] = {}
m = E.nudge_event(T, view("sell", nd, auto=False)["combos"][0], view("sell", nd, auto=False), E.STORE["last"], 1e9)
ok("with Auto cash-out off (or 'I'll sell it'), it says time to cash out", m and "time to cash out ($" in m[0]["text"], m)

# ---- 4. the phone's push (cash_alerts) follows the same rule
setup(h, real(4.14, h))                             # Combo 24 on a real offer, still below cost
E.MINE["alerted"] = {}
fake = {"acts": {T: 1.0}, "plan": {"worth": 50.0, "sure": 4.14}, "hold": {"worth": 3.0, "nothing": 0.99}}
ok("the phone's 'Cash out' push stays quiet for Combo 24", E.cash_alerts(fake) == [])
E.MINE["peak"] = {}
setup(hp, real(round(0.9 * hp["p"] * hp["pays"], 2), hp))
E.MINE["alerted"] = {}
fake = {"acts": {T: 1.0}, "plan": {"worth": 500.0, "sure": E.MINE["cash"][T]["offer"]}, "hold": {"worth": 3.0, "nothing": 0.1}}
got = E.cash_alerts(fake)
ok("and still goes out when smart sell would sell", len(got) == 1 and "Combo 24" in got[0], got)

# ---- 5. live_view gives every combo a `nudge` field
src = inspect.getsource(E.live_view)
ok("live_view sets v['nudge'] from cash_nudge, reusing its take_profit_reason answer",
   'v["nudge"] = cash_nudge(t, h, (why, floor))' in src)
ok("record_view's toast comes only from nudge_event (no verdict-flip advice left)",
   "nudge_event(t, v, view, last, now)" in inspect.getsource(E.record_view)
   and "time to {'cash out' if sig[2]" not in inspect.getsource(E.record_view))

# ---- 6. alerts only: no selling path reads the nudge
for fn in ("auto_sell_now", "take_profit_reason", "exit_policy", "accept_cash", "plan_cashout", "smart_sell_singles",
           "place_hedge", "hedge_guard", "estimate_offers" if hasattr(E, "estimate_offers") else "auto_sell_now"):
    s = inspect.getsource(getattr(E, fn))
    ok(f"{fn} never reads cash_nudge / nudge", "cash_nudge" not in s and not re.search(r"[\"']nudge[\"']", s))
