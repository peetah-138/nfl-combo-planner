# Kalshi removed its legacy order writes (issue #81): POST/DELETE /portfolio/orders now answer 410
# deprecated_v1_order_endpoint. Every order write goes through one adapter in kalshi_send that sends Kalshi's V2
# request (POST /portfolio/events/orders: side bid/ask on the YES book, price a 4-decimal dollar string of the YES price,
# count a 2-decimal contract string) and reads the V2 answer back into the shape the callers use. This checks every
# price and count conversion (a 100x slip would be a money bug), the V2 / legacy / both / gone fake Kalshi, that a
# refusal is a clean skip, that an unknown outcome is "check" and never sent again, no double buy on repeated taps, and
# the once-a-day push when Kalshi retires something. Real signing code with a throwaway key; the network is fakenet's
# order desk, so nothing can reach Kalshi.
import os, sys, json, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.HEDGES = os.path.join(E.HERE, "hedges.json"); E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl")
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
E.CFG["kalshi_key_id"] = "fake-key-id"
E.hub_conf = lambda: None
E.haptic = lambda *a: None
import requests
import fakenet
fakenet.install(port=1)
D = fakenet.ORDERS
FX = json.load(open("fixtures/kalshi_orders_v2.json"))
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
T = "KXNBAGAME-26NOV19NYKMIN-NYK"


def wait(cond, secs=3.0):
    end = time.time() + secs
    while not cond() and time.time() < end:
        time.sleep(0.02)


def reset(mode="v2"):
    D.update(mode=mode, sent=[], next=None, fill=None, headers={}, balance=None, shards={})
    E._ORDER_SHARED.recent.clear()
    E.save_json(E.ORDER_LEDGER, {})


def v2(body):
    return E.order_v2_body(E.order_intent(body))


def refused(body):
    try:
        E.order_intent(body)
    except E.KalshiRefused as err:
        return err
    return None


ok("signing is local (no Mac hub), with the throwaway key", not E.hub_up() and os.path.exists(E.KEYFILE))

# ---- (1) conversions: legacy fields in, V2 out (Decimal, exact)
b = v2({"ticker": T, "action": "buy", "side": "yes", "type": "limit", "count": 10, "yes_price": 52,
        "time_in_force": "immediate_or_cancel", "client_order_id": "abc-1"})
ok("buy YES at 52 cents -> bid, price '0.5200' (dollars, not 52), count '10.00'",
   b["side"] == "bid" and b["price"] == "0.5200" and b["count"] == "10.00" and b["time_in_force"] == "immediate_or_cancel"
   and b["client_order_id"] == "abc-1" and b["self_trade_prevention_type"] == "taker_at_cross" and "reduce_only" not in b)
ok("boundary 1c -> '0.0100', 99c -> '0.9900'",
   v2({"ticker": T, "action": "buy", "side": "yes", "count": 1, "yes_price": 1})["price"] == "0.0100" and
   v2({"ticker": T, "action": "buy", "side": "yes", "count": 1, "yes_price": 99})["price"] == "0.9900")
s = v2({"ticker": T, "action": "sell", "side": "yes", "count": 7, "yes_price": 52, "time_in_force": "immediate_or_cancel",
        "reduce_only": True})
ok("sell YES at the 52c bid, reduce-only IOC -> ask '0.5200', reduce_only kept",
   s["side"] == "ask" and s["price"] == "0.5200" and s["reduce_only"] is True and s["count"] == "7.00")
s = v2({"ticker": T, "action": "sell", "side": "no", "count": 4, "no_price": 30, "time_in_force": "immediate_or_cancel",
        "reduce_only": True})
ok("sell NO at 30c -> bid on the YES book at 1 - 0.30 = '0.7000'", s["side"] == "bid" and s["price"] == "0.7000")
n1 = v2({"ticker": T, "action": "buy", "side": "no", "count": 1, "no_price": 1})
n99 = v2({"ticker": T, "action": "buy", "side": "no", "count": 1, "no_price": 99})
ok("buy NO at 1c -> ask '0.9900'; at 99c -> ask '0.0100'",
   n1["side"] == "ask" and n1["price"] == "0.9900" and n99["side"] == "ask" and n99["price"] == "0.0100")
