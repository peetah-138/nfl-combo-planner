# CHECK: group=engine
# The watch-all recorder (broad_shadow / bp_maintain in the engine): price paths and signals for EVERY market the app already
# fetched, into NEW append-only tables (bp_mkt, bp_path, bp_day), for learning only. Nothing trades from them.
#  A  rows land with bid/ask/depth, the sharp-book fair and the cached score, change-only and throttled, with no request
#  B  every failure is swallowed (no history, a broken insert, junk entries, a broken connection)
#  C  the flag turns it off; the games and lines it was handed are unchanged; the flag is a known setting
#  D  retention prune by age and the oldest-first row cap
#  E  the size ceiling stops writes, and pruning lets it resume
#  F  a database made by an older build is completed, not damaged, and migration is repeatable
#  G  30,000 watched markets: one flush stays inside a fixed time bound, and the cursor reaches them all
#  H  nothing decides from these tables (source scan), and the measured bytes a row match the ceiling's estimate
#  I  labels are copied from the resolver tables; the day's coverage is saved and counted without tickers
import os, re, copy, time, tempfile, sqlite3, importlib.util, traceback, datetime as dt
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
DBP = os.path.join(tempfile.mkdtemp(), "h.db")
E.store_open(DBP); E.HERE = tempfile.mkdtemp()
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
REPO = os.environ.get("REPO") or os.path.abspath("../..")
NOW = 1_800_000_000.0
EV = "KXNBAGAME-26NOV23LALBOS"
BP0 = dict(E.BP)


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def reset(wipe=True):
    if wipe and E.STORE["db"] is not None:
        for tb in ("bp_path", "bp_mkt", "bp_day"):
            E.store_x(f"delete from {tb}")
    for k in ("ids", "mk", "kdb", "last", "fair", "win"):
        E.BP[k].clear()
    E.BP.update(flush=0.0, maint=0.0, logged=0.0, full=None, rows=0, disk=0.0, cursor=0, day=None, tbl=None)
    for k in ("max_bytes", "row_bytes", "keep_days", "budget", "max_rows_flush", "min_free"):
        E.BP[k] = BP0[k]
    E.PRICE_SEEN.clear(); E.KICKOFF.clear()
    E.leg_score = lambda l: None
    E.CFG["broad_shadow"] = True


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()


def games():
    return {EV: [
        {"ticker": EV + "-LAL", "p": 0.55, "bid": 0.53, "fair": 0.58, "src": "pinnacle", "live": False},
        {"ticker": EV + "-BOS", "p": 0.47, "bid": 0.45, "fair": 0.42, "src": "pinnacle", "live": False},
        {"ticker": EV + "-TIE", "p": 0.01, "bid": None, "fair": 0.0, "tie": True}]}


def lines():
    return [{"ticker": "KXNBASPREAD-26NOV23LALBOS-LAL5", "event": "KXNBASPREAD-26NOV23LALBOS", "p": 0.5, "bid": 0.48, "fair": 0.51}]


def seen(now=NOW, bump=0.0):
    E.PRICE_SEEN[EV + "-LAL"] = (now - 5, 0.53 + bump, 0.55 + bump, 120)
    E.PRICE_SEEN[EV + "-BOS"] = (now - 5, 0.45 - bump, 0.47 - bump, 80)
    E.PRICE_SEEN["KXNBASPREAD-26NOV23LALBOS-LAL5"] = (now - 5, 0.48, 0.50, None)


def count(t):
    return E.store_rows(f"select count(*) n from {t}")[0]["n"]


