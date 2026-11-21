# Live "Buy ideas" cards say which game they are for (GitHub #129). The idea's payload now carries the league, each
# leg's matchup ('Baylor at TCU', 'vs' only when home/away isn't known), the pick in plain words ('wins by 8 or more',
# 'Over 7.5 total goals'), the start time (or the live score), Kalshi's price vs the fair price, the edge, the chance to
# win and what the stake is expected to earn. All of it comes from data the idea already holds (no lookups); an unknown
# field is left out. Covers a spread, a total, a moneyline single (college and pro) and a combo, plus an older idea
# saved before these fields existed. Nothing about picking, pricing or buying is touched.
import os, time, tempfile, importlib.util, json
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
# An idea's id is the second it was saved plus a random 100-999, so ideas this test saves within one second could
# share an id (about 1 in 900 per pair) and the lookup by id below found the wrong idea: CI failed "each leg has its
# own matchup/league" once. Give the engine its own random whose randint counts up, so every id here is distinct.
import itertools, random as _random, types
_ids = itertools.count(100)
E.random = types.SimpleNamespace(**{k: getattr(_random, k) for k in dir(_random) if not k.startswith("_")})
E.random.randint = lambda a, b: a + (next(_ids) - 100) % (b - a + 1)
now = time.time()
import datetime as dt
iso = lambda secs: (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=secs)).isoformat()

BAY, TCU = "KXNCAAFGAME-26NOV21BAYTCU-BAY", "KXNCAAFGAME-26NOV21BAYTCU-TCU"
E.PICK_NAME[BAY], E.PICK_NAME[TCU] = "Baylor Bears", "TCU Horned Frogs"
E.KICKOFF["KXNCAAFGAME-26NOV21BAYTCU"] = iso(7200)
E.LEAGUE["code"] = "ncaaf"

# ---- a moneyline single, college football: away team first, full names, a start time
sid = E.store_suggestion({"legs": [{"ticker": BAY, "event": "KXNCAAFGAME-26NOV21BAYTCU", "pick": "Baylor Bears", "p": .30, "fair": .40}],
                          "fair": 25.0}, {"pays": 20.0, "stake": 6.3}, .40 / .315)
rows = {r["id"]: r for r in E.live_suggestions(limit=50)}
r = rows[sid]; li = r["legs_info"][0]
ok("single: league name and icon", r["league_name"] == "College football" and r["icon"] == "🎓")
ok("single: matchup is 'away at home' from the event code", li["game"] == "Baylor Bears at TCU Horned Frogs")
ok("single: plain pick", li["plain"] == "Baylor Bears to win")
ok("single: start time from the kickoff", li["kick"] and abs(li["kick"] - (now + 7200)) < 5 and not li["live"])
ok("single: chance, prices, edge and expected profit",
   abs(r["chance"] - .40) < .001 and r["price_c"] == 31.5 and r["fair_c"] == 40.0 and abs(r["edge"] - (.40 / .315 - 1)) < .001
   and abs(r["profit"] - round(6.3 * (.40 / .315 - 1), 2)) < .01)
home = E.store_suggestion({"legs": [{"ticker": TCU, "event": "KXNCAAFGAME-26NOV21BAYTCU", "pick": "TCU Horned Frogs", "p": .6, "fair": .7}], "fair": 9.0},
                          {"pays": 10.0, "stake": 6.3}, .7 / .63)
hr = next(x for x in E.live_suggestions(limit=50) if x["id"] == home)
ok("single: the home team's idea reads the same game the same way", hr["legs_info"][0]["game"] == "Baylor Bears at TCU Horned Frogs")

# ---- a pro single (last-word names) and a soccer one, where home/away isn't claimed
NJD = "KXNHLGAME-26NOV21NJDSTL-NJD"
nhl = E.store_suggestion({"legs": [{"ticker": NJD, "event": "KXNHLGAME-26NOV21NJDSTL", "pick": "New Jersey Devils", "p": .4, "fair": .5}], "fair": 12.0},
                         {"pays": 10.0, "stake": 4.2}, .5 / .42)
nr = next(x for x in E.live_suggestions(limit=50) if x["id"] == nhl)
ok("pro single: last-word names", nr["legs_info"][0]["game"] == "Devils at Blues" and nr["legs_info"][0]["plain"] == "Devils to win")
ARS = "KXEPLGAME-26NOV21ARSCHE-ARS"
E.PICK_NAME[ARS], E.PICK_NAME["KXEPLGAME-26NOV21ARSCHE-CHE"] = "Arsenal", "Chelsea"
soc = E.store_suggestion({"legs": [{"ticker": ARS, "event": "KXEPLGAME-26NOV21ARSCHE", "pick": "Arsenal", "p": .4, "fair": .5}], "fair": 12.0},
                         {"pays": 10.0, "stake": 4.2}, .5 / .42)
