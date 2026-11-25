# Flexible sell price

**Section:** Selling (cash-out retries)

**ON by default (Pete's explicit opt-in, 2026-11-24).** Turn it off in Settings > Cash out > "Flexible sell price".

When a buyer backs out and the app asks for a fresh cash-out offer, the fixed "at least 97% of the first offer" line
(your own Cash out tap, and an automatic loss cut) was judged against a price that can be minutes old in a fast game.
With `flex_sell` on, each retry is judged against the game right now (`flex_decide`, called from `_accept_with_retries`):

- `flex_now` re-reads every open pick: picks in play get their live chance through `combo_live_fair` (a fresh score,
  Kalshi's fresh book, the panel's own live guards); picks not started keep their last chance. It needs at least one
  pick in play, one pick per game, and no spread or total in play.
- `flex_wait_line` is what waiting is worth now (`wait_value`, risk-adjusted with the Let it ride multiple, plus the
  per-pick cushion, same as `wait_threshold`).
- An offer is taken when it passes the **safety backstop** (at least `flex_backstop`, default 85%, of the combo's usual
  sale value now: live fair x pays x Kalshi's learned discount; a combo cash-out carries no separate fee) and the floors
  the sale already had, AND one of: the old bar would have taken it; selling beats waiting now (offer at or above the
  wait line); it is a profit (at or above cost) and the chance has dropped 3% or more since the round began; or it is a
  loss cut whose learned cut-off still holds on the fresh chance.
- It only ever loosens the old bar and never refuses something the old bar takes (beyond the backstop and the floors).
- **Fails closed:** anything missing or stale (no fresh score or book, a jumpy spread, a spread/total, same-game picks,
  no pick in play, any error) uses exactly the old bar. Switch off = decisions identical to develop.
- Kept as they were: the daily cap (`auto_cap`), the per-position attempt cap, the smart-sell floor, Pause, rule 8
  (an unknown outcome stops everything), Selling at a loss: Never, the cost floor for profit-taking sales, known-order
  outcome checks. No new fixed daily dollar cap was added (Pete: not needed).
- When a sale is taken under the first offer, its message says why; `CASH_LAST[...]["flex"]` and each try's `flex`
  hold the verdict.
- `flex_shadow` (SQLite) records every retry decision: offer, first offer, current fair, usual value, wait value,
  backstop, chance now, mode, reason, accept, and what the old rule would have said. Bounded (20,000 rows), errors
  swallowed, never read by any decision.
- Settings: `flex_sell` (default True) and `flex_backstop` (default 85), plumbed through DEFAULTS, SHARED_KEYS,
  WATCHER_SYNCED, the watcher's SYNCED and settings keys, the web app and the legacy settings page.

Tests: `t_flexsell.py` (default on; fast-moving accept; profit not refused; backstop refuses a spike; stale input falls
back to 97%; OFF identical to develop; loss cut; Never-at-a-loss; Pause; rule 8; tap/auto parity; shadow errors).

ROADMAP: none
