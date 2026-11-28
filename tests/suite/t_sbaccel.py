# CHECK: group=engine
# Smart Buy, faster evidence (issue #137, 'accelerate'): every priced market scored on paper ('universe'), the paper
# book of graduated stakes, the backfill from history, and borrowing sooner (stricter only). All paper: no panel pick,
# stake, skip or sale changes, nothing makes a new request (the fake network counts every call), temp files only.
import os, time, tempfile, importlib.util, json, copy, random, inspect
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.MAIN_SAVED = os.path.join(E.HERE, "main.json"); E.SB_DIAL_FILE = os.path.join(E.HERE, "sb.json")
E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json"); E.LINE_EDGE_FILE = os.path.join(E.HERE, "le.json")
E.leg_score = lambda l: None
E.CFG.update(take_profit=0, lock_trail=True, smart_sell=True, ride=2, panel_budget=40)
E.SMART_CACHE.update(at=time.time() + 1e6, d={})
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
CALLS = []


class NoNet:
    RequestException = E.requests.RequestException

    def __getattr__(self, name):
        def call(*a, **k):
            CALLS.append((name, a[:1]))
            raise E.requests.RequestException("no network in this test")
        return call


E.requests = NoNet()


def dial(d):
    E.save_json(E.SB_DIAL_FILE, d)
    E.SB_GATE.update(dial=None, dial_at=0)


TAG = time.strftime("%y%b%d", time.gmtime(now)).upper()


def side(i, fair, p, live=False, src="pinnacle", lg="NBA"):
    t = f"KX{lg}GAME-{TAG}U{i:03d}-A"
    return {"ticker": t, "event": t.rsplit("-", 1)[0], "fair": fair, "p": p, "src": src, "live": live, "pick": f"T{i}"}


# ---- 1. the universe: what is stashed, from the panel look's own games, as new dicts
games = {"E1": [side(1, 0.60, 0.50), side(2, 0.40, 0.52)],            # a clear edge (cand); the other side none
         "E2": [side(3, 0.53, 0.50), side(4, 0.47, 0.49)],            # a small edge (wide)
         "E3": [side(5, 0.70, 0.50, src=None)],                       # Kalshi's own price: no fair chance
         "E4": [side(6, 0.62, 0.50, live=True), side(7, 0.60, 0.50)],  # a game under way, priced live
         "E5": [dict(side(8, 0.15, 0.05))]}                            # under the panel's 20% floor
for x in games["E4"][1:]:
    x.pop("live")
snap = copy.deepcopy(games)
E.KICKOFF.clear()
E.sb_universe_stash("nba", games, {"E4"})
pool = E.SB_UNI["pool"]["nba"][1]
by = {c["legs"][0]["ticker"][-6:-2]: c for c in pool}
ok("the stash never changes the panel look's games", games == snap)
ok("a clear edge is graded 'cand' (passes the panel's own rule), a small one 'wide'",
   by.get("U001", {}).get("grade") == "cand" and by.get("U003", {}).get("grade") == "wide")
ok("no edge, Kalshi's own price and a long shot under 20% are left out", not {"U002", "U004", "U005", "U008"} & set(by))
ok("a game under way: only its side priced live (never its pre-game chance)", "U006" in by and by["U006"]["live"] and "U007" not in by)
same = [x for x in E.single_candidates(snap, live_ok={"E4"})]
ok("'cand' is exactly single_candidates' own rule", {x["ticker"] for x in same if x["ticker"][-6:-2] != "U007"}   # a live game's sides are all priced live in panel_collect
   == {c["legs"][0]["ticker"] for c in pool if c["grade"] == "cand"})

# line_candidates: its answer is unchanged; every strike it priced with an edge is stashed
DAY = time.strftime("%y%b%d", time.gmtime(now + 5 * 3600)).upper()   # the event's own date must be the game's day (#482)
E.line_markets = lambda code: [{"ticker": f"KXNBASPREAD-{DAY}BOSNYK-BOS{k}", "event_ticker": f"KXNBASPREAD-{DAY}BOSNYK",
                                "kind": "spread", "floor_strike": k - 0.5, "yes_sub_title": f"Boston Celtics wins by over {k - 0.5}",
                                "yes_ask_dollars": "0.50"} for k in (4, 5, 6)]
