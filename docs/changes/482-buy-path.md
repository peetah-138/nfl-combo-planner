# Buy/recommend path follow-ups to the CBB totals report (issue #482, items 5-7)

**Section:** Build page / Spreads and totals

Three stricter-only fixes; none adds spending, loosens a gate or size, or touches Pause, the caps or rule 8.
- **Date on the ESPN match (item 6).** `line_candidates` priced a Kalshi event from an ESPN game on the two team codes
  alone, so a later rematch of the same teams could be priced from today's book total. `_event_day_ok` now requires the
  event ticker's own day (`26NOV27`) to be the ESPN game's UTC day or the day before (evening games start after
  midnight UTC). Only a clear mismatch skips the market; an unreadable ticker or start keeps the old match.
- **Pace only for full-game totals (item 5/7).** `_full_game_total` is true only for a league's `<series>TOTAL` ticker.
  The Live card's "On track / Not on track" text (`_single_how`) is no longer claimed for first-half or team totals,
  whose line is not the whole game's points. Display only: `_bet_kind`, the score lookup and smart sell are unchanged.
- **Alert path runs the Build page's checks (item 7).** `line_pass` now calls `_line_rec_one` (learned bar at the real
  book, a route to profit under smart sell's exit policy, expected-dollars floor) and drops a strike it refuses or
  cannot read; the idea's contracts are capped at what fills inside the edge (`rec["n"]`).

Not done here: item 3 (learned "too good to be true" shrink; needs settled history and a design call), item 4 (the
"game not found" badge wording, display only), and the live-score last-three-letters lookup (changing it would change
the state smart sell reads for held totals, so it needs its own money review).

Tests: `t_buypath482.py` (date window, full-game-total names, `line_pass` refusal, fail-closed error, contract cap 7 not
47); `t_push_gate.py` and `t_orderbook.py` stub the new checks.