ok("dollar strings: 4 decimals, rounded so a buy never pays more (down) and a sale never takes less (up)",
   v2({"ticker": T, "action": "buy", "side": "yes", "count": 1, "yes_price_dollars": "0.56129"})["price"] == "0.5612" and
   v2({"ticker": T, "action": "sell", "side": "yes", "count": 1, "yes_price_dollars": "0.56121", "reduce_only": True,
       "time_in_force": "immediate_or_cancel"})["price"] == "0.5613")
ok("fractional counts: count_fp '2.505' -> '2.50' (never rounded up)",
   v2({"ticker": T, "action": "buy", "side": "yes", "count_fp": "2.505", "yes_price": 40})["count"] == "2.50")
ok("a 0.004-contract or zero order is refused before sending",
   refused({"ticker": T, "action": "buy", "side": "yes", "count_fp": "0.004", "yes_price": 40}) is not None and
   refused({"ticker": T, "action": "buy", "side": "yes", "count": 0, "yes_price": 40}) is not None)
ok("prices of 0c, 100c, $1.00 or '52' dollars (a 100x slip) are refused before sending",
   all(refused(dict({"ticker": T, "action": "buy", "side": "yes", "count": 1}, **p)) is not None for p in
       ({"yes_price": 0}, {"yes_price": 100}, {"yes_price_dollars": "1.00"}, {"yes_price_dollars": "52"},
        {"no_price": 100}, {})))
e = refused({"ticker": T, "action": "sell", "side": "yes", "count": 5, "yes_price_dollars": "0.9000",
             "time_in_force": "good_till_canceled", "reduce_only": True})
ok("a standing (GTC) reduce-only sell is refused before sending (V2 takes reduce-only only with IOC)",
   e is not None and e.code == "app_reduce_only_resting" and "standing sell" in str(e))
ok("expiration: kept in seconds for GTC (ms converted), dropped for IOC",
   v2({"ticker": T, "action": "buy", "side": "yes", "count": 1, "yes_price": 40, "expiration_ts": 1800000000})[
       "expiration_time"] == 1800000000 and
   v2({"ticker": T, "action": "buy", "side": "yes", "count": 1, "yes_price": 40, "expiration_ts": 1800000000123})[
       "expiration_time"] == 1800000000 and
   "expiration_time" not in v2({"ticker": T, "action": "buy", "side": "yes", "count": 1, "yes_price": 40,
                                "time_in_force": "immediate_or_cancel", "expiration_ts": 1800000000}))
ex = FX["create_request"]
ok("the OpenAPI example request goes out unchanged in its fields",
   {k: v for k, v in v2(ex).items() if k in ex} == {k: ex[k] for k in v2(ex) if k in ex})
ok("a bad client order id is replaced with a fresh UUID; a good one is kept (idempotent)",
   len(v2({"ticker": T, "action": "buy", "side": "yes", "count": 1, "yes_price": 40, "client_order_id": "bad id!"})[
       "client_order_id"]) == 36 and v2(ex)["client_order_id"] == ex["client_order_id"])
lg = E.order_legacy_body(E.order_intent({"ticker": T, "side": "bid", "count": "3.00", "price": "0.3000",
                                         "time_in_force": "immediate_or_cancel"}))
la = E.order_legacy_body(E.order_intent({"ticker": T, "side": "ask", "count": "3", "price": "0.3000",
                                         "time_in_force": "immediate_or_cancel"}))
ok("legacy fallback body: bid 0.30 -> buy YES at 30 cents; a plain ask -> buy NO at 70 cents",
   lg["action"] == "buy" and lg["side"] == "yes" and lg["yes_price"] == 30 and lg["count"] == 3 and
   la["action"] == "buy" and la["side"] == "no" and la["no_price"] == 70)
a = E.order_answer_v2(FX["create_response"])
ok("the OpenAPI example answer reads as 0 filled, 10 resting",
   a["order"]["fill_count"] == 0 and a["order"]["remaining_count"] == 10 and a["order"]["status"] == "resting"
   and a["order_id"] == FX["create_response"]["order_id"])
ok("an answer without an order id or counts can't be read (unknown outcome)",
   E.order_answer_v2({"fill_count": "1.00"}) is None and E.order_answer_v2({"order_id": "x"}) is None)
