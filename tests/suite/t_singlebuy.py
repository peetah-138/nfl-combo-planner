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
E.set_league("nba")                       # the fake games are NBA (the cap is the loaded league's)
E.CFG["kalshi_key_id"] = "fake-key-id"
E.CFG["budget"] = 100.0
E.CFG["bankroll"] = 400.0
E.hub_conf = lambda: None
E.haptic = lambda *a: None
import requests
import fakenet
fakenet.install(port=1)
G = fakenet.GAMES["KXNBAGAME"]
G[1], G[2] = G[2], G[1]                 # Denver-LA third: the fake's scoreboard has it not started (the second is final)
D = fakenet.ORDERS
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
SPENT = {"v": 10.0}
REAL_WS = E.week_spend
E.week_spend = lambda: SPENT["v"]
REAL_CCS = E.cap_combo_spend
E.cap_combo_spend = lambda code, key, now=None: SPENT["v"]    # the market's own league's combos (tested on its own below)
E.can_trade = lambda: True
EV = fakenet.event_ticker("KXNBAGAME", "DEN", "LAL")          # not started (the fake's third game after the swap above)
T = EV + "-DEN"
LIVE_EV = fakenet.event_ticker("KXNBAGAME", "BOS", "NYK")     # under way (the fake's first game)
LT = LIVE_EV + "-BOS"
mk = {m["ticker"]: m for m in fakenet.markets()}
X = {"ticker": T, "pick": "Denver Nuggets", "event": EV, "exp": mk[T]["expected_expiration_time"], "fair": 0.80,
     "src": "pinnacle", "opp": "Los Angeles Lakers", "fair_at": time.time()}
REAL_BOOK = E.book_depth
# The fake's tickers carry each game's US date, never the machine's (GitHub #128: CI on UTC lost the fake games' scores
# after 00:00 UTC). A 6 PM Eastern game at 00:10 UTC the next day is still on the 20th; each fake game's ticker date
# matches the day the engine reads off its scoreboard start.
import datetime as _dt
ok("fake tickers use the US game date: 00:10 UTC on the 21st is still the 20th",
   fakenet.us_day(_dt.datetime(2026, 11, 21, 0, 10)) == _dt.date(2026, 11, 20))
_evs = {e["id"]: e for e in fakenet.espn_events("basketball/nba")}
ok("every fake game's ticker date is its scoreboard date (as the engine reads it)",
   all(E.ticker_day(fakenet.event_ticker("KXNBAGAME", g[0], g[2])) == E.espn_day(_evs[f"KXNBAGAME{i}"]["date"])
       for i, g in enumerate(G)))
LOG = []


def reset(mode="v2"):
    D.update(mode=mode, sent=[], next=None, fill=None, headers={})
    E._ORDER_SHARED.recent.clear()
    E.save_json(E.ORDER_LEDGER, {})
    E.book_depth = REAL_BOOK
    SPENT["v"] = 10.0
    E._manual_table()
    E.store_x("delete from manual_buys")


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

# ---- (4b) review fixes: manual singles count toward the cap; a stale board price; spreads/totals; game over; unknown start
reset()
SPENT["v"] = 70.0
r = buy(E.single_buy_quote(X, 10))
q = E.single_buy_quote(X, 10)
ok(f"a manual single counts toward the cap afterwards (Kalshi's combo record doesn't see it): room {q.get('room')}",
   r["ok"] and abs(E.manual_spend(T) - r["cost"]) < 0.01 and abs(q["room"] - round(100 - 70 - r["cost"], 2)) < 0.011)
SPENT["v"] = 81.0
q = E.single_buy_quote(X, 10)
ok("two $10 singles on top of $81: the second is over the cap", q["blocked"] and "cap" in q["blocked"])
ok("the bought market is tagged as a manual buy", E.store_rows("select how from app_bets where ticker=?", (T,))[0]["how"] == "manual")
reset()
D["next"] = requests.Timeout("slow")
q = E.single_buy_quote(X, 10)
buy(q)
ok("an unclear buy counts toward the cap too (it may have gone through)", abs(E.manual_spend(T) - q["cost"]) < 0.01)
E.save_json(E.ORDER_LEDGER, {})
reset()
qs = E.single_buy_quote(dict(X, fair_at=time.time() - 20 * 60))
ok(f"a board price 20 minutes old isn't used: no fair price, yellow ({qs.get('nofair')})",
   qs["ok"] and qs["fair"] is None and not qs["clears"] and "minutes old" in (qs["nofair"] or ""))
