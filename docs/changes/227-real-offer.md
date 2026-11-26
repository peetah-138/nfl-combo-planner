# Ask Kalshi for a real offer when an estimate reaches the bar (issue #227)

**Section:** Selling: smart sell everywhere

When an estimate-driven plan SELL or smart-sell trigger fires in `auto_sell_now`, auto cash-out may ask Kalshi for a
REAL combo offer (`get_cash_offer`). It sells **only** if that real offer meets the same bar as any real offer: the
`exit_policy` bar, 97% of the line (`AUTO_CASH_SLIP`) on a fresh quote, and the below-cost skip (stricter than the
`FLEX_COST_SHARE` 95% floor) unless it is a real loss cut. **Never on the estimate alone.** The manual Sell tap is untouched.

- **Throttle** (`real_ask_gate(t, exempt=)`, state `MINE["real_asks"]`, noted by `real_ask_note(t)` and
  `real_ask_result(t, cleared)`): at most one request per combo per `REAL_ASK_GAP` (60 s), `REAL_ASK_HOUR_COMBO` (20) a
  combo and `REAL_ASK_HOUR_ALL` (60) in all per hour (all per process, in memory). **Back-off:** a combo whose last real
  offer came in under the bar (or none came) waits 60, 120, 240, 480 then `REAL_ASK_BACKOFF_MAX` (600) s between asks
  (about 9 asks an hour); an offer that clears the bar resets it. Three stuck combos therefore cannot use up the overall
  budget. **Exempt from the overall cap only:** lock-in and a guarded stop-loss (`sl_ready`); they still obey the combo's
  own gap, back-off and hourly cap. Unreadable state fails closed (no request). Learned loss cuts ("cut loss") bypass the
  gate on purpose, so the #396 clock-retry behaviour is unchanged.
- **Log:** every request and outcome is a `log_decision` line: "REAL OFFER asked (...): got $X, bar $Y, ..." and, when the
  gate refuses, "REAL OFFER not asked: ...; the estimate (...) never sells on its own" (one per combo per 300 s).
- **Card wording (#513):** `smart_trigger` keeps "will ask Kalshi for a real offer once the estimate reaches $X"; with the
  switch off it says "won't ask Kalshi (switched off)".
- **Untouched:** Pause (read first; unreadable = nothing), rule 8 (`rfq_unsure`), no live data = no sale, the daily cap,
  accept path, hedges.
- **Needs an independent Opus money review before merge.**
- Test: `t_realoffer_227.py` (includes the drain case: 3 stuck combos, a 4th still gets its ask).
