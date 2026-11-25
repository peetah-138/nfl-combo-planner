# CHECK: group=engine
# The ESPN win-chance recorder (issue #483, record-only): wp_shadow / wp_outcome / wp_hist / wp_lines in the engine.
#  A  wp_shadow rows land with the right fields, throttled, with no request made
#  B  every failure is swallowed (no history, a broken insert, a feed that raises, junk input)
#  C  the flags turn it off, the trading inputs are byte-for-byte unchanged, both flags are known settings
#  D  bounded: retention days and a row ceiling, oldest first
#  E  nothing decides from these tables: no mention outside the recorder, never selected from except bookkeeping
#  F  wp_hist: ingest dedupe, line changes only, the request rate limits and state rules
import os, re, copy, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
REPO = os.environ.get("REPO") or os.path.abspath("../..")
T = "KXNBAGAME-26NOV23LALBOS"


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def games():
    return {T: [
        {"ticker": T + "-LAL", "p": 0.55, "bid": 0.53, "fair": 0.58, "pre": 0.58, "live": True},
        {"ticker": T + "-BOS", "p": 0.47, "bid": 0.45, "fair": 0.42, "pre": 0.42, "live": True},
        {"ticker": T + "-TIE", "p": 0.01, "bid": None, "fair": 0.0, "tie": True, "live": True}]}


def score(l):
    return {"state": "in", "me": 55, "opp": 50, "frac": 0.4, "wp": 0.61, "wp_play": "p77", "game": "401"}


def count(t):
    return E.store_rows(f"select count(*) n from {t}")[0]["n"]


def reset():
    for d in (E.WPR["seen"], E.WPR["play"], E.WPH["have"], E.WPH["line"], E.WPH["last"], E.WPH["live"], E.WPH["code"], E.WPH["done"]):
        d.clear()
    E.WPH["stamps"][:] = []; E.WPH["busy"] = False
    E.WPR["prune"] = E.WPH["prune"] = 0.0


class NoNet:
    def __getattr__(self, k):
        raise AssertionError("a request was made: " + k)


def a_rows():
    reset(); E.leg_score = score
    real, E.requests = E.requests, NoNet()
    try:
        n = E.wp_shadow("nba", games(), now=1000.0)
    finally:
        E.requests = real
    ok("A two sides recorded (the tie side never), no request made", n == 2 and count("wp_shadow") == 2, n)
    r = E.store_rows("select * from wp_shadow where ticker like '%LAL'")[0]
    ok("A fields: wp, play id, bid, ask, mid, league", (r["wp"], r["play_id"], r["bid"], r["ask"], r["mid"], r["league"]) == (0.61, "p77", 0.53, 0.55, 0.54, "nba"), r)
    ok("A play age is 0 the first time a play is seen, the lead and clock are kept", r["play_age"] == 0.0 and r["lead"] == 5 and r["frac"] == 0.4, r)
    ok("A throttled: 10 s later writes nothing", E.wp_shadow("nba", games(), now=1010.0) == 0)
    ok("A a minute later the same play is 65 s old", E.wp_shadow("nba", games(), now=1065.0) == 2 and
       E.store_rows("select max(play_age) a from wp_shadow")[0]["a"] == 65.0)
    E.leg_score = lambda l: {"state": "in", "me": 1, "opp": 0, "frac": 0.5, "wp": None, "wp_play": None, "game": "402"}
    E.wp_shadow("nba", games(), now=2000.0)
    r = E.store_rows("select wp, play_age from wp_shadow where ts=2000.0")
    ok("A a game with no wp is still a row (coverage) with wp and age empty", len(r) == 2 and r[0]["wp"] is None and r[0]["play_age"] is None, r)
    E.leg_score = lambda l: {"state": "pre", "me": 0, "opp": 0}
    ok("A a game not in play records nothing", E.wp_shadow("nba", games(), now=3000.0) == 0)
    E.leg_score = lambda l: dict(score(l), wp=7.5)
    E.wp_shadow("nba", games(), now=4000.0)
    ok("A an out-of-range wp is stored as empty, never as junk", E.store_rows("select wp from wp_shadow where ts=4000.0")[0]["wp"] is None)


