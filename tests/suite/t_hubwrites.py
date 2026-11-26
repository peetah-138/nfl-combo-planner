# CHECK: group=engine
# GitHub #102 B: the Mac forwards a phone's Kalshi write only when it is one the app itself sends (order create/cancel,
# quote requests, accepting a quote, making a combo market). Everything else that HUB_PATHS lets through for reads
# (batch/amend orders, other /portfolio writes, transfers) is refused, fail closed, with a logged reason. Reads are
# unchanged. Nothing here sends anything: it only asks the allow-list.
import sys, importlib.util
sys.argv = ["combo_watcher.py", "--webapp"]
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
allowed = lambda m, p: W.hub_refusal(m, p) == ""

for m, p in (("POST", "/portfolio/orders"), ("POST", "/portfolio/events/orders"), ("DELETE", "/portfolio/orders/abc-123"),
             ("DELETE", "/portfolio/events/orders/abc-123"), ("POST", "/communications/rfqs"),
             ("DELETE", "/communications/rfqs/r1"), ("PUT", "/communications/rfqs/r1/quotes/q1/accept"),
             ("POST", "/multivariate_event_collections/KXMVE-COLL")):
    ok(f"the app's own {m} {p} is allowed", allowed(m, p))
for m, p in (("POST", "/portfolio/orders/batched"), ("POST", "/portfolio/events/orders/batched"),
             ("POST", "/portfolio/orders/abc/amend"), ("PUT", "/portfolio/orders/abc"), ("POST", "/portfolio/orders/abc"),
             ("DELETE", "/portfolio/orders"), ("DELETE", "/portfolio/orders/abc/extra"), ("DELETE", "/portfolio/orders/"),
             ("POST", "/portfolio/settlements"), ("PUT", "/portfolio/order_groups/g1"), ("POST", "/markets/KX"),
             ("POST", "/communications/rfqs/r1"), ("PUT", "/communications/rfqs/r1/quotes/q1/confirm"),
             ("POST", "/portfolio/intra_exchange_instance_transfer"), ("DELETE", "/portfolio/subaccounts/1"),
             ("POST", "/portfolio/orders/../../exchange"), ("POST", "/portfolio/orders?x=1"), ("PATCH", "/portfolio/orders"),
             ("POST", "/portfolio/orders\n"), ("POST", "/exchange/anything")):
    ok(f"a write outside the allow-list is refused: {m} {p!r}", not allowed(m, p) and W.hub_refusal(m, p) != "")
ok("reads are unchanged: portfolio, markets, events, series, rfqs",
   all(allowed("GET", p) for p in ("/portfolio/positions", "/portfolio/orders", "/markets/KX", "/events/E", "/series/S",
                                   "/communications/rfqs", "/portfolio/balance")))
ok("a read outside HUB_PATHS is still refused", not allowed("GET", "/exchange/status") and not allowed("GET", "/admin"))
ok("the hub logs why it refused a write (reason in the log, a plain line to the phone)",
   'log("phone request refused:", why' in open("wtest/combo_watcher.py").read())

# #458: a bare "." or ".." as an id is refused; real ids (with dots inside) still work
for m, p in (("DELETE", "/portfolio/orders/."), ("DELETE", "/portfolio/events/orders/.."), ("DELETE", "/communications/rfqs/..."),
             ("PUT", "/communications/rfqs/./quotes/q1/accept"), ("PUT", "/communications/rfqs/r1/quotes/./accept"),
             ("POST", "/multivariate_event_collections/.")):
    ok(f"a dots-only id is refused: {m} {p}", not allowed(m, p))
for m, p in (("DELETE", "/portfolio/orders/a.b"), ("DELETE", "/portfolio/orders/.a"), ("PUT", "/communications/rfqs/r.1/quotes/q.1/accept")):
    ok(f"an id with a dot inside still works: {m} {p}", allowed(m, p))
