# CHECK: group=engine
# Spreads and totals, the margin-shape model (issue #117, part A): the distributions, the strike-distance
# calibration (borrowing like the moneylines), the per-league gate and its Settings switch, both prices logged side by
# side, and the promise that with the gate off every spread/total price is today's, byte for byte, and the panel's
# choice of bets doesn't change (with it on, only the chances do).
import os, json, math, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.book_depth = lambda t, max_age=60: None   # no order book (never Kalshi's real one: netguard); a fake ticker read None there too
E.books_batch = lambda tickers, timeout=10: set()   # the batch read is a Kalshi call too (#225): none, so books_now reads singly (stubbed above)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.MAIN_SAVED = os.path.join(E.HERE, "none.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
SHIPPED = (json.loads(json.dumps(E.LINE_TABLES)), json.loads(json.dumps(E.LINE_EVIDENCE)))
FIX = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "espn_margins.json")))

# ---- the shipped tables: small, every league the panel prices, sports to borrow from
ok("shipped tables cover the leagues with lines", all(lg in E.LINE_TABLES["leagues"] for lg in ("nfl", "ncaaf", "nba", "ncaamb", "ncaawb", "nhl")))
ok("...and the sports, for leagues ESPN doesn't cover (AHL, EuroLeague)", {"football", "basketball", "hockey", "soccer"} <= set(E.LINE_TABLES["sports"]))
ok("...small (no scraped dumps in the engine)", len(json.dumps(E.LINE_TABLES)) + len(json.dumps(E.LINE_EVIDENCE)) < 60000)
ok("borrowing: the AHL uses hockey's shape, EuroLeague basketball's", E.line_params("ahl", "spread") == E.LINE_TABLES["sports"]["hockey"]["spread"]
   and E.line_params("euroleague", "total") == E.LINE_TABLES["sports"]["basketball"]["total"])
ok("a league with its own table uses it", E.line_params("nfl", "spread") is E.LINE_TABLES["leagues"]["nfl"]["spread"])
ok("an unknown league has nothing (falls back to the old model)", E.line_params("ufc", "spread") is None and E.margin_prob("ufc", "spread", 1.5, True, {"spread_home": -3}) is None)

# ---- the distributions
g = {"spread_home": -3.0, "total": 44.5}
p = E.margin_pmf("nfl", "spread", g)
ok("NFL margin adds up to 1", abs(sum(p.values()) - 1) < 1e-9)
ok("NFL key numbers: winning by 3 or 7 is likelier than by 2/4 or 6/8 (line -3)", p[3] > p[2] and p[3] > p[4] and p[7] > p[6] and p[7] > p[8])
ok("NFL: a 3-point line puts a big chunk exactly on 3 (a push risk the normal curve hides)", p[3] > 0.06 > E._phi(0.5 / 13.5) - E._phi(-0.5 / 13.5))
probs = [E.margin_prob("nfl", "spread", k + 0.5, True, g) for k in range(-10, 15)]
ok("chance falls as the strike rises (spreads)", all(a > b for a, b in zip(probs, probs[1:])))
ok("anchored: a half-point line with even prices is 50/50", abs(E.margin_prob("nfl", "spread", 3.5, True, {"spread_home": -3.5}) - 0.5) < 1e-6)
ok("...and follows the sportsbook's price when it isn't even",
   abs(E.margin_prob("nfl", "spread", 3.5, True, {"spread_home": -3.5, "p_hcover": 0.55}) - 0.55) < 1e-6)
up, at, dn = (sum(v for x, v in p.items() if x > 3), p.get(3, 0), sum(v for x, v in p.items() if x < 3))
ok("whole-number line: P(over) + P(push) + P(under) = 1, and over = under once the push is set aside",
   abs(up + at + dn - 1) < 1e-9 and abs(up / (up + dn) - 0.5) < 1e-6)
