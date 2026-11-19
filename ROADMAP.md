# Roadmap: planned work not done yet

Everything we've agreed on or lined up but haven't built, as of version 2026.11.18.118 (Nov 18, 2026).
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

---

## 3. Ready to build (suggested order)

### a. Finish the makeover (Pete: "make it exceptional", like Kalshi's app)
1. **Games page:** live game cards that pulse when someone scores, with the score, clock and a live chance line;
   include single bets and spreads (today Games only lists games inside combos).
2. **A "Sold" moment:** cashing out (by tap or by smart sell, when the page is open) gets the same drawn-check sheet
   as buying, showing profit, not just a toast. Losses get a calm version.
3. **More celebration moments:** a bigger celebration for a big hit, a streak note in the morning recap.
4. **Polish pass on every screen** for consistency: spacing, type sizes, empty states, loading skeletons, light mode.
5. Research Kalshi's own app interactions (the cloud session couldn't open kalshi.com) and borrow what fits.
- Rule: send Pete screenshots or a short clip before shipping visual changes.

### b. Everything learns per league, not just per sport (Pete's rule)
- **Combo cut-offs** are keyed by sport and combo size (`_cut_key`); soccer's leagues share one. Move to league keys
  with the same borrowing (league → sport → everything) the smart-sell tuning uses.
- **Fair-price calibration** (`calib_fair`) is per sport; make it per league.
- **Sizing and the panel's sport priorities** should read league-level results too.

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
