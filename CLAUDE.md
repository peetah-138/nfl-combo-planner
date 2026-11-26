# Brief for Claude: the Kalshi combo planner

You are picking up a long-running project with Pete. This file holds the decisions, rules and context from the
earlier sessions (up to version 2026.11.25.140). Read it all before changing anything. When something here
conflicts with what Pete tells you now, Pete wins: update this file in the same change so it stays true.

**Two machines (Pete, 2026-11-23).** The dev Mac (`~/dev/nfl-combo-planner`) is the development machine: it owns ALL
building, testing, subagents, merging and releasing, and keeps this file and `ROADMAP.md` current (setup:
`docs/DEV_MACHINE.md`; how Pete likes to work: `docs/WORKING_WITH_PETE.md`). Pete's MacBook Air is **production
only**: it trades real money, runs the watcher and the web app, and auto-updates from `main`; nothing is built,
tested or merged there. The dev Mac never gets Pete's Kalshi key, `~/combowatch`, a copy of the history database or any
`combo_*.json` file, never runs the watcher and never places orders.

## Goals and strategy

Two goals, in order: **profit is #1, fun is #2.** Smart Buy and Smart Sell are **one strategy** (issue #137): every
buy needs an edge at a fair price *and* a likely route to profit (a good chance to cash out through the shared exit
policy, or a hold with an acceptable win chance). Rank and size in expected dollars, and fail closed when data
can't be read. Pete's rule (2026-11-20): whenever you build anything, it gets a review for profit and delight.

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
- `watcher/combo_watcher.py` — the Mac watcher, the hub and the web app's server.
- `watcher/spa/` — the whole web UI as plain files, one per screen (GitHub #124), so parallel PRs on different
  screens don't conflict: `index.html` (the shell), the css files (`app.css` is the base; `game.css`, `settings.css`, `responsive.css`, `motion.css`, `games.css`, `chrome.css`, `build.css`, `results.css`, `ideas.css`, `stake.css`, `bestbets.css`, `refusals.css`, `scoreboard.css` follow it in this order, each one a contiguous slice of the old single file; put a new rule in the file of the screen it styles, or add a new css file to the end of the `css` list in `MANIFEST.json`), the scripts in load order (`common.js` core/net/
  toasts/sheets/press feedback/tabs/number rolls/freshness/load, `live.js`, `build.js` (panel, slip, quotes, Buy),
  `haptics.js` (incl. the see-through switch, method N), `results.js`, `access.js` (Face ID, web push, secure
  address rows), `build_cards.js` (killer deals, singles), `buy_straight.js`, `build_sections.js` (standing orders,
  days, folds, lines), `charts.js`, `combo.js` (combo detail), `games.js`, `game.js` (game page, clock, field strip,
  scoreboard), `game_tabs.js` (tabs, play-by-play, box score, stats, injuries, last 5, leaders, win chart, scrubs),
  `moments.js` (Sold sheet, wins, big hit, recap, live link), `settings.js`, `boot.js` (start-up and refresh
  loop)), `login.html`, and `MANIFEST.json` (the list and order). `spa_assemble` joins them at import into the same
  `SPA` and `LOGIN_HTML` strings as before (`@@SPA_CSS@@`/`@@SPA_JS@@` lines in the shell). **Edit the screen's own
  file; a new file must be added to `MANIFEST.json`** (keep its shape: the running updater reads the next one's).
  Files keep exact bytes (`login.html` has no final newline). The split was a pure move: `tools/verify_spa_split.py`.
- `watcher/install_mac.sh`, `setup_wizard.py`, `wizard_window.js`, `install_pi.sh` — installers. Both shell installers
  read the files at GitHub's newest commit and then run `combo_watcher.py --install-spa` (non-fatal).
- **Updates and the web app's files:** `update_if_newer` reads everything at one exact commit (`repo_sha`; none = wait),
  downloads every file in the new `MANIFEST.json`, checks each against GitHub's own blob hash (contents API at that
  commit), assembles it and `node --check`s it when node exists, in a temp folder, and only then swaps in spa, engine,
  watcher (spa put back if the rest fails). Anything missing/changed = nothing replaced, the old version keeps running.
  Phone-approved updates (automatic updates off, e.g. the Pi) also need the phone's `spa` digest in its approval
  (engine `spa_approval_digest` = watcher `spa_digest`: sha256 of the assembled SPA, a zero byte, the login page);
  without it they wait, and the self-repair below needs it too (the phone reads the files at the newest commit). With
  automatic updates on, the digest is never required. Fetch + swap run under `spa_locked()` (thread lock + a
  `.spa.lock` file, so the installer's `--install-spa` and the watcher never collide); temp folders are only cleared
  after an hour. An installed spa folder is stamped (`spa/.version`); a folder for another version is still served but
  marks `SPA_STALE`, so `main()` fetches this version's. node only blocks when it is 18+ and says a script doesn't parse.
  Both Python files are written to `.new` before anything is swapped; the running engine is kept as `engine.py.prev`
  until both are in place, so a failed watcher swap puts the engine (and the spa folder) back. `repo_sha` asks the
  commits API, then git's own ref list (`.git/info/refs`, not rate-limited), so an API limit can't hold an update
  back. The phone's `spa_approval_digest` reads only at an exact commit (none = no digest, never stale `main`), all
  files at once with a 40 s deadline; `refresh_pi_approval` skips it when the saved approval is already complete.
  `spa_repair` refuses to run from a git checkout; the updater's working files are git-ignored.
  A watcher whose spa folder is missing or broken still imports (holding page `SPA_FALLBACK`, loud log `WEB APP FILES
  MISSING OR BROKEN`), keeps trading, and `main()` starts `spa_repair_loop`: it fetches the files only when GitHub's
  newest watcher is byte-identical to itself, then restarts. This is also how the first update from 2026.11.21.126
  (whose updater only knows the two Python files) gets its spa folder. Until it has, the watcher serves the real
  app from **`SPA_LEGACY_Z`** (end of `combo_watcher.py`: zlib+base64 of the SPA and login page as they were when
  they moved out, develop 395a7f4; the holding page only if that copy can't be read), so the first start is never
  blank, even with GitHub down. **Remove `SPA_LEGACY_Z` and `spa_legacy` only once every device (Mac and Pi) reports 2026.11.21.127 or later**
  (a device that skips 127 still arrives from 126 with the old updater), with
  `t_spa_transition` (it runs the verbatim 126 updater, `tests/suite/fixtures/updater_126.py.txt`, against a fake
  GitHub through first start, GitHub down, repair, restart; and the Pi's approved path). Rollback: revert the split
  merge; the reverted watcher has the strings inline again and ignores any spa folder.
  The Raspberry Pi is an **alerts-only backup; it never trades**.
- `version.txt` — what the MacBook Air (production) updates to.
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
   smart sell, take profit, lock-in, learned loss-cutting), auto-hedge (≤ `hedge_cap` a hedge, default $100), killer
   deals, standing orders, approving the daily panel, and "Add to today's panel". Everything else buys or sells only on
   his tap. The Pause switch must always be respected. The Pi never trades.
   **Pete-approved exceptions to "loss guards never tune" (release 507 review):** two loss guards may loosen on a league's
   own record, each behind a data gate and `learned_guards`: `sl_feed_age` (how old a score may be: 150 s to at most 300 s,
   needs 20+ episodes) and learned `break_ok` (a loss sale at a break, needs 40+ episodes). Nothing else about the guards
   loosens by itself. A saved 'Never sell at a loss' becomes 'Let it tune itself' on upgrade (Pete, #479). Smart sell
   more's daily limit can reach about $800 a day at the top setting (cap slider max 200 x the 4x multiplier).
   **Self-tuning limits (Pete's standing opt-in, issue #228, 2026-11-21; not live yet):** the guessed numbers smart
   sell, the loss guards and auto-hedge decide with may tune themselves **per league, on evidence**. This supersedes the
   fixed $100 hedge cap: the system may raise `hedge_cap` up to a ceiling of **$150**, and may adjust auto cash-out's
   daily cap (`auto_cap`) **with no ceiling**. A change needs 10+ bets in the band it changes, a gain of ≥ 2% of stake
   and ≥ 2 standard errors, 20 new results since the last step, and must hold on the newest 30% kept back (holdout);
   borrowed values (sport, everyone) may only move the stricter way. **Brake:** 4 automatic-sale losses in a row, or
   losses over 5% of the month's automatic-sale stake, send that league back to the start numbers for 14 days. The
   manual stop-loss switch became **Let it tune itself (default) / Allow (guarded)** (the old 'Never' choice was removed, #479). **Never tuned
   (invariants):** Pause, `can_trade`/the Pi never trades, rule 8, caps failing closed, fresh score and price ages,
   in play, a real fresh quote before any sale or hedge, secrets. **Live since 2026.11.21.133 for smart sell's exit
   numbers only** (#228 PR2-PR4, Selling): self-tuning of smart sell's exit numbers (`knobs_live`, Settings › Money
   "Let smart sell tune its own numbers", on by default under this opt-in; per league, the evidence bar and the brake;
   Pause, the Pi, rule 8 and every cap unchanged) is an existing opt-in. **Brake (Pete's #284 rulings, 2026-11-22):** a
   "loss" is a sale that got less than holding was **expected** to pay at the time of the sale (not how the game
   ended), and when the brake trips a league goes back to its start numbers but **never looser than what it had
   learned** (per number, the stricter of the two). Nothing raises `hedge_cap` or `auto_cap` yet (a later #228 PR wires
   their judge); a value Pete sets himself is never lowered or clamped. **Since 2026.11.21.134** (#228 PR5-PR7) the
   loss guards and their confirmation counts tune live too, and the stop-loss switch is the 2-way choice; `break_ok` (a loss sale only, behind `learned_guards`, see Selling),
   the hedge lock-in numbers, the `hedge_cap` raise (ceiling $150, `HEDGE_RAISE_LIVE = False`) and Smart Buy's
   `sb_ev_min` are still watch-only (Selling).
   **Smart Buy graduation (Pete's standing opt-in, 2026-11-21; not built yet):** per league, once Smart Buy clears
   the bar (50+ settled bets, ahead in dollars, ≥ 55% of days up, CLV ≥ 0, the shadow beating plain), it may
   graduate by itself: stage 2 = its own suggestions (recommend-only); stage 3 = bigger stakes and extra auto-buys,
   always inside every existing cap, Pause, quarter Kelly and rule 8, with an automatic brake on a losing streak.
   Dropping panel approval entirely stays behind the full-auto gate (rule 6). Today's Smart Buy gate only skips.
   **Smart Buy acceleration (Pete, 2026-11-21, #137/#297, "do 1, 3, 2, 4"):** to reach that bar sooner, every priced
   market is scored on paper, a paper book (`sb_paper`, live panel-grade stakes only) feeds the "Bigger stakes" line
   (still display only), settled games are backfilled, and leagues borrow sooner; the only real effect is the dial's
   stricter-only early level (it can only skip more). See Selling › "Smart Buy, faster evidence".
3. **Each device has its own revocable Kalshi key.** The Pi never accepts keys over sync.
4. Don't touch the Vercel project "cynserus" (unrelated business). Repo write access stays with Pete.
5. Latency arbitrage is not pursued.
6. **Full auto with $300** (it picks, times, buys, sells alone) only after the paper panel clears the gate:
   50+ settled bets, ahead overall, most days up (≥ 55%), CLV ≥ 0. Pete chose 50.
7. Never price or buy a combo other than the one on Pete's screen (the quote API checks the leg tickers the page sends).
8. A buy whose outcome is unknown is marked "check" and **never retried** (no double buys).
9. **The dev Mac never gets the Kalshi key, `~/combowatch`, a copy of the history database file or any `combo_*.json` file.** It **may**
   read the production Mac's logs, and the answers to read-only SELECT questions about the collected data (`source=db`,
   rows only, never the file; rule wording changed 2026-11-25 in PR #524; query results are never dumped in bulk to disk), through the read-only,
   credential-scrubbed `/api/logs` endpoint (Pete decision, 2026-11-23,
   issue #377; `docs/LOG_ACCESS.md`): off by default, turned on only on the production Mac itself (Settings › This
   Mac › "Let the dev Mac read logs"), Tailscale only, its own read-only code (only a hash is stored), two allowlisted
   log files plus the SELECT-only data window, credential-scrubbed server-side and failing closed. It can never buy, sell, pause or change anything; nothing
   about it is a money path.

**How these are enforced in code (money-safety hardening, issue #143; tested by `t_safety.py`):**
- *The Pi:* the watcher's `backup_safe(conf, E)` forces `auto_sell`/`auto_hedge` off and killer/maker `off` at
  start, after every settings copy (`fetch_settings`, the listener thread) and before `live_check`/`autosell_pass`;
  `COMBO_ROLE=backup` / `E.ROLE_BACKUP` make the engine's `can_trade()` False and `kalshi_send`/`_signed` refuse every
  non-GET before anything is sent (`has_kalshi_key()` is the plain "has a key" check for reads).
- *Combo accepts (buy and cash-out):* only a definite refusal **before** Kalshi took the accept (a 4xx other than 408,
  the key, Pause) is "refused". Once the accept PUT was sent (or its send timed out / 5xx'd / the Mac was lost), any
  unclear answer, a failed status poll or no confirmation within `ACCEPT_WAIT` (15 s) is **unknown**: marked in the
  order ledger (`mark_rfq_unsure`, keys `<market>|rfq-buy|o` / `<market>|rfq-sell|r`, with the leg tickers), the
  panel/killer get `None` = "check", the web app answers `check` with `COMBO_UNSURE_MSG`, `get_offer` won't re-quote
  the same legs, a cash-out stops (no second accept; `CASH_RETRIES`, or `AUTO_CASH_RETRIES` for auto cash-out, only
  after a definite refusal) and auto cash-out
  leaves that combo alone (`rfq_unsure(t, "sell")`, like `hedge_unsure`). Settings › Money lists them as order blocks.
- *Ledger and hedges across processes:* `combo_orders.json` and `combo_hedges.json` are read-modify-written under an
  `fcntl` lock (`file_lock`), with `save_json(..., strict=True)` (raises and logs "MONEY STATE NOT SAVED"); a mark
  that couldn't be written stays in that process's memory and still blocks.
- *Killer deals:* the dedupe and caps are read with `store_rows_strict` (unreadable = skip), the row goes in as
  "buying" **before** `buy()` and counts toward the caps until updated.
- *Pause:* `E.TRADING_PAUSED` (watcher: `watcher_paused`, the live `conf["paused"]`; web app: `paused_now`) is read
  by `accept_offer`, `killer_act` and `maker_pass`; the web app's combo quote/idea/Buy refuse while paused; turning
  killer/standing orders/Auto cash-out on while paused is undone if `send_synced` failed. **Exceptions by Pete's
  decision:** his own single-bet Sell tap (#245: `sellquote`/`singlesell`) and his own manual Hedge tap (#280) stay
  allowed while Pause is on, because they close risk; they keep every other guard (Pi / trading access, the
  unknown-outcome block, one order per fresh quote, IOC reduce-only at the bid, a lower bid refused, rule 8). Combo
  cash-out taps already worked while paused. Every automatic path and every buy stays stopped while paused.
- *Taps and updates:* the hub's proxy gives `/app/api/act` `PROXY_ACT_TIMEOUT` (300 s) and answers a timeout with
  JSON 504 "may or may not have gone through" (`check` only for `ORDER_ACTS`, the taps that can move money: buy, go,
  hedgego, singlebuy, pot_move); order taps write `combo_tap_busy.json` (`tap_mark`) and `update_loop` waits while it's
  fresh; once an update (or web app repair) is installed, `restart_when_quiet` writes `combo_restarting.json` (the web
  app refuses new taps while it's fresh; the restarted watcher deletes it) and waits (≤ 240 s) for two quiet checks
  before the watcher exits; the web app's `orphan_check` waits (≤ 120 s) for the tap lock before exiting. A manual
  Hedge tap refuses while `hedge_unsure` (an earlier hedge unclear, or bought but not saved).

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

- **`main` is what Pete's MacBook Air (production) and phone run.** A commit on `main` auto-updates them within ~10 minutes (they
  read the newest commit by SHA via the GitHub API, so GitHub's raw-file cache can't hold them back), and the
  app can place real Kalshi orders. Never push to `main` directly.
- **`develop` is the integration branch.** Work on a short-lived branch from `develop`: `feat/…`, `fix/…`,
  `chore/…`. Commit at logical points with clear messages, and open a PR into `develop` at logical points without
  being asked. Squash-merge once the CI check `checks` is green.
- **Every PR must pass lint (`ruff check .`) and the full `bash tests/run_checks.sh`.** CI runs both
  (`.github/workflows/ci.yml`, job `checks`); run them locally first. Fix lint findings in the code; don't
  silence them. Run code review and security review before opening the PR and fix everything they raise.
- **Four reviews on every PR: code, security, profit, delight** (`docs/REVIEW_LENSES.md`). Builder agents run all
  four on their own diff; the release agent runs all four on the whole release diff. Fix every finding or file an
  issue labelled `profit` or `fun`. The PR template (`.github/pull_request_template.md`) carries the checklist.
- **Releases:** a PR from `develop` into `main`, merged as a **merge commit** (not squashed). It must carry the
  version bump (below), and main is back-merged into develop right after. Releases are owned by the session that
  holds the "release owner" role in issue #83 (it also merges the PRs). **As of 2026-11-23 (Pete) the dev Mac
  (`~/dev/nfl-combo-planner`) holds that role.** It merges PRs; cuts releases `develop` → `main` as a merge commit
  with the version bump in the 3 places; folds `docs/changes/` into `CLAUDE.md` / `ROADMAP.md`; back-merges `main`
  into `develop`; comments on #83; and keeps `CLAUDE.md` / `ROADMAP.md` current. The MacBook Air only receives
  releases (it updates itself from `main`). **Standing go-ahead (Pete, 2026-11-19,
  repeated 2026-11-20: "Release on your own"):** that session may release whenever there is enough green in develop,
  without asking each time. All other gates still apply: code review and security review on the release diff, green
  checks, matching versions, screenshots to Pete for visual changes, no new automatic money movement without his opt-in.
- **Version numbers** are unchanged: `YYYY.MM.DD.N`, currently `2026.11.26.141`. Each release bumps N (N keeps
  counting up, it isn't reset) in all three places, which must match: `VERSION` in
  `nfl_combo_planner.py`, `WATCHER_VERSION` in `watcher/combo_watcher.py`, and `version.txt`. Only the release PR
  bumps it; feature PRs don't.
- **Housekeeping:** `git pull` `develop` and `main` at the start of every session and after every merge, on the dev
  Mac (the MacBook Air never builds, tests or merges, so nothing is pulled there by hand). The
  orchestrating session on the dev Mac manages branches and worktrees (Claude worktrees live in `.claude/`, git-ignored) and
  deletes stale worktrees and merged branches without asking. Keep this file current so every session knows what
  changed.
- **Reading production logs from the dev Mac** (Pete decision, 2026-11-23, #377): use
  `python3 tools/read_prod_logs.py` (address and code from the dev Mac's keychain, never a tracked file). `--source db --table X --since ...` / `--sql` reads
  collected data as query results over the same endpoint. That is the only production data the dev Mac gets: never the
  Kalshi key, `~/combowatch`, a copy of the history DB file or `combo_*.json` files (hard rule 9).
- **Fewer merge conflicts: a PR does not edit `CLAUDE.md` or `ROADMAP.md`** (they were edited by most PRs, so
  parallel PRs conflicted every time). Instead it adds **one new file `docs/changes/<issue-or-slug>.md`**: what
  shipped or changed in the product, written in the style of the product sections below, plus a `ROADMAP:` line when
  it adds or removes a roadmap item (template: `docs/changes/README.md`). **The release owner folds those files into
  `CLAUDE.md` / `ROADMAP.md` at release and deletes them** (in the release PR). Until folded, `CLAUDE.md` plus
  `docs/changes/` is the whole brief: read both. Only a **rule or decision** change (hard rules, workflow, Pete's
  standing decisions) edits `CLAUDE.md` directly, and the PR description says so. The same goes for shared lists:
  a new test is one new file (`tests/suite/` header, see Testing), a new screen's styles go in its own css file
  (`watcher/spa/`, listed in `MANIFEST.json`). Run `git config rerere.enabled true` once per clone so a repeated
  conflict is only resolved once.
- **Decisions Pete made on 2026-11-18:**
  - At most **3 subagents** at once was for the MacBook Air (weaker). On the dev Mac (Pete, 2026-11-23) there is no
    fixed cap: manage by CPU, RAM and ports, and give each parallel check run its own `CHECK_PORT_BASE`.
  - **Rebuild `Combo-Watcher.zip` in the release PR** whenever `install_mac.sh`, `setup_wizard.py`,
    `wizard_window.js` or `install_pi.sh` changed.
  - **Dev and test default: no live buying.** Killer and maker modes stay on `watch`.
  - **Visual PRs** may merge into `develop`, but Pete sees screenshots or a short clip **before** the release PR
    (`develop` → `main`) is merged.
  - **Release PRs** are opened and merged by the release owner (issue #83, the dev Mac since 2026-11-23) under Pete's standing go-ahead (see Releases above), with every other release gate intact.
  - **When Pete gives feedback, open a GitHub issue** to track it.
  - **Questions for Pete go through the AskUserQuestion tool**, interview style. Keep replies short.

## Releasing

1. Feature PRs squash-merge into `develop` once CI (`checks`) is green; nobody pushes to `develop` or `main`
   directly. `develop` must be fully merged and green.
2. Bump the version in all three places (see above) on a short `chore/release-…` branch, PR into `develop`,
   squash-merge once `checks` is green. If any installer file changed (see the decisions above), rebuild
   `Combo-Watcher.zip` in the same PR.
3. **Fold `docs/changes/*.md` (every file but `README.md`) into this file and `ROADMAP.md`**: each into its
   product section in the same style, following its `ROADMAP:` lines (add/remove items), then delete those files in
   the same release PR.
4. Run code review and security review on the release diff; fix every finding.
5. Run `bash tests/run_checks.sh` and `ruff check .`. All must pass. Add a test for every change (see
   `tests/README.md`).
6. Open the `develop` → `main` PR, to be merged as a **merge commit** (not squashed). For visual changes, show Pete
   screenshots or a clip first. Merge it when the gates above are met (Pete's standing go-ahead; visual changes need his screenshots first), then back-merge main into develop. The MacBook Air then updates within ~10 minutes; Pete can
   also tap "Check for an update now". An update restarts the watcher (launchd brings it back).

## Testing (the check list)

Run `ruff check .` (config in `ruff.toml`: correctness rules only, no style rules) and `bash tests/run_checks.sh`
before every push; the latter must end with `ALL CHECKS PASSED`. CI runs both on every PR. See `tests/README.md`
for the one-time Mac setup. The checks and `dev.sh` run on a **Python 3.10+** picked by `tests/python_env.sh` (`$CHECK_PYTHON`, else
the watcher's venv if it has the modules, else a git-ignored `.venv-tests/` it builds itself); never Apple's Command Line Tools 3.9,
whose system SQLite crashes on macOS 26.4 (#68). `CHECK_PORT_BASE` moves the test ports when two runs overlap. It runs in a temp folder with fake services and a fake
key, and its web apps use ports 18766+ (4 lanes in parallel, ~4 minutes), so it can't touch the real app or money.
CI runs it as parallel jobs (`CHECK_GROUPS` static/engine/sim/pages, page tests in `CHECK_SHARD=i/5` shards; the split
and each test registers itself with a `# CHECK: group=... [secs=N] [retry]` header, found by `tests/suite/checklist.py`; adding a test is adding one file, see `tests/README.md`) plus an aggregate job named `checks` (the required one). What it covers:
- **Writing tests** (`tests/README.md`): hermetic (engine tests run under `suite/netguard/`, which fails any real
  connection; `st_hermetic` checks it), wait for state not sleeps (`upwait.go_and_hold` before drawing data in), own
  port/temp files/unique ids.
- **Test hygiene (#240).** `test_gamecard_opp.py` used to bump the opponent's score, sleep 0.15 s and then look for the
  `.gc.scored` pulse, but the page clears that pulse after 1.7 s (`scoreWatch` in `watcher/spa/games.js`) and a background poll
  can repaint the card, so on a loaded Mac the read lost the race. It now renders and reads in one `evaluate`, which cannot be
  interleaved (no product code changed). Already fixed on develop: #189 (#234: hermetic engine tests, netguard), #331 (#330:
  `_clear_of_starts` pins the test clock), #298 (`run_checks.sh` counts a non-zero exit status as FAIL), #159 (`_SID` counter
  in `store_suggestion`, #220).
- **Engine tests no longer depend on the time of day (no product change).** `t_panelpipe` and `t_review` failed on CI runs
  between 1 a.m. and 4 a.m. Pacific (for example 11:54 UTC, 03:54 Pacific) and passed the rest of the day; it was not the
  calendar date rolling over. Their fixtures put kickoffs at `now + 3h` and `now + 4h` by the wall clock, and the panel's
  "today" deliberately ends at 4 a.m. Pacific (`_local_day_end`; the panel day itself starts at 4 a.m., `_panel_day`). In
  that window the fixture games fell after the cut, were treated as tomorrow's, the panel came out empty and the tests
  failed. Verdict: **test bug, not a product bug**; the 4 a.m. Pacific boundary is intended and unchanged, and no trading
  behavior, sizing or money path was touched. `t_panelpipe` and `t_review` now pin the clock (`time.time` and
  `E.dt.datetime.now`) to noon Pacific on 2026-11-24 (time still moves forward, only the start point is fixed). New
  `t_clockday` pins the clock at the boundary: `_local_day_end` and `_panel_day` at 03:59 and 04:00 Pacific, and
  `build_panel` at 02:00 and noon (a 03:30 game is today's, a 04:30 game is not, games 3h and 4h ahead at noon both are).
  When writing a test with kickoffs relative to `now`, pin the clock first (see the top of `t_review`).
- Both files compile (Python 3.10), `node --check` on every `watcher/spa/*.js` and on the assembled SPA's and
  `LOGIN_HTML`'s scripts, the spa files/manifest (`t_spa_files`) and the update path (`t_spa_update`),
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
- A simulated Mac run (fake Kalshi; the log must be clean) and a simulated update install (copies the watcher and its
  spa folder to a temp home, fake GitHub file list; the new web app files must be swapped in; never touches the repo).
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
- **Spreads and totals (issue #117 part B): recommend-only selection.** Build › Spreads & totals no longer lists every
  strike: `line_recommend` (the watcher's Build runs it **off the app lock** in `lines_work`/`lines_kick`, a thread per
  sport, copy ≤ 60 s old, waits ≤ 1.5 s, last good copy otherwise; order books read side by side within
  `LINE_REC["budget"]` 3 s by `books_now`; `everything=True` is no longer used there) shows a strike only
  when (1) its edge after the fee clears the league's **learned bar** (`line_min_edge`: own once 30+ settled games,
  else its sport's (`LINE_SPORT`), else everyone's, else `LINE_MIN_EDGE`; never under `LINE_MIN_EDGE`, max 10¢; file
  `combo_line_edge.json`), (2) its kind of strike isn't **losing to the close** (`line_clv_block`: table `line_clv`,
  price at recommendation `rec` or panel buy `buy` vs Kalshi's last price before the start, read within 90 min of it
  (`line_clv_seen` in `line_candidates`); blocked at ≥ 30 games, mean ≤ −0.5¢ and ≤ −2 SE, per league/kind/band; the
  sport/everyone level may only block), (3) it **fills inside the edge** (`line_fill` walks every ask level of the book,
  `book_asks`/`_ask_ladder` filled by `book_depth`'s same call, fee rounded up per order; stake = the buy sheet's
  `_size` on the 30%-shrunk edge, capped by what fills; unreadable book = not shown), (4) Smart Buy's
  `simulate_exit` (smart sell's exit policy, `_sb_sim`) passes `smart_buy_ok` (route sell or hold, ≥ `SB_EV_MIN`), and
  (5) expected dollars at the fillable size (hold EV after fees + the policy's adjustment) ≥ `SB_EV_MIN`. Ranked by
  expected dollars; cards show route ("Likely to cash out early for a profit: 58%" / "Profit if it holds"), stake,
  contracts, expected profit, the bar. They are shown as the spread/total rows of **Best bets today** (no separate board
  since #63; `lines_priced`/`lines_nobook` still ride on the Build answer; Best bets' own empty state explains a quiet day). **Weekly** `line_edge_tune` (watcher, with `smart_tune`):
  one 0.5¢ step per league/sport/all and kind when the strikes it adds/drops cover 10+ games and move the result ≥ 2%
  of everything staked at the bar ($1 a strike, 30+ games at the bar; settled `line_fairs` rows); ties stay; never
  under the start. **Panel: only stricter** (`_line_ok` after the raw `line_edge`: learned bar, CLV block, and
  `fill_cap` < $2 = out; `_size` never over `fill_cap`; book unread = today's rule, the buy-time recheck still
  applies). The buy sheet's green Buy for a spread/total uses `max(LINE_MIN_EDGE, learned bar)`. Results › What's
  working › Bet types: "Spreads & totals: your bar and the close" (`analytics()["line_sel"]`). Nothing here buys or
  sells; Pause, caps and rule 8 untouched. Tests: `t_linesel`, `test_linesel_ui`.
- **Odds API credits (issue #175).** Every odds-service answer's `x-requests-remaining/-used/-last` headers are
  recorded (`odds_credits_note`, in `fetch_book_odds_one` and `tennis_keys`; no extra calls) in `combo_odds_credits.json`
  (newest numbers plus a small history, under `file_lock`). `odds_credits()` gives remaining, burn per day (needs 6 h of
  history since the last reset, looks back 7 days), projected run-out, and the reset date (a month after a reset we saw,
  i.e. credits jumping back up; else the 1st of next month UTC, marked an estimate). **Low** = run-out before the reset,
  or at/under the floor (max(40, 5% of the plan)), or none left. Settings › The Mac shows it ("Sportsbook odds credits":
  N of M left, pace, runs out / lasts past the reset, resets (about) <date>, a bar; `odds_info` in `mac_settings` and
  `/app/mac-info`, numbers only, never the key). **Low mode** (`odds_saving`, turns off only once comfortably back:
  1.5x the floor and lasting 2+ days past the reset): `HubOdds.worth_credits` (and the phone's `fetch_book_odds`) only
  asks for a league whose panel candidates, panel bets or held bets (`odds_interest`/`held_for_credits`, read-only) have
  a game starting within 4 h or under way; other leagues keep free lines (old sharp lines still expire at 45 min). One
  push per low state per reset cycle (`odds_low_alert`, "Odds credits"). It never buys, sells or touches Pause.
  **Low mode and buying (remove-only):** a far league then falls back to free lines (ESPN, Polymarket), so while low
  mode is on, a panel bet or Buy idea with a game-winner pick (not priced live) more than 4 h away (`CREDIT_NEAR`) or at an
  unknown time that has **no odds-service line** is left out (`low_credit_filter` in `build_panel` before Smart Buy, on
  the longer plays and in `_replacement`; `low_credit_ideas` in `live_ideas`). Which line priced a pick: `sharp_snapshot`
  tags its games `sharp`, `attach_fair` sets `sharp_line` on each side, `_cand` legs and the idea's `legs_info` carry it
  (an older idea with no record counts as free). Spreads/totals are always priced on ESPN's lines, so they're untouched.
  Same plumbing as Smart Buy's skips: the same dicts, order and stakes minus the dropped ones, listed in `sb_skipped`
  with `credits: true` (their stake stays out of the extras budget; their game may come back as an extra, on Pete's Add,
  once it is near or has a sharp line), shown as "Saving odds credits: left out N".
  Normal mode returns everything unchanged; an error keeps the bet. If `build_panel`'s stats recompute after any skip
  fails, it logs, keeps the skips (never puts a bet back) and keeps choose_panel's numbers marked `stale`. Test: `t_lowcredit`.
  Asking only for sharp bookmakers (`bookmakers=` instead of `regions=us,eu`, 1 credit instead of 2) was **not** done:
  the fair price falls back to the median of all books when neither Pinnacle nor a sharp book lists a game, and a
  bookmaker filter would change that. Tests: `t_oddscredits`, `test_oddscredits`.
- Live scores from ESPN's free scoreboard (none for EuroLeague, UFC, tennis). The AHL isn't on ESPN: its scores,
  periods and clocks come from the league's own public score feed (the JSON theahl.com's widgets read; HockeyTech,
  no login; `_fetch_feed_scores`, light polling), with the same cache and last-good-copy fallback as ESPN.
- **College football scores cover all of Division I (issue #224).** `SPORTS["ncaaf"]["score_q"]` = ESPN group 90 (FBS 80 +
  FCS 81), read only by `fetch_scores`; the free lines (`free_snapshot`) and game picking keep `q`/`espn_q` = group 80, so
  no new game is priced from ESPN because of it. Kalshi lists FCS games (Jackson St. at Alcorn St.) that group 80 never had.
  A college football game ESPN still has no record of gets Kalshi's public live data as a **display-only backup**
  (`KLIVE_BACKUP`, `_kfootball`; `klive_events` asks only when `leg_score` has nothing), same isolation rule as below.
  An open pick at 99.5%+ reads ">99%", never "100%" (`chance_pct`, SPA `pct`). Test: `t_fcs_score`.
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
  **Order adapter hardening (issue #102; no automatic path loosened).** (A) `order_intent` forces `reduce_only` whenever a
  legacy body says `action: "sell"`, whatever the caller sent: sell YES becomes an ask and sell NO a bid, and without the
  flag either could open a position. A legacy sell that is not immediate-or-cancel is refused (Kalshi takes reduce-only
  only with IOC), so a forgotten flag fails closed; the in-repo sellers already set the flag. Test: `t_orders_v2.py`.
  (B) The hub's `kalshi` op used to forward any POST/PUT/DELETE under the read prefixes (`HUB_PATHS`). `hub_refusal` in
  `combo_watcher.py` now lets a write through only when it matches `HUB_WRITES`: order create and single-order cancel
  (old and new paths), RFQ create and cancel, quote accept, and combo-market creation. Anything else (batch or amend
  orders, other `/portfolio` writes) is refused and logged as `phone request refused: <reason>`. The
  transfer/allocation/subaccount block stays; reads are unchanged. Test: `t_hubwrites.py`. (C) `game_detail` checks the
  ESPN event id with `re.fullmatch(r"[0-9]+", ...)` (no trailing newline, no non-ASCII digits). Test: `t_gamedetail.py`.
- **Kalshi's refusals, shown honestly** (issue #134). A definite refusal is Kalshi's own words, in full (`body_words`,
  600 characters, tags stripped), never a guess: a 401/403 says "Kalshi refused this (403 code): <its message>" and adds
  "your API key may need write access" only when Kalshi itself says so (`perm_words`, `key_write_denied`). A refusal for
  the account or region (`is_restriction`: 400/401/403/451 with words like "residents ... not allowed", "jurisdiction",
  "region") is written to `combo_kalshi_block.json` (git-ignored; `note_refusal`, `restriction_info`) and the Mac **holds
  back** the same refused request: buys wait 30 min, then 1 h, 2 h, 4 h while it keeps refusing; automatic sales 10-30
  min (`hold_refusal`, `sell_held`). Held (automatic paths only): the shadow's buy-idea quotes, the panel (`hold: "region"`, back to
  "scheduled", never "failed" or "check"), killer deals, standing orders, the automatic hedge (`hold_refusal(..., strict=True)`),
  auto cash-out and smart sell. **Pete's own taps are never held** (`manual_tap`, set around `api_act` and the hub's build
  form: Get price, Buy, Buy straight, idea buys; his sell taps too): they go through the usual guards (Pause, caps, rule 8)
  and are the check after a hold; if Kalshi refuses one again the hold is renewed at the same level (`_restrict_note`), not
  escalated by taps. After a hold the next buy Pete already approved is the check for the panel. Kalshi taking an order clears the
  note (`restriction_clear`), a note a day old is ignored. No harmless read reveals a cleared restriction, so nothing is
  placed just to look. The page shows a calm banner under the header (`rsBan`, `#rsban`) and a sheet with the full message
  (`refusalSheet`, selectable, Copy); `restrict` rides on Live, Build, Settings and panel answers and `refusal` on a refused
  tap (`api_act`). **Rule 8 is untouched:** timeouts and 5xx are `OrderUnknown` ("check", never retried, never a region
  hold). This only reports and waits; it never changes a location, routes an order elsewhere or adds money movement.
  Tests: `t_refusals`, `test_refusals`.
- Leagues: NFL, NBA, NHL, AHL, college football, men's and women's college basketball, EuroLeague, UFC, soccer
  (EPL, La Liga, Serie A, Bundesliga, Ligue 1, MLS, Liga MX), ATP tennis, and "Mix" (cross-sport).
- AHL: Kalshi `KXAHLGAME` (event codes include a start time, e.g. `26NOV191900HERCHA`), odds `icehockey_ahl`,
  require_line, hockey shapes, live scores from the league feed (Kalshi's team codes can differ from the feed's,
  e.g. CHA/CLT, so `AHL_ALIAS` maps them; names are matched too).

- **ESPN free lines, one day per request (issue #341 A, #336).** ESPN's scoreboard now refuses a date range
  (`dates=A-B` = 400), so `free_snapshot` had silently returned no teams: no game-winner side had a `src`, `closes` stayed
  empty, singles/value/slate combos and the shadow's quotes found nothing and the panel held only spreads/totals.
  `espn_scoreboard(path, q, days, code=)` reads one day per request (4 at a time, de-duplicated by event id, never
  raises; `ESPN_DAYS` = 4 days for daily leagues, 8 for weekly; last read per league in `ESPN_FREE`; one total deadline,
  `ESPN_DEADLINE` = 15 s for all days of a path (was up to about 24 s, #351): a day not back by then counts as unread
  (`ESPN_FREE` bad), the answered days are kept and nothing raises, so fewer lines, never invented ones; test
  `t_espn_deadline.py`). `fetch_scores`
  still asks a range and falls back to today's board. With lines back, killer deals and standing orders (existing
  opt-ins, starved by the bug) could act again; #344 below makes them need an odds-service line.
- **Killer deals and standing orders need an odds-service line (issue #344, Pete 2026-11-23; stricter only).**
  `sources_agree` (unchanged) counts ESPN's moneyline and Polymarket as two sources, so free lines alone could buy.
  Now `sharp_backed(snap, pick, fair)` must also hold: the merged snapshot's `parts` for that team carry a `pinnacle` or
  `odds service` chance (`SHARP_PARTS`) within `KILLER["agree"]` (2 points) of the fair used, the team isn't in
  `sharp_stale` (`merge_books` lists teams whose sharp line gave way to a fresh free line) and its line isn't `line_stale`. Missing/junk = not backed. `killer_check` adds
  `NEED_SHARP_WHY` per leg (held back and logged as "near-killer"); `maker_pass` skips free-only candidates (no order, no
  row; logged at most every 10 min, `_CAP_LOGGED["maker_sharp"]`) and **cancels** a resting order that lost its backing
  (`maker_cancel`, the only Kalshi write added). In low-credit mode far leagues' standing orders wait. Tests:
  `t_needsharp.py`, `t_profit2.py` C.
- **Kalshi's price as fair, on paper (#341 B).** `mkt_fair_shadow` (end of `panel_collect`) logs every priced side,
  spread/total and combo candidate into `mkt_fair` (pre-game the latest row per market, ≤ every 30 min; in play one row
  per half hour; phases `pre`/`live` never pooled): Kalshi's mid, today's fair, the anchored fair `mid + w·(fair − mid)`,
  the claimed edges and `vanish`. `w` is 0 until earned: `mkt_learn` (hourly, per league/type/phase) picks the grid weight
  (0-1 in quarters) with the lowest log loss on settled markets (one side per game) and keeps it only with 200+ markets,
  ≥ 0.002 better than the mid and ≥ 2 SE (in-sample: a held-out check must come before any pick uses it). `mkt_resolve`
  fills results (5-day give-up), 60 days kept. Results › What's working: "Kalshi's price as fair" (`mktCard`,
  `mkt_fair_summary`). Picks never change; long shots read the earned `mkt_weight` (Build page).
- **In-play audit (#341; Pete: an in-play bet is judged on a real comeback route, not a pregame-style edge). Stricter
  only.** `live_exit_ok(ticker, event, fair, ask)` runs Smart Buy's exit simulator from the live state and must pass
  `smart_buy_ok` (fails closed): Buy straight and Live's single-idea quote show no green Buy for a game under way without
  it (warning `exit`). The panel's `smart_buy_gate` skips a live-priced bet without a likely profitable exit **whatever
  the switch or dial** (error = skip), re-run on the fresh price in `_buy_panel_bet` after `live_recheck` (a skip, never
  "check"). In-play Buy ideas (`_idea_in_play`) show only once the shadow found `smart_buy_ok` (`IN_PLAY_WHY`). Started
  spreads/totals are never recommended (`_line_rec_one` "started"); Build's random and value combos use only pre-game or
  live-checked picks; `get_offer` gives no green Buy for a non-panel combo with a pick under way
  (`idea_combo_live_gap`); Best bets drops them; `shadow_pass` sends no combo idea with a pick under way and
  `single_pass` skips any game under way before any idea, killer check or push (no alert quotes sharp books for a live
  game; regression in `t_inplay_exit.py`). The richer in-play comeback model (#348) is described right below.
- **Richer in-play comeback model (#348, follow-up to #341).** An in-play bet needs today's gate (`smart_buy_ok` on the
  live state) **and** the comeback model: is a comeback, or a partial one big enough to sell early at a profit, realistic?
  Stricter or equal only: it can hold a bet back, never let one through that today's gate refuses (loosening is a later,
  data-gated step).
  - **One entry point:** `inplay_exit_ok(c, sim, now, source)` = `comeback_judge` (old AND new). Used by `live_exit_ok`
    (Buy straight's and Live single ideas' green Buy), `smart_buy_gate`'s live branch (panel, whatever the switch or dial),
    `_buy_panel_bet`'s buy-time live recheck, Best bets' live candidates and the shadow pass (`smart_buy_shadow` logs the
    verdict for every in-play candidate). Live's in-play Buy ideas (`smart_buy_ideas_gate`) need the comeback verdict on the
    same quote (`cb_verdicts`, table `comeback_shadow`) besides the old one and are now gated **whatever the Smart Buy
    switch** (#352: before, the switch off let them through; a fix, stricter).
  - **Features** (`comeback_features`, `_cb_chance`), from score feeds already fetched (no new request): football: who has
    the ball, yards to go (`_cb_yards`, ESPN's ball spot), down and distance, as the drive's expected points added to the
    lead of the team with the ball; basketball: pace (points so far vs `CB_PACE`, time left scaled 0.75-1.35x) and an
    opponent's run of `CB_RUN` points in the last 8 minutes (stricter only); hockey: shots on goal; soccer: an expected-goals
    stand-in (0.30 per shot on target, 0.05 per other shot) and possession, as a shot-share nudge on the prior (at most +-0.4
    probit, full weight at `CB_SHOTS_FULL`); every sport: the closing line as the prior, then the live model and the league's
    live calibration (`calib_fair(..., table="live_fairs")`). The ESPN scoreboard parse keeps hockey/soccer team stats on the
    score dict (`stats`/`ostats`, `_cb_team_stats`). **Fail closed:** a stale or missing score, no closing line, football with
    no ball position, NHL/soccer with no shots, a spread/total, an excluded sport, a simulator that can't model it, or any
    error = not ok (no green Buy, no idea, no push). Not in the feeds, so not used: power plays, real xG, the AHL's shots
    (AHL needs only score and time).
  - **The league's own recoveries** (`comeback_table`, `_cb_entries`, `comeback_rate`): from `price_path` rows recorded **in
    play only**, per ticker: from each lead (in scoring units, `CB_UNIT`, clipped to +-3) and quarter of the game left, did
    the bid later reach a sale at +10% (`SB_GAIN`) after both fees before the end? One vote per game per bucket; a path that
    stops before the end is censored; one market per game; the newest 120k rows. Shrinkage n/(n+20) everyone -> sport ->
    league toward the model's cash-out chance; borrowed levels may only lower it, only the league's own rows raise it. Used
    once a bucket has 15+ rows (`CB["min_n"]`), else the model decides. Rebuilt hourly per process in a background thread
    (30 days); no gate waits for it. The recorder stores the share of the game left (`price_path.frac`; old rows are read
    from the score's clock text).
  - **Verdict:** `simulate_exit` on the feature-adjusted chance, the cash-out chance replaced by the empirical one when used
    (the sale's share of expected dollars scaled down with it, never up); sell route at 50%, hold route as today, expected
    dollars at least `SB_EV_MIN`.
  - **The other side (Pete, 2026-11-23), paper only:** whenever one side of a two-way game is judged in play, its opponent
    is scored with the same model and the full gate (old AND new, positive expected dollars after fees, fresh score, gap at
    most 6c) and logged as source `other`. Nothing is ever shown, pushed or bought from it. **Which side, game by game
    (Pete: "a judgement call")**: both sides are put on one scale (`_cb_side_score`: expected dollars on $5 after fees times
    the league's learned weight `cb_weight`, realised over predicted dollars shrunk n/(n+30) toward 1, bounds 0-1.5, less
    half the spread per contract); `cb_pick_side` picks the better side only if it clears the full gate and scores above zero
    (logged as `pick`, `pick_t`, `pick_why`, `score`). Scored only off the tap paths (never on a quote or a buy).
  - **Measured:** `comeback_shadow` (one row per bet and source per 10 min, kept 45 days). `comeback_resolve` (in
    `smart_buy_learn`) scores each single on the recorded prices (recovered or not; dollars on $5 selling at the first
    profitable chance else held). Results > What's working > **In-play comebacks** (`comeback_summary`,
    `analytics()["comeback"]`, `cbCard` in `results.js`): per league, checked, predicted (old -> new) vs actual, what the new
    model held back and how those did, the paper side picks and the other side's paper record. Live's skip line says "Games
    under way: left out" when only in-play ideas were left out. Never touches selling, sizing, caps, Pause or rule 8.
    Tests: `t_comeback.py` (leakage, borrowed-only-stricter shrinkage, fail closed, a 300-state property test that the
    verdict is never looser than today's, features, logging/throttling, paper side, resolve and summary, the ideas gate with
    the switch off, every path uses it, no request); `t_inplay_exit.py`, `t_live_panel.py`, `t_orderbook.py` stub the layer.
- **Killer combos respect the quote check's verdict (#398; stricter only).** `shadow_pass` used to take a killer combo on
  `pct >= KILLER["combo_pct"]` alone, so a quote `get_offer` held back as `why="suspect"` (over `COMBO_SUSPECT` = 1.30 of
  fair, a wrong chance far more often than a gift) or under its bar still reached `killer_check` and `killer_act`. Now
  `ok=False` from `get_offer` is final for the killer combo path, in watch and on mode: the deal is skipped and logged
  ("near-killer combo held back: the quote check said suspect (140% of fair)"). An ok quote behaves as before; killer mode
  off logs nothing new. **Wider than "suspect" (Pete chose to KEEP this):** the skip is on ANY `ok=False` verdict, so it also
  covers the **inplay** and **longshot** verdicts and combos **under the green bar**, even when the quote is above the 115%
  killer line; such a quote is held back and logged with the verdict's own words. Fewer killer buys, never more; no new
  switch; no valuation, early-exit, caps, Pause or rule 8 change. Test: `t_killer_suspect.py` (suspect and under-bar quotes
  skipped with a logged reason in watch and on mode; an ok quote still reaches the killer check and act).
- **`mkt_learn` recency-stability veto (#345; stricter only, not a true holdout).** `mkt_learn` keeps a grid weight on the
  books when it beats Kalshi's mid by `MKT["gain"]` (0.002) and 2 standard errors over 200+ settled markets. It now also
  needs the same weight to beat the mid on the newest 30% of that league/bet type/phase's settled markets **by game date**
  (`kick`, else the log time; ties by id; `MKT["hold_share"]`): the log-loss gain on that slice must be above zero, otherwise
  the weight is 0 (Kalshi's mid alone). The weight is still picked on all the markets, the newest 30% included, exactly as
  before, and it never adds or raises a weight, so every learned weight is 0 or what the old rule gave. A vetoed weight moves
  `longshot_leg_fair` from the blend to Kalshi's mid, so it can change which legs fall in the 65-80% band (the one place
  behaviour can move: the paper table and the long-shot `mkt_weight` reads only see a weight that is 0 more often).
  `MKT["hold_min"]` (30) is inert at `min_n` 200 (30% of 200 = 60); it only matters if `min_n` is lowered. Each `MKT_W` entry
  also carries `hold_n`, `hold_gain` and `vetoed` (true when the in-sample bar was cleared and the holdout disagreed);
  `mkt_fair_summary` groups show `hold_gain` and `vetoed`. Picks, stakes, buys and sales are unchanged. A truly out-of-sample
  test is a follow-up issue. Not done (the issue's second sentence): whether the 24 withdrawn carry RFQs a day affect maker
  quote quality needs real quote data and cannot be answered from the dev Mac; left open on #345. Tests: `t_mkthold.py`
  (books right throughout is earned; right in old games and wrong in the newest 30% clears the old bar and is vetoed; ordered
  by game date not id; `kick=None` falls back to the log time; tied kick breaks by id; mixed kick/log-time rows;
  stricter-only across datasets; a slice under `hold_min` earns nothing, distinct from a real veto; under 200 markets is not
  "vetoed"), `t_panelpipe.py`.
- **Live data gaps: UFC round and clock from ESPN (#14, #25, #21; display only).** Already there (checked, not rebuilt): AHL
  scores, periods and clocks come from the league's own feed (`_fetch_feed_scores`, #14); tennis, EuroLeague and UFC come
  from Kalshi's public live data (`kalshi_score`, `display_score`, `KLIVE`, #25); the page's polling and Live rebuilds were
  already sped up, and the remaining wait is the feeds' own cache times (`SCORES_MAX_AGE`), kept so Kalshi and ESPN are not
  hit harder (#21: no further safe display-only change found). **Added:** Kalshi's UFC data had no in-fight round or clock
  ("Round 2 of 3 · no clock"), so `espn_mma_refresh(events)` reads ESPN's free `mma/ufc/scoreboard` (same `ESPN_SITE` base
  and hub cache as the other ESPN reads): the current board plus at most `ESPN_MMA_DAYS` (2) dated boards for fights on days
  it does not cover. It runs from `kalshi_live_kick.run()` only when a UFC market is held or shown, polls at most every
  `ESPN_MMA_LIVE` (8 s) while a fight is on and `ESPN_MMA_IDLE` (120 s) otherwise, and a failure pauses it 60 s
  (`ESPN_MMA["cool"]`). `espn_mma_parse` turns events into fights keyed by both fighters' codes; `espn_mma_score(l)` returns
  `leg_score`'s shape from the pick's side. Wording: "Round 2 of 5 · 3:12 in" (ESPN's MMA clock counts UP, so a decision
  reads 5:00), "End of Round 2", "In progress" with no round, "Fight over · R3 5:00". `kalshi_score` uses ESPN's answer only
  when Kalshi has none, or ESPN says in play and Kalshi does not say post. The wording is built from ESPN's field names plus
  a real finished sample (no fight was on air); it is unverified live. **Isolation:** `src` stays `"kalshi"`, so the UI
  treats it as a display feed; nothing here is read by `leg_score`, `fetch_scores`, `SCORES_BY`, `pick_state`, `started`,
  smart sell or any buy, sell or panel path; no new Kalshi or Odds API call; any error is caught and logged once
  (`klive_log_once("espn_ufc", ...)`). **Not added:** tennis from ESPN (its scoreboard lists tournaments, not live set/game
  state keyed to Kalshi's tickers; Kalshi's own feed already gives sets, games and points), EuroLeague (no free official feed
  with a stable open API; Kalshi's already gives points and clock), AHL via Kalshi as a fallback (the league feed is live and
  complete; a second source adds disagreement risk). Tests: `t_espn_ufc.py` with `fixtures/espn_ufc.json` (a trimmed real
  ESPN board: parse, both sides, round/clock wording, finished fights, request counts and cooldown, fallback precedence, no
  money path reads it); `t_kalshi_live`, `t_robust` unchanged.
- **News and game-context recorder (record only; beside `signal_shadow`).** Pete chose to record, with zero trading effect,
  two signal families to test later against the market. `signal_events` (engine block "signal events", hooks in
  `panel_collect`, `fetch_scores` and `price_seen_markets`) writes three append-only tables in the history file, behind the
  existing `sig_shadow` flag (ON by default). It makes no Kalshi, Odds API or ESPN request of its own: it reads the injury
  cache (`INJ`), `PRICE_SEEN`, the panel's games and the scoreboard records `fetch_scores` already fetched. A tick runs at
  most every 20 s (`SEV["tick"]`), writes in one transaction under the history lock, swallows every error, and nothing in a
  decision path reads the tables (`t_signal_events.py` F scans for it).
  - `sig_news(id, ekey unique, ts, news_ts, league, team, player, pos, kind new|change|removed, old_status, new_status,
    material, game_event, ticker, bid, ask, fair_book, fair_src, px_age)`: one row per injury change. The first read after a
    start only sets the baseline; an empty read is never treated as news.
  - `sig_news_fu(news_id, horizon, ts, delay_s, bid, ask, fair_book, fair_age)`, unique on (news_id, horizon): the same
    market at +5/+15/+60 min from the latest price already read; a sample more than one horizon late is dropped. `fair_book`
    (here and in `sig_news`) is stored only when the sharp-book price is fresh (within the recorder's fair-age limit); a
    stale one is NULL while `fair_age` is still recorded. A failed write is retried at the next tick, not lost.
  - `sig_ctx(ts, phase pre2h|start, mins_to_start, league, game_event, start_ts, ..., neutral, indoor, venue, home/away rest,
    b2b, g7, travel_mi, tz, wx_temp, wx_wind, wx_precip, wx_text, bids/asks/fair)`, unique on (game_event, phase): written
    about 2 h before the start (window 20 to 125 min) and at the start (up to 20 min late). Unknown stays NULL. Travel and
    time zones come from a small static table inside the engine (`SEV_GEO_RAW`, NFL/NBA/NHL; the Air copies only the app
    files).
  - Retention 365 days (`_sev_prune`, hourly) plus a row ceiling per table (60,000 / 200,000 / 80,000) that stops writes and
    never deletes to make room. `create ... if not exists` only, so an existing history file is never altered.
  - `tools/signal_events.py`: read-only (`mode=ro`), aggregates-only report (groups under 20 hidden): the news event study
    and the 70/30 residual test of context factors against plain sharp fair, with game-level bootstrap ranges. Not reused:
    the watch-all recorder's helpers (its PR was not checked); this block keeps its own small helpers. Docs:
    `docs/EXIT_REPLAY.md`.
  - Tests: `t_signal_events.py` (detection without duplicates, follow-ups, NULLs, retention, ceiling, migration, errors
    swallowed, no decision reads, hook counts, no network), `t_signal_events_tool.py` (synthetic history: read-only,
    aggregates only, n<20 hidden, missing tables).
- **Paper shadows: player-prop prices and slate concentration (#323 step 2, #332, #341).** Two more write-only recorders,
  same pattern as `signal_shadow`: bounded, every error swallowed, off the trading path, append-only, and **no decision reads
  them** (`t_paper_shadows.py` fails if the engine mentions the tables outside the block). Neither adds a Kalshi or Odds API
  request, neither buys, sells, sizes, ranks or gates anything.
  - **`prop_shadow`** (#323 step 2). `fetch_series` hands every market list it reads to `prop_shadow(out, series)`. It only
    acts on a plain player-prop series (regex `PROP_RE`: NFL RECYDS/REC/RSHYDS/PASSYDS, NBA PTS/REB/AST/3PT, NHL GOAL/PTS;
    protected `…PROT`, ladders and soccer never). Per market: ticker, league, stat, strike, bid, ask, mid, size at the ask
    (when Kalshi sends it), volume, the game's kickoff (`KICKOFF` of the matching `KX<LG>GAME-<game>`; unknown or past
    kickoff = skipped, so pre-game only), and `result` when a settled market comes back. Kept only with a mid of 10-90% and a
    gap of 6c or less (smart sell's rule), one row per market per 30 minutes, at most 800 rows a call. The last row before
    kickoff is the close. **No fair is recorded:** the recon found no free de-viggable price, and reading the ESPN/DraftKings
    line would be a new request. **Today nothing reads a prop series, so the table stays empty** until a later, separately
    approved poller (public `GET /markets?series_ticker=KX…`, about 15 series every 30 minutes, no key) feeds it. Settings
    key `prop_shadow` (ON for recording; false = off). Bound: 14 days and 150,000 rows (checked every 6 hours).
  - **`slate_shadow`** (#332). Called once at the end of `panel_collect` for each league. Aggregates only (no tickers or
    ids), at most one row per scope per 30 minutes: `held` (all leagues; the open bets from the account and panel caches via
    `game_exposure`, weighted by dollars at risk) and `pool` (that league's panel candidates before the choice, counted
    equally). Columns: bets, games, total weight, share on the top game and top three, Herfindahl index (`hhi`) and effective
    number of games (1/hhi), most bets on one game, share in the top league, share in the top kickoff slot (3-hour blocks,
    Pacific; pool only), share of bets that are favourites (chance 50%+; pool only), share in the top bet class
    (single/line/combo; pool only), combos with two picks in one game. Join `day` to the stored panel's predicted chance of
    finishing ahead and its result to answer "did a samey slate cause the bad day". Settings key `slate_shadow` (ON; false =
    off). Bound: 90 days and 20,000 rows.
  - **#341 (a) and (b) were already built** (`mkt_fair_shadow` / `mkt_fair` and the cost-carry test / `carry`, merged with
    #347 and follow-ups), so nothing was added for them. Still open: the held-out check before the learned market weight is
    used by any pick (ROADMAP), and scoring the carry test needs more settled days. Tests: `t_paper_shadows.py`.
- **Watch all games: price paths and signals for every market the app already fetches.** Pete's goal is that the system keeps
  learning from many games, not only its own bets, to get better at prediction and sell timing (day trading: sell above cost
  before close, or settle at 100). `broad_shadow(code, every, lc_all)` (engine, one wrapped line in `panel_collect` after
  `signal_shadow`) writes a price path and the signals for every market already in `PRICE_SEEN`, with the sharp-book /
  live-model / line-model fair and the cached score, into three append-only tables: `bp_mkt` (market, game, sport, kind,
  kickoff, final result and its source), `bp_path` (bid, ask, depth, fair and its kind, lead, points, share left, state,
  possession, down, distance; prices in thousandths, `BP_SCALE`) and `bp_day` (counts per day). It never writes `price_path`
  (live decisions read that), makes no request, places no order, swallows every error and is read by no decision
  (`t_broad_shadow.py` scans the engine and watcher for any mention of the tables outside the recorder). Setting
  `broad_shadow` (default on) turns it off.
  - **Storage controls (`BP` dict):** change-only rows, at most one a minute from 3 h before kickoff to 6 h after (heartbeat
    10 min) and one every 5 minutes (heartbeat 3 h) otherwise; a flush at most every 45 s, capped at 3,000 rows and 0.15 s,
    resuming where it stopped; retention 21 days; oldest-first row cap at 80% of a 250 MB ceiling; recording stops at the
    ceiling or under 3 GB free disk and resumes after pruning. Pruning, label copying (from `closes`, `live_fairs`,
    `line_fairs`, `mkt_fair`, plus a separate price-implied label, `rs` 9) and the size check run from `resolve_closes` in
    the history loop (`bp_maintain`), never the panel pass. The watcher log gets one counts-only line an hour (markets,
    games, rows today, table size, labelled share).
  - `tools/exit_replay.py --broad` replays the fixed exit rules on the broad dataset per sport x price bucket, net of fees
    and spread, with a game-level bootstrap and a 70/30 time split, aggregates only (groups under 20 games hidden), read-only
    (docs/EXIT_REPLAY.md). Tests: `t_broad_shadow.py` (bounded, swallows errors, no request, flag off, prune, row cap, size
    ceiling, migration of an older file, 30,000-market flush time bound, no reader, bytes a row), `t_broad_replay.py` (the
    replay on a database the engine's recorder wrote).
  - Review follow-ups: a failed lookup while pruning by age no longer risks emptying the table (the age cut is skipped, the
    row cap still holds); a kickoff learned after a market row exists is written to it (the id cache is cleared only when
    market rows were actually deleted); a resolver label (closes, live_fairs, line_fairs, mkt_fair) replaces a price-implied
    one, and label work only touches still-unlabelled markets in short 1,000-update transactions so the history lock is held
    briefly; rows are stamped with the time the price was seen, not written; the recorder never writes inside another
    transaction (it skips that flush) and always rolls back one it began; errors log the type only; the replay's unlabelled
    share is correct when implied labels are excluded, its data-quality block counts markets without a kickoff, and its
    caveats say entry is not stratified by phase and exits assume a fill at the recorded bid whatever its size. Known and
    accepted: the 45 s flush throttle means the 20 s event cadence is effectively 45 s, and the byte ceiling is a row
    estimate (rows x 60 bytes), not the file size; the row cap (80% of the ceiling, about 17 days at the busy-week estimate)
    can shorten retention.
- **Per-league learning, in shadow (#13; nothing live changes, no decision reads it).** Pete's rule is that everything learns
  per league, not just per sport. Once a day (`league_shadow_run`, called from `knob_pass` after the weekly stepper, due at
  most every 24 hours, rows kept 180 days) the app works out what each league's own numbers would be if the league learned
  for itself and borrowed only what it lacks, and records them beside today's in the history table `league_shadow` (ts,
  league, sport, metric, key, current, shadow, n_own, n_sport, n_all, shares, says).
  - **Borrowing rule** (`lgsh_blend`, deterministic and explainable): start from a neutral value, then walk all leagues ->
    the league's sport -> the league; each level moves the value so far toward its own by `n/(n+k)` of the gap (n = that
    level's results, k = `LGSH["k_cut"]` 30 quotes, `k_calib` 300 games, `k_roi` 30 bets). A level with no data changes
    nothing, so a league with no results is exactly its sport and a sport with none is everyone. `shares` says how much of
    the final number each level accounts for ("league 31%, sport 40%, all 22%, start 7%").
  - **Metrics:** `cutoff` = each league's combo cut-off by size bucket, today's `_cut_level` (a hard switch at 30 quotes)
    against the blended level (never under 85 or over 110; a borrowed all-leagues level never under the 95% start). `calib` =
    each soccer league's fair-price nudge per chance band: `calib_fair` named by sport only (what a caller passing no ticker
    gets) against `calib_fair` with the league named (its own record, its sport's behind it; already weighted n/(n+300)
    today, so the row shows only what naming the league changes). `record` = each league's settled-bet return over the last
    60 days (real combos plus paper/real panel bets, `_tune_items`; mixed-league combos left out) shrunk toward 0 through all
    -> sport -> league: what evidence sizing and the panel's sport order would read. Neither reads any league's record today,
    so `current` is empty; no multiplier or priority is invented.
  - **Report:** `league_shadow_view` (read-only, never raises) is in the Results analytics payload as `league_shadow` (latest
    run, per league: cut-offs, calibration, record, how many rows differ from today; leagues that differ first). No page card
    yet; the data is there for one.
  - **Never touches:** any cut-off, fair price, stake, size, buy, sell, Pause, the caps, rule 8, the knobs or any
    settings/learning file (`combo_cutoffs.json`, `combo_knobs.json`, `combo_smart.json`...). The run writes only
    `league_shadow`. Later steps, each its own PR behind a switch: read the blended cut-off, then the league-named
    calibration at every caller, then sizing and the sport order. Tests: `t_leagueshadow.py` (blend maths and shares;
    cut-off, calibration and record rows against hand-worked numbers and today's real `combo_cutoff`/`calib_fair`; the daily
    gate and 180-day prune; identical decisions before and after a run for `combo_cutoff`, `calib_fair`, `_size` and
    `smart_params`, no settings/learning file written, no decision table touched; an AST check that no decision function
    mentions the shadow).
- **Logging and display only: calibrated profit, exit-route log, sale estimate (#361 part 1, #397, #300, #316).** No buy,
  sell or size decision changes.
  - **#361 part 1 (display).** A combo quote carries `ev_cal` (built in `combo_ev_cal` inside `combo_offer`,
    `watcher/combo_watcher.py`): the expected profit on the chance corrected by Pete's own record (`calib_fair` per leg, over
    the books' fair chance), `stake x (pct x calibrated / shown - 1)`. The Build card and slip show it ("on your record,
    before fees") through `evShow` in `stakeCtl`; with no `ev_cal` (live quotes, longshots, a leg that cannot be corrected)
    they show the books' profit as before. The books' `ev` still decides `rec`, `small` and the "recommended" label, so a
    card can say "recommended" with a negative calibrated profit. The 130% tuning half of #361 is left to #397. Tests:
    `test_evcal_ui.py` (390x844, dark and light), `test_ownstake_ui.py`.
  - **#397 (log only).** The live green-Buy exit-route check in `get_offer` always writes its comeback_shadow line
    (`force_log=True`) and prints "combo quote exit-route check (live green Buy): passed|held back (why)". The verdict is
    unchanged; no tuning. Test: `t_combo_live_fair.py`.
  - **#300 (log only).** A combo auto-sale's log line carries `disc` (today's `kalshi_discount`) and `est` (disc x chance x
    pays x share). `knob_sale_expect` and the brake still read what they did before; not done: feeding `est` or ledger
    proceeds on retries into the brake (that changes selling). Singles already log `ask` and `chance`. Test:
    `t_logdisplay.py`.
  - **#316 items 1-2 (watch-only guards).** A single's break episode is filed under the held market, not the game-winner
    stand-in (`break_ok`/`stop_loss_leg` take `watch=`); a full `BRK_EP` drops its oldest episode instead of clearing every
    open one. Both watch-only (`BRK_LIVE` is False). Test: `t_logdisplay.py`. Skipped: items 3 (smart_tune replay counts), 4
    (stale-device `stop_loss_mode` in `sl_sync`) and 5 (97% retry floor on combo cash-outs), because each changes selling
    behaviour or settings semantics. Known gap (item 1): a single's break episode is opened but not closed or written after
    play resumes (`break_watch_held` only walks combo legs); it ages out at 400 entries.
- **No-both-sides and exposure caps, on paper (#335; measuring only, changes no buy).** Pete's call (2026-11-22): no extra
  confirm tap, a warning at most, never block; and the big losers were the app's own suggestions, not his picks.
  `nfl_combo_planner.py` has one new block ("(#335) no-both-sides and exposure caps, on PAPER only", just above
  `SPORT_SCORE_WORD`) and one call in `record_view` (the Live refresh's recorder): `exposure_paper_pass(view, now)`. It runs
  at most every 2 minutes (`EXPO["every"]`), writes each pass in one transaction (stops at the first failed write), can be
  turned off with `CFG["expo_paper"] = False`, is wrapped so it never raises, and no buy, sell, size, panel, Smart Buy, Pause
  or cap path reads it (`t_exposure.py` greps the engine to prove only `record_view` calls it, and that `get_offer`,
  `accept_offer`, `_size`, `smart_buy_ok`, `exit_policy`, `single_sell_reason` and `build_panel` never mention it).
  - **Recorded** (history file, own small tables). `expo_pass`: each pass, one row per game, league and day with a held bet
    or one the panel would still buy. Per game: how many held bets and dollars, how many panel bets and dollars it would
    still add, whether both sides are held (`both_held`) or the panel would add the other side of a held or panel bet
    (`both_would`), how many bets are stacked, and the share of the bankroll (`CFG["bankroll"]`). Written only when something
    changed (or hourly); kept 14 days, at most 20000 rows. A combo's whole cost counts on each game it touches (as
    `game_exposure` does) and in the league and day totals (the league is `mix` for a cross-league combo, which skips the
    league cap).
  - `expo_pos`: one row per held bet, the first time the Live view shows it: its games and what it backs in each, its cost,
    day (the first game's date), league, and the first paper rule that would have stopped it (`blocked`: `both_sides`,
    `game_cap`, `league_cap` or `day_cap`, else empty). A bet is judged against the bets already taken that are still held (a
    finished bet carries no risk); a blocked bet never uses up room for the next one. Once the bet is no longer held and the
    ledger closed it after we first saw it (with a cost within 10% of ours, else it is left unsettled: another bet shared the
    ticker), `net` = what it really made (`back - cost`, fees counted). `batch` = how many new bets showed up in the same
    pass; `own` = the app's own bet (1) or not (0). Kept 60 days (pruned hourly).
  - "What it backs": kind, team (or against it) and strike. Two bets on one game are the two sides when they back different
    teams, a team and against the same team (same strike for spreads), or an over and an under whose strikes cross (over 50
    with under 40; over 40 with under 50 is a middle and is not). A spread's NO beside the same team to win is not both
    sides. A draw is its own side. Known gap: a hedge bought on purpose looks like both sides (the view does not say why a
    bet was bought). The paper numbers, all in `EXPO` and to be tuned from this record: a game 10% of the bankroll, a
    league's day 30%, a whole day 40%. They are guesses, not rules.
  - **Shown** (nowhere else, no screen, no push): one plain-English line in the log when it changes, at most every 10
    minutes, e.g. "exposure (paper only, nothing is blocked): holding both sides of DALNYG; 2 games with 2+ bets stacked;
    biggest game DALNYG $23 (18% of the bankroll); today $41 (33%). The rules would have stopped 7 of 52 bets, and those made
    -$31 net after settling." `exposure_paper_summary()` gives the same as numbers: bets seen, blocked, and per rule, with
    the net of the blocked bets once settled; also split by rule and by origin (app / not own). A group of fewer than
    `EXPO["min_n"]` (5) bets shows no count and no dollars; dollars wait for `EXPO["dollar_n"]` (20) settled bets, then the
    line gives the settled count, the money staked, the return on it and the same return for all bets as a baseline, and says
    "a small sample" under 50 settled.
  - **Limits:** the first look (an empty table) records the bets already open as `seed` rows: they count toward later bets'
    room but are never judged or counted, because their order is unknown. Bets first seen in the same pass cannot be put in
    order (judged by id), so they are marked as one batch and reported by count only, never in the dollars. The record sees
    only what the Live view shows (open combos and open single bets, including ones Pete bought by hand): it cannot say which
    came from the panel, a standing order or Build. A game's cost is the whole combo cost on each of its games, a
    conservative read. It is a measurement to decide from, not a back-test of a rule.
  - **Design for a later opt-in (not built):** if the numbers say the rules would have saved money, add a setting (off by
    default, Pete's explicit opt-in, as for every new automatic money step) read by ONE function, e.g.
    `expo_check(positions_after_this_buy)`, called from each buy path (panel buy, `get_offer`/`accept_offer`, standing
    orders, killer deals, hedges) before the order and failing toward a plain warning first (warn, never block, no extra
    tap), then, only if he asks, a refusal with a logged reason. It would reuse `_expo_judge` on the live account's open bets
    (not this table), respect Pause and rule 8, and log old versus new here so the effect is measured. Both-sides on purpose
    (the covering idea in #74) would need its own exception and is a separate design. Tests: `t_exposure.py` (stances and
    both-sides, each cap, a blocked bet not using up room, the first look not judged, the panel's would-add, settlement from
    the ledger, small groups hidden, bounded tables, errors swallowed, no decision path reads it).
- **Signal-shadow tables created once (#433).** `_sig_tables()` runs its six `create ... if not exists` statements once per open history
  database (`SIG["ddl"]`), not on every panel pass under the shared history lock; a failed statement is retried next pass. Test: `t_signal_shadow.py` F.
- **`mkt_hold` switch and veto log (#497).** Settings > Money "Check the books' weight on the newest games", ON by default (in DEFAULTS,
  `SHARED_KEYS`, `WATCHER_SYNCED`, the watcher's `SYNCED` and `SET_KEYS`, `settings.js`; `t_newkeys.py` checks all six). Off = the in-sample bar
  alone; it never adds a weight the old rule would not give. `mkt_learn` prints one line (once per group and result) when it holds a weight back
  (group, in-sample weight, why). Test: `t_mkthold.py` section 7.

### Kalshi's pots (cash by exchange shard) and moving money between them (issue #144)
- Kalshi keeps API cash in a separate **pot per exchange shard** (GET /portfolio/balance's `balance_breakdown`; public
  `/exchange/status` names them: 0 Default, 1 Combos, 2 Crypto & Commodities, 3 Tennis, Baseball, Basketball), and an
  API order can only use its market's pot (`shard_of`). Kalshi's own app moves cash for its own orders; API orders don't.
  An `insufficient_balance` refusal says which pot is short (`balance_words`). Settings › Money › Kalshi balance by pot
  lists them.
- **Money moves between pots only on Pete's tap** (a confirm sheet with both pots before/after, then "Tap again"):
  the Buy straight sheet refused for its pot offers "Move $X from <pot> to <pot>" (`pot_shortfall`: shortfall + $0.50,
  rounded up to whole dollars, from the largest other pot), and Settings has "Move money between pots".
  `pot_transfer` (on the Mac via hub op `pot_move`; the web app runs it under the tap lock) refuses while paused,
  re-reads the balance fresh, caps a move at $200, sends `POST /portfolio/intra_exchange_instance_transfer` (amount in
  centicents, a UUID `client_transfer_id` per sheet so a double tap is one move), polls its status ~7 s, and logs every
  move in `combo_pot_moves.json`. Rule 8 applies: an unknown outcome is `check`, never resent, and blocks further moves
  (as does a pending one) until Pete clears it in Settings. The hub's generic Kalshi relay refuses transfer paths.
  **Automatic rebalancing (Kalshi's `target_balance_allocation`) is not used**: it would be new automatic money
  movement and needs Pete's explicit opt-in.

### The daily panel (Build page, top)
- Up to ~10 bets a day (size scales with games: 6–14), across combos, single games, spreads/totals and
  sell-early favorites, chosen together for the **most expected profit in dollars** (fees counted, from the same
  simulation) **while the chance the whole day finishes ahead stays over a floor**: 55%, and within 10 points of the
  best chance those bets could reach (when even the best is under 55%: within 5 points of it, as before). Profit
  audit #142 leak 2 (`choose_panel`, `_ahead_floor`, `PANEL_AHEAD_FLOOR`/`PANEL_AHEAD_GIVE`); Settings › Money ›
  **Pick the panel by expected dollars** (`panel_rank_dollars`, shared, on) switches back to the old rule (the chance
  first, profit breaking ties). The NFL/pay-index priorities are small dollar nudges. Sport-aware: NFL weekly slate (with time-slot combos and checkpoints, small NFL priority on NFL
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
- **Profit-audit quick wins (#142, `t_profit.py`; every check failed on the code before):**
  - **Stale sharp lines (leak 4):** every line carries when it was read (`at`, free lines too). A pre-game line read
    more than `PRE_LINE_AGE` (45 min: it missed the Mac's 40-minute near-game refresh) ago, or at an unknown time, for
    a game starting within `PRE_LINE_NEAR` (4 h) is
    stale (`line_stale`): `merge_books` then prefers a fresh free line for that team, and `panel_collect` drops what is
    still stale (`drop_stale_lines`: src None, Kalshi's own chance; no game-winner single, combo or closing price uses
    it; spreads/totals come from ESPN's own lines, not checked here). The near-game refresh also counts the sharp
    lines' own start times (`soonest`), so leagues without free lines (tennis, UFC, EuroLeague, AHL) get it. The
    Mac's `HubOdds.get` drops the old sharp snapshot when the odds service answers empty and retries after the near
    TTL (never on every call).
  - **Green Buy and buy ideas (leak 3):** `green_bar` = max(your cut-off setting, the league's `combo_cutoff`) decides
    the green Buy for every combo but the panel's own (`get_offer` returns `bar`; the quote line names it);
    `notify_bar` = max(that, 100% of `calib_fair`-corrected fair) gates the Mac's buy-idea and better-price alerts in
    `shadow_pass`. Settings › Money › **Stricter green Buy** (`idea_bar_strict`, shared, on). The panel's 95% start is
    unchanged (#137 stage 2 decides it).
  - **Close learning (leak 6):** `record_closes` also stores Kalshi's mid (`close_mids` table; ask kept in `closes.price`
    for history; no mid when the gap is over 10¢). `adjust_cutoffs` and CLV read `close_prices(..., mid=True)`;
    re-quotes of the same set of games count once (`_by_games`); the rule is symmetric: raise when combos just over
    the bar were worth under 97% of cost, lower when the ones just under were worth over 103% (`CUT_BAND`; bigger
    step at ±15%, `CUT_BIG`).
  - **News guard (leak 5):** `_qualifies` (pool, `_fresh`, swaps) and `_buy_panel_bet` skip a pick priced
    `NEWS_GAP` (6 points) or more under its chance while one of its teams has fresh injury news (`news_gap`, the
    `single_pass` rule; an unreadable report never blocks).
  - **Minor:** `single_fee(p, n)` rounds an order's fee up to the cent (the panel's buy recheck and its simulation use
    it); a swapped-in bet is sized for itself, never above the stake it replaces (`_swap_stake`).
  - **Second batch (`t_profit2.py`; every check failed on the code before):**
    - **Combos under fair (leak 1, Pete 2026-11-20 "Keep 95% but only when smart sell is likely to profit"):** with
      Smart Buy on, a combo whose `pct` (share of fair) is under 100% (`SB_UNDER_FAIR`) is skipped unless
      `smart_buy_ok` on its exit simulation (a likely profitable cash-out or a good hold, ≥ `SB_EV_MIN`), at **any**
      dial level, learning leagues included (`_sb_under_fair` in `smart_buy_gate`: panel, longer plays, swaps), and
      again on Kalshi's real quote in `_buy_panel_bet` before any accept (`_sb_quote_under_fair`; a skip drops the RFQ);
      no simulation or an error = skipped (fail closed). Buy ideas (`smart_buy_ideas_gate`): a combo idea under fair
      shows only once the shadow's check of that very quote (`cand` "idea:idea:<id>") says `new` (smart_buy_ok);
      unchecked = "still checking"; the gate erroring still leaves them out. The shadow log records it as a skip. Skip-only:
      stakes, cut-offs and every cap unchanged; Smart Buy off = off. The panel's 95% cut-off itself is unchanged.
      `_size`'s $2 for a non-positive edge is then only reached by such combos (singles/lines qualify with an edge after fees).
    - **Panel P/L from real fills (leak 8, measurement):** `panel_settle` counts a single's contracts really bought
      (`filled`, the order's fee rounded up; `_panel_contracts`), and for real bets takes the profit from Kalshi's own
      record (`_panel_fill_pl`: the `ledger` row, sales and fees included) when that row is this bet's alone (opening
      cost within max($0.10, 3%; combos 9%) of the bet's, `PANEL_FILL_TOL`) as `pl_real` (`pl_src: "fills"`); a row that
      arrives later is picked up on the next pass. `pl`/`result` keep meaning "held to the end" (the replays, tuners,
      knob stepper and calibration compare against that). `panel_pl(c)` (= `pl_real`, else `pl`) feeds `panel_record`
      and `month_profit`'s skim. Paper bets (the $300 gate) are unchanged.
    - **Standing orders (leak 10):** watch mode counts a fill only when the ask trades a cent through the price
      (`MAKER_THROUGH`); orders are priced from `maker_fair` = min(books' chance, `calib_fair`) (only ever lower);
      `maker_summary`'s profit subtracts the resting fee.
    - **`smart_tune` holdout:** each league's settled bets split in two by a hash of their games (`_tune_half`, the
      game part of the ticker, so a game's spreads land with it); the
      step is picked on one half only and must also gain ≥ `SMART_MIN_GAIN` on the other (and on all); each half
      needs ≥ `SMART_HOLD_N` (10) bets or nothing moves. (`_sl_tune`, the stop-loss switch's tuner, is not changed.)
  - Still open in #142: live-football single ideas (leak 7), Build's "more combo ideas" (leak 9; spreads/totals done
    in #117 B), combo fees in the simulation (Kalshi's RFQ fee not
    verified), `_size`'s $2 minimum rounding up a tiny positive edge (#328, #329).
- Sizing: quarter Kelly on a shrunk edge, $2 minimum, ≤ 5% of the base per bet; base grows ≤ 10%/week, drops
  immediately; half of each month's profit is set aside (reminder until Pete says he moved it). A Kalshi balance
  that can't be read is never guessed (#143): `sizing_base` returns None, the draft is marked `base_guess`, and it
  can't be approved or added; approved bets wait (`hold: "balance"`) until the balance reads again.
- Paper panel runs alongside (the $300 gate). The **combo lab** paper-buys up to 3 combos a day in each band
  (80–85, 85–90, 90–95, 95–100, 100+% of fair) from real quotes, $5 each, separate from the gate.

- **The panel's funnel (#341 A).** `panel_collect` keeps `PANEL_FUNNEL[code]` (games not started / under way, no
  outside line, stale lines, priced sides, singles, combos predicted and at the cut-off, spreads/totals priced and short
  of the bar, ESPN days unread, candidates by kind); `choose_panel` adds the bar's rejections by kind, the pool, why each
  qualifying bet wasn't picked (`left`: overlap, line share, budget, full, ranked out) and the floor trim; `build_panel`
  adds `kick`, `held`, old prices, Smart Buy and odds-credit skips. All in `stats["funnel"]`, with `funnel_words` in
  `["why"]`; logged "panel funnel: ..." on change (≤ every 10 min); `combo_funnel.json` keeps the last (`api_panel` →
  `funnel`, under an hour old). Build's pool line and the empty panel card have "Why so few?" (`funnelOpen`). Display
  and log only.
- **Core 2-5 leg combos (#341 D).** `value_combos(..., per_n=2)` returns the old search first, unchanged, then up to 6
  more of each length 2-5 (`extra: True`, each pick in ≤ 2 of a length's extras). `core_combos` keeps the old ones that
  clear their cut-off and adds, for each length short of `CORE["per_n"]` (2), the next ones clearing **the same**
  `combo_cutoff` (`core: True`). `choose_panel` gives a length the panel has under 2 of a tie-break nudge
  (`CORE["nudge"]`, 0.1% of the budget in expected dollars) only while over the day's floor and adding expected dollars.
  Budget, `_size`, every bar, Smart Buy, caps, Pause, rule 8 untouched. Tests: `t_panelpipe.py`, `test_panelpipe_ui.py`.
- **Fresh price for Skipped / Didn't buy cards (#358).** The whole card (at least 44px) is tappable on the approved panel and
  calls the read-only act `panel_reprice` (`A.panel_reprice`): refused while paused; prices only that card's stored bet
  (rule 7); never a market with an unknown order outcome (rule 8; the card says "Check Kalshi"). A combo gets a fresh RFQ
  via `_with_ctx`/`_panel_combo`/`get_offer`, DELETEd at once and never accepted; a single reads Kalshi's book. It uses the
  bar the panel buys by (combo: `combo_cutoff`, then the under-fair rule; single: ask + fee + 2%, or at fair or better for an
  early bet, then the news gap; a bet under way also needs the in-play exit test). The panel is never changed; one price per
  card per 8 s. The card shows "Would buy at this price" / "Still wouldn't buy" / "No fair price right now", the reason and
  "a look only, nothing was bought". Each card says why in plain words (`pNote` maps the Mac's notes). The quote names its
  real bar ("104% of fair on the live chance · at or above your 100% bar"; `green_bar`, sent as `cut`), and says why when the
  bar isn't the reason (`qWhy`). **Never "recommended" without an edge:** `combo_offer` sets `small` ($2) whenever the quote
  isn't green or its expected profit isn't positive ("smallest bet" / "no edge").
  - **Wording batch 2: before fees, a plainer "wouldn't buy" (#290, #304, #307; text and display only, no buy, sell, sizing or
    gate logic).** A combo's "+X% expected" now says "before fees" (the combo entry fee is not counted in it), as do the combo
    screen's "Likely about X% of fair" guess, its "Kalshi will likely pay" line and the stake card's "Expected profit". Once
    "Tap for a fresh price" has answered on a Didn't-buy card (`S.prep[id].pct`), the card's own numbers are dimmed (opacity .75, `.pitem .pn.stl`) and say
    "earlier guess: pays about N% of fair", so one card no longer shows 106% and 99% side by side; on a combo screen with a
    fresh Kalshi quote the older "Likely" / "will likely pay" guess is hidden (`pStale` in `build.js`). A fresh-price reply for a skipped in-play bet is capitalised and ends in one period (`_cap1` in `panel_reprice`). The Overlap "Add anyway" slide (`flipSnap`/`flipPlay`) compares positions plus scroll, so a scroll during the refresh does not move the cards (#446). The **"Still wouldn't
    buy"** reason (`_sb_under_words`, `SB_UNDER_FAIR_WHY`) reads "Kalshi's price is about 1% under what we think it's worth, so
    on average you'd lose about 2¢ per $2 if you held it to the end. Selling early could still make a profit, but not often
    enough to make up for that, so it is left out." The doubled "99% of fair, but Kalshi pays 99%" is gone: the gap is rounded
    once (`_gap_words`) and a share just under 100% reads "a little under"; Smart sell is no longer named as the decider and
    both exits (sell early, hold) stay in the sentence. Skipped: #313 (shows live money settings), #283 and #261 (card
    restructuring, not wording), the rest of #290 (card layout) and #307 items 3 and 4 (the banner already says it keeps
    stricter numbers; the haptics list is not a wording change). Tests: `t_profit2.py` (A8, A8b, A8c), `t_sbgate.py`.
  - **Live combos are priced on the live chance (the 131% screenshot).** `get_offer` used the board's pre-game fair while a
    pick's game was under way, which fed the %, `stake_for`, `store_quote` (the predictor) and the take-profit price. Now each
    started pick goes through `combo_live_fair` (`live_side_fair` on a fresh score and the panel's live guards: two-sided book
    within `LIVE_SPREAD`, not nearly decided, Kalshi's mid within `LIVE_DISAGREE`). No live chance = no fair price: no %,
    nothing stored, never green, $2 sizing. **Loosening (Pete: "I'm okay with accepting recommendations on live games as long
    as they are good recommendations"):** a Build or idea combo under way may be green when every live guard passes, it
    clears `green_bar` on the live chance and passes `inplay_exit_ok` (before #358 never green, #255/#341). The panel's own
    combos are re-priced by `live_recheck` before a buy, as before.
  - **Big-edge audit.** A quote over `COMBO_SUSPECT` (130% of fair, a guess: the dev Mac has no quote history) is held back
    everywhere `get_offer` prices (never green, never a panel buy, logged; stricter only). Known, not changed: `ev` uses the
    uncalibrated fair while `notify_bar` uses `calib_fair` (display only, #361); the Kalshi-mid fallback fair is circular
    (labelled "Kalshi's price"); stale pre-game lines are already dropped by `drop_stale_lines`.
  - Tests: `t_combo_live_fair.py`, `t_panel_reprice.py` (read only: pause, rules 7 and 8, RFQ dropped, panel and CTX
    unchanged), `test_reprice_ui.py` (390px). `t_inplay_exit.py`'s offer case stubs the book and expects "no fair price".

### Selling: smart sell everywhere
- Smart sell runs on **every bet**: combos, singles, spreads, totals — the app's and ones Pete places on Kalshi
  himself — each with a per-bet switch on Live: "🤖 Smart sell" / "✋ I'll sell it" (`combo_selfsell.json`).
  It only acts while Auto cash-out is on; the daily cap applies (Settings › Selling "Auto cash-outs a day, at most", `auto_cap`, default 5, 1-10 or **Unlimited** (Pete's opt-in, #217): the slider's top stop, stored as `AUTO_CAP_UNLIMITED` = 1000 so an older process reads it as a cap it never reaches; `auto_cap_limit()` = None for anything over `AUTO_CAP_MAX` (10), an unreadable value = 5; `auto_cap_reached()` is the one check, "check" sales still count); singles sell into the order book (IOC at the bid,
  reduce-only) and skip thin markets (bid/ask gap > 6¢), bets with a resting sell, and games already over.
- **Leftovers and repeated failures (#334):** smart sell for singles offers only whole contracts, never under
  `SELL_MIN_CONTRACTS` (1, Kalshi's minimum): a 0.92 leftover is skipped and logged once ("under one contract"), never
  sent. After `SELL_FAIL_MAX` (3) failed identical sales in a row (same market, side and size; a definite "failed", not
  "check") it waits 10 min, then an hour after each further failure (`SELL_FAIL_WAITS`, `SELL_FAILS`,
  `sell_backoff_left`/`sell_backoff_note`; per process, a restart starts over), logged once per wait. A sale that goes
  through, a "check" or a different size resets it. It only ever tries less: Pause, the cap, guards, rule 8 unchanged.
  Test: `t_ledgersales.py` (C).
- Rule: sell when the offer beats the risk-adjusted value of holding,
  `max(q·P − λ·P·√(q(1−q)), floor × cost)`, q ≥ 0.5 (`EXIT_Q_MIN`; never lowered by self-tuning since #306); λ from the sport's swing and time left (×1.3 at a slate
  checkpoint); lock-in after a big run-up drops 20%; take-profit % optional (default off — the old 75% default was
  migrated off). There is **no 80% floor** (removed at Pete's request).
- **Self-tuning, per league** (weekly, `smart_tune`): replays settled bets on their recorded game prices with
  nearby settings and moves one small step toward what clearly did better (≥ 2% of stake, 30+ bets): profit floor
  (starts 1.5×, 0.1 steps, 1.2–2.0), risk weight, and a learned loss cut (off until a league's record shows
  selling a sliding bet beats holding). On a tie, the smallest change wins. Results › Selling shows each league's
  settings and why they last changed. With `knobs_live` on (#228 PR3, below), `smart_tune` no longer moves the floor,
  risk weight or loss cut (`knob_tune` does, on the stricter evidence bar), and borrowed values are only stricter (#259).
- Settings: `sell_own` (old "include bets I place myself") is removed; the per-bet switch replaced it. The old
  `stop_loss` on/off override is now **Settings › Cash out & hedging › Selling at a loss**, now two choices:
  **Let it tune itself** (default) and **Allow (guarded)** (`stop_loss_mode`; details in "Self-tuning PR5-PR7" below).
  The third choice, **Never sell at a loss**, was removed (Pete, #479): a saved 'never' reads as 'Let it tune itself'
  on upgrade. Older passages below that mention it are superseded.
- **Stop-loss guards (issue #27):** with Selling at a loss on Allow (or tuned on for the league), auto cash-out may sell a combo below cost only when
  `stop_loss_check` passes: a pick on a **fresh** score feed (`leg_score`, never Kalshi's display-only data; scores
  older than the league's learned tolerance (start 150 s, band 90-300 s, `learned_guards`) or missing = never, and any other pick whose game has started must have a fresh score too), game
  in play and **not at halftime/a break/end of a period** (`at_break`; `break_ok` lifts this for a loss sale only, on a league's own learned record, with `learned_guards` on; off = always blocked), **game played ≥ the league's `prog`** (start
  50%, bounds 35–90%), pick under 50% and **≥ `drop` points below its pregame chance** (start 20 points, bounds
  10–45; `pre_of` on each held combo), all held on **3+ checks in a row spanning ≥ 3 min** (none > 5 min apart).
  `prog`/`drop` are learned weekly in `smart_tune` (`_sl_tune`/`_sl_replay` on recorded ticks + score lines, 50+
  combos, ≥ 2% gain, 0.05 steps, smallest change on ties), stored as `sl_*` in `combo_smart.json`, shown in
  Results › Selling. `stoploss_params` borrows league → sport → all, but borrowed values can only be **stricter**
  than the start; only a league's own record can loosen it. A stop-loss sale is logged with `stop_loss: true` and
  notifies "Stop-loss (your switch)".
- **Auto-hedge guards (issue #27, Pete approved):** auto-hedge (with Auto cash-out on, replaces an already-chosen
  sale when the combo has one pick left and the hedge locks in ≥ 95% of the cash-out, ≤ `hedge_cap`, default $100;
  Pete's #228 opt-in lets the system raise it to at most $150 on evidence once the stepper ships, Hard rule 2)
  now buys only when `hedge_guard` passes: the last game **in play on a fresh score** (`fresh_live_score`, shared with
  the loss guards; missing/stale = no hedge), **not at a break** (`at_break`), the hedge **locks in at least the
  combo's cost** (`locked = contracts − hedge cost ≥ h["cost"]`), all held on **3+ checks over ≥ 3 min** (`_sl_confirm`
  under `hedge:<ticker>`, with the hedge's own counts `hedge_confirm_params` since #228 PR6). Then `hedge_fresh` re-reads the hedge side's order book (`book_depth(max_age=0)`; no ask or
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
- **Smart Buy, stage 1: the foundation (issue #137; watches only, changes no buy, sale or pick).**
  - `exit_policy(state, params)` is smart sell's decision in one pure function (risk-adjusted hold value, profit
    floor, take profit, lock-in, the learned loss cut with `cut_ok`); `take_profit_reason` and `single_sell_reason`
    now only gather their inputs and call it (`EXIT_POLICY_VERSION`). `t_exitpolicy` runs the old functions verbatim
    (`fixtures/exit_policy_old.py.txt`) beside the new ones on 8,000 states: identical answers and peak tracking.
    **The weekly tuner's replay now uses exit_policy too (#228 PR0):** `_replay` (used by `smart_tune`, `sim_exit`,
    the combo lab's and the cover test's replays, and What's working's smart-sell replay) no longer has its own copy of
    the rule. Each recorded price becomes exit_policy's state (`kind`, `value` = the replay's estimate, `real` 0, `peak`,
    `pays`, `cost`, `q`, `live` True) and settings (`smart` on, `lam` = the replay's risk weight, `floor`, `loss`,
    `cut_ok` = a guard time from `_cut_guard_ts`, `trail`, take profit off, no checkpoint); the bet is sold at the
    estimate when exit_policy says sell **and** the estimate reaches its `threshold`. Live selling is untouched. Every
    difference from the old copy (now following live): **D1** lock in arms at a fixed 1.5x cost (old: max(60% of payout,
    floor x stake)); **D2** a single's loss cut accepts any positive value, a combo's at ≥ 2% of cost (old: > 2% of stake);
    **D3** a combo whose estimate is within 5% under the floor answers "smart" and rides (lock in not looked at on that
    price). `t_replaypolicy.py` proves the list complete: the old replay verbatim (`fixtures/replay_old.py.txt`) with
    exactly D1-D3 applied matches the new one on 12,000 fuzzed paths (63 differ: D1 48, D2 1, D3 17). The tuner's output
    was unchanged on the test fixtures and on a read-only copy of Pete's history (26 settled bets). Still different
    from live (later #228 PRs, ROADMAP): take profit isn't replayed, no checkpoint x1.3, the estimate stands in for
    Kalshi's real offer (live accepts down to `CASH_SLIP` 97% of it), and the replay keeps `0.35 x swing` (no
    `swing_lambda` or Let it ride).
  - `simulate_exit(spec)` (spec from `exit_spec(candidate)`; `predict_exit_chance(c)`): Monte Carlo (120 paths,
    seeded from the candidate id) of each pick's hidden lead (pre-game drift `SB_PRE_VOL`, in play scoring jumps per
    sport `SB_SCORE_UNIT`, fair = Φ(lead/√time left) as the live model), Kalshi's mid closing the gap to fair
    (`SB_PRE_CLOSE`), the sellable bid (half the gap, wider in play, cents, the exit fee; a gap over 6¢ or too little
    depth = can't sell), `exit_policy` at every step with the league's settings (`exit_settings`). Returns at a $5
    stake: `p_exit` (cash out ≥ +10%), `p_sell`, `exit_profit`, `hold_profit`, blended `ev` (optional stopping:
    hold value from the sale on = fair × payout), `exit_mins`, `route` (sell / hold / none). ~5 ms a single, ~12 ms a
    2-pick combo. `smart_buy_ok` is the stage-2 gate as it would stand (logged only).
  - **Price recorder** (`price_path` table: ts, ticker, bid, ask, mid, depth, score): `price_seen_markets` (from
    `fetch_series` and the held-singles refresh in `open_singles`) and `price_seen_book` (`book_depth`) note prices the
    engine already read: **no new Kalshi request**. `price_watch` marks markets to record (panel candidates, Buy ideas,
    held singles); `price_flush` writes every 60 s near a game (3 h before to 6 h after), 5 min otherwise, only on a
    change unless 15 min passed, all of a flush's rows in one transaction (`_price_insert`: one sync, the history lock held
    once; inside a `panel_tx` they join it); `price_prune` keeps 30 days and ≤ 250k rows (exit_shadow: 60 days, 200k; both
    indexed on ts). A failed held-markets refresh's fallback copy is never recorded as fresh; held singles are watched
    with their kickoff (`price_watch_held`); `depth` is the size at the best ask (book_info's `ask_size`), not the bid.
    Buy-idea combos share the combo's chance out in proportion to each pick's ask; asks over 15 min old = skipped.
  - **exit_shadow** (`smart_buy_shadow`, called at the end of `panel_collect`; `smart_buy_shadow_ideas` from the
    suggestions table every 10 min): one row per candidate per 30 min with edge, win chance, cash-out chance, dollars,
    route, `old` (today's rules took it) and `new` (`smart_buy_ok`), ≤ 0.15 s of simulation a pass (it can run under `odds.lock`; ideas ≤ 0.1 s), never raises,
    never changes a candidate. `exit_replay`/`exit_calibration` replay `exit_policy` on recorded paths: predicted vs
    actual cash-out rate per league and type (singles/spreads/totals; combos in stage 2), one bet counted once (its
    first check), with the same simplified loss-cut guard as the simulator. Counts in the preview are distinct bets.
  - **Early-exit value test, phase 1 (exit-replay; measurement only, no buy, sell, sizing or gate changes, nothing new is
    automatic).** `tools/exit_replay.py` (read-only, `mode=ro`, no network; how to run it: `docs/EXIT_REPLAY.md`) replays
    fixed exit rules (+3c/+5c/+10c, fair target, T-1h, T-15m, hold) on the paper book's singles and real ledger buys using
    `price_path`, with the engine's fee rate on entry and exit and the bid-ask gap, a game-level bootstrap and a 70/30 time
    split, and prints only aggregates (cells under 20 hidden, no tickers or dates). It also reports measured replacements for
    SB_PRE_CLOSE, SB_PRE_VOL, SB_SPREAD and SB_LIVE_WIDEN, the real combo buyback discount from `offers`, and (`--combo-fee`)
    the ratio of recorded combo entry fees to the standard taker formula. `signal_shadow` (called once in the panel pass after
    `mkt_fair_shadow`) records `sig_sharp`, `sig_related` and `sig_state` from data already in memory: write-only, errors
    swallowed, flag `sig_shadow` (a real `CFG` key, ON by default for recording, so a saved false is kept), 21-day / 300k row
    bound. Combo RFQ sampling: nothing new (held combos are already in `offers`, candidate quotes in `quotes`; more would need
    extra quote calls). Tests: `t_exit_replay.py`, `t_signal_shadow.py`.
  - **Momentum shadow (record only).** `mom_record` writes `mom_shadow` / `mom_after` / `mom_peak` from the exit evaluation (hooked at the end of `take_profit_reason` and the live `single_sell_reason`, each in its own try/except); setting `mom_shadow` (default ON, false = off). It sells and buys nothing, reads nothing back into a decision, and Pause, rule 8 and no-live-data are untouched. DB writes go through a background queue (`mom_flush()` in tests), never on the sell path. Combo cards show smart sell's real bar and whether it can really sell right now (`smart_trigger`, `auto_sell_blockers`); the old let-it-ride number is the "Let-it-ride line". Details: the 'Momentum shadow recorder' notes under Selling; test `t_mom_shadow.py`.
  - Settings › Money › **Smart Buy (preview)** (`smart_buy`, shared, off; `smart_buy_on()` reads the shared file):
    on = Results › What's working shows a folded "🧠 Smart Buy (preview)" card (`sbCard`, `analytics()["smart_buy"]` =
    `smart_buy_summary()`, built only while the switch is on; the route re-reads the switch and builds it when it was
    switched on since the 10-minute cache). Off or on, panel candidates, picks and sells are identical
    (`t_smartbuy`). Next stages: `ROADMAP.md`.
- **Smart Buy, stage 2: the gate (issue #137; skip-only, learning, on by default).**
  - Settings › Money › **Smart Buy** (`smart_buy_gate`, shared, **on** by default; text: "Skips bets that are unlikely
    to be profitable. Each league starts working once it has enough results, and keeps learning from every result.").
    A new key on purpose: the preview's `smart_buy` (off by default) was never a choice about the gate, and an older
    process still running after the update can't write the new one. Off = the gate is fully off (nothing simulated,
    nothing skipped); recording and learning keep running either way. The Results card shows while it's on.
  - **Skip-only, by construction.** `smart_buy_filter(items)` returns the same dicts, same order, same stakes, minus
    the skipped ones. It runs in `build_panel` **after** `choose_panel` (and on the longer plays after their cut), so
    nothing is picked in a skipped bet's place; the card's stats are recomputed on what's left. `_replacement` returns
    no swap (a skip) when the swap it found fails the gate, never the next one down. Live Buy ideas are gated after the
    `IDEA_KEEP` cut (`smart_buy_ideas_gate`, from the shadow's last `ev` for that market; an idea not yet simulated
    stays). The extras pass keeps a skipped bet's stake and games out of its budget (`sb_skipped` on the draft), so a
    skip never makes room for something else. A draft Smart Buy emptied is still saved, so an older draft can't be
    approved. Longer plays are judged against the panel's games as chosen (a skip makes no room there either); sims are
    memoised 5 min per bet and price (`_sb_sim`; `panel_pass` builds several panels under `odds.lock`). Never touches selling, sizing, caps, cut-offs, Pause, claim-before-buy or rule 8. Gate errors pass the bet
    through today's rules. Property test: 400 random panels, output always a subset with identical stakes (`t_sbgate`).
  - **The dial** (`sb_dial`, `combo_smartbuy.json`, gitignored): strictness k skips a bet whose `simulate_exit` `ev`
    (dollars on $5 under smart sell's exit policy) is under `SB_DIAL_BARS[k]` (0 = no bar; then −$0.20, −$0.10, $0,
    +$0.10 … +$0.60). A league with fewer than `SB_LEARN_N` (30) checked bets with known results is "Learning (12 of
    30)" at 0 (exactly as before; nothing simulated) or borrows its sport's, then everyone's dial (borrowed levels never
    under the start, 0). At 30 of its own it starts from what it borrowed; from then on only its own record moves it.
    Since #297 a league still learning may be stricter early, judged on blocks of 10 (`_sb_early`, stricter only; see
    "Smart Buy, faster evidence").
  - **Learning** (`smart_buy_learn`, from the watcher's history loop; dial re-looked at most hourly): `sb_resolve`
    fills each checked bet's result from Kalshi's settled markets (`res`, `outcome` = dollars on $5 held to the end,
    from the `pays` logged with the check); `_sb_results` takes one row per bet (its last check before the game);
    `_sb_step` moves a group (everyone, each sport, each league) one step, judged on the band (the bets the step
    changes): up when they lost money, down when the bets the current level skips made money, each only when the band
    has ≥ `SB_DIAL_BAND` (10) bets averaging ≥ `SB_DIAL_MEAN` ($0.25 on $5) the right way and ≥ `SB_DIAL_T` (2)
    standard errors from zero, and ≥ `SB_DIAL_NEW` (20) results from games after the last step; both ways or neither =
    stay. Under `SB_DIAL_SOFT_N` (100) results a dial stops at 3 (bar $0: only bets expected to lose are skipped).
  - **Counterfactuals:** `smart_buy_shadow` keeps logging every candidate unconditionally, now with `pays`, the
    gate's verdict then (`skip`, the plain reason) and the level (`strict`), so skipped bets are scored too.
  - **Visible:** Results › What's working › 🧠 Smart Buy shows a line per league (`smart_buy_gate_summary`):
    "Learning (12 of 30)" or "Active · strictness N · skipped X · shadow saved $Y" (from the verdicts really logged),
    the last change and why, and a **"Bigger stakes: not yet"** progress line toward the graduation bar (50+ settled,
    ahead, ≥ 55% of days up, CLV on singles/spreads ≥ 0, skips beating plain). Display only: nothing acts on it yet.
    The panel (every view) and the Buy ideas show a calm "Smart Buy skipped N · Why?" (`sbSkipLine`/`sbSkipOpen`): a sheet of
    short plain reasons.
- **Smart Buy, faster evidence: every market on paper, a paper book, a backfill, borrowing sooner (issue #137).**
  Pete (2026-11-21, "How do we accelerate Smart Buy" → "do 1, 3, 2, 4"): reach the graduation evidence sooner by
  scoring more bets on paper. The calendar can't be rushed (games must finish; ≥ 55% of days up), so only what is scored
  widens. **All paper:** no buy, sale, panel pick, stake, cap or Pause path reads anything new here. The one real effect
  is on purpose and only ever skips more: the dial's stricter-only **early level** (4, below).
  - **1. Every priced market, scored (`source='universe'`).** `panel_collect` hands its own games (not started, or live
    priced) to `sb_universe_stash` (new small dicts; the candidates are never touched), and `line_candidates` stashes
    every spread/total strike it priced with an edge (`SB_UNI["lines"]`; its answer is unchanged, and with
    `everything=True` it still doesn't read the CLV block). Kept: every game-winner side (the panel's guards: fair ≥ 20%,
    price < 97¢, a sportsbook or live chance, never a started game's pre-game chance) and every pre-game strike whose
    fair beats Kalshi's ask plus the fee. `grade` = `cand` when it also passes the panel's own rule (single_candidates'
    2.5¢ and 4%; the spread/total bar, its 6% and the CLV block), else `wide`. `smart_buy_universe` scores them with the
    same `simulate_exit` and verdict columns (`skip`, `strict`, `pays`; `old` = 1 for `cand`), never-scored first then
    nearest games, once per market every 30 min within 3 h of its game or in play (`SB_UNI_NEAR`), else every 3 h
    (`SB_UNI_FAR`); a market the panel or a Buy idea scored within that time is skipped (`SB_CACHE["tk"]`, capped);
    a pool older than 15 min (live: `LIVE_POOL_AGE`) or a game that started since is not scored. ≤ `SB_BUDGET` (0.15 s)
    of simulation a pass. The watcher's `smart_buy_universe(odds)` runs it in the shadow engine (H), **outside
    `odds.lock`**, after each full round and each quick round; rows go in short transactions (`_sb_insert`, 500 at a
    time, guarded like `_price_insert`). Scoring makes no request (prices in hand); universe markets are **not** added
    to the price recorder, so `price_path` growth is unchanged. Their results are filled by `sb_resolve`'s public
    Kalshi results read like every checked bet, **after** the gate's own bets (panel/idea sets first, universe in a
    second batch). New column `exit_shadow.grade`.
    **Growth:** ~400 markets a day × ~10 checks before compaction; `_sb_compact` (in `price_prune`) keeps only each
    universe market's first check and last check before its game per grade once a day has passed since the game (or,
    with no start time, since the check); universe rows ≤ `SB_UNI_MAX_ROWS` (80,000, oldest first), and when the table's
    own 200,000-row cap bites, universe rows go first: the gate's own rows always keep 120,000. ~1,000 universe rows a
    day after compaction × 60 days = 60k. CPU ~20 s a day.
  - **What learns from what (`_sb_results`).** One row per bet (keyed by its tickers), its last check before the game.
    `wide=False`, the **dial's evidence** (two-way steps, the 30-result count, `own`, the knob stepper) is exactly the
    gate's own checks, panel candidates and Buy ideas, as before this change (filtered in SQL). `uni=True` adds universe
    `cand` markets, at most one per game and none on a game a panel bet or Buy idea covers (a game's strikes move
    together), and feeds **only** the stricter-only early looks (4). Never in the dial: universe `wide` rows (a different
    population: the biggest edges are the ones most often a pricing mistake, so mixing small-edge bets into a band would
    make it look better than the candidates the gate judges, i.e. looser) and the backfill (smart sell's settings today
    were tuned on those same bets: a look-ahead). `wide=True` (every scored bet) feeds the paper book and the card; each
    bet carries `gate_skip` (what the gate itself said, from its own last check) and `first_price`. The card's
    "skipped/saved", "What it checked this week" and "Predicted vs what happened" still count panel candidates and Buy
    ideas only; `smart_buy_ideas_gate` reads `source='idea'` only.
  - **2. The paper book (`sb_paper` table, `sb_paper_build`, every 6 h, H, outside the lock).** For every scored bet: its
    role (`stake` = panel-grade and kept by the gate; `skip` = the gate turned it down, scored at $5, never staked;
    `extra` = below the panel's rule but Smart Buy's own pick, `smart_buy_ok`; else `watch`), the stake graduated sizing
    would give it (`_size`: quarter Kelly on the 30%-shrunk edge, $2 minimum, ≤ 5% of the base; none when there is no
    Kelly edge at the fair chance; each day best expected dollars first, at most 2 a game, until the day's panel budget is
    used, stakes and extras each with their own budget; less than $2 of room = not bought) and what that stake made if
    held. CLV for singles/spreads/totals from the first panel-grade check's price (when a graduated buy would have
    bought). The base is the panel's saved one (`combo_sizing.json`), else the bankroll setting: never a Kalshi read.
    Its own table: never `panel` (the $300 gate), `ledger` or `analytics()`'s gate numbers. Simpler than the real panel
    on purpose (no ahead floor, no 30% share for spreads/totals, no fill cap), so it is a progress line, not a gate.
    `sb_paper_leagues` (cached 2 min) feeds the Results card's **"Bigger stakes, on paper: not yet"** line per league:
    the bar counts ONLY live-scored (never backfill), panel-grade, staked, settled bets, one per game a day (settled,
    dollars ahead, share of days up, CLV, whether the skips helped); extras and history are kept apart (`extra_n`,
    `hist_n`) and never count. Display only: nothing acts on it; Hard rule 2's graduation is still not built.
    The card says "Scored on paper: N bets, M settled" with the split ("133 panel picks · 63 other markets the Mac priced
    · 191 past bets"), a learning league notes "only bets good enough for the panel count", and an empty card with paper
    bets says so instead of "Nothing checked yet".
  - **3. Backfill (`smart_buy_backfill`, `source='backfill'`, daily, ≤ 3 s of simulation a run, resumes at the next
    pass; H, outside the lock).** Two honest sources: the panel items in history (real and paper panels; the fair chance
    and price they were chosen at, the price really paid, a known result from the item or, for a YES single, the
    ledger; checked before the game) and `line_fairs` (every spread/total strike the engine priced, the fair it used,
    Kalshi's ask and the settled result: its last check before the game, with a positive edge, graded by today's
    spread/total bar; the CLV block isn't replayed). Rows are dated at that check, carry the result and no gate verdict
    (`skip` null, `strict` 0). A bet with any exit_shadow row already is skipped: re-running adds nothing, a bet scored
    live is never counted again; one odd item is skipped, never the run. Kept out of the dial and the graduation bar.
    Not done, no honest inputs: bets placed on Kalshi directly and game-winner checks outside the panel (no fair chance
    or start time with a result), and combos' in-play paths.
    On a read-only copy of Pete's history (2026-11-21): 191 bets (6 panel bets, 185 strikes): NCAAF 132, NCAAMB 49,
    NHL 8, NBA 2.
  - **4. Borrowing sooner, stricter only (`SB_BORROW_N` = 10, registry `sb_borrow_n`).** A group (everyone, a sport, a
    league) under 30 results of its own gets one look per new block of 10 results (its own plus universe `cand`, one per
    game; `early_blk`): `_sb_step` with the same evidence bars, and only a step **up** is kept (`early`, ≤ the soft top 3;
    never down). A league short of 30 uses the strictest of today's borrowed level and the early levels of itself, its
    sport and everyone (`_sb_dial_of`, `_sb_early`; `early: true` on the dial; the card says "already a bit stricter,
    from all leagues' first results"). A lender with 30+ lends only its own level; a group's early level is cleared at
    30 or under 10. At its own 30 a league starts from the larger of the level it borrowed and its own early level; its
    own record then moves it both ways, as before. Universe markets never count toward the 30 or a step down.
  - Tests: `t_sbaccel.py` (the stash and grades, line_candidates unchanged, budget and stagger, cadence, skips, never
    raises, `build_panel`/`smart_buy_filter` byte-identical with the universe on vs off over 60 random panels, relearning
    with universe rows changes no count, level or `own` and only adds an early level, ideas gate untouched, only Smart
    Buy code reads exit_shadow, outside odds.lock, the dial's evidence, compaction (mixed grades and sources) and caps,
    backfill idempotence and no double count, the paper book's roles/sizing/budgets/own table and the bar's evidence,
    borrow-sooner stricter only, the registry); `test_analytics.py` (the card's wording, the empty state, the early note).
- **The knob registry, read-only (issue #228 PR1; no behaviour change).** First step of the self-tuning limits Pete
  opted in to (Hard rule 2). **`KNOBS`** (engine, after `smart_summary`) lists every number smart sell, the loss guards,
  auto-hedge and Smart Buy decide with: `name`, `group` (profit / loss / hedge / sell / buy / evidence / invariant), `cls`
  (`tunable` = a guess that may move on evidence later; `setting` = Pete's setting he let the system raise: `auto_cap`
  (no ceiling), `hedge_cap` (25-150); `evidence` = the bar a change must clear, never moved by data; `invariant` =
  safety/data integrity, with `why`), `label`/`what`, `owner` (live function), `src` (the constant or setting the live
  code reads, `"NAME"`/`"NAME.key"`), `start`, `min`/`max` (a hedge may never lock in under 1x cost), `step`,
  `step_kind` (`add`/`mult`: risk weight x0.85/x1.15), `on_value` (loss cut's first value 0.15), `shared_with` (other
  decisions it drives: confirmation counts also confirm hedges, `SB_EV_MIN` also sets Build's spreads/totals list,
  `LIVE_SPREAD` also live buys, so it must be split before it can move; the old `CASH_SLIP` is split since #228 PR4:
  `cash_slip` is an invariant for your own Cash out retries, `auto_slip` the tunable smart-sell slip),
  `unit`, `stricter` (the direction in which the app does less on its own), `borrow` (`own`/`chain`/`chain-stricter`/
  `none`), `learned` (the function that already moves it) and `metric`/`judge`. `KNOB_BY`, `KNOB_GROUPS`,
  `KNOB_EVIDENCE` (PR2's bar above) and `KNOB_BRAKE` are written down; **no live code reads any of them** (only
  `analytics` calls `knob_view`). Numbers that were inline are now module constants with the same values so the
  registry can name them: `EXIT_Q_MIN`, `EXIT_EST_SMART`, `EXIT_EST_TP`, `CUT_ACCEPT`, `TRAIL_ARM_COST`, `TRAIL_FLOOR`
  (exit_policy), `SB_ROUTE_EXIT` (simulate_exit), `SWING_BASE`, `CHECKPOINT_LAM`, `SL_UNDER`, `HEDGE_LOCK_COST`/
  `HEDGE_LOCK_SHARE`/`HEDGE_LOCK_EXTRA`, `SINGLES_SELL_AGE`, `DISC_PRE`/`DISC_LIVE`, `CUSHION_PER_PICK`/`CUSHION_MAX`;
  `t_exitpolicy`, `t_replaypolicy`, `t_hedge`, `t_stoploss`, `t_cutloss` pass unchanged. **Invariants listed:** Pause,
  the Pi never trades, Pete's switches (Auto cash-out, Smart sell, Let it ride, auto-hedge, the stop-loss override,
  "I'll sell it"), rule 8, `ACCEPT_WAIT` 15 s, `CASH_RETRIES` 3 (`AUTO_CASH_RETRIES` 9 for auto cash-out, Pete 2026-11-23), `OFFER_LIFE` 150 s, caps fail closed (120 s), fresh
  score (150 s start; the loss-sale tolerance is learned, 90-300 s, `learned_guards`), in play, live price age (180 s), live-buy score age (120 s), singles' price age (180 s), a real fresh
  offer before any sale or hedge, secrets. **`knob_view()`** (`analytics()["knobs"]`, cached with it) gives every knob's
  start/bounds in plain words (`knob_say`) and, for the six already learned per league (floor, risk weight, loss cut,
  the loss guards' timing and fall, Smart Buy's dial), the value per league and whose record set it, by the same walk
  as `smart_params`/`stoploss_params`/`sb_dial` (a damaged league entry hides only that league; Mix listed like a
  league; never raises, an error = `{}`). **Results › What's working › Selling:** a folded card "🎛️ The numbers selling
  runs on" (`knobCard`, `watcher/spa/knobs.js`): groups, value/start/range/source, league chips, the bar a change must
  clear, "Never moves by itself" with reasons; only the fold and chips are controls. Tests: `t_knobs.py` (completeness,
  bounds, every `src` equals its start, no inline numbers left, nothing but analytics reads it, per-league values equal
  the live resolvers, never raises), `test_knobs_ui.py`.
- **Self-tuning: the stepper, holdout and brake, in shadow (issue #228, PR2).**
  Pete (2026-11-21): the guessed sell, hedge and loss-cut limits self-adjust per league on evidence; invariants never.
  PR2 builds the machinery and runs it **in shadow only**: it writes down what it would change; **no live decision reads
  it**. `smart_params`, `stoploss_params`, `sb_dial`, `exit_policy`, `hedge_guard`, `auto_cap` and the live tuners
  (`smart_tune`, `_sl_tune`, `smart_buy_learn`) read their own constants and files exactly as before (`KNOB_MODE =
  "shadow"`).
  - **Resolver** `knob(name, league)`: the league's own recorded value, else its sport's, else everyone's; a borrowed
    value only **stricter** than the start (`knob_stricter`: towards the registry's `stricter`; `borrow: own` knobs such
    as the loss cut are never borrowed; this is #259's rule, enforced here and not yet in the live `smart_params`); the
    start while the league is braked or nothing is recorded. Invariants and evidence knobs give their live value.
    `knob_cap(name)` (#260) keeps Pete's own `hedge_cap`/`auto_cap` apart from any system raise: the larger of Pete's and
    the raise (the raise never over the registry ceiling: $150 hedge, none for auto_cap), Pete's own while any league is
    braked; Pete's own value is never lowered or clamped, even above the ceiling; an unreadable hedge cap is the default
    $100, never "no limit". Nothing raises a cap in PR2.
  - **State** `combo_knobs.json` (git-ignored by `combo_*.json`; read-modify-written under `file_lock`, read back
    after the write so a failed save raises, without the money-state alarm): per group (`all`, each sport, each league) the would-be values `v`, `step_at`, `why`, the last run's
    rows `last` and a short `hist`; `brake` per league; `settings` = Pete's own caps and any system raise (#260);
    `_at`/`_next`/`run`. Every proposal is also a row in the history file's **`knob_shadow`** table (knob, league,
    from, to, status, gain, share, band, t, new, holdout gain and count, words, the group's bet count and stake, the value
    the live code uses for that group today, and the bar's version), "thin" rows included, kept 180 days.
  - **Stepper** `knob_tune` (weekly, `KNOB_TUNE_EVERY`): for each group and each `cls == "tunable"` knob with a judge,
    one step either way (`knob_candidates`: `add` or `mult` steps, clamped to `min`/`max`; a knob that starts off
    switches on at `on_value`, and off from below its range), every other knob at the group's current value, judged by
    the registry's judge (`knob_judge`): **`_replay`** for the profit floor, risk weight and loss cut (the cut only where
    the live loss guards would have held, `_cut_guard_ts`), **`_sl_replay`** for the loss guards' timing and fall,
    **Smart Buy's band** for its dial (a bet the new level skips loses its result, one it keeps gains it, $5 each).
    Groups start from today's live value from their **own** record (`_knob_seed`), never a borrowed one. Pete's bar
    (`knob_evidence`, `KNOB_EVIDENCE`): **10+ bets the step changes, a gain of 2%+ of everything the group staked, 2+
    standard errors from luck (t of the band's per-bet gains, sample standard deviation), 20+ results from games after the group's last step, and
    the newest 30% of the group's bets (by start) must gain too** on at least 3 bets the step changes (`KNOB_HOLD_MIN`); the bars are on
    all the bets, the holdout must agree. A group needs `SMART_MIN_N` (30) / `SL_MIN_N` (50) / `SB_LEARN_N` (30) results
    of its own first ("thin" otherwise). **One step per group per run**: the biggest gain; ties go to the smallest change
    (in steps), then the registry's order; other steps that clear the bar are noted as "qualifies", a step failing only
    the holdout as "vetoed". Smart Buy's soft top (level 3 under 100 results) holds. Never stepped: invariants, evidence
    knobs, settings; **tied** knobs (`KNOB_TIED`: `swing_base` moves only through the risk weight, #258); **shared** knobs
    (`shared_with`: `sl_checks`/`sl_span`/`sl_gap` with hedging, `cash_slip`, `live_spread`, `sb_ev_min`), which must be
    split first; knobs whose judge can't take them as a parameter yet (exit_policy's constants: PR3; hedges: PR6; Smart
    Buy's simulator constants: PR7), listed as "waits". #258's bounds: in a **one-of** set (`KNOB_ONE_OF`: swing base /
    risk weight; the lock-in trio) only one knob may stand off its start per league, and the **risk product**
    (`KNOB_PRODUCT`: risk weight × swing base × checkpoint, each as a share of its start) stays inside 0.5×–2.0×.
    A braked league is skipped. Time-bounded (`KNOB_BUDGET` 60 s, the bet reading and each replay included); a run cut
    short continues a day later from the groups not yet judged in that weekly cycle (`run.cycle`), and a group cut in the
    middle takes no step; a run that hits an error waits a day too (in memory, `KNOB_RUN`, and in the file), and the card
    says why (`run.why`). One replay cache is shared across groups. Never raises, Pi never (`ROLE_BACKUP`).
  - **Brake** `knob_brake_pass` (every 30 min, `KNOB_BRAKE_EVERY`): per league, the history file's real automatic sales
    (`sell_log` `result='sold'`, not the Pi; profit = the offer after the single-bet fee minus that share's cost; **one bet
    counts once** however many parts it was sold in) made after its last brake **ended** (sales during a brake never count
    after it) and within 30 days. `knob_brake_check`: the **last 4 all lost money**, or (with 4+ sales) together they
    **lost more than 5% of what they staked** (`KNOB_BRAKE`). Shadow records "would brake": the league's would-be values
    back to their starts for 14 days, its next step needing 20 new results, a `knob_shadow` row, and **one push per league
    per 14 days**, only when it would change something (a value off its start), worded without the notifier's urgent
    words so it goes in the digest ("Self-tuning test, nothing changed: ..."). Information only.
  - **Watcher:** `shadow_loop` calls `H.knob_pass()` (brake, then stepper) **outside `odds.lock`**, after the smart-sell
    scorecard; logs its lines ("knobs: ...") and hands the push lines to the notifier. Never raises.
  - **Results › What's working › Selling:** a folded card "🧪 What self-tuning would change" (`knobShadow` in
    `watcher/spa/knobs.js`, data `analytics()["knob_shadow"]` = `knob_shadow_view()`, read from the file only): the header
    counts steps and brakes; opened, "A test run: nothing changes yet", the bar in plain words, last/next run, league
    chips, per league "Would change", "Also clears the bar", "Held back by the newest bets", "Where the test has it now",
    a brake (test) banner, the count of steps that didn't clear the bar, what needs more results; which knobs are tested
    so far and which wait or are shared. Only the fold and the chips are controls. The header keeps its focus ring.
  On Pete's real history (read-only copy, 2026-11-21): 30 settled bets with recorded prices in 60 days, so every league
  is thin; for everyone, switching the loss cut on at 15% would have gained $6.67 on 6 bets (4.8% of stake, 4.5 SE, the
  newest 30% agree) but is short of the 10-bet band. No brake.
  Nothing touches Pause, can_trade / the Pi, rule 8, caps, the tap lock or any buy/sell path. Tests: `t_knobstep.py`
  (the bar fires only when every part holds; the holdout veto; bounds, mult steps and on/off; borrowed only stricter;
  the resolver and the brake; #260's caps; #258's tied / one-of / product; one step a league, ties; invariants,
  evidence knobs and settings never judged; shared/tied/waiting knobs never stepped; thin histories do nothing; the live
  tuners' files untouched; weekly; 20 new results; errors and the time budget; the Pi; the brake's streak and month rules,
  the Pi's rows, one push, reset, no re-trigger from old sales; with the shadow on every live decision byte-identical:
  `smart_params`, `stoploss_params`, `sb_dial`, `exit_settings` and 400 `exit_policy` answers per league, `hedge_guard`,
  `auto_cap`, `kalshi_discount`, the files and settings), `t_knobs.py` (only analytics and the watcher's `knob_pass` touch
  the registry; no live code calls `knob()`), `test_knobshadow_ui.py`.
- **Self-tuning: smart sell's exit numbers go live (issue #228, PR3).**
  Pete (2026-11-21): the guessed selling limits self-adjust per league on evidence; invariants never. PR3 is the first
  step that changes live selling, behind a master switch, and only for smart sell's **exit numbers**.
  - **The switch.** Settings › Money › **Let smart sell tune its own numbers** (`knobs_live`, shared setting, in
    `SHARED_KEYS` and the web app's `SET_KEYS`). **On by default**, under Pete's standing #228 opt-in (guessed limits
    self-adjust per league on evidence; the brake as he set it). `knob_switch_on()` reads the shared settings file (like
    the other switches), at most every 10 s; unreadable = off. **Off = byte-identical to before this PR**: every exit
    decision reads the constants and smart_tune's file exactly as before (its old either-way borrowing included) and
    PR2's stepper only proposes.
  - **What is live** (`KNOB_LIVE`): the profit floor, risk weight and loss cut (`smart_floor`, `smart_lam`,
    `smart_loss`), the least chance to take a profit (`exit_q_min`), the two estimate allowances (`exit_est_smart`,
    `exit_est_tp`), take profit's minimum (`tp_min_gain`), the lock-in numbers (`trail_arm`, `trail_arm_cost`,
    `trail_drop`, `trail_floor`) and the loss cut's accept (`cut_accept`). Everything else stays shadow (as of PR3; PR5
    made the loss guards `sl_*` and the hedge confirmation counts live, below): the hedge lock-in knobs, Smart Buy's dial and constants, the shared and tied
    knobs. Never tuned: Pause, can_trade / the Pi, rule 8, cap fail-closed, fresh score/price age, in-play, a real fresh
    quote before a sale, the stop-loss/hedge/break guards, secrets.
  - **exit_policy takes its numbers as parameters** (`prm` keys `q_min`, `est_smart`, `est_tp`, `tp_min`, `trail_arm`,
    `trail_arm_cost`, `trail_drop`, `trail_floor`, `cut_accept`), each defaulting to its constant (the registry's start),
    so a caller that passes nothing decides exactly as before (`EXIT_POLICY_VERSION` 2). `_replay` passes them (`ex=`)
    and can replay Pete's own take-profit % (`tp=`); its defaults are unchanged.
  - **The live read path.** While the switch is on, `take_profit_reason`, `single_sell_reason` and `exit_settings`
    (Smart Buy's simulator and the exit replay play the same policy) add `knob_exit_prm(tickers)` (only the numbers that
    differ from their start; `{}` when off, braked, nothing learned or on any error), and `smart_params` answers through
    `knob_smart_params` (falls back to the old walk, logged, if it ever errs). Per number, `knob_live_value`: the league's
    own value, else its sport's, else everyone's; **a borrowed value only stricter** than the start (#259; the loss cut is
    never borrowed). While a league's **live** brake holds its own values are set aside: the start, or a borrowed
  value when that is stricter (a brake never makes selling looser; a test brake recorded while the switch was off never
  changes live selling, `_knob_braked_live`). A group's own value is self-tuning's record (`lv` in
    `combo_knobs.json`, with when, `lat`) unless smart_tune moved the same number later (while the switch was off), else
    smart_tune's own (n ≥ 30) for the floor/risk/loss. A recorded value outside the registry's bounds or not a number is
    ignored (`_knob_valid`). `combo_knobs.json` is cached 60 s for the sellers (`knob_state_cached`; this process's saves
    refresh it at once).
  - **One mover per value (#267).** With the switch on, `smart_tune` stops moving the floor, risk weight and loss cut (it
    still counts `n`/`ret` and still tunes the loss guards); `knob_tune` moves them, starting from smart_tune's own
    values, and **never writes smart_tune's file** (or any setting or CFG). Every run starts every knob from the value
    live uses for that group's own record (re-read each run; the shadow no longer drifts from live).
  - **The stepper, live.** Weekly, per group: at most **one live step** (exit knobs, status `stepped`, `lv`/`lat`,
    `lstep_at`, a `hist` entry with `live` and the words; every live knob is judged from the value live really uses, a
    borrowed stricter one included, `knob_live_value`; at everyone's or soccer's level a step is live only when a league
    would take it, i.e. stricter than the start and not the loss cut, else it stays a test) and, separately, at most one shadow "would step" (the loss
    guards, Smart Buy's dial; `v`, `step_at`). Judges: `_replay` for the floor, risk weight, loss cut (only where the
    live loss guards held), least chance, take profit's minimum, the lock-in numbers and the cut's accept, run with
    Pete's own take-profit % and lock-in switch; the estimate allowances wait (the replay has no real Kalshi offer to
    set against the estimate: PR4). #258's bounds still apply (one of the lock-in trio off its start; the risk product).
  - **The bar, with a real holdout (#264).** `knob_evidence` now uses only bets from games **after the group's last
    step** (live and shadow apart), split by start: the step is chosen on the **older 70%** (10+ bets it changes, a gain
    of 2%+ of what those bets staked, 2+ standard errors from luck), and the **newest 30%**, which played no part in
    choosing it, must gain too on 3+ bets it changes; 20+ results since the last step. **#268, decided:** tightening
    needs the same bar as loosening (one bar both ways; nothing is waved through because it is "safer").
  - **The brake, Pete's #266 ruling, refined by #284 (PR4 below).** A sale is a **loss only when holding was expected
    to pay more than the sale got** (never merely "sold for less than it cost": a loss cut that saved money did its job).
    `_knob_brake_sales`: one row per bet however many parts, sold = Kalshi's ledger proceeds after the fee when known
    (else the offer after the single fee), holding = what holding was expected to pay at the time of the sale
    (`knob_sale_expect`, PR4; PR3 used `sale_outcomes`' realized figure); a bet still waiting for its result, or void, counts neither way;
    only the app's own (not the Pi), after the league's last brake ended, within 30 days. Fires on 4 such losses in a
    row, or (4+ sales) the month's sales getting more than 5% of their stake less than holding. **Live:** the league is
    back on its starting numbers for 14 days (its own values are set aside while it holds, a stricter borrowed value
    still applies; its own self-tuned values are put back to the start, newer than anything smart_tune set, so they
    stay there until a new step clears the bar), logged `braked`, **one push** per league per 14 days when it changed
    something ("Self-tuning brake: in NBA, ... Nothing to do; it can start tuning again after <date>."). A brake that
    changed nothing doesn't restart the league's evidence window. Pete's #284 rulings (PR4): the loss is measured on
    the expectation at the time of sale, and a reset is never looser than what the league had learned.
    Shadow (switch off): "would brake", as in PR2.
  - **Every change is logged and shown.** `knob_shadow` rows (`stepped` with knob, league, from, to, why; `braked`), the
    watcher's log ("knobs: self-tuning changed NBA: ..."), and Results › What's working › Selling: the card becomes
    "🎛️ What self-tuning changed" while on (header counts changes and brakes; per league "Changed", newest first, with
    date and the evidence in plain words; a live brake banner; "Tested, not live yet" for the shadow knobs; "Where it
    stands now"), "🧪 What self-tuning would change" while off. The registry card says which numbers tune themselves and
    shows them per league while on. Only a brake pushes.
  On Pete's real history (read-only copy, 2026-11-21): smart_tune's file has every league at the start (n under 30), no
  `combo_knobs.json` yet; a live run steps nothing (everyone: 32 bets, no step clears the older-70% bar; every league
  thin) and the brake has one finished automatic sale. **So turning this on changes no decision today**; the first live
  step needs a league (or everyone) with 30+ settled bets and a step that clears the bar.
  Tests: `t_knoblive.py` (switch off: 5,000 random combo and single decisions plus smart_params / exit_settings
  byte-identical to the verbatim pre-PR code, `fixtures/exit_knobs_old.py.txt`, with self-tuning's record full of
  learned values; switch on with nothing learned and with only leagues' own values: identical; exit_policy with the
  starts passed in = none; each number moves the decision; a learned value changes only its league, borrowed only
  stricter; the brake on the new measure, 14 days, one push, the starts kept after; one live step a group, the bar, the
  holdout veto, judged only after the last step; smart_tune stops moving floor/risk/loss while on; never smart_tune's
  file, a setting or CFG; the Pi; damaged values), `t_knobstep.py` (PR2's checks with the switch off, the new split),
  `t_knobs.py` (who may read the registry; knob_view mirrors smart_params with the switch on), `t_exitpolicy.py`,
  `t_safety.py`, `t_tune.py`/`t_replaypolicy.py` (smart_tune with the switch off), `test_knobshadow_ui.py` (both cards),
  `test_knobs_ui.py`, `test_analytics.py` (the Settings switch, on by default, saves both ways).
- **Self-tuning: the brake on expectation, real offers in the judge, the slip split (issue #228, PR4).**
  Builds on PR3 (`docs/changes/228-pr3-exit-live.md`). Same switch (`knobs_live`, on by default; **off = byte-identical**:
  every exit decision and every automatic sale's slip are exactly as before this PR). Pause, can_trade / the Pi, rule 8,
  caps failing closed, fresh score/price age, in play and a real fresh offer before any sale are untouched.
  - **The brake, Pete's two rulings (2026-11-22, #284).**
    - **(a) A loss is measured on what holding was EXPECTED to pay at the time of the sale**, not on how the game ended
      (refines #266). `knob_sale_expect(row)` reads only what the sale log recorded at the sale, on the footing smart sell
      itself uses: a **combo**'s offer against Kalshi's usual offer at the logged chance (`kalshi_discount` in play or
      between games x chance x payout x the share sold); a **single**'s sale after its fee (`single_fee` at the bid)
      against a sale at the logged chance less half the bid/ask gap it sold into (a single only sells at the bid; the ask
      is logged from this PR, `sell_log.ask`; before that half the widest gap smart sell sells into, 3 cents; at least
      `KNOB_BRAKE_BID`, 1 cent), after the same fee, x the contracts sold. Each bet counts once (its parts summed); a part with no logged chance doesn't count; a sale counts as soon as
      it is made (no waiting for sale_outcomes). The sale log now records whether a game was under way and a single's ask
      (`sell_log.live`, `sell_log.ask`, added on start; if they can't be added the sale is still saved without them; older
      rows count as in play, Kalshi's lower discount, so they are judged gently).
      Without this footing every sale would count as a loss by construction (Kalshi's offer is ~82-88% of fair; a single
      sells at the bid after a fee), so this is the only threshold change the math needed; 4 in a row, more than 5% of
      the month's automatic-sale stake, 14 days and one push are unchanged (`KNOB_BRAKE`).
    - **(b) When it trips, a league goes back to its start numbers but never looser than what it had**: per knob the
      stricter of the start and its current value (`knob_stricter_of`, the registry's `stricter` direction; for the loss
      cut, off is strictest). `knob_brake_pass` puts back only the numbers looser than their start (`reset` lists them;
      nothing looser = recorded, no push, the evidence window not restarted); while the brake holds, `knob_live_value`
      gives the strictest of the start, the league's own value and what it would borrow. The shadow brake does the same to
      the test's values.
    - Words: the push ("...got less than holding was expected to pay when they sold ... back on its starting numbers for
      14 days (any number it had made stricter stays)"), the Results card's brake banner, its intro, the registry card and
      Settings › Money's switch text say the same.
  - **The judge replays against real Kalshi prices (#285).** `knob_tune`'s replay judge now runs `_replay_real` (the plain
    `_replay`, used by `smart_tune`, `sim_exit` and the lab, is unchanged): the same exit_policy decision, but
    - a **combo** sees the real Kalshi offer recorded within an offer's life before that moment (history `offers`,
      `real_offer=1`), as live does, so the estimate allowances matter; it sells at that offer, else at the next real one
      recorded within an offer's life (the same quote re-written every 2 minutes counts once; live asks Kalshi for one), else at the estimate; only when it reaches the slip x
      the line, and never under what was paid unless cutting a loss (live's own guard);
    - a **single** is valued and sold at its recorded bid on the pick's side (`price_path`, within `SINGLES_SELL_AGE`; a
      NO pick reads the YES book the other way), never into a gap wider than `LIVE_SPREAD` (a NO pick, whose recorded chance is the YES price, replays as before);
      with no recorded bid, as the
      plain replay (the chance after the fee, less 1 cent).
    - **Haircut for loosening steps** (`knob_loosens`: a step that has the app sell sooner or more often): both sides of
      the comparison are replayed with `KNOB_HAIRCUT` on any price that is not a real recorded one (a combo with no offer
      sells at 97% of its estimate, an offer right at the slip line; a single with no bid 3 cents under its chance, half
      the widest gap smart sell sells into). Tightening steps are judged without it. Real recorded offers and bids are
      never cut.
    - **Sold bets join the evidence** (`_knob_items`): real combos that smart sell cashed out (which `_tune_items` leaves
      out; never your own Cash out taps), only when their recorded prices run on to the end of the games (a cashed combo's
      own ticks stop at the sale), with riding to the end = what holding paid (sale_outcomes' result on the ledger or the sale log; unknown or void =
      left out), and a panel combo is counted once (the bets table's copy is dropped). `smart_tune`'s own evidence is
      unchanged.
    - Now judged: the two estimate allowances (`exit_est_smart`, `exit_est_tp`) and the slip (below). Same bar (PR3:
      older 70% / newest 30%, 10+ bets, 2%+, 2+ SE, 20 new results), one mover per value (#267: nothing else moves them).
  - **The slip, split (#285).** `CASH_SLIP` drove both smart sell's own acceptance of a combo's real offer and the
    retries after a buyer backs out. Now `auto_sell_now` reads **`AUTO_CASH_SLIP`** (97%, the registry's new tunable
    `auto_slip`, live through `knob_auto_slip(tickers)`: today's 97% while the switch is off, nothing is learned, the value
    is damaged or on any error; a borrowed value only stricter; kept while braked only when stricter), and
    `_accept_with_retries` keeps `CASH_SLIP` (registry `cash_slip`, now an invariant: self-tuning never changes how your own
    Cash out tap behaves). **Pete's decision, 2026-11-23:** auto cash-out's retries no longer use `CASH_SLIP` ("I don't
    think it needs to be within 97% of the first price, but it should definitely stay above the smart sell line"): up
    to 10 accepts a round (`AUTO_CASH_RETRIES` 9, "let it retry 7, 8, 9 or even 10 times"), each on a fresh offer that
    must clear the smart-sell line the sale was made on (threshold x the path's slip x share), and, for a sale taking a
    profit, cost ("It should only sell at a loss if that's a way to try to minimize losses. Not when there's still an
    opportunity for it to get profit."); a loss-cutting sale (learned cut, guarded stop-loss, first offer already below
    cost) may go below cost down to the line, but never under 97% of its first offer (a loss cut's line is near 0).
    Your own tap keeps `CASH_SLIP`.
    After a failed round there is no 10/60-minute wait for combos (Pete, 2026-11-23: "10 minutes and 60 minutes is
    crazy. It should retry based on changes in the game, not some arbitrary number of minutes"): the combo is tried
    again only when a score, a game's status (live, a break, final) or a pick changes, or its chance, a newer real
    offer or the smart-sell line moves 5% (`COMBO_RETRY_MOVE`; at least 2 points of chance / 25 cents), never twice
    within `COMBO_RETRY_GAP` 5 s. Singles keep their #334 back-off.
  - Card fix: a league braked before any stepper run is now shown on the Results card (it was hidden).
  On Pete's real history (read-only copy of `combo_history.db`, `combo_smart.json`, `combo_discount.json`,
  `combo_smartbuy.json`; 2026-11-22): the judge has 39 settled bets in 60 days (33 as before plus 6 combos smart sell
  cashed out with known results; 34 with enough recorded prices; 8 with real offers, 293 offers in all; 2 with recorded
  bids). Everyone (34) is the only group over 30; nothing clears the bar (best: the loss cut on at 15%, +$3.67 on 3
  changed bets, needs 10); every league is thin (mix 12, nhl 8, ncaaf 6, nba 4, ncaamb 3, tennis 1). The brake sees 1
  automatic sale in the last 30 days (college football, $0.42 above what holding was expected to pay): no brake. **So nothing changes today.**
  Tests: `t_knobreal.py` (singles with nothing recorded = the plain replay on 600 paths; a combo passes up a real offer
  under the slip line, sells at a real offer, takes the next real one, the slip, never under cost; the estimate allowance
  now changes the result; singles at the recorded bid, the gap, stale bids; loosening vs tightening, the haircut on both
  sides only for loosening, a real price never cut, a lower floor gains less on the haircut; cashed combos with what
  holding paid, unknown left out, a panel combo once, smart_tune's list unchanged; the market record; `auto_slip` off =
  97% on 2,000 random bets whatever is recorded, on with nothing learned = 97%, a league's own, never borrowed looser, the
  brake keeps a stricter one, damaged = 97%), `t_knoblive.py` (the brake on expectation: loss cuts that beat the
  expectation never brake even when the game came back, no logged chance doesn't count, 4 under the expectation brake
  even when holding really paid nothing, counted at once, singles and combos' footing, the month rule; the stricter-of
  reset live: a looser number back to its start, stricter ones kept, push only when something changed; PR3's checks with
  the switch off on 5,000 states and on with nothing learned, unchanged), `t_knobstep.py` (the shadow brake keeps a
  stricter test value; the allowances and the slip are judged, nothing waits), `t_knobs.py` (the split: auto_sell_now
  reads only `knob_auto_slip`, the retries keep `CASH_SLIP`), `test_knobshadow_ui.py` (card wording).
  Follow-ups filed: #298 (the check list counts a crashed engine test as passed), #299-#302 (profit: the brake's
  materiality band and what it can't see, the sale's own discount, the haircut's stickiness, remaining replay gaps).
- The **Let it ride** slider sets boldness: Cautious sells sooner, Bold later, "Ride it out" turns smart sell off.
  It also still drives the original combo cash-out plan (sell when the offer beats waiting another game).
- Bets Pete places on Kalshi himself are tagged "You, on Kalshi" (the app records every buy it makes; everything
  held when tracking began counts as the app's). The panel avoids games he already bet himself.

- **Self-tuning PR5-PR7: the stop-loss as a 3-way choice, the loss guards and hedge numbers live, break_ok and Smart
  Buy watch-only (issues #228, #306; shipped in 2026.11.21.134).**
  - **#306 (Pete: tighten).** A league's own record may no longer loosen four exit numbers below their start:
    `cut_accept` (min 0.02), `exit_q_min` (min 0.5), `exit_est_smart` (min 0.95), `exit_est_tp` (min 0.9) now have `min`
    = `start` in the registry, so `knob_candidates` only steps them stricter and `_knob_valid` ignores a value recorded
    below the start before this change (the start is used).
  - **Selling at a loss: three choices (PR5).** Settings › Cash out & hedging › **Selling at a loss** replaces the old
    on/off "Manual override" switch: **Never sell at a loss** (no automatic sale below what you paid: neither the stop-
    loss nor the learned loss cut, combos and singles), **Let it tune itself** (the default) and **Allow (guarded)**
    (the old switch on; every guard still holds). Setting `stop_loss_mode` (shared, synced to the watcher, `SL_MODES`);
    `sl_mode()` reads it, and an older saved file with only `stop_loss` reads as Allow when it was on, else Let it tune
    itself (nothing is rewritten; anything unreadable = Let it tune itself). The web app writes both, keeping
    `stop_loss` = (mode is Allow) for older copies (the Pythonista app, a watcher not yet updated). Let it tune itself
    starts OFF in every league: `sl_allowed(tickers)` is true only with self-tuning on and the league's **own** record
    having turned the new knob `sl_auto` on (borrow `own`: never borrowed; off while its live brake holds). `sl_auto` is
    judged by the loss guards' replay (`_sl_replay`: on = what selling at a loss would have got, on a sale price cut to
    97% for this loosening step (#285); off = held) on Pete's bar. Turning `sl_auto` on needs 3 standard errors
    (`KNOB_EVIDENCE_STRICT`), not 2. With Never, a single never sells below what it cost either. A tuned stop-loss sale
    says "Stop-loss (tuned for this league)" and logs `sl_mode`. Pete's MacBook Air today has `stop_loss` on, so it reads as
    Allow (guarded): unchanged.
  - **The loss guards and confirmation counts go live (PR5).** `sl_prog`, `sl_drop`, `sl_auto`, `sl_checks`, `sl_span`,
    `sl_gap` are in `KNOB_LIVE`: with "Let smart sell tune its own numbers" on, `stoploss_params` and the new
    `sl_confirm_params` read them through `knob_live_value` (league's own, else sport's, else everyone's, borrowed only
    stricter, the start while braked; smart_tune's own `sl_*` record counts as the league's own, as before), and
    smart_tune's `_sl_tune` only counts while the switch is on (one mover, #267). The confirmation counts are **split
    from the hedge's** (`hedge_checks`, `hedge_span`, `hedge_cgap`, constants `HEDGE_CHECKS/SPAN/CGAP`,
    `hedge_confirm_params`); `_sl_confirm`, `_sl_held`, `_sl_replay`, `_cut_guard_ts` take `cf = (checks, span, gap)`.
    #285 item 2: the stepper judges the loss guards (and the learned cut's guards) from the values `stoploss_params`
    really uses, stricter borrowed ones included (`_knob_sl`), not the group's own only.
  - **break_ok, watch-only (PR5).** The fixed "never at a break" rule becomes the conditional `break_ok(ticker, side,
    sc, now, what)` in `stop_loss_leg` and `hedge_guard`: act at a break only on a fresh two-sided book (gap within
    `LIVE_SPREAD`) whose pick's mid moved `brk_move` (start 8 points, 4-20) since the break began, held on `BRK_READS` 2
    reads `BRK_SPACE` 60 s apart (`brk_fires`), half the move with fresh injury news (`_brk_news`, from a cached report
    only), and a fresh order book read (max_age=0) still showing the move. It **never acts in this build**: `BRK_LIVE =
    False`, and `brk_on`/`brk_move` are not live knobs (start off per league, borrow `own`). Today it only records break
    episodes: `break_watch` (from `auto_sell_now` via `break_watch_held`, and from the guards) notes the pick's bid/mid
    every 20 s+ from prices the engine already read (`PRICE_SEEN`, no new Kalshi or ESPN request) while the game is at a
    break, the price once play resumes, and when the rule would have acted, into table `break_ep`; the leg is also
    price-watched so its path with score lines is recorded. The weekly judge (`_knob_res_brk`: selling at the break vs
    just after it, per contract) needs `BRK_MIN_N` 40 own episodes and the usual bar; its steps are "would step" only.
  - **Hedge knobs (PR6), watch-only for now.** The hedge's confirmation counts are split from the loss sale's and are
    live knobs (no judge yet, so they stay at their start; their minimums equal the start: 3 checks over 3 minutes,
    never looser). `hedge_lock_share` (the 95%) and `hedge_lock_cost` (never under 1x: a hedge never locks in a loss)
    now read through `hedge_beats(hg, whole, tickers)` / `hedge_lock_cost(tickers)`, but are **not live knobs**: their
    judge (new evidence, `hedge_seen_note`: each time auto cash-out weighs a hedge against a due sale, one row per combo
    per 10 min, table `hedge_seen` with the whole offer, what the hedge locks in and costs, the combo's cost, your cap,
    Prefer hedging, and whether the game was in play on a fresh score and not at a break; `_knob_res_hedge` counts a
    hedge at what it locked in on a 2% worse fill, never where the game wasn't in play/fresh) only sees a hedge's least,
    never how the game ended, so the code review found it would always push the share up. They step in shadow
    (`HEDGE_MIN_N` 30 decisions) until a judge on real outcomes exists. **The hedge cap raise** (Pete's opt-in, ceiling
    $150): `knob_cap_step` ($10 a run, 3 standard errors, never above $150, never lowering Pete's value) runs as a test
    only (`HEDGE_RAISE_LIVE = False`); `hedge_cap_now()` (used by `auto_sell_now` and `hedge_fresh`) already honours a
    raise, the ceiling and the brake (your value while any league's brake holds; a live brake clears a raise), so
    turning it on later is one switch.
  - **Smart Buy (PR7), watch-only.** `sb_ev_min` (smallest expected profit to recommend, shared with Build's spreads &
    totals list) is judged on Smart Buy's checked bets with results (`sbev`: a bet the bar drops loses its result); a
    shared knob may now be stepped in shadow when it has a judge, never live. Nothing Smart Buy buys changes. Its other
    constants still wait for a judge (re-simulating each bet).
  - **Also:** `tests/run_checks.sh` now fails an engine test that stops with an error after printing some PASS lines (it
    used to count as passed); that showed `t_idea_inplay.py` reading the watcher from the wrong folder (5 checks never
    ran), fixed. Results › What's working › Selling's footer counts the live numbers.
  - **Never touched (invariants):** Pause, `can_trade`/the Pi, rule 8 (`hedge_unsure`, `rfq_unsure`), caps failing
    closed, fresh score/price ages, in play, a real fresh quote or book before a sale or hedge, secrets. Switch off =
    the old code's numbers exactly. Tests: `t_knobpr567.py` (400 random states off and on-with-nothing-learned vs the
    old functions; #306; stricter-only; sl_auto never borrowed or braked; break_ok never live and its rule; episodes;
    hedge cap ceiling and brake; the new judges' signs), `t_stoploss.py` (the three choices end to end in
    `auto_sell_now`), `t_settings.py` (migration), `t_knobs.py`, `t_knobstep.py`, `t_knoblive.py` updated,
    `test_slmode_ui.py` (the Settings wording, taps saving, no sideways scroll, dark and light).
  - Settings sync: `sl_sync` applies Selling at a loss from the phone and the web app; a message without a valid
    `stop_loss_mode` may only make it stricter (an old "off" turns Allow into Let it tune itself, an old "on" is
    ignored). Hard rule 2's hedge ceiling of $150 is not live yet (`HEDGE_RAISE_LIVE = False`).
  - **Release 134 review fixes (Never sell at a loss made honest):** under Never, a combo cash-out whose buyer backs out
    never takes a fresh offer below what was paid (`accept_cash(t, floor=cost x share)` → `_accept_with_retries`;
    Pete's own taps keep the 3% retry rule; under the other choices auto cash-out's retries follow the smart-sell line
    and the sale's purpose, Pete 2026-11-23, above); a single with an unknown cost is skipped, and its
    proceeds are counted after the order's rounded fee (`single_fee(bid, n)`). `_brk_news` reads the injury cache only
    while it is under 25 minutes old, so it can never trigger an ESPN fetch inside auto cash-out. Test: `t_neverloss.py`.
- **No sell line above what a bet can pay (#371; Pete: Live said "Smart sell · sells at $14+" on a $13 bet).** `floor2`'s
  `floor x cost` (1.2-2.0x) is over the payout for a single bought above about 1/floor (about 67 cents at 1.5x), and a combo's
  `wait_threshold` adds `model_cushion` on top of `wait_value`, so lines could never be reached. **The ceiling**
  (`sell_top`): Kalshi's top price is 99 cents (`SELL_TOP`), so a combo sells for at most `pays x 0.99` and a single for at
  most `n x (0.99 - single_fee(0.99, n))`; `sell_line_shown(line, top)` gives `(line, False)` or `(None, True)`. When out of
  reach there is no number: the singles chip says "Smart sell · holding to collect $13" (`sell_over`), a combo "Sell after
  next game · No offer can beat it" (`thr_over`), `plan_words` "No offer can beat that: it pays $13 at most.", and the
  Pythonista card says it won't cash out just to beat the next game (only Let it ride's line; lock in, take profit and the
  guarded cut loss still run). Lines show cents (`cents()` in live.js, `$x.xx` in `plan_words`/`cash_block`) because `money()`
  rounds from $10 up. **Display only, no sell decision changes:** `exit_policy`, `single_sell_reason`, `take_profit_reason`,
  `wait_threshold`, `auto_sell_now`, `plan_cashout`, `tp_ladder` and `cash_nudge` still compare with the unclamped line
  (clamping would have let offers near the top clear a bar they can't clear today). Follow-ups: #375 (profit: should the
  floor be capped at what the bet can reach?), #376 (wording, shipped: one phrase, "no offer can beat waiting", is now used on the do-now card, the combo row,
  `plan_words` and both Smart sell chips; the combo chip (`ssChip`) shows the same hint singles had, "sells at $X+" or the
  phrase, reading the combo's `threshold`/`thr_over`). Tests: `t_sellmax.py`, `test_singlesell_ui.py` (the phrase on the chip
  and the do-now card).
- **Auto cash-out when buyers back out (#372/#385; Pete's decisions are in the self-tuning bullet above).** The success lead
  ("Took the profit...", stop-loss and cut-loss leads) goes out only when the sale really went through; a failed round sends
  one plain note instead (`combo_fail_note`: "Auto cash-out tried to sell <combo>: the buyer backed out N times [and no fresh
  offer came in | and the next offer ($X) was below the line], so nothing was sold." plus when it will try again), at most
  one an hour per combo (`COMBO_FAIL_TELL` 3600 s, `MINE["combo_fail_told"]`). **Retry on changes, not a clock:** after a
  failed round (`COMBO_BACKOFF_STOPS`: cancelled, failed, no fresh offer, offer too low, out of time) `combo_wait_start` saves
  a snapshot in `COMBO_WAIT` (each open pick's game from `leg_score`: state, both scores, at a break; the combo's chance; the
  last offer; the smart-sell line) and `combo_wait_why` lets a watcher pass try again only when a score, a game going live or
  final, a break, a decided pick, the chance (5%, `COMBO_RETRY_MOVE`, and at least 2 points `COMBO_RETRY_MIN_P`), a newer real
  offer (5%, at least 25 cents `COMBO_RETRY_MIN_USD`) or the line moved the same; the new state becomes the baseline; the only
  clock is the 5 s `COMBO_RETRY_GAP`; while waiting it asks Kalshi nothing and logs one line (the next round logs `retry_on`).
  A sale resets it; an unknown outcome is never retried (rule 8). **Up to 10 tries a round:** `AUTO_CASH_RETRIES` 9 (registry
  invariant `auto_cash_retries`), a random 0.3-1.0 s pause before each (`AUTO_CASH_GAP`, `cash_gap`), one extra ask when no
  fresh offer came in, no new try after `AUTO_CASH_BUDGET` 120 s (worst case about 177 s). **The bar** is the smart-sell line
  the sale was made on (`_CASH_CTX.line`; no line = the old `CASH_SLIP` rule); **the purpose** decides below cost: a
  profit-taking sale never takes a fresh offer below cost (`_CASH_CTX.cost_floor`), a loss-cutting one (`rec["stop_loss"]`,
  first offer already below cost) may, but never under 97% of its first offer (`_CASH_CTX.cutting`); 'Never sell at a
  loss' was removed (#479). Before each retry it re-checks Pause, Auto cash-out and `can_trade()` and re-reads the account fresh (`fetch_account(max_age=0)`); if the combo is gone, reduced or the account is unreadable the round stops without selling (`ACCOUNT_STOPS`, fail closed; the auto-sell order is not put back, the next pass re-places it), so a manual Cash out tap in the web app mid-round cannot be double-sold; `restart_when_quiet` also waits (`sell_busy()`, bounded 240 s) while a sale round runs; one
  `auto_sell_now` pass starts no new combo sale after the budget. Rich log in `combo_autosell_log.jsonl` (`round`, `rounds`,
  `tries`, `agreed`, `line`, `floor`, `purpose`, `stop`, `asked_again`, `ask_error`, `low_offer`). Singles keep their #334
  back-off (`SELL_FAILS`). **Words (#384):** the note now ends "Still holding, and we'll keep watching: it tries again when
  the game or the price changes"; the generic fallback no longer repeats the raw error text from `_accept_with_retries`, it
  says Kalshi didn't take the sale this time. When it sells, the retries and the rate limit are unchanged. **Logging
  (#395):** an automatic combo sale that goes through on a retry under the first agreed offer logs `below_agreed` (dollars
  under, in the decision log and the console) and `retry_below_agreed()` counts them (`sell_scorecard()["retry_below"]`); the
  retry bar (the smart-sell line, cost floor, 97% for loss cuts) is unchanged. **Not changed (#396):** a clock retry of a
  stuck loss-cut sale would be a new automatic sale path, against Pete's "retry on changes in the game, not minutes" call;
  a restart already clears the park, so the combo is tried again then. Follow-ups: #383 (loss-cut floor, back-off vs
  hedge, busy hold). Tests: `t_cashretry.py` (also `below_agreed` and the counter), `t_combobackout.py` (also the notes);
  `t_neverloss.py`, `t_hedge.py`, `t_cutloss.py`, `t_stoploss.py` unchanged.
- **"Never sell at a loss": the copy matches Pete's rule (#382, #383; words only).** Pete's rule (2026-11-23): auto-sell never
  sells below what you paid, except when selling now loses less than waiting (the learned loss cut, or the guarded
  stop-loss). A sale that was a profit never retries below cost (superseded under `flex_sell`: see Flexible sell price, `began_at_profit_ended_below_cost`, with the 95%-of-cost profit floor); a loss cut never retries under 97% of its first offer
  (`CASH_SLIP`, kept as is). Checked against the code, which already behaves this way (`auto_sell_now`,
  `_accept_with_retries`, `smart_sell_singles`), so only the wording changed: the auto cash-out explainer, the `below_cost`
  knob description and the stale comment above the stop-loss guard. No decision logic, setting label or number changed. The
  Never setting still also turns the loss cut and stop-loss off (its Settings text already says so). Open, not changed
  (money decisions): a combo's below-cost first offer on a profit reason sells as a stop-loss whenever the guards hold,
  without asking whether a profit is still possible; combo cost floors ignore Kalshi's fee; the 60-minute back-off also
  skips the auto-hedge for a live loss cut (#383 items 2 to 6). Test: `t_sellwording.py`.
- **Sale alerts say the profit or loss (#390).** `sale_result_note(got, cost, cutting=False)` builds the phrase for every success
  message from the cost the app tracks (a combo's `cost` = paid plus buy fees, a single's scaled to the share sold):
  `+$1.42 profit (paid $2.19)`, `-$0.80 loss (paid $4.40)` (plus `, cut to limit the damage` for an automatic loss cut or
  stop-loss, `_CASH_CTX.cutting`), `broke even (paid $4.40)` (compared after rounding to cents). Cost missing, zero, negative
  or not a number: `(cost unknown)` and the old wording; no number is invented. Used by the combo cash-out
  (`_accept_with_retries`, yours or automatic), automatic single sales (`smart_sell_singles`) and your single Sell
  (`single_sell`); hedges and standing orders are buys and unchanged. Wording only. Tests: `t_sellprofit_helper.py`,
  `t_sellprofit_paths.py`.
- **Paper test: capped profit line for favorites bought above ~67c (#375; record only, default OFF).** Smart sell's profit
  line for a single (`max(q*P - lam*P*sqrt(q(1-q)), floor*cost)`) is above what the bet can ever sell for once it was bought
  above about 1/floor, so smart sell never takes a profit on those favorites (`sell_line_shown`'s "over", #371). Pete's call
  (2026-11-24): paper first, default OFF, nothing new automatic; this only RECORDS. `exit_cap_shadow(x, bid)` (called from
  `open_singles` for a held single whose line is out of reach, only when the new setting `exit_cap_shadow` is on; default
  False) writes one row to the table `exit_cap_shadow` with the time, the sale price after fees, today's answer
  (`live_decision`, hold or the reason) and the answer a line capped at `sell_top - EXIT_CAP_MARGIN` (3c a contract) would
  give (`alt_decision`, `alt_line`). Rows are throttled (a changed answer at once, an unchanged one every 5 minutes), pruned
  at 60 days / 100k rows, every error swallowed. Nothing reads the table back. `single_sell_reason` got an optional
  `cap=None` argument that only the recorder passes (always with `track=False`, so no peak moves); with `cap=None` the code
  path is the one that was there. No sell, buy, Pause, cap or rule 8 path is touched. Turning the paper rule into a live one
  is a separate decision for Pete, judged on this record. Tests: `t_exitcapshadow.py` (default off; row contents; the live
  decision identical with the switch on or off over a grid, through `smart_sell_singles`, with peaks and settings untouched;
  throttle, prune, failures swallowed, no reader).
- **Combo cost floor counts Kalshi's selling fee (#382, #383).** **UNCONFIRMED ASSUMPTION, stated plainly:** that Kalshi's
  combo cash-out selling fee equals the single-market taker fee (`single_fee`) has NOT been confirmed against a real combo
  sale. Pete approved building on it, so it is on by default, behind the switch `combo_sell_fee` (config, default `True`);
  set `False` and the cost floor judges the gross offer exactly as before. An offer with no readable `contracts` falls back
  to the old gross comparison and the decision log says so (`fee_note`), so it can never block every auto cash-out; the log
  carries `net` next to the gross `offer`; and a sale whose gross offer is at or above cost but whose net after the fee is under it
  is, when a guarded stop-loss is ready, tagged a stop-loss (`fee_loss`) and worded honestly as a small loss after Kalshi's selling fee
  (release 507 review; before, it read "took the profit"). A real profit is still "take a profit". The cost floor on automatic combo cash-outs now counts the fee the way singles do
  (`single_fee`, rounded up to the cent per order): new `combo_sale_net(offer)` = offer minus `n * single_fee(offer / n, n)`.
  Before, an offer exactly at cost passed every cost floor and still lost the fee. Now:
  - the **below-cost test itself** (`below` in `auto_sell_now`) compares the offer's net of the fee with cost, as singles do.
    An offer between cost and cost + fee used to count as "not below", so a profit sale took it and lost the fee; now it
    follows the existing below-cost rules unchanged (a cut-loss reason or a ready stop-loss sells it as a loss cut; a profit
    reason without a ready stop-loss is skipped, "below what you paid", with `net` logged; Never sell at a loss skipped it,
    see the retirement note below). So a better offer can never be refused where a worse one sells. This changes the INPUT to
    the existing stop-loss-on-a-profit-reason rule (a few cents more offers count as below cost), not the rule;
  - a **retry's fresh offer** must clear the same floor (`_accept_with_retries`: every profit-taking sale, `stop` "offer too
    low"); an offer with no readable contracts falls back to the old gross comparison (`fee_note`), never a block.
- Close to a tightening: nothing sells that did not before, and it only stops sales worth less than cost after the fee. Loss
  cuts (offer already below cost) keep their own rules (97% of the first offer, the smart-sell line). Deliberately **not
  changed** (still open in #382/#383): your own Cash out tap's
  97% retry, the setting wording. Pause, caps, rule 8 untouched. Test: `t_combofee.py`.
- **Loss-cut clock retry for a stuck combo (#396; Selling, auto cash-out when buyers back out, #372).** Pete's decision: a
  stuck combo **loss cut** (never a profit sale) is also retried on a clock, every 5 minutes (`LOSSCUT_CLOCK_SECS` 300), as a
  safety valve for when nothing in the game or the price moves. Until now a failed round parked the combo until the game,
  chance, offer or line changed (`combo_wait_why`), and the park is memory-only. `combo_wait_start` now also records whether
  the failed round was a loss cut (`cutting`), the episode's **first** offer (`first`, kept across rounds) and the clock
  tries used (`clock_n`). `combo_wait_why(..., kind=why)` grants a clock try only when nothing else changed, the wait is a
  loss cut, the sale is not a plan (profit) cash-out, 5 minutes have passed since the last failed round or clock try, and
  fewer than **`LOSSCUT_CLOCK_MAX` 6** clock tries were used for that position (about 30 minutes; after that only a real
  change reopens it; a sale resets it; a restart clears it). Every existing bound still applies, and two are added:
  - **Pause:** `auto_sell_now` returns first when paused; accepts re-check Pause, Auto cash-out and `can_trade()`. **Rule
    8:** an unknown outcome is `check`, its wait is dropped and `rfq_unsure` blocks it; the clock never retries it.
  - **97% of the FIRST offer, across rounds, for EVERY loss-cut round** (review fix: also a round started by a game or price
    change, not only the timed retries): a try whose fresh offer is under 97% of the episode's first offer is skipped and
    logged; inside the round the retries' floor is 97% of that same first offer (`_CASH_CTX.first_offer`), so the price
    cannot ratchet down round after round. **Flexible sell price (below) can loosen this within a round:** a retry's floor
    becomes what Flexible sell allows, down to the 85% backstop of fair value, not a hard 97%. Across rounds the 97% of the
    first offer still holds. (Wording corrected in the release 507 review; no behaviour change.)
  - The smart-sell line, the cost floor for a profit-taking sale and the retired Never sell at a loss floor: unchanged.
    **Only the "cut loss" reason:** a profit reason (smart, take profit, lock in, checkpoint, plan) never uses the clock,
    even when its below-cost first offer sold as a guarded stop-loss (that case now records the wait as a cut, so its later rounds keep the 97%-of-first-offer guard, but still gets no clock try). **Purpose
    re-checked at the clock try:** if the offer is now at or above cost (a profit sale) the try is skipped (`stop` "clock
    retry is for loss cuts only").
  - **Fail closed:** an unreadable account, a combo gone or reduced, or a damaged wait record means no clock try, logged.
    **Logged:** each clock try's decision line carries `retry_on` ("loss-cut clock retry N of 6 ..."), `clock_retry`, and its
    normal `stop`; skips log why; the cap is logged once per wait.
- Cadence (follow-up, not built): 5 minutes is the starting value. Pete said "let it tune itself": a follow-up issue records
  learning the cadence inside a safe band; nothing self-tunes here. No new automatic path for profit sales; nothing loosened.
  Tests: `t_losscutclock.py` (paused, unknown outcome, cap reached, 97% guard, profit-reason and profit-reason-stop-loss
  excluded, unreadable data, line/97% inside the try); `t_combobackout.py`, `t_cashretry.py` unchanged.
- **Flexible sell price (Selling, cash-out retries; ON by default, Pete's explicit opt-in 2026-11-24; Settings > Cash out >
  "Flexible sell price").** When a buyer backs out and the app asks for a fresh cash-out offer, the fixed "at least 97% of
  the first offer" line (your own Cash out tap, and an automatic loss cut) was judged against a price that can be minutes old
  in a fast game. With `flex_sell` on, each retry is judged against the game right now (`flex_decide`, called from
  `_accept_with_retries`):
  - `flex_now` re-reads every open pick: picks in play get their live chance through `combo_live_fair` (a fresh score,
    Kalshi's fresh book, the panel's own live guards); picks not started keep their last chance. It needs at least one pick
    in play, one pick per game, and no spread or total in play. `flex_wait_line` is what waiting is worth now (`wait_value`,
    risk-adjusted with the Let it ride multiple, plus the per-pick cushion, same as `wait_threshold`).
  - An offer is taken when it passes the **safety backstop** (at least `flex_backstop`, default 85%, of the combo's current
    FAIR value now: live chance x pays, NOT discounted by Kalshi's usual offer share (Pete, 2026-11-25); a combo cash-out
    carries no separate fee) and the floors the sale already had, AND one of: the old bar would have taken it; selling beats
    waiting now (offer at or above the wait line); it is a profit (at or above cost) and the chance has dropped 8% or more
    under the holdings' last reading; or it is a loss cut whose learned cut-off still holds on the fresh chance.
  - Automatic profit sales follow the same flexible rule as your tap and loss cuts (Pete, 2026-11-24): when the game moves
    fast they may go below the smart-sell line the sale started on. **A sale that began at a profit may end below cost**
    (Pete, 2026-11-24): in a fast-falling price, refusing can cost more later, so it is judged like any other offer (selling
    beats waiting now, past the backstop). A small loss can result and waiting could have been worse. Every such sale is
    recorded in `flex_shadow.began_at_profit_ended_below_cost = 1` to measure whether it earned its keep. Since the
    release 507 review an automatic profit sale may not accept under **95% of cost** (net of the selling fee) on a retry unless it is a
    real loss cut (`cutting`, with the normal loss guards): the profit floor `FLEX_COST_SHARE`. Otherwise a below-cost retry is
    governed by this rule, the 85% backstop, the guards, the daily limit and Pause.
  - It only ever loosens the old bar and never refuses something the old bar takes (beyond the backstop and the floors).
    **Fails closed:** anything missing or stale (no fresh score or book, a jumpy spread, a spread/total, same-game picks, no
    pick in play, any error) uses exactly the old bar. Switch off = decisions identical to develop.
  - Kept as they were: the daily cap (`auto_cap`), the per-position attempt cap, the 1.5x smart-sell floor setting, Pause,
    rule 8 (an unknown outcome stops everything), known-order outcome checks, and the 85% backstop. With the switch off, or
    stale/missing live info, today's cost floor for a profit-taking sale still applies exactly as before. No new fixed daily
    dollar cap was added (Pete: not needed). When a sale is taken under the first offer, its message says why;
    `CASH_LAST[...]["flex"]` and each try's `flex` hold the verdict.
  - `flex_shadow` (SQLite) records every retry decision: offer, first offer, current fair, usual value, wait value, backstop,
    chance now, mode, reason, accept, and what the old rule would have said. Bounded (20,000 rows), errors swallowed. No sale
    decision reads it; only the fallback learner below does (and it only nudges one share).
  - **Learned fallback share** (`flex_learn`, ON by default, Pete 2026-11-24). When live info is stale or missing, a retry
    must still reach a share of the first offer: 97% (`CASH_SLIP`) to start. `flex_fallback` learns it from this app's own
    record: `flex_shadow` retries joined to `sell_log` (what the position later sold for after a refused retry, or what
    holding paid after an accepted one; a combo cash-out carries no separate fee so the offer is the net cash). Needs 20
    comparable retries (`FLEX_FB_MIN_N`) before a move, moves at most one half-point (`FLEX_FB_STEP`) per hourly evaluation,
    lowers only when waiting lost more than 1% of the offers' value, raises when it gained more, is hard-bounded to 85%-99%
    (`_fb_ok`, so NaN, text or out-of-band values read as 97%), per league (ledger league) once a league has 20 retries else
    global, shrinks back at twice the step when lowering proved too cheap and snaps to 97% after 3 such rounds in a row. A
    learned share under 97% is never below the 85% backstop of what the combo last read as worth (fair value, no Kalshi
    discount). State lives in the `flex_learn` table. Any error or switch off = plain 97% (exactly develop's bar). Applies to
    the tap and loss-cut bar; an automatic profit sale's own bar is its smart-sell line (already tuned by `auto_slip`). The
    Settings row shows the learned value read-only (`flex_fb_view`).
  - Settings: `flex_sell` and `flex_learn` (default True) and `flex_backstop` (default 85), plumbed through DEFAULTS,
    SHARED_KEYS, WATCHER_SYNCED, the watcher's SYNCED and settings keys, the web app and the legacy settings page. Tests:
    `t_flexsell.py` (default on; fast-moving accept; profit not refused; below-cost end flagged, no Never exception; backstop
    refuses a spike; stale input falls back to 97%; OFF identical to develop; loss cut; Pause; rule 8; tap/auto parity;
    shadow errors) and `t_flexlearn.py` (sample threshold, step size, bounds, per-league, corrupt/NaN history, errors,
    streak).
- **The "Never sell at a loss" choice is removed (Pete's explicit decision; supersedes the Never wording elsewhere in this
  section).** Settings > Cash out > Selling at a loss now has two choices: **Let it tune itself** and **Allow (guarded)**. A
  saved `stop_loss_mode: "never"` (any device, an old settings file, an old phone or page) is read as **Let it tune itself**
  (`sl_norm`): migrate on read, no crash, never silently Allow. `sl_mode`, `sl_sync` (phone/web/watcher merge and save),
  `sl_allowed`, the auto cash-out loop and the singles loop all go through it; the web page shows it as Let it tune itself
  too. Gone with it: the auto cash-out cost floor passed for Never, the "skip a single with unknown cost / under cost after
  fee" check, and the flexible rule's Never floor. Below-cost sales are governed by the flexible rule, the 85% backstop, the
  guards, the daily limit and Pause. Untouched: the loss-cut trigger conditions, never at halftime/break/early game/stale
  score, the stop-loss's own guards and per-day limits, rule 8, Pause. Tests: `t_neverloss.py` (rewritten for the migration
  on every path), `t_settings`, `t_stoploss`, `t_knobpr567`, `t_flexsell`, `test_slmode_ui.py`.
- **Sell guards: under-hold note, shared tap marker, closed-bet cache (#244, #400, #407).** **#244, the under-hold note:**
  `single_sell_quote` adds a `{"k": "under"}` warning when a manual single sale brings less than holding is worth: "That's $X
  under what holding is worth (about $Y). You can still sell." `_sell_under_hold` uses smart sell's own hold value
  (`single_sell_reason`, `track=False`, records nothing), or chance x contracts with smart sell off, and says nothing when
  smart sell would sell the bet anyway. Display only: `clears`, `ok`, the checks in `single_sell` and Pete's tap are
  untouched; a failure in the helper is swallowed. **#400, one seller at a time:** the web app and the watcher are separate
  processes, so Pete's Cash out tap (`go` and `singlesell`) writes a short marker (`combo_manual_sell.json`,
  `manual_sell_mark`) and the automatic sellers (`auto_sell_now`, `smart_sell_singles`, `autosell_pass`) skip that bet while
  a fresh marker (under `MANUAL_SELL_MAX` = 90 s) stands, and check it again next round (a skip is logged). One direction
  only: the tap never reads or waits on the marker, a marker that cannot be written never holds the tap up, and a crashed
  tap's old marker counts for nothing. No new sale is made; an automatic sale only waits. **#407, closed-bet detail:**
  `api_closed` answers from a small per-ticker cache (20 s, 4 s for "not found", at most 64 entries) in front of
  `api_closed_work`, the original lookup, so a refreshing page does not rescan the sell log and hold the account lock per
  request. The ticker is checked before the cache. Same answers, fewer scans. Tests: `t_guards2.py`.
- **Learned selling guards (Settings > Cash out > "Let the selling guards learn", `learned_guards`; shared, ON by default,
  effective only with `knobs_live`; either off = exactly develop: same live set, 150 s, a break always blocks, nothing
  recorded).** Pete: "we're just making up rules that we should allow to have some level of learning." `guards_on()` is
  cached 10 s and fails closed. Converted, on the existing knob machinery (registry, weekly stepper, bootstrap bar, brake,
  `knob_shadow` move log, which now keeps 20000 rows via `KNOB_SHADOW_ROWS`):
  - **Score age** (`sl_feed_age`, start 150 s, band 90-300 s, step 30 s, shorter = stricter, per league else global; a global
    value is only borrowed when stricter). `feed_age_limit`, `fresh_live_score(loose=)`. Only a LOSS sale (`stop_loss_leg`)
    uses the learned tolerance; hedge and sell-more callers can only be stricter. Evidence: the bounded `feed_ep` table
    (`feed_note`, `feed_resolve`): a stale-score refusal with every other guard holding and a two-sided book is recorded (age
    90-300 s) and closed 10 minutes later with that later bid (dropped after 30 min). Judge `feed` (`_knob_res_feed`): net
    dollars after the single-leg fee, selling now versus the bid 10 minutes later. Min sample `FEED_MIN_N` 20. Loosening
    needs a seeded bootstrap lower bound above 0 (`_guard_bootstrap`); tightening uses the lighter `GUARD_TIGHT` bar.
  - **Halftime / break** (`brk_on`, `brk_move`, already in the registry as watch-only): `break_ok` may now open for a LOSS
    sale only (never a hedge), only on a league's own learned record (not borrowed), on a fresh two-sided book and two reads.
    `BRK_LIVE` stays False. Min sample `BRK_MIN_N` 40 (stricter than 20); judge is net of fees with guards on. The `break_ep`
    shadow table is bounded to `BRK_KEEP_ROWS` 5000. **Early in a game** (`sl_prog`): already learned by smart_tune and the
    stepper; no second mover added.
  - **Not converted (kept fixed):** Pause, the one-tap Sell, rule 8, no score at all / not in play / one-sided or empty book
    = no sale, the daily limit (PR #480 self-adjusts it), the 85% flex-sell backstop (follow-up). Other fixed sell-timing
    constants left as they are, each tied to data validity or already judged elsewhere: `swing_base`, `checkpoint_lam`,
    `cushion_*`, `hedge_gap`, `live_spread`, `BRK_READS`, `BRK_SPACE`, `sl_under` (judged by `_sl_replay`, not live), #479's
    8% drop, #480's `MORE_PROG_MIN` and `MORE_*` (follow-ups).
  - **Review fixes:** a below-cost sale never goes ahead while a better hedge is blocked by a stale score or a break (the
    wider learned age and the break rule open the loss sale only); a score older than 150 s (learned wider age) also needs a
    fresh two-sided book, since a break may hide inside the window; the break rule needs a falling price for a loss sale
    (live check and judge); junk `break_ep` rows are skipped. Known follow-ups: break evidence still includes picks the live
    rule would not act on (winners, above 50%), and episode counts are per pick, not per game. Behaviour notes: the global
    group can only tighten (chain-stricter borrowing); the feed evidence is a 10-minute-later proxy; the knob views list
    `sl_feed_age` as tunable even with the switch off (display only).
  - **Merge with #479/#480 (Pete, 2026-11-25).** The synced-settings lists are a union: `learned_guards` is in `SHARED_KEYS`,
    the engine's `WATCHER_SYNCED` and the watcher's `SYNCED` and `SET_KEYS`, beside `flex_*` and `sell_more_*`
    (`t_newkeys.py` checks every one, and the Settings screen). The retired "Never sell at a loss" choice reads as 'tune', so
    the Settings line always shows the guards' wording. Tests: `t_learnedguards.py` (sample threshold, bounds, step,
    bootstrap, NaN/corrupt fallback, switch-OFF identity, brake, break loss-only, Pause wins, manual Sell unaffected, bounded
    tables), `test_learnedguards_ui.py` (Settings, dark/light); `t_knobs`, `t_knobpr567` updated.
- **Smart sell more (Pete's opt-in, 2026-11-24; default-ON on purpose).** Pete explicitly opted in to smart sell acting more
  with real money, so the two switches (`sell_more_cheap`, `sell_more_loss`) are **ON by default** and live in Settings >
  Cash out so he can turn either off. Everything is additive: it is only looked at where smart sell's own rule already said
  "hold", so with both switches off every decision is exactly develop's (`t_sellmore.py` proves it). Pete's opt-in is
  recorded here, not elsewhere.
  - **A, a lower profit floor for cheaper singles (`sell_more_cheap`).** A single bought under 60c a contract (entry price,
    `MORE_UNDER`) may sell at 1.35x what was paid (`MORE_FLOOR`) instead of its league's learned floor, never above that
    league floor and never under smart sell's 1.2x bound. Everything else in `exit_policy` still has to hold: the
    risk-adjusted hold-value comparison, chance of winning at least 0.5, spread within `LIVE_SPREAD` (6c), no resting sell, a
    known last order, whole contracts.
  - **B, an earlier loss cut on a clearly sliding single (`sell_more_loss`).** A league with no learned loss cut yet (smart
    sell needs 30 settled bets per league) gets a stand-in cut-off of 15% (`MORE_LOSS`, the self-tuner's first value). It
    keeps every loss guard: a fresh score, game at least half played, a big fall below the pregame chance, never at a
    halftime or break, 3+ confirming checks over 3+ minutes (counted under its own key `cutB:`, never the real loss cut's),
    never below 97% of the bid. Skipped where the league's self-tuning brake is holding, and wherever the league already has
    its own learned cut-off (that one wins). **No longer skipped in "Never sell at a loss" mode (Pete, 2026-11-25):** that
    choice was retired by Flexible sell (#479; a saved 'never' now reads as 'tune'), so anyone who had it saved becomes
    eligible for A's below-cost sales and B's loss cuts, still bounded by the daily dollar limit and every other guard.
  - **Freshness, fail closed.** Neither path ever compares against a stale reference (a sportsbook line, a pre-game number
    that hasn't moved). `more_fresh` requires: the market's own Kalshi fetch no older than 120 s (`MORE_AGE`, stamped per
    market in `SINGLES["mk_at"]`; an old fallback copy has no stamp), a two-sided bid and ask within the spread limit (no
    last-price-only or one-sided book), the game in play, and a score feed under 150 s old. The chance used is that book's
    middle, recomputed on the spot. Any missing means no sale. (B's existing pre-game drop guard still compares to a pre-game
    chance as an extra restriction; B's trigger itself is live-only.)
  - **Self-adjusting daily limit (replaces a fixed cap).** Both paths share one dollar limit on what they may sell in a day
    (`more_limit`, `more_cap_blocks`). It starts at the Settings number (`sell_more_cap`, $50) and moves by a written rule,
    from the record alone with no network: each smart-sell-more sale whose game is over (the history file's
    `sell_log.outcome`/`held`, filled by `sale_outcomes`) is compared with what holding would have paid, net of the sale's
    fee. Nothing moves until 20 such sales have finished games (`MORE_MIN_N`). Then after every 10 more, over the last 20:
    beat holding by more than $1 means +25%, at most weekly and never over 4x the start; worse than holding means halved,
    never under 20% of the start. Brake: 4 sales in a row worse than holding, or the last 30 days $25 under holding, pauses
    both for 7 days; after that it restarts at the smallest limit and must earn its way back (nothing carries over). Same
    record always gives the same limit. State is `combo_more.json`; an unreadable record uses it, else the smallest limit
    (never the start, never unlimited). Settings shows today's limit, what is used and why (`more_view`). The existing
    `auto_cap`, Pause (re-read right before the order), rule 8 (an unknown order outcome means "check", never retried) and
    the whole-contract guard all still apply.
  - **Recording.** Every pass writes the `more_shadow` table per held single (bounded: 60 days / 200k rows, 60 s per ticker,
    errors swallowed, off the trading path, never read by a decision); a sale is a `log_decision` line tagged `more` (A/B)
    with its after-fee net, so net dollars after fees versus hold can be measured. **Registry.** KNOBS entries
    `sell_more_start`, `sell_more_floor`, `sell_more_loss`, `sell_more_age` (invariant, with their source constants); the
    keys are in `SHARED_KEYS`, the engine's `WATCHER_SYNCED` and the watcher's `SET_KEYS` and `SYNCED` (Pete, 2026-11-25: a
    dropped key means the Settings switch never reaches the engine; `t_newkeys.py` checks every new sell key is in all of
    them and on the Settings screen).
  - **Ambiguities.** "Under about 60c" is read as the entry price per contract. A works only in play with a fresh score. B is
    roughly neutral by construction (selling at about 15c against about a 15% chance), so the shadow record is how it gets
    judged. Tests: `t_sellmore.py` (defaults, off = develop, A/B, stale blocks, Pause, rule 8, a saved 'never' no longer
    blocking, whole contracts, a real sale tagged `more` and counted by the daily dollar limit, limit grow/shrink/minimum
    sample/brake, shadow table unread), plus `t_knobs.py`'s allow-list.

#### Ask Kalshi for a real offer when an estimate reaches the bar (issue #227)

When an estimate-driven plan SELL or smart-sell trigger fires in `auto_sell_now`, auto cash-out may ask Kalshi for a
REAL combo offer (`get_cash_offer`). It sells **only** if that real offer meets the same bar as any real offer: the
`exit_policy` bar, 97% of the line (`AUTO_CASH_SLIP`) on a fresh quote, and the below-cost skip (stricter than the
`FLEX_COST_SHARE` 95% floor) unless it is a real loss cut. **Never on the estimate alone.** The manual Sell tap is untouched.

- **Throttle** (`real_ask_gate(t, exempt=)`, state `MINE["real_asks"]`, noted by `real_ask_note(t)` and
  `real_ask_result(t, cleared)`): at most one request per combo per `REAL_ASK_GAP` (60 s), `REAL_ASK_HOUR_COMBO` (20) a
  combo and `REAL_ASK_HOUR_ALL` (60) in all per hour (all per process, in memory). **Back-off:** a combo whose last real
  offer came in under the bar (or none came) waits 60, 120, 240, 480 then `REAL_ASK_BACKOFF_MAX` (600) s between asks
  (about 9 asks an hour); an offer that clears the bar resets it. Three stuck combos therefore cannot use up the overall
  budget. **Exempt:** lock-in and a guarded stop-loss (`sl_ready`) only ever wait the plain 60 s gap: no back-off, no
  per-combo hourly cap, no all-combos cap (a stop-loss never waits minutes); an exempt ask never lengthens the back-off.
  Unreadable state fails closed (no request). Ask history, back-off and told-notes of combos no longer held are pruned
  each pass (`real_ask_prune`). Learned loss cuts ("cut loss") bypass the
  gate on purpose, so the #396 clock-retry behaviour is unchanged.
- **Log:** every request and outcome is a `log_decision` line: "REAL OFFER asked (...): got $X, bar $Y, ..." and, when the
  gate refuses, "REAL OFFER not asked: ...; the estimate (...) never sells on its own" (one per combo per 300 s).
- **Switch off (`real_offer_ask` false) is stricter than before the switch:** automatic selling never asks Kalshi for
  an offer; it sells only on a real offer already in hand that clears the bar (so a plan part-sale waits too). Kept on purpose
  (the safe direction); a learned loss cut still asks. The Settings text says so in plain English.
- **Card wording (#513):** the card reads the throttle read-only (`real_ask_gate(..., readonly=True)`, no state change, same
  exemption via the `MINE["sl_ready"]` copy that `auto_sell_now` keeps); while throttled it says "holding off asking Kalshi". `smart_trigger` keeps "will ask Kalshi for a real offer once the estimate reaches $X"; with the
  switch off it says "won't ask Kalshi (switched off)".
- **Untouched:** Pause (read first; unreadable = nothing), rule 8 (`rfq_unsure`), no live data = no sale, the daily cap,
  accept path, hedges.
- Test: `t_realoffer_227.py` (includes the drain case: 3 stuck combos, a 4th still gets its ask).
- **Error-dict stored offer (#514):** when Kalshi answered a real-offer ask with "no offers", the stored offer was an error
  dict with no `offer` key, and the next `auto_sell_now` pass raised `KeyError: 'offer'` (the "REAL OFFER not asked" note
  and the estimate-vs-bar checks) and aborted the whole pass, stop-loss included. A stored offer without a numeric `offer`
  is now treated as the plain estimate (the same as no offer stored): it can never sell, the throttle and Pause / Rule 8
  checks still apply, and the pass carries on to the next combo. No new automatic sale paths. Test:
  `t_offer_keyerror.py` (an error-dict combo first, then a cut-loss combo and a normal estimate combo).

#### Momentum shadow recorder and the real smart-sell trigger on combo cards

First deliverable of `momentum-exit-design.md` section 5. **Nothing here sells or buys.** It records and explains.

- **Recorder (`mom_record`, tables `mom_shadow`, `mom_after`, `mom_peak`).** Called once at the end of `take_profit_reason`
  (combos) and `single_sell_reason` (singles, live pass only: `track=True`, no `more`, no `cap`), each time inside its own
  try/except, with numbers the exit rule had already worked out. It never changes a return value. One `mom_shadow` row per
  evaluation when any verdict changes, else every 120 s per bet: win chance q, its high over the last 10 min, the drop
  `dq`, a placeholder `sigma` (0.05, nothing learned yet) and `z = -dq / sigma`, the real offer net of fees, the steady
  estimate, quote age, cost, payout, the peak, today's decision / reason / line, a plain `why_not` (`q<50%`,
  `no real quote`, `below floor`, `peak<arm`, `no live data`, `smart sell off`), two HYPOTHETICAL verdicts and the Pause
  flag (recorded only). Hypothetical `m_protect`: real offer, `z >= 2.0`, offer >= cost - 5% of cost, holding worth
  <= offer x 1.10. `m_cut`: stricter (`z >= 2.5`), holding worth less than the offer, offer >= 30% of cost.
  `mom_after` is opened for rows where something fired and fills the offer at +30 s, +1, +5, +15, +60 min (from the first
  evaluation after each time) and the lowest seen; `mom_settle` (from `live_view`, once per bet per run) adds the
  outcome (`won`, `lost`, `cashed`) and payout. `mom_peak` keeps each bet's peak so a restart does not lose it; it is
  reloaded only into the recorder's own dict, never into `MINE["peak"]`.
- **Bounds.** Setting `mom_shadow` (default ON for recording; false = off; a plain DEFAULTS key like `sig_shadow`, not in
  `SHARED_KEYS` or the watcher list). Throttled, 100k-row cap, 60-day prune (every 6 h), every error swallowed through
  `console_note`. Pause, rule 8 and the no-live-data guards are untouched: nothing in the recorder places an order.
- **Log lines (console).** `MOMENTUM would sell <ticker> rule=protect z=2.4 q 61%->44% offer net $4.91 vs cost $4.99
  (today: hold, q<50%)` once per episode; `NO SELL <ticker>: blocked by <q below 50% | offer under floor $X | lock-in not
  armed (peak $Y < $Z) | no real quote | no live data>` every 10 min per live position.
- **Off the sell path.** `mom_record` does only in-memory work and appends the DB writes to a bounded queue; a daemon
  thread (`mom-shadow-writer`) writes them, and the prune runs there too. Errors are swallowed. Each row carries a process
  tag (`main` / `web`) and a `sid` dedupe key (`proc:ms:ticker`), so the web app and the watcher never double-write.
  `MOM["pend"]` entries expire (about 90 min), are capped (400), `mom_after` has a `ts` index and a row cap, and a bet's
  peak is reset when its cost changes or it has not been seen for 6 h (a re-bought single does not inherit the old peak);
  `mom_settle` removes its `mom_peak` row. `why_not` judges a combo on the better of estimate and gross offer, a single on
  the net offer, and uses the tuned `q_min`.
- **Combo cards.** `smart_trigger(t, h)` (display only) adds `smart_at`, `smart_over`, `smart_txt`, `smart_chip`,
  `smart_state`, `lock_at`. It says "should sell on the next check" only when Auto cash-out is on and nothing blocks it
  (`auto_sell_blockers`: Pause, daily limit, "I'll sell it", Kalshi refusing sales, unclear last sale, cannot trade here);
  otherwise it says why it won't sell right now, and shows nothing when Auto cash-out is off or the bet is "I'll sell it".
  The old let-it-ride number is relabelled **Let-it-ride line**. Lock in reads "Protects a profit once the offer has
  reached $X."
- **Tests.** `t_mom_shadow.py` (synthetic DB: rows written, a failing recorder changes nothing for selling, log lines,
  kill switch, throttle, pruning, nothing reads the tables back, card text).

#### Money-guard batch: fee-aware "profit" (#432) and Combo Buy legs re-check gaps (#498)

Three small safety tightenings. Each makes the app do less; nothing new buys or sells, and Pause, caps, quarter Kelly and
rule 8 are untouched.

- **#432, "a profit" is after the selling fee.** The auto cash-out cost floor was already net of the fee on the first
  offer (`auto_sell_now`, `combo_sale_net`) and on a retry (`FLEX_COST_SHARE`, 95% of cost net). Two places still said
  "at or above cost" on the gross offer. `flex_decide` now judges its `profit` flag on `min(offer, net)` (net passed by
  `_accept_with_retries`; with no net passed, a manual tap, it is the offer as before; a NaN or unreadable net is never "a profit": that yes is refused), so a retry that nets under cost
  can no longer be taken as "a profit, and the chance has dropped". `cash_nudge` (alert only, never sells) stays quiet
  when the offer nets under cost. `combo_sell_fee` still switches the fee model off (then net = gross). Singles already net
  the fee (`single_sell_reason`).
- **#498 (1), sent-but-empty legs list.** `accept_offer(..., legs_sent_empty=True)` / `buy_legs_refusal(sent_empty=True)`
  refuse with "the page sent an empty legs list" (nothing sent, offer kept). The web app's Buy sets it when the page's `legs`
  key is a list with nothing in it. A page that sends no `legs` key at all (an older page or a hand-made post; longshots.js always sends real tickers) is
  unchanged: still held to offer = card.
- **#498 (2), hub build-form Buy.** The hub's `/simple` Build form now carries the card's leg tickers in a hidden `legs`
  field; `builder.buy(i, legs)` refuses a Buy with no legs ("That page is out of date ... Nothing was bought") and passes
  them to `accept_offer(expect_legs=...)`, which checks them against the stored offer and the combo now on that card
  (hard rule 7). An old page open across the upgrade just has to be reloaded.
- **Skipped on purpose (commented on the issues):** #365 (a per-game overlap skip on killer, standing orders and the
  panel changes which automatic buys happen and needs Pete's thresholds), #328 (no real combo fee data: no ledger on this
  machine to read, and guessing a fee would change sizing).
- Test: `t_money_guards.py` (synthetic engine, faked Kalshi). Existing `t_buy_legs_203`, `t_flexcostfloor`, `t_combofee`,
  `t_cashnudge` still hold.

#### Do-now batch A: small safety and docs tidy-ups (no display change, no money logic)

- **#458 (hub write ids).** The phone-to-Mac hub no longer accepts an id made only of dots (for example
  `DELETE /portfolio/orders/.`). Real ids that contain dots still work. Refs #458.
- **#457 (money stamp).** Failed cash-outs with no bet id no longer share one key, so two different failures cannot hide
  each other's "money moved" stamp for a minute. The `money_note` double-stamp half is not changed. Refs #457.
- **#434 (Pause read).** If the Pause read fails, the app still treats it as paused (nothing sells or buys by itself), and
  now prints one plain console line, at most once a minute. Refs #434.
- **#441 (exit replay one-liner).** `docs/EXIT_REPLAY.md` now downloads a fixed commit of the script and checks its
  fingerprint before running it; a test keeps the doc in step with the script. Refs #441.

#### Combo trail: a read-only tool that traces what happened to a team's combos

`tools/combo_trail.py` answers "why did that combo ride to settlement?" without touching anything. Run from the app folder:

    python3 tools/combo_trail.py --team nuggets --date 2026-11-23

- Finds every combo or single whose legs name the team (case-insensitive; names are decoded from the leg tickers using the
  engine's own team tables) within 2 days of the date.
- Prints legs by name, cost, payout, when bought; a timeline of at most ~60 lines (combo chance, Kalshi offer real vs
  estimate, the smart-sell line when logged, every auto-sell decision with its reason and the Let-it-ride setting, the
  result); then peak offer vs cost vs sell line. Also saved to `~/combo_trail_summary.txt` (`--out` to change).
- Reads `combo_history.db` (sqlite `mode=ro`) and `combo_autosell_log.jsonl` (where skips and their reasons live; only
  sales are in the database). No network, no Kalshi keys, never starts the watcher, never writes. Only a fixed list of
  fields is printed: no tokens, keys, order ids or balances. Missing tables or files print a "skipped:" line.
- The decision log names combos only as "Combo N"; the tool prints that name next to the legs so the two can be matched.
- Test: `tests/suite/t_combo_trail.py`. No trading logic is touched.
- Importable: `build_report(db, log, team, day)` takes any open sqlite connection plus the decision-log records, so a remote read-only front end can reuse it; the local command stays as a fallback.

#### Wider log and data access for the dev Mac (follow-up to #377)

- **Console log 503 fixed.** The scrubber rebuilt URLs with a parser that raises on a malformed URL (and, on newer Pythons, on its
  own `https://[host]` placeholder), which failed the whole answer. URL handling is now regex-only, scrubbing is idempotent, and one
  bad line is withheld on its own.
- **Only credentials are scrubbed now.** API keys, tokens, private keys, auth headers and passwords are masked and the answer still
  fails closed on them. Team names, tickers, prices, balances, outcomes, emails and hostnames are kept.
- **Auto cash-out records name the legs** (`picks`) instead of only "Combo N".
- **Read-only data window** (`source=db`): SELECT-only questions about the collected data over the same endpoint, same code, same
  Tailscale-only reach, same "Let the dev Mac read logs" switch. Client: `tools/read_prod_logs.py --source db --table X --since ...`
  or `--sql`. The database file is never sent.
- Settings sheet wording: plain English, no Terminal steps.
- CLAUDE.md hard rule 9 reworded: query results over the endpoint are allowed; the database file, key and `~/combowatch` are not.
- **Money follow-ups from the independent review (#499, #500, #496; nothing loosens a guard).** `flex_fb_events` returns ONE entry per sale (its
  first comparable retry, stamped with the sale's last retry time), so the learned fallback share (`FLEX_FB_MIN_N` = 20) needs 20 different sales,
  not 20 retries; the per-league pre-check counts distinct positions too (`t_flexlearn.py`). `book_depth_shared` (a fetch at most 3 s old, else
  fresh) serves the two selling-guard reads (`break_ok`, the learned score-age check); `max_age=0` stays a truly fresh read for every buy, sale
  and hedge check (`t_bookshare.py`). `ledger_price_paid` with no saved `unit_cost` is `(cost - sell_fees) / n_bought` (display only;
  `t_storecounts.py` C3b). #498 was already done by #515. #501 (learn the loss-cut clock cadence) skipped: bounds not agreed, no evidence.
- **Money batch D (#421, #452, #450; no new switch).** `autosell_pass` (standing take-profit, dormant while `RESTING_SELLS_OK` is False) returns
  at once when `trading_paused()` (unreadable = paused); Pete's Cash out taps do not use it. `order_legacy_body` keeps the forced `reduce_only` for
  a sell intent (#443). `fetch_account(max_age=0)` sends `fresh` so the hub's `account` op skips its 3 s `HUB_FRESH_FLOOR` and reads
  Kalshi once; other `max_age` values are unchanged (#271), an older watcher ignores the key. Test: `t_money_d.py`.

## Product notes (moved here from CLAUDE.md)

Log access for the dev Mac (#377; hard rule 9). The watcher hub answers `GET /api/logs?source=console|autosell&since=&limit=`
with a redacted tail of `watcher.log` or `combo_autosell_log.jsonl` plus a status line (versions, uptime, Pause, role, auto
cash-out on/off). Off by default; Settings › This Mac › "Let the dev Mac read logs" (only on the Mac itself, `mac_settings` action
`logaccess` → `log_access_set`) makes a `secrets.token_urlsafe(32)` code shown once and stores only its SHA-256 in `watcher.json`
(`log_access`). Gates in order: on + tailnet only (`log_client_ok`: 100.64/10, fd7a:115c:a1e0::/48, the Mac itself, Tailscale serve
with a user; LAN and Funnel refused) → 404; `LogGate` 30/min per client, 5 wrong codes per client / 30 overall per 10 min → 429;
Bearer only, `hmac.compare_digest` on the hash → 401; bad params → 400; any read or redaction error, or a live secret surviving
(`LogLeak` tripwire) → 503 with an empty body. POST → 405 with `Allow: GET` while on, 404 while off. Caps: 200 lines default, 500
max, 200 KB, last 1.5 MB of a file, 2000 chars a line. Scrubbing is for credentials only (`log_redact`, `log_fields`; control and zero-width characters
stripped first, patterns bounded against huge lines): live secret values (and their URL/JSON forms), PEM blocks (any case), auth
headers, JWTs, the `cw` cookie, credential-named `key=value`/JSON pairs, `user:pass@` and secret query values, long random strings.
Ordinary content (team names, tickers, prices, balances, emails, IPs, hostnames) is kept. It is idempotent and regex-only, and one line that
cannot be scrubbed is withheld on its own (`log_safe`) instead of failing the answer (the old 503 came from `urlsplit` raising on a
malformed URL); `log_tripwire` is the last check. Autosell records keep every field except credential-named ones and carry `picks` (leg names).
`source=db` (`log_db_answer`): `tables=1`, `table=X[&since=]` or `sql=<one SELECT>`; fresh `mode=ro` connection, `query_only`, authorizer
(SELECT/READ only, function allowlist, no `pragma_*`), 5 s deadline, 1000 rows, 1.5 MB, one query at a time (429); credential-named columns
masked, blobs not sent; a bad question is a 400 with a short JSON reason. It never takes a lock and never touches a money path; Pause, the Pi and rule 8 are unaffected. Tests: `t_logs_redact.py`,
`t_logs_failclosed.py`, `t_logs_auth.py`, `t_logs_readonly.py`, `t_logs_caps.py`, `t_logs_allowlist.py`, `t_logs_default_off.py`.


Data window hardening: credential-named columns read as NULL (authorizer), rows read one at a time with a byte budget, 64 KB value limit, sql= refused when SQLite limits are unavailable, no printf/format/replace/char/hex/quote; web-push endpoint URLs, topic and endpoint values are masked. The column mask is best-effort (shape-based).

### Live page
- **Buy idea cards say which game they are for (GitHub #129, display only).** `live_suggestions` adds, per idea, `league_name`,
  `icon`, `legs_info` (per leg: matchup "Away at Home" / "A vs B" when home and away aren't known, plain pick "wins by 8 or
  more" / "Over 7.5 total goals", start time or the cached live score, `live`) and `chance`/`price_c`/`fair_c`/`edge`/`profit`
  (all from the idea's own stake, pays and pct: chance = stake·pct/pays, profit = stake·(pct−1)). `store_suggestion` saves the
  per-leg facts in `suggestions.info`; older ideas are worked out from their tickers (`idea_describe`, `idea_legs_info`,
  `_idea_matchup`, `_idea_plain`); nothing is fetched, and an unknown field is left out. A single's card body opens its game
  page (`ideaOpen`); a combo's leg rows open their games. A game you hold nothing on gets its page from the idea
  (`idea_game_leg`, only games named by a current idea). Tests: `t_ideacards.py`, `test_ideacards.py`.
- Hero card: worth now if sold (rolling number), change vs what's in, a profit/loss chart,
  riding / staked / chance one pays / most it can pay — covering combos **and** singles/spreads.
- Hero chart (`heroChart`/`wireChart`, issue #221): plots **profit and loss**, not worth. Day (16 h, `pnl` in
  `/app/api/live`) or Week (`/app/api/pulse?h=168` → `pnl`; read-only, pulse keeps 30 days) via a plain-text switcher
  (remembered, `cw_rng`). The engine's `pnl_series` (display only, cached 20 s, never raises, writes nothing) builds it:
  P/L(t) = (worth − cost of open bets) + (back − cost of bets that finished in the window: `ledger`, then `bets` for a
  combo the ledger lacks) − the open-bet sum at the window's start, so the window starts at $0, a bet bought in it counts
  from what was paid, a bet **already open at the start counts from its worth then** (the legend says so), and a bet
  leaving moves the line only by what it brought back beyond its last worth. A finished bet's cash is placed at the
  first pulse row (≤ 15 min after Kalshi's time) where its stake left the open list. `record_view` also writes
  `pulse_more(ts, xworth, xcost)` (a separate table so older 3-value inserts keep working): singles whose game is
  over but Kalshi hasn't paid (`_limbo_worth`: payout if decided, else bid, else cost), and one 0/0 row once nothing
  is open (the line then runs flat to now). Rows from before `pulse_more` make the chart say "Rough before <time>"
  (a finished single may dip until its payout lands). Partial cash-outs show only when the bet finishes. Drawn as a
  flat zero line, green above / red below (one gradient split at zero), the glowing end dot, and what was staked as a
  faint stepped band on its own scale. Press and drag to scrub: line and dot follow the finger, the readout shows
  "+$3.20 · $18 staked · 2:40 PM", each point ticks a haptic; the big "worth now if sold" number and its pill never
  change. Live refreshes wait while a finger is on it (`S.scrub`). Tests: `t_heropnl`, `test_heropnl`, `test_motion`.
- Combos table, "Single bets & spreads" section (tap opens the game page: score, chance it covers, your bets on
  that game), Settled view with profit/loss pills, outcome/sport/sort filters and a net total. Offer and chance
  numbers roll frame by frame to new values and the chance bars slide (`rollNums`, `data-num`/`data-bar`).
- **Sell a single by hand (GitHub #238; Pete's tap only, no new automatic selling).** Single bets/spreads/totals never
  had a manual Sell (only smart sell sold them). Each open card on Live › Single bets & spreads (and the game page's
  "Your bets") now has **Get new price** (`sellquote`: `single_sell_quote` reads the book with `book_depth(max_age=0)`,
  updates Worth now and shows what selling gets after the fee) and **Sell** (`watcher/spa/sell_single.js`: a sheet with
  the bid, what comes back, profit, holding's chance, warnings; two taps; `soldSheet` on success). `single_sell` (act
  `singlesell`, in `ORDER_ACTS`) uses the quote once (20 s, `_SQ`, a sell quote can never buy), works while paused (#245, below), refuses with no trading access, the unknown-outcome block or a lower bid on a fresh re-read, needs Sell anyway when the gap is over
  6¢, then one IOC reduce-only sale at the quoted bid (`sell_single_now`, `cw-ss-<quote>`); unclear = "check", blocked,
  never resent. Not logged in the sell log (that counts automatic cash-outs toward the daily cap). Totals' "On track"
  now follows the pace (`_single_how`: total so far over the share played), not the running total. Tests:
  `t_singlesell`, `test_singlesell_ui`.
- **Pete's own single-bet Sell works while paused (issue #245).**
  Pete's decision (2026-11-21, answering #245): Pause stops everything automatic and every buy, but it must not block his
  own tap that closes a position he already holds. So the manual single-bet Sell (Live's single cards and the game page:
  "Get new price" and "Sell", web app acts `sellquote` / `singlesell`, engine `single_sell_quote` / `single_sell`) no
  longer refuses while paused: the Pause refusal before the quote, the one after the quote and the re-read before the
  order are gone (`SELL_PAUSE_MSG` removed). `paused` is still passed in, only to add the sheet's calm grey line
  (`paused`/`paused_note` on the quote, `SELL_PAUSED_NOTE`: "Pause is on. This is your own sale, so it still works.",
  `.sbw.sbcalm` in `sell_single.css`, not a warning) and to note "while Pause is on (your own tap, #245)" in the log.
  Every other guard is unchanged: trading access (`can_trade()`; the Pi never trades, and both web app acts now also
  refuse first on `backup_now()`, the device's role read fresh, an unreadable settings file counting as the backup, since
  `paused_now()` used to cover that), the unknown-outcome block, one order per fresh 20 s quote, one IOC reduce-only order
  at the quoted bid, a lower bid on the fresh re-read refused, a gap over 6¢ needs Sell anyway, an unclear answer is
  "check", blocked and never resent (rule 8).
  Combo cash-out taps were checked and left alone: the web app's `go` / `ask` / `askhalf` / `keep` (`cash_action` ->
  `accept_cash`) never read Pause, so Pete's own combo cash-out already worked while paused; this change makes singles
  consistent with it, and `t_combosell_paused.py` locks the combo side in (including the unknown-outcome block, rule 8). One
  tightening: `auto_sell_now` (auto cash-out, smart sell, the singles pass) now also returns at once when Pause reads as on,
  instead of relying only on the settings flag the watcher flips; no automatic path was loosened and buys are unchanged. The
  manual **Hedge** tap (`hedgego` -> `place_hedge`) also doesn't read Pause, although a hedge is a
  buy: left as it was (out of scope here), flagged on the PR for Pete. Still stopped by Pause (tested): auto cash-out,
  smart sell (combos and singles), the learned loss cut and auto-hedge (`pause()` turns `auto_sell` off and
  `auto_sell_now` does nothing without it), killer deals and standing orders, the panel's buys, the combo quote/idea/Buy,
  Buy straight (`single_buy_quote` / `single_buy`), Live idea single buys (`idea_single_buy`), `accept_offer`, pot moves.
  Tests: `t_singlesell.py` (section 3 now asserts the sale works under Pause, including Pause turning on mid-sale and an
  unreadable Pause, with every other guard still holding; 3b asserts the buys and automatic sales still refuse under
  Pause; section 7 the Pi check in both acts), `test_singlesell_ui.py` (the calm note, a green Sell, one send while
  paused), `t_safety.py` unchanged.
- Game and combo detail pages **push** in Kalshi-style (`pushOpen`/`pushFill`): the page slides in from the right in
  270 ms (ease-out) while the page behind slides a third left and dims; flat skeleton blocks show until the content
  swaps in (never before the slide ends), then the content fades/staggers in. A sticky Back bar, or swipe right,
  goes back. Confirmations stay as bottom sheets (`modal()`); switching modes never animates a half-moved sheet.
- Loading shows a hero-shaped skeleton; an empty Live says "Nothing riding right now" with a button to today's bets.
- Pull to refresh, score-change row flashes, celebrations when a bet wins.
- **Score/swing alert wording (issue #324, text only):** `record_view`'s score, lead-change and swing events name the
  pick through `alert_pick(lg)` (kind, me, opp): the team from the score's own side (`sc.abbr`), else the ticker's team
  code, else the words before "wins by"/"to win" (never the last word of a bet description; the old `short_name` is
  gone); a spread adds its line ("Jets score against your Chargers (-2.5)"), a total says "Score! 13 total so far, your
  Over 47.5" (good for an Over, bad for an Under; no lead-change alert), swings say "to cover"/"to hit"/"to win".
  Ticks, plays and every buy/sell/pick_state path are untouched. Test: `t_alertwords`.
- **When a game starts (issue #223).** `game_start(event, ticker, exp)` → (time, source), in order of trust: the
  sportsbooks' kickoff (`KICKOFF`, a spread/total uses its game's), the score feed's scheduled start for that exact game
  (`feed_game`: ESPN / the AHL feed, cached scores only, memoised per score refresh in `FEED_MEMO`; ESPN's
  `timeValid: false` "TBD" dates ignored), then the old estimate (Kalshi's `expected_expiration_time` minus the sport's
  hours). Kalshi's expected settle time is a placeholder for many college football games (23:00 UTC for most of a
  Saturday's slate, noon and night kickoffs alike), so the estimate alone put Kentucky at Missouri five hours early.
  `start_dt`, `leg_start` and `started` all use it; `started` is also True whenever the feed shows the game in play or
  over. `EVENT_TICK` (filled in `week_games`/`fetch_results`) finds a game's market from its event code. Pre-game panel
  buys still need the sportsbooks' kickoff (`_kick_ts`) and live-priced ones a fresh in-play score (`live_side_fair`),
  so a wrong estimate never bought anything. Test: `t_gamestart` (fixture `game_start_223.json`, real shapes).
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
- **Live and Results catch up right after a sale (issue #242, display and caches only).** A sale is made by the Mac
  watcher, but the pages are drawn by the web app with its own caches (account 60 s/30 s, open singles 30 s, the Live
  snapshot, `profit_board` 2 min, the hero's profit line `PNL` 20 s), so a sold bet could stay on Live for over a minute
  and Results never refreshed by itself. Now the engine's `money_mark()` writes a small stamp, `combo_money.json` next
  to the engine (git-ignored by `combo_*.json`; only its time matters, `money_seen()`), for every sale-type sell-log line
  (`log_decision`: sold, hedged, check, failed, hedge check/failed) and, after every direct account read, when anything a
  screen shows changed (`money_note`: a combo's status/cost/back/pays, any position, the balance; a process's first read
  only remembers). It never raises and never waits (one small file write), so the trading loop is never held up. The
  hub's `account` op reads Kalshi fresh (`max_age=0`) when the stamp is newer than its cached copy; the web app's
  `money_check()` (one file stat) drops its account, singles, scoreboard and profit-line caches when the stamp moves;
  `api_live` rebuilds when the stamp is newer than the moment the snapshot on hand began (`LIVE["from"]`), the warmer
  does it ahead of an open page, and `api_results` checks it first. Each Mac tick carries the stamp (`{"kind": "tick",
  "money": ...}`); `moneyTick` re-reads Live/Games and Results when it moves (a finger on a chart or an open sheet waits
  for the next tick); a Sold moment for a Mac sale re-reads Live 3 s later (`soldReload`). Nothing here buys, sells or
  decides; `analytics()` (10 min) is unchanged. Tests: `t_moneyflag.py`, `test_moneyrefresh.py`.
  **No stamp from incomplete reads, and a floor on forced fresh reads (issue #271; display only, nothing that buys, sells
  or sizes reads the stamp).** `money_note(bets, positions, balance, incomplete=0)`: `_fetch_account` counts combos left
  out because their legs couldn't be read (`unread`). An incomplete read no longer compares or updates the combo
  fingerprint (a combo dropping out then coming back used to stamp twice), but it still compares positions + balance
  (`MONEY_FP["pb"]`), so a real sale or balance change still stamps. The skip is logged once per change ("money stamp
  skipped: N combo(s) couldn't be read"). `log_decision`: a plain `failed` / `hedge failed` cash-out on the same bet stamps
  at most once per `MONEY_FAIL_GAP` (60 s), so a loop logging a failure each pass stops forcing a fresh account read each
  pass; `sold`, `hedged`, `check` and `hedge check` (money may have moved) always stamp, and retry logic is untouched. The
  hub `account` op's forced fresh read (`max_age=0`) now needs the cached copy to be older than `HUB_FRESH_FLOOR` (3 s);
  when held back, the reply carries `held_back: true` and the hub logs why. The web app uses that copy but does not keep it
  as fresh (`ACCT_CACHE["at"]=0`), so the very next call asks again and gets the fresh read: a displayed balance is never
  cached stale because of the floor. The watcher's own `fetch_account(max_age=0)` calls (pre-trade checks) are unchanged.
  Test: `t_moneyflag.py`.
- **Live football game page (GitHub #72, display only).** On a live NFL/college-football game sheet the engine's
  `game_detail` (one ESPN summary fetch, cached 6 s; `_parse_game_detail`, `_situation_info`) feeds `api_game`'s `detail`
  block: the field strip (`fieldStrip`: ball, first-down line, red zone, possession arrow; everything inside `.grass` is
  positioned in % of the grass box = yards from the left goal line), the situation line, the last play and the scoreboard's
  timeout dots and possession ball. Slice 2 adds `detail.pbp` (`_parse_pbp`/`_pbp_play`: ESPN `drives.previous[]` + `current`,
  at most `PBP_MAX_PLAYS` newest plays, short keys) and a generic **game-page tab framework** in the SPA (`GAME_TABS`: a per-sport
  list of `{k, l, has(r), html(r, ov)}`; football = Overview + Play-by-play; a sport with no spec, or a tab whose data is missing,
  shows no tab row and the page is as before; the chosen tab, stepped play and collapsed sections live in `S.gtab`/`S.pbpStep`/
  `S.pbpOpen` and survive the 2 s redraws; a redraw puts the tab row back where the finger left it and only scrolls to the chosen tab when the tab changes, and no redraw happens while a finger is on the row or for 0.5 s after it glides, `gtabHeld`, #218). The Play-by-play tab has a latest-play card with prev/next stepping (the strip shows
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
  ESPN, never through the hub's warm cache; **nothing waits for them**: the first open returns at once with `detail.gxp`
  (still fetching) and the page shows skeletons on Last 5 / Season leaders, re-polls in ~2.5 s and fills them in quietly;
  `gxp` ends after `GX_PENDING_MAX` 45 s so a fetch that never lands cannot leave a skeleton forever; a caller may still pass
  `budget` to wait). **Warm-up (`game_prefetch`, route `/app/api/game_warm`):** the Games tab asks the Mac to warm a LIVE
  football game when its card is shown or hovered/pressed (`warmGame`: once a minute per game, 2 at a time, 6 per 5 minutes in
  the page; the Mac again dedupes 30 s, backs off a failed game 60 s doubling to 10 min, 2 at once, 8 a minute); it only runs
  `game_detail`, nothing that prices, buys or sells. Last-5 dates
  are UTC kickoffs shown in the phone's own time zone. Same isolation rule. **Injuries:** a side shows a real report (or "No
  injuries reported") only when ESPN sent that team's own list; a side it sent nothing for says "Injury report isn't available
  right now" (the tab shows when ESPN sent injuries, or the box score / team stats loaded without them). **Team stats:** rows where fewer is better (turnovers, sacked,
  penalties; `TS_LOWER`) carry `lo`/`ld` from `_ts_leader`: the side with the lower number leads, its number is emphasised, its
  bar is the longer one, a tie is neutral (even bar). An absent block hides its tab, an empty one says so
  ("Recent results aren't available right now", "Not available"). Bars and numbers slide/roll when the game changes them.
  The `GAME_DETAIL` sweep walks a copy (another web thread may insert). Tests: `t_gametabs`, `test_gametabs` (fixture
  `espn_game_tabs.json`: trimmed real ESPN responses). Other sports' tabs are still to come (#72).
- **Buy ideas: ration, dismiss, fold, detail (GitHub #141, display and filtering only; buying still goes through
  `priceIdea`/`buyIdea`/`buySingle` and the guarded Mac paths).** `live_ideas()` (engine) ranks the ideas by expected
  profit in dollars at the suggested stake (`ep` = stake x (share of fair - 1), fields the idea already holds; ideas
  under the green Buy's bar, `green_bar`, or a single with no edge left sort last and say "below your bar"), gives each a
  stable `idea_id`/`key` (the sorted leg tickers, same on every re-offer), and marks a price older than 2 minutes
  `stale` ("refreshing"; the card stays, Get today's price is the refresh). Dismissed ideas (X, swipe left, Not now,
  Clear all) live in `combo_idea_dismiss.json` (today only; back when the edge improves 3+ points or the price drops
  2+ cents; Undo toast), bought ones never come back (kept 3 days); `idea_dismiss`/`idea_undo`/`idea_depth` are
  acts on the web app that take no app lock and move no money. Settings > Money > "Buy ideas shown" (`ideas_shown`,
  default 3, 1-10, shared) sets how many show; the rest fold under "N more ideas". A pre-game idea whose game has
  started is dropped. Live's three sections (Buy ideas, Your combos, Single bets & spreads) fold with a chevron
  button (`cw_fold_*` per phone, count badge stays). Tapping a card body pushes a detail page (`openIdea`: price vs
  fair, edge, chance, stake and expected profit, why it was picked, price line, bid/ask depth for a single, game link).
  The X and fold buttons are compact controls (they get the haptic overlay switch); the whole card does not. The code
  is `watcher/spa/ideas.js`. Tests: `t_ideas_ration.py`, `test_ideas2.py`.
  **The Mac marks a Buy idea bought itself (#270).** Before, only the phone's follow-up `idea_dismiss why=bought` marked
  an idea bought, so a lost reply (or a dismiss that never landed) left it live and a second Get price + Buy could buy it
  twice. Now `idea_mark_bought(legs)` writes `st["bought"][idea_key(legs)]` in `combo_idea_dismiss.json`. It is called
  inside `idea_single_buy` on an ok buy and on an unclear ("check") answer, only when an idea key came with the tap, and in
  the web app's combo `buy` handler on an ok buy or a "check", after `accept_offer`, for that combo's tickers. A definite
  refusal (Pause, cap, block, nobody selling) marks nothing, so the idea stays live. The mark never raises and never
  changes the order's answer; hiding an idea only ever takes it off the list. Nothing here sends, retries or sizes an order
  (rule 8: an unclear outcome stays "check" and is never resent). Phone (`ideas.js`): a lost reply (`r.lost`, "may have
  gone through, check Live") now hides the idea like a check, and `ideaButtons` draws the disabled Pass + "Buying..." row
  whenever a buy is on its way, not only while the 20-second quote is fresh. Tests: `t_singlebuy.py` (marks on ok and
  check, not on a refusal, unwritable file harmless, combo handler order), `test_ideas2.py` (Buying row with no fresh quote).
  **Pass after Get price dismisses the idea (#211):** on a card (and its detail page), Pass closes the idea like the X:
  `ideaPass` drops the quote and its countdown (`S.ideaTid`), then goes through the same dismiss path (`ideaX` /
  `ideaNotNowSheet`: slides out, remembered in `combo_idea_dismiss.json`, Undo toast). Pass is disabled while a buy is
  on its way (`S.ibuy[id]`, set around `buyIdea` / `buySingle`). Display only. Test: `test_ideas2.py`.
  **The Buy button is never green and dead (#252, display only; the Mac's buy paths and guards unchanged).** `ideaVerdict(x, q)`
  reads the fresh price: a single with no edge left after the fee says so in full ("No longer a good bet. Kalshi wants 60¢
  and the fair chance is now 40% (it was 54% when this idea was found), so there's no edge left after the fee."), shows no
  Buy and offers **Get a new price**; a single whose fair chance fell 5+ points since it was found or is under the bar, and
  a combo under the green bar (`clears` false), get a yellow **Buy anyway** with the reason; otherwise the green Buy. The Buy
  is `disabled` only while that buy is on its way ("Buying…"). `ideaBuyGo` (behind `buyIdea`/`buySingle`) ends every tap with
  a plain answer in `S.ideaAns[id]`, drawn on the card and the detail page (`.ians`): bought, Kalshi's or the guard's own
  refusal words, "check", "That price ran out before your tap, so nothing was sent", or "Couldn't reach your Mac, so this
  may or may not have gone through"; a second tap while one is on its way sends nothing. On the detail page a refusal shows
  on the page; a buy or "check" closes it with a toast; toasts now sit above sheets and pages (`z-index:70`). Once a fresh
  price is on screen the numbers from when the idea was found are dimmed under "When this idea was found · 3m old"
  (`ideaOld`); the fresh single block reads Price now, Fair chance, Edge after fee, "Buy now: 4 contracts · $2.47", "Pays if
  it wins: $4"; "Contracts at the ask: 94k" (`ideaCount`). Untouched: Pause, caps (fail closed), rule 8, one order per
  idea/market per 2 min, the fresh book re-read, the Mac's `IDEA_Q` size/price check. Open doubt for Pete: a single idea's
  fresh quote takes its fair chance from the Build board's side for that game (`api_act` "idea"). Test:
  `test_idea_detail_buy.py`.
  **Pass clears the idea and keeps it cleared (#256, hides only).** Pass (the card's X / Not now, and the detail page's
  Pass) removes the idea at once, shows Undo and stays gone. With the Mac unreachable the idea stays hidden
  (`S.idHide[key]` until the Mac confirms, then the usual 9 s mask) and the dismiss is retried in the background
  (`ideaSave`, `IDEA_SAVE_WAIT`: now, 2.5 s, 7 s, 15 s, 30 s, 1 min, 1 min, 2 min); after four failures "Hidden on this
  phone. Your Mac hasn't got that yet, still trying."; if all fail it says the idea may come back after a refresh. Undo
  waits for a save on its way, so Undo is always the last word; a second tap sends nothing. The detail page's Pass no
  longer clears the quote first (the card slides out as it is). The phone sends the fresh price and edge it showed
  (`seen`) and the Mac measures the way back from the better of that and the listed price (`idea_dismiss(..., seen=)`,
  `_idea_seen`; only ids it dismisses, at most 40, numbers checked), which only ever raises the bar to come back; a clearly
  better price (3 points of edge or 2 cents under what he saw) still brings it back. The Undo bar is as wide as its words.
  Test: `test_pass_detail.py`.
- **Buy idea fresh price: a game under way is priced only on a live fair chance (issue #255).**
  Pete's ruling (2026-11-21, option 2). A single-game Buy idea's fresh price ("Get today's price", web app act `idea`)
  used to take its fair chance from the Build board's side for that game. For a game under way that number can be the
  pre-game price (the board was built before the start, or `screen_live` left the game out) or Kalshi's own mid from when
  Build was built, never a real live fair. Now the quote goes through the engine's `idea_single_fair(tk, side, pfair,
  book, kick, row_live)`:
  - **Before the game: unchanged.** The board side's fair (else the idea's own `pfair`, the model chance for a
    spread/total), the same number, edge, sizing and green-Buy rule (`edge >= SINGLE_MIN_EDGE * 0.6`) as before. The
    answer now also names the source (`fair_src`: "sportsbooks", "line model", "Kalshi's price", "when found").
    Note: this path still does not apply Buy straight's 12-minute `SINGLE_FAIR_AGE` rule, `calib_fair` or `_size` (it
    never did); filed as #286 rather than changed here.
  - **Under way** (`started()` on the board side, the idea's start time passed, or the idea saved as live): the fair
    chance comes only from `live_side_fair`, exactly as Buy straight prices it: a live sportsbook line read in the last
    `LIVE_LINE_AGE` (180 s), else the live model on a fresh score (`LIVE_SCORE_AGE`). Spreads/totals under way have none.
    A finished game = "That game is over" (gone, no quote). Buy straight's cautions come along (`warn`): under way (with
    the source), nearly decided (`LIVE_DECIDED`), Kalshi's mid far from the live chance (`LIVE_DISAGREE`), thin (gap over
    `LIVE_SPREAD` or nobody bidding). Under way, thin, nearly decided or far-from-Kalshi is never green (yellow Buy anyway;
    the panel leaves such games out). Build's live side (`screen_live`) holds Kalshi's own mid with the odds' `line_live`/
    `line_at` still on it, so a side marked `live` is never taken as a live sportsbook line (`line_live` off: the live
    model instead).
  - **No live fair:** the quote still gives Kalshi's price, contracts and payout, with `fair`/`edge`/`pct`/`ev` null,
    `fair_src: "none"` and `nofair` (why). The card and the detail page show "—" for the fair chance and the edge with "no
    fair price" under it, "No fair price to check this against: <why>. You'd be going on Kalshi's price alone." and a
    yellow **Buy anyway** (never green, no "no longer a good bet"/"under your bar" math). Suggested stake = Buy straight's
    $2 (`max(OWN_MIN, 2.0)`), labelled "smallest bet" / "Smallest $2", never "recommended" (`stakeCtl`'s `small`).
  - **Combos with a game under way:** found today: they price at Kalshi's RFQ against the board's leg chances
    (`add_own_combo`), and a leg under way there holds either the pre-game price (Build built before the start, or its live
    checks left the game out) or Kalshi's own mid from when Build was built (circular, minutes old). Same hole, so any leg
    under way (`idea_combo_live_gap`) = no fair price: the quote is asked at $2 (when Pete set no amount, never sized on
    that edge) and comes back `clears: false`, `pct`/`ev` null, `fair_src: "none"`, `rec` $2 and `nofair` ("the X game has
    started, and a combo with a game under way has no live fair price"): yellow Buy anyway.
  - Card and detail page: "Kalshi's price now · game under way" when live, a small source line under Fair chance /
    Share of fair (`ideaSrc`: "live line" / "live model" / "none" / the pre-game source) and the cautions (`ideaWarn`,
    Buy straight's `.sbw` style); a thin market under way says so (not "under your bar"); the "chance has dropped" line is
    skipped for a live chance (it moves all game); "Why it was picked" starts "Before the game:" for a game under way;
    "Could you sell it?" says "selling now" during a game. `watcher/spa/ideas.js`, `ideas.css` (`.ifsrc`), `stake.js`.
  - **Buy straight** (`single_buy_quote`) gets the same two tightenings: a `live` side is never a live line, and a
    nearly decided or far-from-Kalshi game under way is never green.
  Unchanged: every buy guard (Pause, the market's own league cap failing closed, the unknown-outcome block, one order per
  idea and per market per `IDEA_TAP_SECS`, the Mac's own quoted size and price only (`IDEA_Q`), IOC at the ask, rule 8:
  "check" never resent). This changes only which fair chance a quote shows and when it is green. `api_act` `idea` also logs
  the reason (`fi["nofair"]`) whenever a game under way falls back to no fair price (log only). Tests: `t_idea_inplay.py`
  (live line, stale live line rejected, live model = Buy straight's number, neither, stale score, spread under way,
  finished game, cautions, pregame unchanged, hiccups, combo legs, Kalshi's mid never a live line, Buy straight's
  "nearly decided" never green, the watcher wiring), `test_idea_inplay_ui.py` (card
  and detail states, buttons, no green without a live fair, the combo case).
- **"Time to cash out" only when smart sell would sell (GitHub #210, alerts and navigation only).** The Live toast
  "Combo N: time to cash out" used to fire on every hold→sell flip of the older Let it ride plan (`plan_cashout`), which
  takes the watcher's *estimated* offer as a fresh one (`fresh_offer` accepts `rfq="estimate"`) and, for a long shot
  with a big payout, prefers a sure few dollars to a ~1% shot (log utility on the bankroll); the Monte Carlo chance's
  noise (8,000 runs) pushes the estimate over its line now and then, so the verdict flickered and the toast repeated.
  Now `cash_nudge(t, h)` decides every cash-out nudge: smart sell's rule (`take_profit_reason`/`exit_policy`) says
  sell, a **real** fresh Kalshi offer (never an estimate), at or above cost and ≥ 97% of the rule's line, and a game
  still to play is under way. `live_view` sets `v["nudge"]`; `nudge_event` (in `record_view`) raises the toast once
  when it turns on (≤ 1 per `NUDGE_GAP` 10 min), worded "smart sell is cashing out at $X" with Auto cash-out on;
  the phone's `cash_alerts` push needs it too. On the page, a combo smart sell looks after (not "I'll sell it") shows
  SELL, the moment bar, the Do now cash-out/"check Kalshi's price" cards and the plan's sentence only with `nudge`
  (`planOn`/`verdictShown`/`whyShown`); "I'll sell it" combos keep the plan's advice. Nothing that sells reads it:
  `auto_sell_now`, smart sell, hedges are unchanged (they already refused a sale below cost and re-quote an estimate).
  **Tapping opens the combo:** the toast is a button (`toast(m, ms, tone, onTap)`, `.toast.tap`) → `openCombo`; an
  urgent push about exactly one combo carries `/#c=<ticker>` (watcher `combo_link`: the text names one "Combo N" on
  this refresh's list; ticker `[A-Za-z0-9._-]` only), and `comboFromHash` (boot.js) opens Live, waits for its data and
  pushes the combo only when it is on Live (unknown, old or malformed = just Live). Tests: `t_cashnudge`,
  `t_push_target`, `test_cashnudge_ui`.
- The Winning now / Losing now / Tied / Won / Lost legend sits right above the combos table and lists only the
  states currently on screen. **A known score decides a live leg's colour (GitHub #320, display only):** `legCls` (chips,
  leg rings, legend, Games card, game page board) says ahead = green, behind = red, level = Tied (a 0-0 kickoff is never
  red because the chance is under 50%); only a leg with no numeric score (a fight, a feed with no points) falls back to the
  chance (≥ 60% green, ≤ 40% red). `pick_state` and every money path never read it. Test: `test_tiedleg.py`.
- Toasts always fade: each has a deadline swept every second (and on touch/scroll/focus), is hidden after the fade and
  dismisses on tap. A Buy idea whose game Kalshi no longer lists shows a calm "not available" card and drops off.
- **Every bet says what it is on, which game and which league (#381/#389).** Spreads and totals showed only Kalshi's bare label
  ("Over 144.5 points"). `bet_describe` / `label_bets` / `label_game_page` (engine) and `betlabel.js` (app) now give every
  single bet and combo leg a plain line: "Over 144.5 total points", "Duke -6.5 (wins by 7+)", "UNC +6.5 (loses by 6 or fewer,
  or wins)", "Duke to win", plus "LEAGUE · Duke vs UNC"; the game page header reads "Game: Duke vs UNC" with "Your bet: ..."
  under it; a game whose teams can't be found shows the ticker's best guess and "game not found". Display only. Tests:
  `t_betlabels.py`, `test_betlabels_ui.py` (390px, dark and light).
- **Tapping a trade alert opens that combo or bet (#391).** `trade_link(E, msg)` = `combo_link` (`/#c=<ticker>`) or the new
  `single_link` (`/#b=<ticker>`, the bet whose label the text names; two different bets = no link), used by `Notifier.add`,
  `E.notify`, the panel and killer-deal pushes and passed to `push`, which adds the ntfy `Click` header (and the Web Push url)
  only when an address is configured (`hub_base(conf)`, never hard-coded). The link holds only the market ticker; opening it
  signs nobody in. `betFromHash` (`boot.js`, beside `comboFromHash`) opens the same bet page as tapping its row; a bet that is
  gone or malformed leaves you on Live. `Notifier.URGENT` gains the robot emoji so the automatic single-sale line goes out at
  once instead of in the 30-minute digest. Tests: `t_tradelink.py`, `test_betlink_ui.py`.
- **Closed bets have a detail page (#392/#393).** The read-only `/app/api/closed?t=<ticker>` (`api_closed`) validates the
  ticker with the combo-link pattern and reads only what the app stores (the account's won/lost/cashed bets, `sell_log`, the
  combo's `combo_autosell_log.jsonl` rows, price history; no account-level data; unknown ids answer `found: false`). The app
  (`openClosed` / `closedFill` in `combo.js`) shows a summary card (league, matchup, bet label, chance, Cost, Paid out or Sold
  for, Profit in dollars and percent, when it closed, a WON / LOST / SOLD EARLY / EXPIRED stamp), why it closed, the chart, the
  picks and what the auto-sell did including retries and back-out notes. Opens from notification links, Results history rows
  and skipped / failed / cancelled / swapped / left-out panel rows (`panelClosed`); an unknown id shows "We can't find that
  bet". Test: `test_closed_ui.py`.
- **Overlap guard: games you already have enough on are held back (#359).** Every pick list holds back a game with **2 or more
  open bets** (`overlap_n`) **or 8% or more of the panel's sizing base at risk** (`overlap_pct`): greyed, sorted last, "You
  already have N open bets on this game ($X at risk)." with an **Add anyway** button that works only on Pete's own tap.
  **Engine** (block before `panel_add`): `overlap_key` maps a game-winner, spread or total market (or event) and any combo leg
  to one game key; `game_exposure()` counts open bets per game from what's already read (account combos, `SINGLES`, today's
  panel items not yet on the account; a combo counts its full cost once on each game it touches; a `check` bet counts, settled/
  failed/skipped never); `overlap_games(allow, base, exposure)` applies the thresholds (base = `_overlap_base`; no balance
  read = count rule only); `overlap_allow` cleans the page's allow list (at most `OVERLAP_ALLOW_MAX` 20); `overlap_note(legs)`
  is the quote line. On display lists any failure = no guard. **Settings › Money:** "Hold back games I already have bets on"
  (`overlap_guard`, on), "Held back from" (1-5 bets, default 2), "Or once this much is riding on it" (2-25%, default 8); all in
  `SHARED_KEYS` and the watcher's `SET_KEYS`. **Where it shows:** Build board, Surprise me, Best bets (inputs on held games
  aren't fed to `best_bets_feed`; a "Left out" card lists them), single games, long shots, Buy ideas and the panel's extras
  (not counted in "Add N"). `/app/api/build`, `/live` and `/panel` take `?allow=`; `panel_add` for `view=extra` drops extras on
  a held game unless the request's `allow` names it (`overlap_extra_ids`) and **fails closed** (refuses if open bets can't be
  read); "Another" and Flip send the allow list too. Quotes carry `overlap` / a `warn` `{"k":"overlap"}` line (display only:
  price, `clears` and Buy unchanged). Rule 7 holds (nothing removed from `CTX`; only a per-request `over` flag); the allow list
  lives only in the page (`S.ovAllow`), never saved. Tests: `t_overlap.py`, `test_overlap_ui.py` (390x844).
  - **Killer deals skip them too (#365/#386).** Both automatic killer paths (killer combo in `shadow_pass`, killer single in
    `single_pass`) skip, never buy, a deal touching a game already at the line, with the same switch and numbers. One check in
    `killer_act`'s `on` branch after the day caps and spending cap and before the `buying` record (`killer_overlap(legs)`
    returns None or the reason; logged "killer deal skipped: ... you already have 2 open bets ($7 at risk) on this game").
    `killer_exposure` counts Kalshi's combos (`cap_bets`, fresh or last good read within `CAP_READ_AGE`), every single/spread/
    total position, today's panel bets, standing orders (`maker`, mode on, `posted`) and killer deals bought, `check` or still
    `buying` in the last day with no outcome yet, each bet once. **Fails closed:** if anything can't be read the deal is skipped
    ("couldn't check your open bets on this game"; retried after 2 minutes, `KILLER_UNREAD_RETRY`); a deal skipped for the
    line isn't looked at again for 6 hours. Switch off = exactly as before. Positions are read through the Mac hub when one
    answers. Known limit: one position per market, so a second killer buy on the same market counts once. Not touched: the
    hedge, standing orders, the panel's auto-buy (#374), watch mode. The killer deals list in Settings shows a skipped deal's
    reason. Test: `t_killer_overlap.py` (`t_safety` section 5 and `t_orders_v2` stub the guard).
  - **Read guards and one alert (#401, #399, #374 part; guards and logging only, nothing is bought that was not before).**
    `killer_act`'s retry exemption matches the reason by prefix (`substr(why, 1, len) = KILLER_OVERLAP_UNREAD`), so the
    "(the setting couldn't be read)" variant is looked at again after `KILLER_UNREAD_RETRY` (2 min) like the other unreadable
    skip, not held 6 hours; the retry re-runs the full overlap check, which still fails closed. `_positions_strict` keeps one
    shared cooldown (`POS_COOL`, `POS_COOL_SECS` = 60) after a 429 (also recognised through the Mac hub's words); while it runs
    the read raises, so every killer candidate skips as unreadable (no buy) instead of hitting Kalshi again (the read itself
    moved to `_positions_read`; closes the "shared cooldown" ask of #399 and the read-load point (3) of #374).
    `killer_unread_watch`: three different killer deals in a row skipped as unreadable send one alert a day
    (`KILLER_UNREAD_RUN`, `KILLER_UNREAD_TOLD`), alert only. Left for #374: scoring the skipped deals in dollars (2), the
    combo dedupe check (4), the stake-in-risk note (5). Tests: `t_killer_overlap.py` (setting retry, cooldown, alert).
- **Surprise me: All | ★ Only, and no star on live combos (#362/#363).** Build › Surprise me has an **All | ★ Only N** switch
  (`surToggle`/`surList`/`setSur` in `build.js`, remembered in `cw_sur`) showing just the "★ Value pick" combos
  (`kind == 'value'`); display only. A combo with a pick under way never carries the star or the "Likely about X% of fair" guess
  (learned from pre-game prices): `value_label(legs)` (used by `value_combos`) labels it `mix` / "Live pick", and `combo_star(c)`
  (used by `combo_view`) re-checks at view time; a live combo also gets no `pred`, `est` or auto-size. Uses
  `idea_combo_live_gap` (a leg it can't judge counts as live; fail closed). Tests: `t_surprise_star.py`, `test_surprise_star.py`.
- **Change vs paid on Live rows, hero and combo detail (#100; display only).** Combo rows (next to the offer, `offNow`),
  single/spread/total rows (Worth now) and the combo detail's Offer carry the change against what was paid: "−7%" over
  "−$0.22" (`chgHtml` in `live.js`; formats `chg`/`chgd`/`absm` in `fmtNum`; dollars always with cents; rounding symmetric on
  magnitude, `rndm`; a zero prints no sign). Both parts are rolling `data-num` numbers, tabular, always two lines so a sign
  flip never moves the row. An estimate (no real Kalshi offer) is prefixed with "≈". The colour follows what is SHOWN in the
  chosen mode (`data-b` both / `data-p` % / `data-u` $: paid $10, offer $9.97 in % mode is a grey "0%"). The hero pill rolls
  its percent and signed dollar change the same way (`heroChg`). A "Change vs paid" switch (`% + $` / `%` / `$`, 44pt hit
  targets, `aria-pressed`, `:focus-visible`) shows above every table with a change line; it only sets `<html data-chg>`
  (`setChg`, remembered as `cw_chg`), so CSS shows the parts and nothing redraws. Same number the row already shows; no
  engine, sell or valuation change. CSS lives in `ideas.css`. Test: `test_pctchange.py`.
- **A newer version reaches an open page (#150, display only).** The web app fills the running version into the page
  (`PAGE_VER`, `__CWVER__` in `SPA`, from `A.VERSION`; the page is `no-store`). Every live/games/game answer carries it
  (`fresh.ver`), and any view also asks the small read-only `GET /app/api/ver` (same sign-in, no app lock, no money) on the
  Mac's tick, every 12 s and when the app comes back (`verPoll`), so a phone parked on Build/Results/Settings notices too.
  `watcher/spa/update.js` (`verSeen`) compares it with `PAGE_VER`. Different + idle = reload by itself with a quiet fade,
  then an "Updated to <version>" toast; busy = a "New version ready: tap to refresh" pill (44 px, labelled, hidden = not
  focusable; `verTap` fires the light haptic inside the real tap, then reloads). **Busy (`verBusy`)** = a finger down, a
  scrub, a sheet or pushed page (game/combo/idea) open, `S.buying`/`S.pSend`/a pot move sending, **any POST still in flight**
  (`api()` counts them in `S.inflight`), a 15 s hold after a buy/go/hedge/single buy/pot move/panel
  approve/add/cancel/restart result (`S.verHold`, so its message can be read), `S.busy`, quote/buy entries
  (`S.qpend`/`S.bpend`) younger than 60 s, a flip, a combo quote or custom offer under 25 s old, a Live Buy-idea quote
  (`S.ideaq`) under 25 s old, a visible bad or "check" toast, a field being typed in, an armed Approve/Add. Idle also needs
  1.5 s since the last touch, scroll or key. The "already reloaded for this version" note (5 min) is kept in sessionStorage
  and localStorage; if neither can be written, or it is there, only the pill shows (no loop). An unreadable version does
  nothing. The service worker has no fetch handler (caches nothing) and carries `WATCHER_VERSION`, so every release changes
  it. Settings > The Mac shows "Up to date" with the app version, or "A newer version is ready" with a Reload button. Tests:
  `t_newversion`, `test_newversion`. Follow-ups: #213, #214.
- **Game page: the "Chance to win" chart starts at kickoff (#486; display only).** Pete: the chart began hours before the
  game (12:41 PM for a later kickoff), a long flat line with the real game squeezed into the last sliver, because the Mac
  records each game's price from long before kickoff and the chart ran from the first sample. No buy, sell, pricing or size
  decision changes, and nothing in the trading loop reads any of this. `api_game` (`watcher/combo_watcher.py`) now also
  returns `start`: the game's kickoff as epoch seconds, from `A.game_start`, but only when it comes from the sportsbooks or
  the score feed (the settle-time estimate, which can be hours off, #223, is never offered; then `start` is null). A failure
  is logged once (`gamestart`) and the page works without it. The page (`winRange` in `watcher/spa/game_tabs.js`, used by
  `paintGame`) takes `t0` = `start`, else the first sample marked in play, else the first score change. Samples before `t0`
  (and any still marked pre-game) are not drawn and cannot be scrubbed. The x-axis starts at `t0` (left label = kickoff
  time); score-change markers use the same scale, so they stay aligned. With nothing to anchor on, every in-game sample is
  drawn as before. A game that has not started (start in the future, or state pre with no start) shows "Kicks off at 7:30 PM.
  The win-chance line starts at kickoff..." (or "Starts <label>") instead of a flat line. "Drag to look back" works across
  the played game from kickoff on; it cannot reach pre-game history any more (that would need a separate pre-game axis, left
  out on purpose). Tests: `test_chartstart_ui.py` (synthetic series with 4 hours of pre-game samples; axis, point count,
  scrub range, marker x, both fallbacks, not-started notes, 390x844 dark and light), `test_gamedetail_api.py` (`start` from a
  book kickoff; an estimate is never offered).

#### Live hero estimate: a leg price with no timestamp is stale (issue #112)

`live_offer_est` (display only, the Live hero's "worth now if sold") used to treat a leg price with no timestamp in
`MARKET_INFO` as fresh. It now counts as stale and returns None, so the frozen estimate stays. No buy, sell, size or
Pause path reads it. Test: `t_offer_live.py`.

Refs #112. Also filed as follow-ups: #517 (inline onclick + no CSP), #518 (#473 delight nits), #519 (#481 findings).
Verified already done on develop: #331, #298, #26 (closed with evidence), #247 (closed; #423 shipped the data-* move).
- **Names by picks (#520).** `combo_names()` / `short_leg()` (engine, next to `team_short`) name a combo `Nuggets + Chiefs +2`: up to 3 picks
  joined with " + ", then "+N more"; pro teams by nickname, a spread stays on its team, player markets and college teams keep their name, cut at
  24 characters; duplicates get the first kickoff ("Nuggets (Nov 23)"), then "(2)". Display only (the ticker is the id). `mine_page` builds the
  names once for `label` (cards, `views[].label`), `MINE["snap"]`, `MINE["hold"]`, so notifications, sheets, toasts and `record_view` use them; the
  old number stays as `num`. Autosell `log_decision`: `combo` is the picks, `combo_id` the old "Combo N", `picks` unchanged; `sell_log.combo` follows.
  `combo_link` (watcher) finds a combo by its picks or number, whole text only. Tests: `t_combonames.py`, `t_push_target.py`.
- **Live hero shows Kalshi's value (#413, #140; display only).** The hero chart is gone (`heroChart`, `wireChart`, `setRng`, `pulseWeek`, `plMoney`,
  `plCol`, `test_heropnl.py`). The big number is "Worth now on Kalshi" with our "If sold now" small beside it; `kalshiNow()` in `live.js` = each open
  combo's `cost` (Kalshi marks a combo at its last trade; includes fees, so it can read a little high) plus each open single's `worth`. `cash_now` and
  valuation unchanged. Result moments (Bought, Sold, Big hit, Approved) have no auto-close: a good result ends on a real `<button class="nice">`
  Nice (44-64px), losses and "Check Kalshi" on OK or Done; bets named by legs (`momName`). A changed score glows its Live row (`.trow.burst`, `S.burst`
  with expiry, off under reduced motion). `btnFail(host,msg,btn)` shakes the button and shows the reason under it (`.berr`, `role="status"`, 15 s,
  `S.berr`/`paintErr()`) for Buy, Buy anyway, Approve, Add; an unknown buy outcome still says "Check Kalshi" and is never retried (rule 8). Tests:
  `test_fun1_ui.py`; `test_motion.py` lost its hero checks.
- **Display polish (#196, #213, #214, #246).** "Change vs paid" keeps its 44px tap area but draws the highlight at text height (24px `::before`).
  The "New version ready" pill sits above sheets (z-index 65, under toasts), has a 44px x (hides it for that version), shrinks to a dot after ~20 s,
  enters softer; a page reloaded for an update fades in (`body.verin`, skipped for reduced motion). `.btn.sm` is 44px tall; "Price it" in Best bets
  opens a folded "More combo ideas"; a tappable toast is `role=button`. Pages open before the first auto-reload release need one manual reload.
  Test: `test_batch_e_ui.py`. Not done: #246 number-roll, settled `#c=` toast, #112 cap message.
- **Leg flip loading (#206).** A row awaiting a flip keeps its size and shimmers (`.lrow.wait`, `lshim` in `build.css`; flat tint under reduced
  motion), text slightly dimmed; `lfold` is gone, `lturn` unchanged. No flip-logic change. `test_flipleg.py`.
- **Small a11y and wording fixes (#455, #437, #435, #438, #313, #304, #283, #307).** "Buying..." rows are `role="status" aria-busy="true"`
  (`test_comeback_ui.py`); the toast is a polite live region (set in `smallwins.js`). After a reprice, focus returns to the card's button and the
  result is read via the never-redrawn `#repLive` (`test_smallwins_ui.py`); `cbTog` fades the Comebacks body over 220 ms (skipped for reduced
  motion). The brake reads "less than holding was worth at the time"; the registry intro is split into What moves / The bar / The brake; a value
  under Changed is not repeated under "Where it stands now". The Selling-at-a-loss row says where "Let it tune itself" is on (`sl_auto` from
  display-only `sl_auto_view()`), "Prefer hedging" no longer prints a fixed "up to 5%". Test: `t_batchf_text.py`.

### Build page
- Panel on top, sport chips (All = mix board), then **⭐ Best bets today**, "Build your own": the games board (live score,
  period, clock for games under way), more combo ideas — each section folds separately (remembered). The old all-strikes
  "Spreads & totals" board is gone (Pete, #63: only recommendations).
- **Best bets today (issue #63, recommend-only, display only).** `best_bets_feed` (engine; called by the web app's
  `api_build`, answer key `best`) ranks single games (`single_candidates`), spreads/totals (the **already vetted** `line_recommend` rows, issue
  #117: learned bar, CLV block, fillable stake, exit route; listed with their own fillable stake and expected dollars, never
  re-priced or loosened; the feed adds only the injury-news guard and the held-combo exposure trim, which can only shrink or
  drop a row; they show even when the balance can't be read for sizing singles/combos, since their stake comes from what fills)
  and value combos (predicted share of fair ≥ 100% and the cut-off) in **one list by expected dollars**:
  each must have an edge at a fair price after fees **and** a likely route to profit, i.e. `smart_buy_ok(simulate_exit)`
  (same exit policy as Smart Sell: a good chance to cash out at +10%, or a hold with `SB_WIN_MIN` win chance and
  `SB_EV_MIN` dollars). Expected dollars = the simulator's `ev` on $5 scaled to the suggested stake (`_size`, quarter
  Kelly, never above it after the exposure cut `exposure_factor`). Rows show type, league, game, pick, Kalshi vs fair,
  edge, stake, expected dollars, the route in plain words, and a real exposure warning ("Kites is already in 7 of your 9
  open combos"). **Fails closed:** an unreadable balance (no stake), a bet the simulator can't model, a pre-game sportsbook
  line too old for how soon the game starts (`line_stale`), or any error = not listed; empty = "Nothing clears your bar right
  now" plus how many were checked. Games already under way and sell-early favorites are not in it. At most `BEST_MAX` (6)
  rows, `BEST_LOOK` (30) simulated per build (memoised 5 min). Nothing is bought from the feed: a single/line's button is
  "Buy straight" (the guarded sheet: fresh quote, cap, Pause, rule 8); a combo's is "Price it" (scrolls to its own card and
  asks for the price there). It is not behind a switch (it only recommends; the Smart Buy switch does not hide it). Type
  chips filter it (`cw_bftype`). Code: `watcher/spa/build.js` (`bestFeed`, `bfRow`). Tests: `t_bestbets.py`,
  `test_bestbets.py`. Still to do (ROADMAP): confidence per league and type, realized return per type, a detail page.
- **Best bets: cash-out time in plain words and just-bought markets (#415, #414).** `exitWhen(mins)` (`build_sections.js`) words
  the likely cash-out time from now: "about 41 min in" up to 90 min, then "in about 5 h" up to 2 days, then "in about 3 days".
  The 73% itself is not changed (the simulator's `p_exit`, which includes pre-game drift, ranks the card). `held_markets()`
  (single markets held on the account, bought in the last 10 minutes via `RECENT_BUYS`, or carrying an unclear-order block) is
  read by `build_page` to drop, from the page only, a held market (either side) from Best bets, the Single games card and the
  spreads/totals list. `buy_single` only records the ticker in `RECENT_BUYS` (a dict write); nothing about whether or how it
  buys changed, and the panel and auto paths do not read the list. Tests: `t_bestbets.py` (`held_markets`), `test_bestbets.py`
  (`exitWhen`).
- **The date range lives on Build (#248) and the combo slip sits with the games board (#249), placement only.** The
  per-league dates combos and the board are built over (`next_day` today/tomorrow for daily leagues and the Mix's "same
  day"; `thursday`/`saturday`/`monday` for slate-week leagues, Sunday always in; `mix_window`, `MIX_WINDOWS`) moved from
  Settings › Games & picks (now one pointer row with Open Build) to a compact card at the top of Build under the league
  chips (`dayRange(d)` in `watcher/spa/build_sections.js`). Same keys and per-league values (not in `SHARED_KEYS`), saved
  through `/app/api/settings` with the league (`api_settings`, `send_synced`), read by the Mac's `by_day`/`day_on` as
  before. `setDays(vals)` ticks, shows the choice at once, saves, reloads Build, drops picks and any quote from the old
  board (a combo is only priced from what is on screen), and on a refused save puts the old choice back ("Nothing was
  changed"). Up to 1360px (`narrowBuild()`) the "Your combo" slip renders right under the games board, before "More combo
  ideas" (`.slip.inl`); wider it stays in the sticky side column. Exactly one slip is ever in the page; crossing the line
  re-renders and keeps the picks (`S.slip`). The floating slip bar, quote/Buy phases, the Buy straight sheet and the flip-leg
  animation are untouched. Tests: `test_buildlayout.py` (plus `test_days.py`, `test_singlebuy_ui.py`, `test_motion.py`).
- Get price → green "Buy" when it clears the cut-off, yellow "Buy anyway" when it doesn't.
- **Over the cap (issue #71):** the Buy/Get price answer (`cap_msg`) says what the spending would reach, how much room
  is left, and the setting to change ("Settings > Money > Weekly cap/Daily cap/Mix cap for <league>"; Pete renamed
  "Weekend cap" to **Weekly cap** on #71). Its window word (`cap_window`) matches what `week_spend` counts:
  "today"/"tomorrow" for daily leagues, "this week (Tue to Mon)" for the slate-week leagues (football, soccer, UFC;
  never "this weekend"), "on games still to play" for the Mix. The rule, the windows and the cap amount are unchanged.
- **Caps fail closed (issue #136).** Every cap check reads spend through `cap_bets` (a fresh Kalshi account read, or
  after a failed one the last good read only while ≤ `CAP_READ_AGE` = 120 s old; else `CapUnknown`). `week_spend` raises
  instead of counting $0; Get price / Buy / Live ideas / the phone's batch refuse with "Couldn't check your weekly cap
  right now, try again in a minute"; killer deals skip; standing orders post nothing new that pass (logged once per
  10 min). `week_spend_shown` is the display-only copy (Build's "spent"). The daily panel's buys are limited by its own
  daily panel budget (`panel_budget`, from the history database) and never read Kalshi spend, so they are unchanged.
  **Single bets use their own league's cap** (`single_cap_block` → `manual_cap`: the market's league from its ticker,
  that league's budget and slate, its combos + manual singles), never the loaded league's or the Mix's: Buy straight
  and Live's single-game buy ideas (`api_act` "idea" quote and "singlebuy" by idea → `idea_single_buy`, which also
  checks Pause, trading access and the unknown-outcome block, allows one order per idea and per market per 2 min
  (`IDEA_TAP_SECS`, marked before the order, freed again when Kalshi clearly bought nothing), sends a sub-cent price rounded down, notes the buy in `manual_buys`, and marks an unclear
  answer "check"). Mix combos keep the Mix cap. `manual_spend` fails closed too (no history database = its own words,
  `NO_HISTORY_MSG`; a failed read = `CapUnknown`, never $0; manual-buy reads and writes use `store_x_strict`/`store_rows_strict`, which raise
  where `store_x` swallows; with no ticker it counts the loaded league's own window, today for daily leagues).
  `_manual_note` never loses a filled buy: tried twice, then kept in memory (`MANUAL_MEM`, still counted by the cap until
  the app restarts), logged "MANUAL BUY NOT SAVED" and pushed to Pete once (`MANUAL_ALERT`, set by the web app). A
  market's kind (win/spread/total) comes from its ticker; a side's `kind` only fills in when the ticker can't tell. The window words say "Tue to Mon" because `sunday_of` puts a Tuesday
  game in the coming Sunday's week (Pete's #71 note said Wed to Mon; the counting itself was not changed).
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
  never sees singles) **plus** `manual_spend` (that league's manual singles in the same window; an unclear one included;
  table `manual_buys`), against the cap of **the market's own league** (from its ticker, never the one Build has loaded
  or the Mix), via `single_cap_block` → `manual_cap`/`manual_cap_msg` (issues #133, #136); the cap check, the order and
  its note run under one lock, `_SQ["buy"]`). The board's fair price
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
- **Your own bet amount (issue #145; Pete's tap only, no new automatic buying).** Combo cards, the slip, Live Buy ideas
  (singles and combos) and panel bets before Approve/Add get an amount row (`watcher/spa/stake.js`, `stakeCtl`): the
  recommended size first ("Recommended $X"), presets $2/$5/$10/$20, a "Last $X" chip (the last amount chosen, kept on
  this phone only, `cw_stk_last`; the default stays the recommended size), -/+ by $1 and a typed amount, the expected
  profit in dollars, "N× the recommended size: more risk for the same edge" at 1.5×+, and the cap room. A changed amount
  drops the old price: singles re-price at once, combos show "Get price · $X". **The Mac checks every amount**
  (`own_stake`: a real finite number, $1-$100 (`OWN_MIN`/`OWN_MAX`), rounded down to the cent; bad = refused with
  words, never clamped): the combo quote and Live idea quote (`combo_offer` in the web app: `get_offer` at that amount,
  plus `rec`, `ev`, `room`, `max`), Buy straight (`single_buy_quote` now refuses a bad amount instead of clamping), and
  the panel (`own_panel_stakes`: $2 to the panel budget; `panel_approve(..., stakes)` refuses when the bets riding would
  pass the budget; `panel_add(..., stakes)` counts them in the same room; the item keeps `rec_stake` and `own`; the card's
  stats are re-simulated; `panel_whatif` (read-only, no app lock) updates the ring while he edits). A Live single
  idea's Buy (`singlebuy` by id) must match the size and price the Mac quoted in the last 25 s (`IDEA_Q`), else nothing is
  sent. Combo buys still accept exactly the cached offer (rule 7/8 unchanged); caps, Pause and the unknown-outcome
  block are unchanged. Tests: `t_ownstake.py`, `test_ownstake_ui.py`.
- **Combo idea card buttons (issue #65):** the button row (`.brow`, primary `.pri` + secondary `.sec`) wraps, and long
  labels wrap instead of widening the button, so "Not this one" never leaves the card (360–430 pt). A card with a price
  asked for (`S.qpend`), a live quote or a buy under way (`S.bpend`) has a phase (`data-ph`, `ccPhase`): `renderBuild`
  puts the same DOM node back across any redraw (refresh, rebuild, load), so the button is never replaced, flickers or
  loses a tap; the countdown ("Ns left", `qTick`) only edits its number in place, and the card is redrawn once when the
  quote runs out. "Not this one" is off while a price or buy is in flight. `test_buildbuttons.py` covers it.
- **Flipping a leg on a combo idea (issue #104, display only; `flip`/`swap` acts, quotes and buys unchanged).** Tapping a
  leg row (`flipLeg`) drops any fetched Kalshi quote on that card **at once** (Buy can't be tapped on a price for other
  legs; `buy()` and `quote()` also return early in the phase) and puts the card in phase `flip` (`S.fpend[i]` is the
  flip's own token object, kept across redraws like `ask`/`buy`): the row folds, the numbers that depend on the flip
  (`.dep`: fair payout, chance, estimate line and the previous "Good flip" note) shimmer, Get price is a disabled
  "Updating…" (`data-stale`), Not this one is off, a second tap does nothing. The quote line's space is kept (`.qgap`,
  covering the quote line **and** the amount row `stakeCtl`, which hides while a flip is on its way: the distance from
  the first of `.qline`/`.stk` to the buttons minus the card's 10 px row gap) and the note box and button widths are
  fixed, so nothing jumps. After at least `FLIP_MIN` (220 ms) the answer is applied **only if** this flip still owns
  the card (token), the league (`S.lg`) is the same and the card still has the tapped legs (`ccSig`); otherwise it is
  dropped and the card just redraws. Applied: the new row turns in, numbers roll, the note slides in. Failed: a short
  shake on the row, an inline "Couldn't flip" note and a toast. One page-level polite announcer (`#flipsay`,
  `flipSay`) says "Updating…" then the verdict. Reduced motion = a crossfade. No `hap()` in the flip (the global tap
  tick only; iOS ignores later ones). Leg rows are keyboard buttons (44 px, focus ring). Test: `test_flipleg.py`.
- **Every panel card names its game** (GitHub #61): a league tag in the header, and a line "Flyers at Bruins" (spreads/totals) or "Flyers vs Bruins" (singles, sell-early, each leg of a combo; pick first), from `stamp_games`/`_cand` (`game`, `vs`, `league`; no lookups); notifications and the recap use `bet_text`. The buy chip says "buys when you approve" until approved, then the buy state.
  Combo-idea legs, the slip, the board and the Bought sheet use `legRow` (sport icon, pick, "vs opponent · league · time", chance; tap a combo idea row to flip it).

- **Long shots (#341).** Replace "More combo ideas" at the top of Build's combo area (the random `build_combos` ideas
  stay under a "🎲 Surprise me" fold). `longshot_build` runs **off the app lock** (`longshots_kick`/`longshots_work`, a
  thread per sport, ≤ every 15 min `LS_EVERY`) and returns ≤ 3 (`LONGSHOT["per_day"]`) by expected dollars. Legs
  (`longshot_pool`/`longshot_leg_fair`): one team per game, **pregame only** (20+ min before a known start), 65-80%;
  the chance is Kalshi's mid (`_mkt_side_mid`; no bid or gap > 10¢ = out) moved toward `calib_fair` only by the earned
  `mkt_weight` (0 until earned), never by disagreeing free lines (> 3 points) or stale lines. Combos
  (`longshot_combos`): 6-8 legs from the 12 best picks, joint chance ≥ 7%, any two sharing ≤ half their picks. Fail
  closed: Pause (`paused_now`), no trading/the Pi, `hold_refusal` strict, `rfq_unsure`, a combo with a live quote on
  Pete's screen (never re-quoted under him); asks multiplying to over chance/0.9 aren't quoted (`pre_ratio`). Kalshi's
  makers quote it via `carry_quote` (withdrawn at once, never accepted). **Pete's hold-to-win test** (`longshot_hold`,
  not `smart_buy_ok`): whole contracts in the stake, fee rounded up, ≥ 7% to hit, payout ≥ fair after the fee
  (`min_pct` 1.0), expected dollars > 0 held to the end; stake quarter Kelly on `_manual_base`, ≤ $5, under $1 = not
  shown; `get_offer`'s green Buy for a long shot runs the same test. The fee is unverified for RFQ trades:
  `longshot_fee` charges the standard taker fee (`FEE_RATE` 0.07, per order, rounded up, never zero;
  `LONGSHOT["fee_rate"]` once confirmed). Logged in `longshot_log`. Card (`watcher/spa/longshots.js`): hit %, expected
  dollars after the fee, stake, payout, picks. **Get price** = act `longshot` (server matches id and shown picks,
  refuses while paused, re-prices each pick fresh, kind `longshot`, `get_offer` at its stake); **Buy** = the usual act
  `buy` → `accept_offer` (caps, Pause, rule 8), which now refuses an offer for other picks than shown (rule 7, every
  combo Buy). An unknown outcome leaves "Check Kalshi" on the card. Nothing buys by itself. Tests: `t_longshots.py`,
  `test_longshots_ui.py`.
- **Scope of the legs check (release 507 review):** the check below (#203, extended in #445) covers only the web app's Buy
  (`combo_watcher.py` ~4076, `expect_legs=shown`). Older callers of `accept_offer(i)` without `expect_legs` skip it: the planner's
  own terminal flows (~14000, ~18673), the panel's own buy (~22204) and `combo_watcher.py` ~2433. They buy only on Pete's tap or an
  approved panel, so this is a documented gap, not a change.
- **Combo Buy re-checks the page's legs (#203, rule 7; guard only: nothing new is bought and no price, size or cap
  changes).** The web app's Buy sends the legs it shows (it already did, since #347). The Mac now checks them in
  `accept_offer(i, expect_legs=...)` (`buy_legs_refusal`): they must equal BOTH the stored offer's legs and the combo now on
  that card (`CTX["combos"][i-1]`), compared as sets of tickers, exactly as `quote` checks the card. Any mismatch sends
  nothing, keeps the offer, prints `buy combo N: refused before the accept (reason); page=... offer=... card=...`, and
  answers "That price was for a different combo, or this page is out of date. Reload the page..." (`legs_mismatch`), so a
  combo-changing path that forgets to pop its offer can no longer buy legs other than the ones on screen. **Pages that send
  no legs:** the idea Buy used to send none, and a stale tab may too. They are NOT refused for missing legs (that would have
  blocked every multi-game idea Buy) but are held to offer = card, so a combo that changed under its offer is still refused.
  The idea price (`a: "idea"`) now returns the combo's `legs`; `ideas.js` keeps them (`S.ideaq[id].legs`) and sends them with
  Buy, so idea Buys are checked against the page's own legs too. The panel, killer and other callers of `accept_offer` pass
  no `expect_legs` and are unchanged. Tests: `t_buy_legs_203.py` (engine) and `test_buy_legs_203.py` (real `/app/api/act`:
  idea Buy with and without legs, other legs, flip without popping the offer, Build card, long shot).
- **Overlap re-grey after Add anyway, overlap log, own request kept (#366, #367, #350).** **#366, never looser:** "Add
  anyway" now carries the game's exposure at the tap (`KEY~n~risk`; `overlap.js` `S.ovAllow` is a Map). `overlap_allow`
  returns a set subclass with the exposure; `overlap_games` greys the game again when more bets (`n`) or more dollars at risk
  than at the tap are riding. Exposure that fell never greys by itself. An older page that sends a plain key is let through
  as before. Malformed or negative values are dropped; duplicates keep the stricter one. **#367, measurement:**
  `overlap_log(kind, game, n, risk, why)` writes greyed games ("grey", once per 30 minutes per game and exposure) and Add
  anyway taps ("add") to the `overlap_log` table; it never raises and never changes the answer. **#350:** `carry_quote` no
  longer withdraws Pete's own open "Get price" request on the same combo: if any request is open (or the list cannot be read)
  it makes no quote instead of calling `clear_my_rfqs`. Tests: `t_guards2.py`.
- **iPhone tap, scroll and layout polish (#274, #273, #272, #178, #186; Build, Results, Live toasts and sheets).** Build date
  card: the "Sunday is always in" note is plain text (no tappable-looking span), the day and week chips are 44px high
  targets, and a refused date change shows an inline `.derr` alert inside the card (from `S.dayErr`) instead of a toast that
  vanished. While the board reloads after a change, the card is kept on screen (`S.dayHold`, rendered by the skeleton branch
  of `build.js`) so it no longer jumps. When a date change clears picks, `setDays` toasts "Picks cleared for the new dates."
  (#274, #273). Toasts: `toast()` drops its tap action while a sheet (`#modal.on`) is open, and `app.css` blocks pointer
  events and the chevron behind the sheet, so a toast can no longer be tapped through a sheet (#272). Idea dismiss/undo: the
  delayed save sleep is cancellable (`job.wake`), so Undo brings the idea back immediately with a "Bringing it back..." toast
  and no server round trip when nothing was saved yet (#178). Results: the Smart Buy "Bigger stakes" line is a collapsible
  `<details class="sbmore">`; the Stopped column uses plain-English `BUCKET_WORDS`, and the engine mirrors that with
  `LINE_BUCKET_WORDS` / `line_bucket_words` in the `line_clv_block` message. Best Bets line cards show "avg N¢" when the
  average fill differs from the quoted price; `line_fill` now returns `avg` and `best_bets_feed` passes it through (display
  only, no pricing or stake change) (#186). Already done on develop and not rebuilt: #281, #151, #218. #205 already works at
  normal row height (rows taller than 64px skip the see-through switch). #196's switch no longer exists. #206 needs a
  real-phone look and a design decision. Tests: `t_tap_polish.py` (engine), `test_tap_polish.py` (page),
  `test_buildlayout.py` (extended).
- **Release 507 review follow-ups (display and wording only; #508, #509).** The sale rules from the review (95%-of-cost profit
  floor, fee-only loss as a stop-loss, 97% guard kept on guarded stop-loss back-outs) are described under Selling. Screens: the
  Settings text is plain English (the guards line names the league, 95% of cost, the ~$800/day smart-sell-more limit, paused
  until a date); stake and slip notes say "before fees"; the Results "more" row (`.sbmore summary`) is a block with a 44px
  minimum so the arrow sits right after the label; the Learned guards switch shows off and disabled with "Off for now: turn on
  ... first." when Auto cash-out or self-tuning is off (`tgl` takes an optional `why`); the Ideas card's "Expected profit" sits on
  its own line at the left (`.stkev` full width); the chart's pre-game note is only "The win-chance line fills in once play
  begins." (the banner above already says the kickoff time; kickoff wording stays out because the app is multi-sport).
  `combo_sell_fee` is a Mac-file-only key (`t_newkeys.py` documents it); `t_neverloss.py` marks its stub. Tests:
  `t_flexcostfloor.py`, `t_flexsell.py`, `t_combofee.py`, `t_losscutclock.py`, `test_chartstart_ui.py`, `test_learnedguards_ui.py`.

### Results page
- P/L by week, history with sport/date/outcome filters, the paper gate, and "📊 What's working": combo price
  levels (every quote by band: hit vs expected, riding return, worth at game time, lab ride vs smart sell),
  bet types and sports (real vs paper, return, smart-sell replay, CLV), selling (ridden vs cashed, automatic sales,
  per-league smart-sell tuning), and the read-only knob registry card (#228 PR1, see Selling). Results re-reads
  itself after a sale or any money change (#242, see Live page).
- **Profit scoreboard (issue #138, read-only).** Top of Results (`pbBlock` in `watcher/spa/scoreboard.js`; it replaces
  the old combo-only KPI row once it has data). Source of truth is the **`ledger` table**: one row per finished market
  (combos from `_fetch_account`'s bets; single bets/spreads/totals via `_single_ledger` from the same fills and
  settlements, read as a signed YES position so NO bets and closing by buying the other side are right), written by
  `ledger_note` at the end of every direct Kalshi account read (only changed rows; never raises into the read).
  cost = money paid to open + every fee (incl. a settlement `fee_cost`), back = sale proceeds + settlement payout;
  `sold_back`/`sell_fees`/`n_sold` for sales; `closed` = Kalshi's sell/settle time, else the Mac's `bets.settled`, else
  when first seen. `profit_board()` (cached 2 min; `api_results` → `board`): week (from Monday) / month / all time with
  profit, ROI, fees, days up/down, best/worst day, a running total (scrubbable), open bets as a separate **estimate**
  (last `pulse` row ≤ 30 min), Smart Sell vs holding (scorecard), Smart Buy skips (from `analytics()["smart_buy"]`'s
  gate, paper at $5), and breakdowns: bet type (paper beside it), league, how it ended (smart sell / you / held won /
  lost, with "vs holding"), source (panel, panel extras via the item's new `origin`, Buy straight, Build & Live ideas
  together, held before tracking, you on Kalshi), price quality (panel items: expected edge band vs actual ROI,
  predicted chance of profit vs actual per league, CLV, time before start; real and paper), stake. Groups under
  `BOARD_FEW` (20) say "too few to trust"; `_board_say` writes one sentence per breakdown using a ratio-estimator ROI
  standard error (|z| ≥ 2 = "more/worse than luck explains"). Tests: `t_scoreboard.py`, `test_scoreboard.py`.
  **Sales in V2 fills (#333):** Kalshi reports a sale at the YES price with the side flipped (selling YES shows as
  "sell no"); `fill_yes_delta(f, pos, n)` treats every `action: sell` as closing what is held (towards zero; any excess
  opens the other side), and with nothing held or no `action` uses the YES-book direction (`book_side`,
  `outcome_side`), else the legacy side; buys keep their side. `ledger_note` writes only rows that differ from the saved
  one (`_ledger_same`, money to the cent), so rows written wrong before are put right on the next account read; the
  old guards stay (fewer fills, settlement-only rows, rows closed 180+ days ago). Read-only. Test: `t_ledgersales.py` (A, B).
  Not built yet (in #138): weekly summary push, automatic tightening from losing groups, links into settings.
- **Wording on the self-tuning and Smart Buy cards (#304, #290, #307; text only).** The self-tuning brake reason says "less than
  holding was worth at the time"; its sections are named "Changed (live now)", "Waiting its turn", "Held back: the newest bets
  disagree" and "Still a test, nothing changes". On the Smart Buy card "beats plain" is now "skips helping", and the
  scored-on-paper note reads "Only bets that would have made today's panel teach Smart Buy. The rest are for the paper book".
  Tests: `t_knoblive.py`, `test_knobshadow_ui.py`, `test_analytics.py`.
- **Smart sell's decision log and scorecard (issue #115, read-only).** `log_decision` writes a "skipped" once per bet
  and reason (again when the offer's 10%-of-cost band changes; `SELL_TOLD`), trims to the newest `SELL_KEEP` (3,000)
  other lines but **never trims sales, hedges or "check"s** (`_trim_sell_log`, at 1.5 MB), labels `by` as
  mac/phone/pi (`device_label`), and copies every sale-type line into the **`sell_log` table** (`sale_store`;
  `sale_import` copies the file's older ones once). Sale records now carry `frac`, `kind`, `side`.
  `sale_outcomes()` (the watcher's shadow loop, outside `odds.lock`, at most every 10 min; public `GET /markets`, ≤ 200
  markets) records what holding would have paid for each sale (`sell_log.outcome/held`) and each sold ledger row, for
  60 days. `sell_scorecard()` (in the board; What's working › Selling, `scoreCard`): per league and reason, sold for
  (the ledger's proceeds after the sale fee, else the logged offer net of the single fee) vs holding paid, too early vs
  right and dollars left on the table; your own sales; ridden combos' best real offer vs payout. Not yet fed to
  `smart_tune` (that would change selling).
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
  (engine), `test_cover.py` (page). The cover pass picks its Sunday with `_cover_sunday(now)` (Pacific date of the pass's own clock); `t_cover.py` pins its week (Sunday 2026-11-22) so it no longer depends on the real date or time zone (#370).

- **Cover test, v2 (#340).** Every later checkpoint is rebuilt from Kalshi's results each pass in slate order: worth =
  what a cash-out would get given the picks settled so far (full payout once nothing is left); the first lost/tied pick
  marks the survivor dead (`lost`, `alive: false`) and it is worth $0 from then on. The replay is one sale and stops where
  the lost pick was last alive (`sim_exit(c, until=)`, default unchanged); won early legs start at 1.0. Costs include the
  taking fee on every combo (`_cover_fees`, `fees_both`, `one_sided_cost`). **Lean variant** (`cover_lean_split`): only
  close early games (favourite under `COVER["lean_fav"]` 75%) are covered both ways, lopsided favourites carried; the
  result gets `variants: {full, lean}`, `value`, `lost`, `v: 2`; `cover_math` previews lean (`p_alive`); `cover_summary`
  adds `fees` and a `lean` aggregate; older finished weeks (< 45 days) are redone once, quietly. Card: "Cover all | Lean"
  table, carried favourites and upsets, "out" checkpoints, green/red profit.
- **"Combos as the cheap way in", paper (#341 C).** Own `carry` table, apart from the panel, the $300 gate, the quotes
  table and every learned number. `carry_pick` (shadow loop, under `odds.lock`, quick) picks 2-3 near-even picks (mid
  35-65%, gap ≤ 6¢) from separate games within 8 h (one set a day); `carry_pass` asks the price **outside** `odds.lock`
  via `carry_quote` (clears a leftover request, never accepts, always withdraws); ≤ 1 attempt a round, 24 a day; never
  paused, on the Pi or without trading access. `carry_note` (also after every `get_offer` combo quote) logs separate-game
  near-even 2-3 leg quotes and paper-buys $5 at or under the legs' mid product (same-game only logged; none with a game
  under way). `carry_resolve` settles after the taking fee. Results: `carryCard`/`carry_summary` ("too few to trust"
  under 20).
- **Held to the end: how it has done, on Results (#461; "How it ended" tab; display only, nothing moves money).** Pete saw
  the "How it ended" breakdown, concluded that holding to the end has a poor record, and wants smart sell to become aware of
  it; he chose to show it on Results first while the paper test (`tools/exit_replay.py`) measures it. No buy, sell, sizing or
  gate decision changes. `profit_board()` adds `periods[*].held` (from `_held_facts` + `_held_summary`, both read-only; the
  existing groups and the "vs holding" column are untouched). The tab shows, above the table: `Won 5 of 17; at these prices
  you needed about 3 in 4 to break even`, the break-even being the average cost per $1 of payout (`_in_n` turns it into "N in
  M" or a percent), tagged `small sample` under `BOARD_FEW` (20) bets; and below it (under "Held to the end: lost"): **Could
  have been sold higher**, `N of M traded above what you paid before closing (best bid beat cost by $a to $b)`, plus how many
  had no price history, also tagged `small sample`. Data: only what the app already stores. A combo's payout comes from
  `bets.pays` and its best price from its real `offers` (the same source as the "rode to the end" line); a single bet's
  contract count was not kept in the ledger, so its price paid was unknown: it counted as "no price history" and was left out
  of the break-even (counting only the winners would bias it; see the next bullet for the stored count). No division by zero:
  no payout known gives "no break-even", no bets gives no line. Tests: `t_heldlosers.py` (the rate wording, every empty and
  zero case, board end to end), `test_scoreboard.py` (the lines on the page, phone dark and light).
- **Each bet's contract count is stored in the ledger (follow-up to #461; bookkeeping only).** Single bets did not keep how
  many contracts were bought, so Results could not price them (the "could have been sold higher" line only covered combos,
  whose payout is in `bets.pays`). The `ledger` table now keeps per bet `n_bought` (real: contracts opened; a fill that
  closes a position is not counted; a fill that flips the side counts only the part that opens) and `unit_cost` (real: all-in
  cost per contract: money paid to open plus the buy fees, not the sale fees; `(ledger.cost - sell_fees) / n_bought`, rounded
  to 4 places). No buy, sell, sizing or gate decision reads these fields; nothing moves money; rule 8 untouched; the buy path
  itself is not touched. No new Kalshi call: both come from the fills `_single_ledger` / `ledger_note` already read
  (`bought_n` for combos). Schema is additive and backward compatible: `_ledger_table` adds the columns to an older file with
  `alter table` (checked against `pragma table_info`, so safe to run twice), alongside the existing `nf` column. Old rows
  stay NULL = unknown. The first account read after a restart fills a row whose fills are still inside Kalshi's window
  (`LEDGER_SIG` starts empty; `_ledger_same` sees the difference); a row whose fills have aged out stays NULL, and a saved
  count is never overwritten by an unknown one (`coalesce(excluded.n_bought, ledger.n_bought)`). A settlement-only row (no
  fills) stays unknown rather than guessed. Reading: `ledger_price_paid(row)` returns `(contracts, cost per contract)` or
  `(None, None)`; it never raises on NULL, zero, negative, text or a missing key. `_ledger_rows()` puts the cleaned
  `n_bought` / `unit_cost` on every row, so `profit_board` rows carry them. **Follow-up (small, not done because #462 was not
  in develop):** once #462 (held losers) lands, `_held_facts` can price a single from `ledger_price_paid(r)` (payout =
  `n_bought`, a contract pays $1; best sell price from the single's own price history; "no price history" when `(None,
  None)`), and the "a single bet's contract count is not kept" wording in `_held_facts` / `_held_summary` and its doc should
  be replaced. Tests: `t_storecounts.py` (counts from fills, settlement-only unknown, migration of an old-schema file, NULL
  handling, `ledger_price_paid` edge cases, and that the new names appear only in ledger bookkeeping, never in a
  buy/sell/sizing function); `t_ledgersales.py` unchanged.


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
  **Exception (#151, scrolling first):** on iPhones the tick is a see-through switch over each control (`.hsw`,
  method N), and a switch under the finger can stop iOS scrolling. So big scroll surfaces (`hswBig`: taller than
  64px, or wider than 70% of the screen unless a real button/chip/tab) get **no switch and no iOS tick** (the tap still
  works); their compact buttons/chips inside keep theirs. Switches and their controls have `touch-action:manipulation`,
  and while the finger scrolls (momentum included) `html.hswscr` makes switches `pointer-events:none` until 150 ms
  after the last scroll. The audit counts big cards/rows as exempt; `test_hsw.py` checks drags from them scroll.
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
  text fields, scrub charts, sideways strips, the test card's other buttons. **Controls inside a sideways-scrolling strip get no switch either** (`HSWX`: the game page's tab row `.gtabs`, the scoreboard's `.pbt`, wide tables `.gtw`, the Settings index `.sidx`; GitHub #218): WebKit's switch grabs a drag that starts on it as a slide of its knob, so a row of tabs that each carried one couldn't be scrolled sideways on Pete's iPhone. They keep press feedback and their tap (no iOS tick); a new sideways strip must be added to `HSWX` (`test_gtabscroll` fails on any overflowing strip with switches inside). A MutationObserver adds them to new content
  (never two per control). Only on iPhones/iPads, not in the Pythonista app, and off with the Haptics switch or reduced
  motion (`hswSync`). `hap()` still tries the scripted switch for a pattern's extra ticks and for gestures with no tap
  (chart scrub, pull-to-refresh, sheet drag, tab swipe, slider steps): iOS 27 ignores those, so they stay silent there.
  Settings › Test haptics (`hapCard`, `HAPM`/`HT`) lists N first, marks G/H/I "Pete confirmed" and the scripted ones
  "did nothing on iOS 27", and asks whether every tap ticks now. Tests: `test_hsw.py` (Chromium and, where installed,
  WebKit; CI installs it), `test_haptics.py`, the iPhone audit in `test_motion.py`. The card's on/off switch is per phone (`cw_hapoff`); helper switches carry class `hapx`,
  test buttons `data-hapt` (N's also `data-hsw`).
- **Settings scrolls on an iPhone again (issue #281).**
  Pete (iOS 27.2.1, Home Screen app): swiping up or down on Settings was really bad. Cause: the Settings folds (#212,
  shipped in 2026.11.21.131) made every section header a full-width 56pt button (`.sfold`, about 360x56 at 390 wide),
  and the Mac line (`.smac`, 362x44) is one too. Real buttons count as compact in `hswBig` unless taller than 64px, so
  each got a see-through iOS switch (method N). With most sections folded (only Money and The Mac start open) those
  headers stack up: measured at 390x844 in WebKit and Chromium, 55-65% of a screen of Settings was see-through switch
  (Live and Build: at most ~24%, Results ~15%), and a switch under the finger can stop iOS scrolling (#151). Ruled out
  by measurement: no re-render while scrolling (Settings isn't in the refresh loop; 2 DOM mutations over a full scroll),
  no long tasks (p95 frame ~18 ms in both engines), the tab swipe and pull-to-refresh skip inputs and only act on a
  mostly sideways / at-the-top drag, native switches (`.tg`) and sliders cover 1-6% of a screen, no `touch-action`,
  `will-change` or blur layer specific to Settings.
  Fix: `.sfold` and `.smac` carry `data-hsw="0"` (already in `HSWNO`), so they get no switch: scrolling first, as in
  #151. They keep press feedback and their tap (fold/unfold, jump to The Mac); they no longer tick on iOS 27. Every small
  Settings control (chips, choice and stepper buttons, the Mac's buttons) keeps its switch. Settings at 390x844 is now at
  most ~11% switch (the league chips). UI only: no setting, save, money, buy/sell, Pause or cap code touched.
  Tests: `test_settings_scroll.py` (new; fails on the old code): folded and unfolded, a drag from every kind of Settings
  line (section header, Mac line, switch row, slider row, Let it ride, choice row, moved-to-Build row, combo-mix row, the
  Mac's facts and buttons) starts on the line itself, never on a switch or slider (WebKit and Chromium), and in Chromium
  (real touch events through CDP) scrolls ~the dragged 216px and changes no setting or fold; no screen of Settings is
  over 25% switch; header and Mac line still work on a tap; small controls keep their switches. `test_motion.py`'s
  iPhone audit counts `[data-hsw="0"]` controls as exempt scroll surfaces.
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
    **Live > Settled cards carry the date too (issue #207, display only):** `mine_page` adds `done_at` to each settled combo
    view (`done_stamp` = `realized_ts`: cash-out sell, else Kalshi's settlement time, else the Mac's own `bets.settled`; None
    = no date shown, never a guess; pending = None). The card shows a small grey line under the picks ("Today",
    "Yesterday", "Sat Nov 21", year only when it isn't this one) in the phone's own time zone (`doneWord`, `.sdt`), and
    "Newest" sorts by it. Results' History rows already carry the day; settled singles on Live are open positions with no
    realized time, so they have none. Tests: `t_realdate.py`, `test_settled.py`.
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
- **Settings folds, jump chips, search and the Mac line (GitHub #212, UI only; no setting, switch, save or Mac action changed).**
  Every Settings section (`scard`, `watcher/spa/settings.js`) folds with a chevron: the header is one real button
  (`.sfold`, 56 pt, under `hswBig`'s 64 pt so it keeps its iOS tick) and the body is the same `.fold` grid as Live's
  sections, remembered per phone as `cw_fold_set_<id>` (`sOpen`/`sShow`/`sTog`; Money and The Mac start open, the rest
  folded). A folded card's badge (`sBadges`: "N of M on" switches, Watching/Off for Killer and Standing orders, the version
  on The Mac, Kalshi connected) updates on every change. The body stays in the page (hidden), so nothing re-renders to open
  it; a test that needs a folded control calls `sShow('<id>', true)` first. The chips (`.sidx` buttons, never links, so they
  get the haptic tick) jump to a section and open it: a sticky row under the header on a phone (`--toph`, kept by
  `sAfter`), the side index on a desktop. The search box (`sFind`, `S.sq`, the input keeps focus across redraws) filters
  rows (`.srow`, `.kv>div`, `.mixr`, `.sact`) by name and description across every section **in the DOM, without
  touching the saved folds** (`.set.sq` forces sections open; clearing restores them; "No settings match" when empty). The
  "The Mac · version X · up to date / update available" line (`macLine`) sits under the title and opens The Mac. Test:
  `test_settingsfold`.
- **Small no-money UI wins (#404 #405 #406 #408 #353 #368 #402 #403 #275; presentation only, nothing in buying, selling, sizing
  or the order paths changed).** Touches Results, Build, Live, Long shots, Overlap and the Closed-bet page.
  - **#404 Comebacks header** is a real `<button class="cbh">` with a keyboard focus ring, `aria-expanded` and a one-shot open
    animation (`cbin`, `cbchev`); `cbTog()` puts focus back on the header after the redraw.
  - **#405 Tappable rows:** Results history rows (`.hrow2`) are `role=button` with a tab stop; Enter and Space work (a global
    handler in `smallwins.js` for any `[role=button][tabindex]` that is not a real button). The Build "Skipped" card is no
    longer a button wrapped around a button: the card opens the detail and "Tap for a fresh price" is its own 44px button
    (`.prbtn`).
  - **#406 Closed bet:** a network error or malformed answer shows "Couldn't load that bet" with Try again; "We can't find
    that bet" shows only when the server says `found:false`. The retry area keeps its height so the page does not jump.
  - **#408 Inline handlers:** game, combo and pick ids are passed through `data-t` / `data-ev` and read with `this.dataset`, not
    interpolated into `onclick` strings (`pToggle` and `pStakeSheet` ids were left alone). `onclick` stays because the press and
    haptic layers key off `[onclick]`.
  - **#402 #403 Reprice feedback:** `pReprice` no longer fires a haptic or toast after the await. A failed or unreachable
    reprice shows inline on the card (`pRepFail`: "Check Kalshi", "Paused", "Just priced", or "Couldn't get a fresh price",
    each ending "Nothing was bought."), and a later success replaces it. Only `panel_reprice` is called.
  - **#353 (client half only):** a long-shot price failure shows an inline `.lsfail` reason instead of a toast, and an unknown
    outcome (`res.check`) keeps saying "Check Kalshi" across Build refreshes in this page (`S.lsChecked`); display state
    only. Skipped: carrying the unknown-outcome state from the server, because it touches the buy path and rule 8.
  - **#368 Overlap:** "Add anyway" keeps its width (`min-width`) and the list re-renders with a FLIP slide
    (`flipSnap`/`flipPlay`) instead of jumping; the error haptic after the await is gone.
  - **#275:** a "bad" idea answer shakes once (`shk`, one-shot); reduced-motion turns every new animation off.
  - Files: `watcher/spa/smallwins.js`, `smallwins.css` (new, in `MANIFEST.json`), `results.js`, `build.js`, `combo.js`, `games.js`,
    `game.js`, `ideas.js`, `live.js`, `longshots.js`, `overlap.js`. Tests: `test_smallwins_ui.py` (dark and light at 390x844:
    roles, keyboard, focus ring, one-shot animations, failure feedback, retry, no JS errors, no sideways scroll);
    `test_reprice_ui`, `test_comeback_ui`, `test_closed_ui`, `test_overlap_ui`, `test_longshots_ui` still pass.
- Next makeover work (Kalshi-style game page drill-down, shareable result card, more charts): `ROADMAP.md` and issue #12.
- **Tickers and ids travel as data, not as code, in tap handlers (#247, part of #408).** Buttons in the web app used to paste
  a ticker or id straight into the JavaScript of their `onclick` (`ssPrice('${x.t}',this)`). Even with `esc()` that is not
  safe: the browser decodes `&#39;` back to `'` before it runs the handler, so a ticker holding a quote could end the string
  and run code. Now each such button carries the value in a `data-*` attribute (escaped with `esc()`) and the handler reads
  `this.dataset.<name>` when tapped. The handler stays inline on purpose (not a document-level listener):
  `event.stopPropagation()` and bubbling work exactly as before. Same actions, endpoints and guards; nothing about buying,
  selling, Pause or rule 8 changed. Converted: `sell_single.js` (Sell sheet buttons), `build.js` (panel Skip/amount, Buy
  straight in rows, slip bar and slip card, Flip a team), `build_cards.js` (singles card), `combo.js` (Hedge/Ask/Sell),
  `game.js` (Buy a team), `ideas.js` (price/buy/pass/not now/dismiss/open), `longshots.js` (quote/buy), `live.js` (cash-out,
  smart-sell chip, row open, Hedge sheet, Cash out sheet; NOT the Decision cards at `live.js` lines 97-103, whose Keep, Cash
  out, Hedge and Ask buttons still paste the ticker into an inline `onclick`), `access.js` (copy link). Still inline (not converted, no change in this release): `overlap.js` line 15 (Add anyway), `pick(...)`
  in `build.js`, `openCombo`/`openGame`/results/overlap handlers, and `game.js` line 35. Test: `test_onclick_data_ui.py`
  renders each of these with a ticker holding a quote, angle brackets and an ampersand, taps every button and checks the
  handler got the exact string, nothing ran as code and the onclick text never contains the ticker; plus a source check that
  converted handlers stay converted.

#### UI polish batch 2 (issues #436, #454, #455, #437, #440, #281)

- **44px tap targets (#436, #454):** one rule in `app.css` gives `.dbtns .btn` (Pass / Buying / Cash out / Hedge), `.sheet .btn`
  (Done, Copy code, Copy address, closed-bet Try again), `.srow .btn` (Settings rows such as Secure address › Try again),
  `.empty .btn` (the "Couldn't load this screen" Try again) and `.sbgo .btn` a `min-height:44px`.
- **Screen readers (#455, #437):** every `<span class="spin">` is `aria-hidden`; the disabled "Buying…" buttons carry `aria-busy`.
  The shared sheet (`#sheet`) is now `role="dialog" aria-modal="true"` and `modal()` names it from its first `<h3>`.
  The one-time log-access code sheet keeps its short wording; its button row just gets a little breathing room.
- **Best bets wording (#440):** `exitWhen` reads "about 41 min from now" (minutes from now, not minutes into the game).
- **Settings scroll (#281, partial, not confirmed on a device):** range sliders get `touch-action:pan-y` so a vertical swipe that
  starts on a slider scrolls the page. The other suspects were checked and are already fine: the swipe-between-tabs, pull-to-refresh
  and scroll listeners are all passive, and Settings has no backdrop blur. #281 stays open until Pete says it feels right.
- **Tests:** new page test `test_polish2_ui.py` (phone size, dark and light: heights, aria, dialog role, wording, slider
  touch-action); `test_bestbets.py` expects the new wording.
- **Dev Mac log access hardening (#528, #380, #378).** `log_db_connect` sets `SQLITE_LIMIT_COLUMN` to `LOG_DB_COLUMNS_MAX` (100), so a result
  with more columns is refused ("too many columns", a plain 400) before a huge row is built (`t_logs_db.py`). In `log_answer` a line over
  `LOG_LINE_HUGE` (20,000 chars) becomes `[line too long]` before scrubbing (`t_logs_caps.py`); lowering `LOG_RATE` to 10 a minute waits on
  measuring the real Mac. Turning log reading off and "New code" ask in the app's bottom sheet (`modal()`), not `confirm()` (`test_logaccess_ui.py`).

## Kalshi API watch (GitHub issue #82)

- `.github/workflows/kalshi-api-watch.yml` runs on GitHub (not the Mac) every 6 hours and runs `tools/kalshi_feed_watch.py`, which reads Kalshi's API changelog RSS feed (`docs.kalshi.com/changelog/rss.xml`) and opens one issue per new entry from the last 14 days (max 5 a run, deduped by the feed id in the body, open or closed), labelled `kalshi-api-change`; two tiers: a removal/deprecation word (deprecat/remov/no longer/sunset/migrat/410...) AND an app area (orders, portfolio, RFQ/quotes, order book, market fields, signing, rate limit, websocket...) in the title/description gets `breaking` + an "ACTION LIKELY NEEDED" first line; everything else is filed as a plain "FYI" issue (2 of the 15 entries at launch were breaking). It never touches `wip:*` labels.
- **Alerts appear as GitHub issues**: GitHub emails/notifies Pete (the repo owner) for each one. A dead feed exits quietly; after 4 failed runs in a row it opens one "Kalshi API watch is failing" issue (count kept in the `kalshi-watch-failures` label's description). Try it with `python3 tools/kalshi_feed_watch.py --dry-run` (prints, changes nothing).
- Feed text is untrusted: stripped to plain text, trimmed, fenced, never run. Permissions are only `contents: read` + `issues: write`. Tested by `tests/suite/t_kalshi_feed_watch.py`. Scheduled runs start only once the file is on `main`.

## Open items

All planned work that isn't built yet (what it's waiting on, and the suggested order) is in **`ROADMAP.md`**.
Read it before starting new work, and keep it current: when something ships, describe it here and remove it there.

## Code map (where to look)

Engine: Smart Buy evidence `sb_universe_stash`, `smart_buy_universe`, `smart_buy_backfill`, `sb_paper_build`,
`sb_paper_leagues`, `_sb_early`, `_sb_game`; self-tuning `KNOBS`, `knob_view`, `knob_tune`, `knob_live_value`,
`knob_brake_pass`, `knob_sale_expect`, `_replay_real`; `panel_collect`, `build_panel`, `choose_panel`, `panel_pass`, `panel_exec`, `panel_approve`, `panel_add`,
`prune_drafts`, `panel_rebuild`/`rebuild_status`/`panel_look_now`, `panel_settle`, `panel_record`, `adjust_cutoffs`, `combo_cutoff`, `lab_pass`, `lab_ticks`,
`_replay`/`sim_exit`, `smart_tune`/`smart_params`, `analytics`, `take_profit_reason`, `auto_sell_now`,
`single_sell_reason`, `smart_sell_singles`, `open_singles`, `live_view`, `record_view`, `mine_page`,
`fetch_account`/`_fetch_account`, `kalshi_send` (records app buys via `note_app_order`), `get_offer`,
`accept_offer`, `add_own_combo`, `set_league`, `LEAGUES`/`SPORTS`/`SPORT_PREFIX`.
Watcher: `shadow_loop`, `quick_rounds`, `panel_loop`, `rebuild_loop`, `update_loop`/`update_if_newer`/`repo_now`/`repo_sha`, `spa_assemble`/`spa_fetch`/`spa_swap`/`spa_repair`, `start_hub`,
`webapp_main` (`api_live`, `api_build`, `api_act`, `api_panel`, `api_results`, `api_game`), `mac_settings`,
`tailscale_clis`/`tailscale_env`/`tailscale_run`/`tailscale_status`/`tailscale_https`/`https_loop` (secure address: tries
every Tailscale CLI with a launchd-safe env; "signed out" only when BackendState is NeedsLogin; retries every 5 min until on), `push`/`web_push`
(every ntfy alert also goes to web push unless `web=False` or a topic is given; the Pi has no subscribers so it stays alerts-only). SPA (in `watcher/spa/`): `renderLive`/`heroLive`, `renderBuild`, `renderResults`/`anBlock`, `renderSettings`,
`afterPaint` (number rolls, stagger, indicators), `go`, `modal`, `okSheet`, `toast`, `hap`.
Tools and docs: `tools/exit_replay.py` (read-only early-exit value test, `docs/EXIT_REPLAY.md`; see "Early-exit value test" under
Fair prices and data), `tools/read_prod_logs.py` (the dev Mac's client for the production Mac's logs; keychain `nfl-combo-logs-url` /
`nfl-combo-logs-token`; `docs/LOG_ACCESS.md`), `watcher/spa/smallwins.js` / `smallwins.css` (small UI wins, keyboard handler for
`[role=button]`, one-shot animations), `watcher/spa/logaccess.js` (the Settings › This Mac "Let the dev Mac read logs" row).
**Log access for the dev Mac (#377; hard rule 9).** The watcher hub answers `GET /api/logs?source=console|autosell&since=&limit=`
with a redacted tail of `watcher.log` or `combo_autosell_log.jsonl` plus a status line (versions, uptime, Pause, role, auto
cash-out on/off). Off by default; Settings › This Mac › "Let the dev Mac read logs" (only on the Mac itself, `mac_settings` action
`logaccess` → `log_access_set`) makes a `secrets.token_urlsafe(32)` code shown once and stores only its SHA-256 in `watcher.json`
(`log_access`). Gates in order: on + tailnet only (`log_client_ok`: 100.64/10, fd7a:115c:a1e0::/48, the Mac itself, Tailscale serve
with a user; LAN and Funnel refused) → 404; `LogGate` 30/min per client, 5 wrong codes per client / 30 overall per 10 min → 429;
Bearer only, `hmac.compare_digest` on the hash → 401; bad params → 400; any read or redaction error, or a live secret surviving
(`LogLeak` tripwire) → 503 with an empty body. POST → 405 with `Allow: GET` while on, 404 while off. Caps: 200 lines default, 500
max, 200 KB, last 1.5 MB of a file, 2000 chars a line. Redaction (`log_redact`, `log_fields`; control and zero-width characters
stripped first, patterns bounded against huge lines): live secret values (and their URL/JSON forms), PEM blocks (any case), auth
headers, JWTs, the `cw` cookie, sensitive `key=value`/JSON pairs, non-allowlisted URL hosts, emails, `*.ts.net`, IPs, UUIDs, home
paths, long random strings, balance/pot amounts; autosell records are field-allowlisted (`LOG_FIELDS`). Tickers and per-trade amounts
are kept. It never takes a lock and never touches a money path; Pause, the Pi and rule 8 are unaffected. Tests: `t_logs_redact.py`,
`t_logs_failclosed.py`, `t_logs_auth.py`, `t_logs_readonly.py`, `t_logs_caps.py`, `t_logs_allowlist.py`, `t_logs_default_off.py`.
