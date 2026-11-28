# Autopilot: Drift since start and Back to start (issue #145, plan section 5)

**Section:** Autopilot (full auto card, Settings and Results)

Many small autopilot steps can add up. The Autopilot card now has a "Drift since start" section: for every setting autopilot
has moved it shows one plain line, for example "Bet size: 100% → 90%, tighter", grouped as How much it bets (per-game limit,
open-bet limit, budget shares, bet size, share of the daily cap used), How picky it is (combo bars, Smart Buy bars and their
borrowed values) and How smart sell sells (a league's own exit-knob values). The open-bet limit is measured from Pete's own
number, which autopilot never writes. A setting at its start is not listed. Once a calendar month (Pacific) the weekly look
adds one summary line to the log (`L["drift_m"]` keys it), "Autopilot, month in review: N settings are away from where you started. ...".

**Back to start** is a button per setting and "Reset all", each behind an app sheet (never `confirm()`). `ap_reset(key)` removes
the saved value (nothing saved = the start; for the open-bet limit, Pete's own number), stamps `since`, holds the setting two
weeks (`AP_HOLD`, like Undo: a hold blocks only loosening), marks the matching last step judged and the last change undone (so
Undo and the weekly review cannot put it back), and logs it ("you put X back to its start: a → b. It stays there for 2 weeks").
Exit knobs: the group's own `lv` value is taken away, the start is in force, a `reset` history entry and a `knob:<group>:<name>`
hold are written, in the knob file first (like `_ap_undo_knob`).

Safety, all enforced in the engine, not the page:
- The start value is the LOOSE end for most settings, so a reset that would loosen is refused while `ap_brake_cautious` is true
  (hard brake or soft-brake level above 0), and for bet size and cap use also until `_ap_quiet` (the same rule as an automatic
  loosening). The setting stays exactly where it is, nothing is queued, and the message and card say why in words. A reset that
  tightens (a setting that had drifted looser than start, e.g. bet size 120%) is always allowed.
- Reset all skips frozen settings and names them; a tap on one frozen setting is Pete's own call and keeps the freeze. Works
  with the master switch off (same gates).
- Fail closed: `fa_state()` turns a damaged `caution` into level 0 and `_fa_update` would save defaults over an unreadable
  file, so `_ap_raw_fa()` reads the raw file first (unreadable file, or lessons/caution/brake not a record, or a malformed saved
  value = refuse, file untouched); the knob file is checked the same way (`_ap_raw_knobs`). The card then shows no buttons.
- Never writes the outer limits ($300 bankroll, daily cap, loss limit, streak, max open, Pause).
- `/app/api/act` `autopilot_reset` (`watcher/combo_watcher.py` -> `ap_reset_act`) needs `confirm: true` (exactly) and a key that
  is `all`, a known `bar:`/`sbev:`/`share:` key, `game_share`, `open_slots`, `stake_mult`, `cap_use` or `knob:<group>:<knob>`;
  anything else changes nothing. It is logged to the watcher log.

Card: `fal_view()["drift"]` = `ap_drift_view(st)`; page code `faDrift` / `faResetAsk` / `faResetDo` in `watcher/spa/fullauto.js`,
styles in `settings.css` (`.fadrift`, 44px taps).

Tests: `t_autopilot_drift.py` (exact lines, one reset, hold and log, cautious not loosening, quiet period, Reset all with frozen
settings, master off, Undo after reset, unreadable state byte-for-byte unchanged, act validation, open-bet limit, exit knobs,
monthly line). Phone screenshots: `~/dev/wt/screens/autopilot-drift/`.
