# Loss-cut clock retry for a stuck combo (issue #396)

**Section:** Selling (auto cash-out when buyers back out, #372)

Pete's decision: a stuck combo **loss cut** (never a profit sale) is also retried on a clock, every 5 minutes
(`LOSSCUT_CLOCK_SECS` 300), as a safety valve for when nothing in the game or the price moves. Until now a failed round
parked the combo until the game, chance, offer or line changed (`combo_wait_why`), and the park is memory-only.

How it works: `combo_wait_start` now also records whether the failed round was a loss cut (`cutting`), the episode's
**first** offer (`first`, kept across rounds) and the clock tries used (`clock_n`). `combo_wait_why(..., kind=why)` grants a
clock try only when nothing else changed, the wait is a loss cut, the sale is not a plan (profit) cash-out, 5 minutes
have passed since the last failed round or clock try, and fewer than **`LOSSCUT_CLOCK_MAX` 6** clock tries were used for
that position (about 30 minutes; after that only a real change reopens it; a sale resets it; a restart clears it).

Every existing bound still applies, and two are added:
- **Pause**: `auto_sell_now` returns first when paused; accepts re-check Pause, Auto cash-out and `can_trade()`.
- **Rule 8**: an unknown outcome is `check`, its wait is dropped and `rfq_unsure` blocks it; the clock never retries it.
- **97% of the FIRST offer, across rounds, for EVERY loss-cut round** (review fix: also a round started by a game or price change, not only the timed retries): a try whose fresh offer is under 97% of the episode's first offer is
  skipped and logged; inside the round the retries' floor is 97% of that same first offer (`_CASH_CTX.first_offer`), so
  the price cannot ratchet down round after round.
- **Smart-sell line**, the cost floor for a profit-taking sale and Never sell at a loss: unchanged.
- **Only the "cut loss" reason**: a profit reason (smart, take profit, lock in, checkpoint, plan) never uses the clock, even when
  its below-cost first offer sold as a guarded stop-loss; that case stays as is until #382 is decided.
- **Purpose re-checked at the clock try**: if the offer is now at or above cost (a profit sale) the try is skipped
  (`stop` "clock retry is for loss cuts only"); profit-reason sales never use the clock.
- **Fail closed**: an unreadable account, a combo gone or reduced, or a damaged wait record means no clock try, logged.
- **Logged**: each clock try's decision line carries `retry_on` ("loss-cut clock retry N of 6 ..."), `clock_retry`, and its
  normal `stop`; skips log why; the cap is logged once per wait.

**Cadence (follow-up, not built):** 5 minutes is the starting value. Pete said "let it tune itself": a follow-up issue records learning the cadence inside a safe band; nothing self-tunes here. Rule 8 and Pause unchanged.

No new automatic path for profit sales; nothing loosened. Tests: `t_losscutclock.py` (paused, unknown outcome, cap reached,
97% guard, profit-reason and profit-reason-stop-loss excluded, unreadable data, line/97% inside the try); `t_combobackout.py`, `t_cashretry.py` unchanged.

ROADMAP: none
