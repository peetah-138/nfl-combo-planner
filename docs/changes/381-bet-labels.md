# Every bet now says what it is on, which game, and which league (issue #381)

**Section:** Live tab / Game page / Games tab / Combo legs

Spreads and totals showed only Kalshi's bare label ("Over 144.5 points"), with no teams, league or matchup, so Pete could not tell
what a bet was on. A shared label helper (`bet_describe` / `label_bets` / `label_game_page` in the engine, `betlabel.js` in the app)
now gives every single bet and every combo leg a plain-English line: "Over 144.5 total points", "Duke -6.5 (wins by 7+)",
"UNC +6.5 (loses by 6 or fewer, or wins)", "Duke to win", plus "LEAGUE · Duke vs UNC". The game page header reads "Game: Duke vs UNC"
with "Your bet: ..." under it. A game whose teams cannot be found shows the ticker's best guess and "game not found". Display only:
no prices, sells, buttons or order logic changed. Tests: `t_betlabels.py` (helper) and `test_betlabels_ui.py` (390px, dark and light).
ROADMAP: none (display fix, no roadmap change)
