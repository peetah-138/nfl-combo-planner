# Smart Buy stage 1 (issue #137): smart sell's decision moved into one pure function, exit_policy, which the live
# sellers (take_profit_reason for combos, single_sell_reason for singles/spreads/totals) and the simulator share.
# The refactor must not change a single live decision: the old functions (verbatim, fixtures/exit_policy_old.py.txt)
# and the new ones run side by side on thousands of states, edge cases included; answers and peak tracking must match.
import os, time, tempfile, importlib.util, json, random, copy
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json"); E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)

ns = dict(vars(E))                                   # the old functions see the engine's own state and helpers
exec(open("fixtures/exit_policy_old.py.txt").read(), ns)
old_tp, old_ss = ns["take_profit_reason_old"], ns["single_sell_reason_old"]

rng = random.Random(137)
T_COMBO = ["KXNBAGAME-26NOV21BOSNYK-BOS", "KXNHLGAME-26NOV21PHIBOS-PHI", "KXNFLGAME-26NOV22KCBUF-KC",
           "KXEPLGAME-26NOV22ARSCHE-ARS", "KXNCAAMBGAME-26NOV21DUKUNC-DUK"]
T_SINGLE = ["KXNBASPREAD-26NOV21BOSNYK-BOS5", "KXNFLTOTAL-26NOV22KCBUF-47", "KXNHLGAME-26NOV21PHIBOS-PHI",
            "KXNCAAFSPREAD-26NOV22OSUMICH-OSU7", "KXAHLGAME-26NOV191900HERCHA-HER"]
SCORES = {}                                          # some picks are mid-game (swing_lambda's sqrt of time left)
E.leg_score = lambda l: SCORES.get(l["ticker"])


def smart_table():
    d = {}
    for k in ("nba", "nhl", "nfl", "epl", "ncaamb", "ncaaf", "ahl"):
        r = rng.random()
        if r < 0.4:
            d[k] = {"n": 40, "floor": rng.choice([1.2, 1.4, 1.5, 1.7, 2.0]), "lam": rng.choice([0.5, 1.0, 1.3, 2.0]),
                    "loss": rng.choice([None, 0.15, 0.25, 0.3])}
        elif r < 0.55:
            d[k] = {"n": 5, "floor": 1.9, "lam": 2.0, "loss": 0.3}      # too few results: not used
    return d


def cfg():
    E.CFG.update(take_profit=rng.choice([0, 0, 50, 75, 90]), lock_trail=rng.random() < 0.8,
                 smart_sell=rng.random() < 0.85, ride=rng.choice([0, 1, 2, 2, 3, 4]))
    E.SMART_CACHE.update(at=time.time() + 1e6, d=smart_table())
    SCORES.clear()
    for t in T_COMBO + T_SINGLE:
        if rng.random() < 0.4:
            SCORES[t] = {"state": "in", "frac": rng.choice([0.01, 0.2, 0.5, 0.9])}


def q_val():
    return rng.choice([0.5, 0.0, 1.0, 0.4999, 0.5001, rng.random(), rng.random(), rng.uniform(0.45, 0.99)])


def combo_state():
    n = rng.randint(1, 4)
    tks = rng.sample(T_COMBO, n)
    legs = [(rng.random(), rng.random() < 0.5, 0) for _ in tks]
    cost = rng.choice([0.0, 2.0, 5.0, 10.0, rng.uniform(1, 30)])
    h = {"left": rng.choice([n, n, 0, -1]) if rng.random() < 0.1 else n, "pays": rng.choice([0, cost * rng.uniform(1, 20)]) if rng.random() < 0.05 else cost * rng.uniform(1, 20),
         "p": q_val(), "cost": cost, "legs_left": legs, "need": [(("yes", t), None) for t in tks],
         "won_some": rng.random() < 0.4, "progressed": rng.random() < 0.3}
    if rng.random() < 0.03:
        h = rng.choice([None, {}])
    return h


def cash_for(t, h):
    r = rng.random()
    if r < 0.3 or not h:
        E.MINE["cash"].pop(t, None)
        return
    pays = (h or {}).get("pays") or 1
    E.MINE["cash"][t] = {"offer": rng.uniform(0, pays), "frac": rng.choice([1.0, 0.5, 0.0]),
                         "rfq": rng.choice(["abc", "estimate", None]),
                         "at": time.time() - rng.choice([0, 10, 400, 10000])}


mism, n_combo, reasons = [], 0, {}
for i in range(4000):
    if i % 40 == 0:
        cfg()
    t = f"KXMVECOMBO-{i % 50}"
    h = combo_state()
    cash_for(t, h)
    peak0 = copy.deepcopy(E.MINE.get("peak") or {})
    if rng.random() < 0.5 and h:
        peak0[t] = rng.uniform(0, (h.get("pays") or 1) * 1.2)
    cut_ok = rng.random() < 0.5
    E.MINE["peak"] = copy.deepcopy(peak0)
    a = old_tp(t, h, cut_ok)
    pa = copy.deepcopy(E.MINE["peak"])
    E.MINE["peak"] = copy.deepcopy(peak0)
    b = E.take_profit_reason(t, h, cut_ok)
    pb = copy.deepcopy(E.MINE["peak"])
    n_combo += 1
    reasons[a[0]] = reasons.get(a[0], 0) + 1
    if a != b or type(a[1]) is not type(b[1]) or pa != pb:
        mism.append(("combo", i, a, b))
ok(f"combos: the refactored take_profit_reason answers exactly as before on {n_combo} states ({len(mism)} differ)", not mism)
ok("...and the corpus covers every combo decision (smart, checkpoint, take profit, lock in, cut loss, hold)",
   all(reasons.get(k) for k in ("smart", "checkpoint", "take profit", "lock in", "cut loss", None)))
