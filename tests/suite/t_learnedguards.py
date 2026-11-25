# CHECK: group=engine
# Learned selling guards (Pete: "we're just making up rules that we should allow to have some level of learning").
# The score-age tolerance (sl_feed_age) and the break rule (brk_on / brk_move) become learned settings behind Settings >
# Cash out 'Let the selling guards learn' (learned_guards, ON by default, needs knobs_live). Checks: the defaults and the
# registry bounds; switch OFF (either switch) is exactly develop (same live set, 150 s, a break always blocks a sale, no
# episodes recorded, the stepper's list unchanged); nothing learned = the start; a learned value is used for its own
# league, a borrowed one only stricter, a corrupt or out-of-range recorded value is the start; the sample threshold
# (20 episodes), the 30 s step, the 90-300 s band; a loosening step needs net dollars after fees and a bootstrap range above
# zero (seeded: deterministic), a tightening one a lighter bar; NaN / junk rows are skipped; a break may open only a LOSS
# sale, never a hedge, only on a league's own record, a fresh two-sided book and two reads; no score at all, a game not
# under way and a one-sided book still mean no sale; Pause wins over the automatic path; the manual Sell never reads any of
# this; every move is logged in a bounded table.
import os, time, tempfile, importlib.util, json, math, inspect, re
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SB_DIAL_FILE = os.path.join(E.HERE, "sb.json"); E.SB_GATE["dial"] = None
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json"); E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.KNOBS_FILE = os.path.join(E.HERE, "knobs.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
K = E.KNOB_BY
T = "KXNBAGAME-26NOV19LALBOS-LAL"


def switches(knobs=True, guards=True):
    E.CFG["knobs_live"] = knobs
    E.CFG["learned_guards"] = guards
    E.save_json(E.MAIN_SAVED, {"knobs_live": knobs, "learned_guards": guards})
    E.KNOB_SWITCH["on"] = None
    E.GUARD_SWITCH.update(at=0.0, on=None)
    E.KNOB_STATE_CACHE["d"] = None


def put_knobs(groups):
    json.dump({"groups": groups}, open(E.KNOBS_FILE, "w"))
    E.KNOB_STATE_CACHE["d"] = None


def feed_rows(rows, league="nba"):
    E._feed_table()
    E.store_x("delete from feed_ep")
    for i, (age, bid, later) in enumerate(rows):
        E.store_x("insert into feed_ep(ts, ticker, side, league, age, bid, later) values(?,?,?,?,?,?,?)",
                  (now - 30 * 86400 + i * 3600, T, "yes", league, age, bid, later))


def reset_stepper():
    E.KNOB_RUN["tune_next"] = 0
    E.store_x("delete from knob_shadow")
    try:
        os.remove(E.KNOBS_FILE)
    except OSError:
        pass
    E.KNOB_STATE_CACHE["d"] = None


# ---- 1. defaults, registry
ok("the switch is a shared setting and defaults ON", E.DEFAULTS["learned_guards"] is True and "learned_guards" in E.SHARED_KEYS)
k = K["sl_feed_age"]
ok("the score age starts at today's 150 s, tunable 90-300 s in 30 s steps, only shorter is stricter",
   k["cls"] == "tunable" and k["start"] == E.SL_FEED_AGE == 150 and (k["min"], k["max"], k["step"]) == (90, 300, 30)
   and k["stricter"] == "down" and k["borrow"] == "chain-stricter" and E.KNOB_JUDGED["sl_feed_age"] == "feed"
   and E.KNOB_MIN_N["feed"] == "FEED_MIN_N" and E.FEED_MIN_N == 20)
ok("the break guard starts blocked and needs its sample (40 episodes) before it can open",
   K["brk_on"]["start"] == 0 and E.BRK_MIN_N >= 20 and E.KNOB_MIN_N["brk"] == "BRK_MIN_N")
ok("the early-game cutoff (sl_prog) is already learned: no second mover is added",
   K["sl_prog"]["cls"] == "tunable" and E.KNOB_JUDGED["sl_prog"] == "sl" and "sl_prog" in E.KNOB_LIVE
   and "sl_prog" not in E.GUARD_KNOBS)