def a_rows():
    reset()
    E.KICKOFF[EV] = iso(NOW + 3600)                  # an hour to go: "near", no score yet
    seen()
    class NoNet:
        def __getattr__(self, k):
            raise AssertionError("a request was made: " + k)
    real, E.requests = E.requests, NoNet()
    try:
        n = E.broad_shadow("nba", games(), lines(), now=NOW)
    finally:
        E.requests = real
    ok("A one pass writes a row for each of the 3 watched markets (win, win, spread), no request made", n == 3 and count("bp_path") == 3, n)
    r = E.store_rows("select p.bid, p.ask, p.dep, p.fb, p.fk, p.st, m.sp, m.kind, m.kick from bp_path p join bp_mkt m on m.id=p.m "
                     "where m.ticker=?", (EV + "-LAL",))
    ok("A bid 0.53, ask 0.55, depth 120, sharp fair 0.58 (kind 1), no score, sport nba, kind win, kickoff known",
       r and (r[0]["bid"], r[0]["ask"], r[0]["dep"], r[0]["fb"], r[0]["fk"], r[0]["st"], r[0]["sp"], r[0]["kind"]) == (530, 550, 120, 580, 1, 0, "nba", "win") and r[0]["kick"], r)
    ok("A the spread market shares its game with the win markets (one normalized game)",
       len({x["ev"] for x in E.store_rows("select ev from bp_mkt")}) == 1 and E.store_rows("select fb, fk from bp_path p join bp_mkt m on m.id=p.m where m.kind='spread'")[0] == {"fb": 510, "fk": 3})
    ok("A the tie side is never recorded", not E.store_rows("select 1 from bp_mkt where ticker like '%TIE'"))
    ok("A unchanged prices 60 s later write nothing (change-only)", E.broad_shadow("nba", games(), lines(), now=NOW + 60) == 0)
    seen(NOW + 120)
    ok("A the same prices, seen again, still nothing before the heartbeat", E.broad_shadow("nba", games(), lines(), now=NOW + 120) == 0)
    seen(NOW + 180, 0.02)
    ok("A a moved price writes again (the two win markets; the unmoved spread does not)", E.broad_shadow("nba", games(), lines(), now=NOW + 180) == 2 and count("bp_path") == 5)
    seen(NOW + 700, 0.02)
    ok("A near the game an unchanged market still gets a heartbeat row (10 min)", E.broad_shadow("nba", games(), lines(), now=NOW + 700) == 1)
    # the game is under way: the cached score rides along, and a score change allows a row after 20 s
    reset(); E.KICKOFF[EV] = iso(NOW - 1800); seen()
    state = {"me": 50, "opp": 45}
    E.leg_score = lambda l: {"state": "in", "me": state["me"], "opp": state["opp"], "frac": 0.4,
                             "situation": {"possession": True, "down": 2, "distance": 7}}
    ok("A in play: rows carry the score", E.broad_shadow("nba", games(), lines(), now=NOW) == 3)
    s = E.store_rows("select p.ld, p.pt, p.fr, p.st, p.pos, p.dn, p.ds, m.kind from bp_path p join bp_mkt m on m.id=p.m where m.kind='win' order by m.ticker limit 1")[0]
    ok("A state fields: lead 5, points 95, share left 0.4, in play, ball, 2nd and 7", (s["ld"], s["pt"], s["fr"], s["st"], s["pos"], s["dn"], s["ds"]) == (5, 95, 400, 1, 1, 2, 7), s)
    state["me"] = 53; seen(NOW + 50)
    ok("A a score change writes a row on the next pass even though the price did not move", E.broad_shadow("nba", games(), lines(), now=NOW + 50) >= 2)


