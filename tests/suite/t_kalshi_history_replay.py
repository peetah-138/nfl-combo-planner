# CHECK: group=engine
# tools/kalshi_history_replay.py (offline research on Kalshi's public settled markets), on a tiny synthetic cache with a
# known answer: the fee formula, one trade replayed by hand (exit at the bid, fee both ways, lag shifts the fill), the
# end-to-end report (hold and rule numbers, the 70/30 pick, the pass bar needing 2+ sports or 3+ good weeks, groups under
# 20 games hidden, aggregates only), lag resolving to a later candle, exclusion counts in the gates, spread/total never
# passing (hindsight line selection), the kickoff check, the measured spread widening, and the network rules (exact-regex
# public GET paths only, unsafe tickers refused, fetch lock, no auth header, one request a second, back-off on 429).
# No network is used: the client is given a fake opener.
import os, io, json, tempfile, importlib.util, contextlib, traceback, urllib.error
from pathlib import Path
REPO = os.environ.get("REPO") or os.path.abspath("../..")
spec = importlib.util.spec_from_file_location("K", os.path.join(REPO, "tools", "kalshi_history_replay.py"))
K = importlib.util.module_from_spec(spec); spec.loader.exec_module(K)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
TMP = Path(tempfile.mkdtemp())


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def fee():
    ok("fee 100 @ 50c = 175c", K.fee_cents(100, 0.5) == 175)
    ok("fee 100 @ 40c = 168c", K.fee_cents(100, 0.4) == 168)
    ok("fee rounds up", K.fee_cents(1, 0.5) == 2 and K.fee_cents(100, 0.99) == 7)


def S(rows):
    return K.Series([[t, b, a, b, a, a, 1] for t, b, a in rows])


def one_trade():
    # minute 0 entry ask .40; bid .38 until minute 9, .50 at minute 10, back to .40 at minute 11; settles NO
    rows = [(60 * i, 3800, 4000) for i in range(10)] + [(600, 5000, 5200), (660, 4000, 4200), (720, 4000, 4200)]
    s = S(rows)
    mk = {"settle": 0, "end_trade": 10 ** 9}
    r = K.trade_outcomes(s, mk, 0, K.RULES, (0, 60, 120), kick=10 ** 6)
    stake = 40.0 + 1.68
    ok("stake is cost plus entry fee", abs(r["stake"] - stake) < 1e-9, r["stake"])
    ok("hold of a loser loses the whole stake", abs(r["hold"] + stake) < 1e-9)
    want = 50.0 - 1.75 - stake                                   # sells at the bid .50, fee on the exit too
    ok("+5c exit at the bid, fee both ways", abs(r[(("plus", 5), 0)] - want) < 1e-9, r[(("plus", 5), 0)])
    ok("+10c never fires (bid never 10c over cost): holds", abs(r[(("plus", 10), 0)] + stake) < 1e-9)
    late = 40.0 - 1.68 - stake                                    # 60 s later the bid is .40
    ok("a 60 s lag fills at the later, worse bid", abs(r[(("plus", 5), 60)] - late) < 1e-9, r[(("plus", 5), 60)])
    win = K.trade_outcomes(s, {"settle": 10000, "end_trade": 10 ** 9}, 0, K.RULES, (0,), kick=10 ** 6)
    ok("hold of a winner pays 100 less stake", abs(win["hold"] - (100 - stake)) < 1e-9)
    tie = K.trade_outcomes(s, {"settle": 5000, "end_trade": 10 ** 9}, 0, K.RULES, (0,), kick=10 ** 6)
    ok("a tie settles at 50c", abs(tie["hold"] - (50 - stake)) < 1e-9)
    noask = K.trade_outcomes(S([(0, 3800, None)]), mk, 0, K.RULES, (0,), kick=10 ** 6)
    ok("no ask = no entry", noask is None)
    # T-minus rule: sell at kick-15m only when the bid is above cost
    s2 = S([(0, 3800, 4000), (3000, 4500, 4700), (3600, 3000, 3200)])
    r2 = K.trade_outcomes(s2, mk, 0, [("tminus", 15)], (0,), kick=3600 + 900 - 600)
    ok("T-15m uses the candle at that time, not a later one", abs(r2[(("tminus", 15), 0)] - (45 - K.fee_cents(100, .45) / 100 - stake)) < 1e-9,
       r2[(("tminus", 15), 0)])


