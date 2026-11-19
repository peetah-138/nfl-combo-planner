# Brief for Claude: the Kalshi combo planner

You are picking up a long-running project with Pete. This file holds the decisions, rules and context from the
earlier sessions (up to version 2026.11.18.118). Read it all before changing anything. When something here
conflicts with what Pete tells you now, Pete wins: update this file in the same change so it stays true.

## What this is

A betting planner for Kalshi (prediction markets): it finds sports bets priced better than their real chance,
builds combos (Kalshi "multivariate" parlays), buys on Pete's approval, and sells smartly during games.
Real money is involved. Pete uses it daily.

- `nfl_combo_planner.py` — the engine (one big file). It runs in three places:
  - **Pythonista on Pete's iPhone** (the original app; still works as a backup, talks to the Mac when it can).
  - **The Mac watcher** loads it as `E` (main loop: live combos, auto cash-out, smart sell) and as `H`
    (`odds.engine()`, the "shadow": quotes combos to learn, builds the daily panel, buys panel bets, the lab).
  - **The Combo Hub web app** (`--webapp`, 127.0.0.1:8766) loads it as `A`. The hub on :8765 proxies to it with a
    session cookie plus the `X-CW` token. Pete opens Combo Hub on his phone over Tailscale (and the
    `https://<mac>.<tailnet>.ts.net` secure address for Face ID passkeys and push notifications).
    The SPA is the only UI there: the old "Classic screens" (the phone UI drawn in the browser through a bridge) and the
    header "⋯" menu are gone. Settings is a tab, "Reload the page" is a button in Settings › The Mac, and pull-to-refresh
    reloads data. The web-app copy of the engine keeps no-op stand-ins for Pythonista's modules so it still imports as
    "on the phone"; the real Pythonista app is untouched.
- `watcher/combo_watcher.py` — the Mac watcher, the hub, the web app, and the whole web UI: the single-page app is
  the raw string `SPA = r"""..."""` (HTML/CSS/JS in one string), the login page is `LOGIN_HTML`.
- `watcher/install_mac.sh`, `setup_wizard.py`, `wizard_window.js`, `install_pi.sh` — installers.
  The Raspberry Pi is an **alerts-only backup; it never trades**.
- `version.txt` — what the Macs update to.
- History lives in SQLite `~/combowatch/combo_history.db` (WAL; many processes; use `store_x`/`store_rows`,
  and `panel_tx` for read-modify-write of panel rows). Settings and state are JSON files next to the engine
  (`combo_*.json`, `held_events.json`). **None of these are ever committed.**

## Hard rules (never break these)

1. **The repo is public.** Never commit keys, key IDs, ntfy topics, emails, settings, history or session files.
   `.gitignore` covers `*.db*`, `*.pem`, `*.key`, `combo_*.json`, `combowatch*.json`, `hub_sessions.json`,
   `watcher_conf.json`, `held_events.json`. Before every commit, grep the staged diff for secrets. The cloud
   session used a local `.git/hooks/pre-commit` that refuses known secret strings; set one up on this machine too.
   Ask Pete for the strings it should block, and **never write them into any tracked file** (including this one).
2. **No new automatic money movement** without Pete explicitly opting in. Existing opt-ins: auto cash-out (with
   smart sell, take profit, lock-in, learned loss-cutting), auto-hedge (≤ $100 a hedge), killer deals,
   standing orders, approving the daily panel, and "Add to today's panel". Everything else buys or sells only on
   his tap. The Pause switch must always be respected. The Pi never trades.
3. **Each device has its own revocable Kalshi key.** The Pi never accepts keys over sync.
4. Don't touch the Vercel project "cynserus" (unrelated business). Repo write access stays with Pete.
5. Latency arbitrage is not pursued.
6. **Full auto with $300** (it picks, times, buys, sells alone) only after the paper panel clears the gate:
   50+ settled bets, ahead overall, most days up (≥ 55%), CLV ≥ 0. Pete chose 50.