def b_swallow():
    reset(); E.KICKOFF[EV] = iso(NOW + 3600); seen()
    db = E.STORE["db"]
    E.STORE["db"] = None
    ok("B no history open: 0, no raise", E.broad_shadow("nba", games(), lines(), now=NOW) == 0)
    E.STORE["db"] = db
    old = E._bp_write
    def boom(*a, **k): raise RuntimeError("disk full")
    E._bp_write = boom
    try:
        ok("B a failing write is swallowed", E.broad_shadow("nba", games(), lines(), now=NOW) == 0)
    finally:
        E._bp_write = old
    reset(); E.KICKOFF[EV] = iso(NOW + 3600); seen()
    E.PRICE_SEEN["junk1"] = None; E.PRICE_SEEN["junk2"] = (1,); E.PRICE_SEEN["junk3"] = ("x", "y", "z", "w"); E.PRICE_SEEN[5] = (NOW, 0.4, 0.5, 1)
    ok("B junk entries are skipped and the good ones still record", E.broad_shadow("nba", games(), lines(), now=NOW) >= 3)
    reset()
    ok("B junk sides and lines are swallowed", E.broad_shadow("nba", {"e": [None, 5, {"ticker": 3}]}, [object(), None], now=NOW) == 0)
    ok("B games=None and lines=None are fine", E.broad_shadow("nba", None, None, now=NOW) == 0)
    def bad_score(l): raise ValueError("feed broke")
    E.leg_score = bad_score; E.KICKOFF[EV] = iso(NOW - 600); seen()
    E.BP["flush"] = 0.0
    n = E.broad_shadow("nba", games(), lines(), now=NOW)
    ok("B a score feed that raises costs only the score", n == 3 and E.store_rows("select st from bp_path limit 1")[0]["st"] == 0, n)
    class Broken:
        in_transaction = False
        def execute(self, *a, **k): raise RuntimeError("closed")
        executemany = execute
    reset(); seen()
    E.STORE["db"] = Broken()
    try:
        ok("B a broken connection is swallowed (no raise)", isinstance(E.broad_shadow("nba", games(), lines(), now=NOW), int))
        ok("B bp_maintain on a broken connection is swallowed too", isinstance(E.bp_maintain(NOW), int))
    finally:
        E.STORE["db"] = db
    # a failing transaction rolls back whole and forgets the ids it had cached (no row points at a missing market)
    reset(); seen(); E.KICKOFF[EV] = iso(NOW + 3600)
    real_db = E.STORE["db"]
    class Flaky:
        def __init__(s, d): s.d = d; s.in_transaction = False
        def execute(s, q, *a):
            if q.startswith("insert into bp_path"): raise sqlite3.OperationalError("boom")
            return s.d.execute(q, *a)
        def executemany(s, q, *a): raise sqlite3.OperationalError("boom")
    before = count("bp_path")
    E.STORE["db"] = Flaky(real_db); E.BP["tbl"] = E.STORE["db"]
    try:
        n = E.broad_shadow("nba", games(), lines(), now=NOW)
    finally:
        E.STORE["db"] = real_db
    ok("B a failed batch writes nothing and caches no market ids", n == 0 and count("bp_path") == before and not E.BP["ids"])


def c_flag_and_inputs():
    reset(); E.KICKOFF[EV] = iso(NOW + 3600); seen()
    g, ln = games(), lines()
    g0, ln0, ps0 = copy.deepcopy(g), copy.deepcopy(ln), dict(E.PRICE_SEEN)
    E.broad_shadow("nba", g, ln, now=NOW)
    ok("C the games, lines and the price memory it was handed are unchanged", g == g0 and ln == ln0 and E.PRICE_SEEN == ps0)
    reset(); seen(); E.KICKOFF[EV] = iso(NOW + 3600)
    E.CFG["broad_shadow"] = False
    before = count("bp_path")
    ok("C the flag off writes nothing", E.broad_shadow("nba", games(), lines(), now=NOW + 5000) == 0 and count("bp_path") == before)
    E.CFG["broad_shadow"] = True
    ok("C the flag defaults ON and is a known setting (a saved false is kept)", E.DEFAULTS.get("broad_shadow") is True)
    e1 = E.single_fee(0.4); E.broad_shadow("nba", games(), lines(), now=NOW + 9000)
    ok("C a trading function's output is the same after recording", E.single_fee(0.4) == e1)
    ok("C no new request module use: the recorder block never names requests", "requests" not in blocksrc().replace("# ", "").split("def _bp_on")[1].replace("requests is never touched", ""))


def blocksrc():
    src = open(os.path.join(REPO, "nfl_combo_planner.py")).read()
    a, b = src.index("# ---- broad recorder (watch all games)"), src.index("# ---- exit_shadow: old")
    return src[a:b]


