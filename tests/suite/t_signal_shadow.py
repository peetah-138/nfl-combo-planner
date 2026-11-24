# CHECK: group=engine
# The early-exit test's shadow recorders (signal_shadow in the engine): sharp-book probability beside Kalshi's bid/ask,
# sibling-market bids and game state, written to NEW append-only tables from what the panel pass already holds.
#  A  rows land in the three tables, throttled (about every 60 s / 2 min), with no fetch (requests is never touched)
#  B  every failure is swallowed (no history, a broken insert, a score feed that raises, junk sides): returns 0, no raise
#  C  the flag turns it off, and the trading inputs (the games and lines it was handed) are byte-for-byte unchanged
#  D  bounded: pruning drops old rows and caps the table
#  E  nothing decides from these tables: the engine and watcher never mention them outside the recorder itself
import os, re, copy, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
REPO = os.environ.get("REPO") or os.path.abspath("../..")


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def games():
    return {"KXNBAGAME-26NOV23LALBOS": [
        {"ticker": "KXNBAGAME-26NOV23LALBOS-LAL", "p": 0.55, "bid": 0.53, "fair": 0.58, "src": "pinnacle", "live": True, "line_live": False},
        {"ticker": "KXNBAGAME-26NOV23LALBOS-BOS", "p": 0.47, "bid": 0.45, "fair": 0.42, "src": "pinnacle", "live": True},
        {"ticker": "KXNBAGAME-26NOV23LALBOS-TIE", "p": 0.01, "bid": None, "fair": 0.0, "tie": True}]}


def lines():
    return [{"ticker": "KXNBASPREAD-26NOV23LALBOS-LAL5", "event": "KXNBASPREAD-26NOV23LALBOS", "p": 0.5, "bid": 0.48}]


def count(t):
    return E.store_rows(f"select count(*) n from {t}")[0]["n"]


def a_rows():
    E.leg_score = lambda l: {"state": "in", "me": 55, "opp": 50, "frac": 0.4, "situation": {"possession": True, "down": 2, "distance": 7}}
    class NoNet:
        def __getattr__(self, k):
            raise AssertionError("a request was made: " + k)
    real, E.requests = E.requests, NoNet()
    try:
        E.SIG["seen"].clear()
        n = E.signal_shadow("nba", games(), lines(), now=1000.0)
    finally:
        E.requests = real
    ok("A one call writes sharp (2), related (3 siblings) and state (2) rows, no request made", n == 7, n)
    r = E.store_rows("select fair_book, bid, ask, src from sig_sharp where fair_book=0.58")
    ok("A (sharp) fair 0.58, bid 0.53, ask 0.55", r == [{"fair_book": 0.58, "bid": 0.53, "ask": 0.55, "src": "pinnacle"}], r)
    s = E.store_rows("select me, opp, frac, poss, down, dist, pts from sig_state limit 1")
    ok("A state rows carry score, clock share left, possession, down, distance, total points", s == [{"me": 55, "opp": 50, "frac": 0.4, "poss": 1, "down": 2, "dist": 7, "pts": 105}], s)
    ok("A related rows pair the game's win bids with its spread bid", {x["kind"] for x in E.store_rows("select kind from sig_related")} == {"win", "spread"})
    ok("A throttled: the same pass 10 s later writes nothing", E.signal_shadow("nba", games(), lines(), now=1010.0) == 0)
    ok("A and again after a minute (sharp/state) but not related (2 min)", E.signal_shadow("nba", games(), lines(), now=1070.0) == 4)
    ok("A the tie side is never recorded", count("sig_sharp") == 4 and not E.store_rows("select 1 from sig_sharp where ticker like '%TIE'"))


