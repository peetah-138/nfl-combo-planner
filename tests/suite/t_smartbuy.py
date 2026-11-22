# CHECK: group=engine
# Smart Buy stage 1 (issue #137): the exit simulator, the shadow price recorder, the exit_shadow log, the
# calibration replay and the Results preview. Everything here only watches: no buy, sale or panel pick changes,
# and nothing makes a new Kalshi request (the fake network counts every call).
import os, time, tempfile, importlib.util, json, copy
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json"); E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.leg_score = lambda l: None
E.CFG.update(take_profit=0, lock_trail=True, smart_sell=True, ride=2)
E.SMART_CACHE.update(at=time.time() + 1e6, d={})
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)

CALLS = []


class NoNet:
    """requests stand-in: any call is counted (and fails)."""
    RequestException = E.requests.RequestException

    def __getattr__(self, name):
        def call(*a, **k):
            CALLS.append((name, a[:1]))
            raise E.requests.RequestException("no network in this test")
        return call


E.requests = NoNet()
now = time.time()
T = "KXNBAGAME-26NOV21BOSNYK-BOS"


def sp(q0=0.55, ask=0.50, bid=0.48, start=3 * 3600, f0=1.0, code="nba", depth=None):
    return {"kind": "single", "tickers": [T], "id": "x", "league": code, "type": "single", "depth": depth,
            "legs": [{"ticker": T, "code": code, "q0": q0, "ask": ask, "bid": bid, "start": start, "f0": f0, "dur": 2.75 * 3600}]}


# ---- the simulator
a, b = E.simulate_exit(sp(), seed=7), E.simulate_exit(sp(), seed=7)
ok("simulate_exit is deterministic with a seed", {k: v for k, v in a.items() if k != "ms"} == {k: v for k, v in b.items() if k != "ms"})
c1, c2 = E.simulate_exit(sp()), E.simulate_exit(sp())
ok("...and with no seed (one per candidate)", c1["p_exit"] == c2["p_exit"] and c1["ev"] == c2["ev"])
ok("it reports the chance to cash out, sell chance, exit and hold profit, blended EV, minutes to exit, route",
   all(k in a for k in ("p_exit", "p_sell", "exit_profit", "hold_profit", "ev", "exit_mins", "route", "win")) and 0 <= a["p_exit"] <= a["p_sell"] <= 1)
ok("hold profit is the fair chance times the payout, less the stake", abs(a["hold_profit"] - (0.55 * 5 / (0.5 + E.single_fee(0.5)) - 5)) < 0.01)
N, S = 1500, 11


def pe(**k):
    fr = k.pop("fee_rate", None)
    return E.simulate_exit(sp(**k), n_paths=N, seed=S, fee_rate=fr)["p_exit"]


for code in ("nba", "nfl", "nhl"):
    e = [pe(q0=q, code=code) for q in (0.45, 0.5, 0.55, 0.6, 0.65)]
    ok(f"{code}: a stronger edge raises the chance to cash out for a profit {e}", all(x <= y + 0.01 for x, y in zip(e, e[1:])) and e[-1] > e[0] + 0.1)
    t_ = [pe(start=0, f0=f, code=code) for f in (0.1, 0.3, 0.6, 1.0)]
    ok(f"{code}: more game left raises it {t_}", all(x <= y + 0.01 for x, y in zip(t_, t_[1:])) and t_[-1] > t_[0] + 0.1)
    g = [pe(bid=0.5 - gp, code=code) for gp in (0.06, 0.04, 0.02, 0.01)]
    ok(f"{code}: a narrower bid-ask gap raises it (a gap too wide to sell in play = 0) {g}", all(x <= y + 0.01 for x, y in zip(g, g[1:])) and g[0] == 0)
    f_ = [pe(fee_rate=fr, code=code) for fr in (0.0, 0.07, 0.14)]
    ok(f"{code}: a bigger fee lowers it {f_}", all(x >= y - 0.01 for x, y in zip(f_, f_[1:])) and f_[0] > f_[-1])
