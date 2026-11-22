# CHECK: group=engine
# Issue #228, PR3: smart sell's exit numbers go LIVE behind Settings › Money › 'Let smart sell tune its own numbers'
# (knobs_live, on by default). Checks: with the switch OFF every exit decision (take_profit_reason, single_sell_reason,
# smart_params, exit_settings, _replay) is byte-identical to the code before this PR (verbatim copy,
# fixtures/exit_knobs_old.py.txt) on thousands of random states, whatever self-tuning has recorded; with it ON and
# nothing learned, identical too (and with only leagues' own learned values); exit_policy with the start values passed
# in = without them; a learned value changes only its own league; a borrowed one only stricter (#259); the brake
# (Pete's #266 rule: a loss = holding would have paid more) puts the league back at its starts, holds 14 days and
# pushes once; the live stepper moves one exit knob a group a run, only at the bar, on the older 70% with the newest
# 30% agreeing, judged only on games after its last step (#264), writes self-tuning's own record and never smart_tune's
# file or a setting, and smart_tune stops moving the floor / risk weight / loss cut while the switch is on (#267);
# the loss guards and Smart Buy's dial stay shadow; the Pi never runs it; the view shows each change.
import os, time, tempfile, importlib.util, json, random, copy
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SB_DIAL_FILE = os.path.join(E.HERE, "sb.json"); E.SB_GATE["dial"] = None
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json"); E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.KNOBS_FILE = os.path.join(E.HERE, "knobs.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()

ns = dict(vars(E))                                   # the old functions: they call each other, never the new code
exec(open("fixtures/exit_knobs_old.py.txt").read(), ns)
O = {n: ns[n] for n in ("exit_policy", "take_profit_reason", "single_sell_reason", "smart_params", "exit_settings", "_replay")}


def switch(on):
    E.CFG["knobs_live"] = on
    E.save_json(E.MAIN_SAVED, {"knobs_live": on})
    E.KNOB_SWITCH["on"] = None
    E.KNOB_STATE_CACHE["d"] = None


def set_knobs(st):
    json.dump(st, open(E.KNOBS_FILE, "w"))
    E.KNOB_STATE_CACHE["d"] = None


ok("on by default (Pete's standing opt-in), a shared setting", E.DEFAULTS["knobs_live"] is True
   and "knobs_live" in E.SHARED_KEYS and (os.path.exists(E.MAIN_SAVED) or E.knob_switch_on() is True))
E.save_json(E.MAIN_SAVED, {"knobs_live": False}); E.KNOB_SWITCH["on"] = None
ok("the shared settings file wins (the web app's switch reaches the Mac's engines)", E.knob_switch_on() is False)
switch(True)
ok("...and turns it back on", E.knob_switch_on() is True)

rng = random.Random(228)
T_COMBO = ["KXNBAGAME-26NOV21BOSNYK-BOS", "KXNHLGAME-26NOV21PHIBOS-PHI", "KXNFLGAME-26NOV22KCBUF-KC",
           "KXEPLGAME-26NOV22ARSCHE-ARS", "KXNCAAMBGAME-26NOV21DUKUNC-DUK", "KXLALIGAGAME-26NOV22RMABAR-RMA"]
T_SINGLE = ["KXNBASPREAD-26NOV21BOSNYK-BOS5", "KXNFLTOTAL-26NOV22KCBUF-47", "KXNHLGAME-26NOV21PHIBOS-PHI",
            "KXEPLGAME-26NOV22ARSCHE-ARS", "KXAHLGAME-26NOV191900HERCHA-HER", "KXLALIGAGAME-26NOV22RMABAR-RMA"]
SCORES = {}
E.leg_score = lambda l: SCORES.get(l["ticker"])
LEAGUES = ("nba", "nhl", "nfl", "epl", "laliga", "soccer", "ncaamb", "ahl", "mix", "all")


