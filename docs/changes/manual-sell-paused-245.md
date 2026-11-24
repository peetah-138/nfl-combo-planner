# Pause never blocks Pete's own Sell; automatic sales also check Pause fresh (#245)

**Section:** Safety

Pete's decision on #245: his own Sell / Cash out tap must work while Paused. For a single bet that shipped in #279 (the sale
runs while paused, with every other guard, and the sheet shows a calm note). A combo's Cash out tap (`accept_cash`) has no Pause
check, so it already works; this PR adds `t_combosell_paused.py` to lock that in (including the unknown-outcome block, rule 8).
One tightening only: `auto_sell_now` (auto cash-out, smart sell, singles pass) now also returns at once when Pause reads as on,
instead of relying on the settings flag the watcher flips. No automatic path was loosened; buys are unchanged.

ROADMAP: none
