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
import math
ok(f"what the order needs in cash: 55 x 17c + the fee rounded up to the cent = ${need:.2f}",
   abs(need - (55 * 0.17 + math.ceil(round(55 * E.single_fee(0.17) * 100, 6)) / 100)) < 1e-9
   and need >= 55 * (0.17 + E.single_fee(0.17)))
ok("a NO buy costs its NO price: ask at YES 0.70 for 10 = 10 x 30c + fee",
   abs(E.order_cost({"side": "ask", "yes": E._dec("0.70"), "count": E._dec("10")})
       - (3.0 + math.ceil(round(10 * E.single_fee(0.3) * 100, 6)) / 100)) < 1e-9)

# ---- (2) Pete's case: $69.49 in all, but the sports pot (shard 0) holds $4.10 and the combos pot the rest
reset(next=(400, "insufficient_balance"), balance=pots(69.49, (0, 4.10), (1, 65.39)))
filled, err = E.buy_single(BAY, n, ask)
ok(f"breakdown shows this market's pot short: says so with the total and the pot ({err})",
   filled == 0 and "money available for this market isn't enough" in err and "your total is $69.49" in err
   and "this market's pot has $4.10" in err and "isn't enough money in your" not in err)
ok("a refusal: nothing placed, no 'check', no block on the market, one order sent",
   not E.order_unsure(BAY) and not E.order_blocks() and len([x for x in D["sent"] if x[0] == "POST"]) == 1)
ok("the balance by pot is logged (no account ids), once while it doesn't change",
   sum("Kalshi balance by pot: index 0 $4.10, index 1 $65.39, total $69.49" == x for x in LOGS) == 1)
ok("Settings can read it: total and each pot", E.kalshi_pots() == {"total": 69.49, "by": [[0, 4.1], [1, 65.39]],
                                                                    "at": E.kalshi_pots()["at"]})
reset(next=(400, "insufficient_balance"), balance=pots(69.49, (0, 4.10), (1, 65.39)))
E.buy_single(BAY, n, ask)
ok("the same pots again: not logged twice", sum("Kalshi balance by pot:" in x for x in LOGS) == 1)
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
ok(f"the pot shows enough: no cause claimed, the code, the total, 'Check Kalshi' ({err})",
   filled == 0 and "code insufficient_balance" in err and "$69.49" in err and "Check Kalshi" in err
   and "pot" not in err and "isn't enough money in your" not in err)
reset(next=(400, "insufficient_balance"), balance=pots(69.49, (0, 69.49)))
filled, err = E.buy_single(BAY, n, ask)
ok(f"a single pot: no pot story, the code and the total ({err})",
   filled == 0 and "code insufficient_balance" in err and "Your total shows $69.49" in err and "pot" not in err)
reset(next=(400, "insufficient_balance"), balance=fakenet.R({"error": "down"}, 503))
filled, err = E.buy_single(BAY, n, ask)
ok(f"balance can't be read: the code and 'Check Kalshi', no cause claimed, still a clean refusal ({err})",
   filled == 0 and "code insufficient_balance" in err and "pot" not in err and "isn't enough money" not in err
   and not E.order_unsure(BAY))
reset(next=(400, "insufficient_balance"), balance={"balance": 6949}, shards={})
filled, err = E.buy_single(BAY, n, ask)
ok(f"no breakdown (an older answer): the code and the total, no pot story ({err})",
   filled == 0 and "code insufficient_balance" in err and "$69.49" in err and "pot" not in err)

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
   filled == 0 and err.startswith("Kalshi didn't take the order: Kalshi says the money available for this market")
   and "(400)" not in err and "{" not in err and not E.order_unsure(BAY))
reset()
filled, err = A.buy_single(BAY, n, ask)
ok("through the Mac, a funded pot buys: 55 filled", filled == 55 and err is None)
from wsrc import watcher_text   # the watcher file plus its web app files (watcher/spa/)
src = watcher_text()
i = src.index('if a == "singlebuy":')
seg = src[i:src.index('if a == "buy":', i)]
esrc = open("wahome/engine.py").read()
j = esrc.index("def idea_single_buy(")
eseg = esrc[j:esrc.index("\ndef ", j + 10)]
ok("api_act singlebuy (via idea_single_buy) shows buy_single's words as they are (no money words of its own)",
   "A.idea_single_buy(" in seg and '"msg": err or f"Nobody was selling' in eseg and "enough money" not in seg + eseg)