ok("too little depth at the bid to sell the whole bet: no cash-out", pe(depth=1) == 0)
fav = E.simulate_exit(sp(q0=0.75, ask=0.70, bid=0.68), n_paths=400, seed=3)
ok("a 70c favorite can't reach smart sell's 1.5x profit floor: no cash-out, it's a hold bet", fav["p_exit"] == 0 and fav["route"] == "hold")
E.CFG["ride"] = 4
ro = E.simulate_exit(sp(q0=0.6), n_paths=400, seed=3)
E.CFG["ride"] = 2
ok("Ride it out (smart sell off): only lock-in can sell, so cashing out is rarer", ro["p_exit"] < E.simulate_exit(sp(q0=0.6), n_paths=400, seed=3)["p_exit"])
combo = {"kind": "combo", "tickers": [T, "KXNBAGAME-26NOV21LALMIA-LAL"], "id": "c", "league": "nba", "type": "combo",
         "pays_per": 1.0 / 0.36, "legs": [{"ticker": T, "code": "nba", "q0": 0.6, "ask": 0.57, "bid": 0.55, "start": 3600, "f0": 1, "dur": 9900},
                                          {"ticker": "KXNBAGAME-26NOV21LALMIA-LAL", "code": "nba", "q0": 0.6, "ask": 0.57, "bid": 0.55, "start": 7200, "f0": 1, "dur": 9900}]}
cr = E.simulate_exit(combo, seed=5)
ok("combos simulate too (each pick its own game path)", 0 <= cr["p_exit"] <= 1 and abs(cr["win"] - 0.36) < 1e-9)
t0 = time.perf_counter()
for i in range(40):
    E.simulate_exit(sp(q0=0.5 + i / 400), seed=i)
ms = (time.perf_counter() - t0) / 40 * 1000
t0 = time.perf_counter()
for i in range(10):
    E.simulate_exit(combo, seed=i)
msc = (time.perf_counter() - t0) / 10 * 1000
print(f"timing: {ms:.1f} ms a single/spread/total, {msc:.1f} ms a 2-pick combo ({E.SB_PATHS} paths)")
ok("fast enough for the shadow pass (under 40 ms a single on a slow runner)", ms < 40)

# ---- the price recorder: only prices the engine already read
CALLS.clear()
ms_ = [{"ticker": T, "yes_bid_dollars": "0.48", "yes_ask_dollars": "0.50"},
       {"ticker": "KXNBAGAME-26NOV21BOSNYK-NYK", "yes_bid_dollars": "0.49", "yes_ask_dollars": "0.52"},
       {"ticker": "OTHER", "yes_bid_dollars": "0.10", "yes_ask_dollars": "0.12"}]
E.price_seen_markets(ms_)
E.price_watch([T, "KXNBAGAME-26NOV21BOSNYK-NYK"], kick=now + 3600)
n1 = E.price_flush(now)
rows = E.store_rows("select * from price_path order by ticker")
ok("watched markets get a row (bid, ask, mid); unwatched ones don't", n1 == 2 and {r["ticker"] for r in rows} == {T, "KXNBAGAME-26NOV21BOSNYK-NYK"}
   and rows[0]["bid"] == 0.48 and rows[0]["ask"] == 0.5 and rows[0]["mid"] == 0.49)
