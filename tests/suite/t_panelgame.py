# Every panel bet names its game in plain English (issue #61): a spread or total ("Over 7.5") used to show nothing about
# which game it was on. Singles, sell-early favorites, combos (each leg), spreads and totals carry a game label and a
# league tag, built from data the Mac already has (no lookups); notifications and the recap name the game too; and
# nothing about choosing or buying changes.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.injury_note = lambda code, *teams, hours=48: ([], False)   # no injury news: never ESPN's real report (netguard)
import datetime as _dt; _u = _dt.datetime.now(_dt.timezone.utc); E.PACIFIC = _dt.timezone(_dt.timedelta(hours=round(12 - _u.hour - _u.minute / 60)))
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.BUY_FLAG = os.path.join(E.HERE, "panel_buy.flag")
E.fetch_account = lambda **k: ([], 300.0, None)
E.account_events = lambda *a, **k: set()
E.kalshi_send = lambda *a, **k: {}
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()

# ---- the matchup text: pro teams by last word, college and others by full name; the pick comes first
games = {"E1": [{"ticker": "E1-PHI", "event": "E1", "pick": "Philadelphia Flyers", "p": .4, "fair": .5},
                {"ticker": "E1-BOS", "event": "E1", "pick": "Boston Bruins", "p": .6, "fair": .5}]}
E.stamp_games("nhl", games)
a, b = games["E1"]
ok("pro game: 'Flyers vs Bruins', pick first, opponent kept", a["game"] == "Flyers vs Bruins" and a["vs"] == "Bruins" and b["game"] == "Bruins vs Flyers")
cg = {"E2": [{"ticker": "E2-TEM", "event": "E2", "pick": "Temple Owls", "p": .4, "fair": .5},
             {"ticker": "E2-TUL", "event": "E2", "pick": "Tulane Green Wave", "p": .6, "fair": .5}]}
E.stamp_games("ncaaf", cg)
ok("college game keeps full names ('Owls' alone would be ambiguous)", cg["E2"][0]["game"] == "Temple Owls vs Tulane Green Wave")
sg = {"E3": [{"ticker": "E3-ARS", "event": "E3", "pick": "Arsenal", "p": .4, "fair": .5},
             {"ticker": "E3-TIE", "event": "E3", "pick": "Draw", "p": .3, "fair": .3, "tie": True},
             {"ticker": "E3-CHE", "event": "E3", "pick": "Chelsea", "p": .3, "fair": .2}]}
E.stamp_games("soccer", sg)
ok("soccer: the draw is not a team", sg["E3"][0]["game"] == "Arsenal vs Chelsea" and "game" not in sg["E3"][1])
ok("league tags are plain", E.league_tag("nhl") == "NHL" and E.league_tag("ncaaf") == "CFB" and E.league_tag("soccer") == "Soccer")
ok("two-word nicknames stay whole ('Maple Leafs', 'Wolf Pack', 'Utah Hockey Club')",
   E.team_short("nhl", "Toronto Maple Leafs") == "Maple Leafs" and E.team_short("ahl", "Hartford Wolf Pack") == "Wolf Pack"
   and E.team_short("nhl", "Utah Hockey Club") == "Hockey Club" and E.team_short("nba", "Portland Trail Blazers") == "Trail Blazers")
ok("a soccer bet names its league, not just 'Soccer'", E.league_tag("soccer", "KXEPLGAME-26NOV19ARSCHE-ARS") == "Premier League"
   and E.league_tag("soccer", "KXLIGAMXGAME-26NOV19AAABBB-AAA") == "Liga MX" and E.league_tag("nhl", "KXNHLGAME-X-Y") == "NHL")
ok("pro teams are short, others full", E.team_short("nhl", "Philadelphia Flyers") == "Flyers" and E.team_short("ncaamb", "Temple Owls") == "Temple Owls")

