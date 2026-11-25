# Paper shadows: player-prop prices and slate concentration (issues #323 step 2, #332, #341)

**Section:** Fair prices and data (next to `signal_shadow` and `mkt_fair_shadow`)

Two more write-only recorders, same pattern as `signal_shadow`: bounded, every error swallowed, off the trading path,
append-only, and **no decision reads them** (`t_paper_shadows.py` fails if the engine mentions the tables outside the
block). Neither adds a Kalshi or Odds API request, neither buys, sells, sizes, ranks or gates anything.

- **`prop_shadow`** (#323 step 2, table `prop_shadow`). `fetch_series` hands every market list it reads to
  `prop_shadow(out, series)`. It only acts when the series is a plain player-prop series (regex `PROP_RE`: NFL
  RECYDS/REC/RSHYDS/PASSYDS, NBA PTS/REB/AST/3PT, NHL GOAL/PTS; protected `…PROT`, ladders, soccer never). Per market:
  ticker, league, stat, strike, bid, ask, mid, size at the ask (when Kalshi sends it), volume, the game's kickoff
  (`KICKOFF` of the matching `KX<LG>GAME-<game>`; unknown or past kickoff = skipped, so pre-game only), and `result`
  when a settled market comes back. Kept only with a mid of 10-90% and a gap of 6c or less (smart sell's rule), one row
  per market per 30 minutes, at most 800 rows a call. The last row before kickoff is the close. **No fair is recorded:**
  the recon found no free de-viggable price, and reading the ESPN/DraftKings line would be a new request.
  **Today nothing reads a prop series, so the table stays empty** until a later, separately approved poller (public
  `GET /markets?series_ticker=KX…`, about 15 series every 30 minutes, no key) feeds it. Settings key `prop_shadow`
  (ON for recording; false = off). Bound: 14 days and 150,000 rows (checked every 6 hours).
- **`slate_shadow`** (#332, table `slate_shadow`). Called once at the end of `panel_collect` for each league. Writes
  aggregates only (no tickers or ids), at most one row per scope per 30 minutes:
  `held` (all leagues; the open bets from the account and panel caches via `game_exposure`, weighted by dollars at
  risk) and `pool` (that league's panel candidates before the choice, counted equally). Columns: bets, games, total
  weight, share on the top game and top three, Herfindahl index (`hhi`) and effective number of games (1/hhi), most bets
  on one game, share in the top league, share in the top kickoff slot (3-hour blocks, Pacific; pool only), share of
  bets that are favourites (chance 50%+; pool only), share in the top bet class (single/line/combo; pool only), combos
  with two picks in one game. Join `day` to the stored panel's predicted chance of finishing ahead and its result to
  answer "did a samey slate cause the bad day". Settings key `slate_shadow` (ON; false = off). Bound: 90 days and
  20,000 rows.
- **#341 (a) and (b) were already built** (`mkt_fair_shadow` / `mkt_fair` and the cost-carry test / `carry`, merged
  with #347 and its follow-ups), so nothing was added for them. Still open there: the held-out check before the learned
  market weight is used by any pick (ROADMAP), and the scoring of the carry test needs more settled days.

Tests: `t_paper_shadows.py`.

ROADMAP: adds "Prop price poller: a public, key-free read of the prop series every 30 minutes, with a fair from the ESPN/DraftKings line, to give `prop_shadow` data (needs Pete's OK for the extra Kalshi requests)"
