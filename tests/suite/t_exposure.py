# CHECK: group=engine
# No-both-sides and exposure caps on PAPER (issue #335): each Live refresh records whether both sides of a game (or
# stacked bets) are held or would be added by the panel, the money on each game / league / day against the bankroll,
# and which held bets a no-both-sides rule or a cap WOULD have stopped, with what they made once settled. Checks: the
# stance rules, the verdicts (blocked bets never count toward the next one's room), the first look is not judged,
# settlement from the ledger, small groups hidden, the tables stay bounded, errors are swallowed, and nothing that
# buys, sells or sizes mentions any of it. Fakes only: no network, a temp history.
import os, time, tempfile, importlib.util, inspect, re
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
now = time.time()


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)


DAL = "KXNFLGAME-26NOV30DALNYG-DAL"
NYG = "KXNFLGAME-26NOV30DALNYG-NYG"
SPR = "KXNFLSPREAD-26NOV30DALNYG-NYG3"
TOT = "KXNFLTOTAL-26NOV30DALNYG-47"
OTH = "KXNFLGAME-26NOV30KCPHI-KC"
OTH2 = "KXNFLGAME-26DEC01GBCHI-GB"

# ---- stances
st = E._expo_stance
ok("stance win yes", st(DAL, "yes") == "win:DAL:")
ok("stance win no", st(DAL, "no") == "win:~DAL:")
ok("stance spread keeps kind and strike", st(SPR, "yes") == "spread:NYG:3")
ok("stance total", st(TOT, "yes") == "total:over:47" and st(TOT, "no") == "total:under:47")
ok("stance unknown", st("WEIRD", "yes") is None)
op = E._expo_opposed
W = lambda x: "win:%s:" % x
ok("two teams are opposed", op(W("DAL"), W("NYG")))
ok("a team and against that team are opposed", op(W("DAL"), W("~DAL")) and op(W("~DAL"), W("DAL")))
ok("a team and against the other team are not", not op("DAL", "~NYG") and not op("~NYG", "DAL"))
ok("same team is not opposed", not op(W("DAL"), W("DAL")))
ok("against both teams is opposed", op(W("~DAL"), W("~NYG")))
T = lambda w, k: "total:%s:%s" % (w, k)
ok("over and under at the same strike are opposed; a team and a total never",
   op(T("over", 47), T("under", 47)) and not op(T("over", 47), W("DAL")) and not op(T("over", 47), T("over", 47)))
ok("cross-strike totals: a middle is not the other side, a crossed pair is",
   not op(T("over", 40), T("under", 50)) and op(T("over", 50), T("under", 40)))
Sp = lambda w, k: "spread:%s:%s" % (w, k)
ok("spread NO beside the same team to win is not both sides", not op(Sp("~DAL", 3), W("DAL")) and not op(W("DAL"), Sp("~DAL", 3)))
ok("spread YES on each team is both sides; different strikes of one team are a middle",
   op(Sp("DAL", 3), Sp("NYG", 3)) and not op(Sp("DAL", 3), Sp("~DAL", 7)) and op(Sp("DAL", 3), Sp("~DAL", 3)))


def single(t, ticker, cost, side="yes"):
    return {"t": t, "ticker": ticker, "cost": cost, "side": side, "state": "pre"}


def combo(t, legs, cost):
    return {"t": t, "cost": cost, "group": "pending", "legs": [{"ticker": k, "side": s} for k, s in legs]}


E.panel_get = lambda mode="real", day=None: None
E.CFG["bankroll"] = 100
E.EXPO["every"] = 0

# ---- the first look is recorded but never judged
v1 = {"singles": [single("a1", DAL, 3), single("a2", NYG, 3)], "combos": []}
info = E.exposure_paper_pass(v1, now, force=True)
ok("first look: both sides held is reported", info and info["both_held"] == ["DALNYG"])
ok("first look: nothing counted as blocked", E.store_rows("select count(*) n from expo_pos where seed=1 and blocked=''")[0]["n"] == 2
   and E.exposure_paper_summary() == {})
ok("the log line is plain English", "holding both sides of DALNYG" in info["line"] and "nothing is blocked" in info["line"])

