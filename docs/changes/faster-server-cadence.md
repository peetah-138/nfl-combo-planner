# Faster server cadence (faster-updates plan, package 2)

**Section:** Live page

Display freshness only. The web app's Live snapshot is now rebuilt every 5 s while a game is on (was 8 s) and its ESPN
score cache is 5 s (was 8 s); idle stays 30 s. Constants at the top of `watcher/combo_watcher.py` (`LIVE_FAST_SECS`,
`SCORES_FAST_SECS`, `SCORES_FLOOR_SECS` 4, `SCORES_BACKOFF_SECS` 8, ...). When a Live rebuild finishes the web app
publishes an extra `tick` on the BUS (at most one per `LIVE_TICK_MIN_GAP_SECS` = 2 s) so open pages refetch when data is new.

Rate-limit safety: `ScorePacer` wraps the web app's `fetch_scores`. Never faster than 4 s by default; at most
`SCORES_CALLS_PER_MIN_CAP` (36) ESPN scoreboard reads a minute across leagues (over it the cached copy is served);
after 2 failed reads in a row (error, no new timestamp, or an empty board after a non-empty one, which is how a 429 looks)
the age falls back to 8 s and doubles per further failure up to 60 s; one good read resets it. Kalshi call volume is
unchanged (the account cache is not touched).

Never touches: the watcher engine's `E.SCORES_MAX_AGE` (8 s), `SL_FEED_AGE`, `LIVE_SCORE_AGE`, `SINGLES_SELL_AGE`, any
`max_age=0` guard read, buy/sell/stop-loss logic, Pause, caps, rule 8.

Test: `t_server_cadence.py`.
