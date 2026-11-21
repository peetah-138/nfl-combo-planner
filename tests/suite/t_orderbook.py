# Kalshi changed its public order book answer (issue #70): GET /markets/<ticker>/orderbook now returns
# {"orderbook_fp": {"yes_dollars": [["0.52", "3703.51"], ...], "no_dollars": [...]}} (dollar strings, lowest price
# first) instead of {"orderbook": {"yes": [[52, 3703], ...], "no": [...]}} (whole cents). The app read only the old
# key, so every book looked empty and every single/spread/total panel buy failed with "no price on Kalshi right now".
# book_depth reads both shapes the same, in dollars, and never raises on an odd answer. Real-shape fixtures:
# fixtures/kalshi_orderbook.json and fixtures/kalshi_market.json. No real orders: every trading call is faked here.
import os, json, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.HEDGES = os.path.join(E.HERE, "hedges.json"); E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl")
import fakenet
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
FX = json.load(open("fixtures/kalshi_orderbook.json"))
MK = json.load(open("fixtures/kalshi_market.json"))["market"]
NYK, LAC = "KXNBAGAME-26NOV19NYKMIN-NYK", "KXNBAGAME-26NOV19LACSAS-LAC"


def old_book_depth(payload):
    """What book_depth worked out before the fix (copied as it was), for the old-shape answer."""
    ob = (payload or {}).get("orderbook") or {}

    def levels(side):
        rows = ob.get(f"{side}_dollars") or [[x[0] / 100, x[1]] for x in (ob.get(side) or [])]
        out = []
        for row in rows:
            try:
                out.append((float(row[0]), float(row[1])))
            except (TypeError, ValueError, IndexError):
                pass
        return sorted(out)
    yes, no = levels("yes"), levels("no")
    if not yes or not no:
        return {"bid": yes[-1][0] if yes else None, "ask": 1 - no[-1][0] if no else None,
                "spread": None, "ask_size": no[-1][1] if no else 0, "thin": True}
    bid, ask = yes[-1][0], 1 - no[-1][0]
    return {"bid": bid, "ask": ask, "spread": round(ask - bid, 4), "ask_size": no[-1][1],
            "thin": ask - bid > 0.04 or no[-1][1] < 100}


# ---- the real shapes: the new answer reads exactly like the old one did
for t in (NYK, LAC):
    new, old = E.book_info(FX[t]["new"]), E.book_info(FX[t]["old"])
    ok(f"{t[-3:]}: new shape reads the same as the old shape", new == old)
    ok(f"{t[-3:]}: old shape reads exactly as before the fix", old == old_book_depth(FX[t]["old"]))
    ok(f"{t[-3:]}: the old code saw nothing in the new shape (the bug)", old_book_depth(FX[t]["new"])["ask"] is None)
nyk = E.book_info(FX[NYK]["new"])
ok("NYK: best bid 52c, ask 53c (1 - best NO bid 47c), in dollars not cents",
   abs(nyk["bid"] - 0.52) < 1e-9 and abs(nyk["ask"] - 0.53) < 1e-9 and nyk["spread"] == 0.01)
ok("NYK: matches the market's own yes_bid/yes_ask from GET /markets/<ticker>",
   abs(nyk["bid"] - float(MK["yes_bid_dollars"])) < 1e-9 and abs(nyk["ask"] - float(MK["yes_ask_dollars"])) < 1e-9)
ok("NYK: size at the best ask read from the quantity string, not thin", abs(nyk["ask_size"] - 143646.29) < 1e-6 and not nyk["thin"])
lac = E.book_info(FX[LAC]["new"])
ok("LAC: bid 11c, ask 12c", abs(lac["bid"] - 0.11) < 1e-9 and abs(lac["ask"] - 0.12) < 1e-9)
shuffled = {"orderbook_fp": {k: list(reversed(v)) for k, v in FX[NYK]["new"]["orderbook_fp"].items()}}
ok("rows in any order: the best price still wins", E.book_info(shuffled) == nyk)
lv = E.book_levels(FX[NYK]["new"]["orderbook_fp"], "yes")
ok("book_levels: dollars, lowest first", lv[0] == (0.01, 1598443.56) and lv[-1] == (0.52, 3703.51))