def a2_screened():
    reset(); E.leg_score = score
    scr = {"G2": ([{"ticker": "KXNBAGAME-26NOV23MIAPHI-MIA", "p": 0.60, "bid": 0.50, "pre": 0.5, "fair": 0.9},
                   {"ticker": "KXNBAGAME-26NOV23MIAPHI-PHI", "p": 0.55, "bid": 0.45, "pre": 0.5}], "the live price is jumpy (10 cents)")}
    n = E.wp_shadow("nba", games(), now=1500.0, screened=scr)
    rows = E.store_rows("select ticker, screened, fair, wp from wp_shadow where ts=1500.0")
    kept = [r for r in rows if r["screened"] is None]; sc = [r for r in rows if r["screened"]]
    ok("A2 kept and screened games both recorded, screened marked with a short reason", n == 4 and len(kept) == 2 and len(sc) == 2
       and {r["screened"] for r in sc} == {"spread"}, rows)
    ok("A2 a screened side never carries the engine's fair", all(r["fair"] is None for r in sc) and all(r["wp"] == 0.61 for r in sc))
    ok("A2 reasons map to words", [E._wp_why(t) for t in ("no live buyers or sellers on Kalshi", "nearly decided", "no fresh live score",
       "Kalshi's live price and the live chance disagree too much", "zzz")] == ["no_buyers", "decided", "stale", "disagree", "other"])
    real, E.requests = E.requests, NoNet()
    try:
        E.espn_wp_record("nba", games(), scr)
    finally:
        E.requests = real
    ok("A2 the hook takes screened games and makes no request itself", True)
    st = E.store_rows("pragma table_info(wp_shadow)")
    ok("A2 screened is the last column", st[-1]["name"] == "screened")


def b_swallow():
    reset(); E.leg_score = score
    db = E.STORE["db"]; E.STORE["db"] = None
    ok("B no history open: 0, no raise", E.wp_shadow("nba", games(), now=5000.0) == 0 and E.wp_resolve() == 0
       and E.wp_hist_ingest("nba", "1", {}) == 0 and E.wp_hist_tick("nba", games()) == 0)
    E.STORE["db"] = db
    old = E._wp_insert
    def boom(b): raise RuntimeError("disk full")
    E._wp_insert = boom
    try:
        ok("B a failing insert is swallowed", E.wp_shadow("nba", games(), now=5000.0) == 0)
        ok("B a failing insert in ingest is swallowed", E.wp_hist_ingest("nba", "9", {"winprobability": [{"playId": "a", "homeWinPercentage": .5}]}) == 0)
    finally:
        E._wp_insert = old
    reset()
    def bad(l): raise ValueError("feed broke")
    E.leg_score = bad
    ok("B a score feed that raises records nothing and does not raise", E.wp_shadow("nba", games(), now=6000.0) == 0)
    ok("B junk sides and junk input are swallowed", E.wp_shadow("nba", {"e": [None, 5, {"ticker": 3}]}, now=7000.0) == 0
       and E.wp_shadow("nba", None) == 0 and E.wp_hist_ingest("nba", "1", "junk") == 0 and E.wp_hist_ingest("nba", "1", None) == 0)
    ok("B a game id that is not digits is never fetched", E.wp_hist_fetch("nba", "../x") == 0)
    class Broken:
        in_transaction = False
        def execute(self, *a, **k): raise RuntimeError("closed")
        executemany = execute
    E.STORE["db"] = Broken(); E.leg_score = score
    try:
        reset()
        ok("B a broken connection is swallowed", isinstance(E.wp_shadow("nba", games(), now=8000.0), int))
    finally:
        E.STORE["db"] = db
    reset()
    E.requests = NoNet()
    try:
        ok("B a request that raises costs nothing", E.wp_hist_fetch("nba", "401") == 0)
    finally:
        E.requests = __import__("requests")
    ok("B espn_wp_record never raises", E.espn_wp_record("nba", object()) is None)