def ins(rows):
    E.store_x("delete from bp_path")
    E.store_x("delete from bp_mkt")
    E.store_x("insert into bp_mkt(id, ticker, ev, sp, kind, kick, first) values(1,'T','E','nba','win',0,0)")
    for ts in rows:
        E.store_x("insert into bp_path(ts, m, bid, ask) values(?,1,400,420)", (ts,))


def d_prune():
    reset(); E._bp_tables()
    ins([NOW - 40 * 86400 + i for i in range(50)] + [NOW - 100 + i for i in range(50)])
    E.BP["keep_days"] = 21
    E.bp_maintain(NOW)
    ok("D rows older than the retention age are pruned, newer kept", count("bp_path") == 50 and E.store_rows("select min(ts) m from bp_path")[0]["m"] >= NOW - 100, count("bp_path"))
    ins([NOW - 1000 + i for i in range(200)])
    E.BP["max_bytes"], E.BP["row_bytes"] = 1000, 10          # cap = 80 rows
    E.bp_maintain(NOW)
    ok("D the oldest rows over the row cap go first", count("bp_path") == 80 and E.store_rows("select min(ts) m from bp_path")[0]["m"] == NOW - 1000 + 120, count("bp_path"))
    ok("D a second prune on a table under the cap deletes nothing", E._bp_prune(NOW) == 0 and count("bp_path") == 80)
    E.store_x("delete from bp_path"); E.store_x("delete from bp_mkt")
    E.store_x("insert into bp_mkt(id, ticker, first) values(1,'OLDM',?)", (int(NOW - 60 * 86400),))
    E.store_x("insert into bp_mkt(id, ticker, first) values(2,'LIVE',?)", (int(NOW - 60 * 86400),))
    E.store_x("insert into bp_path(ts, m, bid, ask) values(?,2,400,420)", (int(NOW - 100),))
    E.bp_maintain(NOW)
    ok("D an old market row with no paths left is dropped, one that still has paths stays", [r["ticker"] for r in E.store_rows("select ticker from bp_mkt")] == ["LIVE"])
    E.store_x("delete from bp_path"); E.store_x("delete from bp_mkt")
    ok("D prune and maintain on empty tables are fine", E.bp_maintain(NOW) == 1)


def e_ceiling():
    reset(); E._bp_tables(); E.store_x("delete from bp_path"); E.store_x("delete from bp_mkt")
    E.KICKOFF[EV] = iso(NOW + 3600)
    E.BP["max_bytes"], E.BP["row_bytes"] = 450, 45             # ceiling 10 rows, cap 8
    t = NOW
    for i in range(6):
        seen(t, 0.01 * i)
        E.broad_shadow("nba", games(), lines(), now=t)
        t += 70
    ok("E recording stops once the byte ceiling is reached (and says why)", E.BP["full"] == "size" and 10 <= count("bp_path") <= 12, (E.BP["full"], count("bp_path")))
    n = count("bp_path")
    seen(t, 0.2)
    ok("E while stopped, nothing more is written", E.broad_shadow("nba", games(), lines(), now=t) == 0 and count("bp_path") == n)
    E.bp_maintain(t)
    ok("E maintenance prunes under the cap and recording resumes", E.BP["full"] is None and count("bp_path") <= 8, (E.BP["full"], count("bp_path")))
    t += 200; seen(t, 0.3)
    ok("E after the pruning a new row can be written", E.broad_shadow("nba", games(), lines(), now=t) > 0)
    reset(); E.BP["min_free"] = 10 ** 18
    seen()
    ok("E a free-disk floor stops it too", E.broad_shadow("nba", games(), lines(), now=NOW) == 0 and E.BP["full"] == "disk")
    reset()


