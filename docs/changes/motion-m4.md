# Celebrations, pull-to-refresh, boot and page transitions (package M4)

**Section:** Whole app (moments, pull-to-refresh, launch, tab changes)

Display only: nothing here reads or changes a price, bet, cap, Pause or rule 8; it fetches nothing.
New files `watcher/spa/motion4.js` and `motion4.css` (last in the css order, `motion4.js` before `moments.js` in
`MANIFEST.json`); `moments.js` and `boot.js` call into it. `live.js`, `build_cards.js`, `games.*`, `game.*`,
`results.*`, `common.js` and every money or server file are untouched.

- **Wins celebrate.** A big hit gets two confetti bursts (40 then 24 pieces, seeded, three shapes, drift and spin),
  a gold shimmer sweeping the payout, sparks leaving the number, and the label and profit chip rising in turn. A
  combo that wins gets one 32-piece burst; a sale at a real profit gets a small 18-piece burst, sparks off the check,
  and a soft glow on the amount and profit chip.
- **Losses stay sober.** A flat or losing sale gets no confetti and no sparks: a slower, opacity-only fade and a grey
  check or dash, no spring and no colour alarm.
- **Pull to refresh.** A halo ripples while the refresh really runs, the check pops when it lands. If the Mac link is
  down when it ends, the check becomes a grey dash, so the gesture never claims fresh data it did not get.
- **Boot.** The app opens under a brand-mark cover (painted by `<body>` on the first frame, so no white flash). It
  lifts once the first load finishes (held at least 0.45 s, gone by 1.5 s at the latest, and by itself after 2.4 s
  even if the script never runs), and the header settles in. It never blocks a tap.
- **Page transitions.** On a tab change the first six blocks rise 30 ms apart (never on a refresh); the browser's
  cross-fade is a quick fade-out and a rise; the chosen tab pops.
- **Rules kept.** Only transform and opacity (plus glow shadows on small elements), tokens `--dur-*`, `--elev-*`,
  `--ease`, `--out`, `--spring`. Reduced motion gets the final state only (no splash, no confetti, no stagger). Loops
  pause when the page is hidden; confetti is capped at 40 per burst and 64 on screen and removed when done, and
  skipped on a hidden page. `common.js` poll timing (#674) is not touched.

Tests: `t_motion_m4.py` (seeded confetti plan and caps, win/flat/loss tone, burst sizes, the motion gate, the
pull-to-refresh ending and the splash timing).
