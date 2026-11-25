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
- An offer is taken when it passes the **safety backstop** (at least `flex_backstop`, default 85%, of the combo's current
  FAIR value now: live chance x pays, NOT discounted by Kalshi's usual offer share (Pete, 2026-11-25); a combo cash-out carries no separate fee) and the floors
  the sale already had, AND one of: the old bar would have taken it; selling beats waiting now (offer at or above the
  wait line); it is a profit (at or above cost) and the chance has dropped 8% or more under the holdings' last reading; or it is a
  loss cut whose learned cut-off still holds on the fresh chance.
- Automatic profit sales follow the same flexible rule as your tap and loss cuts (Pete, 2026-11-24): when the game moves fast they may go below the smart-sell line the sale started on.
- **A sale that began at a profit may end below cost** (Pete, 2026-11-24): in a fast-falling price, refusing can cost more later, so it is judged like any other offer (selling beats waiting now, past the backstop). A small loss can result and waiting could have been worse. Every such sale is recorded in `flex_shadow.began_at_profit_ended_below_cost = 1` to measure whether it earned its keep. With the 'Never sell at a loss' choice removed (below), the only things that govern a below-cost retry are this rule, the 85% backstop, the guards, the daily limit and Pause.
- It only ever loosens the old bar and never refuses something the old bar takes (beyond the backstop and the floors).
- **Fails closed:** anything missing or stale (no fresh score or book, a jumpy spread, a spread/total, same-game picks,
  no pick in play, any error) uses exactly the old bar. Switch off = decisions identical to develop.
- Kept as they were: the daily cap (`auto_cap`), the per-position attempt cap, the 1.5x smart-sell floor setting, Pause, rule 8
  (an unknown outcome stops everything), known-order outcome checks, and the 85% backstop. With
  the switch off, or stale/missing live info, today's cost floor for a profit-taking sale still applies exactly as before.
  No new fixed daily dollar cap was added (Pete: not needed).
- When a sale is taken under the first offer, its message says why; `CASH_LAST[...]["flex"]` and each try's `flex`
  hold the verdict.
- `flex_shadow` (SQLite) records every retry decision: offer, first offer, current fair, usual value, wait value,
  backstop, chance now, mode, reason, accept, and what the old rule would have said. Bounded (20,000 rows), errors
  swallowed. No sale decision reads it; only the fallback learner below does (and it only nudges one share).
- **Learned fallback share** (`flex_learn`, ON by default, Pete 2026-11-24). When live info is stale or missing, a retry must still reach a share of the
  first offer: 97% (`CASH_SLIP`) to start. `flex_fallback` learns it from this app's own record: `flex_shadow` retries joined
  to `sell_log` (what the position later sold for after a refused retry, or what holding paid after an accepted one; a combo
  cash-out carries no separate fee so the offer is the net cash). Needs 20 comparable retries (`FLEX_FB_MIN_N`) before a
  move, moves at most one half-point (`FLEX_FB_STEP`) per hourly evaluation, lowers only when waiting lost more than 1% of
  the offers' value, raises when it gained more, is hard-bounded to 85%-99% (`_fb_ok`, so NaN, text or out-of-band values
  read as 97%), per league (ledger league) once a league has 20 retries else global, shrinks back at twice the step when
  lowering proved too cheap and snaps to 97% after 3 such rounds in a row. A learned share under 97% is never below the
  85% backstop of what the combo last read as worth (fair value, no Kalshi discount). State lives in the `flex_learn` table. Any error or switch off = plain 97%
  (exactly develop's bar). Applies to the tap and loss-cut bar; an automatic profit sale's own bar is its smart-sell line
  (already tuned by `auto_slip`). The Settings row shows the learned value read-only (`flex_fb_view`).
- Settings: `flex_sell` and `flex_learn` (default True) and `flex_backstop` (default 85), plumbed through DEFAULTS, SHARED_KEYS,
  WATCHER_SYNCED, the watcher's SYNCED and settings keys, the web app and the legacy settings page.

Tests: `t_flexsell.py` (default on; fast-moving accept; profit not refused; below-cost end flagged, no Never exception;
backstop refuses a spike; stale input falls back to 97%; OFF identical to develop; loss cut; Pause; rule 8; tap/auto parity;
shadow errors) and `t_flexlearn.py` (sample threshold, step size, bounds, per-league, corrupt/NaN history, errors, streak).

ROADMAP: none

## The "Never sell at a loss" choice is removed (Pete's explicit decision)

- Settings > Cash out > Selling at a loss now has two choices: **Let it tune itself** and **Allow (guarded)**.
- A saved `stop_loss_mode: "never"` (any device, an old settings file, an old phone or page) is read as **Let it tune
  itself** (`sl_norm`): migrate on read, no crash, never silently Allow. `sl_mode`, `sl_sync` (phone/web/watcher merge
  and save), `sl_allowed`, the auto cash-out loop and the singles loop all go through it; the web page shows it as Let
  it tune itself too.
- Gone with it: the auto cash-out cost floor passed for Never, the "skip a single with unknown cost / under cost after
  fee" check, and the flexible rule's Never floor. Below-cost sales are governed by the flexible rule, the 85% backstop,
  the guards, the daily limit and Pause.
- Untouched (independent of this choice): the loss-cut trigger conditions, never at halftime/break/early game/stale
  score, the stop-loss's own guards and per-day limits, rule 8, Pause.
- Tests: `t_neverloss.py` (rewritten for the migration on every path), `t_settings`, `t_stoploss`, `t_knobpr567`,
  `t_flexsell`, `test_slmode_ui.py`.
