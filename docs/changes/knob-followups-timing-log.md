# Buy-timing log: three correctness fixes (#640, part of #649)

**Section:** Results / buy timing (record only)

`timing_log_pass` now refreshes a row when its pl, fees or stake changes (not only result, close, pl_real, clv); a ticker bought
twice has its ledger fees split by stake instead of counted on both rows; a buy after the kickoff counts as live even without the
live flag (so it gets no close and no CLV). Record only: nothing here prices, buys, sells or sizes.

Checked and not changed: #299, #300 (money-path wording or design for Pete), #301, #302, #309 (relabelling a knob's borrow mode
could loosen it), #316 items 1-2 (already fixed), 3-5, #645 slot pre-filter (already sizes by room), #645/#648 (own learned
records may legitimately sit below the defaults; needs Pete), #647 and the odds.lock part of #649.

ROADMAP: none
