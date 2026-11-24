# CHECK: group=engine
# In-play comeback model (issue #348): an in-play bet needs today's gate (smart_buy_ok on the live state) AND the comeback
# model (features from the score feeds already fetched, plus the league's own recorded in-play price recoveries). Checks:
# no pregame row ever enters an in-play bucket (leakage), borrowed levels only lower the rate, the verdict is always
# stricter or equal to today's (property test), every missing feature fails closed, both verdicts and the other side
# (paper) are logged, rows are scored on the recorded prices, the Results summary, and every gate path uses it.
# Fakes only: no network, temp files, a temp history.
import os, time, json, random, tempfile, importlib.util, inspect, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
now = time.time()
NBA = "KXNBAGAME-26NOV23LALBOS-LAL"
NBA_O = "KXNBAGAME-26NOV23LALBOS-BOS"
NFL = "KXNFLGAME-26NOV23KCPHI-KC"
NHL = "KXNHLGAME-26NOV23NYRBOS-NYR"


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)


def safe(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


PASS_SIM = {"route": "sell", "ev": 1.0, "p_exit": 0.6, "win": 0.5, "hold_profit": 0.2}
FAIL_SIM = {"route": "none", "ev": -0.6, "p_exit": 0.05, "win": 0.12, "hold_profit": -0.5}
REAL_W = E.cb_weight
REAL = {k: getattr(E, k) for k in ("leg_score", "score_age", "pregame_fair", "_sb_sim", "simulate_exit", "comeback_table",
                                   "comeback_judge", "smart_buy_on")}


def restore():
    for k, v in REAL.items():
        setattr(E, k, v)
    E.CB_STATE.update(tab=None, at=0.0, seen={})


def sc_nba(me=80, opp=90, frac=0.3, **kw):
    return dict({"state": "in", "frac": frac, "me": me, "opp": opp, "detail": "Q4 8:00", "wp": None}, **kw)


def live_env(sc, pre=0.5, sim=PASS_SIM):
    E.leg_score = lambda l: sc
    E.score_age = lambda code, now=None: 5
    E.pregame_fair = lambda t: pre
    E._sb_sim = lambda c, now: dict(sim) if sim is not None else None


def cand(t=NBA, fair=0.3, ask=0.25, live=True):
    return {"kind": "single", "live": live, "id": "single:" + t, "code": E.ticker_sport(t),
            "legs": [{"ticker": t, "event": t.rsplit("-", 1)[0], "fair": fair, "p": ask, "pre": 0.5}]}


def path(t, start, rows):
    """rows: (minutes after start, bid, ask, score text or None, frac or None)."""
    for m, b, a, s, f in rows:
        E.store_x("insert into price_path(ts, ticker, bid, ask, mid, score, frac) values(?,?,?,?,?,?,?)",
                  (start + m * 60, t, b, a, (b + a) / 2, s, f))


def t_leakage():
    restore()
    E._price_table()
    E.store_x("delete from price_path")
    s0 = now - 5 * 3600
    # A: pregame only (no score text): its bid doubles before the start. Must never enter any bucket.
    path("KXNBAGAME-26NOV20AAABBB-AAA", s0 - 7200, [(0, 0.20, 0.22, None, None), (60, 0.60, 0.62, None, None),
                                                    (100, 0.65, 0.67, None, None)])
    # B: a score text that isn't a moment in play (pre-game time) is no entry either
    path("KXNBAGAME-26NOV20CCCDDD-CCC", s0, [(0, 0.20, 0.22, "0-0 7:00 PM", None), (5, 0.70, 0.72, "0-0 7:30 PM", None),
                                             (200, 0.99, 1.0, "100-90 Final", None)])
    # C: a real in-play path, trailing by 10 (2 units) in Q2, then recovering to a profitable sale, then Final
    path(NBA, s0, [(20, 0.25, 0.27, "30-40 Q2 6:00", 0.62), (40, 0.45, 0.47, "50-50 Q3 9:00", 0.44),
                   (80, 0.01, 0.02, "95-105 Final", None)])
    # D: censored in-play path (stops early, never reaches the end): gives nothing
    path("KXNBAGAME-26NOV20EEEFFF-EEE", s0, [(20, 0.20, 0.22, "30-40 Q2 6:00", 0.62), (30, 0.60, 0.62, "45-40 Q2 1:00", 0.52)])
    tab = E.comeback_table(now, force=True)
    allk = {k: v for k, v in tab.items() if k[0] == "all"}
    ok("leakage: only the one complete in-play path enters (pregame rows, pre-game scores and a cut-off path don't)",
       sum(v[0] for v in allk.values()) == 2)
    ok("leakage: the trailing entry (-2 units, Q2 left) is counted as recovered",
       tab.get(("all", -2, 2)) == [1, 1] and tab.get(("nba", -2, 2)) == [1, 1])
    ok("leakage: the pregame doubling (A) is nowhere", not any(k for k in tab if k[1] == 0 and k[2] == 3))
    # the 50-50 Q3 entry had no later profitable bid: not recovered
    ok("leakage: an entry with no later profitable sale is 0", tab.get(("all", 0, 1)) == [1, 0])
    ok("leakage: the table reads only rows with a score (in play or over)", "score is not null" in inspect.getsource(E._cb_build))
    path(NBA_O, s0, [(20, 0.73, 0.75, "40-30 Q2 6:00", 0.62), (40, 0.53, 0.55, "50-50 Q3 9:00", 0.44),
                     (80, 0.98, 0.99, "105-95 Final", None)])
    tab = E.comeback_table(now, force=True)
    ok("one market per game: the mirrored other side doesn't count the game twice",
       sum(v[0] for k, v in tab.items() if k[0] == "all") == 2)


def t_rate():
    restore()
    E.comeback_table = lambda now=None, force=False: {("all", -2, 1): [100, 5], ("nba", -2, 1): [0, 0]}
    p, n, used = E.comeback_rate(NBA, -2, 1, 0.6)
    ok("rate: everyone's poor record lowers a league with none of its own (stricter)", used and p < 0.6 and n == 100)
    E.comeback_table = lambda now=None, force=False: {("all", -2, 1): [100, 95]}
    p, n, used = E.comeback_rate(NBA, -2, 1, 0.3)
    ok("rate: a borrowed level never raises it above the model", used and abs(p - 0.3) < 1e-9)
    E.comeback_table = lambda now=None, force=False: {("all", -2, 1): [100, 95], ("nba", -2, 1): [80, 76]}
    p, n, used = E.comeback_rate(NBA, -2, 1, 0.3)
    ok("rate: only the league's own rows can raise it", used and p > 0.5)
    E.comeback_table = lambda now=None, force=False: {("all", -2, 1): [3, 0]}
    p, n, used = E.comeback_rate(NBA, -2, 1, 0.6)
    ok("rate: too few rows = the model decides (not used)", not used and p is None)
    restore()


def t_fail_closed():
    restore()
    E.comeback_table = lambda now=None, force=False: {}
    live_env({"state": "in", "frac": 0.5, "me": 7, "opp": 14, "detail": "Q3 7:00", "situation": {}})
    j = E.comeback_judge(cand(NFL), now)
    ok("fail closed: football with no ball position", not j["ok"] and j["miss"] == "ball" and j["old"])
    live_env({"state": "in", "frac": 0.5, "me": 1, "opp": 2, "detail": "P2 7:00"})
    j = E.comeback_judge(cand(NHL), now)
    ok("fail closed: hockey with no shots", not j["ok"] and j["miss"] == "shots")
    live_env(sc_nba())
    E.score_age = lambda code, now=None: 999
    ok("fail closed: a stale score", not E.comeback_judge(cand(), now)["ok"])
    live_env(sc_nba(), pre=None)
    c = cand()
    c["legs"][0].pop("pre")
    ok("fail closed: no closing line", not E.comeback_judge(c, now)["ok"])
    live_env(None)
    ok("fail closed: no score at all", not E.comeback_judge(cand(), now)["ok"])
    live_env(sc_nba())
    E.comeback_judge = lambda c, now=None, sim=None: (_ for _ in ()).throw(ValueError("x"))
    ok("fail closed: an error in the model", E.inplay_exit_ok(cand(), now=now) == (False, E.IN_PLAY_WHY))
    restore()
    live_env(sc_nba(), sim=None)
    ok("fail closed: the simulator can't model it", not E.comeback_judge(cand(), now)["ok"])
    live_env(sc_nba(), sim=FAIL_SIM)
    j = E.comeback_judge(cand(), now)
    ok("fail closed: today's gate failing is never overruled", not j["ok"] and j["why"] == E.IN_PLAY_WHY)
    restore()


def t_property():
    """Stricter or equal: across random live states, sims and recorded rates, ok is never true when today's gate
    (smart_buy_ok on the same sim) is false, and a pregame bet always gets today's verdict unchanged."""
    restore()
    rng = random.Random(348)
    bad = 0
    for i in range(300):
        sim = {"route": rng.choice(["sell", "hold", "none"]), "ev": rng.uniform(-1, 2), "p_exit": rng.random(),
               "win": rng.random(), "hold_profit": rng.uniform(-1, 1)}
        tab = {("all", lu, tb): [rng.randint(0, 60), 0] for lu in range(-3, 4) for tb in range(4)}
        for v in tab.values():
            v[1] = rng.randint(0, v[0])
        E.comeback_table = lambda now=None, force=False, tab=tab: tab
        sport_t = rng.choice([NBA, NFL, NHL])
        sc = {"state": "in", "frac": rng.uniform(0.02, 1), "me": rng.randint(0, 40), "opp": rng.randint(0, 40),
              "detail": "Q2 5:00", "situation": {"possAbbr": "KC", "possessionText": f"PHI {rng.randint(1, 50)}",
                                                 "possession": rng.random() < .5, "down": rng.randint(1, 4), "distance": 7},
              "stats": {"saves": rng.randint(0, 30)}, "ostats": {"saves": rng.randint(0, 30)}}
        if sport_t == NHL:
            sc.update(me=rng.randint(0, 5), opp=rng.randint(0, 5))
        live_env(sc, pre=rng.uniform(0.1, 0.9), sim=sim)
        c = cand(sport_t, fair=rng.uniform(0.05, 0.95), ask=rng.uniform(0.03, 0.95), live=True)
        got, _ = E.inplay_exit_ok(c, now=now, source="prop")
        if got and not E.smart_buy_ok(sim):
            bad += 1
        pre = dict(cand(sport_t, live=False))
        pre["legs"][0]["pre"] = None
        E.leg_score = lambda l: None
        j = E.comeback_judge(pre, now + 0)
        if j.get("pregame") and j["ok"] != E.smart_buy_ok(sim):
            bad += 1
    ok("property: 300 random states, never looser than today's gate; pregame bets unchanged", bad == 0)
    restore()


def t_features():
    restore()
    E.comeback_table = lambda now=None, force=False: {}
    base = {"state": "in", "frac": 0.2, "me": 14, "opp": 17, "detail": "Q4 12:00"}
    f1, _ = E.comeback_features(NFL, dict(base, situation={"possAbbr": "KC", "possessionText": "PHI 5", "possession": True,
                                                           "down": 1, "distance": 5}), now)
    f2, _ = E.comeback_features(NFL, dict(base, situation={"possAbbr": "PHI", "possessionText": "PHI 20", "possession": False,
                                                           "down": 1, "distance": 10}), now)
    ok("features: yards to go read from the ball spot and who has it", f1["ytg"] == 5 and f2["ytg"] == 80)
    q1 = E._cb_chance(NFL, 0.5, base, f1)
    q2 = E._cb_chance(NFL, 0.5, base, f2)
    ok("features: the ball at the other team's 5 is worth more than them having it at their own 20", q1 > q2 + 0.1)
    fa, _ = E.comeback_features(NBA, sc_nba(me=90, opp=100, frac=0.25), now)
    ok("features: basketball pace from points so far", fa["pace"] > 1.0)
    st = E._cb_team_stats({"statistics": [{"name": "saves", "displayValue": "21"}, {"name": "savePct", "displayValue": ".913"},
                                          {"name": "possessionPct", "displayValue": "61.2"}, {"name": "x", "displayValue": "n/a"}]})
    ok("features: ESPN team stats parsed, odd values left out", st == {"saves": 21.0, "savePct": 0.913, "possessionPct": 61.2})
    fh, miss = E.comeback_features(NHL, {"state": "in", "frac": 0.5, "me": 1, "opp": 2, "stats": {"saves": 30},
                                         "ostats": {"saves": 10}}, now)
    ok("features: hockey shots = the other goalie's saves + goals", miss is None and fh["shots"] == 11 and fh["oshots"] == 32)
    ok("features: being outshot 11-32 lowers the chance", E._cb_chance(NHL, 0.5, {"state": "in"}, fh) <
       E._cb_chance(NHL, 0.5, {"state": "in"}, dict(fh, shots=32, oshots=11)))
    restore()


def t_logging_and_other_side():
    restore()
    E._cb_table()
    E.store_x("delete from comeback_shadow")
    E.comeback_table = lambda now=None, force=False: {("all", -2, 1): [40, 1]}   # this league's teams rarely came back
    live_env(sc_nba(me=80, opp=90, frac=0.3), sim=PASS_SIM)
    E.PRICE_SEEN[NBA_O] = (now, 0.74, 0.76, None)
    okv, why = E.inplay_exit_ok(cand(NBA, fair=0.3, ask=0.25), now=now, source="panel")
    ok("verdict: a trailing team the league's own history says rarely recovers is held back (old passed)",
       okv is False and "similar spots" in (why or ""))
    rows = E.store_rows("select source, old, new, ok, paper, ticker from comeback_shadow order by rowid")
    main = [r for r in rows if not r["paper"]]
    oth = [r for r in rows if r["paper"]]
    ok("logging: both verdicts logged (old 1, new 0)", main and main[0]["old"] == 1 and main[0]["new"] == 0 and main[0]["ok"] == 0)
    ok("logging: the other side of the game is scored and logged as paper only", oth and oth[0]["ticker"] == NBA_O
       and oth[0]["source"] == "other")
    pk = E.store_rows("select pick, pick_why from comeback_shadow where paper=0")
    ok("side pick: logged on the main row with a plain reason (paper only)", pk and pk[0]["pick"] in ("this", "other", "neither")
       and pk[0]["pick_why"])
    n = len(rows)
    E.inplay_exit_ok(cand(NBA, fair=0.3, ask=0.25), now=now + 5, source="panel")
    ok("logging: throttled (one row per bet per 10 minutes)", len(E.store_rows("select 1 from comeback_shadow")) == n)
    E.CB_STATE["seen"] = {}
    E.store_x("delete from comeback_shadow")
    E.inplay_exit_ok(cand(NBA, fair=0.3, ask=0.25), now=now + 1, source="quote")
    ok("other side: never scored on a tap's path (quote/buy)",
       not E.store_rows("select 1 from comeback_shadow where paper=1"))
    src = inspect.getsource(E._cb_other_side)
    ok("other side: never buys, never shows (no order, push or suggestion call)",
       not any(w in src for w in ("kalshi_send", "push(", "store_suggestion", "buy_single", "accept_offer")))
    E.PRICE_SEEN.pop(NBA_O, None)
    restore()


def t_resolve_and_summary():
    restore()
    E._cb_table()
    E._price_table()
    E.store_x("delete from comeback_shadow")
    E.store_x("delete from price_path")
    s0 = now - 6 * 3600
    path(NBA, s0, [(0, 0.20, 0.25, "30-40 Q2 6:00", 0.62), (30, 0.40, 0.42, "60-60 Q3 3:00", 0.4),
                   (90, 0.99, 1.0, "100-95 Final", None)])
    path(NBA_O, s0, [(0, 0.74, 0.76, "40-30 Q2 6:00", 0.62), (30, 0.58, 0.60, "60-60 Q3 3:00", 0.4),
                     (90, 0.01, 0.02, "95-100 Final", None)])
    ins = ("insert into comeback_shadow(ts, cand, source, league, kind, ticker, ask, p_old, p_new, old, new, ok, paper) "
           "values(?,?,?,?,?,?,?,?,?,?,?,?,?)")
    E.store_x(ins, (s0 + 1, "single:" + NBA, "quote", "nba", "single", NBA, 0.25, 0.6, 0.2, 1, 0, 0, 0))
    E.store_x(ins, (s0 + 1, "other:" + NBA_O, "other", "nba", "single", NBA_O, 0.76, 0.3, 0.3, 1, 1, 1, 1))
    E.comeback_resolve(now)
    r = {x["ticker"]: x for x in E.store_rows("select ticker, rec, pnl from comeback_shadow")}
    ok("resolve: the trailing side recovered to a profitable sale (rec 1, a profit)", r[NBA]["rec"] == 1 and r[NBA]["pnl"] > 0)
    ok("resolve: the leader never got a profitable sale and lost (rec 0, -$5)", r[NBA_O]["rec"] == 0 and r[NBA_O]["pnl"] == -5.0)
    sm = E.comeback_summary(now=now)
    lg = sm["leagues"][0] if sm["leagues"] else {}
    ok("summary: per league predicted vs actual and what the new model held back",
       lg.get("league") == "nba" and lg.get("actual") == 1.0 and lg.get("held") == 1 and lg.get("held_rec") == 1)
    ok("summary: the other side's paper record", sm["other"] and sm["other"]["n"] == 1 and sm["other"]["pass"] == 1)
    a = E.analytics()
    ok("summary: on Results > What's working (analytics)", isinstance(a.get("comeback"), dict))
    restore()


def t_side_pick():
    restore()
    E.cb_weight = lambda t, now=None: (1.0, 0)
    base = {"ok": True, "ev_new": 0.8, "ask": 0.30, "bid": 0.28, "ticker": NBA}
    oth = {"ok": True, "ev_new": 0.4, "ask": 0.70, "bid": 0.68, "ticker": NBA_O}
    ok("side pick: the better side on one scale", E.cb_pick_side(base, oth, now)["pick"] == "this")
    ok("side pick: the other side when it scores better", E.cb_pick_side(dict(base, ev_new=0.1), dict(oth, ev_new=0.9),
                                                                         now)["pick"] == "other")
    ok("side pick: neither when neither clears the full check", E.cb_pick_side(dict(base, ok=False), dict(oth, ok=False),
                                                                               now)["pick"] == "neither")
    ok("side pick: a wide spread rules this side out", E.cb_pick_side(dict(base, bid=0.20), None, now)["pick"] == "neither")
    ok("side pick: a side with a missing feature isn't scored", E._cb_side_score(dict(base, miss="ball"), now) is None)
    E.cb_weight = REAL_W
    E._cb_table()
    E.store_x("delete from comeback_shadow")
    ins = "insert into comeback_shadow(ts, ticker, ev_new, pnl, rec) values(?,?,?,?,?)"
    for i in range(200):                              # other leagues' in-play guesses paid only half
        E.store_x(ins, (now - 100, "KXNHLGAME-X-A", 1.0, 0.5, 1))
    E.CB_STATE.pop("w", None)
    w, n = E.cb_weight(NBA, now)
    ok("weights: a borrowed record can only lower a league's weight", w < 1.0 and n == 200)
    for i in range(200):                              # this league's own paid more than expected
        E.store_x(ins, (now - 100, NBA, 1.0, 1.4, 1))
    E.CB_STATE.pop("w", None)
    w2, _ = E.cb_weight(NBA, now)
    ok("weights: the league's own record moves it up", w2 > w)
    E.store_x("delete from comeback_shadow")
    E.CB_STATE.pop("w", None)
    restore()


def t_ideas_gate():
    restore()
    E._exit_shadow_table()
    E._cb_table()
    idea = {"idea_id": "9", "id": 9, "legs": [NBA], "live": True, "picks": "Lakers"}
    cand_key = E._sb_idea_cand(idea)
    E.store_x("insert into exit_shadow(ts, cand, source, tickers, new, ev) values(?,?,?,?,?,?)",
              (now, cand_key, "idea", json.dumps([NBA]), 1, 1.0))
    E.store_x("insert into comeback_shadow(ts, cand, source, ok) values(?,?,?,?)", (now, cand_key, "idea", 0))
    E.smart_buy_on = lambda: True
    kept, sk = E.smart_buy_ideas_gate([idea], now)
    ok("ideas: an in-play idea the comeback model hasn't agreed with is left out", not kept and sk)
    E.smart_buy_on = lambda: False
    kept, sk = E.smart_buy_ideas_gate([idea], now)
    ok("ideas: ...even with Smart Buy switched off", not kept and sk)
    E.store_x("insert into comeback_shadow(ts, cand, source, ok) values(?,?,?,?)", (now + 1, cand_key, "idea", 1))
    E.smart_buy_on = lambda: True
    kept, _ = E.smart_buy_ideas_gate([idea], now + 2)
    ok("ideas: kept once both agree", kept == [idea])
    pre = {"idea_id": "8", "id": 8, "legs": ["KXNBAGAME-X-A"], "picks": "x"}
    E.smart_buy_on = lambda: False
    ok("ideas: pregame ideas with the switch off are untouched", E.smart_buy_ideas_gate([pre], now)[0] == [pre])
    restore()


def t_paths():
    ok("paths: live_exit_ok goes through the comeback model", "inplay_exit_ok" in inspect.getsource(E.live_exit_ok))
    ok("paths: the panel gate's live branch does too", "inplay_exit_ok" in inspect.getsource(E.smart_buy_gate))
    ok("paths: the buy-time recheck does too", "inplay_exit_ok" in inspect.getsource(E._buy_panel_bet))
    ok("paths: Best bets' live candidates do too", "inplay_exit_ok" in inspect.getsource(E.best_bets_feed))
    ok("paths: the shadow pass logs the verdict for in-play candidates", "inplay_exit_ok" in inspect.getsource(E.smart_buy_shadow))
    ok("paths: no Kalshi request in the model (cached scores, recorded prices)",
       not any("requests." in inspect.getsource(f) or "kalshi_get" in inspect.getsource(f)
               for f in (E.comeback_judge, E.comeback_features, E.comeback_table, E.comeback_resolve, E._cb_other_side)))


for name, fn in list(globals().items()):
    if name.startswith("t_") and callable(fn):
        safe(name, fn)