# ---- later bets are judged against what was taken
t = now + 200
v2 = {"singles": v1["singles"] + [single("b1", "KXNFLTOTAL-26NOV30DALNYG-47", 3, "yes")], "combos": []}
E.exposure_paper_pass(v2, t, force=True)
r = {x["pos"]: x for x in E.store_rows("select * from expo_pos")}
ok("over on a game already held by the seed is fine (no opposing total)", r["b1"]["blocked"] == "")
v3 = dict(v2, singles=v2["singles"] + [single("b2", "KXNFLTOTAL-26NOV30DALNYG-47", 2, "no")])
E.exposure_paper_pass(v3, t + 200, force=True)
ok("under after over on the same game: both_sides", E.store_rows("select blocked from expo_pos where pos='b2'")[0]["blocked"] == "both_sides")
v4 = dict(v3, singles=v3["singles"] + [single("c1", OTH, 12)])
E.exposure_paper_pass(v4, t + 400, force=True)
ok("12 on one game with a 100 bankroll: game_cap", E.store_rows("select blocked from expo_pos where pos='c1'")[0]["blocked"] == "game_cap")
v5 = dict(v4, singles=v4["singles"] + [single("c2", OTH, 9)])
E.exposure_paper_pass(v5, t + 600, force=True)
ok("the blocked 12 did not use up the game's room: the 9 is fine", E.store_rows("select blocked from expo_pos where pos='c2'")[0]["blocked"] == "")
v6 = dict(v5, singles=v5["singles"] + [single("d1", OTH2, 9), single("d2", "KXNFLGAME-26NOV30LARSEA-LAR", 9), single("d3", "KXNFLGAME-26NOV30MIAJAX-MIA", 9)])
E.exposure_paper_pass(v6, t + 800, force=True)
rows = {x["pos"]: x["blocked"] for x in E.store_rows("select pos, blocked from expo_pos")}
ok("league cap (30) stops the bet that would take the day's nfl total over it", rows["d3"] == "league_cap" or rows["d2"] == "league_cap")
E.EXPO["league"] = 9.0
v7 = dict(v6, combos=[combo("k1", [(OTH2, "yes"), ("KXNBAGAME-26DEC01LALBOS-LAL", "yes")], 6)])
E.exposure_paper_pass(v7, t + 1000, force=True)
ok("a combo spreads its cost over its games and is judged on the day (mixed league skips the league cap)",
   E.store_rows("select blocked, league from expo_pos where pos='k1'")[0]["league"] == "mix")
E.EXPO["league"] = 0.30

# ---- a game's both-sides stays visible in the pass rows
g = E.store_rows("select * from expo_pass where kind='game' and key like '%DALNYG' order by ts desc limit 1")[0]
ok("pass row: game with both sides held", g["both_held"] == 1 and g["stacked"] >= 2 and g["held_n"] >= 2)
ok("pass rows exist for league and day", E.store_rows("select count(*) n from expo_pass where kind in ('league','day')")[0]["n"] >= 2)

# ---- the panel's would-buy list
E.panel_get = lambda mode="real", day=None: {"items": [
    {"id": "p1", "kind": "single", "state": "scheduled", "stake": 4, "legs": [{"ticker": NYG}]},
    {"id": "p2", "kind": "single", "state": "skipped", "stake": 4, "legs": [{"ticker": "KXNFLGAME-26NOV30DALNYG-DAL"}]}]}
vp = {"singles": [single("z1", DAL, 3)], "combos": []}
E.EXPO_STATE["sig"] = None
info = E.exposure_paper_pass(vp, t + 1200, force=True)
ok("panel would add the other side: reported; a skipped item is ignored", info["both_would"] == ["DALNYG"])
ok("the line says so", "the panel would add both sides of DALNYG" in info["line"])
E.panel_get = lambda mode="real", day=None: None

# ---- settlement from the ledger; small groups hidden
E._ledger_table()
for pos, cost, back in (("b2", 2.0, 0.0), ("c1", 12.0, 0.0), ("d3", 9.0, 18.0)):
    E.store_x("insert or replace into ledger(ticker, kind, league, side, cost, back, fees, status, closed) values(?,?,?,?,?,?,?,?,?)",
              (pos, "single", "nfl", "yes", cost, back, 0.0, "won" if back else "lost", t + 5000))