def lag_later_candle():
    # candles are 5 minutes apart: a 60 s lag must fill at the NEXT candle (first ending at or after fire+60), not the firing one
    rows = [(0, 3800, 4000), (600, 5000, 5200), (900, 4200, 4400), (1200, 4200, 4400)]
    s = S(rows)
    mk = {"settle": 0, "end_trade": 10 ** 9}
    r = K.trade_outcomes(s, mk, 0, [("plus", 5)], (0, 60, 120), kick=10 ** 6)
    stake = 40.0 + 1.68
    ok("lag 0 fills at the firing candle's bid", abs(r[(("plus", 5), 0)] - (50 - 1.75 - stake)) < 1e-9)
    ok("lag 60 fills at the later candle's bid (.42), not the firing candle", abs(r[(("plus", 5), 60)] - (42 - K.fee_cents(100, .42) / 100 - stake)) < 1e-9, r[(("plus", 5), 60)])
    ok("the counters see that lag 60 hit a different candle", r["lag_fired"] == 1 and r["lag_diff"][60] == 1 and r["lag_diff"][120] == 1, (r["lag_fired"], r["lag_diff"]))
    # no candle at or after fire+lag: cannot fill, holds
    s2 = S([(0, 3800, 4000), (600, 5000, 5200)])
    r2 = K.trade_outcomes(s2, mk, 0, [("plus", 5)], (0, 60), kick=10 ** 6)
    ok("no candle at or after fire+lag: holds", abs(r2[(("plus", 5), 60)] + stake) < 1e-9)
    # a stale carried bid (last quoted 20 min ago) is not a fill and does not fire a rule
    s3 = K.Series([[0, 3800, 4000, 3800, 4000, 4000, 1], [60, 5000, 5200, 5000, 5200, 5200, 1], [1800, None, 4400, None, 4400, 4400, 1]])
    r3 = K.trade_outcomes(s3, mk, 0, [("plus", 5)], (0, 1800), kick=10 ** 6)
    ok("a bid older than 10 minutes cannot fill the lagged exit", abs(r3[(("plus", 5), 1800)] + stake) < 1e-9, r3[(("plus", 5), 1800)])
    # worse fill: entry at the candle's ask high, exit at its bid low
    s4 = K.Series([[0, 3800, 4000, 3800, 4200, 4000, 1], [60, 5000, 5200, 4800, 5200, 5200, 1]])
    r4 = K.trade_outcomes(s4, mk, 0, [("plus", 5)], (0,), kick=10 ** 6)
    sw = 42.0 + K.fee_cents(100, .42) / 100
    ok("worse fill enters at ask_high and exits at bid_low", abs(r4[("w", ("plus", 5))] - (48 - K.fee_cents(100, .48) / 100 - sw)) < 1e-9, r4[("w", ("plus", 5))])


def kick_rules():
    close = 1_760_000_000
    m = {"close": close, "occ": close - 3 * 3600}
    ok("occurrence time is the kickoff when close - occ is 1.5-6h", K.kick_of(m, "NFL") == (close - 3 * 3600, "occ"))
    ok("occ = close (outside the window) falls back to close - game length", K.kick_of({"close": close, "occ": close}, "NFL") == (close - 10800, "fallback"))
    ok("occ too early (>6h) falls back", K.kick_of({"close": close, "occ": close - 8 * 3600}, "NBA")[1] == "fallback")
    ok("no occ falls back", K.kick_of({"close": close, "occ": None}, "NBA") == (close - 9000, "fallback"))
    kick = 100000
    # volume steps up right after kickoff: the check is True; flat volume: False
    rows = [[t, 4000, 4200, 4000, 4200, 4200, (50 if t > kick else 5)] for t in range(kick - 3 * 3600, kick + 3 * 3600, 60)]
    ok("kick check true when the step-up is at kickoff", K.kick_check(K.Series(rows), kick) is True)
    flat = [[t, 4000, 4200, 4000, 4200, 4200, 5] for t in range(kick - 3 * 3600, kick + 3 * 3600, 60)]
    ok("kick check false on flat volume", K.kick_check(K.Series(flat), kick) is False)
    wrong = K.kick_check(K.Series(rows), kick + 2 * 3600)
    ok("kick check false when the estimate is 2h late", wrong is False, wrong)
    ok("kick check None with no volume", K.kick_check(K.Series([[t, 4000, 4200, 4000, 4200, 4200, 0] for t in range(kick - 3600, kick + 3600, 60)]), kick) is None)


