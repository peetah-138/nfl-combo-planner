# Motion M3: Games tab, game sheet, Results

Display only. Nothing here touches a price, bet, cap, Pause or rule, and nothing fetches. New `watcher/spa/motion3.js` and `motion3.css` (last in their lists) wrap `renderGames`, `renderResults` and `paintGame`; each hook is in try/catch so an error leaves the page as drawn. Only transform and opacity animate, on the `--dur-*` tokens.

- **Honest motion.** A moment fires only between two real consecutive pictures: never on the first paint, after a gap over 90 s, after a stale picture, on a stale feed (page `.old` threshold, 60 s), in a hidden tab, or with reduced motion. Stale or hidden also hides the "+N" chips and pauses running animations.
- **Games tab.** A live score that goes up flips its digits and a "+7" rises off it (green for your side, grey for the other). A win-chance move of 3+ points shows a "+8 pts" chip; 10+ also sweeps a highlight across the bar. The bar is now a transform (`scaleX`, `data-m3b`) that eases from its old value, not a width. A card that just finished gets a win pop or a slow loss dim and keeps a calm tint (win) or dim (loss); spread and total cards are left plain. First paint or skeleton-to-content: cards rise in six at a time, 30 ms apart, and the skeleton fades out over the content.
- **Game sheet.** The scoreboard digits flip with a "+N" chip (`data-still` keeps the number roll off them), the win-chance number gets its move chip and a pop on a 10+ point move; first open staggers the KPI tiles and fades the chart in.
- **Results.** The P/L, ROI and scoreboard numbers count up (about 0.8 s for a profit, 0.5 s flat or loss); a real profit also pops the tile. Profit bars grow from their baseline, history rows settle in 30 ms apart, a winning row gets a thin green underline, a loss just fades.
- Tests: `t_motion_m3.py` (pure logic under node: gate, score and chance moves, final tone, diff gating, bar slide, stagger, tone, count text).
ROADMAP: none.
