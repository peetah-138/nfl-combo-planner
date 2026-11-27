# NFL trend discovery (offline research)

Goal (Pete): "figure out trends that DO matter". This is a research tool, not part of the app. It never touches the
trading code, the watcher, keys, the history database or any `combo_*.json` file. Data lives outside the repo.

Code: `tools/research/nfl_discovery.py`. Air-side check: `tools/research/nfl_state_vs_kalshi.py`. Pinned research
environment: `tools/research/requirements-research.txt` (use a venv outside the app's). First results:
`docs/results/nfl-discovery-first-run.md`.

## Data and attribution

Play-by-play (1999 to the latest season) and `games.csv` come from nflverse (https://github.com/nflverse), released
under CC-BY-4.0. Credit: nflverse contributors. Files are downloaded politely (one at a time, cached, with a
`manifest.json` of SHA-256 hashes) into `~/dev/research/nfl/` (override with `NFL_RESEARCH_DIR`); the tool refuses a
data folder inside the repo. Only aggregates are ever written into the repo.

## What it does

1. **Baseline** win-probability model from game state only: score margin, time left, possession, down, distance,
   yard line, timeouts, pre-game spread and total. Trained walk-forward: to score season S it has only seen seasons
   before S-2; the two seasons in between pick the number of trees. Reports log loss, Brier and a calibration table.
2. **Richer model** with candidate facts added (rest days, neutral site, roof, division, weather, referee, quarterback
   experience and change, run/pass pace, recent scoring run, penalties, turnovers). Reports the held-out improvement
   over the baseline (with a range from resampling whole games) and permutation importance per group and season.
   Injuries are not in nflverse play-by-play and are not used.
3. **Situation scan**: one observation per game at seven clock points (kickoff, end of Q1, half, start of Q4, 10:00,
   5:00 and 2:00 left). The residual is what happened minus what the baseline said, from the point of view of the
   team ahead (the favorite if tied). Every cell (all, one condition, two conditions over 18 dimensions) with at least
   `--min-n` games is a hypothesis; all of them are counted and printed. Benjamini-Hochberg false-discovery control is
   applied over the whole family. A survivor must also be at least 2.0 win-probability points and have the same sign in
   at least 70% of seasons. Because one real effect shows up through many overlapping slices (an indoor edge appears in
   every "home" cell), survivors are then explained away greedily: the strongest is subtracted, everything is rescanned,
   and what is left is an independent finding.
4. **Pre-registered claims**: 12 sportscaster-style win-probability claims and 3 over/under claims, fixed in the code
   and committed before the first real run, tested as their own multiple-testing family.
5. **Survivors table** (aggregates only, plain-English labels) and **decay tracker** (effect by season, slope, last
   three seasons against the pooled effect; "retire", "fading" or "holding").
6. **Portable model**: a small antisymmetric logistic (8 coefficients, no intercept, exported to
   `tools/research/nfl_state_model.json`) that runs in plain Python. `nfl_state_vs_kalshi.py` uses it.

## Checks built in

- Start-of-play scores only. nflverse `total_*_score` is the score after the play and is on a banned list that the
  model code refuses.
- Splits are by season and asserted; never random rows (plays of one game are near-duplicates).
- Referee and quarterback features use only earlier games (expanding, leak-free).
- The scan unit is a game, so 150 plays of one game are not counted as 150 pieces of evidence.
- A random-sign placebo scan must reject about nothing (printed).
- Synthetic mode (`run --synthetic`) plants a stable indoor edge and a decaying short-rest edge in made-up games with
  pure-noise referee and wind, and the tests check that the planted edge is found and the noise is not.

## Running

    python3 -m venv ~/dev/research/venv-nfl
    ~/dev/research/venv-nfl/bin/pip install -r tools/research/requirements-research.txt
    ~/dev/research/venv-nfl/bin/python tools/research/nfl_discovery.py fetch
    ~/dev/research/venv-nfl/bin/python tools/research/nfl_discovery.py run --ablate-last 2 \
        --results-md docs/results/nfl-discovery-first-run.md --export-model tools/research/nfl_state_model.json

## Comparing with Kalshi (Air side)

No recorded Kalshi data exists in the repo's test fixtures, so the comparison is a read-only script for the machine
that has the history file (same rules as `tools/exit_replay.py`: mode=ro, no network, aggregates only, groups under
20 samples hidden):

    python3 tools/research/nfl_state_vs_kalshi.py --model tools/research/nfl_state_model.json --out ~/nfl_state_vs_kalshi.json

It joins `sig_state` (score, share left, possession), `price_path` (bid/ask within two minutes) and `closes`
(pre-game chance, outcome) for NFL game tickers, one sample per game per 10 minutes. It prints log loss and Brier for
the model against Kalshi's mid, and the hypothetical per-contract result after the fee of buying when the model is 3,
5 or 8 cents above the ask, with game-clustered ranges. A win here is a reason to test further, not a trading rule.

## Honest limits

- Most candidates fail; the point is to know which few do not.
- BH assumes independent or positively dependent tests; overlapping cells are positively dependent, but this is an
  assumption. The explain-away step reduces redundancy, not the dependence itself.
- Survivors are deviations from a state-only baseline, not from the betting market. A deviation from the baseline is
  not an edge against Kalshi until the price is compared (that is what the Air-side script is for).
- A model-misfit deviation (for example a baseline that is slightly too cautious late in games) can look like a stable
  effect. The scan reports it as such; read late-game survivors with that in mind.
- The latest season is partial. Era changes (rules, passing rates) can make a baseline trained on old seasons drift;
  walk-forward retraining limits but does not remove this.
- Permutation importance scrambles one group at a time and can create unrealistic rows; `--ablate-last N` refits
  without each group as a cross-check.
