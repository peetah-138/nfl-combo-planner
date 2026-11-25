# Per-league learning, in shadow (issue #13)

**Section:** Self-tuning (#228) / Fair prices and data / Sizing

Pete's rule is that everything learns per league, not just per sport. This is the shadow-first step: **nothing live
changes and no decision reads any of it**. Once a day (`league_shadow_run`, called from `knob_pass` after the weekly
stepper, due at most every 24 hours, rows kept 180 days) the app works out what each league's own numbers would be
if the league learned for itself and borrowed only what it lacks, and records them beside today's numbers in the new
history table `league_shadow` (ts, league, sport, metric, key, current, shadow, n_own, n_sport, n_all, shares, says).

- **The borrowing rule** (`lgsh_blend`, deterministic and explainable): start from a neutral value, then walk
  all leagues -> the league's sport -> the league; each level moves the value so far toward its own by `n/(n+k)` of the
  gap (n = that level's results, k = `LGSH["k_cut"]` 30 quotes, `k_calib` 300 games, `k_roi` 30 bets). A level with no
  data changes nothing, so a league with no results is exactly its sport and a sport with none is everyone. `shares`
  says how much of the final number each level accounts for ("league 31%, sport 40%, all 22%, start 7%").
- **Metrics:** `cutoff` = each league's combo cut-off by size bucket, today's `_cut_level` (a hard switch at 30 quotes)
  against the blended level (never under 85 or over 110; a borrowed all-leagues level never under the 95% start).
  `calib` = each soccer league's fair-price nudge per chance band: `calib_fair` named by sport only (what a caller that
  passes no ticker gets) against `calib_fair` with the league named (its own record, its sport's behind it; this
  already weights n/(n+300) today, so the row shows only what naming the league changes). `record` = each league's
  settled-bet return over the last 60 days (real combos plus paper/real panel bets, `_tune_items`; mixed-league combos
  left out) shrunk toward 0 through all -> sport -> league: the evidence sizing and the panel's sport order would
  read. Neither reads any league's record today, so `current` is empty; no multiplier or priority is invented here.
- **Report:** `league_shadow_view` (read-only, never raises) is in the Results analytics payload as `league_shadow`
  (latest run, per league: cut-offs, calibration, record, how many rows differ from today; leagues that differ first).
  There is no page card yet; the data is there for one.
- **Never touches:** any cut-off, fair price, stake, size, buy, sell, Pause, the caps, rule 8, the knobs or any
  settings/learning file (`combo_cutoffs.json`, `combo_knobs.json`, `combo_smart.json`...). The run writes only
  `league_shadow`. Later steps (each its own PR, behind a switch): read the blended cut-off, then the league-named
  calibration at every caller, then sizing and the sport order.

Tests: `t_leagueshadow.py` (the blend maths and shares; cut-off, calibration and record rows against hand-worked
numbers and today's real `combo_cutoff`/`calib_fair`; the daily gate and 180-day prune; **identical decisions before
and after a run** for `combo_cutoff`, `calib_fair`, `_size` and `smart_params`, no settings/learning file written, no
decision table touched; an AST check that no decision function mentions the shadow).

ROADMAP: adds "Per-league learning goes live: read the blended cut-off, league-named calibration at every caller, then
sizing and the sport order. Waits on a few weeks of `league_shadow` showing the blended numbers beat today's."
