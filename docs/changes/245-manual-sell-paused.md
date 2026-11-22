# Pete's own single-bet Sell works while paused (issue #245)

**Section:** "Selling: smart sell everywhere" (the single-bet Sell from #238/#239), plus the Pause bullet in "Hard rules"

Pete's decision (2026-11-21, answering #245): Pause stops everything automatic and every buy, but it must not block his
own tap that closes a position he already holds. So the manual single-bet Sell (Live's single cards and the game page:
"Get new price" and "Sell", web app acts `sellquote` / `singlesell`, engine `single_sell_quote` / `single_sell`) no
longer refuses while paused: the Pause refusal before the quote, the one after the quote and the re-read before the
order are gone (`SELL_PAUSE_MSG` removed). `paused` is still passed in, only to add the sheet's calm grey line
(`paused`/`paused_note` on the quote, `SELL_PAUSED_NOTE`: "Pause is on. This is your own sale, so it still works.",
`.sbw.sbcalm` in `sell_single.css`, not a warning) and to note "while Pause is on (your own tap, #245)" in the log.

Every other guard is unchanged: trading access (`can_trade()`; the Pi never trades, and both web app acts now also
refuse first on `backup_now()`, the device's role read fresh, an unreadable settings file counting as the backup, since
`paused_now()` used to cover that), the unknown-outcome block, one order per fresh 20 s quote, one IOC reduce-only order
at the quoted bid, a lower bid on the fresh re-read refused, a gap over 6¢ needs Sell anyway, an unclear answer is
"check", blocked and never resent (rule 8).

Combo cash-out taps were checked and left alone: the web app's `go` / `ask` / `askhalf` / `keep` (`cash_action` ->
`accept_cash`) never read Pause, so Pete's own combo cash-out already worked while paused; this change makes singles
consistent with it. The manual **Hedge** tap (`hedgego` -> `place_hedge`) also doesn't read Pause, although a hedge is a
buy: left as it was (out of scope here), flagged on the PR for Pete. Still stopped by Pause (tested): auto cash-out,
smart sell (combos and singles), the learned loss cut and auto-hedge (`pause()` turns `auto_sell` off and
`auto_sell_now` does nothing without it), killer deals and standing orders, the panel's buys, the combo quote/idea/Buy,
Buy straight (`single_buy_quote` / `single_buy`), Live idea single buys (`idea_single_buy`), `accept_offer`, pot moves.

Tests: `t_singlesell.py` (section 3 now asserts the sale works under Pause, including Pause turning on mid-sale and an
unreadable Pause, with every other guard still holding; 3b asserts the buys and automatic sales still refuse under
Pause; section 7 the Pi check in both acts), `test_singlesell_ui.py` (the calm note, a green Sell, one send while
paused), `t_safety.py` unchanged.

**CLAUDE.md note (for the release owner to fold in; this PR does not edit CLAUDE.md):** in Hard rule 2 / "How these are
enforced in code" › *Pause*, add: "Exception by Pete's decision (#245): his own single-bet Sell tap (`sellquote` /
`singlesell`) works while paused, with every other guard (Pi / trading access, unknown-outcome block, one order per
fresh quote, IOC reduce-only at the bid, lower bid refused, Sell anyway on a thin market, rule 8); the sheet says
'Pause is on. This is your own sale, so it still works.' Combo cash-out taps already worked while paused." Also drop
"Pause" from the #238/#239 single-sell description's list of checks.

ROADMAP: none