# ---- candidates: every kind names its game, and the league
single = E._cand("single", "nhl", [a], .6, .1, "w", price=.4, opp="Boston Bruins")
early = E._cand("early", "nhl", [a], .8, .1, "w", price=.4, exit=.6, opp="Boston Bruins")
combo = E._cand("combo", "nhl", [a, dict(cg["E2"][0], ticker="X-9")], .3, .1, "w", pct=1.0, fair_mult=3.0)
ok("a single names its game and league", single["game"] == "Flyers vs Bruins" and single["league"] == "NHL")
ok("a sell-early favorite names its game and league", early["game"] == "Flyers vs Bruins" and early["league"] == "NHL")
ok("a soccer single is tagged with its league", E._cand("single", "soccer", [{"ticker": "KXEPLGAME-26NOV19ARSCHE-ARS", "event": "KXEPLGAME-26NOV19ARSCHE", "pick": "Arsenal", "p": .4, "fair": .5, "game": "Arsenal vs Chelsea", "vs": "Chelsea", "me": "Arsenal"}],
   .5, .1, "w", price=.4)["league"] == "Premier League")
ok("each leg of a combo names its game", [l["game"] for l in combo["legs"]] == ["Flyers vs Bruins", "Temple Owls vs Tulane Green Wave"])
ok("nothing about ids, prices or kickoffs changed", single["id"] == "single:E1-PHI" and single["price"] == .4 and combo["id"].startswith("combo:"))

# ---- spreads and totals, straight from line_candidates (ESPN's line + Kalshi's market)
E.espn_lines = lambda code: {
    frozenset({"temple owls", "tulane green wave"}): {"home": "Tulane Green Wave", "away": "Temple Owls", "home_abbr": "TUL", "away_abbr": "TEM",
                                                      "spread_home": -7.5, "total": 140, "start": None}}


def m(tk, sub, strike, p, kind):
    return {"ticker": tk, "event_ticker": "KXNCAAMBSPREAD-26NOV19TEMTUL", "yes_sub_title": sub, "floor_strike": strike, "yes_ask_dollars": str(p + .01),
            "yes_bid_dollars": str(p - .01), "last_price_dollars": str(p), "kind": kind}


E.line_markets = lambda code: [m("KXNCAAMBSPREAD-26NOV19TEMTUL-TUL7", "Tulane Green Wave wins by over 7.5 Points", 7.5, .45, "spread"),
                               m("KXNCAAMBTOTAL-26NOV19TEMTUL-140", "Over 140.5 Points scored", 140.5, .45, "total")]
E.price = lambda mm: float(mm["last_price_dollars"])
lc = {x["kind"]: x for x in E.line_candidates("ncaamb", everything=True)}
ok("spread and total markets were found", set(lc) == {"spread", "total"})
G = "Temple Owls at Tulane Green Wave"
ok("a spread names the game (full college names)", lc["spread"]["game"] == G)
sp = E._cand("line", "ncaamb", [dict(lc["spread"], start=None)], lc["spread"]["fair"], .2, "w", price=lc["spread"]["p"], game=lc["spread"]["game"])
tt = E._cand("line", "ncaamb", [dict(lc["total"], start=None)], lc["total"]["fair"], .2, "w", price=lc["total"]["p"], game=lc["total"]["game"])
ok("a spread bet carries its game and league", sp["game"] == G and sp["league"] == "CBB" and sp["legs"][0]["game"] == G)
ok("a total bet carries its game and league", tt["game"] == G and tt["league"] == "CBB")
ok("a line without a game still gets an empty one, never an error",
   E._cand("line", "nhl", [{"ticker": "Z", "event": "Z", "pick": "Over 5.5"}], .5, .1, "w", price=.4)["game"] == "")

# ---- notifications and the recap say which game
ok("single, in words", E.bet_text(single) == "Flyers to beat Bruins")
ok("spread, in words", E.bet_text(sp) == f"{lc['spread']['pick']} ({G})")
ok("total, in words", E.bet_text(tt).startswith("Over 140.5") and E.bet_text(tt).endswith(f"({G})") and E.bet_text(tt).count("(") == 1)
ok("combo, every leg named", E.bet_text(combo).count(" + ") == 1 and "to beat Bruins" in E.bet_text(combo))
ok("an older saved bet with no game text still reads fine",
   E.bet_text({"kind": "line", "legs": [{"pick": "Over 5.5 (A at B)"}]}) == "Over 5.5 (A at B)" and E.bet_text({"kind": "single", "legs": [{"pick": "Flyers"}]}) == "Flyers")

