# Release 507 review fixes (Pete's decisions A-D, items E1-E7)

Money rules are already folded into CLAUDE.md (Flexible sell price, hard rule 2, scope of the legs check, onclick note).
What is left to fold:

- **Profit floor (A).** `flex_decide` refuses a retry of an automatic profit sale under 95% of cost net of the selling fee
  (`FLEX_COST_SHARE`), unless it is a real loss cut. Test: `t_flexcostfloor.py`; `t_flexsell.py` updated.
- **Fee-only loss is a stop-loss (E3).** Gross at or above cost but net below, with a guarded stop-loss ready: tagged
  `stop_loss` and `fee_loss`, purpose "cut a loss", message says it was a small loss after Kalshi's selling fee.
- **Back-outs keep the 97% guard (E1).** `combo_wait_start` now stores `cutting` for a guarded stop-loss too (clock retries
  still only for the "cut loss" reason). Tests in `t_combofee.py`.
- **Tests (E4, E6).** `t_newkeys.py` documents `combo_sell_fee` as Mac-file-only; `t_neverloss.py` marks its stub.
- **Screens (C).** Plain-English Settings text (guards line with league, 95% of cost, ~$800/day smart-sell-more limit, paused
  until date), "before fees" wording on the stake and slip notes, 44px "more" summary row, chart "Starts at ..." note.
