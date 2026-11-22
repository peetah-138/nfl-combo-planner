# The knob registry, read-only (issue #228, PR1)

**Section:** Selling (after "Smart Buy, stage 2"), and Results page (What's working › Selling)

Pete (2026-11-21): the guessed sell, hedge and loss-cut limits should tune themselves per league on evidence; the
safety invariants never. PR1 is the list only: **no behaviour changes**, nothing new moves by itself.

- **`KNOBS`** (engine, after `smart_summary`): one entry per number smart sell, the loss guards, auto-hedge and Smart
  Buy decide with. Each has `name`, `group` (profit / loss / hedge / sell / buy / evidence / invariant), `cls`
  (`tunable` = a guess that may move on evidence later; `setting` = Pete's own setting he opted in to letting the
  system raise: `auto_cap` (no ceiling) and `hedge_cap` (up to $150); `evidence` = the bar a change must clear, never
  moved by the data; `invariant` = safety / data integrity, with `why`), `label`/`what` (plain English), `owner` (the
  live function), `src` (the constant or setting the live code reads: `"NAME"` or `"NAME.key"`), `start`, `min`/`max`
  (hard bounds; a hedge may never lock in under 1× cost; `hedge_cap` 25-150), `step`, `step_kind` (`add` / `mult`: the risk weight steps ×0.85/×1.15), `on_value` (the loss cut's first value, 0.15), `shared_with` (other decisions the number drives: the confirmation counts also confirm hedges, `SB_EV_MIN` also sets Build's spreads/totals list, `CASH_SLIP` also your own Cash out retries, `LIVE_SPREAD` also live buys), `unit`, `stricter` (the direction in which the app does less on its own; a borrowed value may
  only move that way), `borrow` (today: `own`, `chain`, `chain-stricter`, `none`), `learned` (the function that already
  moves it, else None), `metric` and `judge` (the replay/sim that would judge a change). `KNOB_BY`, `KNOB_GROUPS`,
  `KNOB_EVIDENCE` (PR2's bar: 10+ bets in band, 2% of stake, 2 SE, 20 new results, newest-30% holdout) and
  `KNOB_BRAKE` (4 losses in a row or 5% of the month's automatic-sale stake: back to start for 14 days) are written
  down; **no live code reads any of them** (`t_knobs` checks only `analytics` calls `knob_view`).
- **Tunable (start):** profit floor 1.5×, risk weight 1.0, least chance to take a profit 50%, swing base 0.35,
  checkpoint 1.3×, estimate allowances 0.95 / 0.9, take-profit minimum 1.25×, lock in arms at 60% of payout and 1.5×
  cost, sells after a 20% fall, never under 1.1×; loss cut off (0.10-0.30, own record only), loss cut accepts ≥ 2% of
  cost, loss guards 50% of the game / 20-point fall (borrowed only stricter), pick under 50%, 3 checks / 3 min / ≤ 5 min
  apart, break guard on (rule; becomes the conditional `break_ok` in PR5); hedge at 95% of the cash-out (or +$0.50
  with "Hedge instead" off), locks in ≥ 1× cost, hedge-side gap ≤ 6¢; `CASH_SLIP` 97%, singles' sell gap 6¢
  (`LIVE_SPREAD`, shared with live buys: must be split before it can move), Kalshi offer before 5 quotes 88% / 82%,
  room for error 2% a pick ≤ 15%, each sport's swing (`SWING`, a table), the below-cost guard (rule: on); Smart Buy dial 0, sell-route bar 50% of paths (`SB_ROUTE_EXIT`, was inline), `SB_EV_MIN` $0.25, `SB_WIN_MIN` 40%, `SB_GAIN` 10%,
  `SB_PRE_VOL` 0.12, `SB_PRE_CLOSE` 0.5, assumed gaps 2¢ / 4¢, widen 1.5×. **Settings:** `auto_cap` 5, `hedge_cap` $100.
- **Invariants:** Pause, the Pi never trades, your switches (Auto cash-out, Smart sell, Let it ride, auto-hedge, the stop-loss override, "I'll sell it"), rule 8 (unclear orders never retried), `ACCEPT_WAIT` 15 s, `CASH_RETRIES` 3 (only after a clear refusal), `OFFER_LIFE` 150 s, caps fail closed (120 s), fresh
  score (150 s), in play, live price age (180 s), live-buy score age (120 s), singles' price age (180 s), a real fresh
  offer before any sale or hedge, secrets.
- **Named, same values:** numbers that were written inline are now module constants so the registry can name them:
  `EXIT_Q_MIN`, `EXIT_EST_SMART`, `EXIT_EST_TP`, `CUT_ACCEPT`, `TRAIL_ARM_COST`, `TRAIL_FLOOR` (exit_policy),
  `SB_ROUTE_EXIT` (simulate_exit), `SWING_BASE`, `CHECKPOINT_LAM` (swing_lambda, `_replay`, simulate_exit, the exit replay), `SL_UNDER`
  (stop_loss_leg, `_sl_held`), `HEDGE_LOCK_COST`/`HEDGE_LOCK_SHARE`/`HEDGE_LOCK_EXTRA` (hedge_guard, hedge_fresh,
  hedge_beats), `SINGLES_SELL_AGE`, the auto-hedge message's `HEDGE_LOCK_EXTRA`, `DISC_PRE`/`DISC_LIVE`, `CUSHION_PER_PICK`/`CUSHION_MAX`. `t_exitpolicy` (the old
  functions verbatim on 8,000 states), `t_replaypolicy`, `t_hedge`, `t_stoploss`, `t_cutloss` pass unchanged.
- **`knob_view()`** (in `analytics()["knobs"]`, so cached with it): every knob with start/bounds in plain words
  (`knob_say`), and for the six already learned by league (floor, risk weight, loss cut, the loss guards' timing and
  fall, Smart Buy's dial) the value per league and whose record set it (own / borrowed from X / starting point), by
  the same walk as `smart_params`, `stoploss_params` and `sb_dial`; the rest one value ("fixed for now", "your
  setting", "never moves"; Kalshi's offer share shows `kalshi_discount`'s learned median once 5 quotes exist). A damaged
  league entry hides only that league. Mix is listed like a league. Reads only; never raises (an error = `{}`).
- **Results › What's working › Selling:** a folded card "🎛️ The numbers selling runs on" (`knobCard`,
  `watcher/spa/knobs.js`): groups, value / start / range / source per row, league chips, the bar a change must clear,
  "Never moves by itself" with reasons. Only the fold and the chips are controls; no setting can be changed there.

Nothing touches Pause, caps, sizing, rule 8, the tap lock or any buy/sell path. Tests: `t_knobs.py` (completeness and
bounds; every `src` equals its start; rule probes; no inline numbers left in the live functions; nothing but analytics
reads the registry; per-league values identical to the live resolvers; read-only; never raises), `test_knobs_ui.py`.

ROADMAP: none
