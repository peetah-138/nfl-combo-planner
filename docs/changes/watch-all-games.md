# Watch all games: recording price paths and signals for every market the app already fetches

**Section:** Fair prices and data (the shadow recorders, next to the early-exit test)

Pete's goal is that the system keeps learning from many games, not only the bets it makes, to get better at prediction and
sell timing (day trading: sell above cost before close, or settle at 100). `broad_shadow(code, every, lc_all)` (engine, one
wrapped line in `panel_collect` after `signal_shadow`) writes a price path and the signals for every market already in
`PRICE_SEEN`, with the sharp-book / live-model / line-model fair and the cached score, into three new append-only tables:
`bp_mkt` (market, game, sport, kind, kickoff, final result and its source), `bp_path` (bid, ask, depth, fair and its kind,
lead, points, share left, state, possession, down, distance; prices in thousandths, `BP_SCALE`) and `bp_day` (counts per day).
It never writes `price_path` (live decisions read that), makes no request, places no order, swallows every error and is
read by no decision: `t_broad_shadow.py` scans the engine and watcher for any mention of the tables outside the recorder.
Setting `broad_shadow` (default on) turns it off.

Storage controls (`BP` dict): change-only rows, at most one a minute from 3 h before kickoff to 6 h after (heartbeat 10 min)
and one every 5 minutes (heartbeat 3 h) otherwise; a flush at most every 45 s, capped at 3,000 rows and 0.15 s, resuming
where it stopped; retention 21 days; oldest-first row cap at 80% of a 250 MB ceiling; recording stops at the ceiling or
under 3 GB free disk and resumes after pruning. Pruning, label copying (from `closes`, `live_fairs`, `line_fairs`,
`mkt_fair`, plus a separate price-implied label, `rs` 9) and the size check run from `resolve_closes` in the history loop
(`bp_maintain`), never the panel pass. The watcher log gets one counts-only line an hour (markets, games, rows today, table
size, labelled share).

`tools/exit_replay.py --broad` replays the fixed exit rules on the broad dataset per sport x price bucket, net of fees and
spread, with a game-level bootstrap and a 70/30 time split, aggregates only (groups under 20 games hidden), read-only.
See docs/EXIT_REPLAY.md. Tests: `t_broad_shadow.py` (bounded, swallows errors, no request, flag off, prune, row cap, size
ceiling, migration of an older file, 30,000-market flush time bound, no reader, bytes a row), `t_broad_replay.py` (the replay
on a database the engine's recorder wrote).

ROADMAP: none
