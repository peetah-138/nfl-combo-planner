# League shadow: settle to dollars, no double counting; mkt_learn true holdout (issues #476, #477, #474)

**Section:** "Per-league learning in shadow" and "Fair prices and data" (mkt_learn)

All of this is record-keeping or stricter-only. Nothing here moves money, and no decision function reads the new table.

## #477 The league blend counted the same results at several levels
`lgsh_rows` (the daily shadow) treated all / sport / league as nested groups, so one game or quote moved the number once
per level. Now each result counts once, at its narrowest level (`_lgsh_minus` takes a group's games without the narrower
group's):
- **cutoff:** the file's `n` are nested counts, so a level's weight is its `n` minus the narrower level's. A thin league's
  entry (not `_cut_own`: under 30 quotes and no step yet) carries its sport's LEVEL next to its own small `n`; it now counts
  for nothing, like a sport still on a borrowed level.
- **calib:** everyone-without-sport, then sport-without-league, then the league's own games, each moved by n/(n+300).
- **record:** the same, on stakes and profit.
Live `calib_fair(code, fair, ticker)` is NOT changed (it subtracts sport from all, but a league's games are still also in
its sport's band when a ticker is named). That is a live fair price, so it is left for review, not changed here.
Tests: `t_leagueshadow.py` (the `#477` lines; they fail on the old nested blend).

## #476 Data a promotion gate can settle to dollars
New table `league_shadow_q`, one row per combo quote (from `quotes`), written by the daily `league_shadow_run` through
`lgsh_log_quotes`. Columns:
`qid` (the `quotes` rowid, unique so a quote is logged once), `ts`, `league` (soccer league, else the sport), `sport`,
`n` (legs), `pct` (price as a share of fair), `stake`, `pays`, `cut_now` and `cut_blend` (the combo cut-off in %, today's rule
and the blended one), `pass_now` and `pass_blend` (1 when `pct*100 >= cut`), `outcome` ('won' / 'lost' once the quote
settles, else NULL), `pnl` ((pays if won else 0) - stake, set with `outcome`).
Dollars for a rule = sum of `pass * pnl` over rows with an outcome; a skipped quote makes and loses 0. Both rules use the
same outcomes, so the gap is only the pass/skip choice.
`lgsh_gate(days=None)` does exactly that sum and returns `{"all": row, "leagues": [row, ...]}`, each row
`{league, settled, dollars_now, dollars_blend, diff, flips}` (`diff` = blend minus now; `flips` = quotes the two rules decide
differently); `{}` when nothing has settled. This is the function the "Ready to promote?" card should read.
Limits (honest ones): the cut-off recorded is the one in force when the daily run logged the quote (up to a day later; cut-offs
move weekly); `pnl` is hold-to-settle, with no early exit or fee; mixed-sport quotes and quotes with no price are not logged;
rows keep 180 days.
Tests: `t_leagueshadow.py` (the `quotes:` and `gate:` lines).

## #474 mkt_learn: a true out-of-sample test, stricter only
`mkt_learn` already vetoed a learned books weight unless the same weight gained on the newest 30% (by game date), but that
weight was picked on all the rows, newest included. Now it ALSO picks a weight on the oldest 70% only and requires THAT
weight to gain on the newest 30% it never saw (`oos_w`, `oos_gain`, also in `mkt_fair_summary` groups). A weight is
still either 0 or exactly what the old rule gave, never a different or larger one, so this can only take a weight away
(a vetoed group falls back to Kalshi's mid, as the #345 veto does) and never adds one. The Settings switch `mkt_hold`
(off = the in-sample bar alone) bypasses both checks, as before. This changes when mkt_learn acts live: STRICTER ONLY.
Not done: the issue's measure-before-change pass on real settled data (the weight is still the in-sample one, not
re-picked on the old 70%) and the `hold_min` question. `hold_min` (30) stays inert at `min_n` 200 (30% of 200 = 60).
Tests: `t_mkthold.py` (the `oos:` lines; the main case fails on the old code).
