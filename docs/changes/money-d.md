# Money batch D: Pause on the standing-sell pass, legacy reduce_only, must-be-fresh guard reads (issues #421, #452, #450)

**Section:** Selling (automatic sale paths, Pause), Kalshi orders, Hub (account read)

Three small guard changes. Each makes the app do less or read fresher; nothing new buys or sells, and Pause, caps,
rule 8 and "manual Sell always works" are untouched. No new switch: none of these is a behaviour Pete would turn off.

- **#421, `autosell_pass` checks Pause.** The standing take-profit pass (dormant while `RESTING_SELLS_OK` is False)
  checked `can_trade()` but not Pause. It now returns at once, before reading the account, when `trading_paused()` is
  true; an unreadable Pause counts as paused (that function's existing rule). Pete's own Cash out taps do not go through it.
- **#452, the legacy order fallback keeps `reduce_only`.** `order_legacy_body` returned the caller's legacy body as sent,
  without the forced `reduce_only` that `order_intent` sets for a sell (#443). It now adds `reduce_only` whenever the
  intent has it. The endpoint is retired (hygiene only); the fallback was kept rather than removed.
- **#450, a guard check reads Kalshi now.** `fetch_account(max_age=0)` (the two guard checks in the sell retry loop) now
  sends `fresh` to the hub (`ACCT_FRESH`); the hub's `account` op then skips its 3 second `HUB_FRESH_FLOOR` hold-back and
  reads Kalshi once. Ordinary reads (any other `max_age`) are unchanged, so a changing money stamp still cannot force a
  Kalshi read per request (#271). An older watcher ignores the unknown key and behaves as before.

Tests: `t_money_d.py` (Pause on, off and unreadable for #421; sell, flagged and plain-buy legacy bodies for #452; the
flag set only for `max_age=0`, cleared after a read or a failure, and the hub source for #450).

Not done from the triage list: #352 (already fixed on develop: in-play ideas are gated whatever the switch, #348),
#177 (needs a product call: a push is sent before the shadow has simulated the idea, so gating it would silence pushes
that were never judged), #475 (same lines as open PR #527), #329 (the issue itself says wait for scoreboard data), #309
(grab-bag of nits). Refs #421, Refs #452, Refs #450.
