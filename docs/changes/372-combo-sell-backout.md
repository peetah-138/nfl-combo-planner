# Auto cash-out when buyers back out: honest alerts, back-off, 10 tries on the smart-sell line (issue #372)

**Section:** Selling (auto cash-out, `auto_sell_now` / `_accept_with_retries`)

What changed for an **automatic** combo cash-out (your own Cash out tap is unchanged: `CASH_RETRIES` 3, each fresh
offer at least `CASH_SLIP` 97% of the price you confirmed, no pauses):

- **The success lead only on a sale.** "🤖 Took the profit…", the stop-loss and cut-loss leads go out only when the
  sale really went through (✅). A round where buyers backed out sends one plain note instead (`combo_fail_note`):
  "🤖 Auto cash-out tried to sell <combo>: the buyer backed out N times [and no fresh offer came in | and the next
  offer ($X) was below the line], so nothing was sold." plus "Waiting N min before trying again." or "It will try
  again on the next check." Rate-limited per combo and share: at most one an hour (`COMBO_FAIL_TELL` 3600 s,
  `MINE["combo_fail_told"]`) unless a wait just began.
- **Back-off like singles (#334).** The same `SELL_FAILS` machinery (`sell_backoff_left` / `sell_backoff_note`, key
  `(ticker, "combo", share)`): after `SELL_FAIL_MAX` 3 failed rounds it waits 10 min, then 60 min
  (`SELL_FAIL_WAITS`); a sale resets it. Only clear failures count (`COMBO_BACKOFF_STOPS`: cancelled, failed, no
  fresh offer, offer too low, out of time). An unknown outcome is never retried and never backed off: it stays
  blocked in the order ledger until checked (rule 8).
- **Up to 10 tries a round** (Pete, 2026-11-23: "I don't think it's a bad idea to let it retry 7, 8, 9 or even 10
  times"): `AUTO_CASH_RETRIES` 9 fresh offers after the first accept (registry invariant `auto_cash_retries`), a
  random 0.3–1.0 s pause before each (`AUTO_CASH_GAP`, `cash_gap`), one extra ask when no fresh offer came in, and no
  new try starts after `AUTO_CASH_BUDGET` 120 s. Worst case for one round: about 177 s plus network time (a try
  starting at 120 s: 1 s pause + 20 s offer + 1 s + 20 s extra ask + 15 s `ACCEPT_WAIT`). No price laddering.
- **The bar for a fresh offer** (Pete, 2026-11-23: "I don't think it needs to be within 97% of the first price, but
  it should definitely stay above the smart sell line"): the smart-sell line the sale was made on, the same bar
  `auto_sell_now` used (plan: `thr x share`; other paths: `thr x knob_auto_slip x share`), passed as `_CASH_CTX.line`.
  No 97%-of-first-price gate for auto. If no line is given, the old `CASH_SLIP` rule holds (never looser).
- **The sale's purpose** (Pete, 2026-11-23: "It should only sell at a loss if that's a way to try to minimize
  losses. Not when there's still an opportunity for it to get profit."): a sale taking a profit (plan, smart, take
  profit, lock in, cut loss, with the first offer at or above cost) never takes a fresh offer below cost
  (`_CASH_CTX.cost_floor`); a loss-cutting one (the learned "cut loss" or a guarded stop-loss sale, `rec["stop_loss"]`,
  with the first offer already below cost) may take one below cost as long as it clears the line, and (because a loss
  cut's line, `CUT_ACCEPT` 2% of cost, is close to nothing) never under 97% of its first offer (`_CASH_CTX.cutting`). Under Never sell at a loss the cost floor always applies
  (unchanged, `t_neverloss.py`). Logged as `purpose`.
- **Pause mid-round:** before every retry an auto round checks Pause, Auto cash-out still on and `can_trade()`; if
  not, it stops ("paused", never a back-off failure). One `auto_sell_now` pass starts no new combo sale after
  `AUTO_CASH_BUDGET` (the rest wait for the next check), so `MINE["busy"]` is not held for long. No haptic and no
  loading screen on an auto round (no tap behind them). A sale after retries logs the price it really sold at.
- **Rich log** (`combo_autosell_log.jsonl`, `log_decision`): result (sold / check / failed), `round` (failed rounds in
  a row for this combo), `rounds`, `tries` (each try's quote status, offer and Kalshi's words for a refusal,
  `ACCEPT_ERR`), `agreed`, `line`, `floor`, `purpose`, `stop`, `asked_again`, `ask_error`, `low_offer`, the
  threshold and why. No secrets. One summary alert per round.

Never touched: Pause, the daily cap (a round is one sale), rule 7, rule 8, the Pi (alerts only), manual taps.

Tests: `t_cashretry.py` (constants and registry, pause bounds, success on try 7, gives up after 10, Kalshi's words,
unknown stops at once, below first price but above the line taken, under the line stops, profit-taking below cost
stops, under Never below cost stops, no line = 97%, manual tap unchanged, 120 s budget), `t_combobackout.py` (plain
note and log on a failed round, rate limit, 10 then 60 min waits, no asks while waiting, a sale resets and gets its
lead, unknown blocked with no back-off, the line, the purpose: profit-taking vs cut loss). `t_neverloss.py`,
`t_hedge.py`, `t_cutloss.py`, `t_stoploss.py` pass unchanged.

ROADMAP: none
