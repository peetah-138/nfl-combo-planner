# Money batch J: follow-ups checked (#525, #451, #309, #316)

**Section:** Results › What's working (self-tuning registry label only)

Each issue was read against develop first.

- **#525** closed already (PR #548 merged). Nothing to do.
- **#451** already fixed on develop (PR #550: an unclear order hides a Buy idea only while it may be live, and the check
  fails closed when the singles read fails). Nothing to do.
- **#316 items 1-2** already in develop (see the issue comment and PR #546). Items 3-5 change sell behaviour, left for a
  money-path pass.
- **#309, first bullet** fixed here: the registry marked the live exit knobs `borrow: "none"` while `knob_live_value`
  does borrow them from the sport / everyone, never looser than the start. They are now `chain-stricter`, which is what
  the code does. A label only: no number, gate or order changes. Test: `t_knobborrow_309.py` (fails on base).
- **#309, other bullets** left open on purpose: `_knob_items` kick time, `sb_resolve` duplicates and `sb_paper_build`
  chunking change what the stepper judges or how reads are done, not caution. The `ideas.js` null check is already fine
  (`pct(null)` shows a dash). The lowest-value `auto_sell_now` test is a test-only addition, not done here.