ok("no row again right away", E.price_flush(now + 5) == 0)
E.PRICE_SEEN[T] = (now + 30, 0.48, 0.50, None)
ok("near a game: unchanged price within 15 min = no new row", E.price_flush(now + 70) == 0)
E.PRICE_SEEN[T] = (now + 80, 0.51, 0.53, None)
ok("near a game: a changed price a minute later = a new row", E.price_flush(now + 90) == 1)
FAR = "KXNFLGAME-26NOV29KCBUF-KC"
E.price_watch([FAR], kick=now + 3 * 86400)
E.PRICE_SEEN[FAR] = (now + 90, 0.4, 0.42, None)
E.price_flush(now + 95)
E.PRICE_SEEN[FAR] = (now + 150, 0.41, 0.43, None)
far1 = E.price_flush(now + 160)
E.PRICE_SEEN[FAR] = (now + 400, 0.42, 0.44, None)
far2 = E.price_flush(now + 410)
ok("far from a game: every 5 minutes, not every minute", far1 == 0 and far2 == 1)
E.price_seen_book("BOOKED", {"bid": 0.3, "ask": 0.33, "ask_size": 120})
E.price_watch(["BOOKED"])
E.price_flush(time.time())
br = E.store_rows("select depth from price_path where ticker='BOOKED'")
ok("order books the engine read count too, with the size", br and br[0]["depth"] == 120)
ok("the recorder made no network call at all", not CALLS)
E.store_x("insert into price_path(ts, ticker, bid, ask, mid) values(?,?,?,?,?)", (now - 40 * 86400, "OLD", 0.1, 0.2, 0.15))
E.price_prune(now)
ok("rows older than 30 days are pruned", not E.store_rows("select 1 from price_path where ticker='OLD'"))
cap = E.PRICE_MAX_ROWS
E.PRICE_MAX_ROWS = 3
E.price_prune(now)
left = E.store_rows("select count(*) n from price_path")[0]["n"]
E.PRICE_MAX_ROWS = cap
ok("and the table is capped (oldest go first)", left == 3)
_db = E.STORE["db"]
E._price_insert([(now, "BATCH1", 0.1, 0.2, 0.15, None, None), (now, "BATCH2", 0.3, 0.4, 0.35, None, None)])
ok("a flush's rows go in one transaction and are committed",
   not _db.in_transaction and len(E.store_rows("select 1 from price_path where ticker like 'BATCH%'")) == 2)
_db.execute("begin")
E._price_insert([(now, "INTX", 0.1, 0.2, 0.15, None, None)])
ok("inside someone else's transaction the rows join it (no commit of theirs)", _db.in_transaction)
_db.execute("rollback")
ok("...and go with it on their rollback", not E.store_rows("select 1 from price_path where ticker='INTX'"))
E._price_insert([(now, "BAD")])
ok("a bad row never raises and leaves no transaction open", not _db.in_transaction)
E.price_seen_markets([None, {"ticker": None}, {"ticker": "X", "yes_bid": "junk"}])
ok("odd market data never raises", True)

# ---- exit_shadow: old vs new for each candidate, without touching the candidates
E.KICKOFF["KXNBAGAME-26NOV21BOSNYK"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 3 * 3600))
cands = [{"id": "single:" + T, "kind": "single", "code": "nba", "legs": [{"ticker": T, "event": "KXNBAGAME-26NOV21BOSNYK", "p": 0.5, "fair": 0.56}],
          "chance": 0.56, "ret": 0.1, "kick": now + 3 * 3600},
         {"id": "line:KXNBASPREAD-26NOV21BOSNYK-BOS5", "kind": "line", "code": "nba",
          "legs": [{"ticker": "KXNBASPREAD-26NOV21BOSNYK-BOS5", "event": "KXNBASPREAD-26NOV21BOSNYK", "p": 0.45, "fair": 0.5}],
          "chance": 0.5, "ret": 0.1, "kick": now + 3 * 3600},
         {"id": "combo:a+b", "kind": "combo", "code": "nba", "pct": 1.02, "fair_mult": 2.78, "chance": 0.36, "ret": 0.02,
          "legs": [{"ticker": T, "event": "KXNBAGAME-26NOV21BOSNYK", "p": 0.57, "fair": 0.6},
                   {"ticker": "KXNBAGAME-26NOV21LALMIA-LAL", "event": "KXNBAGAME-26NOV21LALMIA", "p": 0.57, "fair": 0.6}]},
         {"id": "early:x", "kind": "early", "legs": [{"ticker": T, "p": 0.7, "fair": 0.7}]},
         {"id": "junk", "kind": "single", "legs": [{"ticker": "", "p": None}]}]