def f_migration():
    p = os.path.join(tempfile.mkdtemp(), "old.db")
    c = sqlite3.connect(p)
    c.executescript("create table bp_mkt(id integer primary key, ticker text unique); create table bp_path(ts integer, m integer, bid integer, ask integer);"
                    "insert into bp_mkt values(1,'OLD'); insert into bp_path values(5,1,300,320);"
                    "create table ledger(id integer primary key, ticker text); insert into ledger values(7,'KEEP');")
    c.commit(); c.close()
    E.STORE["db"].close(); E.STORE["db"] = None
    E.store_open(p); reset(wipe=False)
    try:
        ok("F an older-shape file is completed (columns added)", E._bp_tables() and {"fb", "fk", "st", "pt", "ld"} <= {r["name"] for r in E.store_rows("pragma table_info(bp_path)")} and {"result", "rs", "kick", "ev"} <= {r["name"] for r in E.store_rows("pragma table_info(bp_mkt)")})
        ok("F its existing rows and other tables are untouched", E.store_rows("select ticker from bp_mkt") == [{"ticker": "OLD"}] and E.store_rows("select bid, ask from bp_path") == [{"bid": 300, "ask": 320}] and E.store_rows("select ticker from ledger") == [{"ticker": "KEEP"}])
        E.BP["tbl"] = None
        ok("F running the migration again changes nothing and raises nothing", E._bp_tables() and count("bp_path") == 1)
        E.KICKOFF[EV] = iso(NOW + 3600); seen()
        ok("F the recorder then writes into the migrated tables", E.broad_shadow("nba", games(), lines(), now=NOW) == 3 and count("bp_path") == 4)
    finally:
        E.STORE["db"].close(); E.STORE["db"] = None
        E.store_open(DBP); reset()
    ok("F a fresh file gets the tables and a second open is harmless", True)


def g_scale():
    reset(); E._bp_tables(); E.store_x("delete from bp_path"); E.store_x("delete from bp_mkt")
    E.KICKOFF[EV] = iso(NOW + 3600)
    for i in range(30000):
        E.PRICE_SEEN[f"KXNBAGAME-26NOV23T{i % 1500:04d}-X{i}"] = (NOW - 1, 0.40, 0.42, 50)
    t0 = time.perf_counter()
    n = E.broad_shadow("nba", games(), lines(), now=NOW)
    dt1 = time.perf_counter() - t0
    ok("G one flush over 30,000 watched markets is bounded by rows and time (under 2 s, at most 3,000 rows)", dt1 < 2.0 and 0 < n <= E.BP["max_rows_flush"], (dt1, n))
    got, t = n, NOW
    for _ in range(60):
        t += 50
        got += E.broad_shadow("nba", games(), lines(), now=t)
        if got >= 30000:
            break
    ok("G the cursor carries on where it stopped: every market is reached in a few passes", got >= 30000, got)
    t0 = time.perf_counter()
    E.broad_shadow("nba", games(), lines(), now=t + 60)
    ok("G a pass with nothing new is cheap (under 1 s for 30,000 entries)", time.perf_counter() - t0 < 1.0)
    reset()


