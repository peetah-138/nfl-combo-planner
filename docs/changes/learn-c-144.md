# learn-c-144: learning follow-ups (#477 #476 #474 #309 #291)

**Section:** Self-tuning (knob stepper), Smart Buy results, shadows

**Already on develop, skipped on purpose (nothing changed for them):**
- #477 league blend double counting: fixed in #549 (`_lgsh_minus`, disjoint counts; `calib_fair` unchanged).
- #476 league shadow dollars gate: shipped in #549 (`league_shadow_q`, `lgsh_gate`).
- #474 mkt_learn holdout: #549 made the weight pick on the oldest 70% and require a gain on the newest 30% (stricter-only), #566 added `mkt_holdout_report`. What is left (a holdout that may pick a weight the old rule would not, and the inert `hold_min`) is a measure-before-change pass on real settled data and would loosen a live number, so it stays open.
- #291 paper book: #566 added the panel's one-per-game-and-family, spread/total share and daily-size rules. The rest (ahead floor, fill cap by depth, buying at approval time, a stage-3 extras budget) needs data that is not recorded or a stage-3 definition that does not exist yet; paper only, left open.
- #309 bullets 1 (labels, #564) and the `ideas.js` NaN check (`pct(null)` already returns a dash, `common.js`).

**Done (#309 nits, read/record side):**
- `_knob_items`: a cashed combo's `kick` is now its game start (`_knob_game_kick`: recorded kickoff, else the first in-play tick, else the buy time as before; never earlier than the buy, so a combo bought in play replays from its buy as before), so the stepper's "after the last step" filter and 70/30 holdout place it right.
- `sb_resolve`: the second (universe) look skips rows the first batch already holds, so a full batch no longer wastes its second look on repeats (more universe results resolve per pass; nothing else changes).
- `_sb_results` reads `exit_shadow` in pages of 20,000 by (ts, rowid) (`_sb_rows_chunked`) instead of one read of up to 200k rows under the store lock the panel buy thread shares. Same rows, same order; a read error in any page raises (`store_rows_strict`) instead of truncating.
- Test gap: `t_knobfloor_309.py` runs `auto_sell_now` with `auto_slip` at its lowest allowed value (0.90) and shows a profit sale under cost is not made and the daily cap still stops the next sale; it also pins that `cut_accept` 0 and values below a knob's minimum are refused.

**Live numbers that could move:** none directly (no buy, sell, size, price or cut-off is changed). Indirectly, the knob stepper's judgement of the cashed combos moves with the corrected start time (which bets count as before/after a step and which fall in the newest 30%), so a knob step could land one round earlier or later; the stepper's own bounds and stricter-only rules are unchanged. `sb_resolve` may settle more Smart Buy universe rows per pass, which feeds only the stricter-only early look.

Tests: `t_learnc_309.py` (kick, paging, resolve), `t_knobfloor_309.py` (lowest knob values through a real sell pass). Both fail on the old code.

ROADMAP: none
