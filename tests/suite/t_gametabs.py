"""Slice 3 of the live game page (issue #72): box score, team stats, injury report, last 5 games and season leaders.
Display only, football first. The network is faked from fixtures/espn_game_tabs.json (trimmed copies of real public ESPN
responses: the site summary, each team's schedule, the core feed's season leaders and two athletes). Covers each parser
with real shapes and odd/missing fields, the background team fetches (cache, backoff, Retry-After, first-open wait),
the GAME_DETAIL eviction race fix, and isolation from every money path."""
import os, json, copy, time, inspect, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))
FX = json.load(open("fixtures/espn_game_tabs.json"))
EV = "401873066"


class Resp:
    def __init__(self, body, code=200, headers=None):
        self.body, self.status_code, self.ok, self.headers = body, code, code < 400, headers or {}

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class Net:
    """requests stand-in: the summary, team schedules, core season leaders and athletes from the fixture."""
    RequestException = E._requests.RequestException

    def __init__(self):
        self.calls, self.heads, self.mode, self.athletes, self.delay = [], [], "ok", dict(FX["athletes"]), 0

    def get(self, url, params=None, headers=None, **kw):
        self.calls.append(url)
        if self.delay and "/summary" not in url:
            time.sleep(self.delay)
        if "/summary" not in url:
            self.heads.append(headers)
        if self.mode == "down":
            raise self.RequestException("down")
        if self.mode == "429":
            return Resp({}, 429, {"Retry-After": "600"})
        if self.mode == "500":
            return Resp({}, 503)
        if self.mode == "garbage":
            return Resp(["not", "a", "dict"])
        if "/summary" in url:
            return Resp(copy.deepcopy(FX["summary"]))
        if "/schedule" in url:
            tid = url.split("/teams/")[1].split("/")[0]
            return Resp(copy.deepcopy(FX["schedule"][tid])) if tid in FX["schedule"] else Resp({}, 404)
        if "/leaders" in url:
            tid = url.split("/teams/")[1].split("/")[0]
            return Resp(copy.deepcopy(FX["leaders"][tid])) if tid in FX["leaders"] else Resp({}, 404)
        if "/athletes/" in url:
            aid = url.rstrip("/").split("/athletes/")[1].split("?")[0]
            return Resp(copy.deepcopy(self.athletes[aid])) if aid in self.athletes else Resp({"error": "not found"}, 404)
        return Resp({}, 404)


def fresh():
    E.GX.clear(); E.ATH.clear(); E.GAME_DETAIL.clear()
    for t in list(E.GX_JOB["t"].values()):
        t.join(5)
    E.GX_JOB["t"].clear()


net = Net(); E.requests = net
E.set_league("nfl")
S = FX["summary"]

# ---- the summary's own pieces (no extra fetch): box score, team stats, injuries, and the season for the team fetches
d = E._parse_game_detail(copy.deepcopy(S), EV)
b = d.get("board") or {}
ok("the board knows the season and its type for the team fetches", b.get("season") == 2026 and b.get("stype") == 2, (b.get("season"), b.get("stype")))
box = d.get("box") or {}
ok("box score has both sides", set(box) == {"away", "home"}, list(box))
ind = {g["k"]: g for g in box.get("away", [])}
ok("IND (away) has passing, rushing, receiving tables in that order",
   [g["k"] for g in box.get("away", [])][:3] == ["passing", "rushing", "receiving"], [g["k"] for g in box.get("away", [])])
ok("passing keeps the asked columns in order (C/ATT, YDS, TD, INT, SACKS)", ind["passing"]["c"] == ["C/ATT", "YDS", "TD", "INT", "SACKS"], ind["passing"]["c"])
r0 = ind["passing"]["r"][0]
ok("the passer's row: name, jersey, and his numbers under the right columns",
   r0["n"] == "Daniel Jones" and r0["j"] == "17" and r0["s"] == ["12/27", "144", "0", "1", "2-15"], r0)
ok("rushing columns CAR YDS AVG TD LONG and receiving REC YDS AVG TD LONG",
   ind["rushing"]["c"] == ["CAR", "YDS", "AVG", "TD", "LONG"] and ind["receiving"]["c"] == ["REC", "YDS", "AVG", "TD", "LONG"])
ok("team totals ride along under each table", len(ind["passing"]["tot"]) == 5 and ind["passing"]["tot"][1] == "129", ind["passing"]["tot"])
ok("HOU's passer is C.J. Stroud", (box.get("home") or [{}])[0].get("r", [{}])[0].get("n") == "C.J. Stroud")
ts = d.get("tstats") or []
by = {r["k"]: r for r in ts}
ok("team stats come in our order, starting with total yards", ts and ts[0]["k"] == "totalYards" and ts[0]["l"] == "Total yards", ts[:1])
ok("total yards 167 vs 354, with numbers for the bar", by["totalYards"]["a"] == "167" and by["totalYards"]["h"] == "354"
   and by["totalYards"]["an"] == 167 and by["totalYards"]["hn"] == 354, by.get("totalYards"))