# ---- odd answers never raise and never invent a price
empty = {"bid": None, "ask": None, "spread": None, "ask_size": 0, "thin": True}
odd = [None, [], "x", 5, {}, {"orderbook_fp": None}, {"orderbook_fp": []}, {"orderbook_fp": {"yes_dollars": "x"}},
       {"orderbook": {"yes": None, "no": None}}, {"orderbook_fp": {"yes_dollars": [[None, 1], ["abc", "2"], [0.5], "x", None]}},
       {"orderbook_fp": {"yes_dollars": [["nan", "5"], ["inf", "5"], ["1.5", "5"], ["0", "5"], ["-0.2", "5"]]}},
       {"orderbook_fp": {"no_dollars": [["0.40", "nan"], ["0.40", "0"], ["0.40", "-3"], ["0.40", "inf"]]}},
       {"orderbook": {"yes": [[150, 10], [0, 10]], "no": [["x", 1]]}}]
res = []
for o in odd:
    try:
        res.append(E.book_info(o))
    except Exception as err:                 # noqa: BLE001 (any raise is a failure)
        res.append(repr(err))
ok("garbage answers: no prices, thin, never raises", all(r == empty for r in res))
one = E.book_info({"orderbook_fp": {"yes_dollars": [["0.40", "10"]], "no_dollars": []}})
ok("one side only: the bid, no ask, thin", one["bid"] == 0.40 and one["ask"] is None and one["thin"])
mixed = E.book_info({"orderbook_fp": {"yes_dollars": [], "no_dollars": []}, "orderbook": {"yes": [[45, 200]], "no": [[50, 200]]}})
ok("empty new key but a filled old one: reads the old one", abs(mixed["bid"] - 0.45) < 1e-9 and abs(mixed["ask"] - 0.50) < 1e-9)
ds = E.book_info({"orderbook": {"yes": [["0.45", "200"]], "no": [["0.50", "200"]]}})
ok("old key with dollar strings: read as dollars, not divided by 100", abs(ds["bid"] - 0.45) < 1e-9 and abs(ds["ask"] - 0.50) < 1e-9)
df = E.book_info({"orderbook": {"yes": [[0.45, 200]], "no": [[0.50, 200]]}})
ok("old key with dollar numbers: read as dollars, not divided by 100", abs(df["bid"] - 0.45) < 1e-9 and abs(df["ask"] - 0.50) < 1e-9)
half = E.book_info({"orderbook_fp": {"yes_dollars": [["0.30", "200"]], "no_dollars": []},
                    "orderbook": {"yes": [[45, 200]], "no": [[50, 200]]}})
ok("new key with one side only, full old key: reads the full one", abs(half["bid"] - 0.45) < 1e-9 and abs(half["ask"] - 0.50) < 1e-9)
four = E.book_info({"orderbook_fp": {"yes_dollars": [["0.49", "500"]], "no_dollars": [["0.47", "500"]]}})
ok("exactly 4c apart (0.53 - 0.49 in floats): spread 0.04, not thin", four["spread"] == 0.04 and not four["thin"])
both = E.book_info({"orderbook_fp": {"yes_dollars": [["0.30", "200"]], "no_dollars": [["0.60", "200"]]},
                    "orderbook": {"yes": [[45, 200]], "no": [[50, 200]]}})
ok("both keys: the new one wins", abs(both["bid"] - 0.30) < 1e-9)

# ---- book_depth over the (fake) network: Kalshi's new shape by default, the old one too, identical
fakenet.install()
mk = fakenet.markets()
m0 = next(m for m in mk if m["ticker"].startswith("KXNBAGAME"))
T = m0["ticker"]
seen = {}
for shape in ("fp", "old"):
    fakenet.BOOK_SHAPE["v"] = shape
    E.BOOK_DEPTH.clear()
    seen[shape] = E.book_depth(T, max_age=0)
fakenet.BOOK_SHAPE["v"] = "fp"
ok("book_depth: new-shape answer gives the market's bid and ask",
   seen["fp"] and abs(seen["fp"]["ask"] - float(m0["yes_ask_dollars"])) < 1e-9 and abs(seen["fp"]["bid"] - float(m0["yes_bid_dollars"])) < 1e-9)
ok("book_depth: old-shape answer reads identically", seen["fp"] == seen["old"])
E.BOOK_DEPTH.clear()
ok("book_depth: an unknown ticker = no prices (not an error)", E.book_depth("KXNOPE-1", max_age=0)["ask"] is None)
_get = E.requests.get
E.requests.get = lambda url, **k: fakenet.R({"error": "rate limited"}, 429)
E.BOOK_DEPTH.clear()
r429 = E.book_depth(T)
E.requests.get = _get
ok("book_depth: a 429 is unknown (None), not an empty book, and isn't cached", r429 is None and T not in E.BOOK_DEPTH
   and E.book_depth(T)["ask"] is not None)