ok("steps are bounded by the registry: 90 up only, 300 down only, 30 s at a time",
   E.knob_candidates("sl_feed_age", 150) == [120, 180] and E.knob_candidates("sl_feed_age", 90) == [120]
   and E.knob_candidates("sl_feed_age", 300) == [270])

# ---- 2. switch OFF = develop
E.leg_score = lambda l: {"state": "in", "frac": 0.3, "detail": "Q3 4:00", "brk": False}
E.SCORES_BY["nba"] = {"at": now - 200, "by": {}}                         # a score 200 s old
for kn, gd in ((False, True), (True, False), (False, False)):
    switches(kn, gd)
    put_knobs({"nba": {"lv": {"sl_feed_age": 240, "brk_on": 1, "brk_move": 0.04}, "lat": {}}})
    ok(f"knobs_live={kn} learned_guards={gd}: develop's live set, 150 s, a 200 s score stale, no episodes",
       E.guards_on() is False and E.knob_live_names() is E.KNOB_LIVE and E.feed_age_limit(T, True) == 150
       and E.fresh_live_score(T, "yes", now, loose=True) == (None, "score feed stale")
       and E.guards_view("nba")["on"] is False)
    E.FEED_EP.clear()
    E.PRICE_SEEN[T] = (now, 0.2, 0.24, 5)
    E.stop_loss_leg(T, "yes", 0.7, 0.2, {"prog": 0.2, "drop": 0.2}, now)
    ok(f"   ...nothing is recorded ({kn},{gd})", not E.FEED_EP)
E.SCORES_BY["nba"] = {"at": now - 100, "by": {}}
switches(False, False)
ok("a break always blocks a loss sale with the guards off, whatever is recorded",
   E.break_ok(T, "yes", {"state": "in", "detail": "Half", "frac": 0.5}, now, "loss") is False)

# ---- 3. switch ON: nothing learned = the start; a learned value; borrowed only stricter; junk = the start
switches(True, True)
put_knobs({})
E.SCORES_BY["nba"] = {"at": now - 200, "by": {}}
ok("ON with nothing learned: still 150 s (a 200 s score is stale)",
   E.guards_on() and E.feed_age_limit(T, True) == 150 and E.fresh_live_score(T, "yes", now, loose=True)[1] == "score feed stale")
put_knobs({"nba": {"lv": {"sl_feed_age": 210}, "lat": {}}})
E.book_depth = lambda t, max_age=None: {"bid": 0.30, "ask": 0.34, "spread": 0.04}
ok("a league's own learned 210 s lets a LOSS sale use a 200 s score",
   E.feed_age_limit(T, True) == 210 and E.fresh_live_score(T, "yes", now, loose=True)[0] is not None)
ok("...but a hedge or the sell-more check never goes above 150 s", E.feed_age_limit(T, False) == 150
   and E.fresh_live_score(T, "yes", now)[1] == "score feed stale")
ok("...and a score 260 s old is still stale at 210 s", E.SCORES_BY["nba"].update(at=now - 260) is None
   and E.fresh_live_score(T, "yes", now, loose=True)[1] == "score feed stale")
E.SCORES_BY["nba"] = {"at": now - 200, "by": {}}
put_knobs({"all": {"lv": {"sl_feed_age": 240}, "lat": {}}})
ok("a value learned for everyone is never borrowed looser (per league else global: only stricter)",
   E.feed_age_limit(T, True) == 150)
put_knobs({"all": {"lv": {"sl_feed_age": 120}, "lat": {}}})
ok("...a stricter one is borrowed", E.feed_age_limit(T, True) == 120)
bad = True
for junk in (float("nan"), float("inf"), "x", None, True, 9999, 10, -5, [1]):
    put_knobs({"nba": {"lv": {"sl_feed_age": junk}, "lat": {}}})
    bad = bad and E.feed_age_limit(T, True) == 150