ok("refusal words: 410 -> 'Kalshi changed how orders are placed', no JSON; bad_request at the top level is read",
   E.kalshi_plain(410, "deprecated_v1_order_endpoint") == "Kalshi changed how orders are placed; the app is updating"
   and "{" not in E.kalshi_plain(400, "", '{"x": 1}') and
   E._kalshi_error(fakenet.R(FX["error_400_top_level"], 400)) == ("bad_request", "bad request"))

# ---- (2) end to end on the fake Kalshi, V2 mode (Kalshi today)
reset("v2")
filled, err = E.buy_single(T, 5, 0.52)
m, p, body, _ = D["sent"][-1]
ok("panel/Live single buy: one V2 order, bid '0.5200' x '5.00' IOC, 5 filled",
   filled == 5 and err is None and len(D["sent"]) == 1 and p.endswith("/portfolio/events/orders") and
   body["side"] == "bid" and body["price"] == "0.5200" and body["count"] == "5.00"
   and body["time_in_force"] == "immediate_or_cancel")
reset("v2")
sold, err = E.sell_single_now(T, "no", 4, 0.30)
body = D["sent"][-1][2]
ok("smart sale of a NO single at its 30c bid: bid '0.7000' x '4.00', reduce-only IOC",
   sold == 4 and err is None and body["side"] == "bid" and body["price"] == "0.7000" and body["reduce_only"] is True
   and body["time_in_force"] == "immediate_or_cancel")
reset("v2")
D["fill"] = 2
filled, _ = E.buy_single(T, 5, 0.52)
ok("a part fill reads as 2 of 5", filled == 2)
reset("v2")
T2 = "KXNBAGAME-26NOV19NYKMIN-MIN"
E.MINE["hold"] = {"C1": {"label": "Combo 1"}}
msg = E.place_hedge("C1", hg={"ticker": T2, "name": "Wolves", "price": 0.3, "n": 20.0, "fee": 0.3, "done": 0,
                              "cost": 6.3, "locked": 13.7})
body = D["sent"][-1][2]
ok("hedge: V2 bid '0.3000' x '20.00', bought", msg.startswith("✅") and body["side"] == "bid" and body["price"] == "0.3000"
   and body["count"] == "20.00" and len(D["sent"]) == 1)
reset("v2")
r = E.kalshi_send("DELETE", "/portfolio/orders/ord-9", params={"market_ticker": T})
m, p, _, prm = D["sent"][-1]
ok("cancel: V2 DELETE /portfolio/events/orders/ord-9 routed by market_ticker",
   m == "DELETE" and p.endswith("/portfolio/events/orders/ord-9") and prm == {"market_ticker": T} and r["order_id"] == "ord-9")
E.resting_sells = lambda: {"KXMVECOMBO-1": [{"order_id": "o1", "ticker": "KXMVECOMBO-1"}]}
reset("v2")
ok("take-profit cancel goes through V2 with the combo's market", E.cancel_take_profit("KXMVECOMBO-1") == 1 and
   D["sent"][-1][3] == {"market_ticker": "KXMVECOMBO-1"})
reset("v2")
E.book_depth = lambda tk, max_age=60: {"bid": 0.50, "ask": 0.52, "spread": 0.02}
good, note, d = E._buy_panel_bet({"kind": "single", "code": "nba", "stake": 10.0, "legs": [{"ticker": T, "fair": 0.9}]})
ok(f"panel single bet bought end to end on V2 ({note})", good is True and d["filled"] >= 1 and len(D["sent"]) == 1)
reset("v2")
good, note, _ = E._buy_panel_bet({"kind": "early", "code": "nba", "stake": 10.0, "exit": 0.7,
                                  "legs": [{"ticker": T, "fair": 0.9}]})
ok("a sell-early bet is skipped (its standing exit can't be placed), nothing sent", good is False and not D["sent"])

# ---- (3) legacy only / both / gone
reset("legacy")
filled, err = E.buy_single(T, 5, 0.52)
ok("account without V2 yet: V2 404, then the legacy order in cents (52), filled",
   filled == 5 and [x[1].split("/trade-api/v2")[-1] for x in D["sent"]] == ["/portfolio/events/orders", "/portfolio/orders"]
   and D["sent"][1][2]["yes_price"] == 52 and D["sent"][1][2]["client_order_id"] == D["sent"][0][2]["client_order_id"])
