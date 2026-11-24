# Wording batch 2: before fees, plainer "wouldn't buy", self-tuning words (issues #290, #304, #307)

**Section:** Build page (panel), Smart Buy, Results page

Text and display only; no buy, sell, sizing or gate logic changed.

- **Panel and combo screens:** a combo's "+X% expected" now says "before fees" (the combo entry fee is not counted in it), as do
  the combo screen's "Likely about X% of fair" guess, its "Kalshi will likely pay" line and the stake card's "Expected profit".
  Once "Tap for a fresh price" has answered on a Didn't-buy card (`S.prep[id].pct`), the card's own numbers are dimmed and
  say "earlier guess: pays about N% of fair", so one card no longer shows 106% and 99% side by side. On a combo screen with
  a fresh Kalshi quote, the older "Likely" / "will likely pay" guess is hidden (`pStale` in `build.js`).
- **"Still wouldn't buy" reason** (`_sb_under_words`, `SB_UNDER_FAIR_WHY`): "Kalshi's price is about 1% under what we think
  it's worth, so on average you'd lose about 2¢ per $2 if you held it to the end. Selling early could still make a profit,
  but not often enough to make up for that, so it is left out." The doubled "99% of fair, but Kalshi pays 99%" is gone; the
  gap is rounded once (`_gap_words`) and a share just under 100% reads "a little under". Smart sell is no longer named as
  the decider; both exits (sell early, hold) stay in the sentence.
- **Self-tuning card (#304, #307):** the brake reason says "less than holding was worth at the time"; sections are named
  "Changed (live now)", "Waiting its turn", "Held back: the newest bets disagree", "Still a test, nothing changes".
- **Smart Buy card (#290, #307):** "beats plain" is now "skips helping"; the scored-on-paper note reads "Only bets that
  would have made today's panel teach Smart Buy. The rest are for the paper book".
- Skipped: #313 (shows live money settings), #283 and #261 (card restructuring, not wording), the rest of #290 (card
  layout) and #307 items 3 and 4 (the banner already says it keeps stricter numbers; the haptics list is not a wording change).

Tests updated: `t_profit2.py` (A8, A8b, A8c), `t_knoblive.py`, `test_knobshadow_ui.py`, `test_analytics.py`, `t_sbgate.py`.
