# Faster game page (package 3)

Browser-only pacing change for the open game sheet (`watcher/spa/game.js`, constants in `common.js`, one gate in `moments.js`).
The browser still only calls our own server. Server pacing (the 36/min, 4 s score pacer), engine score ages, `game_detail`
`max_age` and all buy/sell code are untouched, so ESPN and Kalshi volume cannot rise from this change.

- Stream tick redraws an open game after `GAME_TICK_GATE_MS` 3000 (was 4000).
- Fallback timer runs every `GAME_POLL_EVERY_MS` 2000 and redraws if the last draw is over `GAME_POLL_SKIP_MS` 3500 (was 5500).
  A hidden tab never polls.
- Returning to the tab with a game open redraws at once if the last draw is over `FG_RELOAD_MIN_MS` 5000 (the same gate Live and Games use).
- The existing "Updated / Prices ... scores ..." line on the game sheet greys (class `old`) after `GAME_STALE_S` 20 s (was 60 s) so stale data is visible.

Test: `tests/suite/t_game_refresh.py`.