def build_cache(root, sport, n, series, spread_live=True, extra=()):
    lists = list(extra)
    for i in range(n):
        close = 1_760_000_000 + i * 86400 + 7200
        tk = f"{series}-25OCT{i:03d}AAABBB-AAA"
        lists.append({"ticker": tk, "event": f"{series}-25OCT{i:03d}AAABBB", "series": series, "open": close - 10 ** 6,
                      "close": close, "occ": close, "exp": close, "result": "no", "settle": 0, "vol": 100.0, "route": "hist"})
        kick = close - int(K.GAME_HOURS[sport] * 3600)
        rows = []
        for t in range(close - 36 * 3600, close + 120, 300):
            if t < kick - 3 * 3600:
                b, a = 3800, 4000
            elif t < kick:
                b, a = 5000, 5200
            else:
                b, a = 4800, 5200                                   # in play: the book is twice as wide
            rows.append([t, b, a, b, a, a, 5])
        K.write_gz(root / "candles" / (tk + ".json.gz"), {"fields": K.CANDLE_FIELDS, "rows": rows})
    K.write_gz(root / "lists" / (series + ".json.gz"), lists)


def end_to_end():
    root = TMP / "cache"
    build_cache(root, "NFL", 80, "KXNFLGAME")
    build_cache(root, "NBA", 80, "KXNBAGAME")
    build_cache(root, "NHL", 10, "KXNHLGAME")                       # too small: must be hidden
    out = TMP / "out.json"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = K.main(["report", "--cache", str(root), "--sports", "NFL", "NBA", "NHL", "--kinds", "game", "--out", str(out),
                     "--boot", "200"])
    txt, d = buf.getvalue(), json.loads(out.read_text())
    ok("report runs", rc == 0)
    ok("data-quality gates print before results", txt.index("DATA QUALITY GATES") < txt.index("RESULTS"))
    ok("gates count games and span", d["gates"]["NFL"]["game_winner_games"] == 80 and d["gates"]["NFL"]["pct_with_candles"] == 100.0)
    g = {tuple(x["key"]): x for x in d["groups"]}
    a = g[("NFL", "game", "T-4h", "30-60c")]
    stake = 40.0 + 1.68
    gain = 100.0 * (50 - 1.75 - stake) / stake                      # +5c exit
    ok("hold net is -100c per $1 on all-losing entries", abs(a["cells"]["hold"]["net_c"] + 100) < 0.01, a["cells"]["hold"])
    ok("+5c net matches the hand number", abs(a["cells"]["+5c"]["net_c"] - gain) < 0.02, a["cells"]["+5c"])
    ok("edge over hold is rule minus hold", abs(a["cells"]["+5c"]["edge_c"] - (gain + 100)) < 0.02)
    ok("+10c holds (never fires), edge 0", abs(a["cells"]["+10c"]["edge_c"]) < 0.01)
    ok("fair filter: all entries under baseline, so no change from hold", abs(a["cells"]["fair"]["edge_c"]) < 0.01)
    ok("70/30 split picks a rule on the first 70%", a["oos"]["picked"] in ("+3c", "+5c", "T-1h", "T-15m") and a["oos"]["train_games"] == 56)
    ok("test set is the last 30%", a["oos"]["test_games"] == 24 and a["oos"]["test"]["edge_c"] > 100)
    ok("one sport alone cannot pass: no other sport, no 3 scored weeks", a["oos"]["pass"] is False, a["oos"]["stable"])
    allg = g[("ALL", "game", "T-4h", "30-60c")]
    ok("two sports positive (each range above 0) and survives 60 s lag: passes the bar", allg["oos"]["pass"] is True, allg["oos"])
    ok("per-sport stability scores the pooled test games (no re-split)", allg["oos"]["stable"]["sports_positive"] == 2, allg["oos"]["stable"])
    ok("pass needs >= 50 games", g[("NFL", "game", "T-4h", "30-60c")]["games"] >= K.MIN_PASS_GAMES)
    live = g[("NFL", "game", "live+30m", "30-60c")]
    ok("a live entry cannot use the pre-game exit rules: edge 0", abs(live["cells"]["+5c"]["edge_c"]) < 0.01 and abs(live["cells"]["T-1h"]["edge_c"]) < 0.01)
    ok("groups under 20 games are hidden", not any(k[0] == "NHL" for k in g))
    ok("output holds no tickers", "KXNFL" not in json.dumps(d) and "AAABBB" not in json.dumps(d) and "AAABBB" not in txt)
    pl = d["placeholders"]["NFL"]
    ok("measured spread pre-game .02, in play .04, widening 2.0",
       pl["median_spread_pre"] == 0.02 and pl["median_spread_live"] == 0.04 and pl["live_widen"] == 2.0, pl)
    ok("kickoff check present (flat volume in the fixture: 0 of 80)", pl["kick_check_share"] == 0.0 and pl["kick_check_games"] == 80, pl)
    ok("old weak kick sanity key is gone", "kick_sanity_live_volume_gt_pre" not in pl)
    gt = d["gates"]["NFL"]
    ok("gates show the occ/exp distributions and kick source counts", gt["close_minus_occ_h"]["median"] == 0.0 and gt["kick_source_markets"] == {"occ": 0, "fallback": 80}, gt)
    ok("lag-change share is reported", "60" in d["lag_changes_candle_pct"])
    ok("picked rule has a worse-fill number", a["oos"]["worse"] is not None)
    ok("pass reasons are recorded for a failing group", any("stable" in x for x in a["oos"]["pass_reasons"]), a["oos"]["pass_reasons"])