ok("a NaN, text, bool, out-of-band or corrupt recorded value falls back to the start", bad)
open(E.KNOBS_FILE, "w").write("{not json"); E.KNOB_STATE_CACHE["d"] = None
ok("a corrupt knobs file falls back to the start", E.feed_age_limit(T, True) == 150)
ok("no score at all is never allowed, whatever is learned",
   (put_knobs({"nba": {"lv": {"sl_feed_age": 300}, "lat": {}}}), setattr(E, "leg_score", lambda l: None),
    E.fresh_live_score(T, "yes", now, loose=True))[2] == (None, "no score feed"))
put_knobs({"nba": {"lv": {"sl_feed_age": 210}, "lat": {}}})
E.leg_score = lambda l: {"state": "in", "frac": 0.3, "detail": "Q3 4:00", "brk": False}
E.SCORES_BY["nba"] = {"at": now - 200, "by": {}}
E.book_depth = lambda t, max_age=None: {"bid": 0.30, "ask": 0.0, "spread": None}
ok("a widened score age needs a fresh two-sided book (else stale: a break may hide inside it)",
   E.fresh_live_score(T, "yes", now, loose=True)[1] == "score feed stale")
E.book_depth = lambda t, max_age=None: {"bid": 0.30, "ask": 0.34, "spread": 0.04}
E.leg_score = lambda l: {"state": "post", "frac": 0.0, "detail": "Final", "brk": False}
ok("a game not under way is never allowed", E.fresh_live_score(T, "yes", now, loose=True)[1] == "game not under way")
E.leg_score = lambda l: {"state": "in", "frac": 0.3, "detail": "Q3 4:00", "brk": False}
E.SCORES_BY["nba"] = {"at": 0, "by": {}}
ok("a feed that never reported (age unknown) is stale even at 300 s", E.fresh_live_score(T, "yes", now, loose=True)[1] == "score feed stale")

# ---- 4. episodes: recorded only when every other guard held and the book is two-sided; resolved after 10 minutes
switches(True, True); put_knobs({})
E.SCORES_BY["nba"] = {"at": now - 200, "by": {}}
E.FEED_EP.clear()
pr = {"prog": 0.2, "drop": 0.2}
E.PRICE_SEEN[T] = (now, 0.30, 0.34, 5)
E.stop_loss_leg(T, "yes", 0.7, 0.2, pr, now)
ok("a stale-score refusal with every other guard holding is recorded as an episode (age 200, bid 0.30)",
   list(E.FEED_EP.values())[0]["age"] == 200.0 and list(E.FEED_EP.values())[0]["bid"] == 0.30)
E.FEED_EP.clear(); E.PRICE_SEEN[T] = (now, 0.30, 0.0, 5)
E.stop_loss_leg(T, "yes", 0.7, 0.2, pr, now)
ok("a one-sided book is never an episode", not E.FEED_EP)
E.FEED_EP.clear(); E.PRICE_SEEN[T] = (now, 0.30, 0.34, 5)
E.stop_loss_leg(T, "yes", 0.9, 0.6, pr, now)
ok("not far enough below the pregame chance: not an episode", not E.FEED_EP)
E.leg_score = lambda l: {"state": "in", "frac": 0.95, "detail": "Q1 11:00", "brk": False}
E.FEED_EP.clear()
E.stop_loss_leg(T, "yes", 0.7, 0.2, pr, now)
ok("too early in the game: not an episode", not E.FEED_EP)
E.leg_score = lambda l: {"state": "in", "frac": 0.3, "detail": "Half", "brk": True}
E.FEED_EP.clear()
E.stop_loss_leg(T, "yes", 0.7, 0.2, pr, now)
ok("a break: not an episode", not E.FEED_EP)
E.leg_score = lambda l: {"state": "in", "frac": 0.3, "detail": "Q3 4:00", "brk": False}
E.SCORES_BY["nba"] = {"at": now - 400, "by": {}}
E.FEED_EP.clear()
E.stop_loss_leg(T, "yes", 0.7, 0.2, pr, now)
ok("a score older than the band (400 s) is not an episode", not E.FEED_EP)
E.SCORES_BY["nba"] = {"at": now - 200, "by": {}}
E.stop_loss_leg(T, "yes", 0.7, 0.2, pr, now)
E.PRICE_SEEN[T] = (now + 600, 0.22, 0.26, 5)
E.store_x("delete from feed_ep")
E.feed_resolve(now + 601)
row = (E.store_rows("select * from feed_ep") or [{}])[0]
ok("after 10 minutes the later bid is written (0.22) and the episode closes",
   row.get("bid") == 0.30 and row.get("later") == 0.22 and row.get("league") == "nba" and not E.FEED_EP)