start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 5 * 3600))
E.espn_lines = lambda code: {"g": {"home_abbr": "NYK", "away_abbr": "BOS", "home": "New York Knicks", "away": "Boston Celtics",
                                   "spread_home": 4.5, "total": 220, "start": start}}
FAIRS = {3.5: 0.60, 4.5: 0.535, 5.5: 0.45}
E.line_fair = lambda code, kind, line, home, g: FAIRS[line]
E._line_pick_model = lambda code, m, line, home, g, fair, p: (fair, None)
got = E.line_candidates("nba")
ok("line_candidates still answers with only the strikes that clear the bar", [x["ticker"][-4:] for x in got] == ["BOS4"])
ls = E.SB_UNI["lines"]["nba"][1]
ok("...and stashes every strike it priced with an edge, graded by that same bar",
   sorted((x["ticker"][-4:], x["cand"]) for x in ls) == [("BOS4", True), ("BOS5", False)])
E.sb_universe_stash("nba", games, {"E4"})
lines = [c for c in E.SB_UNI["pool"]["nba"][1] if c["kind"] == "line"]
ok("the strikes join the pool as spreads/totals, before the start only", len(lines) == 2 and all(c["kick"] > now for c in lines))

# ---- the paper scoring pass: bounded, cadenced, skips what the panel just scored, never raises
E._exit_shadow_table()
E.store_x("delete from exit_shadow")
real_sim = E.simulate_exit
big = [{"id": f"single:KXNBAGAME-{TAG}B{i:04d}-A", "kind": "single", "code": "nba", "grade": "wide", "live": False,
        "edge": 0.01, "price": 0.5, "chance": 0.52, "kick": now + 3600 * (1 + i % 20),
        "legs": [{"ticker": f"KXNBAGAME-{TAG}B{i:04d}-A", "event": f"KXNBAGAME-{TAG}B{i:04d}", "p": 0.5, "fair": 0.52}]}
       for i in range(2000)]
E.SB_UNI["pool"] = {"nba": (now, big)}
E.SB_UNI["seen"].clear()
t0 = time.perf_counter()
n1 = E.smart_buy_universe(now=now)
secs = time.perf_counter() - t0
ok(f"one pass stays inside its 0.15 s budget of simulation (wrote {n1} rows in {secs:.3f} s)", 0 < n1 < 2000 and secs < 0.6)
first = E.store_rows("select min(kick) k from exit_shadow where source='universe'")[0]["k"]
ok("the nearest games are scored first", first is not None and first < now + 2 * 3600)
n2 = E.smart_buy_universe(now=now + 1)
ok("the next pass scores markets not scored yet (it staggers across passes)", n2 > 0 and
   E.store_rows("select count(distinct tickers) n from exit_shadow")[0]["n"] == n1 + n2)
E.SB_UNI["pool"] = {"nba": (now, [big[0], big[20], big[40]])}      # the first ones scored (games in an hour)
ok("a market scored in the last 30 min (near its game) is not scored again", E.smart_buy_universe(now=now + 60) == 0)
k = json.dumps([big[1500]["legs"][0]["ticker"]])
E.SB_UNI["pool"] = {"nba": (now, [big[1500]])}
E.SB_UNI["seen"].pop(k, None)
E.SB_CACHE.setdefault("tk", {})[k] = now
ok("a market the panel or a Buy idea scored just now is skipped", E.smart_buy_universe(now=now + 60) == 0)
E.SB_UNI["pool"] = {"nba": (now - 3600, big[1600:1610])}
ok("a pool older than 15 minutes is not scored (stale prices)", E.smart_buy_universe(now=now) == 0)
E.SB_UNI["pool"] = {"nba": (now, [dict(big[1700], kick=now - 60)])}
ok("a pre-game market whose game has started since is not scored", E.smart_buy_universe(now=now) == 0)
E.simulate_exit = lambda *a, **k: 1 / 0
E.SB_UNI["pool"] = {"nba": (now, big[1800:1805])}
ok("a broken simulator never raises out of the pass", E.smart_buy_universe(now=now) == 0)
E.simulate_exit = real_sim
row = E.store_rows("select * from exit_shadow where source='universe' limit 1")[0]
ok("universe rows carry the verdict columns (skip, strict, pays), the grade and old=0 for 'wide'",
   row["pays"] and row["strict"] is not None and row["grade"] == "wide" and row["old"] == 0 and row["cand"].startswith("universe:"))
