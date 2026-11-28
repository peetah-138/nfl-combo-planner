# No-money follow-ups, batch 5 (display and safety only)

**Section:** Autopilot / Games / Engine

Changed (no pricing, buying, selling, sizing, limits or gates):

- **#651 (h):** the Autopilot "Freeze / Unfreeze this" button no longer builds a JavaScript string from `esc(x.rec)`.
  The record key sits in `data-rec` (HTML-escaped) and the handler reads `this.dataset.rec`. Same call, same 44px button.
- **#650 (e):** `_cut_guard_ts` reads `c.get("legs") or []`, so a bet with no legs returns the empty set instead of raising.
- **#652:** Games cards are real buttons for keyboards and screen readers (`role="button"`, `tabindex="0"`, Enter or Space opens the game, visible focus ring).
  A card with no win chance yet keeps its chance row's height (`visibility:hidden`, was `display:none`), so the card no longer jumps when the number arrives.
- **#652 (docs):** the polish-games-2 entry in CLAUDE.md wrongly said the bet-type chips tick on iOS. They are in `HSWX`, so they get no see-through haptic switch; corrected there.

Not done: #652 "fair-chance bars all green" (the cited `build.css:1244` no longer exists; Games bars already colour yes/no),
the #633 copy items (money sign already fixed; wording sits next to money code), #646 (needs Pete), #640/#645/#647-#649/#650 (f)(g)
(touch spending evidence or stop-loss values; money batch).

ROADMAP: none
