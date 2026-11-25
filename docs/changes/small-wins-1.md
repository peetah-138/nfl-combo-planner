# Small no-money UI wins (issues #404 #405 #406 #408 #353 #368 #402 #403 #275)

**Section:** Results page, Build page, Long shots, Overlap, Closed-bet page

Presentation only. Nothing in buying, selling, sizing or the order paths changed.

- **#404 Comebacks header.** The header is a real `<button class="cbh">` with a keyboard focus ring, `aria-expanded`,
  and a one-shot open animation (`cbin`, `cbchev`). `cbTog()` puts focus back on the header after the redraw.
- **#405 Tappable rows.** Results history rows (`.hrow2`) are `role=button` with a tab stop; Enter and Space work
  (global handler in `smallwins.js` for any `[role=button][tabindex]` that is not a real button). The Build "Skipped"
  card is no longer a button wrapped around a button: the card opens the detail, and "Tap for a fresh price" is its own
  44px button (`.prbtn`).
- **#406 Closed bet.** A network error or malformed answer shows "Couldn't load that bet" with Try again;
  "We can't find that bet" now only shows when the server says `found:false`. The retry area keeps its height so the
  page does not jump.
- **#408 Inline handlers.** Game, combo and pick ids are passed through `data-t` / `data-ev` and read with
  `this.dataset`, not interpolated into `onclick` strings. `pToggle` and `pStakeSheet` ids were left alone (outside
  the named functions). `onclick` stays because the press and haptic layers key off `[onclick]`.
- **#402 #403 Reprice feedback.** `pReprice` no longer fires a haptic or toast after the await. A failed or
  unreachable reprice shows inline on the card (`pRepFail`: "Check Kalshi", "Paused", "Just priced", or "Couldn't get a
  fresh price", each ending "Nothing was bought."), and a later success replaces it. Only `panel_reprice` is called.
- **#353 (client half only).** A long-shot price failure shows an inline `.lsfail` reason instead of a toast, and an
  unknown outcome (`res.check`) keeps saying "Check Kalshi" across Build refreshes in this page (`S.lsChecked`).
  Display state only. **Skipped:** carrying the unknown-outcome state from the server, because it touches the buy
  path and rule 8.
- **#368 Overlap.** "Add anyway" keeps its width (`min-width`), and the list re-renders with a FLIP slide
  (`flipSnap`/`flipPlay`) instead of jumping; the error haptic after the await is gone.
- **#275.** A "bad" idea answer shakes once (`shk`, one-shot); reduced-motion turns every new animation off.

Files: `watcher/spa/smallwins.js`, `smallwins.css` (new, in `MANIFEST.json`), `results.js`, `build.js`, `combo.js`,
`games.js`, `game.js`, `ideas.js`, `live.js`, `longshots.js`, `overlap.js`.

Tests: `test_smallwins_ui.py` (dark and light at 390x844: roles, keyboard, focus ring, one-shot animations, failure
feedback, retry, no JS errors, no sideways scroll); `test_reprice_ui`, `test_comeback_ui`, `test_closed_ui`,
`test_overlap_ui`, `test_longshots_ui` still pass.

ROADMAP: none
