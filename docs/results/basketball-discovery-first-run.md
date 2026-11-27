# Basketball discovery: first run (aggregate results only)

Pre-registration (anecdote list, survivor rule, split design) was committed first, in 6958583, before any result was
read. Method and caveats: `docs/BASKETBALL_DISCOVERY.md`. No per-game data, no raw ESPN rows and no market data are in
this file; the source files stay in `~/dev/research/basketball/` and are not redistributed (hoopR/sportsdataverse,
CC-BY-4.0 but ESPN-derived; ESPN's own terms may be stricter).

**Data span.** Seasons 2019-2026 (2018-19 to 2025-26). NBA: 10,183 games built; modelling from 2020 (2019 spread
unusable, so it is excluded), totals from 2021. Men's college: about 6,000 games per season. Models train on all earlier
seasons and score each of 2022, 2023, 2024, 2025, 2026 (expanding window). NBA closing lines are market lines; college
pre-game margin is derived from ESPN's pre-game win probability and the college pre-game total is a rolling proxy.

## 1. Baseline and richer win-probability models

NBA (about 1,310 held-out games per season): held-out log loss is 0.44-0.48. The boosted baseline is no better than
the plain normal-curve model (paired difference -0.005 to +0.002, within about 2 standard errors), so the NBA has no
demonstrated gain from machine learning on state alone. The richer model (rest, neutral site, pace, crew tendencies,
foul trouble) is not better either: it is worse in four of five seasons (+0.001 to +0.008) and better only in 2024
(-0.002). Calibration error is 0.010-0.018. Permutation importance is dominated by the score-and-time feature
(about 4,500-6,300 x1e-4 log loss), then the pre-game margin (60-200); every other feature is noise (the crew foul tendency
swings from -34 to +28 by season, mean near zero).

College (about 6,000 held-out games per season): log loss is 0.38-0.40. Here the boosted baseline beats the normal
curve in every season (paired difference -0.008 to -0.012, many standard errors), and the richer model adds essentially
nothing (+/-0.001, standard errors of the same size). Calibration error is 0.006-0.012. Importance ranks the same
way: score-and-time (about 6,000), pre-game margin (about 60), then rest, neutral site and pace priors at 5-12, noise
level for the rest.

## 2. Win-probability residual scan

| league | hypotheses | BH rejections | pass stability + size | survivors |
|---|---|---|---|---|
| NBA | 72 | 14 | 11 | 6 |
| College | 73 | 36 | 19 | 7 |

Survivors are almost entirely the baseline's own late-game calibration, not trends. The scanned model is the boosted
baseline: its late leaders win 1-4 points less often than it says and its trailers win 2-5 points more, in both leagues
(four or five of five seasons). This is a property of our model (rows from the same game are correlated, which a boosted
model can fit too confidently), not a finding about basketball; the normal-curve and richer models were not scanned, so
nothing is claimed about them. The only non-calibration survivor is college `own_gain8_last5|ph2` (a team that just
gained 8+ points in 5 minutes then does 1.2 points worse than the model says; same sign in 4 of 5 seasons; the NBA echo
is z -1.9). `own_has_ball` (the team with the derived possession does 0.3-0.5 points better) is significant in both
leagues but below the 1-point size floor, so it is not a survivor; possession is derived and approximate, so treat it as
a measurement artifact until proven otherwise. About 28 of the 73 cells per family are lead-bucket diagnostics and they
inflate the family; the report counts them separately.

## 3. Pre-registered anecdotes (13, own BH family)

| anecdote | league | n games | effect (win-prob pts) | q | verdict |
|---|---|---|---|---|---|
| A5 rested (3+ days) vs back-to-back team, at half | College | 605 | +4.5 | 0.010 | passes the rule, but fragile: the NBA copy is +3.6 on 390 games (one-sided p about 0.03, q 0.81), same sign in only 4 of 5 college seasons, and tournament and neutral-site structure may confound the college sample |
| A7 foul trouble only, at half | College | 7,034 | -1.5 | 0.002 | significant after BH; NBA copy has only 250 games, so not testable there |
| A4 back-to-back team starts 2nd half | College | 750 | -4.0 | 0.011 | significant after BH, failed replication (NBA copy has far fewer games) |
| A12 ball trailing by 1-3 in last 2 min | College | 2,491 | +2.6 | 0.013 | significant after BH, failed replication (NBA copy has far fewer games) |
| A10 10-point run in final period | College | 4,581 | -1.0 | 0.013 | significant after BH, failed replication (NBA copy has far fewer games) |
| the other 8 | both | | within +/-1.5 | 0.07-0.92 | nothing |

In the NBA no anecdote has q below 0.8. The most hyped sportscaster lines (first to 20, halftime leader, big
halftime lead, clutch home team, run momentum) are all null or sub-point.

## 4. Totals (where live pace departs from the pre-game total)

The simple pace projection alone is far worse than the pre-game total early in the game, and the best linear blend puts
about 90-98% weight on the pre-game number in the NBA (near 108% plus 6% pace in college). In college a boosted model
beats the linear blend by about 1 point of RMSE late in the game. Final total minus pre-game total has a standard
deviation of about 17.6-18.2 in the NBA and 17.1-17.8 in college, mild right skew, and very little excess kurtosis
(0.0-0.7), which is consistent with pricing the total on a normal curve.

| league | hypotheses | BH rejections | survivors |
|---|---|---|---|
| NBA | 62 (+5 anecdotes) | 32 | 19 |
| College | 68 (+5 anecdotes) | 60 | 26 |

Most "survivors" are the crude linear baseline being wrong, not a market-relevant finding. A post-hoc, clearly labelled
cross-check scores each cell against the boosted model's residual instead: pace mean reversion (`slow_vs_prior` about
+5 to +6.7 points; `fast_vs_prior` about -5 to -6) survives in both leagues, while the foul, close-game and
crew-tendency cells vanish (effects fall from 2-4 points to about 0). Pace mean reversion is a well-known effect; with no live prices here we cannot say whether a market already prices it. The cells
that vanish may do so partly because the boosted model sees those same features, which does not prove they are noise.

