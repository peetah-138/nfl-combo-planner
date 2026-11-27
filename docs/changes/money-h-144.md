# money-h-144: two stricter-only money items (#482, #374)

Nothing here moves money by itself, loosens a guard, or adds an automatic action. Each change can only make a displayed
fair chance, a green mark or a recommendation the same or stricter. No new switches (nothing to turn on or off).

## #482 Old total curve never gives a higher chance than at the fitted width
`line_fair` (totals, old model) now takes the lower of the old curve (`TOTAL_SD`) and the same curve at the league's
fitted width from `LINE_TABLES` (`_fitted_total_sd`), when that width is larger. Wider width only lowers a strike below
the book total, and the `min` keeps a strike above it unchanged. Leagues without a fitted width (euroleague) and
hockey/soccer (Poisson) are unchanged. Not done: the learned "too good to be true" check, the book-line display, team
naming, live-score matching, `_bet_kind` exactness and the ESPN date match (items 2-7: display/matching or a product call).

Live numbers that could move: ONLY the old-model fair chance for totals in ncaamb, nba, ncaaf, ncaawb and nfl, and only downward or
unchanged: strikes below the book total get a lower chance (for example ncaamb with a 9-point gap: about 74% becomes about 71%), strikes
above it are unchanged (the `min` makes a higher chance impossible). So totals can only get stricter: a smaller edge, fewer recommendations
on Build, Best bets and the panel. `line_fairs.fair_old` (the old-vs-new comparison feeding `line_gate`) moves the same way.

## #374 Killer skipped deals are scored (measurement only)
`killer_skipped_summary()` adds `skipped` to `killer_summary()`: how many skipped deals, how many settled, and what they
would have won or lost in dollars, split into overlap skips (including "couldn't check your open bets") and the rest, so
the 2-bet / 8% defaults can be tuned from data. Records nothing, buys nothing, changes no skip. Items 1 (unreadable-read
alert) and the 429 cooldown part of 3 were already on develop; the read cache and combo dedupe are not done (a cache
could hide a fresh bet and loosen the guard; the dedupe needs a real Kalshi combo record).

Live numbers that could move: none (a new read-only field).

## Skipped from the middle third of the money list
- #286: already covered by PR #595.
- #309: overlaps open PR #594 (learn-c). #312: overlaps open PR #467 (hedge-vs-skip).
- #287: needs a learned per-league bar from `live_fairs` (design call).
- #316 items 3-5, #383, #382: change sell behaviour or need Pete's call (retry floors, hedge vs back-off, back-off counts).
  #382's wording is already done (#424, #428).

## Tests
`t_money_h144.py` (new; never-higher total curve, skipped-deal scoring).
