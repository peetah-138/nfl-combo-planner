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
- **Decisions Pete made on 2026-11-18:**
  - At most **3 subagents** at once.
  - **Rebuild `Combo-Watcher.zip` in the release PR** whenever `install_mac.sh`, `setup_wizard.py`,
    `wizard_window.js` or `install_pi.sh` changed.
  - **Dev and test default: no live buying.** Killer and maker modes stay on `watch`.
  - **Visual PRs** may merge into `develop`, but Pete sees screenshots or a short clip **before** the release PR
    (`develop` → `main`) is merged.
  - **Release PRs** are opened by Claude and merged only on Pete's explicit go-ahead.
  - **When Pete gives feedback, open a GitHub issue** to track it.
  - **Questions for Pete go through the AskUserQuestion tool**, interview style. Keep replies short.

## Releasing

1. Feature PRs squash-merge into `develop` once CI (`checks`) is green; nobody pushes to `develop` or `main`
   directly. `develop` must be fully merged and green.
2. Bump the version in all three places (see above) on a short `chore/release-…` branch, PR into `develop`,
   squash-merge once `checks` is green. If any installer file changed (see the decisions above), rebuild
   `Combo-Watcher.zip` in the same PR.
3. Run code review and security review on the release diff; fix every finding.
4. Run `bash tests/run_checks.sh` and `ruff check .`. All must pass. Add a test for every change (see
   `tests/README.md`).
5. Open the `develop` → `main` PR, to be merged as a **merge commit** (not squashed). For visual changes, show Pete
   screenshots or a clip first. Merge it only after Pete says go. The Macs then update within ~10 minutes; Pete can
   also tap "Check for an update now". An update restarts the watcher (launchd brings it back).

## Testing (the check list)

