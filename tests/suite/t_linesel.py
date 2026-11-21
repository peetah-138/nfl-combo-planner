# Spreads and totals, part B (issue #117): closing-line value per strike, fillable size after fees, a learned minimum
# edge per league (start at today's bar, small steps on clear evidence, borrowing league -> sport -> all, never looser),
# and the Build page's recommendations: only strikes worth buying, with a likely route to profit, ranked by expected
# dollars. Recommend-only: nothing here buys or sells. Fakes only: no network, temp files, a temp history.
import os, time, tempfile, importlib.util, inspect, re, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.leg_score = lambda l: None
E.SMART_CACHE.update(at=time.time() + 1e6, d={})


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)


def safe(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


class NoNet:
    RequestException = E.requests.RequestException

    def __getattr__(self, name):
        def call(*a, **k):
            raise E.requests.RequestException("no network in this test")
        return call


E.requests = NoNet()
now = time.time()
START = E.LINE_MIN_EDGE
fee = E.single_fee


def bar_file(d):
    E.save_json(E._le_file(), d)
    E.LE_CACHE["at"] = 0.0


# ---------------------------------------------------------------- 3. the learned minimum edge
def t_min_edge():
    bar_file({})
    me = E.line_min_edge("nba", "spread")
    ok("min edge: starts at today's bar (LINE_MIN_EDGE) with nothing learned", me["v"] == START and me["src"] == "start")
    bar_file({"nba:spread": {"v": 0.05, "games": 40}})
    ok("min edge: a league with 30+ games of its own uses its own bar", E.line_min_edge("nba", "spread")["v"] == 0.05
       and E.line_min_edge("nba", "spread")["src"] == "own")
    ok("min edge: kinds are apart (totals keep the start)", E.line_min_edge("nba", "total")["v"] == START)
    bar_file({"nba:spread": {"v": 0.06, "games": 12}, "basketball:spread": {"v": 0.055, "games": 80}})
    me = E.line_min_edge("nba", "spread")
    ok("min edge: a league short of games borrows its sport's (basketball for the NBA)", me["v"] == 0.055 and me["src"] == "sport")
    ok("min edge: college basketball borrows basketball too, not the NBA's own", E.line_min_edge("ncaamb", "spread")["v"] == 0.055)
    bar_file({"all:total": {"v": 0.045, "games": 90}})
    ok("min edge: then everyone's", E.line_min_edge("nhl", "total")["v"] == 0.045 and E.line_min_edge("nhl", "total")["src"] == "all")
    bar_file({"nba:spread": {"v": 0.01, "games": 400}, "basketball:spread": {"v": -1, "games": 400}})
    ok("min edge: never under today's bar, whatever the file says (only ever stricter)", E.line_min_edge("nba", "spread")["v"] == START
       and E.line_min_edge("ncaamb", "spread")["v"] == START)
    bar_file({"nba:spread": {"v": 0.9, "games": 400}})
    ok("min edge: capped at LINE_EDGE['max']", E.line_min_edge("nba", "spread")["v"] == E.LINE_EDGE["max"])
    bar_file({"nba:spread": {"v": "junk", "games": "x"}})
    ok("min edge: a broken file means the start, never an error", E.line_min_edge("nba", "spread")["v"] == START)
    bar_file({})


safe("min edge", t_min_edge)


# ---------------------------------------------------------------- the weekly review (line_edge_tune)
def settle(rows):
    """rows: (event, edge after fee, won) -> settled line_fairs rows priced at 45c."""
    E._line_fair_table()
    E.store_x("delete from line_fairs")
    p = 0.45
    for i, (ev, edge, won) in enumerate(rows):
        fair = round(p + fee(p) + edge, 4)
        E.store_x("insert into line_fairs values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (f"KXNBASPREAD-{ev}-T{i}", now - 86400, "nba", "nba", "spread", 3.5, "at the line", fair, None, None,
                   "old", p, now - 80000, "yes" if won else "no"))
    E.LINE_STATS.update(v=None, at=0)


