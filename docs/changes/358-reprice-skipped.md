# Fresh price for Skipped / Didn't buy, live combos on the live chance, big-edge audit (issue #358)

**Section:** Build (today's panel, combo quotes, the amount control); Fair prices and data

- **Tap a Skipped or Didn't buy card** on the approved panel for a fresh price. The tap target is the whole card, at
  least 44px tall. It calls the new act `panel_reprice` (`A.panel_reprice`), which only reads:
  - It is refused while paused. It prices only that card's stored bet (rule 7). It never prices a market with an
    unknown order outcome (rule 8); the card then says "Check Kalshi".
  - A combo gets a fresh RFQ through `_with_ctx`/`_panel_combo`/`get_offer`. The RFQ is DELETEd at once and never
    accepted. A single reads Kalshi's book.
  - It uses the bar the panel buys by. A combo needs `combo_cutoff`, then the under-fair rule. A single needs
    ask + fee + 2% (or at fair or better for an early bet), then the news gap. A bet under way also needs the in-play
    exit test.
  - The panel is never changed. The act allows one price per card every 8 s.
  - The card shows the verdict ("Would buy at this price" / "Still wouldn't buy" / "No fair price right now"), the
    reason, and "a look only, nothing was bought".
- **Each card says why in plain words:** "Why not: Its price got worse before it could be bought…", "Kalshi didn't
  answer with a price…" and so on (`pNote` maps the Mac's notes, and unknown notes are shown as they are).
- **The quote names its real bar:** "104% of fair on the live chance · at or above your 100% bar". The bar is
  `green_bar`, sent as `cut`, not the old fixed accept_pct. When the bar isn't the reason, the quote says so: no fair
  price, too far over fair to trust, the in-play test, or the long shot hold test (`qWhy`).
- **Never "recommended" without an edge.** `combo_offer` sets `small` (the smallest usual bet, $2) whenever the quote
  isn't green or its expected profit isn't positive. The amount control then says "smallest bet" or "no edge", never
  "recommended", and drops the "× the recommended size" warning.
- **Live combos are priced on the live chance (the 131% screenshot).** Before, `get_offer` worked out %, expected
  profit and the recommended size from the board's pre-game fair while a pick's game was under way. The quote, the
  quote log (`store_quote`, which feeds the predictor) and the take-profit price (`offers["p"]`) all carried that
  number, and the card read "131% of fair". Now each started pick goes through `combo_live_fair`, which uses
  `live_side_fair` on a fresh score and the panel's live guards: a two-sided book within `LIVE_SPREAD`, not nearly
  decided, and Kalshi's mid within `LIVE_DISAGREE`.
  - If no live chance can be had, there is no fair price: no %, nothing stored, never green, $2 sizing.
  - **Loosening (Pete: "I'm okay with accepting recommendations on live games as long as they are good
    recommendations"):** a Build or idea combo under way may now be green when every live guard passes, it clears
    `green_bar` on the live chance, and it passes `inplay_exit_ok`. Before #358 it was never green (#255/#341).
    The panel's own combos are unchanged: they are re-priced by `live_recheck` before a buy, as before.

## Big-edge audit

1. **Pre-game fair against a live price.** This was the main source of 100%+ quotes on games under way, and it is
   fixed above. The inflated % also fed `stake_for` (bigger sizes), `store_quote` (a polluted predictor) and the
   take-profit price.
2. **No sanity cap.** A quote over `COMBO_SUSPECT` (130% of fair) is now held back everywhere `get_offer` prices
   (Build, ideas and the panel's buy). It is never green, never a panel buy, and logged. This is stricter only. 130%
   is a guess, because the dev Mac has no quote history; see the ROADMAP line.
3. **`ev` uses the uncalibrated fair, while `notify_bar` uses `calib_fair`.** In a league whose favourites under-win,
   the expected profit shown is optimistic. This is noted and not changed here: it is display only.
4. **The Kalshi-mid fallback fair is circular.** When a side has no sportsbook line, its "fair" is Kalshi's own mid,
   so an edge against Kalshi is mostly noise. It is already labelled "Kalshi's price" on ideas. The cap above catches
   the extreme cases.
5. **Stale pre-game lines** are already dropped by `drop_stale_lines`. No change.

Tests: `t_combo_live_fair.py` (the guards, live re-pricing, the 131% case, a good live price allowed, the in-play
test, the cap including the panel, nothing stored without a fair, combo_offer's no-edge sizing), `t_panel_reprice.py`
(read only: pause, rule 7, rule 8, the RFQ dropped and never accepted, the panel and CTX unchanged, live, singles, the
act), `test_reprice_ui.py` (390px: only skipped/failed cards are tappable at 44px+, the plain reasons, the tap asks
only `panel_reprice`, the inline verdict, `qWhy`, no "recommended" without an edge). `t_inplay_exit.py`'s offer case
now stubs the book and expects "no fair price".

ROADMAP: "Combo sanity cap (#358): after ~2 weeks of the quotes table, look at how often quotes land over 120-130% of
fair and how they settled, then tune `COMBO_SUSPECT` (data-gated); consider using the calibrated fair for the shown
expected profit."
