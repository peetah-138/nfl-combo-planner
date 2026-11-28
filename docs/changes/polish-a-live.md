# Polish A: Live / Your Combos (display only)

Pete: the app is nowhere near Kalshi-level mobile polish. This is the Live tab's share (`watcher/spa/live.js`, new `live.css`
in `MANIFEST.json`, `tests/suite/test_polish_a_ui.py`). No money logic changed: no seller, buyer, threshold, guard or
endpoint is touched; only what is drawn.

- **Auto cash-out off is said once.** `autoNote()` draws one quiet note above Your combos ("Auto cash-out is off. Nothing
  sells on its own; offers below still update." plus a 44px Settings button) when `live.auto_sell === false` and something is
  riding. While it is off, a card hides its "Smart sell - off in Settings" chip (`ssChip`) and the "Take profit / Loss cut" lines
  (`ssLines`). A bet set to "I'll sell it" keeps its chip. With the switch on nothing is hidden and there is no note.
  The engine still sends the same `smart_profit` / `loss_chip` text; the page just does not repeat it.
- **One money rule on Live.** `lm()` (amount) and `lsm()` (signed change) always show cents ("$2.00", "$54.00", "$1,234.50",
  true minus "−$0.37", never "-$0.00"). Every card, single row, the hero, Do now and the settled pill use them, so the numbers in a row
  share decimals. The number roller gets two formats (`'lusd'`, `'labs'`) added to `fmtNum` from `live.js`, so a rolling cell
  does not snap back to `$13` when it animates; `common.js` is untouched (swap to the foundation helper if it lands).
- **Card hierarchy (phone).** Worth now leads (big, with its change on one line, "Offer now" for a real Kalshi offer,
  "Worth now" for an estimate), the chance sits beside it, what it paid and what it pays are the quiet second row, the next
  event line stays under the name. CSS only (`live.css`, grid order); the markup keeps the table order for the desktop table.
- **44px taps** on the filter chips (now one horizontally scrolling row), settled-filter chips, section toggles, the % / $ switch,
  the Smart sell chip, the card's action buttons and the new note's button.
- **No jumps, skeletons not spinners.** First paint shows three card-height skeleton blocks (`liveCardSkel`); asking Kalshi for an
  offer shows a shimmer pill instead of a spinner and the Ask button keeps its width (`.askb`).
- **Not done here (other packages own them):** type/space/radius tokens, shared freshness pill and the shared money helper
  (foundation), section header redesign (`ideas.js`).
- **Tests:** `test_polish_a_ui.py` compares exact strings for `lm`/`lsm`/roller formats, the settled pill, the note (once, off
  only), hidden chip/lines, the labels and numbers of an estimate, real-offer and cashed card, the skeleton and Ask button, and
  at 390px light and dark: one note, no "off in Settings" anywhere, taps >= 44px, worth-now above paid, no sideways scroll.
