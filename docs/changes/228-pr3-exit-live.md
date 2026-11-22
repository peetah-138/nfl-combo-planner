# Self-tuning: smart sell's exit numbers go live (issue #228, PR3)

**Section:** Selling (after "The knob registry" and PR2's stepper), Results page (What's working › Selling), Settings › Money

Pete (2026-11-21): the guessed selling limits self-adjust per league on evidence; invariants never. PR3 is the first
step that changes live selling, behind a master switch, and only for smart sell's **exit numbers**.

- **The switch.** Settings › Money › **Let smart sell tune its own numbers** (`knobs_live`, shared setting, in
  `SHARED_KEYS` and the web app's `SET_KEYS`). **On by default**, under Pete's standing #228 opt-in (guessed limits
  self-adjust per league on evidence; the brake as he set it). `knob_switch_on()` reads the shared settings file (like
  the other switches), at most every 10 s; unreadable = off. **Off = byte-identical to before this PR**: every exit
  decision reads the constants and smart_tune's file exactly as before (its old either-way borrowing included) and
  PR2's stepper only proposes.
- **What is live** (`KNOB_LIVE`): the profit floor, risk weight and loss cut (`smart_floor`, `smart_lam`,
  `smart_loss`), the least chance to take a profit (`exit_q_min`), the two estimate allowances (`exit_est_smart`,
  `exit_est_tp`), take profit's minimum (`tp_min_gain`), the lock-in numbers (`trail_arm`, `trail_arm_cost`,
  `trail_drop`, `trail_floor`) and the loss cut's accept (`cut_accept`). Everything else stays shadow: the loss guards
  (`sl_prog`/`sl_drop`, still smart_tune's), the hedge knobs, Smart Buy's dial and constants, the shared and tied
  knobs. Never tuned: Pause, can_trade / the Pi, rule 8, cap fail-closed, fresh score/price age, in-play, a real fresh
  quote before a sale, the stop-loss/hedge/break guards, secrets.
- **exit_policy takes its numbers as parameters** (`prm` keys `q_min`, `est_smart`, `est_tp`, `tp_min`, `trail_arm`,
  `trail_arm_cost`, `trail_drop`, `trail_floor`, `cut_accept`), each defaulting to its constant (the registry's start),
  so a caller that passes nothing decides exactly as before (`EXIT_POLICY_VERSION` 2). `_replay` passes them (`ex=`)
  and can replay Pete's own take-profit % (`tp=`); its defaults are unchanged.
- **The live read path.** While the switch is on, `take_profit_reason`, `single_sell_reason` and `exit_settings`
  (Smart Buy's simulator and the exit replay play the same policy) add `knob_exit_prm(tickers)` (only the numbers that
  differ from their start; `{}` when off, braked, nothing learned or on any error), and `smart_params` answers through
  `knob_smart_params` (falls back to the old walk, logged, if it ever errs). Per number, `knob_live_value`: the league's
  own value, else its sport's, else everyone's; **a borrowed value only stricter** than the start (#259; the loss cut is
  never borrowed); the start while the league's brake holds. A group's own value is self-tuning's record (`lv` in
  `combo_knobs.json`, with when, `lat`) unless smart_tune moved the same number later (while the switch was off), else
  smart_tune's own (n ≥ 30) for the floor/risk/loss. A recorded value outside the registry's bounds or not a number is
  ignored (`_knob_valid`). `combo_knobs.json` is cached 60 s for the sellers (`knob_state_cached`; this process's saves
  refresh it at once).
- **One mover per value (#267).** With the switch on, `smart_tune` stops moving the floor, risk weight and loss cut (it
  still counts `n`/`ret` and still tunes the loss guards); `knob_tune` moves them, starting from smart_tune's own
  values, and **never writes smart_tune's file** (or any setting or CFG). Every run starts every knob from the value
  live uses for that group's own record (re-read each run; the shadow no longer drifts from live).
- **The stepper, live.** Weekly, per group: at most **one live step** (exit knobs, status `stepped`, `lv`/`lat`,
  `lstep_at`, a `hist` entry with `live` and the words) and, separately, at most one shadow "would step" (the loss
  guards, Smart Buy's dial; `v`, `step_at`). Judges: `_replay` for the floor, risk weight, loss cut (only where the
  live loss guards held), least chance, take profit's minimum, the lock-in numbers and the cut's accept, run with
  Pete's own take-profit % and lock-in switch; the estimate allowances wait (the replay has no real Kalshi offer to
  set against the estimate: PR4). #258's bounds still apply (one of the lock-in trio off its start; the risk product).
