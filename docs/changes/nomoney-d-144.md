# Leftover small items from the 144 backlog sweep (#246)

**Section:** Build page (Best bets heading)

Display wording only. The Best bets heading total now uses the app's one signed-money formatter (`smoney`, same as the
rest of the page) instead of a hand-built `+$` string, so big totals read `+$1,200` like every other figure.

Checked and already done on develop, so not touched: #517 (inline handlers moved to `data-*`, report-only CSP, #552),
#214 (#535), #379 (Copy setup command and `--problems`, #575), #414 (`held_markets()`, #419), #569 #570 #571 #573 (#580).

Left out on purpose: #519 (needs Pete's decisions on a hedge marker, caps and a Settings card before any code), and from
#246 the `get_offer` raw exception text (server side, sits on the sell path), the stake-control rounding, the `.sacts`
hint taps and "Rough before 9 AM" (text not found in the code).

Tests: `test_bestbets.py` (heading total).
