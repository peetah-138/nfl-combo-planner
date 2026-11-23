# Cover the early games: dead combos are worth $0, fees counted, and a lean variant (issue #340)

**Section:** Results page ("Cover the early games" paper test, #74)

**The bug.** `_cover_resolve` valued each later checkpoint on its own (only that slot's picks), so a survivor that had
already lost a later pick still showed worth at the next checkpoint, and smart sell's replay (`sim_exit`) could "sell"
it on the lost pick's last recorded (stale) price (ticks stop once a market leaves 2-98%). Now every later checkpoint
is rebuilt from Kalshi's results each pass, in slate order: worth = what a cash-out would get given every pick settled
so far (the full payout, with no cash-out discount, once nothing is left to play); the first lost (or tied) pick marks the
combo dead (`lost`, `alive: false`) and that checkpoint and every one after are worth $0. The replay stops where the lost
pick was last seen alive (`sim_exit(c, until=)`: new optional cut-off, default unchanged; the last tick in 2-98%, else
the game's kickoff), so a dead combo is never sold. The replay is one sale, shown once (it was copied to every
checkpoint). The survivor's early legs (already won) now start the replay at 1.0 instead of their pre-kickoff price,
which had understated every recorded value by that price; `pays` still uses the prices it was bought at.

**Fees.** Costs now include Kalshi's taking fee on every combo (`_cover_fees`: each combo's price = its legs' product
over `r_buy`, `single_fee` rounded up per order; past `COVER["max_games"]` the ceiling 7% x stake). `sim_pl`,
`beat_cost` and the one-sided baseline count them (`fees_both`, `one_sided_cost`).

**Lean variant (paper).** `cover_lean_split`: of the earliest checkpoint's games, only the close ones are covered both
ways (favourite's Kalshi chance under `COVER["lean_fav"]`, 75%, Pete's start; a constant at the top, to tune once weeks
of results exist); a lopsided game's favourite is carried in every combo. Lean and full carry the same survivor when it
lives, so they differ in cost (2^k combos plus fees) and in lopsided upsets (one kills every lean combo). The result
JSON gets `variants: {full, lean}` (k, combos, stake, fees, cost, result, pl, alive; lean also thr, carried, upset),
`value`, `lost`, `v: 2`; no schema change. `cover_math` shows the lean preview before kickoff (`lean`: k, combos,
cost, `p_alive` = chance every carried favourite wins). `cover_summary` adds `fees` and a `lean` aggregate. Finished
weeks from an older version (result without `v: 2`, row under 45 days old) are worked out again once by `cover_pass`,
quietly (no second alert), from the saved slate and Kalshi's results.

**Screen.** Results › edgeBlock's cover card: per finished week a "Cover all | Lean" table (games covered, combos, cost
with fees, came back, profit), a line naming the carried favourites and any upset, checkpoints show "out" once the
survivor is dead, and a "Lean, over N weeks" line next to the headline. Profit numbers are now actually green/red
(`.mini b` painted them ink).

**Isolation.** Paper only: no quotes, orders or money paths; never writes the `panel` table; Pause, caps and rule 8
untouched. Still runs outside `odds.lock`, fully defensive. Tests: `t_cover.py` (the dead-combo checks fail on the old
code; stale-path replay, cumulative worth, fees, lean split/upset, redo of an old week, panel untouched),
`test_cover.py` (both variants, "out", the lean aggregate and note, green/red).

ROADMAP: none