Pre-registered totals anecdote T5, close game late goes over: +3.1 points (NBA, 1,891 games) and +5.7 points (college,
9,072 games), q below 0.001, same sign in all five seasons. Overtime explains most of it. Diagnostic only (overtime is an outcome, so removing those games conditions on the future):
the residual was fit with overtime games in, so every no-overtime cell sits lower by construction. Measured against the
mean residual of all no-overtime games at the same snapshot, T5 falls to +0.5 in the NBA
(1,685 games, SE 0.15; raw +0.7 against a +0.2 baseline) and +0.5 in college (7,820 games, SE 0.07; raw +2.9 against a
+2.3 baseline). That is under the 1-point size floor. The college total is a proxy, so even that is soft. T3 (physical
first half) was pre-registered but dropped: too few games at the required foul level (the report now lists any dropped
pre-registered test; the totals anecdote family is therefore 5, not 6). College T1 (+0.8) and T2 (-0.8) are BH-significant (q 0.001 or below) but under 1 point and do not replicate; T4 and T6 are within
+/-0.6.

## 5. Decay

Over five seasons, the late-lead calibration effects drift by about -0.6 to +0.9 points per season with slope z-scores
mostly inside +/-2 (college `lead_lead3-8|ph3` -2.0 and `lead_trail3-8|ph0` -2.2 is the only pair near the line).
Five seasons has little power, so a flat slope is not evidence the effects are stable.

## What this does and does not say

* There are no live prices in the data. A residual against our own model is a lead to price, never a mispricing, and
  nothing here meets the app's pass bar (issue #484).
* The only pre-registered win-probability survivor (A5) is a college-led result on 605 games from one of 13 tests, with
  a weak NBA echo. Worth re-checking once live prices exist; not worth trading on.
* Late-game overconfidence in our own baseline, derived possession, and linear-baseline totals residuals explain most
  other survivors; an effect that vanishes against a stronger baseline is the baseline's fault.
* College pre-game lines are derived or proxied, possession is approximate, and officials data is partial.
