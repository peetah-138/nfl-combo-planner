# Tickers and ids travel as data, not as code, in tap handlers (#247, part of #408)

Buttons in the web app used to paste a ticker or id straight into the JavaScript of their `onclick`
(`ssPrice('${x.t}',this)`). Even with `esc()` that is not safe: the browser decodes `&#39;` back to `'` before it
runs the handler, so a ticker holding a quote could end the string and run code. Now each such button carries the
value in a `data-*` attribute (escaped with `esc()`) and the handler reads `this.dataset.<name>` when tapped.
The handler stays inline on purpose (not a document-level listener): `event.stopPropagation()` and bubbling work
exactly as before. Same actions, endpoints and guards; nothing about buying, selling, Pause or rule 8 changed.

Converted: `sell_single.js` (Sell sheet buttons), `build.js` (panel Skip/amount, Buy straight in rows, slip bar and
slip card, Flip a team), `build_cards.js` (singles card), `combo.js` (Hedge/Ask/Sell), `game.js` (Buy a team),
`ideas.js` (price/buy/pass/not now/dismiss/open), `longshots.js` (quote/buy), `live.js` (cash-out, smart-sell chip,
row open, Hedge sheet, Cash out sheet), `access.js` (copy link). Left to PR #412 (its lines): `pick(...)` in
`build.js`, `openCombo`/`openGame`/results/overlap handlers, and `game.js` line 35.

Test: `test_onclick_data_ui.py` renders each of these with a ticker holding a quote, angle brackets and an ampersand,
taps every button and checks the handler got the exact string, nothing ran as code and the onclick text never
contains the ticker; plus a source check that converted handlers stay converted.
