# Button feedback (visual only, haptics-independent)

With haptics off, every button that moves money or state now shows the same sequence on screen:
pressed (instant darken/scale), then pending (spinner, "Buying…", disabled, aria-busy, width locked so nothing jumps),
then a result: green check, red "Didn't go through" with the reason in plain words, or amber "Check Kalshi" when the
answer is unknown. An unknown answer is never shown as Bought/Sold/Hedged and never offers a blind retry (rule 8).

New files: `watcher/spa/press.js` (helper: fbPend / fbEnd / fbIdle / fbKind / fbNote, hidden `#fbsr` live region) and
`watcher/spa/press.css`. No request body, order logic or server code changed.

Buttons covered: Buy (build), Buy idea, Long-shot buy, Buy straight, Sell straight, Cash out, Place hedge, Move money
between pots, Panel approve/add, Restart panel, Stop panel.

New guards (a second tap while pending does nothing): Cash out, Place hedge, Restart panel, Stop panel. Existing guards
(S.buying, S.ibuy, s.sending, S.pSend, S.lsBusy) are kept and tested.

Behaviour changes worth a look in review: Place hedge no longer closes the sheet before sending; a Panel request timeout
now reads as "may or may not have gone through" (check) instead of a plain failure; a bought idea now ends on the Bought sheet.