reset("both")
filled, _ = E.buy_single(T, 5, 0.52)
ok("both answer: only V2 is used", filled == 5 and len(D["sent"]) == 1 and "/events/" in D["sent"][0][1])
reset("gone")
HOOK = []
E.DEPRECATION_HOOK = HOOK.append
filled, err = E.buy_single(T, 5, 0.52)
ok("V2 missing and legacy 410: a clean refusal in plain English, two tries, no loop",
   filled == 0 and err == "Kalshi didn't take the order: Kalshi changed how orders are placed; the app is updating"
   and len(D["sent"]) == 2 and not E.order_unsure(T))
wait(lambda: HOOK)
ok("the 410 told the watcher's retirement hook (on its own thread)", HOOK == ["deprecated_v1_order_endpoint"])
reset("v2")
D["next"] = (410, "deprecated_v1_order_endpoint")
good, note, _ = E._buy_panel_bet({"kind": "single", "code": "nba", "stake": 10.0, "legs": [{"ticker": T, "fair": 0.9}]})
ok(f"panel: a 410 is a clean skip (False, not 'check'), no JSON in the note ({note})",
   good is False and "{" not in note and "changed how orders are placed" in note)
reset("v2")
D["next"] = (400, "insufficient_balance")
filled, err = E.buy_single(T, 5, 0.52)
ok("400 insufficient_balance (account holds plenty, pots unknown): refused, the code, never 'not enough money in your account'",
   filled == 0 and "code insufficient_balance" in err and "enough money in your" not in err and not E.order_unsure(T))

# ---- (4) unknown outcomes: "check", never sent again; no double buy on repeated taps
for what, nxt in (("timeout", requests.Timeout("slow")), ("connection lost", requests.ConnectionError("gone")),
                  ("500", 500), ("503", (503, "service_unavailable")), ("408", 408),
                  ("409 order_already_exists", (409, "order_already_exists")),
                  ("unreadable 201", fakenet.R({"weird": True}, 201))):
    reset("v2")
    D["next"] = nxt
    try:
        E.buy_single(T, 5, 0.52)
        raised = False
    except E.OrderUnknown:
        raised = True
    n = len(D["sent"])
    filled, err = E.buy_single(T, 5, 0.52)
    ok(f"{what}: unknown outcome raised (the caller marks 'check'); a second try is not sent",
       raised and E.order_unsure(T) and n == 1 and len(D["sent"]) == 1 and filled == 0 and "no clear answer" in err)
reset("v2")
D["next"] = requests.Timeout("slow")
try:
    E._buy_panel_bet({"kind": "single", "code": "nba", "stake": 10.0, "legs": [{"ticker": T, "fair": 0.9}]})
    st = "no raise"
except Exception as err:
    st = "check" if E.order_outcome(err) == "unknown" else "refused"
ok("panel buy on a timeout raises an unknown outcome (panel_exec marks it 'check')", st == "check")
reset("v2")
D["next"] = requests.Timeout("slow")
sold, err = E.sell_single_now(T, "yes", 4, 0.5)
ok("smart sale on a timeout: 'check', and the market is left alone (no sale on top)",
   sold == 0 and err.startswith("check:") and E.order_unsure(T))
reset("v2")
D["next"] = requests.Timeout("slow")
msg = E.place_hedge("C1", hg={"ticker": T2, "name": "Wolves", "price": 0.3, "n": 20.0, "fee": 0.3, "done": 0,
                              "cost": 6.3, "locked": 13.7}, auto=True)
ok("hedge on a timeout: ⚠️ and 'check' in combo_hedges.json", msg.startswith("⚠️") and
   (E.load_json(E.HEDGES, {}).get("C1") or {}).get("check"))
reset("v2")
f1, _ = E.buy_single(T, 5, 0.52)
f2, err2 = E.buy_single(T, 5, 0.52)
ok("double tap: the second identical order isn't sent", f1 == 5 and f2 == 0 and "moment ago" in err2 and len(D["sent"]) == 1)
f4, _ = E.buy_single(T, 3, 0.52)
ok("a different order on the same market right after (the rest of a hedge) still goes", f4 == 3 and len(D["sent"]) == 2)
first = D["sent"][0][2]["client_order_id"]
E._ORDER_SHARED.recent.clear()
f3, _ = E.buy_single(T, 5, 0.52)
ok("after the double-tap window a new order goes out with a new client order id",
   f3 == 5 and len(D["sent"]) == 3 and D["sent"][-1][2]["client_order_id"] != first)

