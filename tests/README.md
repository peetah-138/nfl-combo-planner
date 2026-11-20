# The check list

Everything here must pass before any push (Pete's rule). From the repo:

```
bash tests/run_checks.sh
```

It prints one PASS/FAIL line per check and ends with `ALL CHECKS PASSED` (exit 0) or `SOME CHECKS FAILED`
(exit 1). It takes about 4 minutes: the page tests run in 4 lanes side by side, each with its own copy of everything and its own port (18766–18769); set `CHECK_WORKERS` to change the number of lanes, and `CHECK_PORT_BASE` (default 18766) to move the ports when two runs happen at once.

## Safe on the Mac that runs the real app

- It copies the suite to a temporary folder and runs there. It never reads or writes `~/combowatch`, the real
  history database, settings, or your Kalshi key. The engine under test gets a throwaway fake key.
- The page tests start their own web apps on ports **18766–18769** (the real Combo Hub uses 8765/8766), so a test can
  never reach the real app. If any of those ports is busy, the run fails instead of guessing.
- Kalshi, ESPN and GitHub are faked; anything that slips past the fakes carries a throwaway key Kalshi rejects.
  Nothing is bought or sold.

## One-time setup on a Mac

```
brew install node                       # checks the web app's JavaScript
```

The Python is picked by `tests/python_env.sh` (used by `run_checks.sh` and `dev.sh`), which prints the interpreter, its
SQLite version and whether it links Apple's `/usr/lib/libsqlite3.dylib`. It needs **Python 3.10 or newer**: Apple's
Command Line Tools Python 3.9 uses the system SQLite, which segfaults on macOS 26.4 ("Python quit unexpectedly",
GitHub #68). Order of choice:

1. `$CHECK_PYTHON`, if you set it (a name or path of an interpreter that has `requests pyflakes playwright`; it warns if it is older than 3.10).
2. `~/combowatch/.venv/bin/python`, only if it is 3.10+ and already has all of those (nothing is ever installed there).
3. `.venv-tests/` in the repo (git-ignored). **First run builds it by itself** from `python3.13/3.12/3.11/3.10` found on
   PATH, Homebrew, pyenv or uv (`pip install requests cryptography pyflakes ruff playwright`, then
   `playwright install chromium`). To do it by hand: `python3.12 -m venv .venv-tests && .venv-tests/bin/pip install requests cryptography pyflakes ruff playwright && .venv-tests/bin/python -m playwright install chromium`.
   Set `CHECK_VENV_NO_CREATE=1` to stop it building, `CHECK_VENV=/some/path` to put it elsewhere (e.g. shared by worktrees).
4. `python3` on PATH if it is already 3.10+ with those modules (that is how CI runs; tried before step 3 builds the venv), else plain `python3` with a printed warning (expect SQLite crash dialogs on macOS 26.4).

`CHECK_PORT_BASE` must be 1024 or more and never near 8765/8766.

Lint: `.venv-tests/bin/python -m ruff check .` (CI runs `ruff check .` too).

Optional: put the strings that must never be committed in `SECRET_PATTERN` (an extended-regex alternation) in
your shell profile, not in any file in this repo. With it set, the run also greps the repo for them. Use the same
pattern in a local `.git/hooks/pre-commit`.

## What's in it

- **compile, JavaScript syntax, undefined names, secret grep.**
- **Engine tests** (`suite/t_*.py`): review fixes, spread/total game matching, restart and extras, your own
  Kalshi bets, started games (pre-game-priced bets never bought once a game starts; `t_live_panel.py`: games under way only when priced live on a fresh score, the switch, recheck before buying, refusals are skips), smart sell for singles, the combo lab and analytics, self-tuning smart
  sell, AHL, AHL live scores (the league's feed, faked), tennis/EuroLeague/UFC scores from Kalshi's public live data
  (`t_kalshi_live.py`: real response shapes in `fixtures/kalshi_live.json`, sides, caching, backoff, and a source check
  that no buy/sell function reads it), display-code robustness (`t_robust.py`: a malformed or slow live feed never stops or delays auto
  cash-out, caches pruned, the web app's capped tap lock and shared request limit), settings cleanup (removed `sell_own`; `stop_loss` kept as a
  labelled manual override), the learned loss cut's guards (`t_cutloss.py`: the same guards for combos and singles, never borrowed, held cuts
  logged, the replay only cuts where the guards held, Pause/Ride it out win), the auto-hedge guards (`t_hedge.py`: fresh score, no break, locks in at least the cost, confirmed over 3+ minutes, fresh order-book price, the cap, Pause, an unknown outcome marked check and never retried, held hedges counted), the stop-loss guards (`t_stoploss.py`: late enough, fresh score, no break, big fall,
  confirmed over 3+ minutes, per-league learning that never loosens on borrowed data, off/paused never sells), the secure address (`t_https_push`: a fake Tailscale command line that only answers when
  started like launchd would, state and log for every failure, retry loop) and web push coverage (every `push()` also
  reaches web push, deduped; nothing trades), notification tap targets (`t_push_target.py`: `/` not `/app`, the service worker maps legacy
  `/app` payloads, the hub redirects page navigations to `/app` and never answers a page with an empty file, API routes unchanged), per-league learning
  (cut-offs, calibration, pay index; checked against the old code), the hub's read cache (`t_hubcache.py`: short
  score ttl, last-good copy, per-host backoff, warming that never keeps an entry alive on its own), the panel rebuild on
  request (`t_rebuild.py`: flag, per-sport progress notes, done/why, drafts only, no started game, the watcher's
  `rebuild_loop` picks a request up within seconds), buying right after approval (`t_buynow.py`: no lead time,
  Approve/Add wake the Mac's `panel_loop` within seconds, the price recheck still skips or swaps, start rules, Pause,
  unknown outcome = check never retried, no double buy from passes at once, live bets skipped once switched off), every panel bet naming its game (`t_panelgame.py`: singles, sell-early, each combo leg, spreads/totals, notifications, saved drafts),
  Kalshi's order book shapes (`t_orderbook.py`: the new `orderbook_fp` dollar-string answer and the old `orderbook`
  cents answer read identically, from real fixtures `fixtures/kalshi_orderbook.json`/`kalshi_market.json`; garbage never
  raises; the 6¢ gap rule; a single/spread/total panel buy, a hedge re-read and a smart-sell single sale against the
  fake Kalshi, which serves the new shape by default: `fakenet.BOOK_SHAPE`), Kalshi's V2 orders (`t_orders_v2.py`:
  every price/count conversion incl. 1¢/99¢, NO prices, fractional counts and reduce-only IOC sells; the fake order
  desk `fakenet.ORDERS` in V2 / legacy / both / gone modes; 410 = clean skip, timeouts/5xx = check and never resent,
  no double buy on a repeated tap, the once-a-day push when Kalshi retires something; fixtures from the OpenAPI spec in
  `fixtures/kalshi_orders_v2.json`).
  Results dated by when the money moved (`t_realdate.py`, issue #91): `sunday_of` rounding shared with `week_of`,
  `realized_ts`/`realized_buckets` precedence (cash-out sell > settlement > the Mac's detection time > the game date),
  a cashed-early bet bucketed by its cash-out date in both day and week, day and week always from one date in one tz,
  and `_fetch_account` capturing the last sell fill as `cashed_at` and a settlement time as `settled_at`.
- **Simulated Mac** (`suite/macsmoke/run.py`): the real watcher for ~45 s against fake services; the log must be
  clean, a requested panel rebuild must run; and an update install into a temp home.
- **Page tests** (`suite/test_*.py`, Playwright): every screen at phone and desktop sizes; no JS errors, no
  sideways scrolling on a phone, and the behaviour each test names. `test_login_faceid` needs no web app: it renders the login page on a fake https address and checks the
  Face ID button works as the fallback when the automatic prompt is refused (iOS wants a tap). `test_haptics.py` covers Settings › Test haptics (each method runs inside its own tap, the iPhone switch is on screen, the on/off switch). `test_motion.py` covers the makeover's motion
  layer: every visible clickable element on every screen has press feedback and a haptic, the haptic patterns are
  distinct, the push transition (slide, dim, skeleton, Back, swipe back), the hero chart (Day/Week, scrub readout and
  ticks) and rolling numbers, plus a reduced-motion run. It seeds its own pulse history in the lane's throwaway database.
  `test_makeover2.py` covers phase 2: live Games cards with singles/spreads (API and page), the score pulse and its
  haptic, scrubbing the game chart, the Sold moment (tap, failed sale, smart sell's calm card from a fake sell log),
  small win vs big hit, Results profit bars (scrub ticks, tap for bets, Day/Week) and the loading skeletons.
  `test_makeover3.py` covers phase 3 at phone (dark and light) and desktop: the press/haptic audit on every screen
  (Build's full board and panel and an open sheet included), the reconnecting banner and Back online, the error card
  with Try again, header collapse, pull to refresh on every tab, the keyboard-aware sheet, Let it ride's detents,
  Mac buttons reporting back (and Update now asking first), Build's rolling prices, pick pop, slip bar, quote
  countdown and Buy anyway, folds, panel sparklines and the arming Approve, Results' skeleton and tabs, the recap
  streak note, light mode, the login page's motion and haptics, and reduced motion. Every action call is faked.
  `test_rebuild_ui.py`: the empty panel card (no 10-minute promise, Look now), live rebuild progress redrawn in place,
  the new panel dropping in by itself, and the "nothing found, here's why" card.
  `test_loadwidth.py`: a frame-by-frame sampler on a phone for 2.4 s after every tab switch and a game page push (dark and light): no
  element past the screen's right edge, no line past its card, `<main>` keeps normal wrapping and text size (the `arrived` class on
  `<main>` once reused the name `fresh`, the "Updated Ns ago" stamp, and every new screen drew too wide for 1.6 s).
  `test_livefresh.py` covers the "Updated Ns ago" stamps and the self-redrawing game sheet (scripted game answers,
  ticking clock). `test_klive.py` runs the web app with Kalshi's live data faked from the fixtures: tennis sets/games,
  EuroLeague quarter and clock, a finished fight, a late match on Live, Games and the game sheet.
  `test_realdate.py` (issue #91): a combo cashed out early (game Sunday Nov 22, cashed Wed Nov 18) buckets by its
  Nov 18 cash-out, not the game date, in both the Profit-by-day and Profit-by-week bars, and the day and week detail
  sheets show the buy date and the cash-out date.

## Writing tests

- Engine tests print `PASS ...`/`FAIL ...` lines. Page tests print `PROBLEMS: ...` on any failure and their JS
  errors as `errs: [...]`; the runner fails on either, or on any traceback other than a dropped connection.
- Page tests share `test_settings.py`'s setup (everything before `with sync_playwright() as pw:`), which starts the
  web app against `test_webapp_pw.py`'s fake Kalshi.
- Numbers on Live animate (~0.65 s), page changes render on the next frame, and pages refresh themselves: wait
  for the state you expect (poll `page.evaluate(...)`) rather than a fixed sleep, or stop refreshes with
  `window.load=async()=>{}` after the page has loaded.
- Add every new test to the lists in `run_checks.sh`.