# ---- a Buy idea for a single never offers under one contract (sizes can be fractional now)
from wsrc import watcher_text   # the watcher file plus its web app files (watcher/spa/)
W = watcher_text() if os.path.exists("wtest/combo_watcher.py") else ""
ok("Buy idea: caps at the whole contracts on sale, says so when under one",
   'n = min(n, int(dpt["ask_size"]))' in W and "under one contract for sale" in W)

# ---- the gap rule at exactly 6c on a live panel single: 0.55 - 0.49 is 0.06000000000000005 in floats, still allowed
_real_book_depth, _real_recheck = E.book_depth, E.live_recheck
E.buy_single = lambda t, n, px: (n, None)
E.live_recheck = lambda legs: (legs, "")
E.book_depth = lambda t, max_age=60: E.book_info({"orderbook_fp": {"yes_dollars": [["0.49", "500"]], "no_dollars": [["0.45", "500"]]}})
good, note, _ = E._buy_panel_bet({"kind": "single", "live": True, "code": "nba", "stake": 10.0, "legs": [{"ticker": T, "fair": 0.7}]})
ok(f"live panel single, exactly 6c gap: allowed ({note})", good)
E.book_depth = lambda t, max_age=60: E.book_info({"orderbook_fp": {"yes_dollars": [["0.48", "500"]], "no_dollars": [["0.45", "500"]]}})
good, note, _ = E._buy_panel_bet({"kind": "single", "live": True, "code": "nba", "stake": 10.0, "legs": [{"ticker": T, "fair": 0.7}]})
ok("live panel single, 7c gap: too jumpy, not bought", good is False and "jumpy" in note)
E.book_depth, E.live_recheck = _real_book_depth, _real_recheck

# ---- the 6c gap rule on the parsed book
wide = {"orderbook_fp": {"yes_dollars": [["0.40", "500"]], "no_dollars": [["0.53", "500"]]}}   # 40c bid, 47c ask
ok("a 7c gap: spread 0.07, thin", E.book_info(wide)["spread"] == 0.07 and E.book_info(wide)["thin"])
ok("the gap rule: 7c is over LIVE_SPREAD and HEDGE_GAP (6c), 1c is not",
   E.book_info(wide)["spread"] > E.LIVE_SPREAD and E.book_info(wide)["spread"] > E.HEDGE_GAP and nyk["spread"] <= E.LIVE_SPREAD)

