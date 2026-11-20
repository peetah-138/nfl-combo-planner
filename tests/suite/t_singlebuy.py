# Manual single-game buy (issue #113): Pete taps a team (or a spread/total) and buys it straight. The quote reads
# Kalshi's order book now and is good for 20 s; the buy re-reads the book, refuses a higher price, and sends one
# fill-now-or-cancel order at the quoted price (never more), once per quote. Pause, the weekly cap and the
# unknown-outcome block apply; an unclear answer is "check" and never resent (rule 8). A game under way never uses the
# pre-game fair price. Real signing code with a throwaway key; the network is fakenet (V2 order desk), so nothing can
# reach Kalshi.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
E.SIZING_FILE = os.path.join(E.HERE, "sizing.json")
E.CFG["kalshi_key_id"] = "fake-key-id"
E.CFG["budget"] = 100.0
E.CFG["bankroll"] = 400.0
E.hub_conf = lambda: None
E.haptic = lambda *a: None
import requests
import fakenet
fakenet.install(port=1)
D = fakenet.ORDERS
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
SPENT = {"v": 10.0}
E.week_spend = lambda: SPENT["v"]
E.can_trade = lambda: True
EV = fakenet.event_ticker("KXNBAGAME", "DEN", "LAL")          # not started (the fake's second game)
T = EV + "-DEN"
LIVE_EV = fakenet.event_ticker("KXNBAGAME", "BOS", "NYK")     # under way (the fake's first game)
LT = LIVE_EV + "-BOS"
mk = {m["ticker"]: m for m in fakenet.markets()}
X = {"ticker": T, "pick": "Denver Nuggets", "event": EV, "exp": mk[T]["expected_expiration_time"], "fair": 0.80,
     "src": "pinnacle", "opp": "Los Angeles Lakers"}
REAL_BOOK = E.book_depth
LOG = []


def reset(mode="v2"):
    D.update(mode=mode, sent=[], next=None, fill=None, headers={})
    E._ORDER_SHARED.recent.clear()
    E.save_json(E.ORDER_LEDGER, {})
    E.book_depth = REAL_BOOK
    SPENT["v"] = 10.0


def book(ask, bid, size=500):
    E.book_depth = lambda tk, max_age=60: {"ask": ask, "bid": bid, "spread": round(ask - bid, 4) if bid and ask else None,
                                           "ask_size": size, "thin": False}


def buy(q, t=T, **k):
    return E.single_buy(q["q"], t, log=LOG.append, **k)


ok("signing is local (no Mac hub), with the throwaway key", not E.hub_up() and os.path.exists(E.KEYFILE))

# ---- (1) the quote: fresh order book, fair, edge, sizing, contracts, cap
reset()
q = E.single_buy_quote(X, 10)
fee = 0.07 * 0.72 * 0.28
ok(f"quote reads the real book: ask 72c, bid 70c, gap 2c, 500 for sale ({q.get('ask')}, {q.get('bid')}, {q.get('gap')})",
   q["ok"] and abs(q["ask"] - 0.72) < 1e-9 and abs(q["bid"] - 0.70) < 1e-9 and abs(q["gap"] - 0.02) < 1e-9
   and q["depth"] == 500)
ok("fair 80% (sportsbooks, no record yet to adjust it), edge = fair - ask - fee, return = fair/(ask+fee) - 1",
   q["fair"] == 0.8 and abs(q["edge"] - round(0.8 - 0.72 - fee, 4)) < 1e-9 and abs(q["ret"] - round(0.8 / (0.72 + fee) - 1, 4)) < 1e-9)
ok(f"$10 stake -> {q['n']} contracts for ${q['cost']}, pays ${q['pays']:g}",
   q["n"] == int(10 / (0.72 + fee)) == 13 and q["cost"] == round(13 * (0.72 + fee), 2) and q["pays"] == 13.0
   and q["profit"] == round(13 - q["cost"], 2))
ok("clears (green Buy), not live, no warnings, cap room shown", q["clears"] and not q["live"] and not q["warn"]
   and q["room"] == 90.0 and q["budget"] == 100.0 and not q["blocked"])
ok("a 16-hex quote id, a 20 s life, presets $3/$5/$10, second tap above $25, at most $100",
   len(q["q"]) == 16 and q["secs"] == 20 and q["presets"] == [3, 5, 10] and q["arm"] == 25.0 and q["max"] == 100.0)
qs = E.single_buy_quote(X)
base = 400.0
b = (1 - 0.72 - fee) / (0.72 + fee)
edge = 0.8 * b - 0.2
want = round(min(max(2.0, 0.05 * base), max(2.0, 0.25 * 0.7 * edge / b * base)), 2)
ok(f"suggested stake = the panel's sizing (quarter Kelly on a 30%-shrunk edge, $2 minimum): {qs['sug']} == {want}",
   qs["sug"] == want and qs["stake"] == want)