ok("a fresh board price is used", E.single_buy_quote(dict(X, fair_at=time.time() - 60))["fair"] == 0.8)
SPT0 = f"KXNBASPREAD-{EV.split('-')[1]}-DEN5"      # a real spread ticker (its kind comes from the ticker, #136)
real_mo0 = E.market_open
E.market_open = lambda t: ((True, {"event_ticker": EV.replace("GAME", "SPREAD"), "expected_expiration_time": X["exp"]})
                           if "SPREAD" in t else real_mo0(t))
book(0.72, 0.70)
LX = dict(X, ticker=SPT0, kind="spread", src="model")
ok("a spread 6.6c under the model: green", E.single_buy_quote(dict(LX, fair=0.80))["clears"])
s2 = E.single_buy_quote(dict(LX, fair=0.76))
ok("a spread only 2.6c under the model: yellow (the board's 4c margin), and sized on a shrunk edge",
   not s2["clears"] and E.single_buy_quote(dict(X, fair=0.76))["clears"] and
   s2["sug"] <= E.single_buy_quote(dict(X, fair=0.76))["sug"])
E.market_open = real_mo0
E.book_depth = REAL_BOOK
real_ls = E.leg_score
E.leg_score = lambda l: {"state": "post", "me": 100, "opp": 90}
r = E.single_buy_quote(X, 10)
ok("a finished game: no quote", not r["ok"] and "over" in r["msg"])
E.leg_score = real_ls
q = E.single_buy_quote(dict(X, live=True))
E._SQ["q"][q["q"]]["live"] = True
E.leg_score = lambda l: {"state": "post", "me": 100, "opp": 90}
r = buy(q)
E.leg_score = real_ls
ok("a live quote whose game ends before the tap: refused, nothing sent", not r["ok"] and "ended" in r["msg"] and not D["sent"])
real_mo = E.market_open
E.market_open = lambda t: (None, {})
u = E.single_buy_quote({"ticker": T, "pick": "Denver Nuggets", "fair": 0.8, "src": "pinnacle"}, 10)
E.market_open = real_mo
ok("can't tell when the game starts: a warning, yellow (event taken from the ticker)",
   u["ok"] and any(w["k"] == "start" for w in u["warn"]) and not u["clears"])

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

# ---- (8) second review: missing board time, spreads after the final, event_sides filtering and failure caching, the cap window
q = E.single_buy_quote({k: v for k, v in X.items() if k != "fair_at"}, 10)
ok("a board price with no read time counts as stale: no fair price", q["ok"] and q["fair"] is None and "unknown age" in q["nofair"])
real_ls, real_fs = E.leg_score, E.fetch_scores
E.fetch_scores = lambda max_age=None, code=None: None
E.leg_score = lambda l: {"state": "post"} if l["ticker"].endswith("-DEN") else None
ok("a spread's game is found through its team codes: over after the final (either side's line)",
   E._game_over(f"KXNBASPREAD-{EV.split('-')[1]}-DEN5") and E._game_over(f"KXNBASPREAD-{EV.split('-')[1]}-LAL5"))
E.leg_score, E.fetch_scores = real_ls, real_fs
FIN = fakenet.event_ticker("KXNBAGAME", "MIL", "CHI") + "-MIL"
r = E.single_buy_quote({"ticker": FIN, "fair": 0.6, "src": "pinnacle", "fair_at": time.time()}, 5)
ok("a game the (fake) scoreboard has as final gets no quote, read fresh from the feed", not r["ok"] and "over" in r["msg"])
E.fetch_scores = lambda max_age=None, code=None: None
E.leg_score = lambda l: None
ok("no score for the game: not 'over'", not E._game_over(f"KXNBASPREAD-{EV.split('-')[1]}-DEN5"))
E.leg_score, E.fetch_scores = real_ls, real_fs
real_markets = fakenet.markets
fakenet.markets = lambda hours=6: real_markets(hours) + [dict(real_markets(hours)[2], ticker="BAD'X<", event_ticker=EV)]
E.EVENT_SIDES.clear(); E.EVENT_FAIL.clear()
ok("event_sides drops a market whose ticker isn't a plain code (it would land in an onclick)",
   [s["ticker"] for s in E.event_sides(EV)] == [EV + "-DEN", EV + "-LAL"])
