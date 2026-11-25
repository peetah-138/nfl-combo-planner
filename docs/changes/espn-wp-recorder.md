# ESPN win-chance recorder and scorecard (issue #483, proposals 1 to 3; record-only)

**Section:** Fair prices and data (next to the live model and "Kalshi's price as fair"); the Early-exit value test.

**Correction to the brief.** `CLAUDE.md` says ESPN's win chance is football only. That is wrong: ESPN's scoreboard carries a
win chance (`situation.lastPlay.probability`) for **NBA and college basketball as well**, and the summary endpoint's
`winprobability` history exists for them too. The live model (`live_model_chance`) already averages ESPN's chance in for
whatever the feed gives (`sc["wp"]`), so this is only a wording fix; no pricing changes. Which leagues really have it, and
how fresh it is, is now measured (coverage below) instead of assumed. Fold this correction into the "ESPN's football win
chance" sentences when folding this file.

**Nothing here decides anything.** No buy, sell, sizing, price, Smart Buy, panel or guard reads anything this adds (a source
scan test proves it). Pause, rule 8, caps and the Pi are untouched. Everything is append-only, bounded, errors are swallowed
and it runs off the trading path (the panel pass's one wrapped call, and a background thread for requests).

## Tables (new, in the history file; they join on `ticker` + `ts`, no hot-path table is altered)
- **`wp_shadow`**: for a game in play, every side of a game-winner market at most every 60 s (`WPR["every"]`), but the panel pass only runs every ~150 s in play, so in practice a row every ~150 s: ESPN's raw win
  chance `wp`, its play id (`play_id`), `play_age` (seconds since we FIRST saw that play: the scoreboard has no wall clock for
  the last play), `feed_age` (the score cache's age), our pure model chance (`model`, no wp), the 50/50 blend with wp
  (`blend`, both **before** the league's calibration), the engine's live `fair`, Kalshi `bid`/`ask`/`mid`, the lead and the clock
  share left. A row with `wp` empty means that league/game has none (coverage). Built only from scores and prices already in
  memory: **no request**. 30 days / 300,000 rows.
- **`wp_outcome`**: one row per ticker, `yes`/`no`/`void` (void after 3 days unsettled), appended by `wp_resolve` (the watcher's
  history loop, 100 a pass, Kalshi's own results read the same way `resolve_live_fairs` does). Separate so `wp_shadow` stays
  append-only.
- **`wp_hist`**: ESPN's summary `winprobability` history, new plays only (unique on game + play id; home win chance, tie chance, the
  play's wall clock when the summary has it). 45 days / 400,000 rows.
- **`wp_lines`**: ESPN's `pickcenter` line (details, spread, total, over/under prices, moneylines) when it changes. 45 days /
  50,000 rows.
Retention and the row ceiling prune oldest first only (`_wp_prune`, every 6 h). Flags `wp_shadow` and `wp_hist` are real `CFG`
keys, ON by default for recording (a saved false is kept).

## Requests (Proposal 2), exact volume
- **Reused, free:** the football game page already fetches the ESPN summary; that same answer is ingested (`wp_hist_ingest`), no
  new request, and it counts as the game's recent look so the poller skips it.
- **New (key-free public GET of ESPN's summary, `wp_hist_fetch`),** NFL, college football, NBA and men's college basketball only,
  only for a game that has a Kalshi market in the panel's games:
  - in play: **1 per game per 300 s = 12 an hour per game** (the panel pass runs every ~150 s, so each pass serves up to 12 due games);
  - before the start: at most **1 per 2 h**, and only within **4 h** of the kickoff (so 2 at most);
  - **1 final fetch** after the game ends or leaves the panel for 10 min (only if we saw it in play).
  - Global ceilings: **240 requests an hour** across all games, at most 12 queued per panel pass, least recently fetched first, one background thread, 0.5 s
    between requests, 10 s timeout. No key, no login; any error just records nothing.
  - A typical NBA game (about 2.5 h) is about 2 + 30 + 1 = **~33 requests**; a football game about 3.3 h, ~43; the average is ~39. A
    heavy night with 12 followed games in play at once is 144 an hour, under the 240 cap. Pete approves this volume in the PR.
- **Screened-out games are recorded too** (Pete's follow-up): live games the panel leaves out (wide spread, stale or missing score, fair 95%+, fair 8+ points from Kalshi, no buyers, no pre-game line) are passed to the recorder with the panel's reason (`LIVE_WHY`). `wp_shadow.screened` is empty for a game the panel kept, else a short word (`spread`, `stale`, `decided`, `disagree`, `no_buyers`, `no_line`, `no_feed`, `not_in_play`, `over`, `other`); their `fair` is left empty (the engine never priced them). They are followed by the same poller, so they share the same 240/h ceiling, 12 per pass and per-game cadence: more games share the same budget (a very busy night is held at 240/h, least recently fetched first, so the exact per-game numbers above are the ceiling, not a promise for every game). Storage caps are unchanged. Nothing outside the recorder reads them.
- Switch: `wp_hist` (default ON). Off stops the background GETs and the ingest.

## Scorecard (Proposal 3): `tools/espn_wp_scorecard.py`
Read-only (`mode=ro`), no network, aggregates only (no ticker, game id or date), groups under 20 games print "n<20, hidden".
`python3 tools/espn_wp_scorecard.py --out <file>`. Per league it compares ESPN wp, Kalshi mid, our model and today's 50/50 blend on
the same rows and settled games: Brier and log score (lower is better) with a game-level bootstrap 95% range; and net dollars per
$1 staked after the entry fee (the engine's `FEE_RATE`) and the spread (a buy fills at the ask) for one rule, "buy once when a
source is at least X above the ask, hold to settlement", X chosen on the first 70% of games by time and scored on the last 30%.
**Pass bar** (as in `docs/EXIT_REPLAY.md`): a source passes in a league when, held out, it beats the blend by at least 1 cent per
$1, its net is above 0 and its bootstrap range is above 0; it counts only if it passes in 2+ leagues. The scorecard also reports the kept and screened groups apart (each hidden under 20 games, with a count of screened games per reason); the scores headline uses both together, but the pass bar and verdict count only the games the panel kept (screened games are picked for a gap, which would bias an edge); a pooled verdict is shown beside it, informational. Only fully priced rows are scored, so some screened reasons (no buyers, no line) may not appear. A screened game with neither wp nor a model (e.g. soccer) is not recorded. Coverage per league shows
whether it carries wp at all and how old the last play was (median and 90th percentile of the observed play age) and whether the
summary history is recorded. Nothing consumes the result; deciding to use wp in pricing is a later, separate, Pete-approved PR.

## Tests
`t_espn_wp_recorder.py` (rows and fields, throttle, no request, errors swallowed, flags and unchanged inputs, retention and ceiling,
**a source scan that nothing outside the recorder touches the tables and nothing reads them but the resolver/prune**, ingest dedupe
and line-change-only, request rate limits and state rules, the resolver); `t_espn_wp_scorecard.py` (synthetic data with a known
answer: Brier 0.01 vs 0.25, the pass bar needs 2 leagues, hidden groups, read-only byte-identical file, no ticker strings).

## Storage
`wp_shadow` about 150 bytes a row: 2 sides x 1 row a minute x ~150 min = ~300 rows a game, ~45 KB; the 300k-row ceiling is ~45 MB.
`wp_hist` ~100 bytes x ~400 plays a game = ~40 KB a game; 400k rows ~40 MB. `wp_lines`/`wp_outcome` are small. Worst case under
~100 MB in total, normally far less.

ROADMAP: none
