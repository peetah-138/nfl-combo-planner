# Dismiss a hedge card, and clear Moments rows (display only)

**Section:** Live page (Do now cards, Moments)

Pete: "There's also no way to clear this hedge notification." The Do-now hedge card ("X: lock in $N with a hedge") had
Details and Hedge only. It now has a third thumb-sized (44px) **Dismiss** button.

**What Dismiss does.** `act hedge_dismiss` (web app, same shape as `selfsell`) calls `hedge_dismiss(ticker)` in the engine,
which writes today's `combo_hedge_dismiss.json` (`{day, items: {combo ticker: {locked, cost}}}`; gitignored by
`combo_*.json`). The combo payload carries `hedge_dismissed`, and `live.js` leaves a dismissed hedge out of Do now. The
phone hides the card at once and puts it back with a message if the Mac could not save.

**When it comes back (one simple rule).** `hedge_dismissed(ticker, hg)` stays true only while it is still the same day AND
neither what the hedge locks in nor what it costs has moved by BOTH 20% (`HEDGE_RE_MOVE`) and $0.50 (`HEDGE_RE_MIN`) since
the dismiss. A new day starts over. Any error or unreadable file shows the card (the safe side).

**Moments rows.** The Moments card (the in-app list of live alerts, including hedge advice) had no way to clear a row.
Each row now has a 44px X; the row's text is remembered for the day in this phone's `localStorage` (`cw_mom_x`, capped at
100), so it stays gone after a reload. The lock-screen push itself is the phone's to swipe away.

**Display only.** Nothing places, cancels or blocks an order: the action is not in `ORDER_ACTS`, takes no app lock and has no
Pause check; `hedge_for` (what the Hedge button, the combo page's hedge button and auto-hedge use) is untouched, and sells and
hedges are never blocked. Hedge pushes and auto-hedge behave exactly as before.

**Spinner over the card title (screenshot).** That ring was the pull-to-refresh indicator (`#ptr`, a fixed overlay centred
70px below the top) caught mid-spin while the page reloaded; it is meant to float above content and clears itself. Not a bug,
no change.

**Tests.** `tests/suite/t_hedge_dismiss.py` (engine: dismiss, persists, small wobble stays hidden, 20%+$0.50 move and a new
day bring it back, hedge numbers unchanged, wiring) and `tests/suite/test_hedge_dismiss_ui.py` (page, 390px light and dark:
button size, card hides, exactly one non-order action, reload, Moments clear).
