# CHECK: group=engine
# The news + game-context recorder (signal events in the engine): injury changes and per-game context written to NEW
# append-only tables, from caches the app already fills, with no request and no effect on any decision.
#  A  change detection: baseline first, then a new item / status change writes ONE row, never a duplicate
#  B  follow-up samples at +5/+15/+60 minutes from the prices already read; a sample too late is dropped, not faked
#  C  context rows (pre2h and start): unknown fields stay NULL, travel/time zones from the static table, rest days
#  D  retention (a year) and the row ceiling that stops writes; migration on an existing history file; restart reload
#  E  every failure is swallowed; the flag turns it off; trading inputs are untouched; no request is made
#  F  nothing decides from these tables: only the recorder's own loader/pruner select from them
import os, re, copy, sqlite3, tempfile, datetime as dt, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
DBP = os.path.join(tempfile.mkdtemp(), "h.db")
E.store_open(DBP); E.HERE = tempfile.mkdtemp()
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
REPO = os.environ.get("REPO") or os.path.abspath("../..")
T0 = 1_800_000_000.0


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


class NoNet:
    def __getattr__(self, k):
        raise AssertionError("a request was made: " + k)


E.requests = NoNet()                                   # nothing in this file may touch the network


def count(t):
    return E.store_rows(f"select count(*) n from {t}")[0]["n"]


def reset():
    E._sev_tables()
    for t in ("sig_news", "sig_news_fu", "sig_ctx"):
        E.store_x(f"delete from {t}")
    for k in ("inj", "inj_at", "team", "games", "fair", "pend", "espn", "sched", "cov"):
        E.SEV[k].clear()
    E.SEV["done"].clear(); E.SEV["full"].clear(); E.SEV["last"] = 0.0
    E.SEV["load"] = False
    E.PRICE_SEEN.clear(); E.INJ.clear()
    E.CFG["sig_shadow"] = True


def games(start_ts=None, live=False):
    return {"KXNBAGAME-26NOV23LALBOS": [
        {"ticker": "KXNBAGAME-26NOV23LALBOS-LAL", "pick": "Los Angeles L", "p": 0.55, "bid": 0.53, "fair": 0.58,
         "fair_book": 0.60, "src": "pinnacle", "live": live, "exp": "x"},
        {"ticker": "KXNBAGAME-26NOV23LALBOS-BOS", "pick": "Boston", "p": 0.47, "bid": 0.45, "fair": 0.42,
         "fair_book": 0.40, "src": "pinnacle", "live": live, "exp": "x"}]}


def inj(status, name="Jayson Tatum", when="2026-11-23T20:00Z"):
    return {"boston celtics": [(name, "SF", status, when, "note")], "los angeles lakers": []}


def put_inj(t, snap):
    E.INJ["nba"] = (t, snap)


def px(t, bid, ask, tm):
    E.PRICE_SEEN[t] = (tm, bid, ask, None)


BOS = "KXNBAGAME-26NOV23LALBOS-BOS"


