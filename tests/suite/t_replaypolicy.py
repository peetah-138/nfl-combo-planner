# CHECK: group=engine
# Issue #228, PR0: the weekly tuner's replay (_replay, used by smart_tune and sim_exit) now calls exit_policy, the one
# rule live smart sell uses, instead of its own copy. The old _replay runs verbatim (fixtures/replay_old.py.txt) next
# to the new one on thousands of fuzzed paths and on recorded ones. Where the old copy differed from exit_policy the
# new replay follows exit_policy (that is what live does); every such difference is listed below (D1-D3) and in
# docs/changes/228-pr0-replay.md. `aligned` is the old code with exactly those three changes: the new replay must
# match it on every path, so the list is complete, and the old one must match on every path none of them touches.
import os, time, tempfile, importlib.util, json, random, math
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json"); E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
E.CFG["knobs_live"] = False; E.KNOB_SWITCH["on"] = None   # the weekly tuner as it runs with self-tuning off (#228 PR3)

ns = dict(vars(E))                                   # the old replay sees the engine's own helpers and constants
exec(open("fixtures/replay_old.py.txt").read(), ns)
old = ns["_replay_old"]
single_fee, kalshi_discount, SWING, ticker_sport = E.single_fee, E.kalshi_discount, E.SWING, E.ticker_sport
TRAIL_ARM, TRAIL_DROP = E.TRAIL_ARM, E.TRAIL_DROP


def aligned(c, path, fl=1.5, lm=1.0, loss=None, trail=True, cut_at=None, d1=True, d2=True, d3=True):
    """The old replay with the documented differences from exit_policy switched on one by one."""
    stake = c["stake"]
    if c["kind"] == "combo":
        P = c.get("pays") or 0
    else:
        p0 = c.get("paid") or c.get("price") or c["legs"][0].get("p") or 0.5
        P = stake / (p0 + single_fee(p0))
    if not P or len(path) < 3:
        return None
    tks = [l["ticker"] for l in c["legs"]]
    peak = 0.0
    for ts, cur in path:
        q = math.prod(cur[t] for t in tks)
        open_ = [t for t in tks if 0.02 < cur[t] < 0.98]
        if not open_:
            return None
        if c["kind"] == "combo":
            est = kalshi_discount(True) * q * P
        else:
            x = cur[tks[0]]
            est = P * max(x - single_fee(x) - 0.01, 0)
        lam = 0.35 * lm * sum(SWING.get(ticker_sport(t) or "", 1.0) for t in open_) / len(open_)
        floor = max(q * P - lam * P * math.sqrt(max(q * (1 - q), 0)), fl * stake)
        if q >= 0.5 and est >= floor:
            return round(est - stake, 2), "smart"
        # D3: a combo whose estimate is within 5% of the floor has exit_policy saying "smart" (it allows for Kalshi's
        # real offer coming in a little higher), but the sale needs the offer at the floor, so nothing else (lock in)
        # is looked at on that price: the bet rides on to the next one, as live does.
        if d3 and c["kind"] == "combo" and q >= 0.5 and est / 0.95 >= floor:
            peak = max(peak, est)
            continue
        # D2: exit_policy cuts a single at any positive value (its least to accept is 0) and a combo once the offer
        # reaches 2% of cost (>=); the old copy wanted the estimate over 2% of the stake for both.
        cut_val = (est >= 0.02 * stake if c["kind"] == "combo" else est > 0) if d2 else est > 0.02 * stake
        if loss and q <= loss and cut_val and round(ts) in (cut_at or ()):
            return round(est - stake, 2), "cut loss"
        peak = max(peak, est)
        # D1: lock in arms at 1.5x cost in exit_policy (fixed), not at the tuned profit floor x stake.
        arm = 1.5 * stake if d1 else fl * stake
        if trail and peak >= max(TRAIL_ARM * P, arm) and est <= (1 - TRAIL_DROP) * peak and est >= 1.1 * stake:
            return round(est - stake, 2), "lock in"
    return None


rng = random.Random(228)
T_ALL = ["KXNBAGAME-26NOV21BOSNYK-BOS", "KXNHLGAME-26NOV21PHIBOS-PHI", "KXNFLGAME-26NOV22KCBUF-KC",
         "KXEPLGAME-26NOV22ARSCHE-ARS", "KXNCAAMBGAME-26NOV21DUKUNC-DUK", "KXAHLGAME-26NOV191900HERCHA-HER",
         "KXNBASPREAD-26NOV21BOSNYK-BOS5", "KXNFLTOTAL-26NOV22KCBUF-47"]