7. Never price or buy a combo other than the one on Pete's screen (the quote API checks the leg tickers the page sends).
8. A buy whose outcome is unknown is marked "check" and **never retried** (no double buys).

## How Pete wants work done

- **Check thoroughly before pushing.** He was fed up with bugs reaching him. Every release goes through the full
  check list (see Testing). If a check fails, fix it and rerun everything; never push on a partial pass.
- **Code and security reviews:** run both before every PR and every release, and fix every finding and warning.
- **No rigid never/always rules.** Start from sensible defaults and let the data tune them over time,
  **per league, not just per sport** (college basketball ≠ NBA, college football ≠ NFL, each soccer league apart,
  AHL ≠ NHL). Leagues short on data borrow from their sport, then from everything.
- **Delight matters.** He wants the app to feel as good as Kalshi's own (haptics, animation, transitions) so friends
  would want to use it. For visual changes, send screenshots/a short clip before shipping when practical.
- Plain English in the app and in replies. Keep screens simple: filter out noise, surface statistically good bets.
- He uses the app on his phone and is often away from the Mac. Remote-friendly controls matter
  (e.g. Settings › The Mac › "Check for an update now").

## Git workflow (Git Flow)

- **`main` is what Pete's real Mac and phone run.** A commit on `main` auto-updates them within ~10 minutes (they
  read the newest commit by SHA via the GitHub API, so GitHub's raw-file cache can't hold them back), and the
  app can place real Kalshi orders. Never push to `main` directly.
- **`develop` is the integration branch.** Work on a short-lived branch from `develop`: `feat/…`, `fix/…`,
  `chore/…`. Commit at logical points with clear messages, and open a PR into `develop` at logical points without
  being asked. Squash-merge once the CI check `checks` is green.
- **Every PR must pass lint (`ruff check .`) and the full `bash tests/run_checks.sh`.** CI runs both
  (`.github/workflows/ci.yml`, job `checks`); run them locally first. Fix lint findings in the code; don't
  silence them. Run code review and security review before opening the PR and fix everything they raise.
- **Releases:** a PR from `develop` into `main`, merged as a **merge commit** (not squashed). It must carry the
  version bump (below). Open it, but **never merge it without Pete's explicit go-ahead in that conversation.**
