# Kalshi history replay (offline research)

Question: using Kalshi's own public history of settled single-game markets, do any simple sell rules beat just holding to
the final whistle, after the entry fee, the exit fee and the bid-ask gap? This is OFFLINE research. It changes nothing in
the app's trading code, never runs the watcher and never touches `~/combowatch`, the history DB or `combo_*.json`.

## Run it

```
python3 tools/kalshi_history_replay.py fetch --sports NFL NBA --kinds game        # winner markets
python3 tools/kalshi_history_replay.py fetch --sports NFL NBA --kinds spread total
python3 tools/kalshi_history_replay.py report --sports NFL NBA --out summary.json --null 200 --kick-jitter-min 30
```

`fetch` is resumable (cached files are skipped; a candle file cached after a 404 is retried after 24 h). `report` only
reads the cache and prints. `--boot N` lowers the number of bootstrap draws for a quick look; `--null N` runs the
permutation null (below, default off); `--kick-jitter-min M` reruns everything with every kickoff moved by +/- M minutes
and prints whether any pass flips. Data lives OUTSIDE the repo in `~/dev/research/kalshi-history/` (`--cache` changes it).

## Network rules (enforced in the code and tested)

- Only Kalshi's public, unauthenticated GET market-data paths, matched EXACTLY by regex: `/historical/cutoff`,
  `/historical/markets`, `/markets`, `/historical/markets/<ticker>/candlesticks`,
  `/series/<series>/markets/<ticker>/candlesticks`. Anything else (portfolio, orders, `..`, extra segments, any case) is
  refused before a request is made.
- Tickers and series are validated against `^[A-Za-z0-9._-]+$` (never `..`) before they touch a URL or a file name, and are
  URL-quoted with no safe characters.
- A lock file (`.fetch.lock`) in the cache dir stops two fetches from running at once (a dead process's lock is taken over).
- No keys, no login, no signing: the only headers sent are `User-Agent` and `Accept`.
- At most one request per second (1.1 s gap), back-off on 429 and 5xx (doubling, honours Retry-After), every response
  cached on disk. A market list is cached only after a clean last page; an unexpected body, or a market outside the series
  prefix, raises and caches nothing. The historical list wins over the live one.

## Kalshi terms

The kalshi.com legal pages returned 429 when fetched and could not be read, so the terms were NOT reviewed. Kalshi's API
docs say unauthenticated requests have separate, unpublished rate limits and to back off on 429, which the client does.
Until the terms are read: the data stays local, nothing is redistributed, and the repo holds aggregate numbers only (no
tickers, dates per game, or raw candles).

## The model

- Markets are filtered BEFORE any selection: result must be yes or no (voids and scalars dropped), a close time must exist,
  and a missing settlement value is taken from the yes/no result. The gates print how many markets were listed and dropped.
- Entries (one per market): T-24h, T-4h and kickoff+30m, taken at the ASK of a quote at most 10 minutes old (the age of the
  quote itself, not of the candle row that carried it), only if the ask is 10-90c. Price buckets 10-30, 30-60, 60-90c.
- Exits at the BID. Fee `ceil(7 * n * p * (1-p))` cents for n = 100 contracts, on entry and on any early exit.
  Settlement is free. A tie settles at the market's settlement value.
- Rules: hold; sell when bid >= all-in cost + 3/5/10c (first candle that qualifies); sell at T-1h or T-15m before the
  start if bid > cost; "fair" filter (below). A rule only fires on a bid at most 10 minutes old.
- Lag: the exit fills at the bid of the FIRST candle ending at or after (firing candle + 0, 60 or 120 s), and only if that
  bid is at most 10 minutes old; otherwise it holds. (Candles are 1 minute, so 30 s cannot be tested.) The report prints the
  share of exits where a 60 s lag lands on a different candle than lag 0, so a lag test that changes nothing is visible.
- Metric: net cents per $1 staked (ratio of sums). EDGE = rule minus hold on the same entries.
- Bootstrap 95% ranges resample whole (sport, day) blocks: every game, side and line closing the same day for the same sport
  moves together (the game keys of winner, spread and total turned out to be the same string for one game, and the report
  prints how often; day blocks cover the correlation either way).
- 70/30 time-ordered split by day block: the rule is picked on the first 70% and scored on the last 30%.
- Groups under 20 games are hidden. Data-quality gates print first.
- PASS bar, all of: winner markets only (spread/total can never pass, see below); >= 50 games in the group; test edge >= 1c
  per $1 with bootstrap low end above 0; stable, meaning EITHER 2+ sports each with its own range above 0 (every sport is
  scored on exactly the pooled test games with the pooled pick, no re-split) OR at least 70% of at least 3 scored weeks
  positive (a week is scored with >= 10 games); and still >= 1c with range above 0 at a 60 s lag.
- Permutation null (`--null N`): for each single-sport, single-entry, single-bucket winner group that is eligible to pass,
  the per-day-block rule-minus-hold difference keeps its size but its sign is shuffled N times (200 in the real report),
  then the same pipeline runs (pick the best of 5 rules on the first 70%, score the rest, apply the bar). The report prints
  the share of groups that pass this way next to the number that really passed. It uses a normal-approximation range, not
  the bootstrap, and it forces every rule to equal hold on average, so it measures luck from picking and from the many
  groups, not whether fees make true edges negative. It is a sanity check, not a p-value.
- Worse-fill sensitivity: for the headline pick the report also shows the edge when entering at the candle's ask HIGH and
  exiting at the candle's bid LOW (lag 0).
- Fee schedule assumption: the standard taker formula `0.07 * n * p * (1-p)` rounded up to the cent for a 100-contract order,
  on both legs, for every market and date. Kalshi's real fee schedule can differ by market and over time (some series have
  other multipliers or reduced fees), and rounding on a different order size changes the cents. If the schedule differs for
  these series, every number here shifts by that fee difference.