FLOORS = [1.2, 1.3, 1.4, 1.5, 1.5, 1.5, 1.6, 1.7, 2.0]


def walk(n, start):
    x, out = start, []
    for _ in range(n):
        r = rng.random()
        x = rng.random() if r < 0.05 else min(max(x + rng.gauss(0, rng.choice([0.02, 0.05, 0.12])), 0.0), 1.0)
        out.append(round(x, rng.choice([2, 4, 6])))
    if rng.random() < 0.5:
        out.append(rng.choice([0.0, 1.0]))
    return out


def case():
    combo = rng.random() < 0.6
    tks = rng.sample(T_ALL, rng.randint(1, 4) if combo else 1)
    stake = rng.choice([2.0, 5.0, 10.0, rng.uniform(1, 40)])
    n = rng.choice([2, 3, 5, 10, 25, 60])
    t0 = 1_800_000_000 + rng.uniform(0, 1e5)
    walks = {t: walk(n, rng.uniform(0.3, 0.95)) for t in tks}
    m = max(len(w) for w in walks.values())
    path = []
    for k in range(m):
        path.append((t0 + 60 * k + rng.choice([0, 0.3, 0.5, 0.7]), {t: w[min(k, len(w) - 1)] for t, w in walks.items()}))
    p0 = rng.uniform(0.2, 0.9)
    c = {"id": "x", "kind": "combo" if combo else rng.choice(["single", "spread", "total"]), "stake": stake,
         "legs": [{"ticker": t, "p": rng.choice([None, p0])} for t in tks]}
    if combo:
        c["pays"] = rng.choice([0, stake * rng.uniform(1.2, 25)]) if rng.random() < 0.03 else stake * rng.uniform(1.2, 25)
    else:
        c[rng.choice(["paid", "price", "none"])] = p0
    loss = rng.choice([None, None, 0.1, 0.15, 0.2, 0.25, 0.3])
    cut_at = None
    if loss and rng.random() < 0.8:
        cut_at = {round(ts) for ts, _ in path if rng.random() < rng.choice([0.1, 0.5, 1.0])}
    kw = dict(fl=rng.choice(FLOORS), lm=rng.choice([0.5, 0.85, 1.0, 1.15, 2.0]), loss=loss, trail=rng.random() < 0.85,
              cut_at=cut_at)
    return c, path, kw


def set_discount():
    r = rng.random()
    if r < 0.5:
        E.save_json(E.DISCOUNT_FILE, {})                # the default guess, 82% in play
    else:
        E.save_json(E.DISCOUNT_FILE, {"live": [rng.uniform(0.5, 1.0) for _ in range(rng.choice([5, 9, 30]))]})


N = 12000
mism, diff_old, why_new, by_cause, untouched_same, untouched_n = [], 0, {}, {"D1": 0, "D2": 0, "D3": 0}, 0, 0
for i in range(N):
    if i % 50 == 0:
        set_discount()
    c, path, kw = case()
    a, b, al = old(c, path, **kw), E._replay(c, path, **kw), aligned(c, path, **kw)
    why_new[b[1] if b else None] = why_new.get(b[1] if b else None, 0) + 1
    if b != al:
        mism.append((i, c["kind"], kw, a, b, al))
    if a != b:
        diff_old += 1
        for d in ("D1", "D2", "D3"):                     # which single difference alone moves the old answer
            only = {"d1": d == "D1", "d2": d == "D2", "d3": d == "D3"}
            if aligned(c, path, **kw, **only) != a:
                by_cause[d] += 1
    # paths none of D1-D3 can touch: the 1.5x floor (D1), no loss cut (D2), and no combo price just under the floor (D3)
    if kw["fl"] == 1.5 and not kw["loss"] and aligned(c, path, **kw, d1=False, d2=False) == a:
        untouched_n += 1
        untouched_same += a == b