def smart_table(own_only=False):
    """smart_tune's file: own, borrowed (looser and stricter than the start) and too-thin entries."""
    d = {}
    for k in LEAGUES:
        if own_only and k in ("soccer", "all"):
            continue
        r = rng.random()
        if r < 0.45:
            d[k] = {"n": 40, "floor": rng.choice([1.2, 1.4, 1.5, 1.7, 2.0]), "lam": rng.choice([0.5, 0.85, 1.0, 1.3, 2.0]),
                    "loss": rng.choice([None, 0.15, 0.25, 0.3]), "at": now - rng.choice([0, 86400 * 30])}
        elif r < 0.6:
            d[k] = {"n": 5, "floor": 1.9, "lam": 2.0, "loss": 0.3}
    return d


def knobs_table():
    """Self-tuning's own record: learned exit numbers for random groups (used only while the switch is on)."""
    g = {}
    for k in LEAGUES:
        if rng.random() < 0.5:
            lv = {n: rng.choice([E.KNOB_BY[n]["min"], E.KNOB_BY[n]["max"]]) for n in rng.sample(E.KNOB_LIVE, 4)
                  if E.KNOB_BY[n]["min"] is not None}
            g[k] = {"lv": lv, "lat": {n: now for n in lv}}
    return {"groups": g, "brake": {}, "settings": {}}


def cfg(own_only=False, nothing=False):
    E.CFG.update(take_profit=rng.choice([0, 0, 50, 75, 90]), lock_trail=rng.random() < 0.8,
                 smart_sell=rng.random() < 0.85, ride=rng.choice([0, 1, 2, 2, 3, 4]))
    E.SMART_CACHE.update(at=time.time() + 1e6, d={} if nothing else smart_table(own_only))
    SCORES.clear()
    for t in T_COMBO + T_SINGLE:
        if rng.random() < 0.4:
            SCORES[t] = {"state": "in", "frac": rng.choice([0.01, 0.2, 0.5, 0.9])}


def q_val():
    return rng.choice([0.5, 0.0, 1.0, 0.4999, 0.5001, rng.random(), rng.random(), rng.uniform(0.45, 0.99)])


def combo_state():
    n = rng.randint(1, 3)
    tks = rng.sample(T_COMBO, n) if rng.random() < 0.6 else [rng.choice(T_COMBO)] * 1
    legs = [(rng.random(), rng.random() < 0.5, 0) for _ in tks]
    cost = rng.choice([2.0, 5.0, 10.0, rng.uniform(1, 30)])
    return {"left": len(tks), "pays": cost * rng.uniform(1, 20), "p": q_val(), "cost": cost, "legs_left": legs,
            "need": [(("yes", t), None) for t in tks], "won_some": rng.random() < 0.4, "progressed": rng.random() < 0.3}


def cash_for(t, h):
    if rng.random() < 0.3:
        E.MINE["cash"].pop(t, None)
        return
    E.MINE["cash"][t] = {"offer": rng.uniform(0, h["pays"]), "frac": rng.choice([1.0, 0.5]),
                         "rfq": rng.choice(["abc", "estimate", None]), "at": time.time() - rng.choice([0, 10, 400])}


def single_x():
    t = rng.choice(T_SINGLE)
    n = rng.choice([1, 3, 10, 25, rng.uniform(1, 50)])
    return {"t": t, "kind": E._bet_kind(t), "sport": E.ticker_sport(t), "side": rng.choice(["yes", "no"]), "label": t,
            "n": n, "cost": n * rng.uniform(0.05, 0.95), "chance": q_val(), "state": rng.choice(["live", "live", "pre"])}


