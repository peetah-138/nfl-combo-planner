# CHECK: group=page secs=94
"""Slice 1 of the live game page (issue #72): the web app's /app/api/game endpoint assembles the `detail` block
(situation + ESPN-derived board/drive) for a live football game, and never for anything else. Display only; the
real api_game runs against a stubbed engine, so no network or account is touched. Checks:
  (a) a live NFL single -> detail has `situation` plus the board keys;
  (b) a non-live NFL single -> detail is null;
  (c) a live NBA single -> detail is null (football only);
  (d) game_detail raising -> detail null while leg/combos/story stay intact.
Runs the webapp (like test_webapp_pw.py) and reads the endpoint over localhost; no Playwright needed."""
import sys, os, time, threading, json, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
import requests
sys.argv = ["combo_watcher.py", "--webapp"]
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))

NFL_TK = "KXNFLGAME-26NOV20INDHOU-IND"
NBA_TK = "KXNBAGAME-26NOV20BOSNYK-BOS"

# One live single, injected straight into the engine's live snapshot (A.MINE["view"]) that api_live serves.
LIVE_SINGLE = {"t": NFL_TK, "ticker": NFL_TK, "sport": "nfl", "state": "live", "kind": "win", "side": "yes",
               "name": "Colts", "opp": "Texans", "label": "Colts to win", "chance": 0.44, "live": 0.44,
               "pays": 10.0, "cost": 5.0, "worth": 6.0, "how": "Live", "self": False,
               "sc": {"abbr": "IND", "opp_abbr": "HOU", "me": 3, "opp": 0, "detail": "Q1 6:50"}}

# The ESPN-derived summary game_detail would return for the live NFL game (board + drive).
GD = {"board": {"home": {"abbr": "HOU", "name": "Houston Texans", "color": "#03202f", "score": 0, "record": "7-3", "homeAway": "home"},
                "away": {"abbr": "IND", "name": "Indianapolis Colts", "color": "#002c5f", "score": 3, "record": "3-7", "homeAway": "away"},
                "period": 1, "displayClock": "6:50", "state": "in", "completed": False, "broadcast": "CBS"},
      "drive": {"teamId": "11", "teamAbbr": "IND", "ballYardsToEndzone": 69, "downDistanceText": "1st & 10"}}
# The live situation leg_score carries on the score row.
SIT = {"down": 1, "distance": 10, "yardLine": 31, "isRedZone": False, "possession": True,
       "homeTimeouts": 3, "awayTimeouts": 2, "myTimeouts": 2, "downDistanceText": "1st & 10",
       "possessionText": "IND 31", "lastPlayText": "C.Stroud pass INTERCEPTED by A.Smith.", "lastPlayType": "Interception"}

STATE = {"single": dict(LIVE_SINGLE), "gd_raises": False, "A": None}
real_load = W.load_engine


def load():
    A = real_load()
    STATE["A"] = A
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}

    def mine_page(live=False):
        # api_live serves A.MINE["view"]; rebuild it from the current STATE on every refresh so each case's single is seen.
        A.MINE["view"] = {"at": time.time(), "combos": [], "singles": [dict(STATE["single"])], "games": [],
                          "riding": 0, "staked": 0, "chance_one": 0, "best": 0, "cash_now": 0, "today": {}, "auto_sell": True}
        return None
    A.mine_page = mine_page
    A.MINE["all_games"] = {"_": []}          # so api_live doesn't try to fetch real markets
    A.MINE["live"] = True
    mine_page()
    # api_game's detail block: ticker_sport maps the ticker; leg_score gives the score row with the ESPN event id
    # and the live situation; game_detail returns the parsed summary (or raises, for case d).
    A.ticker_sport = lambda t: "nfl" if "NFL" in (t or "") else ("nba" if "NBA" in (t or "") else "")

    def leg_score(leg):
        return {"game": "401873066", "situation": dict(SIT)} if (leg or {}).get("ticker", "").startswith("KXNFL") else {"game": "0"}
    A.leg_score = leg_score

    def game_detail(ev, code, max_age=6):
        if STATE["gd_raises"]:
            raise ValueError("espn feed broke")        # a caught type: api_game must swallow it -> detail None
        return dict(GD) if code == "nfl" else {}
    A.game_detail = game_detail
    A.game_story = lambda t: {"ticks": [], "plays": []}
    A.what_if = lambda *a, **k: None
    return A