# ---- (4a) the unknown-outcome block: 2 hours by default; Pete can clear it (the unclear order is never resent)
reset("v2")
D["next"] = requests.Timeout("slow")
try:
    E.buy_single(T, 5, 0.52)
except E.OrderUnknown:
    pass
bl = E.order_blocks()
ok("an unknown outcome blocks that market and side for 2 hours, listed for Settings",
   E.ORDER_UNSURE_SECS == 2 * 3600 and len(bl) == 1 and bl[0]["ticker"] == T and bl[0]["side"] == "YES" and
   not bl[0]["sell"] and abs(bl[0]["until"] - (time.time() + 7200)) < 5)
sent_before = len(D["sent"])
ok("clearing it: logged, the block is gone, and nothing was resent by clearing",
   E.clear_order_block(bl[0]["key"]) and not E.order_blocks() and not E.order_unsure(T) and len(D["sent"]) == sent_before)
ok("clearing a block that isn't there says so", not E.clear_order_block(bl[0]["key"]))
E._ORDER_SHARED.recent.clear()
f, _ = E.buy_single(T, 5, 0.52)
ok("after clearing, a new order (Pete's own tap) can go again", f == 5 and len(D["sent"]) == sent_before + 1)
E.save_json(E.ORDER_LEDGER, {f"{T}|bid|o": {"ts": time.time() - 2 * 3600 - 5, "coid": "x"}})
ok("a block ends by itself after 2 hours", not E.order_blocks() and not E.order_unsure(T))

# ---- (4b) review fixes: words passed back from the Mac, 404s with a code, no key, standing sells, killer checks
ok("words from the Mac: a trailing 4xx is a refusal even if they say 'may or may not'; no code = unknown",
   E.order_outcome(RuntimeError("an earlier order may or may not have gone through (409)")) == "refused" and
   E.order_outcome(RuntimeError("Lost contact with your Mac during this trade, so it may or may not have gone")) == "unknown"
   and E.order_outcome(RuntimeError("Kalshi said: bad gateway (502)")) == "unknown")
reset("v2")
D["next"] = (404, "not_found")
try:
    E.kalshi_send("DELETE", "/portfolio/orders/ord-gone", params={"market_ticker": T})
    out = "ok"
except E.KalshiRefused:
    out = "refused"
ok("a cancel answered 404 not_found is a refusal, not a reason to try the legacy path", out == "refused" and len(D["sent"]) == 1)
reset("v2")
real_key = E.KEYFILE
E.KEYFILE = os.path.join(E.HERE, "missing.pem")
filled, err = E.buy_single(T, 1, 0.5)
E.KEYFILE = real_key
ok("no key file: a plain refusal before anything is sent (not 'check')", filled == 0 and not D["sent"] and "key" in err
   and not E.order_unsure(T))
reset("v2")
ok("standing auto-sell: refused in plain words, nothing sent", "standing auto-sell orders are off" in
   E.place_take_profit("KXMVECOMBO-1", 10, 4.0, steps=[(10, 9.0)]) and not D["sent"])
cancels = []
E.cancel_take_profit = lambda t: cancels.append(t) or 1
ok("a ladder that can't be put back is never cancelled to be moved",
   E.retarget_one("KXMVECOMBO-1", [{"order_id": "o1", "remaining_count_fp": "10.00", "yes_price_dollars": "0.9"}], 4.0, 10.0)
   is None and not cancels)
src = open("wahome/engine.py").read()
ok("the panel doesn't draft sell-early bets while standing sells are off",
   "sell_early_candidates(games) if RESTING_SELLS_OK else []" in src)
E.store_x("create table if not exists killer(ts, kind, legs, picks, mode, status, stake, pays, pct, why, outcome)")
ALERTS = []
E.CFG.update(killer_mode="on", budget=1000)
E.week_spend = lambda: 0
st = E.killer_act("single", [{"ticker": T, "pick": "Knicks"}], 5.0, 10.0, 1.2, lambda: (None, "check Kalshi: slow"),
                  alert=lambda m, k, u=None: ALERTS.append(m), log=lambda *a: None)
