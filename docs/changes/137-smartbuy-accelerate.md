# Smart Buy, faster evidence: every market on paper, a paper book, a backfill, borrowing sooner (issue #137)

**Section:** Selling (after "Smart Buy, stage 2: the gate"), and Results page (What's working › 🧠 Smart Buy)

Pete (2026-11-21, "How do we accelerate Smart Buy" → "do 1, 3, 2, 4"): reach the graduation evidence sooner by
scoring more bets on paper. The calendar can't be rushed (games must finish; ≥ 55% of days up), so only what is scored
widens. **All paper:** no buy, sale, panel pick, stake, skip, cap or Pause path reads anything new here, except the
dial's stricter-only early level (4, below), which is the gate getting stricter sooner by design.

- **1. Every priced market, scored (`source='universe'`).** `panel_collect` hands its own games (not started, or live
  priced) to `sb_universe_stash` (new small dicts; the candidates are never touched), and `line_candidates` stashes
  every spread/total strike it priced with an edge (`SB_UNI["lines"]`; its answer is unchanged). Kept: every game-winner
  side (the panel's guards: fair ≥ 20%, price < 97¢, a sportsbook or live chance, never a started game's pre-game
  chance) and every pre-game strike whose fair beats Kalshi's ask plus the fee. `grade` = `cand` when it also passes
  the panel's own rule (single_candidates' 2.5¢ and 4%; the spread/total bar, its 6% and the CLV block), else `wide`.
  `smart_buy_universe` scores them with the same `simulate_exit` and verdict columns (`skip`, `strict`, `pays`; `old` =
  1 for `cand`), never-scored first then nearest games, once per market every 30 min within 3 h of its game or in play
  (`SB_UNI_NEAR`), else every 3 h (`SB_UNI_FAR`); a market the panel or a Buy idea scored within that time is skipped
  (`SB_CACHE["tk"]`); a pool older than 15 min (live: `LIVE_POOL_AGE`) or a game that started since is not scored.
  ≤ `SB_BUDGET` (0.15 s) of simulation a pass; the watcher calls it **outside `odds.lock`** after each full round and
  each quick round (`smart_buy_universe(odds)`), rows written in one short transaction (`_sb_insert`). No request of
  any kind: prices in hand only; universe markets are **not** added to the price recorder (`price_watch`), so
  `price_path` growth is unchanged. New column `exit_shadow.grade`.
  **Growth:** ~400 markets a day × ~10 checks before compaction; `_sb_compact` (in `price_prune`) keeps only each
  universe market's first check and last check before its game per grade once the game is a day old, and universe rows
  stay ≤ `SB_UNI_MAX_ROWS` (120,000, oldest first): ~1,000 rows a day × 60 days = 60k, inside the table's own 60-day,
  200,000-row cap (unchanged). CPU ~20 s a day.
- **What learns from what (`_sb_results`).** One row per bet (keyed by its tickers), its last check before the game.
  `wide=False` is the **dial's evidence** (`smart_buy_learn`, the knob stepper): live checks of bets that pass the
  panel's own rule (panel candidates, Buy ideas, universe `cand`). Left out on purpose: universe `wide` rows (a different
  population: the biggest edges are the ones most often a pricing mistake, so mixing small-edge bets into a band would
  make it look better than the candidates the gate judges, i.e. looser) and the backfill (smart sell's settings today
  were tuned on those same bets: look-ahead). `wide=True` (every scored bet) feeds the paper book and the card. A bet
  scored by several sources counts once, attributed panel > idea > universe > backfill. The card's "skipped/saved",
  "What it checked this week" and "Predicted vs what happened" still count panel candidates and Buy ideas only
  (`source in ('panel','idea')`), so their meaning is unchanged; `smart_buy_ideas_gate` reads `source='idea'` only.
