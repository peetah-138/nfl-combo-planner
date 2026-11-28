# Games and Build phone polish, round two (display only)

Before/after phone shots (390px, light and dark): `~/dev/wt/screens/polish-games-2/`.

Changed (markup, CSS and one client-side filter; no pricing, buying, selling, sizing, limits, gates or data code):

- **Bet-type chips on Games** (`All`, `Moneyline`, `Total`, `Spread`, each with a count). A sideways row that scrolls inside itself, the selected chip outlined, 44px tall.
  It only hides cards you already have, by the kind of bet on them. A chip shows only when a card of that kind exists, and the whole row only when there is a choice.
  The row is added to `HSWX` (sideways strips get no see-through haptic switches, scrolling first, as the game page's tabs do), so `test_hsw` and `test_gtabscroll` keep their meaning; the chips still press and tick through the normal tap feedback. No test needed changing.
- Games loading state: a heading placeholder and shimmering card placeholders. One 12px gap between cards (was 14px, the Build board used 12px).
- Build board: each game card's league and start time share one line (was two).

Not done, and what is missing:

- **Team Total chip, and Total/Spread chips on the Build board:** the Build board only carries moneyline sides (`board[].sides`); spread/total prices are not in that payload (`lines` is sent but unused by the page). A real chip row there needs the board to carry those markets: server work, a feature.
- **Team records (e.g. 3-8):** not in the Games or Build payloads. Records exist only in the game page's ESPN summary (`game_detail`, per game, fetched when a game is opened). Needs the scoreboard feed's `record` carried into `sc` / the board.
- **Game volume in the card footer:** Kalshi volume is stored per quote row in the engine's database, but not sent to Games or Build. Needs a field added to `api_games` / the board.
