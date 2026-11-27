# NFL trend discovery (offline research tool)

Adds a research-only tool; nothing in the app, watcher or trading code changes.

- `tools/research/nfl_discovery.py`: walk-forward state-only baseline, richer gradient-boosted model with candidate
  facts, game-level situation scan with Benjamini-Hochberg control over every scanned cell (count printed), effect size
  in win-probability points, season-stability (>=70% same sign), greedy explain-away of overlapping cells, 15
  pre-registered claims (A01-A12 win probability, T01-T03 totals) as their own family, decay tracker, random-sign
  placebo, and a synthetic mode with planted effects. Data is downloaded into `~/dev/research/nfl/` (never the repo).
- `tools/research/nfl_state_vs_kalshi.py`: read-only Air-side check of the exported portable model
  (`tools/research/nfl_state_model.json`) against Kalshi's live price from `sig_state`, `price_path` and `closes`.
- `tools/research/requirements-research.txt`: pinned research venv (not installed by the app or CI).
- Tests: `tests/suite/t_nfl_discovery.py` (pure-Python statistics always; synthetic end-to-end only where numpy,
  pandas and scikit-learn exist) and `tests/suite/t_nfl_state_vs_kalshi.py` (synthetic history file: read-only,
  aggregates only, hidden small groups, missing-table degradation).
- Docs: `docs/NFL_DISCOVERY.md`; first real-data results in `docs/results/nfl-discovery-first-run.md`.
- Data: nflverse, CC-BY-4.0 (credit nflverse contributors).
