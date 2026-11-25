# mkt_learn held-out check (issue #345)

**Section:** Fair prices and data (Kalshi's price as fair, on paper, #341 B)

`mkt_learn` used to keep a grid weight on the books when it beat Kalshi's mid by `MKT["gain"]` (0.002) and 2 standard
errors over 200+ settled markets, all tested on the same markets it was picked on. It now also needs the same weight to
beat the mid on a held-out slice: the newest 30% of that league/bet type/phase's settled markets **by game date**
(`kick`, else the log time; ties by id), `MKT["hold_share"]`. The held-out slice must hold at least `MKT["hold_min"]`
(30) markets and the log-loss gain on it must be above zero, otherwise the weight is 0 (Kalshi's mid alone). The
check only ever takes a weight away: the weight is still picked on all the markets exactly as before and is never
added to or raised by the holdout, so every learned weight is either 0 or what the old rule would have given.

Each `MKT_W` entry now also carries `hold_n`, `hold_gain` and `vetoed` (true when the in-sample bar was cleared and
the holdout disagreed); `mkt_fair_summary` groups show `hold_gain` and `vetoed`. Picks, stakes, buys and sales are
unchanged (the paper table and the long-shot `mkt_weight` reads only see a weight that is 0 more often).

Not done here (the issue's second sentence): whether the 24 withdrawn carry RFQs a day affect maker quote quality needs
real quote data and cannot be answered from the dev Mac; left open on #345.

Tests: `t_mkthold.py` (books right throughout is earned; right in old games and wrong in the newest 30% clears the
old bar and is vetoed; ordered by date not id; too-small holdout earns nothing; stricter-only across datasets; under
200 markets is not "vetoed"); `t_panelpipe.py` (the existing earn/not-earn checks still pass).

ROADMAP: none
