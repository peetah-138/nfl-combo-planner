# Money follow-ups from the independent review: learner evidence per sale, shared guard book reads, ledger fallback, holdout switch (Refs #499, #500, #496, #497, #498)

**Section:** Selling (Flexible sell price, learned selling guards), Fair prices and data (`mkt_learn`), Results (ledger)

Small tightenings and visibility fixes. Nothing here buys or sells, nothing loosens a guard, and Pause, caps, quarter Kelly,
rule 7 and rule 8 are untouched.

- **#499, the learned fallback share counts evidence per sale.** `flex_fb_events` returns ONE entry per sale (its first
  comparable retry, stamped with the sale's last retry time so the next look skips all of them). A sale with 10 retries used to
  be 10 of the 20 cases `FLEX_FB_MIN_N` asks for, so 2 sales could move the share; now 20 different sales are needed. The
  per-league "enough history" pre-check counts distinct positions too. Test: `t_flexlearn.py` (2 sales x 10 retries: no move;
  20 sales: one step; no sale counted twice).
- **#500, `book_depth_shared`.** `max_age=0` is still a truly fresh read (every buy, sale and hedge check keeps it; it
  never reuses a fetch). The two selling-guard reads (`break_ok`, the learned score-age check) call
  `book_depth_shared` (a fetch at most 3 s old, else a fresh read), so repeated guard checks on one ticker in one pass share one fetch. Test: `t_bookshare.py` (fake Kalshi, counts the calls).
- **#496, `ledger_price_paid` fallback.** With no saved `unit_cost` the price per contract is `(cost - sell_fees) / n_bought`,
  the same as the saved value (the row's `cost` includes the selling fee). Display only. Test: `t_storecounts.py` C3b.
- **#497, `mkt_hold` switch and veto log.** New Settings > Money switch "Check the books' weight on the newest games", ON by
  default (`mkt_hold`; in DEFAULTS, `SHARED_KEYS`, `WATCHER_SYNCED`, the watcher's `SYNCED` and `SET_KEYS`, `settings.js`;
  `t_newkeys.py` checks all six). Off = the in-sample bar alone; it never adds a weight the old rule would not give.
  `mkt_learn` prints one line (once per group and result) when it holds a weight back: the group, the in-sample weight and
  why (newest slice too small, or its gain not above 0). The wording fix (it is a recency-stability veto, not a true
  holdout) was already in CLAUDE.md. Tests: `t_mkthold.py` section 7.
- **#498 already done** by #515 (empty legs list refused; hub build-form Buy carries and re-checks the card's legs). No other hub
  Buy path exists in `combo_watcher.py` (`builder.buy` is the only `accept_offer` caller there besides the web app route).
- **Skipped, #501 (learn the loss-cut clock cadence).** The bounds are "to be agreed", and a stuck combo's data holds no
  evidence about any cadence other than the 5-minute one that ran, so there is nothing to learn from yet; it also changes how
  often automatic sales are tried. Needs Pete's floor and ceiling, and a decision to explore other cadences.

ROADMAP: none
