# Cautious default loss cut: 12.5% win chance, on from day one (Pete, option A)

**What changed.** The learned "cut loss" in `exit_policy` used to be off until a league had its own 30+ results. It now starts
ON for every league's combos at a **12.5% win chance** (`LOSS_CUT_DEFAULT`), through `smart_params` (`loss`, `loss_src:
"default"`). Singles are not included (the evidence was combos only).

**Nothing else loosened.** Every guard is unchanged: `stop_loss_leg` (fresh live score, not halftime, at least half the game,
pick under 50% and 20+ points under its pregame chance, 3+ checks over 3+ minutes), a real Kalshi offer, at least 2% of cost
(`CUT_ACCEPT`), at least 97% of the first offer, Pause, and the Auto cash-out and Smart profit-taking switches. No new money
movement: it only changes the starting value from "never".

**Per-league tuning replaces it.** A league's own value (30+ results, `SMART_BOUNDS["loss"]` 10-30%) wins over the default.
`smart_tune` now tunes from 12.5% rather than from "never", and marks `loss_off` if it ever chooses to stop cutting; only that
explicit choice (or self-tuning's smart_loss set off) keeps a league off. A borrowed sport/everyone value is still never used.

**Switch.** `loss_cut_default` (Settings > Cash out, default ON, synced to the Pi). Off = exactly the old behaviour.

**Measurement.** Every firing is logged in the sell log as `loss_cut`: `{src: "default"|"league", cutoff, chance, offer, cost,
legs}` next to the usual `offer`, `cost`, `chance`, `picks`. Re-run the replay (fit first 70% by time, score last 30%,
game-day bootstrap) at about 30 settled combos per league; move the default or switch it off if a winner is cut or the extra
dollars turn negative.

**Evidence is thin (be honest about it).** 131 settled combos, about 13 game days. At 12.5%: 18 cuts, no winner cut, about +$59
versus holding but only about +$10 versus what prod already did. Out of sample: 4 cuts, about +$13 versus prod, bootstrap range
roughly $0 to +$39, so it may be flat. 15% cut a winner. This is a cautious start to be re-measured, not a proven gain.

**Stepper.** Self-tuning (knob) stepping now judges a league from 12.5% (what live really uses) unless the league was explicitly
turned off, and a brake resets a league's loss cut to 12.5%, not to "off". The default is never double-applied: a step or a
league's own value replaces it. The Bet card / loss chip (PR feat/loss-chip) reads the same `smart_params` fields, unchanged.

**Tests.** `tests/suite/t_cutloss_default.py` (default fires under guards; not above 12.5%; not when any guard fails; switch off
restores old behaviour; league value overrides; firing record). `t_cutloss.py`/`t_tune.py`/`t_knoblive.py` updated for the new default.
