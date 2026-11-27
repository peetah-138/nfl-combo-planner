# Autopilot moves full auto's open-bet limit (#145, step 4 of the self-improvement plan)

Full auto's "max open bets" (Pete's number, default 15) now moves by itself through the Autopilot registry, as a fourth record
(`open`, key `open_slots`). Weekly look, one bet at a time, between 8 and 20. Only while full auto and the Autopilot master
switch are on. No new automatic money movement: the daily cap, bankroll and daily loss limit never move and still bind through
`room`/`free` in `fa_check`.

## Evidence (new table `fa_slots`)

- Each full-auto buy is logged with how many bets were open when it was bought (settled later from the panel's profit).
- When open slots were the ONLY thing stopping a bet (it fit the cap, bankroll and brakes), a "skip" row is logged (throttled,
  one per bet), with its price. `fa_slot_settle` later settles skips from Kalshi's results, held to the end, after fees.
  Rows are kept 90 days. All of this swallows errors and never blocks a buy.
- A limit v "passes" a bet when it was bought or skipped with fewer than v bets open. Judged like the other records: older 70%
  picks, newest 30% must agree, net dollars after fees, bootstrap low end above zero, minimum sample (25 rows).

## Tighten fast, loosen slow

- Tightening is the normal weekly step. Loosening needs 14 days since the last move and twice the sample (50 rows).
- No loosening while the soft brake is cautious, or the setting is held (Undo hold, 14 days) or frozen.
- Fail closed: unreadable data, a malformed or out-of-range saved value means no step, and the limit falls back to Pete's number.

## What you see

Log lines on the full-auto card with Undo, Freeze (`open_slots`) and the master switch, e.g. "Open-bet limit: 15 -> 14. Why: the
15th open one lost on 4 of 9 bets." The "Bets open" line reads "0 of 14 allowed (you set 15; Autopilot moved it)".

## Not changed / worth a look

- Pete's saved number is the ceiling: learning goes below it (floor 8) and back up to it, never above. Saving a different "Open bets" number clears what was learned; saving only the cap keeps it.
- Skipped bets in one pass are replayed in order: each adds one to the open count and uses up room and bankroll, so only bets that would really have fit are counted.
- Replay biases: skipped bets are held to the end (no early sale), paper `pl` has no fee, and taking one more bet may have
  changed which later bets were available.
- The skip logging sits in `_full_auto_pass` (the money path) but only records after the decision, inside try/except.
- Data starts empty: no step until evidence accumulates.
- Files: `nfl_combo_planner.py`, `watcher/spa/fullauto.js`, `tests/suite/t_autopilot_open.py`, `tests/suite/t_autopilot.py`.