def network():
    sent = []

    class R:
        def __init__(s, body): s.body = body
        def read(s): return self_body
        def __enter__(s): return s
        def __exit__(s, *a): return False
    self_body = b'{"markets":[]}'
    calls = {"n": 0}

    def opener(req, timeout=0):
        sent.append(req)
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "slow down", {"Retry-After": "7"}, None)
        return R(None)
    naps, now = [], [0.0]
    c = K.Client(sleep=lambda s: (naps.append(s), now.__setitem__(0, now[0] + s)), clock=lambda: now[0], opener=opener)
    d = c.get("/historical/markets", {"series_ticker": "KXNFLGAME"})
    ok("429 is retried after backing off (Retry-After honoured)", d == {"markets": []} and c.backoffs == 1 and max(naps) >= 7, naps)
    hdr = {k.lower() for k in sent[0].headers}
    ok("no auth or key header is ever sent", not ({"authorization", "kalshi-access-key", "kalshi-access-signature",
                                                     "kalshi-access-timestamp", "cookie"} & hdr), hdr)
    ok("only GET", sent[0].get_method() == "GET")
    c.get("/markets", {"status": "settled"})
    n2, t2 = [], [0.0]
    c2 = K.Client(sleep=lambda x: (n2.append(x), t2.__setitem__(0, t2[0] + x)), clock=lambda: t2[0], opener=lambda r, timeout=0: R(None))
    c2.get("/markets"); c2.get("/markets")
    ok("requests are at least a second apart", len(n2) >= 1 and all(x >= 1.0 for x in n2), n2)
    for bad in ("/portfolio/orders", "/portfolio/balance", "/exchange/status", "/series", "/historical/orders",
                "/Portfolio/Balance", "/historical/markets/../../portfolio/orders/candlesticks",
                "/historical/markets/..%2Fportfolio/candlesticks", "/markets/", "/markets?x=1", "/series/KX/markets",
                "/series/KX/markets/KX-A/candlesticks/extra", "/historical/markets/A B/candlesticks"):
        try:
            c.get(bad)
            ok("refuses " + bad, False)
        except ValueError:
            ok("refuses " + bad, True)
    n = len(sent)
    try:
        c.get("/markets/portfolio/x")
    except ValueError:
        pass
    ok("a refused path sends nothing", len(sent) == n)


