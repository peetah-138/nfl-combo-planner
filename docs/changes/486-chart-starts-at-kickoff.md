# Game page: the "Chance to win" chart starts at kickoff (issue #486)

**Section:** Live page (game detail)

Pete: the chart on a game page began hours before the game (12:41 PM for a later kickoff), a long flat line with the real game squeezed into the last sliver. The Mac records each game's price from long before kickoff, and the chart ran from the first sample.

Display only. No buy, sell, pricing or size decision changes, and nothing in the trading loop reads any of this.

- `api_game` (`watcher/combo_watcher.py`) now also returns `start`: the game's kickoff as epoch seconds, from `A.game_start`, but only when it comes from the sportsbooks or the score feed. The settle-time estimate (which can be hours off, #223) is never offered; then `start` is null. A failure is logged once (`gamestart`) and the page works without it.
- The page (`winRange` in `watcher/spa/game_tabs.js`, used by `paintGame`) takes `t0` = `start`, else the first sample marked in play, else the first score change. Samples before `t0` (and any still marked pre-game) are not drawn and cannot be scrubbed. The x-axis starts at `t0` (left label = kickoff time); score-change markers use the same scale, so they stay aligned. With nothing to anchor on, every in-game sample is drawn as before.
- A game that has not started (start in the future, or state pre with no start) shows "Kicks off at 7:30 PM. The win-chance line starts at kickoff..." (or "Starts <label>") instead of a flat line.
- "Drag to look back" works across the played game from kickoff on. It cannot reach pre-game history any more, because pre-game samples are not drawn (reaching them would need a separate pre-game axis, left out on purpose).

Tests: `test_chartstart_ui.py` (synthetic series with 4 hours of pre-game samples; axis, point count, scrub range, marker x, both fallbacks, not-started notes, 390x844 dark and light), `test_gamedetail_api.py` (`start` from a book kickoff; an estimate is never offered).

ROADMAP: none