if mism:
    print("first differences:", mism[:3])

mism, reasons = [], {}
for i in range(4000):
    if i % 40 == 0:
        cfg()
    t = rng.choice(T_SINGLE)
    n = rng.choice([0, 1, 3, 10, 25, rng.uniform(1, 50)])
    x = {"t": t, "kind": E._bet_kind(t), "sport": E.ticker_sport(t), "side": rng.choice(["yes", "no"]), "label": t, "n": n,
         "cost": rng.choice([0, n * rng.uniform(0.05, 0.95)]), "chance": rng.choice([None, q_val(), q_val()]),
         "state": rng.choice(["live", "live", "pre", "over", "won"])}
    bid = rng.choice([None, 0, 0.01, 0.5, 0.99, rng.random(), rng.random()])
    ask = (bid or 0) + rng.choice([0.01, 0.02, 0.06, 0.2])
    track, cut_ok = rng.random() < 0.8, rng.random() < 0.5
    peak0 = copy.deepcopy(E.MINE.get("peak") or {})
    if rng.random() < 0.5:
        peak0[t] = rng.uniform(0, max(n, 1) * 1.1)
    E.MINE["peak"] = copy.deepcopy(peak0)
    a = old_ss(x, bid, ask, track, cut_ok)
    pa = copy.deepcopy(E.MINE["peak"])
    E.MINE["peak"] = copy.deepcopy(peak0)
    b = E.single_sell_reason(x, bid, ask, track, cut_ok)
    pb = copy.deepcopy(E.MINE["peak"])
    reasons[a[0]] = reasons.get(a[0], 0) + 1
    if a != b or type(a[1]) is not type(b[1]) or pa != pb:
        mism.append(("single", i, a, b))
ok(f"singles: the refactored single_sell_reason answers exactly as before on 4000 states ({len(mism)} differ)", not mism)
ok("...covering smart, take profit, lock in, cut loss and hold (with the floor Live shows)",
   all(reasons.get(k) for k in ("smart", "take profit", "lock in", "cut loss", None)))
if mism:
    print("first differences:", mism[:3])

# exit_policy itself: pure (same input, same answer, no state touched) and the documented rules
st = {"kind": "single", "value": 9.0, "peak": 9.0, "pays": 10, "cost": 5.0, "q": 0.9, "live": True}
pr = {"tp": 0, "trail": True, "smart": True, "lam": 0.35, "floor": 1.5, "loss": None, "cut_ok": False}
before = json.dumps([E.MINE.get("peak"), E.CFG], sort_keys=True, default=str)
d1, d2 = E.exit_policy(dict(st), dict(pr)), E.exit_policy(dict(st), dict(pr))
ok("exit_policy is pure: the same state gives the same answer and touches no engine state",
   d1 == d2 and json.dumps([E.MINE.get("peak"), E.CFG], sort_keys=True, default=str) == before)
ok("a late cover worth 9 on a 5 stake: sell, 'smart', at the risk-adjusted floor", d1["sell"] and d1["reason"] == "smart"
   and abs(d1["threshold"] - max(9 - 0.35 * 10 * 0.3, 7.5)) < 1e-9)
d = E.exit_policy(dict(st, q=0.45, value=4.0, peak=4.0), pr)
ok("an underdog right now: holds", not d["sell"] and d["reason"] is None)
d = E.exit_policy(dict(st, q=0.2, value=1.0, peak=1.0), dict(pr, loss=0.25, cut_ok=False))
ok("a learned loss cut never fires without its guards", not d["sell"])
d = E.exit_policy(dict(st, q=0.2, value=1.0, peak=1.0), dict(pr, loss=0.25, cut_ok=True))
ok("...and fires once every guard held", d["sell"] and d["reason"] == "cut loss")
d = E.exit_policy(dict(st, q=0.6, value=7.0, peak=9.5), dict(pr, smart=False))
ok("lock in after a run-up that fell 20%+ (still a profit)", d["sell"] and d["reason"] == "lock in" and abs(d["threshold"] - 5.5) < 1e-9)
d = E.exit_policy({"kind": "combo", "value": 5.0, "real": 9.5, "peak": 5.0, "pays": 10, "cost": 5.0, "q": 0.9, "live": True},
                  dict(pr, tp=0.9, smart=False))
ok("combos: a real Kalshi offer counts (take profit at 90% of the payout)", d["sell"] and d["reason"] == "take profit")

# the Smart Buy switch changes no live sell decision
E.CFG.update(take_profit=0, lock_trail=True, smart_sell=True, ride=2)
E.SMART_CACHE.update(at=time.time() + 1e6, d={})
x = {"t": "KXNBASPREAD-26NOV21BOSNYK-BOS5", "kind": "spread", "sport": "nba", "side": "yes", "label": "x", "n": 10, "cost": 5.6,
     "chance": .9, "state": "live"}
outs = []
for on in (False, True):
    E.save_json(E.MAIN_SAVED, {"smart_buy": on, "smart_buy_v2": True})
    E.MINE["peak"] = {}
    outs.append((E.smart_buy_on(), E.single_sell_reason(x, .88, .89)))
ok("Smart Buy on or off: smart sell decides the same", outs[0][1] == outs[1][1] and outs[0][0] is False and outs[1][0] is True)
E.save_json(E.MAIN_SAVED, {})
ok("Smart Buy is on by default (stage 2), and the gate never touches selling", E.smart_buy_on() is True and E.CFG.get("smart_buy") is True)