def a_detect():
    reset()
    E.game_start = lambda e, t=None, x=None: (dt.datetime.fromtimestamp(T0 + 40 * 3600, dt.timezone.utc), "book")
    put_inj(T0, inj("Active"))
    px(BOS, 0.45, 0.47, T0)
    E.signal_events("nba", games(), now=T0)
    ok("A the first read only sets the baseline: no row", count("sig_news") == 0)
    put_inj(T0 + 1800, inj("Out"))
    px(BOS, 0.44, 0.46, T0 + 1790)
    E.signal_events("nba", games(), now=T0 + 1800)
    r = E.store_rows("select * from sig_news")
    ok("A a status change writes exactly one row", len(r) == 1, r)
    r = r[0] if r else {}
    ok("A the row names team, player, old/new status, ticker, market bid/ask and book probability",
       (r.get("team"), r.get("player"), r.get("old_status"), r.get("new_status"), r.get("ticker"), r.get("bid"), r.get("ask"),
        r.get("fair_book"), r.get("kind"), r.get("material")) ==
       ("boston celtics", "Jayson Tatum", "Active", "Out", BOS, 0.44, 0.46, 0.40, "change", 1), r)
    E.signal_events("nba", games(), now=T0 + 1900)
    put_inj(T0 + 3700, inj("Out"))
    E.signal_events("nba", games(), now=T0 + 3700)
    ok("A the same news seen again (same read, or a fresh read with no change) writes no duplicate", count("sig_news") == 1)
    E.SEV["inj"].clear(); E.SEV["inj_at"].clear()          # a restart forgets the baseline: the same item must not repeat
    put_inj(T0 + 3800, inj("Out")); E.signal_events("nba", games(), now=T0 + 3800)
    put_inj(T0 + 5600, inj("Doubtful")); E.signal_events("nba", games(), now=T0 + 5600)
    put_inj(T0 + 7400, inj("Out")); E.signal_events("nba", games(), now=T0 + 7400)
    ok("A a different change is a new row", count("sig_news") == 3, count("sig_news"))
    put_inj(T0 + 9200, {"boston celtics": [("Jayson Tatum", "SF", "Out", "2026-11-23T20:00Z", "n"),
                                           ("New Guy", "PG", "Questionable", "2026-11-23T21:00Z", "n")],
                        "los angeles lakers": []})
    E.signal_events("nba", games(), now=T0 + 9200)
    n = E.store_rows("select kind, old_status, new_status from sig_news where player='New Guy'")
    ok("A a new item is kind 'new' with no old status", n == [{"kind": "new", "old_status": None, "new_status": "Questionable"}], n)
    put_inj(T0 + 11000, {})
    E.signal_events("nba", games(), now=T0 + 11000)
    put_inj(T0 + 12800, inj("Out")); E.signal_events("nba", games(), now=T0 + 12800)
    ok("A a failed (empty) read is not news and does not wipe the baseline (only the real removal of New Guy shows)",
       count("sig_news") == 5 and E.store_rows("select count(*) n from sig_news where kind='removed'")[0]["n"] == 1, count("sig_news"))


def b_followups():
    reset()
    E.game_start = lambda e, t=None, x=None: (dt.datetime.fromtimestamp(T0 + 40 * 3600, dt.timezone.utc), "book")
    put_inj(T0, inj("Active")); E.signal_events("nba", games(), now=T0)
    put_inj(T0 + 1800, inj("Out")); px(BOS, 0.45, 0.47, T0 + 1799)
    E.signal_events("nba", games(), now=T0 + 1800)
    nid = E.store_rows("select id from sig_news")[0]["id"]
    ok("B the news is queued for three samples", E.SEV["pend"].get(nid, {}).get("todo") == {5, 15, 60})
    t = T0 + 1800
    for mins, bid in ((3, 0.46), (5, 0.40), (16, 0.38), (61, 0.35)):
        px(BOS, bid, bid + 0.02, t + mins * 60 - 5)
        E.signal_events("nba", games(), now=t + mins * 60)
    r = E.store_rows("select horizon, bid, ask, fair_book from sig_news_fu order by horizon")
    ok("B one row per horizon, none at 3 minutes", [x["horizon"] for x in r] == [5, 15, 60], r)
    ok("B each carries the bid/ask the engine last read and the book probability", [x["bid"] for x in r] == [0.40, 0.38, 0.35]
       and all(x["fair_book"] == 0.40 for x in r), r)
    ok("B done: nothing left queued", nid not in E.SEV["pend"])
    n0 = count("sig_news_fu")
    E.signal_events("nba", games(), now=t + 62 * 60)
    ok("B no duplicate samples afterwards", count("sig_news_fu") == n0)
    # a late sample (app off) is dropped, not faked; and a stale price is never used
    reset()
    put_inj(T0, inj("Active")); E.signal_events("nba", games(), now=T0)
    put_inj(T0 + 1800, inj("Out")); px(BOS, 0.45, 0.47, T0 + 1799); E.signal_events("nba", games(), now=T0 + 1800)
    px(BOS, 0.30, 0.32, T0 + 1800 + 5 * 60 - 400)           # 400 s old at the +5 mark: too stale
    E.signal_events("nba", games(), now=T0 + 1800 + 5 * 60)
    ok("B a price older than the freshness limit is not sampled", count("sig_news_fu") == 0)
    px(BOS, 0.30, 0.32, T0 + 1800 + 12 * 60)
    E.signal_events("nba", games(), now=T0 + 1800 + 12 * 60)
    ok("B the +5 sample, more than 5 minutes late, is dropped; +15 not yet due", count("sig_news_fu") == 0)
    px(BOS, 0.30, 0.32, T0 + 1800 + 16 * 60 - 3)
    E.signal_events("nba", games(), now=T0 + 1800 + 16 * 60)
    ok("B the +15 sample lands with its delay recorded", E.store_rows("select horizon, delay_s from sig_news_fu") ==
       [{"horizon": 15, "delay_s": 60.0}], E.store_rows("select horizon, delay_s from sig_news_fu"))
    # follow-up recovery after a restart
    E.SEV["pend"].clear(); E.SEV["load"] = False; E.SEV["inj"].clear(); E.SEV["inj_at"].clear()
    px(BOS, 0.28, 0.30, T0 + 1800 + 61 * 60 - 2)
    E.sev_tick(T0 + 1800 + 61 * 60, force=True)
    ok("B after a restart the waiting news is reloaded and its +60 sample still lands",
       sorted(x["horizon"] for x in E.store_rows("select horizon from sig_news_fu")) == [15, 60])


