# Smart Buy, faster evidence: every market on paper, a paper book, a backfill, borrowing sooner (issue #137)

**Section:** Selling (after "Smart Buy, stage 2: the gate"), and Results page (What's working › 🧠 Smart Buy)

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

ROADMAP: adds "Smart Buy faster evidence, next: universe markets for the leagues the Mac's panel doesn't look at
(soccer, tennis, EuroLeague, UFC: priced only by the web app's Build board today); game-winner backfill once a start
time and result are recorded with each check; price paths for universe markets if exit calibration needs them (would
grow price_path); the paper book choosing like the panel (choose_panel's ahead floor and type shares, fill caps)"

**CLAUDE.md notes for the release owner:** add a "Smart Buy, faster evidence" bullet group under Selling after stage 2
(the bullets above, shortened); in the stage 2 text, "Learning (12 of 30)" now notes that a league may be stricter
early from blocks of 10 (stricter only); in Hard rule 2's graduation text, the "Bigger stakes" line is now fed by the
paper book (`sb_paper`, live panel-grade stakes only), still display only. Code map: `sb_universe_stash`,
`smart_buy_universe`, `smart_buy_backfill`, `sb_paper_build`, `sb_paper_leagues`, `_sb_early`, `_sb_game`.
