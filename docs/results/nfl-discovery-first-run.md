# NFL discovery: first run (aggregates only)

Data: nflverse (https://github.com/nflverse), play-by-play releases and nfldata games.csv, licensed CC-BY-4.0. Credit: nflverse contributors.

- Data: seasons 1999-2026, 7,420 games, 1,211,501 plays. Held-out (walk-forward) seasons 2010-2026: 4,512 games, 739,943 plays. Engine: sklearn.
- Every number below is out of sample: a season is only scored by models trained on seasons that ended at least two seasons earlier.

## 1. How good is the state-only baseline, and what do the extra facts add?

| Model | Log loss | Brier |
|---|---|---|
| baseline_gbm | 0.47421 | 0.15692 |
| richer_gbm | 0.47324 | 0.15744 |
| portable_logistic | 0.47695 | 0.15786 |

nflverse's own win probability (trained on all seasons including these, so not a fair comparison): log loss 0.48202.

Improvement in log loss (positive = the second model is better), with a 95% range from resampling whole games:

| Comparison | Gain | 95% range | Seasons better |
|---|---|---|---|
| richer_gbm vs baseline_gbm | +0.00096 | [-0.00216, +0.00410] | 10/17 |
| portable_logistic vs baseline_gbm | -0.00275 | [-0.00675, +0.00125] | 5/17 |
| portable_logistic vs richer_gbm | -0.00371 | [-0.00808, +0.00043] | 4/17 |

By phase of the game (log loss):

| Phase | baseline_gbm | richer_gbm | portable_logistic |
|---|---|---|---|
| Q1 | 0.59069 | 0.59521 | 0.58816 |
| Q2 | 0.52448 | 0.52617 | 0.52269 |
| Q3 | 0.44616 | 0.44334 | 0.44754 |
| Q4 | 0.34559 | 0.3385 | 0.35835 |
| OT | 0.64124 | 0.65843 | 0.65128 |

Calibration of the baseline on held-out seasons (predicted home win chance vs what happened):

| Predicted | Plays | Mean predicted | Observed |
|---|---|---|---|
| 0.0-0.1 | 70,180 | 0.0482 | 0.0505 |
| 0.1-0.2 | 54,241 | 0.1502 | 0.1633 |
| 0.2-0.3 | 59,181 | 0.2518 | 0.2482 |
| 0.3-0.4 | 64,113 | 0.35 | 0.3388 |
| 0.4-0.5 | 64,980 | 0.4497 | 0.437 |
| 0.5-0.6 | 70,929 | 0.5515 | 0.5533 |
| 0.6-0.7 | 77,412 | 0.6501 | 0.6607 |
| 0.7-0.8 | 79,533 | 0.7511 | 0.7618 |
| 0.8-0.9 | 76,325 | 0.8494 | 0.8431 |
| 0.9-1.0 | 123,049 | 0.9581 | 0.9567 |

## 2. Which extra facts does the richer model lean on?

Permutation importance (held-out log loss gets worse by this much when the group is scrambled; mean over seasons, and how many seasons it is positive):

| Group | Mean | Seasons positive |
|---|---|---|
| rest | +0.000167 | 9/17 |
| venue | +0.000232 | 10/17 |
| weather | -0.000796 | 6/17 |
| referee | -0.000976 | 6/17 |
| qb | +0.001577 | 10/17 |
| pace | +0.009335 | 16/17 |
| scoring_run | +0.000270 | 13/17 |
| penalties | +0.000030 | 10/17 |
| turnovers | +0.000269 | 11/17 |

Refit ablation on seasons [2025, 2026] (log loss increase when the group is left out):

- rest: -0.001109
- venue: -0.004357
- weather: +0.000150
- referee: -0.005393
- qb: +0.000581
- pace: -0.002594
- scoring_run: -0.000752
- penalties: -0.002973
- turnovers: -0.001636

## 3. Situation scan (where is the baseline systematically wrong?)

- Observations: 31,584 (one per game per snapshot clock).
- **Hypotheses tested: 4,937** (cells with at least 150 games, out of 14,723 enumerated).
- Nominal p < 0.05: 1,001 (about 246.9 expected by pure chance).
- Pass Benjamini-Hochberg at 0.05: 331; also >= 2.0 win-probability points: 282; also same sign in >= 70% of seasons: 248 overlapping survivors, which collapse to **12 independent findings** once each found effect is subtracted and everything is rescanned.
- Placebo check (random sign flips per game, 20 reps): BH rejections per rep [0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] (should be about 0).

### Independent survivors (in the order they were found; each one is subtracted before looking for the next)

| # | Situation | Games | Effect (WP pts) | 95% range | q | Same sign | Size is tradable? | Trend |
|---|---|---|---|---|---|---|---|---|
| 1 | With 2:00 left: the leading team (the favorite if tied), when it leads by 15+ and it has passed on 45% or fewer of its plays | 364 | +4.1 | [3.27, 4.91] | 5.95e-19 | 100% of 15 | maybe | holding |
| 2 | With 2:00 left: the leading team (the favorite if tied), when it has the ball and no 10-point scoring run in the last 10 minutes | 1916 | +4.4 | [3.42, 5.35] | 3.83e-15 | 100% of 17 | maybe | holding |
| 3 | With 5:00 left: the leading team (the favorite if tied), when it leads by 15+ and penalty yards are within 30 | 888 | +3.0 | [2.29, 3.71] | 7.96e-13 | 94% of 17 | no, too small | holding |
| 4 | With 2:00 left: the leading team (the favorite if tied), when it leads by 15+ and it has the ball | 744 | -3.5 | [-4.39, -2.5] | 4.86e-09 | 94% of 17 | no, too small | holding |
| 5 | With 10:00 left: the leading team (the favorite if tied), when it leads by 15+ and its pass rate is 46-64% | 901 | +2.5 | [1.67, 3.38] | 1.28e-05 | 88% of 17 | no, too small | retire |
| 6 | With 5:00 left: the leading team (the favorite if tied), when it has the ball and outdoor temperature is 36-60F | 644 | +5.2 | [3.34, 7.13] | 0.000106 | 88% of 16 | maybe | holding |
| 7 | With 10:00 left: the leading team (the favorite if tied), when it has the ball and no 10-point scoring run in the last 10 minutes | 2011 | +3.1 | [1.75, 4.41] | 0.007 | 82% of 17 | no, too small | holding |
| 8 | Entering the 4th quarter: the leading team (the favorite if tied), when it is a division game and its QB has 10+ prior starts | 1434 | +3.9 | [2.19, 5.68] | 0.00987 | 94% of 17 | no, too small | retire |
| 9 | With 2:00 left: the leading team (the favorite if tied), when it has the ball and it leads the turnover battle by 2+ | 681 | +2.5 | [1.35, 3.7] | 0.0237 | 88% of 17 | no, too small | holding |
| 10 | With 2:00 left: the leading team (the favorite if tied), when it is the pre-game favorite and no 10-point scoring run in the last 10 minutes | 2455 | -2.4 | [-3.43, -1.39] | 0.00627 | 82% of 17 | no, too small | holding |
| 11 | With 2:00 left: the leading team (the favorite if tied), when it leads by 15+ and penalty yards are within 30 | 917 | +2.5 | [1.94, 3.09] | 4.17e-14 | 94% of 17 | no, too small | holding |
| 12 | With 2:00 left: the leading team (the favorite if tied), when it has the ball and turnovers are within 1 | 1304 | +2.9 | [1.76, 4.12] | 0.00158 | 88% of 17 | no, too small | retire |

### Closest misses (small p-value but not surviving)

- With 2:00 left: the leading team (the favorite if tied), when it leads by 15+ and it has passed on 45% or fewer of its plays: +4.1 pts (n=364), q=5.95e-19, same sign 100% of 15 seasons
- With 2:00 left: the leading team (the favorite if tied), when it has the ball and no 10-point scoring run in the last 10 minutes: +4.8 pts (n=1916), q=5.95e-19, same sign 100% of 17 seasons
- With 2:00 left: the leading team (the favorite if tied), when it leads by 15+ and penalty yards are within 30: +2.9 pts (n=917), q=9.22e-19, same sign 94% of 17 seasons
- With 2:00 left: the leading team (the favorite if tied), when it leads by 15+ and no 10-point scoring run in the last 10 minutes: +2.7 pts (n=1166), q=2.12e-18, same sign 94% of 17 seasons
- With 2:00 left: the leading team (the favorite if tied), when it has the ball and it leads the turnover battle by 2+: +5.4 pts (n=681), q=2.2e-16, same sign 100% of 17 seasons
- With 2:00 left: the leading team (the favorite if tied), when it has the ball and penalty yards are within 30: +5.0 pts (n=1353), q=3.06e-16, same sign 100% of 17 seasons

## 4. Pre-registered sportscaster claims

15 claims fixed in the code before the first run, one multiple-testing family of their own (BH over 15).

| ID | Claim | Games | Effect | 95% range | q | Same sign | Verdict |
|---|---|---|---|---|---|---|---|
| A01 | A team leading at halftime wins more often than the numbers say | 4183 | +0.85 WP pts | [-0.33, 2.03] | 0.605 | 71% of 17 | no evidence (indistinguishable from zero) |
| A02 | A halftime lead of 15+ is a lock (the leader is even safer than priced) | 778 | -0.23 WP pts | [-2.11, 1.66] | 0.939 | 53% of 17 | no evidence (indistinguishable from zero) |
| A03 | Never count out a team down 8-14 with 10:00 left: comebacks happen more than priced | 1274 | -0.93 WP pts | [-2.53, 0.67] | 0.65 | 65% of 17 | no evidence (indistinguishable from zero) |
| A04 | In high-scoring games (total 47+) the trailing team comes back more than priced (down 8-14, 10:00 left) | 425 | -1.91 WP pts | [-4.58, 0.76] | 0.605 | 64% of 14 | no evidence (indistinguishable from zero) |
| A05 | Home underdogs of 3+ are better than their price (at kickoff) | 1176 | -0.71 WP pts | [-3.32, 1.91] | 0.892 | 59% of 17 | no evidence (indistinguishable from zero) |
| A06 | A team on short rest (5 days or fewer) against a rested opponent is worse than priced | 9 | - | - | - | - | not testable (too few games) |
| A07 | A team coming off a long break (9+ days) against an opponent on 8 or fewer is better than priced | 985 | +0.40 WP pts | [-2.45, 3.24] | 0.939 | 47% of 17 | no evidence (indistinguishable from zero) |
| A08 | Momentum: a team that outscored the other by 10+ in the last 10 minutes keeps rolling (10:00 left) | 573 | -0.89 WP pts | [-3.63, 1.85] | 0.892 | 41% of 17 | no evidence (indistinguishable from zero) |
| A09 | The turnover battle decides it: +2 or better at halftime wins more than priced | 777 | +1.53 WP pts | [-1.13, 4.19] | 0.65 | 59% of 17 | no evidence (indistinguishable from zero) |
| A10 | Penalty trouble hurts: 30+ more penalty yards than the other team at halftime | 992 | -0.57 WP pts | [-3.08, 1.93] | 0.892 | 59% of 17 | no evidence (indistinguishable from zero) |
| A11 | Division games are tighter: the favorite does worse than priced in division games (at kickoff) | 1487 | +0.65 WP pts | [-1.65, 2.94] | 0.892 | 47% of 17 | no evidence (indistinguishable from zero) |
| A12 | Cold weather helps the home team (outdoors, 32F or colder, at kickoff) | 220 | -0.20 WP pts | [-5.94, 5.53] | 1 | 86% of 7 | no evidence (indistinguishable from zero) |
| T01 | Dome games go over the total | 1246 | +1.35 pts vs total | [0.61, 2.09] | 0.00535 | 82% of 17 | SURVIVES (claim holds) |
| T02 | Windy games (15+ mph, outdoors) go under the total | 359 | -1.19 pts vs total | [-2.51, 0.14] | 0.595 | 50% of 14 | no evidence (indistinguishable from zero) |
| T03 | Freezing games (32F or colder, outdoors) go under the total | 220 | +0.55 pts vs total | [-1.3, 2.4] | 0.892 | 57% of 7 | no evidence (indistinguishable from zero) |

## 5. Decay tracker (effect by season; retire what fades)

| Tracked effect | Pooled | First half | Last 3 seasons | Trend per season | Status |
|---|---|---|---|---|---|
| With 2:00 left: the leading team (the favorite if tied), when it leads by 15+ and it has passed on 45% or fewer of its plays | +4.09 | 5.022 | 3.079 | -0.146 | holding |
| With 2:00 left: the leading team (the favorite if tied), when it has the ball and no 10-point scoring run in the last 10 minutes | +4.38 | 5.08 | 4.155 | -0.009 | holding |
| With 5:00 left: the leading team (the favorite if tied), when it leads by 15+ and penalty yards are within 30 | +3.00 | 3.342 | 1.548 | -0.044 | holding |
| With 2:00 left: the leading team (the favorite if tied), when it leads by 15+ and it has the ball | -3.45 | -3.855 | -3.624 | -0.141 | holding |
| With 10:00 left: the leading team (the favorite if tied), when it leads by 15+ and its pass rate is 46-64% | +2.52 | 2.799 | 1.14 | -0.083 | retire |
| With 5:00 left: the leading team (the favorite if tied), when it has the ball and outdoor temperature is 36-60F | +5.24 | 5.602 | 2.741 | -0.071 | holding |
| With 10:00 left: the leading team (the favorite if tied), when it has the ball and no 10-point scoring run in the last 10 minutes | +3.08 | 2.083 | 5.013 | 0.326 | holding |
| Entering the 4th quarter: the leading team (the favorite if tied), when it is a division game and its QB has 10+ prior starts | +3.93 | 5.37 | 1.914 | -0.223 | retire |
| With 2:00 left: the leading team (the favorite if tied), when it has the ball and it leads the turnover battle by 2+ | +2.53 | 3.694 | 1.289 | -0.142 | holding |
| With 2:00 left: the leading team (the favorite if tied), when it is the pre-game favorite and no 10-point scoring run in the last 10 minutes | -2.41 | -1.644 | -2.453 | 0.012 | holding |
| With 2:00 left: the leading team (the favorite if tied), when it leads by 15+ and penalty yards are within 30 | +2.51 | 2.769 | 1.28 | -0.065 | holding |
| With 2:00 left: the leading team (the favorite if tied), when it has the ball and turnovers are within 1 | +2.94 | 3.755 | 1.161 | -0.083 | retire |
| A01 A team leading at halftime wins more often than the numbers say | +0.85 | 0.818 | 0.61 | 0.076 | holding |
| A02 A halftime lead of 15+ is a lock (the leader is even safer than priced) | -0.23 | -2.192 | 0.981 | -0.353 | retire |
| A03 Never count out a team down 8-14 with 10:00 left: comebacks happen more than priced | -0.93 | -0.952 | -0.741 | 0.075 | holding |
| A04 In high-scoring games (total 47+) the trailing team comes back more than priced (down 8-14, 10:00 left) | -1.91 | -2.649 | -6.64 | 0.345 | holding |
| A05 Home underdogs of 3+ are better than their price (at kickoff) | -0.71 | -1.603 | -6.706 | 0.138 | holding |
| A07 A team coming off a long break (9+ days) against an opponent on 8 or fewer is better than priced | +0.40 | 0.02 | 4.036 | 0.301 | holding |
| A08 Momentum: a team that outscored the other by 10+ in the last 10 minutes keeps rolling (10:00 left) | -0.89 | -3.263 | 2.496 | -0.712 | retire |
| A09 The turnover battle decides it: +2 or better at halftime wins more than priced | +1.53 | 0.378 | -1.556 | 0.112 | retire |
| A10 Penalty trouble hurts: 30+ more penalty yards than the other team at halftime | -0.57 | -1.889 | 3.902 | -0.303 | retire |
| A11 Division games are tighter: the favorite does worse than priced in division games (at kickoff) | +0.65 | 2.873 | -1.553 | -0.378 | retire |
| A12 Cold weather helps the home team (outdoors, 32F or colder, at kickoff) | -0.20 | -7.581 | -0.182 | -0.721 | holding |
| T01 Dome games go over the total | +1.35 | 0.899 | 1.42 | 0.032 | holding |
| T02 Windy games (15+ mph, outdoors) go under the total | -1.19 | -0.154 | -1.746 | 0.078 | holding |
| T03 Freezing games (32F or colder, outdoors) go under the total | +0.55 | 2.407 | 0.724 | -0.197 | holding |

Effect-by-season tables for each tracked item are in the JSON output.

## Plain-English reading (written by hand after the run; the tables above are generated)

- Most candidates fail. Of 4,937 situations scanned, 248 overlapping ones cleared every bar, and those collapse to 12 independent findings. Of the 15 pre-registered sportscaster claims, none of the 12 win-probability claims shows any evidence once tested properly, and one of the 3 totals claims holds (dome games go over the total by about 1.4 points, stable in 82% of seasons).
- The "halftime leaders win more than priced" and "never count out a team down 8-14" claims, which looked nominally significant before the baseline was recalibrated, are indistinguishable from zero in the final run. This shows how easily a slightly miscalibrated baseline manufactures trends.
- Every independent survivor is a late-game situation (2:00 to 10:00 left, or entering Q4). They are deviations from a state-only model, not from the market. The most likely explanation is that the baseline is still a little off in the end-game, where possession and clock management matter and trees are coarse. Treat them as leads to check against recorded Kalshi prices, not as trades. Rows 1, 2 and 6 are the largest (+4 to +5 points) and the only ones rated "maybe" tradable.
- Three survivors are flagged "retire" by the decay tracker (effect fading in recent seasons), so even the survivors are not stable.
- The richer model (rest, venue, weather, referee, QB, pace and so on) does not beat the state-only baseline out of sample (gain +0.0003 log loss, range spans zero). Only game-pace features carry signal in permutation importance, and that mostly restates the score and the clock.
- The placebo scan (random sign flips) gave 0 false rejections in 19 of 20 reps and 5 in one, so the correction is working but not perfect.
- Not covered: injuries, real Kalshi prices (none in the repo fixtures; see the Air-side script), and the partial 2026 season.