def compare(n_states, mode, cut_rate=0.5):
    """Old vs new on n_states combos and n_states singles (and smart_params / exit_settings per bet). Returns the
    differences and how many decisions sold, by reason."""
    diffs, reasons = [], {}
    for i in range(n_states):
        if i % 40 == 0:
            cfg(own_only=(mode == "own"), nothing=(mode == "nothing"))
            if mode == "off-learned":
                set_knobs(knobs_table())
        t = f"KXMVECOMBO-{i % 50}"
        h = combo_state()
        cash_for(t, h)
        peak0 = copy.deepcopy(E.MINE.get("peak") or {})
        if rng.random() < 0.5:
            peak0[t] = rng.uniform(0, h["pays"] * 1.2)
        cut_ok = rng.random() < cut_rate
        E.MINE["peak"] = copy.deepcopy(peak0)
        a = O["take_profit_reason"](t, h, cut_ok)
        pa = copy.deepcopy(E.MINE["peak"])
        E.MINE["peak"] = copy.deepcopy(peak0)
        b = E.take_profit_reason(t, h, cut_ok)
        pb = copy.deepcopy(E.MINE["peak"])
        reasons[a[0]] = reasons.get(a[0], 0) + 1
        tks = [tk for (_, tk), _ in h["need"]]
        if a != b or type(a[1]) is not type(b[1]) or pa != pb:
            diffs.append(("combo", i, a, b))
        if O["smart_params"](tks) != E.smart_params(tks) or O["exit_settings"](tks) != E.exit_settings(tks):
            diffs.append(("params", i, tks, O["smart_params"](tks), E.smart_params(tks)))
        x = single_x()
        bid = rng.choice([0.01, 0.5, 0.99, rng.random(), rng.random()])
        peak0 = copy.deepcopy(E.MINE.get("peak") or {})
        E.MINE["peak"] = copy.deepcopy(peak0)
        a = O["single_sell_reason"](x, bid, bid + 0.02, True, cut_ok)
        E.MINE["peak"] = copy.deepcopy(peak0)
        b = E.single_sell_reason(x, bid, bid + 0.02, True, cut_ok)
        reasons[a[0]] = reasons.get(a[0], 0) + 1
        if a != b or type(a[1]) is not type(b[1]):
            diffs.append(("single", i, a, b))
    return diffs, reasons


# ---- 1. switch OFF: byte-identical to the code before this PR, whatever self-tuning has recorded
switch(False)
d1, r1 = compare(2500, "off-learned")
ok(f"switch off: every exit decision is exactly as before on 5000 states, with self-tuning's own record full of "
   f"learned values and smart_tune's file borrowing both ways ({len(d1)} differ)", not d1)
ok("...covering smart, checkpoint, take profit, lock in, cut loss and hold",
   all(r1.get(k) for k in ("smart", "checkpoint", "take profit", "lock in", "cut loss", None)))
if d1:
    print("first differences:", d1[:3])

# ---- 2. switch ON, nothing learned: identical; only leagues' own learned values: identical too
switch(True)
set_knobs({"groups": {}, "brake": {}, "settings": {}})
d2, r2 = compare(2000, "nothing")
ok(f"switch on, nothing learned anywhere: identical on 4000 states ({len(d2)} differ)", not d2 and r2.get("smart"))
d3, _ = compare(2000, "own")
ok(f"switch on, only leagues' own learned values (smart_tune's, nothing borrowed): identical ({len(d3)} differ)", not d3)
if d2 or d3:
    print("first differences:", (d2 or d3)[:3])

# ---- 3. exit_policy: the start values passed in = nothing passed in
STATES = [{"kind": rng.choice(("combo", "single")), "value": rng.uniform(0, 30), "real": rng.choice((0.0, rng.uniform(0, 30))),
           "peak": rng.uniform(0, 40), "pays": 30.0, "cost": rng.uniform(3, 12), "q": rng.random(), "live": rng.random() < .6}
          for _ in range(3000)]
START = {pk: E.KNOB_BY[n]["start"] for n, pk in E.KNOB_EXIT_PRM.items()}
bad = 0
for s_ in STATES:
    prm = {"tp": rng.choice((0, 0.5, 0.9)), "trail": rng.random() < .8, "smart": rng.random() < .9, "lam": rng.uniform(0.1, 1),
           "floor": rng.choice((1.2, 1.5, 2.0)), "loss": rng.choice((None, 0.2)), "cut_ok": rng.random() < .5,
           "checkpoint": rng.random() < .2}
    a, b, c = O["exit_policy"](s_, prm), E.exit_policy(s_, prm), E.exit_policy(s_, dict(prm, **START))
    bad += not (a == b == c)
