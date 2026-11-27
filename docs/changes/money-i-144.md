# money-i-144: money backlog, last third (#551, #300, #302)

**Section:** "Selling" (self-tuning brake) and "Fair prices and data" (books weight veto)

Three guard-side fixes. Nothing here adds an automatic buy, sell or hedge, loosens a guard, or touches Pause, caps or rule 8.

- **#551a, books-weight veto (`mkt_learn`):** a run where a group is not earned at all used to delete its veto entry, so the next
  good run was earned at once and the 2 h wait (`MKT['hold_wait']`) was skipped. The entry now stays and its clock restarts
  (`since = None`). Stricter only. The Settings switch off (`mkt_hold`) behaves as before (in-sample bar alone).
- **#551b, Live card:** the "Lock in" line (`lock_at`, `lock_armed` in `_smart_trigger`) now uses the tuned `trail_arm` and
  `trail_arm_cost` that `exit_policy` really sells on (via `knob_exit_prm`), not the fixed 60% / 1.5x. Display only.
- **#300, brake footing:** the combo discount at the sale (`rec["disc"]`, already in the decision file) is now stored in
  `sell_log` (new `disc` column, added to old files) and `knob_sale_expect` uses `max(today's discount, the one logged at the
  sale)`, ignoring unusable values. Never lower than before, so the brake can only trip sooner, never later.
- **Fallback:** if only the `disc` column cannot be added, `sale_store` still stores `live` and `ask` (`STORE["sell_disc"]`).
- **#302, test only:** `t_money_i.py` adds the `auto_sell_now`-level test (learned 0.99 slip: an offer at 0.98 x the line is
  skipped, 0.995 x sells, 0.97 control sells at 0.98).

## Live numbers that could move

1. The self-tuning brake (`knob_brake_check`) can trip a little sooner for a league whose combo sales were made when Kalshi's
   discount was higher than it is now. A brake puts that league's tuned exit numbers back to their starts (the strict direction).
   Single sales, thresholds, `KNOB_EPS`, the streak length and the 30-day share are unchanged.
2. A books-weight (`MKT_W` weights, so `longshot_leg_fair`'s blend vs Kalshi's mid in the 65-80% long-shot band) can stay 0 for up
   to 2 h longer for a group that flaps between not earned and earned. Weights are only ever removed, never added or raised.
   The veto record is in memory, so a restart still clears it, as before.
3. A braked league loses the default 12.5% loss cut (existing behaviour: no cut is the strictest while a brake holds), and the brake can now trip sooner, so the default cut is dropped sooner. Worst case about $1 of salvage on a $10 payout per combo that would have been cut. Pinned by `t_money_i.py`.
4. The Live card's "Lock in arms at $X" figure changes for a league whose arm numbers were tuned. Display only; the sale is unchanged.

Nothing else: no stake, price, floor, slip, cap or buy decision changes.

## Not done (from the last third of the money list)

- #519 (needs Pete: whether a Settings card / enforcement is wanted, and the caps), #299 (needs Pete's view on the #284 wording and
  the band), #301 (needs a design decision: pricing both judge directions the same way moves tuned values), #353 (the server half
  adds a card state on the buy path; the client half already ships), #246 (PR #593 is open on it; the rest is the sell-path text).
- #302's replay differences (auto cap, retries at 0.97, ask throttle, offer timestamps) change the judge's results and wait for a
  decision; only its requested test is added here.

ROADMAP: none
