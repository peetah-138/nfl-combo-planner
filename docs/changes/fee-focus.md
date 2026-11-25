# Fee focus: what fees really cost, and would fewer, bigger bets help (measurement only)

**Section:** Selling > "Early-exit value test, phase 1" (next to `tools/exit_replay.py`)

`tools/fee_focus.py` is a read-only analysis script, one standalone file (it copies exit_replay's read-only helpers, so
it needs nothing else). The Air's updater copies only the app's own files, so `tools/` is not in `~/combowatch`; one line
fetches the script (public code, no key) and runs it (from a full clone: `python3 tools/fee_focus.py --out ~/fee_focus_summary.json`):

```
curl -fsSL https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/develop/tools/fee_focus.py -o ~/combowatch/fee_focus.py && python3 ~/combowatch/fee_focus.py --out ~/fee_focus_summary.json
```
 It opens `combo_history.db` with the same read-only helper as
`exit_replay.py` (sqlite URI `mode=ro`), never writes to it, makes no network call and needs no key. It prints and writes
**group aggregates only**: no tickers, no dates of individual bets, no order ids, no balances; any cell with fewer than 20
bets prints "n<20, hidden". Missing tables or columns print "skipped: ..." for that part and the rest still runs. It is
descriptive: nothing in the app, no buy, sell, sizing, cap or gate reads it, and no live behaviour changes.

**Part A, fees (ledger).** (1) Recorded entry fee vs the standard `ceil(0.07 x n x p x (1-p))` per order, by single vs
combo, both against the unrounded and the cent-rounded formula (this answers the open "what do combos pay" question; the
combo ratio is exact on single-fill rows, `nf == 1`; zero-fee combos stay in the sample, so a true "combos pay no entry fee" shows as a ratio near 0 and Part B then uses that ratio). (2) Fee as % of stake by stake bucket ($0-1, 1-2, 2-5, 5-10, 10-25,
25+) and price bucket (<15c, 15-30, 30-60, 60-85, 85+), and the rounding excess (the cent round-up) as % of stake.
(3) Round-trip fees for bets sold early vs held, per bucket, and whether rebates or refunds show (negative or zero fee
rows; the ledger keeps only fee totals, so a refund netted inside a positive total is invisible).

**Part B, few strategic bets.** Net return per $ staked after fees, with game-level bootstrap 95% ranges, by grade, EV
quartile, stake bucket and bets that day (1-2 / 3-5 / 6+), on the real ledger and on the settled `sb_paper` book (every
paper bet re-scored at the app's flat $5 with whole contracts and the fee rounded up; combos use the Part A ratio).
The same grade and EV cuts are also run on the REAL ledger bets that the paper book scored too (matched on the sorted leg
tickers; `real_bets_by_paper_grade_and_ev`). Then the what-if: only the top N (1, 2, 3, 5) bets a day by EV, at 1x, 2x and 3x the paper stake, fees recomputed with
rounding. The rule is picked on the first 70% of days (best per-dollar among the 2x and 3x rules) and scored on the last
30%; `paper_book_as_staked` (the paper book at its own stakes, not real P/L) is printed beside it.

**Caveats the output states.** Lost singles have no recorded size unless a `sell_log` row exists, so price-bucket and ratio
cells lean toward won and sold rows. `ledger.fees` sums over fills (ratio exact only for one fill). `sb_paper` covers
about 60 days, is a different population from real buys, and its recorded `plain` uses the app's unrounded fee model.
Top-N cells shrink fast; hidden cells mean "too few to say". A past sample, not a decision.

Tests: `t_feefocus.py` (synthetic history: byte-identical file after, no tickers or dates in the output, cells under 20
hidden, the combo fee ratio read right at 1x and 2x, the 70/30 simulation grid, missing tables and files degrade).

ROADMAP: none.
