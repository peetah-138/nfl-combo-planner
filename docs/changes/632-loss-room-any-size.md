# #632 Loss room stops full auto at any stake size

- `_full_auto_pass`: after `_fa_sized`, every bet goes through new `_fa_loss_fit(stake, left)`, where `left` is the day's loss room
  (`day_loss + loss_today - spent`) minus what this pass already took. A bet that fits is unchanged, one that does not is trimmed
  to the room (to the cent), and a room under the $2 panel minimum (or empty, or not a number) leaves the bet out. So a normal-size
  $10 bet with $3 of room is bought at $3, with $0 it is not bought, and the room shrinks bet by bet inside one pass.
  Before, only grown stakes (150% size) were held to the room; `_fa_sized` never goes below the normal stake.
- Fail closed: a missing, non-numeric or non-finite `day_loss` / `loss_today` / `spent` logs and approves nothing this pass.
- `money()` (planner, ~line 578) now prints negatives as `-$3.50`, not `$-3.50` (#628 had switched a message to this helper).
- Copy: "eases off right away" now says it tightens that setting one step right away.
- Unchanged: $30 cap, $300 bankroll, Pause, the daily-loss brake.
- Tests: `t_autopilot_stake.py` section 13 (exact values for rooms $3, $0, $1.99, $11, $14, $15, $20, 150% size, unreadable data, money()).
