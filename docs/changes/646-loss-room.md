# Loss room counts a settled loss once (#646)

**Section:** Full auto / Money

Changed (a money brake, loosened by Pete's decision of 2026-11-28 and given a safety cushion):

- The daily loss room full auto sizes against was `day_loss + loss_today - spent`. `spent` is every stake bought today, settled
  or not, and a settled bet's loss is already in `loss_today`, so a settled loss was taken off twice and full auto stopped
  sooner than the $20 limit. Now `_fa_loss_room(v)` = `(day_loss x (1 - FA_LOSS_MARGIN)) + loss_today - open_stake`, where
  `open_stake` (new field from `fa_check`) is today's stakes still at risk (no result yet; includes Pete's manual open bets, the conservative reading).
- `FA_LOSS_MARGIN = 0.10` is a named constant: full auto plans against $18 of a $20 limit. The room is the smaller of the cushioned
  and the exact value, so it is never larger than the exact-$20 answer, never below 0, and Pete's $20 setting itself is untouched.
- Example day, limit $20, one settled $5 loss, nothing open: old room $10.00, exact $15.00, now $13.00.
- Fail closed: a missing, None, text, non-finite or negative number raises and the pass buys nothing. Trimming still rounds down
  (`_fa_loss_fit`), nothing under the $2 minimum, and the room still shrinks bet by bet within a pass.
- The brake itself (`loss_today <= -day_loss`) and Pete's limits ($300 bankroll, $30 cap, $20 loss limit, Pause; Pi never trades) are unchanged.

Tests: `tests/suite/t_autopilot_stake.py` section 13 (exact values: settled loss once, cushion, old-blocked/new-allows, right at the limit blocks, fail closed).

ROADMAP: none