ok("no request of any kind was made", not CALLS)

# ---- 'no change to any panel pick, stake, skip or sale': the gate's answers with the universe on vs off
EVS = {}


def fake_sim(spec_, **k):
    return {"ev": EVS.get(spec_["id"], 0.5), "route": "hold", "p_exit": 0.3, "win": 0.5, "p_sell": 0.3,
            "exit_profit": 0.5, "hold_profit": 0.4, "exit_mins": 30.0}


E.simulate_exit = fake_sim


def cand(i, ev, lg="NBA"):
    t = f"KX{lg}GAME-{TAG}P{i:03d}-A"
    EVS["single:" + t] = ev
    return {"id": "single:" + t, "kind": "single", "code": lg.lower(), "chance": 0.55, "ret": 0.08, "price": 0.5,
            "kick": now + 3 * 3600, "last": now + 3 * 3600, "why": "t",
            "legs": [{"ticker": t, "event": t.rsplit("-", 1)[0], "p": 0.5, "fair": 0.55}]}


E.sizing_base = lambda *a, **k: (300.0, {})
E.spent_earlier_today = lambda now=None: 0.0
E.account_events = lambda: set()
E.day_items = lambda day: []
E.sport_pay_index = lambda: {}
rng = random.Random(137)
diff = 0
for trial in range(60):
    dial({lg: {"n": rng.choice([0, 12, 30, 80]), "level": rng.randint(0, 6), "own": True, "early": rng.randint(0, 3),
              "early_blk": 1}
          for lg in ("nba", "all") if rng.random() < 0.8})
    pool_ = [cand(trial * 20 + i, rng.uniform(-1, 1)) for i in range(rng.randint(1, 10))]
    E.PANEL_POOL.clear()
    E.PANEL_POOL["nba"] = (now, copy.deepcopy(pool_))
    E.SB_GATE.setdefault("sims", {}).clear()
    E.SB_UNI_ON = False
    off = (json.dumps(E.build_panel(now=now)["items"], sort_keys=True), json.dumps(E.smart_buy_filter(copy.deepcopy(pool_), now), sort_keys=True))
    E.SB_UNI_ON = True
    E.SB_UNI["pool"] = {"nba": (now, [dict(c, grade="cand", live=False, edge=0.05) for c in copy.deepcopy(pool_)])}
    E.SB_UNI["seen"].clear()
    E.smart_buy_universe(now=now)                     # universe rows for the very same markets
    E.PANEL_POOL["nba"] = (now, copy.deepcopy(pool_))
    E.SB_GATE.setdefault("sims", {}).clear()
    on = (json.dumps(E.build_panel(now=now)["items"], sort_keys=True), json.dumps(E.smart_buy_filter(copy.deepcopy(pool_), now), sort_keys=True))
    diff += on != off
ok("60 random panels: build_panel and smart_buy_filter are byte-identical with the universe on vs off", diff == 0)
ideas = [{"idea_id": "i1", "legs": [big[0]["legs"][0]["ticker"]]}]
dial({"nba": {"n": 50, "level": 8, "own": True}})
E.store_x("update exit_shadow set ev=-5 where source='universe'")
ok("Buy ideas are judged only on their own ('idea') checks: universe rows for the same market change nothing",
   E.smart_buy_ideas_gate(ideas, now)[0] == ideas)
src = open("wahome/engine.py", encoding="utf-8").read()
readers = sorted({n for n, f in inspect.getmembers(E, inspect.isfunction)
                  if "exit_shadow" in (inspect.getsource(f) if f.__module__ == E.__name__ else "")})
ok("only Smart Buy's own code reads exit_shadow (no sale, hedge, cash-out or panel path)",
   all(n.startswith(("smart_buy", "sb_", "_sb", "exit_", "_exit_shadow", "price_prune")) for n in readers) and readers
   or print("readers:", readers))
