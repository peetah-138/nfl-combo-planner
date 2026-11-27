# Rank on your own record: Best bets and the flip verdict (issues #243, #204; #265 held)

**Section:** Build page (Best bets), Fair prices and data, Selling (self-tuning). Display and ranking only: nothing here buys or sells, and no live cut or guard changes.

- **#243 Best bets rank on the calibrated chance.** `best_bets_feed` used to pick the top `BEST_LOOK` (30) candidates by the books' raw
  edge, then size and simulate them on the raw chance. `_best_calibrate(c)` now puts every single and combo on the chance
  corrected by your own record (`calib_fair` per leg, as the panel and the sheet's "on your record" profit do) before that
  cut: the legs' `fair`, `chance`, the ranking return (`ret`), the stake (`_size`) and the exit simulation all read it. A
  combo's return is `pct x corrected chance / books' chance - 1`. A candidate with no edge left on your record, or under the single bar
  (`SINGLE_MIN_EDGE` 2.5c after fee and 4%, as in `single_candidates`), is dropped (never simulated, still counted in `looked`). The books' chance stays on each row as `chance_book`. An empty record or a
  leg `calib_fair` cannot correct changes nothing. Spreads and totals are untouched (already on `calib_line`). It can only
  reorder or drop a row.
- **#204 The flip verdict is in dollars.** `flip_pick` adds `flip_ev` (stake / combo price x (corrected chance - price - fee),
  fee = the standard taker fee on the combo's price, as Kalshi's combo fee is not verified) before and after, shown as
  "Expected profit at $S, after fees and on your own record: $a -> $b". "Good flip" now also needs expected dollars not to
  fall (more than a cent); a likelier flip whose dollars fall is a Trade-off, or Worse bet when it is not also clearly
  likelier. Without prices the note is as before.
- **#265 is held, not shipped (pending Pete's sign-off).** The loss guards `sl_prog`, `sl_drop`, `sl_checks`, `sl_span` and
  `sl_gap` gate both the manual stop-loss switch and the learned loss cut, but `knob_judge("sl", ...)` replays only the
  switch. A first version that judged each bet on the cut's replay when the cut is on was taken out: those knobs are in
  `KNOB_LIVE` and live self-tuning is on, so it would change live loss numbers, and with the cut and `sl_auto` both on it
  would look only at the cut and could let through a step that loses on the switch replay. Nothing about the judge, the
  steppers, `_sl_tune` or any live guard changes in this PR. Option for later: judge a step on the WORSE of the two replays
  (the switch's and the cut's, each only when that feature is on) so a step must not lose on either.
- **Not done / checked:** none of the three was already built. No screenshots: the only visible change is the order of the
  Best bets rows and one added sentence in the flip note (no layout or style change).
- **Tests:** `t_ranke.py` (record flips the ranking and the simulated chance, an edge that exists only on the raw chance is
  dropped, combo return, empty record unchanged, flip dollars and verdict); `t_bestbets.py`,
  the knob tests are unchanged and passing.
