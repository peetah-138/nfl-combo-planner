# Richer in-play comeback model (issue #348)

**Section:** Fair prices and data / Smart Buy (in-play bets); Results page

Follow-up to #341 / PR #347. An in-play bet now needs today's gate (`smart_buy_ok` on the live state) **and** the
comeback model: is a comeback, or a partial one big enough to sell early at a profit, realistic? Stricter or equal only
in this PR: the new model can only hold a bet back, never let one through that today's gate refuses. Letting it loosen
is a later, data-gated step.

- **One entry point:** `inplay_exit_ok(c, sim, now, source)` = `comeback_judge` (old AND new). Used by `live_exit_ok`
  (Buy straight's and Live single ideas' green Buy), `smart_buy_gate`'s live branch (panel, whatever the switch or dial),
  `_buy_panel_bet`'s buy-time live recheck, Best bets' live candidates, and the shadow pass (`smart_buy_shadow` logs the
  verdict for every in-play candidate). Live's in-play Buy ideas (`smart_buy_ideas_gate`) need the comeback verdict on
  the same quote (`cb_verdicts`, table `comeback_shadow`) besides the old one, and are now gated **whatever the Smart
  Buy switch** (before, the switch off let in-play ideas through: a fix, stricter).
- **Features** (`comeback_features`, `_cb_chance`), from the score feeds already fetched (no new request of any kind):
  football: who has the ball, yards to go (`_cb_yards` from ESPN's ball spot), down and distance, as the drive's
  expected points added to the lead of the team with the ball; basketball: pace (points so far vs `CB_PACE`, time left
  scaled 0.75-1.35x) and an opponent's run of `CB_RUN` points in the last 8 minutes (2 points against; optional, from
  the recorded scores, stricter only); hockey: shots on goal (the other goalie's saves + goals) and soccer: an
  expected-goals stand-in (0.30 per shot on target, 0.05 per other shot) and possession, as a shot-share nudge on the
  prior (at most +-0.4 probit, full weight at `CB_SHOTS_FULL`); every sport: the closing line as the prior, then the
  live model and the league's live calibration (`calib_fair(..., table="live_fairs")`). The ESPN scoreboard parse now
  keeps hockey/soccer team stats on the score dict (`stats`/`ostats`, `_cb_team_stats`).
  **Fail closed:** a stale or missing score, no closing line, football with no ball position, NHL/soccer with no shots,
  a spread/total, an excluded sport, a simulator that can't model it, or any error = not ok (no green Buy, no idea, no
  push). Not available in the feeds and so not used: power plays (no scoreboard field), real xG, the AHL's shots
  (HockeyTech feed), so AHL needs only score and time.
- **The league's own recoveries** (`comeback_table`, `_cb_entries`, `comeback_rate`): from `price_path` rows recorded
  **in play only** (a score text that is a moment in play; pregame rows have no score and never enter), per ticker: from
  each lead (in scoring units, `CB_UNIT`, clipped to +-3) and quarter of the game left, did the bid later reach a sale at
  +10% (`SB_GAIN`) after both fees before the end? One vote per game per bucket; a path that stops before the end is
  censored (left out); one market per game (both sides mirror each other), the newest 120k rows. Shrinkage n/(n+20) everyone -> sport -> league toward the model's cash-out chance; borrowed levels
  (everyone, the sport) may only lower it; only the league's own rows raise it. Used once the bucket has 15+ rows
  (`CB["min_n"]`), else the model decides. Rebuilt hourly per process in a background thread (30 days): no gate waits for it; until the first build the
  model alone decides. The recorder now also stores
  the share of the game left (`price_path.frac`, added on start; old rows are read from the score's clock text).
- **Verdict:** `simulate_exit` on the feature-adjusted chance; its cash-out chance replaced by the empirical one when
  used (the sale's share of the expected dollars scaled down with it, never up); sell route at 50%, hold route as today,
  expected dollars at least `SB_EV_MIN`.
- **The other side (Pete, 2026-11-23):** whenever one side of a two-way game is judged in play, its opponent (the other
  market of the event, priced from what the engine already read) is scored with the same model and the full gate (old
  AND new, positive expected dollars after fees, fresh score, gap at most 6c) and logged as **paper only** (source
  `other`). Nothing is ever shown, pushed or bought from it. A leader's price is usually already high, so its room to
  rise is small; the paper record tells us whether leaders priced by Kalshi are worth anything.
- **Which side, game by game (Pete: "a judgement call", paper only):** no hard rule for trailing vs leading. Both sides
  are put on one scale (`_cb_side_score`): the comeback model's expected dollars on $5 after fees (cash-out chance and
  the hold's win chance are both in it) times the league's learned weight (`cb_weight`: realised over predicted dollars
  on its scored in-play rows, shrunk n/(n+30) toward 1 everyone -> sport -> league, borrowed levels only lower it,
  bounds 0-1.5), less half the spread per contract. `cb_pick_side` picks the better side only if it clears the full gate
  and scores above zero, else neither, with a plain reason; logged on the main row (`pick`, `pick_t`, `pick_why`,
  `score`). Nothing reads it to show, push or buy; recommending a side stays behind the full gate and later data. The
  other side is scored only off the tap paths (never on a quote or a buy).
- **Measured:** `comeback_shadow` (one row per bet and source per 10 min: old/new/applied verdicts, the features, the
  model, empirical and blended chances, expected dollars). `comeback_resolve` (in `smart_buy_learn`) scores each single
  on the recorded prices: recovered or not, and dollars on $5 selling at the first profitable chance else held to the
  result. Kept 45 days. Results > What's working > **In-play comebacks** (`comeback_summary`, `analytics()["comeback"]`,
  `cbCard` in `results.js`): per league, checked, predicted (old -> new) vs actual, what the new model held back and how
  those did, the paper side picks and what they would have made, and the other side's paper record. Live's skip line says "Games
  under way: left out" when only in-play ideas were left out (they are gated whatever the Smart Buy switch).
- Never touches selling, sizing, caps, Pause or rule 8; nothing new buys by itself.

Tests: `t_comeback.py` (leakage: pregame rows, pre-game scores and cut-off paths never enter; borrowed-only-stricter
shrinkage; fail closed on each missing feature, stale score, no closing line, errors; a 300-state property test that the
verdict is never looser than today's and pregame bets are unchanged; the features; logging, throttling and the other
side as paper; resolve and the summary; the ideas gate with the switch off; every path uses it; no request).
`t_inplay_exit.py`, `t_live_panel.py`, `t_orderbook.py` stub the comeback layer (they test today's gate).

ROADMAP: "In-play comeback model: after ~2 weeks of `comeback_shadow`, compare old vs new on settled checks per league
and decide (data-gated) whether the new model may loosen; consider surfacing the other side only if its paper record
clears the gate with positive dollars."