def c_flags():
    reset(); E.leg_score = score
    g = games(); g0 = copy.deepcopy(g)
    E.wp_shadow("nba", g, now=9000.0)
    ok("C the games it was handed are unchanged (trading inputs untouched)", g == g0)
    for flag, fn in (("wp_shadow", lambda: E.wp_shadow("nba", games(), now=9500.0)),
                     ("wp_hist", lambda: E.wp_hist_ingest("nba", "55", {"winprobability": [{"playId": "a", "homeWinPercentage": .5}]}))):
        E.CFG[flag] = False
        try:
            before = count("wp_shadow") + count("wp_hist")
            ok(f"C the {flag} flag off writes nothing", fn() == 0 and count("wp_shadow") + count("wp_hist") == before)
        finally:
            E.CFG[flag] = True
    ok("C both flags default ON and are known settings", all(E.CFG.get(k) is True and E.DEFAULTS.get(k) is True for k in ("wp_shadow", "wp_hist")))
    e1 = E.single_fee(0.4); E.wp_shadow("nba", games(), now=12000.0)
    ok("C a trading function's output is the same after recording", E.single_fee(0.4) == e1)


def d_bounded():
    E._wp_tables()
    for t in ("wp_shadow", "wp_hist", "wp_lines", "wp_outcome"):
        E.store_x(f"delete from {t}")
    now = 10_000_000.0
    for i in range(30):
        E.store_x("insert into wp_shadow(ts, ticker) values(?,?)", (now - i, "t%d" % i))
        E.store_x("insert into wp_hist(ts, league, game, seq, play_id) values(?,?,?,?,?)", (now - i, "nba", "g", i, "p%d" % i))
    E.store_x("insert into wp_shadow(ts, ticker) values(?,?)", (now - 31 * 86400, "old"))
    E.store_x("insert into wp_hist(ts, league, game, seq, play_id) values(?,?,?,?,?)", (now - 46 * 86400, "nba", "g", 99, "oldp"))
    cap, hcap = E.WPR["cap"], E.WPH["cap"]; E.WPR["cap"] = 10; E.WPH["cap"] = 12
    try:
        E._wp_prune(now)
    finally:
        E.WPR["cap"], E.WPH["cap"] = cap, hcap
    ok("D rows past retention and rows over the ceiling are pruned, wp_shadow", count("wp_shadow") == 10 and not E.store_rows("select 1 from wp_shadow where ticker='old'"), count("wp_shadow"))
    ok("D the same for wp_hist", count("wp_hist") == 12, count("wp_hist"))
    left = E.store_rows("select ticker from wp_shadow order by ts")
    ok("D oldest first: the newest rows survive", [r["ticker"] for r in left][-1] == "t0" and "t29" not in {r["ticker"] for r in left})


def d2_prune_independent():
    reset(); E.CFG["wp_shadow"] = False
    for t in ("wp_hist",):
        E.store_x(f"delete from {t}")
    E.store_x("insert into wp_hist(ts, league, game, seq, play_id) values(?,?,?,?,?)", (1.0, "nba", "g", 1, "ancient"))
    try:
        E.espn_wp_record("nba", {})
    finally:
        E.CFG["wp_shadow"] = True
    ok("D the prune runs even with wp_shadow off (wp_hist is bounded too)", count("wp_hist") == 0)