def unsafe_tickers():
    sent = []
    c = K.Client(sleep=lambda x: None, clock=lambda: 0.0, opener=lambda r, timeout=0: sent.append(r))
    for bad in ("../x", "..", "a/../b", "A/B", "A%2FB", "a b", "", None, "..."):
        try:
            K.candle_path({"ticker": bad, "series": "KXNFLGAME", "route": "hist"})
            ok("candle_path refuses ticker %r" % (bad,), False)
        except ValueError:
            ok("candle_path refuses ticker %r" % (bad,), True)
    try:
        K.candle_path({"ticker": "KXNFLGAME-X-A", "series": "../orders", "route": "live"})
        ok("candle_path refuses an unsafe series", False)
    except ValueError:
        ok("candle_path refuses an unsafe series", True)
    try:
        c.get("/historical/markets/../../portfolio/orders/candlesticks")
        ok("a '../' path is refused before any request", False)
    except ValueError:
        ok("a '../' path is refused before any request", not sent)
    ok("hist and live candle paths are on the allowlist",
       c.allowed(K.candle_path({"ticker": "KXNFLGAME-25OCT01AB-AB", "series": "KXNFLGAME", "route": "hist"}))
       and c.allowed(K.candle_path({"ticker": "KXNFLGAME-25OCT01AB-AB", "series": "KXNFLGAME", "route": "live"})))
    ok("allowlist covers the market-list and cutoff paths", all(c.allowed(x) for x in ("/historical/cutoff", "/historical/markets", "/markets")))


def cache_robustness():
    root = TMP / "robust"
    c = K.Client(sleep=lambda x: None, clock=lambda: 0.0, opener=lambda r, timeout=0: None)
    # list: an unexpected body raises and caches nothing
    c.get = lambda path, params=None, tries=6: {"oops": 1}
    try:
        K.list_series(c, root, "KXNFLGAME", log=lambda *a: None)
        ok("an unexpected list body raises", False)
    except RuntimeError:
        ok("an unexpected list body raises", True)
    ok("... and nothing is cached", not (root / "lists" / "KXNFLGAME.json.gz").exists())
    # list: a market outside the series prefix raises
    c.get = lambda path, params=None, tries=6: {"markets": [{"ticker": "KXOTHER-1-A", "event_ticker": "KXOTHER-1", "result": "yes"}]}
    try:
        K.list_series(c, root, "KXNFLGAME", log=lambda *a: None)
        ok("a market outside the series prefix raises", False)
    except RuntimeError:
        ok("a market outside the series prefix raises", True)
    # list: hist wins over live, clean terminal page is cached, unsettled markets skipped
    def pages(path, params=None, tries=6):
        mk = lambda sfx, res, ts: {"ticker": "KXNFLGAME-" + sfx, "event_ticker": "KXNFLGAME-" + sfx.split("-")[0], "result": res,
                                   "close_time": ts, "volume": 1}
        if path == "/historical/markets":
            return {"markets": [mk("E1-A", "yes", "2025-10-01T00:00:00Z")], "cursor": ""}
        return {"markets": [mk("E1-A", "no", "2025-10-01T00:00:00Z"), mk("E2-A", "yes", "2025-10-02T00:00:00Z"), mk("E3-A", "", "")], "cursor": None}
    c.get = pages
    rows = K.list_series(c, root, "KXNFLGAME", log=lambda *a: None)
    by = {r["ticker"]: r for r in rows}
    ok("hist is preferred over live; unsettled skipped", len(rows) == 2 and by["KXNFLGAME-E1-A"]["route"] == "hist" and by["KXNFLGAME-E1-A"]["result"] == "yes", rows)
    ok("a clean list is cached", (root / "lists" / "KXNFLGAME.json.gz").exists())
    # prep: filters before choose
    ok_m, cnt = K.prep([{"result": "yes", "close": 5, "settle": None, "event": "e", "vol": 1, "ticker": "t1"},
                        {"result": "scalar", "close": 5, "settle": 5000}, {"result": "void", "close": 5, "settle": 0},
                        {"result": "no", "close": None, "settle": 0}, {"result": "no", "close": 5, "settle": 0}])
    ok("settle is derived from the yes/no result when missing", ok_m[0]["settle"] == 10000 and len(ok_m) == 2, ok_m)
    ok("prep counts what it drops", cnt == {"n_listed": 5, "n_nonbinary": 2, "n_no_close": 1, "n_no_settle": 1}, cnt)
    # candle cache: a 404 is cached with a marker (old files still load) and retried only after 24 h
    m = {"ticker": "KXNFLGAME-E9-A", "series": "KXNFLGAME", "route": "hist", "close": 1_760_000_000, "open": 1_759_000_000}
    c.get = lambda path, params=None, tries=6: None
    K.fetch_candles(c, root, m, log=lambda *a: None)
    d = K.read_gz(root / "candles" / "KXNFLGAME-E9-A.json.gz")
    ok("a 404 is cached as empty rows with the marker", d["rows"] == [] and d["empty_404"] is True and "fields" in d, d)
    ok("a fresh 404 marker is not retried", K.candle_cached(root, m))
    ok("a 404 marker older than 24 h is retried", not K.candle_cached(root, m, now=d["empty_at"] + 25 * 3600))
    K.write_gz(root / "candles" / "KXNFLGAME-E8-A.json.gz", {"fields": K.CANDLE_FIELDS, "rows": []})
    ok("an empty file without the marker (old format / other cause) is not retried", K.candle_cached(root, dict(m, ticker="KXNFLGAME-E8-A"), now=10 ** 12))
    c.get = lambda path, params=None, tries=6: {"weird": 1}
    m2 = dict(m, ticker="KXNFLGAME-E7-A")
    ok("an unexpected candle body is not cached", K.fetch_candles(c, root, m2, log=lambda *a: None) is False and not (root / "candles" / "KXNFLGAME-E7-A.json.gz").exists())
    # lock
    lk = TMP / "lockdir"
    with K.FetchLock(lk):
        ok("the lock file exists during fetch", (lk / ".fetch.lock").exists())
        try:
            with K.FetchLock(lk):
                ok("a second fetch is refused while the first holds the lock", False)
        except RuntimeError:
            ok("a second fetch is refused while the first holds the lock", True)
    ok("the lock is released afterwards", not (lk / ".fetch.lock").exists())
    (lk / ".fetch.lock").write_text("999999999")
    with K.FetchLock(lk):
        ok("a stale lock from a dead pid is taken over", True)