q0 = E.single_buy_quote(dict(X, fair=0.70), 5)
ok("negative edge: allowed, but yellow (not clears) with a 'price above fair' warning, suggested $2",
   q0["ok"] and not q0["clears"] and q0["edge"] < 0 and any(w["k"] == "above" for w in q0["warn"]) and q0["sug"] == 2.0)
ok("a stake over $100 is held to $100; a silly one falls back to the suggestion",
   E.single_buy_quote(X, 500)["stake"] == 100.0 and E.single_buy_quote(X, "abc")["stake"] == qs["sug"])
qn = E.single_buy_quote(dict(X, src=None))
ok("no sportsbook line: no fair price, Kalshi's price only (yellow), says so", qn["ok"] and qn["fair"] is None
   and not qn["clears"] and any(w["k"] == "nofair" for w in qn["warn"]))
ok("nothing was sent by any quote", not D["sent"])

# ---- (2) buying: one order at the quoted price, IOC, recorded as the app's
reset()
q = E.single_buy_quote(X, 10)
r = buy(q)
m, p, body, _ = D["sent"][-1]
ok(f"buy: one V2 order, bid '0.7200' x '13.00' IOC with the quote's client id ({r.get('msg')})",
   r["ok"] and r["filled"] == 13 and len(D["sent"]) == 1 and p.endswith("/portfolio/events/orders")
   and body["side"] == "bid" and body["price"] == "0.7200" and body["count"] == "13.00"
   and body["time_in_force"] == "immediate_or_cancel" and body["client_order_id"] == "cw-sb-" + q["q"])
ok("recorded as the app's buy (smart sell's per-bet switch defaults to on, like other app buys)",
   T in (E.app_bets() or set()) and not E.is_own(T) and not E.hands_off(T))
r2 = buy(q)
ok("the same quote tapped again: refused, still one order", not r2["ok"] and "already used" in r2["msg"] and len(D["sent"]) == 1)
r3 = buy(E.single_buy_quote(X, 10), t=EV + "-LAL")
ok("a quote used for a different market than the one on screen: refused, nothing sent",
   not r3["ok"] and len(D["sent"]) == 1)
reset()
q = E.single_buy_quote(X, 10, now=time.time() - 25)
r = buy(q)
ok("a quote older than 20 s: refused as expired, nothing sent", not r["ok"] and r.get("expired") and not D["sent"])

# ---- (3) price moved, thin book, Buy anyway
reset()
q = E.single_buy_quote(X, 10)
book(0.75, 0.73)
r = buy(q)
ok(f"the ask went up between the quote and the tap: refused in plain English, nothing sent ({r['msg'][:40]}...)",
   not r["ok"] and r.get("moved") and "75" in r["msg"] and "72" in r["msg"] and not D["sent"])
reset()
q = E.single_buy_quote(X, 10)
book(0.70, 0.68)
r = buy(q)
ok("the ask went down: still bought, the limit stays at the quoted 72c (fills at the better price on Kalshi)",
   r["ok"] and D["sent"][-1][2]["price"] == "0.7200")
reset()
book(0.72, 0.60)
q = E.single_buy_quote(X, 10)
ok("thin book (12c gap): warned, yellow", q["ok"] and not q["clears"] and any(w["k"] == "thin" for w in q["warn"]))
r = buy(q)
ok("thin book without Buy anyway: refused, nothing sent", not r["ok"] and "Buy anyway" in r["msg"] and not D["sent"])
q = E.single_buy_quote(X, 10)
r = buy(q, anyway=True)
ok("thin book with Buy anyway: bought", r["ok"] and len(D["sent"]) == 1)
reset()
book(0.72, 0.70, size=4)
q = E.single_buy_quote(X, 10)
ok("only 4 for sale at the ask: the quote buys 4 and says so", q["n"] == 4 and any(w["k"] == "depth" for w in q["warn"]))
reset()
book(0.525, 0.51)
q = E.single_buy_quote(dict(X, fair=0.7), 5)
r = buy(q)
ok("a sub-cent ask (52.5c) goes as dollars, exactly, never rounded up", r["ok"] and D["sent"][-1][2]["price"] == "0.5250")
reset()
D["fill"] = 5
r = buy(E.single_buy_quote(X, 10))
ok("a part fill says 5 of 13", r["ok"] and r["filled"] == 5 and "5 of 13" in r["msg"])
reset()
book(None, 0.7)
ok("nobody selling: no quote", not E.single_buy_quote(X, 10)["ok"])
E.book_depth = lambda tk, max_age=60: None
ok("unreadable order book (429/5xx): no quote, plain words", "order book" in E.single_buy_quote(X, 10)["msg"])

# ---- (4) the cap, Pause, closed / unlisted markets
reset()
SPENT["v"] = 95.0
q = E.single_buy_quote(X, 10)
ok("over the weekly cap: blocked with the cap message (what it would reach, room left, which setting)",
   q["ok"] and q["blocked"] and "over your $100 cap" in q["blocked"] and "$5 left" in q["blocked"] and not q["clears"])
