# Logging and display only: calibrated profit, exit-route log, sale estimate (issues #361 part 1, #397, #300, #316)

**Section:** Build page, Fair prices and data, Selling

No buy, sell or size decision changes in this PR.

- **#361 part 1 (display).** A combo quote now carries `ev_cal` (built in `combo_ev_cal` inside `combo_offer`, `watcher/combo_watcher.py`): the expected profit on the chance corrected by Pete's own record (`calib_fair` per leg, over the books' fair chance), `stake x (pct x calibrated / shown - 1)`. The Build card and the slip show it ("on your record, before fees") through `evShow` in `stakeCtl`; with no `ev_cal` (live quotes, longshots, a leg that cannot be corrected) they show the books' profit as before. The books' `ev` still decides `rec`, `small` and the "recommended" label, so a card can say "recommended" with a negative calibrated profit. The 130% tuning half of #361 is left to #397. Tests: `test_evcal_ui.py` (390x844, dark and light), `test_ownstake_ui.py`.
- **#397 (log only).** The live green-Buy exit-route check in `get_offer` now always writes its comeback_shadow line (`force_log=True`) and prints "combo quote exit-route check (live green Buy): passed|held back (why)". The verdict is unchanged. No tuning. Test: `t_combo_live_fair.py`.
- **#300 (log only).** A combo auto-sale's log line carries `disc` (today's `kalshi_discount`) and `est` (disc x chance x pays x share). `knob_sale_expect` and the brake still read what they did before; not done: feeding `est` or ledger proceeds on retries into the brake (that changes selling). Singles already log `ask` and `chance`. Test: `t_logdisplay.py`.
- **#316 items 1-2 (watch-only guards).** A single's break episode is filed under the held market, not the game-winner stand-in (`break_ok`/`stop_loss_leg` take `watch=`); a full `BRK_EP` drops its oldest episode instead of clearing every open one. Both are watch-only (`BRK_LIVE` is False). Test: `t_logdisplay.py`. Skipped: items 3 (smart_tune replay counts), 4 (stale-device `stop_loss_mode` in `sl_sync`) and 5 (97% retry floor on combo cash-outs), because each changes selling behaviour or settings semantics.

ROADMAP: none