# ---- a single / spread / total panel bet buys against the new-shape book (no real order: buy_single is faked)
BOUGHT = []
E.buy_single = lambda t, n, px: (BOUGHT.append((t, n, px)) or (n, None))
E.post_sell = lambda *a, **k: None
ask0 = float(m0["yes_ask_dollars"])
E.RESTING_SELLS_OK = True     # sell-early bets wait for Pete's call on resting exits (issue #81); priced the same way
for kind in ("single", "line", "early"):
    BOUGHT.clear(); E.BOOK_DEPTH.clear()
    c = {"kind": kind, "code": "nba", "stake": 10.0, "exit": 0.9, "legs": [{"ticker": T, "pick": "x", "fair": ask0 + 0.1, "p": ask0}]}
    good, note, d = E._buy_panel_bet(c)
    ok(f"panel {kind}: bought at Kalshi's ask from the new-shape book ({note})",
       good and BOUGHT and BOUGHT[0][0] == T and abs(BOUGHT[0][2] - ask0) < 1e-9 and BOUGHT[0][1] == int(10 // (ask0 + E.single_fee(ask0))))
E.RESTING_SELLS_OK = False
BOUGHT.clear(); E.BOOK_DEPTH.clear()
good, note, _ = E._buy_panel_bet({"kind": "single", "code": "nba", "stake": 10.0, "legs": [{"ticker": "KXNOPE-1", "fair": 0.9}]})
ok("panel single, empty book: skipped with 'no price', nothing bought", good is False and "no price" in note and not BOUGHT)

# ---- auto-hedge re-reads the hedge side's book (new shape) and buys at that ask
other = next(m for m in mk if m["event_ticker"] == m0["event_ticker"] and m["ticker"] != T)
E.MINE["all_games"] = {"g": [{"ticker": T, "pick": "A", "p": 0.7}, {"ticker": other["ticker"], "pick": "B", "p": 0.2}]}
E.MINE["hold"] = {"C1": {"need": [(("yes", T), "A")], "cost": 5.0, "pays": 20}}
E.CFG.update(hedge_cap=100, prefer_hedge=True)
E.BOOK_DEPTH.clear()
hg, why = E.hedge_fresh("C1", E.MINE["hold"]["C1"], 10.0)
ok(f"hedge_fresh: priced on the hedge side's fresh new-shape book ({why or 'ok'})",
   hg is not None and hg["ticker"] == other["ticker"] and abs(hg["price"] - float(other["yes_ask_dollars"])) < 1e-9)

# ---- smart sell for a single: it sells at the market's bid (GET /markets fields, which kept their shape), in cents
SENT = []
E.kalshi_send = lambda m, p, b=None, params=None: (SENT.append((m, p, b)), {"order": {"fill_count_fp": f"{b['count']:.2f}"}})[1]
E.hands_off = lambda t: False
E.single_sell_reason = lambda x, bid, ask, cut_ok=False: ("smart", 1.0)
E.smart_params = lambda ts: {"loss": None}
E.resting_single_sells = lambda: set()
E.sold_today = lambda: 0
E.log_decision = lambda rec: None
E.CFG["auto_cap"] = 5
real = dict(MK)
E.SINGLES.update(at=time.time(), mk={real["ticker"]: real},
                 items=[{"t": real["ticker"], "side": "yes", "state": "live", "label": "Knicks", "n": 10, "cost": 4.0, "chance": 0.5, "kind": "win"}])
msgs = E.smart_sell_singles()
ok("smart sell single: sold into the bid from the real market fields (52c, sent as 52 cents)",
   len(SENT) == 1 and SENT[0][2]["yes_price"] == 52 and SENT[0][2]["count"] == 10 and SENT[0][2]["reduce_only"] and msgs)
SENT.clear()
E.SINGLES.update(at=time.time(), mk={real["ticker"]: dict(real, yes_bid_dollars="0.4400", yes_ask_dollars="0.5300")})
E.smart_sell_singles()
ok("smart sell single: a 9c gap is too thin, nothing sold", not SENT)

# ---- an order book Kalshi would not answer (429/5xx -> book_depth None) is unknown, never "fine": the single and
# spread/total idea loops skip that bet and send no alert (before, only a thin book was skipped)
_cand = {"ticker": T, "pick": "Knicks", "p": 0.40, "fair": 0.55, "edge": 0.12, "kind": "spread", "book_line": -3.5,
         "event": "EV1", "start": "2099-01-01T00:00:00Z", "opp": "x"}
_names = ("line_candidates", "single_candidates", "book_depth", "load_book_state", "week_games", "fetch_markets",
          "attach_fair", "maker_pass", "screen_live", "injury_note")
_saved = {k: getattr(E, k) for k in _names}
E.line_candidates = lambda code: [dict(_cand)]
E.single_candidates = lambda games, live_ok=(), min_fair=0.2: [dict(_cand, kind="single")]
E.load_book_state = lambda snap: {}
E.week_games = lambda mk: ({}, None, None)
E.fetch_markets = lambda: []
E.attach_fair = lambda games, book: None
E.maker_pass = lambda *a, **k: []
E.screen_live = lambda games, bf: ([], [])
E.injury_note = lambda *a, **k: ([], False)
E.LEAGUE["code"] = "nba"
for label, depth, expect in (("unknown book (None)", None, 0), ("thin book", {"thin": True, "ask": 0.4, "bid": 0.3}, 0),
                             ("good book", {"thin": False, "ask": 0.40, "bid": 0.39, "ask_size": 500}, 1)):
    E.book_depth = lambda t, max_age=60, _d=depth: _d
    for name, fn in (("line_pass", lambda al: E.line_pass("nba", alert=al)), ("single_pass", lambda al: E.single_pass({}, alert=al))):
        E.store_x("delete from suggestions")
        sent = []
        did = fn(lambda *a, **k: sent.append(a))
        ok(f"{name}, {label}: " + ("idea offered, alert sent" if expect else "skipped, no idea, no alert"),
           (len(did) == 1 and len(sent) == 1) if expect else (not did and not sent))
for k, v in _saved.items():
    setattr(E, k, v)