- **The bar, with a real holdout (#264).** `knob_evidence` now uses only bets from games **after the group's last
  step** (live and shadow apart), split by start: the step is chosen on the **older 70%** (10+ bets it changes, a gain
  of 2%+ of what those bets staked, 2+ standard errors from luck), and the **newest 30%**, which played no part in
  choosing it, must gain too on 3+ bets it changes; 20+ results since the last step. **#268, decided:** tightening
  needs the same bar as loosening (one bar both ways; nothing is waved through because it is "safer").
- **The brake, Pete's #266 ruling.** A sale is a **loss only when holding would have paid more than the sale got**
  (never merely "sold for less than it cost": a loss cut that saved money did its job). `_knob_brake_sales`: one row
  per bet however many parts, sold = Kalshi's ledger proceeds after the fee when known (else the offer after the
  single fee), holding = `sale_outcomes`' figure; a bet still waiting for its result, or void, counts neither way;
  only the app's own (not the Pi), after the league's last brake ended, within 30 days. Fires on 4 such losses in a
  row, or (4+ sales) the month's sales getting more than 5% of their stake less than holding. **Live:** the league is
  back on its starting numbers for 14 days (the read path returns the starts while it holds; its own self-tuned values
  are put back to the start, newer than anything smart_tune set, so they stay there until a new step clears the bar),
  logged `braked`, **one push** per league per 14 days when it changed something ("Self-tuning brake: in NBA, ...").
  Shadow (switch off): "would brake", as in PR2.
- **Every change is logged and shown.** `knob_shadow` rows (`stepped` with knob, league, from, to, why; `braked`), the
  watcher's log ("knobs: self-tuning changed NBA: ..."), and Results › What's working › Selling: the card becomes
  "🎛️ What self-tuning changed" while on (header counts changes and brakes; per league "Changed", newest first, with
  date and the evidence in plain words; a live brake banner; "Tested, not live yet" for the shadow knobs; "Where it
  stands now"), "🧪 What self-tuning would change" while off. The registry card says which numbers tune themselves and
  shows them per league while on. Only a brake pushes.

On Pete's real history (read-only copy, 2026-11-21): smart_tune's file has every league at the start (n under 30), no
`combo_knobs.json` yet; a live run steps nothing (everyone: 32 bets, no step clears the older-70% bar; every league
thin) and the brake has one finished automatic sale. **So turning this on changes no decision today**; the first live
step needs a league (or everyone) with 30+ settled bets and a step that clears the bar.

Tests: `t_knoblive.py` (switch off: 5,000 random combo and single decisions plus smart_params / exit_settings
byte-identical to the verbatim pre-PR code, `fixtures/exit_knobs_old.py.txt`, with self-tuning's record full of
learned values; switch on with nothing learned and with only leagues' own values: identical; exit_policy with the
starts passed in = none; each number moves the decision; a learned value changes only its league, borrowed only
stricter; the brake on the new measure, 14 days, one push, the starts kept after; one live step a group, the bar, the
holdout veto, judged only after the last step; smart_tune stops moving floor/risk/loss while on; never smart_tune's
file, a setting or CFG; the Pi; damaged values), `t_knobstep.py` (PR2's checks with the switch off, the new split),
`t_knobs.py` (who may read the registry; knob_view mirrors smart_params with the switch on), `t_exitpolicy.py`,
`t_safety.py`, `t_tune.py`/`t_replaypolicy.py` (smart_tune with the switch off), `test_knobshadow_ui.py` (both cards),
`test_knobs_ui.py`, `test_analytics.py` (the Settings switch, on by default, saves both ways).

ROADMAP: removes "#228 PR3: exit knobs go live"
ROADMAP: adds "#228 PR4: the estimate allowances (exit_est_smart / exit_est_tp) and CASH_SLIP judged against real Kalshi offers and sale_outcomes; wire sale_outcomes into the stepper's judge"

## Notes for the release owner (CLAUDE.md)

- Fold this into Selling next to PR2's stepper. In "Smart Buy, stage 1" the line "`_replay` ... still has its own copy
  of the rule" is already stale since PR0; `_replay` now also takes `tp`/`ex`.
- **Hard rule 2 / existing opt-ins:** add "self-tuning of smart sell's exit numbers (`knobs_live`, on by default under
  Pete's #228 opt-in; per league, the evidence bar and the brake; Pause, the Pi, rule 8 and every cap unchanged)" to
  the list of opt-ins, alongside PR2's note on `hedge_cap`/`auto_cap` (still not raised by anything).
- In the Selling "Self-tuning, per league" paragraph: with the switch on, smart_tune no longer moves the floor/risk
  weight/loss cut (knob_tune does, on the stricter bar), and borrowed values are only stricter (#259).
