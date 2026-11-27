# Paper lessons for full auto (#144)

While full auto is ON, a paper or shadow record that has enough data and clearly passes its bar may move ONE small step of a
full-auto-only number, tighter or looser, at most once per record per week. Nothing here runs while full auto is off.

## What can move (the only live numbers)

All three are skip-only filters on the bets full auto itself picks (`full_auto_pass`). They can only leave a bet out; they never
add, resize or buy anything. Buying stays in `panel_exec`.

| Number | Start (today) | Range | Step | Evidence |
|---|---|---|---|---|
| `bar:<league>`: extra points over that league's combo cut-off | 0 | 0 to +5 | 0.5 | league shadow (`league_shadow_q`), min 30 settled quotes |
| `sbev:<league>`: Smart Buy level (none .. +$0.10 expected on $5) | 0 | 0 to 4 | 1 | Smart Buy paper book (`sb_paper`), min 50 bets |
| `game_share`: most of the full-auto bankroll one game may carry | 30% | 30% down to 10% | 2.5 points | exposure paper log (`expo_pos`), min 20 dollars-settled bets |

"Looser" only walks a number back toward its start value; it never goes past today's behaviour.

## What never moves

Daily cap, daily loss limit, bankroll, losing-streak brake, the manual panel, the live combo cut-off, Smart Buy's own dial,
sizing, every sell rule. The code does not edit `fa_check`, `fa_set` or the limit fields (overlaps #589 only by sitting beside
them in the same file).

## How a step is judged (same style as the knob stepper)

Picked on the older 70% of past bets; the newest 30% must also gain; net dollars after fees; seeded bootstrap range above zero;
the stepper's minimum of changed and new bets. Unreadable data, a small sample, or any error means no step. A malformed saved
value approves nothing and shows as a blocker on the card.

A week later the step is re-scored on the bets since. If they lost money it is reverted automatically (and only newer bets
count afterwards); otherwise it is kept. Every step, keep and revert is logged with before/after and the evidence and shown on
the full-auto card, for example "Learned: NBA combo bar +0 points -> +0.5 points because ...".

Master switch `fa_lessons`: default ON, effective only while full auto is on. Its own tap on the card
(`full_auto_lessons`), not part of `full_auto_set`.

## Honest caveats

- The league shadow log is hold-to-settle (no early exits) and never backfills, so expect "too few yet" for a while.
- The exposure evidence includes Pete's own manual bets, and its replay never releases finished bets.
- Smart Buy paper book backfilled rows are ignored.

## Not wired yet (shown on the card with the reason)

Paper panel (it is the unlock gate itself), Smart Buy shadow and dial (already self-learning), knob stepper shadow (own stepper),
momentum, exit-cap, smart-sell-more, flex, combo shadow trader, signal, broad, slate, prop shadows (no bar defined or sell-side
only), books' weight.

## Tests

`tests/suite/t_fa_lessons.py`: off when full auto is off, fail closed on bad data, bounds both ways, revert and keep, weekly
cap, master switch, identity at start values, manual panel unchanged. `t_leagueshadow.py` and `t_exposure.py` source guards are
narrowed to allow only `_fal_load` / `_fal_min_n`.
