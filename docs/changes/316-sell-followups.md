# #316 items 3-4 (sell follow-ups); #382 wording and #316 item 5 checked, already done

- **Item 3 (fixed):** `_cut_guard_ts` (the replay that learns the loss cut, used by `smart_tune` and `sim_exit`) now confirms with
  `sl_confirm_params(tickers)` (the league's live checks / span / gap) when no counts are passed, and its "too few ticks" test
  uses those checks. Before, it used the starting constants. Learned counts can only be as strict as or stricter than the start
  (their minimum is the start), so the replay now cuts the same or less often, never more. A caller that passes `cf`
  (the knob judge) is unchanged.
- **Item 4 (fixed):** `sl_sync(cfg, incoming, loosen=True)`. The watcher applying a phone's relayed settings
  (`fetch_settings`) passes `loosen=False`: a valid `allow` never replaces a stored `tune` (or a stored nothing / retired
  `never`); `tune` still tightens and a stored Allow stays. A phone relays its whole settings, so a stale device could re-send an
  old mode with a newer `at`. The web app's own save still uses the default and can turn Allow on. When the phone app gets
  the 3-way control, it needs an explicit "loosened now" signal to be allowed to turn Allow on.
- **Item 5 (skipped, already fixed):** an automatic sale that is not a loss cut passes `_CASH_CTX.cost_floor` to
  `_accept_with_retries` (profit-taking sales never retry below cost, net of fee); a loss cut keeps 97% of its first offer.
  Pete's own Cash out tap still retries to 97% of the price he confirmed (his decision, left alone).
- **#382 wording (skipped, moot):** the "Never sell at a loss" choice was removed (#479); no label or explainer still offers it,
  and the retry wording (`below_cost`, auto cash-out explainer) already describes the profit/loss-cut rules.
- Unchanged: $300 bankroll, $30 cap, $20 loss limit, Pause, Pi never trades. Nothing here adds spending or sells more.
- Tests: `t_sell_followups316.py` (exact guard times under live counts of 3, 4, 5, a 300 s span, 99; relay vs web-app sync).
