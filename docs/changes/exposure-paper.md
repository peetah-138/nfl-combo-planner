# No-both-sides and exposure caps, on paper (issue #335)

**Section:** Build page / Results (a paper test, like the cost-carry test); the log.

Pete's call (2026-11-22): no extra confirm tap, a warning at most, never block; and the big losers were the app's own
suggestions, not his picks. So this ships the measuring first and changes nothing about any buy. `nfl_combo_planner.py`
has one new block ("(#335) no-both-sides and exposure caps, on PAPER only", just above `SPORT_SCORE_WORD`) and one call
in `record_view` (the Live refresh's recorder): `exposure_paper_pass(view, now)`. It runs at most every 2 minutes
(`EXPO["every"]`), writes each pass in one transaction (stops at the first failed write), can be turned off with `CFG["expo_paper"] = False`, is wrapped so it never raises, and no buy, sell, size, panel, Smart Buy, Pause or cap path reads
it (`t_exposure.py` greps the engine to prove only `record_view` calls it, and that `get_offer`, `accept_offer`, `_size`,
`smart_buy_ok`, `exit_policy`, `single_sell_reason` and `build_panel` never mention it).

**What is recorded** (the history file, its own small tables):

- `expo_pass`: each pass, one row per game, league and day that has a held bet or one the panel would still buy. Per
  game: how many held bets and dollars, how many panel bets and dollars it would still add, whether both sides are
  held (`both_held`) or the panel would add the other side of a held or panel bet (`both_would`), how many bets are
  stacked on it, and the share of the bankroll (`CFG["bankroll"]`). Written only when something changed (or hourly);
  kept 14 days and at most 20000 rows. A combo's whole cost counts on each game it touches (as `game_exposure` does) and in
  the league and day totals (the league is `mix` for a cross-league combo, which skips the league cap).
- `expo_pos`: one row per held bet, the first time the Live view shows it: its games and what it backs in each,
  its cost, day (the first game's date), league, and the first paper rule that would have stopped it
  (`blocked`: `both_sides`, `game_cap`, `league_cap` or `day_cap`, else empty). A bet is judged against the bets
  already taken that are still held (a finished bet carries no risk); a blocked bet never uses up room for the next one (it would not have been bought). Once the bet is no longer held
  and the ledger closed it after we first saw it (with a cost within 10% of ours, else it is left unsettled: another bet
  shared the ticker), `net` = what it really made (`back - cost`, fees counted). `batch` = how many new bets showed up
  in the same pass; `own` = the app's own bet (1) or not (0). Kept 60 days (pruned hourly).
- "What it backs": kind, team (or against it) and strike. Two bets on one game are the two sides when they back
  different teams, a team and against the same team (same strike for spreads), or an over and an under whose
  strikes cross (over 50 with under 40; over 40 with under 50 is a middle and is not). A spread's NO beside the same
  team to win is not both sides. A draw is its own side. Known gap: a hedge bought on purpose looks like both sides
  (the view does not say why a bet was bought).
- The paper numbers, all in `EXPO` and to be tuned from this record: a game 10% of the bankroll, a league's day 30%,
  a whole day 40%. They are guesses, not rules.

**What is shown** (nowhere else, no screen, no push): one plain-English line in the log when it changes, at most every
10 minutes, e.g. "exposure (paper only, nothing is blocked): holding both sides of DALNYG; 2 games with 2+ bets stacked;
biggest game DALNYG $23 (18% of the bankroll); today $41 (33%). The rules would have stopped 7 of 52 bets, and those
made -$31 net after settling." `exposure_paper_summary()` gives the same as numbers: bets seen, blocked, and per rule,
with the net of the blocked bets once they have settled. A group of fewer than `EXPO["min_n"]` (5) bets shows no count
and no dollars; dollars wait for `EXPO["dollar_n"]` (20) settled bets. With dollars the line gives the settled
count, the money staked, the return on it and the same return for all bets as a baseline, and says "a small sample"
under 50 settled. The summary also splits by rule and by origin (app / not own).

**Limits, said plainly:** the first look (an empty table) records the bets already open as `seed` rows: they count
toward later bets' room but are never judged or counted, because their order is unknown. Bets first seen in the same
pass cannot be put in order (they are judged by id), so they are marked as one batch and reported by count only,
never in the dollars. The record sees only what the Live view shows (open combos and
open single bets, including ones Pete bought by hand): it cannot say which came from the panel, a standing order or
Build. The caps are guesses (`EXPO`). A game's cost is the whole combo cost on each of its games, a conservative read. It is a measurement to decide from, not a back-test of a rule.

**Design for a later opt-in (not built, out of scope):** if the numbers say the rules would have saved money, add a
setting (off by default, Pete's explicit opt-in, as for every new automatic money step) read by ONE function, e.g.
`expo_check(positions_after_this_buy)`, called from each buy path (panel buy, `get_offer`/`accept_offer`, standing
orders, killer deals, hedges) before the order and failing toward a plain warning first (Pete's rule: warn, never
block, no extra tap), then, only if he asks, a refusal with a logged reason. It would reuse `_expo_judge` on the live
account's open bets (not this table), respect Pause and rule 8, and log old versus new here so the effect is measured.
Both-sides on purpose (the covering idea in #74) would need its own exception and is a separate design.

**Tests:** `t_exposure.py` (stances and both-sides, each cap, a blocked bet not using up room, the first look not
judged, the panel's would-add, settlement from the ledger, small groups hidden, bounded tables, errors swallowed, no
decision path reads it).