CALLS = []
def boom(hours=6):
    CALLS.append(1)
    raise requests.ConnectionError("down")
fakenet.markets = boom
good = E.EVENT_SIDES[EV][1]
E.EVENT_SIDES[EV] = (time.time() - 20, good)
ok("Kalshi down: the last good copy (under 3 min old) is shown", E.event_sides(EV) == good and len(CALLS) == 1)
ok("...and Kalshi isn't asked again for 15 s", E.event_sides(EV) == good and len(CALLS) == 1)
E.EVENT_SIDES[EV] = (time.time() - 200, good)
ok("a copy over 3 min old isn't shown while Kalshi is down", E.event_sides(EV) == [])
fakenet.markets = real_markets
reset()
E._manual_note("KXNBAGAME-26OCT01DENLAL-DEN", 30.0)          # last month's game (its own slate, not this one)
E.store_x("update manual_buys set ts=? where cost=30.0", (time.time() - 30 * 86400,))
E._manual_note("KXNHLGAME-26NOV19COLSJ-COL", 12.0)
E._manual_note(T, 5.0)
ok(f"the cap counts this window's singles for the loaded league only: not last month's, not the NHL's ({E.manual_spend(T)})",
   E.LEAGUE["code"] == "nba" and E.manual_spend(T) == 5.0)

# ---- (9) release review of 2026.11.20.125: the cap is the market's own league's and fails closed; no false edge on a
# spread/total that left the board; Pause and trading access are checked before anything is quoted; draws refused;
# the balance diagnostics never hold the order lock for long.
import json as _json
reset()
_json.dump({"budget": 30}, open(os.path.join(E.HERE, E.LEAGUES["nhl"]["settings"]), "w"))
NHL_T = "KXNHLGAME-26NOV19COLSJ-COL"
E.ACCT_CACHE.update(at=time.time(), value=([], None, None))
sp, bud, code = E.manual_cap(NHL_T)
ok(f"an NHL market while NBA is loaded: NHL's own cap ($30 from its settings), not NBA's $100 ({bud}, {code})",
   code == "nhl" and bud == 30.0)
KEY = E.week_of(T)
E.ACCT_CACHE.update(at=time.time(), value=([{"cost": 7.0, "lgs": ["nhl"], "first_week": KEY.isoformat(), "week": KEY.isoformat()},
                                             {"cost": 9.0, "lgs": ["nba"], "first_week": KEY.isoformat(), "week": KEY.isoformat()},
                                             {"cost": 4.0, "lgs": ["nba"], "first_week": "2020-01-05", "week": "2020-01-05"}],
                                            None, None))
ok("combo spend is the market's league's, in its game's slate (NBA $9, not NHL's $7, not an old week's $4)",
   REAL_CCS("nba", KEY) == 9.0 and REAL_CCS("nhl", KEY) == 7.0)
E._manual_note(NHL_T, 6.0)
ok("manual spend is the market's league's too: the NHL single doesn't count for NBA",
   E.manual_spend(T) == 0.0 and E.manual_spend(NHL_T) == 6.0)
E.set_league("nhl")                       # Build has the NHL loaded with a big cap; the NBA's is small
E.CFG["budget"] = 1000.0
E.CFG["kalshi_key_id"] = "fake-key-id"
_json.dump({"budget": 15}, open(os.path.join(E.HERE, E.LEAGUES["nba"]["settings"]), "w"))
q = E.single_buy_quote(X, 10)
ok(f"an NBA buy while the NHL is loaded: blocked by the NBA's $15 cap, in the NBA's words ({(q.get('blocked') or '')[:70]})",
   q["ok"] and q["blocked"] and "$15 cap" in q["blocked"] and "NBA" in q["blocked"] and q["budget"] == 15.0)
