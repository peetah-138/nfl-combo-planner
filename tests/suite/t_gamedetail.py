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

# ---- a non-numeric event id is turned away before any ESPN fetch (defence in depth)
before = len(net.calls)
ok("a non-numeric event id returns empty and never calls ESPN",
   E.game_detail("401; drop", "nfl", max_age=0) == {} and E.game_detail("../secret", "nfl", max_age=0) == {}
   and len(net.calls) == before)

# ---- college football is gated in exactly like the NFL (both are "football/..." in SPORTS/LEAGUES)
net.mode = "ok"
dc = E.game_detail("401873066", "ncaaf", max_age=0)
ok("college football (ncaaf) is a football league, so the strip is built like the NFL's",
   isinstance(dc, dict) and bool(dc.get("board")), dc)

# ---- a valid board but no current drive: the strip still gets its scoreboard, no 'drive' key, no raise
import copy as _copy
FX_NODRIVE = _copy.deepcopy(FX)
FX_NODRIVE["summary"].pop("drives", None)                       # a feed with no drives block at all
orig_get = net.get


def _nodrive_get(url, params=None, headers=None, **kw):
    net.calls.append((url, dict(params or {})))
    if "/summary" in url:
        return Resp(_copy.deepcopy(FX_NODRIVE["summary"]))
    if "/scoreboard" in url:
        return Resp(_copy.deepcopy(FX_NODRIVE["scoreboard"]))
    return Resp({"events": []})


net.get = _nodrive_get
try:
    nd = E.game_detail("401873066", "nfl", max_age=0)
    raised = False
except Exception as err:
    nd, raised = {"X": err}, True
net.get = orig_get
ok("no drives.current: a board but no 'drive' key, and no raise",
   raised is False and bool((nd.get("board") or {}).get("home")) and "drive" not in nd, nd)

# ---- _situation_info (called directly) is tolerant: a bad shape yields {}, a partial-but-dict shape passes through
#      (a missing field is None/empty so the strip just leaves it out), and nothing ever raises.
cases = [
    (None, {}, "{}", lambda r: r == {}),                       # not a dict -> {}
    ("oops", {}, "{}", lambda r: r == {}),                     # a string -> {}
    ({"down": "x", "distance": None}, {}, "dict", lambda r: isinstance(r, dict) and r.get("down") == "x"),
    ({"down": 2, "distance": 7}, {"text": "pass complete"}, "dict (no lastPlay.type)",
     lambda r: isinstance(r, dict) and r.get("lastPlayType") == "" and r.get("lastPlayText") == "pass complete"),
]
for sit_in, lp_in, label, check in cases:
    try:
        r = E._situation_info(sit_in, lp_in)
        raised = False
    except Exception as err:
        r, raised = {"X": err}, True
    ok("_situation_info degraded (" + label + "): no raise, expected shape", raised is False and check(r), r)

# ---- isolation: no money/account/trading function may reach the game-detail display helpers, and those three
#      must never take the web app's tap lock (they are read on the page thread, outside TapLock). Static source
#      checks, like the other isolation tests (t_kalshi_live / t_robust).
import inspect
# The money/account/trading functions the review named (panel_*, auto_sell_now, take_profit_reason,
# single_sell_reason, leg_score, pick_state), plus the other buy/sell paths. fetch_scores is NOT here: it is the
# score-fetching plumbing that legitimately builds the display situation via _situation_info.
MONEY = ["panel_exec", "panel_pass", "build_panel", "choose_panel", "panel_approve", "panel_add", "_buy_panel_bet",
         "auto_sell_now", "take_profit_reason", "single_sell_reason", "smart_sell_singles", "leg_score",
         "pick_state", "accept_offer", "get_offer", "kalshi_send"]
DISPLAY = ("game_detail", "_parse_game_detail", "_situation_info")
leaks = [f for f in MONEY if hasattr(E, f)
         and any(k in inspect.getsource(getattr(E, f)) for k in DISPLAY)]
ok("no money/account/trading function calls the game-detail display helpers",
   not leaks and all(hasattr(E, f) for f in ("auto_sell_now", "take_profit_reason", "single_sell_reason",
                                             "leg_score", "pick_state")), leaks)
# the display helpers themselves touch no lock (TapLock lives in the watcher; here just prove they never try to)
locked = [f for f in DISPLAY if hasattr(E, f)
          and any(k in inspect.getsource(getattr(E, f)) for k in ("TapLock", "act_lock", ".hold(", "alock"))]
ok("the game-detail display helpers never acquire the tap lock", not locked, locked)