sr = next(x for x in E.live_suggestions(limit=50) if x["id"] == soc)
ok("soccer: 'vs' (home/away not assumed) and the league's own name", sr["legs_info"][0]["game"] == "Arsenal vs Chelsea" and sr["league_name"] == "Premier League")

# ---- a spread: 7.5+ reads 'wins by 8 or more'
spread = {"ticker": "KXNCAAFSPREAD-26NOV21BAYTCU-BAY8", "event": "KXNCAAFSPREAD-26NOV21BAYTCU", "pick": "Baylor Bears win by 7.5+",
          "p": .3, "fair": .38, "kind": "spread", "line": 7.5, "start": iso(7200), "game": "Baylor Bears at TCU Horned Frogs"}
sp = E.store_suggestion({"legs": [spread], "fair": 20.0}, {"pays": 10.0, "stake": 3.3}, .38 / .33)
spr = next(x for x in E.live_suggestions(limit=50) if x["id"] == sp)
ok("spread: wins by 8 or more", spr["legs_info"][0]["plain"] == "Baylor Bears wins by 8 or more")
ok("spread: names its game and start", spr["legs_info"][0]["game"] == "Baylor Bears at TCU Horned Frogs" and spr["legs_info"][0]["kick"])
ok("spread: a whole-number line reads 'more than'", E._idea_plain("ncaaf", {"pick": "Baylor Bears win by 7+"}, "spread") == "Baylor Bears wins by more than 7")
ok("spread: a negative line (lose by under) reads as covering", E._idea_plain("nfl", {"pick": "Colts lose by under 3"}, "spread") == "Colts wins, or loses by fewer than 3")

# ---- a total: over/under what, and the game from the text it was found with
total = {"ticker": "KXNHLTOTAL-26NOV21NJDSTL-7", "event": "KXNHLTOTAL-26NOV21NJDSTL", "pick": "Over 7.5 (Devils at Blues)",
         "p": .4, "fair": .48, "kind": "total", "line": 7.5, "start": iso(5400), "game": "Devils at Blues"}
tt = E.store_suggestion({"legs": [total], "fair": 20.0}, {"pays": 10.0, "stake": 4.2}, .48 / .42)
tr = next(x for x in E.live_suggestions(limit=50) if x["id"] == tt)
ok("total: over 7.5 total goals, with the game", tr["legs_info"][0]["plain"] == "Over 7.5 total goals" and tr["legs_info"][0]["game"] == "Devils at Blues")
ok("total (basketball): points; an Under says Under",
   E._idea_plain("nba", {"pick": "Over 220.5 (Suns at Lakers)"}, "total") == "Over 220.5 total points"
   and E._idea_plain("nfl", {"pick": "Under 44.5 (Colts at Texans)"}, "total") == "Under 44.5 total points")
ok("total: unknown sport leaves out the unit", E._idea_plain("tennis", {"pick": "Over 22.5 games"}, "total") == "Over 22.5 total")

# ---- a combo: every leg names its own game
LA, DEN = "KXNBAGAME-26NOV21LALDEN-LAL", "KXNBAGAME-26NOV21LALDEN-DEN"
E.KICKOFF["KXNBAGAME-26NOV21LALDEN"] = iso(3600)
cb = E.store_suggestion({"legs": [{"ticker": BAY, "event": "KXNCAAFGAME-26NOV21BAYTCU", "pick": "Baylor Bears", "p": .3, "fair": .4},
                                  {"ticker": DEN, "event": "KXNBAGAME-26NOV21LALDEN", "pick": "Denver Nuggets", "p": .5, "fair": .6}],
                         "fair": 30.0}, {"pays": 40.0, "stake": 5.0}, 1.2)
cr = next(x for x in E.live_suggestions(limit=50) if x["id"] == cb)
games = [l["game"] for l in cr["legs_info"]]
ok("combo: each leg has its own matchup", games == ["Baylor Bears at TCU Horned Frogs", "Lakers at Nuggets"])
ok("combo: each leg has its own league", [l["league_name"] for l in cr["legs_info"]] == ["College football", "NBA"])
ok("combo: a start per leg", all(l["kick"] for l in cr["legs_info"]))

