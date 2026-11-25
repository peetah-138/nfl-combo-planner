# iPhone tap, scroll and layout polish (issues #274 #273 #272 #178 #186)

**Section:** Build page, Results page, Live page (toasts and sheets)

Build date card: the "Sunday is always in" note is now plain text (no tappable-looking span), the day and week chips are
44px high targets, and a refused date change shows an inline `.derr` alert inside the card (from `S.dayErr`) instead of
a toast that vanished. While the board reloads after a change, the card is kept on screen (`S.dayHold`, rendered by the
skeleton branch of `build.js`) so it no longer jumps. When a date change clears picks, `setDays` toasts "Picks cleared
for the new dates." (#274, #273).

Toasts: `toast()` drops its tap action while a sheet (`#modal.on`) is open, and `app.css` blocks pointer events and the
chevron behind the sheet, so a toast can no longer be tapped through a sheet (#272). Idea dismiss/undo: the delayed
save sleep is cancellable (`job.wake`), so Undo brings the idea back immediately with a "Bringing it back..." toast and
no server round trip when nothing was saved yet (#178).

Results: the Smart Buy "Bigger stakes" line is a collapsible `<details class="sbmore">`; the Stopped column uses
plain-English `BUCKET_WORDS`, and the engine mirrors that with `LINE_BUCKET_WORDS` / `line_bucket_words` in the
`line_clv_block` message. Best Bets line cards show "avg N¢" when the average fill differs from the quoted price;
`line_fill` now returns `avg` and `best_bets_feed` passes it through (display only, no pricing or stake change) (#186).

Already done on develop and not rebuilt: #281, #151, #218. #205 already works at normal row height (rows taller than
64px skip the see-through switch). #196's switch no longer exists. #206 needs a real-phone look and a design decision.

Tests: `t_tap_polish.py` (engine), `test_tap_polish.py` (page), `test_buildlayout.py` (extended).

ROADMAP: none
