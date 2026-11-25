# CHECK: group=engine
# The paper shadows (#323 step 2, #332): prop_shadow (player-prop prices a pass already read) and slate_shadow (aggregates of
# how concentrated the held and candidate positions are). Same pattern as signal_shadow.
#  A  prop rows: plain, pre-game, tight, mid 10-90% only; throttled; a settled market's result kept; no request made
#  B  every failure is swallowed (no history, a failing insert, junk markets): 0, no raise
#  C  the flags turn them off; the inputs are unchanged; fetch_series hands over what it read and fetches nothing extra
#  D  bounded: old rows and rows over the cap are pruned
#  E  slate rows: numbers right for a known slate, aggregates only (no ticker column), throttled
#  F  nothing decides from these tables: never mentioned outside the block
import os, re, copy, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
REPO = os.environ.get("REPO") or os.path.abspath("../..")
NOW = 1_700_000_000.0
E.KICKOFF["KXNFLGAME-26NOV30JACNYG"] = "2023-11-15T10:00:00Z"          # NOW + ~16 h
E.KICKOFF["KXNFLGAME-26NOV22OLDGAME"] = "2023-11-14T00:00:00Z"         # before NOW: under way


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def count(t):
    return E.store_rows(f"select count(*) n from {t}")[0]["n"]


def mk(t, bid, ask, **kw):
    return dict({"ticker": t, "event_ticker": t.rsplit("-", 2)[0], "yes_bid_dollars": str(bid), "yes_ask_dollars": str(ask),
                 "floor_strike": 49.5, "volume": 10}, **kw)


def markets():
    return [mk("KXNFLRECYDS-26NOV30JACNYG-JACPWASHINGTON11-50", 0.44, 0.46),      # recorded
            mk("KXNFLRECYDS-26NOV30JACNYG-JACPWASHINGTON11-70", 0.20, 0.22, yes_ask_size_fp="150.00"),   # recorded, with size
            mk("KXNFLRECYDS-26NOV30JACNYG-JACPWASHINGTON11-90", 0.02, 0.04),       # tail: mid under 10%
            mk("KXNFLRECYDS-26NOV30JACNYG-JACPWASHINGTON11-30", 0.40, 0.50),       # gap over 6c
            mk("KXNFLRECYDS-26NOV22OLDGAME-X1-50", 0.44, 0.46),                    # game under way
            mk("KXNFLRECYDS-26NOV99NOKICK-X1-50", 0.44, 0.46),                     # kickoff unknown
            mk("KXNFLGAME-26NOV30JACNYG-JAC", 0.44, 0.46)]                         # not a prop


def a_rows():
    class NoNet:
        def __getattr__(self, k):
            raise AssertionError("a request was made: " + k)
    real, E.requests = E.requests, NoNet()
    try:
        E.PROP["seen"].clear()
        n = E.prop_shadow(markets(), "KXNFLRECYDS", now=NOW)
        ok("A plain pre-game tight markets only (2 of 7), no request made", n == 2, n)
        r = E.store_rows("select league, stat, strike, bid, ask, mid, ask_size, kick, result from prop_shadow order by ask")
        ok("A the row holds league, stat, strike, bid, ask, mid, size and the kickoff", r[0]["league"] == "NFL" and r[0]["stat"] == "RECYDS"
           and r[0]["strike"] == 49.5 and r[0]["mid"] == 0.21 and r[0]["ask_size"] == 150.0 and r[1]["mid"] == 0.45 and r[0]["kick"] and r[0]["result"] is None, r)
        ok("A throttled: the same pass a minute later writes nothing", E.prop_shadow(markets(), "KXNFLRECYDS", now=NOW + 60) == 0)
        ok("A and again after 30 minutes", E.prop_shadow(markets(), "KXNFLRECYDS", now=NOW + 1900) == 2)
        ok("A a protected series and a game series are never recorded", E.prop_shadow(markets(), "KXNFLRECYDSPROT", now=NOW + 9000) == 0
           and E.prop_shadow(markets(), "KXNFLGAME", now=NOW + 9000) == 0)
        sett = [mk("KXNBAPTS-26NOV30LALBOS-LALX5-20", 0, 0, result="yes", status="settled")]
        ok("A a settled market's result is kept", E.prop_shadow(sett, "KXNBAPTS", now=NOW + 9000) == 1
           and E.store_rows("select result r from prop_shadow where ticker like 'KXNBAPTS%'")[0]["r"] == "yes")
    finally:
        E.requests = real