def t_tune():
    # 30 games of good strikes (edge 7c, half win) and 12 games of strikes just over the bar (4.2c) that all lost
    good = [(f"G{i}", 0.07, i % 2 == 0) for i in range(30)]
    band = [(f"B{i}", 0.042, False) for i in range(12)]
    settle(good + band)
    bar_file({})
    moved = E.line_edge_tune(force=True, now=now)
    d = E.load_json(E._le_file(), {})
    ok("tune: the strikes just over the bar lost clearly -> the bar goes up one step (4c -> 4.5c)",
       abs(d["nba:spread"]["v"] - (START + E.LINE_EDGE["step"])) < 1e-9 and any("nba:spread" in m for m in moved))
    ok("tune: the change says why, in words", "lost" in (d["nba:spread"].get("why") or ""))
    ok("tune: sport and everyone's levels learn from the same games", "basketball:spread" in d and "all:spread" in d)
    ok("tune: once a week (a second call without force does nothing)", E.line_edge_tune(now=now + 3600) == [])
    ok("tune: the league now uses its own bar", E.line_min_edge("nba", "spread")["v"] == round(START + E.LINE_EDGE["step"], 4))
    # one step at most, even with a lot of evidence
    bar_file({})
    settle(good + band + [(f"C{i}", 0.047, False) for i in range(12)])
    E.line_edge_tune(force=True, now=now)
    ok("tune: one small step a week at most", abs(E.load_json(E._le_file(), {})["nba:spread"]["v"] - (START + E.LINE_EDGE["step"])) < 1e-9)
    # not enough games: no move
    bar_file({})
    settle([(f"G{i}", 0.07, i % 2 == 0) for i in range(10)] + [(f"B{i}", 0.042, False) for i in range(12)])
    E.line_edge_tune(force=True, now=now)
    ok("tune: under 30 games at the bar it never moves", E.load_json(E._le_file(), {})["nba:spread"]["v"] == START)
    # a small band (under 10 games) is not clear evidence
    bar_file({})
    settle(good + [(f"B{i}", 0.042, False) for i in range(5)])
    E.line_edge_tune(force=True, now=now)
    ok("tune: a band of under 10 games is not clear evidence", E.load_json(E._le_file(), {})["nba:spread"]["v"] == START)
    # mixed results in the band: no clear gain -> it stays (smallest change)
    bar_file({})
    settle(good + [(f"B{i}", 0.042, i % 2 == 0) for i in range(12)])
    E.line_edge_tune(force=True, now=now)
    ok("tune: no clear evidence -> it stays where it is", E.load_json(E._le_file(), {})["nba:spread"]["v"] == START)
    # down again (never under the start) when the strikes it left out made money
    bar_file({"nba:spread": {"v": 0.05, "games": 40}})
    settle(good + [(f"B{i}", 0.047, True) for i in range(12)])
    E.line_edge_tune(force=True, now=now)
    ok("tune: comes back down a step when the strikes it left out won clearly",
       abs(E.load_json(E._le_file(), {})["nba:spread"]["v"] - 0.045) < 1e-9)
    bar_file({})
    settle(good + [(f"B{i}", 0.041, True) for i in range(30)])
    E.line_edge_tune(force=True, now=now)
    ok("tune: at the start it never goes lower, however well the strikes did",
       E.load_json(E._le_file(), {})["nba:spread"]["v"] >= START)
    settle([(f"L{i}", 0.02, True) for i in range(60)])
    ok("tune: strikes under today's bar are never in the review at all", E._line_edge_rows(now) == [])
    bar_file({})
    E.store_x("delete from line_fairs")
    E.LINE_STATS.update(v=None, at=0)


safe("tune", t_tune)