ok("exit_policy with the registry's start values passed in decides exactly as the old one with none (3000 states)", bad == 0)
ok("exit_policy's parameters are the knobs' starts (the constants)", START == {
    "q_min": E.EXIT_Q_MIN, "est_smart": E.EXIT_EST_SMART, "est_tp": E.EXIT_EST_TP, "tp_min": E.TP_MIN_GAIN,
    "trail_arm": E.TRAIL_ARM, "trail_arm_cost": E.TRAIL_ARM_COST, "trail_drop": E.TRAIL_DROP,
    "trail_floor": E.TRAIL_FLOOR, "cut_accept": E.CUT_ACCEPT})
st0 = {"kind": "single", "value": 6.0, "peak": 9.0, "pays": 10, "cost": 5.0, "q": 0.45, "live": True}
pr0 = {"tp": 0, "trail": True, "smart": False}
ok("each one really moves the decision: lock in sells after a 33% fall; with a 35% fall needed it holds",
   E.exit_policy(st0, pr0)["reason"] == "lock in" and not E.exit_policy(st0, dict(pr0, trail_drop=0.35))["sell"])
st1 = {"kind": "single", "value": 9.0, "peak": 9.0, "pays": 10, "cost": 5.0, "q": 0.55, "live": True}
pr1 = {"tp": 0, "trail": False, "smart": True, "lam": 0.35, "floor": 1.5}
ok("...and the least chance: 55% sells at the start (50%), holds at 60%",
   E.exit_policy(st1, pr1)["sell"] and not E.exit_policy(st1, dict(pr1, q_min=0.6))["sell"])
ok("_replay passes them through, and gives the old answer without them",
   E._replay.__defaults__[-2:] == (0, None))
c_ = {"id": "x", "kind": "single", "stake": 5.0, "price": 0.5, "kick": now - 86400, "pl": -5.0,
      "legs": [{"ticker": "KXNBAGAME-26NOV19LALBOS-LAL", "p": 0.5}]}
path = [(now - 86400 + i * 60, {"KXNBAGAME-26NOV19LALBOS-LAL": x}) for i, x in enumerate((0.5, 0.6, 0.75, 0.92, 0.94, 0.7, 0.3, 0.1))]
ok("_replay: old == new (no knobs) == new with the starts", O["_replay"](c_, path) == E._replay(c_, path)
   == E._replay(c_, path, ex=START) and E._replay(c_, path, fl=1.7, ex={"q_min": 0.95}) != E._replay(c_, path, fl=1.7))

# ---- 4. a learned value changes only its own league; borrowed only stricter; the brake gives the start
E.SMART_CACHE.update(at=time.time() + 1e6, d={})
set_knobs({"groups": {"nba": {"lv": {"trail_drop": 0.35, "exit_q_min": 0.6, "smart_floor": 1.3},
                              "lat": {"trail_drop": now, "exit_q_min": now, "smart_floor": now}},
                      "soccer": {"lv": {"exit_q_min": 0.4, "trail_floor": 1.3, "smart_lam": 1.3, "smart_loss": 0.2},
                                 "lat": {}}},
           "brake": {}, "settings": {}})
NBA, NHL, EPL = "KXNBASPREAD-26NOV21BOSNYK-BOS5", "KXNHLGAME-26NOV21PHIBOS-PHI", "KXEPLGAME-26NOV22ARSCHE-ARS"
ok("NBA's learned numbers reach its bets (its own, even looser than the start)",
   E.knob_exit_prm([NBA]) == {"trail_drop": 0.35, "q_min": 0.6} and E.smart_params([NBA])["floor"] == 1.3)
ok("...and no other league's", E.knob_exit_prm([NHL]) == {} and E.smart_params([NHL]) == O["smart_params"]([NHL]))
ok("a soccer league borrows soccer's only stricter (#259): the least chance 40% is looser (start 50%), the lock-in "
   "floor 1.3x stricter, the risk weight 1.3 looser (start 1.0), the loss cut never",
   E.knob_exit_prm([EPL]) == {"trail_floor": 1.3} and E.smart_params([EPL])["lam"] == 1.0
   and E.smart_params([EPL])["loss"] is None)