# One worked example of each difference (old answer -> new answer), shown in the log and in the notes file
T0 = 1_800_000_000
ex_path = lambda xs, tk: [(T0 + 60 * k, {t: x for t in tk}) for k, x in enumerate(xs)]
S = ["KXNBAGAME-26NOV21BOSNYK-BOS"]
C2 = ["KXNBAGAME-26NOV21BOSNYK-BOS", "KXNHLGAME-26NOV21PHIBOS-PHI"]
E.save_json(E.DISCOUNT_FILE, {})
NFL2 = ["KXNFLGAME-26NOV22KCBUF-KC", "KXNFLTOTAL-26NOV22KCBUF-47"]
examples = {
    # D1: a single that ran to 82c then fell back, tuned floor 1.7x: lock in arms at 1.5x cost (exit_policy), where
    # the old copy waited for 1.7x and rode it to a loss
    "D1": ({"kind": "single", "stake": 5.0, "paid": .5, "legs": [{"ticker": S[0]}]},
           ex_path([.5, .6, .7, .82, .62, .3, .1], S), dict(fl=1.7)),
    # D2: a single whose loss guards only held once its price was down to 2.1c: exit_policy cuts it for what is
    # left, the old copy wanted more than 2% of the stake back and rode it to zero
    "D2": ({"kind": "single", "stake": 5.0, "paid": .5, "legs": [{"ticker": S[0]}]},
           ex_path([.5, .3, .1, .05, .03, .021], S), dict(loss=0.2, cut_at={T0 + 300})),
    # D3: a 2-pick NFL combo (from the fuzz corpus) whose estimate fell to just under smart sell's floor right as it
    # had dropped 20% from its high: exit_policy says "smart" there (the offer must reach the floor), so lock in is not
    # looked at; the old copy locked in at +$39.72, the new replay rides (and this one lost)
    "D3": ({"kind": "combo", "stake": 5.0, "pays": 101.15, "legs": [{"ticker": t} for t in NFL2]},
           [(T0 + 60 * k, dict(zip(NFL2, xs))) for k, xs in enumerate(
               [(.8666, 1.0), (.8374, 1.0), (.821247, 1.0), (.67, .804678), (.6758, .7425), (1.0, 0.0)])],
           dict(fl=1.4, lm=0.5, loss=0.1)),
}
for d, ex in examples.items():
    c, path, kw = ex
    a, b = old(c, path, **kw), E._replay(c, path, **kw)
    by_cause[d] += a != b
    print(f"INFO {d} example: old replay {a} -> new replay {b}")
    ok(f"{d} example: the old copy and exit_policy really differ, and the new replay follows exit_policy",
       a != b and b == aligned(c, path, **kw))
ok(f"the new replay is exactly the old one with D1-D3 applied, on {N} fuzzed paths ({len(mism)} differ)", not mism)
if mism:
    print("first differences:", mism[:3])
ok(f"...and exactly the old one wherever none of D1-D3 applies ({untouched_same} of {untouched_n})",
   untouched_n > 1000 and untouched_same == untouched_n)
ok("...covering every replay outcome (smart, lock in, cut loss, ride)",
   all(why_new.get(k, 0) >= 50 for k in ("smart", "lock in", "cut loss", None)))
ok("...and every documented difference really occurs in the corpus", all(by_cause[d] > 0 for d in by_cause))
print(f"INFO old vs new replay on {N} fuzzed paths: {diff_old} differ; by cause {by_cause}; outcomes {why_new}")

# The checkpoint flag only renames the reason in exit_policy (its x1.3 is in the risk weight, worked out before the
# call, which the replay has never had: between-games combos are not told apart in recorded paths) and take profit
# is off in the replay as before; both are listed as remaining differences from live, unchanged here.
st = {"kind": "combo", "value": 9.0, "real": 0.0, "peak": 9.0, "pays": 10, "cost": 5.0, "q": 0.9, "live": True}
pr = {"tp": 0, "trail": True, "smart": True, "lam": 0.35, "floor": 1.5, "loss": None, "cut_ok": False}
a1, a2 = E.exit_policy(st, dict(pr, checkpoint=False)), E.exit_policy(st, dict(pr, checkpoint=True))
ok("exit_policy's checkpoint flag changes only the reason's name, not when it sells",
   a1["sell"] == a2["sell"] and a1["threshold"] == a2["threshold"] and a2["reason"] == "checkpoint")

# ---- recorded paths through the real tuner: smart_tune with the old replay and with the new one
now = time.time()
E.CFG.update(smart_sell=True, ride=2, take_profit=0, lock_trail=True)
E.save_json(E.DISCOUNT_FILE, {})