E.stop_loss_leg(T, "yes", 0.7, 0.2, pr, now + 700)
E.PRICE_SEEN[T] = (now + 700, 0.22, 0.26, 5)
E.feed_resolve(now + 700 + E.FEED_DROP + 5)
ok("an episode that cannot be priced within 30 minutes is dropped", not E.FEED_EP)

# ---- 5. the judge: net dollars after fees, sign, tolerance
f = E.single_fee
sell, later = 0.30, 0.22
ok("selling at 0.30 vs 0.22 later: +the gap, less the fee difference",
   abs(E._knob_res_feed({"age": 170, "bid": sell, "later": later}, {"sl_feed_age": 180})
       - ((sell - f(sell)) - (later - f(later)))) < 1e-9
   and E._knob_res_feed({"age": 170, "bid": sell, "later": later}, {"sl_feed_age": 150}) == 0.0
   and E._knob_res_feed({"age": 170, "bid": 0.2, "later": 0.3}, {"sl_feed_age": 180}) < 0)
ds = E.knob_judge("feed", [{"kick": 1, "age": 170, "bid": 0.3, "later": 0.2}], {"sl_feed_age": 150}, "sl_feed_age", 180)
ds2 = E.knob_judge("feed", [{"kick": 1, "age": 170, "bid": 0.3, "later": 0.2}], {"sl_feed_age": 180}, "sl_feed_age", 150)
ok("loosening gains what tightening back loses", len(ds) == 1 and ds[0][1] > 0 and abs(ds[0][1] + ds2[0][1]) < 1e-3)

# ---- 6. the stepper: sample threshold, step size, bootstrap, tightening bar, bounds
import random as _r
rg = _r.Random(7)


def gain_rows(n, age=170, bid=0.30, drop=0.08):
    return [(age, bid + rg.uniform(-0.01, 0.01), bid - drop + rg.uniform(-0.02, 0.02)) for _ in range(n)]


switches(True, True); reset_stepper()
feed_rows(gain_rows(19))
E.knob_tune(now, force=True)
st = E.knob_state()
last = {r["knob"]: r for r in st["groups"].get("nba", {}).get("last", [])}
ok("19 episodes: too few, nothing moves (sample threshold 20)",
   last.get("sl_feed_age", {}).get("status") == "thin" and "sl_feed_age" not in (st["groups"]["nba"].get("lv") or {}))
reset_stepper(); feed_rows(gain_rows(20))
said = E.knob_tune(now, force=True)
st = E.knob_state()
lv = (st["groups"].get("nba") or {}).get("lv") or {}
ok("20 episodes where waiting lost money: the league's score age loosens ONE 30 s step (150 to 180), live",
   lv.get("sl_feed_age") == 180 and any("sl_feed_age" in str(x) or "score" in str(x).lower() for x in said))
logged = E.store_rows("select knob, from_v, to_v, status, why from knob_shadow where knob='sl_feed_age' and status='stepped'")
ok("the move is logged in the bounded table (old to new, with the reason)",
   len(logged) >= 1 and json.loads(logged[0]["from_v"]) == 150 and json.loads(logged[0]["to_v"]) == 180 and logged[0]["why"])
ok("...and the live walk now uses it for that league only", E.feed_age_limit(T, True) == 180
   and E.feed_age_limit("KXNHLGAME-26NOV21PHIBOS-PHI", True) == 150)