r = buy(q, anyway=True)
ok("...and the tap is refused, nothing sent", not r["ok"] and "cap" in r["msg"] and not D["sent"])
E.set_league("nba")
E.CFG["budget"] = 100.0
E.CFG["kalshi_key_id"] = "fake-key-id"
os.remove(os.path.join(E.HERE, E.LEAGUES["nba"]["settings"]))
CALLS = []
real_mo = E.market_open
E.market_open = lambda t: (CALLS.append(t), real_mo(t))[1]
r = E.single_buy_quote({"ticker": "KXFOOGAME-26NOV19AAABBB-AAA", "fair": 0.8, "src": "pinnacle"}, 10)
ok(f"a market whose league can't be told: refused in plain words before anything is read ({r['msg'][:50]}...)",
   not r["ok"] and "which league" in r["msg"] and not CALLS)
try:
    E.manual_cap("KXFOOGAME-26NOV19AAABBB-AAA")
    ok("manual_cap refuses an unknown league", False)
except E.CapUnknown:
    ok("manual_cap refuses an unknown league (never the loaded one's cap)", True)
r = E.single_buy_quote({"ticker": "KXEPLGAME-26NOV19ARSCHE-TIE"}, 10)
ok("a soccer draw market: refused in plain words (the panel never prices draws)", not r["ok"] and "draw" in r["msg"].lower())
q = E.single_buy_quote(X, 10, paused=True)
ok("Pause: refused at quote time with the Pause message, nothing read", not q["ok"] and "Paused" in q["msg"] and not CALLS)
E.can_trade = lambda: False
q = E.single_buy_quote(X, 10)
ok("no trading access: refused at quote time", not q["ok"] and "can't trade" in q["msg"])
E.can_trade = lambda: True
q = E.single_buy_quote(X, 10)
E.can_trade = lambda: False
r = buy(q)
E.can_trade = lambda: True
ok("trading access lost between the quote and the tap: refused, nothing sent",
   not r["ok"] and "can't trade" in r["msg"] and not D["sent"])
E.market_open = real_mo

# the cap fails closed: an account read that fails (429 / timeout) never counts as $0
reset()
E.cap_combo_spend = REAL_CCS
real_fa = E._fetch_account
E._fetch_account = lambda: (None, None, "Couldn't reach your Kalshi account just now (Kalshi asked us to slow down).")
E.ACCT_CACHE.update(at=0, value=None)
try:
    REAL_CCS("nba", KEY)
    ok("a failed account read with no earlier one: CapUnknown", False)
except E.CapUnknown:
    ok("a failed account read with no earlier one: CapUnknown (not $0)", True)
q = E.single_buy_quote(X, 10)
ok(f"...the quote is blocked with 'Couldn't check your weekly cap' ({q.get('blocked')})",
   q["ok"] and q["blocked"] and "Couldn't check your weekly cap" in q["blocked"] and not q["clears"])
r = buy(q, anyway=True)
ok("...and Buy anyway is refused, nothing sent", not r["ok"] and not D["sent"])
GOOD = ([{"cost": 9.0, "lgs": ["nba"], "first_week": KEY.isoformat(), "week": KEY.isoformat()}], None, None)
E.ACCT_CACHE.update(at=time.time() - 90, value=GOOD)
ok("a failed read with a good one 90 s ago: that one is used ($9)", REAL_CCS("nba", KEY) == 9.0)
E.ACCT_CACHE.update(at=time.time() - 200, value=GOOD)
try:
    REAL_CCS("nba", KEY)
    ok("a failed read with only a 200 s old one: CapUnknown", False)
except E.CapUnknown:
    ok("a failed read with only a 200 s old one: CapUnknown (too old to trust)", True)
E.ACCT_CACHE.update(at=time.time(), value=GOOD)
q = E.single_buy_quote(X, 10)
E.ACCT_CACHE.update(at=0, value=None)
r = buy(q)
ok("the read fails between the quote and the tap: refused with the cap words, nothing sent",
   q["ok"] and not q["blocked"] and not r["ok"] and "Couldn't check your weekly cap" in r["msg"] and not D["sent"])
