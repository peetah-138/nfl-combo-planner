"""Slice 1 of the live game page (issue #72): the situation fields fetch_scores now surfaces, and the
game_detail() helper that parses the ESPN summary for the field strip. Display only, football only, defensive:
a malformed feed yields empty and never raises. The network is faked from fixtures/espn_game_detail.json."""
import os, json, copy, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))
FX = json.load(open("fixtures/espn_game_detail.json"))


class Resp:
    def __init__(self, body, code=200):
        self.body, self.status_code, self.ok, self.headers = body, code, code < 400, {}

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class Net:
    """requests stand-in: answers ESPN scoreboard + summary from the fixture; `mode` forces failures/garbage."""
    RequestException = E._requests.RequestException

    def __init__(self):
        self.calls, self.mode = [], "ok"

    def get(self, url, params=None, headers=None, **kw):
        self.calls.append((url, dict(params or {})))
        if self.mode == "down":
            raise self.RequestException("down")
        if self.mode == "500":
            return Resp({}, 500)
        if "/summary" in url:
            return Resp(copy.deepcopy(FX["summary"]) if self.mode != "garbage" else {"header": {"competitions": []}})
        if "/scoreboard" in url:
            return Resp(copy.deepcopy(FX["scoreboard"]) if self.mode != "garbage" else {"events": [{"competitions": [{"situation": "oops"}]}]})
        return Resp({"events": []})


net = Net(); E.requests = net
E.set_league("nfl")

# ---- fetch_scores now carries the football situation (down/distance/yardLine/timeouts/last play) on the game info
by = E.fetch_scores(max_age=0, code="nfl")
ind = (by.get("Indianapolis Colts") or by.get(E.norm_team("Indianapolis Colts")) or [None])[0]
hou = (by.get("Houston Texans") or by.get(E.norm_team("Houston Texans")) or [None])[0]
ok("fetch_scores finds both teams of the live game", bool(ind) and bool(hou))
sit = (ind or {}).get("situation") or {}
ok("situation has down & distance", sit.get("down") == 1 and sit.get("distance") == 10, sit)
ok("situation has the yard line", sit.get("yardLine") == 27, sit)
ok("situation carries last play text + type",
   "INTERCEPTED" in (sit.get("lastPlayText") or "") and sit.get("lastPlayType") == "Interception", sit)
ok("timeouts are split per team (home 3 / away 2), and the pick's own side is picked out",
   sit.get("homeTimeouts") == 3 and sit.get("awayTimeouts") == 2 and sit.get("myTimeouts") == 2, sit)  # IND is away
ok("possession is a boolean from this team's side (IND has the ball)", sit.get("possession") is True, sit)
housit = (hou or {}).get("situation") or {}
ok("the home side sees it does not have the ball", housit.get("possession") is False and housit.get("myTimeouts") == 3, housit)

# ---- game_detail(): the parsed ESPN summary the field strip reads
d = E.game_detail("401873066", "nfl", max_age=0)
b = d.get("board") or {}
ok("game_detail returns a scoreboard with both teams", (b.get("home") or {}).get("abbr") == "HOU" and (b.get("away") or {}).get("abbr") == "IND", b)
ok("scoreboard carries scores, period, clock, broadcast",
   (b.get("away") or {}).get("score") == 3 and b.get("period") == 1 and b.get("displayClock") == "6:50" and b.get("broadcast") == "CBS", b)
ok("team colours come through for the end zones", (b.get("home") or {}).get("color") == "#03202f" and (b.get("away") or {}).get("color") == "#002c5f", b)
ok("records come through", (b.get("away") or {}).get("record") == "3-7", b)
dr = d.get("drive") or {}
ok("the current drive names the offence and the ball spot (yards to end zone) for the strip",
   dr.get("teamAbbr") == "IND" and dr.get("ballYardsToEndzone") == 69, dr)

# ---- football only: other sports get nothing (no field strip)
ok("non-football sport returns empty (no field strip)", E.game_detail("401873066", "nba", max_age=0) == {})
ok("no event id returns empty", E.game_detail("", "nfl", max_age=0) == {})

# ---- defensive: a malformed/empty/failed feed must be empty, never raise
net.mode = "garbage"
try:
    g1 = E.game_detail("401873066", "nfl", max_age=0)
    bad_sit = E.fetch_scores(max_age=0, code="nfl")
    raised = False
except Exception as err:
    g1, raised = {"X": err}, True
ok("malformed summary -> empty dict, no raise", raised is False and g1 == {}, g1)
net.mode = "500"
ok("a 5xx -> empty (last good copy kept), no raise", E.game_detail("401873066", "nfl", max_age=0) in ({}, d))
net.mode = "down"
ok("a network error -> no raise", isinstance(E.game_detail("401873066", "nfl", max_age=0), dict))

# ---- the whole thing is display-only: _parse_game_detail must swallow anything thrown at it
for junk in (None, {}, {"header": None}, {"header": {"competitions": [{"competitors": []}]}}, {"drives": "nope"}):
    try:
        E._parse_game_detail(junk)
        raised = False
    except Exception:
        raised = True
    ok("_parse_game_detail never raises on " + repr(junk)[:40], raised is False)
