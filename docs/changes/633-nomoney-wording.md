# No-money wording nits from release 146 (#633 part a)

Display and wording only; no buying, selling, sizing, limit, gate or data change.

- `_fal_val_text`: bet size and cap-use steps print whole percents (90%, not 90.3%); the underlying value is unchanged.
- `_fal_name`: the Mix league's budget share reads "mixed-sports budget share" (was "Mixed budget share").
- Full-auto card, cap used up: "Today's spending cap is used up: $X of $Y spent." then, when it applies, "Autopilot has cut it to N% of your usual $Z." or "Autopilot only lets it use N% of your usual $Z."
- Brake step reason: "this setting tightens one step now instead of waiting for its weekly turn" (was "right away").
- `fullauto.js`: the Freeze button's `x.rec` is escaped in its onclick.
- `money()` already prints -$3.50 (shipped earlier); an exact test now pins it.
- #246 and #283 were already shipped (44px buttons, toast role=button, data-num on the panel numbers, split registry intro, Changed row folds "where it stands"); closed with a note.
- Tests: `tests/suite/t_fullauto.py` (exact strings).