# ---------------------------------------------------------------- 1. closing-line value per strike
def t_clv():
    E._line_clv_table()
    E.store_x("delete from line_clv")
    E.CLV_STATE.update(at=0, stats=None)
    kick = now + 3600
    x = {"ticker": "KXNBASPREAD-26NOV21AAABBB-AAA3", "code": "nba", "league": "nba", "kind": "spread",
         "bucket": "at the line", "line": 3.5, "p": 0.45, "fair": 0.52, "kick": kick}
    E.note_line_rec(x, now=now)
    E.note_line_rec(dict(x, p=0.40), now=now + 10)
    r = E.store_rows("select * from line_clv")
    ok("clv: a recommendation is remembered once per strike, at the first price", len(r) == 1 and r[0]["price"] == 0.45)
    E.line_clv_seen(x["ticker"], 0.48, kick, now=now + 600)
    E.line_clv_seen(x["ticker"], 0.49, kick, now=now + 1200)
    E.line_clv_seen(x["ticker"], 0.70, kick, now=kick + 60)
    r = E.store_rows("select * from line_clv")[0]
    ok("clv: the last price before the start is the close (none after it)", r["close"] == 0.49)
    E.note_line_rec(dict(x, ticker="KXNBASPREAD-OLD-1", kick=now - 10), now=now)
    ok("clv: nothing is recorded for a game already under way", not E.store_rows("select 1 from line_clv where ticker='KXNBASPREAD-OLD-1'"))
    E.note_line_rec(dict(x, ticker="KXNBASPREAD-B-1"), "buy", price=0.46, now=now)
    ok("clv: a buy is kept apart from the recommendation", E.store_rows("select src from line_clv where ticker='KXNBASPREAD-B-1'")[0]["src"] == "buy")
    E.note_line_rec({"ticker": None}, now=now)
    E.note_line_rec({"ticker": "X", "kick": "junk"}, now=now)
    ok("clv: odd input never raises", True)
    # 40 settled games whose recommended price closed 2c lower (we paid more than the close): that kind is stopped
    E.store_x("delete from line_clv")

    def games(lg, sport, bucket, n, delta, tag):
        for i in range(n):
            E.store_x("insert into line_clv values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (f"KXNBASPREAD-{tag}{i}-T", "rec", now - 90000, sport, lg, "spread", bucket, 3.5, 0.45, 0.52,
                       now - 86400, round(0.45 + delta + (0.002 if i % 2 else -0.002), 4), now - 86400 - 600))
    games("nba", "nba", "far above", 40, -0.02, "A")
    E.CLV_STATE.update(stats=None)
    st = E.line_clv_stats(now)
    ok("clv: stats per league, kind and band (close minus price)", abs(st[("nba", "spread", "far above")]["mean"] + 0.02) < 1e-6
       and st[("nba", "spread", "far above")]["games"] == 40)
    ok("clv: a kind of strike that keeps losing to the close is stopped", bool(E.line_clv_block("nba", "spread", "far above", now)))
    ok("clv: other bands are not", E.line_clv_block("nba", "spread", "at the line", now) is None)
    games("ncaamb", "ncaamb", "far above", 5, 0.03, "C")
    E.CLV_STATE.update(stats=None)
    ok("clv: a league short of games borrows its sport's record, only to stop (stricter)",
       bool(E.line_clv_block("ncaamb", "spread", "far above", now)))
    games("ncaawb", "ncaawb", "far above", 60, 0.03, "W")
    E.CLV_STATE.update(stats=None)
    ok("clv: a league whose own 30+ games beat the close is never stopped by borrowing",
       E.line_clv_block("ncaawb", "spread", "far above", now) is None)
    E.store_x("delete from line_clv")
    games("nba", "nba", "far above", 40, -0.02, "A")
    E.store_x("update line_clv set close_ts = kick - 4 * 3600")
    E.CLV_STATE.update(stats=None)
    ok("clv: a 'close' read hours before the start doesn't count", E.line_clv_block("nba", "spread", "far above", now) is None)
    E.store_x("delete from line_clv")
    E.CLV_STATE.update(stats=None, at=0)


safe("clv", t_clv)


