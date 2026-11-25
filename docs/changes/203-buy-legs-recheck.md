# Combo Buy re-checks the page's legs (issue #203)

**Section:** Build page (Buy), rule 7

Guard only; nothing new is bought and no price, size or cap changes. The web app's Buy sends the legs it shows (it
already did, since #347). The Mac now checks them in `accept_offer(i, expect_legs=...)` (`buy_legs_refusal`): they must
equal BOTH the stored offer's legs and the combo now on that card (`CTX["combos"][i-1]`), compared as sets of tickers,
exactly as `quote` checks the card. Any mismatch sends nothing, keeps the offer, prints
`buy combo N: refused before the accept (reason); page=... offer=... card=...`, and answers with "That price was for a
different combo, or this page is out of date. Reload the page..." (`legs_mismatch`), so a combo-changing path that forgets
to pop its offer can no longer buy legs other than the ones on screen.

**Pages that send no legs:** the idea Buy used to send none, and a stale tab may too. They are NOT refused for missing legs
(that would have blocked every multi-game idea Buy). They are held to offer = card, so a combo that changed under its offer is
still refused. The idea price (`a: "idea"`) now returns the combo's `legs`; `ideas.js` keeps them (`S.ideaq[id].legs`) and sends
them with Buy, so idea Buys are checked against the page's own legs too. No open product question.

The panel, killer and other callers of `accept_offer` pass no `expect_legs` and are unchanged.
Tests: `t_buy_legs_203.py` (engine) and `test_buy_legs_203.py` (real `/app/api/act`: idea Buy with and without legs, other legs, flip without popping the offer, Build card, long shot).
