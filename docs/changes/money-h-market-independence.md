# Winner vs total independence, and never both sides of one market (money-h)

**Section:** Buying (panel, overlap rules, single buys)

Pete's rule: a bet on a game's WINNER must not hide or block a TOTAL-points buy on the same game, and a spread and a
total never block each other. A winner and a spread are nearly the same bet, so they keep hiding each other. The same
market is never bought twice by the panel, and the other side of the same market is never bought.

**Families** (`bet_family`): a winner and a spread are one family ("side"), a total is its own. A straight bet is held
by (game, family) (`_fams_of`, `_busy_of`, `_busy_hit`); a combo still holds its whole game (open question).

**What changed (each only ever frees a total/spread, never a same-market repeat):**
- `choose_panel`: "one straight bet per game" is now one per game and family (a winner and a total can both be picked).
  `per_game` (2 bets a game) and `line_share` are untouched.
- `_extras_filter`, `panel_add`, `panel_pass` (extras), `_replacement`, `build_panel`: a live panel straight bet hides
  only its own family on the game. A held combo, or a candidate combo, behaves as before.
- Pete's own account: `note_held` now also saves `fams` (his single bets by game and family) and `combo_events`;
  `account_held()` gives `build_panel` what to leave out. An older file without them, or a stale one, behaves as before.

**New guard (stricter only): `opposite_side_refusal`**, called first in `buy_single`, so every single buy goes through it
(panel auto-buy, Buy ideas, killer single, Pete's own Buy tap). It refuses when the account holds, has a waiting buy
order on, has an order with no clear answer on (`order_blocks`), or just bought (`RECENT_BUYS`) the opposite side of the
same market on the same game: the other team to win or cover, NO on the same ticker, under against over. It reads
positions and waiting orders fresh (`_positions_strict`, `GET /portfolio/orders`) and fails closed ("Couldn't check your
open bets on this game, so nothing was bought"). It reuses `overlap_key`, `_expo_stance` and `_expo_opposed`. A winner
never blocks a total. The same side again is not touched. Hedges and combos never come through it.

**Not changed (questions for Pete):** the overlap guard and its Add anyway, `killer_overlap`/`killer_exposure` and the
per-game exposure caps count every bet on a game together (a winner counts toward the 2-bet line); combos that contain
a winner leg; combos whose legs contradict a held single; buying the same side twice (nothing stops it but the 120 s
repeat on idea buys).

Tests: `t_money_h.py` (fails on the old code).

**Round 2 (Pete):**
- A combo with a leg that goes against a single he holds (holds Chicago to win, combo has Detroit to win) is hidden from
  idea lists, the panel pool/extras/replacements and Best bets (`hide_contradicting`, one read per list, fails closed,
  reused 10 s), and refused on every buy path (`accept_offer`, the panel's combo buy before any quote:
  `combo_contradiction`, fresh read, fails closed, names the teams). Same-side legs and totals beside a winner stay.
- Standing orders (`maker_mode` on): `_maker_post` now runs `opposite_side_refusal` (fails closed).
- A panel bet refused with "couldn't check your open bets" goes back to scheduled (hold `bets`), not failed.
- The waiting-orders read pages through (`ORDER_PAGES_MAX`) and fails closed if pages never end.
