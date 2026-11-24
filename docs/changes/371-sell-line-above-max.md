# No sell line above what a bet can pay (issue #371)

**Section:** Selling: smart sell everywhere (and Live page)

Pete (2026-11-23): Live said "🤖 Smart sell · sells at $14+" on a bet that pays $13. A bet can never sell for more than
it pays, so that line could never be reached: a nonsense number on the screen and a rule that silently never fires.

- **Where it came from.** The singles chip (`ssChip`, `watcher/spa/live.js`) showed `sell_at` from `open_singles`,
  which is `single_sell_reason`'s hold line when it doesn't sell: exit_policy's `floor2 = max(q·P − λ·P·√(q(1−q)),
  floor × cost)`. The profit floor is 1.2–2.0× cost, so for a single bought above about 1/floor (≈ 67¢ at 1.5×)
  `floor × cost` is over the payout (13 contracts at 70¢ = $9.10 paid × 1.5 = $13.65, shown "$14+"). Combos had the same
  problem: `wait_threshold` adds `model_cushion` (2% a pick, ≤ 15%) on top of `wait_value`, so with near-certain picks
  left it goes over `pays` (Live's "Sell after next game at $X+" and "sell at $X+", `plan_words`' "Worth cashing out at
  about $X", the Pythonista card's "sells by itself if Kalshi offers about $X or more").
- **The ceiling** (`sell_top`): Kalshi's top price is 99¢ a contract (`SELL_TOP`), so a combo can sell for at most
  `pays × 0.99`; a single at most `n × (0.99 − single_fee(0.99, n))` (its line is compared with its value after the
  fee). `sell_line_shown(line, top)` gives `(line, False)` when a sale could reach it, else `(None, True)`.
- **What the screen says when the line can't be reached:** no number. The singles chip reads "🤖 Smart sell · holding
  to collect $13" (`sell_over`); a combo reads "Sell after next game · No offer can beat it" / "· no offer can beat
  waiting" (`thr_over`); `plan_words` says "No offer can beat that: it pays $13 at most."; the Pythonista card says it
  "won't cash out just to beat the next game: no offer can beat waiting … Your other sell rules still apply" (only
  Let it ride's line is out of reach; smart sell's lock in / take profit / guarded cut loss still run on combos). A reachable line is shown exactly as before.
- **Display only; no sell decision changes.** `exit_policy`, `single_sell_reason`, `take_profit_reason`,
  `wait_threshold`, `auto_sell_now`, `plan_cashout`, `tp_ladder` and `cash_nudge` still compare offers with the
  unclamped line, so nothing sells that didn't before and nothing sells below smart sell's floor (clamping the line
  down to the ceiling would have let offers near the top clear a bar they can't clear today). Where the line is out of
  reach the smart-sell profit route simply never fires, as before; lock in, take profit and the guarded loss rules are
  untouched. `v["moment"]` needs an offer ≥ 97% of its line, so it can't appear for an unreachable one; `tp_ladder` is
  already capped at 97% of the payout and sits behind `RESTING_SELLS_OK = False`.
- **Rounding, stale payout, flips and hedges.** Sell lines now show cents (`cents()` in live.js; `$x.xx` in
  `plan_words`/`cash_block`): `money()` rounds anything from $10 up to whole dollars, so a reachable $12.70 line on a
  $13 bet would still have read "$13+". The payout isn't stale: a combo's `pays` is its contracts held, rebuilt from
  the account on every refresh (`MINE["hold"]`), and a single's is its contracts from the same positions read, so a
  partial sale or a leg change is picked up on the next read. A NO-side single uses the same ceiling (test A checks
  both sides). A hedge is a separate single with its own contracts and its own chip; it doesn't change the combo's
  `pays`, so each line is checked against its own payout.
- **Follow-up for Pete (profit, not changed here):** for any single bought above about 1/floor, smart sell's profit
  route can never fire (many favorites); whether the floor should be capped at what the bet can reach is a strategy
  decision, filed as #375 (`profit`). Wording polish: #376 (`fun`).
- Tests: `t_sellmax.py` (Pete's $13 bet on both sides, a combo with near-certain picks left, reachable lines unchanged,
  the ceilings, and that no sell decision reads the new helpers); `test_singlesell_ui.py` checks the chip on the page.

ROADMAP: none
