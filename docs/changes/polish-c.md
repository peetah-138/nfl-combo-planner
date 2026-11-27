# Polish C: real-offer switch wording, calm error box, error buzz on iPhone (issues #542 #545)

**Section:** Settings (Profit), every button that shows an inline error

Display and wording only: no buy, sell, sizing or setting behaviour changes.

- **#542 Real-offer switch wording** (`watcher/spa/settings.js`, CLAUDE.md "Switch off" bullet). The "Off" text now says the switch
  covers every sale it lists: take profit, lock-in, smart sell, plan sales and the guarded stop-loss. Each sells only on a real
  offer already in hand. The code is unchanged (the stricter behaviour stays, as CLAUDE.md says is deliberate); only the words
  were wrong. If Pete would rather lock-in and stop-loss keep asking when the switch is off, that is a scope change for him to
  decide.
- **#545 Error box fades in once** (`paintErr` in `common.js`, `.berr.still` in `app.css`). A repaint rebuilds the box, so it used
  to fade in again each time. It now remembers it was shown and is rebuilt already settled; a new failure still fades in.
- **#545 Error buzz on iPhone** (`hap`/`hapOwed` in `haptics.js`, tap listener in `common.js`). iPhone ignores a buzz that comes
  after an await. On an iPhone, `hap('error')` outside a tap now leaves an 8 second note, and the next real tap plays the error
  pattern inside itself (once). The inline box and toast still show the reason at once. Not verifiable on a real phone here.
- **Already done, nothing added:** #213 and #196 (batch E, PR #535), #195 and #518 items 1 to 3 (PR #547). #518 item 4 (a single's
  break episode never closed) is #316 item 1 and belongs with the money-path work.

Tests: `test_polish_c_ui.py` (phone, dark and light).
