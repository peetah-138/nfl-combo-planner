# Display polish: switch highlight, update pill, small tap targets (issues #196 #213 #214 #246)

**Section:** Live page, Build page, "New version ready" (#150)

Display only. Nothing here touches buying, selling, sizing, Pause or any Kalshi call.

- **Change-vs-paid switch (#196):** the buttons keep their 44px tap area, but the selected highlight is now drawn at the
  bar text's own height (a 24px `::before`), so it no longer looks taller than "Change vs paid".
- **"New version ready" pill (#213, #214):** sits above sheets (z-index 65, under toasts), so an open sheet or pushed page no
  longer hides it. It has a 44px x that hides it for that version; after about 20 s it shrinks to a small tappable dot; it
  enters slower and softer. A page that just reloaded for an update fades in (`body.verin`, skipped for reduced motion).
  `html` already paints `--bg`, so dark mode never flashes white. Release note for the next release: pages already open
  before the first release with the auto-reload need one manual reload. The "reload sooner from a busy page" idea needs
  nothing more: `verBusy()` already lets the page reload as soon as Pete is back on a list view and idle.
- **#246 small items:** `.btn.sm` (Get new price, Sell on singles) is 44px tall; "Price it" in Best bets opens the
  "More combo ideas" section if it was folded; a tappable toast is `role=button` and focusable.

Test: `test_batch_e_ui.py` (phone size, dark and light).

Refs #196, #213, #214, #246. Not done: #246's number-roll on panel stake, settled `#c=` link toast, wording nits; #112 cap
message (touches how the cap is explained, left for a money-aware pass); #195 (the hero is being changed in PR #526);
#63 and #69 are large features; #80 and #205 are already closed.
