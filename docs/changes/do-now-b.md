# Live hero estimate: a leg price with no timestamp is stale (issue #112)

**Section:** Live page

`live_offer_est` (display only, the Live hero's "worth now if sold") used to treat a leg price with no timestamp in
`MARKET_INFO` as fresh. It now counts as stale and returns None, so the frozen estimate stays. No buy, sell, size or
Pause path reads it. Test: `t_offer_live.py`.

Refs #112. Also filed as follow-ups: #517 (inline onclick + no CSP), #518 (#473 delight nits), #519 (#481 findings).
Verified already done on develop: #331, #298, #26 (closed with evidence), #247 (closed; #423 shipped the data-* move).