ok("a Mix combo of NBA and NHL takes neither league's numbers", E.knob_exit_prm([NBA, NHL]) == {})
diff_nba = diff_nhl = 0
E.CFG.update(take_profit=0, lock_trail=True, smart_sell=True, ride=2)
for i in range(600):
    for t, cnt in ((NBA, "nba"), (NHL, "nhl")):
        x = dict(single_x(), t=t, kind=E._bet_kind(t), sport=E.ticker_sport(t))
        bid = rng.random()
        pk = rng.uniform(0, x["n"])
        E.MINE["peak"] = {t: pk}
        a = O["single_sell_reason"](x, bid, bid + .02, True, True)
        E.MINE["peak"] = {t: pk}
        b = E.single_sell_reason(x, bid, bid + .02, True, True)
        if a != b:
            if cnt == "nba":
                diff_nba += 1
            else:
                diff_nhl += 1
ok(f"on random states NBA's decisions change ({diff_nba}) and NHL's never ({diff_nhl})", diff_nba > 0 and diff_nhl == 0)
S0 = E.knob_state()
S0["brake"]["nba"] = {"at": now - 60, "until": now + 14 * 86400, "why": "x"}
set_knobs(S0)
ok("a braked league is back at its starting numbers", E.knob_exit_prm([NBA]) == {}
   and E.smart_params([NBA]) == dict(E.SMART_DEFAULT, key=None))
S0["brake"]["nba"]["until"] = now - 1
set_knobs(S0)
ok("...until the brake ends", E.knob_exit_prm([NBA]) != {})

# ---- 5. smart_tune's file and self-tuning's record: one mover per value (#267)
E.SMART_CACHE.update(at=time.time() + 1e6, d={"nba": {"n": 40, "floor": 1.7, "lam": 1.0, "loss": None, "at": now - 100}})
set_knobs({"groups": {"nba": {"lv": {"smart_floor": 1.6}, "lat": {"smart_floor": now - 50}}}, "brake": {}, "settings": {}})
ok("self-tuning's step is newer than smart_tune's: it wins", E.smart_params([NBA])["floor"] == 1.6)
E.SMART_CACHE["d"]["nba"]["at"] = now
ok("smart_tune moved it later (while the switch was off): smart_tune's wins", E.smart_params([NBA])["floor"] == 1.7)
items = [{"id": i, "kind": "single", "stake": 5.0, "kick": now - 86400 * (40 - i), "pl": -5.0,
          "legs": [{"ticker": NBA}]} for i in range(40)]
real = (E._tune_items, E._paths, E._sl_paths, E._replay)
E._tune_items = lambda days=60: [dict(c) for c in items]
E._paths = lambda c: [(0, {}), (1, {}), (2, {})]
E._sl_paths = lambda c: []
E._replay = lambda c, path, fl=1.5, lm=1.0, loss=None, cut_at=None, **k: (5.0, "smart") if fl > 1.55 else None
json.dump({"nba": {"n": 40, "floor": 1.5, "lam": 1.0, "loss": None}}, open(E.SMART_FILE, "w"))
switch(True)
E.smart_tune(force=True)
on_after = json.load(open(E.SMART_FILE))["nba"]
switch(False)
E.smart_tune(force=True)
off_after = json.load(open(E.SMART_FILE))["nba"]
E._tune_items, E._paths, E._sl_paths, E._replay = real
ok("switch on: smart_tune no longer moves the floor / risk weight / loss cut (it still counts)",
   on_after["floor"] == 1.5 and on_after["n"] == 40 and "at" not in on_after)
ok("switch off: smart_tune moves them as before", off_after["floor"] == 1.6)

# ---- 6. the live stepper: one exit knob a group a run, only at the bar, own record, never a setting
switch(True)
os.remove(E.KNOBS_FILE)
json.dump({"nba": {"n": 45, "floor": 1.7, "lam": 1.0, "loss": None}, "_at": now}, open(E.SMART_FILE, "w"))
E.SMART_CACHE["at"] = 0
bets = [({"id": i, "stake": 5.0, "kick": now - 50 * 86400 + i * 86400 * 0.75, "pl": -5.0, "kind": "single",
          "legs": [{"ticker": "KXNBAGAME-X%d-LAL" % i}]}, [], []) for i in range(60)]
