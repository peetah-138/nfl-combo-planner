# Money batch E: real-offer card, veto flapping, per-call fresh read (#525, #475, #536/#450)

**Section:** Money path (guards only; no new automatic money movement; Rule 8, Pause, the account check and the cost check are unchanged)

- **#525 (card wording only).** Smart sell's card said "holding off asking Kalshi" while a combo was backing off, even when Lock in
  (armed: the peak reached its arm line) or a guarded stop-loss could still ask Kalshi, because auto cash-out sends those two asks past the
  back-off. The card now treats an armed Lock in like a ready stop-loss. Display only: `real_ask_gate(readonly=True)` still changes nothing.
  The "over the bar but under cost" test in `t_realoffer_227.py` now also checks the decision log says "below what you paid", so it is the
  cost rule that stops the sale, not the bar (it fails when that rule is removed). Item 3 of the issue (no hourly cap on exempt asks) is left as
  it is: same 60 s cadence as before #514, a cap on a stop-loss would delay a loss cut; open for a decision.
- **#475.** `mkt_learn`'s recency check (the newest 30% of a group's markets) now has to clear zero by `MKT["hold_se"]` (1.0) standard errors of
  that slice, not just be above zero, and a group that was vetoed stays vetoed until the check has held on every run for `MKT["hold_wait"]`
  (2 hours). So a `hold_gain` hovering near zero no longer flips the weight, and `longshot_leg_fair` with it, from one run to the next. Only
  stricter than before: a weight the old rule vetoed is never given. The history (`MKT_VETO`) is in memory; after a restart a group that was never
  vetoed is judged by the margin alone with no wait. The Settings switch `mkt_hold` off still means the in-sample bar alone. Test: `t_mkthold.py` section 8.
- **#536 (follow-up to #450).** The must-be-fresh flag for the hub's `account` read is now an argument of that one call
  (`_fetch_account(fresh=True)`), not the module global `ACCT_FRESH`, so a read another thread starts or finishes in between can no longer clear a
  guard's flag. Behaviour is otherwise as in #533. Test: `t_money_d.py`. The sibling flag `ACCT_HUB_STALE` is still a module global (it only decides
  whether a held-back copy is cached; guard reads never use the cache): left alone, noted for review.