pc = inspect.getsource(E.panel_collect)
ok("panel_collect's only new step is the stash, after its candidates are final",
   pc.index("sb_universe_stash(") > pc.index("PANEL_POOL[code] = (time.time(), cands)"))
wsrc = open("wtest/combo_watcher.py", encoding="utf-8").read() if os.path.exists("wtest/combo_watcher.py") else \
    open(os.path.join(os.environ.get("REPO", "."), "watcher/combo_watcher.py"), encoding="utf-8").read()
import re
sl = wsrc[wsrc.index("def shadow_loop("):wsrc.index("def quick_rounds(")]
qr = wsrc[wsrc.index("def quick_rounds("):wsrc.index("def smart_buy_universe(odds)")]
calls = re.findall(r"\n( *)smart_buy_universe\(odds\)", sl + qr)
ok("the watcher runs the paper scoring OUTSIDE odds.lock (the lock a real approved buy takes): loop level, never in a with-block",
   len(calls) == 2 and all(len(c) == 8 for c in calls)
   and '("smart_buy_universe", "smart_buy_backfill", "sb_paper_build")' in wsrc)

# ---- the dial's evidence: one row per bet, last check before the game; 'wide' and the backfill are left out
E.simulate_exit = real_sim
E.store_x("delete from exit_shadow")


def row(t, ts, kick, ev, out, source="panel", grade=None):
    E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, kick, price, fair, ev, route, old, new, ver, pays, "
              "res, outcome, grade) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (ts, f"{source}:{t}", source, "nhl", "single", json.dumps([t]), kick, 0.5, 0.55, ev, "hold", 1, 1, 1, 9.5,
               "won" if out > 0 else "lost", out, grade))


K = now - 2 * 86400
row("KXNHLGAME-26NOV19A-A", K - 7200, K, 0.1, 4.5)                                   # panel, early check
row("KXNHLGAME-26NOV19A-A", K - 600, K, 0.3, 4.5, source="universe", grade="cand")   # same bet, later universe check
row("KXNHLGAME-26NOV19B-A", K - 600, K, -0.2, -5.0, source="universe", grade="wide")
row("KXNHLGAME-26NOV19C-A", K - 600, K, 0.2, 4.5, source="backfill", grade="cand")
row("KXNHLGAME-26NOV19D-A", K - 600, K, 0.2, -5.0, source="universe", grade="cand")
narrow = {r["tickers"][0][-3:]: r for r in E._sb_results(now)}
uni = {r["tickers"][0][-3:]: r for r in E._sb_results(now, uni=True)}
wide = {r["tickers"][0][-3:]: r for r in E._sb_results(now, wide=True)}
ok("the dial's evidence (two-way steps, its 30-result count): the gate's own checks only, exactly as before",
   set(narrow) == {"A-A"} and narrow["A-A"]["ev"] == 0.1 and narrow["A-A"]["source"] == "panel")
ok("the stricter-only early looks may add universe 'cand' markets (never 'wide', never the backfill)",
   set(uni) == {"A-A", "D-A"} and uni["D-A"]["source"] == "universe")
row("KXNHLGAME-26NOV19D-B", K - 600, K, 0.2, -5.0, source="universe", grade="cand")   # same game as D-A
row("KXNHLGAME-26NOV19A-B", K - 600, K, 0.2, -5.0, source="universe", grade="cand")   # game a panel bet covers
uni = {r["tickers"][0][-3:]: r for r in E._sb_results(now, uni=True)}
ok("...one per game, and none on a game the panel already covers (a game's strikes move together)",
   set(uni) == {"A-A", "D-A"})
ok("the wide view has every scored bet, each once, with its source", set(wide) == {"A-A", "B-A", "C-A", "D-A"}
   and wide["B-A"]["grade"] == "wide" and wide["C-A"]["source"] == "backfill")

# ---- growth: compaction after the game and the universe cap
E.store_x("delete from exit_shadow")
rows = []
for b in range(300):                               # a day's worth: 300 bets x 13 checks each, games yesterday
    kick = now - 30 * 3600
    for j in range(13):
        rows.append((kick - (13 - j) * 3 * 3600 + 5400 * (j > 9), f"universe:{b}", "universe", "nba", "single",
                     json.dumps([f"KXNBAGAME-{b}"]), kick, 0.5, 0.52, 0.01, 0.5, 0.2, 0.3, 0.1, 0.1, 0.05, 30, "hold",
                     0, 0, 1, 9.5, None, 0, "wide"))
