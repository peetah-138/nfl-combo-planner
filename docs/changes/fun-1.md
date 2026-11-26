# Live hero shows Kalshi's value; fun upgrades (issues #413, #140)

**Section:** Live page / Delight (display and feel only; nothing here touches buying, selling, prices, valuation math, Pause or caps)

Refs #140 #413

- **Live hero (#413):** the big hero chart is gone (`heroChart`, `wireChart`, `setRng`, `pulseWeek`, `plMoney`, `plCol`, its CSS, and
  `test_heropnl.py`). The big number is now Kalshi's own value, labelled "Worth now on Kalshi", with our "If sold now" estimate small
  beside it. The engine has no Kalshi figure, so `kalshiNow()` in `live.js` builds it: each open combo's `cost` (Kalshi marks a combo at
  its last trade, which is your buy price) plus each open single's `worth` (contracts x best bid). `cash_now` and every valuation
  number are unchanged. `cost` includes fees, so this can read a little high next to the Kalshi app. The change line under it is
  Kalshi's value minus what is staked.
- **Result moments (#140 a):** Bought, Sold, Big hit and Approved (`panelApprove` now ends on a sheet) have no auto-close timers. A good
  result ends on a big real `<button class="nice">` labelled Nice (44-64px tall, so the see-through switch in `haptics.js` still covers it
  and a finger gets the real tap tick); "Check Kalshi" and losses end on OK or Done. Bets are named by their legs (`momName`), never "Combo N".
- **Score burst (#140 b):** a changed score glows its Live row (`.trow.burst`) and pops the digits. The burst is kept in `S.burst` with an
  expiry (Live repaints every tick), and is off under reduced motion. Games keeps its existing glow and digit pop.
- **Button errors (#140 c):** `btnFail(host,msg,btn)` shakes the button and shows the reason under it (`.berr`, `role="status"`, 15 s, survives
  repaints through `S.berr` and `paintErr()`), replacing the 6-7 s toast for Buy, Buy anyway (longshots), Approve and Add. If the button
  is gone it falls back to the toast. An unknown buy outcome (`check`) still shows "Check Kalshi" in the toast and is never retried (rule 8).
- **Tests:** new `test_fun1_ui.py` (hero number and no chart, score glow and its survival, Nice button size and tap, no auto-close, inline
  error outlasting the revert, reduced motion); `test_motion.py` lost its hero-chart checks.

ROADMAP: none