ok("3rd down (made-att) compares success rates: 1-11 vs 8-14", abs(by["thirdDownEff"]["an"] - 1 / 11) < 1e-3 and abs(by["thirdDownEff"]["hn"] - 8 / 14) < 1e-3, by.get("thirdDownEff"))
ok("possession time compares seconds (22:14 vs 37:46)", by["possessionTime"]["an"] == 1334 and by["possessionTime"]["hn"] == 2266, by.get("possessionTime"))
ok("sacked / penalties use the first number (2-15 -> 2)", by["sacksYardsLost"]["an"] == 2 and by["totalPenaltiesYards"]["an"] == 2)
ok("all thirteen football rows are there", [r["k"] for r in ts] == [k for k, _ in E.TEAM_STATS], [r["k"] for r in ts])
lo_rows = sorted(r["k"] for r in ts if r["lo"])
ok("fewer-is-better rows: sacked, turnovers and penalties (and nothing else, time of possession is higher-is-better)",
   lo_rows == ["sacksYardsLost", "totalPenaltiesYards", "turnovers"], lo_rows)
ok("yards and possession: the bigger number leads (HOU 354 yards, 37:46)", by["totalYards"]["ld"] == "h" and by["possessionTime"]["ld"] == "h" and by["firstDowns"]["ld"] in ("a", "h", ""))
ok("sacked 2 (IND) vs 1 (HOU): fewer leads, HOU", by["sacksYardsLost"]["ld"] == "h", by["sacksYardsLost"])
ok("penalties 2 (IND) vs 4 (HOU): fewer leads, IND", by["totalPenaltiesYards"]["ld"] == "a", by["totalPenaltiesYards"])
ok("turnovers 1 vs 1 is a tie: nobody leads", by["turnovers"]["ld"] == "", by["turnovers"])
inj = d.get("inj") or {}
ok("injuries for both sides", len(inj.get("away", [])) == 5 and len(inj.get("home", [])) == 5, {k: len(v) for k, v in inj.items()})
ok("worst first: Out before Doubtful before Questionable",
   [x["st"] for x in inj["home"]] == ["Out", "Doubtful", "Questionable", "Questionable", "Questionable"], [x["st"] for x in inj["home"]])
w = inj["home"][0]
ok("an injury row: name, position, status, what, expected return", w["n"] == "Wyatt Teller" and w["ty"] == "Back" and w["ret"] == "2026-11-29" and w["pos"], w)
ok("summary athletes are remembered (name + jersey) for the leaders", (E.ATH.get("3917792") or (0, {}))[1].get("j") == "17")

# ---- odd or missing fields: each piece drops alone, nothing raises
odd = copy.deepcopy(S)
odd["boxscore"]["players"][0]["statistics"][0]["labels"] = None
odd["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"] = "x"
odd["boxscore"]["players"][1]["team"]["id"] = "999"
odd["boxscore"]["teams"][1]["statistics"] = [{"name": "turnovers", "displayValue": None}]
odd["injuries"] = [{"team": {"id": "34"}, "injuries": [{"status": "Active", "athlete": {"displayName": "X"}},
                                                         {"status": "Out", "athlete": {}}, "junk",
                                                         {"status": "out", "athlete": {"displayName": "Y", "jersey": "<b>"}, "details": {"returnDate": "soon"}}]}]
try:
    od = E._parse_game_detail(odd, EV)
    raised = False
except Exception as err:
    od, raised = {"X": repr(err)}, True
ok("odd box/team/injury fields never raise", not raised, od.get("X"))
ok("a side whose team id is unknown is left out of the box score", "home" not in (od.get("box") or {}), list(od.get("box") or {}))
pg = [g for g in (od.get("box") or {}).get("away", []) if g["k"] == "passing"]
ok("no labels: the table still lists its players (no columns), and a row with odd stats has blanks", pg and pg[0]["c"] == [] and pg[0]["r"][0]["s"] == [], pg[:1])
ok("team stats need both sides with real rows: none here", "tstats" not in od, od.get("tstats"))
oi = (od.get("inj") or {}).get("home", [])
ok("injuries: active and nameless players skipped, status capitalised, odd jersey and date dropped",
   len(oi) == 1 and oi[0]["n"] == "Y" and oi[0]["st"] == "Out" and oi[0]["j"] == "" and oi[0]["ret"] == "", oi)
for junk in (None, {}, {"boxscore": "x"}, {"boxscore": {"players": "x", "teams": [None, 3]}}, {"injuries": "x"},
             {"boxscore": {"players": [{"team": {"id": "34"}, "statistics": [{"name": "passing", "athletes": [None, {"athlete": "x"}]}]}]}}):
    try:
        for fn in (E._parse_box, E._parse_team_stats, E._parse_injuries):
            fn(junk if isinstance(junk, dict) else {}, {"34": "home", "11": "away"})
        E._note_athletes(junk)
        raised = False
    except Exception as err:
        raised = repr(err)
    ok("the slice-3 parsers never raise on " + repr(junk)[:50], raised is False, raised)
SIDES = {"34": "home", "11": "away"}
ok("no injuries block, or one with no team lists -> nothing known (the tab says not available, never 'no injuries')",
   E._parse_injuries({}, SIDES) == {} and E._parse_injuries({"injuries": []}, SIDES) == {} and E._parse_injuries({"injuries": "x"}, SIDES) == {}
   and E._parse_injuries({"injuries": [{"team": {"id": "34"}}, {"team": {"id": "11"}, "injuries": None}]}, SIDES) == {})
