# Games and Build phone polish (display only)

Gaps found at 390px (before/after shots in `~/dev/wt/screens/polish-games-ui/`):

- Games cards were busy: a big dash where the chance isn't known yet, a loud blue YOURS badge, "$ riding" jammed against the bet chips.
- The board put two teams side by side, so names were cut ("Bosto...", "Den...") and price and fair chance were tiny.
- The combo tray was a bright blue bar with a cut-off sentence.

Changed (markup, CSS and labels only; no pricing, buying, selling, sizing or data code):

- Games card: rounder, quieter header, chance shown as one pill (or hidden when unknown), footer "$X riding" on the left and "Open game ›" on the right.
- Board: one calm card per game, teams stacked with full names, a thin bar under each sized by its fair chance (the number already shown).
- Combo tray: dark card with "YOUR COMBO" (or "YOUR BET"), a plain headline that wraps instead of cutting, 44px buttons.

Not done: a sideways-scrolling chip row (tried; the haptic-switch rules forbid sideways-scrolling strips of switches, tests test_hsw and test_chips_stay), a Moneyline/Total/Spread chip row (we have no bet-type filter; that is a feature), team marks/records, volume in the footer.
