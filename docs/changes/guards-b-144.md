# Guards batch B: follow-ups checked (#451, #352, #177, #182, #525)

Every item was re-read against develop. All five are already fixed, so this batch changes no code.

- **#451** (lost reply hides a Buy idea 3 days): fixed in PR #550. An unclear order hides the idea only for
  `IDEA_UNSURE_SECS` (2 hours), and it comes back only when the Mac has a fresh read of what you hold built after the
  order (`_idea_unsure_over`); no view of positions stays hidden. Tests: `t_money_g.py`.
- **#352** (in-play Buy ideas ungated with Smart Buy off): fixed in #348. `smart_buy_ideas_gate` gates in-play ideas
  whatever the switch. Test: `t_comeback.py` (`t_ideas_gate`), `t_inplay_exit.py`.
- **#177** (gate Buy-idea pushes like the page): fixed in PR #559. `idea_push_state` requires the idea to be on
  `live_ideas` (which applies the Smart Buy and low-credit gates) and waits for the shadow verdict. Test: `t_push_gate.py`.
- **#182** (tag draw sides; end-to-end low-credit test): fixed in PR #565. `attach_fair` tags draw sides with the game's
  `sharp_line`, and `t_lowcredit.py` section E runs `attach_fair` -> `_cand` -> `idea_legs_info`.
- **#525** (real-offer ask follow-ups): items 1 and 2 fixed in PR #548 (the card counts lock-in and the guarded
  stop-loss as exempt asks; the under-cost test is stopped by the cost rule, `t_realoffer_227.py`). Item 3 (a combined
  hourly cap for exempt asks) was left as is on purpose: it is the same 60 s cadence as before and a cap could delay a
  stop-loss or lock-in sale, so adding one would loosen a guard's reach rather than tighten it.

Open issues #451, #177 and #182 can be closed.
