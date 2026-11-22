# Buy idea fresh price: a game under way is priced only on a live fair chance (issue #255)

**Section:** Live page (Buy ideas), next to "Buy ideas: ration, dismiss, fold, detail"

Pete's ruling (2026-11-21, option 2). A single-game Buy idea's fresh price ("Get today's price", web app act `idea`)
used to take its fair chance from the Build board's side for that game. For a game under way that number can be the
pre-game price (the board was built before the start, or `screen_live` left the game out) or Kalshi's own mid from when
Build was built, never a real live fair. Now the quote goes through the engine's `idea_single_fair(tk, side, pfair,
book, kick, row_live)`:

- **Before the game: unchanged.** The board side's fair (else the idea's own `pfair`, the model chance for a
  spread/total), the same number, edge, sizing and green-Buy rule (`edge >= SINGLE_MIN_EDGE * 0.6`) as before. The
  answer now also names the source (`fair_src`: "sportsbooks", "line model", "Kalshi's price", "when found").
  Note: this path still does not apply Buy straight's 12-minute `SINGLE_FAIR_AGE` rule or `calib_fair` (it never did);
  filed as a separate profit issue rather than changed here.
- **Under way** (`started()` on the board side, the idea's start time passed, or the idea saved as live): the fair
  chance comes only from `live_side_fair`, exactly as Buy straight prices it: a live sportsbook line read in the last
  `LIVE_LINE_AGE` (180 s), else the live model on a fresh score (`LIVE_SCORE_AGE`). Spreads/totals under way have none.
  A finished game = "That game is over" (gone, no quote). Buy straight's cautions come along (`warn`): under way (with
  the source), nearly decided (`LIVE_DECIDED`), Kalshi's mid far from the live chance (`LIVE_DISAGREE`), thin (gap over
  `LIVE_SPREAD` or nobody bidding). A thin market under way is never green (as on Buy straight).
- **No live fair:** the quote still gives Kalshi's price, contracts and payout, with `fair`/`edge`/`pct`/`ev` null,
  `fair_src: "none"` and `nofair` (why). The card and the detail page show "—" for the fair chance and the edge, the
  source line "none", "No fair price to check this against (why). You'd be going on Kalshi's price alone." and a yellow
  **Buy anyway** (never green, no "no longer a good bet"/"under your bar" math). Suggested stake = `size_min`.
- **Combos with a game under way:** they price at Kalshi's RFQ against the board's leg chances (`add_own_combo`); a
  live leg the board priced live (`screen_live`: Kalshi's mid, `live=True`) is kept as today. A leg whose game is under
  way but whose board chance is still the pre-game one (`idea_combo_live_gap`) was the same hole: such a quote now comes
  back `clears: false`, `pct`/`ev` null, `fair_src: "none"` and `nofair` naming the game, so the card says "No fair price
  to check this against" with a yellow Buy anyway.
- Card and detail page: "Kalshi's price now · game under way" when live, a small source line under Fair chance /
  Share of fair (`ideaSrc`: "live line" / "live model" / "none" / the pre-game source) and the cautions (`ideaWarn`,
  Buy straight's `.sbw` style). `watcher/spa/ideas.js`, `ideas.css` (`.ifsrc`).

Unchanged: every buy guard (Pause, the market's own league cap failing closed, the unknown-outcome block, one order per
idea and per market per `IDEA_TAP_SECS`, the Mac's own quoted size and price only (`IDEA_Q`), IOC at the ask, rule 8:
"check" never resent). This changes only which fair chance a quote shows and when it is green. Tests: `t_idea_inplay.py`
(live line, stale live line rejected, live model = Buy straight's number, neither, stale score, spread under way,
finished game, cautions, pregame unchanged, hiccups, combo legs, the watcher wiring), `test_idea_inplay_ui.py` (card
and detail states, buttons, no green without a live fair, the combo case).

CLAUDE.md-notes: in "Live page", after the #141 Buy ideas paragraph, add a bullet "Buy idea fresh price for a game under
way (#255)" with the paragraph above, shortened.

ROADMAP: none
