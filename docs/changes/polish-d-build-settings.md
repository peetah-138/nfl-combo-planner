# Polish D: Build and Settings chips, calmer phone Settings (display only)

**Section:** Build / Settings / Knobs

Changed (looks only; no setting, value, switch, save or Mac action changes, every control is still reachable):

- The Build league chips, the Build lines-type chips and the Settings sport chips were 32px tall and wrapped to three rows (about 215px above the
  content on Build). They are now one sideways row (`.chips.chrow`, in `build.css`): 44px chips, 8px gap, a 28px fade at the right edge, and the
  chosen chip scrolled into view (`chrowFit()`, scrolls the row only; Build keeps the row's scroll across redraws). Build's chip row went from about 205px to 48px.
- Settings jump chips are 44px tall. On a phone the grid's 32px gap no longer stacks between the title, Mac line, search and chips (`.set{gap:0}`
  under 1100px) and card spacing is 12px (8px when folded).
- A folded Settings section now keeps its one-line summary under the title (ellipsis), next to the existing "N of M on" badge.
- The Mac line, when its status can't be read, is grey (not the red alarm dot) and says "status can't be read right now".
- Not changed here: `app.css` tokens, `common.js`, `motion.css`, `chrome.css`, `haptics.js` (package E). The Settings search, jump chips, folds and
  the Build and Settings skeletons already existed (#212), so nothing was added there. The Knobs card already used 44px chips.

Tests: `tests/suite/st_polish_d.py` pins the exact CSS and markup values above.
