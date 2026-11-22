# Flipping a leg on a combo idea (issue #104)

**Section:** Build page (after "Combo idea card buttons (issue #65)")

**Flipping a leg on a combo idea (issue #104, display only; `flip`/`swap` acts, quotes and buys unchanged).** Tapping a leg row
(`flipLeg`) drops any fetched Kalshi quote on that card **at once** (Buy can't be tapped on a price for other legs; `buy()` and
`quote()` also return early in the phase) and puts the card in phase `flip` (`S.fpend[i]` is the flip's own token object, kept across
redraws like `ask`/`buy`): the row folds, the numbers that depend on the flip (`.dep`: fair payout, chance, estimate line and the
previous "Good flip" note) shimmer, Get price is a disabled "Updating…" (`data-stale`), Not this one is off, a second tap does
nothing. The quote line's space is kept (`.qgap`) and the note box and button widths are fixed, so nothing jumps. After at least
`FLIP_MIN` (220 ms) the answer is applied **only if** this flip still owns the card (token), the league (`S.lg`) is the same and the
card still has the tapped legs (`ccSig`); otherwise it is dropped and the card just redraws. Applied: the new row turns in, numbers
roll, the note slides in. Failed: a short shake on the row, an inline "Couldn't flip" note and a toast. One page-level polite
announcer (`#flipsay`, `flipSay`) says "Updating…" then the verdict. Reduced motion = a crossfade. No `hap()` in the flip (the global
tap tick only; iOS ignores later ones). Leg rows are keyboard buttons (44 px, focus ring). Test: `test_flipleg.py`.

The flip gap (`.qgap`) covers the quote line **and** the amount row (`stakeCtl`, which hides while a flip is on its way), measured as the distance from the first of `.qline`/`.stk` to the buttons minus the card's 10 px row gap.
