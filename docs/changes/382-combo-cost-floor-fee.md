# Combo cost floor counts Kalshi's selling fee (issues #382, #383)

**Section:** Selling

**UNCONFIRMED ASSUMPTION, stated plainly:** that Kalshi's combo cash-out selling fee equals the single-market taker fee
(`single_fee`) has NOT been confirmed against a real combo sale. Pete approved building on it, so it is on by default, but
it sits behind the switch `combo_sell_fee` (config, default `True`); set it to `False` and the cost floor judges the
gross offer exactly as before. Also: an offer with no readable `contracts` falls back to the old gross comparison and the
decision log says so (`fee_note`), so it can never block every auto cash-out; the log carries `net` next to the gross
`offer`; and a sale whose gross offer is above cost is never labelled a loss cut or stop-loss (it is "take a profit").

The cost floor on automatic combo cash-outs now counts Kalshi's selling fee, the way singles already do
(`single_fee`, rounded up to the cent per order). New `combo_sale_net(offer)` = offer minus `n * single_fee(offer / n, n)`.
Before, an offer exactly at cost passed every cost floor and still lost the fee. Now:
- the **below-cost test itself** (`below` in `auto_sell_now`) now compares the offer's net of the fee with cost, as singles
  do. An offer between cost and cost + fee used to count as "not below", so a profit sale took it and lost the fee; now it
  follows the existing below-cost rules unchanged (a cut-loss reason or a ready stop-loss sells it as a loss cut; a profit
  reason without a ready stop-loss is skipped, "below what you paid", with `net` logged; Never sell at a loss skips it).
  So a better offer can never be refused where a worse one sells. This changes the INPUT to the existing stop-loss-on-a-
  profit-reason rule (a few cents more offers count as below cost), not the rule;
- a **retry's fresh offer** must clear the same floor (`_accept_with_retries`: Never sell at a loss, and every
  profit-taking sale, `stop` "offer too low");
- an offer with no readable contracts falls back to the old gross comparison (logged as `fee_note`), never a block.

This is close to a tightening (see the switch above): nothing sells that did not before, and it only stops sales worth less than cost after the fee.
Loss cuts (offer already below cost) keep their own rules (97% of the first offer, the smart-sell line). Deliberately
**not changed** (still open in #382/#383): a profit reason's below-cost first offer sold as a stop-loss, your own Cash out
tap's 97% retry, the setting wording. Pause, caps, rule 8 untouched. Test: `t_combofee.py`.

ROADMAP: none
