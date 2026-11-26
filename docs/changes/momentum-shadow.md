# Momentum shadow recorder and the real smart-sell trigger on combo cards

**Section:** Selling (next to `signal_shadow` and `exit_cap_shadow`) and the Live page

First deliverable of `momentum-exit-design.md` section 5. **Nothing here sells or buys.** It records and explains.

- **Recorder (`mom_record`, tables `mom_shadow`, `mom_after`, `mom_peak`).** Called once at the end of `take_profit_reason`
  (combos) and `single_sell_reason` (singles, live pass only: `track=True`, no `more`, no `cap`), each time inside its own
  try/except, with numbers the exit rule had already worked out. It never changes a return value. One `mom_shadow` row per
  evaluation when any verdict changes, else every 120 s per bet: win chance q, its high over the last 10 min, the drop
  `dq`, a placeholder `sigma` (0.05, nothing learned yet) and `z = -dq / sigma`, the real offer net of fees, the steady
  estimate, quote age, cost, payout, the peak, today's decision / reason / line, a plain `why_not` (`q<50%`,
  `no real quote`, `below floor`, `peak<arm`, `no live data`, `smart sell off`), two HYPOTHETICAL verdicts and the Pause
  flag (recorded only). Hypothetical `m_protect`: real offer, `z >= 2.0`, offer >= cost - 5% of cost, holding worth
  <= offer x 1.10. `m_cut`: stricter (`z >= 2.5`), holding worth less than the offer, offer >= 30% of cost.
  `mom_after` is opened for rows where something fired and fills the offer at +30 s, +1, +5, +15, +60 min (from the first
  evaluation after each time) and the lowest seen; `mom_settle` (from `live_view`, once per bet per run) adds the
  outcome (`won`, `lost`, `cashed`) and payout. `mom_peak` keeps each bet's peak so a restart does not lose it; it is
  reloaded only into the recorder's own dict, never into `MINE["peak"]`.
- **Bounds.** Setting `mom_shadow` (default ON for recording; false = off; a plain DEFAULTS key like `sig_shadow`, not in
  `SHARED_KEYS` or the watcher list). Throttled, 100k-row cap, 60-day prune (every 6 h), every error swallowed through
  `console_note`. Pause, rule 8 and the no-live-data guards are untouched: nothing in the recorder places an order.
- **Log lines (console).** `MOMENTUM would sell <ticker> rule=protect z=2.4 q 61%->44% offer net $4.91 vs cost $4.99
  (today: hold, q<50%)` once per episode; `NO SELL <ticker>: blocked by <q below 50% | offer under floor $X | lock-in not
  armed (peak $Y < $Z) | no real quote | no live data>` every 10 min per live position.
- **Combo cards.** `smart_trigger(t, h)` (display only, touches no peak) adds `smart_at`, `smart_over`, `smart_txt`,
  `lock_at` to each combo in `live_view`. The card now says, e.g. "Smart sell waits until the offer reaches $7.20; it needs
  a real Kalshi offer." and "Lock in arms once the offer has reached $9.00." The old let-it-ride number (`wait_threshold`)
  is relabelled **wait line**, and the Smart sell chip on a combo shows smart sell's real bar instead of that number.
- **Tests.** `t_mom_shadow.py` (synthetic DB: rows written, a failing recorder changes nothing for selling, log lines,
  kill switch, throttle, pruning, nothing reads the tables back, card text).

ROADMAP: none
