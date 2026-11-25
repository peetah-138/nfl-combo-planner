# News and game-context recorder (record only)

**Section:** Smart Buy / "Early-exit value test, phase 1" (beside `signal_shadow`)

Pete chose to record, with zero trading effect, two signal families to test later against the market. `signal_events`
(engine block "signal events", hooks in `panel_collect`, `fetch_scores` and `price_seen_markets`) writes three new
append-only tables in the history file, behind the existing `sig_shadow` flag (ON by default). It makes no Kalshi, Odds API
or ESPN request of its own: it reads the injury cache (`INJ`), `PRICE_SEEN`, the panel's games and the scoreboard records
`fetch_scores` already fetched. A tick runs at most every 20 s (`SEV["tick"]`), writes in one transaction under the history
lock, swallows every error, and nothing in a decision path reads the tables (`t_signal_events.py` F scans for it).

- `sig_news(id, ekey unique, ts, news_ts, league, team, player, pos, kind new|change|removed, old_status, new_status,
  material, game_event, ticker, bid, ask, fair_book, fair_src, px_age)`: one row per injury change. The first read after a
  start only sets the baseline; an empty read is never treated as news.
- `sig_news_fu(news_id, horizon, ts, delay_s, bid, ask, fair_book, fair_age)`, unique on (news_id, horizon): the same market
  at +5/+15/+60 min from the latest price already read; a sample more than one horizon late is dropped.
  `fair_book` (here and in `sig_news`) is stored only when the sharp-book price is fresh (within the recorder's fair-age
  limit); a stale one is NULL while `fair_age` is still recorded. A failed write is retried at the next tick, not lost.
- `sig_ctx(ts, phase pre2h|start, mins_to_start, league, game_event, start_ts, ..., neutral, indoor, venue, home/away rest,
  b2b, g7, travel_mi, tz, wx_temp, wx_wind, wx_precip, wx_text, bids/asks/fair)`, unique on (game_event, phase): written about
  2 h before the start (window 20 to 125 min) and at the start (up to 20 min late). Unknown stays NULL. Travel and time
  zones come from a small static table inside the engine (`SEV_GEO_RAW`, NFL/NBA/NHL; the Air copies only the app files).
- Retention 365 days (`_sev_prune`, hourly) plus a row ceiling per table (60,000 / 200,000 / 80,000) that stops writes and
  never deletes to make room. `create ... if not exists` only, so an existing history file is never altered.
- `tools/signal_events.py`: read-only (`mode=ro`) aggregates-only report (groups under 20 hidden): the news event study and the
  70/30 residual test of context factors against plain sharp fair, with game-level bootstrap ranges.
- Not reused: the watch-all recorder's helpers (its PR was not checked); this block keeps its own small helpers.
- Tests: `t_signal_events.py` (detection without duplicates, follow-ups, NULLs, retention, ceiling, migration, errors
  swallowed, no decision reads, hook counts, no network), `t_signal_events_tool.py` (synthetic history: read-only,
  aggregates only, n<20 hidden, missing tables). Docs: `docs/EXIT_REPLAY.md`.
