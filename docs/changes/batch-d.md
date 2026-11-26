# Batch D: accessibility and small display follow-ups (Refs #433 #435 #437 #438 #455 #378)

**Section:** Build page, Results page, Settings, Fair prices and data (recorders)

Display and hygiene only. Nothing here buys, sells, prices or sizes anything, and no automatic path changes.

- **#433 signal_shadow create-table once.** `_sig_tables()` now runs its six `create ... if not exists` statements once per
  open history database (remembered in `SIG["ddl"]`), instead of on every panel pass under the shared history lock. A
  statement that fails (`store_x` swallows it and returns None) is simply tried again next pass. Test: `t_signal_shadow.py` F.
- **#455 Buying row.** The "Buying…" rows (Build combo card, Buy ideas) are `role="status" aria-busy="true"`; their spinners were
  already `aria-hidden`. Test: `test_comeback_ui.py`.
- **#437 "copied" is announced.** The toast is a polite live region (`role="status"`), so "Code copied" and every other toast is
  read out. The code sheet is already `role="dialog" aria-modal="true"` (the shared `#sheet`).
- **#435 pReprice focus.** After a fresh price the redraw replaces the tapped button; `pRepAfter()` puts focus on the card's new
  button (or its result line) and `srSay()` says the verdict through one steady, visually hidden live region (`#srl`).
  Test: `test_reprice_ui.py`.
- **#438 Comebacks closes by sliding.** `cbTog()` animates the body's height and opacity to zero (220 ms) before removing it, so
  content below glides up. Instant with reduced motion. Test: `test_comeback_ui.py`.
- **#378 Log access uses the app's own sheet.** Stopping log reading, and making a new code, ask in the shared sheet
  ("Stop the dev Mac reading logs?" / "Make a new code?", Cancel plus a 44px action button) instead of `confirm()`. The switch is
  put back at once, so closing the sheet any other way changes nothing. Test: `test_logaccess_ui.py`.

Checked already fixed on develop, not touched: #458, #457, #454, #441, #440, #439, #436, #434, #415.
