# Buy-timing data (issue #8, autopilot step 8): record only

What was already logged per bet (panel items in the `panel` table, real, paper and lab): kick time, `bought_at`, price at
build (`legs[].p`), price paid (`paid`/`price`, or `pays` for a combo), `clv` (game-time mid vs the build price, set when the
game starts, never for live buys), result, `pl` (held to the end, fee in) and `pl_real` (Kalshi's fills). The scoreboard
already shows ROI and CLV by four hours-before buckets, but only as a transient view. Not logged: a flat row to query,
full auto vs Pete's bet, fees, CLV against the price actually paid, a retention bound.

Added (no behavior change):
- `timing_log` table (one row per bought panel bet): hours before start, bucket (`live`, `lt1h`, `1-6h`, `6-24h`, `24h+`),
  full-auto flag, league, kind, price at build, price at buy, game-time close, CLV on build and on buy, stake, fees (ledger,
  real bets), result, pl, pl_real. Written by `timing_log_pass`, called at the very end of `panel_settle` (every 5 minutes),
  never from the buy path. It uses only data already on disk (no Kalshi or other network call). Every failure is swallowed and
  printed to the console only. Bounded: at most 200 rows written a pass, rows older than 120 days or beyond 20,000 trimmed hourly.
- `tools/timing_report.py` (read-only, `--db FILE` or `--prod`): net dollars after fees, ROI, CLV and sample size by bucket
  and by league, real and paper apart, groups under 20 settled bets flagged TOO FEW. Falls back to the saved panel bets when
  `timing_log` is empty, so it also covers history from before this change (full-auto flag and fees unknown there).
- Skipped ideas are not duplicated: the gate's skips are already scored with price, kick and result in `exit_shadow`.
- Tests: `tests/suite/t_timing_log.py` (bucket boundaries to the second, missing data, rows, idempotence, trimming, failures never raise).
