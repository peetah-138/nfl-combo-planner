# rank-e-144: Best bets and paper live bar (#243, #287)

Rules kept: fail closed, no new automatic money movement, nothing loosened, switch `live_bar_learn` defaults ON.

## Done
- **#243 Best bets.** Singles are dropped when the board is older than 12 min (`fair_at`); up to 10 extra candidates by expected dollars are simulated beyond the cut. (Calibrated ranking and #204 were already fixed in #576.)
- **#287 learned in-play green bar:** PAPER ONLY. `live_single_bar` is reported as `live_bar` on the live quote and noted when it would have changed green; it gates nothing.
- "Game not found" badge has a hover explanation (text unchanged).

## Live numbers that could move
- Best bets: singles vanish when the board is stale; extra candidates are simulated.
- Paper `live_bar` field only; no buy decision changes.

## Skipped / needs Pete
- #482 totals curve and #286 pregame idea fair: landed on develop meanwhile (dropped from this PR).
- #312: its own PR (#603), needs Pete.
- #204, #243 part 1: already fixed (#576).
- #287 enforcing the learned bar and two-side normalisation: needs Pete.
- #482 items 3 to 7 and changing the badge text.

Tests: `tests/suite/t_rank_e144.py` (new).
