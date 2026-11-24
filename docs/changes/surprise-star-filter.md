# Surprise me: All | ★ Only, and no star on live combos

**Section:** The Build page (Surprise me), Fair prices and data

- Build › Surprise me has an **All | ★ Only N** switch (`surToggle`/`surList`/`setSur` in `watcher/spa/build.js`,
  remembered in `cw_sur`). ★ Only shows just the "★ Value pick" combos (`kind == 'value'`); with none it says so.
  Display only: nothing it hides is bought, sold or changed.
- **A combo with a pick under way never carries the ★ or the "Likely about X% of fair" guess** (the guess is learned from
  past pre-game Kalshi prices, and a value combo's edge is a pre-game one). Fixed where they are assigned:
  `value_label(legs)` (used by `value_combos`) labels such a combo `mix` / "Live pick", and `combo_star(c)` (used by the
  watcher's `combo_view`) re-checks at view time, so a combo built before kickoff loses its star once a leg starts; a live
  combo also gets no `pred`, no `est` and no auto-size. Uses `idea_combo_live_gap` (a leg it can't judge counts as live;
  fail closed). Panel, Best bets, sizing, caps, Pause and rule 8 untouched.
- Tests: `t_surprise_star.py`, `test_surprise_star.py`.
