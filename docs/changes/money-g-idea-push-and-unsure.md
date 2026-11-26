# Buy-idea pushes follow the Smart Buy gate; an unclear order hides an idea only while it may be live (issues #177, #451; #352 already done)

**Section:** Live page (Buy ideas), Smart Buy

- **#177 push gate.** `idea_push_ok(sid)` reads the idea's own stored row and asks `smart_buy_ideas_gate`, the same gate the
  Live page uses, whether it would be shown. The combo push ("Buy idea" and "Better price") and the single-game push
  (`single_pass`) go out only if it says yes. Skip-only: it can only hold a push back; the idea card is stored and shown by
  the page's own rule as before. It fails closed (no stored row, any error: no push). Effects to know: a push is only tried when the idea is first seen or improves 5 points, at which moment the shadow has
  no verdict on that exact quote yet, so an under-fair combo idea (under 100% of fair, possible when the league's cut-off is
  below 100%) gets no push at all (it is not deferred; the card still shows once the shadow clears it). A gated idea also
  skips the Notifier's live "idea" event. With Smart Buy off, pregame ideas are pushed as before (in-play ones never reach
  a push, #341).
- **#451 unclear order.** A buy whose answer was lost or unclear (single `check`, combo `check`, the phone's lost reply,
  sent by the page as `why: 'unsure'`) is written with `idea_mark_bought(..., unsure=True)` / `idea_dismiss(bought='unsure')`.
  Such an idea is hidden only for `IDEA_UNSURE_SECS` (2 hours, the span of the order-unsure block; the buy is fill-now-or-
  cancel), and comes back only if the Mac has a read of what you hold built after the unclear order and no older than
  `IDEA_VIEW_FRESH_SECS` (10 min; `MINE['view']` with `MINE['view_at']`, singles and combos, no error) and you don't hold it; a fill shows as held and keeps it off. A definite buy (`ok`) still hides it `IDEA_BOUGHT_DAYS` (3 days)
  and always overrides an unclear mark; an unclear mark never softens a definite one. The order-unsure block on the market
  (`order_unsure`, `rfq_unsure`) and the one-order-per-tap guard are untouched, so no order is ever resent.
- **#352** was already fixed in #357 (#348): `smart_buy_ideas_gate` judges in-play ideas whatever the switch
  (`t_comeback.py`: "even with Smart Buy switched off"). Nothing to do.
- Tests: `t_money_g.py` (push gate for combos and singles, the single path end to end, every unclear-order case).
