# Kalshi history replay: first run (aggregates only)

Tool: `tools/kalshi_history_replay.py` (see `docs/KALSHI_HISTORY_REPLAY.md` for the model and caveats). Run on 2026-11-24
over Kalshi's public settled markets. No tickers, per-game dates or raw candles are kept here.

## Data-quality gates

| | NFL winner | NBA winner |
|---|---|---|
| Settled markets listed | 1,090 | 3,552 |
| Dropped: void/scalar (survivorship) | 14 | 6 |
| Dropped: no close time | 66 | 148 |
| Games replayed | 505 | 1,699 |
| Date span | 2025-08-01 to 2026-11-24 | 2025-04-16 to 2026-11-25 |
| With 1-minute candles | 99.8% | 100% |
| With spread/total candles | 0% (not downloaded) | 0% (not downloaded) |

About 45 MB cached locally (4,586 candle files). Spread and total markets were NOT downloaded: their lines are picked
by full-life volume (hindsight), so they can never pass the bar, and at 1 request a second they would add hours. Only
winner markets are in these results. NHL, MLB and college sports were not run.

Kickoff is not in the public data. Kalshi's occurrence time sits within minutes of the close time, so kickoff is
ESTIMATED as close minus a typical game length. A check (does the biggest half-hour volume step-up fall at the estimated
kickoff?) agreed in only 17% of NFL and 20% of NBA games, so the estimate is rough. Anything timed off kickoff (the
T-1h and T-15m sells, the live entry, the measured spreads) is soft.

## Headline (plain English)

Net result per $1 staked, after fees, buying at the ask and selling at the bid:

- Holding to the end loses money on average: about -4 to -5c per $1 (NFL -4.0 to -4.5, NBA -4.3 to -5.4). That is the
  fee plus the bid-ask gap.
- "Sell at +3c, +5c, +10c": clearly WORSE than holding in every sport and entry time (edge about -4 to -5c per $1, ranges
  entirely below zero). Taking small gains early gives up more than it saves; the two fees eat it.
- "Sell before the game if the bid is above cost" (T-1h, T-15m): roughly break-even against hold (edge between -2c and
  +1c per $1). Not a reliable gain.
- "Buy only below the pre-game price" looks great (+6 to +11c) but is an oracle for early entries: the pre-game price
  is not known at entry. It shows how much the market moves, not a tradable rule.
- Pass bar (>= 1c per $1 over hold, range above 0, 2+ sports or enough separate weeks, still works at a 60 s lag): 1 of
  72 groups passed. That one is NBA, T-4h entry, price 10-30c, sell at T-15m: +10c per $1 on 196 test games (range
  +3 to +17). It is not credible: it is a single cell of 18, a random-shuffle test gets at least one pass 17% of the
  time, it passes on weekly consistency inside ONE sport (no second sport agrees), and it FAILS when kickoff is shifted
  by 30 minutes either way. Treat it as noise until a second sport and a real kickoff time say otherwise.

Honest bottom line: no early-exit rule beats hold-to-settlement in a way this data can confirm. The +X cent rules lose.

## Measured replacements for the app's placeholders

Measured on winner markets, 1-minute candles, with the rough kickoff estimate:

| App placeholder | App value | NFL | NBA | Confidence |
|---|---|---|---|---|
| SB_PRE_VOL (probit std per day, T-24h to T-5m) | 0.12 | 0.215 | 0.214 | medium: the two sports agree |
| SB_PRE_CLOSE (slope, a stand-in) | 0.5 | 0.04 | 0.37 | low: sports disagree, definition is a stand-in |
| SB_SPREAD pre-game / in play (median, mid 10-90c) | (0.02, 0.04) | 0.01 / 0.01 | 0.01 / 0.01 | low: median spread is 1c both ways |
| SB_LIVE_WIDEN (live / pre-game spread) | 1.5 | 1.0 | 1.0 | low: kickoff estimate rough, 1c is the minimum tick |

Medians hide fat tails (spreads widen at big plays); a percentile view is needed before changing SB_SPREAD or
SB_LIVE_WIDEN. SB_PRE_VOL looks like it should be about twice the placeholder.

## What this does not tell us

Whether size would fill (no depth), real kickoff times, spread/total markets, other sports, any strategy more selective
than these simple rules. Many groups were tested, so lone wins are likely luck. No terms of use were read (pages
returned 429), so the data stays local and is not redistributed.