def c_context():
    reset()
    start = T0 + 100 * 60
    E.game_start = lambda e, t=None, x=None: (dt.datetime.fromtimestamp(start, dt.timezone.utc), "book")
    def note(gid, ts, home, away, neutral=False, weather=None, indoor=True):
        e = {"id": gid, "date": dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}
        if weather is not None:
            e["weather"] = weather
        comp = {"venue": {"indoor": indoor, "address": {"city": "Boston", "state": "MA"}}}
        if neutral is not None:
            comp["neutralSite"] = neutral
        teams = [{"homeAway": "home", "team": {"displayName": home}}, {"homeAway": "away", "team": {"displayName": away}}]
        E.sev_note_event("nba", e, comp, teams)
    note("g0", start - 86400 * 2, "Boston Celtics", "Chicago Bulls")           # the Celtics' previous game: 2 days earlier
    note("g1", start - 86400 * 1 - 3600, "Los Angeles Lakers", "Utah Jazz")    # the Lakers played yesterday
    note("g9", start, "Boston Celtics", "Los Angeles Lakers", neutral=False, weather={"temperature": 41, "windSpeed": "12 mph", "displayValue": "Clear"})
    E.signal_events("nba", games(), now=T0)
    r = E.store_rows("select * from sig_ctx")
    ok("C one pre2h row for the game, no more on the next pass", len(r) == 1 and r[0]["phase"] == "pre2h" and
       E.signal_events("nba", games(), now=T0 + 60) == 0 and count("sig_ctx") == 1, r)
    r = r[0]
    ok("C home/away, venue and neutral flag come from ESPN", (r["home_team"], r["away_team"], r["neutral"], r["indoor"], r["venue_city"]) ==
       ("Boston Celtics", "Los Angeles Lakers", 0, 1, "Boston"), r)
    ok("C weather from ESPN's field; fields it does not send stay NULL (precip, a wind that is absent elsewhere)",
       (r["wx_temp"], r["wx_wind"], r["wx_precip"], r["wx_text"]) == (41.0, 12.0, None, "Clear"), r)
    ok("C rest days and back-to-back from the schedule it has seen", r["home_rest"] is not None and abs(r["home_rest"] - 2.0) < 0.1 and r["home_b2b"] == 0
       and r["away_b2b"] == 1, (r["home_rest"], r["home_b2b"], r["away_rest"], r["away_b2b"]))
    ok("C games in the last 7 days is NULL when the record doesn't reach back a week (never a guess)", r["home_g7"] is None and r["away_g7"] is None, (r["home_g7"], r["away_g7"]))
    ok("C travel: home 0 miles; Los Angeles to Boston about 2,600 miles and 3 time zones", r["home_travel_mi"] == 0.0 and 2500 < r["away_travel_mi"] < 2700 and r["away_tz"] == 3 and r["home_tz"] == 0,
       (r["home_travel_mi"], r["away_travel_mi"], r["away_tz"]))
    ok("C the market's bid/ask and book probability for each side sit in the row", (r["home_ticker"], r["away_ticker"], r["home_fair"], r["away_fair"]) ==
       (BOS, "KXNBAGAME-26NOV23LALBOS-LAL", 0.40, 0.60), r)
    E.signal_events("nba", games(), now=start + 60)
    ok("C a 'start' row follows at the start", sorted(x["phase"] for x in E.store_rows("select phase from sig_ctx")) == ["pre2h", "start"])
    ok("C a game outside both windows gets no row", (E.signal_events("nba", games(), now=start - 5 * 3600), count("sig_ctx"))[1] == 2)
    # unknown stays NULL: neutral flag missing, no weather, a team with no travel entry
    reset()
    E.game_start = lambda e, t=None, x=None: (dt.datetime.fromtimestamp(start, dt.timezone.utc), "book")
    note("g9", start, "Boston Celtics", "Los Angeles Lakers", neutral=None, indoor=None)
    E.signal_events("nba", games(), now=T0)
    r = E.store_rows("select * from sig_ctx")[0]
    ok("C neutral-site missing: neutral NULL, and so travel NULL (we do not guess the venue)", r["neutral"] is None and r["away_travel_mi"] is None and r["indoor"] is None, r)
    ok("C no weather sent: all four weather columns NULL", (r["wx_temp"], r["wx_wind"], r["wx_precip"], r["wx_text"]) == (None,) * 4, r)
    reset()
    E.game_start = lambda e, t=None, x=None: (None, None)
    E.signal_events("nba", games(), now=T0)
    ok("C a game with no known start is not given a row", count("sig_ctx") == 0)
    ok("C the static table covers the 3 pro leagues' teams (NFL 32, NBA 30, NHL 32+)", sum(1 for k in E.SEV_GEO) >= 94)


