# Autopilot: bet size and share of cap used (issue #145, step 7)

**Section:** Full auto / Autopilot

Full auto now self-adjusts two more settings in small steps: how big each bet is, and how much of Pete's daily cap it uses.
Two new records in the autopilot registry (`AP_REG`, `FAL_RISKY` = `stake`, `capuse`):

- `stake` (key `stake_mult`): a multiple of today's bet size. 50% to 150%, start 100%, step 5% of the current size, weekly.
- `capuse` (key `cap_use`): the share of Pete's daily cap full auto may use. 50% to 100%, start 100%, step 5 points, weekly.

Pete's limits never move: the $300 bankroll, the $30 daily cap, the $20 daily loss limit and Pause stay his. The Pi never trades.
The cap-use dial can only go down from Pete's cap (never above 100%); a bigger bet is still clamped by what is left of the day's
cap, the free bankroll, what is left before the daily loss limit, the panel budget and the per-bet ceiling (`OWN_MAX`).

- **Tighten fast, loosen slow.** Loosening needs all of: the last 30 days net positive after fees, the soft brake quiet now
  (`caution.level == 0`) with no brake or cautious episode in the last 14 days (`_ap_quiet`, tracked in `lessons["cq"]`; unreadable
  data = not quiet), and the shared gate (70/30 out of sample, bootstrap low end above zero, minimum sample). Tightening is one
  step after any brake week or net-negative evidence, and needs no bootstrap. A tighten step is never auto-reverted.
- **Scheduling.** Stake and cap use never move in the same week; neither moves in the same week as a league-share or bar step
  (`AP_EXCL`); at most 2 autopilot settings change a week overall (`AP_WEEK_MAX`). Size and cap use choose first.
- **Soft brake stays on top.** The live readers (`ap_stake_mult`, `ap_cap_use`) never go above 1 while the brake is cautious, and
  `_fa_sized` never lets a multiple undo the brake's own 50%/25% cut. Unreadable values fail toward 50%.
- **Evidence.** `_stake_load` / `_capuse_load` replay full-auto real settled bets (stake multiple recorded in `sizes`) and the paper
  panel; stake evidence is a linear approximation (profit scales with the multiple).
- **Controls.** Undo, per-setting freeze, the master Autopilot switch and the 2-week hold work as for the other settings; changes
  appear on the Autopilot card in plain words with the dollars behind them. Data starts empty, so nothing loosens until there is evidence.
- **Tests:** `tests/suite/t_autopilot_stake.py` (bounds, step sizes, loosen gates, brake gating, tighten fast, same-week exclusion,
  a revert after a losing week, unreadable data = no change, switch/freeze/undo/hold, exact stakes in `_fa_sized`, cap/bankroll/loss
  limit never exceeded in the buy pass, the card). The older autopilot tests take the two new records out of their way.

ROADMAP: none.
