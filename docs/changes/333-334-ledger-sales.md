# Ledger reads V2 sale fills as sales; smart sell skips sub-contract leftovers and backs off failures (issues #333, #334)

**Section:** Results page (Profit scoreboard) for #333; Selling (smart sell everywhere) for #334

**Sales in V2 fills (#333).** Kalshi reports a sale at the YES price with the side flipped (selling YES shows as
"sell no", as combo cash-outs always did), which `_single_ledger` booked as a second buy: the sale's dollars went into
cost, none into back, and a sold bet that hadn't settled was missing. `fill_yes_delta(f, pos, n)` now treats every
`action: sell` as closing what is held (towards zero; any excess opens the other side, as Kalshi nets); with nothing
held, or no legacy `action`, it uses the YES-book direction (`book_side` bid/ask, `outcome_side`), else the legacy
side. Buys keep their side (buying NO while holding YES = closing by the opposite side). `ledger_note` now compares
each recomputed row with the saved one (`_ledger_same`, money to the cent) and writes only rows that differ, so rows
written wrong before are put right on the next account read (the update restarts the watcher) and unchanged rows are
never rewritten, even after a restart. Existing guards are kept (fewer fills than the saved row, settlement-only rows,
rows closed over 180 days ago are not rewritten). Read-only: no new Kalshi calls, nothing bought or sold. Panel items
already settled keep the `pl_real` they got (it was mostly `None`, since the wrong cost didn't match the stake).
Test: `t_ledgersales.py` (A, B).

**Leftovers and repeated failures (#334).** Smart sell for singles only offers whole contracts and never under
`SELL_MIN_CONTRACTS` (1, Kalshi's minimum): a 0.92 leftover is skipped and logged once ("under one contract"), never
sent (it was retried every ~8 s for 90 minutes). After `SELL_FAIL_MAX` (3) failed identical sales in a row (same
market, side and whole-contract size; a definite "failed", not "check") it waits 10 minutes, then an hour after every
further failure (`SELL_FAIL_WAITS`, `SELL_FAILS`, `sell_backoff_left`/`sell_backoff_note`; this process only, a restart
starts over), logged once per wait (decision log + console). A sale that goes through, a "check", or a different size
resets it. It only ever tries less: Pause, the daily cap, every guard and rule 8 are unchanged. Test: `t_ledgersales.py` (C).

ROADMAP: none