def d_retention():
    reset()
    now = T0 + 400 * 86400
    E.store_x("insert into sig_news(ekey, ts, league) values('old', ?, 'nba')", (T0,))
    E.store_x("insert into sig_news(ekey, ts, league) values('new', ?, 'nba')", (now - 86400,))
    E.store_x("insert into sig_news_fu(news_id, horizon, ts) values(1, 5, ?)", (T0,))
    E.store_x("insert into sig_ctx(game_event, phase, ts) values('e', 'pre2h', ?)", (T0,))
    E._sev_prune(now)
    ok("D rows past a year are dropped, newer ones kept", count("sig_news") == 1 and count("sig_news_fu") == 0 and count("sig_ctx") == 0)
    old = dict(E.SEV["cap"])
    try:
        E.SEV["cap"]["sig_news"] = 3
        for i in range(3):
            E.store_x("insert into sig_news(ekey, ts, league) values(?, ?, 'nba')", (f"k{i}", now - 100 + i))
        E._sev_prune(now)
        ok("D at the ceiling the table is marked full", "sig_news" in E.SEV["full"])
        n = count("sig_news")
        ids = E._sev_write("sig_news", E.SEV_NEWS_COLS, [("z", now, now, "nba", "t", "p", None, "new", None, "Out", 1, None, None, None, None, None, None, None)])
        ok("D a full table accepts no more writes and deletes nothing to make room", ids == [] and count("sig_news") == n)
        E.SEV["cap"]["sig_news"] = 100
        E._sev_prune(now + 1)
        ok("D when room appears writes resume", "sig_news" not in E.SEV["full"])
    finally:
        E.SEV["cap"].update(old)
    # migration on an existing history file: a file that already has the tables (and rows) and one that has none
    p = os.path.join(tempfile.mkdtemp(), "old.db")
    c = sqlite3.connect(p); c.execute("create table legacy(ticker text primary key)"); c.execute("insert into legacy values('x')"); c.commit(); c.close()
    E.SEV["tbl"], db0 = False, E.STORE["db"]
    E.STORE["db"] = None; E.store_open(p)
    ok("D migration: tables are created on an older file, its data untouched", E._sev_tables() and count("legacy") == 1)
    E.store_x("insert into sig_news(ekey, ts, league) values('a', 1, 'nba')")
    E.SEV["tbl"] = False
    ok("D migration: running it again on a file that already has them is a no-op that keeps the rows", E._sev_tables() and count("sig_news") == 1)
    E.STORE["db"].close(); E.STORE["db"] = db0
    E.SEV["tbl"] = True