# ---- an older idea (saved before these fields): worked out from the tickers; fields it can't tell are left out
OKL = "KXNCAAFGAME-26NOV21OKLTEX-OKL"
E.PICK_NAME[OKL], E.PICK_NAME["KXNCAAFGAME-26NOV21OKLTEX-TEX"] = "Oklahoma Sooners", "Texas Longhorns"
E.store_x("insert into suggestions(id, ts, lg, legs, picks, n, pct, pays, stake, fair, kick, live) values(?,?,?,?,?,?,?,?,?,?,?,?)",
          ("oldone", now, "ncaaf", json.dumps([OKL]), "Oklahoma Sooners", 1, 1.25, 10.0, 6.0, 20.0, now + 3600, 0))
old = next(x for x in E.live_suggestions(limit=50) if x["id"] == "oldone")
ok("older idea: matchup and plain pick still come out", old["legs_info"][0]["game"] == "Oklahoma Sooners at Texas Longhorns" and old["legs_info"][0]["plain"] == "Oklahoma Sooners to win")
ok("older idea: start time from the row", abs(old["legs_info"][0]["kick"] - (now + 3600)) < 1)
E.store_x("insert into suggestions(id, ts, lg, legs, picks, n, pct, pays, stake, fair, kick, live) values(?,?,?,?,?,?,?,?,?,?,?,?)",
          ("unk", now, "ncaaf", json.dumps(["KXNCAAFGAME-26NOV21ZZZYYY-ZZZ"]), "Mystery", 1, 1.1, 10.0, 6.0, 20.0, None, 0))
unk = next(x for x in E.live_suggestions(limit=50) if x["id"] == "unk")
ok("unknown game: matchup omitted, not guessed", unk["legs_info"][0]["game"] == "" and not unk["legs_info"][0]["kick"])
ok("no info column leaks into the payload", "info" not in unk)
bad = {"legs": "not json", "stake": 1}
ok("a broken row never raises", E.idea_describe(bad) == {})

# ---- a game under way shows its score and clock, from the scores already cached; never fetched
E.store_x("insert into suggestions(id, ts, lg, legs, picks, n, pct, pays, stake, fair, kick, live) values(?,?,?,?,?,?,?,?,?,?,?,?)",
          ("livey", now, "ncaaf", json.dumps(["KXNCAAFGAME-26NOV21LSUALA-LSU"]), "LSU Tigers", 1, 1.25, 10.0, 6.0, 20.0, None, 1))
E.display_score = lambda l, **k: {"me": 21, "opp": 14, "abbr": "BAY", "opp_abbr": "TCU", "detail": "Q3 4:12", "state": "in"}
lv = next(x for x in E.live_suggestions(limit=50) if x["id"] == "livey")
ok("live idea: score and clock instead of a start time", lv["legs_info"][0]["live"] and lv["legs_info"][0]["score"] == "BAY 21–14 TCU · Q3 4:12")
E.display_score = lambda l, **k: (_ for _ in ()).throw(RuntimeError("boom"))
lv = next(x for x in E.live_suggestions(limit=50) if x["id"] == "livey")
ok("live idea: a broken score feed leaves the score out, the card stays", lv["legs_info"][0]["live"] and lv["legs_info"][0]["score"] == "")

# ---- the game page for a game in an idea (nothing held there)
E.display_score = lambda l, **k: None
g = E.idea_game_leg(BAY)
ok("game page block for an idea's game", g and g["name"] == "Baylor Bears" and g["opp"] == "TCU Horned Frogs" and g["sport"] == "ncaaf" and g["state"] == "pre")
ok("game page block: only games named by a current idea", E.idea_game_leg("KXNBAGAME-NOPE-XXX") is None)
TL = "KXNHLTOTAL-26NOV21NJDSTL-7"
E.store_x("delete from suggestions where id != ?", (tt,))      # the page lists the best six ideas; keep only this one
tg = E.idea_game_leg(TL)
ok("game page block for a total: headed by the game, no side", tg and tg["name"] == "Devils at Blues" and tg["opp"] == "" and tg["label"] == "Over 7.5 total goals" and tg["kind"] == "total")
ok("a longer team name wins the side match (Michigan State vs Michigan)",
   (lambda: (E.PICK_NAME.update({"KXNCAAFGAME-26NOV21MICMSU-MSU": "Michigan State Spartans", "KXNCAAFGAME-26NOV21MICMSU-MIC": "Michigan Wolverines"}),
             E.store_suggestion({"legs": [{"ticker": "KXNCAAFGAME-26NOV21MICMSU-MSU", "event": "KXNCAAFGAME-26NOV21MICMSU", "pick": "Michigan State Spartans", "p": .4, "fair": .5}], "fair": 12.0}, {"pays": 10.0, "stake": 4.2}, 1.19),
             E.idea_game_leg("KXNCAAFGAME-26NOV21MICMSU-MSU"))[2])()["name"] == "Michigan State Spartans")
