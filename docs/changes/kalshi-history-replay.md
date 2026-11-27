# Kalshi history replay (research tool)

**Section:** Research tools (next to `tools/exit_replay.py`)

`tools/kalshi_history_replay.py` downloads Kalshi's public settled single-game markets with 1-minute bid/ask candles
(NFL first, then NBA and other sports with enough history), caches them OUTSIDE the repo in
`~/dev/research/kalshi-history/`, and replays simple exit rules against hold-to-settlement: sell at bid >= cost + 3/5/10c,
sell at T-1h or T-15m if bid > cost, and a buy-only-below-baseline filter. Fees `ceil(0.07*n*p*(1-p))` on entry and exit,
entry at ask, exit at bid. The report gives per sport and price bucket the net cents per $1 staked, game-level bootstrap
95% ranges, a 70/30 time-ordered pick-then-score, hides groups under 20 games, prints data-quality gates first, and
tests the pass bar (>= 1c over hold, range above 0, 2+ sports or 2+ weeks, survives a 60 s lag). It also measures
replacements for SB_PRE_CLOSE, SB_PRE_VOL, SB_SPREAD and SB_LIVE_WIDEN.

Offline only: no change to any trading code, no keys, public unauthenticated GET paths only (others refused in code), one
request per second with 429 back-off, responses cached. The Kalshi terms pages could not be read (429), so data stays
local and is not redistributed. Docs: `docs/KALSHI_HISTORY_REPLAY.md`; first results: `docs/results/kalshi-history-first-run.md`.
Tests: `tests/suite/t_kalshi_history_replay.py` (synthetic fixture with a known answer, no network).
