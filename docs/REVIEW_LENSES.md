# Review lenses: profit and delight

Pete's rule (2026-11-20): **whenever you build anything, it gets a review for profit and delight.**
Goals, in order: **profit is #1, fun is #2.** Every PR gets four reviews: code, security, profit, delight.
Builder agents run all four on their own diff. The release agent runs all four on the whole release diff.

Each lens below works as a prompt for a reviewer agent (paste the section plus the diff or PR number) and as a
checklist for a person. Real money is involved: read `CLAUDE.md` first, especially the hard rules.

The strategy both lenses protect: **Smart Buy and Smart Sell are one strategy** (issue #137). Every buy needs
an edge at a fair price *and* a likely route to profit (a good chance to cash out through the shared exit policy,
or a hold with an acceptable win chance).

---

## PROFIT lens (goal #1)

### Questions

1. Does this change raise expected profit or protect the bankroll? Say which, in one sentence. "Neither" is a valid
   answer for pure plumbing, but then say what it could cost.
2. Every path that recommends, sizes or buys: is there an **edge at a fair price**? Is the fair chance calibrated
   (`calib_fair`), is the line fresh, are fees counted, is the bid-ask gap small, and is there fillable depth for
   the size?
3. Is there also a **likely route to profit**? Either a decent chance to cash out (through the shared exit policy
   Smart Sell uses) or a hold whose win chance is acceptable. A bet with edge on paper and no way to realise it is
   not a bet we want (issue #137).
4. **Dollars, not pennies.** Is ranking by expected dollars (not cents or percent)? Is continuation value used
   instead of a fixed floor? Are partial exits considered? Is regret measured in dollars?
5. Sizing and caps: does stake respect the per-bet cap, the daily budget and the base? What happens when data is
   unreadable, stale or missing: does it **fail closed** (no buy, no sale) with a logged reason?
6. Does Smart Buy know Smart Sell? Is the buy-time plan (how and when we expect to exit) recorded and consistent
   with what Smart Sell will do later?
7. Does the screen show expected profit **in dollars**, in plain English?
8. Is it **measured**? Scoreboard (#138), scorecard (#115), old-versus-new logging, and a switch to turn it off.
9. Are non-recommended lines kept off the screen? No walls of options that fail the edge or exit tests.
10. Money movement: is anything *automatic* new? It needs Pete's explicit opt-in. Is **Pause** respected on every
    new path? Does the Pi stay alerts-only?

### Red flags

- A buy or size decided on edge alone, with no exit route or win-chance check.
- Ranking by percent or cents when dollars at stake differ a lot.
- A hard-coded floor or threshold where the data could tune it per league.
- Missing, stale or unparseable data treated as "fine" (fail open), or a cap that silently stops applying.
- Fees, bid-ask gap or depth ignored; a fair price taken from a stale line or the pre-game price of a live game.
- A new buy or sell path that skips `Pause`, the daily cap or the "outcome unknown means check, never retry" rule.
- New automatic money movement without Pete's opt-in; anything that lets the Pi trade.
- No log, no switch, no way to compare against the old behaviour.
- Lines shown that the system would not itself recommend.
- Secrets, key IDs or topics in tracked files (the repo is public).

### What good looks like

- One sentence in the PR: "raises expected profit by X because Y" or "protects the bankroll by Z".
- Edge and exit route are both checked in the same place, from the same functions Smart Sell uses.
- Rankings and sizes are in expected dollars; the screen shows the dollars.
- Unreadable data means a calm "skipped: reason", never a guess.
- It ships behind a switch (or is a strict tightening), logs old versus new, and feeds the scoreboard/scorecard.
- A test proves the guard, including the fail-closed path.

### How to report

List findings **ranked by dollars at risk or gained**, highest first. For each: where (file and function), what is
wrong, the likely dollar effect, and the fix. Mark each as:

- **Fix in this PR** (anything that can lose money or break a hard rule; always fixed here), or
- **File an issue** with label `profit` (improvements that can wait), linking the PR.

End with a one-line verdict: "profit review: pass" or "profit review: N fixes made, M issues filed".

---

## DELIGHT lens (goal #2)

### Questions

1. **Haptics (iOS 27):** only a finger landing on a real `<input switch>` ticks. A haptic fired after an `await`,
   a timer, or without a tap is **silent**. Is every haptic tied to a tap, and is the result moment gated on that
   tap? (Issues #60, #116, #140.)
2. Do results arrive as **moments**: bought, sold in profit, a win, a day up? Are they tap-gated where haptics are
   needed? Does hold-to-confirm fit this action (big or hard-to-undo buys and sells)?
3. Do numbers **roll** and flash green or red when they change? Do transitions move smoothly with **no layout
   jumps** (reserve space, animate height, avoid late-arriving content)?
4. Loading, empty and error states: skeletons while loading, charming and useful empty states, errors with a
   **shake** and an **inline reason** (not just a toast that disappears).
5. Accessibility: **44 pt** minimum hit targets, `:focus-visible`, `aria-live` for changing results, labels on icon
   buttons, `prefers-reduced-motion` respected.
6. Phone performance: no runaway `requestAnimationFrame` loops, sparing use of blur and big shadows, long lists
   kept cheap, a small overlay count, listeners cleaned up.
7. Does the display code **never slow or stop the trading loop**? (It must not take the trading lock for long,
   raise into the engine, or add work to the watcher's loops.)
8. Plain English, short screens, noise filtered out. Does it feel as good as Kalshi's own app?

### Red flags

- `hap()` called after `await`, in a `setTimeout`/`requestAnimationFrame`, or from a poll or push (silent on iOS 27).
- A result that appears with no moment, or a moment that needs a tap but has no tap behind it.
- Numbers that jump instead of rolling; content that shifts the page when it loads.
- Blank screen while loading; "No data" with no guidance; an error that says only "failed".
- Tap targets under 44 pt; missing focus ring; live changes not announced; animation ignoring reduced motion.
- A rAF loop that never stops, stacked backdrop blurs or large shadows on scrolling lists, hundreds of DOM nodes
  where a few would do, listeners added on every redraw.
- UI work that blocks or waits on the trading lock, or that raises into the engine.
- New controls that miss the press feedback and tick (`test_motion.py` audits this).

### What good looks like

- Every tap feels answered within a frame: press shrink, tick, then the result moment.
- Wins and sales are celebrated; losses are calm and honest.
- Numbers roll, bars slide, pages push in; nothing jumps.
- Empty and error states are friendly and tell the person what to do next.
- It works with a thumb, a screen reader and reduced motion, and stays smooth on a phone.
- Screenshots or a short clip are in the PR for visual changes.

### How to report

List findings **ranked by how much they hurt the feel on a phone**, highest first. For each: where, what the person
sees or feels, and the fix. Mark each as:

- **Fix in this PR** (silent haptics, jumps, broken accessibility, anything that slows trading), or
- **File an issue** with label `fun` (polish that can wait), linking the PR.

End with a one-line verdict: "delight review: pass" or "delight review: N fixes made, M issues filed".
