# Display and wording batch: Smart Buy card, hero change pill, expected-profit words (issues #290 #195 #518)

**Section:** Results page (Smart Buy card), Live page (hero), Build page (stake row)

Display and wording only: no buy, sell, sizing or setting is touched, and no new switch was needed.

- **#290 Smart Buy card, fewer numbers per league** (`sbLine` in `watcher/spa/results.js`). Each league now shows its status line
  and ONE progress line, `Bigger stakes, on paper: 34 of 50 settled · +$8.20 · 60% of days up` (a league with nothing settled shows
  just `0 of 50 settled`; a met bar adds `bar met, not switched on`). The old fold with CLV and "skips helping" behind it is gone:
  those two now appear only as a `Held back: ...` line when they are what holds the league back (CLV below zero: "losing to the
  closing price"; skips not helping: "its skips are not helping yet"), and never once the bar is met. "beats plain" was already
  "skips helping" and is no longer printed. The grey text on these lines uses `--sub` (`results.css`) for better contrast.
- **#195 Hero change pill stops rolling when it cannot move** (`heroLive` in `watcher/spa/live.js`, `rollNums` in `common.js`). The
  big number and its pill follow Kalshi's own value (combos at cost, singles at the bid), so they can only move with a single's
  price: with no single open the pill is plain text, not a rolling, flashing number. The "If sold now" estimate keeps its rolling
  only when some estimated combo was priced live (`offer_live`); otherwise it carries `data-still="1"` and `rollNums` skips the roll
  and flash for such numbers. The freshness stamp beside the label is unchanged.
- **#518 Delight nits on the calibrated-profit card.** Item 1 (a "recommended" chip beside a negative calibrated profit) was already
  fixed in release 507's review: `stakeCtl` says "no edge" when the shown profit is not positive; a test covers it. New here: the
  wording "on your record, before fees" is now "based on how your past bets did, before fees" (`build.js`, both places), and the
  exit-route and "held back as suspect" log lines name the combo by its legs (`legs_log_name`, built on `combo_names`) instead of
  joined tickers. Not done: item 4 (a single's break episode never closed) is #316 item 1 and belongs with the money-path work.
- **#439 (Overlap "Add anyway" loading state): already there.** `ovAdd` has shown a spinner and "Showing..." in the button, at a
  fixed width, since #369/#368; nothing added.

Tests: `t_queue_ui3.py` (log names, source checks), `test_queue_ui3.py` (phone, dark and light: pill, still estimate, Smart Buy
lines, wording), and the updated `t_tap_polish.py`, `test_analytics.py`, `test_evcal_ui.py`.
