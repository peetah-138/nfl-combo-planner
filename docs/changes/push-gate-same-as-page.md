# Buy-idea pushes use the same gate as the Live page

**Problem.** Buy-idea pushes arrived but the idea was not on Live. Pushes and the page used different gates: the
single-line push (`line_pass`) had no gate at all (only "starts 5+ minutes away"), and the combo/single pushes used
only the Smart Buy part of the page's filter, failing open when the shadow had not yet written its row.

**Now.** One gate, `idea_push_ok(sid)`, covers all three push paths (`line_pass`, `shadow_pass`, `single_pass`):

- The idea must be on the page's own list right now (`live_ideas`: dismissed, bought, held, started, Smart Buy,
  low-credit and the top-15 cut all apply), and it must be the very quote the push links to.
- The game must start at least 15 minutes away (was 5, and absent for line ideas). No kick time on file: no push.
- Where Smart Buy's dial is active, the shadow's verdict must already be written; before, a missing row let it through.
- Anything unreadable or missing: no push (fails closed).
- `line_pass` pushes a given idea once; it re-stores after 2 hours as before, but only pushes again if the price got
  3+ points better.

**Findability.** The push already links to `/#s=<id>`; opening it runs `ideaReveal`, which unfolds the Buy ideas
section and the "N more ideas" list and scrolls to the card. An overlap-greyed idea is still listed (display only),
so it is found the same way.

**Unchanged.** Skip-only: this only holds pushes back. The idea cards, Smart Buy itself, and every buy, sell and
order path are untouched. Tests: `tests/suite/t_push_gate.py`.