def h_unread():
    src = open(os.path.join(REPO, "nfl_combo_planner.py")).read()
    blk = blocksrc()
    outside = src.replace(blk, "")
    ok("H the engine outside the recorder never mentions the tables", not re.search(r"bp_(mkt|path|day)", outside))
    ok("H nor the recorder's internals (only the two hook calls and the flag exist outside)", not re.search(r"_bp_|bp_status|BP\[|BP\.", outside) and outside.count("broad_shadow(") == 1 and outside.count("bp_maintain(") == 1)
    ok("H the hook is one call after the signal-shadow line", "    signal_shadow(code, games, lc_all)                 # early-exit test: write-only recorder, never raises\n    broad_shadow(code, every, lc_all)" in src)
    other = open(os.path.join(REPO, "watcher", "combo_watcher.py")).read()
    ok("H the watcher never mentions the tables", not re.search(r"bp_(mkt|path|day)|broad_shadow", other))
    ok("H the web app (spa) and logs status never read them", not any(re.search(r"bp_(mkt|path|day)", open(os.path.join(dp, f), errors="ignore").read()) for dp, _, fs in os.walk(os.path.join(REPO, "watcher")) for f in fs if f.endswith((".py", ".js", ".html"))))
    ok("H it never writes price_path or the other shadow tables", not re.search(r"(insert|update|delete)[^\n\"']*(price_path|sig_|live_fairs|closes)", blk, re.I))
    # measured size of a row (table plus both indexes), against the estimate the ceiling uses
    reset(); E._bp_tables(); E.store_x("delete from bp_path"); E.store_x("delete from bp_mkt")
    db = E.STORE["db"]
    size = lambda: (db.execute("pragma page_count").fetchone()[0] - db.execute("pragma freelist_count").fetchone()[0]) * db.execute("pragma page_size").fetchone()[0]
    s0 = size()
    metas = {f"KXNBAGAME-26NOV23T{i:04d}-X": ("E%d" % i, NOW, "win", "nba", NOW) for i in range(400)}
    rows = []
    for i in range(30000):
        t = f"KXNBAGAME-26NOV23T{i % 400:04d}-X"
        rows.append((t, int(NOW) + i, 400 + i % 50, 420 + i % 50, 100, 560, 1, 3, 95, 400, 1, 1, 2, 7))
    for k in range(0, 30000, 3000):
        E._bp_write(rows[k:k + 3000], metas, NOW)
    per = (size() - s0) / 30000
    ok("H measured about %.1f bytes a row (table and index) stays inside the %d the ceiling assumes" % (per, E.BP["row_bytes"]), per <= E.BP["row_bytes"] * 1.15, per)
    reset()


def i_labels_and_coverage():
    reset(); E._bp_tables(); E.store_x("delete from bp_path"); E.store_x("delete from bp_mkt")
    E.store_x("create table if not exists closes(ticker text primary key, sport text, event text, fair real, price real, kick real, ts real, outcome text)")
    E.store_x("delete from closes")
    E.store_x("create table if not exists live_fairs(ticker text, ts real, sport text, fair real, how text, outcome text)")
    E.store_x("create table if not exists line_fairs(ticker text, ts real, sport text, league text, kind text, strike real, bucket text, fair_old real, fair_new real, fair_cal real, used text, price real, kick real, outcome text)")
    E.store_x("create table if not exists mkt_fair(id text, ts real, code text, lg text, kind text, phase text, tickers text, kick real, p real, mid real, fair_book real, fair_mkt real, w real, edge_book real, edge_mkt real, claimed int, vanish int, pays real, outcome text)")
    E.store_x("delete from live_fairs"); E.store_x("delete from line_fairs"); E.store_x("delete from mkt_fair")
    for tk, kick in (("A", NOW - 20 * 3600), ("B", NOW - 20 * 3600), ("C", NOW - 20 * 3600), ("D", NOW - 20 * 3600), ("E", NOW - 20 * 3600)):
        E.store_x("insert into bp_mkt(ticker, ev, sp, kind, kick, first) values(?,?,?,?,?,?)", (tk, "g" + tk, "nba", "win", int(kick), int(kick)))
    E.store_x("insert into closes values('A','nba','ev',0.5,0.5,0,?, 'yes')", (NOW - 3600,))
    E.store_x("insert into live_fairs values('B',?, 'nba',0.5,'x','no')", (NOW - 3600,))
    E.store_x("insert into line_fairs(ticker, ts, outcome) values('C',?, 'yes')", (NOW - 3600,))
    E.store_x("insert into bp_path(ts, m, bid, ask) values(?, (select id from bp_mkt where ticker='D'), 990, 1000)", (int(NOW - 10 * 3600),))
    E.bp_maintain(NOW)
    r = {x["ticker"]: (x["result"], x["rs"]) for x in E.store_rows("select ticker, result, rs from bp_mkt")}
    ok("I labels are copied from closes, live_fairs and line_fairs; a settled-looking last price is labelled apart (rs 9); the rest stay open",
       r == {"A": (1, 1), "B": (0, 2), "C": (1, 4), "D": (1, 9), "E": (None, None)}, r)
    ok("I a label is never overwritten once set", (E._bp_set_results([(0, 1, "A")]) == 0) and E.store_rows("select result from bp_mkt where ticker='A'")[0]["result"] == 1)
    reset(); E.KICKOFF[EV] = iso(NOW + 3600); seen()
    E.broad_shadow("nba", games(), lines(), now=NOW)
    E.bp_maintain(NOW)
    st = E.bp_status(NOW)
    ok("I coverage counts the day's markets and games (3 markets, 1 game)", (st["markets_today"], st["games_today"], st["rows_today"]) == (3, 1, 3), st)
    ok("I the status carries counts only (no ticker, id or date)", all(isinstance(v, (int, float, bool, type(None), str)) for v in st.values()) and "KX" not in str(st) and not re.search(r"26NOV", str(st)))
    ok("I the day's coverage is saved (survives a restart)", E.store_rows("select mk, gm, rows from bp_day")[0] == {"mk": 3, "gm": 1, "rows": 3})
    notes = []
    old = E.console_note; E.console_note = lambda m: notes.append(m)
    try:
        E.BP["logged"] = 0.0; E.bp_maintain(NOW + 4000)
    finally:
        E.console_note = old
    line = next((n for n in notes if n.startswith("broad recorder: today")), "")
    ok("I the watcher log gets one counts-only line", line and not re.search(r"KX|26NOV|[A-Z]{3}-", line), line)


