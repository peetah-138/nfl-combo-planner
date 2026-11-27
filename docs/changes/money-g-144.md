# money-g-144: the pregame single Buy idea is priced like Buy straight (#286)

Only fail-closed changes. No new automatic money movement; no guard loosened. Switch `idea_pre_strict`
(Settings file, default ON; OFF = the old pricing).

## What changed

The web app's quote for a pregame single-game Buy idea (act `idea`) now takes its fair chance from
`idea_pre_fair`, the same rules as `single_buy_quote`:

- (a) the board's price must have been read within `SINGLE_FAIR_AGE` (12 min); an unknown age counts as too old;
- (b) a moneyline chance goes through `calib_fair` but only ever the lower of calibrated and raw (`min`), so it can never move up;
- (c) a board side with no sportsbook `src` (Kalshi's own normalised price, circular) is never a fair price;
- (d) the idea's stored `pfair` (up to an hour old, uncalibrated) is never used;
- (e) the suggested stake is the smaller of the old `edge_stake` and Buy straight's `_size` (never larger).

With no fair price the card shows Kalshi's price only, no edge, never green, at the smallest usual stake (the
same as an idea under way with no live fair price). Pete's own typed stake is untouched. The buy guards
(`singlebuy`: price, size, cap, Pause, unknown outcome) are unchanged.

## Live numbers that could move

Display and the suggested stake on the pregame single Buy idea card only:

1. the card's fair chance and edge (calibrated, or absent when the price is stale, circular or from the stored chance);
2. whether the card is green (`clears`): only ever green -> not green, never the reverse;
3. the card's suggested stake: only ever lower or equal.

Nothing else moves: not the panel, Smart Buy dial, smart sell, hedge, loss cut, caps, or any learned value.

## Looked at and left alone (see the PR text)

#142 leaks 1-8 and 10 are already shipped; leak 7 is covered by #341 (no idea on a game under way). #285 item 2 is
done (`_replay_real` haircut). The rest needs Pete or a design pass.

Tests: `tests/suite/t_idea_inplay.py` (stale, unknown age, circular, stored chance, calibration, spread, switch).