ROWS = {"replay": {"nba": bets, "all": bets, "nhl": bets[:12]}, "sl": {"nba": bets[:55]}, "sb": {}}
E._knob_rows = lambda now, deadline=None: ROWS
JUDGE = {"mode": "good"}


def judge(jd, rows, cur_, name, to, cache=None, **kw):
    base = [(c.get("kick"), 0.0, 5.0) for c, _, _ in rows]
    m = JUDGE["mode"]
    if name == "smart_floor" and to == 1.8 and m == "good":           # a clear gain, old and new bets alike
        return [(k, (0.9 if i % 4 == 0 else 0.0), s) for i, (k, _, s) in enumerate(base)]
    if name == "trail_drop" and to > cur_[name] and m == "good":       # smaller, also clears the bar
        return [(k, (0.6 if i % 4 == 0 else 0.0), s) for i, (k, _, s) in enumerate(base)]
    if name == "sl_prog" and to > cur_[name] and m == "good":          # a shadow knob clears the bar too
        return [(k, (0.9 if i % 4 == 0 else 0.0), s) for i, (k, _, s) in enumerate(base)]
    if name == "exit_q_min" and m in ("good", "oldonly"):            # big gains only in the older 70%: vetoed
        return [(k, (2.0 if i % 3 == 0 and i < 40 else 0.0), s) for i, (k, _, s) in enumerate(base)]
    if name == "smart_floor" and m == "thin":                         # under 2% of what was staked
        return [(k, (0.2 if i % 4 == 0 else 0.0), s) for i, (k, _, s) in enumerate(base)]
    return base


E.knob_judge = judge
smart_bytes = open(E.SMART_FILE, "rb").read()
cfg_before = json.dumps(E.CFG, sort_keys=True, default=str)
said = E.knob_tune(now, force=True)
S = E.knob_state()
nba = S["groups"]["nba"]
st_ = {r["knob"]: r["status"] for r in nba["last"]}
ok("one live step for the league, the biggest gain: the profit floor 1.7 → 1.8 (from smart_tune's own value)",
   st_.get("smart_floor") == "stepped" and nba["lv"]["smart_floor"] == 1.8 and nba.get("lstep_at") == now
   and sum(1 for r in nba["last"] if r["status"] == "stepped") == 1)
ok("the other exit step that clears the bar waits its turn", st_.get("trail_drop") == "qualifies" and "trail_drop" not in nba["lv"])
ok("the newest 30% veto a step chosen on the older bets (#264)", st_.get("exit_q_min") == "vetoed" and "exit_q_min" not in nba["lv"])
ok("the loss guards stay a test: 'would step', in the shadow record only", st_.get("sl_prog") == "would step"
   and "sl_prog" not in nba["lv"] and nba["v"]["sl_prog"] > 0.5 and E.stoploss_params([NBA]) == E.stoploss_params([NBA]))
ok("smart sell uses the new floor in NBA now, and nowhere else", E.smart_params(["KXNBAGAME-X1-LAL"])["floor"] == 1.8
   and E.smart_params([NHL])["floor"] == 1.5)
ok("smart_tune's file, the settings and CFG are untouched", open(E.SMART_FILE, "rb").read() == smart_bytes
   and json.dumps(E.CFG, sort_keys=True, default=str) == cfg_before)
ok("it says what changed, in plain words", any(s.startswith("changed NBA: Profit floor") for s in said)
   and any("not active yet" in s for s in said))
rows = E.store_rows("select league, knob, from_v, to_v, status, why from knob_shadow where status='stepped'")
ok("every change is logged: what, league, from, to, why", any(r["league"] == "nba" and r["knob"] == "smart_floor"
   and json.loads(r["from_v"]) == 1.7 and json.loads(r["to_v"]) == 1.8 and "Profit floor" in r["why"] for r in rows))
