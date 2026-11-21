"""A fake internet for the dev environment (tests/dev_webapp.py): Kalshi, ESPN, GitHub, ntfy and the odds service
answered from memory, patched over `requests`. Same shapes as the fakes in macsmoke/run.py and test_webapp_pw.py.
Nothing here ever opens a real connection: any URL it does not know gets an empty answer, any non-GET Kalshi call
is refused (unless an engine test turns on the fake order desk, ORDERS["mode"]), and any local address except the dev web app's own port is refused (so the real hub on 8765 and the
real app on 8766 can't be reached)."""
import json, time, datetime as dt, requests
from urllib.parse import urlsplit

GAMES = {   # series -> [(away abbr, away name, home abbr, home name, chance away wins)]
    "KXNBAGAME": [("BOS", "Boston Celtics", "NYK", "New York Knicks", .62), ("DEN", "Denver Nuggets", "LAL", "Los Angeles Lakers", .70),
                  ("MIL", "Milwaukee Bucks", "CHI", "Chicago Bulls", .58), ("PHX", "Phoenix Suns", "GSW", "Golden State Warriors", .55)],
    "KXNHLGAME": [("COL", "Colorado Avalanche", "SJ", "San Jose Sharks", .66), ("VGK", "Vegas Golden Knights", "DAL", "Dallas Stars", .52)],
}
STARTED = time.time()
ESPN_PATH = {"KXNBAGAME": "basketball/nba", "KXNHLGAME": "hockey/nhl"}


class R:
    """Just enough of requests.Response."""
    def __init__(s, o, code=200, raw=None):
        s._o, s.status_code, s.ok = o, code, code < 400
        s.content = raw if raw is not None else json.dumps(o).encode()
        s.text = s.content.decode()
        s.headers = {}

    def json(s):
        return s._o

    def raise_for_status(s):
        if s.status_code >= 400:
            raise requests.HTTPError(f"{s.status_code} Error (fake)", response=s)

    def iter_lines(s, *a, **k):
        return iter(())

    def __enter__(s):
        return s

    def __exit__(s, *a):
        return False


def game_start(series, i):
    """When fake game i of a series starts (naive UTC): the first one an hour before this process began (under way),
    the second four hours before (over), the rest 3+i hours after. Fixed at import, never the clock at call time, so a
    game's ticker date and its scoreboard start can never disagree because a test ran across midnight. Keyed on the
    game's place in GAMES (the scoreboard's live/over/not-started roles are too): a test that reorders GAMES must do it
    before building any ticker or market (t_singlebuy swaps two games right after import)."""
    base = _base()
    return base - dt.timedelta(hours=1 if i == 0 else 4) if i < 2 else base + dt.timedelta(hours=3 + i)


def _base():
    return dt.datetime.fromtimestamp(STARTED, dt.timezone.utc).replace(tzinfo=None)


def us_day(t):
    """The US game date Kalshi writes in a ticker (Eastern; the engine's espn_day uses UTC-5 the same way). Never the
    machine's own date: CI runs on UTC, so after 00:00 UTC a 7 PM Eastern game would get tomorrow's date (GitHub #128)."""
    return (t - dt.timedelta(hours=5)).date()


def event_ticker(series, a, b, day=None):
    if day is None:
        i = next((k for k, g in enumerate(GAMES.get(series, [])) if g[0] == a and g[2] == b), None)
        day = us_day(game_start(series, i) if i is not None else _base())
    return f"{series}-{day.strftime('%y%b%d').upper()}{a}{b}"


def markets(hours=6):
    """Two markets (one per team) for every fake game, ending in a few hours (counted from when this process began,
    like the games' start times, so expiry and start stay in step)."""
    now = _base()
    out = []
    for series, games in GAMES.items():
        for gi, (a, an, b, bn, pa) in enumerate(games):
            # the first game of each league is under way (it started about an hour ago), so the live screens have something to show
            exp = (now + dt.timedelta(hours=2 if gi == 0 else hours)).isoformat() + "Z"
            ev = event_ticker(series, a, b)
            for t, n, p in ((a, an, pa), (b, bn, 1 - pa)):
                out.append({"ticker": f"{ev}-{t}", "event_ticker": ev, "yes_sub_title": n, "yes_ask_dollars": f"{p + .02:.2f}",
                            "yes_bid_dollars": f"{p:.2f}", "last_price_dollars": f"{p:.2f}",
                            "expected_expiration_time": exp, "status": "active"})
    return out


