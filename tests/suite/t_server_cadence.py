# CHECK: group=engine
"""Faster server cadence (display only): exact constants, the score pacer's ceiling and back-off, the tick throttle, and
that no trading age was touched. No network."""
import os, importlib.util
REPO = os.environ.get("REPO") or os.path.abspath("../..")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
src = open(os.path.join(REPO, "watcher/combo_watcher.py")).read()
spec = importlib.util.spec_from_file_location("W", os.path.join(REPO, "watcher/combo_watcher.py"))
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)

ok("live snapshot 5s fast / 30s slow", (W.LIVE_FAST_SECS, W.LIVE_SLOW_SECS) == (5, 30))
ok("score cache 5s fast / 30s slow", (W.SCORES_FAST_SECS, W.SCORES_SLOW_SECS) == (5, 30))
ok("score floor 4s, backoff 8s, max 60s, 2 fails, 36 per minute, tick gap 2s",
   (W.SCORES_FLOOR_SECS, W.SCORES_BACKOFF_SECS, W.SCORES_BACKOFF_MAX_SECS, W.SCORES_FAIL_LIMIT,
    W.SCORES_CALLS_PER_MIN_CAP, W.LIVE_TICK_MIN_GAP_SECS) == (4, 8, 60, 2, 36, 2))
ok("engine loop score age left at 8 and guard ages untouched", "E.SCORES_MAX_AGE = 8 " in src)

t = [1000.0]
P = W.ScorePacer(clock=lambda: t[0])
ok("healthy: 5s live, 30s idle", P.max_age(True, 'a') == 5 and P.max_age(False, 'a') == 30)
P.note(False, 'a')
ok("one failure: no change", P.max_age(True, 'a') == 5 and P.backoff_age('a') == 0)
P.note(False, 'a')
ok("two failures: back to 8s", P.max_age(True, 'a') == 8 and P.backoff_age('a') == 8)
P.note(False, 'a'); ok("third failure: 16s", P.max_age(True, 'a') == 16)
P.note(False, 'a'); ok("fourth failure: 32s", P.max_age(True, 'a') == 32)
P.note(False, 'a'); P.note(False, 'a'); ok("capped at 60s", P.max_age(True, 'a') == 60)
P.note(True, 'a')
ok("a good read resets to 5s", P.max_age(True, 'a') == 5 and P.backoff_age('a') == 0)

for _ in range(W.SCORES_CALLS_PER_MIN_CAP):
    ok_now = P.allow(); P.record_call()
ok("cap: 36 reads allowed, 37th refused", ok_now and not P.allow())
t[0] += 61
ok("cap clears after a minute", P.allow())

T = W.TickGate(clock=lambda: t[0])
a = T.ready(); t[0] += 1; b = T.ready(); t[0] += 1.5; c = T.ready()
ok("tick: first out, 1s later held, 2.5s later out", a and not b and c)

# review nits: idle never shortens, backoff is per league, exceptions are not retried
Q = W.ScorePacer(clock=lambda: t[0])
for _ in range(2): Q.note(False, "nba")
ok("idle board in backoff stays 30s, never 8s", Q.max_age(False, "nba") == 30 and Q.max_age(True, "nba") == 8)
for _ in range(5): Q.note(False, "nba")
ok("idle board deep in backoff goes to 60s", Q.max_age(False, "nba") == 60)
ok("other league unaffected", Q.max_age(True, "nhl") == 5 and Q.backoff_age("nhl") == 0)
Q.note(True, "nhl")
ok("good read in another league does not reset the failing one", Q.fails["nba"] == 7 and Q.max_age(True, "nba") == 60)
Q.note(True, "nba")
ok("the failing league's own good read resets it", Q.max_age(True, "nba") == 5)
ok("wrapper serves cache on exception, no second read", "return got[\"by\"]" in src and src.count("_orig_fetch_scores(") == 2 and "except Exception:\n            PACER.note(False, c)" in src)