r = buy(q, anyway=True)
ok("over the cap even with Buy anyway: refused, nothing sent", not r["ok"] and "cap" in r["msg"] and not D["sent"])
SPENT["v"] = 10.0
q = E.single_buy_quote(X, 10)
SPENT["v"] = 95.0
r = buy(q)
ok("the cap is checked again at the tap (spending changed since the quote): refused", not r["ok"] and "cap" in r["msg"]
   and not D["sent"])
reset()
q = E.single_buy_quote(X, 10, paused=True)
ok("Pause: the quote is blocked and says how to resume", q["blocked"] and "Paused" in q["blocked"])
q = E.single_buy_quote(X, 10)
r = buy(q, paused=True)
ok("Pause at the tap: refused, nothing sent", not r["ok"] and "Paused" in r["msg"] and not D["sent"])
r = E.single_buy_quote({"ticker": "KXNBAGAME-26NOV19ZZZYYY-ZZZ"}, 10)
ok("a market Kalshi doesn't list (404): no quote, 'isn't listing'", not r["ok"] and r.get("gone") and "listing" in r["msg"])
real_markets = fakenet.markets
fakenet.markets = lambda hours=6: [dict(m, status="closed") if m["ticker"] == T else m for m in real_markets(hours)]
r = E.single_buy_quote(X, 10)
ok("a closed market: no quote, 'closed for trading'", not r["ok"] and "closed" in r["msg"])
fakenet.markets = real_markets
ok("a bad ticker is refused before anything is read", not E.single_buy_quote({"ticker": "x y"})["ok"])

# ---- (5) unknown outcomes: "check", never resent; 410 is a clean refusal
reset()
q = E.single_buy_quote(X, 10)
D["next"] = requests.Timeout("slow")
r = buy(q)
ok("timeout: 'check' (may or may not have gone through), one order sent", not r["ok"] and r.get("check")
   and "may or may not" in r["msg"] and len(D["sent"]) == 1)
ok("the market is blocked for 2 hours (listed in Settings)", E.order_unsure(T) and E.order_blocks()[0]["ticker"] == T)
q2 = E.single_buy_quote(X, 10)
ok("a new quote on that market is blocked", q2["blocked"] and "no clear answer" in q2["blocked"])
r = buy(q, anyway=True)
ok("the unclear quote tapped again: refused, never resent", not r["ok"] and len(D["sent"]) == 1)
E.save_json(E.ORDER_LEDGER, {})
E._ORDER_SHARED.recent.clear()
reset()
D["next"] = (503, "service_unavailable")
r = buy(E.single_buy_quote(X, 10))
ok("503: 'check' too", r.get("check") and E.order_unsure(T))
reset("gone")
r = buy(E.single_buy_quote(X, 10))
ok(f"V2 missing and legacy 410: a clean refusal in plain English, not 'check' ({r['msg']})",
   not r["ok"] and not r.get("check") and "changed how orders are placed" in r["msg"] and "{" not in r["msg"]
   and not E.order_unsure(T))
reset()
D["next"] = (400, "insufficient_balance")
r = buy(E.single_buy_quote(X, 10))
ok("400 insufficient balance: refused, plain words, can be tried again with a fresh price",
   not r["ok"] and "enough money" in r["msg"] and not E.order_unsure(T))
reset()
D["fill"] = 0
r = buy(E.single_buy_quote(X, 10))
ok("nothing filled (IOC cancelled): 'nobody was selling', nothing bought", not r["ok"] and "Nobody was selling" in r["msg"])

# ---- (6) a game under way: never the pre-game fair price
reset()
lx = {"ticker": LT, "pick": "Boston Celtics", "event": LIVE_EV, "exp": mk[LT]["expected_expiration_time"], "fair": 0.80,
      "src": "pinnacle"}
ok("the fake's first game is under way", E.started(lx))
lq = E.single_buy_quote(lx, 5)
ok(f"under way with no pre-game line: no fair price (not the 80% pre-game one), labelled live, yellow ({lq.get('nofair')})",
   lq["ok"] and lq["live"] and lq["fair"] is None and not lq["clears"] and lq["warn"][0]["k"] == "live")
lq = E.single_buy_quote(dict(lx, pre=0.62), 5)
ok(f"under way with its closing line: a live chance from the score ({lq.get('how')}, {lq.get('fair')}), never 0.80",
   lq["ok"] and lq["live"] and lq["how"] == "live model" and lq["fair"] is not None and lq["fair"] != 0.80)
sp = E.single_buy_quote(dict(lx, ticker=LT, kind="spread"), 5)
ok("a spread on a game under way: no live fair price, Kalshi's price only", sp["ok"] and sp["fair"] is None)

# ---- (7) the game page's buttons: each side's price now (display only)
sides = E.event_sides(EV)
ok(f"event_sides: both teams with their asks ({[(s['name'], s['ask']) for s in sides]})",
   len(sides) == 2 and {s["ticker"] for s in sides} == {EV + "-DEN", EV + "-LAL"} and all(s["ask"] for s in sides))
ok("event_sides refuses a bad code and never raises", E.event_sides("x y") == [] and E.event_sides("") == [])
ok("every buy was logged", any("manual single bought" in str(x) for x in LOG))