ok("both teams sent an empty list -> a real empty report for both sides",
   E._parse_injuries({"injuries": [{"team": {"id": "34"}, "injuries": []}, {"team": {"id": "11"}, "injuries": []}]}, SIDES) == {"away": [], "home": []})
one = E._parse_injuries({"injuries": [{"team": {"id": "34"}, "injuries": [{"status": "Out", "athlete": {"displayName": "Z"}}]}]}, SIDES)
ok("a team the feed did not mention is left out (unknown), not shown as healthy", list(one) == ["home"] and len(one["home"]) == 1, one)
ok("the same team listed twice: the first list wins",
   E._parse_injuries({"injuries": [{"team": {"id": "34"}, "injuries": []}, {"team": {"id": "34"}, "injuries": [{"status": "Out", "athlete": {"displayName": "Z"}}]}]}, SIDES) == {"home": []})
ok("the parsed game detail only carries 'inj' when some side is known",
   "inj" not in E._parse_game_detail({**copy.deepcopy(S), "injuries": []}, EV) and "inj" not in E._parse_game_detail({k: v for k, v in copy.deepcopy(S).items() if k != "injuries"}, EV)
   and (E._parse_game_detail({**copy.deepcopy(S), "injuries": [{"team": {"id": "34"}, "injuries": []}, {"team": {"id": "11"}, "injuries": []}]}, EV).get("inj") == {"away": [], "home": []}))

# ---- the number parser for the share bars
cases = [("31:24", "possessionTime", 1884), ("5-11", "thirdDownEff", round(5 / 11, 4)), ("0-0", "thirdDownEff", 0.0),
         ("2-15", "sacksYardsLost", 2), ("12/29", "completionAttempts", round(12 / 29, 4)), ("5.2", "yardsPerPlay", 5.2),
         ("1,234", "totalYards", 1234), ("-3", "rushingYards", None), ("--", "x", None), (None, "x", None), ("1e999", "x", None),
         ("nan", "x", None), (True, "x", None)]
bad = [(v, n, E._ts_num(v, n), want) for v, n, want in cases if E._ts_num(v, n) != want]
ok("_ts_num: mm:ss, made-att rates, first numbers, plain numbers; junk and negatives are None", not bad, bad)
both0 = E._parse_team_stats({"boxscore": {"teams": [
    {"homeAway": "away", "statistics": [{"name": n, "displayValue": "0"} for n, _ in E.TEAM_STATS]},
    {"homeAway": "home", "statistics": [{"name": n, "displayValue": "0"} for n, _ in E.TEAM_STATS]}]}}, {})
ok("both teams at zero: no bar numbers (the page draws an even, quiet bar)", both0 and all(r["an"] is None and r["hn"] is None for r in both0))
pre = E._parse_team_stats({"boxscore": {"teams": [
    {"homeAway": "away", "statistics": [{"name": "totalPointsPerGame", "label": "Points Per Game", "displayValue": "16.4"}]},
    {"homeAway": "home", "statistics": [{"name": "totalPointsPerGame", "label": "Points Per Game", "displayValue": "31.9"}]}]}}, {})
ok("another shape (season averages): the feed's own rows and labels are used", pre == [{"k": "totalPointsPerGame", "l": "Points Per Game", "a": "16.4", "h": "31.9", "an": 16.4, "hn": 31.9, "lo": False, "ld": "h"}], pre)
ok("_lead_line drops the yards (the big number): passing, rushing, receiving",
   E._lead_line("222/347, 2656 YDS, 22 TD, 4 INT") == "222/347, 22 TD, 4 INT" and E._lead_line("107 CAR, 391 YDS, 2 TD") == "107 CAR, 2 TD"
   and E._lead_line("33 REC, 1,354 YDS, 1 TD") == "33 REC, 1 TD" and E._lead_line(None) == "")

# ---- the background team fetches through game_detail (first open waits for them; later polls never do)
fresh()
net.calls.clear()
g = E.game_detail(EV, "nfl", max_age=0, budget=5)   # summary + waits (as a caller may choose to) for schedule/leaders/names
l5 = g.get("last5") or {}
ok("last 5 games for both teams after the first open", set(l5) == {"away", "home"}, list(l5))
ia = l5.get("away") or {}
ok("IND's record from its schedule (3-8) and five games, newest first",
   ia.get("rec") == "3-8" and len(ia.get("g", [])) == 5 and ia["g"][0]["d"] >= ia["g"][-1]["d"], ia)
ok("this game itself is never in its own last 5", all(x["id"] != EV for x in ia.get("g", []) + l5["home"].get("g", [])))
hg = l5["home"]["g"][0]
ok("a last-5 game keeps its full UTC kickoff (the page shows the local date, so a night game is not a day late)",
   hg["d"].startswith("2026-11-15T") and hg["d"].endswith("Z"), hg["d"])
ok("schedules ask for this season's regular season explicitly", any("/teams/11/schedule?season=2026&seasontype=2" in u for u in net.calls), net.calls)
ok("team fetches carry an explicit header, so they go straight to ESPN (never the hub's warm cache)",
   net.heads and all(h and h.get("Accept") for h in net.heads), net.heads[:3])
