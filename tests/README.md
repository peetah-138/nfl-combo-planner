# The check list

Everything here must pass before any push (Pete's rule). From the repo:

```
bash tests/run_checks.sh
```

It prints one PASS/FAIL line per check and ends with `ALL CHECKS PASSED` (exit 0) or `SOME CHECKS FAILED`
(exit 1). It takes about 4 minutes: the page tests run in 4 lanes side by side, each with its own copy of everything and its own port (18766–18769); set `CHECK_WORKERS` to change the number of lanes.

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
pip3 install requests pyflakes playwright ruff   # ruff is the lint step: `ruff check .` (CI runs it too)
python3 -m playwright install chromium  # the browser the page tests drive
```

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
  reaches web push, deduped; nothing trades), per-league learning
  (cut-offs, calibration, pay index; checked against the old code), the hub's read cache (`t_hubcache.py`: short
  score ttl, last-good copy, per-host backoff, warming that never keeps an entry alive on its own).
- **Simulated Mac** (`suite/macsmoke/run.py`): the real watcher for ~45 s against fake services; the log must be
  clean; and an update install into a temp home.
- **Page tests** (`suite/test_*.py`, Playwright): every screen at phone and desktop sizes; no JS errors, no
  sideways scrolling on a phone, and the behaviour each test names. `test_login_faceid` needs no web app: it renders the login page on a fake https address and checks the
  Face ID button works as the fallback when the automatic prompt is refused (iOS wants a tap). `test_motion.py` covers the makeover's motion
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
  `test_livefresh.py` covers the "Updated Ns ago" stamps and the self-redrawing game sheet (scripted game answers,
  ticking clock). `test_klive.py` runs the web app with Kalshi's live data faked from the fixtures: tennis sets/games,
  EuroLeague quarter and clock, a finished fight, a late match on Live, Games and the game sheet.

## Writing tests

- Engine tests print `PASS ...`/`FAIL ...` lines. Page tests print `PROBLEMS: ...` on any failure and their JS
  errors as `errs: [...]`; the runner fails on either, or on any traceback other than a dropped connection.
- Page tests share `test_settings.py`'s setup (everything before `with sync_playwright() as pw:`), which starts the
  web app against `test_webapp_pw.py`'s fake Kalshi.
- Numbers on Live animate (~0.65 s), page changes render on the next frame, and pages refresh themselves: wait
  for the state you expect (poll `page.evaluate(...)`) rather than a fixed sleep, or stop refreshes with
  `window.load=async()=>{}` after the page has loaded.
- Add every new test to the lists in `run_checks.sh`.