W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")


def game(tk, want_state=None):
    """Hit /app/api/game, waiting out the Live snapshot cache (served up to ~30 s) until the single matching `tk`
    shows the state this case set (so one case's cached snapshot can't leak into the next)."""
    end = time.time() + 40
    r = requests.get(B + "/app/api/game", params={"t": tk}, timeout=10).json()
    while want_state is not None and time.time() < end:
        leg = r.get("leg")
        if (leg or {}).get("t") == tk and (leg or {}).get("state") == want_state:
            break
        time.sleep(1)
        r = requests.get(B + "/app/api/game", params={"t": tk}, timeout=10).json()
    return r


# ---- (a) a live NFL single: the detail block is assembled with the situation and the board
STATE["single"] = dict(LIVE_SINGLE); STATE["gd_raises"] = False
g = game(NFL_TK, want_state="live")
det = g.get("detail") or {}
ok("live NFL: leg found and live", (g.get("leg") or {}).get("state") == "live", g.get("leg"))
ok("live NFL: detail carries the ESPN board (both teams, clock, broadcast)",
   bool(det) and (det.get("board") or {}).get("home", {}).get("abbr") == "HOU"
   and (det.get("board") or {}).get("away", {}).get("abbr") == "IND" and (det.get("board") or {}).get("broadcast") == "CBS", det)
ok("live NFL: detail carries the live situation (down/distance/possession)",
   (det.get("situation") or {}).get("downDistanceText") == "1st & 10" and (det.get("situation") or {}).get("possession") is True, det.get("situation"))
ok("live NFL: detail carries the current drive for the ball spot",
   (det.get("drive") or {}).get("teamAbbr") == "IND" and (det.get("drive") or {}).get("ballYardsToEndzone") == 69, det.get("drive"))

# ---- (b) a non-live NFL single: no field strip
STATE["single"] = dict(LIVE_SINGLE, state="pre")
g = game(NFL_TK, want_state="pre")
ok("non-live NFL: detail is null (the strip is live-only)", g.get("detail") is None, g.get("detail"))
ok("non-live NFL: the rest of the page is intact", g.get("leg") is not None and "combos" in g and "story" in g, list(g))

# ---- (c) a live NBA single: football only, so no strip
STATE["single"] = dict(LIVE_SINGLE, t=NBA_TK, ticker=NBA_TK, sport="nba", name="Celtics", opp="Knicks")
g = game(NBA_TK, want_state="live")
ok("live NBA: detail is null (football-only gate)", g.get("detail") is None, g.get("detail"))
ok("live NBA: leg/combos/story still returned", g.get("leg") is not None and "combos" in g and "story" in g, list(g))

# ---- (d) game_detail raising: detail null, but leg/combos/story unaffected
STATE["single"] = dict(LIVE_SINGLE); STATE["gd_raises"] = True
g = game(NFL_TK, want_state="live")
ok("game_detail raising: detail is null", g.get("detail") is None, g.get("detail"))
ok("game_detail raising: leg stays intact", (g.get("leg") or {}).get("state") == "live", g.get("leg"))
ok("game_detail raising: combos and story are still there", "combos" in g and "story" in g, list(g))

# ---- (e) the game's start (issue #486): the chart begins at kickoff, so the answer carries it (sportsbook time), and never an estimate
import datetime as _dt
STATE["single"] = dict(LIVE_SINGLE); STATE["gd_raises"] = False
EV = NFL_TK.rsplit("-", 1)[0]
STATE["A"].KICKOFF[EV] = "2026-11-20T18:00:00Z"
g = game(NFL_TK, want_state="live")
want = _dt.datetime(2026, 11, 20, 18, 0, tzinfo=_dt.timezone.utc).timestamp()
ok("start: the answer carries the sportsbook kickoff as epoch seconds", g.get("start") == want, g.get("start"))
STATE["A"].KICKOFF.pop(EV, None)
STATE["A"].GAME_EXP[EV] = "2026-11-20T23:00:00Z"            # only a settle-time estimate is known now
g = game(NFL_TK, want_state="live")
ok("start: a settle-time estimate is never offered as the start (the page falls back to the first in-play sample)", g.get("start") is None, g.get("start"))
ok("start: the rest of the answer is intact", (g.get("leg") or {}).get("state") == "live" and "story" in g, list(g))
