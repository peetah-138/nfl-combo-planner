# Order adapter hardening (issue #102)

**Section:** Selling / Mac hub

Three tightenings, no loosening of any automatic path.

- **A. Legacy sells can only close.** `order_intent` now forces `reduce_only` whenever a legacy body says `action: "sell"`,
  whatever the caller sent. Sell YES becomes an ask and sell NO a bid, and without the flag either could open a position.
  A legacy sell that is not immediate-or-cancel is refused (Kalshi takes reduce-only only with IOC), so a forgotten flag
  fails closed. The in-repo sellers already set the flag, so their behaviour is unchanged. Test: `t_orders_v2.py`.
- **B. Allow-list for phone writes.** The hub's `kalshi` op used to forward any POST/PUT/DELETE under the read prefixes
  (`HUB_PATHS`). `hub_refusal` in `combo_watcher.py` now lets a write through only when it matches `HUB_WRITES`: order
  create and single-order cancel (old and new paths), RFQ create and cancel, quote accept, and combo-market creation. Anything
  else (batch or amend orders, other `/portfolio` writes) is refused and logged as `phone request refused: <reason>`. The
  transfer/allocation/subaccount block stays. Reads are unchanged. Test: `t_hubwrites.py`.
- **C. Stricter event id.** `game_detail` checks the ESPN event id with `re.fullmatch(r"[0-9]+", ...)` (no trailing
  newline, no non-ASCII digits). Test: `t_gamedetail.py`.

ROADMAP: none
