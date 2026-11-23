# The panel's pipeline: game-winner picks reach it again, its funnel, two paper tests, a core of 2-5 leg combos (issue #341, #336)

**Section:** The daily panel (Build page, top); Fair prices and data; Results page

**Root cause (A).** ESPN's scoreboard stopped answering a date range: `dates=YYYYMMDD-YYYYMMDD` now gets a 400
("Failed to get events endpoint"), while one day (`dates=YYYYMMDD`) works. `free_snapshot` asked for today..+7 days in
one range, got nothing, and quietly returned no teams. The Mac has no odds-service key and its shadow loop asks for free
lines only (`odds.get(code, "")`), so free lines were the only outside line: no game-winner side had a `src`, so
`record_closes` stored nothing (closes/close_mids empty, #336: no CLV, calibration or live-model prior),
`single_candidates`/`value_combos`/`slate_combos` returned nothing, the shadow quoted nothing (it also needs `src`) and
the panel's pool held only spreads/totals (priced from `_espn_board`, which already asks one day). `single_pass`'s ideas
were games under way (`screen_live`), not pre-game lines. Fix: `espn_scoreboard(path, q, days, code=)` reads one day
per request (4 at a time, de-duplicated by event id, never raises; each league's last read counted in `ESPN_FREE`):
`ESPN_DAYS` = 4 days for daily leagues (the panel's day and longer plays up to 3 days out), 8 for weekly ones.
`fetch_scores` still asks a range but already falls back to today's board (unchanged). Checked live on 2026-11-22: NBA
9/10, NHL 7/7, men's college basketball 25/31 games got a line again, and `closes` fills. With lines back, Kalshi's prices
mostly sit at the books' (that night no single cleared 2.5¢ and no combo the 95% cut-off), so the pool stays small for
an honest reason, which the funnel now says.

**Side effect to know before release:** killer deals (`single_pass`/`shadow_pass`, `killer_check` counts ESPN's line and
Polymarket as two sources) and standing orders (`maker_pass`) read sides with `src`; both are existing opt-ins and were
starved by the bug. Where they are "on", they can act again inside their own caps, Pause and rule 8.

**The funnel (A).** `panel_collect` keeps `PANEL_FUNNEL[code]`: games not started / under way, no outside line, stale
lines, priced sides, singles found, combos predicted and at the cut-off, spreads/totals priced and short of the bar,
ESPN days unread, candidates by kind. `choose_panel` adds the bar's rejections by kind (`_qualifies`), the pool, why each
qualifying bet wasn't picked (`left`: overlap, line share, budget, full, ranked out) and the floor trim; `build_panel` adds
started/too soon (`kick`), already bet (`held`), old prices, Smart Buy and odds-credit skips. All in `stats["funnel"]`,
with `funnel_words` (plain English, one line per league and step) in `stats["funnel"]["why"]`. The log gets
"panel funnel: ..." when it changes (at most every 10 min), and `combo_funnel.json` keeps the last one so an empty panel
can explain itself (`api_panel` → `funnel`, under an hour old). Build's pool line has "Why so few?" (with 4+ bets "How
these were picked") and the empty panel card "Why so few?" (`funnelOpen`, a sheet listing the lines; no link when an
older Mac sends no funnel). Display and log only.

**Core combos (D).** `value_combos(..., per_n=2)` returns the old search first, unchanged, then up to 6 more of each
length 2-5 (best-priced first, each pick in at most 2 of a length's extras, `extra: True`); `panel_collect` runs the old
search exactly as before and adds only the extras. `core_combos` keeps the old ones that clear their cut-off and adds,
for each length still short of `CORE["per_n"]` (2), the next ones that clear **the same** `combo_cutoff` (`core: True`).
`choose_panel` gives a combo of a length the panel has under 2 of a tie-break nudge (`CORE["nudge"]`, 0.1% of the budget
in expected dollars) only while it is over the day's floor and adds expected dollars. Budget, sizes (`_size`), every bar,
Smart Buy (still after the choice), caps, Pause, rule 8 untouched.

**Kalshi's price as fair, on paper (B).** `mkt_fair_shadow` (end of `panel_collect`) logs every priced side, every
spread/total candidate and every combo candidate into `mkt_fair` (before the game the latest row per market, rewritten at
most every 30 min; during it one row per half hour; phase `pre`/`live` kept apart, never pooled): Kalshi's mid, today's
fair, the market-anchored fair `mid + w·(fair − mid)`, the claimed edge on each, and `vanish` (a candidate whose edge is
gone, ≤ 0 after the fee, or a combo under 100% of the anchored fair). `w` (the books' weight) is 0 until earned:
`mkt_learn` (hourly) per league, bet type and phase picks the grid weight (0-1 in quarters) with the lowest log loss on
settled markets (one side per game: both sides' results are one result) and keeps it only with 200+ markets, ≥ 0.002
better than the mid and ≥ 2 SE (the line gate's thresholds, but in-sample: a held-out check must come before a weight is
ever used for picks). While the weight is 0 the anchored fair is the mid, which sits under the ask, so every claimed edge
vanishes by construction; the card says so, and the number that matters is what those claimed bets made at $5.
`mkt_resolve` (history loop, via `resolve_closes`; newest first, given up after 5 days) fills results; 60 days kept.
Results › What's working: "Kalshi's price as fair" (`mktCard`, `mkt_fair_summary`): per league/type/phase which price
predicted better (too few under 20), the weight, claimed edges and what $5 on each made held to the end ("estimated
price" on combos). Picks never change.

**Combos as the cheap way in, on paper (C).** `carry` table, separate from the panel, the $300 gate, the quotes table
and every learned number. `carry_pick` (shadow loop, under `odds.lock`, quick) picks 2-3 near-even picks (Kalshi mid
35-65%, gap ≤ 6¢) from separate games starting within 8 hours (`carry_candidates`, closest to even first, one set a day);
`carry_pass` then asks for the price OUTSIDE `odds.lock` (a quote waits up to 15 s; that lock is the one an approved panel
buy needs) through `carry_quote`, which clears a leftover request, never accepts and always withdraws. At most one attempt
a round and 24 a day (an unpriced attempt is an "asked" row: counted, never asked again); never while paused, on the Pi or
without trading access. `carry_note` (also after every other combo quote in `get_offer`) logs separate-game near-even 2-3
leg quotes and paper-buys $5 when the price is at or under the product of the legs' mids (once per set a day); same-game
quotes are only logged (correlation pricing); a quote with a game under way is never logged. `carry_resolve` settles
with Kalshi's results, profit after the taking fee. Results: "Combos as the cheap way in" (`carryCard`, `carry_summary`;
"too few to trust" under 20 settled).

Tests: `t_panelpipe.py` (the range refusal and per-day read, pool by kind with singles and 2-5 leg combos, closes
written, the funnel and its words and log, the old search unchanged and no combo under its cut-off, budget and stakes
unchanged, market-fair rows/vanish/weights earned only with enough data, carry paper rules, fees, asked rows, in-play
skipped, paused/Pi refusals, never accepting, never the quotes table) and `test_panelpipe_ui.py` (the sheet from the
panel and the empty card, both cards and their empty states, phone light and dark, desktop).

ROADMAP: adds "Market-anchored fair (#341 B): once a league/type has 200+ settled markets in mkt_fair, add a held-out
check, then decide with Pete whether the panel prices on it (the skip side first, stricter only)"
ROADMAP: adds "Cost-carry combos (#341 C): after a few weeks of paper results, decide whether near-even 2-3 leg combos
become a panel kind"