g_all = (st["groups"].get("all") or {})
ok("the global group never loosens live (a borrowed value is only stricter): it is a would-step at most",
   (g_all.get("lv") or {}).get("sl_feed_age") is None)
reset_stepper(); feed_rows(gain_rows(40, drop=-0.05))
E.knob_tune(now, force=True)
lv = (E.knob_state()["groups"].get("nba") or {}).get("lv") or {}
ok("episodes where selling beat waiting by nothing (waiting was better): no loosening", lv.get("sl_feed_age") != 180)
# noisy, zero-mean: the bootstrap range includes zero, so no loosening
reset_stepper()
feed_rows([(170, 0.30, 0.30 + (0.1 if i % 2 else -0.1)) for i in range(40)])
E.knob_tune(now, force=True)
lv = (E.knob_state()["groups"].get("nba") or {}).get("lv") or {}
ok("a noisy, zero-mean result never loosens (the bootstrap range includes zero)", lv.get("sl_feed_age") != 180)
ok("the bootstrap is seeded: the same data gives the same bound",
   E._guard_bootstrap([(1, d, 1.0) for d in (0.1, -0.05, 0.2, 0.0, 0.07)], None, "a|b")
   == E._guard_bootstrap([(1, d, 1.0) for d in (0.1, -0.05, 0.2, 0.0, 0.07)], None, "a|b")
   and E._guard_bootstrap([(1, 0.1, 1.0)], None, "a|b") == -math.inf
   and E._guard_bootstrap([(1, float("nan"), 1.0), (1, 0.1, 1.0)], None, "a|b") == -math.inf)
# tightening: selling on a 130 s score lost against waiting, so the age tightens to 120 on a lighter bar (12 episodes)
reset_stepper(); feed_rows([(130, 0.30 + rg.uniform(-0.01, 0.01), 0.40 + rg.uniform(-0.02, 0.02)) for _ in range(24)])
E.knob_tune(now, force=True)
lv = (E.knob_state()["groups"].get("nba") or {}).get("lv") or {}
ok("episodes where selling on a 130 s score lost against waiting tighten the age one step (to 120)",
   lv.get("sl_feed_age") == 120 and E.GUARD_TIGHT["new"] < E.KNOB_EVIDENCE["new"])
# bounds: from 300 nothing can go above; from 90 nothing below; a loosening is never proposed there
reset_stepper()
put_knobs({"nba": {"lv": {"sl_feed_age": 300}, "lat": {}, "v": {}, "last": []}})
feed_rows(gain_rows(40, age=290))
E.knob_tune(now, force=True)
lv = (E.knob_state()["groups"].get("nba") or {}).get("lv") or {}
ok("at the top of the band (300 s) the value never goes higher", lv.get("sl_feed_age", 300) <= 300)
# corrupt history rows are skipped, never raise
reset_stepper()
E._feed_table(); E.store_x("delete from feed_ep")
for r in (("x", 0.3, 0.2), (170, None, 0.2), (170, 0.3, "junk"), (170, 1.7, 0.2), (170, 0.3, -1), (float("nan"), 0.3, 0.2)):
    E.store_x("insert into feed_ep(ts, ticker, side, league, age, bid, later) values(?,?,?,?,?,?,?)", (now - 86400, T, "yes", "nba", *r))
rows = E._knob_rows_feed(now)
ok("NaN, NULL, text and out-of-range history rows are skipped (the start stays)", not rows.get("nba") and not rows.get("all"))
ok("...and the stepper still runs", isinstance(E.knob_tune(now, force=True), list))
ok("with the switch off the stepper's list and rows are develop's (no feed judge, no sl_feed_age row)",
   (switches(True, False), reset_stepper(), feed_rows(gain_rows(40)), E.knob_tune(now, force=True),
    "sl_feed_age" not in [r["knob"] for r in E.knob_state()["groups"].get("nba", {}).get("last", [])] and not E._knob_rows_feed(now))[-1])

