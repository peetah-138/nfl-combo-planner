# Basketball discovery (NBA and men's college): offline research, not a trading change

This is **offline research**. Nothing here is imported by the app, the watcher or any trading code, and nothing here
changes a buy, sell or size decision. The code is in `tools/research/`; the data lives **outside the repo**
(`~/dev/research/basketball/`) and is never committed.

The question: using play-by-play, closing lines and officials for the NBA and men's college basketball, is there any
**systematic, out-of-sample, repeatable** pattern that a plain live win-probability model or a plain pace projection
for totals misses? The expected answer is "mostly no": most candidate trends are noise or are already priced.

## What is NOT shown here (read this first)

- **A residual against our own model is not a market mispricing.** The data has no live market prices. A segment that a
  model of game state under-predicts could still be fully priced by a live market. The app's pass bar (issue #484: net
  dollars after fees and spread, 95% game-bootstrap above zero, 70/30 time split, 2+ leagues, survives 30-60 s of lag, a
  multiple-testing guard) needs live prices and is **not** met by anything in this document. A survivor here is a
  *lead worth pricing*, never an edge.
- **College has no market line in the data.** The college "pre-game strength" is ESPN's pre-game win probability turned
  into an approximate point margin, and the college "pre-game total" is a rolling team-scoring proxy (tagged
  `pre_total_src = proxy`). Any college totals finding is about a proxy, not a market total, and a width/shape result
  there (issue #482's normal-curve question) is inflated by the proxy's own error.
- **Possession is derived**, not recorded (made shot gives the ball to the other team, a rebound or steal to the taker,
  a turnover flips it, an NBA last free throw flips it). College free-throw order is unknown. Treat it as approximate.
- **Data terms.** The data comes from the hoopR / sportsdataverse release files (labelled CC-BY-4.0) but they are
  derived from ESPN. We keep the files local, do not redistribute them, and do not commit them or any row-level extract.
  Only aggregate results are published (`docs/results/basketball-discovery-first-run.md`). stats.nba.com and
  cdn.nba.com are not used.

## Data and quality

Seasons 2019 to 2026 (2018-19 to 2025-26; "season 2026" means 2025-26). Per league: play-by-play, schedule, officials.
NBA closing lines come from a separate odds file (`nba_closing_lines.parquet`, 2020 onward). Quality rules (each count is
reported by the builder): the play-by-play must end on the schedule's final score and cover regulation (else the game is
dropped); the NBA All-Star game (impossible totals) is dropped; duplicate college foul rows are removed.

- NBA spread: closing-lines file first (`pre_margin = -home_point`); the play-by-play spread field is only used where it
  agrees with the final margin (2020-2022). For **2019 it does not** (correlation about -0.2), so NBA 2019 has no usable
  pre-game line and is **excluded** from NBA modelling. NBA totals need the market total, available 2021 onward (2020 is
  15% covered), so NBA totals models train from 2021. 2020 is the bubble season; it is in training only.
- Rest days come from `game_date`, which is already the US Eastern calendar date (checked against the timestamp: 100%).
  A team's rest is days since its previous game on a strictly earlier date, capped at 7. Back-to-back = rest of 1.
- Rolling team form/pace, and the referee crew features, use only games on strictly earlier dates (shift-by-one;
  referee effects are shrunk toward zero/league mean with k = 30). Nothing uses the label.

## Method (fixed before the first scored run)

**Splits.** Expanding window, per league: train on every season before Y, test on Y, for Y = 2022 ... 2026. All
reported metrics and every scan are on **held-out** seasons only.

**Baseline win probability (state only).** Home win from: score margin, time left, derived possession, team fouls and
bonus flags, pre-game margin (and total where present). Two versions: an analytic normal-curve model
`p = Phi((margin + pre_margin * tl/T) / (sigma * sqrt(tl/T)))` with sigma fitted on training log loss, and a gradient-
boosted tree (HistGradientBoosting) using the same features. Metrics: log loss, Brier, calibration (and ECE).

**Richer model.** Adds neutral site, postseason, rest days and back-to-back flags, recent scoring run (current
unanswered run, margin change over 5 and 10 minutes), scoring pace (so far and prior), foul trouble (players at 4+
fouls NBA, 3+ college), referee-crew tendencies, and the clock. Permutation importance per held-out season (game
constants are shuffled between games, not rows). The richer model is used **only** for importance and the baseline
comparison; it is not the scan's reference.

**Feature whitelist and leakage guard.** `BASE_FEATS` and `RICH_FEATS` are explicit lists; the code asserts no outcome
column (`home_win`, `home_margin`, `final_total`, `went_ot`, `fouls`, ...) is ever in a feature matrix before a fit,
a prediction or a permutation.

**Residual / segment scan.** Residuals are `home_win - p_baseline` on held-out rows, taken from the **baseline** only, so
a segment asks "does this add anything beyond game state?". Segments are viewed from "the team in the segment" (stacked
home and away views; a segment is defined only where it applies to one side, so views never cancel; mirror segments are
not separate hypotheses). Rows inside a game are highly correlated, so each segment is reduced to **one number per game**
(the mean residual in the segment) and the standard error is across games (game-clustered). Effect size is in
win-probability points (x100). Segments cut by game phase (quarter of regulation) and "all".

