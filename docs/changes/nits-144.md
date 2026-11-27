# nits-144: display and wording nits from the 143 reviews

Wording and layout only; nothing here touches buying, selling or sizing.

- Settings "More" button (`.smore`) is at least 44px tall.
- Full-auto "can't read positions" blocker no longer shows a Python exception name.
- Hedge card "Sell at" with no beatable offer reads "Not until it pays more".
- Full-auto losing-streak line reads "N lost (pauses after M in a row)".
- Results cut-losses cell uses "Up to X%" for both its own and the starting value.
- `knobCard`: the "Couldn't read the numbers" line shows for `null` as well as `{}`, is a live region, and has a Try again button (reloads Results).
- Flip verdict note leads with the expected-dollars sentence (order only).

Tests: `test_singlesell_ui.py` (new wording), `test_knobs_ui.py` (null, Try again, aria-live).
