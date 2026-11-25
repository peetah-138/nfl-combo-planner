# Sell guards: under-hold note, shared tap marker, closed-bet cache (issues #244, #400, #407)

**Section:** Selling

- **#244, the under-hold note.** `single_sell_quote` adds a `{"k": "under"}` warning when a manual single sale brings less
  than holding is worth: "That's $X under what holding is worth (about $Y). You can still sell." `_sell_under_hold` uses
  smart sell's own hold value (`single_sell_reason`, `track=False`, records nothing), or chance x contracts with smart sell
  off, and says nothing when smart sell would sell the bet anyway. It is display only: `clears`, `ok`, the checks in
  `single_sell` and Pete's tap are untouched, and a failure in the helper is swallowed.
- **#400, one seller at a time.** The web app and the watcher are separate processes, so Pete's Cash out tap
  (`go` and `singlesell`) writes a short marker (`combo_manual_sell.json`, `manual_sell_mark`) and the automatic sellers
  (`auto_sell_now`, `smart_sell_singles`, `autosell_pass`) skip that bet while a fresh marker (under `MANUAL_SELL_MAX` = 90 s)
  stands, and check it again next round (a skip is logged). One direction only: the tap never reads or waits on the marker,
  a marker that cannot be written never holds the tap up, and a crashed tap's old marker counts for nothing. No new sale is
  made; an automatic sale only waits.
- **#407, closed-bet detail.** `api_closed` in the web app now answers from a small per-ticker cache (20 s, 4 s for "not
  found", at most 64 entries) in front of `api_closed_work`, the original lookup, so a page refreshing it does not rescan
  the sell log and hold the account lock per request. The ticker is checked before the cache. Same answers, fewer scans.

Tests: `t_guards2.py`.