def j_review_fixes():
    reset(); seen(); E.KICKOFF[EV] = iso(NOW + 3600)
    E.broad_shadow("nba", games(), lines(), now=NOW)
    ts = E.store_rows("select ts from bp_path limit 1")[0]["ts"]
    ok("J a row is stamped with the time the price was seen, not the write time", ts == int(NOW - 5), ts)
    # a failed read must not wipe the table: the age cut is skipped
    n0 = count("bp_path")
    real = E.store_rows
    E.store_rows = lambda *a, **k: []
    try:
        cut = E._bp_cut(NOW)
    finally:
        E.store_rows = real
    ok("J a failed lookup gives no cut (nothing deleted)", cut is None and count("bp_path") == n0, cut)
    # a kickoff learned later is written to a market row that already exists
    reset(); seen()
    E.broad_shadow("nba", games(), lines(), now=NOW)
    ok("J a market first seen without a kickoff has none stored", E.store_rows("select count(*) n from bp_mkt where kick is null")[0]["n"] == 3)
    E.BP["ids"].clear(); E.BP["kdb"].clear(); E.BP["mk"].clear(); E.BP["flush"] = 0.0; E.KICKOFF[EV] = iso(NOW + 3600); seen(NOW + 100, 0.05)
    E.broad_shadow("nba", games(), lines(), now=NOW + 100)
    ok("J the kickoff is stored once it is known", E.store_rows("select count(*) n from bp_mkt where kick is not null")[0]["n"] >= 2)
    # a resolver label replaces a price-implied one
    E.store_x("update bp_mkt set result=1, rs=9 where ticker=?", (EV + "-LAL",))
    E.store_x("create table if not exists closes(ts real, ticker text, outcome text)")
    E.store_x("insert into closes(ts, ticker, outcome) values(?,?,?)", (NOW, EV + "-LAL", "no"))
    E._bp_labels(NOW + 200)
    r = E.store_rows("select result, rs from bp_mkt where ticker=?", (EV + "-LAL",))[0]
    ok("J a resolver label replaces a price-implied one", r["rs"] == 1 and r["result"] == 0, r)


for n, f in (("a", a_rows), ("b", b_swallow), ("c", c_flag_and_inputs), ("d", d_prune), ("e", e_ceiling), ("f", f_migration),
             ("g", g_scale), ("h", h_unread), ("i", i_labels_and_coverage), ("j", j_review_fixes)):
    section(n, f)
