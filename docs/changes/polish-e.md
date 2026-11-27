# Polish E: no double refresh after an incomplete account read (issue #457)

**Section:** every screen that refreshes when money moves

Display refresh only: nothing about buying, selling, sizing or balances changes.

- **#457 (double-stamp half):** when an account read left a combo out (its legs couldn't be read) and a position or the
  balance really changed, screens were told to refresh. The very next complete read then saw the same change against its older
  copy and told them to refresh again. Now that second read stays quiet when only the already-announced money change differs and
  no combo changed (`money_note`, `nfl_combo_planner.py`). The no-id failed-sale key half was already fixed in #523.
- **Already done on develop, no change here:** #435 (`pReprice` restores focus and announces via `#repLive`), #438 (Comebacks
  panel slides closed), #439 (Add anyway spinner and "Showing..."), #456 (Buy button keeps its width, polish-b / #557),
  #414 (Best bets, Single games and Buy-lines already drop any market Pete holds, just bought or has an unclear order on, via
  `held_markets()`, #419). Only a combo card that happens to include a held single stays listed; that is a different bet.
- No screenshots: this PR has no visible change.
