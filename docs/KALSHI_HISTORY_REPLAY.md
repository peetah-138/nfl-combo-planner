# Kalshi history replay (offline research)

Question: using Kalshi's own public history of settled single-game markets, do any simple sell rules beat just holding to
the final whistle, after the entry fee, the exit fee and the bid-ask gap? This is OFFLINE research. It changes nothing in
the app's trading code, never runs the watcher and never touches `~/combowatch`, the history DB or `combo_*.json`.

## Run it

```
python3 tools/kalshi_history_replay.py fetch --sports NFL NBA --kinds game        # winner markets
python3 tools/kalshi_history_replay.py fetch --sports NFL NBA --kinds spread total
python3 tools/kalshi_history_replay.py report --sports NFL NBA --out summary.json
```

`fetch` is resumable (cached files are skipped). `report` only reads the cache and prints; `--boot N` lowers the number of
bootstrap draws for a quick look. Data lives OUTSIDE the repo in `~/dev/research/kalshi-history/` (`--cache` changes it).

## Network rules (enforced in the code and tested)

- Only Kalshi's public, unauthenticated GET market-data paths (`/historical/cutoff`, `/historical/markets`, `/markets`,
  `/series/...`). Any other path (portfolio, orders, anything else) is refused before a request is made.
- No keys, no login, no signing: the only headers sent are `User-Agent` and `Accept`.
- At most one request per second (1.1 s gap), back-off on 429 and 5xx (doubling, honours Retry-After), every response
  cached on disk.

## Kalshi terms

The kalshi.com legal pages returned 429 when fetched and could not be read, so the terms were NOT reviewed. Kalshi's API
docs say unauthenticated requests have separate, unpublished rate limits and to back off on 429, which the client does.
Until the terms are read: the data stays local, nothing is redistributed, and the repo holds aggregate numbers only (no
tickers, dates per game, or raw candles).

## The model

- Entries (one per market): T-24h, T-4h and kickoff+30m, taken at the ASK of a candle at most 10 minutes old, only if the
  ask is 10-90c. Price buckets 10-30, 30-60, 60-90c.
- Exits at the BID. Fee `ceil(7 * n * p * (1-p))` cents for n = 100 contracts, on entry and on any early exit.
  Settlement is free. A tie settles at the market's settlement value.
- Rules: hold; sell when bid >= all-in cost + 3/5/10c (first candle that qualifies); sell at T-1h or T-15m before the
  start if bid > cost; "fair" filter (below).
- Lag: the exit fills at the bid of the candle 0, 60 or 120 s later (1-minute candles, so 30 s cannot be tested). If it
  cannot fill, it holds.
- Metric: net cents per $1 staked (ratio of sums). EDGE = rule minus hold on the same entries.
- Game-level bootstrap 95% ranges (a game's winner, spread and total rows, both sides, resample together).
- 70/30 time-ordered split: the rule is picked on the first 70% of games by close time and scored on the last 30%.
- Groups under 20 games are hidden. Data-quality gates print first.
- PASS bar: test edge >= 1c per $1, bootstrap low end above 0, positive in 2+ sports or 2+ separate weeks (weeks with
  >= 10 games), and still >= 1c with range above 0 at a 60 s lag.

## Stand-ins and caveats (read these)

- Kickoff is ESTIMATED as close time minus a typical game length (NFL 3.0h, NBA 2.5h, ...). The report prints how often
  volume after the estimated kickoff exceeds volume before it, as a sanity check. T-1h/T-15m rules and the live entry
  depend on it.
- "Buy only below baseline fair": the baseline is the mid just before the estimated start (a stand-in for a closing
  price). For T-24h and T-4h entries that price is not known at entry, so this is an ORACLE (look-ahead) and an upper
  bound only. It is never picked by the split and never counts toward a pass.
- No depth: candles give top-of-book only, so whether 100 contracts would fill at the bid is untested.
- Survivorship: only settled markets are listed; voided or cancelled markets drop out. Markets with no close time (some
  2025 ones) are excluded, and the gates say how many.
- Correlated rows: both sides and multiple lines of one game are the same bet in disguise. Winner, spread and total
  of a game are bootstrapped together; spread/total keep the 2 most-traded lines per event.
- Many groups are tested, so a few will look good by luck. The 70/30 split, the 2-sport/2-week stability test and the lag
  test are there to cut that; treat a lone pass with suspicion.
- Fee model assumes the standard taker fee on both legs (no maker rebates).

## Measured replacements for the app's placeholders

The report prints, from winner markets: `SB_PRE_VOL` (std of the probit move T-24h to T-5m per day), `SB_PRE_CLOSE` (slope
of the T-4h move on the full move, a stand-in), `SB_SPREAD` (median spread pre-game vs in play, mid 10-90c) and
`SB_LIVE_WIDEN` (live spread over pre-game spread). Compare with the app's `0.12`, `0.5`, `(0.02, 0.04)`, `1.5`. These
are suggestions to evaluate, not changes made here.