def b_swallow():
    E.SIG["seen"].clear()
    db = E.STORE["db"]
    E.STORE["db"] = None
    ok("B no history open: 0, no raise", E.signal_shadow("nba", games(), lines(), now=2000.0) == 0)
    E.STORE["db"] = db
    old = E._sig_insert
    def boom(rows): raise RuntimeError("disk full")
    E._sig_insert = boom
    try:
        ok("B a failing insert is swallowed", E.signal_shadow("nba", games(), lines(), now=2000.0) == 0)
    finally:
        E._sig_insert = old
    E.SIG["seen"].clear()
    def bad_score(l): raise ValueError("feed broke")
    E.leg_score = bad_score
    n = E.signal_shadow("nba", games(), lines(), now=3000.0)
    ok("B a score feed that raises costs only the state rows", n == 5, n)
    E.SIG["seen"].clear()
    ok("B junk sides and lines are swallowed", E.signal_shadow("nba", {"e": [None, 5, {"ticker": 3}]}, [object(), None], now=4000.0) == 0)
    ok("B games=None and lines=None are fine", E.signal_shadow("nba", None, None, now=4000.0) == 0)
    class Broken:
        in_transaction = False
        def execute(self, *a, **k): raise RuntimeError("closed")
        executemany = execute
    E.STORE["db"] = Broken()
    try:
        E.SIG["seen"].clear()
        ok("B a broken connection is swallowed (no raise)", isinstance(E.signal_shadow("nba", games(), lines(), now=5000.0), int))
    finally:
        E.STORE["db"] = db


def c_flag_and_inputs():
    E.SIG["seen"].clear()
    E.leg_score = lambda l: None
    g, ln = games(), lines()
    g0, ln0 = copy.deepcopy(g), copy.deepcopy(ln)
    E.signal_shadow("nba", g, ln, now=6000.0)
    ok("C the games and lines it was handed are unchanged (trading inputs untouched)", g == g0 and ln == ln0)
    E.CFG["sig_shadow"] = False
    try:
        before = count("sig_sharp")
        ok("C the flag off writes nothing", E.signal_shadow("nba", games(), lines(), now=9000.0) == 0 and count("sig_sharp") == before)
    finally:
        E.CFG["sig_shadow"] = True
    ok("C the flag defaults ON for recording, and is a known setting (so a saved false is kept, not dropped)", E.SIG["on"] is True and E.CFG.get("sig_shadow") is True and E.DEFAULTS.get("sig_shadow") is True)
    e1 = E.single_fee(0.4); E.signal_shadow("nba", games(), lines(), now=12000.0)
    ok("C a trading function's output is the same after recording", E.single_fee(0.4) == e1)


def d_bounded():
    E._sig_tables()
    E.store_x("delete from sig_sharp")
    for i in range(30):
        E.store_x("insert into sig_sharp values(?,?,?,?,?,?,?,?)", (100000.0 + i, "t", 0.5, 0.5, 0.5, "x", 0, 0))
    E.store_x("insert into sig_sharp values(?,?,?,?,?,?,?,?)", (1.0, "old", 0.5, 0.5, 0.5, "x", 0, 0))
    old = E.SIG["cap"]; E.SIG["cap"] = 10
    try:
        E._sig_prune(100000.0 + 40)
    finally:
        E.SIG["cap"] = old
    ok("D the old row (past 21 days) and the rows over the cap are pruned", count("sig_sharp") == 10 and not E.store_rows("select 1 from sig_sharp where ticker='old'"), count("sig_sharp"))


def e_unread():
    src = open(os.path.join(REPO, "nfl_combo_planner.py")).read()
    a, b = src.index("# ---- signal shadow (early-exit test"), src.index("# ---- exit_shadow: old")
    outside = src[:a] + src[b:]
    ok("E the engine outside the recorder never mentions the new tables", not re.search(r"sig_(sharp|related|state)", outside))
    ok("E inside it the tables are only created, inserted into, pruned and counted, never selected from", not re.search(r"select[^\n\"']*from\s+sig_", src[a:b], re.I) and "select * from" not in src[a:b])
    other = open(os.path.join(REPO, "watcher", "combo_watcher.py")).read()
    ok("E the watcher never mentions them", not re.search(r"sig_(sharp|related|state)", other))
    ok("E the single hook in the panel is one wrapped call after the market-fair log", src.count("signal_shadow(code, games, lc_all)") == 1)


for n, f in (("a", a_rows), ("b", b_swallow), ("c", c_flag_and_inputs), ("d", d_bounded), ("e", e_unread)):
    section(n, f)
