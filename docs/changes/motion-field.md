# Field motion (package M1)

**Section:** Live page (game sheet, field strip)

The in-game field strip now moves. Display only: nothing here reads or changes a price, bet, cap, Pause or rule 8.
New files `watcher/spa/field.js` and `field.css` (listed in `MANIFEST.json` after `game.css` and `game_tabs.js`);
`game.js` and `game_tabs.js` are untouched: `field.js` wraps `gameAfterPaint`, `pbpRefresh` and `pbpFx` at load and
swallows its own errors.

- Ball and arrow glide from the old spot (a long gain hops in an arc); the drive trail grows in the team colour; the
  first-down line slides and locks in; touchdown, field goal, safety, turnover, possession-change and red-zone moments
  (banner, colour wash, end-zone pulse, ghost ball, uprights, crowd twinkle); richer team-coloured end zones; new
  play-by-play rows slide in (30 ms stagger, at most 6) and scoring rows pulse their rail.
- Honest motion: events fire only between two real consecutive snapshots (not after a gap over 90 s, not after a stale
  one, not when live and replay switch). The live dot pulses only while the game is live AND the feed is fresh; stale is
  a grey still dot. Reduced motion, a hidden tab or a stale feed means the final state only; loops pause offscreen.
- Only transform/opacity (WAAPI `translate`/`scale`), no layout shift, taps never delayed, numbers always final.
  Tokens from polish E are not merged yet, so durations use local values.

Tests: `t_field_motion.py` with `fixtures/field_replay.json` (exact values for yard-to-position, first-down line,
event classification, drive trail, glide kind, the animate-or-snap decision).
