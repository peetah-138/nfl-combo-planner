# UI polish batch 2 (issues #436, #454, #455, #437, #440, #281)

**Section:** Delight / Live page / Settings (display only; nothing here touches buying, selling, prices, Pause or caps)

- **44px tap targets (#436, #454):** one rule in `app.css` gives `.dbtns .btn` (Pass / Buying / Cash out / Hedge), `.sheet .btn`
  (Done, Copy code, Copy address, closed-bet Try again), `.srow .btn` (Settings rows such as Secure address › Try again),
  `.empty .btn` (the "Couldn't load this screen" Try again) and `.sbgo .btn` a `min-height:44px`.
- **Screen readers (#455, #437):** every `<span class="spin">` is `aria-hidden`; the disabled "Buying…" buttons carry `aria-busy`.
  The shared sheet (`#sheet`) is now `role="dialog" aria-modal="true"` and `modal()` names it from its first `<h3>`.
  The one-time log-access code sheet says plainly to run `security add-generic-password ... -w` in Terminal on the dev Mac
  (no more "ask Claude to walk you through them").
- **Best bets wording (#440):** `exitWhen` reads "about 41 min from now" (minutes from now, not minutes into the game).
- **Settings scroll (#281, partial, not confirmed on a device):** range sliders get `touch-action:pan-y` so a vertical swipe that
  starts on a slider scrolls the page. The other suspects were checked and are already fine: the swipe-between-tabs, pull-to-refresh
  and scroll listeners are all passive, and Settings has no backdrop blur. #281 stays open until Pete says it feels right.
- **Tests:** new page test `test_polish2_ui.py` (phone size, dark and light: heights, aria, dialog role, wording, slider
  touch-action); `test_bestbets.py` expects the new wording.
