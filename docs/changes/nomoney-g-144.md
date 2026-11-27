# Scoreboard follow-ups: Live idea buys tagged apart, stricter "more than luck" bar (issue #187)

**Section:** Results > scoreboard

Labels and words only. Nothing here changes what is bought or sold, sizing, Pause, or any setting.

- **Live idea buys tagged apart:** buying a Live buy idea's single game now tags it, so "Where it came from" lists
  "Live buy ideas" on its own line and the old "Build & Live ideas" line is now "Build and other app buys". Bets bought
  before this change stay under the old line (no history is rewritten). One tag write before the order; the order,
  its caps and checks are untouched.
- **Fairer "more than luck" sentence:** each breakdown's sentence tests several groups at once (about 10 leagues), so
  one will look special by luck now and then. The bar for "keep it" / "worse than luck explains" now rises with the
  number of groups (2.5 standard errors for a couple of groups, about 2.8 for ten). Combos have heavy tails (a few
  big wins), so a combos row also needs 30 settled bets before it gets a verdict (other groups still 20).

Checked and already done or taken: #431 (open PR #465), #494 (open PR #502), #483 (open PR #487), #453 #112 #140
(merged #598), #112 hero-estimate stale price (already counted as not fresh). Left out as large or needing Pete's
call on design: #63 #64 #69 #72 #78 #148, #512 (new recorder), and the rest of #187 (weekly push, settings links,
timing for non-panel bets, feeding `smart_tune` is a selling change).

Tests: `t_nomoney_g.py`.
