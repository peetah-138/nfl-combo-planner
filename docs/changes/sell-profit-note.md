# Sale alerts say the profit or loss; trade alerts open that combo or bet (issues #390, #391)

**Section:** Selling (cash-out and single-sale messages, `sale_result_note`), Notifications (`trade_link`), Live page (`betFromHash`)

Stacked on #385 (combo sell back-out). Wording and links only: no change to selling logic, prices, thresholds,
retries or triggers.

## 1. Sale alerts say how it went against what was paid (#390)

Pete: "It would be nice if this would tell me how much profit it was instead of what it sold for. I can't remember
what we paid for it." One helper, `sale_result_note(got, cost, cutting=False)`, builds the phrase for every success
message, from the cost the app already tracks (the combo's `cost` = what was paid plus buy fees, the same number
Results and the sell sheet use; a single's `cost`, scaled to the share sold):

- profit: `+$1.42 profit (paid $2.19)`; loss: `-$0.80 loss (paid $4.40)`, plus `, cut to limit the damage` when an
  automatic loss cut or stop-loss made the sale (`_CASH_CTX.cutting`, `why == "cut loss"`); even to the cent:
  `broke even (paid $4.40)`. Compared after rounding to cents, so the sign never contradicts the dollars shown.
- cost missing, zero, negative or not a number: `(cost unknown)` and the old wording. No number is ever invented.
- the proceeds figure stays. Combo proceeds are the offer (no sale fee); a single's are after Kalshi's sale fee.

Messages changed:

| Where | Before | After |
|---|---|---|
| Combo cash-out, yours or automatic (`_accept_with_retries`) | `✅ Combo 5 cashed out for about $3.61.` | `✅ Combo 5 cashed out for about $3.61: +$1.42 profit (paid $2.19).` / `... $3.60: -$0.80 loss (paid $4.40).` (`, cut to limit the damage` on an automatic cut) |
| Automatic single sale (`smart_sell_singles`) | `<lead>: sold Lakers to win for about $5.70 (paid $5).` | `<lead>: sold Lakers to win for about $5.70: +$0.70 profit (paid $5).` |
| Your single Sell (`single_sell`) | `✅ Sold 10 at 60¢ or better: about $5.70 back after Kalshi's fee.` | `... back after Kalshi's fee: +$0.70 profit (paid $5).` |

Unknown cost keeps the old wording with ` (cost unknown)`. Hedges and standing orders are buys: they have no sale
wording, so there is nothing to compare and they are unchanged.

## 2. Tapping a trade alert opens that combo or bet (#391)

Pete: "it would be nice if these push notifications would let me tap into them and they would take me to the
specific combo or bet instead of just to the app itself."

- `trade_link(E, msg)` = `combo_link` (`/#c=<ticker>`, existing) or the new `single_link` (`/#b=<ticker>`, the bet
  whose label the text names; two different bets named gives no link). Used by `Notifier.add`, the engine's
  `E.notify`, the panel and killer-deal pushes. The link is passed to `push`, which already adds the ntfy `Click`
  header (and the Web Push url) only when an address is configured: `hub_base(conf)` from the app's own settings,
  never hard-coded. No address configured means no `Click` header, exactly as before.
- The link holds only the market ticker (URL-safe characters only): no keys, tokens, topic or account ids. Opening
  it signs nobody in; the app still asks for its passcode.
- The app (`betFromHash` in `boot.js`, beside `comboFromHash`) opens the same bet page as tapping its row. A bet that
  is gone, finished or malformed leaves you on Live. An already-open app follows the link.
- `Notifier.URGENT` gains "🤖": the automatic single-sale line has no other trigger word, so it used to wait for the
  30-minute digest. It now goes out at once like the combo cash-out (it is a notice that money moved).

Tests: `t_sellprofit_helper.py`, `t_sellprofit_paths.py`, `t_tradelink.py`, `test_betlink_ui.py` (phone size).

## 3. Closed bets have a detail page (new issue, see PR)

Pete: "It seems like we should have the ability to tap into the ones that have already closed and see the details of
that."

- New read-only `/app/api/closed?t=<ticker>` (`api_closed` in the watcher). It validates the ticker with the same
  pattern as the combo links, then reads only what the app already stores: the account's won/lost/cashed bets,
  the `sell_log` rows and `combo_autosell_log.jsonl` for that ticker, and the combo's price history. It returns no
  account-level data and changes nothing. Unknown or malformed ids answer `found: false`.
- The app (`openClosed` / `closedFill` in `combo.js`) shows a summary card: league, matchup, the plain bet label,
  chance, Cost, Paid out (or Sold for), Profit in dollars and percent (green or red), when it closed, and a stamp
  (WON, LOST, SOLD EARLY, EXPIRED). Below it: why it closed, the chart, the picks, and what the auto-sell did,
  including retries and back-out notes. The profit figure is the same cost basis the notifications use.
- Opens from a notification link (`#c=` or `#b=` for something no longer live), from Results history rows, and
  from skipped / failed / cancelled / swapped / left-out rows in the build panel (`panelClosed`).
- An id found nowhere shows "We can't find that bet" on a small page instead of a silent home screen.

Tests: `test_closed_ui.py` (phone size, dark and light, including the unknown-id page and the endpoint); the old
`test_cashnudge_ui.py` now expects the not-found page for an unknown combo.
