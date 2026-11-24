# "Never sell at a loss": copy now matches Pete's rule (issues #382, #383)

**Section:** Selling

Pete's rule (2026-11-23): auto-sell never sells below what you paid, except when selling now loses less than waiting
(the learned loss cut, or the guarded stop-loss). A sale that was a profit never retries below cost; a loss cut never
retries under 97% of its first offer (`CASH_SLIP`, kept as is). Checked against the code: it already behaves this way
(`auto_sell_now`, `_accept_with_retries`, `smart_sell_singles`), so this PR changes WORDING ONLY: the auto cash-out
explainer, the `below_cost` knob description and the stale comment above the stop-loss guard. No decision logic, no
setting label and no number changed. The Never setting still also turns the loss cut and stop-loss off (its Settings
text already says so).

Open, not changed here (money decisions): a combo's below-cost first offer on a profit reason sells as a stop-loss
whenever the guards hold, without asking whether a profit is still possible; combo cost floors ignore Kalshi's fee;
the 60-minute back-off also skips the auto-hedge for a live loss cut (#383 items 2 to 6).

Test: `t_sellwording.py`.

ROADMAP: none