def e_swallow():
    reset()
    E.game_start = lambda e, t=None, x=None: (dt.datetime.fromtimestamp(T0 + 100 * 60, dt.timezone.utc), "book")
    db = E.STORE["db"]
    E.STORE["db"] = None
    ok("E no history open: 0, no raise", E.signal_events("nba", games(), now=T0) == 0 and E.sev_tick(T0, force=True) == 0)
    E.STORE["db"] = db
    class Broken:
        in_transaction = False
        def execute(self, *a, **k): raise RuntimeError("closed")
    E.STORE["db"] = Broken(); E.SEV["tbl"] = True; E.SEV["load"] = True
    try:
        put_inj(T0, inj("Active"))
        ok("E a broken connection is swallowed", isinstance(E.signal_events("nba", games(), now=T0), int))
        put_inj(T0 + 1800, inj("Out"))
        ok("E ... also with news to write", isinstance(E.signal_events("nba", games(), now=T0 + 1800), int))
    finally:
        E.STORE["db"] = db
    reset()
    ok("E junk games and junk ESPN events are swallowed", E.signal_events("nba", {"e": [None, 5, {"ticker": 3}]}, now=T0) == 0
       and E.signal_events("nba", None, now=T0) == 0 and E.sev_note_event("nba", None, None, None) is None
       and E.sev_note_event("nba", {"id": 1, "date": "bad"}, {}, [{}, {}]) is None)
    E.INJ["nba"] = (T0, {"boston celtics": [None, 5, ("a",)]})
    ok("E junk injury rows are swallowed", isinstance(E.sev_tick(T0, force=True), int))
    old = E._sev_write
    E._sev_write = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        put_inj(T0 + 9000, inj("Active")); put_inj(T0 + 9100, inj("Out"))
        ok("E a failing writer is swallowed", isinstance(E.sev_tick(T0 + 9100, force=True), int))
    finally:
        E._sev_write = old
    reset()
    g, g0 = games(), copy.deepcopy(games())
    E.game_start = lambda e, t=None, x=None: (dt.datetime.fromtimestamp(T0 + 100 * 60, dt.timezone.utc), "book")
    E.signal_events("nba", g, now=T0)
    ok("E the games it was handed (trading inputs) are unchanged", g == g0)
    n = count("sig_ctx")
    E.CFG["sig_shadow"] = False
    try:
        E.SEV["done"].clear()
        ok("E the flag off writes nothing", E.signal_events("nba", games(), now=T0 + 5) == 0 and count("sig_ctx") == n)
    finally:
        E.CFG["sig_shadow"] = True
    e1 = E.single_fee(0.4); E.signal_events("nba", games(), now=T0 + 10)
    ok("E a trading function's output is the same after recording", E.single_fee(0.4) == e1)
    ok("E the price tap hook runs from price_seen_markets without raising", E.price_seen_markets([{"ticker": BOS, "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.42"}]) is None)


def f_unread():
    src = open(os.path.join(REPO, "nfl_combo_planner.py")).read()
    a, b = src.index("# ---- signal events (news + game context"), src.index("# ---- end signal events")
    outside = src[:a] + src[b:]
    pat = r"sig_(news|news_fu|ctx)\b"
    ok("F the engine outside the recorder never mentions the new tables", not re.search(pat, outside))
    inner = src[a:b]
    sel = [m.start() for m in re.finditer(r"select[^\n]*\bfrom\s+(sig_|\{tbl\})", inner, re.I)]
    fns = {inner.rfind("\ndef ", 0, i) for i in sel}
    names = {re.match(r"\ndef (\w+)", inner[i:]).group(1) for i in fns}
    ok("F only the recorder's loader and pruner select from the tables", names <= {"_sev_load", "_sev_prune"}, names)
    other = open(os.path.join(REPO, "watcher", "combo_watcher.py")).read()
    ok("F the watcher never mentions them", not re.search(pat, other))
    ok("F the hooks are one wrapped call each (panel pass, price tap, score read)",
       len(re.findall(r"^\s+signal_events\(code, games\)", src, re.M)) == 1 and src.count("    sev_tick()") == 1 and len(re.findall(r"^\s+sev_note_event\(code, ev, comp, teams\)", src, re.M)) == 1)
    ok("F no new network call inside the block", not re.search(r"requests\.|league_injuries\(|fetch_scores\(|_odds_get", inner))


for n, f in (("a", a_detect), ("b", b_followups), ("c", c_context), ("d", d_retention), ("e", e_swallow), ("f", f_unread)):
    section(n, f)
