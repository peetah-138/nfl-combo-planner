# Change vs paid on Live rows, hero and combo detail (issue #100)

**Section:** Live page

Display only. Combo rows (next to the offer, `offNow`), single/spread/total rows (Worth now) and the combo detail's Offer carry the change against what was paid: "−7%" over "−$0.22" (`chgHtml` in `live.js`; formats `chg`/`chgd`/`absm` in `fmtNum`; dollars always with cents; rounding symmetric on magnitude, `rndm`; a zero prints no sign). Both parts are rolling `data-num` numbers, tabular, always two lines so a sign flip never moves the row. An estimate (no real Kalshi offer) is prefixed with "≈". The colour follows what is SHOWN in the chosen mode (`data-b` both / `data-p` % / `data-u` $: paid $10, offer $9.97 in % mode is a grey "0%"). The hero pill rolls its percent and signed dollar change the same way (`heroChg`). A "Change vs paid" switch (`% + $` / `%` / `$`, 44pt hit targets, `aria-pressed`, `:focus-visible`) shows above every table with a change line; it only sets `<html data-chg>` (`setChg`, remembered as `cw_chg`), so CSS shows the parts and nothing redraws. Same number the row already shows; no engine, sell or valuation change. CSS lives in `ideas.css`. Test: `test_pctchange.py`.

ROADMAP: none
