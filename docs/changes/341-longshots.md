# Long shots on Build, and the in-play audit (issue #341)

**Section:** Build page (Long shots); Fair prices and data / Smart Buy (in-play bets)

**Long shots** replace "More combo ideas" at the top of Build's combo area (the random `build_combos` ideas stay, under a
"🎲 Surprise me" fold, retitled "Random combos built to your mix, for fun"). `longshot_build(games, ...)` (engine) runs
**off the app lock** in the web app (`longshots_kick`/`longshots_work`, a thread per sport, a copy of the board's games,
at most every 15 minutes, `LS_EVERY`; the page shows the last copy) and returns at most 3 (`LONGSHOT["per_day"]`)
recommendations, ranked by expected dollars:
- **Legs** (`longshot_pool`, `longshot_leg_fair`): one team per game (never both sides), **pregame only** (a game under
  way, a live-priced side, a live line or a start under 20 minutes = out), each 65-80% (`leg_lo`/`leg_hi`; no coin flips,
  nothing under 50%). The chance is **Kalshi's own mid** (`_mkt_side_mid`: no bid or a gap over 10¢ = out), moved toward
  the sportsbooks' calibrated chance (`calib_fair`) only by the weight the books have earned for that league and bet type
  (`mkt_weight`, #341 B; 0 until earned), and never by free lines alone when they disagree with the mid by more than
  3 points, or by a stale line.
- **Combos** (`longshot_combos`): 6-8 legs from the 12 best-priced picks, a joint chance of at least 7% (`min_hit`), any
  two sharing at most half their picks.
- **Checks, fail closed:** Pause (read fresh, `paused_now`), no trading access or the Pi, Kalshi refusing (`hold_refusal`
  strict), an unknown-outcome block on the picks (`rfq_unsure`), a combo with a live quote on Pete's screen (never
  re-quoted underneath him). Smart Buy's `smart_buy_ok` must pass at a generous 150% of fair before Kalshi is even asked
  (saves quotes), then Kalshi's combo makers quote it (`carry_quote`, request withdrawn at once, never accepted; no quote
  or an error = not shown); the quote **after the taking fee** must pay at least the fair value (`min_pct` 1.0), and
  `smart_buy_ok` must pass again on the real price. Stake: quarter Kelly on the bankroll (`_manual_base`), at most $5,
  under $1 = not shown. Each quoted candidate is logged in `longshot_log` (chance, price, share of fair, ev, route,
  shown/why) for later tuning.
- **Card** (`watcher/spa/longshots.js`): hit %, expected dollars, stake and payout, share of fair after the fee, the route
  ("Likely to cash out early for a profit: N%" / "Profit if it holds"), each pick. **Get price** sends act `longshot`
  (the server matches the id and the shown picks to its own list, refuses while paused or once a game started, puts the
  combo in the combo list as kind `longshot` and prices it through `combo_offer`/`get_offer` at its own stake); **Buy**
  is the usual act `buy` → `accept_offer` (caps, Pause, rule 8 unchanged). `get_offer`'s green Buy for a long shot needs
  the payout after the fee at least its fair value. Nothing buys by itself. With no recommendation the section sits with
  the board as an empty state saying why.
- **Note on the gate:** with today's `smart_buy_ok` (hold route needs a 40% win chance, `SB_WIN_MIN`; sell route needs a
  50% cash-out chance, `SB_ROUTE_EXIT`), simulations of 6-8 pick combos at 100-125% of fair never pass, so the section
  will usually show the empty state until the gate learns a long-shot route (a decision for Pete).

**In-play audit (Pete: in-play bets are judged on the chance the price rises because the team has a real comeback shot,
not on a pregame-style edge).** Stricter only:
- `live_exit_ok(ticker, event, fair, ask)`: Smart Buy's exit simulator from the live state must pass `smart_buy_ok`; it
  fails closed. Buy straight (`single_buy_quote`) and Live's single-idea quote no longer show a green Buy for a game under
  way without it (warning `exit`: "a profitable sale or win from here doesn't look likely").
- Panel: `smart_buy_gate` skips a live-priced bet without a likely profitable exit **whatever the Smart Buy switch or the
  league's dial** (an error = skip), and `_buy_panel_bet` re-runs the gate on the fresh live price after `live_recheck`
  (a skip, never "check").
- Live Buy ideas: an in-play idea (`_idea_in_play`) is shown only once the shadow found `smart_buy_ok` on its own quote
  (`IN_PLAY_WHY` otherwise).
- Build: spreads/totals whose game has started are never recommended (`_line_rec_one`, "started"); suggested combos
  (random and value) only use games before their start or ones that passed the live checks; `get_offer` never shows a green
  Buy for a non-panel combo with a pick under way (`idea_combo_live_gap`); Best bets drops combos with a pick under way.
- The Mac's buy-idea alerts: no combo idea with a pick under way (`shadow_pass`), and `single_pass` skips games under way
  (their chance there was screen_live's Kalshi mid, not a live-state chance).

Tests: `t_longshots.py` (leg range, one side per game, pregame only, mid/blend fair, 6-8 legs, 7% floor, overlap, no quote
and errors fail closed, after-fee price, smart_buy_ok before and after the quote, Pause/no trading/refusing/Pi, rule 8
block, no re-quote under Pete, logging, get_offer's green Buy), `t_inplay_exit.py` (live_exit_ok, panel gate whatever the
switch/dial, buy-time recheck, in-play ideas, started lines, Build combos, Best bets, alerts, get_offer), `test_longshots_ui.py`
(phone size: card, Get price with the shown picks, green Buy, Buy through the accept, bought state, empty state, Surprise
me). `t_live_panel.py` and `t_orderbook.py` stub the simulator (they test other guards).

ROADMAP: adds "Long shots: a learned route for long-shot combos in smart_buy_ok (today's hold route needs a 40% win chance, so 6-8 pick combos rarely pass); tune leg band/min hit from longshot_log"
