"""A fake internet for the dev environment (tests/dev_webapp.py): Kalshi, ESPN, GitHub, ntfy and the odds service
answered from memory, patched over `requests`. Same shapes as the fakes in macsmoke/run.py and test_webapp_pw.py.
Nothing here ever opens a real connection: any URL it does not know gets an empty answer, any non-GET Kalshi call
is refused, and any local address except the dev web app's own port is refused (so the real hub on 8765 and the
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


def event_ticker(series, a, b, day=None):
    return f"{series}-{(day or dt.date.today()).strftime('%y%b%d').upper()}{a}{b}"


def markets(hours=6):
    """Two markets (one per team) for every fake game, ending in a few hours."""
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
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


def espn_events(path):
    """Scoreboard events: the first game of each sport is live, the second is over, the rest haven't started."""
    series = next(s for s, p in ESPN_PATH.items() if p == path)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    evs = []
    for i, (a, an, b, bn, pa) in enumerate(GAMES[series]):
        state, name = (("in", "STATUS_IN_PROGRESS"), ("post", "STATUS_FINAL"))[i] if i < 2 else ("pre", "STATUS_SCHEDULED")
        start = now - dt.timedelta(hours=1 if i == 0 else 4) if i < 2 else now + dt.timedelta(hours=3 + i)
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


def fake(method, url, params=None, port=18800):
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
        if method != "GET":
            return R({"error": "dev environment: no orders"}, 403)          # never a trade
        if path.startswith("/markets"):
            mk = markets()
            if path.count("/") >= 2:
                m = next((x for x in mk if x["ticker"] == path.split("/")[2]), None)
                return R({"market": m} if m else {}, 200 if m else 404)
            st = (params or {}).get("series_ticker", "")
            return R({"markets": [m for m in mk if st and m["ticker"].startswith(st)], "cursor": ""})
        if path == "/portfolio/balance":
            return R({"balance": 21103})
        if path.startswith("/portfolio"):
            return R({"fills": [], "settlements": [], "positions": [], "market_positions": [], "event_positions": [], "orders": [], "cursor": ""})
        if path.startswith("/communications"):
            return R({"rfqs": [], "quotes": []})
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
        r = fake(method.upper(), url, k.get("params"), port)
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
