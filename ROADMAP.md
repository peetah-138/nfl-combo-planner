# Roadmap: planned work not done yet

Everything we've agreed on or lined up but haven't built, as of version 2026.11.19.119 (Nov 18, 2026).
What's already built is described in `CLAUDE.md`. When an item ships, move its facts into `CLAUDE.md` and delete it
here; when Pete adds or drops something, update this file in the same change.

Items are grouped by what they're waiting on: **you (Pete)**, **data**, or **just building**.

---

## 1. Waiting on Pete

### Novig (a second exchange)
- **What:** read Novig's prices alongside Kalshi's, and later buy wherever the price is better.
- **Waiting on:** a **read-only API key** from the Novig app (Profile › Settings › Novig API, if Pete's account has it).
- **Then:** price comparison first (show when Novig beats Kalshi for the same bet, read-only), and only later, with
  Pete's explicit opt-in, any buying there. Each exchange needs its own revocable key; same security rules as Kalshi.

### Polymarket as a place to buy (not just a price source)
- **Today:** Polymarket prices are already averaged into the "fair" price for some leagues (`poly_games`).
- **Planned:** take the better price between Kalshi and Polymarket when buying. Pete has no Polymarket account yet.
- **Waiting on:** Pete deciding to open an account. Then the same path as Novig: compare first, buy only on opt-in.

### Secure address (https) on the Mac
- Needed for Face ID sign-in and iPhone notifications. Settings › This Mac › Secure address now shows exactly
  where it's stuck. If it says "one step left", Pete taps **Allow https**, approves in Tailscale, then **Check**.
- Code fixes are in (PR for issue #5, not yet confirmed on Pete's Mac): the watcher can now read Tailscale under launchd
  (prefers `/usr/local/bin/tailscale`, `TAILSCALE_BE_CLI=1`, stdin closed), every failure says what is wrong, it retries
  every 5 minutes, and all alerts (panel buys, extras, recap) also reach web push.
- **Waiting on Pete (stays until he confirms it works):** in Tailscale admin (login.tailscale.com/admin/dns) scroll to
  **HTTPS Certificates**, tap **Enable HTTPS...**, confirm. Then in Combo Hub on the Mac: Settings › This Mac › Secure address
  (Check if needed). Then on the iPhone open the ts.net address in Safari, Add to Home Screen (delete the old icon: a
  different address is separate storage), and turn on **Face ID sign-in** and **Notifications on this device** (each needs a tap).

### Secret guard on the Mac
- The Mac session should set up a local `.git/hooks/pre-commit` (and `SECRET_PATTERN` for the check list) with the
  strings Pete gives it. They must never be written into a tracked file.

### The old "Sell at a loss" switch (`stop_loss`)
- Kept for now as a labelled manual override in Settings (behaviour unchanged). Decide: keep it, or remove it now that
  the learned per-league loss cut exists.

### The $300 full-auto experiment
- The Mac picks, times, buys and sells on its own with $300. **Only after** the paper panel clears the gate
  (50+ settled bets, ahead overall, ≥ 55% of days up, CLV ≥ 0), and only when Pete then says go. Results › the
  paper gate card shows progress. Building the switch itself is small; the decision is Pete's.

---

## 2. Waiting on data (decisions with a date)

### Buy timing (≈ early December)
- **Question:** should the panel buy earlier than ~45 minutes before a game? Pete saw good prices disappear
  before the buy time.
- **Data being recorded:** price at build, at buy, and at game time for every panel and paper bet.
- **Then:** compare how much price is lost or gained by waiting, by league and bet type; move the buy time
  (per league if it differs) and explain it to Pete before shipping.

### The combo cut-off, from the combo lab (≈ 2–3 weeks)
- The lab paper-buys combos at 80–85, 85–90, 90–95, 95–100 and 100+% of fair, and replays smart sell on them.
- **Then:** if lower bands come out ahead *after* smart-sell exits (Pete's theory: cheap combos are fine if we rarely
  ride to the end), let the cut-off's self-adjustment use the lab's results, and revisit the 85% floor with Pete.
  Results › What's working › Combo price levels shows it as it fills in.

### Self-tuning smart sell, first moves (≈ 1–2 weeks)
- Nothing to build: each league starts moving once it has ~30 settled bets with recorded game prices. Worth a check
  that the first changes (Results › Selling) look sensible, and that the reasons read clearly.

### Calibration and the paper gate
- Fair-price calibration and the paper panel's record fill in on their own; just watch for oddities.
- **Question for Pete:** calibration learns per league (borrowing its sport's) but, unlike the cut-off, a sport
  with no games in a chance band keeps the books' chance rather than borrowing everyone's record (borrowing would
  change today's numbers and jump once the sport's first game lands). Mix everyone's in as a third level?

---

## 3. Ready to build (suggested order)

### a. Finish the makeover (Pete: "make it exceptional", like Kalshi's app; issue #12)
Phases 1, 2 and 3 shipped (phase 1: haptics and press feedback on everything, Live polish, push transition, hero
chart scrub; phase 2: live Games cards, score pulse, scrubbable game chart, the Sold moment, the big hit, Results
profit bars, skeletons; phase 3: every remaining screen (Build, Settings, Results, login, sheets) in the same motion
system, the reconnecting banner, error cards, pull to refresh everywhere, header collapse, safe areas, keyboard-aware
sheets, Let it ride detents, light mode, the recap streak note, panel sparklines; see `CLAUDE.md`). Kalshi/Novig
references and a frame-by-frame motion brief are in issue #12's comments. Still to do:
1. **Game page drill-down** (Kalshi live game page): team rows with scores, a live chance chart per side (or both on
   one chart; scrub is in), range switcher (LIVE/1D/1W), outlined pills with payout multipliers, a strip of other live
   games to hop between, a one-line plain-English summary. Coordinate with the faster-live work on the game page's refresh.
2. **A shareable result card** (copy image / share) for Sold and Won, like Kalshi's "Position closed" card.
3. **Charts to drill into:** bet value over time with scrub (combo page), charts for Results › What's working.
   Panel cards' price line is from what the phone has seen; a server-side price history per panel bet would make it
   complete (needs an API field, so it was left out of the UI-only phase).
- Haptics on the Home Screen app still need checking on Pete's iPhone (the `<input switch>` route; ticks while
  dragging the chart or the Let it ride slider may need a real device to confirm), and the safe-area / keyboard
  handling wants a look on the real Home Screen app.
- Rule: send Pete screenshots or a short clip before shipping visual changes.

### c. Faster live numbers, the rest (GitHub #21; first slice shipped)
- Shipped: 8 s score cache and Live snapshot while a game is on, the fresh snapshot served, a game sheet that redraws
  itself with a ticking clock, "Updated Ns ago" stamps, polite caching with backoff. See CLAUDE.md, Live page.
- Next, in order: (1) the watcher pushes every score change over the live link (today only basketball lead changes
  produce an event; other sports rely on the 8 s poll); (2) one shared scoreboard read for the Mac and the web app, so
  ESPN is asked once per 6 s however many screens are open; (3) a faster Kalshi price read for the games on screen.
  Measure with the `fresh` block on `/app/api/live` (`built`, `scores`) before changing anything else.

### d. Live scores for every sport, the rest (GitHub #25; display shipped)
- Shipped: tennis, EuroLeague and UFC scores from Kalshi's public live data, display only (see CLAUDE.md).
- Still open: (1) **UFC in-fight detail is unverified**: no fight was live when it was built, so only the round is
  read and the page says "no clock"; check the `/live_data` fields on the next fight night and add the clock if one
  exists. (2) How fast Kalshi's live data updates during play is unmeasured; log it on a live match before tuning
  the 8 s cache. (3) **Waiting on Pete:** these scores feed nothing that sells or decides a result (smart sell, early
  results, the started-game rules still use ESPN/the AHL feed only). Letting smart sell use them (per sport) is a
  separate opt-in. (4) Kalshi also covers the AHL (as a backup to the league feed) and cricket, darts, volleyball etc.;
  not wired in since the AHL feed works and we don't bet those.

### e. Friends could use it (onboarding)
- Pete wants an app friends would want to use. Today it's one person, one Mac, one Kalshi key. A friend-ready
  version needs: a guided first-run (connect Kalshi with their own key, pick sports, set a budget), plain
  explanations of the panel and smart sell, and a setup that doesn't need a terminal. Scope this with Pete first;
  it's the biggest item here.

---

## 4. Ideas mentioned but not agreed

- A **"Sell now" button** on single bets and spreads on Live (Pete chose automatic smart sell with a per-bet
  "I'll sell it" switch instead; revisit only if he asks).
- A **lower starting combo cut-off** (e.g. 90%) for the real panel: on hold until the combo lab's results are in.
- **Paid odds data**: not planned; Pete is staying on free sources.

---

## Keeping this file honest

- Pull before editing; two Claude sessions may work on this repo.
- When something ships: describe it in `CLAUDE.md`, remove it here, and mention both in the commit.
