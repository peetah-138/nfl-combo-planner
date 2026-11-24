# Money stamp: no stamp from incomplete reads, floor on forced fresh reads (issue #271)

**Section:** "Live page" / money-moved stamp (#242)

Display only; nothing that buys, sells or sizes reads the stamp, and no automatic path changes.

- `money_note(bets, positions, balance, incomplete=0)`: `_fetch_account` counts combos left out because their legs
  couldn't be read (`unread`). An incomplete read no longer compares or updates the combo fingerprint (a combo dropping
  out then coming back used to stamp twice). It still compares positions + balance (`MONEY_FP["pb"]`), so a real sale or
  balance change still stamps. The skip is logged once per change ("money stamp skipped: N combo(s) couldn't be read").
- `log_decision`: a plain `failed` / `hedge failed` cash-out on the same bet stamps at most once per
  `MONEY_FAIL_GAP` (60 s), so a loop logging a failure each pass stops forcing a fresh account read each pass. `sold`,
  `hedged`, `check` and `hedge check` (money may have moved) always stamp. Retry logic is untouched.
- Hub `account` op: the forced fresh read (`max_age=0`) now needs the cached copy to be older than `HUB_FRESH_FLOOR`
  (3 s). When held back, the reply carries `held_back: true` and the hub logs why; the web app uses that copy but does
  not keep it as fresh (`ACCT_CACHE["at"]=0`), so the very next call asks again and gets the fresh read. A displayed
  balance is therefore never cached stale because of the floor. The watcher's own `fetch_account(max_age=0)` calls
  (pre-trade checks) are unchanged.
- Tests: `t_moneyflag.py`.
