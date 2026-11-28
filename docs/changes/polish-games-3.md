# Games tab and game sheet polish (package B, display only)

**Section:** Games tab, game sheet. No money, sizing, buy or sell behaviour changed.

- Game cards: one "Your pick" tag in the card header (not on the team row), team names clamp to two lines, scores are tabular and right-aligned, the empty chance row still keeps its height (kept from #664), bet chips stay on one row (two chips, then "+N"), section headers are 44px tall with plain helper text, bet-type chips are 44px.
- States: a loading skeleton (`aria-busy`) while games load, a plain "Games didn't load" card with Try again, and empty states ("No games to watch yet", "No games for this bet type" with Show all games).
- Game sheet: a friendly "This game didn't load" (Try again) or "This game isn't on the board" instead of "Game not found"; tabs are 44px; small labels are at least 11px; numbers are tabular; the buy bar is opaque, pinned, has safe-area padding and a one-line note that the price can differ slightly from the chance above; buy buttons carry a spoken label.
- Not done: a skeleton on tab switch (the tab data is already loaded, the swap is instant). `scoreboard.*` is the Results profit scoreboard (another package) and was left alone.

Tests: `tests/suite/test_games_polish.py`; `test_gamecard_opp`, `test_makeover2` and `t_nomoney_batch5` updated for the new markup.
