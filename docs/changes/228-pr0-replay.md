# #228 PR0: the weekly tuner's replay uses exit_policy

For CLAUDE.md (Selling > Smart Buy stage 1 says "`_replay`, the weekly tuner's replay, still has its own copy of the
rule; aligning it is stage 5") and ROADMAP.md, to fold in when the docs are next updated.

## What changed

- `_replay` (used by `smart_tune`, `sim_exit`, the combo lab's and the cover test's replays, and What's working's
  smart-sell replay) no longer has its own copy of smart sell's rule. Each recorded price is turned into
  exit_policy's state (`kind`, `value` = the replay's estimate, `real` 0, `peak`, `pays`, `cost`, `q`, `live` True)
  and settings (`smart` on, `lam` = the replay's risk weight, `floor`, `loss`, `cut_ok` = a guard time from
  `_cut_guard_ts`, `trail`, take profit off, no checkpoint). The bet is sold at the estimate when exit_policy says sell
  **and** the estimate reaches exit_policy's `threshold` (the least live accepts); otherwise it rides on.
- Live selling is untouched: `exit_policy`, `take_profit_reason`, `single_sell_reason` and `auto_sell_now` are not
  changed. Nothing here buys or sells.

## Every difference between the old replay copy and exit_policy (the replay now follows exit_policy)

- **D1, lock in arms at 1.5x cost.** The old copy armed lock in at `max(60% of payout, tuned floor x stake)`;
  exit_policy (live) uses a fixed `1.5 x cost`. Only matters when a league's floor is not 1.5. Example: a single run up
  to 82c then back to 62c with floor 1.7x: old rode it to a loss, new locks in +$0.73.
- **D2, cutting a loss for what is left.** The old copy needed the estimate over 2% of the stake for any cut; exit_policy
  cuts a single at any positive value (its least to accept is 0) and a combo once the offer reaches 2% of cost
  (`>=` instead of `>`). Example: a single whose guards only held at 2.1c: old rode it to 0, new gets $0.09 back.
- **D3, a combo just under the floor.** exit_policy says "smart" for a combo once the steady estimate is within 5% of
  the floor (`value / 0.95 >= floor`, allowing for the real offer being a bit higher), with the floor as the least to
  accept. When the estimate is in that last 5%, the sale doesn't happen and lock in is not looked at on that price
  (live: `take_profit_reason` answers "smart", `auto_sell_now` skips an offer under the line). The old copy went on to
  test lock in there. Example (fuzz corpus): a 2-pick NFL combo whose estimate fell to just under the floor right as
  it had dropped 20% from its high: old locked in +$39.72, new rides (that one lost).

`tests/suite/t_replaypolicy.py` proves the list is complete: the old replay (verbatim,
`tests/suite/fixtures/replay_old.py.txt`) with exactly D1-D3 applied matches the new one on 12,000 fuzzed paths
(combos of 1-4 picks and singles/spreads/totals, every floor/risk/loss step on the tuner's grid, cut guard times,
lock in on/off, several learned Kalshi discounts), and the old one matches the new one exactly on every path none of
them touches. 63 of 12,000 fuzzed paths differ (D1 48, D2 1, D3 17).

## Did the tuner's output change?

- Test fixtures (t_tune's NBA and NHL bets plus 45 run-up NFL combos): `smart_tune` moves exactly the same settings,
  same returns, with the old and the new replay.
- Pete's own history (a read-only copy of the Mac's database and smart-sell file, never written back): 26 settled bets
  with prices; `smart_tune` gives identical settings and returns; 78 per-bet replays (floors 1.4/1.5/1.6) all
  identical. No league has reached the 30-bet minimum yet except "all", and nothing moved either way.

## Still different from live (unchanged here, for later PRs in #228)

- Take profit (Pete's `take_profit`, off by default) is not replayed.
- The checkpoint x1.3 risk weight between a slate's games is not modelled (recorded paths don't say which picks had
  won); exit_policy's checkpoint flag only renames the reason.
- Kalshi's real offer is not known: the estimate (Kalshi's learned discount x chance x payout) stands in for it, and
  the sale needs the estimate at the threshold, where live accepts an offer down to `CASH_SLIP` (97%) of it. PR4
  (sale_outcomes + CASH_SLIP) is where that should be learned.
- The live risk weight also shrinks with time left in a game (`swing_lambda`) and is scaled by Let it ride; the
  replay keeps its own `0.35 x swing` as before.
