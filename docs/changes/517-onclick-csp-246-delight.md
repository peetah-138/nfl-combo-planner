# Inline handlers to data attributes, report-only CSP, delight follow-ups (issues #517, #246)

**Section:** Web app (security hygiene), Live page, Build page

**#517.** The Live "Do now" cards (`doNow` in `live.js`: Keep, Cash out, Hedge, Get offer) and the overlap bar's Add anyway
(`ovBar` in `overlap.js`) no longer paste an id or game name inside an `onclick` string. Each button carries it as
`data-t` / `data-game` (escaped with `esc()`) and the handler reads `this.dataset`; same functions, same endpoints, same
guards. `test_onclick_data_ui.py` now taps every one of these with a hostile id and also guards the source.
The hub, web app and login page now send `Content-Security-Policy-Report-Only` (`CSP_REPORT_ONLY` in `combo_watcher.py`).
It is report-only on purpose: the SPA still has hundreds of inline `onclick` handlers (and inline `<script>`), so a policy
that forbids inline script would break the page. The header only makes the browser log what a policy would block, so it
cannot break anything. It already forbids plugins, `<base>` tricks, framing and outside connections; the next step is to
convert the remaining inline handlers screen by screen, then enforce. No enforcing CSP header is sent.

**#246 (items not done in #535).** The panel header's chance-up %, Expected and range carry `data-num` (new `fmtNum` format
`sm` = signed money) so they roll like the amount when `panel_whatif` returns; a tappable toast now gets the press feedback
and tick (`#toast.tap` in the `TAP` selector in `common.js`); a `#c=` link to a bet that is no longer live opens its page
with a calm toast; the sell sheet drops "no sellers" and says "contracts wanted". Left open from #246: the stake-control
rounding, "Rough before 9 AM" (text not found in the code), "expected +$" formatting, the `.sacts` hint taps, and the raw
`get_offer` exception string (server side, touches the sell path). #213 and #214 were fully done in #535 (their issues can be closed).

Tests: `test_queue_hygiene_ui.py`, `test_onclick_data_ui.py`.

ROADMAP: none