v = E.knob_shadow_view(now)
L = [x for x in v["leagues"] if x["key"] == "nba"][0]
ok("the card's view: live mode, the change with when and why, where it stands now",
   v["mode"] == "live" and L["changes"] and L["changes"][0]["label"] == "Profit floor"
   and L["changes"][0]["to"] == "1.8× what you paid" and L["changes"][0]["at"] == int(now)
   and any(m["knob"] == "smart_floor" and m["live"] for m in L["moved"]) and "Profit floor" in v["live"])
nhl = S["groups"].get("nhl") or {}
ok("a thin league (12 bets) learns nothing of its own; it borrows everyone's step only because it is stricter "
   "(lock in waits for a 25% fall, not 20%)", not (nhl.get("lv") or {}) and E.knob_exit_prm([NHL]) == {"trail_drop": 0.25}
   and (S["groups"]["all"].get("lv") or {}).get("trail_drop") == 0.25)
said2 = E.knob_tune(now + 8 * 86400, force=True)
n2 = E.knob_state()["groups"]["nba"]
ok("the next run judges only games after the last step (#264): none yet, so nothing moves",
   n2["lv"]["smart_floor"] == 1.8 and not any(r["status"] == "stepped" for r in n2["last"]))
later = [({"id": 100 + i, "stake": 5.0, "kick": now + 60 + i * 3600, "pl": -5.0, "kind": "single",
           "legs": [{"ticker": "KXNBAGAME-Y%d-LAL" % i}]}, [], []) for i in range(40)]
ROWS["replay"]["nba"] = bets + later
JUDGE["mode"] = "thin"
E.knob_tune(now + 16 * 86400, force=True)
n3 = E.knob_state()["groups"]["nba"]
ok("with 40 new games but a gain under 2% of what was staked: no step (the bar, not the calendar)",
   n3["lv"]["smart_floor"] == 1.8 and not any(r["status"] == "stepped" for r in n3["last"]))
E.ROLE_BACKUP = True
ok("the Pi never runs it", E.knob_tune(now + 30 * 86400, force=True) == [] and E.knob_brake_pass(now, force=True) == [])
E.ROLE_BACKUP = False
switch(False)
JUDGE["mode"] = "good"
ROWS["replay"]["nba"] = bets
os.remove(E.KNOBS_FILE)
E.knob_tune(now, force=True)
S = E.knob_state()
ok("switch off: the same evidence only proposes ('would step'), nothing live", not (S["groups"]["nba"].get("lv") or {})
   and any(r["status"] == "would step" for r in S["groups"]["nba"]["last"]) and E.knob_shadow_view(now)["mode"] == "shadow")
switch(True)

# ---- 7. the brake: a loss = holding would have paid more (#266); back to the start for 14 days; one push
os.remove(E.KNOBS_FILE)
E.knob_tune(now, force=True)                              # NBA's floor 1.8 again (live)
E._ledger_table()
E.store_x("delete from sell_log")
E._combo_league_of = lambda t: "nba" if "NBA" in t else "nhl"


def sale(ts, t, offer, cost, held, by="mac"):
    E.store_x("insert into sell_log(ts, ticker, result, kind, offer, cost, pays, frac, by, outcome, held) "
              "values(?,?,?,?,?,?,?,?,?,?,?)", (ts, t, "sold", "combo", offer, cost, 20.0, 1.0, by,
                                              None if held is None else ("won" if held else "lost"), held))


for i in range(4):                                        # four loss cuts that saved money: sold under cost, holding paid 0
    sale(now - 5000 + i, "KXMVENBA-CUT%d" % i, 1.0, 5.0, 0.0)
ok("sales under cost that beat holding (loss cuts doing their job) never brake", E.knob_brake_pass(now, force=True) == []
   and "nba" not in E.knob_state()["brake"])
E.store_x("delete from sell_log where ticker like '%CUT%'")
for i in range(4):                                        # four profit sales that left money on the table
    sale(now - 4000 + i, "KXMVENBA-EARLY%d" % i, 8.0, 5.0, 20.0 if i < 3 else None)
