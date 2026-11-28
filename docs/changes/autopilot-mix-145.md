# Autopilot: league and bet-type budget shares (issue #145, step 6)

**Section:** Full auto / Autopilot

Full auto now learns, league by league (NBA, NHL, ...) and for combo vs single bets, the MAX share of the day's spending cap
each may use. New record `share` in the autopilot registry (`AP_REG`, `FAL["share"]` = 5%..100%, 5-pt step, start 100%, key
`share:<league>` / `share:@combo` / `share:@single`). It only ever SPLITS the existing daily cap: it skips bets, never adds
spending, and Pete's limits ($300 bankroll, $30 daily cap, $20 loss limit, Pause) never move.

- **Evidence** (`_share_load`): the paper practice panel (never filtered by shares, so no feedback loop), replayed per day
  under the old and the new share (`_share_passes`: a day's first bet always passes, the running stake total stays within the
  share of the LIVE daily cap; each practice day is first fitted into that same cap, so the replay judges the rule the buy pass enforces, not the panel's bigger day). Net dollars after fees plus closing-line value per league. The shared gate (`ap_gate`: 70/30
  out-of-sample, bootstrap low end above zero, `FAL_SHARE["min_n"]` = 40 practice bets for the key; the gate's own minimum of changed bets in each split comes on top) decides. Step sizes (`_share_step`): loosening is exactly one 5-pt step; tightening is the first 5-pt value (at most 3 steps, 15 pts, in a week) that changes which bets pass; never below the 5% floor.
- **Tighten fast, loosen slow:** loosening needs twice the sample (`loose_mult` 2), 14 days since the last move
  (`loose_wait`), and non-negative readable closing-line value on the blocked bets (`_share_clv_ok`; unreadable = no loosen).
  No loosening or shift-up while `caution.level` > 0 (fail closed, also on an unreadable level). One step per setting per
  week; a `share` step and a `bar` step never happen in the same week (`AP_EXCL`, plain note on the card).
- **Floor:** every league keeps 5%, and its first bet of the day always passes, so it keeps producing evidence. Evidence comes
  from the paper panel, not the held real bets, so a league at the floor can still step back up.
- **Buy pass** (`FaShareGuard`, wired into `_full_auto_pass` before the open-slot skip logic): skip-only, reads today's
  full-auto spend; unreadable shares or bets approve nothing. Today's spend counts every bet bought today, open or already settled, including bets swapped in for ours (followed through `swap_of`, like `fa_check`), and is read strictly (unreadable = approve nothing). A share-held bet is filtered out before the open-slot skip logging so the #614 `fa_slots` evidence stays clean (tested with a no-share control).
- **Card:** logged on the Autopilot card in plain words with the dollars, with Undo, freeze (whole record or one league) and
  the master switch (`fa_lessons`), like every other autopilot setting. Data starts empty: nothing moves until there is sample.
- **Tests:** `tests/suite/t_autopilot_share.py` (gate, thin data, loosen/CLV/cautious rules, floor and feedback loop, cap-basis replay, step sizes, a real revert, #614 evidence, swap counting, cap never
  exceeded or added to, bar/share exclusion, fail-closed on unreadable data, freeze/undo, the buy pass).
