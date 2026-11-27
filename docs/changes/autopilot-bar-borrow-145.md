# Autopilot bar borrow for thin leagues (#145, step 5 of the self-improvement plan)

A league with too little shadow data for its own buy-bar step can now **borrow the other leagues' record** to step its combo
bar. It rides the autopilot registry (#607) unchanged: the same shared gate (`ap_gate`), card log, Undo, freeze and brake hook.

## Rules

- **Who borrows**: a league whose own record is below the bar record's minimum sample (`LGSH["k_roi"]`). Its evidence is the
  pooled rows of every other league, judged by the same gate: the older 70% picks the step, the newest 30% must agree, net
  dollars after fees, bootstrap low end above zero. Negative or thin group evidence means no step.
- **Skip-only**: same 0.5 point step, range 0 to +5. A borrowed step can only tighten, so full auto skips more bets and never
  buys more. A borrowed bar is never loosened by borrowed evidence; a bad step is walked back by the existing weekly
  re-score (a loss, or too few bets in two weeks, reverts it). Once the league has its own data it moves by its own record.
- **Exploration floor**: shadow rows keep being logged against the live cut-off (not the borrowed bar), so a thin league keeps
  collecting the data it needs. The +5 ceiling and one step a record per week still apply.
- **Brake priority**: no loosening while cautious (a lost borrowed step is not reverted to looser until the brake clears);
  tightening is still allowed. Freeze (per league or the whole `bar` record), Undo (restores the value, holds it 2 weeks) and
  the master Autopilot switch all apply.
- **Fail closed**: unreadable data, NaN or any error means no step.
- Card log wording says the step used the other leagues' record. No new automatic money movement.

Tests: `tests/suite/t_autopilot_borrow.py`.