E.ACCT_CACHE.update(at=0, value=None)

# ---- (10) issue #136: every other cap fails closed too, Live-idea singles have a cap, singles use their own league's
# cap (never the Mix's). The account read still fails here (429), with no good read in the last 120 s.
try:
    REAL_WS()
    ok("week_spend on a failed read with no recent good one: CapUnknown", False)
except E.CapUnknown:
    ok("week_spend on a failed read with no recent good one: CapUnknown (never $0)", True)
ok("Build's display copy still answers (never used for a cap)", E.week_spend_shown() == 0)
E.week_spend = REAL_WS
real_ks = E.kalshi_send
KS = []
E.kalshi_send = lambda *a, **k: (KS.append(a), (_ for _ in ()).throw(AssertionError("must not reach Kalshi")))[1]
saved_ctx = dict(E.CTX)
E.CTX.update(combos=[{"legs": [{"ticker": T, "event": EV, "pick": "Denver Nuggets", "fair": 0.8}], "fair": 2.0, "min": 1}],
             stake=5, sunday=KEY, offers={1: {"stake": 5.0, "rfq": "r1", "quote": "q1", "market": "M", "pays": 9.0}})
r = E.get_offer(1)
ok(f"combo Get price (Build, and Live's combo ideas) on an unreadable spend: refused with the cap words ({r.get('error')})",
   "Couldn't check your weekly cap" in (r.get("error") or "") and not KS)
r = E.accept_offer(1)
ok("combo Buy on an unreadable spend: refused, nothing sent to Kalshi, no 'check'",
   "Couldn't check your weekly cap" in (r.get("error") or "") and not KS and 1 in E.CTX["offers"])
E.CTX.update(offers={1: {"stake": 5.0, "rfq": "r1", "quote": "q1", "market": "M", "pays": 9.0}})
GOOD90 = ([{"cost": 9.0, "lgs": ["nba"], "first_week": KEY.isoformat(), "week": KEY.isoformat()}], None, None)
E.ACCT_CACHE.update(at=time.time() - 90, value=GOOD90)
ok("a failed read with a good one 90 s ago: the combo cap uses it ($9)", REAL_WS() == 9.0)
E.CFG["budget"] = 12.0
r = E.get_offer(1)
ok(f"...and over the cap on that read the old cap words still answer ({(r.get('error') or '')[:60]})",
   "over your $12 cap" in (r.get("error") or "") and not KS)
E.CFG["budget"] = 100.0
E.ACCT_CACHE.update(at=0, value=None)
E.CTX.clear(); E.CTX.update(saved_ctx)
E.kalshi_send = real_ks
E.CFG["killer_mode"] = "on"
BOUGHT = []
line = E.killer_act("combo", [{"ticker": T, "pick": "Denver Nuggets"}], 5.0, 9.0, 1.3,
                    lambda: (BOUGHT.append(1), (True, "bought"))[1])
krow = E.store_rows("select status, why from killer order by ts desc limit 1")
ok(f"a killer deal on an unreadable spend: skipped, never bought ({krow and dict(krow[0])})",
   not BOUGHT and krow and krow[0]["status"] == "skipped" and "spending cap" in krow[0]["why"])
E.CFG["killer_mode"] = "watch"

# Live's single-game buy idea: the market's own league cap, fail closed, Pause, and noted for every manual cap
reset()
E.week_spend = lambda: SPENT["v"]
E.cap_combo_spend = REAL_CCS
no, sp, bud = E.single_cap_block(T, 3.0)
ok(f"a Live-idea single on an unreadable spend: refused with the cap words ({no})",
   no and "Couldn't check your weekly cap" in no and sp is None)
r = E.idea_single_buy(T, 4, 0.72, log=LOG.append)
ok("...and its Buy is refused, nothing sent", not r["ok"] and "Couldn't check your weekly cap" in r["msg"]
   and not D["sent"] and not r.get("check"))
E.ACCT_CACHE.update(at=time.time(), value=([{"cost": 95.0, "lgs": ["nba"], "first_week": KEY.isoformat(),
                                             "week": KEY.isoformat()}], None, None))
