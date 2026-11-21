# Brief for Claude: the Kalshi combo planner

You are picking up a long-running project with Pete. This file holds the decisions, rules and context from the
earlier sessions (up to version 2026.11.20.124). Read it all before changing anything. When something here
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
  version bump (below), and main is back-merged into develop right after. Releases are owned by the session that
  holds the "release owner" role in issue #83 (it also merges the PRs). **Standing go-ahead (Pete, 2026-11-19,
  repeated 2026-11-20: "Release on your own"):** that session may release whenever there is enough green in develop,
  without asking each time. All other gates still apply: code review and security review on the release diff, green
  checks, matching versions, screenshots to Pete for visual changes, no new automatic money movement without his opt-in.
- **Version numbers** are unchanged: `YYYY.MM.DD.N`, currently `2026.11.20.124`. Each release bumps N (N keeps
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
  - **Release PRs** are opened and merged by the release owner (issue #83) under Pete's standing go-ahead (see Releases above), with every other release gate intact.
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
   screenshots or a clip first. Merge it when the gates above are met (Pete's standing go-ahead; visual changes need his screenshots first), then back-merge main into develop. The Macs then update within ~10 minutes; Pete can
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
  push (`t_https_push`: fake Tailscale CLI, push dedupe), notification tap targets (`t_push_target`: GitHub #79, a tap opens
  `/`, never `/app`; the service worker maps old `/app` payloads to `/`; the hub redirects a browser navigation to `/app` and
  `/app/` to `/` and answers any other navigation that finds nothing or has no session with a small HTML page, never an empty
  file; API routes unchanged) and the login page's Face ID tap fallback (`test_login_faceid`).
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
- **Spreads and totals (issue #117 part A).** Today's ("old") price: ESPN's line + a normal curve (`MARGIN_SD`/
  `TOTAL_SD`) or Poisson (`line_fair`). The **margin-shape model** (`margin_pmf`/`margin_prob`) prices each strike from
  how each league's games really finish: whole-number margins/totals, a fitted width `sd = a + b·|line|`, learned
  weights (NFL 3/7/10/14, no ties in basketball/college football; hockey = Poisson + overtime goal, soccer = Poisson with
  the market's draw), anchored on the line and its de-vigged price (`espn_line_prices`: spread/total juice and
  moneylines from ESPN's scoreboard), shrunk league → sport (AHL/EuroLeague borrow hockey/basketball). Tables and the
  backtest evidence are a generated block in the engine (`LINE_TABLES`/`LINE_EVIDENCE`, ~tens of KB) built by
  `tools/build_line_tables.py` (scrape ESPN politely into a cache outside the repo, fit, leave-one-season-out backtest
  with the engine's own code, `--write`). Then `calib_line`: per league, kind and strike-distance band (`line_bucket`),
  n/(n+300) borrowing everyone → sport → league, n = games. Every spread/total market's old and new price is logged in
  `line_fairs` (one row per market per 30 min, pre-game; resolved in `resolve_closes`). **Gate** (`line_gate`, per
  league and kind): new model only where it beat the old by ≥ 0.002 log loss and ≥ 2 SE on 200+ backtest games, or on
  the Mac's own settled markets once they cover 200+ games (which also turn it off if worse). Settings › Money
  "Smarter spread/total pricing" (`line_model`, shared, on = auto) turns it off everywhere. **Only the chance changes**
  (`_line_pick_model` in `line_candidates`): selection rules, caps, sizing, start rules and approval are untouched, a
  market the old model doesn't price stays unpriced, any error falls back to the old price, and with the gate off every
  price is byte for byte the old one (`t_linemodel`). Results › What's working › Bet types shows old vs new per league.
  Shipped backtest (2023-26, held-out seasons): the gate is on for **NFL spreads, college football spreads, NHL totals
  and women's college basketball totals**; NBA, men's college basketball, NFL/college football totals and women's
  spreads improved too little to pass; soccer and NHL spreads have no old price to compare (not priced today); ESPN
  has no lines for Serie A, Bundesliga and Ligue 1 (they borrow soccer's shape). Rebuild the block after a season.
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
- **Kalshi V2 orders** (issue #81): Kalshi removed the legacy order writes (`POST/DELETE /portfolio/orders` = 410
  `deprecated_v1_order_endpoint`). Callers still pass the app's order fields to `kalshi_send`; the one adapter there
  (`order_intent` → `order_v2_body`, `_order_create`/`_order_cancel`, answers read by `order_answer_v2`) sends V2:
  `POST /portfolio/events/orders` with `side` on the YES book (bid = buy YES / sell NO, ask = sell YES / buy NO),
  `price` = the YES price as a 4-decimal dollar string (a NO price q goes as 1 − q; cents ÷ 100 exactly, Decimal;
  rounded so a buy never pays more and a sale never takes less), `count` = a 2-decimal contract string; cancels are
  `DELETE /portfolio/events/orders/{id}?market_ticker=…`. V2 first; legacy only on a 405 or a 404 with no error code
  (route missing), and a 410 there is final (never loops). A 4xx is a definite refusal (plain words via `kalshi_plain`, nothing placed, panel
  skips; `ORDER_WORDS` covers every code on Kalshi's Order Errors page, tested in `t_buyfunds`). **Cash pots (exchange
  shards, issue #126):** Kalshi's docs say cash is kept per shard (combos 1, crypto 2, tennis/baseball/basketball 3,
  everything else 0), `GET /portfolio/balance`'s `balance` is the total, and `insufficient_balance` means the
  market's shard is short. Kalshi's own app shows one total; Pete's real breakdown hadn't been seen when this shipped.
  `_fetch_account` keeps `balance_breakdown` (`note_pots` → `ACCT_POTS`, one copy per process) and logs
  "Kalshi balance by pot: index 0 $x, index 1 $y, total $z" when it changes; Settings › Money shows it read-only
  (`kalshi_pots`, hub op `pots`). On `insufficient_balance`, `balance_words` re-reads the balance and the market's
  `exchange_index` (public `GET /markets/{t}`), 3 s each (`POTS_WAIT`), and claims a cause only when the numbers show
  it: the total below the order's cost ("not enough money in your Kalshi account", never for a sale), or a listed
  multi-pot breakdown with this market's pot short. Otherwise: the code, the total, "Check Kalshi". The app never
  moves cash between pots. A timeout, lost connection, 408/5xx, `order_already_exists` or an unreadable answer is `OrderUnknown`:
  "check", logged in `combo_orders.json`, and that market+side gets no order for 2 h, which Pete can lift sooner with Settings › Money › "Clear order block" (confirm, logged; the unclear order itself is never resent) (killer "check"s alert and count
  toward the caps; a "check" sale counts toward `auto_cap`). The same order (market, side, size, price) within 10 s
  (a double tap) isn't sent. V2 takes reduce-only only with IOC, so standing sell orders (take-profit ladders,
  sell-early exits) are refused before sending, existing ladders are never moved (cancelled), and the panel doesn't
  draft sell-early bets (`RESTING_SELLS_OK = False`, Pete to decide). Reads (`GET /portfolio/orders`, fills, positions) are unchanged; combos use the live RFQ endpoints. Any
  Kalshi answer with a 410, a "deprecated" code or a Deprecation/Sunset header calls `DEPRECATION_HOOK` → the
  watcher's `deprecation_alert` (one push per code per day; raw code in the log). Test: `t_orders_v2`.
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
  `/app/api/live`, `/game` and `/games` carry `fresh` (`now`, `built`, `scores` = age of the live leagues' scores
  (or, with none live, the newest score cache), `live` = a game is under way, `fast`); the page shows a small freshness stamp (Live hero, Games tab, game sheet) that counts on its own.
  **It names what it measures (issue #80):** while the server says a game is under way (`fresh.live`, not merely a scores cache) it reads "Prices Ns ago · scores Ns ago" — the
  snapshot/build age (how old the dollar numbers on screen actually are) and the live scores' age, kept separate so a
  stale snapshot and stale scores are never conflated into one misleading "Updated N ago". With no game live it falls
  back to the single "Updated N ago" (build age). It goes red after a minute **on the snapshot/prices age** (the
  number's own age), not on the scores age (`frBuilt`/`frScores`/`frTxt`, `frTick` toggles `.old`). (The "worth now if
  sold" dollar number is a model estimate that in the web app only moves when a leg resolves, not on every price tick —
  driving it off live leg prices was investigated under #80 and is a separate, larger change, not done here.)
  The open **game sheet redraws itself**: on every Mac tick, and on a 2 s timer when the
  link is down; it repaints only when something changed and keeps its scroll place. Between updates the clock counts
  down by itself, only for NBA/college basketball/NHL/AHL, and only once two polls showed it running (a clock that
  hasn't moved for 25 s is treated as stopped); football and soccer show the last value. Tests: `t_hubcache.py`,
  `test_livefresh.py`.
- **Live football game page (GitHub #72, display only).** On a live NFL/college-football game sheet the engine's
  `game_detail` (one ESPN summary fetch, cached 6 s; `_parse_game_detail`, `_situation_info`) feeds `api_game`'s `detail`
  block: the field strip (`fieldStrip`: ball, first-down line, red zone, possession arrow; everything inside `.grass` is
  positioned in % of the grass box = yards from the left goal line), the situation line, the last play and the scoreboard's
  timeout dots and possession ball. Slice 2 adds `detail.pbp` (`_parse_pbp`/`_pbp_play`: ESPN `drives.previous[]` + `current`,
  at most `PBP_MAX_PLAYS` newest plays, short keys) and a generic **game-page tab framework** in the SPA (`GAME_TABS`: a per-sport
  list of `{k, l, has(r), html(r, ov)}`; football = Overview + Play-by-play; a sport with no spec, or a tab whose data is missing,
  shows no tab row and the page is as before; the chosen tab, stepped play and collapsed sections live in `S.gtab`/`S.pbpStep`/
  `S.pbpOpen` and survive the 2 s redraws). The Play-by-play tab has a latest-play card with prev/next stepping (the strip shows
  the ball as it stood after that play, from the play's `yardsToEndzone` and the team whose end zone it is), Back to live,
  collapsible quarters and drives, and tinted scoring/turnover plays, newest first. Stepping (and a new live play) plays a small
  illustration (pass arc, run trail, sack, kick, flag, touchdown, turnover) driven only by play type and yardage: **illustrations
  only, there is no player tracking** (the tab says so); `prefers-reduced-motion` turns the motion off, the text and ball spot still
  update. **Isolation:** none of this is read by any buy/sell/panel path or takes the tap lock; a bad or missing feed hides the
  tab and is logged once per game (`klive_log_once("gamedetail", ...)`). Tests: `t_gamedetail`, `test_fieldstrip`,
  `test_gamedetail_api`, `test_pbptabs` (fixture `espn_game_detail.json`). Slice 3 adds five football tabs (Box score, Team
  stats, Injury report, Last 5 games, Season leaders). Box score (`detail.box`, `_parse_box`: passing/rushing/receiving, then
  defence/kicking, per side with a team switch), team stats (`detail.tstats`, `_parse_team_stats`/`_ts_num`: 13 head-to-head rows,
  share bars; made-att rows compare success rates, possession compares seconds) and injuries (`detail.inj`, `_parse_injuries`,
  worst first) come off the same summary. Last 5 games and season leaders (`detail.last5`/`detail.leaders`) come from each
  team's ESPN schedule (regular season, plus the postseason in the playoffs; last season in the preseason) and ESPN's
  core-feed season leaders (`game_extras`: a background thread, `GX` cache 30/60 min, a player's name 24 h in `ATH`, any
  failure backs off 30 s doubling to 30 min, Retry-After honoured; these GETs carry an Accept header so they go straight to
  ESPN, never through the hub's warm cache; only the first open of a game waits, at most `GX_BUDGET` 1.5 s). Last-5 dates
  are UTC kickoffs shown in the phone's own time zone. Same isolation rule; an absent block hides its tab, an empty one says so ("No injuries listed",
  "Recent results aren't available right now", "Not available"). Bars and numbers slide/roll when the game changes them.
  The `GAME_DETAIL` sweep walks a copy (another web thread may insert). Tests: `t_gametabs`, `test_gametabs` (fixture
  `espn_game_tabs.json`: trimmed real ESPN responses). Other sports' tabs are still to come (#72).
- The Winning now / Losing now / Tied / Won / Lost legend sits right above the combos table and lists only the
  states currently on screen.
- Toasts always fade: each has a deadline swept every second (and on touch/scroll/focus), is hidden after the fade and
  dismisses on tap. A Buy idea whose game Kalshi no longer lists shows a calm "not available" card and drops off.

### Build page
- Panel on top, sport chips (All = mix board), "Build your own": the games board (live score, period, clock for
  games under way), spreads & totals, more combo ideas — each section folds separately (remembered).
- Get price → green "Buy" when it clears the cut-off, yellow "Buy anyway" when it doesn't.
- **Over the cap (issue #71):** the Buy/Get price answer (`cap_msg`) says what the spending would reach, how much room
  is left, and the setting to change ("Settings > Money > Weekend cap/Daily cap/Mix cap for <league>"). Its window word
  (`cap_window`) matches what `week_spend` counts: "today"/"tomorrow" for daily leagues, "this weekend" only for NFL and
  college football Friday to Monday, otherwise "this week" (the Wed-Mon slate week: soccer, UFC, football Wed/Thu),
  "on games still to play" for the Mix. The rule and the cap amount are unchanged.
- **Buy straight (manual single buys, issue #113; Pete's tap only, no automatic buying).** With one team picked the slip
  has a **Single bet / Combo** switch (`slipMode`; Single bet keeps one pick and its button is "Buy straight"); the slip
  card offers "Buy <team> straight" too; spreads & totals rows, Best bets and the Single games card open the same sheet;
  the game page pins one big button per team ("Colts · 24% · 3.96x" = Kalshi's ask and $1's return after the fee;
  `api_game` → `buy` from `event_sides`, display only). The **buy sheet** (`sbOpen`/`sbQuote`/`sbBuy`, a `modal()`)
  shows Kalshi's ask now, our fair chance and the edge, presets $3/$5/$10/custom (`SINGLE_PRESETS`) plus the suggested
  stake, contracts, payout, room under the cap, warnings and a 20 s draining bar; green Buy or yellow Buy anyway; stakes
  over `SINGLE_ARM` ($25) need a second tap; at most `SINGLE_MAX` ($100). Engine: `single_buy_quote(x, stake, paused)`
  reads the book fresh (`book_depth(max_age=0)`), checks the market is open (`market_open`), prices fair as the panel does
  (sportsbooks via `calib_fair`; a game under way **only** via `live_side_fair`, else "no live fair price"; spreads/totals
  under way have none), sizes with `_size` (quarter Kelly, shrunk edge, $2 minimum), warns (thin > 6¢ gap, little for
  sale, live, nearly decided, live price far from the live chance, above fair, no fair price) and blocks (Pause, the
  unknown-outcome block, under one contract, account unreadable, over the cap: `week_spend` (Kalshi's combo record, which
  never sees singles) **plus** `manual_spend` (that league's manual singles in the same window, `_cap_start`: today for daily
  slates and the Mix, else the slate week; an unclear one included; table `manual_buys`), against the cap of the league Build
  has loaded, via `cap_msg`; the cap check, the order and its note run under one lock, `_SQ["buy"]`). The board's fair price
  is used only while under 12 min old (`SINGLE_FAIR_AGE`, `fair_at`; no read time = stale); spreads/totals need the board's 4¢ `LINE_MIN_EDGE` for a green Buy and size
  on a 30%-shrunk model edge; a finished game (`_game_over`) gets no quote; a start time it can't tell = a warning, yellow. It keeps a
  quote id (16 hex) for 20 s (`_SQ`). `single_buy(qid, ticker, anyway, paused)` checks the quote is the one on screen,
  unused, fresh, not blocked and (unless Buy anyway) clear; marks it used **before** sending (one order per quote, ever);
  re-reads the book and refuses a higher ask; rechecks a live game isn't over (market status and the score feed), the block and the cap; then
  `buy_single(..., coid="cw-sb-<qid>", exact=True)`: one IOC limit at the quoted ask (sub-cent asks sent as dollars,
  rounded down). An unclear answer = "check", the market blocked 2 h (`_mark_unsure`), never resent; a refusal is plain
  words and a fresh price may be asked. Bought markets are marked the app's (`app_bets.how = 'manual'`), so they show on
  Live under Single bets & spreads with smart sell on by default. Web app actions: `singlequote`, `singlebuy` with `q`
  (Pause read fresh from `watcher.json` each time: `paused_now`); `single_side` finds the side on the board on screen
  or a saved board (`SNAP`), read only, never rebuilding or switching it. The sheet's answer always shows (a sheet, else a
  toast), and Cancel from a game page goes back to it. Tests: `t_singlebuy.py`, `test_singlebuy_ui.py`.
- **Combo idea card buttons (issue #65):** the button row (`.brow`, primary `.pri` + secondary `.sec`) wraps, and long
  labels wrap instead of widening the button, so "Not this one" never leaves the card (360–430 pt). A card with a price
  asked for (`S.qpend`), a live quote or a buy under way (`S.bpend`) has a phase (`data-ph`, `ccPhase`): `renderBuild`
  puts the same DOM node back across any redraw (refresh, rebuild, load), so the button is never replaced, flickers or
  loses a tap; the countdown ("Ns left", `qTick`) only edits its number in place, and the card is redrawn once when the
  quote runs out. "Not this one" is off while a price or buy is in flight. `test_buildbuttons.py` covers it.
- **Every panel card names its game** (GitHub #61): a league tag in the header, and a line "Flyers at Bruins" (spreads/totals) or "Flyers vs Bruins" (singles, sell-early, each leg of a combo; pick first), from `stamp_games`/`_cand` (`game`, `vs`, `league`; no lookups); notifications and the recap use `bet_text`. The buy chip says "buys when you approve" until approved, then the buy state.
  Combo-idea legs, the slip, the board and the Bought sheet use `legRow` (sport icon, pick, "vs opponent · league · time", chance; tap a combo idea row to flip it).

### Results page
- P/L by week, history with sport/date/outcome filters, the paper gate, and "📊 What's working": combo price
  levels (every quote by band: hit vs expected, riding return, worth at game time, lab ride vs smart sell),
  bet types and sports (real vs paper, return, smart-sell replay, CLV), selling (ridden vs cashed, automatic sales,
  per-league smart-sell tuning).
- **"Cover the early games" paper test (issue #74):** paper only, no money. Its own `cover` **table** holds the test's
  rows (status, slots, result JSON); it never writes the `panel` table or calls `panel_record`, so it can't touch the
  $300 gate or `analytics()`. It is **not** the sole storage, though: `cover_ticks` records `state='sim'` rows into the
  **shared `ticks` table** exactly as `lab_ticks` does. Isolation from real bets does **not** come from a separate table
  — `_paths`/`_sl_paths` (the only consumers of these ticks) read `ticks` with no state filter and bucket by
  `round(ts)` (last-writer-wins); it comes from those being **replay/analytics-only** readers that never drive a real
  buy or sell. (Sim ticks sharing the `ticks` table is pre-existing `lab_ticks` behaviour, out of scope here.)
  `cover_pass`/`cover_ticks` run in `shadow_loop` **outside `odds.lock`** (both do batched Kalshi `requests.get` via
  `fetch_results` and `cover_ticks`' own calls, and the lock is the one `panel_loop` holds to place a real approved
  buy) across the whole NFL week (gated by `_nfl_week_end`, not Sunday-only): the week's slate is bucketed into ~90-min
  kickoff checkpoints (`_cover_week_slots`), the earliest checkpoint (Thu night / Sat / Sun-early) is "covered both
  sides" before kickoff, and the one surviving **full-week-slate** combo (the early winners carried together with every
  later game's higher-`p` side; no `fair` in this path) is measured at each later checkpoint and replayed through smart
  sell (`sim_exit`, which already applies the cash-out discount; `cover_ticks` feeds it `state='sim'` ticks, which the
  replay needs because `lab_ticks` only scans the `panel` table). `beat_cost` = the best smart-sell exit beat the
  doubled cost of covering both sides; the baseline is a single $5 **favourite-side** combo (the highest-Kalshi-price
  side of each early game) — a rough proxy only: the cover path has no `fair`, so it can't pick by edge, whereas the
  real panel picks by edge (`fair - p`) and often takes the underdog. Everything is JSON in the existing `result`
  column (no schema migration). Covering both sides adds no EV (the vig is paid twice) — it shifts variance and timing;
  the test measures whether smart sell's exit beats the doubled cost. Results > What's working shows it in `edgeBlock`
  (next to the gate), not in `anBlock`. Both bodies are fully defensive (never crash the loop). Tests: `t_cover.py`
  (engine), `test_cover.py` (page).

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
  **Haptics on iOS (issue #60):** Pete's test on iOS 27.2.1 (Home Screen app): only G, H and I tick, i.e. only when the
  finger itself lands on a real `<input type=checkbox switch>`; every scripted click (A-F, J, K) does nothing. So the
  default (`HAPDEF = 'N'`) is **method N**: every tappable control (`HSWQ`: buttons, `[onclick]`, chips, rows)
  gets a see-through switch (`.hsw`, opacity .01, appearance none, tabindex -1, aria-hidden) as its **first child**,
  covering it; the control becomes `position:relative` through a zero-specificity rule while `html.hswon` is set. The
  tap flips that switch (the tick) and the same real click bubbles on to the control's own handler; nested controls
  paint above their row's switch; icons/chance lines inside a control let taps through (`.hsw~svg`, `.mline`); disabled
  controls hide theirs; a field appearing inside a control removes its switch (`hswFix`); the switches' change/input
  events never reach the app. Skipped (`HSWNO`/`HSWIN`): links (no tick: a switch would take their navigation and
  long-press menu), labels (their checkboxes carry `switch` themselves, method I), selects, sliders,
  text fields, scrub charts, sideways strips, the test card's other buttons. A MutationObserver adds them to new content
  (never two per control). Only on iPhones/iPads, not in the Pythonista app, and off with the Haptics switch or reduced
  motion (`hswSync`). `hap()` still tries the scripted switch for a pattern's extra ticks and for gestures with no tap
  (chart scrub, pull-to-refresh, sheet drag, tab swipe, slider steps): iOS 27 ignores those, so they stay silent there.
  Settings › Test haptics (`hapCard`, `HAPM`/`HT`) lists N first, marks G/H/I "Pete confirmed" and the scripted ones
  "did nothing on iOS 27", and asks whether every tap ticks now. Tests: `test_hsw.py` (Chromium and, where installed,
  WebKit; CI installs it), `test_haptics.py`, the iPhone audit in `test_motion.py`. The card's on/off switch is per phone (`cw_hapoff`); helper switches carry class `hapx`,
  test buttons `data-hapt` (N's also `data-hsw`).
- **Makeover phase 2** (UI only; no buy/sell/panel logic touched):
  - **Games** shows one live card per game you have money on, combos **and** single bets, spreads and totals
    (`api_games` puts a single on its game's card by the game code, or gives it a card of its own). Card: league and
    clock (red live dot), your side ("YOURS") and theirs with the score, the chance (rolling, with a bar) and a chance
    line with a glowing end dot (the Mac's `ticks`, plus what the page saw itself in `S.gh`), and chips for the bets
    riding on it. When someone scores the card pulses green (your side) or red (theirs), the number bumps and the
    phone ticks (`scoreWatch`). Tap pushes the game page. Skeleton cards while loading.
    **Both teams and both scores on every card (issue #95, display only):** their row shows the full opponent name, else the
    short code on the score (`sc.opp_abbr`), else "Opponent" when only their score is known; a card with no opponent score
    (tennis/UFC on Kalshi's live data) shows no number, never a fake 0 (a real 0 shows). The server fills the leg/single
    `opp` from the score when no odds-book match names the other side (college hoops). `test_gamecard_opp.py` covers it.
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
    **Dated by when the money moved (issue #91, display only):** both bars group each settled bet by when the
    transaction actually happened — the cash-out sell for a bet cashed early, else Kalshi's settlement time, else the
    Mac's detection time (`settled`), and only as a last resort the game/slate date — not the NFL game date. The engine
    captures the last sell fill as `cashed_at` and the settlement time as `settled_at` in `_fetch_account`;
    `realized_buckets(a, st)` derives the day and the week from that one realized date in the Mac's local tz (the week
    is `sunday_of` that day, the same rounding `week_of` uses), so day and week can't land in different buckets.
    `api_results` buckets both the per-day `day` and the per-week grouping with it; the detail sheet shows the buy date
    and the cash-out/settlement date so the grouping explains itself. No bet, P/L or buy/sell/panel logic changed.
    `t_realdate.py` and `test_realdate.py` cover it.
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

## Kalshi API watch (GitHub issue #82)

- `.github/workflows/kalshi-api-watch.yml` runs on GitHub (not the Mac) every 6 hours and runs `tools/kalshi_feed_watch.py`, which reads Kalshi's API changelog RSS feed (`docs.kalshi.com/changelog/rss.xml`) and opens one issue per new entry from the last 14 days (max 5 a run, deduped by the feed id in the body, open or closed), labelled `kalshi-api-change`; two tiers: a removal/deprecation word (deprecat/remov/no longer/sunset/migrat/410...) AND an app area (orders, portfolio, RFQ/quotes, order book, market fields, signing, rate limit, websocket...) in the title/description gets `breaking` + an "ACTION LIKELY NEEDED" first line; everything else is filed as a plain "FYI" issue (2 of the 15 entries at launch were breaking). It never touches `wip:*` labels.
- **Alerts appear as GitHub issues**: GitHub emails/notifies Pete (the repo owner) for each one. A dead feed exits quietly; after 4 failed runs in a row it opens one "Kalshi API watch is failing" issue (count kept in the `kalshi-watch-failures` label's description). Try it with `python3 tools/kalshi_feed_watch.py --dry-run` (prints, changes nothing).
- Feed text is untrusted: stripped to plain text, trimmed, fenced, never run. Permissions are only `contents: read` + `issues: write`. Tested by `tests/suite/t_kalshi_feed_watch.py`. Scheduled runs start only once the file is on `main`.

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
