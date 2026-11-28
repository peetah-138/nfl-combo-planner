# Loss room also counts Pete's settled manual losses (#646 follow-up, tighten-only)

**Section:** Full auto / Money

Found in the release 149 review: `loss_today` carries only full auto's own bets, and #646 stopped subtracting settled stakes, so a
settled MANUAL loss (or a settled bet with no P/L recorded) no longer reduced full auto's room at all. New `_fa_extra_loss(rows)`,
read by `fa_check` as `extra_loss`: today's settled real bets that `loss_today` does not carry. A manual loss counts as the dollars
lost (`panel_pl`); a manual win adds nothing; a settled bet with no readable P/L (either kind) counts as its whole stake. `_fa_loss_room`
subtracts it from both the cushioned and the exact value, so the room only ever shrinks: never above the #646 value, never above
exact-$20, never below 0. No manual loss and readable P/L = identical to #646. A present `extra_loss` that is NaN, infinite, text,
None or negative raises (the pass buys nothing). The brake (`loss_today <= -day_loss`) is untouched.

Tests: `tests/suite/t_autopilot_stake.py` (extra loss lines).

ROADMAP: none
