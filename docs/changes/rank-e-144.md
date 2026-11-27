# rank-e-144: ranking and price-quality fixes (#482, #243, #286, #287)

Rules kept: fail closed, no new automatic money movement, nothing loosened, every new switch defaults ON.

## Done
- **#482 totals curve.** `total_sd_fit` (switch `total_fit_sd`): the Over chance is `min(old, curve at the league's fitted width)`, so it can only go down. "Game not found" badge now has a hover explanation (text unchanged).
- **#243 Best bets.** Singles are dropped when the board is older than 12 min (`fair_at`); up to 10 extra candidates by expected dollars are simulated beyond the cut. (Ranking on calibrated chance and #204 were already fixed in #576.)
- **#286 pregame idea quote** (switch `pregame_idea_fair`): fair needs a fresh (under 12 min) sportsbook-backed side and is `min(book, calibrated)`; otherwise Kalshi's price only, no edge. Suggested stake can only go lower (capped at the panel's own sizing).
- **#287 learned in-play green bar** (switch `live_bar_learn`): PAPER ONLY. `live_single_bar` is reported as `live_bar` on the live quote and noted when it would have changed green; it gates nothing.

## Live numbers that could move
- Totals Over chance (lower only), widths: ncaamb 14.0 to 16.5, ncaawb 13.0 to 16.2, ncaaf 14.0 to 16.0, nfl 10.0 to 12.8, nba 17.0 to 17.8.
- Best bets: singles vanish when the board is stale; extra candidates are simulated.
- Pregame idea fair, edge and stake (lower only; price only without a fresh book).
- Paper `live_bar` field only; no buy decision changes.

## Skipped / needs Pete
- #312 (hedge before below-cost skip): split to its own PR, needs Pete.
- #204 and #243 part 1: already fixed on develop (#576).
- #287 enforcing the learned bar and two-side normalisation: needs Pete's decision.
- #482 items 3 to 7 (learned too-good-to-be-true check, ESPN date match, live-score matching and `_bet_kind`, routing alert totals through `line_recommend`) and changing the badge text.

Tests: `tests/suite/t_rank_e144.py` (new), `t_idea_inplay.py` (updated).
