# Live and Results catch up right after a sale (issue #242)

**Section:** Live page (the "Fast live numbers" paragraph) and Results page

Pete: "The live page doesn't update for a while after smart sell sells something. Same with results."

**Why it lagged.** A sale is made by the Mac watcher, but the pages are drawn by the web app, a separate process with
its own caches: its copy of the Kalshi account (`fetch_account`, kept 60 s for Live and 30 s for Results), the open
singles (30 s), the Live snapshot (8 s with a game on, 30 s otherwise), the scoreboard (`profit_board`, 2 min) and the
hero chart's profit line (`PNL`, 20 s). Nothing told the web app a sale had happened, so Live could show a sold bet for
over a minute (the Sold sheet even appeared on top of a list that still had the bet, because `sales` is read fresh
from the sell log while the list came from the old snapshot). Results never refreshed by itself at all: the page only
re-read it when you opened the tab, since Mac ticks and the 12 s timer only reload Live and Games.

**The fix (display and caches only).**
- Engine: `money_mark()` writes a small stamp, `combo_money.json` next to the engine (git-ignored by `combo_*.json`;
  only its time matters, `money_seen()`). It is written for every sale-type sell-log line (`log_decision`:
  sold, hedged, check, failed, hedge check/failed) and, after every direct account read, when anything a screen shows
  changed (`money_note`: a combo's status/cost/back/pays, any position, the balance), which covers fills, panel
  buys, Pete's own Kalshi trades and settlements. A process's first read only remembers. Never raises, never waits.
- Hub: the `account` op reads Kalshi fresh (`max_age=0`) when the stamp is newer than its cached copy, so the web
  app can't re-cache the pre-sale account.
- Web app: `money_check()` (one file stat) drops its account, singles, scoreboard and profit-line caches when the
  stamp moves; `api_live` rebuilds when the stamp is newer than the moment the snapshot on hand began building
  (`LIVE["from"]`), the warmer does it ahead of the page while a page is open, and `api_results` checks it first.
- Page: each Mac tick carries the stamp (`{"kind": "tick", "money": ...}`); `moneyTick` re-reads the screen on show
  when it moves: Live/Games, and now Results too. A finger on a chart or an open sheet waits for the next tick. A Sold
  moment for a sale the Mac made re-reads Live 3 s later (`soldReload`), even under the Sold sheet.

Nothing here buys, sells, sizes or decides anything: no change to smart sell, auto cash-out, hedges, the panel, caps,
Pause, rule 8 or the tap lock; the trading loop never waits on it (a stamp is one small file write). "What's working"
(`analytics()`, 10 min) is unchanged; Results' main numbers never came from it.

Tests: `t_moneyflag.py` (stamp rules, never raises, git-ignored name, no order code), `test_moneyrefresh.py` (through
the real web app: a sold combo stays on Live without a stamp and leaves on the next read with one; Results re-reads;
no stamp = no rebuild; the page's tick, same-stamp, open-sheet and Sold-moment behaviour).

ROADMAP: none
