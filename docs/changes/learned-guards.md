# Learned selling guards

**Section:** Selling (self-tuning knobs, stop-loss guards)

Pete: "we're just making up rules that we should allow to have some level of learning." Settings > Cash out > **Let the
selling guards learn** (`learned_guards`, shared setting, ON by default; effective only with `knobs_live`; either off =
exactly develop: same live set, 150 s, a break always blocks, nothing recorded). `guards_on()` is cached 10 s and fails closed.

Converted, on the existing knob machinery (registry, weekly stepper, bootstrap bar, brake, `knob_shadow` move log, which now
keeps 20000 rows via `KNOB_SHADOW_ROWS`):
- **Score age** (`sl_feed_age`, start 150 s, band 90-300 s, step 30 s, shorter = stricter, per league else global; a
  global value is only borrowed when stricter). `feed_age_limit`, `fresh_live_score(loose=)`. Only a LOSS sale
  (`stop_loss_leg`) uses the learned tolerance; hedge and sell-more callers can only be stricter. Evidence: the bounded
  `feed_ep` table (`feed_note`, `feed_resolve`): a stale-score refusal with every other guard holding and a two-sided book is
  recorded (age 90-300 s) and closed 10 minutes later with that later bid (dropped after 30 min). Judge `feed`
  (`_knob_res_feed`): net dollars after the single-leg fee, selling now versus the bid 10 minutes later. Min sample
  `FEED_MIN_N` 20. Loosening needs a seeded bootstrap lower bound above 0 (`_guard_bootstrap`); tightening uses the lighter
  `GUARD_TIGHT` bar.
- **Halftime / break** (`brk_on`, `brk_move`, already in the registry as watch-only): `break_ok` may now open for a LOSS sale
  only (never a hedge), only on a league's own learned record (not borrowed), on a fresh two-sided book and two reads.
  `BRK_LIVE` stays False. Min sample `BRK_MIN_N` 40 (stricter than 20); judge is net of fees with guards on. The `break_ep`
  shadow table is bounded to `BRK_KEEP_ROWS` 5000.
- **Early in a game** (`sl_prog`): already learned by smart_tune and the stepper; no second mover added.

Not converted (kept fixed): Pause, the one-tap Sell, rule 8, no score at all / not in play / one-sided or empty book = no
sale, the daily limit (PR #480 self-adjusts it), the 85% flex-sell backstop (follow-up). Other fixed sell-timing constants
left as they are, each tied to data validity or already judged elsewhere: `swing_base`, `checkpoint_lam`, `cushion_*`,
`hedge_gap`, `live_spread`, `BRK_READS`, `BRK_SPACE`, `sl_under` (judged by `_sl_replay`, not live), #479's 8% drop,
#480's `MORE_PROG_MIN` and `MORE_*` (follow-ups).

Behaviour notes: the global group can only tighten (chain-stricter borrowing); the feed evidence is a 10-minute-later proxy;
the knob views list `sl_feed_age` as tunable even with the switch off (display only).

Tests: `t_learnedguards.py` (sample threshold, bounds, step, bootstrap, NaN/corrupt fallback, switch-OFF identity, brake,
break loss-only, Pause wins, manual Sell unaffected, bounded tables), `test_learnedguards_ui.py` (Settings, dark/light);
`t_knobs`, `t_knobpr567` updated.

ROADMAP: adds "Learned flex-sell 85% backstop and sell-more `MORE_PROG_MIN`: follow-ups once #479 and #480 land"
