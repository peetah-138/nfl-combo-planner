# fullauto-harden-144: harden the full-auto switch (follow-ups to #583)

Full auto stays OFF by default. Nothing here adds automatic money movement; buying stays in `panel_exec`.

- Bankroll free and the losing streak now use all real-panel history (`_fa_rows` no longer cuts at 10 days), so old losses
  can't drop out and free up bankroll or reset the streak. "Spent today" and "bets open" stay a recent (10 day) view.
- Stale tab: "Save limits" / "Reset the pause" send `on=true` without the "Turn on?" confirm. The server now ignores `on=true`
  unless the request is the explicit turn-on (`turn_on` is exactly `true`, sent only by the Turn on button). While it is
  already on, limits and reset still work. Fails closed.
- A bet swapped in for one of ours is followed through the whole swap chain (was 3 deep), with no way to loop on a cycle.

Tests: `tests/suite/t_fullauto.py` (deep chain and cycle, 30-day-old loss, stale-tab limits/reset, explicit turn-on).
