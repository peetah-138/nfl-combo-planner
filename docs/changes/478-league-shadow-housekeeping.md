# #478 League shadow housekeeping (paper only; Refs #478, #433, #316, #519)

Records and shows only. No buy, sale, size or setting changes; nothing a decision reads is touched.

- `lgsh_rows(now)` now passes `now` to `_tune_items`, so the 60-day window counts back from it (was the real clock).
  (`calibration()` keeps its own hourly cache; its clock is not the shadow's and it is not date-windowed.)
- `_lgsh_n(entry)`: a cut-off entry with no quotes (n=0) but a recorded move (`why`, the borrowed level) weighs as one
  quote in the shadow blend, matching `_cut_own`. The n shown on the row stays the raw count. `_cut_own` itself, and so
  every real cut-off, is unchanged.
- `_tune_items(days, now=None, dedupe=False)`: with `dedupe=True` (the league shadow only) a bets-table row that is the
  same market as a real panel buy already listed is skipped, so it is not counted twice. smart_tune and the others use
  the default (False) and keep their old list.

Checked, already done, nothing to build: #433 (signal_shadow DDL runs once per open database, #534) and #316 items 1
(break episodes filed under the held market) and 2 (BRK_EP drops the oldest). Left alone on purpose: #316 items 3-5
(smart_tune replay counts, `sl_sync` stale mode, cash-out retry floor) change sell behaviour; #519 (needs a bought-as-hedge
marker on the buy path, and a Settings card is Pete's call).

Tests: `t_leagueshadow_housekeeping.py`.