snap = copy.deepcopy(cands)
CALLS.clear()
n = E.smart_buy_shadow(cands, "panel", now=now)
sh = E.store_rows("select * from exit_shadow order by kind")
ok("one exit_shadow row per candidate it can model (single, spread, combo; not sell-early or junk)", n == 3 and len(sh) == 3)
ok("each row has the edge, chance to cash out, expected dollars, route, and old vs new", all(
    r["exit_chance"] is not None and r["ev"] is not None and r["route"] in ("sell", "hold", "none") and r["old"] == 1 and r["new"] in (0, 1)
    and r["ver"] == E.EXIT_POLICY_VERSION for r in sh))
ok("the candidates themselves are untouched", cands == snap)
ok("the same candidates again within half an hour: no new rows", E.smart_buy_shadow(cands, "panel", now=now + 60) == 0)
ok("their markets are now recorded too", T in E.PRICE_WATCH and "KXNBASPREAD-26NOV21BOSNYK-BOS5" in E.PRICE_WATCH)
ok("logging made no network call", not CALLS)
ok("a broken candidate list never raises", E.smart_buy_shadow([{"legs": "x"}, None], "panel", now=now) == 0)
E.SB_CACHE["seen"].clear()
t0 = time.perf_counter()
E.smart_buy_shadow([dict(cands[0], id=f"single:{i}") for i in range(500)], "panel", now=now + 5000, budget=0.2)
ok("the shadow pass keeps to its time budget", time.perf_counter() - t0 < 1.0)

# ideas (Live's Buy ideas) are logged from the suggestions table, read-only
E.store_x("insert into suggestions(id, ts, lg, legs, picks, n, pct, pays, stake, fair, kick, live) values(?,?,?,?,?,?,?,?,?,?,?,?)",
          ("idea1", now, "nba", json.dumps([T]), "BOS", 1, 1.05, 10.5, 5.0, 0, now + 3 * 3600, 0))
E.PRICE_SEEN[T] = (now, 0.48, 0.50, None)
E.SB_CACHE["ideas"] = 0
ok("Buy ideas get a row too (source 'idea')", E.smart_buy_shadow_ideas(now=now) == 1
   and E.store_rows("select count(*) n from exit_shadow where source='idea'")[0]["n"] == 1)

# ---- calibration: replays the exit rule on recorded prices
row = {"price": 0.5, "tickers": json.dumps([T]), "kick": now - 4 * 3600}
up = [(now - 4 * 3600 + i * 600, b_, b_ + 0.01, b_ + 0.005) for i, b_ in enumerate((0.5, 0.6, 0.7, 0.8, 0.9, 0.95))]
flat = [(now - 4 * 3600 + i * 600, 0.49, 0.5, 0.495) for i in range(8)]
ok("a recorded path that climbs to 90c in play: the exit rule fires for a profit", E.exit_replay(row, up) is True)
ok("a flat path: it never fires", E.exit_replay(row, flat) is False)
ok("too few prices: can't judge", E.exit_replay(row, up[:2]) is None)
TC = "KXNBAGAME-26NOV20AAABBB-AAA"
E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, kick, price, fair, exit_chance, route, old, new, ver) "
          "values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (now - 9 * 3600, "single:" + TC, "panel", "nba", "single", json.dumps([TC]),
                                                   now - 8 * 3600, 0.5, 0.55, 0.6, "sell", 1, 1, 1))
for ts, b_, a_, m_ in up:
    E.store_x("insert into price_path(ts, ticker, bid, ask, mid) values(?,?,?,?,?)", (ts - 4 * 3600, TC, b_, a_, m_))
cal = E.exit_calibration(now=now)
ok("exit_calibration: predicted vs actual for finished games, per league and type",
   any(x["league"] == "nba" and x["kind"] == "single" and x["n"] == 1 and x["pred"] == 0.6 and x["actual"] == 1.0 for x in cal))