def exclusions():
    root = TMP / "excl"
    base = 1_760_000_000
    extra = [
        {"ticker": "KXNFLGAME-25OCT900ZZZ-ZZZ", "event": "KXNFLGAME-25OCT900ZZZ", "series": "KXNFLGAME", "open": base - 10 ** 6, "close": base,
         "occ": None, "exp": None, "result": "scalar", "settle": 5000, "vol": 1.0, "route": "hist"},
        {"ticker": "KXNFLGAME-25OCT901ZZZ-ZZZ", "event": "KXNFLGAME-25OCT901ZZZ", "series": "KXNFLGAME", "open": base - 10 ** 6, "close": None,
         "occ": None, "exp": None, "result": "no", "settle": 0, "vol": 1.0, "route": "hist"},
        {"ticker": "KXNFLGAME-25OCT902ZZZ-ZZZ", "event": "KXNFLGAME-25OCT902ZZZ", "series": "KXNFLGAME", "open": base - 10 ** 6, "close": base,
         "occ": None, "exp": None, "result": "yes", "settle": None, "vol": 1.0, "route": "hist"},
    ]
    build_cache(root, "NFL", 25, "KXNFLGAME", extra=extra)
    out = TMP / "excl.json"
    with contextlib.redirect_stdout(io.StringIO()):
        K.main(["report", "--cache", str(root), "--sports", "NFL", "--kinds", "game", "--out", str(out), "--boot", "50"])
    gt = json.loads(out.read_text())["gates"]["NFL"]
    ok("gates count listed, void/scalar, no-close and missing-settle markets",
       (gt["n_listed"], gt["n_nonbinary"], gt["n_no_close"], gt["n_no_settle"]) == (28, 1, 1, 1), gt)
    ok("only admitted markets are chosen (25 + the derived-settle one, no candles for it)", gt["markets_chosen"] == 26 and gt["markets_with_candles"] == 25, gt)
    ok("game keys sharing is reported (no spread/total here: n/a)", gt["pct_spread_keys_also_winner"] is None)


