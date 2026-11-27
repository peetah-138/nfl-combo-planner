# money-h-144: three stricter-only money items (#286, #482, #374)

Nothing here moves money by itself, loosens a guard, or adds an automatic action. Each change can only make a displayed
fair chance, a green mark or a recommendation the same or stricter. No new switches (nothing to turn on or off).

## #286 Pregame single Buy idea follows Buy straight's fair-price rules
`idea_single_fair` (before the game) now uses `single_buy_quote`'s rules: the board's side only when it has a sportsbook
behind it (`src` set; a side holding Kalshi's own price is circular), read within `SINGLE_FAIR_AGE` (12 min; unknown age
= stale), and a winner's chance goes through `calib_fair`. With no board side the idea's own stored chance is used only
when `pfair_at` (the idea row's `ts`) is that fresh. Otherwise there is no fair price: the card shows Kalshi's price
only, "No fair price (why)", no edge, never green (Buy anyway still works, exactly like a game under way). The watcher's
idea quote passes `pfair_at` and no longer answers "Kalshi isn't listing that game" for a pregame idea with no fair
price. Buy guards, caps, rule 8 and the `IDEA_Q` size/price check are unchanged. Not done: (e) sizing from `_size`
instead of `edge_stake` (changes stakes; Pete's call).

Live numbers that could move: a pregame single idea's shown fair chance and edge (winners: calibrated, so a few points
lower or higher), its green mark (only toward not-green), and the suggested stake `rec` (follows the fair; shown as
$2 minimum when there is none). Ideas older than 12 minutes with no fresh board read show no edge.

## #482 Old total curve never gives a higher chance than at the fitted width
`line_fair` (totals, old model) now takes the lower of the old curve (`TOTAL_SD`) and the same curve at the league's
fitted width from `LINE_TABLES` (`_fitted_total_sd`), when that width is larger. Wider width only lowers a strike below
the book total, and the `min` keeps a strike above it unchanged. Leagues without a fitted width (euroleague) and
hockey/soccer (Poisson) are unchanged. Not done: the learned "too good to be true" check, the book-line display, team
naming, live-score matching, `_bet_kind` exactness and the ESPN date match (items 2-7: display/matching or a product call).

Live numbers that could move: old-model fair chance for totals in ncaamb, nba, ncaaf, ncaawb and nfl on strikes below
the book total (for example ncaamb with a 9-point gap: about 74% becomes about 71%), so fewer total recommendations and
a smaller edge on Build, Best bets and the panel's total lines. The old-model value stored in `line_fairs` (`fair_old`,
the old-vs-new comparison that feeds `line_gate`) moves the same way.

## #374 Killer skipped deals are scored (measurement only)
`killer_skipped_summary()` adds `skipped` to `killer_summary()`: how many skipped deals, how many settled, and what they
would have won or lost in dollars, split into overlap skips (including "couldn't check your open bets") and the rest, so
the 2-bet / 8% defaults can be tuned from data. Records nothing, buys nothing, changes no skip. Items 1 (unreadable-read
alert) and the 429 cooldown part of 3 were already on develop; the read cache and combo dedupe are not done (a cache
could hide a fresh bet and loosen the guard; the dedupe needs a real Kalshi combo record).

Live numbers that could move: none (a new read-only field).

## Skipped from the middle third of the money list
- #309: overlaps open PR #594 (learn-c). #312: overlaps open PR #467 (hedge-vs-skip).
- #287: needs a learned per-league bar from `live_fairs` (design call); its "no side and no kick" gap is covered by #286.
- #316 items 3-5, #383, #382: change sell behaviour or need Pete's call (retry floors, hedge vs back-off, back-off counts).
  #382's wording is already done (#424, #428).

## Tests
`t_money_h144.py` (new; fair-chance rules, never-higher total curve, skipped-deal scoring) and `t_idea_inplay.py` (pregame
cases updated to the new rules).
