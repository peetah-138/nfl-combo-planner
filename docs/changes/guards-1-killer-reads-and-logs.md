# Killer read guards, retry-below-offer log, ESPN deadline (issues #401, #399, #374, #395, #351)

**Section:** Killer deals (overlap guard), Selling (auto cash-out retries), Fair prices and data

Guards and logging only; nothing is bought or sold that was not before, and no sizing or price changes.

- **#401** `killer_act`'s retry exemption now matches the reason by prefix (`substr(why, 1, len) = KILLER_OVERLAP_UNREAD`), so
  the "(the setting couldn't be read)" variant is looked at again after `KILLER_UNREAD_RETRY` (2 min) like the other
  unreadable skip, not held 6 hours. The retry re-runs the full overlap check, which still fails closed.
- **#399** `_positions_strict` keeps one shared cooldown (`POS_COOL`, `POS_COOL_SECS` = 60) after a 429 (also recognised through
  the Mac hub's words). While it runs the read raises, so every killer candidate skips as unreadable (no buy) instead of
  hitting Kalshi again. The read itself moved to `_positions_read`. Closes the "shared cooldown" ask of #399 and the read-load
  point (3) of #374.
- **#374 (part)** `killer_unread_watch`: three different killer deals in a row skipped as unreadable send one alert a
  day (`KILLER_UNREAD_RUN`, `KILLER_UNREAD_TOLD`). Alert only. Left for #374: scoring the skipped deals in dollars (2), the combo
  dedupe check (4), the stake-in-risk note (5).
- **#395** An automatic combo sale that goes through on a retry under the first agreed offer logs `below_agreed` (dollars
  under, in the decision log and the console) and `retry_below_agreed()` counts them (`sell_scorecard()["retry_below"]`). The retry
  bar (the smart-sell line, cost floor, 97% for loss cuts) is unchanged.
- **#351** `espn_scoreboard` has one total deadline, `ESPN_DEADLINE` = 15 s for all days of a path (was up to ~24 s). A day not
  back by then counts as unread (`ESPN_FREE` bad), the answered days are kept, nothing raises. Fewer lines, never invented ones.
- **#396** Not changed: a clock retry of a stuck loss-cut sale would be a new automatic sale path, against Pete's
  "retry on changes in the game, not minutes" call. A restart already clears the park, so the combo is tried again then.

Tests: `t_killer_overlap.py` (setting retry, cooldown, alert), `t_cashretry.py` (below_agreed, counter), `t_espn_deadline.py`.

ROADMAP: none