- Win-probability scan hypotheses (identical names in both leagues): 8 perspective features (back-to-back team only,
  own 10-point run, own gain of 8+ in the last 5 minutes, own team in the bonus only, own foul trouble only, own
  possession, underdog in a fast game, underdog in a slow game) x (4 phases + all), plus home-team x (4 phases + all),
  plus 7 lead buckets x 4 phases (these 28 are **calibration diagnostics of the baseline**, not trend claims).
- Totals scan: 13 features (back-to-back either/both, rested both, neutral, postseason, crew over/under lean, crew
  whistle heavy/light, fast/slow versus prior pace, foul trouble, heavy team fouls) x (4 phases + all), plus close-game
  and blowout cells. Residual is the held-out error of the OLS pace + anchor baseline, in total points.

**Multiple testing.** Benjamini-Hochberg at q = 0.05, **one family per league per question**: (1) win-probability scan,
(2) win-probability anecdotes, (3) totals scan, (4) totals anecdotes. The count of hypotheses in each family is printed.

**Survivor rule (all must hold).** BH q < 0.05; effect at least 1.0 win-probability point (1.0 total point for totals);
at least 100 games; **at least 4 testable held-out seasons (40+ games each) with the same sign in at least 4**; and
**replication**: the same segment in the **other** league has the same sign with one-sided p < 0.05 (a single
pre-specified test, not a second BH pass). A segment with fewer than 4 testable seasons fails; it does not pass by
default. Optional robustness not done in this run: team-season clustered standard errors (game-clustered errors can be
too small for team-attribute segments such as rest).

**Decay tracker.** Effect by held-out season with a weighted slope per season. With only 5 held-out seasons the slope
has little power: a non-significant slope is **not** evidence of "no decay".

**Totals.** On held-out snapshots: points still to come predicted by (a) the pre-game anchor `pre_total * tl/T`, (b) a pure pace
projection, (c) an OLS blend of both plus `|margin| * tl/T` (to absorb end-of-game fouling and garbage time, which the
market prices), then (d) a GBM on the OLS residual with the rich features. `final_total` includes overtime (about 5% of games), so the OT
bump (mean residual of OT games minus the rest) is reported as its own term, together with the SD, skew and excess kurtosis of
the final total about the pre-game total per season. College numbers use the proxy total and are labelled so.

## Pre-registered anecdotes (definitions fixed here, before the first full run)

Each is one snapshot per game, from the perspective of the named team, value = `100 * (outcome - p_baseline)` in
win-probability points, T = regulation seconds (NBA 2880, college 2400), "half" = T/2, "q1end" = 720 s (NBA) / 600 s
(college), "late5" = T - 300 s, "late2" = T - 120 s.

| id | claim as a sportscaster would say it | exact definition |
|---|---|---|
| A1 | The team to 20 first wins | first snapshot where either team has 20+; the team with 20+ while the other has fewer |
| A2 | A small halftime lead is not safe | at half, own margin 1 to 6 |
| A3 | A 15-point halftime hole is too deep | at half, own margin <= -15 |
| A4 | The back-to-back team fades after halftime | at half, own rest = 1 and opponent rest >= 2 |
| A5 | Rested home/own team beats the tired one | at half, own rest >= 3 and opponent rest = 1 |
| A6 | Momentum going into the final stretch | at 0.75 T, own margin change over the last 5 minutes >= +6 |
| A7 | Foul trouble hurts | at half, own foul-trouble player(s) >= 1 and opponent 0 |
| A8 | Team in the bonus down the stretch | at late5, own in the bonus only and |margin| <= 5 |
| A9 | Home team in the clutch | at late5, home team (non-neutral), |margin| <= 3 |
| A10 | A 10-0 run in the last quarter swings it | at or after 0.75 T, own current run >= 10 |
| A11 | A 12-point halftime lead is safe | at half, own margin >= 12 |
| A12 | The ball is worth a lot in the last two minutes | at late2, own possession and own margin -3 to -1 |
| A13 | The first-quarter leader wins | at q1end, own margin >= 1 |

Totals anecdotes (residual in total points): T1 fast first period (pace > 1.10x prior) goes over; T2 slow first period
(< 0.90x) goes under; T3 physical first half (6+ NBA / 8+ college team fouls by half) means more late points; T4 a back-to-back
team in the game at half; T5 a close game (|margin| <= 5) at late5 goes over; T6 a blowout (|margin| >= 20) at half slows down.

## How to run

```
python3 -m venv ~/dev/research/venv && ~/dev/research/venv/bin/pip install numpy pandas pyarrow scikit-learn requests
~/dev/research/venv/bin/python tools/research/basketball_fetch.py          # polite, cached downloads (no stats.nba.com / cdn.nba.com)
~/dev/research/venv/bin/python tools/research/basketball_data.py nba       # builds the game and snapshot tables
~/dev/research/venv/bin/python tools/research/basketball_data.py mbb
~/dev/research/venv/bin/python tools/research/basketball_discovery.py      # trains, scans, writes aggregate results
```

The synthetic test (`tests/suite/t_discovery_synth.py`) plants a known effect in fake data and checks the scan finds it and
leaves null segments alone.
