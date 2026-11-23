# Killer deals and standing orders need an odds-service line (issue #344)

**Section:** Fair prices and data (killer deals and standing orders)

Pete's decision (2026-11-23): with ESPN's free lines working again (#341), `sources_agree` counted ESPN's posted
moneyline and Polymarket as two agreeing sources, so a killer deal could buy, and a standing order could rest, on free
lines alone. Now both also need **at least one odds-service (sharp) line backing the price**: `sharp_backed(snap, pick,
fair)` is true only when the merged snapshot's `parts` for that team hold a `pinnacle` or `odds service` chance
(`SHARP_PARTS`) within `KILLER["agree"]` (2 points) of the fair chance used, and the team isn't in `sharp_stale`
(`merge_books` now lists the teams whose sharp line was too old and gave way to a fresh free line, so a stale sharp
line never counts). No snapshot, no parts, an unknown team or junk = not backed (fails closed).

- **Killer deals:** `killer_check` adds the reason "<pick>: only free lines (ESPN, Polymarket) back this price; needs an
  odds-service line" (`NEED_SHARP_WHY`) for every leg without one, so the deal is held back and logged ("near-killer ...
  held back: ...") as other reasons are. Both `killer_act` call sites (combos in the shadow's quotes, singles in
  `single_pass`) sit behind `killer_check`.
- **Standing orders:** `maker_pass` skips a free-only candidate after the two-source rule (no order, no row, also in
  watch mode) and logs "standing orders: N left out, ..." at most once per 10 minutes (`_CAP_LOGGED["maker_sharp"]`).
  An order already resting whose price lost its odds-service backing is **cancelled** (`maker_cancel`, "no
  odds-service line behind the price any more"); a cancel is the only Kalshi write this adds.
- Sharp-backed prices are treated exactly as before. `sources_agree` itself is unchanged. Low-credit mode (#175)
  means far leagues fall back to free lines, so standing orders there wait until the odds-service line is back.

Stricter only: never a new buy, order or stake; caps, Pause, rule 8, sizing and selling untouched. Tests:
`t_needsharp.py` (free-only = skip with the reason, stale sharp = skip, sharp-backed = unchanged, a resting order is
only cancelled, no Kalshi POST in any free-only path); `t_profit2.py` C now gives its standing-order fixture a sharp line.