# ---- 7. the brake shrinks a learned value back to the start (reused machinery)
switches(True, True)
put_knobs({"nba": {"lv": {"sl_feed_age": 240}, "lat": {}}, "_": 0})
st = E.knob_state_cached()
st["brake"] = {"nba": {"until": now + 86400, "mode": "live", "why": "test"}}
E.KNOB_STATE_CACHE.update(at=time.monotonic(), d=st)
ok("a losing streak (the league's live brake) puts the score age back at its start",
   E.knob_live_value("sl_feed_age", "nba", None, st, {}, now)[0] == 150)
E.KNOB_STATE_CACHE["d"] = None

# ---- 8. the break: a LOSS sale only, own record only, two reads, fresh two-sided book
switches(True, True)
T1 = "KXNBAGAME-26NOV21BOSNYK-BOS"
sc_half = {"state": "in", "detail": "Half", "frac": 0.5}
E.leg_score = lambda l: sc_half
E.SCORES_BY["nba"] = {"at": time.time(), "by": {}}
put_knobs({})
E.BRK_EP.clear()
t0 = time.time()
for j, (bid, ask) in enumerate(((0.30, 0.34), (0.20, 0.24), (0.19, 0.23))):
    E.PRICE_SEEN[T1] = (t0 + 30 * j, bid, ask, 5)
    E.break_watch(T1, "yes", sc_half, t0 + 30 * j)
E.PRICE_SEEN[T1] = (t0 + 100, 0.20, 0.24, 5)
E.break_watch(T1, "yes", sc_half, t0 + 100)
E.book_depth = lambda t, max_age=None: {"bid": 0.20, "ask": 0.24, "spread": 0.04}
ok("nothing learned: a break blocks a loss sale and a hedge (the start)",
   E.break_ok(T1, "yes", sc_half, t0 + 100, "loss") is False and E.break_ok(T1, "yes", sc_half, t0 + 100, "hedge") is False)
put_knobs({"nba": {"lv": {"brk_on": 1, "brk_move": 0.08}, "lat": {}}})
ok("a league's own learned break rule lets a LOSS sale through on two reads and a fresh book",
   E.break_ok(T1, "yes", sc_half, t0 + 100, "loss") is True)
ok("...but never a hedge (a hedge always waits out the break)", E.break_ok(T1, "yes", sc_half, t0 + 100, "hedge") is False)
E.book_depth = lambda t, max_age=None: {"bid": 0.20, "ask": 0.0, "spread": None}
ok("...a one-sided or empty book still means no sale", E.break_ok(T1, "yes", sc_half, t0 + 100, "loss") is False)
E.book_depth = lambda t, max_age=None: {"bid": 0.20, "ask": 0.24, "spread": 0.04}
put_knobs({"all": {"lv": {"brk_on": 1, "brk_move": 0.08}, "lat": {}}})
ok("...a break rule learned for everyone is never borrowed (own record only)", E.break_ok(T1, "yes", sc_half, t0 + 100, "loss") is False)
put_knobs({"nba": {"lv": {"brk_on": 1, "brk_move": 0.08}, "lat": {}}})
switches(True, False)
ok("...and switched off, develop's rule: a break blocks it again", E.break_ok(T1, "yes", sc_half, t0 + 100, "loss") is False)
ok("BRK_LIVE (the old unlearned way) stays off", E.BRK_LIVE is False)
switches(True, True)
for junk in (float("nan"), "x", 7, True, -1):
    put_knobs({"nba": {"lv": {"brk_on": junk, "brk_move": 0.08}, "lat": {}}})
    if E.break_ok(T1, "yes", sc_half, t0 + 100, "loss") is not False:
        junk = "FAIL"
        break
ok("a corrupt recorded break value never opens a break", junk != "FAIL")

# ---- 9. the break table: bounded, and the judge counts fees only with the guards on
E.store_x("delete from break_ep")
for i in range(5200):
    E.store_x("insert into break_ep(ts, ticker, side, league, detail, news, reads, after_bid, after_ts, would) "
              "values(?,?,?,?,?,?,?,?,?,?)", (now - 100 - i, T1, "yes", "nba", "Half", 0, "[]", 0.1, now, None))