def b_swallow():
    db = E.STORE["db"]
    E.PROP["seen"].clear(); E.SLATE["seen"].clear()
    E.STORE["db"] = None
    ok("B no history open: 0, no raise", E.prop_shadow(markets(), "KXNFLRECYDS", now=NOW) == 0 and E.slate_shadow("nfl", [{"kind": "single"}], now=NOW) == 0)
    E.STORE["db"] = db
    old = E._shadow_insert
    def boom(*a): raise RuntimeError("disk full")
    E._shadow_insert = boom
    try:
        ok("B a failing insert is swallowed", E.prop_shadow(markets(), "KXNFLRECYDS", now=NOW + 1e5) == 0
           and E.slate_shadow("nfl", [{"kind": "single", "legs": []}], now=NOW + 1e5) == 0)
    finally:
        E._shadow_insert = old
    E.PROP["seen"].clear()
    ok("B junk markets and junk candidates are swallowed", E.prop_shadow([None, 5, {"ticker": 3}, {"ticker": "KXNFLREC-A-B-1", "yes_bid": "x"}], "KXNFLREC", now=NOW + 2e5) == 0
       and isinstance(E.slate_shadow("nfl", [None, 5, {"legs": 3}, {"kind": "single"}], now=NOW + 2e5), int))   # the pass survives a bad candidate
    ok("B markets=None is fine", E.prop_shadow(None, "KXNFLRECYDS", now=NOW + 3e5) == 0)


def c_flags_inputs():
    E.PROP["seen"].clear()
    m = markets(); m0 = copy.deepcopy(m)
    E.prop_shadow(m, "KXNFLRECYDS", now=NOW + 4e5)
    ok("C the markets it was handed are unchanged", m == m0)
    E.CFG["prop_shadow"] = False; E.CFG["slate_shadow"] = False
    try:
        before = count("prop_shadow")
        E.PROP["seen"].clear()
        ok("C the flags off write nothing", E.prop_shadow(markets(), "KXNFLRECYDS", now=NOW + 5e5) == 0 and count("prop_shadow") == before
           and E.slate_shadow("nfl", [{"kind": "single", "legs": []}], now=NOW + 5e5) == 0)
    finally:
        E.CFG["prop_shadow"] = True; E.CFG["slate_shadow"] = True
    ok("C both default ON for recording and are known settings", E.PROP["on"] and E.SLATE["on"] and E.DEFAULTS.get("prop_shadow") is True and E.DEFAULTS.get("slate_shadow") is True)
    seen = []
    class R:
        def raise_for_status(self): pass
        def json(self): return {"markets": markets()[:2]}
    class Req:
        def get(self, url, **k): seen.append(k.get("params")); return R()
    real, E.requests = E.requests, Req()
    old = E.prop_shadow
    got = []
    E.prop_shadow = lambda out, series="", now=None: got.append((len(out), series)) or 0
    try:
        E.fetch_series("KXNFLRECYDS")
    finally:
        E.requests, E.prop_shadow = real, old
    ok("C fetch_series hands over what it read, with the series, and makes just its own one request", got == [(2, "KXNFLRECYDS")] and len(seen) == 1, got, seen)


