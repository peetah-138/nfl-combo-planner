# Combo Buy re-checks the page's legs (issue #203)

**Section:** Build page (Buy), rule 7

Guard only; nothing new is bought and no price, size or cap changes. The web app's Buy sends the legs it shows (it
already did, since #347). The Mac now checks them in `accept_offer(i, expect_legs=...)` (`buy_legs_refusal`): they must
equal BOTH the stored offer's legs and the combo now on that card (`CTX["combos"][i-1]`), compared as sets of tickers,
exactly as `quote` checks the card. Any mismatch sends nothing, keeps the offer, prints
`buy combo N: refused before the accept (reason); page=... offer=... card=...`, and answers with "That price was for a
different combo, or this page is out of date. Reload the page..." (`legs_mismatch`), so a combo-changing path that forgets
to pop its offer can no longer buy legs other than the ones on screen.

**Older pages:** the page is served by the same Mac, so only a tab left open across an update lacks legs. A Buy with no
legs (or a non-list) is now REFUSED (fail closed; it used to skip the check). The tab shows the reload message. Open product
question: if stale tabs blocking one buy is not acceptable, the alternative is to allow legs-less buys (the old behaviour).

The panel, killer and other callers of `accept_offer` pass no `expect_legs` and are unchanged.
Test: `t_buy_legs_203.py` (match, no legs, other legs, flip without popping the offer both ways, no card).