# ---- Results › What's working preview
E.save_json(E.MAIN_SAVED, {"smart_buy_gate": False})       # Pete switched it off (stage 2: on by default)
s = E.smart_buy_summary(now=now)
ok("the summary lists leagues with sample sizes, and is marked off when switched off", s["on"] is False and s["rows"]
   and all(k in s["rows"][0] for k in ("name", "kind", "n", "ok", "p_exit", "ev")) and s["calib"])
E.save_json(E.MAIN_SAVED, {"smart_buy_gate": True})
ok("...and on once the switch is on", E.smart_buy_summary(now=now)["on"] is True)
E.ANALYTICS.update(at=0, v=None)
an = E.analytics(max_age=0)
ok("analytics() carries it for the page when the switch is on", isinstance(an.get("smart_buy"), dict) and "rows" in an["smart_buy"])
E.save_json(E.MAIN_SAVED, {"smart_buy_gate": False})
E.ANALYTICS.update(at=0, v=None)
real_cal = E.exit_calibration
E.exit_calibration = lambda **k: (_ for _ in ()).throw(AssertionError("calibration ran with the switch off"))
an = E.analytics(max_age=0)
E.exit_calibration = real_cal
ok("...and does no Smart Buy work at all when it's off", an.get("smart_buy") == {"on": False})
E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, kick, price, fair, exit_chance, route, old, new, ver) "
          "values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (now - 8.5 * 3600, "single:" + TC, "panel", "nba", "single", json.dumps([TC]),
                                                   now - 8 * 3600, 0.5, 0.55, 0.2, "sell", 1, 1, 1))
cal = E.exit_calibration(now=now)
ok("a bet checked again every half hour counts once (its first check) in calibration",
   any(x["league"] == "nba" and x["kind"] == "single" and x["n"] == 1 and x["pred"] == 0.6 for x in cal))
s = E.smart_buy_summary(now=now)
nba = [r for r in s["rows"] if r["name"] == "NBA" and r["kind"] == "Single games"]
ok("...and once in the preview's counts", nba and nba[0]["n"] == E.store_rows(
    "select count(distinct cand) n from exit_shadow where league='nba' and kind='single'")[0]["n"])

# held singles: only freshly read prices are recorded, with their game's kickoff
E.requests = type("R", (), {"RequestException": NoNet.RequestException, "get": staticmethod(
    lambda *a, **k: (_ for _ in ()).throw(NoNet.RequestException("429")))})()
HS = "KXNBAGAME-26NOV21BOSNYK-NYK"
E.ACCT_POS.update(at=time.time(), items=[{"ticker": HS, "position_fp": "3"}])
E.SINGLES.update(at=0, items=[], mk={HS: {"ticker": HS, "event_ticker": "KXNBAGAME-26NOV21BOSNYK", "yes_bid_dollars": "0.10", "yes_ask_dollars": "0.12"}})
E.PRICE_SEEN.pop(HS, None)
try:
    E.open_singles(max_age=0)
except Exception as err:
    print("open_singles:", type(err).__name__, err)
ok("a failed held-markets refresh never records the old copy as a fresh price", HS not in E.PRICE_SEEN)
ok("held singles are watched with their game's kickoff (recorded every minute near it)",
   HS in E.PRICE_WATCH and E.PRICE_WATCH[HS][1] == E._kick_ts({"event": "KXNBAGAME-26NOV21BOSNYK"}) and E.PRICE_WATCH[HS][1])
E.requests = NoNet()

# idea combos: the chance is shared out by each pick's price, and stale asks are skipped
TB = "KXNBAGAME-26NOV21LALMIA-LAL"
E.store_x("insert into suggestions(id, ts, lg, legs, picks, n, pct, pays, stake, fair, kick, live) values(?,?,?,?,?,?,?,?,?,?,?,?)",
          ("idea2", now, "nba", json.dumps([T, TB]), "BOS + LAL", 2, 1.0, 5 / 0.21 * 1.0, 5.0, 0, now + 3 * 3600, 0))
