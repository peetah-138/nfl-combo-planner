#### Full auto: the losing-streak brake becomes a confidence level (issue #144; Pete: "It should just adjust.")

**Section:** "Full auto: the real master switch" (replaces its streak-brake paragraph; the daily loss limit paragraph stays)

A losing streak no longer stops full auto. It stays ON and steps down a level; it steps back up on wins or calm. Only the real
master switch turns it off. It can only ever be more careful than the saved limits, never looser, and it adds no money movement.

**Levels** (`FA_LADDER`, one row per level; a later adjustable setting plugs in by adding a key to every row and one `_fa_knob` reader):
- Level 0, Normal: the saved settings exactly (the ceiling; nothing goes above it).
- Level 1, Cautious 50%: bet size 50%, daily cap 50%, combos must clear their league cut-off by 0.5 more points.
- Level 2, Cautious 25% (the floor): size 25%, cap 25%, +1.0 point. Never zero, never off.
Sizes round down to the cent, never under the $2 minimum and never above the normal stake (scaled stakes go through the
existing `stakes=` argument of `panel_approve` / `panel_add`). The bar is a filter after the lessons filter, combos only (singles
and spreads/totals are not touched by the bar, only by size and cap); an error in it approves nothing.

**Moves** (`_fa_caution_eval`, pure, saved by the pass in `combo_fullauto.json` as `caution`):
- Down: normal goes cautious after the streak limit in a row (default 4); while cautious, 2 more losses in a row step down one level.
- Up: 2 winning (non-loss) full-auto bets in a row step up one level (only the 2 needed are used up), or 3 days with no loss since
  the last change step up one level. Each step is logged in the history in plain words with its reason.
- Manual reset ("Back to normal now") returns to normal immediately and resets the loss count.
- An older saved streak pause is migrated to the lowest level (25%), with a plain card note ("Brake from before this update: tap Back to normal now, or it eases back by itself"). It never buys silently at 50%.
- Settled bets are replayed in the order the money moved (settle time, else buy time), each bet counted exactly once by its id (a bounded list is saved), so a first-bought bet that settles last still counts. Settled bets are replayed oldest first, one at a time, so a batch settling between passes gives the same level as one at a time. A push (exactly $0) is neutral: not a win, not a loss, no recovery progress.

**Unchanged:** the $20 daily loss limit still pauses until the next panel day, with its "Paused itself" card line. Pause, the Pi,
rule 8, the paper gate and every cap are untouched.

**The card** shows "Normal" or "Cautious (50%)" with the reason, the effect, and recovery progress (wins so far of 2, about N calm
days left); the Lessons blurb says the confidence level may step down and back up but never above your settings.

**My picks, easy to change in `FA_LADDER` / `FA_CAUTION`:** 50% and 25%, +0.5 point per level, 2 wins to step up, 3 calm days, 2
losses to step down. Tests: `t_fullauto.py` (trip is cautious not off, scaling, recovery, floor, never above normal, calm days,
manual reset, daily loss limit, legacy pause, master switch), `t_fa_lessons.py` unchanged and passing.
