# mkt_learn recency-stability veto (issue #345)

**Section:** Fair prices and data (Kalshi's price as fair, on paper, #341 B)

`mkt_learn` keeps a grid weight on the books when it beats Kalshi's mid by `MKT["gain"]` (0.002) and 2 standard
errors over 200+ settled markets. It now also needs the same weight to beat the mid on the newest 30% of that
league/bet type/phase's settled markets **by game date** (`kick`, else the log time; ties by id), `MKT["hold_share"]`.
The log-loss gain on that slice must be above zero, otherwise the weight is 0 (Kalshi's mid alone).

This is a recency-stability veto, **not a true holdout**: the weight is still picked on all the markets, the newest
30% included, exactly as before. It never adds or raises a weight, so every learned weight is either 0 or what the old
rule would have given: it can only make the learner stricter. A truly out-of-sample test is a follow-up issue.

A vetoed weight moves `longshot_leg_fair` from the blend to Kalshi's mid, so it can change which legs fall in the
65-80% band (visible through `vetoed` and `hold_gain`). `MKT["hold_min"]` (30) is inert at `min_n` 200 (30% of 200 =
60); it only matters if `min_n` is lowered.

Each `MKT_W` entry now also carries `hold_n`, `hold_gain` and `vetoed` (true when the in-sample bar was cleared and
the holdout disagreed); `mkt_fair_summary` groups show `hold_gain` and `vetoed`. Picks, stakes, buys and sales are
unchanged (the paper table and the long-shot `mkt_weight` reads only see a weight that is 0 more often, which is the one place
behavior can move; see above).

Not done here (the issue's second sentence): whether the 24 withdrawn carry RFQs a day affect maker quote quality needs
real quote data and cannot be answered from the dev Mac; left open on #345.

Tests: `t_mkthold.py` (books right throughout is earned; right in old games and wrong in the newest 30% clears the
old bar and is vetoed; ordered by game date not id; kick=None falls back to the log time; tied kick breaks by id; mixed
kick/log-time rows; stricter-only across datasets (old rule 0 implies new rule 0); a slice under `hold_min` earns
nothing, distinct from a real veto; under 200 markets is not "vetoed"); `t_panelpipe.py` (the existing earn/not-earn
checks still pass).

ROADMAP: none
