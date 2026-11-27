# The loss guards are judged on the decisions that really run (issue #265)

**Section:** Selling (self-tuning, the loss guards). **Money path: needs an independent Opus review before merge.** Pete chose
the full change (not the "worse of two" shortcut) after the Opus review of #576 held this out.

`sl_prog`, `sl_drop`, `sl_checks`, `sl_span` and `sl_gap` gate two decisions: the manual stop-loss switch and smart sell's
learned loss cut (`stoploss_params`, `sl_confirm_params`, `_cut_guard_ts`). The weekly stepper judged them on the switch's
replay alone (`_sl_replay`), so a step could be justified by a feature that is off and move a number a live feature uses.

## What changed

- `knob_judge("sl", ...)` for those five knobs now calls `_knob_res_loss` per bet, on `knob_loss_drivers(vals)`:
  the **learned cut** runs when smart sell is on and the group has a cut-off (the cautious default 12.5% included); the
  **stop-loss** runs under Settings > Selling at a loss = Allow, or under Let it tune itself when the group's own
  `sl_auto` is on. Cut only: the cut's real-record replay (`_knob_replay_at`, i.e. `_replay_real`, the guards gating its
  loss cut). Stop-loss only: `_sl_replay`. Both: whichever would have sold **first** on that bet (on a tie the lower
  result), because both would sell the same bet once. Neither: the bet's settled result, so the step gains nothing.
- Net dollars after fees: the replays' sale prices are Kalshi's offers (or the estimate, with the 3% haircut on a loosening
  step, #285) against what the bet cost; singles are not in this judge (loss guards are combos).
- Out of sample: unchanged `knob_evidence` (only bets after the group's last step, step picked on the older 70%, the newest
  30% must also gain). Brake, one mover per value, borrowed values only stricter, the start while braked: unchanged.
- New for a **loosened** loss guard (`sl_prog` or `sl_drop` below the live value; the counts can't go below their start): the
  bootstrap range of its net gain must be above zero too (the same check `sl_feed_age` and `brk_*` already had).
  A tightening step keeps the ordinary bar.
- Fail closed: no price record or damaged evidence for a bet raises `KnobJudgeUnreadable`; the stepper marks that knob
  `unread` (logged, nothing moves) and carries on with the league's other knobs.
- Untouched: `sl_auto`'s own judge, `_sl_tune` and everything smart_tune does with "Let smart sell tune its own numbers" OFF
  (the old numbers exactly), the guards themselves, Pause, caps, rule 8. No new automatic money movement: it only changes
  which step the existing self-tuning may take. The registry text for the five knobs now names the new judge.

## Which live numbers can move, and by how much

Only these, only one step per league per weekly run, and only when the bar is cleared; bounds are the registry's:
`sl_prog` 35-90% of the game (step 5 points, start 50%), `sl_drop` 10-45 points (step 5, start 20), `sl_checks` 3-6 (step 1,
start 3), `sl_span` 180-600 s (step 30), `sl_gap` 120-300 s (step 30). The counts never loosen below their start. A league
borrows only the stricter value of its sport's or everyone's.

What moves versus the old judge (the old one's answer vs the new one's, dollars on one recorded game, stake $10 payout $20,
a pick falling from 60% to 10% late in Q3; reproduced in `t_lossguard265.py`):

| Settings | Step | Old judge | New judge |
|---|---|---|---|
| Let it tune itself, sl_auto off (a cut-off set) | `sl_prog` 50 to 55% | -0.98 | 0.00 (the cut is unmoved) |
| same | `sl_drop` 20 to 15 pts (a LOOSENING step) | +0.66 | 0.00 (no stop-loss runs) |
| same | `sl_span` 180 to 210 s | -0.98 | -1.64 (the cut would not have confirmed) |
| Allow (guarded) | `sl_prog` 50 to 55% | -0.98 | -0.98 |
| Allow (guarded) | `sl_drop` 20 to 15 pts | +0.66 | +0.64 |

So for the common setting (the cut on, the stop-loss off) the old judge could have loosened `sl_drop` on a feature that
was off; the new one cannot. Steps the old judge would have taken for stop-loss reasons stop; steps that matter to the cut
(and were invisible before) can now qualify. Under Allow the answers are close, because the stop-loss sells first.

Honest limit: Pete's real price history is not on this machine (it lives in the watcher's database), so there is no
replay over it here; the table is a recorded-game fixture plus the random-state tests. The first weekly run after release
logs every guard step it considers in `knob_shadow` (status `qualifies`, `vetoed`, `below`, `unread`), so the effect on the
real record is readable before a second step is taken.

## Tests

`t_lossguard265.py` (drivers per setting; the old vs new numbers above; earliest sale, tie, one rides on, neither;
neither runs = no gain; `sl_auto` judge unchanged; unreadable record = no step and the other knobs still judged; the five
use the new judge; `_sl_tune` untouched). Existing `t_knobpr567.py`, `t_knobstep.py`, `t_knoblive.py`, `t_knobreal.py`,
`t_knobs.py` and `t_stoploss.py` pass unchanged.
