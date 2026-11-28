# Results screen polish (display only)

**Section:** Results

Changed (no computed number changes, only how they are shown):

- The top tiles are now the profit or loss number first and largest, with "3 settled combos" under it (it used to wrap to three
  lines), then four equal tiles: Return on stake, Best result, Won, Cashed out ("Won - cashed 1 . 1" was cryptic).
- One money format on Results: dollars and cents always (`$9.40`, `$54.00`, `$1,234.50`), a sign only on a profit or loss.
  Win is green and loss is red everywhere, including Return on stake and the history rows.
- History rows lead with the Result, then Paid and Got back in aligned columns. The filter chips, sort menu, Day/Week toggle and
  What's working tabs are 44px tall.
- Loading shows a matching skeleton (one tall tile, four small). With nothing settled the tiles are hidden instead of showing zeros.
- The profit tiles no longer roll their money number (the roll used the old rounding); percent and counts still roll.
- The cut-losses explanation (#570) was already shortened on develop; left as is.

Tests: `tests/suite/test_polish_results.py` (exact strings, 44px, skeleton, empty state).