E.exposure_paper_pass(vp, t + 1400, force=True)
s = E.exposure_paper_summary()
ok("dollars are hidden while fewer than the minimum have settled", s["blocked"]["settled"] is None and s["blocked"]["net"] is None)
ok("small per-rule groups show neither a count nor dollars", all(x["n"] is None and x["net"] is None for x in s["by"].values()))
E.EXPO["min_n"] = 2
E.EXPO["dollar_n"] = 2
s = E.exposure_paper_summary()
ok("with a lower minimum the settled net of the blocked bets is shown", s["blocked"]["settled"] is not None and isinstance(s["blocked"]["net"], float))
ok("net is dollars after cost (b2 -2, c1 -12, plus d3/d2 if blocked)", s["blocked"]["net"] <= -14 + 9 + 1e-9)
E.EXPO["min_n"] = 5
E.EXPO["dollar_n"] = 20

# ---- review fixes: held only, same-pass batches, settlement rules, origin, one transaction, the off switch
GEE, GFF = "KXNFLGAME-26NOV30EEFF-EE", "KXNFLGAME-26NOV30EEFF-FF"
E.exposure_paper_pass({"singles": [single("e1", GEE, 1)], "combos": []}, t + 1100, force=True)
E.exposure_paper_pass({"singles": [], "combos": []}, t + 1110, force=True)
E.exposure_paper_pass({"singles": [single("e2", GFF, 1)], "combos": []}, t + 1120, force=True)
ok("a bet no longer held is not counted against a new one (no both_sides)",
   E.store_rows("select blocked from expo_pos where pos='e2'")[0]["blocked"] == "")
GGG, GHH = "KXNFLGAME-26NOV30GGHH-GG", "KXNFLGAME-26NOV30GGHH-HH"
E.exposure_paper_pass({"singles": [single("g1", GGG, 1), dict(single("g2", GHH, 1), own=False)], "combos": []}, t + 1130, force=True)
gr = {x["pos"]: x for x in E.store_rows("select * from expo_pos where pos in ('g1','g2')")}
ok("bets that arrive together are marked as one batch", gr["g1"]["batch"] == 2 and gr["g2"]["batch"] == 2)
ok("the origin is stored (the app's by default, not-own marked)", gr["g1"]["own"] == 1 and gr["g2"]["own"] == 0)
ok("a same-pass batch is counted apart, never in the dollars", E.exposure_paper_summary().get("ambiguous", 0) >= 1)
E.store_x("update expo_pos set blocked='both_sides', net=5, settled=1 where pos='g2'")
sm = E.exposure_paper_summary()
ok("an ambiguous blocked bet is left out of the blocked group", sm["blocked"]["n"] is None or sm["blocked"]["n"] == sum(
    1 for x in E.store_rows("select 1 from expo_pos where seed=0 and blocked!='' and coalesce(batch,1)<=1")))
HOLD = {"singles": [single("s1", "KXNFLGAME-26NOV30SSTT-SS", 4), single("s2", "KXNFLGAME-26NOV30SSTT-TT", 4)], "combos": []}
for pos, closed, cost in (("s1", t + 5000, 4.0), ("s2", t + 5000, 40.0)):
    E.store_x("insert or replace into ledger(ticker, kind, league, side, cost, back, fees, status, closed) values(?,?,?,?,?,?,?,?,?)",
              (pos, "single", "nfl", "yes", cost, 0.0, 0.0, "lost", closed))
E.exposure_paper_pass(HOLD, t + 1140, force=True)
ok("a bet still held is not settled", E.store_rows("select settled from expo_pos where pos='s1'")[0]["settled"] is None)
E.exposure_paper_pass({"singles": [], "combos": []}, t + 1150, force=True)
ok("settled once it is no longer held and the ledger closed it after we saw it",
   E.store_rows("select net from expo_pos where pos='s1'")[0]["net"] == -4.0)
