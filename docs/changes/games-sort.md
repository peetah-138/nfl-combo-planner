# Games page: sorted by next game (display order only)

**Section:** Screens > Games

Pete: "The games page should be sorted by next game." Order now (all leagues mixed, no money logic touched):

1. **Playing now** (live) first, earliest start first.
2. **Coming up**, soonest start first. A game with no known start time goes after the timed ones.
3. **Finished** at the bottom, most recent first (then "Probably finished", same rule).

Ties break on the ticker, so cards never shuffle between refreshes. The section headings are unchanged.
The Games page has no league filter or tabs, so there was none to keep working.

How: `api_games` (watcher) adds `start_ts` (epoch seconds from the engine's `start_dt`, the same start the game page uses;
null when unknown) and sorts by the same rule; `renderGames` (`spa/games.js`) sorts again with `gameOrder`, so the page does
not depend on the server's order. Test: `tests/suite/test_games_sort.py`.