ok("a sale still waiting for its result counts neither way (3 losses + 1 open: no brake)",
   E.knob_brake_pass(now, force=True) == [])
sale(now - 3000, "KXMVENBA-EARLY9", 8.0, 5.0, 20.0)
msgs = E.knob_brake_pass(now, force=True)
S = E.knob_state()
b = S["brake"].get("nba") or {}
ok("4 sales in a row that got less than holding (even at a profit): brake, one push, plain words, no urgent words",
   len(msgs) == 1 and "NBA" in msgs[0] and "less than holding" in msgs[0] and "starting numbers" in msgs[0]
   and not any(w in msgs[0].lower() for w in ("auto", "hedge", "cash out", "paused", "can't", "at risk")))
ok("live: NBA is back at its starting numbers for 14 days, its own learned floor put back",
   abs(b.get("until", 0) - (now + 14 * 86400)) < 2 and b.get("mode") == "live" and b.get("reset", {}).get("smart_floor") == 1.8
   and E.smart_params(["KXNBAGAME-X1-LAL"]) == dict(E.SMART_DEFAULT, key=None) and E.knob_exit_prm(["KXNBAGAME-X1-LAL"]) == {})
ok("the brake is logged and shown", any(r["status"] == "braked" for r in E.store_rows("select status from knob_shadow"))
   and [x for x in E.knob_shadow_view(now)["leagues"] if x["key"] == "nba"][0]["brake"])
ok("while braked: no second push, the stepper skips the league", E.knob_brake_pass(now + 60, force=True) == []
   and (E.knob_tune(now + 60, force=True) or True) and E.knob_state()["groups"]["nba"]["last"][0]["status"] == "braked")
S = E.knob_state()
S["brake"]["nba"]["until"] = now - 1
set_knobs(S)
ok("after 14 days the league stays on its starting numbers (its own record was put back), old sales never re-brake",
   E.smart_params(["KXNBAGAME-X1-LAL"])["floor"] == 1.5 and E.knob_brake_pass(now + 120, force=True) == [])
ok("the month rule on the new measure: 5% of the stake worse than holding",
   E.knob_brake_check([(1, 1.0, 5), (2, -3.0, 5), (3, 0.5, 5), (4, -0.5, 5)]) is not None
   and E.knob_brake_check([(1, 1.0, 5), (2, -1.0, 5), (3, 0.5, 5), (4, -0.5, 5)]) is None)

# ---- 8. what never moves
ok("only tunable exit knobs are live; no invariant, evidence knob, setting or guard",
   all(E.KNOB_BY[n]["cls"] == "tunable" for n in E.KNOB_LIVE)
   and not set(E.KNOB_LIVE) & {"sl_prog", "sl_drop", "sl_under", "sl_checks", "sl_span", "sl_gap", "break_guard",
                               "below_cost", "hedge_lock_share", "hedge_lock_extra", "hedge_lock_cost", "hedge_gap",
                               "cash_slip", "live_spread", "sb_dial", "sb_ev_min"})
ok("knob_exit_prm only ever gives exit_policy's own numbers", set(E.KNOB_EXIT_PRM.values()) <= set(START))
set_knobs({"groups": {"all": {"lv": {"exit_q_min": "junk"}}, "nhl": {"lv": {"smart_floor": "junk", "trail_drop": 9.0}}},
           "brake": {}, "settings": {}})
try:
    r = E.knob_exit_prm([NHL])
    sp = E.smart_params([NHL])
    E.MINE["peak"] = {}
    E.single_sell_reason(dict(single_x(), t=NHL), 0.6, 0.62)
    ok("a damaged or out-of-range value is ignored (the start), never stops selling",
       r == {} and sp["floor"] == 1.5)
except Exception as err:
    ok("a damaged record must not raise: " + repr(err), False)
open(E.KNOBS_FILE, "w").write("{not json"); E.KNOB_STATE_CACHE["d"] = None
ok("an unreadable record = the starting numbers", E.knob_exit_prm([NBA]) == {} and E.smart_params([NHL])["floor"] == 1.5)
json.dumps(E.knob_shadow_view(now))
ok("the view is plain JSON", True)