- **2. The paper book (`sb_paper` table, `sb_paper_build`, hourly from the history loop).** For every scored bet: its
  role (`stake` = panel-grade and kept by the gate; `skip` = the gate turned it down, scored at $5, never staked;
  `extra` = below the panel's rule but Smart Buy's own pick, `smart_buy_ok`; else `watch`), the stake graduated sizing
  would give it (`_size`: quarter Kelly on the 30%-shrunk edge, $2 minimum, ≤ 5% of the base; bets taken in the order
  they were found until the day's panel budget, `panel_budget`, is used; less than $2 of room = not bought), what that
  made (the $5 result scaled), and CLV for singles/spreads/totals (`close_prices(mid=True)`). The base is the panel's
  saved one (`combo_sizing.json`), else the bankroll setting: never a Kalshi read. Its own table: never `panel` (the
  $300 gate), `ledger` or `analytics()`'s gate numbers. `sb_paper_leagues` feeds the Results card's **"Bigger stakes:
  not yet"** line per league with real numbers (settled staked bets, dollars ahead "on paper", share of days up, CLV,
  whether the skips beat plain), plus "Scored on paper: N bets, M settled" per league and in total by source
  (`smart_buy_summary()["scored"]`, each gate line's `scored`). Display only: nothing acts on it; Hard rule 2's
  graduation is still not built.
- **3. Backfill (`smart_buy_backfill`, `source='backfill'`, daily, ≤ 3 s of simulation a run, resumes at the next
  history pass).** Two honest sources: the panel items in history (real and paper; the fair chance and price they were
  chosen at, the price really paid, a known result from the item or the ledger, checked before the game) and
  `line_fairs` (every spread/total strike the engine priced, the fair it used, Kalshi's ask and the settled result:
  its last check before the game, with a positive edge, graded by today's spread/total bar; the CLV block isn't
  replayed). Rows are dated at that check, carry the result, and no gate verdict (`skip` null, `strict` 0). A bet with
  any exit_shadow row already is skipped: re-running adds nothing, a bet scored live is never counted again. Kept out
  of the dial (above). Not done, no honest inputs: bets placed on Kalshi directly and game-winner checks outside the
  panel (no fair chance or start time with a result), and combos' in-play paths.
  On a read-only copy of Pete's history (2026-11-21): 191 bets (6 panel bets, 185 strikes): NCAAF 132, NCAAMB 49,
  NHL 8, NBA 2.
- **4. Borrowing sooner, stricter only (`SB_BORROW_N` = 10, registry `sb_borrow_n`).** A group (everyone, a sport, a
  league) with 10-29 results gets one look per new block of 10 (`early_blk`): `_sb_step` with the same evidence bars,
  and only a step **up** is kept (`early`, ≤ the soft top 3; never down). A league short of 30 of its own uses the
  strictest of today's borrowed level and the early levels of itself, its sport and everyone (`_sb_dial_of`,
  `_sb_early`; `early: true` on the dial and the card: "already a little stricter (1) from NBA's first results"). A
  lender with 30+ results lends only its own level. At its own 30 a league starts from the strictest level it was
  using and its own record then moves it both ways, as before.
- Tests: `t_sbaccel.py` (the stash and grades, line_candidates unchanged, budget and stagger, cadence, skips, never
  raises, `build_panel`/`smart_buy_filter` byte-identical with the universe on vs off over 60 random panels, ideas
  gate untouched, only Smart Buy code reads exit_shadow, outside odds.lock, the dial's evidence, compaction and caps,
  backfill idempotence and no double count, the paper book's roles/sizing/budget/own table, the card numbers,
  borrow-sooner stricter only, the registry); `test_analytics.py` (the card's "Scored on paper" wording).

ROADMAP: adds "Smart Buy faster evidence, next: universe markets for the leagues the Mac's panel doesn't look at
(soccer, tennis, EuroLeague, UFC: priced only by the web app's Build board today), game-winner backfill once a start
time and result are recorded with each check, and price paths for universe markets if exit calibration needs them
(would grow price_path)"

**CLAUDE.md notes for the release owner:** add a "Smart Buy, faster evidence" bullet group under Selling after stage 2
(the five bullets above, shortened); in the stage 2 text, "Learning (12 of 30)" now notes that a league may be
stricter early from blocks of 10 (stricter only); in Hard rule 2's graduation text, the "Bigger stakes: not yet" line
is now fed by the paper book (`sb_paper`), still display only. Code map: `sb_universe_stash`, `smart_buy_universe`,
`smart_buy_backfill`, `sb_paper_build`, `sb_paper_leagues`, `_sb_early`.
