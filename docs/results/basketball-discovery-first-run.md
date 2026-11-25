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
(about 4,500-6,300 x1e-4 log loss), then the pre-game margin (60-200); every other feature is below 30 and many are
negative in some seasons.

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

Survivors are almost entirely the baseline's own late-game calibration, not trends: both the normal-curve and the
boosted model are overconfident in late leads (leaders win less than the model says by 1-5 points; trailers win more),
in both leagues and all five seasons. A bigger boosted model did not fix it. The remaining survivor family is
`own_has_ball` (the team with the derived possession wins 0.3-0.5 points more than the model says); possession is
derived and approximate, so this is a measurement artifact until proven otherwise. Treat these as notes on our
baseline, not as edges.

## 3. Pre-registered anecdotes (13, own BH family)

| anecdote | league | n games | effect (win-prob pts) | q | verdict |
|---|---|---|---|---|---|
| A5 rested (3+ days) vs back-to-back team, at half | College | 605 | +4.5 | 0.010 | survives the rule (only the sign replicates in the NBA: +3.6 on 390 games, q 0.81) |
| A7 foul trouble only, at half | College | 7,034 | -1.5 | 0.002 | rejected by BH, does not replicate |
| A4 back-to-back team starts 2nd half | College | 750 | -4.0 | 0.011 | rejected by BH, does not replicate |
| A12 ball trailing by 1-3 in last 2 min | College | 2,491 | +2.6 | 0.013 | rejected by BH, does not replicate |
| A10 10-point run in final period | College | 4,581 | -1.0 | 0.013 | rejected by BH, does not replicate |
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
crew-tendency cells vanish (effects fall from 2-4 points to about 0). Pace mean reversion is the standard known effect
that any live total already prices.

Pre-registered totals anecdote T5, close game late goes over: +3.1 points (NBA, 1,891 games) and +5.7 points (college,
9,072 games), q below 0.001, same sign in all five seasons. This is almost certainly end-of-game fouling, which a live
market sees and prices; the college total is a proxy, so its size is not trustworthy. T1, T2, T4 and T6 are within
+/-0.8 points.

## 5. Decay

Over five seasons, the late-lead calibration effects drift by about -0.4 to +0.9 points per season with slope z-scores
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