# ---- (5) every order error code in Kalshi's docs -> its own true words (never "not enough money")
WANT = {
    (400, "invalid_order"): "as sent", (400, "invalid_parameters"): "as sent", (400, "missing_parameters"): "as sent",
    (400, "bad_request"): "as sent", (400, "invalid_price"): "price", (400, "invalid_order_size"): "number of contracts",
    (400, "insufficient_balance"): "code insufficient_balance", (400, "too_many_open_orders"): "too many open orders",
    (400, "exceeded_order_group_contracts_limit"): "as sent", (400, "EXPIRED_TIMESTAMP"): "time limit",
    (400, "Cannot_specify_both_IoC_and_expiration_timestamp"): "time limit",
    (400, "Post_only_but_execution_type_can't_rest"): "as sent", (400, "ID_parse_error: bad"): "as sent",
    (404, "market_not_found"): "doesn't list that market",
    (404, "insufficient_shard_balance"): "no cash set up for this kind of market",
    (409, "fill_or_kill_insufficient_resting_volume"): "enough contracts for sale",
    (409, "market_inactive"): "isn't open for trading", (409, "trading_is_paused"): "paused",
    (409, "exchange_is_paused"): "paused", (409, "TRADING_BLOCKED"): "isn't letting this account",
    (403, "Trading_is_not_available_in_your_location"): "from here",
    (410, "deprecated_v1_order_endpoint"): "changed how orders are placed", (429, "too_many_requests"): "busy",
    (429, ""): "busy",
}
bad = {k: E.kalshi_plain(*k) for k, w in WANT.items() if w not in E.kalshi_plain(*k)}
ok(f"the error-code table: all {len(WANT)} documented codes give their own words ({bad or 'all right'})", not bad)
ok("no code but insufficient_balance itself talks about money, and none blames the whole account without numbers",
   not [k for k in WANT if "enough money" in E.kalshi_plain(*k) and k[1] != "insufficient_balance"] and
   not [k for k in WANT if "enough money in your" in E.kalshi_plain(*k)])
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
ok(f"pot amounts read with the same unit rule as the total (410 cents = $4.10) ({err})", "pot has $4.10" in err)
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

reset(next=(400, "insufficient_balance"), balance=pots(69.49, (1, 69.49)))
filled, err = E.buy_single(BAY, n, ask)
ok(f"all the cash in the combos pot and this market's pot not listed (= $0): named ({err})",
   "this market's pot has $0.00" in err and "your total is $69.49" in err)
reset(next=(400, "insufficient_balance"), balance={"balance": 6949, "balance_breakdown": [
    {"exchange_index": "0", "balance": "4.1000"}, {"exchange_index": True, "balance": "1.0000"},
    {"exchange_index": 1, "balance": "65.3900"}]})
filled, err = E.buy_single(BAY, n, ask)
ok(f"a digit-string index is read, a true/false one ignored ({err})", "pot has $4.10" in err and
   E.shard_balances({"balance_breakdown": [{"exchange_index": True, "balance": "1.0"}]}) == {})
before = dict(E.ACCT_POTS["by"])
E.note_pots({"balance": 5000})
ok("a balance answer without a breakdown keeps the last pots (total updated)", E.ACCT_POTS["by"] == before and
   E.ACCT_POTS["total"] == 50.0)


def refuse(*a, **k):
    raise RuntimeError(E.kalshi_plain(400, "insufficient_balance") + " (400)")


E.CTX.setdefault("offers", {})[7] = {"rfq": "r1", "quote": "q1", "stake": 5.0, "pays": 20.0, "market": "M", "price": 0.25}
real_send, E.kalshi_send = E.kalshi_send, refuse
r = E.accept_offer(7, skip_cap=True)
E.kalshi_send = real_send
ok(f"a combo accept refused for insufficient_balance isn't called 'probably expired' ({r.get('error')})",
   "probably expired" not in r.get("error", "") and "insufficient_balance" in r.get("error", ""))

# ---- (6) Settings › Money shows the pots, read-only, from the Mac when paired
ok("the webapp asks the Mac for the pots (hub op 'pots'), and an older Mac without it gives none",
   (setattr(A, "hub_call", lambda op, timeout=0, **k: {"pots": E.kalshi_pots()} if op == "pots" else None) or
    A.kalshi_pots() == E.kalshi_pots()) and
   (setattr(A, "hub_call", lambda op, timeout=0, **k: {"err": "kalshi", "msg": "unknown request"}) or A.kalshi_pots() is None))
ok("the hub answers 'pots' from the Mac's engine", 'if op == "pots":' in src and 'E.kalshi_pots()' in src)
ok("Settings › Money: 'Kalshi balance by pot', says Kalshi's own app shows one total, no button (read-only)",
   "potRow(d.pots)" in src and "Kalshi balance by pot" in src and "Kalshi's own app shows one total" in src and
   "onclick" not in src[src.index("function potRow"):src.index("function clearBlock")] and "As of " in src)
ok("Settings saves don't wait on the pots (read only on a plain read)", "pots = _pots() if vals is None else None" in src)
esrc = open("wahome/engine.py").read()
j = esrc.index("def single_buy(")
sb = esrc[j:j + 9000]
ok("Buy straight (single_buy) buys through buy_single and shows its words as they are (the same honest text)",
   "buy_single(t, n, ask, coid=coid, exact=True)" in sb and 'return {"ok": False, "msg": err}' in sb
   and "enough money" not in sb)