def d_bounded():
    E._prop_tables(); E._slate_tables()
    E.store_x("delete from prop_shadow")
    for i in range(30):
        E.store_x("insert into prop_shadow values(?,?,?,?,?,?,?,?,?,?,?,?,?)", (100000.0 + i, "t", "e", "NFL", "REC", 1, .4, .5, .45, 1, 1, 1, None))
    E.store_x("insert into prop_shadow values(?,?,?,?,?,?,?,?,?,?,?,?,?)", (1.0, "old", "e", "NFL", "REC", 1, .4, .5, .45, 1, 1, 1, None))
    E._shadow_prune("prop_shadow", 14, 10, 100000.0 + 40)
    ok("D the old row and the rows over the cap go, newest kept", count("prop_shadow") == 10 and not E.store_rows("select 1 from prop_shadow where ticker='old'")
       and E.store_rows("select max(ts) m from prop_shadow")[0]["m"] == 100029.0, count("prop_shadow"))
    E.store_x("delete from prop_shadow")
    n = 0
    mm = [mk(f"KXNFLRECYDS-26NOV30JACNYG-P{i}-50", 0.44, 0.46) for i in range(900)]
    E.PROP["seen"].clear()
    n = E.prop_shadow(mm, "KXNFLRECYDS", now=NOW + 100)
    ok("D one call writes at most 800 rows", n == 800, n)
    E.store_x("delete from slate_shadow")
    for i in range(30):
        E.store_x("insert into slate_shadow values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (100000.0 + i, "d", "held", "all", 1, 1, 1, 1, 1, 1, 1, 1, 1, None, None, None, None))
    E._shadow_prune("slate_shadow", 90, 10, 100000.0 + 40)
    ok("D slate rows are capped too", count("slate_shadow") == 10)


def e_slate():
    E.SLATE["seen"].clear()
    E.store_x("delete from slate_shadow")
    E.game_exposure = lambda *a, **k: {"KXNFLGAME-26NOV30AAABBB": {"n": 2, "risk": 30.0}, "KXNFLGAME-26NOV30CCCDDD": {"n": 1, "risk": 10.0},
                                       "KXNBAGAME-26NOV30EEEFFF": {"n": 1, "risk": 10.0}}
    k = 1_700_100_000.0
    def c(kind, evs, chance, kick):
        return {"kind": kind, "legs": [{"event": e} for e in evs], "chance": chance, "kick": kick}
    cands = [c("single", ["KXNFLGAME-26NOV30AAABBB"], 0.6, k), c("combo", ["KXNFLGAME-26NOV30AAABBB", "KXNFLGAME-26NOV30CCCDDD"], 0.3, k),
             c("line", ["KXNFLSPREAD-26NOV30AAABBB"], 0.45, k + 60), c("combo", ["KXNFLGAME-26NOV30AAABBB", "KXNFLSPREAD-26NOV30AAABBB"], 0.2, k + 90)]
    n = E.slate_shadow("nfl", cands, now=NOW)
    ok("E one held row and one pool row", n == 2, n)
    h = E.store_rows("select * from slate_shadow where scope='held'")[0]
    ok("E held: 4 bets on 3 games, $50 at risk, top game 60%, top three 100%, NFL league share 80%", h["n"] == 4 and h["games"] == 3 and h["w"] == 50.0 and h["top1"] == 0.6 and h["top3"] == 1.0 and h["lg_top"] == 0.8 and h["max_on_game"] == 2, dict(h))
    ok("E held: HHI 0.6^2+0.2^2+0.2^2 = 0.44 and 2.27 effective games", h["hhi"] == 0.44 and h["eff_games"] == 2.27, dict(h))
    p = E.store_rows("select * from slate_shadow where scope='pool'")[0]
    ok("E pool: 4 candidates over 2 games, 1 same-game combo, 50% favourites, 3-hour slot all one, top class 2 of 4", p["n"] == 4 and p["games"] == 2 and p["same_game"] == 1
       and p["fav"] == 0.25 and p["slot_top"] == 1.0 and p["cls_top"] == 0.5 and p["max_on_game"] == 4, dict(p))
    cols = {r["name"] for r in E.store_rows("pragma table_info(slate_shadow)")}
    ok("E aggregates only: no ticker, event or id column", not cols & {"ticker", "event", "id", "tickers"}, cols)
    ok("E throttled: the same call a minute later writes nothing", E.slate_shadow("nfl", cands, now=NOW + 60) == 0)
    ok("E an empty candidate list writes no pool row (the held row only)", E.slate_shadow("nba", [], now=NOW + 5000) == 1 and count("slate_shadow") == 3)


def f_unread():
    src = open(os.path.join(REPO, "nfl_combo_planner.py")).read()
    a, b = src.index("# ---- paper shadows, part 1"), src.index("# ---- signal shadow (early-exit test")
    outside, inside = src[:a] + src[b:], src[a:b]
    gone = "\n".join(l for l in outside.splitlines() if "prop_shadow(out, series)" not in l and "slate_shadow(code, cands)" not in l and '"prop_shadow": True' not in l and '"slate_shadow": True' not in l)
    ok("F the engine outside the block never mentions the new tables or recorders (bar the two hooks and the two settings)", not re.search(r"prop_shadow|slate_shadow", gone))
    ok("F inside it the tables are only created, inserted into, pruned and counted, never selected from for a decision",
       not re.search(r"select\s+(?!count\(\*\) n)[^\n\"']*from\s+(prop|slate)_shadow", inside, re.I))
    other = open(os.path.join(REPO, "watcher", "combo_watcher.py")).read()
    ok("F the watcher never mentions them", not re.search(r"prop_shadow|slate_shadow", other))
    ok("F one wrapped hook each: fetch_series and the panel pass", src.count("prop_shadow(out, series)") == 1 and src.count("slate_shadow(code, cands)") == 1)


for n, f in (("a", a_rows), ("b", b_swallow), ("c", c_flags_inputs), ("d", d_bounded), ("e", e_slate), ("f", f_unread)):
    section(n, f)