## Stand-ins and caveats (read these)

- Kickoff is ESTIMATED. If the market has an occurrence time and close minus occurrence is between 1.5 and 6 hours, that is
  the kickoff; otherwise it is close time minus a typical game length (NFL 3.0h, NBA 2.5h, ...). The gates print, per sport,
  the median / 10th / 90th percentile of close minus occurrence and of close minus expected expiry, and how many markets used
  each source. On the partial NFL cache the occurrence window almost never applies (the occurrence time is near the close
  time, not the start), so nearly every kickoff is the typical-length estimate. The kickoff check prints the share of games
  where the 30 minutes after the estimated kickoff trade more than the 30 before AND that is the biggest half-hour
  step-up within 3 hours either side; a low share (18% on the partial NFL cache) means the estimate is rough, and the
  T-1h/T-15m rules and the live entry depend on it. `--kick-jitter-min 30` shows whether any pass survives moving the
  kickoff by half an hour either way.
- Spread and total results are SELECTED WITH HINDSIGHT: the 2 most-traded lines per game are chosen using each line's
  whole-life volume, which includes volume after the entry time. They are labelled that way in the report, and any group of
  spread or total markets, and any group that mixes them with winners (type=all), is forced to pass=False with the reason
  "hindsight line selection". Only winner markets can pass.
- "Buy only below baseline fair": the baseline is the mid just before the estimated start (a stand-in for a closing
  price). For T-24h and T-4h entries that price is not known at entry, so this is an ORACLE (look-ahead) and an upper
  bound only. It is never picked by the split and never counts toward a pass.
- No depth: candles give top-of-book only, so whether 100 contracts would fill at the bid is untested.
- Survivorship: only settled markets are listed; voided, cancelled and scalar markets are dropped (the gates count them), and
  markets with no close time (some 2025 ones) are excluded (counted too). If those differ from the rest the results are biased.
- Correlated rows: both sides and multiple lines of one game are the same bet in disguise; the bootstrap and the 70/30 split
  work on (sport, day) blocks to cover that.
- Many groups are tested, so a few will look good by luck. The 70/30 split, the stability test, the lag test, the 50-game
  minimum and the permutation null are there to cut and measure that; treat a lone pass with suspicion.
- Fee model assumes the standard taker fee on both legs (no maker rebates); see the fee schedule assumption above.

## Measured replacements for the app's placeholders

The report prints, from winner markets: `SB_PRE_VOL` (std of the probit move T-24h to T-5m per day), `SB_PRE_CLOSE` (slope
of the T-4h move on the full move, a stand-in), `SB_SPREAD` (median spread pre-game vs in play, mid 10-90c) and
`SB_LIVE_WIDEN` (live spread over pre-game spread), all measured from the estimated kickoff (see the kickoff caveat). Compare with the app's `0.12`, `0.5`, `(0.02, 0.04)`, `1.5`. These
are suggestions to evaluate, not changes made here.
