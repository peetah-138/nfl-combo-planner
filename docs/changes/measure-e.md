# Measure E: batch order-book read (#225), live-feel measurement and next step (#21), draw side tag (#182)

**Section:** Reads and display only. What is bought or sold is unchanged (no stake, price, rule or order touched).

## #225: one Kalshi call for many order books
- `books_now` (the Build page's spreads/totals and the shadow's panel fill) used to start one thread and one
  `GET /markets/{ticker}/orderbook` per strike that was not read in the last minute (up to 8 per league for the Build
  page, 4 for the panel fill). It now first asks `GET /markets/orderbooks?tickers=A&tickers=B...` once (up to 100
  tickers per call, checked against Kalshi's live endpoint on 2026-11-26: same per-book shape, `orderbook_fp` plus
  `ticker`), then reads singly only whatever the batch did not give.
- Same numbers: each book goes through the same `_book_keep` (the one `book_depth` uses) into `BOOK_DEPTH`,
  `BOOK_LADDER` and the price recorder.
- Fails closed to the old path: a failed call, a non-200, an answer that is not a list, a book that is missing, garbled or not
  asked for is left out, and that strike is read the old single way. One book or an error never changes the answer.
- Not used on any buy, sale or hedge check: those keep `book_depth(..., max_age=0)`; `t_bookbatch.py` checks that.
- Not done: reading Kalshi's rate-limit headers. The live answer only carries `x-ratelimit-limit` (600) and
  `x-ratelimit-cost` (10 for a batch call), no "remaining", so there is nothing to back off on yet. Smart sell's own guard reads stay single (they must
  be fresh); batching those is a separate money-path decision.
- Before/after: 8 reads become 1 call for a Build line page with 8 unread strikes (4 become 1 for the panel fill).
  `BOOK_BATCH_STATS` (`batch_calls`, `batch_books`, `fallbacks`) counts them for a real before/after on the Mac;
  the age of the bid smart sell sees is not changed by this PR.
- Test: `tests/suite/t_bookbatch.py` (batch vs individual reads give identical asks and depth; 500, exception and junk answers fall back; a missing or garbled book is read singly; splits at 100).

## #21: live feel, what is measured and the next step
Already on develop before this change: the web app's score cache is 8 s while a game is live (was 45 s), the Live snapshot is served for 8 s,
and the phone shows how old the numbers are. So the "45 s score cache" finding in the issue is done.

Measured here (dev Mac, read-only log access, nothing secret printed): `tools/read_prod_logs.py` works, but neither the watcher log nor the
database carries a per-page refresh time (page build, score age, tick-to-screen), so the stage-by-stage staleness table in the issue is still
an estimate. A page build can only be timed where the app runs, with Pete's session, so it was not timed from here.

Next step (smallest thing that gives real numbers, display/log only):
1. Stamp the age of each input into the Live payload (ESPN scores, Kalshi prices, snapshot build seconds) and log one line a minute while a game
   is live ("live ages: scores 6s, prices 9s, build 2.1s, tick gap 5s").
2. Read that log for one live evening with `read_prod_logs.py --grep "live ages"`, then cut the biggest stage.
3. Only after that: the slice from the issue's plan (a push of changed numbers over the existing SSE, a ticking clock on the game sheet).

## #182: draw side is tagged
`attach_fair` now gives a 3-way game's draw side the same `sharp_line` (and `line_at`/`line_live`) as its two teams, so in low-credit mode a far
combo or idea with a draw leg is not left out when the game has an odds-service line. Panel builders still skip draws, so nothing changes today.
`t_lowcredit.py` section E runs the real path: `attach_fair` -> `_cand` -> `idea_legs_info`, and checks a game with no line is not tagged.
