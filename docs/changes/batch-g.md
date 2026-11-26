# Leg flip loading: soft shimmer instead of a folded sliver (issue #206)

**Section:** Build: flip a leg

While a leg flip is awaited, the tapped row no longer folds to 80 degrees at 35% opacity (which left a thin sliver and a
gap). Pete chose a shimmer: the row keeps its full size and shows a soft moving highlight (`.lrow.wait`, `lshim` in
`watcher/spa/build.css`), its text slightly dimmed. With `prefers-reduced-motion` the row is held still with a flat tint.
Display only: no change to the flip logic, quotes, Buy or any price. The `lfold` animation is gone; `lturn` (the reveal)
is unchanged. `test_flipleg.py` now checks the row keeps its size, has no transform, and shimmers (still when motion is allowed).

Refs #206 #483

#483 is not built here: open PR #487 already records ESPN win chance and lines beside our model and Kalshi price.
