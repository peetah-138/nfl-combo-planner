# Autopilot registry (#144, step 1 of the self-improvement plan)

The paper lessons (#602) are now the first three entries of one **autopilot registry**. Later self-adjusting settings
register in the same place and get the same gate, log, Undo and freeze for free. Behaviour of the three existing settings
is unchanged: same ranges, step sizes (bar 0.5, Smart Buy level 1, game share 2.5 pts), evidence (older 70% picks, newest
30% must agree, net dollars after fees, bootstrap low end above zero, the record's minimum sample) and one step per record
per week. No new money movement; loosening still only walks back toward the start value.

## New

- **One shared gate** `ap_gate`: the #602 evidence check, now the single function every registered setting uses.
- **Master switch**: the Lessons switch is now labelled **Autopilot**. The stored key is still `fa_lessons`, so Pete's current
  setting carries over untouched.
- **Card log**: plain-English lines (what, from -> to, why, dollars behind it). An unreadable record logs
  "no change, not enough evidence" (at most once a day per record).
- **Undo last change** (`autopilot_undo`): puts the last moved setting (a step or an automatic revert) back to its previous
  value and holds that setting for 2 weeks (the hold blocks only loosening); a loosening undo is refused while the brake is cautious, and undoing a revert never restores a looser value; only bets after the undo count toward its next step. Refuses if the value is no
  longer where autopilot left it. Works with Autopilot off.
- **Freeze** (`autopilot_freeze`): per setting (`bar:nba`) or per record (`bar`, `sbev`, `game`). A frozen setting takes no
  new automatic step; a pending step is still judged and reverted.
- **Brake hook** `ap_brake_cautious(st)`: while it is True nothing loosens anywhere (a losing step is also not walked back to a
  looser value until the brake clears); tightening is still allowed. It reads the tripped brake and the soft brake's `caution.level` (> 0), failing closed on unreadable state. The soft brake plugs into this one function; the brake logic itself is not touched.
- **Outer fence** `ap_clamp`: every value is forced inside its bounds (game share also never above the bankroll) right before
  it is saved; a plan outside the bounds is dropped. Bankroll, daily cap, open bets, streak and loss limit are never written.
- **Fail closed**: any error in the look, an unreadable table, NaN, or a malformed saved value means no step.

## Not in this step

Stake size, open-bet count, buy timing, league mix, exit knobs in the same log, and the "at most two settings at once" rule
(only three settings exist, one step each per week as before) come in later steps.
