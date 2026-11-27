# Shadow batch E: paper book chooses like the panel; mkt_learn holdout report (issues #291, #474; #476 and #477 already done)

**Section:** "Smart Buy" (paper book) and "Fair prices and data" (mkt_learn)

Paper and record only. No buy, sell or sizing change, no new automatic money movement.

## Already done, skipped
- **#476** (store what the promotion gate needs): shipped in PR #549 (`league_shadow_q`, `lgsh_gate`, dollars after Kalshi's fee,
  hold to settle). See `league-shadow-gate.md`. Nothing more to do here.
- **#477** (blend double-counts evidence): shipped in PR #549 for the shadow measurement (disjoint all-minus-sport,
  sport-minus-league counts; a thin league's copied sport level counts for nothing). Live `calib_fair` is deliberately unchanged.
- **#474**: the stricter-only oldest-70% / newest-30% test shipped in #549; only the measurement report is new here.

## #291 Smart Buy paper book picks like the real panel
`sb_paper_build` now applies `choose_panel`'s overlap and share rules when it decides which paper bets are "bought":
- one straight bet per game and family (a winner and a spread are one family, a total its own; `bet_family`),
- spreads/totals at most `max(2, int(PANEL["size"] * PANEL["line_share"]))` (3) a day per budget,
- at most `PANEL["size"]` (10) bets a day per budget (stakes and extras each),
- still best expected dollars first, at most 2 a game, inside the day's budget (stakes and extras each).
A bet the rules drop is still scored (its row stays, stake 0), so the CLV, skip and settled counts are unchanged; only the
staked dollars and the graduation line's "ahead" follow the panel's discipline.
Not modelled (the docstring and CLAUDE.md say so): the ahead floor (needs `_sim_panel`), the fill cap (book depth is not
recorded in `exit_shadow`, so "cap by depth where known" has nothing to read), buying at approval time (it still uses the last
check before the game). It stays a progress line, not a gate. Paper only: nothing here buys or sizes a real bet.
Tests: `t_shadow_e.py` (the `#291` lines).

## #474 mkt_learn holdout: measurement report only
`mkt_holdout_report` reads the cached `mkt_learn` result (never re-runs it, changes no weight) and counts, over groups with
at least `min_n` markets: groups whose weight picked on the oldest 70% gained on the newest 30% (`oos_pass`), earned groups the
holdout refuses (`oos_refuses`), the mean out-of-sample gain, and slices under `hold_min` (`under_hold_min`; 0 at min_n 200,
so `hold_min` is inert as the issue noted). It rides along in `mkt_fair_summary` as `holdout`.
The score is log loss under Kalshi's mid, not dollars: a dollar figure for a probability model would need an invented stake rule.
Out of scope still: letting the oldest-70% weight replace the live weight (changes live fair prices; needs the measure-first
pass on real settled data, which this report supports).
Tests: `t_shadow_e.py` (the `#474` lines).
