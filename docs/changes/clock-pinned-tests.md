# Engine tests no longer depend on the time of day

**Section:** Tests (no product change)

`t_panelpipe` and `t_review` failed on CI runs between 1 a.m. and 4 a.m. Pacific (for example 11:54 UTC, 03:54 Pacific)
and passed the rest of the day. It was not the calendar date rolling over. Their fixtures put kickoffs at `now + 3h` and
`now + 4h` by the wall clock, and the panel's "today" deliberately ends at 4 a.m. Pacific (`_local_day_end`; the panel
day itself starts at 4 a.m., `_panel_day`). In that window the fixture games fell after the cut, were treated as
tomorrow's, the panel came out empty and the tests failed.

Verdict: **test bug, not a product bug.** The 4 a.m. Pacific boundary is intended and unchanged. No trading behavior,
sizing or money path was touched.

- `t_panelpipe` and `t_review` now pin the clock (`time.time` and `E.dt.datetime.now`) to noon Pacific on 2026-11-24;
  time still moves forward, only the start point is fixed.
- New `t_clockday` pins the clock at the boundary: `_local_day_end` and `_panel_day` at 03:59 and 04:00 Pacific, and
  `build_panel` at 02:00 and noon (a 03:30 game is today's, a 04:30 game is not, games 3h and 4h ahead at noon both are).
- When writing a test with kickoffs relative to `now`, pin the clock first (see the top of `t_review`).