E._sb_insert(rows)
E._sb_compact(now)
n_after = E.store_rows("select count(*) n from exit_shadow")[0]["n"]
ok(f"after its game a universe bet keeps at most 2 rows per grade ({n_after} rows for 300 bets, was 3900)", n_after <= 600)
r2 = {r["tickers"][0]: r for r in E._sb_results(now, wide=True, settled=False)}
ok("...and still the same last-before-the-game check", len(r2) == 300)
E.store_x("delete from exit_shadow")
kick = now - 30 * 3600
for j, (src_, gr) in enumerate([("universe", "cand"), ("universe", "wide"), ("universe", "cand"), ("universe", "wide"),
                                ("panel", None), ("universe", "cand")]):
    E._sb_insert([(kick - 7200 + j * 600, "x", src_, "nhl", "single", json.dumps(["KXNHLGAME-MIX-A"]), kick, 0.5, 0.55,
                   0.03, 0.5, 0.2, 0.3, 0.1, 0.1, 0.1 * j, 30, "hold", 1, 1, 1, 9.5, None, 0, gr)])
before = [(r["ev"], r["source"], r["grade"]) for r in E._sb_results(now, wide=True, settled=False)] + \
    [(r["ev"], r["source"]) for r in E._sb_results(now, settled=False, uni=True)]
E._sb_compact(now)
after = [(r["ev"], r["source"], r["grade"]) for r in E._sb_results(now, wide=True, settled=False)] + \
    [(r["ev"], r["source"]) for r in E._sb_results(now, settled=False, uni=True)]
ok("compaction with mixed grades and sources on one market keeps exactly what the results read", before == after
   and E.store_rows("select count(*) n from exit_shadow")[0]["n"] < 6)
E.store_x("delete from exit_shadow")
E._sb_insert([(now - 3600 + i, "u", "universe", "nba", "single", json.dumps([f"KXNBAGAME-C{i}"]), now + 3600, 0.5, 0.52, 0.01,
               0.5, 0.2, 0.3, 0.1, 0.1, 0.05, 30, "hold", 0, 0, 1, 9.5, None, 0, "wide") for i in range(150)])
E.SB_UNI_MAX_ROWS = 100
E._sb_compact(now)
ok("universe rows are capped (oldest first)", E.store_rows("select count(*) n from exit_shadow where source='universe'")[0]["n"] == 100)
E.SB_UNI_MAX_ROWS = 120000
per_day = 500 * 2                                   # ~500 markets a day kept at <= 2 rows each, 60 days
ok(f"growth math: 60 days at ~{per_day} rows a day stay under the universe cap ({60 * per_day} < {E.SB_UNI_MAX_ROWS}), and the "
   "table's own 200,000-row cap still holds", 60 * per_day < E.SB_UNI_MAX_ROWS < 200000)

# ---- 3. backfill from history: idempotent, never double counts, kept out of the dial
E.store_x("delete from exit_shadow")
E.store_x("create table if not exists panel(day text, mode text, ts real, status text, body text, primary key(day, mode))")
E.store_x("delete from panel")


def item(t, kind="single", res="won", at=None, kick=None, paid=None, live=False):
    d = {"id": f"{kind}:{t}", "kind": kind, "code": "nhl", "chance": 0.6, "ret": 0.1, "price": 0.5, "kick": kick or K,
         "legs": [{"ticker": t, "event": t.rsplit("-", 1)[0], "p": 0.5, "fair": 0.6}], "at": at or K - 3600, "result": res}
    if paid:
        d["paid"] = paid
    if live:
        d["live"] = True
    return d


items = [item("KXNHLGAME-26NOV19H1-A"), item("KXNHLGAME-26NOV19H2-A", res="lost", paid=0.48),
         item("KXNHLGAME-26NOV19H3-A", res=None), item("KXNHLGAME-26NOV19H4-A", at=K + 60),
         item("KXNHLGAME-26NOV19H5-A", live=True), item("KXNHLGAME-26NOV19H6-A")]
