# Games page: score memory covers every game (fix)

**Section:** Live page / Games

`renderGames` now calls `scoreWatch(allG)` (the full game list) instead of `scoreWatch(gs)` (the chip-filtered list). Score memory
(`S.gsc`) used to stop updating for cards hidden by a bet-type chip, so switching chips fired a stale "scored" pulse and tick for
a score change that happened while the card was hidden. Display only: nothing here prices, buys, sells or sizes.

ROADMAP: none