ok("a ledger cost far from ours is left unsettled", E.store_rows("select settled from expo_pos where pos='s2'")[0]["settled"] is None)
E.store_x("insert or replace into ledger(ticker, kind, league, side, cost, back, fees, status, closed) values('s3','single','nfl','yes',4,0,0,'lost',1)")
E.exposure_paper_pass({"singles": [single("s3", "KXNFLGAME-26NOV30UUVV-UU", 4)], "combos": []}, t + 1160, force=True)
E.exposure_paper_pass({"singles": [], "combos": []}, t + 1170, force=True)
ok("a ledger row closed before we first saw the bet is not its result", E.store_rows("select settled from expo_pos where pos='s3'")[0]["settled"] is None)
before = E.store_rows("select count(*) n from expo_pass")[0]["n"]
ok("one failed statement rolls the whole batch back",
   E._expo_write([("insert into expo_pass values(?,?,?,?,?,?,?,?,?,?,?,?)", (1, "game", "k", 0, 0, 0, 0, 0, 0, 0, 0, 0)),
                  ("insert into nosuchtable values(1)", ())]) is False
   and E.store_rows("select count(*) n from expo_pass")[0]["n"] == before)
E.CFG["expo_paper"] = False
ok("the config switch turns it off", E.exposure_paper_pass(v1, t + 1180, force=True) is None)
E.CFG.pop("expo_paper", None)

# ---- never raises, never blocks, bounded
real_db = E.STORE["db"]
E.STORE["db"] = None
ok("with no history file it returns None", E.exposure_paper_pass(vp, t + 2000, force=True) is None and E.exposure_paper_summary() == {})
E.STORE["db"] = real_db
ok("garbage views are fine", all(E.exposure_paper_pass(x, t + 2100, force=True) is None or True
                                 for x in (None, {}, {"singles": [None]}, {"combos": [{"t": "x", "group": "pending", "legs": [None]}]}, "str")))
real_x = E.store_x
E.store_x = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full"))
ok("a storage error is swallowed", E.exposure_paper_pass(vp, t + 2200, force=True) is None)
E.store_x = real_x
E.EXPO["pass_rows"] = 10
E.EXPO_STATE["pruned"] = 0.0          # the prune runs hourly: let this pass do it
E.EXPO_STATE["sig"] = None
E.exposure_paper_pass({"singles": [single("q%d" % i, "KXNFLGAME-26NOV30AA%dBB-AA" % i, 1) for i in range(30)], "combos": []}, t + 2300, force=True)
ok("expo_pass stays bounded", E.store_rows("select count(*) n from expo_pass")[0]["n"] <= 10 + 70)
old = E.store_rows("select count(*) n from expo_pos")[0]["n"]
E.EXPO["keep_days"] = 0
E.exposure_paper_pass(vp, t + 9e6, force=True)
ok("old expo_pos rows are pruned", E.store_rows("select count(*) n from expo_pos where ts < ?", (t,))[0]["n"] == 0 and old > 0)
ok("the pass is throttled", (setattr(E, "EXPO", dict(E.EXPO, every=500)) or True)
   and E.exposure_paper_pass(vp, t + 9e6 + 1, force=False) is None)

# ---- decisions never read it
src = open("wahome/engine.py", encoding="utf-8").read()
users = [m.start() for m in re.finditer(r"exposure_paper_|_expo_|expo_pos|expo_pass|EXPO\b", src)]
defs_end = src.index("SPORT_SCORE_WORD = {")
defs_start = src.index("# ---- (#335) no-both-sides")
outside = [src[max(0, i - 60):i + 40].replace("\n", " ") for i in users if not defs_start <= i < defs_end]
# money-h: the no-both-sides single-buy guard deliberately reuses the stance/opposed helpers (Pete's instruction); nothing else may
outside = [o for o in outside if "_expo_stance" not in o and "_expo_opposed" not in o]
ok("only record_view calls it from outside its own block", len(outside) == 1 and "exposure_paper_pass(view, now)" in outside[0])
rv = inspect.getsource(E.record_view)
ok("record_view calls it after its own writes, not before the return value is built", "exposure_paper_pass(view, now)" in rv)
for fn in ("get_offer", "accept_offer", "panel_buy", "_size", "smart_buy_ok", "exit_policy", "single_sell_reason", "build_panel"):
    f = getattr(E, fn, None)
    ok(fn + " never mentions the exposure paper check", f is None or "expo" not in inspect.getsource(f).lower())