E.store_x("insert into panel values(?,?,?,?,?)", ("2026-11-19", "real#1", K - 4000, "closed", json.dumps({"at": K - 4000, "items": items})))
E.store_x("insert into panel values(?,?,?,?,?)", ("2026-11-19", "paper", K - 4000, "paper", json.dumps({"at": K - 4000, "items": items[:2]})))
row("KXNHLGAME-26NOV19H6-A", K - 500, K, 0.2, 4.5)                                       # H6 was scored live
n_bf = E.smart_buy_backfill(now=now, force=True)
bf = {json.loads(r["tickers"])[0][-4:]: r for r in E.store_rows("select * from exit_shadow where source='backfill'")}
ok("backfill: the history's panel bets with a known result, checked before their game (H1, H2), once each",
   n_bf == 2 and set(bf) == {"H1-A", "H2-A"})
ok("...a result scored on $5 held to the end, the price really paid, no invented gate verdict",
   bf["H1-A"]["res"] == "won" and abs(bf["H1-A"]["outcome"] - (bf["H1-A"]["pays"] - 5)) < 1e-6 and bf["H2-A"]["outcome"] == -5.0
   and bf["H2-A"]["price"] == 0.48 and bf["H1-A"]["skip"] is None and bf["H1-A"]["strict"] == 0)
ok("re-running adds nothing (idempotent)", E.smart_buy_backfill(now=now, force=True) == 0
   and E.store_rows("select count(*) n from exit_shadow where source='backfill'")[0]["n"] == 2)
ok("a bet already scored live is never backfilled (no double count)", "H6-A" not in bf)
ok("the backfill stays out of the dial's evidence", not any(r["source"] == "backfill" for r in E._sb_results(now)))
ok("backfill made no request", not CALLS)

# ---- 2. the paper book: graduated stakes on paper, in its own table
E.save_json(E.SIZING_FILE, {"base": 200.0})
row("KXNHLGAME-26NOV19S1-A", K - 600, K, 0.4, 4.5, source="universe", grade="cand")
E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, kick, price, fair, ev, route, old, new, ver, pays, res, "
          "outcome, grade, skip) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (K - 600, "panel:x", "panel", "nhl", "single", json.dumps(["KXNHLGAME-26NOV19S2-A"]), K, 0.5, 0.55, -0.6, "none", 1, 0,
           1, 9.5, "lost", -5.0, None, "expects to lose"))
row("KXNHLGAME-26NOV19S3-A", K - 600, K, 0.5, 4.5, source="universe", grade="wide")   # Smart Buy's own pick (new=1): extra
panel_before = E.store_rows("select * from panel")
n_pb = E.sb_paper_build(now=now, force=True)
pb = {json.loads(r["bet"])[0][-4:]: r for r in E.store_rows("select * from sb_paper")}
ok("the paper book has one row per scored bet", n_pb == len(pb) and {"H1-A", "S1-A", "S2-A", "S3-A"} <= set(pb))
ok("roles: kept panel-grade bets are staked, a skipped one only scored at $5, Smart Buy's own pick is an extra",
   pb["S1-A"]["role"] == "stake" and pb["S2-A"]["role"] == "skip" and pb["S2-A"]["stake"] == 0 and pb["S3-A"]["role"] == "extra")
st = [r for r in pb.values() if r["stake"]]
ok("graduated stakes come from _size: at least $2, at most 5% of the base ($10 on $200)",
   st and all(2.0 <= r["stake"] <= 10.0 for r in st))
want = E._size({"kind": "combo", "chance": 0.55, "pct": 9.5 / 5, "fair_mult": 1.0}, 200.0)
ok("...exactly _size's quarter Kelly on the shrunk edge", abs(pb["S1-A"]["stake"] - want) < 1e-9)
ok("...and what it made scales the $5 result to that stake", abs(pb["S1-A"]["outcome"] - 4.5 * pb["S1-A"]["stake"] / 5) < 1e-6)
days = {}
for r in pb.values():
    days[r["day"]] = days.get(r["day"], 0) + r["stake"]
