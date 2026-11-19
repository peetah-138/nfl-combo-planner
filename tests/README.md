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
  Kalshi bets, never buying started games, smart sell for singles, the combo lab and analytics, self-tuning smart
  sell, AHL, AHL live scores (the league's feed, faked), settings cleanup (removed `sell_own`; `stop_loss` kept as a
  labelled manual override), the secure address (`t_https_push`: a fake Tailscale command line that only answers when
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
  `test_livefresh.py` covers the "Updated Ns ago" stamps and the self-redrawing game sheet (scripted game answers,
  ticking clock).

## Writing tests

- Engine tests print `PASS ...`/`FAIL ...` lines. Page tests print `PROBLEMS: ...` on any failure and their JS
  errors as `errs: [...]`; the runner fails on either, or on any traceback other than a dropped connection.
- Page tests share `test_settings.py`'s setup (everything before `with sync_playwright() as pw:`), which starts the
  web app against `test_webapp_pw.py`'s fake Kalshi.
- Numbers on Live animate (~0.65 s), page changes render on the next frame, and pages refresh themselves: wait
  for the state you expect (poll `page.evaluate(...)`) rather than a fixed sleep, or stop refreshes with
  `window.load=async()=>{}` after the page has loaded.
- Add every new test to the lists in `run_checks.sh`.