ok("a last-5 row: W/L, home/away, opponent, both scores, date (HOU lost at CLE 24-27 on Nov 15)",
   hg == {"id": hg["id"], "d": hg["d"], "w": "L", "at": "@", "opp": "CLE", "me": 24, "them": 27}, hg)
ld = {r["k"]: r for r in g.get("leaders") or []}
ok("season leaders: passing, rushing, receiving", list(ld) == ["pass", "rush", "rec"], list(ld))
p = ld["pass"]
ok("passing yards: Daniel Jones #17 (from the summary) vs C.J. Stroud #7, with stat lines without the yards",
   p["away"]["n"] and p["away"]["j"] == "17" and p["away"]["v"] == 1974 and p["away"]["line"] == "205/351, 7 TD, 13 INT"
   and p["home"]["j"] == "7" and p["home"]["v"] == 2656, p)
ok("a leader the summary did not carry is looked up once (W. Marks #4, J. Downs #2)",
   ld["rush"]["home"]["n"] == "W. Marks" and ld["rush"]["home"]["j"] == "4" and ld["rec"]["away"]["n"] == "J. Downs", (ld["rush"]["home"], ld["rec"]["away"]))
n_calls = len(net.calls)
kinds = [sum(k in u for u in net.calls) for k in ("/summary", "/schedule", "/leaders", "/athletes/")]
ok("fetched: the summary, 2 schedules, 2 leader lists, 2 names", n_calls == 7 and kinds == [1, 2, 2, 2], (n_calls, kinds))
g2 = E.game_detail(EV, "nfl", max_age=0)
ok("the next poll refetches only the summary (team data cached for 30-60 min)", len(net.calls) == n_calls + 1 and g2.get("last5") == g.get("last5"), net.calls[n_calls:])
for k in list(E.GX):
    if k[0] == "sched":
        E.GX[k] = (E.GX[k][0] - E.GX_TTL["sched"] - 1,) + E.GX[k][1:]
t0 = time.time()
g3 = E.game_detail(EV, "nfl", max_age=0)
ok("a later poll with stale team data never waits for the refresh (it runs in the background)", time.time() - t0 < 1.0 and bool(g3.get("last5")))
for t in list(E.GX_JOB["t"].values()):
    t.join(5)
ok("the background refresh fetched the two schedules again", sum("/schedule" in u for u in net.calls[n_calls:]) == 2, net.calls[n_calls:])

# ---- a 404 name lookup: the leader shows without a name, not looked up again every poll
fresh(); net.calls.clear(); net.athletes.pop("4688813")
E.game_extras(E._parse_game_detail(copy.deepcopy(S), EV), "football/nfl", EV, budget=5)
g = E.game_extras(E._parse_game_detail(copy.deepcopy(S), EV), "football/nfl", EV, budget=5)
rec = {r["k"]: r for r in g.get("leaders") or []}["rec"]["away"]
ok("a name the core feed cannot find: the stat still shows, the name is blank", rec["n"] == "" and rec["v"] == 354, rec)
ok("...and that name is not asked for again on the next poll", sum("/athletes/4688813" in u for u in net.calls) == 1)
net.athletes = dict(FX["athletes"])

# ---- failures: back off politely, never raise, the tab says not available
fresh(); net.calls.clear(); net.mode = "down"
base = E._parse_game_detail(copy.deepcopy(S), EV)
try:
    g = E.game_extras(base, "football/nfl", EV, budget=5)
    raised = False
except Exception as err:
    g, raised = {}, repr(err)
ok("ESPN down: no raise, the page keeps its summary tabs", not raised and "box" in g, raised)
ok("ESPN down: last 5 says not available on both sides, no leaders tab",
   (g.get("last5") or {}).get("away", {}).get("na") is True and "leaders" not in g, (g.get("last5"), g.get("leaders")))
n = len(net.calls)
E.game_extras(base, "football/nfl", EV, budget=5)
ok("after a failure it backs off (no refetch on the next poll)", len(net.calls) == n, net.calls[n:])
k = ("sched", "football/nfl", "11", 2026, 2)
ok("the backoff starts at 30 s and doubles", 25 < E.GX[k][3] - time.time() <= 31 and E.GX[k][2] == 1, E.GX.get(k))
E.GX[k] = E.GX[k][:3] + (0,)
E._gx_get(k, "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/11/schedule", E._shape_sched)
ok("a second failure waits 60 s", 55 < E.GX[k][3] - time.time() <= 61 and E.GX[k][2] == 2, E.GX.get(k))
net.mode = "429"
E.GX[k] = E.GX[k][:3] + (0,)
E._gx_get(k, "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/11/schedule", E._shape_sched)
ok("a 429 honours Retry-After (600 s)", 595 < E.GX[k][3] - time.time() <= 601, E.GX.get(k))
net.mode = "500"
E.GX[k] = E.GX[k][:3] + (0,)
E._gx_get(k, "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/11/schedule", E._shape_sched)
ok("a 5xx backs off too and keeps the last copy", E.GX[k][2] == 4 and E.GX[k][3] > time.time())
net.mode = "ok"
E.GX[k] = E.GX[k][:3] + (0,)
E._gx_get(k, "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/11/schedule", E._shape_sched)
ok("a good answer clears the backoff", E.GX[k][2] == 0 and E.GX[k][3] == 0 and E.GX[k][1]["rec"] == "3-8")
fresh(); net.mode = "garbage"
try:
    g = E.game_extras(E._parse_game_detail(copy.deepcopy(S), EV), "football/nfl", EV, budget=5)
    raised = False
