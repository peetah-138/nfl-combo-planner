# Faster browser refresh (issue 21, package 1)

Browser-only pacing change in `watcher/spa/` (`common.js` constants, `boot.js`, `moments.js`). Nothing in the watcher,
`game.js`, `games.*`, buy/sell logic or any external API is touched; the browser still only calls our own server.

- `TICK_GATE_MS` 1500 (was 4000): a stream "tick" refetches Live/Games when the last load is over 1.5 s old.
- Fallback poll every `POLL_EVERY_MS` 5000 (was 12000). It skips when the last load is under `POLL_SSE_SKIP_MS` 30000
  while the stream is up (unchanged), or under `POLL_NOSSE_SKIP_MS` 4000 when the stream is down (was 30000 only when up,
  so a down stream polled every 12 s). A hidden tab never polls (floor unchanged).
- Returning to the tab reloads Live or Games (was Live only) if the last load is over `FG_RELOAD_MIN_MS` 5000 old.
- Game-page redraw gate (4 s, `game.js` package) and server cadence are not changed here.

Test: `tests/suite/t_spa_refresh.py` (exact values and where each is used).
