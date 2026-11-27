# CHECK: group=engine
# Issue #265 (Pete chose the full change): the loss guards sl_prog / sl_drop / sl_checks / sl_span / sl_gap gate BOTH the
# learned loss cut (smart sell's) and the stop-loss switch, but the stepper judged them on the switch's replay alone. Now
# `knob_judge("sl", ...)` judges a step on the decisions that really run (`knob_loss_drivers`: the cut when smart sell is
# on and a cut-off is set; the stop-loss under Allow or a group's own sl_auto), whichever would have sold FIRST per bet,
# net dollars against what the bet cost; neither running = the step changes nothing. This is the case the Opus review of
# #576 flagged: the judge change moves live loss numbers, so it is checked here in numbers. sl_auto's own judge, the
# evidence bar (older 70% picks, newest 30% confirms), the brake, borrowing stricter only and the switch-off numbers are
# unchanged; a loosened loss guard also needs the bootstrap range above zero; an unreadable record = no step.
import os, time, tempfile, importlib.util, json
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.KNOBS_FILE = os.path.join(E.HERE, "knobs.json"); E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.SB_DIAL_FILE = os.path.join(E.HERE, "sb.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
T = "KXNBAGAME-26NOV21BOSNYK-BOS"
t0 = now - 20000
pts = [(0.6, ""), (0.6, ""),
       (0.40, "AAA 40-50 BBB Q3 12:00"), (0.30, "AAA 40-50 BBB Q3 10:30"), (0.25, "AAA 40-50 BBB Q3 9:00"),
       (0.22, "AAA 40-50 BBB Q3 8:00"), (0.18, "AAA 40-50 BBB Q3 7:00"), (0.12, "AAA 40-50 BBB Q3 6:00"),
       (0.11, "AAA 40-50 BBB Q3 5:00"), (0.10, "AAA 40-50 BBB Q3 4:00"), (0.10, "AAA 40-50 BBB Q3 3:00"), (0.0, "Final")]
slp = [(t0 + 60 * k, {T: (ch, tx)}) for k, (ch, tx) in enumerate(pts)]
path = [(ts, {T: v[T][0]}) for ts, v in slp]
c = {"id": "c1", "kind": "combo", "stake": 10.0, "pays": 20.0, "kick": t0, "pl": -10.0, "legs": [{"ticker": T, "p": 0.6}], "_mk": {}}
cur = {"smart_floor": 1.5, "smart_lam": 1.0, "smart_loss": 0.125, "sl_prog": 0.5, "sl_drop": 0.2, "sl_checks": 3,
       "sl_span": 180, "sl_gap": 300, "sl_auto": 0}
for k in ("exit_q_min", "exit_est_smart", "exit_est_tp", "tp_min_gain", "trail_arm", "trail_arm_cost", "trail_drop",
          "trail_floor", "cut_accept", "auto_slip"):
    cur[k] = E.KNOB_BY[k]["start"]


def mode(m):
    E.CFG["stop_loss_mode"] = m
    E.CFG["stop_loss"] = m == "allow"


# ---- 1. which decisions really run
mode("tune")
ok("the default (Let it tune itself, sl_auto off, a cut-off set): only the learned loss cut runs",
   E.knob_loss_drivers(cur) == (True, False))
ok("...its own sl_auto on: both run", E.knob_loss_drivers(dict(cur, sl_auto=1)) == (True, True))
ok("...no cut-off (cut off): only the stop-loss, and only when on", E.knob_loss_drivers(dict(cur, smart_loss=None)) == (False, False)
   and E.knob_loss_drivers(dict(cur, smart_loss=None, sl_auto=1)) == (False, True))
mode("allow")
ok("Allow (guarded): the stop-loss runs in every league", E.knob_loss_drivers(cur) == (True, True))
E.CFG["smart_sell"] = False
ok("smart sell off: the cut does not run", E.knob_loss_drivers(cur) == (False, True))
E.CFG["smart_sell"] = True

# ---- 2. the #576 case: the judge change moves live loss numbers; here is by how much on a recorded game
mode("tune")
cache = {}
cut_cur, cut_new = E._knob_replay_at(c, path, slp, cur, cache), E._knob_replay_at(c, path, slp, dict(cur, sl_prog=0.55), cache)
sl_cur, sl_new = E._knob_sl_at(c, slp, cur, cache), E._knob_sl_at(c, slp, dict(cur, sl_prog=0.55), cache)
old_d = sl_new[0] - sl_cur[0]
new_d = E.knob_judge("sl", [(c, path, slp)], cur, "sl_prog", 0.55)[0][1]
ok("a stricter 'not before' step: the old judge saw the stop-loss (off here) lose money, the real driver (the cut) is unmoved",
   old_d < -0.5 and abs(new_d) < 1e-9 and abs(cut_new[0] - cut_cur[0]) < 1e-9)
d_span = E.knob_judge("sl", [(c, path, slp)], cur, "sl_span", 240)[0][1]
ok("a longer hold step: the cut would never have confirmed in time, so the real driver loses what holding lost (more than the old judge said)",
   d_span < old_d and abs(d_span - (E._knob_replay_at(c, path, slp, dict(cur, sl_span=240), cache)[0] - cut_cur[0])) < 1e-9)
ok("the judge returns the bet's kick time and stake like every judge (the evidence bar's split needs both)",
   E.knob_judge("sl", [(c, path, slp)], cur, "sl_prog", 0.55)[0][0] == c["kick"]
   and E.knob_judge("sl", [(c, path, slp)], cur, "sl_prog", 0.55)[0][2] == 10.0)

# ---- 3. both drivers: whichever sells first
mode("allow")
d_both = E.knob_judge("sl", [(c, path, slp)], cur, "sl_prog", 0.55)[0][1]
ok("Allow: the stop-loss (which sells first here) is what the step moves, on top of the cut", sl_cur[1] < cut_cur[1]
   and abs(d_both - (sl_new[0] - sl_cur[0])) < 1e-9 and d_both < -0.5)
real_a, real_b = E._knob_replay_at, E._knob_sl_at
E._knob_replay_at = lambda *a, **k: (-3.0, 100.0)
E._knob_sl_at = lambda *a, **k: (-6.0, 200.0)
ok("the earlier sale wins (the cut at 100 beats the stop-loss at 200)", E._knob_res_loss(c, path, slp, cur, {}) == -3.0)
E._knob_sl_at = lambda *a, **k: (-6.0, 50.0)
ok("...and the other way round", E._knob_res_loss(c, path, slp, cur, {}) == -6.0)
E._knob_sl_at = lambda *a, **k: (-6.0, 100.0)
ok("a tie takes the lower result (never the rosier one)", E._knob_res_loss(c, path, slp, cur, {}) == -6.0)
E._knob_replay_at = lambda *a, **k: (-10.0, None)
E._knob_sl_at = lambda *a, **k: (-6.0, 200.0)
ok("one sells and the other rides on: the sale counts", E._knob_res_loss(c, path, slp, cur, {}) == -6.0)
E._knob_sl_at = lambda *a, **k: (-10.0, None)
ok("neither sells: the settled result", E._knob_res_loss(c, path, slp, cur, {}) == -10.0)
E._knob_replay_at, E._knob_sl_at = real_a, real_b

# ---- 4. neither running: the step changes nothing live, so it is not judged as a gain
mode("tune")
none = dict(cur, smart_loss=None)
ds = E.knob_judge("sl", [(c, path, slp)], none, "sl_prog", 0.55)
ok("no loss decision running: a guard step gains nothing (it was a feature Pete does not use)", ds[0][1] == 0.0)
ok("sl_auto's own judge is unchanged (the stop-loss's replay on a haircut price vs holding)",
   abs(E.knob_judge("sl", [(c, None, slp)], dict(cur, sl_auto=0), "sl_auto", 1)[0][1]
       - (E._sl_replay(c, slp, 0.5, 0.2, hair=True) - c["pl"])) < 1e-9)

# ---- 5. a record that cannot be read: not judged, no step (fail closed)
try:
    E.knob_judge("sl", [(c, None, slp)], cur, "sl_prog", 0.55)
    ok("a bet with no price record cannot be judged on the cut", False)
except E.KnobJudgeUnreadable:
    ok("a bet with no price record cannot be judged on the cut: the judge says so, never guesses", True)
bad = dict(c, legs=[{"ticker": None}])
bad["stake"] = "junk"
try:
    E._knob_res_loss(bad, path, slp, cur, {})
    ok("damaged evidence raises as unreadable", False)
except E.KnobJudgeUnreadable:
    ok("damaged evidence raises as unreadable", True)
except Exception as err:
    ok("damaged evidence raises as unreadable, not " + type(err).__name__, False)

# ---- 6. the stepper: an unreadable record = no step for that knob, the others still go; a loosened loss guard needs the bootstrap
json.dump({"nba": {"n": 45, "floor": 1.5, "lam": 1.0, "loss": None, "sl_n": 60}, "_at": now}, open(E.SMART_FILE, "w"))
E.SMART_CACHE["at"] = 0
E.CFG["knobs_live"] = True
E.save_json(E.MAIN_SAVED, {"knobs_live": True}); E.KNOB_SWITCH["on"] = None; E.KNOB_STATE_CACHE["d"] = None
bets = [({"id": i, "stake": 5.0, "kick": now - 50 * 86400 + i * 86400 * 0.75, "pl": -5.0, "kind": "combo", "pays": 20.0,
          "legs": [{"ticker": "KXNBAGAME-X%d-LAL" % i}]}, [], []) for i in range(60)]
E._knob_rows = lambda now, deadline=None: {"replay": {"nba": bets}, "sl": {"nba": bets}, "sb": {}}
SEEN = []
def judge(jd, rows, cur_, name, to, cache=None, **kw):
    SEEN.append((name, to))
    if name == "sl_span":
        raise E.KnobJudgeUnreadable("no price record")
    base = [(cc.get("kick"), 0.0, 5.0) for cc, _, _ in rows]
    if name == "sl_prog" and to == 0.45:                      # a clear gain from a LOOSER guard, spread evenly: bootstrap must pass
        return [(k, (0.9 if i % 4 == 0 else 0.0), s) for i, (k, _, s) in enumerate(base)]
    if name == "sl_drop" and to == 0.25:                      # the same gain from a STRICTER guard
        return [(k, (0.9 if i % 4 == 0 else 0.0), s) for i, (k, _, s) in enumerate(base)]
    return base
real_judge = E.knob_judge
E.knob_judge = judge
E.knob_tune(now, force=True)
last = {(r["knob"], r.get("to")): r["status"] for r in (E.knob_state()["groups"].get("nba") or {}).get("last", [])}
ok("an unreadable loss-guard record: that knob is marked unread and takes no step",
   any(k[0] == "sl_span" and v == "unread" for k, v in last.items()) and not any(k[0] == "sl_span" and v in ("stepped", "would step") for k, v in last.items()))
ok("...and the other knobs of the league are still judged (sl_drop, sl_prog, smart sell's numbers)",
   any(n == "sl_drop" for n, _ in SEEN) and any(n == "smart_floor" for n, _ in SEEN))
ok("a stricter loss guard (sl_drop 0.25) that clears the bar steps (live: the five are in KNOB_LIVE)",
   last.get(("sl_drop", 0.25)) in ("stepped", "would step", "qualifies"))
ok("a looser one (sl_prog 0.45) of the same gain is looked at too, the bootstrap check is part of its bar",
   ("sl_prog", 0.45) in last)
E.knob_judge = real_judge
ok("every one of the five is judged by the real-driver judge, and still shares nothing with the hedge",
   all(E.KNOB_JUDGED[n] == "sl" and E.KNOB_BY[n]["judge"] == "_knob_res_loss" for n in E.KNOB_LOSS_GUARDS))

# ---- 6b. Pete's call: the first weekly run is TIGHTEN-ONLY. A loosening step is logged "would have loosened", never applied,
# until the marker lg265_loosen_ok is True in combo_knobs.json (Pete's okay after reading the log). Fail closed.
def run_once(marker, loosen_to, tighten_to=None):
    E.save_json(E.KNOBS_FILE, {} if marker is None else {"lg265_loosen_ok": marker}); E.KNOB_STATE_CACHE["d"] = None
    E.CFG["knobs_live"] = True; E.KNOB_SWITCH["on"] = None
    def jd(jdn, rows, cur_, name, to, cache=None, **kw):
        base = [(cc.get("kick"), 0.0, 5.0) for cc, _, _ in rows]
        if name == "sl_prog" and to == loosen_to or (tighten_to is not None and name == "sl_prog" and to == tighten_to):
            return [(k, (0.9 if i % 4 == 0 else 0.0), s) for i, (k, _, s) in enumerate(base)]
        return base
    E.knob_judge = jd
    E.knob_tune(now, force=True)
    E.knob_judge = real_judge
    g = E.knob_state()["groups"].get("nba") or {}
    return g, {r["to"]: r["status"] for r in g.get("last", []) if r["knob"] == "sl_prog"}
for marker, label in ((None, "no marker"), (False, "marker false"), ("yes", "marker not exactly True")):
    g, st_ = run_once(marker, 0.45)
    ok("loosening a loss guard (" + label + "): not applied, logged as would have loosened",
       st_.get(0.45) == "would have loosened" and "sl_prog" not in (g.get("lv") or {}))
g, st_ = run_once(None, 0.45)
ok("...and the move log has the row", any(r["status"] == "would have loosened" for r in E.store_rows(
    "select status from knob_shadow where knob='sl_prog'")))
g, st_ = run_once(None, 0.45, tighten_to=0.55)
ok("tighten-only: a stricter step of the same gain still goes live on that first run",
   st_.get(0.55) == "stepped" and (g.get("lv") or {}).get("sl_prog") == 0.55)
g, st_ = run_once(True, 0.45)
ok("once Pete okays it (marker True) the loosening step is allowed again",
   st_.get(0.45) == "stepped" and (g.get("lv") or {}).get("sl_prog") == 0.45)
real_load = E.load_json
E.load_json = lambda path, dflt=None: (_ for _ in ()).throw(OSError("unreadable")) if path == E.KNOBS_FILE else real_load(path, dflt)
ok("an unreadable marker file reads as tighten-only", E._lg265_loosen_ok({}) is False and E._lg265_loosen_ok(None) is False)
E.load_json = real_load

# ---- 6c. the reviewer's gap: the bootstrap check blocks a weak loosening gain even with the marker on and every other check met
ds_weak = [(now - 86400 * i, v, 5.0) for i, v in enumerate([3, -2, -2, -2, 3, -2, 3, -2, 3, -2, 3, -2])]
ok("a lumpy gain with a positive mean has a bootstrap range that does not clear zero",
   sum(d for _, d, _ in ds_weak) > 0 and E._guard_bootstrap(ds_weak, None, "sl_prog|nba") <= 0)
E.save_json(E.KNOBS_FILE, {"lg265_loosen_ok": True}); E.KNOB_STATE_CACHE["d"] = None
real_boot = E._guard_bootstrap
def run_boot(lo):
    E._guard_bootstrap = lambda *a, **k: lo
    try:
        return run_once(True, 0.45)
    finally:
        E._guard_bootstrap = real_boot
g, st_ = run_boot(-0.2)
ok("same steady gain, bootstrap range at or below 0 (marker on): the loosening is NOT applied",
   st_.get(0.45) != "stepped" and "sl_prog" not in (g.get("lv") or {}))
g, st_ = run_boot(0.3)
ok("...and with the range above 0 it is (so the bootstrap alone is what blocked it)", st_.get(0.45) == "stepped")

# ---- 7. what does not change
ok("_sl_tune (smart_tune's own mover, used with the switch off) is untouched: the old stop-loss-only score",
   "knob_loss_drivers" not in E._sl_tune.__code__.co_names and "_knob_res_loss" not in E._sl_tune.__code__.co_names)
r_old = E._sl_replay(c, slp, 0.5, 0.2)
ok("_sl_replay without a `when` returns exactly what it did", r_old == sl_cur[0])
print("done")