ok("a day's paper stakes never go over the daily panel budget", all(v <= 40 + 1e-9 for v in days.values()))
E.CFG["panel_budget"] = 4
E.sb_paper_build(now=now, force=True)
days = {}
for r in E.store_rows("select day, role, source='backfill' h, stake from sb_paper"):
    k_ = (r["day"], r["role"], r["h"])
    days[k_] = days.get(k_, 0) + r["stake"]
ok("...even a tight one ($4 each for stakes, extras and history: the rest are left out, never squeezed under $2)",
   all(v <= 4 + 1e-9 for v in days.values()) and all(r["stake"] in (0, 0.0) or r["stake"] >= 2
                                                       for r in E.store_rows("select stake from sb_paper")))
E.CFG["panel_budget"] = 40
E.sb_paper_build(now=now, force=True)
ok("the paper book never touches the panel table (the $300 gate) or the ledger",
   E.store_rows("select * from panel") == panel_before and
   not E.store_rows("select name from sqlite_master where name='ledger'") or not E.store_rows("select * from ledger"))
pl = E.sb_paper_leagues(now)
nhl = pl.get("nhl") or {}
ok("per league: scored, settled; the bar counts only live panel-grade stakes, one a game (extras, history apart)",
   nhl.get("scored", 0) >= 6 and nhl.get("settled") == nhl.get("scored") and nhl.get("n") == 2 and nhl.get("extra_n") == 1
   and nhl.get("hist_n") == 2 and nhl.get("skips") == 1 and nhl.get("beats") is True and nhl.get("days") == 1)
ok("...split by source", set(nhl["by"]) == {"panel", "universe", "backfill"})
dial({"nhl": {"n": 3, "level": 0}})
g = next(x for x in E.smart_buy_gate_summary(now=now) if x["league"] == "nhl")
ok("the 'Bigger stakes: not yet' line is fed by the paper book (real sizing rules, on paper)",
   g["optin"].get("paper") and g["optin"]["n"] == nhl["n"] and g["optin"]["ahead"] == nhl["ahead"] and g["optin"]["met"] is False
   and g["scored"]["n"] == nhl["scored"])
sm = E.smart_buy_summary(now=now)
ok("the card's header gets the total scored on paper, by source", sm["scored"]["n"] >= 6 and "backfill" in sm["scored"]["by"])
ok("the card's 'what it checked' table still counts only panel candidates and Buy ideas",
   all(r["n"] <= 2 for r in sm["rows"]))

# ---- 4. borrowing sooner, stricter only
EPL = "KXEPLGAME-26NOV21ARSCHE-ARS"
dial({"soccer": {"n": 15, "level": 0, "early": 2, "early_blk": 1}})
d = E.sb_dial([EPL], now)
ok("a league with no results borrows its sport's early level from 15 results (not waiting for 30)",
   d["level"] == 2 and d["key"] == "soccer" and d["early"] and d["state"] == "learning")
dial({"soccer": {"n": 9, "level": 0, "early": 2}})
ok("...not without a look from 10 results (no early_blk)", E.sb_dial([EPL], now)["level"] == 0)
dial({"soccer": {"n": 40, "level": 0, "own": True, "early": 3}})
ok("a lender with 30+ results lends its own level only (its old early level is gone)", E.sb_dial([EPL], now)["level"] == 0)
dial({"soccer": {"n": 40, "level": 4, "own": True}, "all": {"n": 20, "level": 0, "early": 1, "early_blk": 2}})
ok("an early level never lowers what is borrowed today (stricter only)", E.sb_dial([EPL], now)["level"] == 4)
dial({"all": {"n": 20, "level": 0, "early": 9, "early_blk": 2}})
ok("an early level is capped at the soft top (3: skips expected losers only)", E.sb_dial([EPL], now)["level"] == 3)
dial({"epl": {"n": 35, "level": 1, "own": True}, "soccer": {"n": 15, "early": 3, "early_blk": 1}})
ok("at its own 30 a league's own record takes over, both ways", E.sb_dial([EPL], now)["level"] == 1)
E.store_x("delete from exit_shadow")
RES = {}