except Exception as err:
    g, raised = {}, repr(err)
ok("garbage team feeds: no raise, empty last 5 and no leaders", not raised and "leaders" not in g
   and all(not v.get("g") for v in (g.get("last5") or {}).values()), (raised, g.get("last5")))
net.mode = "ok"
for junk in (None, [], {"events": "x"}, {"team": {"id": "11"}, "events": [None, {"competitions": "x"}, {"competitions": [{"status": {"type": {"completed": True}}, "competitors": [{"id": "11", "score": {"value": "x"}}, {}]}]}]}):
    try:
        E._shape_sched(junk); E._shape_leaders(junk); E._shape_ath(junk)
        raised = False
    except Exception as err:
        raised = repr(err)
    ok("the team-feed shapers never raise on " + repr(junk)[:40], raised is False, raised)
ok("a leader with an odd athlete link or value is skipped",
   E._shape_leaders({"categories": [{"name": "passingLeader", "leaders": [{"value": 10, "athlete": {"$ref": "http://x/athletes/../../etc"}}]},
                                    {"name": "rushingLeader", "leaders": [{"value": "big", "athlete": {"$ref": "http://x/athletes/12"}}]}]}) == {})

# ---- only football leagues with a known core league, plain numeric team ids; anything else is left alone (no fetch)
fresh(); net.calls.clear()
base = E._parse_game_detail(copy.deepcopy(S), EV)
odd = copy.deepcopy(base); odd["board"]["home"]["id"] = "34/../x"
ok("an odd team id: no team fetch, the detail is returned as it was",
   E.game_extras(odd, "football/nfl", EV, budget=1) == odd and E.game_extras(base, "basketball/nba", EV, budget=1) == base and not net.calls, net.calls)
ok("college football maps to the core feed's league", E.CORE_LEAGUE.get("football/college-football") == "college-football")
E.game_extras(base, "football/college-football", EV, budget=5)
ok("college football fetches its own schedule and leaders", any("/football/college-football/teams/11/schedule" in u for u in net.calls)
   and any("/leagues/college-football/seasons/2026/types/2/teams/11/leaders" in u for u in net.calls), net.calls)

# ---- review fixes: any failure backs off; playoffs add postseason games; preseason uses last season; missing names are
#      retried on their own; names expire after a day; a backing-off entry survives a prune
fresh(); net.calls.clear()
big = {"categories": [{"name": "passingLeader", "leaders": [{"value": 10 ** 400, "athlete": {"$ref": "http://x/athletes/12"}}]}]}
orig_get = net.get
net.get = lambda url, params=None, headers=None, **kw: Resp(big) if "/leaders" in url else orig_get(url, params, headers, **kw)
kL = ("lead", "nfl", 2026, "11")
E._gx_get(kL, "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2026/types/2/teams/11/leaders", E._shape_leaders)
net.get = orig_get
ok("a feed that makes the shaper overflow still takes the backoff path (no refetch every poll)",
   kL in E.GX and E.GX[kL][2] == 1 and E.GX[kL][3] > time.time(), E.GX.get(kL))
fresh(); net.calls.clear()
po = copy.deepcopy(base); po["board"]["stype"] = 3
E.game_extras(po, "football/nfl", EV, budget=5)
ok("in the playoffs both the regular season and the postseason schedules are read",
   any("seasontype=3" in u for u in net.calls) and any("seasontype=2" in u for u in net.calls), [u for u in net.calls if "schedule" in u])
fresh(); net.calls.clear()
pr = copy.deepcopy(base); pr["board"]["stype"] = 1
E.game_extras(pr, "football/nfl", EV, budget=5)
ok("in the preseason last season's results and leaders are used", any("season=2025&seasontype=2" in u for u in net.calls)
   and any("/seasons/2025/types/2/" in u for u in net.calls), [u for u in net.calls if "schedule" in u or "leaders" in u])
fresh(); net.calls.clear(); net.mode = "down"
E.game_extras(base, "football/nfl", EV, budget=0)
for t in list(E.GX_JOB["t"].values()):
    t.join(5)
net.mode = "ok"
for k in list(E.GX):
    E.GX[k] = (time.time(), {"pass": {"id": "4688813", "v": 354.0, "line": ""}} if k[0] == "lead" else {"rec": "", "g": []}, 0, 0)
E.ATH.pop("4688813", None); net.calls.clear()
g = E.game_extras(base, "football/nfl", EV, budget=5)
ok("a leader whose name is missing is looked up again on its own (schedule and leaders still fresh)",
   [u for u in net.calls if "/athletes/4688813" in u] and not [u for u in net.calls if "schedule" in u or "/leaders" in u], net.calls)