# ---------------------------------------------------------------- 2. fillable size after fees
def t_fill():
    asks = [(0.45, 10), (0.46, 20), (0.50, 500)]
    f = E.line_fill("T", 0.53, 0.04, 1000, asks=asks)
    ok("fill: only the levels inside the edge (45c and 46c with a 53% fair and a 4c bar), never 50c",
       f["n"] == 30 and f["depth"] == 30 and f["capped"] == "depth")
    cost = 10 * 0.45 + 20 * 0.46
    feec = -(-round((10 * 0.07 * 0.45 * 0.55 + 20 * 0.07 * 0.46 * 0.54) * 100, 6) // 1) / 100
    ok("fill: the cost is the prices plus Kalshi's fee rounded up to the cent", abs(f["cost"] - round(cost + feec, 2)) < 1e-9)
    ok("fill: expected profit = contracts x fair - cost (after fees)", abs(f["exp"] - round(30 * 0.53 - (cost + feec), 2)) < 1e-9)
    ok("fill: every contract keeps the edge after the fee", 0.53 - f["per"] >= 0.04 - 1e-9)
    g = E.line_fill("T", 0.53, 0.04, 5.0, asks=asks)
    ok("fill: never more than the stake", g["cost"] <= 5.0 and g["n"] >= 1 and g["capped"] == "stake")
    h = E.line_fill("T", 0.50, 0.04, 100, asks=asks)
    ok("fill: nothing inside the edge = 0 contracts (not recommended)", h["n"] == 0 and h["exp"] == 0)
    ok("fill: an empty book = 0 contracts", E.line_fill("T", 0.6, 0.04, 100, asks=[])["n"] == 0)
    E.BOOK_LADDER.clear()
    E.BOOK_DEPTH.clear()
    ok("fill: an unreadable book = None (nothing recommended: fails closed)", E.line_fill("NOBOOK", 0.6, 0.04, 100) is None)
    ok("fill: the ladder reads both order book shapes", E._ask_ladder({"orderbook_fp": {"no_dollars": [["0.50", "12.5"], ["0.55", "3"]]}})
       == [(0.45, 3.0), (0.5, 12.5)] and E._ask_ladder({"orderbook": {"no": [[55, 3]]}}) == [(0.45, 3)]
       and E._ask_ladder({"junk": 1}) == [] and E._ask_ladder(None) == [])
    one = E.line_fill("T", 0.5, 0.04, 1000, asks=[(0.45, 1)])
    ok("fill: a single contract whose rounded fee eats the edge is dropped", one["n"] == 0)


safe("fill", t_fill)


# ---------------------------------------------------------------- the Build page's recommendations
def t_recommend():
    E._manual_base = lambda: 300.0
    bar_file({})
    kick = now + 4 * 3600
    base = {"code": "nba", "league": "nba", "kind": "spread", "bucket": "at the line", "line": 3.5, "kick": kick,
            "min_edge": START, "src": "model", "game": "Lakers at Celtics", "start": None}
    C = [dict(base, ticker="KXNBASPREAD-26NOV21LALBOS-BOS3", event="KXNBASPREAD-26NOV21LALBOS", pick="Celtics win by 3.5+", p=0.45, fair=0.53,
              edge=round(0.53 - 0.45 - fee(0.45), 4)),
         dict(base, ticker="KXNBASPREAD-26NOV21LALBOS-BOS6", event="KXNBASPREAD-26NOV21LALBOS", pick="Celtics win by 6.5+", p=0.30, fair=0.37,
              edge=round(0.37 - 0.30 - fee(0.30), 4)),
         dict(base, ticker="KXNBATOTAL-26NOV21LALBOS-220", event="KXNBATOTAL-26NOV21LALBOS", kind="total", pick="Over 220.5", p=0.40, fair=0.48,
              edge=round(0.48 - 0.40 - fee(0.40), 4)),
         dict(base, ticker="KXNBATOTAL-26NOV21LALBOS-230", event="KXNBATOTAL-26NOV21LALBOS", kind="total", pick="Over 230.5", p=0.20, fair=0.27,
              edge=round(0.27 - 0.20 - fee(0.20), 4))]
    E.line_candidates = lambda code, everything=False: [dict(x) for x in C]
    E.LINE_LAST["nba"] = {"n": 40, "at": now}
    t = time.time()
    E.BOOK_LADDER.update({C[0]["ticker"]: (t, [(0.45, 400)]), C[1]["ticker"]: (t, [(0.30, 300)]),
                          C[2]["ticker"]: (t, [(0.47, 900)]),       # moved: nothing inside the edge any more
                          C[3]["ticker"]: (t, [(0.20, 600)])})
    sims = {C[0]["ticker"]: {"route": "sell", "ev": 0.6, "hold_profit": 0.5, "p_exit": 0.58, "win": 0.53, "exit_mins": 40},
            C[1]["ticker"]: {"route": "hold", "ev": 0.9, "hold_profit": 0.9, "p_exit": 0.2, "win": 0.45, "exit_mins": None},
            C[2]["ticker"]: {"route": "sell", "ev": 1.0, "hold_profit": 1.0, "p_exit": 0.6, "win": 0.48, "exit_mins": 30},
            C[3]["ticker"]: {"route": "none", "ev": 0.8, "hold_profit": 0.8, "p_exit": 0.1, "win": 0.27, "exit_mins": None}}
    real_sim = E._sb_sim
    E._sb_sim = lambda c, now=None: sims.get(c["legs"][0]["ticker"])
    recs, info = E.line_recommend("nba", now=now)
    tk = [r["ticker"] for r in recs]
    ok("recommend: a strike with edge but no route to profit (no likely cash-out, long shot) is not recommended", C[3]["ticker"] not in tk)
    ok("recommend: a strike the book no longer fills inside the edge is not recommended", C[2]["ticker"] not in tk)
    ok("recommend: strikes with a route (cash out early, or a hold with a fair win chance) are", set(tk) == {C[0]["ticker"], C[1]["ticker"]})
    ok("recommend: ranked by expected dollars", [r["exp"] for r in recs] == sorted([r["exp"] for r in recs], reverse=True))
    ok("recommend: never an edge under its bar, never a negative edge", all(r["edge"] >= r["min_edge"] - 1e-9 and r["edge"] > 0 for r in recs))
    ok("recommend: each card has the stake, contracts, expected dollars, route and cash-out chance",
       all(r["stake"] > 0 and r["n"] >= 1 and r["exp"] >= E.SB_EV_MIN and r["route"] in ("sell", "hold") and "p_exit" in r for r in recs))
    ok("recommend: the stake never buys more than fills inside the edge", all(r["n"] <= r["depth"] for r in recs))
    ok("recommend: the empty state knows how many were checked and why they were left out",
       info["priced"] == 40 and info["skipped"].get("route") == 1 and info["skipped"].get("depth") == 1)
    ok("recommend: what it recommends is remembered for closing-line value",
       {r["ticker"] for r in E.store_rows("select ticker from line_clv where src='rec'")} >= set(tk))
    # a small expected profit (under SB_EV_MIN dollars at the size that fills) is left out
    E.BOOK_LADDER[C[0]["ticker"]] = (time.time(), [(0.45, 2)])
    E.BOOK_LADDER[C[1]["ticker"]] = (time.time(), [(0.30, 1)])
    recs2, info2 = E.line_recommend("nba", now=now)
    ok("recommend: under SB_EV_MIN expected dollars at the fillable size = left out", recs2 == [] and info2["skipped"].get("small", 0) >= 1)
    # the book can't be read: nothing (fails closed)
    E.BOOK_LADDER.clear()
    E.BOOK_DEPTH.clear()
    recs3, info3 = E.line_recommend("nba", now=now)
    ok("recommend: an unreadable order book = nothing recommended", recs3 == [] and info3["skipped"].get("book") == 4)
    # nothing at all to check
    E.line_candidates = lambda code, everything=False: []
    E.LINE_LAST["nba"] = {"n": 0, "at": now}
    ok("recommend: no markets = nothing and 0 checked", E.line_recommend("nba", now=now) == ([], {"priced": 0, "skipped": {}}))

    def boom(code, everything=False):
        raise ValueError("bad feed")
    E.line_candidates = boom
    ok("recommend: a broken feed never raises", E.line_recommend("nba", now=now)[0] == [])
    # the real simulator takes the recommendation's candidate shape
    E._sb_sim = real_sim
    sim = E._sb_sim({"kind": "line", "code": "nba", "id": "line:X", "kick": kick,
                     "legs": [{"ticker": C[0]["ticker"], "event": C[0]["event"], "fair": 0.53, "p": 0.45, "pick": "x"}]}, now)
    ok("recommend: the real exit simulator (smart sell's exit policy) scores a strike", isinstance(sim, dict) and sim.get("route") in ("sell", "hold", "none"))
    src = inspect.getsource(E.line_recommend) + inspect.getsource(E._line_rec_one) + inspect.getsource(E.line_fill)
    ok("recommend-only: nothing that recommends places an order",
       not re.search(r"buy_single|kalshi_send|accept_offer|post_sell|panel_exec|_buy_panel_bet|sell_single", src))


safe("recommend", t_recommend)


# ---------------------------------------------------------------- the panel: only ever stricter
def t_panel():
    bar_file({})
    leg = {"ticker": "KXNBASPREAD-26NOV21LALBOS-BOS3", "p": 0.45, "fair": 0.53, "event": "KXNBASPREAD-26NOV21LALBOS"}
    c = {"kind": "line", "code": "nba", "legs": [leg], "line_kind": "spread", "line_lg": "nba", "bucket": "at the line",
         "chance": 0.53, "price": 0.45, "ret": 0.1, "fill_cap": None}
    E.news_gap = lambda x, ask=None: None
    ok("panel: a spread at the usual bar still qualifies (nothing learned yet)", E._qualifies(c))
    bar_file({"nba:spread": {"v": 0.07, "games": 50}})
    ok("panel: a learned higher bar leaves it out", not E._qualifies(c))
    bar_file({})
    ok("panel: under $2 fillable inside the edge = left out", not E._qualifies(dict(c, fill_cap=1.5)))
    ok("panel: book unread (no cap) = today's rule", E._qualifies(dict(c, fill_cap=None)))
    ok("panel: the stake never goes over what fills inside the edge", E._size(dict(c, fill_cap=3.1), 1000) <= 3.1
       and E._size(dict(c, fill_cap=None), 1000) == E._size(dict(c), 1000))
    ok("panel: the raw 6-point bar still applies first", not E._qualifies(dict(c, legs=[dict(leg, fair=0.50)])))
    src = inspect.getsource(E.panel_collect)
    ok("panel: line candidates carry their league, band and fillable dollars", "fill_cap=" in src and "line_lg=" in src)


safe("panel", t_panel)


# ---------------------------------------------------------------- review fixes
def t_review():
    # a league's own raised bar never falls back to a looser borrowed one when fewer games sit at the new bar
    bar_file({"nba:spread": {"v": 0.06, "games": 3, "games_all": 45}, "basketball:spread": {"v": 0.045, "games": 90}})
    ok("review: a league's own stricter bar holds once it has 30+ games in all", E.line_min_edge("nba", "spread")["v"] == 0.06)
    E.save_json(E._le_file(), {"_at": "junk", "nba:spread": "junk"})
    E.LE_CACHE["at"] = 0.0
    ok("review: a broken bar file never raises in the weekly review", isinstance(E.line_edge_tune(force=False, now=now), list))
    bar_file({})
    f = E.line_fill("T", 0.53, 0.04, 100, asks=[(0.44, 0.5), (0.45, 10)])
    ok("review: the price shown is the one it can buy (a fractional top level is skipped)", f["best"] == 0.45 and f["n"] == 10)
    # the order books are read side by side, on a time budget
    import threading as _th
    slow = _th.Event()
    real = E.book_asks
    E.book_asks = lambda t, max_age=60: slow.wait(5)
    E.BOOK_LADDER.clear()
    t0 = time.time()
    got = E.books_now(["A", "B", "C", "D"], budget=0.5)
    ok("review: slow order books never hold the page past the budget (late = not recommended)",
       time.time() - t0 < 1.5 and got == {"A": None, "B": None, "C": None, "D": None})
    slow.set()
    E.book_asks = real
    E.BOOK_LADDER["Z"] = (time.time(), [(0.4, 3)])
    ok("review: a book read in the last minute is used as is", E.books_now(["Z"], budget=0)["Z"] == [(0.4, 3)])
    js = open(os.path.join(os.environ.get("REPO", ".."), "watcher", "spa", "build_sections.js")).read()
    ok("review: the ticker reaches the tap through a data attribute, not a quoted JS string",
       "lineFromBoard(this.dataset.t,this)" in js and "lineFromBoard('" not in js)


safe("review", t_review)


# ---------------------------------------------------------------- wiring
def t_wiring():
    w = open(os.path.join(os.environ.get("REPO", ".."), "watcher", "combo_watcher.py")).read()
    ok("wiring: Build shows recommendations (line_recommend), never every strike (everything=True)",
       "A.line_recommend(" in w and "line_candidates(c, everything=True)" not in w)
    ok("wiring: the weekly review runs with the other weekly tuning", "H.line_edge_tune()" in w)
    ab = w[w.index("    def api_build("):]
    ok("wiring: Build's spreads/totals are worked out off the app lock (taps never wait on order books)",
       ab.index("lines_kick(lg") < ab.index("with alock:") and "A.line_recommend(" not in ab[:ab.index("def ", 10)])
    js = open(os.path.join(os.environ.get("REPO", ".."), "watcher", "spa", "build_sections.js")).read()
    ok("wiring: the empty state says so plainly", "No spread or total clears your bar right now." in js)
    ok("wiring: the old table of every strike is gone", "lrow2" not in js)
    src = inspect.getsource(E.single_buy_quote)
    ok("wiring: the buy sheet's green Buy for a spread/total uses the learned bar (never looser)", "line_min_edge(" in src and "max(need" in src)
    ok("wiring: analytics shows each league's bar and the close", "line_sel_summary()" in inspect.getsource(E.analytics))
    bar_file({"nba:spread": {"v": 0.05, "games": 40, "why": "strikes just over 4.0¢ lost $12.00 ($1 each) over 12 games"}})
    s = E.line_sel_summary(now)
    ok("summary: a league's bar, where it came from and why it moved", any(r["lg"] == "nba" and r["kind"] == "spread" and r["bar"] == 0.05
                                                                          and r["src"] == "own" and "lost" in r["why"] for r in s))
    bar_file({})


safe("wiring", t_wiring)
