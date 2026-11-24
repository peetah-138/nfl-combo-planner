# CHECK: group=engine
# Issue #228, PR2: the knob stepper, its holdout and the brake, in SHADOW ONLY. Checks: Pete's bar (10+ bets in the
# band, 2% of stake, 2 SE, 20 new results, the newest 30% must agree) fires only when every part holds; candidates stay
# inside the registry's bounds (mult steps, the loss cut's on/off); borrowed values only stricter; one step a league a
# run, the biggest gain, ties to the smallest change; invariants, evidence knobs and settings never stepped; tied and
# shared knobs blocked; #258's one-of and risk-product bounds; a thin or short history does nothing; Pete's caps kept
# apart from any system raise (#260); the brake (4 losses in a row, 5% of the month's stake) records "would brake",
# resets only the shadow values and pushes once per league per 14 days; errors never raise; the time budget holds;
# and with the shadow on, every live decision (smart_params, stoploss_params, exit_settings / exit_policy, sb_dial,
# hedge_guard, auto_cap, the live tuners' files) is byte-identical to before.
import os, time, tempfile, importlib.util, json, random, copy
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SB_DIAL_FILE = os.path.join(E.HERE, "sb.json"); E.SB_GATE["dial"] = None
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json")
E.KNOBS_FILE = os.path.join(E.HERE, "knobs.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
E.CFG["knobs_live"] = False; E.KNOB_SWITCH["on"] = None   # PR2's shadow world: self-tuning off (t_knoblive.py has it on)
now = time.time()
EV = E.KNOB_EVIDENCE

# ---- 1. Pete's bar: fires only when every part holds
def ds_of(gains, n=60, kick0=now - 40 * 86400):
    """n bets a day apart; `gains` = {index: dollars} (the band), everything else 0."""
    return [(kick0 + i * 86400 / 2, gains.get(i, 0.0), 5.0) for i in range(n)]
good = {i: (0.9 if i % 3 else 0.6) for i in range(0, 60, 4)}              # 15 bets, spread over old and new
ev = E.knob_evidence(ds_of(good), 300.0, 0)
ok("a clear, broad gain clears the bar (judged on the older 70%: 11 of its 15 bets)", ev["ok"] and ev["band"] == 11
   and ev["share"] >= 0.02 and ev["t"] >= 2 and ev["hold_n"] == 4)
ev = E.knob_evidence(ds_of({i: 0.9 for i in range(0, 36, 4)}), 300.0, 0)  # 9 bets in the band
ok("9 bets in the band: below the bar (needs 10)", not ev["ok"] and not ev["checks"]["band"])
ev = E.knob_evidence(ds_of({i: 0.3 for i in range(0, 60, 4)}), 300.0, 0)   # 15 x 0.3 = 4.5 = 1.5% of 300
ok("a gain under 2% of what was staked: below the bar", not ev["ok"] and not ev["checks"]["gain"] and ev["checks"]["band"])
noisy = {i: (3.0 if i % 8 == 0 else -2.2) for i in range(0, 60, 4)}
ev = E.knob_evidence(ds_of(noisy), 100.0, 0)
ok("a gain within luck (under 2 SE): below the bar", not ev["ok"] and not ev["checks"]["se"] and ev["checks"]["gain"])
ev = E.knob_evidence(ds_of(good), 300.0, now - 5 * 86400)                 # last step 5 days ago: ~10 new results
ok("fewer than 20 new results since the last step: below the bar", not ev["ok"] and not ev["checks"]["new"])
_ds = ds_of(good)
ok("exactly 19 new results: below; exactly 20: the bar's new part holds",
   E.knob_evidence(_ds, 300.0, _ds[-20][0])["new"] == 19 and not E.knob_evidence(_ds, 300.0, _ds[-20][0])["checks"]["new"]
   and E.knob_evidence(_ds, 300.0, _ds[-21][0])["new"] == 20 and E.knob_evidence(_ds, 300.0, _ds[-21][0])["checks"]["new"])
ok("the holdout needs at least 3 bets it changes", E.knob_evidence(ds_of({**{i: 0.9 for i in range(0, 42, 3)}, 50: 1.0, 55: 1.0}), 300.0, 0)["checks"]["holdout"] is False
   and E.knob_evidence(ds_of({**{i: 0.9 for i in range(0, 42, 3)}, 50: 1.0, 55: 1.0, 58: 1.0}), 300.0, 0)["checks"]["holdout"])
ok("a one-step change counts as one step either way (ties are real ties)",
   E._knob_dist("smart_lam", 1.0, 0.85) == E._knob_dist("smart_lam", 1.0, 1.15) == 1.0
   and E._knob_dist("smart_floor", 1.7, 1.6) == E._knob_dist("smart_floor", 1.7, 1.8) == 1.0)
old_only = {i: 0.9 for i in range(0, 42, 3)}                              # 14 gains, all in the oldest 70%
ev = E.knob_evidence(ds_of(old_only), 300.0, 0)
ok("the holdout vetoes a step none of the newest 30% would change",
   not ev["ok"] and ev["checks"]["band"] and ev["checks"]["gain"] and ev["checks"]["se"] and not ev["checks"]["holdout"])
dis = dict(old_only); dis.update({50: -1.5, 55: -1.4, 58: -1.0})
ev = E.knob_evidence(ds_of(dis), 300.0, 0)
ok("...and one the newest 30% disagree with", not ev["ok"] and ev["hold_n"] == 3 and ev["hold"] < 0 and not ev["checks"]["holdout"])
say = E.knob_step_say("smart_floor", 1.5, 1.6, E.knob_evidence(ds_of(dis), 300.0, 0), 60)
ok("a vetoed step says so in plain words", "newest 30% disagree" in say and "1.5× what you paid → 1.6× what you paid" in say)
ok("nothing at all: below the bar, no error", not E.knob_evidence([], 0, 0)["ok"])

# ---- 2. candidates: bounds, mult steps, on/off, whole numbers
ok("one step either way", E.knob_candidates("smart_floor", 1.5) == [1.4, 1.6])
ok("never past the bounds (floor 1.2-2.0)", E.knob_candidates("smart_floor", 2.0) == [1.9]
   and E.knob_candidates("smart_floor", 1.2) == [1.3])
ok("the risk weight steps x0.85 / x1.15, inside 0.5-2.0", E.knob_candidates("smart_lam", 1.0) == [0.85, 1.15]
   and E.knob_candidates("smart_lam", 2.0) == [1.7] and E.knob_candidates("smart_lam", 0.5) == [0.575])
ok("the loss cut: off switches on at 0.15; at its lowest the next step down is off",
   E.knob_candidates("smart_loss", None) == [0.15] and E.knob_candidates("smart_loss", 0.1) == [0.15, None]
   and E.knob_candidates("smart_loss", 0.3) == [0.25])
ok("Smart Buy's dial steps whole levels inside 0-8", E.knob_candidates("sb_dial", 0) == [1]
   and E.knob_candidates("sb_dial", 8) == [7] and all(isinstance(x, int) for x in E.knob_candidates("sb_dial", 3)))
ok("rules and invariants have no steps", E.knob_candidates("below_cost", True) == [] and E.knob_candidates("pause", True) == [])
for k in E.KNOBS:
    if k["cls"] == "tunable" and k["unit"] not in ("rule", "table") and k["start"] is not None:
        for x in E.knob_candidates(k["name"], k["start"]):
            if x is not None and not (k["min"] - 1e-9 <= x <= (k["max"] if k["max"] is not None else x)):
                ok("candidate outside bounds: %s %r" % (k["name"], x), False)

# ---- 3. borrowed only stricter; the resolver's chain and the brake
ok("a borrowed floor is never under the start (1.5)", E.knob_stricter("smart_floor", 1.3) == 1.5 and E.knob_stricter("smart_floor", 1.8) == 1.8)
ok("a borrowed risk weight is never over the start (1.0: higher sells sooner)", E.knob_stricter("smart_lam", 1.3) == 1.0
   and E.knob_stricter("smart_lam", 0.85) == 0.85)
ok("the loss cut is never borrowed", E.knob_stricter("smart_loss", 0.25) is None)
ok("the loss guards borrow only stricter", E.knob_stricter("sl_prog", 0.4) == 0.5 and E.knob_stricter("sl_drop", 0.3) == 0.3)
st = {"groups": {"nba": {"lv": {"smart_floor": 1.3}}, "soccer": {"lv": {"smart_floor": 1.3, "smart_lam": 1.3, "smart_loss": 0.2}},
                 "all": {"v": {"sb_dial": 2}}}, "brake": {}, "settings": {}}   # exit knobs: the live record (PR3)
ok("own value used as is (even looser than the start)", E.knob("smart_floor", "nba", st, now) == 1.3)
ok("a soccer league borrows soccer's, only stricter", E.knob("smart_floor", "epl", st, now) == 1.5
   and E.knob("smart_lam", "epl", st, now) == 1.0 and E.knob("smart_loss", "epl", st, now) is None)
ok("nothing recorded: the start", E.knob("smart_floor", "nhl", st, now) == 1.5 and E.knob("exit_q_min", "nhl", st, now) == 0.5)
ok("borrowed from everyone, never under the start", E.knob("sb_dial", "nhl", st, now) == 2)
st["brake"]["nba"] = {"at": now - 60, "until": now + 86400, "mode": "live"}
ok("a braked league is back at its start", E.knob("smart_floor", "nba", st, now) == 1.5)
ok("an invariant is its live value", E.knob("cap_read_age", "nba", st, now) == E.CAP_READ_AGE)

# ---- 4. Pete's caps apart from the system's raise (#260)
E.CFG["hedge_cap"] = 100
st2 = {"groups": {}, "brake": {}, "settings": {"hedge_cap": {"pete": 100, "system": 140}, "auto_cap": {"system": 9}}}
ok("a system raise counts, up to the $150 ceiling", E.knob_cap("hedge_cap", st=st2, now=now) == 140
   and E.knob_cap("hedge_cap", st={**st2, "settings": {"hedge_cap": {"system": 400}}}, now=now) == 150)
ok("Pete's own value above the ceiling is never clamped", E.knob_cap("hedge_cap", pete=500, st=st2, now=now) == 500)
ok("a brake anywhere gives Pete's own value back", E.knob_cap("hedge_cap", st={**st2, "brake": {"nba": {"until": now + 60}}}, now=now) == 100)
ok("auto_cap: Unlimited stays unlimited; a raise has no ceiling", E.knob_cap("auto_cap", pete=None, st=st2, now=now) is None
   and E.knob_cap("auto_cap", pete=5, st=st2, now=now) == 9)

# ---- 5. #258: tied, one-of, product
cur = {k["name"]: k["start"] for k in E.KNOBS if k["cls"] == "tunable"}
ok("risk product: a risk weight step inside the range is fine", E._knob_blocked("smart_lam", 1.15, cur) is None)
c2 = dict(cur, checkpoint_lam=1.6)
ok("...but not when the whole product would leave 0.5-2.0", E._knob_blocked("smart_lam", 1.7, c2) is not None
   and E._knob_blocked("smart_lam", 1.5, c2) is None)
c3 = dict(cur, trail_drop=0.25)
ok("lock-in trio: only one moves off its start", E._knob_blocked("trail_floor", 1.15, c3) is not None
   and E._knob_blocked("trail_drop", 0.3, c3) is None)

# ---- 6. the stepper, end to end with a stand-in judge
json.dump({"nba": {"n": 45, "floor": 1.7, "lam": 1.15, "loss": None, "sl_n": 10}, "_at": now}, open(E.SMART_FILE, "w"))
json.dump({"all": {"n": 40, "level": 2}}, open(E.SB_DIAL_FILE, "w"))
E.SMART_CACHE["at"] = 0; E.SB_GATE["dial"] = None
bets = [({"id": i, "stake": 5.0, "kick": now - 50 * 86400 + i * 86400 * 0.75, "pl": -5.0, "kind": "single",
          "legs": [{"ticker": "KXNBAGAME-X%d-LAL" % i}]}, [], []) for i in range(60)]
ROWS = {"replay": {"nba": bets, "all": bets, "nhl": bets[:12]}, "sl": {"nba": bets[:20]},
        "sb": {"all": [{"ev": 0.0, "out": 0.0, "kick": now} for _ in range(40)]}}
E._knob_rows = lambda now, deadline=None: ROWS
CALLS = []
def judge(jd, rows, cur_, name, to, cache=None, **kw):
    CALLS.append((name, to))
    base = [(c.get("kick"), 0.0, 5.0) for c, _, _ in rows] if jd not in ("sb", "sbev") else [(r["kick"], 0.0, 5.0) for r in rows]
    if name == "smart_floor" and to == 1.8:          # a clear gain, spread over old and new
        return [(k, (0.9 if i % 4 == 0 else 0.0), s) for i, (k, _, s) in enumerate(base)]
    if name == "smart_lam" and to < cur_[name]:      # an equally clear but smaller gain
        return [(k, (0.6 if i % 4 == 0 else 0.0), s) for i, (k, _, s) in enumerate(base)]
    if name == "smart_loss":                         # a gain only in the old bets: the holdout vetoes it
        return [(k, (1.2 if i % 3 == 0 and i < 40 else 0.0), s) for i, (k, _, s) in enumerate(base)]
    return base
E.knob_judge = judge
smart_before = open(E.SMART_FILE, "rb").read(); dial_before = open(E.SB_DIAL_FILE, "rb").read()
said = E.knob_tune(now, force=True)
S = E.knob_state()
nba = S["groups"].get("nba") or {}
step = [r for r in nba.get("last", []) if r.get("status") == "would step"]
ok("one step for the league: the biggest gain (floor 1.7 → 1.8, seeded from its own live record)",
   len(step) == 1 and step[0]["knob"] == "smart_floor" and step[0]["from"] == 1.7 and step[0]["to"] == 1.8
   and nba["v"]["smart_floor"] == 1.8 and nba.get("step_at") == now)
ok("the other step that clears the bar is noted, not taken",
   any(r["knob"] == "smart_lam" and r["status"] == "qualifies" for r in nba["last"]) and nba["v"]["smart_lam"] == 1.15)
ok("the holdout's veto is recorded", any(r["knob"] == "smart_loss" and r["status"] == "vetoed" for r in nba["last"])
   and nba["v"]["smart_loss"] is None)
ok("the stepper says what it would change, marked not active", any("not active yet" in s and "Profit floor" in s for s in said))
stepped = {n for n, _ in CALLS}
never = {k["name"] for k in E.KNOBS if k["cls"] != "tunable"}
ok("invariants, evidence knobs and settings are never judged or stepped", not (stepped & never)
   and not any(r["knob"] in never for g in S["groups"].values() for r in g.get("last", [])))
ok("only the knobs with a judge are judged", stepped <= set(E.KNOB_JUDGED))
st_of = {r["knob"]: r["status"] for r in nba["last"]}
ok("shared knobs are blocked, tied ones move only through their partner, the rest wait for their test",
   st_of.get("live_spread") == "shared" and "cash_slip" not in st_of and st_of.get("sb_ev_min") != "shared"
   and st_of.get("sl_checks") != "shared" and st_of.get("swing_base") == "tied" and st_of.get("hedge_gap") == "waits"
   and all(st_of.get(n) not in ("waits", "shared") for n in ("exit_q_min", "exit_est_smart", "exit_est_tp", "auto_slip")))
nhl = S["groups"].get("nhl") or {}
ok("a thin history (12 bets) does nothing", not any(r.get("status") in ("would step", "qualifies") for r in nhl.get("last", []))
   and {r["status"] for r in nhl["last"] if r["knob"] == "smart_floor"} == {"thin"} and "smart_floor" not in (nhl.get("v") or {}))
ok("loss guards need 50 combos of their own (20 here): thin", st_of.get("sl_prog") == "thin")
ok("the live tuners' files are untouched", open(E.SMART_FILE, "rb").read() == smart_before and open(E.SB_DIAL_FILE, "rb").read() == dial_before)
rows = E.store_rows("select league, knob, status from knob_shadow")
ok("proposals are logged in the shadow table", any(r["league"] == "nba" and r["knob"] == "smart_floor" and r["status"] == "would step" for r in rows)
   and any(r["status"] == "vetoed" for r in rows))
lr = E.store_rows("select n, staked, live, ver from knob_shadow where league='nba' and knob='smart_floor' and status='would step'")
ok("each row carries the group's size and stake, the live value then and the bar's version",
   lr and lr[0]["n"] == 60 and lr[0]["staked"] == 300.0 and json.loads(lr[0]["live"]) == 1.7 and "hold_min" in lr[0]["ver"])
ok("thin rows are logged with their counts", any(r["status"] == "thin" and r["league"] == "nhl" for r in rows))
ok("Pete's own caps are recorded apart (#260)", S["settings"]["hedge_cap"] == {"pete": 100.0, "system": None}
   and S["settings"]["auto_cap"]["pete"] == E.auto_cap_limit())
ok("weekly: a second call does nothing", E.knob_tune(now + 3600) == [] and S["_next"] >= now + E.KNOB_TUNE_EVERY - 1)
said2 = E.knob_tune(now + 2 * 86400, force=True)
nba2 = E.knob_state()["groups"]["nba"]
ok("the next step waits for 20 new results since the last (judged only on games after it, #264), and the test starts "
   "again from the live value (#267)", nba2["v"]["smart_floor"] == 1.7
   and not any(r.get("status") == "would step" for r in nba2["last"]))
# ties: two equal gains, smallest change wins; then the registry's order
def tie_judge(jd, rows, cur_, name, to, cache=None, **kw):
    base = [(c.get("kick"), 0.0, 5.0) for c, _, _ in rows] if jd not in ("sb", "sbev") else [(r["kick"], 0.0, 5.0) for r in rows]
    if name in ("smart_floor", "smart_lam"):
        return [(k, (0.9 if i % 4 == 0 else 0.0), s) for i, (k, _, s) in enumerate(base)]
    return base
E.knob_judge = tie_judge
os.remove(E.KNOBS_FILE)
E.knob_tune(now, force=True)
st3 = [r for r in E.knob_state()["groups"]["nba"]["last"] if r.get("status") == "would step"]
ok("a tie goes to the smallest change, then the registry's order (floor before risk weight)",
   len(st3) == 1 and st3[0]["knob"] == "smart_floor" and st3[0]["to"] == 1.6)

# ---- 7. errors never raise; the time budget holds
E.knob_judge = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
os.remove(E.KNOBS_FILE)
try:
    r = E.knob_tune(now, force=True)
    ok("a judge that raises: the stepper returns, never raises", r == [])
except Exception as err:
    ok("a judge that raises must not raise: " + repr(err), False)
E.knob_judge = judge
r = E.knob_tune(now, force=True, budget=0.0)
ok("over the time budget: it stops and continues a day later", any("ran out of time" in x for x in r)
   and E.knob_state()["_next"] <= now + E.KNOB_RETRY + 1)
real_rows = E._knob_rows
def slow_rows(now, deadline=None):
    raise E.KnobOutOfTime()
E._knob_rows = slow_rows
ok("reading the bets past the budget: no proposals, tries again in a day", "ran out of time" in " ".join(E.knob_tune(now, force=True)))
E._knob_rows = lambda now, deadline=None: ROWS
open(E.KNOBS_FILE, "w").write("{not json")
E.knob_judge = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
os.remove(E.KNOBS_FILE) if os.path.exists(E.KNOBS_FILE) else None
E.KNOB_RUN["tune_next"] = 0
E.knob_tune(now)
CALLS.clear(); E.knob_judge = judge
ok("a run that hit an error waits a day (not every 10-minute pass), and says why",
   E.knob_tune(now + 600) == [] and not CALLS and "error" in (E.knob_shadow_view(now).get("why") or ""))
E.KNOB_RUN["tune_next"] = 0
# a run cut short resumes where it stopped, within the same weekly cycle
os.remove(E.KNOBS_FILE)
E.knob_tune(now, force=True, budget=1e9)
full = set(E.knob_state()["groups"])
S0 = E.knob_state(); S0["run"] = {"done": False, "cycle": now - 10}; S0["groups"]["all"]["at"] = now - 5
S0["groups"]["nba"]["at"] = now - 20; json.dump(S0, open(E.KNOBS_FILE, "w"))
CALLS.clear()
E.knob_tune(now + 86400, force=True)
ok("a resumed run skips the groups already judged this cycle", full >= {"all", "nba"} and E.knob_state()["groups"]["all"]["at"] == now - 5
   and E.knob_state()["groups"]["nba"]["at"] == now + 86400)
open(E.KNOBS_FILE, "w").write("{not json")
ok("a damaged knobs file is an empty state", E.knob_state()["groups"] == {} and isinstance(E.knob_shadow_view(now), dict))
E.ROLE_BACKUP = True
ok("the Pi never runs it", E.knob_tune(now, force=True) == [] and E.knob_brake_pass(now, force=True) == [])
E.ROLE_BACKUP = False

# ---- 8. the brake, on real automatic sales
os.remove(E.KNOBS_FILE)
E.knob_judge = judge
E.knob_tune(now, force=True)                                   # nba's shadow floor now 1.8 (off its start)
E._ledger_table()
def sale(ts, t, offer, cost, by="mac", kind="combo", held="cost", chance=0.5):
    """A sold bet. #284: a loss = holding was EXPECTED to pay more at the sale: Kalshi's usual offer at the logged
    chance (0.5 x $20 x the in-play discount = $8.20) against the offer; `held` (the realized result) no longer
    matters."""
    held = cost if held == "cost" else held
    E.store_x("insert into sell_log(ts, ticker, result, kind, offer, cost, pays, frac, by, outcome, held, chance) "
              "values(?,?,?,?,?,?,?,?,?,?,?,?)", (ts, t, "sold", kind, offer, cost, 20.0, 1.0, by,
                                                None if held is None else "won", held, chance))
E._combo_league_of = lambda t: "nba" if "NBA" in t else "nhl"
for i in range(3):
    sale(now - 3000 + i, "KXMVENBA-%d" % i, 3.0, 5.0)
ok("3 losses in a row: no brake", E.knob_brake_pass(now, force=True) == [])
sale(now - 2000, "KXMVENBA-PI", 1.0, 5.0, by="pi")
ok("a Pi row never counts", E.knob_brake_pass(now, force=True) == [])
sale(now - 1000, "KXMVENBA-3", 2.0, 5.0)
msgs = E.knob_brake_pass(now, force=True)
S = E.knob_state()
b = S["brake"].get("nba") or {}
ok("4 losses in a row: would brake, one push, plain words, no urgent words", len(msgs) == 1 and "NBA" in msgs[0]
   and "nothing changed" in msgs[0] and not any(w in msgs[0].lower() for w in ("auto", "hedge", "cash out", "paused", "can't")))
ok("the brake lasts 14 days and resets only the shadow values, never looser than they were (#284): the looser risk "
   "weight 1.15 back to 1.0, the stricter floor 1.8x kept", abs(b.get("until", 0) - (now + 14 * 86400)) < 2
   and S["groups"]["nba"]["v"]["smart_floor"] == 1.8 and S["groups"]["nba"]["v"]["smart_lam"] == 1.0
   and b.get("reset") == {"smart_lam": 1.15})
ok("while braked: no second push, the stepper skips the league", E.knob_brake_pass(now + 60, force=True) == []
   and E.knob_tune(now + 60, force=True) is not None
   and E.knob_state()["groups"]["nba"]["last"][0]["status"] == "braked")
ok("the brake is in the shadow table", any(r["status"] == "would brake" for r in E.store_rows("select status from knob_shadow")))
v = E.knob_shadow_view(now)
nb = [x for x in v.get("leagues", []) if x["key"] == "nba"]
ok("the view shows the brake and when it ends", nb and nb[0]["brake"] and nb[0]["brake"]["until_say"])
# the month rule, and old sales before the brake never count again
for i in range(3):
    sale(now - 300 + i, "KXMVENHL-PARTS", 1.0, 5.0)          # one bet sold in 3 parts: one sale for the brake
ok("a bet sold in parts counts once", E.knob_brake_pass(now, force=True) == [] and "nhl" not in E.knob_state()["brake"])
E.store_x("delete from sell_log where ticker='KXMVENHL-PARTS'")
ok("the month rule: 5% of the stake lost (with 4+ sales)",
   E.knob_brake_check([(1, 1.0, 5), (2, -3.0, 5), (3, 0.5, 5), (4, -0.5, 5)]) is not None
   and E.knob_brake_check([(1, 1.0, 5), (2, -1.0, 5), (3, 0.5, 5), (4, -0.5, 5)]) is None
   and E.knob_brake_check([(1, -3.0, 5)]) is None)
for i in range(4):
    sale(now - 500 + i, "KXMVENHL-%d" % i, 1.0, 5.0)
m2 = E.knob_brake_pass(now, force=True)
ok("a league with nothing off its start: would brake is recorded, but no push",
   m2 == [] and (E.knob_state()["brake"].get("nhl") or {}).get("until", 0) > now)
S = E.knob_state()
S["brake"]["nba"]["until"] = now - 1
json.dump(S, open(E.KNOBS_FILE, "w"))
ok("after the brake ends, the sales before it never brake again", E.knob_brake_pass(now + 120, force=True) == []
   and not E._knob_braked(E.knob_state(), "nba", now + 120))

# ---- 9. with the shadow on, every live decision is byte-identical to before
E.knob_judge = judge
os.remove(E.KNOBS_FILE)
E.SMART_CACHE["at"] = 0; E.SB_GATE["dial"] = None
TK = [["KXNBAGAME-26NOV19LALBOS-LAL"], ["KXNHLGAME-26NOV19PHIBOS-PHI"], ["KXEPLGAME-26NOV22ARSCHE-ARS"],
      ["KXNBAGAME-26NOV19LALBOS-LAL", "KXNHLGAME-26NOV19PHIBOS-PHI"]]
rnd = random.Random(7)
STATES = [{"kind": rnd.choice(("combo", "single")), "value": rnd.uniform(0, 30), "real": rnd.choice((0.0, rnd.uniform(0, 30))),
           "peak": rnd.uniform(0, 40), "pays": 30.0, "cost": rnd.uniform(3, 12), "q": rnd.random(), "live": rnd.random() < .6}
          for _ in range(400)]
E.leg_score = lambda l: {"state": "in", "frac": 0.6, "detail": "Q3 4:00", "brk": False}
E.SCORES_BY["nba"] = {"at": time.time(), "by": {}}
def snapshot():
    E.SMART_CACHE["at"] = 0; E.SB_GATE["dial"] = None
    out = []
    for tks in TK:
        es = E.exit_settings(tks)
        out.append((E.smart_params(tks), E.stoploss_params(tks), E.sb_dial(tks, now), es))
        prm = {k: es[k] for k in es if k in ("smart", "floor", "loss", "tp", "trail")}
        prm["lam"] = E.SWING_BASE * es["lam_mult"]
        out.append([E.exit_policy(s, dict(prm, cut_ok=True)) for s in STATES])
    h = {"need": [(("yes", "KXNBAGAME-26NOV19LALBOS-LAL"), "x")], "cost": 5.0}
    E.SL_SEEN.clear() if hasattr(E, "SL_SEEN") and hasattr(E.SL_SEEN, "clear") else None
    out.append(E.hedge_guard("C9", h, {"locked": 9.0}, now)[1])
    out.append((E.auto_cap_limit(), E.auto_cap_reached(), E.CFG.get("hedge_cap"), E.CFG.get("auto_cap")))
    out.append((E.kalshi_discount(True), E.kalshi_discount(False)))
    out.append((open(E.SMART_FILE, "rb").read(), open(E.SB_DIAL_FILE, "rb").read(), json.dumps(E.CFG, sort_keys=True, default=str)))
    return json.dumps(out, sort_keys=True, default=str)
before = snapshot()
cfg_before = copy.deepcopy(E.CFG)
E.knob_tune(now, force=True)
for i in range(4):
    sale(now - 100 + i, "KXMVENBA-L%d" % i, 1.0, 5.0)
E.KNOB_RUN["brake_at"] = 0
E.knob_pass(now)
after = snapshot()
_sv = E.knob_state()
ok("...while the shadow really holds values the live code doesn't use (nba's test floor 1.8, braked back)",
   (_sv["groups"].get("nba") or {}).get("hist", [{}])[-1].get("to") == 1.8 and E.smart_params(TK[0])["floor"] == 1.7
   and (_sv["brake"].get("nba") or {}).get("until", 0) > now)
ok("with the shadow on (proposals and a brake written), every live decision is byte-identical", before == after
   and E.CFG == cfg_before and os.path.exists(E.KNOBS_FILE))
ok("the live code still reads its own constants and files (KNOB_MODE is shadow)", E.KNOB_MODE == "shadow")

# ---- 10. a real replay judge runs on recorded prices (no stand-in)
spec2 = importlib.util.spec_from_file_location("E2", "wahome/engine.py"); E2 = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(E2)
E2.STORE.update(E.STORE)
c = {"id": "x", "kind": "single", "stake": 5.0, "price": 0.5, "kick": now - 86400, "pl": -5.0,
     "legs": [{"ticker": "KXNBAGAME-26NOV19LALBOS-LAL", "p": 0.5}]}
path = [(now - 86400 + i * 60, {"KXNBAGAME-26NOV19LALBOS-LAL": x}) for i, x in enumerate((0.5, 0.6, 0.7, 0.85, 0.9, 0.6, 0.3, 0.1))]
cur0 = {k["name"]: k["start"] for k in E2.KNOBS if k["cls"] == "tunable"}
d = E2.knob_judge("replay", [(c, path, [])] * 3, cur0, "smart_floor", 1.6)
ok("the real replay judge gives one change per bet, in dollars", len(d) == 3 and all(len(x) == 3 for x in d)
   and all(isinstance(x[1], float) for x in d))
v = E2.knob_shadow_view(now)
json.dumps(v)
ok("the view is plain JSON", isinstance(v, dict))