ok("...and the name then shows", any((r.get("away") or {}).get("n") == "J. Downs" for r in g.get("leaders") or []), g.get("leaders"))
E.ATH["4688813"] = (time.time() - E.GX_TTL["ath"] - 5, {"n": "Old Name", "s": "O. Name", "j": "99"})
E.GX.pop(("ath", "4688813"), None)
ok("a name older than a day is due again", not E._ath_known("4688813") and E._ath_due("nfl", 2026, ["11", "34"]) == ["4688813"])
fresh()
E.GX[("sched", "x", "1", 2026, 2)] = (0, None, 3, time.time() + 1800)       # backing off
for i in range(E.GX_MAX):
    E.GX[("ath", str(i))] = (time.time() - 100, None, 0, 0)
E._gx_get(("ath", "zz"), "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/athletes/0", E._shape_ath)
ok("pruning the cache keeps an entry that is still backing off", ("sched", "x", "1", 2026, 2) in E.GX and len(E.GX) <= E.GX_MAX // 2 + 2, len(E.GX))
fresh()

# ---- the GAME_DETAIL eviction no longer trips over another thread adding a game mid-sweep (issue #72 follow-up)
fresh()


class Sneaky(float):
    """A fetched-at time that adds a game to the cache the moment the sweep looks at it (another web thread)."""
    def __rsub__(self, other):
        E.GAME_DETAIL.setdefault("sneaky-%d" % len(E.GAME_DETAIL), (time.time(), {}))
        return float(other) - float(self)


E.GAME_DETAIL["111"] = (Sneaky(time.time() - E.GAME_DETAIL_KEEP - 5), {"old": 1})
E.GAME_DETAIL["222"] = (Sneaky(time.time() - 60), {"recent": 1})
try:
    E.game_detail(EV, "nfl", max_age=0)
    raised = False
except RuntimeError as err:
    raised = repr(err)
ok("eviction while another thread inserts: no 'dictionary changed size' error", raised is False, raised)
ok("...and the old game is still evicted, the recent one kept", "111" not in E.GAME_DETAIL and "222" in E.GAME_DETAIL and EV in E.GAME_DETAIL, list(E.GAME_DETAIL))
src = inspect.getsource(E.game_detail)
ok("the sweep walks a copy and pops", "list(GAME_DETAIL.items())" in src and "GAME_DETAIL.pop(k, None)" in src)

# ---- lower-is-better: the leader logic itself (fewer leads on those rows, more on the rest, a tie or no numbers is neutral)
ok("_ts_leader: higher-is-better", E._ts_leader(5, 3, False) == "a" and E._ts_leader(3, 5, False) == "h")
ok("_ts_leader: lower-is-better flips it", E._ts_leader(5, 3, True) == "h" and E._ts_leader(3, 5, True) == "a" and E._ts_leader(0, 1, True) == "a")
ok("_ts_leader: a tie or missing numbers lead nobody", E._ts_leader(2, 2, True) == "" and E._ts_leader(2, 2, False) == "" and E._ts_leader(None, 2, True) == "" and E._ts_leader(2, None, False) == "")
want_lo = ["turnovers", "fumblesLost", "interceptions", "sacksYardsLost", "totalPenaltiesYards", "Fumbles Lost", "Penalty Yards"]
want_hi = ["totalYards", "netPassingYards", "rushingYards", "firstDowns", "thirdDownEff", "fourthDownEff", "redZoneAttempts",
           "yardsPerPlay", "totalOffensivePlays", "possessionTime", "defensiveTouchdowns"]
ok("_ts_lower: the fewer-is-better keys", all(E._ts_lower(k, "") for k in want_lo), [k for k in want_lo if not E._ts_lower(k, "")])
LABELS = dict(E.TEAM_STATS)
ok("_ts_lower: everything else is higher-is-better", not [k for k in want_hi if E._ts_lower(k, LABELS.get(k, ""))], [k for k in want_hi if E._ts_lower(k, LABELS.get(k, ""))])
ok("_ts_lower: a feed's own labels count too (Turnovers, Times Sacked, Penalties)",
   E._ts_lower("x", "Turnovers") and E._ts_lower("x", "Times Sacked") and E._ts_lower("x", "Penalties") and not E._ts_lower("x", "Points Per Game"))
mk = lambda a, h, k="turnovers", lab="Turnovers": E._parse_team_stats({"boxscore": {"teams": [
    {"homeAway": "away", "statistics": [{"name": k, "label": lab, "displayValue": a}]},
    {"homeAway": "home", "statistics": [{"name": k, "label": lab, "displayValue": h}]}]}}, {})
r_ = mk("3", "1")[0]
ok("a row through the parser: turnovers 3 vs 1 -> lo, home leads", r_["lo"] is True and r_["ld"] == "h", r_)
r_ = mk("0", "0")[0]
ok("turnovers 0 vs 0: no bar numbers, nobody leads", r_["ld"] == "" and r_["an"] is None, r_)
r_ = mk("0", "2")[0]
ok("turnovers 0 vs 2: away leads", r_["ld"] == "a", r_)
r_ = mk("31:24", "28:36", "possessionTime", "Time of possession")[0]
ok("time of possession 31:24 vs 28:36: more leads (away)", r_["lo"] is False and r_["ld"] == "a", r_)

# ---- the first open of a game never waits for the team fetches: a slow ESPN gives the page at once, the tabs fill in later
fresh(); net.calls.clear(); net.delay = 1.2
t0 = time.time()
g = E.game_detail(EV, "nfl", max_age=0)
took = time.time() - t0
ok("slow team feeds: the first open returns without waiting (well under the old 1.5 s)", took < 0.6, round(took, 2))
ok("...with the scoreboard, plays and summary tabs already there", bool(g.get("board")) and "box" in g and "tstats" in g and "inj" in g, list(g))
ok("...and 'gxp' (team data still coming) instead of last 5 / leaders", g.get("gxp") is True and "last5" not in g and "leaders" not in g, list(g))
t0 = time.time()
g = E.game_detail(EV, "nfl", max_age=0)
ok("a poll while they are still loading is quick too, and still says gxp", time.time() - t0 < 0.6 and g.get("gxp") is True)
for t in list(E.GX_JOB["t"].values()):
    t.join(15)
net.delay = 0
g = E.game_detail(EV, "nfl", max_age=0)
ok("once the background fetch lands the next poll has last 5 and season leaders, and no gxp", bool(g.get("last5")) and bool(g.get("leaders")) and "gxp" not in g, list(g))
fresh(); net.calls.clear(); net.delay = 0.2
g = E.game_detail(EV, "nfl", max_age=0, budget=5)
ok("budget=5 waits for the fetch and then has the data", bool(g.get("last5")) and "gxp" not in g, list(g))
net.delay = 0
# a team fetch that never lands: 'still loading' ends after GX_PENDING_MAX, so the page stops showing a skeleton forever
fresh(); net.calls.clear()
real_kick = E._gx_kick
E._gx_kick = lambda job: None
base = E._parse_game_detail(copy.deepcopy(S), EV)
g = E.game_extras(base, "football/nfl", EV)
ok("nothing fetched yet and no thread: gxp", g.get("gxp") is True)
for k in list(E.GX_FIRST):
    E.GX_FIRST[k] -= E.GX_PENDING_MAX + 5
g = E.game_extras(base, "football/nfl", EV)
ok("...but not forever: after GX_PENDING_MAX the page stops saying 'loading'", "gxp" not in g, list(g))
E._gx_kick = real_kick
# a refresh that is still running keeps saying 'loading' however long ESPN takes (the cap is only for a fetch that never started)
fresh(); net.calls.clear(); net.delay = 1.0
g = E.game_extras(base, "football/nfl", EV)
for k in list(E.GX_FIRST):
    E.GX_FIRST[k] -= E.GX_PENDING_MAX + 5
g = E.game_extras(base, "football/nfl", EV)
ok("a live background fetch still says gxp past the cap", g.get("gxp") is True and any(t.is_alive() for t in E.GX_JOB["t"].values()), list(g))
for t in list(E.GX_JOB["t"].values()):
    t.join(15)
net.delay = 0
ok("...and stops once it has landed", "gxp" not in E.game_extras(base, "football/nfl", EV))
ok("the penalty/turnover matching is exact: a 'failed' or defensive label is not flipped", not E._ts_lower("x", "Failed Conversions") and not E._ts_lower("sacks", "Sacks"))
fresh()

# ---- prefetch (a game card shown or pressed): polite, deduped, capped, backs off
def warm_join():
    import threading
    for th in [x for x in threading.enumerate() if x.name == "gamewarm"]:
        th.join(10)
    for t in list(E.GX_JOB["t"].values()):
        t.join(10)


def warm_reset():
    fresh()
    E.GAME_WARM["ev"].clear(); E.GAME_WARM["stamps"].clear(); E.GAME_WARM["busy"] = 0
    net.calls.clear(); net.mode = "ok"; net.delay = 0


warm_reset()
ok("a football game is warmed once", E.game_prefetch(EV, "nfl") is True)
warm_join()
ok("...its summary and team data are then ready (the page opens with last 5 and leaders at once)",
   EV in E.GAME_DETAIL and bool(E.game_detail(EV, "nfl", max_age=60).get("last5")) and "gxp" not in E.game_detail(EV, "nfl", max_age=60))
n = len(net.calls)
ok("the same game again right away is skipped (deduped)", E.game_prefetch(EV, "nfl") is False)
ok("...and nothing was fetched for it", len(net.calls) == n)
ok("a sport with no football feed, a bad id, and nothing are all skipped (no fetch, no raise)",
   E.game_prefetch(EV, "nba") is False and E.game_prefetch("../x", "nfl") is False and E.game_prefetch("", "nfl") is False
   and E.game_prefetch(None, None) is False and E.game_prefetch("1" * 40, "nfl") is False and len(net.calls) == n)
warm_reset()
E.GAME_WARM["ev"][EV] = (time.time() - E.WARM_MIN - 1, 0, 0)
ok("a game warmed a while ago can be warmed again", E.game_prefetch(EV, "nfl") is True)
warm_join()
warm_reset()
net.mode = "down"
ok("ESPN down: the warm-up still just returns (started)", E.game_prefetch(EV, "nfl") is True)
warm_join()
fails, nxt = E.GAME_WARM["ev"][EV][1], E.GAME_WARM["ev"][EV][2]
ok("a failed warm-up backs off 60 s", fails == 1 and 55 < nxt - time.time() <= 61, E.GAME_WARM["ev"][EV])
E.GAME_WARM["ev"][EV] = (time.time() - E.WARM_MIN - 1, fails, nxt)
ok("...even when the dedupe window has passed, it waits out the backoff", E.game_prefetch(EV, "nfl") is False)
E.GAME_WARM["ev"][EV] = (time.time() - E.WARM_MIN - 1, 1, 0)
net.mode = "ok"
ok("...and after the backoff a good answer clears it", E.game_prefetch(EV, "nfl") is True)
warm_join()
ok("...failures back to zero", E.GAME_WARM["ev"][EV][1] == 0 and E.GAME_WARM["ev"][EV][2] <= time.time() + 1, E.GAME_WARM["ev"][EV])
warm_reset()
E.GAME_WARM["busy"] = E.WARM_THREADS
ok("at most WARM_THREADS warm-ups at once", E.game_prefetch(EV, "nfl") is False and not net.calls)
E.GAME_WARM["busy"] = 0
E.GAME_WARM["stamps"][:] = [time.time()] * E.WARM_PER_MIN
ok("at most WARM_PER_MIN a minute across all games", E.game_prefetch(EV, "nfl") is False and not net.calls)
warm_reset()
for i in range(E.WARM_KEEP + 20):
    E.GAME_WARM["ev"][str(1000 + i)] = (time.time() - 1000 + i, 0, 0)
E.game_prefetch(EV, "nfl"); warm_join()
ok("the remembered games stay bounded", len(E.GAME_WARM["ev"]) <= E.WARM_KEEP, len(E.GAME_WARM["ev"]))
warm_reset()
wsrc0 = open(os.path.join(os.environ.get("REPO", ".."), "watcher/combo_watcher.py")).read()
wm = wsrc0[wsrc0.index("    def api_game_warm(t):"):wsrc0.index("    def api_games():")]
ok("the warm route only ever calls game_prefetch (no buy/sell/panel/offer function)",
   "A.game_prefetch(" in wm and not any(k in wm for k in ("accept_offer", "get_offer", "kalshi_send", "panel_", "auto_sell", "TapLock", "alock", "api_act", ".post(")), wm[:200])
ok("...and the route is a plain GET that the page can call", 'path == "/app/api/game_warm"' in wsrc0)

# ---- isolation: no money/account/trading path reaches any of this, and none of it takes a lock or writes anything
MONEY = ["panel_exec", "panel_pass", "build_panel", "choose_panel", "panel_approve", "panel_add", "_buy_panel_bet", "panel_collect",
         "auto_sell_now", "take_profit_reason", "single_sell_reason", "smart_sell_singles", "leg_score", "pick_state", "fetch_scores",
         "accept_offer", "get_offer", "kalshi_send", "what_if", "stop_loss_check", "hedge_guard", "smart_tune", "live_view", "mine_page"]
NEW = ("game_extras", "game_prefetch", "GAME_WARM", "_ts_lower", "_ts_leader", "_gx_", "GX", "ATH[", "ATH.", "_parse_box", "_parse_team_stats", "_parse_injuries", "_note_athletes",
       "_shape_sched", "_shape_leaders", "_shape_ath", "_lead_line", "_ts_num", "LEAD_CATS", "TEAM_STATS", "BOX_GROUPS")
leaks = [f for f in MONEY if hasattr(E, f) and any(k in inspect.getsource(getattr(E, f)) for k in NEW)]
ok("no money/account/trading function reads the slice-3 tabs or their caches", not leaks and all(hasattr(E, f) for f in MONEY[:12]), leaks)
mine = [f for f in dir(E) if f in ("game_extras", "_parse_box", "_parse_team_stats", "_parse_injuries", "_note_athletes", "_shape_sched",
                                   "_shape_leaders", "_shape_ath", "_gx_get", "_gx_refresh", "_gx_kick", "_gx_last5", "_gx_leaders")]
ok("all the slice-3 helpers exist", len(mine) == 13, mine)
locked = [f for f in mine if any(k in inspect.getsource(getattr(E, f)) for k in ("TapLock", "act_lock", ".hold(", "alock", "store_x", "panel_tx", "save_json", "open("))]
ok("the slice-3 helpers take no tap lock and write nothing to disk or the database", not locked, locked)
posts = [f for f in mine if any(k in inspect.getsource(getattr(E, f)) for k in (".post(", "kalshi", "hub_call"))]
ok("the slice-3 helpers only GET public ESPN feeds (never Kalshi, never the hub's signed calls)", not posts, posts)
wsrc = open(os.path.join(os.environ.get("REPO", ".."), "watcher/combo_watcher.py")).read() if os.path.exists(
    os.path.join(os.environ.get("REPO", ".."), "watcher/combo_watcher.py")) else open("wtest/combo_watcher.py").read()
api_src = wsrc[wsrc.index("    def api_game(t):"):wsrc.index("    def api_games():")]
ok("the watcher calls the game detail only from the web app's game page (api_game)",
   wsrc.count("game_detail(") == 1 and "A.game_detail(" in api_src and "game_extras" not in wsrc and "_gx_" not in wsrc
   and wsrc.count("game_prefetch(") == 1)
fresh()
