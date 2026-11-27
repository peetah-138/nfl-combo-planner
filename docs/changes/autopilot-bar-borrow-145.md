# Autopilot bar borrow for thin leagues (#145, step 5 of the self-improvement plan)

A league with too little shadow data for its own buy-bar step can now **borrow the other leagues' record** to step its combo
bar. It rides the autopilot registry (#607) unchanged: the same shared gate (`ap_gate`), card log, Undo, freeze and brake hook.

## Rules

- **Who borrows**: a league whose own record is below the bar record's minimum sample (`LGSH["k_roi"]`). Its evidence is the
  pooled rows of every other league, judged by the same gate: the older 70% picks the step, the newest 30% must agree, net
  dollars after fees, bootstrap low end above zero. Negative or thin group evidence means no step.
- **Capped, two-way, never stuck**: same 0.5 point steps. A borrowed bar tightens only up to +1.5 in all (tighten-fast), skipping
  more bets, never buying more. It eases back one step toward the start when the group's evidence supports looser (same gate), or
  after four weeks with too little own data to confirm it. Easing back is blocked by the brake, a hold or a freeze, like any
  loosening. A bad step is also reverted by the weekly re-score (a loss, or too few bets in two weeks). With its own data the
  league moves by its own record.
- **Scoped hold**: a borrowed step still being judged holds only its own league; other leagues' steps are not blocked.
- **Exploration floor**: shadow rows keep being logged against the live cut-off (not the borrowed bar), so a thin league keeps
  collecting the data it needs. The +5 ceiling and one step a record per week still apply.
- **Brake priority**: no loosening while cautious (a lost borrowed step is not reverted to looser until the brake clears);
  tightening is still allowed. Freeze (per league or the whole `bar` record), Undo (restores the value, holds it 2 weeks) and
  the master Autopilot switch all apply.
- **Fail closed**: unreadable data, NaN or any error means no step.
- Card log wording says the step used the other leagues' record. No new automatic money movement.

Tests: `tests/suite/t_autopilot_borrow.py`.