def e_unread():
    src = open(os.path.join(REPO, "nfl_combo_planner.py")).read()
    a, b = src.index("# ---- ESPN win-chance recorder (issue #483"), src.index("# ---- exit_shadow: old")
    outside, inside = src[:a] + src[b:], src[a:b]
    tbl = r"wp_(shadow|outcome|hist|lines)\b"
    ok("E nothing outside the recorder reads or writes the tables in SQL", not re.search(r"(from|into|join|table|update|exists)\s+" + tbl, outside, re.I))
    outside_calls = set(re.findall(r"\b(wp_shadow|wp_resolve|wp_hist_\w+|espn_wp_record|_wp_\w+)\(", outside))
    ok("E the only calls outside are the hook, the resolver and the game page's ingest", outside_calls <= {"espn_wp_record", "wp_resolve", "wp_hist_ingest"}, outside_calls)
    reads = [m.start() for m in re.finditer(r"select", inside, re.I)]
    fn_of = lambda i: re.findall(r"\ndef (\w+)\(", inside[:i])[-1]
    ok("E inside it, selects appear only in wp_resolve and the prune's counts", {fn_of(i) for i in reads} <= {"wp_resolve", "_wp_prune"}, {fn_of(i) for i in reads})
    other = open(os.path.join(REPO, "watcher", "combo_watcher.py")).read()
    ok("E the watcher never mentions them", not re.search(r"wp_(shadow|outcome|hist|lines)", other))
    ok("E the panel hook is one wrapped call", src.count("espn_wp_record(") >= 1 and "wp_hist_ingest(" in outside)


