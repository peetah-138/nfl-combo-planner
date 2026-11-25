# Weigh a hedge before skipping a below-cost sale: paper first (issue #312)

**Section:** Selling (auto cash-out, auto-hedge)

When auto cash-out skips a sale because the offer is under what the bet cost ("below what you paid", the combo path in
`auto_sell_now` and the single-bet path in `smart_sell_singles`), `hedge_skip_note` records, in the new bounded
`hedge_skip` table, the numbers of THAT moment (never a stale reference): what selling right now returns net of fees
(`whole`), what the position cost and pays, and for combos what a hedge on the other side of the game would lock in
at the board price (`hedge_for`'s own sums, fee included: `hcost`, `locked`; not the order-book ask a live hedge would use, and
not for a part-hedged combo) and whether that lock-in is at least `hedge_lock_cost` x cost (`hok`; the cap, spread, score and
confirmation guards are NOT applied, so it is not proof auto-hedge would have fired). One row per bet per 10 minutes; 60 days and 20000 rows at most.
`hedge_skip_report(days)` returns aggregates only (no tickers): how many below-cost sales were skipped, selling-now and
hedge dollars against cost, and, for bets that have settled (ledger outcome), what holding actually paid beside the same
bets' sell and hedge figures (`hedge_beats_hold`, `sell_beats_hold`, against holding to settlement). Each bet counts once, at its latest recorded moment.

**Paper only.** It is write-only: nothing decides from it, it sends no order, no hedge is added, the skip still
happens exactly as before, errors are swallowed (a broken recorder changes nothing), and it makes no request of its own
(board prices already in memory). Rule 8, Pause, rule 7, "Never sells below what you paid" and every hedge guard are
untouched. Turning it into a live "hedge instead of skip" needs the report to show a hedge beating both selling and
holding on settled bets first, and then Pete's opt-in (an automatic buy).

Test: `t_hedge_skip.py`.