# ---- end to end: a drafted panel keeps the game text through save and load, and the buy notification names it
E.KICKOFF["E1"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 9 * 3600))
E.book_depth = lambda t, max_age=60: {"ask": 0.40, "bid": 0.39}
E.buy_single = lambda t, n, px: (n, None)
single = dict(single, stake=3.0, kick=now + 9 * 3600, last=now + 9 * 3600)
p = {"at": now, "items": [single], "longer": [], "stats": {}, "budget": 40, "base": 100, "codes": ["nhl"], "games": {}}
E.panel_save_draft(p, "real")
back = E.panel_get("real")
ok("the saved draft still has the game and league", back["items"][0]["game"] == "Flyers vs Bruins" and back["items"][0]["league"] == "NHL"
   and back["items"][0]["legs"][0]["game"] == "Flyers vs Bruins")
E.PANEL_POOL.clear(); E.PANEL_POOL["nhl"] = (time.time(), [single])
okA, msg = E.panel_approve(None, "all", at=back["at"])
out = E.panel_exec()
ok("the 'bought' notification names the game", okA and any("Panel bought" in x and "Flyers to beat Bruins" in x and "Philadelphia" not in x for x in out))

# ---- panel_collect itself stamps the games (singles, sell-early favorites, combo legs), with the real chooser
E.load_book_state = lambda snap: {}
E.fetch_markets = lambda: []
tag = time.strftime("%y%b%d", time.gmtime(now)).upper()
EV = [f"KXNHLGAME-{tag}PHIBOS", f"KXNHLGAME-{tag}COLSJ", f"KXNHLGAME-{tag}VGKLAK"]
names = [("Philadelphia Flyers", "Boston Bruins"), ("Colorado Avalanche", "San Jose Sharks"), ("Vegas Golden Knights", "Los Angeles Kings")]
live_games = {}
for ev, (n1, n2) in zip(EV, names):
    E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 5 * 3600))
    live_games[ev] = [{"event": ev, "ticker": ev + "-A", "abbr": "A", "pick": n1, "p": .40, "tie": False, "bid": .39, "exp": "", "fair": .52, "src": "Pinnacle"},
                      {"event": ev, "ticker": ev + "-B", "abbr": "B", "pick": n2, "p": .62, "tie": False, "bid": .61, "exp": "", "fair": .48, "src": "Pinnacle"}]
E.week_games = lambda mk, **k: ({e: [dict(x) for x in s] for e, s in live_games.items()}, {}, None)
E.attach_fair = lambda g, b: None
E.record_closes = lambda g, c: None
E.live_panel_on = lambda: False
E.calib_fair = lambda code, fair, ticker=None: fair
E.line_candidates = lambda code, everything=False: []
E.sell_early_candidates = lambda g: [dict(g[EV[1]][1], touch=.9, ev=.1, exit=.7)]
E.value_combos = lambda g, k=6, live_ok=(), max_legs=None: [{"legs": [g[EV[0]][0], g[EV[2]][0]], "value_pct": 1.2}]
E.predict_quote = lambda c: None
E.combo_cutoff = lambda *a, **k: 0.9
E.RESTING_SELLS_OK = True        # sell-early bets wait for Pete's call on resting exits (issue #81)
cands = E.panel_collect({}, "nhl", log=lambda *a: None)
kinds = {c["kind"]: c for c in cands}
E.RESTING_SELLS_OK = False
ok("while standing sells are off (V2), panel_collect drafts no sell-early bet",
   "early" not in {c["kind"] for c in E.panel_collect({}, "nhl", log=lambda *a: None)})
ok("panel_collect made singles, sell-early and combo candidates", {"single", "early", "combo"} <= set(kinds))
ok("every collected single/early names its game and league", all(c["game"] and c["league"] == "NHL" for c in cands if c["kind"] in ("single", "early")))
ok("...the sell-early favorite reads from its own side", kinds["early"]["game"] == "Sharks vs Avalanche")
ok("every leg of every collected combo names its game", all(l.get("game") for c in cands if c["kind"] == "combo" for l in c["legs"]))
ok("...as 'pick vs opponent'", [l["game"] for l in kinds["combo"]["legs"]] == ["Flyers vs Bruins", "Golden Knights vs Kings"])
