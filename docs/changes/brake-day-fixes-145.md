#### Full auto: three brake fixes from the release 145 review

**Section:** "Full auto: the real master switch"

- A daily-loss pause from an earlier day no longer counts as cautious. Before, one day at the loss limit left the saved pause
  in place, so Autopilot's settings, exit knobs, hedge raises and Undo-of-tightening never loosened again. Only a pause from
  today (or one whose day cannot be read, or a streak pause) still holds things. The daily loss limit still stops buying that
  day exactly as before, and a caution level above 0 still holds.
- "Back to normal now" tapped while a pass is running is no longer overwritten: the pass saves its caution step only if the
  saved caution and reset time are still what it read.
- The cautious bar now ADDS to the league's learned bar instead of replacing it, so a learned +1.0 plus cautious level 1 needs
  +1.5. It can only tighten.