ok("killer deal with an unknown outcome: 'check', Pete is told, and it counts toward the day's caps",
   st == "check" and ALERTS and "may or may not" in ALERTS[0] and E.killer_today()[0] >= 1)

# ---- (5) the 6-cent gap rule for single sales (exactly 6c sells, 7c is too thin), resting sells read both ways
E.hands_off = lambda t: False
E.single_sell_reason = lambda x, bid, ask, cut_ok=False: ("smart", 1.0)
E.smart_params = lambda ts: {"loss": None}
E.resting_single_sells = lambda: set()
E.sold_today = lambda: 0
E.log_decision = lambda rec: None
E.CFG["auto_cap"] = 5
for bid, ask, want in (("0.5000", "0.5600", 1), ("0.5000", "0.5700", 0), ("0.4700", "0.5300", 1)):
    reset("v2")
    E.SINGLES.update(at=time.time(), mk={T: {"ticker": T, "yes_bid_dollars": bid, "yes_ask_dollars": ask}},
                     items=[{"t": T, "side": "yes", "state": "live", "label": "Knicks", "n": 10, "cost": 4.0,
                             "chance": 0.5, "kind": "win"}])
    E.smart_sell_singles()
    ok(f"gap {bid}/{ask}: {'sold' if want else 'too thin, not sold'}", len(D["sent"]) == want and
       (not want or D["sent"][0][2]["price"] == f"{float(bid):.4f}"))
ok("resting orders: legacy action read; without it, outcome/book side (sell YES = ask)",
   E.order_may_sell({"action": "sell"}) and not E.order_may_sell({"action": "buy"}) and
   E.order_may_sell({"book_side": "ask"}, "yes") and not E.order_may_sell({"outcome_side": "yes"}, "yes") and
   E.order_may_sell({"book_side": "bid"}, None))

# ---- (6) Kalshi retiring something: one push a day per code (watcher), raw code in the log only
TMP = tempfile.mkdtemp()
os.environ["COMBOWATCH_HOME"] = TMP
sys.argv = ["combo_watcher.py"]
wspec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(wspec); wspec.loader.exec_module(W)
PUSHED, LOGS = [], []
W.push = lambda conf, msg, **k: PUSHED.append(msg)
W.log = lambda *a: LOGS.append(" ".join(str(x) for x in a))
conf = {"topic": "t", "secret": "s"}
E.DEPRECATION_HOOK = lambda code: W.deprecation_alert(code, conf)
for k in range(2):
    reset("gone")
    E.buy_single(f"KXNBAGAME-26NOV19NYKMIN-X{k}", 1, 0.5)
    wait(lambda: PUSHED)
time.sleep(0.3)
ok("410 twice in a day -> one push, plain words", len(PUSHED) == 1 and PUSHED[0] ==
   "Kalshi is retiring something the app uses (deprecated_v1_order_endpoint). Claude is looking at it.")
ok("the raw code is in the log", any("deprecated_v1_order_endpoint" in x for x in LOGS))
reset("v2")
D["headers"] = {"Deprecation": "true"}
E.buy_single("KXNBAGAME-26NOV19NYKMIN-Y", 1, 0.5)
wait(lambda: len(PUSHED) >= 2)
ok("a Deprecation header is a notice too (its own push)", len(PUSHED) == 2 and "deprecation_header" in PUSHED[1])
seen = json.load(open(W.DEP_FILE))
seen = {k: "2000-01-01" for k in seen}
json.dump(seen, open(W.DEP_FILE, "w"))
ok("a new day pushes again", W.deprecation_alert("deprecated_v1_order_endpoint", conf) and len(PUSHED) == 3)
ok("no topic (the web app's copy): logged only, nothing pushed", not W.deprecation_alert("x_deprecated", None))
ok("the watcher wires every engine copy to the hook", "E.DEPRECATION_HOOK = deprecation_alert" in open("wtest/combo_watcher.py").read())
ok("every order write went to the fake desk's order paths",
   all(x[1].startswith(("/portfolio/orders", "/portfolio/events/orders")) for x in D["sent"]))