def nhl_row(i, ev, won, day_off=3):
    t = f"KXNHLGAME-26NOV10Q{i:03d}-A"
    RES[t] = "yes" if won else "no"
    kick = now - day_off * 86400
    E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, kick, price, ev, route, old, new, ver, pays, res, outcome) "
              "values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (kick - 3600, "panel:" + t, "panel", "nhl", "single", json.dumps([t]), kick,
                                                          0.5, ev, "hold", 1, 1, 1, 9.5, "won" if won else "lost", 4.5 if won else -5.0))


for i in range(8):
    nhl_row(i, 0.5, i % 2 == 0)
for i in range(8, 20):
    nhl_row(i, -0.5, False)                        # 12 bets expected to lose clearly lost
E.fetch_results = lambda tks: {t: RES[t] for t in tks if t in RES}
dial({})
got = E.smart_buy_learn(now=now, force=True)
ok("20 results (two blocks of 10) whose low-EV bets clearly lost: the early level steps up to 1",
   got["nhl"].get("early") == 1 and got["nhl"]["level"] == 0 and got["nhl"].get("early_blk") == 2)
ok("...and the NHL uses it now (stricter), while still learning", E.sb_dial(["KXNHLGAME-26NOV21PHIBOS-PHI"], now)["level"] == 1)
got = E.smart_buy_learn(now=now + 10, force=True)
ok("no new block of 10: no new look", got["nhl"]["early"] == 1)
E.store_x("delete from exit_shadow")
for i in range(8):
    nhl_row(100 + i, 0.5, i % 2 == 0)
for i in range(8, 20):
    nhl_row(100 + i, -0.5, True)                   # now the bets a level-1 dial skips clearly WON
dial({"nhl": {"n": 20, "level": 0, "early": 1, "early_blk": 1}})
got = E.smart_buy_learn(now=now + 20, force=True)
ok("an early level never steps down, even when its skips would have won (it is only a reason to skip more)",
   got["nhl"].get("early") == 1 and got["nhl"].get("early_blk") == 2)
dial({"nhl": {"n": 25, "level": 0, "early": 2, "early_blk": 2}})
for i in range(30, 40):
    nhl_row(i, 0.5, True)
got = E.smart_buy_learn(now=now + 30, force=True)
ok("at 30 of its own a league starts from the early level it was using, then its own record moves it",
   got["nhl"]["own"] and got["nhl"]["n"] >= 30 and got["nhl"]["level"] == 2)
# the universe may only make the dial stricter sooner: relearn with and without its rows
E.store_x("delete from exit_shadow")


def ahl_row(i, ev, won, source="panel", grade=None):
    t = f"KXAHLGAME-26NOV10{i:03d}ABCDEF-A"
    kick = now - 3 * 86400
    E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, kick, price, ev, route, old, new, ver, pays, res, "
              "outcome, grade) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (kick - 3600, source + ":" + t, source, "ahl", "single", json.dumps([t]), kick, 0.5, ev, "hold", 1, 1, 1, 9.5,
               "won" if won else "lost", 4.5 if won else -5.0, grade))


for i in range(6):
    ahl_row(i, 0.5, i % 2 == 0)
dial({})
base_ = E.smart_buy_learn(now=now, force=True)
for i in range(6, 40):
    ahl_row(i, -0.5 if i < 20 else 0.5, i >= 20 and i % 2 == 0, source="universe", grade="cand")
for i in range(40, 70):
    ahl_row(i, 0.5, True, source="universe", grade="wide")
dial({})
with_ = E.smart_buy_learn(now=now, force=True)
same = all(with_.get(g, {}).get(f) == base_.get(g, {}).get(f) for g in ("ahl", "all") for f in ("n", "level", "own"))
ok("universe markets never change a group's own count, level or 'own' (no step down, no early 'active')", same
   and not with_["ahl"].get("own"))
ok("...they only give the stricter-only early look more to go on (14 universe bets expected to lose did lose)",
   with_["ahl"].get("early", 0) >= 1 and E.sb_dial(["KXAHLGAME-26NOV21ABCDEF-A"], now)["level"] >= 1
   and not base_["ahl"].get("early"))
ok("the registry lists the new evidence bar (10) and it matches the code", E.KNOB_BY["sb_borrow_n"]["start"] == 10
   and E.knob_live("sb_borrow_n") == 10 and E.KNOB_BY["sb_borrow_n"]["cls"] == "evidence")
ok("still no request of any kind", not CALLS)
