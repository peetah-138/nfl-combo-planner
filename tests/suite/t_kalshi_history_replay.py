# CHECK: group=engine
# tools/kalshi_history_replay.py (offline research on Kalshi's public settled markets), on a tiny synthetic cache with a
# known answer: the fee formula, one trade replayed by hand (exit at the bid, fee both ways, lag shifts the fill), the
# end-to-end report (hold and rule numbers, the 70/30 pick, the pass bar needing 2+ sports, groups under 20 games hidden,
# aggregates only), the measured spread widening, and the network rules (public GET paths only, no auth header, one
# request a second, back-off on 429). No network is used: the client is given a fake opener.
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


def build_cache(root, sport, n, series, spread_live=True):
    lists = []
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
    ok("one sport alone cannot pass: no other sport, no 10-game week", a["oos"]["pass"] is False, a["oos"]["stable"])
    allg = g[("ALL", "game", "T-4h", "30-60c")]
    ok("two sports positive and survives 60 s lag: passes the bar", allg["oos"]["pass"] is True, allg["oos"])
    live = g[("NFL", "game", "live+30m", "30-60c")]
    ok("a live entry cannot use the pre-game exit rules: edge 0", abs(live["cells"]["+5c"]["edge_c"]) < 0.01 and abs(live["cells"]["T-1h"]["edge_c"]) < 0.01)
    ok("groups under 20 games are hidden", not any(k[0] == "NHL" for k in g))
    ok("output holds no tickers", "KXNFL" not in json.dumps(d) and "AAABBB" not in json.dumps(d) and "AAABBB" not in txt)
    pl = d["placeholders"]["NFL"]
    ok("measured spread pre-game .02, in play .04, widening 2.0",
       pl["median_spread_pre"] == 0.02 and pl["median_spread_live"] == 0.04 and pl["live_widen"] == 2.0, pl)
    ok("kickoff sanity line present", pl["kick_sanity_live_volume_gt_pre"] is not None)


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
    for bad in ("/portfolio/orders", "/portfolio/balance", "/exchange/status", "/series", "/historical/orders"):
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


def parsing():
    c = {"end_period_ts": 100, "price": {"close": "0.4100"}, "yes_bid": {"close": "0.40", "low": "0.39"},
         "yes_ask": {"close_dollars": "0.42", "high_dollars": "0.43"}, "volume": 3}
    r = K.slim_candle(c)
    ok("candles parse in both field styles, dollars to ten-thousandths", r[:3] == [100, 4000, 4200] and r[5] == 4100 and r[6] == 3, r)
    ok("null prices are missing, not a crash", K.slim_candle({"end_period_ts": 1, "yes_bid": {"close": None}})[1] is None)
    s = K.Series([[1, 0, 10000, 0, 10000, None, 0], [2, 3000, 3300, 3000, 3300, 3100, 1]])
    ok("a void book (bid 0, ask 1.00) is no price", s.bid[0] is None and s.ask[0] is None and s.bid[1] == 3000)


for name, fn in (("fee", fee), ("one_trade", one_trade), ("end_to_end", end_to_end), ("network", network), ("parsing", parsing)):
    section(name, fn)
