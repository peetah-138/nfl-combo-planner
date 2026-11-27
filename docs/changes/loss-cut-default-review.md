# Loss-cut default: review fixes (#556 follow-up)

- **Pre-marker "never cut" leagues stay off.** A league with 30+ results and no loss cut, with no `loss_off` key at all (tuned
  to "never" before the marker existed), is now treated as having chosen "never cut", so the 12.5% default does not override it.
  Read-time only, nothing is rewritten. An explicit `loss_off: false` or a league under 30 results still gets 12.5%.
- **Fails closed.** If `_loss_cut_chosen_off` cannot read the settings it now returns True (no default cut), not False.
- **Doc fix.** `loss-cut-default.md` said a brake resets a league to 12.5%; the code applies no default while braked.
- Tests: `tests/suite/t_cutloss_default_legacy.py`; `t_cutloss_default.py` untouched-league case now uses under 30 results.