BOOK_SHAPE = {"v": "fp"}    # "fp" = Kalshi's order book shape since Nov 2026 (orderbook_fp, dollar strings); "old" = cents


def orderbook(m, size=500):
    """The order book behind a fake market: best YES bid = its bid, best NO bid = 1 - its ask (so the YES ask
    matches the market's), a few worse levels under each, lowest price first like Kalshi."""
    bid, ask = float(m["yes_bid_dollars"]), float(m["yes_ask_dollars"])
    yes = [(round(bid - k / 100, 2), size + 100 * k) for k in (3, 2, 1, 0) if bid - k / 100 > 0]
    no = [(round(1 - ask - k / 100, 2), size + 100 * k) for k in (3, 2, 1, 0) if 1 - ask - k / 100 > 0]
    if BOOK_SHAPE["v"] == "old":
        return {"orderbook": {"yes": [[round(p * 100), n] for p, n in yes], "no": [[round(p * 100), n] for p, n in no]}}
    return {"orderbook_fp": {"yes_dollars": [[f"{p:.4f}", f"{n:.2f}"] for p, n in yes],
                             "no_dollars": [[f"{p:.4f}", f"{n:.2f}"] for p, n in no]}}


def espn_events(path):
    """Scoreboard events: the first game of each sport is live, the second is over, the rest haven't started."""
    series = next(s for s, p in ESPN_PATH.items() if p == path)
    evs = []
    for i, (a, an, b, bn, pa) in enumerate(GAMES[series]):
        state, name = (("in", "STATUS_IN_PROGRESS"), ("post", "STATUS_FINAL"))[i] if i < 2 else ("pre", "STATUS_SCHEDULED")
        start = game_start(series, i)
        sc = {0: (54, 49), 1: (112, 104)}.get(i, (0, 0))
        clock = "5:42"
        if i == 0:                      # the live game plays on: the clock runs down and baskets drop as time passes
            el = int(time.time() - STARTED)
            left = max(5, 342 - el)
            clock = f"{left // 60}:{left % 60:02d}"
            sc = (54 + 2 * (el // 20), 49 + 3 * (el // 35))
        st = {"period": 2 if i == 0 else 4, "displayClock": clock, "type": {"state": state, "name": name, "shortDetail": "7:00 PM"}}
        evs.append({"id": f"{series}{i}", "date": start.strftime("%Y-%m-%dT%H:%MZ"), "status": st,
                    "competitions": [{"status": st,
                                      "competitors": [{"id": x, "homeAway": ha, "score": str(s),
                                                       "team": {"id": x, "displayName": n, "shortDisplayName": n.split()[-1],
                                                                "location": n.rsplit(" ", 1)[0], "abbreviation": x}}
                                                      for x, n, ha, s in ((a, an, "away", sc[0]), (b, bn, "home", sc[1]))]}]})
    return evs


def _tennis(mid, ev, a, b, sets_a, sets_b, games, pts=(0, 0), done=False):
    """Kalshi's milestone and live block for one tennis match, in the shapes its public API returns."""
    ia, ib = f"{mid}-a", f"{mid}-b"
    ms = {"id": mid, "type": "tennis_tournament_singles", "title": f"{a} vs {b}", "primary_event_tickers": [ev], "related_event_tickers": [ev],
          "details": {"best_of": "3", "first_competitor_id": ia, "second_competitor_id": ib, "status": "closed" if done else "live"}}
    rs = lambda mine, done_: [{"outcome": ("winner" if x > y else "loser") if done_ or i < len(games) - 1 else "ongoing", "score": x}
                              for i, (x, y) in enumerate(g if mine else (g[1], g[0]) for g in games)]
    d = {"competitor1_id": ia, "competitor2_id": ib, "competitor1_overall_score": sets_a, "competitor2_overall_score": sets_b,
         "competitor1_round_scores": rs(True, done), "competitor2_round_scores": rs(False, done),
         "competitor1_current_round_score": 0 if done else pts[0], "competitor2_current_round_score": 0 if done else pts[1],
         "advantage": "", "server": "" if done else ia, "status": "closed" if done else "started",
         "widget_status": "finished" if done else "live", "winner": (ia if sets_a > sets_b else ib) if done else "",
         "match_status": "ended" if done else ""}
    return ms, {"milestone_id": mid, "type": "tennis_tournament_singles", "details": d}


def kalshi_live():
    """The dev seed's tennis on Kalshi's live data: Sinner-Alcaraz finished, Rublev-Zverev in play (games move as time
    passes), Djokovic-Medvedev unknown to it (so it keeps the honest 'Probably finished')."""
    el = int(time.time() - STARTED)
    g = 3 + (el // 40) % 3
    out = [_tennis("ms-sinalc", "KXATPMATCH-26NOV18SINALC", "Sinner", "Alcaraz", 2, 1, [(6, 4), (3, 6), (7, 5)], done=True),
           _tennis("ms-rubzve", "KXATPMATCH-26NOV18RUBZVE", "Rublev", "Zverev", 1, 0, [(6, 3), (g, 3)], pts=((15 * (el // 10)) % 45, 30))]
    return {ms["related_event_tickers"][0]: ms for ms, _ in out}, {ld["milestone_id"]: ld for _, ld in out}


# A fake Kalshi order desk, OFF unless a test turns it on (the dev web app never places orders). Modes, from the
# OpenAPI spec (docs.kalshi.com/openapi.yaml): "v2" = V2 at /portfolio/events/orders, the legacy writes answer 410
# deprecated_v1_order_endpoint (Kalshi today); "legacy" = an account without V2 yet (404 on the V2 path, legacy works);
# "both"; "gone" = 404 on V2 and 410 on legacy. ORDERS["next"] = a status code, (status, code), or an exception to
# answer the next order write with; ORDERS["fill"] = contracts filled (default: all). Every write is in ORDERS["sent"].
# ORDERS["balance"] = the GET /portfolio/balance answer (with balance_breakdown, the cash in each exchange shard);
# ORDERS["shards"] = {ticker: exchange_index} for GET /markets/{ticker}.
ORDERS = {"mode": None, "sent": [], "next": None, "fill": None, "headers": {}, "balance": None, "shards": {}}
GONE = {"error": {"code": "deprecated_v1_order_endpoint", "message": "This endpoint has been removed. Please switch "
                  "to the V2 endpoints", "details": "https://docs.kalshi.com/getting_started/order_errors"}}


def order_desk(method, path, params, data):
    try:
        body = json.loads(data) if data else None
    except (TypeError, ValueError):
        body = None
    ORDERS["sent"].append((method, path, body, dict(params or {})))
    mode, v2 = ORDERS["mode"], path.startswith("/portfolio/events/orders")
    nxt, ORDERS["next"] = ORDERS["next"], None
    if isinstance(nxt, BaseException):
        raise nxt
    if isinstance(nxt, R):
        return nxt
    if nxt:
        st, code = nxt if isinstance(nxt, tuple) else (nxt, "")
        return R({"error": {"code": code, "message": f"fake {st}"}} if code else {"message": f"fake {st}"}, st)
    if v2 and mode in ("legacy", "gone"):
        return R({"message": "404 page not found"}, 404)
    if not v2 and mode in ("v2", "gone"):
        return R(GONE, 410)
    if method == "DELETE":
        oid = path.rsplit("/", 1)[-1]
        return R({"order_id": oid, "reduced_by": "5.00", "ts_ms": 1} if v2 else {"order": {"order_id": oid, "status": "canceled"}})
    n = float(body.get("count") or body.get("count_fp") or 0)
    f = n if ORDERS["fill"] is None else min(n, ORDERS["fill"])
    if v2:
        ans = {"order_id": f"ord-{len(ORDERS['sent'])}", "client_order_id": body.get("client_order_id"),
               "fill_count": f"{f:.2f}", "remaining_count": "0.00", "ts_ms": 1715793600123}
        if f:
            ans["average_fill_price"] = body.get("price")
        r = R(ans, 201)
    else:
        r = R({"order": {"order_id": f"ord-{len(ORDERS['sent'])}", "status": "executed" if f else "canceled",
                         "fill_count_fp": f"{f:.2f}", "remaining_count_fp": "0.00"}}, 201)
    r.headers = dict(ORDERS["headers"])
    return r


# A fake desk for moving cash between pots (POST /portfolio/intra_exchange_instance_transfer), OFF unless a test turns
# it on (TRANSFERS["on"]). Shapes from docs.kalshi.com/openapi.yaml: amount in centicents, source/destination
# "event_contract", source_exchange_shard / destination_exchange_shard, client_transfer_id (a repeat answers 409).
# TRANSFERS["next"] = a status code, (status, code), an R or an exception for the next POST; TRANSFERS["status"] =
# what GET .../intra_exchange_instance_transfers/{id} says ("complete" moves the cash in ORDERS["balance"] at once,
# "pending" leaves it until the status flips); TRANSFERS["active"] = intra_exchange_transfers_active in /exchange/status.
TRANSFERS = {"on": False, "sent": [], "next": None, "status": "complete", "ids": {}, "active": True, "moved": {}}


def _move_cash(src, dst, cents):
    b = ORDERS.get("balance")
    if not isinstance(b, dict):
        return
    for row in b.get("balance_breakdown") or []:
        if row["exchange_index"] == src:
            row["balance"] = f"{float(row['balance']) - cents / 100:.4f}"
        if row["exchange_index"] == dst:
            row["balance"] = f"{float(row['balance']) + cents / 100:.4f}"


def transfer_desk(method, path, data):
    T = TRANSFERS
    if method == "GET":
        tid = path.rsplit("/", 1)[-1]
        t = T["moved"].get(tid)
        if not t:
            return R({"error": {"code": "not_found", "message": "fake"}}, 404)
        if T["status"] == "complete" and not t["done"]:
            t["done"] = True
            _move_cash(t["src"], t["dst"], t["amount"] // 100)
        return R({"transfer": {"transfer_id": tid, "client_transfer_id": t["cid"], "source": "event_contract",
                               "destination": "event_contract", "source_exchange_shard": t["src"],
                               "destination_exchange_shard": t["dst"], "amount": f"{t['amount'] / 10000:.4f}",
                               "status": "complete" if t["done"] else "pending", "created_ts": 1}})
    try:
        body = json.loads(data) if data else None
    except (TypeError, ValueError):
        body = None
    T["sent"].append(body)
    nxt, T["next"] = T["next"], None
    if isinstance(nxt, BaseException):
        raise nxt
    if isinstance(nxt, R):
        return nxt
    if nxt:
        st, code = nxt if isinstance(nxt, tuple) else (nxt, "")
        return R({"error": {"code": code, "message": f"fake {st}"}}, st)
    cid = (body or {}).get("client_transfer_id")
    if cid and cid in T["ids"]:
        return R({"error": {"code": "conflict", "message": "duplicate client_transfer_id"}}, 409)
    tid = f"tr-{len(T['sent'])}"
    T["ids"][cid] = tid
    T["moved"][tid] = {"cid": cid, "src": body["source_exchange_shard"], "dst": body["destination_exchange_shard"],
                       "amount": int(body["amount"]), "done": False}
    if T["status"] == "complete":
        T["moved"][tid]["done"] = True
        _move_cash(body["source_exchange_shard"], body["destination_exchange_shard"], int(body["amount"]) // 100)
    return R({"transfer_id": tid})


def fake(method, url, params=None, port=18800, data=None):
    """The answer for one call, or None for the dev app's own address (the caller makes that one for real)."""
    try:
        parts = urlsplit(url)
        host, uport = parts.hostname, parts.port
    except ValueError:                      # unparseable (bad port etc.): never pass it through
        host, uport = None, None
    if host in ("127.0.0.1", "localhost", "::1", "0.0.0.0") or (host or "").startswith("127."):
        if host in ("127.0.0.1", "localhost") and uport == port:
            return None
        raise requests.ConnectionError(f"dev environment: refused local address {url.split('?')[0]}")
    if "kalshi" in url:
        path = url.split("/trade-api/v2")[-1].split("?")[0]
        if method != "GET" and ORDERS["mode"] and path.startswith(("/portfolio/orders", "/portfolio/events/orders")):
            return order_desk(method, path, params, data)                   # a test's fake order desk only
        if TRANSFERS["on"] and path.startswith("/portfolio/intra_exchange_instance_transfer"):
            return transfer_desk(method, path, data)                        # a test's fake transfer desk only
        if path == "/exchange/status" and TRANSFERS["on"]:
            return R({"exchange_active": True, "exchange_index_statuses": [
                {"exchange_index": i, "description": d, "intra_exchange_transfers_active": TRANSFERS["active"]}
                for i, d in ((0, "Default"), (1, "Combos"), (3, "Tennis, Baseball, Basketball"))]})
        if method != "GET":
            return R({"error": "dev environment: no orders"}, 403)          # never a trade
        tk = path.split("/")[2] if path.startswith("/markets/") and path.count("/") == 2 else None
        if tk and tk in (ORDERS.get("shards") or {}):                  # a test's market and its cash pot
            return R({"market": {"ticker": tk, "exchange_index": ORDERS["shards"][tk], "status": "active"}})
        if path == "/portfolio/balance" and ORDERS.get("balance") is not None:
            b = ORDERS["balance"]
            return b if isinstance(b, R) else R(b)
        if path.startswith("/markets"):
            mk = markets()
            if path.endswith("/orderbook"):
                m = next((x for x in mk if x["ticker"] == path.split("/")[2]), None)
                return R(orderbook(m) if m else {"orderbook_fp": {"yes_dollars": [], "no_dollars": []}})
            if path.count("/") >= 2:
                m = next((x for x in mk if x["ticker"] == path.split("/")[2]), None)
                return R({"market": m} if m else {}, 200 if m else 404)
            st, ev = (params or {}).get("series_ticker", ""), (params or {}).get("event_ticker", "")
            if ev:                          # one game's markets (the game page's buy buttons)
                return R({"markets": [m for m in mk if m["event_ticker"] == ev], "cursor": ""})
            return R({"markets": [m for m in mk if st and m["ticker"].startswith(st)], "cursor": ""})
        if path == "/portfolio/balance":
            return R({"balance": 21103})
        if path.startswith("/portfolio"):
            return R({"fills": [], "settlements": [], "positions": [], "market_positions": [], "event_positions": [], "orders": [], "cursor": ""})
        if path.startswith("/communications"):
            return R({"rfqs": [], "quotes": []})
        if path == "/milestones":
            ms, _ = kalshi_live()
            m = ms.get((params or {}).get("related_event_ticker"))
            return R({"milestones": [m] if m else [], "cursor": ""})
        if path == "/live_data/batch":
            _, ld = kalshi_live()
            ids = (params or {}).get("milestone_ids") or []
            return R({"live_datas": [ld[i] for i in ([ids] if isinstance(ids, str) else ids) if i in ld]})
        return R({"multivariate_contracts": [], "series": [], "events": [], "cursor": ""})
    if "espn.com" in url:
        p = next((p for p in ESPN_PATH.values() if f"/{p}/" in url), None)
        return R({"events": espn_events(p) if p else []})
    if "github" in url:
        return R({}, 404)
    if "ntfy" in url:
        return R({"id": "x", "event": "message"})
    return R({"events": [], "markets": []})


def install(port=18800):
    """Patch requests (module functions and Session) so every outgoing call is answered by `fake`."""
    real = {"get": requests.get, "post": requests.post, "request": requests.request}

    def over(method, f):
        def go(url, *a, **k):
            r = fake(method, url, k.get("params") or (a[0] if a and method == "GET" else None), port)
            return r if r is not None else f(url, *a, **k)
        return go
    requests.get = over("GET", real["get"])
    requests.post = over("POST", real["post"])
    requests.put = over("PUT", real["post"])
    requests.delete = over("DELETE", real["post"])

    def req(method, url, **k):
        r = fake(method.upper(), url, k.get("params"), port, k.get("data"))
        return r if r is not None else real["request"](method, url, **k)
    requests.request = req

    class FakeSession:
        def __init__(s, *a, **k): s.headers = {}
        def get(s, url, **k): return requests.get(url, **k)
        def post(s, url, **k): return requests.post(url, **k)
        def request(s, m, url, **k): return requests.request(m, url, **k)
        def mount(s, *a): pass
        def close(s): pass
    requests.Session = FakeSession
