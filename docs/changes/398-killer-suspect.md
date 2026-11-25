# Killer combos respect the quote check's verdict (issue #398)

**Section:** Fair prices and data (killer deals)

`shadow_pass` used to take a killer combo on `pct >= KILLER["combo_pct"]` alone, so a quote that `get_offer` held back
as `why="suspect"` (over `COMBO_SUSPECT` = 1.30 of fair, a wrong chance far more often than a gift) or under its bar
still reached `killer_check` and `killer_act`. Now `ok=False` from `get_offer` is final for the killer combo path, in
watch and on mode: the deal is skipped and logged ("near-killer combo held back: the quote check said suspect (140% of
fair)"). An ok quote behaves exactly as before. Killer mode off logs nothing new.

**Wider skip than "suspect" (Pete chose to KEEP this):** the skip is on ANY `ok=False` verdict from `get_offer`, not only
`suspect`. So it also covers the **inplay** and **longshot** verdicts, and combos that sit **under the green bar**, even
when the quote is above the 115% killer line (`KILLER["combo_pct"]`). Such a quote used to reach `killer_check` and
`killer_act`; now it is held back and logged with the verdict's own words.

Strictly a tightening: fewer killer buys, never more. No new switch (it only removes buys the normal path already
refuses); no valuation, early-exit, caps, Pause or rule 8 change. Test: `t_killer_suspect.py` (suspect and under-bar
quotes skipped with a logged reason in watch and on mode, an ok quote still reaches the killer check and act).
