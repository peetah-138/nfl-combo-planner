# Live motion (package M2)

**Section:** Live tab and Your Combos cards

Display only: nothing here reads or changes a price, bet, cap, Pause or rule 8. All of it lives in `watcher/spa/live.js`
(one small block at the end, called once from `renderLive` inside a try/catch) and `watcher/spa/live.css`. Only transform and
opacity animate, on the `--dur-*` tokens, and every block has its own reduced-motion rule.

- **Honest live dot.** The Live dots (hero and on in-play leg chips) pulse with a spreading ring only while the feed is fresh and
  the tab is visible. A stale feed (older than 60 s, network down, live link dropped) turns them grey and still. A hidden tab
  pauses them.
- **Leg hit.** When a leg turns into a win between two real consecutive refreshes, its chip pops once and a green ring spreads
  from it. A leg that turns into a loss only dims once (sober, no shake, no red flash).
- **Combo win and loss.** A combo that just won gets a gold sheen across the row (twice) and its verdict pill pops. A combo that
  just lost fades in grey, nothing else. A combo that first appears already settled is not celebrated.
- **Hot combos.** A pending combo whose real Kalshi offer is 80% or more of what it pays (or one flagged as a moment) gets a slow
  soft sheen while the feed is fresh. At most two rows at once, closest to paying first; estimates never count.
- **First paint.** Leg chips settle in 30 ms apart after their row (first six), on the first paint of the tab only.
- Existing and untouched: number roll on worth-now and the offer (`rollNums`), row stagger, `.fl-up/.fl-down` flashes.

Honest motion: moments fire only between two real snapshots (not after a gap over 90 s, not when the earlier one was stale, not
while hidden, never with reduced motion). Numbers are always final in the DOM.

Tests: `t_live_motion.py` (exact values for the hit/miss/win/loss diff, the gate, and the hot-combo rule).