switches(True, True); reset_stepper()
E.knob_tune(now, force=True)
ok("the break table keeps its newest ~5000 rows with the guards on",
   E.store_rows("select count(*) n from break_ep")[0]["n"] <= E.BRK_KEEP_ROWS)
ok("the move log is bounded too", E.KNOB_SHADOW_ROWS == 20000)
r = {"reads": [(0, 0.3, 0.32), (30, 0.2, 0.22), (95, 0.2, 0.22)], "after": 0.15, "news": False}
v = {"brk_on": 1, "brk_move": 0.08}
net = E._knob_res_brk(r, v)
E.GUARD_SWITCH.update(at=time.monotonic(), on=False)
gross = E._knob_res_brk(r, v)
E.GUARD_SWITCH.update(at=0.0, on=None)
ok("the break judge is net of fees with the guards on, develop's gross with them off",
   abs(gross - 0.05) < 1e-9 and abs(net - ((0.2 - f(0.2)) - (0.15 - f(0.15)))) < 1e-9 and net != gross)

# ---- 10. Pause wins; the manual Sell never reads any of this
switches(True, True)
put_knobs({"nba": {"lv": {"sl_feed_age": 300, "brk_on": 1, "brk_move": 0.04}, "lat": {}}})
called = []
E.CFG["auto_sell"] = True
E.can_trade = lambda: True
E.TRADING_PAUSED = lambda: True
E.sell_held = lambda out: called.append("sell_held") or False
E.stop_loss_leg = lambda *a, **k: called.append("leg") or (True, "")
res = E.auto_sell_now({"acts": {"KXNBAGAME-26NOV19LALBOS": 1.0}})
ok("Pause wins: with every guard learned wide open, the automatic path does nothing", res == [] and not called)
E.TRADING_PAUSED = None
src = open("wahome/engine.py", encoding="utf-8").read()
ws = open("wtest/combo_watcher.py", encoding="utf-8").read()
fns = {m.group(1): m.start() for m in re.finditer(r"^def (\w+)\(", src, re.M)}
names = sorted(fns, key=fns.get)


def owner_of(pos):
    best = None
    for n in names:
        if fns[n] <= pos:
            best = n
    return best


users = {"guards_on", "feed_age_limit", "fresh_live_score", "feed_note", "break_ok", "guards_view", "knob_live_names"}
callers = set()
for u in users:
    for m in re.finditer(r"\b%s\(" % u, src):
        o = owner_of(m.start())
        if o != u:
            callers.add(o)
allowed = {"guards_on", "knob_live_names", "feed_age_limit", "fresh_live_score", "feed_note", "feed_resolve", "stop_loss_leg",
           "break_ok", "guards_view", "hedge_guard", "_knob_res_brk", "_knob_rows_feed", "knob_tune", "knob_pass",
           "sell_more_guard", "knob_shadow_view", "_knob_league", "knob_view", "_knob_rows", "knob_tune", "knob_state_cached",
           "stoploss_params", "knob_live_names", "_knob_ctx", "knob_judge", "knob_cap", "knob", "break_watch", "break_watch_held"}
odd = sorted(c for c in callers if c not in allowed and not str(c).startswith(("_knob", "knob", "hedge", "sell_more", "stop_loss", "sl_", "auto_")))
ok("only the automatic sell paths and the stepper read the learned guards (never the manual Sell)" + (f" {odd}" if odd else ""), not odd)
man = inspect.getsource(E.sell_single_now) + inspect.getsource(E.accept_offer)
ok("the one-tap Sell and the order sender never read a guard",
   not any(u in man for u in ("guards_on", "feed_age_limit", "fresh_live_score", "break_ok", "feed_note")))
ok("the watcher reads the guards only to show them (Settings)", {m for m in re.findall(r"A\.(guards_on|feed_age_limit|fresh_live_score|break_ok|feed_note|guards_view)\b", ws)} <= {"guards_view"})
ok("Rule 8 is untouched: an unknown buy outcome is still marked and never retried",
   "COMBO_UNSURE_MSG" in src and "mark_rfq_unsure" in inspect.getsource(E.accept_offer))