ok("Kalshi's 'wins by over 3' is strict: a 3-point win loses it", abs(E.margin_prob("nfl", "spread", 3, True, g) - up) < 1e-12)
ok("...and a half point is exactly the complement of the other side",
   abs(E.margin_prob("nfl", "spread", 3.5, True, g) + E.margin_prob("nfl", "spread", -3.5, False, g) - 1) < 1e-9)
ok("the underdog side reads the same curve from the other end",
   abs(E.margin_prob("nfl", "spread", -2.5, False, g) - sum(v for x, v in p.items() if -x > -2.5)) < 1e-12)
b = E.margin_pmf("nba", "spread", {"spread_home": -1.5})
ok("basketball never ties: no chance on a 0 margin", b.get(0, 0) == 0 and abs(sum(b.values()) - 1) < 1e-9)
c = E.margin_pmf("ncaaf", "spread", {"spread_home": -0.5})
ok("college football never ties either", c.get(0, 0) == 0)
t = E.margin_pmf("nba", "total", {"total": 224.5, "p_over": 0.5})
tp = [E.margin_prob("nba", "total", k + 0.5, True, {"total": 224.5}) for k in range(210, 240)]
ok("totals add up to 1 and fall as the strike rises", abs(sum(t.values()) - 1) < 1e-9 and all(a > b for a, b in zip(tp, tp[1:])))
ok("total anchored on its line", abs(E.margin_prob("nba", "total", 224.5, True, {"total": 224.5}) - 0.5) < 1e-6)
hk = {"total": 5.5, "p_over": 0.48, "p_home": 0.6, "p_away": 0.4}
hm, ht = E.margin_pmf("nhl", "spread", hk), E.margin_pmf("nhl", "total", hk)
ok("hockey: margin and total add up to 1", abs(sum(hm.values()) - 1) < 1e-9 and abs(sum(ht.values()) - 1) < 1e-9)
ok("hockey: no ties (overtime/shootout), the moneyline's split kept",
   hm.get(0, 0) == 0 and abs(sum(v for x, v in hm.items() if x > 0) - 0.6) < 1e-9)
ok("hockey: the total keeps the line's over chance", abs(E.margin_prob("nhl", "total", 5.5, True, hk) - 0.48) < 1e-6)
ok("hockey: winning by 2+ is less likely than winning", 0 < E.margin_prob("nhl", "spread", 1.5, True, hk) < 0.6)
sc = {"total": 2.5, "p_over": 0.52, "p_home": 0.45, "p_away": 0.28, "p_draw": 0.27}
sm = E.margin_pmf("epl", "spread", sc)
ok("soccer: the draw keeps the market's chance", abs(sm.get(0, 0) - 0.27) < 1e-9 and abs(sum(sm.values()) - 1) < 1e-9)
ok("soccer without a draw price: not priced (old model stays)", E.margin_pmf("epl", "spread", dict(sc, p_draw=None)) is None)
ok("a broken line is never priced", E.margin_prob("nfl", "spread", 3.5, True, {"spread_home": -185}) is None
   and E.margin_prob("nfl", "spread", 3.5, True, {}) is None)
ok("American prices de-vig", abs(E._devig("-110", "-110") - 0.5) < 1e-9 and abs(E._am_prob("+150") - 0.4) < 1e-9 and E._am_prob("EVEN") == 0.5
   and E._am_prob("junk") is None and E._am_prob(None) is None)

# ---- shrinkage: a league with few games stays near its sport's shape (built by the same rule as the tool)
_ts = importlib.util.spec_from_file_location("T", os.path.join(os.environ["REPO"], "tools", "build_line_tables.py"))
T = importlib.util.module_from_spec(_ts); _ts.loader.exec_module(T)
few = T._weights([0], [2.0], {3: 1.4}, [3])            # 2 expected, none seen, sport says 1.4
lots = T._weights([0], [2000.0], {3: 1.4}, [3])        # 2,000 expected, none seen
none = T._weights([5], [5.0], None, [3])               # seen exactly as often as expected
ok("shrinkage: a league with few games stays near its sport's weight", abs(few[3] - (30 * 1.4) / 32) < 1e-3)
ok("shrinkage: with lots of games a league's own record wins", lots[3] < 0.03)
ok("shrinkage: a weight that doesn't move isn't shipped (tables stay small)", none == {})

