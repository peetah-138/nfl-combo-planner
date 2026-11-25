# Loss wording (#431, words only)

Pete (2026-11-24): the "never sell at a loss" copy overstated the guarded stop-loss. It said selling below cost happens
when selling now loses less than waiting; the stop-loss is gated by game-state guards, not a strict comparison, so the
copy now says what happens: auto-sell never sells below cost, except that a guarded stop-loss may sell below cost when
the app judges that selling now loses less than waiting (never under 97% of its first offer or the smart-sell floor).

- Changed text only: the auto cash-out explainer and the `below_cost` knob description (`nfl_combo_planner.py`), and the
  "Allow (guarded)" line in Settings › Cash out & hedging › Selling at a loss (`watcher/spa/settings.js`).
- The three choice labels, the Never and Let-it-tune-itself lines and all decision code and numbers are unchanged.
- Tests updated for the new strings: `t_sellwording.py`, `test_slmode_ui.py`.
- Follow-up still open for Pete (#383 item 2): whether to make the stop-loss compare against waiting in code.