def f_hist():
    reset()
    for t in ("wp_hist", "wp_lines"):
        E.store_x(f"delete from {t}")
    data = {"header": {"competitions": [{"competitors": [{"homeAway": "home", "team": {"abbreviation": "BOS"}}, {"homeAway": "away", "team": {"abbreviation": "LAL"}}]}]},
            "plays": [{"id": "a", "wallclock": "2026-11-23T20:00:00Z"}],
            "winprobability": [{"playId": "a", "homeWinPercentage": 0.5}, {"playId": "b", "homeWinPercentage": 0.55}, {"playId": "c", "homeWinPercentage": 7}],
            "pickcenter": [{"provider": {"name": "X"}, "details": "BOS -3", "spread": -3, "overUnder": 220.5, "overOdds": -110, "underOdds": -110,
                            "homeTeamOdds": {"moneyLine": -150}, "awayTeamOdds": {"moneyLine": 130}}]}
    n = E.wp_hist_ingest("nba", "401", data, "in", now=100.0)
    ok("F plays and one line are recorded (the junk 7 is skipped)", n == 3 and count("wp_hist") == 2 and count("wp_lines") == 1, n)
    r = E.store_rows("select home, away, wall from wp_hist where play_id='a'")[0]
    ok("F teams and the play's wallclock are kept", r["home"] == "BOS" and r["away"] == "LAL" and r["wall"], r)
    ok("F the same summary again writes nothing (new plays and line changes only)", E.wp_hist_ingest("nba", "401", data, "in", now=200.0) == 0)
    data["winprobability"].append({"playId": "d", "homeWinPercentage": 0.6}); data["pickcenter"][0]["spread"] = -4
    ok("F a new play and a changed line add one row each", E.wp_hist_ingest("nba", "401", data, "in", now=300.0) == 2 and count("wp_lines") == 2)
    # due rules
    reset()
    st = {"s": "in"}
    E.leg_score = lambda l: {"state": st["s"], "game": "500", "start": "2026-11-23T20:00:00Z"}
    g = {"E": [{"ticker": "KXNBAGAME-26NOV23AABB-AA"}]}
    ok("F in play: due the first time", E.wp_hist_due("nba", g, now=1000.0) == [("nba", "500", "in")])
    E.WPH["last"]["500"] = 1000.0
    ok("F in play: not again within 300 s", E.wp_hist_due("nba", g, now=1100.0) == [] and E.wp_hist_due("nba", g, now=1301.0) != [])
    ok("F a league outside the list is never fetched", E.wp_hist_due("nhl", g, now=1000.0) == [])
    ok("F a game with no Kalshi market is never fetched", E.wp_hist_due("nba", {}, now=1000.0) == [])
    E.WPH["last"].clear(); st["s"] = "pre"
    kick = E._wp_wall("2026-11-23T20:00:00Z")
    ok("F pre-game: due only within 4 h of kickoff", E.wp_hist_due("nba", g, now=kick - 3 * 3600) != [] and E.wp_hist_due("nba", g, now=kick - 5 * 3600) == [])
    E.WPH["last"]["500"] = kick - 3 * 3600
    ok("F pre-game: at most one per 2 h", E.wp_hist_due("nba", g, now=kick - 3 * 3600 + 600) == [])
    reset(); st["s"] = "post"
    ok("F a game we never saw live gets no final fetch", E.wp_hist_due("nba", g, now=kick + 9999) == [])
    st["s"] = "in"; E.wp_hist_due("nba", g, now=kick); st["s"] = "post"
    ok("F a game seen live gets one final fetch", E.wp_hist_due("nba", g, now=kick + 9999) == [("nba", "500", "post")])
    # ceilings
    reset(); st["s"] = "in"
    many = {"E%d" % i: [{"ticker": "KXNBAGAME-26NOV23X%d" % i}] for i in range(20)}
    E.leg_score = lambda l: {"state": "in", "game": str(100 + int(re.search(r"X(\d+)", l["ticker"]).group(1)))}
    ok("F at most per_tick games a pass", len(E.wp_hist_due("nba", many, now=1000.0)) == E.WPH["per_tick"])
    E.WPH["stamps"][:] = [990.0] * (E.WPH["per_hour"] - 1)
    ok("F never past the hourly ceiling", len(E.wp_hist_due("nba", many, now=1000.0)) == 1)
    E.WPH["stamps"][:] = [990.0] * E.WPH["per_hour"]
    ok("F ... and none at the ceiling", E.wp_hist_due("nba", many, now=1000.0) == [])
    ok("F the ceiling frees after an hour", E.wp_hist_due("nba", many, now=1000.0 + 3700) != [])
    reset()
    E.WPH["last"].update({"%d" % (100 + i): 900.0 + i for i in range(1, 20)})   # game 100 never fetched, the rest were
    first = E.wp_hist_due("nba", many, now=1000.0)
    ok("F least recently fetched first (the never-fetched game leads)", first and first[0][1] == "100", first[:2])
    reset(); st["s"] = "in"
    E.leg_score = lambda l: {"state": "in", "game": "500"}
    E.wp_hist_due("nba", g, now=2000.0); E.leg_score = lambda l: {"state": "pre", "game": "999"}
    ok("F a game that left the panel still gets its one final fetch after 10 min", E.wp_hist_due("nba", {}, now=2000.0 + 700) == [("nba", "500", "post")])
    E.WPH["done"]["500"] = 1.0
    ok("F ... and only once", E.wp_hist_due("nba", {}, now=2000.0 + 900) == [])
    E.leg_score = lambda l: {"state": "in", "game": str(100 + int(re.search(r"X(\d+)", l["ticker"]).group(1)))}
    reset()
    calls = []
    E.wp_hist_fetch = lambda code, g, state=None, now=None: calls.append(g) or 0
    E.time.sleep = lambda s: None
    ok("F a tick queues a background fetch and returns at once", E.wp_hist_tick("nba", many, now=5000.0) == E.WPH["per_tick"])
    import time as _t
    for _ in range(100):
        if not E.WPH["busy"]: break
        _t.sleep(0.05)
    ok("F one worker ran the queued games", len(calls) == E.WPH["per_tick"], calls)


def g_resolve():
    reset(); E.leg_score = score
    for t in ("wp_shadow", "wp_outcome"):
        E.store_x(f"delete from {t}")
    E.wp_shadow("nba", games(), now=1000.0)
    E.fetch_results = lambda ts: {t: ("yes" if t.endswith("LAL") else "no") for t in ts}
    ok("G a game's tickers are not resolved before 3 h", E.wp_resolve(now=1000.0 + 3600) == 0)
    ok("G after 3 h each ticker gets its result once", E.wp_resolve(now=1000.0 + 4 * 3600) == 2 and E.wp_resolve(now=1000.0 + 5 * 3600) == 0)
    ok("G outcomes are yes and no", {r["outcome"] for r in E.store_rows("select outcome from wp_outcome")} == {"yes", "no"})


for n, f in (("a", a_rows), ("a2", a2_screened), ("b", b_swallow), ("c", c_flags), ("d", d_bounded), ("d2", d2_prune_independent), ("e", e_unread), ("f", f_hist), ("g", g_resolve)):
    section(n, f)
