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
  Note: this path still does not apply Buy straight's 12-minute `SINGLE_FAIR_AGE` rule, `calib_fair` or `_size` (it
  never did); filed as #286 rather than changed here.
- **Under way** (`started()` on the board side, the idea's start time passed, or the idea saved as live): the fair
  chance comes only from `live_side_fair`, exactly as Buy straight prices it: a live sportsbook line read in the last
  `LIVE_LINE_AGE` (180 s), else the live model on a fresh score (`LIVE_SCORE_AGE`). Spreads/totals under way have none.
  A finished game = "That game is over" (gone, no quote). Buy straight's cautions come along (`warn`): under way (with
  the source), nearly decided (`LIVE_DECIDED`), Kalshi's mid far from the live chance (`LIVE_DISAGREE`), thin (gap over
  `LIVE_SPREAD` or nobody bidding). Under way, thin, nearly decided or far-from-Kalshi is never green (yellow Buy anyway;
  the panel leaves such games out). Build's live side (`screen_live`) holds Kalshi's own mid with the odds' `line_live`/
  `line_at` still on it, so a side marked `live` is never taken as a live sportsbook line (`line_live` off: the live
  model instead).
- **No live fair:** the quote still gives Kalshi's price, contracts and payout, with `fair`/`edge`/`pct`/`ev` null,
  `fair_src: "none"` and `nofair` (why). The card and the detail page show "—" for the fair chance and the edge with "no
  fair price" under it, "No fair price to check this against: <why>. You'd be going on Kalshi's price alone." and a
  yellow **Buy anyway** (never green, no "no longer a good bet"/"under your bar" math). Suggested stake = Buy straight's
  $2 (`max(OWN_MIN, 2.0)`), labelled "smallest bet" / "Smallest $2", never "recommended" (`stakeCtl`'s `small`).
- **Combos with a game under way:** found today: they price at Kalshi's RFQ against the board's leg chances
  (`add_own_combo`), and a leg under way there holds either the pre-game price (Build built before the start, or its live
  checks left the game out) or Kalshi's own mid from when Build was built (circular, minutes old). Same hole, so any leg
  under way (`idea_combo_live_gap`) = no fair price: the quote is asked at $2 (when Pete set no amount, never sized on
  that edge) and comes back `clears: false`, `pct`/`ev` null, `fair_src: "none"`, `rec` $2 and `nofair` ("the X game has
  started, and a combo with a game under way has no live fair price"): yellow Buy anyway.
- Card and detail page: "Kalshi's price now · game under way" when live, a small source line under Fair chance /
  Share of fair (`ideaSrc`: "live line" / "live model" / "none" / the pre-game source) and the cautions (`ideaWarn`,
  Buy straight's `.sbw` style); a thin market under way says so (not "under your bar"); the "chance has dropped" line is
  skipped for a live chance (it moves all game); "Why it was picked" starts "Before the game:" for a game under way;
  "Could you sell it?" says "selling now" during a game. `watcher/spa/ideas.js`, `ideas.css` (`.ifsrc`), `stake.js`.
- **Buy straight** (`single_buy_quote`) gets the same two tightenings: a `live` side is never a live line, and a
  nearly decided or far-from-Kalshi game under way is never green.

Unchanged: every buy guard (Pause, the market's own league cap failing closed, the unknown-outcome block, one order per
idea and per market per `IDEA_TAP_SECS`, the Mac's own quoted size and price only (`IDEA_Q`), IOC at the ask, rule 8:
"check" never resent). This changes only which fair chance a quote shows and when it is green. Tests: `t_idea_inplay.py`
(live line, stale live line rejected, live model = Buy straight's number, neither, stale score, spread under way,
finished game, cautions, pregame unchanged, hiccups, combo legs, Kalshi's mid never a live line, Buy straight's
"nearly decided" never green, the watcher wiring), `test_idea_inplay_ui.py` (card
and detail states, buttons, no green without a live fair, the combo case).

CLAUDE.md-notes: in "Live page", after the #141 Buy ideas paragraph, add a bullet "Buy idea fresh price for a game under
way (#255)" with the paragraph above, shortened.

Filed from the reviews: #286 (pregame idea freshness/calibration/sizing), #287 (learned live-model bar).

ROADMAP: none
