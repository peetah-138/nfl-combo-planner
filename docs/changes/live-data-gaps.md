# Live data gaps: UFC round and clock from ESPN (issues #14, #25, #21)

**Section:** Fair prices and data (live scores)

**What was already there (checked, not rebuilt).** AHL scores, periods and clocks come from the league's own feed
(`_fetch_feed_scores`, #14). Tennis, EuroLeague and UFC come from Kalshi's public live data (`kalshi_score`,
`display_score`, `KLIVE`, #25). The web page's polling and the Live rebuilds were already sped up in earlier PRs, and
the remaining wait is the feeds' own cache times (`SCORES_MAX_AGE`), which are kept so Kalshi and ESPN are not hit
harder (#21: no further safe display-only change found).

**What this adds: UFC in-fight round and clock.** Kalshi's UFC live data had no in-fight round or clock (the note said
"Round 2 of 3 · no clock"). `espn_mma_refresh(events)` reads ESPN's free `mma/ufc/scoreboard` (the same `ESPN_SITE`
base and the same hub cache as the other ESPN reads): the current board, plus at most `ESPN_MMA_DAYS` (2) dated boards
for fights on days the current board does not cover. It runs from `kalshi_live_kick.run()` only when a UFC market is
held or shown, polls at most every `ESPN_MMA_LIVE` (8 s) while a fight is on and `ESPN_MMA_IDLE` (120 s) otherwise, and
a failure pauses it 60 s (`ESPN_MMA["cool"]`). `espn_mma_parse` turns events into fights keyed by both fighters'
codes; `espn_mma_score(l)` returns leg_score's shape from the pick's side. Detail wording: "Round 2 of 5 · 3:12 in"
(ESPN's MMA clock counts UP, so a decision reads 5:00), "End of Round 2", "In progress" with no round, "Fight over ·
R3 5:00" when finished. `kalshi_score` uses ESPN's answer only when Kalshi has none, or ESPN says in play and Kalshi
does not say post. The live wording is built from ESPN's field names plus a real finished sample (no fight was on air
when it was built); it is unverified live.

**Isolation (unchanged rule).** Display only: `src` stays `"kalshi"`, so the UI treats it as a display feed. Nothing
here is read by `leg_score`, `fetch_scores`, `SCORES_BY`, `pick_state`, `started`, smart sell or any buy, sell or panel
path; no new Kalshi or Odds API call; any error is caught and logged once (`klive_log_once("espn_ufc", ...)`).

**Not added, and why.**
- Tennis from ESPN: its tennis scoreboard lists tournaments, not live set/game state per match we could key to
  Kalshi's tickers; Kalshi's own tennis feed already gives sets, games and points.
- EuroLeague: no free official feed with a stable open API; Kalshi's feed already gives points and clock.
- AHL via Kalshi as a fallback: the league feed is already live and complete; a second source would add a
  disagreement risk for no coverage.

**Tests.** `t_espn_ufc.py` with `fixtures/espn_ufc.json` (a trimmed real ESPN board): parse, both sides, round/clock
wording, finished fights, request counts and cooldown, fallback precedence, and a source check that no money path
reads it. `t_kalshi_live` and `t_robust` pass unchanged.

ROADMAP: none
