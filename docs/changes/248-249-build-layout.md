# Build layout: the date range and the combo slip, with the games board (issues #248, #249)

**Section:** Build page

**The date range moved from Settings to Build (#248).** The setting Pete means is the per-league set of dates combos and the
board are built over: `next_day` (today / tomorrow; daily leagues and the Mix's "same day"), `thursday`, `saturday`, `monday`
(slate-week leagues: football, soccer, UFC; Sunday is always in) and `mix_window` (the Mix's "Games from" windows,
`MIX_WINDOWS`). They used to be rows under Settings > Games & picks. Nothing about them changed: same keys, same per-league
values (they are not in `SHARED_KEYS`), saved through the same `/app/api/settings` call with the league (`api_settings`, then
`send_synced` to the Mac), so every device and the Mac agree, and the Mac's `by_day`/`day_on` read them exactly as before.
On Build, `dayRange(d)` (`watcher/spa/build_sections.js`, from Build's existing `days` block) draws a compact card at the top of Build, directly under
the league chips (so it is on the first screen on a phone): Today / Tomorrow, or Thursday / Saturday / Monday chips with "Sunday is always in", or the
Mix's windows (plus Today / Tomorrow for "Same day"). `setDays(vals)` ticks a haptic, shows the choice at once, saves, reloads
Build, and on a refused save puts the old choice back and says "Nothing was changed". Other dates mean another
board, so a successful change also drops any picks and a quote made on the old one (a combo is only priced from what is on screen). The buttons use the global press feedback
and haptic switches. Settings > Games & picks no longer has the rows: one pointer row says the dates moved to Build (button:
Open Build). Display and placement only: no pricing, caps, cut-offs or buying changed.

**The combo slip sits with the games board (#249).** Up to 1360px the Build grid is one column, which left the "Your combo" card
(Single bet / Combo switch, picks, hint, spent/cap/cut-off line) after everything in the main column, far from the board where teams are tapped.
`narrowBuild()` (`matchMedia('(max-width:1360px)')`) now renders the slip right under the games board, before "More combo
ideas" (`.slip.inl`, static); above 1360px it stays in the sticky side column as before. Exactly one slip is ever in the page
(never both, so ids like `#sbslip` don't repeat); crossing the line re-renders Build and keeps the picks (`S.slip`). The floating
slip bar, the quote and Buy phases (`data-ph`, `ccPhase`, `S.qpend`/`S.bpend`), the Buy straight sheet and the #209 flip-leg
animation are untouched. The hint now reads "Tap teams on the board to build your own combo, or use one of the ideas."

Tests: `test_buildlayout.py` (phone dark and light, desktop, wide: date range above the board, saves through the settings call,
refusal puts the old choice back, week and Mix modes, Settings pointer, slip placement and crossing 1360px, quote in the slip,
no sideways scroll, haptic switches); `test_days.py`, `test_singlebuy_ui.py`, `test_motion.py` still apply.

ROADMAP: none
