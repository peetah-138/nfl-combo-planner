"""Slice 1 of the live game page (issue #72): the football field strip, situation line, last play and the
enhanced scoreboard on the pushed game-detail page. Display only. The game answer (with its ESPN-derived
`detail` block) is scripted; nothing real is touched. Phone (390x844) and desktop: no JS errors, no sideways
scroll on the phone, the strip (ball marker, first-down line, possession), the situation line, the last play
and the scoreboard all render."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
bets = []


def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: (bets, 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    return A


W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); time.sleep(3)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright

TK = "KXNFLGAME-26NOV20INDHOU-IND"


def game(ball_ytz, down, dist, lastplay, lasttype, possAbbr, me=3, opp=0, clock="Q1 6:50", chance=.24, redzone=False):
    """A live NFL game answer with the slice-1 detail block (scoreboard + situation + current drive)."""
    return {"leg": {"ticker": TK, "t": TK, "sport": "nfl", "state": "live", "phase": "on", "on": True,
                    "name": "Colts", "opp": "Texans", "kind": "win", "chance": chance, "live": chance, "side": "yes",
                    "sc": {"abbr": "IND", "opp_abbr": "HOU", "me": me, "opp": opp, "detail": clock}},
            "combos": [], "story": {"ticks": [{"ts": time.time() - 60 * i, "chance": chance} for i in range(4)], "plays": []},
            "whatif": None,
            "detail": {
                "situation": {"down": down, "distance": dist, "yardLine": 100 - ball_ytz, "isRedZone": redzone,
                              "homeTimeouts": 3, "awayTimeouts": 2, "myTimeouts": 2, "theirTimeouts": 3,
                              "possession": True, "downDistanceText": f"{down} & {dist}", "possessionText": f"{possAbbr} {100 - ball_ytz}",
                              "lastPlayText": lastplay, "lastPlayType": lasttype},
                "board": {"home": {"abbr": "HOU", "name": "Houston Texans", "color": "#03202f", "alt": "#a71930", "score": opp, "record": "7-3", "homeAway": "home"},
                          "away": {"abbr": "IND", "name": "Indianapolis Colts", "color": "#002c5f", "alt": "#a2aaad", "score": me, "record": "3-7", "homeAway": "away"},
                          "period": 1, "displayClock": "6:50", "state": "in", "completed": False, "broadcast": "CBS"},
                "drive": {"teamId": "11", "teamAbbr": possAbbr, "ballYardsToEndzone": ball_ytz, "downDistanceText": f"{down} & {dist}"}},
            "fresh": {"now": time.time(), "built": time.time() - 2, "scores": 3, "fast": True}}


state = {"g": game(73, "1st", "10", "C.Stroud pass intended for N.Collins INTERCEPTED by A.Smith at IND 40.", "Interception", "IND")}


def answer(route):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(state["g"]))


def until(pg, js, secs=12):
    end = time.time() + secs
    while time.time() < end:
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        time.sleep(.15)
    return False


def run(pg, label, phone):
    probs = []
    pg.route("**/app/api/game*", answer)
    pg.goto(B + "/app"); time.sleep(.6)
    pg.evaluate(f"openGame('{TK}')")
    if not until(pg, "!!document.querySelector('#sheet .board2')"):
        probs.append(label + ": game sheet didn't draw"); return probs
    if not until(pg, "!!document.querySelector('#sheet .fstrip .fld')"):
        probs.append(label + ": field strip didn't render")
    # the field: a ball marker, a yellow first-down line, a possession arrow, and the yard ruler
    if not pg.evaluate("!!document.querySelector('#sheet .fstrip .fball')"):
        probs.append(label + ": no ball marker")
    if not pg.evaluate("!!document.querySelector('#sheet .fstrip .fdline')"):
        probs.append(label + ": no first-down line")
    if not pg.evaluate("!!document.querySelector('#sheet .fstrip .fdir')"):
        probs.append(label + ": no possession arrow")
    rn = pg.evaluate("[...document.querySelectorAll('#sheet .fstrip .ruler span')].map(e=>e.textContent).join(' ')")
    if "50" not in rn or rn.split(" ")[0] != "G":
        probs.append(label + ": yard ruler wrong: " + repr(rn))
    # the situation line: down & distance, ball spot, who has it; and the last play with its type
    situ = pg.evaluate("(document.querySelector('#sheet .fstrip .situ')||{}).innerText||''")
    if "1st & 10" not in situ or "IND" not in situ:
        probs.append(label + ": situation line wrong: " + repr(situ))
    lp = pg.evaluate("(document.querySelector('#sheet .fstrip .lastplay')||{}).innerText||''")
    if "INTERCEPTED" not in lp or "interception" not in lp.lower():     # type is styled uppercase via CSS
        probs.append(label + ": last play wrong: " + repr(lp))
    # the scoreboard: scores, a live dot, possession football, timeout dots
    sc = pg.evaluate("[...document.querySelectorAll('#sheet .board2 .tm2 b')].map(e=>e.textContent).join('-')")
    if sc != "3-0":
        probs.append(label + ": scoreboard score wrong: " + repr(sc))
    if not pg.evaluate("!!document.querySelector('#sheet .board2 .live-dot')"):
        probs.append(label + ": no live dot")
    if not pg.evaluate("!!document.querySelector('#sheet .board2 .poss')"):
        probs.append(label + ": no possession indicator")
    if not pg.evaluate("[...document.querySelectorAll('#sheet .board2 .tdots i.on')].length>=2"):
        probs.append(label + ": timeout dots missing")
    # the ball slides when the play changes (a new line of scrimmage): position moves
    x0 = pg.evaluate("parseFloat(document.querySelector('#sheet .fstrip .fball').style.left)")
    state["g"] = game(45, "2nd", "3", "A.Smith return to IND 40. 2nd & 3.", "Rush", "IND", redzone=False)
    pg.evaluate("S.gameSig=null;drawGame()")
    if not until(pg, "Math.abs(parseFloat(document.querySelector('#sheet .fstrip .fball').style.left)-%s)>1" % x0, 5):
        probs.append(label + ": ball didn't move to the new line of scrimmage")
    # red zone shading appears inside the 20
    state["g"] = game(12, "1st", "goal", "C.Stroud scramble to HOU 12.", "Rush", "IND", redzone=True)
    pg.evaluate("S.gameSig=null;drawGame()")
    if not until(pg, "!!document.querySelector('#sheet .fstrip .frz')", 5):
        probs.append(label + ": no red-zone shading inside the 20")
    if phone and pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
        probs.append(label + ": page scrolls sideways")
    pg.screenshot(path="fieldstrip_%s.png" % label)
    pg.evaluate("closeModal()")
    state["g"] = game(73, "1st", "10", "C.Stroud pass intended for N.Collins INTERCEPTED by A.Smith at IND 40.", "Interception", "IND")
    return probs


with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []
    probs = []
    pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    pg.on("pageerror", lambda e: errs.append(str(e)))
    probs += run(pg, "phone", True)
    pg.close()
    pg = br.new_page(viewport={"width": 1280, "height": 900}, color_scheme="dark")
    pg.on("pageerror", lambda e: errs.append(str(e)))
    probs += run(pg, "desktop", False)
    pg.close()
    print("errs:", errs)
    if errs:
        probs.append("JS errors")
    if probs:
        print("PROBLEMS:", probs)
    br.close()
