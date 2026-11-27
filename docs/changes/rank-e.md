# Rank on your own record: Best bets, the flip verdict, the loss-guard judge (issues #243, #204, #265)

**Section:** Build page (Best bets), Fair prices and data, Selling (self-tuning). Display, ranking and the knob judge only: nothing here buys or sells, and no live cut or guard changes.

- **#243 Best bets rank on the calibrated chance.** `best_bets_feed` used to pick the top `BEST_LOOK` (30) candidates by the books' raw
  edge, then size and simulate them on the raw chance. `_best_calibrate(c)` now puts every single and combo on the chance
  corrected by your own record (`calib_fair` per leg, as the panel and the sheet's "on your record" profit do) before that
  cut: the legs' `fair`, `chance`, the ranking return (`ret`), the stake (`_size`) and the exit simulation all read it. A
  combo's return is `pct x corrected chance / books' chance - 1`. A candidate with no edge left on your record is dropped
  (never simulated, still counted in `looked`). The books' chance stays on each row as `chance_book`. An empty record or a
  leg `calib_fair` cannot correct changes nothing. Spreads and totals are untouched (already on `calib_line`). It can only
  reorder or drop a row.
- **#204 The flip verdict is in dollars.** `flip_pick` adds `flip_ev` (stake / combo price x (corrected chance - price - fee),
  fee = the standard taker fee on the combo's price, as Kalshi's combo fee is not verified) before and after, shown as
  "Expected profit at $S, after fees and on your own record: $a -> $b". "Good flip" now also needs expected dollars not to
  fall (more than a cent); a likelier flip whose dollars fall is a Trade-off, or Worse bet when it is not also clearly
  likelier. Without prices the note is as before.
- **#265 The loss-guard judge totals the decision that is running.** `sl_prog`, `sl_drop`, `sl_checks`, `sl_span` and `sl_gap`
  gate both the manual stop-loss switch and the learned loss cut. `knob_judge("sl", ...)` (via `_knob_sl_total`) now judges each
  bet on the learned cut's real-price replay (`_knob_res_replay`) when the cut is on and the bet has a price record, else on the
  switch's replay (`_knob_res_sl`) when the switch is on, else holds it at its settled result; one replay per bet, never both
  added, because both would sell the same bet. `sl_auto` is judged as before. `_sl_tune`, `stoploss_params`,
  `_cut_guard_ts` and every live guard are untouched; these knobs stay in `KNOB_LIVE` (so the stepper's live moves now rest on
  the better judge).
- **Not done / checked:** none of the three was already built. No screenshots: the only visible change is the order of the
  Best bets rows and one added sentence in the flip note (no layout or style change).
- **Tests:** `t_ranke.py` (record flips the ranking and the simulated chance, an edge that exists only on the raw chance is
  dropped, combo return, empty record unchanged, flip dollars and verdict, the judge in all three states); `t_bestbets.py`,
  `t_knobpr567.py`, `t_knobstep.py`, `t_knobreal.py`, `t_knoblive.py`, `t_learnedguards.py` unchanged and passing.
