# Live › Buy ideas said "there isn't enough money in your Kalshi account" with $69.49 in it (2026-11-20). Kalshi's
# real answer was 400 insufficient_balance, which (docs.kalshi.com, Order Errors and Exchange Sharding) means the cash
# in the market's exchange shard ("pot") doesn't cover the order: Kalshi keeps combos, crypto and some sports in
# separate pots, and GET /portfolio/balance's `balance` is the total of all of them. This replays that order (Baylor
# Bears win by 7.5+, 55 contracts at 17c, IOC, the Live idea's own sizing) on the fake Kalshi in V2 mode, through the
# webapp's copy of the engine relaying to the Mac's copy (the real path), and checks: the body's units, the true
# reason in plain words, "not enough money" only when the numbers prove it, a clean refusal (nothing placed, no
# "check", no block), and the words for every order error code in Kalshi's docs. Throwaway key; fake network only.
import os, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")


def engine(name):
    spec = importlib.util.spec_from_file_location(name, "wahome/engine.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


E = engine("E")
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
E.CFG["kalshi_key_id"] = "fake-key-id"
E.hub_conf = lambda: None
import fakenet
fakenet.install(port=1)
D = fakenet.ORDERS
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
BAY = "KXNCAAFSPREAD-26NOV21TTUBAY-BAY8"
LOGS = []
E.print = lambda *a, **k: LOGS.append(" ".join(str(x) for x in a))


def reset(**k):
    D.update(mode="v2", sent=[], next=None, fill=None, headers={}, balance=None, shards={BAY: 0})
    D.update(k)
    E._ORDER_SHARED.recent.clear()
    E.save_json(E.ORDER_LEDGER, {})


def pots(total, *by):
    return {"balance": int(round(total * 100)), "balance_dollars": f"{total:.4f}", "portfolio_value": 0, "updated_ts": 1,
            "balance_breakdown": [{"exchange_index": i, "balance": f"{v:.4f}"} for i, v in by]}


# The idea as stored on Pete's Mac: 55 contracts at the 17c ask (stake $9.89)
ask, n = 0.17, 55
ok(f"the idea's order needs about ${n * (ask + E.single_fee(ask)):.2f}, well under $69.49", n * ask < 10)

# ---- (1) the exact order: the units Kalshi gets are right (no 100x, YES side, IOC)
reset()
filled, err = E.buy_single(BAY, n, ask)
m, p, body, _ = D["sent"][-1]
ok("Live buy idea: V2 bid on the YES book, price '0.1700' dollars, count '55.00', IOC (no unit slip)",
   p.endswith("/portfolio/events/orders") and body["side"] == "bid" and body["price"] == "0.1700"
   and body["count"] == "55.00" and body["time_in_force"] == "immediate_or_cancel" and filled == 55 and err is None)
need = E.order_cost(E.order_intent(dict(body)))
ok(f"what the order needs in cash: 55 x (17c + fee) = ${need:.2f}", abs(need - 55 * (0.17 + E.single_fee(0.17))) < 1e-9)
ok("a NO buy costs its NO price: ask at YES 0.70 for 10 = 10 x (30c + fee)",
   abs(E.order_cost({"side": "ask", "yes": E._dec("0.70"), "count": E._dec("10")}) - 10 * (0.3 + E.single_fee(0.3))) < 1e-9)

# ---- (2) Pete's case: $69.49 in all, but the sports pot (shard 0) holds $4.10 and the combos pot the rest
reset(next=(400, "insufficient_balance"), balance=pots(69.49, (0, 4.10), (1, 65.39)))
filled, err = E.buy_single(BAY, n, ask)
ok(f"the true reason: this market's pot is short, the rest is in another pot, where to move it ({err})",
   filled == 0 and "this market's pot has only $4.10" in err and "$69.49" in err and "Exchange indexes" in err
   and "isn't enough money" not in err)
ok("a refusal: nothing placed, no 'check', no block on the market, one order sent",
   not E.order_unsure(BAY) and not E.order_blocks() and len([x for x in D["sent"] if x[0] == "POST"]) == 1)
ok("the cash in each pot is logged once for the diagnosis (no account ids)",
   any("Kalshi cash by pot: 0: $4.10, 1: $65.39" in x and "pot 0" in x for x in LOGS))
reset(balance=pots(69.49, (0, 69.49)))
filled, err = E.buy_single(BAY, n, ask)
ok("once Pete moves the cash, a fresh tap goes through (a refusal never blocks the next try)", filled == 55 and err is None)

# ---- (3) "not enough money" only when the numbers prove it
reset(next=(400, "insufficient_balance"), balance=pots(3.00, (0, 3.00)))
filled, err = E.buy_single(BAY, n, ask)
ok(f"really short ($3.00 for a ${need:.2f} order): says so, with both numbers ({err})",
   filled == 0 and "isn't enough money in your Kalshi account" in err and "$3.00" in err and f"${need:.2f}" in err)
reset(next=(400, "insufficient_balance"), balance=pots(69.49, (0, 50.00), (1, 19.49)))
filled, err = E.buy_single(BAY, n, ask)
ok(f"the pot shows enough: says open orders hold cash, never 'not enough money' ({err})",
   filled == 0 and "open orders" in err and "isn't enough money" not in err)
reset(next=(400, "insufficient_balance"), balance=fakenet.R({"error": "down"}, 503))
filled, err = E.buy_single(BAY, n, ask)
ok("balance can't be read: the general pot explanation, still a clean refusal",
   filled == 0 and "separate pots" in err and "isn't enough money" not in err and not E.order_unsure(BAY))
reset(next=(400, "insufficient_balance"), balance={"balance": 6949}, shards={})
filled, err = E.buy_single(BAY, n, ask)
ok("no breakdown and no pot for the market (an older answer): the general pot explanation",
   filled == 0 and "separate pots" in err and "isn't enough money" not in err)

# ---- (4) the real Live path: the webapp's engine copy relays to the Mac's copy, which signs and sends
A = engine("A")
A.hub_up = lambda: True


def hub_call(op, timeout=0, **req):         # the hub's "kalshi" op (start_hub's handle), on the Mac's engine
    try:
        return {"json": E.kalshi_send(req["method"], req["path"], req.get("body"), req.get("params") or None)}
    except PermissionError as e:
        return {"err": "perm", "msg": str(e)}
    except (RuntimeError, ValueError, OSError) as e:
        return {"err": "kalshi", "msg": str(e)}


A.hub_call = hub_call
reset(next=(400, "insufficient_balance"), balance=pots(69.49, (0, 4.10), (1, 65.39)))
filled, err = A.buy_single(BAY, n, ask)
ok(f"through the Mac (as on Pete's phone): the same true words, no status code, no raw JSON ({err})",
   filled == 0 and err.startswith("Kalshi didn't take the order: Kalshi keeps your cash in separate pots")
   and "(400)" not in err and "{" not in err and not E.order_unsure(BAY))
reset()
filled, err = A.buy_single(BAY, n, ask)
ok("through the Mac, a funded pot buys: 55 filled", filled == 55 and err is None)
src = open("wtest/combo_watcher.py").read()
i = src.index('if a == "singlebuy":')
seg = src[i:src.index('if a == "buy":', i)]
ok("api_act singlebuy shows buy_single's words as they are (no money words of its own)",
   'return {"ok": False, "msg": err}' in seg and "enough money" not in seg)

# ---- (5) every order error code in Kalshi's docs -> its own true words (never "not enough money")
WANT = {
    (400, "invalid_order"): "as sent", (400, "invalid_parameters"): "as sent", (400, "missing_parameters"): "as sent",
    (400, "bad_request"): "as sent", (400, "invalid_price"): "price", (400, "invalid_order_size"): "number of contracts",
    (400, "insufficient_balance"): "separate pots", (400, "too_many_open_orders"): "too many open orders",
    (400, "exceeded_order_group_contracts_limit"): "as sent", (400, "EXPIRED_TIMESTAMP"): "time limit",
    (400, "Cannot_specify_both_IoC_and_expiration_timestamp"): "time limit",
    (400, "Post_only_but_execution_type_can't_rest"): "as sent", (400, "ID_parse_error: bad"): "as sent",
    (404, "market_not_found"): "doesn't list that market",
    (404, "insufficient_shard_balance"): "no cash set aside for this kind of market",
    (409, "fill_or_kill_insufficient_resting_volume"): "enough contracts for sale",
    (409, "market_inactive"): "isn't open for trading", (409, "trading_is_paused"): "paused",
    (409, "exchange_is_paused"): "paused", (409, "TRADING_BLOCKED"): "isn't letting this account",
    (403, "Trading_is_not_available_in_your_location"): "from here",
    (410, "deprecated_v1_order_endpoint"): "changed how orders are placed", (429, "too_many_requests"): "busy",
    (429, ""): "busy",
}
bad = {k: E.kalshi_plain(*k) for k, w in WANT.items() if w not in E.kalshi_plain(*k)}
ok(f"the error-code table: all {len(WANT)} documented codes give their own words ({bad or 'all right'})", not bad)
ok("no code but insufficient_balance itself ever says 'not enough money'",
   not [k for k in WANT if "enough money" in E.kalshi_plain(*k)])
ok("a 404 not_found outside a cancel doesn't talk about an order; an unknown 403 isn't called a location block",
   "order" not in E.kalshi_plain(404, "not_found", "not found") and
   "from here" not in E.kalshi_plain(403, "account_suspended", "suspended"))
reset(next=(404, "not_found"))
try:
    E.kalshi_send("DELETE", "/portfolio/orders/ord-gone", params={"market_ticker": BAY})
    words = ""
except E.KalshiRefused as e:
    words = e.plain
ok(f"a cancel answered 404 not_found: 'couldn't find that order' ({words})", "couldn't find that order" in words)
reset(next=(403, "permission_denied"))
filled, err = E.buy_single(BAY, n, ask)
ok(f"403 permission_denied: the key needs trading access ({err})", filled == 0 and "write (trading) access" in err)
reset(next=(400, "insufficient_balance"), balance=pots(1.00, (0, 1.00)))
sold, err = E.sell_single_now(BAY, "yes", 100, 0.90)
ok(f"a sale refused for insufficient_balance never says 'not enough money' (no purchase sums) ({err})",
   sold == 0 and "isn't enough money" not in err and not E.order_unsure(BAY))
reset(next=(400, "insufficient_balance"), balance={"balance": 6949, "balance_breakdown": [
    {"exchange_index": 0, "balance": 410}, {"exchange_index": 1, "balance_dollars": "65.3900"}]})
filled, err = E.buy_single(BAY, n, ask)
ok(f"pot amounts read with the same unit rule as the total (410 cents = $4.10) ({err})", "pot has only $4.10" in err)
ok("the diagnostic reads are short (the phone's relay waits 40 s for the whole order)", E.POTS_WAIT <= 5)
ok("an unknown code reads Kalshi's message, without JSON", E.kalshi_plain(400, "new_code", '{"m": "odd thing"}')
   == "Kalshi said: m: odd thing")
for st, code, outcome in ((400, "insufficient_balance", "refused"), (404, "insufficient_shard_balance", "refused"),
                          (409, "market_inactive", "refused"), (403, "Trading_is_not_available_in_your_location", "refused"),
                          (409, "order_already_exists", "unknown"), (503, "service_unavailable", "unknown")):
    reset(next=(st, code), balance=pots(69.49, (0, 69.49)))
    try:
        filled, err = E.buy_single(BAY, n, ask)
        got = "refused" if filled == 0 and err and not E.order_unsure(BAY) else "?"
    except E.OrderUnknown:
        got = "unknown" if E.order_unsure(BAY) else "?"
    ok(f"{st} {code}: {outcome}" + (" (a clean refusal, can be tried again)" if outcome == "refused" else
                                     " (marked 'check', never resent)"), got == outcome)