r = E.idea_single_buy(T, 10, 0.72, log=LOG.append)
ok(f"a Live-idea single over the NBA's daily cap: refused, names the window, the setting and the room left ({r['msg'][:90]}...)",
   not r["ok"] and not D["sent"] and "NBA" in r["msg"] and "that day" in r["msg"] and "Daily cap" in r["msg"]
   and "$5.00 left" in r["msg"].replace("$5 left", "$5.00 left") and "$100" in r["msg"])
E.ACCT_CACHE.update(at=time.time(), value=([], None, None))
r = E.idea_single_buy(T, 4, 0.72, paused=True, log=LOG.append)
ok("a Live-idea single while paused: refused, nothing sent", not r["ok"] and "Paused" in r["msg"] and not D["sent"])
r = E.idea_single_buy(T, 4, 0.72, log=LOG.append, key="idea1")
ok(f"a Live-idea single inside the cap: one V2 order ({r.get('msg')})", r["ok"] and len(D["sent"]) == 1)
r2 = E.idea_single_buy(T, 4, 0.72, log=LOG.append, key="idea1")
ok("...a double tap (or a retry) on the same idea sends nothing", not r2["ok"] and len(D["sent"]) == 1)
ok("...noted in manual_buys, so Buy straight's cap sees it", abs(E.manual_spend(T) - 4 * (0.72 + E.single_fee(0.72))) < 0.02)
reset()
E._SQ["ideas"] = {}
E.ACCT_CACHE.update(at=time.time(), value=([], None, None))
book(0.455, 0.45)
r = E.idea_single_buy(T, 2, 0.455, log=LOG.append, key="idea2")
sent = D["sent"][-1][2] if D["sent"] else {}
sent = sent if isinstance(sent, dict) else {}
ok(f"a sub-cent idea price is sent rounded down, never up ({ {k: v for k, v in sent.items() if 'price' in k} })",
   r["ok"] and "46" not in str({k: v for k, v in sent.items() if "price" in k}) and "45" in str(sent))
reset()
E._SQ["ideas"] = {}
E.ACCT_CACHE.update(at=time.time(), value=([], None, None))
D["next"] = requests.Timeout("slow")
r = E.idea_single_buy(T, 4, 0.72, log=LOG.append)
ok("a Live-idea single with no clear answer: 'check', the market blocked, never resent",
   not r["ok"] and r.get("check") and E.order_unsure(T))
n0 = len(D["sent"])
r = E.idea_single_buy(T, 4, 0.72, log=LOG.append)
ok("...a second tap sends nothing", not r["ok"] and len(D["sent"]) == n0)
WSRC = open("wtest/combo_watcher.py").read()
iq = WSRC.index('if a == "idea":')
seg_q = WSRC[iq:WSRC.index('if row["kick"]', iq)]
ib = WSRC.index('if a == "singlebuy":')
seg_b = WSRC[ib:WSRC.index('if a == "buy":', ib)]
ok("the web app's idea single quote checks its own league's cap (not the loaded league's week_spend)",
   "A.single_cap_block(tk" in seg_q and "week_spend" not in seg_q and "A.NO_TRADE_MSG" in seg_q)
ok("the web app's idea single buy goes through idea_single_buy (cap, Pause, block) and never buy_single directly",
   "A.idea_single_buy(" in seg_b and "paused_now()" in seg_b and "buy_single" not in seg_b and "key=" in seg_b)
ok("Build's 'spent' line uses the display-only copy", "A.week_spend_shown()" in WSRC)

# manual singles use their own league's cap even with the Mix loaded (Mix combos keep the Mix cap)
reset()
E.set_league("mix")
E.ACCT_CACHE.update(at=time.time(), value=([{"cost": 8.0, "lgs": ["mix"], "first_week": KEY.isoformat(),
                                             "week": KEY.isoformat()}], None, None))
E.CFG["budget"] = 5.0                     # a tiny Mix cap, already used up by a Mix combo
E.CFG["kalshi_key_id"] = "fake-key-id"
q = E.single_buy_quote(X, 10)
NBA_CAP = float(E.league_cfg("nba")["budget"])
ok(f"Mix loaded with its cap used up: an NBA single is checked against the NBA's own cap (${NBA_CAP:g}), not the "
   f"Mix's $5 ({q.get('budget')}, {q.get('blocked')})", q["ok"] and q["budget"] == NBA_CAP > 5 and not q["blocked"])