def add_item(mode, i, code, path, won, scores=None, kind="single", legs=1):
    tks = [f"KX{code.upper()}GAME-26NOV{10 + i % 9:02d}T{i:03d}{j}-AAA" for j in range(legs)]
    kick = now - 86400 * 3 - i * 600
    for t in tks:
        for k, ch in enumerate(path):
            E.store_x("insert into ticks values(?,?,?,?,?)", (kick + 60 * (k + 1), t, ch, "sim", scores[k] if scores else "active"))
    c = {"id": f"{mode}:{tks[0]}", "kind": kind, "code": code, "legs": [{"ticker": t, "p": .5, "pick": t} for t in tks],
         "stake": 5.0, "price": .5, "paid": .5, "kick": kick, "state": "paper", "result": "won" if won else "lost"}
    if kind == "combo":
        c["pays"] = 5.0 / (.5 ** legs) * 0.9
        c["pl"] = round(c["pays"] - 5, 2) if won else -5.0
    else:
        c["pl"] = round(5 / (.5 + E.single_fee(.5)) - 5, 2) if won else -5.0
    return c


NHL_SC = ["", "AAA 0–1 BBB P2 10:00", "AAA 0–2 BBB P2 2:00", "AAA 0–3 BBB P3 15:00", "AAA 0–3 BBB P3 14:00",
          "AAA 0–3 BBB P3 13:00", "AAA 0–3 BBB P3 12:00", "AAA 0–3 BBB P3 11:00", "AAA 0–4 BBB Final"]
items = [add_item("paper", i, "nba", [.52, .6, .7, .78, .6, .4, .2, 0.0], False) for i in range(40)]      # t_tune's
items += [add_item("paper", 100 + i, "nhl", [.5, .4, .25, .12, .1, .08, .07, .06, 0.0], False, NHL_SC) for i in range(40)]
rr = random.Random(7)                                   # combos that run up and fall back, some won, some lost
for i in range(45):
    up = [round(.5 + .45 * min(k, 6) / 6 * rr.uniform(.85, 1), 3) for k in range(9)]
    tail = [round(up[-1] - .1 * k * rr.uniform(.5, 1.5), 3) for k in range(1, 5)]
    won = rr.random() < 0.4
    items.append(add_item("paper", 300 + i, "nfl", up + tail + [1.0 if won else 0.0], won, kind="combo", legs=2))
E._panel_table()
E.store_x("insert or replace into panel values(?,?,?,?,?)", ("2026-11-15", "paper", now - 86400 * 3, "paper",
                                                            json.dumps({"at": now - 86400 * 3, "items": items})))


def tune(replay):
    E.save_json(E.SMART_FILE, {}); E.SMART_CACHE["at"] = 0
    keep = E._replay
    E._replay = replay
    try:
        moved = E.smart_tune(force=True)
    finally:
        E._replay = keep
    d = E.load_json(E.SMART_FILE, {})
    strip = {k: {x: v for x, v in e.items() if x not in ("at", "sl_at")} for k, e in d.items() if k != "_at"}
    return moved, strip


new_replay = E._replay
mo, do = tune(old)
mn, dn = tune(new_replay)
show = lambda d: {k: (e.get("floor"), e.get("lam"), e.get("loss"), e.get("ret")) for k, e in sorted(d.items())}
print("INFO smart_tune with the old replay:", show(do))
print("INFO smart_tune with the new replay:", show(dn))
ok("recorded paths: the tuner moves the same settings with the new replay (t_tune's NBA and NHL cases included)",
   {k: (e.get("floor"), e.get("lam"), e.get("loss")) for k, e in do.items()}
   == {k: (e.get("floor"), e.get("lam"), e.get("loss")) for k, e in dn.items()})
ok("...and t_tune's lessons still hold (NBA floor 1.4, NHL cuts under 15%)",
   dn["nba"]["floor"] == 1.4 and dn["nhl"]["loss"] == 0.15)
c0 = items[0]
p0 = E.smart_params([c0["legs"][0]["ticker"]])
ok("sim_exit reads the same rule (a recorded NBA run-up that fell back)",
   E.sim_exit(c0) == aligned(c0, E._paths(c0), p0["floor"], p0["lam"], p0["loss"]))
src = open("wahome/engine.py").read()
body = src[src.index("def _replay("):src.index("def sim_exit(")]
ok("the replay has no sell rule of its own any more: it calls exit_policy",
   "exit_policy(" in body and "TRAIL_ARM" not in body and "floor = max(" not in body and "\"lock in\"" not in body)
