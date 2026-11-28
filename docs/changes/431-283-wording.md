# #431 and #283: wording only (no behaviour change)

- #431: the Settings cash-out help text (`HELP` sentence about automatic sales) and the `below_cost` knob line no longer say
  every below-cost sale "loses less than waiting". That is true for the learned loss cut only; the guarded stop-loss
  override is allowed by its game guards (`auto_sell_now`), so both sentences now say which is which. Code unchanged
  (the behaviour question stays in #383).
- #283: the Smart Buy evidence-bar knob (`sb_dial_t`) reads "how clearly more than luck" instead of "standard errors
  from zero". Display text only.
- Audit of the old no-money backlog: #246, #112 (cap message), #453, #353 (client half), #304, #283 (tint, fold, quiet test
  push) were already shipped in #535 #552 #560 #593 #598, so they were not touched again.