Run `ruff check .` (config in `ruff.toml`: correctness rules only, no style rules) and `bash tests/run_checks.sh`
before every push; the latter must end with `ALL CHECKS PASSED`. CI runs both on every PR. See `tests/README.md`
for the one-time Mac setup. The checks and `dev.sh` run on a **Python 3.10+** picked by `tests/python_env.sh` (`$CHECK_PYTHON`, else
the watcher's venv if it has the modules, else a git-ignored `.venv-tests/` it builds itself); never Apple's Command Line Tools 3.9,
whose system SQLite crashes on macOS 26.4 (#68). `CHECK_PORT_BASE` moves the test ports when two runs overlap. It runs in a temp folder with fake services and a fake
key, and its web apps use ports 18766+ (4 lanes in parallel, ~4 minutes), so it can't touch the real app or money. What it covers:
- Both files compile (Python 3.10), `node --check` on the SPA's script and on `LOGIN_HTML`'s script,
  pyflakes for undefined names, secret grep.
- Engine tests (each prints PASS/FAIL lines): review fixes, lines (spread game matching), restart, extras,
  own-bets, started-games, games under way priced live (`t_live_panel`), smart sell for singles, combo lab, self-tuning, AHL, AHL live scores, Kalshi live data
  (`t_kalshi_live`; page test `test_klive`), robustness of the display code and tap lock (`t_robust`), per-league learning, the secure address and web
  push (`t_https_push`: fake Tailscale CLI, push dedupe) and the login page's Face ID tap fallback (`test_login_faceid`).
- **Tests never touch the real Tailscale or ntfy (issue #54).** `run_checks.sh`, macsmoke, `dev.sh` and `dev_webapp.py` set
  `COMBO_NO_TAILSCALE=1`; `tailscale_run` refuses every Tailscale command (serve, funnel, cert, status) unless the config
  folder is a real install home (`~/combowatch`, the Pi's `/var/lib/combowatch`), and `tailscale_https`/`https_loop` do
  nothing (state `off-in-tests`). Only `t_https_push` runs a fake script from a temp folder (`TS_FAKE_OK`). `t_tailscale_safe`
  uses a shim `tailscale` that records calls. `COMBOWATCH_NTFY` points at `ntfy.invalid` in the checks. New harnesses that boot
  the watcher must set the flag too.
- A simulated Mac run (fake Kalshi; the log must be clean) and a simulated update install (copies the watcher to a
  temp home; must never touch the repo files).
- Playwright page tests at phone (390×844) and desktop sizes for every screen: no JS errors, no sideways scroll on a
  phone, and the specific behaviour (taps, filters, toggles, numbers). Beware timing: numbers animate (~0.65 s),
  view transitions render on the next frame, and the page auto-refreshes; wait for state rather than fixed sleeps.

## The product, by area (decisions and current behaviour)

### Fair prices and data
- "Fair" = sharp sportsbooks de-vigged (free sources; The Odds API free plan; no paid odds). Calibrated by Pete's own
  record per league and chance band (`calib_fair`, shrink n/(n+300)), borrowing everyone -> sport -> league (Pete,
  #37): the other sports' record (`calibration()["all"]` minus this sport's own games, so none count twice) nudges
  the books' chance by n/(n+300); the sport moves from that nudge toward its own record by its n/(n+300); a league
  inside a sport (each soccer league) moves from its sport's the same way. A level with no games gets exactly the one
  above; a sport alone in a band is exactly as before; a band nobody has played keeps the books' chance.
  Leagues marked `require_line` need a sportsbook line (Kalshi alone isn't trusted there).
- Live scores from ESPN's free scoreboard (none for EuroLeague, UFC, tennis). The AHL isn't on ESPN: its scores,
  periods and clocks come from the league's own public score feed (the JSON theahl.com's widgets read; HockeyTech,
  no login; `_fetch_feed_scores`, light polling), with the same cache and last-good-copy fallback as ESPN.
- **Tennis, EuroLeague and UFC scores come from Kalshi's public live data (GitHub #25), display only.** No key, no
  account endpoints: `GET /milestones?related_event_ticker=<event>` maps a game to its milestone (cached 6 h, a miss
  15 min, at most 8 new lookups a refresh) and one `GET /live_data/batch?milestone_ids=...` per refresh covers every
  game under way (cached like ESPN, `SCORES_MAX_AGE`; last good copy kept; 429/5xx/unreachable pauses 15 s doubling
  to 10 min, Retry-After honoured; sent straight to Kalshi with only an Accept header, never through the hub).
  `kalshi_score` returns leg_score's shape from the pick's side (side from the event code: tennis/UFC list the first
  competitor first, team games are "Away at Home"; can't tell → nothing shown). Tennis: sets as the score, detail
  "Set 2 of 3 · 4–3 · 30–15 · serving", finals "6–2 7–6"; EuroLeague: points, "Q3 4:18" / "End Q1" / "Half" / "Final"
  (its clock ticks on the game sheet like the NBA's); UFC: no points, the note says "Round 2 of 3 · no clock" (in-fight
  fields unverified) or "Fight over · Decision · R5 · waiting on Kalshi to settle". **Isolation rule:** only
  `display_score` (the Live legs, the combo row, the game strip, the Build board, singles' display fields) reads it;
  `leg_score`, `fetch_scores`, `SCORES_BY`, `pick_state`, `started`, early results (`final_result`), singles' `state`
  and their order, smart sell and every buy/sell/panel path never do (`t_kalshi_live` checks the sources). Tick
  sampling ignores a Kalshi score so smart-sell tuning's replays are unchanged. Fixtures of the real shapes:
  `tests/suite/fixtures/kalshi_live.json`.
  **Robustness (review #37):** the display code can never stop or slow the trading loop. `kalshi_score`,
  `display_score` and `safe_run_status` never raise (a bad feed field = no score for that game, logged once per game);
  `mine_page`/`open_singles` refresh through `kalshi_live_kick` (a background thread, waiting at most `KLIVE_BUDGET`
  = 1.5 s, last good copy otherwise); `klive_prune` drops old cache entries. Web app taps (`api_act`) take the lock
  through `TapLock` (wait ≤ `ACT_WAIT` = 20 s, then "busy", nothing done; Live rebuilds stand aside while a tap
  waits); the hub's reads share one `RateLimit` (~6/s, bursts of 20). Tested by `t_robust`.
- **Kalshi's order book** (`book_depth` → `book_info`/`book_levels`, issue #70): since Nov 2026 the public
  `GET /markets/<t>/orderbook` answers `{"orderbook_fp": {"yes_dollars": [["0.52","3703.51"],...], "no_dollars": [...]}}`
  (dollar strings, lowest first); the old `{"orderbook": {"yes": [[52, 3703]...]}}` (cents) is still read. Both give
  the same dollars; an odd answer = no prices, never an error. Ask = 1 − best NO bid. Smart sell for singles reads
  the market's own `yes_bid_dollars`/`yes_ask_dollars` (`GET /markets`), not the book. Test: `t_orderbook`.
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
  follows its sport's live (`soccer:2`, the old keys, read exactly as before). A sport with no level of its own
  borrows everyone's (`all:2`, once that has 30+ quotes) **only upward: max(everyone's, 95%)** (Pete, #37 M2;
  `CUT_START`). `adjust_cutoffs` saves such a sport marked `"borrowed": true` (ignored by `_cut_level`, hidden in
  Settings) until it has 30+ quotes of its own, so a borrowed level is never kept as its own; it becomes its own
  at 30+ quotes or when its own record moves it. Only a group's own record can take it below 95% (to the 85% floor).
- The panel's sport tie-break (`sport_pay_index`/`pay_index_of`) uses a league's own pay index once it has 10+
  quotes, else its sport's. Sizing reads league results through the calibrated chance.
- Pete approves once; **the Mac buys each bet right after he approves it** (Pete's decision, issue #51: waiting
  until ~45 min before the game gave up the price he approved; the old lead-time code, `PANEL["buy_before"]` and
  `best_combo_lead`, is gone and bets carry no `buy_at`). Approve and Add leave `panel_buy.flag` (`ask_buy`); the
  watcher's `panel_loop` (`panel_wait`) sees it within ~2 s and runs `panel_exec`, otherwise it runs every minute. Each
  bet still gets the fresh price recheck first (newest candidates via `_fresh`, then Kalshi's book/quote in
  `_buy_panel_bet`), swaps in a similar bet (bought on the pass right after) or skips; prices too old to judge wait
  (the item gets `hold: "price"` and its sport joins `sports_near` via `BUY_WAIT`, so it's re-collected within ~2.5
  min; Pause / no key set `hold: "paused"` / `"no key"`, shown on the card). Items approved before this change keep a
  stored `buy_at` and wait for it (no surprise buys on the update). `panel_settle` runs every 5 min by the clock.
  A bet whose game is hours or days away is bought now too. Unchanged: Pause, the start rules (`_start_ok`), sizing
  and budget, claim-before-buy under `panel_tx` (no double buy), unknown outcome = "check". The panel card says
  "buys when you approve" (or "when you add it") before, "Buying now" once approved (or why not yet), then
  "Bought"; after Approve/Add the page re-checks a few times (`pBuyWatch`). The paper panel
  buys at once the same way. Price at build, at buy (`bought_at`) and game time are still recorded, so CLV works. "Build a fresh panel" (after a Stop) and the empty card's
  "Look now" start at once: the tap leaves `panel_rebuild.flag`, the watcher's `rebuild_loop` thread sees it within
  ~2 s and runs `panel_rebuild` (collects every shadow sport fresh, then the usual `panel_pass`; drafts only, never
  buys or approves). Progress is noted in `combo_rebuild.json` (`rebuild_status`: asked / running "Looking at NBA…
  2 of 6 sports" / done with a count, or why none). The Build page polls it every 2 s, redraws the card in place,
  and swaps in the new panel by itself. No screen promises a 10-minute wait (the old "check back shortly" card
  waited for the shadow's next round, and a rebuild from a stale pool silently found nothing). After approval the Mac keeps looking
  (every ~2.5 min for sports with games within 2 h) and offers "🆕 New since you approved" extras (one
  notification each, Add button, inside the remaining budget). A skipped/swapped (or left-out) bet can come back as an
  extra; one that is scheduled, buying, bought, "check" or failed (Kalshi turned it down at buy time) never comes back
  or gets added again that day (`PANEL_TRIED`), and extras on a game a live panel bet covers are hidden
  (`panel_extras`/`_extras_filter`, used by the Build page and the rebuild status). **Add is safe to repeat (#62):**
  `panel_add` checks and adds inside one `panel_tx`, so two taps or two phones at once add a bet once; an added extra
  is dropped from the extras row at once; the page disables the button ("Adding…" then "✓ Added"), ignores taps while
  one is on its way (`S.pSend`/`pPost`, gives up waiting after 30 s), and hides just-added extras for 2 min unless
  today's panel doesn't have them. Approve works the same way (already idempotent in `panel_approve`).
- **Games already under way (Pete's decision, replaces the old "never buys or approves a game that has started"):**
  the panel picks on the chance of a profit, not on whether a game has started. Settings › Money › **Include games
  already under way** (`panel_live`, shared setting, **on** by default; `live_panel_on()` reads the shared settings
  file) lets `panel_collect` add started games via `panel_live_games`. A game under way **never uses its pre-game
  fair price**: it gets a fresh live sportsbook line (odds-service line read after the start, ≤ `LIVE_LINE_AGE` 180 s:
  `line_live`/`line_at` from `attach_fair`) or else the **live model** (`live_model_chance`: points sports = normal
  margin, hockey/soccer = Poisson goals, on the closing line from `closes` as the prior, ESPN's football win chance
  averaged in), calibrated per league by its own record of live chances (`live_fairs` table, `calib_fair(...,
  table="live_fairs")`, resolved in `resolve_closes`). Eligible only with a **fresh score** (`score_age` ≤
  `LIVE_SCORE_AGE` 120 s; missing/stale = out), the game **in play** (never finished), Kalshi bid/ask gap ≤ 6¢, not
  nearly decided (≥ 95%), and Kalshi's mid within 8 points of the live chance (a wider gap is treated as something the
  score doesn't show, not a bargain). **EuroLeague, UFC and tennis stay out once started** (only Kalshi's display-only
  live data, no clock); spreads/totals and sell-early favorites stay pre-game only. Live candidates carry `live`,
  `kick_pre` and per-leg `live`/`pre`; `_start_ok` replaces the old start-time checks in `build_panel`,
  `panel_approve`, `panel_add`, `panel_exec`, `prune_drafts` and `_replacement` (pre-game-priced bets still need
  20 min/5 min before the start). Live prices older than `LIVE_POOL_AGE` (6 min) are never offered or bought; sports
  with a live-priced game are re-checked every 2.5 min (`LIVE_NOW` in `sports_near`). Buying: bought straight away;
  `_buy_panel_bet` re-prices every live leg on a fresh score (`live_recheck`) and still rechecks Kalshi's price; any
  refusal before an order (stale score, finished game, price moved, Kalshi won't price the combo: `get_offer` errors
  are caught) is **skipped**, never "check"; rule 8 unchanged. Pause still wins; the switch turned off after approval
  skips live bets. Same cut-offs, sizing and per-league learning; CLV isn't counted for live buys (the closing price
  predates them); Results › What's working › Bet types shows **Bought during the game, by league** (`analytics()["live"]`).
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
- **Stop-loss guards (issue #27):** with `stop_loss` on, auto cash-out may sell a combo below cost only when
  `stop_loss_check` passes: a pick on a **fresh** score feed (`leg_score`, never Kalshi's display-only data; scores
  older than 150 s or missing = never, and any other pick whose game has started must have a fresh score too), game
  in play and **not at halftime/a break/end of a period** (`at_break`), **game played ≥ the league's `prog`** (start
  50%, bounds 35–90%), pick under 50% and **≥ `drop` points below its pregame chance** (start 20 points, bounds
  10–45; `pre_of` on each held combo), all held on **3+ checks in a row spanning ≥ 3 min** (none > 5 min apart).
  `prog`/`drop` are learned weekly in `smart_tune` (`_sl_tune`/`_sl_replay` on recorded ticks + score lines, 50+
  combos, ≥ 2% gain, 0.05 steps, smallest change on ties), stored as `sl_*` in `combo_smart.json`, shown in
  Results › Selling. `stoploss_params` borrows league → sport → all, but borrowed values can only be **stricter**
  than the start; only a league's own record can loosen it. A stop-loss sale is logged with `stop_loss: true` and
  notifies "Stop-loss (your switch)".
- **Auto-hedge guards (issue #27, Pete approved):** auto-hedge (with Auto cash-out on, replaces an already-chosen
  sale when the combo has one pick left and the hedge locks in ≥ 95% of the cash-out, ≤ `hedge_cap`, default $100)
  now buys only when `hedge_guard` passes: the last game **in play on a fresh score** (`fresh_live_score`, shared with
  the loss guards; missing/stale = no hedge), **not at a break** (`at_break`), the hedge **locks in at least the
  combo's cost** (`locked = contracts − hedge cost ≥ h["cost"]`), all held on **3+ checks over ≥ 3 min** (`_sl_confirm`
  under `hedge:<ticker>`). Then `hedge_fresh` re-reads the hedge side's order book (`book_depth(max_age=0)`; no ask or
  a gap > 6¢ = no hedge) and redoes the sums on the fresh ask (still beats the cash-out, within the cap, ≥ cost); the
  IOC order goes at that ask. While confirming, the sale waits; any other failed guard = it cashes out as if
  auto-hedge were off. A hedge order with an unknown outcome (timeout, lost Mac, 5xx) is marked `check` in
  `combo_hedges.json` (`hedge_unsure`): never retried, no sale on top, and auto cash-out leaves that combo alone. Holds
  are logged (`result: "held"`, `hedge: true`) and Results › Selling shows the count by reason (`hedge_held`). The
  manual Hedge tap has no guards (Pete's own tap, board price), but an unknown outcome there is also marked `check`.
- **Loss-cut guards (issue #27, Pete's decision):** the learned per-league "cut loss" (combos in `take_profit_reason`,
  singles/spreads/totals in `single_sell_reason`) now needs the **same guards**, reusing the helpers: combos run
  `stop_loss_check(t, h, also=<under the cut-off>, key="cut:<ticker>")` once per `auto_sell_now` pass and pass
  `cut_ok`; singles run `cut_loss_single_check` (`stop_loss_leg` on the game's score + `_sl_confirm`), with the
  pregame chance from `single_pre` (last chance seen before the game in `MINE["pre_single"]`, else the saved
  `PREGAME` for game-winners; unknown = never). Same league `prog`/`drop` as the switch (`stoploss_params`).
  Without `cut_ok` both functions never cut (Live display included). The cut is **never borrowed**: `smart_params`
  drops `loss` unless it is the league's own. The weekly replay only cuts where the live guards would have held
  (`_sl_held` → `_cut_guard_ts`, `_replay(..., cut_at=)`), so the tuner learns what live can actually do. A cut the
  guards hold back is logged once per bet and reason (`note_cut_held`, `result: "held"`); `analytics()["cut_held"]`
  counts them for Results › Selling, which also shows the guard settings per league. Pause / Auto cash-out off /
  Ride it out still stop it (it runs only inside `auto_sell_now`).
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
  until Kalshi settles it. Tennis, EuroLeague and UFC now usually have Kalshi's live data instead (above), so these
  words are the fallback when it has nothing. With a score source, `run_status` also says "Not started yet · was due
  20 min ago" (phase `waiting`: a match running late is never shown as live; the combo row says "Not started yet")
  and "Match/Fight/Game over · <score> · waiting on Kalshi to settle" (phase `over`; the Games tab files these under
  "Finished", not "Playing now").
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
- **Every panel card names its game** (GitHub #61): a league tag in the header, and a line "Flyers at Bruins" (spreads/totals) or "Flyers vs Bruins" (singles, sell-early, each leg of a combo; pick first), from `stamp_games`/`_cand` (`game`, `vs`, `league`; no lookups); notifications and the recap use `bet_text`. The buy chip says "buys when you approve" until approved, then the buy state.
  Combo-idea legs, the slip, the board and the Bought sheet use `legRow` (sport icon, pick, "vs opponent · league · time", chance; tap a combo idea row to flip it).

### Results page
- P/L by week, history with sport/date/outcome filters, the paper gate, and "📊 What's working": combo price
  levels (every quote by band: hit vs expected, riding return, worth at game time, lab ride vs smart sell),
  bet types and sports (real vs paper, return, smart-sell replay, CLV), selling (ridden vs cashed, automatic sales,
  per-league smart-sell tuning).
- **"Cover the early games" paper test (issue #74):** paper only, no money, its own `cover` table (never `panel`, so
  it can't touch the gate/analytics). `cover_pass`/`cover_ticks` run inside `panel_loop` across the whole NFL week
  (gated by `_nfl_week_end`, not Sunday-only): the week's slate is bucketed into ~90-min kickoff checkpoints
  (`_cover_week_slots`), the earliest checkpoint (Thu night / Sat / Sun-early) is "covered both sides" before kickoff,
  and the one surviving **full-week-slate** combo (the early winners carried together with every later game's
  value-picked = higher-`p` side; no `fair` in this path) is measured at each later checkpoint and replayed through
  smart sell (`sim_exit`, which already applies the cash-out discount; `cover_ticks` feeds it `state='sim'` ticks
  since `lab_ticks` only scans `panel`). `beat_cost` = the best smart-sell exit beat the doubled cost of covering both
  sides; the baseline is a single $5 one-sided combo on the same early games. Everything is JSON in the existing
  `result` column (no schema migration). Covering both sides adds no EV (the vig is paid twice) — it shifts variance
  and timing; the test measures whether smart sell's exit beats the doubled cost. Results > What's working shows it
  in `edgeBlock` (next to the gate), not in `anBlock`. Both bodies are fully defensive (never crash `panel_loop`).
  Tests: `t_cover.py` (engine), `test_cover.py` (page).

### Look and feel (the makeover)
- CSS class names are global: `<main>` is marked `arrived` for 1.6 s after a screen change (never `fresh`, which is the small
  "Updated Ns ago" stamp: nowrap, small grey text). Reusing it made every new screen draw too wide for a moment (GitHub #52);
  `test_loadwidth.py` samples every frame after each tab switch.
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
  **Haptics on iOS (issue #60, unresolved):** Pete feels none on iOS 27.2.1 in the Home Screen app, and the `<input
  switch>` trick is only documented for iOS 17.4-18. `hap()` now toggles a tiny see-through switch laid out *inside* the
  screen (not parked off it), and iPhones/iPads use it even if `navigator.vibrate` exists. Settings › Test haptics
  (`hapCard`, tests in `test_haptics.py`) has one lettered button per method (the list is `HAPM`, the code is `HT`);
  the one `hap()` uses is the single letter `HAPDEF` (now `B`): **once Pete reports which letter he feels, change
  `HAPDEF` to it** (and drop the methods that don't work). The card also has a per-phone Haptics on/off switch
  (`cw_hapoff`). Helper switches carry class `hapx` (the tap listener ignores them); test buttons carry `data-hapt`.
- **Makeover phase 2** (UI only; no buy/sell/panel logic touched):
  - **Games** shows one live card per game you have money on, combos **and** single bets, spreads and totals
    (`api_games` puts a single on its game's card by the game code, or gives it a card of its own). Card: league and
    clock (red live dot), your side ("YOURS") and theirs with the score, the chance (rolling, with a bar) and a chance
    line with a glowing end dot (the Mac's `ticks`, plus what the page saw itself in `S.gh`), and chips for the bets
    riding on it. When someone scores the card pulses green (your side) or red (theirs), the number bumps and the
    phone ticks (`scoreWatch`). Tap pushes the game page. Skeleton cards while loading.
  - **Charts you can scrub** (`wireScrubs` + a spec in `S.scr[name]`): the game page's chance chart (readout of time
    and chance) and the Results profit bars; a haptic tick per point, refreshes wait while a finger is down
    (`S.scrub`), a short tap can open the point.
  - **The Sold moment** (`soldSheet`): a successful cash-out tap (the reply starts with ✅) gets the drawn-check sheet
    with what came back, the profit and %, a "You paid / Got back" stub. A loss gets a calm grey version (dash
    instead of a check, light haptic). While the page is open, sales smart sell / auto cash-out made by themselves
    show the same card stamped "SOLD BY SMART SELL" (`api_live` now returns `sales`, read-only from the sell log;
    only sales made after the page opened; each once). If a sheet is already open it's a toast instead.
  - **Wins** (`liveMoments`, diffing two Live loads): a small win = confetti + toast; a **big hit** (profit ≥ $50, or
    ≥ $15 at 5×+) = a full-screen moment (`bigWin`): the payout rolls up, rings pulse, two confetti waves, a double
    success haptic; tap to close. Each win once (`S.momSeen`).
  - **Results**: "Profit by day / week" bars (Day = last 14 days with results, Week = last 12 weeks; remembered),
    drag across for a readout, tap a bar for that day's or week's bets in a sheet. Skeletons for Results and the
    Build panel; empty states point to Build. `test_makeover2.py` covers all of this.
- **Makeover phase 3** (UI only; no buy/sell/panel logic or thresholds touched): every remaining screen in the same
  motion system.
  - **Offline / reconnecting**: `api()` reports each answer to `netUp()`; a failed request or a dropped live link
    (`S.live_ok===false`, or the phone offline) for more than ~1.2 s brings up a calm pill under the header,
    "Reconnecting to your Mac · Updated 40s ago" (the stamp counts from the last good answer, `S.okAt`), which says
    "Back online" briefly when it returns. A screen with nothing to show yet gets an error card with **Try again**
    (`errCard`/`retry`) instead of an endless skeleton. Settings and What's working have their own skeletons.
  - **Header** tucks in once you scroll on a phone (`body.hc`, with hysteresis). **Pull to refresh** works on every
    tab: rubber band, a ring that fills, a tick at the threshold, a spin, then a check (`load(view, true)`).
  - **Safe areas** for the Home Screen app (side insets, bottom sheets clear the home indicator), **keyboard-aware
    sheets** (`visualViewport` → `--kb`, `kbSet()`; the sheet rides above the keyboard and the field stays in view),
    sheet content staggers in, a light backdrop blur.
  - **Settings**: Let it ride is a slider with five detents (a haptic tick per step, the name pops, dots follow;
    same `ride` value 0–4). Every slider's value pops as it moves; switches have a springier knob; "Saved" pops.
    Buttons that do something on the Mac report back on the button itself (`btnBusy`/`btnState`: spinner, then
    "✓ Done"/"✓ Sent" or "✕ Didn't work"), and **Update now asks first** (it restarts the watcher).
  - **Build**: board prices, panel stakes and combo chances roll with green/red flashes (`data-num`, `cent` format);
    picking a team pops; the slip bar slides in once; a fresh quote rises in with a bar draining over its 20 s (also
    on Live's idea Buy buttons and the slip's Buy); Buy anyway stays the yellow button; fold chevrons turn and
    sections rise in; leaving a panel bet out animates; the first Approve/Add tap arms the button (orange, "Tap again",
    a 4 s draining bar). Panel cards show a **tiny price line** (Kalshi price, or a combo's share of fair) from what
    this phone has seen in the last 36 h (`cw_pxh` in localStorage); it appears only with 2+ readings.
  - **Results**: KPIs roll, the edge bars grow in on arrival, What's working tabs crossfade (rows stagger) and it
    says "updated just now" (not "now ago").
  - **Morning recap streak** (`streakNote`): 2+ days up = a flame, "N days up in a row" and a dot per day (up to 7);
    one day up = a gentle "another good day starts a streak"; a down day shows nothing.
  - **Login page**: soft entrance (logo pops), press feedback, a haptic on every tap and on a Face ID failure.
  - **Light mode** fixes (`color-scheme`, a theme colour per scheme, warmer "You, on Kalshi" tag, softer shadows,
    visible switch track), and a fix for Settings › Accounts showing "Not connected" as a label.
  - `test_makeover3.py` covers all of this at phone (dark and light) and desktop sizes, plus the login page and a
    reduced-motion run.
- Next makeover work (Kalshi-style game page drill-down, shareable result card, more charts): `ROADMAP.md` and issue #12.

## Open items

All planned work that isn't built yet (what it's waiting on, and the suggested order) is in **`ROADMAP.md`**.
Read it before starting new work, and keep it current: when something ships, describe it here and remove it there.

## Code map (where to look)

Engine: `panel_collect`, `build_panel`, `choose_panel`, `panel_pass`, `panel_exec`, `panel_approve`, `panel_add`,
`prune_drafts`, `panel_rebuild`/`rebuild_status`/`panel_look_now`, `panel_settle`, `panel_record`, `adjust_cutoffs`, `combo_cutoff`, `lab_pass`, `lab_ticks`,
`_replay`/`sim_exit`, `smart_tune`/`smart_params`, `analytics`, `take_profit_reason`, `auto_sell_now`,
`single_sell_reason`, `smart_sell_singles`, `open_singles`, `live_view`, `record_view`, `mine_page`,
`fetch_account`/`_fetch_account`, `kalshi_send` (records app buys via `note_app_order`), `get_offer`,
`accept_offer`, `add_own_combo`, `set_league`, `LEAGUES`/`SPORTS`/`SPORT_PREFIX`.
Watcher: `shadow_loop`, `quick_rounds`, `panel_loop`, `rebuild_loop`, `update_loop`/`update_if_newer`/`repo_now`, `start_hub`,
`webapp_main` (`api_live`, `api_build`, `api_act`, `api_panel`, `api_results`, `api_game`), `mac_settings`,
`tailscale_clis`/`tailscale_env`/`tailscale_run`/`tailscale_status`/`tailscale_https`/`https_loop` (secure address: tries
every Tailscale CLI with a launchd-safe env; "signed out" only when BackendState is NeedsLogin; retries every 5 min until on), `push`/`web_push`
(every ntfy alert also goes to web push unless `web=False` or a topic is given; the Pi has no subscribers so it stays alerts-only). SPA: `renderLive`/`heroLive`, `renderBuild`, `renderResults`/`anBlock`, `renderSettings`,
`afterPaint` (number rolls, stagger, indicators), `go`, `modal`, `okSheet`, `toast`, `hap`.