no, sp, bud = E.single_cap_block(T, 3.0)
ok("...and so is a Live-idea single (the same check)", no is None and bud == NBA_CAP)
_json.dump({"budget": 2}, open(os.path.join(E.HERE, E.LEAGUES["nba"]["settings"]), "w"))
no, _, _ = E.single_cap_block(T, 3.0)
ok(f"...a small NBA cap still limits it while the Mix is loaded ({(no or '')[:60]})", no and "NBA" in no and "$2" in no)
os.remove(os.path.join(E.HERE, E.LEAGUES["nba"]["settings"]))
ok("Mix combos keep the Mix cap", E.cap_label() == "Mix cap" and REAL_WS() == 8.0)
E.set_league("nba")
E.CFG["budget"] = 100.0
E.CFG["kalshi_key_id"] = "fake-key-id"
E.ACCT_CACHE.update(at=0, value=None)
E._fetch_account = real_fa
E.ACCT_CACHE.update(at=0, value=None)
E.cap_combo_spend = lambda code, key, now=None: SPENT["v"]

# release 125 review, for #136: the manual-buy record fails closed too, and a note that can't be saved is never lost
reset()
real_db = E.STORE["db"]
E.STORE["db"] = None
try:
    E.manual_spend(T)
    ok("manual_spend with no history database: CapUnknown", False)
except E.CapUnknown:
    ok("manual_spend with no history database: CapUnknown (never $0)", True)
no, _, _ = E.single_cap_block(T, 3.0)
ok("...so a single's cap check refuses with the cap words", no and "Couldn't check your weekly cap" in no)
q = E.single_buy_quote(X, 10)
ok("...and Buy straight's quote is blocked", q["ok"] and q["blocked"] and "Couldn't check your weekly cap" in q["blocked"])
E.STORE["db"] = real_db
real_rows = E.store_rows
E.store_rows = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("database is locked"))
try:
    E.manual_spend(T)
    ok("manual_spend when the read fails: CapUnknown", False)
except E.CapUnknown:
    ok("manual_spend when the read fails: CapUnknown (never $0)", True)
E.store_rows = real_rows
ALERTS = []
E.MANUAL_ALERT = ALERTS.append
real_sx = E.store_x
TRIES = []


def bad_insert(sql, *a, **k):
    if "insert into manual_buys" in sql:
        TRIES.append(1)
        raise RuntimeError("disk I/O error")
    return real_sx(sql, *a, **k)


E.store_x = bad_insert
r = E.idea_single_buy(T, 4, 0.72, log=LOG.append, key="idea-note")
E.store_x = real_sx
ok(f"a filled buy whose note won't save: still reported bought, tried twice ({len(TRIES)})", r["ok"] and len(TRIES) == 2)
ok("...logged loudly and Pete told once", any("MANUAL BUY NOT SAVED" in str(x) for x in LOG) and len(ALERTS) == 1)
ok(f"...and the cap still counts it from memory ({E.manual_spend(T)})", E.manual_spend(T) >= 4 * 0.72)
E.store_x = bad_insert
E.idea_single_buy(T, 1, 0.72, log=LOG.append, key="idea-note2")
E.store_x = real_sx
ok("...a second unsaved note doesn't notify again", len(ALERTS) == 1)
E.MANUAL_MEM.clear()
E.MANUAL_ALERT = None
E._CAP_LOGGED.pop("manual_note", None)
E._SQ["ideas"] = {}
reset()
import datetime as _d2
TODAY_T = "KXNBAGAME-" + _d2.date.today().strftime("%y%b%d").upper() + "DENLAL-DEN"
E._manual_note(TODAY_T, 7.0)
ok(f"manual_spend() with no ticker on a daily league counts today's singles ({E.manual_spend()})",
   E.by_day() and E.manual_spend() == 7.0)
# the market's own kind comes from its ticker: a side that says "spread" can't make a game-winner a spread
reset()
qk = E.single_buy_quote(dict(X, kind="spread"), 10)
ok(f"a game-winner ticker stays a game-winner whatever kind the side says ({qk.get('kind')})", qk["ok"] and qk["kind"] == "win")

