# Killer deals skip games you already have enough on (issue #365)

**Section:** Settings › Money (Killer deals); Build page / killer deals list

The overlap guard from #359 held games back from every pick list, but the Mac's two automatic **killer** buy paths
(killer combo in `shadow_pass`, killer single in `single_pass`) still bought straight through it. Now both **skip,
never buy,** a deal that touches a game already at the line, with the same switch and numbers as the pick lists:
**2 or more open bets** on it (`overlap_n`), **or 8% or more of the panel's sizing base at risk** (`overlap_pct`).
It only ever reduces buying; nothing new moves money.

- **Engine** (`nfl_combo_planner.py`): one check in `killer_act`'s `on` branch, after the day caps and the spending
  cap and before the `buying` record goes in, so both paths get it at one choke point and Pause/watch mode are unchanged.
  `killer_overlap(legs)` returns `None` (go ahead) or the reason. The skip is recorded and logged like every other
  killer skip: `killer deal skipped: … you already have 2 open bets ($7 at risk) on this game (Knicks)`.
- **What it counts** (`killer_exposure`): Kalshi's combos (`cap_bets`: fresh, or the last good read ≤ `CAP_READ_AGE`),
  every single/spread/total position (read at that moment), today's panel bets, standing orders out there (`maker`, mode
  on, `posted`), and killer deals bought, `check` or still `buying` in the last day with no outcome yet, so a run can't
  stack on its own buys before Kalshi shows them. A bet the account already shows is counted once, not again from the
  panel or killer's own record. `game_exposure` takes these sources as optional arguments; with none (the pick lists)
  it behaves exactly as before.
- **Fails closed:** unlike the pick lists, if anything can't be read (the account, positions, the history, the balance
  for the base) the deal is skipped with "couldn't check your open bets on this game"; the detail goes to the log.
- **Switch off** ("Hold back games I already have bets on"): killer deals behave exactly as before and nothing extra is
  read.
- **Not touched:** the hedge (auto-hedge stays allowed on any game), standing orders, the panel's auto-buy, and watch
  mode.
- **Shows:** the killer deals list in Settings now shows a skipped deal's reason next to "skipped".
- Like every killer skip, a deal skipped because its game is at the line isn't looked at again for 6 hours (the
  existing one-per-deal rule). One skipped only because the bets couldn't be read is looked at again after 2 minutes
  (`KILLER_UNREAD_RETRY`), so a passing 429 doesn't cost the deal.
- Positions are read through the Mac hub when one answers (like every other account read), so a device that trades
  through the hub isn't blocked for good. Known limit: Kalshi shows one position per market, so a second killer buy on
  the exact same market as an open position counts once (the guard is per game; same-market stacking stays rare).
- **Tests:** `tests/suite/t_killer_overlap.py`. Two existing killer tests (`t_safety` §5, `t_orders_v2`) stub the
  guard so they keep testing what they tested (their fake account can't be read, so the guard would skip).

ROADMAP: none
