# Held to the end: how it has done, on Results (issue #461)

**Section:** Results page (profit scoreboard, "How it ended" tab)

Pete saw the "How it ended" breakdown, concluded that holding to the end has a poor record, and wants smart sell to
become aware of it. He chose to show it on Results first while the paper test (`tools/exit_replay.py`) measures it.
**Display only: no buy, sell, sizing or gate decision changes and nothing moves money.**

`profit_board()` adds `periods[*].held` (from `_held_facts` + `_held_summary`, both read-only; the existing groups and
the "vs holding" column are untouched). The tab shows:
- above the table: `Won 5 of 17; at these prices you needed about 3 in 4 to break even`, the break-even being the
  average cost per $1 of payout (`_in_n` turns it into "N in M" or a percent), tagged `small sample` under
  `BOARD_FEW` (20) bets;
- below it (so under "Held to the end: lost"): **Could have been sold higher**, `N of M traded above what you paid
  before closing (best bid beat cost by $a to $b)`, plus how many had no price history. Also tagged `small sample`.

Data: only what the app already stores. A combo's payout comes from `bets.pays` and its best price from its real
`offers` (the same source as the "rode to the end" line); a single bet's contract count is not kept in the ledger, so
its price paid is unknown: it counts as "no price history" and is left out of the break-even (counting only the
winners would bias it). No division by zero: no payout known gives "no break-even", no bets gives no line.
Recommended follow-up: store each bet's contract count in the ledger so singles can be priced too.

Tests: `t_heldlosers.py` (the rate wording, every empty and zero case, board end to end),
`test_scoreboard.py` (the lines on the page, phone dark and light).