E.PRICE_SEEN[T], E.PRICE_SEEN[TB] = (now, 0.28, 0.30, None), (now, 0.68, 0.70, None)
got = []
real_sh = E.smart_buy_shadow
E.smart_buy_shadow = lambda cands, source="panel", now=None, budget=0: got.extend(cands) or 0
E.SB_CACHE["ideas"] = 0
E.smart_buy_shadow_ideas(now=now)
c2 = [c for c in got if c["id"] == "idea:idea2"]
ok("an idea combo's picks get fair chances in proportion to their prices (not one shared number)",
   c2 and abs(c2[0]["legs"][0]["fair"] / c2[0]["legs"][1]["fair"] - 0.3 / 0.7) < 1e-6
   and abs(c2[0]["legs"][0]["fair"] * c2[0]["legs"][1]["fair"] - 0.21) < 1e-6)
got.clear(); E.PRICE_SEEN[TB] = (now - 3600, 0.68, 0.70, None); E.SB_CACHE["ideas"] = 0
E.smart_buy_shadow_ideas(now=now)
ok("an idea whose pick's ask is over 15 min old is skipped", not [c for c in got if c["id"] == "idea:idea2"])
E.smart_buy_shadow = real_sh

# ---- the switch off (and the logging) changes nothing in the panel
E.fetch_markets = lambda: []
E.load_book_state = lambda snap: {}
tag = time.strftime("%y%b%d", time.gmtime(now)).upper()
EV = [f"KXNHLGAME-{tag}PHIBOS", f"KXNHLGAME-{tag}COLSJ", f"KXNHLGAME-{tag}VGKLAK"]
games = {}
for ev in EV:
    E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 5 * 3600))
    games[ev] = [{"event": ev, "ticker": ev + "-A", "abbr": "A", "pick": "A", "p": .40, "tie": False, "bid": .39, "exp": "", "fair": .52, "src": "Pinnacle"},
                 {"event": ev, "ticker": ev + "-B", "abbr": "B", "pick": "B", "p": .62, "tie": False, "bid": .61, "exp": "", "fair": .48, "src": "Pinnacle"}]
E.week_games = lambda mk, **k: ({e: [dict(x) for x in s] for e, s in games.items()}, {}, None)
E.attach_fair = lambda g, b: None
E.record_closes = lambda g, c: None
E.live_panel_on = lambda: False
E.calib_fair = lambda code, fair, ticker=None: fair
E.line_candidates = lambda code, everything=False: []
E.value_combos = lambda g, k=6, live_ok=(), max_legs=None: [{"legs": [g[EV[0]][0], g[EV[2]][0]], "value_pct": 1.2}]
E.predict_quote = lambda c: None
E.combo_cutoff = lambda *a, **k: 0.9
E.SB_CACHE["seen"].clear()
real_shadow = E.smart_buy_shadow
outs = []
for on, shadow in ((False, real_shadow), (True, real_shadow), (False, lambda *a, **k: 0)):
    E.save_json(E.MAIN_SAVED, {"smart_buy_gate": on})
    E.smart_buy_shadow = shadow
    cs = E.panel_collect({}, "nhl", log=lambda *a: None)
    picked, st = E.choose_panel(cs, 40, 300.0, size=6)
    outs.append((json.dumps(cs, sort_keys=True), [c["id"] for c in picked], [c["stake"] for c in picked], st))
E.smart_buy_shadow = real_shadow
E.save_json(E.MAIN_SAVED, {})
ok("panel candidates are identical with Smart Buy on, off, or its logging removed", outs[0][0] == outs[1][0] == outs[2][0])
ok("...and so are the panel's picks, stakes and odds", outs[0][1:] == outs[1][1:] == outs[2][1:] and outs[0][1])
ok("panel_collect's Smart Buy logging wrote rows", E.store_rows("select count(*) n from exit_shadow where cand like 'panel:%KXNHL%'")[0]["n"] > 0)
