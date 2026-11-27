# Exit knobs in the Autopilot log (#145, step 3 of the self-improvement plan)

The weekly knob stepper (#228) already moves smart sell's exit numbers (profit floor, risk weight, loss cut, lock-in and the
other live knobs) on its own evidence. Those live steps now show in the **same Autopilot log** on the full-auto card, with the
same Undo, Freeze and master switch. **When and how much a knob moves is untouched**: same candidates, same evidence bar
(older 70% picks, newest 30% must agree, dollars after fees), one live step per group per run. No new automatic money movement.

## What you see

- Log line per live step: `NBA Profit floor: 1.7x what you paid -> 1.8x what you paid. Why: 15 of 60 past bets would have ended
  differently, +$13.50 in all after fees.` plus how it stands on full-auto bets (below). Brake resets show too. The log shows the
  newest 6 lines of both kinds.
- **Undo last change** now takes the newest of (a setting change, a knob step). A knob undo puts the group's value back exactly
  (its own earlier value, or "none" if it had none), makes the group's next step wait for bets after the undo, and holds that knob
  in that group for 2 weeks (a hold stops only loosening steps, as for the other settings). Refused when the knob has since moved,
  when the step was made before this change (no record of what was there), or when it would loosen while the brake is cautious.
- **Freeze**: a new "Smart sell's numbers" row (key `knobs`) freezes every live exit knob; `knob:<name>` (e.g. `knob:smart_floor`)
  freezes one. A frozen knob shows status "frozen" in the stepper's rows and takes no live step.
- **Master Autopilot switch**: off (explicit) pauses the live knob steps too (status "paused"). Full auto itself being off does not:
  the knobs also serve manual smart sell.
- **Fail closed**: an unreadable or malformed Autopilot control file pauses the live knob steps; a malformed hold counts as held.

## Judged on full-auto bets

A week after a live step the stepper judges that same step again, with the same replay (fees included), on the full-auto bets
(the ones full auto placed and anything swapped in for them) settled after the step. Needs 5+ such bets; shown in the log line as
`On 40 full-auto bets since: +$9.00 after fees.` With no (or too few, or unreadable) full-auto bets the line says
`Judged on all bets` and the all-bets evidence stands unchanged. It is display only: nothing is reverted automatically.

## Not changed / worth a look

- The brake hook `ap_brake_cautious` deliberately does **not** gate knob steps (that would change when knobs move); it only
  refuses an Undo that would loosen.
- Held and frozen only apply to live steps; shadow ("would step") rows are as before. The hedge cap's system raise is not live and out of scope.
- Files: `nfl_combo_planner.py` (knob_tune skips + history record, `ap_knob_*` helpers, `ap_undo`, `ap_freeze`, `fal_view`),
  `watcher/spa/fullauto.js` (one sentence), `tests/suite/t_autopilot_knobs.py`.
