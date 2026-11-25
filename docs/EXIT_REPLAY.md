# Early-exit value test (phase 1)

Question: the app values a buy as "what it is worth if I hold to the final whistle". Kalshi lets you sell any time. For
bets the app WOULD buy (its fair above the ask), how much does selling at the bid before the end beat holding, after the
entry fee, the exit fee and the bid-ask gap? Phase 1 measures that on the app's own history and starts recording the
signals a later phase needs. Nothing here changes any buy, sell, size or gate, and nothing new is automatic.

## The one command (on the MacBook Air)

The Air's updater copies only the app's own files, so `tools/` is not in `~/combowatch`. Once this is on `main`, one
line fetches the script (public code, no key) and runs it:

```
curl -fsSL https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main/tools/exit_replay.py -o ~/combowatch/exit_replay.py && python3 ~/combowatch/exit_replay.py --out ~/exit_replay_summary.json
```

(From a full clone it is `python3 tools/exit_replay.py --out ~/exit_replay_summary.json`.)

It takes about a minute, only reads (the history file is opened read-only), makes no network call and never touches the
watcher or any key. It prints the numbers, writes the same to the file and says "safe to send". Send that one small file
to the dev Mac. It holds group totals only: no tickers, game dates, ids, order numbers or balances, and any group with
fewer than 20 bets shows "n<20, hidden".

To check what combos really pay in entry fees (a second one-liner, same safety):

```
python3 ~/combowatch/exit_replay.py --combo-fee
```

Reading it: a ratio near 1.0 per kind means the standard 7% x p x (1-p) taker fee applies; near 0 means no entry fee.
Kinds with fewer than 3 fills are hidden. It is a hint, not proof: confirm on 3+ fills before any code change.

`--db <file>` points at another history file; without it the script uses `combo_history.db` next to the app, then
`~/combowatch/combo_history.db`.

## What the report says

- `data_quality` first: rows per table, days of price history, the share of buys with 10+ path points after the buy and
  with a bid-ask gap seen. Read this before believing the rest.
- `singles`: for the paper book's buys (and real ledger buys with a stored entry price) the price path after the buy is
  walked with fixed rules: sell at +3c / +5c / +10c over all-in cost, at our fair, at one hour or 15 minutes before the
  start if the bid is above cost, or hold. Entry at the ask, exit at the bid, taker fee both ways. Result per rule in
  cents per dollar staked, its edge over hold with a 95% game-level bootstrap range, by kind, price bucket and league.
  Out of sample: the best rule is chosen on the first 70% of games by time and scored on the last 30%. The peak is never
  reported as a result.
- `singles.placeholders`: measured stand-ins for SB_PRE_CLOSE (share of the fair gap that closes before the start),
  SB_PRE_VOL, SB_SPREAD (pre-game and in play) and SB_LIVE_WIDEN.
- `combos`: no price path exists for combos, so this uses Kalshi's real buyback offers (`offers`, `real_offer=1`): the
  real offer-over-hold-value discount (instead of 0.82 / 0.88) and a replay of the cent rules on settled combos, with its
  own range. It is the weakest evidence and is reported apart.

## The shadow recorders (new data for phase 2, write-only)

`signal_shadow` runs once per panel pass, wrapped so any error is swallowed, and writes new append-only tables in the
history file from what the pass already holds in memory (no request of its own):

| Table | What | How often |
|---|---|---|
| `sig_sharp` | sharp-book probability (devig) next to Kalshi's bid and ask, per side | ~60 s per market |
| `sig_related` | bids of one game's win / spread / total markets, side by side | ~2 min per game |
| `sig_state` | score, share of game left, possession, down, distance, total points (games under way, cached feed) | ~60 s per market |

Bounded: rows older than 21 days go, and each table is capped at 300,000 rows (checked every 6 hours). Recording is ON by
default; set `"sig_shadow": false` in settings to turn it off. No decision reads these tables (a test fails if the engine
mentions them outside the recorder).

Combo RFQ offer samples: nothing new added, because the data already exists. Held combos are sampled in `offers` (at
least every two minutes while pending, real Kalshi offers flagged `real_offer=1`) and every quote Kalshi gives for a
candidate is already logged by `store_quote` into `quotes`. A separate sampler would mean extra quote calls, which phase 1
does not do.

## News and context recorder (record only, zero trading effect)

Two more write-only recorders ride the same `sig_shadow` flag (ON by default). They make no request of their own: the
injury lists come from ESPN reads the app already makes (`INJ`, cache only), Kalshi bids from `PRICE_SEEN` (every read
the app already does), the sharp-book probability from the panel pass, and schedules and weather from `fetch_scores`.
A tick runs at most every 20 seconds, one transaction, errors swallowed, nothing in a decision reads these tables.

| Table | What | When |
|---|---|---|
| `sig_news` | one row per injury/lineup change (new item, status change, or removal): time, league, team, player, old and new status, `material` (Out, Doubtful, Questionable and the like), game and ticker when known, Kalshi bid/ask and the sharp probability at that moment, and how old each price was | when a change is seen |
| `sig_news_fu` | the same market's bid, ask and sharp probability at +5, +15 and +60 minutes, from the latest price already read; a sample more than one horizon late is dropped, never faked | follow-ups |
| `sig_ctx` | per game: home flag, neutral-site flag, dome, rest days for both teams, back-to-back, games in the last 7 days, travel miles and time zones crossed (small table inside the engine, pro leagues only), weather from ESPN's field (wind, temperature, precipitation, text), and both sides' Kalshi bid/ask and sharp fair | about 2 hours before the start and at the start |

Unknown stays NULL (never guessed): neutral site, dome, weather, rest and games-in-7-days when the schedule record does not
reach back far enough, and travel when the site is not explicitly a home game. ESPN's scoreboard often has no weather, so
those columns will usually be empty. Retention is 365 days, and each table has a row ceiling (news 60,000, follow-ups
200,000, context 80,000) that stops writes and never deletes to make room.

Report: `python3 tools/signal_events.py --out ~/signal_events_summary.json` (read-only, no network, aggregates only, groups under
20 hidden). Part 1, the event study: after a news event, how far Kalshi's bid moved at +5/+15/+60 minutes next to how far the
sharp probability moved, by league and material or not, with a game-level bootstrap range. Part 2, the residual test: whether
a context factor explains what the sharp probability missed, fitted on the first 70% of games and scored (Brier) on the last
30%, with a game-level bootstrap range. A lone factor "working" out of many tried is more likely luck than signal.
