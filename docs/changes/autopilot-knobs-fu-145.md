#### Autopilot exit knobs: follow-ups to #612 (issue #145)

**Section:** "Autopilot" (the card) and "Self-tuning: the exit knobs"

- **Wording made true.** The card no longer says every step is undone the next week. Only the combo-setting steps are. Smart sell's
  exit-knob steps are judged again on full-auto bets for display only; nothing undoes them, so the card says to use Undo last
  change. It also says the knobs keep stepping while full auto is off (the "Waits for full auto" tag is about the combo settings).
- **Loosening waits for the brake.** While the full-auto brake is cautious (`ap_brake_cautious`: soft level above 0, the hard
  brake, or anything unreadable = cautious) a live exit-knob step that loosens (`knob_loosens`: profit floor, lock-in, and the
  rest; the loss guards also still need your OK) is not taken, and shows as "cautious" in the group's last look. Tightening
  steps still go. A hedge-cap raise waits too (it is a loosening one; it is a test only today). Unreadable full-auto file = cautious.
- **Undo during the weekly run.** The run reads each league at the start and used to write it back whole at the end, which could
  silently put an Undone step back. Now, if a league's own values, times or undone marks changed in between (your Undo), the run
  does not write that league, drops its log lines, says so in plain words, and judges that league again the next day.
- **Stale knob step.** A newest knob step that has since moved on no longer hides Undo for an older setting change: the card and
  Undo fall back to that change. With nothing else to undo, Undo still says the knob is no longer where autopilot left it.

No money movement added; only fewer steps ever happen (loosening while cautious, and a run that lost to an Undo).
