# Batch D: accessibility and small display follow-ups (Refs #433 #437 #455)

**Section:** Build page, Results page, Settings, Fair prices and data (recorders)

Display and hygiene only. Nothing here buys, sells, prices or sizes anything, and no automatic path changes.

- **#433 signal_shadow create-table once.** `_sig_tables()` now runs its six `create ... if not exists` statements once per
  open history database (remembered in `SIG["ddl"]`), instead of on every panel pass under the shared history lock. A
  statement that fails (`store_x` swallows it and returns None) is simply tried again next pass. Test: `t_signal_shadow.py` F.
- **#455 Buying row.** The "Buying…" rows (Build combo card, Buy ideas) are `role="status" aria-busy="true"`; their spinners were
  already `aria-hidden`. Test: `test_comeback_ui.py`.
- **#437 "copied" is announced.** The toast is a polite live region (`role="status"`), so "Code copied" and every other toast is
  read out (set from `smallwins.js`, so it does not touch the markup #532 edits). The code sheet is already `role="dialog" aria-modal="true"` (the shared `#sheet`).


Checked already fixed on develop, not touched: #458, #457, #454, #441, #440, #439, #436, #434, #415.

#378 (log access sheet), #435 (reprice focus and announce) and #438 (Comebacks slide) are done in #532 (batch-f) and were removed from here so the two PRs do not conflict. No visible change remains in this PR.