# ---- real ESPN games (fixture): the model is sane on them
for lg, games in FIX.items():
    old_ll = new_ll = n = 0
    for x in games:
        gg = {"spread_home": x["S"], "total": x["T"]}
        for L in (x["S"] * -1 - 3.5, x["S"] * -1 + 0.5, x["S"] * -1 + 3.5):
            L = math.floor(L) + 0.5
            o = E.line_fair(lg, "spread", L, True, gg)
            nw = E.margin_prob(lg, "spread", L, True, gg)
            y = x["hs"] - x["as"] > L
            old_ll += -math.log(o if y else 1 - o)
            new_ll += -math.log(nw if y else 1 - nw)
            n += 1
    ok(f"real {lg.upper()} games ({len(games)}): every new price is a real chance, and no worse than 5% off the old on average",
       n > 0 and new_ll / n < old_ll / n * 1.05)
nfl_m = [abs(x["hs"] - x["as"]) for x in FIX.get("nfl", [])]
ok("real NFL games land on 3 and 7 more than on 2 and 4 (what the key weights learned)", nfl_m.count(3) + nfl_m.count(7) > nfl_m.count(2) + nfl_m.count(4))

# ---- calibration by distance from the line: borrows everyone -> sport -> league, n counts games
E._line_fair_table()
ok("no record: the model's chance is used as is", E.calib_line("nba", "nba", "spread", "above", 0.4) == 0.4)
now = time.time()
def add(tk, sport, lg, kind, bucket, new, y, old=0.4):
    E.store_x("insert into line_fairs values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (tk, now - 9000, sport, lg, kind, 1.5, bucket, old, new, new, "old", 0.4, now - 8000, "yes" if y else "no"))
for i in range(100):                        # 100 other-sport games where 40% chances won 60% of the time
    add(f"KXNFLSPREAD-G{i}-A", "nfl", "nfl", "spread", "above", 0.4, i < 60)
E.LINE_STATS["at"] = 0
got = E.calib_line("nba", "nba", "spread", "above", 0.4)
ok("other sports' record nudges by n/(n+300) (100 games: a quarter of the gap)", abs(got - (0.4 + 0.25 * 0.2)) < 1e-6)
for i in range(4):                          # 4 strikes of ONE game count as one game
    add(f"KXNBASPREAD-ONE-S{i}", "nba", "nba", "spread", "above", 0.4, False)
E.LINE_STATS["at"] = 0
one = E.calib_line("nba", "nba", "spread", "above", 0.4)
ok("strikes of one game count as one game", abs(one - (0.45 + 1 / 301 * (0.0 - 0.4 - 0.05))) < 1e-6)
ok("a different bucket or kind is untouched", E.calib_line("nba", "nba", "total", "above", 0.4) == 0.4 and E.calib_line("nba", "nba", "spread", "below", 0.4) == 0.4)
ok("buckets: how far the strike is from the line", E.line_bucket("nfl", "spread", 3.5, 3.0) == "at the line" and E.line_bucket("nfl", "spread", 14.5, 3.0) == "far above"
   and E.line_bucket("nhl", "total", 4.5, 5.5) == "far below" and E.line_bucket("nba", "total", 220.5, 224.5) == "below")
E.store_x("delete from line_fairs"); E.LINE_STATS["at"] = 0

# ---- the gate, per league and kind
E.LINE_EVIDENCE = {"nfl": {"spread": {"games": 1000, "ll_old": 0.62, "ll_new": 0.61, "se": 0.001},
                           "total": {"games": 800, "ll_old": 0.65, "ll_new": 0.649, "se": 0.001}},
                   "nba": {"spread": {"games": 150, "ll_old": 0.66, "ll_new": 0.60, "se": 0.001}},
                   "epl": {"total": {"games": 900, "ll_old": None, "ll_new": 0.67}}}
ok("gate on: beat the old model clearly on 200+ games", E.line_gate("nfl", "spread")[0])
ok("gate off: a gain too small to trust (by kind)", not E.line_gate("nfl", "total")[0])
ok("gate off: under 200 past games", not E.line_gate("nba", "spread")[0])
ok("gate off: nothing to compare against", not E.line_gate("epl", "total")[0] and "nothing to compare" in E.line_gate("epl", "total")[1])
ok("gate off: a league with no evidence at all", not E.line_gate("ncaawb", "spread")[0])
E.CFG["line_model"] = False
ok("Settings switch off: every league uses the old model", not E.line_gate("nfl", "spread")[0] and "Settings" in E.line_gate("nfl", "spread")[1])
json.dump({"line_model": True}, open(E.MAIN_SAVED, "w"))
ok("...the shared settings file wins (the Mac and the web app agree)", E.line_gate("nfl", "spread")[0])
os.remove(E.MAIN_SAVED); E.CFG["line_model"] = True
for i in range(210):                        # the Mac's own record: worse than the old model -> off, whatever the backtest
    add(f"KXNFLSPREAD-L{i}-A", "nfl", "nfl", "spread", "above", 0.9, False, old=0.3)
E.LINE_STATS["at"] = 0
ok("your own settled markets (200+ games) switch it off when the new prices did worse", not E.line_gate("nfl", "spread")[0]
   and "Worse" in E.line_gate("nfl", "spread")[1])
acc = {(r["lg"], r["kind"]): r for r in E.line_accuracy()}
ok("Results lists old vs new with sample sizes and the gate state", acc[("nfl", "spread")]["live_n"] == 210 and acc[("nfl", "spread")]["bt_games"] == 1000
   and acc[("nfl", "spread")]["on"] is False and ("epl", "total") in acc)
E.store_x("delete from line_fairs"); E.LINE_STATS["at"] = 0

# ---- line_candidates: gate off = today's prices byte for byte; both prices logged; gate on = only chances change
E.espn_lines = lambda code: {
    frozenset({"temple owls", "tulane green wave"}): {"home": "Tulane Green Wave", "away": "Temple Owls", "home_abbr": "TUL", "away_abbr": "TEM",
                                                      "spread_home": -7.5, "total": 140.5, "start": "2099-01-01T00:00:00Z", "p_hcover": 0.52, "p_over": 0.49},
    frozenset({"brown bears", "yale bulldogs"}): {"home": "Yale Bulldogs", "away": "Brown Bears", "home_abbr": "YALE", "away_abbr": "BRWN",
                                                  "spread_home": -3.0, "total": 132.0, "start": "2099-01-01T00:00:00Z"}}


def m(ev, tk, sub, strike, p, kind):
    return {"ticker": tk, "event_ticker": ev, "yes_sub_title": sub, "floor_strike": strike, "yes_ask_dollars": str(p + .01),
            "yes_bid_dollars": str(p - .01), "last_price_dollars": str(p), "kind": kind}


MK = []
for k, pr in ((3.5, .62), (5.5, .55), (7.5, .40), (9.5, .44), (11.5, .30)):
    MK.append(m("KXNCAAMBSPREAD-99JAN01TEMTUL", f"KXNCAAMBSPREAD-99JAN01TEMTUL-TUL{int(k)}", f"Tulane Green Wave wins by over {k} Points", k, pr, "spread"))
for k, pr in ((0.5, .48), (2.5, .38), (3.5, .45)):
    MK.append(m("KXNCAAMBSPREAD-99JAN01BRWNYALE", f"KXNCAAMBSPREAD-99JAN01BRWNYALE-YALE{int(k)}", f"Yale wins by over {k} Points", k, pr, "spread"))
for k, pr in ((134.5, .66), (138.5, .52), (140.5, .44), (144.5, .30), (130.5, .58), (132, .45)):
    ev = "KXNCAAMBTOTAL-99JAN01TEMTUL" if k > 134 else "KXNCAAMBTOTAL-99JAN01BRWNYALE"
    MK.append(m(ev, f"{ev}-{k:g}", f"Over {k} Points scored", k, pr, "total"))
E.line_markets = lambda code: [dict(x) for x in MK]
E.price = lambda mm: float(mm["last_price_dollars"])
_real_pick = E._line_pick_model
E.LINE_EVIDENCE = {}
ref = {}
for everything in (True, False):            # today's pipeline: the new model cut out entirely
    E._line_pick_model = lambda code, mk, line, home, gg, old, p: (old, None)
    ref[everything] = json.dumps(E.line_candidates("ncaamb", everything=everything), sort_keys=True)
E._line_pick_model = _real_pick
E.CFG["line_model"] = False
off = {ev: json.dumps(E.line_candidates("ncaamb", everything=ev), sort_keys=True) for ev in (True, False)}
ok("Settings off: every spread/total candidate is byte for byte today's", off == ref)
E.CFG["line_model"] = True
auto_fail = {ev: json.dumps(E.line_candidates("ncaamb", everything=ev), sort_keys=True) for ev in (True, False)}
ok("auto, but the league hasn't passed its gate: still byte for byte today's", auto_fail == ref)
rows = E.store_rows("select * from line_fairs")
ok("both prices logged for every market from day one (old and new side by side)",
   len(rows) == len(MK) and all(r["fair_old"] is not None and r["fair_new"] is not None and r["fair_cal"] is not None for r in rows))
ok("...with the model actually used, the strike, its distance band, Kalshi's price and the game's start",
   all(r["used"] == "old" and r["bucket"] and r["price"] and r["kick"] > time.time() and r["league"] == "ncaamb" for r in rows))
E.line_candidates("ncaamb", everything=True)
ok("one row per market per half hour (no flood)", len(E.store_rows("select * from line_fairs")) == len(MK))
E.store_x("delete from line_fairs")
E.LINE_EVIDENCE = {"ncaamb": {"spread": {"games": 9000, "ll_old": 0.64, "ll_new": 0.62, "se": 0.001},
                              "total": {"games": 9000, "ll_old": 0.66, "ll_new": 0.65, "se": 0.001}}}
on = E.line_candidates("ncaamb", everything=True)
old_all = {x["ticker"]: x for x in json.loads(ref[True])}
ok("gate on: the same markets, the same bets, only the chance (and the edge from it) changes",
   {x["ticker"] for x in on} == set(old_all) and all({k: v for k, v in x.items() if k not in ("fair", "edge", "model")} ==
                                                      {k: v for k, v in old_all[x["ticker"]].items() if k not in ("fair", "edge")} for x in on))
ok("gate on: those chances come from the margin model and are marked so",
   all(x.get("model") == "margin" for x in on) and any(abs(x["fair"] - old_all[x["ticker"]]["fair"]) > 0.005 for x in on))
ok("gate on: logged as used=new", all(r["used"] == "new" for r in E.store_rows("select used from line_fairs")))
ok("whole-number total (132): the new model sets the push aside, the old curve can't",
   next(x for x in on if x["line"] == 132)["fair"] != old_all["KXNCAAMBTOTAL-99JAN01BRWNYALE-132"]["fair"])
_mp = E.margin_prob
E.margin_prob = lambda *a, **k: 1 / 0
ok("a broken new model never breaks pricing: today's prices come back", json.dumps(E.line_candidates("ncaamb", everything=True), sort_keys=True) == ref[True])
E.margin_prob = _mp

# ---- the panel: candidate selection unchanged with the gate off; with it on only the prices of line bets move
spec2 = importlib.util.spec_from_file_location("E2", "wahome/engine.py"); E2 = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(E2)
E2.book_depth = E.book_depth
E2.books_batch = E.books_batch
E2.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E2.HERE = tempfile.mkdtemp(); E2.MAIN_SAVED = os.path.join(E2.HERE, "none.json")
E2.espn_lines, E2.line_markets, E2.price = E.espn_lines, E.line_markets, E.price
E2.load_book_state = lambda snap: {}
E2.fetch_markets = lambda: []
E2.week_games = lambda mk, **k: ({}, {}, None)
E2.attach_fair = lambda g, b: None
E2.record_closes = lambda g, c: None
E2.live_panel_on = lambda: False
E2.value_combos = lambda g, k=6, live_ok=(), max_legs=None: []
E2.sell_early_candidates = lambda g: []
def panel(gate):
    E2.CFG["line_model"] = gate
    E2.LINE_EVIDENCE = E.LINE_EVIDENCE if gate else {}
    E2.store_x("delete from line_fairs")
    E2.LINE_CACHE.clear()
    return [c for c in E2.panel_collect({}, "ncaamb", log=lambda *a: None) if c["kind"] == "line"]


E2_pick = E2._line_pick_model
E2._line_pick_model = lambda code, mk, line, home, gg, old, p: (old, None)
base = panel(False)
E2._line_pick_model = E2_pick
off_p, on_p = panel(False), panel(True)


def strip(cs, drop=()):
    return json.dumps([dict({k: v for k, v in c.items() if k not in drop},
                            legs=[{k: v for k, v in l.items() if k not in drop} for l in c["legs"]]) for c in cs], sort_keys=True, default=str)


PRICE = ("fair", "chance", "ret")
ok("panel, gate off: the same line candidates as today, byte for byte", strip(off_p) == strip(base) and len(base) > 0)
ok("panel, gate on: the bets both versions pick are identical apart from the chance and the return from it",
   all(strip([c], PRICE) == strip([b], PRICE) for c in on_p for b in base if b["id"] == c["id"]) and any(c["id"] in {b["id"] for b in base} for c in on_p))
allm = E2.line_candidates("ncaamb", everything=True)
want = {"line:" + x["ticker"] for x in allm if x["edge"] >= E2.LINE_MIN_EDGE and x["edge"] / x["p"] >= 0.06}
ok("panel, gate on: a bet comes or goes only when its new chance crosses the same edge rule", {c["id"] for c in on_p} == want)

# ---- review fixes: a price for another line never anchors the curve; void markets stop being asked about; the
# Mac's own 200+ games decide alone; the shipped evidence is valid Python; a partial rebuild keeps the rest
od = {"pointSpread": {"home": {"close": {"line": "-3", "odds": "-125"}}, "away": {"close": {"line": "+3", "odds": "+105"}}},
      "total": {"over": {"close": {"line": "o44.5", "odds": "-115"}}, "under": {"close": {"line": "u44.5", "odds": "-105"}}},
      "moneyline": {"home": {"close": {"odds": "-170"}}, "away": {"close": {"odds": "+145"}}}}
got = E.espn_line_prices(od, -3.5, 44.5)
ok("a spread price for a different line (-3 vs the game's -3.5) is dropped; the total's own price kept",
   "p_hcover" not in got and abs(got["p_over"] - E._devig("-115", "-105")) < 1e-3 and "p_home" in got)
got = E.espn_line_prices(od, -3.0, 45.5)
ok("...and the other way round", "p_over" not in got and "p_hcover" in got)
ok("no line text at all: the price isn't trusted", "p_hcover" not in E.espn_line_prices(
    {"pointSpread": {"home": {"close": {"odds": "-125"}}, "away": {"close": {"odds": "+105"}}}}, -3.5, None))
ok("the shipped evidence is valid Python (no JSON null) and lists the leagues tested",
   all(lg in SHIPPED[1] for lg in ("nfl", "ncaaf", "nba", "ncaamb", "ncaawb", "nhl")) and SHIPPED[1]["nhl"]["spread"]["ll_old"] is None)
E.store_x("delete from line_fairs"); E.LINE_STATS["at"] = 0
ok("a market with no known start isn't logged", E.note_line_fair("KXNFLSPREAD-X-A", "nfl", "nfl", "spread", 3.5, "above", .4, .41, .41, "old", .4, None) is None
   and not E.store_rows("select 1 from line_fairs"))
old_now = time.time()
for i in range(160):                        # 160 voided markets would block the oldest-first queue forever
    E.store_x("insert into line_fairs values(?,?,?,?,?,?,?,?,?,?,?,?,?,null)", (f"KXNFLSPREAD-V{i}-A", old_now - 90000, "nfl", "nfl", "spread", 3.5, "above", .4, .4, .4, "old", .4, old_now - 80000))
E.store_x("insert into line_fairs values(?,?,?,?,?,?,?,?,?,?,?,?,?,null)", ("KXNFLSPREAD-NEW-A", old_now - 20000, "nfl", "nfl", "spread", 3.5, "above", .4, .4, .4, "old", .4, old_now - 15000))
E.store_x("insert into line_fairs values(?,?,?,?,?,?,?,?,?,?,?,?,?,null)", ("KXNFLSPREAD-NEW-A", old_now - 19000, "nfl", "nfl", "spread", 3.5, "above", .4, .45, .45, "old", .4, old_now - 15000))
_fr = E.fetch_results
def fake_results(tks):
    for t in tks:
        E.MARKET_INFO[t] = {"status": "finalized" if "-V" in t else "settled"}
    return {t: "yes" for t in tks if "NEW" in t}
E.fetch_results = fake_results
E.resolve_line_fairs(limit=150)
E.fetch_results = _fr
ok("the newest finished market is resolved first, voided ones are marked and never asked about again",
   E.store_rows("select outcome from line_fairs where ticker='KXNFLSPREAD-NEW-A'")[0]["outcome"] == "yes"
   and E.store_rows("select count(*) n from line_fairs where outcome='void'")[0]["n"] >= 149)
ok("...only the last reading before the game is kept once it settles",
   [r["fair_new"] for r in E.store_rows("select fair_new from line_fairs where ticker='KXNFLSPREAD-NEW-A'")] == [0.45])
E.LINE_STATS["at"] = 0
ok("void markets stay out of the record", all(r["event"] != "KXNFLSPREAD-V1" for r in E.line_record()))
E.store_x("delete from line_fairs"); E.LINE_STATS["at"] = 0
E.LINE_EVIDENCE = {"nfl": {"spread": {"games": 1000, "ll_old": 0.62, "ll_new": 0.61, "se": 0.001}}}
for i in range(210):                        # own record: new barely better (gain < 0.002) -> off despite the backtest
    E.store_x("insert into line_fairs values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (f"KXNFLSPREAD-T{i}-A", now - 9000, "nfl", "nfl", "spread", 3.5, "above", 0.5, 0.501, 0.501, "new", .5, now - 8000, "yes" if i % 2 else "no"))
E.LINE_STATS["at"] = 0
on, why = E.line_gate("nfl", "spread")
ok("200+ of your own games decide alone: not clearly better = off, whatever the backtest said", not on and "Not clearly better" in why)
st1 = E.line_live_stats(); st2 = E.line_live_stats()
ok("the record's sums are worked out once per read, not once per market", st1 is st2)
E.store_x("delete from line_fairs"); E.LINE_STATS["at"] = 0
src = open(os.path.join(os.environ["REPO"], "tools", "build_line_tables.py")).read()
ok("the tool writes a Python literal and a partial rebuild keeps the other leagues' evidence",
   T._compact({"a": None, "b": 1}) == '{"a":None,"b":1}' and "dict(shipped, **ev)" in src)
E.LINE_CACHE.clear(); E.LINE_CACHE[("x",)] = None
ok("a cache read never raises (another thread may clear it)", E.margin_pmf("nfl", "spread", {"spread_home": -3.0}) is not None)
ok("the line helpers don't shadow the Live page's own (_line_num reads 'wins by over 6.5')",
   E._line_num("Kansas City wins by over 6.5 points") == 6.5 and E._espn_line_num("o44.5") == 44.5)
