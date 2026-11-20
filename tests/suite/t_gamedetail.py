"""Slices 1 and 2 of the live game page (issue #72): the situation fields fetch_scores now surfaces, and the
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

# ===================== Slice 2: the play-by-play (drives + plays) pulled from the same summary =====================
net.mode = "ok"
before = len([c for c in net.calls if "/summary" in c[0]])
d2 = E.game_detail("401873066", "nfl", max_age=0)
after = len([c for c in net.calls if "/summary" in c[0]])
ok("drives and plays ride the one summary fetch game_detail already makes (no second ESPN call)", after - before == 1, after - before)
pb = d2.get("pbp") or {}
dvs = pb.get("drives") or []
ok("pbp has the 4 earlier drives plus the current one, oldest first", [x["id"] for x in dvs] == ["4018730661", "4018730662", "4018730663", "4018730664", "4018730665"], [x.get("id") for x in dvs])
ok("each drive carries the offence, result, 'N plays, M yards' and its quarter",
   dvs[0]["team"] == "IND" and dvs[0]["side"] == "away" and dvs[0]["res"] == "Touchdown" and dvs[0]["sum"] == "3 plays, 75 yards" and dvs[0]["q"] == 1
   and dvs[1]["team"] == "HOU" and dvs[1]["side"] == "home" and dvs[2]["q"] == 2 and dvs[3]["sum"] == "1 play, 0 yards", dvs[:2])
ok("the current drive is appended and marked", dvs[-1].get("cur") is True and len(dvs[-1]["plays"]) == 1 and not any(x.get("cur") for x in dvs[:-1]))
byid = {pl["id"]: pl for x in dvs for pl in x["plays"]}
td, fg, intc, pen, sack, tmo, punt, ko = (byid.get(i) or {} for i in (
    "401873066103", "401873066121", "401873066112", "401873066120", "401873066110", "401873066111", "401873066130", "401873066100"))
ok("a scoring play is flagged and so is its drive", td.get("sc") is True and fg.get("sc") is True and dvs[0]["sc"] is True and dvs[2]["sc"] is True and dvs[1]["sc"] is False, (td, dvs[1]))
ok("a turnover play is flagged (isTurnover) and so is its drive", intc.get("to") is True and dvs[1]["to"] is True and td.get("to") is False and dvs[0]["to"] is False, intc)
ok("a penalty is flagged", pen.get("pen") is True and td.get("pen") is False)
ok("play fields: type, text, clock, down & distance, yards, quarter",
   sack.get("ty") == "Sack" and "sacked" in sack.get("txt", "") and sack.get("clk") == "12:51" and sack.get("dn") == "1st & 10" and sack.get("yd") == -8 and sack.get("q") == 1, sack)
ok("ball spots: yards to the end zone before/after, and whose end zone it is (a turnover or punt flips it)",
   intc.get("a") == 50 and intc.get("as") == "home" and intc.get("b") == 73 and intc.get("bs") == "away"
   and punt.get("a") == 60 and punt.get("as") == "home" and punt.get("b") == 78 and punt.get("bs") == "away"
   and ko.get("a") == 65 and ko.get("as") == "home" and ko.get("b") == 75 and ko.get("bs") == "away", (intc, punt, ko))
ok("a touchdown or field goal ends with the ball in the end zone (0)", td.get("b") == 0 and fg.get("b") == 0 and td.get("bs") == "away", td)
ok("the state after the play (spot text, new down & distance) is there for the strip",
   ko.get("ep") == "IND 25" and ko.get("edd") == "1st & 10 at IND 25" and ko.get("ed") == 10 and td.get("edd") == "", ko)
ok("a timeout/admin play has no ball movement (ESPN's yard line on it is junk)", tmo.get("a") is None and tmo.get("b") is None and tmo.get("as") is None, tmo)

# the turnover flag is derived from the type when ESPN leaves isTurnover off; a fumble the offence recovers is not one
SUM = copy.deepcopy(FX["summary"])
pl = SUM["drives"]["previous"][1]["plays"][2]
pl.pop("isTurnover")
SUM["drives"]["previous"][0]["plays"][1]["type"]["text"] = "Fumble Recovery (Own)"
SUM["drives"]["previous"][0]["plays"][2]["type"]["text"] = "Fumble Recovery (Opponent)"
q2 = E._parse_game_detail(SUM)["pbp"]["drives"]
ok("interception is a turnover even without isTurnover",
   q2[1]["plays"][2]["to"] is True)
ok("a fumble recovered by the offence is not a turnover, by the other side is",
   q2[0]["plays"][1]["to"] is False and q2[0]["plays"][2]["to"] is True)

# the current drive is not added twice when ESPN also lists it in previous[]
SUM = copy.deepcopy(FX["summary"])
SUM["drives"]["previous"].append(copy.deepcopy(SUM["drives"]["current"]))
ok("a current drive that is also in previous[] is not duplicated", len(E._parse_game_detail(SUM)["pbp"]["drives"]) == 5)

# ---- missing/odd drives never raise and just leave the tab out
def pbp_of(summary_drives):
    S = copy.deepcopy(FX["summary"])
    if summary_drives == "ABSENT":
        S.pop("drives", None)
    else:
        S["drives"] = summary_drives
    try:
        r = E._parse_game_detail(S)
        return r, False
    except Exception as err:
        return {"X": err}, True

for label, val in (("absent", "ABSENT"), ("a string", "nope"), ("a list", []), ("empty dict", {}), ("previous is None", {"previous": None}),
                   ("previous holds junk", {"previous": [None, "x", 7, {"plays": "oops"}, {"team": None, "plays": [None, 5, "a"]}]}),
                   ("drives with no plays", {"previous": [{"id": "1", "team": {"id": "11"}, "plays": []}]}),
                   ("current with no plays", {"current": {"id": "9", "team": {"id": "11"}, "plays": []}})):
    r, raised = pbp_of(val)
    ok("odd drives (%s): no raise, board still there, no pbp key" % label, not raised and "pbp" not in r and bool((r.get("board") or {}).get("home")), r)

# odd plays inside a good drive: the bad ones are skipped, a missing yard line is None, a wild one is dropped
r, raised = pbp_of({"previous": [{"id": "1", "team": {"id": "11", "abbreviation": "IND"}, "result": "PUNT", "plays": [
    None, 5, {"id": "a", "type": None, "text": None, "start": None, "end": "x", "clock": "bad", "period": "bad"},
    {"id": "b", "type": {"text": "Rush"}, "text": "x" * 900, "period": {"number": 1},
     "start": {"down": 1, "distance": 10, "yardsToEndzone": 250, "team": {"id": "99"}}, "end": {"yardsToEndzone": "abc"}},
    {"id": "c", "type": {"text": "Rush"}, "text": "ok", "period": {"number": 1}, "start": {"down": 2, "yardsToEndzone": 40}, "end": {"yardsToEndzone": 35}}]}]})
pp = ((r.get("pbp") or {}).get("drives") or [{}])[0].get("plays") or []
ok("odd plays: junk skipped, no raise", not raised and [x["id"] for x in pp] == ["a", "b", "c"], pp)
ok("a missing or out-of-range yard line becomes None (no ball move), and the text is capped",
   pp and pp[1]["a"] is None and pp[1]["b"] is None and len(pp[1]["txt"]) == E.PBP_TEXT_MAX and pp[0]["a"] is None, pp[:2])
ok("a half-known move (only one end) shows no ball move rather than a jump from nowhere", pp and pp[2]["a"] == 40 and pp[2]["b"] == 35 and pp[2]["dn"] == "", pp[2:])
ok("an unknown team falls back to the drive's side", pp and pp[1]["as"] is None and pp[2]["as"] == "away" and pp[2]["bs"] == "away", pp)

# ---- the cap: hundreds of plays are cut to PBP_MAX_PLAYS, the newest drives kept and `cut` says how many were left off
def mk_play(i):
    return {"id": "p%d" % i, "type": {"text": "Rush"}, "text": "t", "period": {"number": 1}, "start": {"down": 1, "yardsToEndzone": 50}, "end": {"yardsToEndzone": 45}}
big = {"previous": [{"id": "d%d" % n, "team": {"id": "11", "abbreviation": "IND"}, "result": "PUNT", "offensivePlays": 10,
                      "plays": [mk_play(n * 100 + i) for i in range(10)]} for n in range(60)]}
r, raised = pbp_of(big)
bp = r.get("pbp") or {}
sent = sum(len(x["plays"]) for x in bp.get("drives", []))
ok("600 plays are capped at PBP_MAX_PLAYS", not raised and 0 < sent <= E.PBP_MAX_PLAYS and bp.get("n") == 600 and bp.get("cut") == 600 - sent, (sent, bp.get("n"), bp.get("cut")))
ok("the cap keeps the NEWEST drives", bp["drives"][-1]["id"] == "d59" and bp["drives"][0]["id"] != "d0")
one = {"previous": [{"id": "d1", "team": {"id": "11"}, "plays": [mk_play(i) for i in range(500)]}]}
r, raised = pbp_of(one)
ok("a single huge drive keeps its latest plays", not raised and len(r["pbp"]["drives"][0]["plays"]) == E.PBP_MAX_PLAYS and r["pbp"]["drives"][0]["plays"][-1]["id"] == "p499")

# ---- a garbage / failed summary leaves no pbp and a swallowed error is logged once with the existing gamedetail pattern
net.mode = "garbage"
ok("a malformed summary gives no pbp (empty detail)", "pbp" not in E.game_detail("401873066", "nfl", max_age=0))
net.mode = "ok"
ok("a non-football sport gets no pbp", E.game_detail("401873066", "nba", max_age=0) == {})
orig_pbp = E._parse_pbp
E._parse_pbp = lambda drives, side_of: (_ for _ in ()).throw(TypeError("boom"))       # the backstop: a bug in the shaper must only drop the tab
try:
    bd = E.game_detail("401873066", "nfl", max_age=0)
    raised = False
except Exception as err:
    bd, raised = {"X": err}, True
E._parse_pbp = orig_pbp
ok("if the pbp shaper itself failed, the rest of the detail survives and nothing raises", not raised and bool((bd.get("board") or {}).get("home")) and "pbp" not in bd, bd)
ok("that swallowed failure was logged under the gamedetail key", any(k[0] == "gamedetail" and k[2] == "TypeError" for k in E.KLIVE_LOGGED), list(E.KLIVE_LOGGED)[:5])

# ---- isolation (slice 2): the feed's plays reach no money path, take no lock, and the page's JS never trades or fetches
import re as _re
wsrc = open(os.path.join(os.environ.get("REPO", ".."), "watcher/combo_watcher.py")).read() if os.path.exists(
    os.path.join(os.environ.get("REPO", ".."), "watcher/combo_watcher.py")) else open("wtest/combo_watcher.py").read()
j0 = wsrc.index("/* ---- The game page's tab framework")
j1 = wsrc.index("function winChart(")
block = wsrc[j0:j1]
ok("the tab/play-by-play JS block was found", len(block) > 3000, len(block))
code = _re.sub(r"/\*.*?\*/", "", block, flags=_re.S)            # the explanatory comments may name what the code must not do
bad = [k for k in ("api(", "fetch(", "XMLHttpRequest", "/app/api/", "TapLock", "localStorage")
       if k in code] + _re.findall(r"\b(?:buy|sell|order|cashout|panel|stake)", code)
ok("the tab/play-by-play JS never fetches, trades, or stores anything (it only reads the page's own game answer)", not bad, bad)
api_src = wsrc[wsrc.index("    def api_game(t):"):wsrc.index("    def api_games():")]
ok("api_game never takes the tap lock and logs feed trouble under gamedetail", "TapLock" not in api_src and 'klive_log_once("gamedetail"' in api_src)
for fn in ("panel_loop", "panel_wait"):
    ok("the watcher's %s never touches the pbp data" % fn, "pbp" not in wsrc[wsrc.index("def %s(" % fn):wsrc.index("def %s(" % fn) + 6000].split("\ndef ")[0])

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
DISPLAY = ("game_detail", "_parse_game_detail", "_situation_info", "_parse_pbp", "_pbp_play")
leaks = [f for f in MONEY if hasattr(E, f)
         and any(k in inspect.getsource(getattr(E, f)) for k in DISPLAY)]
ok("no money/account/trading function calls the game-detail display helpers",
   not leaks and all(hasattr(E, f) for f in ("auto_sell_now", "take_profit_reason", "single_sell_reason",
                                             "leg_score", "pick_state")), leaks)
# the display helpers themselves touch no lock (TapLock lives in the watcher; here just prove they never try to)
locked = [f for f in DISPLAY if hasattr(E, f)
          and any(k in inspect.getsource(getattr(E, f)) for k in ("TapLock", "act_lock", ".hold(", "alock"))]
ok("the game-detail display helpers never acquire the tap lock", not locked, locked)