def hindsight():
    root = TMP / "hind"
    for sp, win, spr in (("NFL", "KXNFLGAME", "KXNFLSPREAD"), ("NBA", "KXNBAGAME", "KXNBASPREAD")):
        build_cache(root, sp, 80, win)
        build_cache(root, sp, 80, spr)
    out = TMP / "hind.json"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        K.main(["report", "--cache", str(root), "--sports", "NFL", "NBA", "--kinds", "game", "spread", "--out", str(out), "--boot", "100",
                "--null", "20"])
    d = json.loads(out.read_text())
    g = {tuple(x["key"]): x for x in d["groups"]}
    ok("the winner pooled group passes", g[("ALL", "game", "T-4h", "30-60c")]["oos"]["pass"] is True)
    sp, al = g[("ALL", "spread", "T-4h", "30-60c")], g[("ALL", "all", "T-4h", "30-60c")]
    ok("the same pattern in spread markets does NOT pass: hindsight line selection", sp["oos"]["pass"] is False and K.HINDSIGHT in sp["oos"]["pass_reasons"], sp["oos"])
    ok("a group mixing winner and spread does not pass either", al["oos"]["pass"] is False and K.HINDSIGHT in al["oos"]["pass_reasons"], al["oos"])
    ok("no spread/total/all group passes anywhere", not any(x["oos"]["pass"] for x in d["groups"] if x["key"][1] != "game"))
    ok("spread groups are labelled selected-with-hindsight in the report", "[selected-with-hindsight]" in buf.getvalue())
    ok("spread game keys are shared with winner keys (100%)", d["gates"]["NFL"]["pct_spread_keys_also_winner"] == 100.0, d["gates"]["NFL"])
    ok("the permutation null ran and reports a share", d["null"]["chance_pass_share"] is not None and d["null"]["leaf_groups"] > 0, d["null"])
    ok("the permutation null is a share between 0 and 1", 0 <= d["null"]["chance_pass_share"] <= 1)
    ok("day-block clustering: every cluster is one sport-day", all(len(c[5]) >= 1 for c in K.clusters([{"day": ("NFL", 1), "t": 1, "game": ("NFL", "a"), "stake": 1, "hold": 0, "stake_w": 1, "hold_w": 0, "below": False, (K.RULES[0], 0): 0}], K.RULES[0], 0)))
    # jitter runs and prints
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        K.main(["report", "--cache", str(root), "--sports", "NFL", "NBA", "--kinds", "game", "--boot", "50", "--kick-jitter-min", "30"])
    ok("the kick-jitter rerun prints whether passes flip", "KICKOFF JITTER" in buf2.getvalue() and "base passes still pass" in buf2.getvalue(), buf2.getvalue()[-400:])


def parsing():
    c = {"end_period_ts": 100, "price": {"close": "0.4100"}, "yes_bid": {"close": "0.40", "low": "0.39"},
         "yes_ask": {"close_dollars": "0.42", "high_dollars": "0.43"}, "volume": 3}
    r = K.slim_candle(c)
    ok("candles parse in both field styles, dollars to ten-thousandths", r[:3] == [100, 4000, 4200] and r[5] == 4100 and r[6] == 3, r)
    ok("null prices are missing, not a crash", K.slim_candle({"end_period_ts": 1, "yes_bid": {"close": None}})[1] is None)
    s = K.Series([[1, 0, 10000, 0, 10000, None, 0], [2, 3000, 3300, 3000, 3300, 3100, 1]])
    ok("a void book (bid 0, ask 1.00) is no price", s.bid[0] is None and s.ask[0] is None and s.bid[1] == 3000)


for name, fn in (("fee", fee), ("one_trade", one_trade), ("lag_later_candle", lag_later_candle), ("kick_rules", kick_rules),
                 ("end_to_end", end_to_end), ("network", network), ("unsafe_tickers", unsafe_tickers),
                 ("cache_robustness", cache_robustness), ("exclusions", exclusions), ("hindsight", hindsight),
                 ("parsing", parsing)):
    section(name, fn)