- **Version numbers** are unchanged: `YYYY.MM.DD.N`, currently `2026.11.18.118`. Each release bumps N (N keeps
  counting up, it isn't reset) in all three places, which must match: `VERSION` in
  `nfl_combo_planner.py`, `WATCHER_VERSION` in `watcher/combo_watcher.py`, and `version.txt`. Only the release PR
  bumps it; feature PRs don't.
- **Housekeeping:** `git pull` `develop` and `main` at the start of every session and after every merge. The
  orchestrating session manages branches and worktrees (Claude worktrees live in `.claude/`, git-ignored) and
  deletes stale worktrees and merged branches without asking. Keep this file current so every session knows what
  changed.

## Releasing

1. Branch is `develop`, fully merged and green. Bump the version in all three places (see above).
2. Run code review and security review on the release diff; fix every finding.
3. Run `bash tests/run_checks.sh`. All must pass. Add a test for every change (see `tests/README.md`).
4. Commit (no `__pycache__`) on `develop` and push it. Wait for CI (`checks`) to go green.
5. Open the `develop` → `main` PR (merge commit). Merge it only after Pete says go. The Macs then update within
   ~10 minutes; Pete can also tap "Check for an update now". An update restarts the watcher (launchd brings it
   back).

## Testing (the check list)

Run `ruff check .` (config in `ruff.toml`: correctness rules only, no style rules) and `bash tests/run_checks.sh`
before every push; the latter must end with `ALL CHECKS PASSED`. CI runs both on every PR. See `tests/README.md`
for the one-time Mac setup (node, pyflakes, ruff, playwright + chromium). It runs in a temp folder with fake services and a fake
key, and its web apps use ports 18766+ (4 lanes in parallel, ~4 minutes), so it can't touch the real app or money. What it covers:
- Both files compile (Python 3.10), `node --check` on the SPA's script and on `LOGIN_HTML`'s script,
  pyflakes for undefined names, secret grep.
- Engine tests (each prints PASS/FAIL lines): review fixes, lines (spread game matching), restart, extras,
  own-bets, started-games, smart sell for singles, combo lab, self-tuning, AHL, AHL live scores, per-league learning, the secure address and web
  push (`t_https_push`: fake Tailscale CLI, push dedupe) and the login page's Face ID tap fallback (`test_login_faceid`).
- A simulated Mac run (fake Kalshi; the log must be clean) and a simulated update install (copies the watcher to a
  temp home; must never touch the repo files).
- Playwright page tests at phone (390×844) and desktop sizes for every screen: no JS errors, no sideways scroll on a
  phone, and the specific behaviour (taps, filters, toggles, numbers). Beware timing: numbers animate (~0.65 s),
  view transitions render on the next frame, and the page auto-refreshes; wait for state rather than fixed sleeps.

## The product, by area (decisions and current behaviour)

### Fair prices and data
- "Fair" = sharp sportsbooks de-vigged (free sources; The Odds API free plan; no paid odds). Calibrated by Pete's own
  record per league and chance band (`calib_fair`, shrink n/(n+300)): the sport's nudge as before, and a league
  inside a sport (each soccer league) moves from its sport's nudge toward its own record by the same n/(n+300), so
  a league with no games gets exactly its sport's. A sport with no games in a band keeps the books' chance (no
  "everyone" level here yet; see ROADMAP). Leagues marked `require_line` need a sportsbook line (Kalshi alone
  isn't trusted there).
- Live scores from ESPN's free scoreboard (none for EuroLeague, UFC, tennis). The AHL isn't on ESPN: its scores,
  periods and clocks come from the league's own public score feed (the JSON theahl.com's widgets read; HockeyTech,
  no login; `_fetch_feed_scores`, light polling), with the same cache and last-good-copy fallback as ESPN.
- Leagues: NFL, NBA, NHL, AHL, college football, men's and women's college basketball, EuroLeague, UFC, soccer
  (EPL, La Liga, Serie A, Bundesliga, Ligue 1, MLS, Liga MX), ATP tennis, and "Mix" (cross-sport).
- AHL: Kalshi `KXAHLGAME` (event codes include a start time, e.g. `26NOV191900HERCHA`), odds `icehockey_ahl`,
  require_line, hockey shapes, live scores from the league feed (Kalshi's team codes can differ from the feed's,
  e.g. CHA/CLT, so `AHL_ALIAS` maps them; names are matched too).

### The daily panel (Build page, top)
- Up to ~10 bets a day (size scales with games: 6–14), across combos, single games, spreads/totals and
  sell-early favorites, chosen together to **maximize the chance the whole day finishes ahead** (bigger profit is a
  tie-breaker). Sport-aware: NFL weekly slate (with time-slot combos and checkpoints, small NFL priority on NFL
  days), NBA/NHL daily, bigger panels on heavy nights. Overlap rules: both sides of one game only when both are
  fairly priced, ≤ 2 bets per game, one straight bet per game, spreads/totals ≤ 30% of the panel.
- Combos need a predicted price ≥ the cut-off: **starts at 95% of fair, self-adjusts weekly per league and size,
  floor 85%, no ceiling**, counting the whole trip (value at game time × exit factor), learning from skipped quotes,
  moving only on solid data. Pete considered 80% and agreed 95% start; the combo lab tests lower levels on paper.
  Borrowing (`_cut_level`, `combo_cutoff(code, n, legs)`, file `combo_cutoffs.json`): a league inside a sport
  (e.g. `epl:2`) uses its own level once it has 30+ quotes or has moved, starting from its sport's; until then it
  follows its sport's live (`soccer:2`, the old keys, read exactly as before). A sport with no entry borrows
  everyone's (`all:2`) once that has 30+ quotes, and a sport new to the file starts from that level.
- The panel's sport tie-break (`sport_pay_index`/`pay_index_of`) uses a league's own pay index once it has 10+
  quotes, else its sport's. Sizing reads league results through the calibrated chance.
- Pete approves once; the Mac buys each bet at a good time before its game (~45 min; combos at their best lead
  time), rechecks price, swaps in a similar bet or skips. Never buys or approves a game that has started; drafts
  drop started games. "Build a fresh panel" rebuilds within a minute. After approval the Mac keeps looking
  (every ~2.5 min for sports with games within 2 h) and offers "🆕 New since you approved" extras (one
  notification each, Add button, inside the remaining budget). A skipped/swapped bet can come back as an extra.
- Sizing: quarter Kelly on a shrunk edge, $2 minimum, ≤ 5% of the base per bet; base grows ≤ 10%/week, drops
  immediately; half of each month's profit is set aside (reminder until Pete says he moved it).
- Paper panel runs alongside (the $300 gate). The **combo lab** paper-buys up to 3 combos a day in each band
  (80–85, 85–90, 90–95, 95–100, 100+% of fair) from real quotes, $5 each, separate from the gate.

### Selling: smart sell everywhere
- Smart sell runs on **every bet**: combos, singles, spreads, totals — the app's and ones Pete places on Kalshi
  himself — each with a per-bet switch on Live: "🤖 Smart sell" / "✋ I'll sell it" (`combo_selfsell.json`).
  It only acts while Auto cash-out is on; daily cap applies; singles sell into the order book (IOC at the bid,
  reduce-only) and skip thin markets (bid/ask gap > 6¢), bets with a resting sell, and games already over.
- Rule: sell when the offer beats the risk-adjusted value of holding,
  `max(q·P − λ·P·√(q(1−q)), floor × cost)`, q ≥ 0.5; λ from the sport's swing and time left (×1.3 at a slate
  checkpoint); lock-in after a big run-up drops 20%; take-profit % optional (default off — the old 75% default was
  migrated off). There is **no 80% floor** (removed at Pete's request).
- **Self-tuning, per league** (weekly, `smart_tune`): replays settled bets on their recorded game prices with
  nearby settings and moves one small step toward what clearly did better (≥ 2% of stake, 30+ bets): profit floor
  (starts 1.5×, 0.1 steps, 1.2–2.0), risk weight, and a learned loss cut (off until a league's record shows
  selling a sliding bet beats holding). On a tie, the smallest change wins. Results › Selling shows each league's
  settings and why they last changed.
- Settings: `sell_own` (old "include bets I place myself") is removed; the per-bet switch replaced it. `stop_loss` stays as a
  labelled **manual override** ("Manual override: sell at a loss when a game turns", off by default, separate from the
  learned per-league loss cut). Pete to confirm whether to keep or remove it.
- The **Let it ride** slider sets boldness: Cautious sells sooner, Bold later, "Ride it out" turns smart sell off.
  It also still drives the original combo cash-out plan (sell when the offer beats waiting another game).
- Bets Pete places on Kalshi himself are tagged "You, on Kalshi" (the app records every buy it makes; everything
  held when tracking began counts as the app's). The panel avoids games he already bet himself.

### Live page
- Hero card: worth now if sold (rolling number), change vs what's in, a chart of open-bet worth (`pulse` table),
  riding / staked / chance one pays / most it can pay — covering combos **and** singles/spreads.
- Hero chart (`heroChart`/`wireChart`): Day (16 h, from `/app/api/live`) or Week (`/app/api/pulse?h=168`, read-only,
  pulse keeps 30 days) via a plain-text switcher (remembered, `cw_rng`); gradient area, glowing end dot, the staked
  amount dashed; draws in left to right when the range changes. Press and drag to scrub: a line and dot follow the
  finger, the big number and change pill show that moment's value, a time readout sits above, each point crossed ticks
  a haptic; release restores the live numbers. Live refreshes wait while a finger is on it (`S.scrub`).
- Combos table, "Single bets & spreads" section (tap opens the game page: score, chance it covers, your bets on
  that game), Settled view with profit/loss pills, outcome/sport/sort filters and a net total. Offer and chance
  numbers roll frame by frame to new values and the chance bars slide (`rollNums`, `data-num`/`data-bar`).
- Game and combo detail pages **push** in Kalshi-style (`pushOpen`/`pushFill`): the page slides in from the right in
  270 ms (ease-out) while the page behind slides a third left and dims; flat skeleton blocks show until the content
  swaps in (never before the slide ends), then the content fades/staggers in. A sticky Back bar, or swipe right,
  goes back. Confirmations stay as bottom sheets (`modal()`); switching modes never animates a half-moved sheet.
- Loading shows a hero-shaped skeleton; an empty Live says "Nothing riding right now" with a button to today's bets.
- Pull to refresh, score-change row flashes, celebrations when a bet wins.
- **Honest status for sports with no live score source** (tennis, UFC, EuroLeague, AHL): the engine's `run_status`
  says "Started 42 min ago · no live score" while inside a sport-typical length (`DONE_HOURS`), then "Probably
  finished · started 5h ago, waiting on Kalshi" (legs stop looking like they are winning/losing; the Games tab files
  them under "Probably finished"). Display only: `pick_state` and all money logic are unchanged, the pick stays open
  until Kalshi settles it. Live scoring for those sports is a separate roadmap item (GitHub #25).
- **Fast live numbers (display only, GitHub #21).** The web app keeps a league's scores for 8 s while any game is
  live (30 s when none; `A.SCORES_MAX_AGE` in `webapp_main`, the old default was 45 s) and rebuilds the Live snapshot
  when it is older than 8 s (30 s idle) and serves the **fresh** one, not the one-refresh-behind copy; if a build
  fails or is stuck behind another job it serves the last good copy and retries in ~5 s. The warmer keeps it ready
  (~6 s while a page has asked in the last 90 s). The hub's read cache (`HubCache`) keeps ESPN scores 6 s, prices
  12 s, series 120 s, warms only what was asked for recently (quick) and drops entries nobody has asked for in 30
  min; a host answering 429/5xx or timing out is backed off per host (Retry-After honoured, doubling to 60 s) while
  the last good copy is served. **None of this touches trading:** the watcher's `E`/`H` loops, smart sell, auto
  cash-out, the panel and every buy/sell decision read their own data on their own timing.
  `/app/api/live`, `/game` and `/games` carry `fresh` (`now`, `built`, `scores` = age of the live leagues' scores,
  `fast`); the page shows a small "Updated Ns ago" stamp (Live hero, Games tab, game sheet) that counts on its own
  and goes red after a minute. The open **game sheet redraws itself**: on every Mac tick, and on a 2 s timer when the
  link is down; it repaints only when something changed and keeps its scroll place. Between updates the clock counts
  down by itself, only for NBA/college basketball/NHL/AHL, and only once two polls showed it running (a clock that
  hasn't moved for 25 s is treated as stopped); football and soccer show the last value. Tests: `t_hubcache.py`,
  `test_livefresh.py`.
- The Winning now / Losing now / Tied / Won / Lost legend sits right above the combos table and lists only the
  states currently on screen.
- Toasts always fade: each has a deadline swept every second (and on touch/scroll/focus), is hidden after the fade and
  dismisses on tap. A Buy idea whose game Kalshi no longer lists shows a calm "not available" card and drops off.

### Build page
- Panel on top, sport chips (All = mix board), "Build your own": the games board (live score, period, clock for
  games under way), spreads & totals, more combo ideas — each section folds separately (remembered).
- Get price → green "Buy" when it clears the cut-off, yellow "Buy anyway" when it doesn't.

### Results page
- P/L by week, history with sport/date/outcome filters, the paper gate, and "📊 What's working": combo price
  levels (every quote by band: hit vs expected, riding return, worth at game time, lab ride vs smart sell),
  bet types and sports (real vs paper, return, smart-sell replay, CLV), selling (ridden vs cashed, automatic sales,
  per-league smart-sell tuning).

### Look and feel (the makeover)
- One motion system: rolling numbers with green/red flashes, staggered entrances, page fades (View Transitions),
  swipe left/right between tabs, sliding tab and segmented indicators, spring bottom sheets with drag-to-close,
  press feedback, a drawn-check "Bought" moment, haptics everywhere (`hap()`: in-app via `combo://haptic`, iOS 18
  Safari via the `<input switch>` trick), and `prefers-reduced-motion` respected.
- **Press feedback + haptic on every control, from one place** (makeover phase 1): anything matching `TAP` (buttons,
  links, `[onclick]`, chips, rows, labels, selects, switches, sliders) shrinks while pressed (`.prs`; rows and settings
  lines highlight instead) and ticks on tap via a global capture listener, so new controls get it for free. Tabs,
  chips, segments and switches tick as `selection`, the rest `light`; sliders tick per step. Distinct patterns:
  success = 2 ticks, warning = 2 slower, error = 3. A control's own `hap()` right after the tap folds into the same
  tick (no double buzz). Sheets tick on open/close and when a drag crosses the close threshold; pull-to-refresh ticks
  at its threshold. `test_motion.py` audits every screen: no visible clickable element may miss press + haptic.
- Planned next phases (game page drill-down, Games cards, Sold moment, charts): `ROADMAP.md` and issue #12.

## Open items

All planned work that isn't built yet (what it's waiting on, and the suggested order) is in **`ROADMAP.md`**.
Read it before starting new work, and keep it current: when something ships, describe it here and remove it there.

## Code map (where to look)

Engine: `panel_collect`, `build_panel`, `choose_panel`, `panel_pass`, `panel_exec`, `panel_approve`, `panel_add`,
`prune_drafts`, `panel_settle`, `panel_record`, `adjust_cutoffs`, `combo_cutoff`, `lab_pass`, `lab_ticks`,
`_replay`/`sim_exit`, `smart_tune`/`smart_params`, `analytics`, `take_profit_reason`, `auto_sell_now`,
`single_sell_reason`, `smart_sell_singles`, `open_singles`, `live_view`, `record_view`, `mine_page`,
`fetch_account`/`_fetch_account`, `kalshi_send` (records app buys via `note_app_order`), `get_offer`,
`accept_offer`, `add_own_combo`, `set_league`, `LEAGUES`/`SPORTS`/`SPORT_PREFIX`.
Watcher: `shadow_loop`, `quick_rounds`, `panel_loop`, `update_loop`/`update_if_newer`/`repo_now`, `start_hub`,
`webapp_main` (`api_live`, `api_build`, `api_act`, `api_panel`, `api_results`, `api_game`), `mac_settings`,
`tailscale_cli`/`tailscale_run`/`tailscale_https`/`https_loop` (secure address; retries every 5 min until on), `push`/`web_push`
(every ntfy alert also goes to web push unless `web=False` or a topic is given; the Pi has no subscribers so it stays alerts-only). SPA: `renderLive`/`heroLive`, `renderBuild`, `renderResults`/`anBlock`, `renderSettings`,
`afterPaint` (number rolls, stagger, indicators), `go`, `modal`, `okSheet`, `toast`, `hap`.