# a single bought weeks before its game still counts in that game's slate; a market with no date says so
reset()
E._manual_note(T, 20.0)
E.store_x("update manual_buys set ts=? where cost=20.0", (time.time() - 12 * 86400,))
ok("a manual single bought 12 days before its game still counts toward that game's cap", E.manual_spend(T) == 20.0)
try:
    E.manual_cap("KXNBAGAME-NODATE-DEN")
    ok("a market with no date: CapUnknown", False)
except E.CapUnknown as err:
    ok(f"a market with no date: refused with its own words, not 'try again' ({err.words[:45]}...)",
       "which day" in err.words and "try again" not in err.words)
LOCKED = []
E.can_trade = lambda: (LOCKED.append(E._SQ["lock"].locked()), True)[1]
buy(E.single_buy_quote(X, 10))
E.can_trade = lambda: True
ok("can_trade (it may ping the hub) is never called while the quote lock is held", LOCKED and not any(LOCKED))

# a spread/total that's no longer on the board never borrows a moneyline chance
reset()
book(0.50, 0.49)
SPT = f"KXNBASPREAD-{EV.split('-')[1]}-DEN5"
E.market_open = lambda t: (True, {"event_ticker": EV.replace("GAME", "SPREAD"), "expected_expiration_time": X["exp"],
                                  "yes_sub_title": "Denver wins by over 5.5"})
s0 = E.single_buy_quote({"ticker": SPT, "fair": 0.80, "src": "pinnacle", "fair_at": time.time()}, 5)
ok(f"a spread with no line on the board (only a moneyline-style fair): no fair price, no edge, yellow ({s0.get('nofair')})",
   s0["ok"] and s0["kind"] == "spread" and s0["fair"] is None and s0["edge"] is None and not s0["clears"]
   and any(w["k"] == "nofair" for w in s0["warn"]))
s1 = E.single_buy_quote({"ticker": SPT, "kind": "spread", "fair": 0.62, "src": "model", "fair_at": time.time()}, 5)
ok(f"the same spread still on the board: priced from its own line ({s1.get('fair')})", s1["ok"] and s1["fair"] == 0.62)
LSPT = f"KXNBASPREAD-{LIVE_EV.split('-')[1]}-BOS5"
E.market_open = lambda t: (True, {"event_ticker": LIVE_EV.replace("GAME", "SPREAD"),
                                  "expected_expiration_time": mk[LT]["expected_expiration_time"]})
s2 = E.single_buy_quote({"ticker": LSPT, "event": LIVE_EV, "pre": 0.62, "fair": 0.8, "src": "pinnacle"}, 5)
ok(f"a spread on a game under way with no board line: never the live moneyline model (fair {s2.get('fair')}, {s2.get('how')})",
   s2["ok"] and s2["live"] and s2["fair"] is None and s2["how"] is None and s2["edge"] is None)
E.market_open = real_mo

# the balance diagnostics are time-boxed (they can run inside the buy's order lock)
real_signed = E._signed


def slow_signed(method, path, *a, **k):
    if method == "GET" and str(path).startswith("/portfolio/balance"):
        time.sleep(4)
    return real_signed(method, path, *a, **k)


E._signed = slow_signed
t0 = time.time()
w = E.balance_words({"ticker": T, "side": "bid", "yes": 0.5, "count": 10, "reduce_only": False})
took = time.time() - t0
ok(f"a slow balance read: balance_words gives up after ~{E.POTS_BUDGET}s with plain words ({took:.1f}s)",
   took < 2.5 and "insufficient_balance" in w)
reset()
D["next"] = (400, "insufficient_balance")
t0 = time.time()
r = buy(E.single_buy_quote(X, 10))
took = time.time() - t0
ok(f"a manual buy refused for funds with a slow balance read: answered in {took:.1f}s (the order lock isn't held long)",
   not r["ok"] and "enough money" in r["msg"] and took < 3.5 and not E.order_unsure(T))
E._signed = real_signed
time.sleep(2.5)                           # let the abandoned slow reads finish before the file ends
