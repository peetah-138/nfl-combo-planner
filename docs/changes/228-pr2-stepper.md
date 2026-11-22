# Self-tuning: the stepper, holdout and brake, in shadow (issue #228, PR2)

**Section:** Selling (after "The knob registry"), and Results page (What's working › Selling)

Pete (2026-11-21): the guessed sell, hedge and loss-cut limits self-adjust per league on evidence; invariants never.
PR2 builds the machinery and runs it **in shadow only**: it writes down what it would change; **no live decision reads
it**. `smart_params`, `stoploss_params`, `sb_dial`, `exit_policy`, `hedge_guard`, `auto_cap` and the live tuners
(`smart_tune`, `_sl_tune`, `smart_buy_learn`) read their own constants and files exactly as before (`KNOB_MODE =
"shadow"`).

- **Resolver** `knob(name, league)`: the league's own recorded value, else its sport's, else everyone's; a borrowed
  value only **stricter** than the start (`knob_stricter`: towards the registry's `stricter`; `borrow: own` knobs such
  as the loss cut are never borrowed; this is #259's rule, enforced here and not yet in the live `smart_params`); the
  start while the league is braked or nothing is recorded. Invariants and evidence knobs give their live value.
  `knob_cap(name)` (#260) keeps Pete's own `hedge_cap`/`auto_cap` apart from any system raise: the larger of Pete's and
  the raise (the raise never over the registry ceiling: $150 hedge, none for auto_cap), Pete's own while any league is
  braked; Pete's own value is never lowered or clamped, even above the ceiling; an unreadable hedge cap is the default
  $100, never "no limit". Nothing raises a cap in PR2.
- **State** `combo_knobs.json` (git-ignored by `combo_*.json`; read-modify-written under `file_lock`, read back
  after the write so a failed save raises, without the money-state alarm): per group (`all`, each sport, each league) the would-be values `v`, `step_at`, `why`, the last run's
  rows `last` and a short `hist`; `brake` per league; `settings` = Pete's own caps and any system raise (#260);
  `_at`/`_next`/`run`. Every proposal is also a row in the history file's **`knob_shadow`** table (knob, league,
  from, to, status, gain, share, band, t, new, holdout gain and count, words, the group's bet count and stake, the value
  the live code uses for that group today, and the bar's version), "thin" rows included, kept 180 days.
- **Stepper** `knob_tune` (weekly, `KNOB_TUNE_EVERY`): for each group and each `cls == "tunable"` knob with a judge,
  one step either way (`knob_candidates`: `add` or `mult` steps, clamped to `min`/`max`; a knob that starts off
  switches on at `on_value`, and off from below its range), every other knob at the group's current value, judged by
  the registry's judge (`knob_judge`): **`_replay`** for the profit floor, risk weight and loss cut (the cut only where
  the live loss guards would have held, `_cut_guard_ts`), **`_sl_replay`** for the loss guards' timing and fall,
  **Smart Buy's band** for its dial (a bet the new level skips loses its result, one it keeps gains it, $5 each).
  Groups start from today's live value from their **own** record (`_knob_seed`), never a borrowed one. Pete's bar
  (`knob_evidence`, `KNOB_EVIDENCE`): **10+ bets the step changes, a gain of 2%+ of everything the group staked, 2+
  standard errors from luck (t of the band's per-bet gains, sample standard deviation), 20+ results from games after the group's last step, and
  the newest 30% of the group's bets (by start) must gain too** on at least 3 bets the step changes (`KNOB_HOLD_MIN`); the bars are on
  all the bets, the holdout must agree. A group needs `SMART_MIN_N` (30) / `SL_MIN_N` (50) / `SB_LEARN_N` (30) results
  of its own first ("thin" otherwise). **One step per group per run**: the biggest gain; ties go to the smallest change
  (in steps), then the registry's order; other steps that clear the bar are noted as "qualifies", a step failing only
  the holdout as "vetoed". Smart Buy's soft top (level 3 under 100 results) holds. Never stepped: invariants, evidence
  knobs, settings; **tied** knobs (`KNOB_TIED`: `swing_base` moves only through the risk weight, #258); **shared** knobs
  (`shared_with`: `sl_checks`/`sl_span`/`sl_gap` with hedging, `cash_slip`, `live_spread`, `sb_ev_min`), which must be
  split first; knobs whose judge can't take them as a parameter yet (exit_policy's constants: PR3; hedges: PR6; Smart
  Buy's simulator constants: PR7), listed as "waits". #258's bounds: in a **one-of** set (`KNOB_ONE_OF`: swing base /
  risk weight; the lock-in trio) only one knob may stand off its start per league, and the **risk product**
  (`KNOB_PRODUCT`: risk weight × swing base × checkpoint, each as a share of its start) stays inside 0.5×–2.0×.
  A braked league is skipped. Time-bounded (`KNOB_BUDGET` 60 s, the bet reading and each replay included); a run cut
  short continues a day later from the groups not yet judged in that weekly cycle (`run.cycle`), and a group cut in the
  middle takes no step; a run that hits an error waits a day too (in memory, `KNOB_RUN`, and in the file), and the card
  says why (`run.why`). One replay cache is shared across groups. Never raises, Pi never (`ROLE_BACKUP`).
- **Brake** `knob_brake_pass` (every 30 min, `KNOB_BRAKE_EVERY`): per league, the history file's real automatic sales
  (`sell_log` `result='sold'`, not the Pi; profit = the offer after the single-bet fee minus that share's cost; **one bet
  counts once** however many parts it was sold in) made after its last brake **ended** (sales during a brake never count
  after it) and within 30 days. `knob_brake_check`: the **last 4 all lost money**, or (with 4+ sales) together they
  **lost more than 5% of what they staked** (`KNOB_BRAKE`). Shadow records "would brake": the league's would-be values
  back to their starts for 14 days, its next step needing 20 new results, a `knob_shadow` row, and **one push per league
  per 14 days**, only when it would change something (a value off its start), worded without the notifier's urgent
  words so it goes in the digest ("Self-tuning test, nothing changed: ..."). Information only.
- **Watcher:** `shadow_loop` calls `H.knob_pass()` (brake, then stepper) **outside `odds.lock`**, after the smart-sell
  scorecard; logs its lines ("knobs: ...") and hands the push lines to the notifier. Never raises.
- **Results › What's working › Selling:** a folded card "🧪 What self-tuning would change" (`knobShadow` in
  `watcher/spa/knobs.js`, data `analytics()["knob_shadow"]` = `knob_shadow_view()`, read from the file only): the header
  counts steps and brakes; opened, "A test run: nothing changes yet", the bar in plain words, last/next run, league
  chips, per league "Would change", "Also clears the bar", "Held back by the newest bets", "Where the test has it now",
  a brake (test) banner, the count of steps that didn't clear the bar, what needs more results; which knobs are tested
  so far and which wait or are shared. Only the fold and the chips are controls. The header keeps its focus ring.

On Pete's real history (read-only copy, 2026-11-21): 30 settled bets with recorded prices in 60 days, so every league
is thin; for everyone, switching the loss cut on at 15% would have gained $6.67 on 6 bets (4.8% of stake, 4.5 SE, the
newest 30% agree) but is short of the 10-bet band. No brake.

Nothing touches Pause, can_trade / the Pi, rule 8, caps, the tap lock or any buy/sell path. Tests: `t_knobstep.py`
(the bar fires only when every part holds; the holdout veto; bounds, mult steps and on/off; borrowed only stricter;
the resolver and the brake; #260's caps; #258's tied / one-of / product; one step a league, ties; invariants,
evidence knobs and settings never judged; shared/tied/waiting knobs never stepped; thin histories do nothing; the live
tuners' files untouched; weekly; 20 new results; errors and the time budget; the Pi; the brake's streak and month rules,
the Pi's rows, one push, reset, no re-trigger from old sales; with the shadow on every live decision byte-identical:
`smart_params`, `stoploss_params`, `sb_dial`, `exit_settings` and 400 `exit_policy` answers per league, `hedge_guard`,
`auto_cap`, `kalshi_discount`, the files and settings), `t_knobs.py` (only analytics and the watcher's `knob_pass` touch
the registry; no live code calls `knob()`), `test_knobshadow_ui.py`.

**CLAUDE.md rule 2 (for the release owner to fold in; this PR does not edit CLAUDE.md):** Pete's #228 opt-in
(2026-11-21) supersedes rule 2's auto-hedge limit "≤ $100 a hedge": the system may raise `hedge_cap` on evidence up to
a ceiling of **$150**, and `auto_cap` (automatic sales a day) with **no ceiling**; the brake returns both to Pete's own
values, and a value Pete sets himself is never lowered or clamped. Nothing raises either cap until a later #228 PR wires
their judge; Pause, the Pi, rule 8 and every other cap are unchanged.

ROADMAP: adds "#228 PR3: exit knobs go live: exit_policy takes the knobs as parameters (q floor, estimate allowances, take-profit minimum, lock-in trio, cut accept) so `_replay` can judge them; live smart sell reads `knob()` for the profit floor, risk weight and loss cut (and borrows only stricter, #259); a master 'let it tune itself' switch; the shadow log compared with what happened"
ROADMAP: adds "#228 PR4-PR7: CASH_SLIP and sale_outcomes judge (PR4), loss guards / break_ok shadow first (PR5), hedge knobs and the hedge_cap raise (PR6), Smart Buy simulator constants (PR7); split the shared knobs first"
