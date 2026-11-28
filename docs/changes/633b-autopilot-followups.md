# #633 (money half) + #592: autopilot follow-ups

Fixed (all fail-closed; nothing here adds spending or loosens anything):
- #592 `_sl_tune` (the legacy stop-loss mover that writes `sl_prog` / `sl_drop` into smart.json) is now tighten-only, like the
  stepper (#590): it only tries the same value or one step UP (a later "not before" point, a bigger fall), never down, and a value
  already outside its bounds is never pulled down. Before, it could step 0.50 -> 0.45 / 0.20 -> 0.15 on a good-looking replay.
- Open-slot evidence (`fa_slot_skips` and its caller) is sized by `_fa_sized` like the live buy pass: autopilot's bet-size multiple,
  the day's loss room (`_fa_loss_fit`) and the panel budget now count, each as if the bets before were bought. Unreadable numbers
  log and record nothing.
- Share evidence (`_share_load`) judges against the live cap (Pete's cap x the brake's cap cut x autopilot's cap use), not his plain
  cap. The brake level is read from the saved state; an unreadable level reads as the smallest cap (`_fa_level_saved`).
- A step that tightens because the soft brake stepped in no longer waits a week behind a bar/share/size/cap-use step
  (`_ap_brake_tighten`). A tightening from a losing month still waits, as before; loosening is unchanged.

Already fixed in #635, skipped: `money()` negatives (`-$3.50`), the "eases off right away" wording.
Left alone (not money, display only): other copy nits, `fullauto.js` onclick escape (fixed server value). The $30 per-bet bound
still comes from the daily cap room (`s <= room`), unchanged ($30 cap, $300 bankroll, $20 loss limit, Pause, Pi never trades).
Not done: an `_sl_tune` value already written below the default in an old smart.json is still served; only new moves are tighten-only.
Tests: `t_autopilot_633b.py` (exact values; fails without each fix).
