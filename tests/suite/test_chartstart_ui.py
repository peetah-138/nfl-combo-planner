# CHECK: group=page secs=40
"""The game page's 'Chance to win' chart starts at kickoff (issue #486). Display only; the game answer is faked, nothing real is
touched. A synthetic series has four hours of flat PRE-GAME samples before the start, then the game itself. Checks: the x-axis
starts at the game's start time (left label, first point on the axis edge); no pre-game sample is drawn or scrubbable (path size,
scrub spec, and nothing at x < the axis edge); score-change markers sit at the right x; the start falls back to the first in-play
sample and then to the first score change when the Mac sent none; a game that has not started shows 'Kicks off at ...' and no
line; no sideways scroll or JS errors on a phone (390x844, dark and light). Phone screenshots go to CS_SHOTS_DIR when set."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine


def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    return A


W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright

TK = "KXNFLGAME-26NOV20INDHOU-IND"
SHOTS = os.environ.get("CS_SHOTS_DIR")
NOW = time.time()
START = NOW - 50 * 60                                       # kicked off 50 minutes ago
PRE_N, LIVE_N = 120, 30


def series(start, live_state="live"):
    """4 hours of flat pre-game samples ending 30 s before the start, then one sample every 100 s from the start."""
    pre = [{"ts": start - 4 * 3600 + i * (4 * 3600 - 30) / (PRE_N - 1), "chance": .5, "state": "pre"} for i in range(PRE_N)]
    live = [{"ts": start + i * 100, "chance": .5 + .3 * i / (LIVE_N - 1) + (.03 if i % 2 else 0), "state": live_state} for i in range(LIVE_N)]
    return pre, live


PLAYS = [{"ts": START + 120, "me": 0, "opp": 0, "detail": "Start"}, {"ts": START + 900, "me": 7, "opp": 0, "detail": "TD"},
         {"ts": START + 1700, "me": 7, "opp": 7, "detail": "TD"}, {"ts": START + 2500, "me": 10, "opp": 7, "detail": "FG"}]


def game(ticks, plays=PLAYS, start=START, state="live", starts=""):
    return {"leg": {"ticker": TK, "t": TK, "sport": "nfl", "state": state, "phase": "on" if state == "live" else "", "on": state == "live",
                    "name": "Colts", "opp": "Texans", "kind": "win", "chance": .8, "live": .8, "side": "yes", "starts": starts,
                    "sc": {"abbr": "IND", "opp_abbr": "HOU", "me": 10, "opp": 7, "detail": "Q3 4:10"} if state == "live" else None},
            "combos": [], "story": {"ticks": ticks, "plays": plays}, "whatif": None, "detail": None, "start": start,
            "fresh": {"now": time.time(), "built": time.time() - 2, "scores": 3, "fast": True}}


STATE = {"g": None}
pre, live = series(START)
SERIES = pre + live


def answer(route):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(STATE["g"]))


def open_game(pg):
    pg.goto(B + "/app"); time.sleep(.6)
    pg.evaluate(f"openGame('{TK}')")
    end = time.time() + 10
    while time.time() < end:
        if pg.evaluate("!!document.querySelector('#sheet .board2')"):
            return True
        time.sleep(.1)
    return False


READ = """(()=>{const sc=document.querySelector('#sheet .scrub');if(!sc)return {none:true,text:(document.querySelector('#sheet .chartbox')||{}).textContent};
 const svg=sc.querySelector('svg'),vb=svg.viewBox.baseVal,W=vb.width;const tx=[...svg.querySelectorAll('text')].map(t=>t.textContent);
 const paths=[...svg.querySelectorAll('path')];const d=paths[paths.length-1].getAttribute('d');
 const pts=[...d.matchAll(/[ML]([\\d.]+) ([\\d.]+)/g)].map(m=>[+m[1],+m[2]]);
 const marks=[...svg.querySelectorAll('line[stroke-width="1"]')].map(l=>+l.getAttribute('x1'));
 return {W,left:tx[tx.length-2],right:tx[tx.length-1],pts,marks,n:S.scr.win.n,lab0:S.scr.win.lab(0),at0:S.scr.win.at(0),at1:S.scr.win.at(.9999),
  side:document.documentElement.scrollWidth-innerWidth};})()"""


def read(pg, t_start):
    r = pg.evaluate(READ)
    if not r.get("none"):
        r["want_left"] = pg.evaluate("t=>new Date(t*1000).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})", t_start)
    return r


def run(pg, label):
    probs = []
    pg.route("**/app/api/game*", answer)
    # ---- 1. start known: axis starts at kickoff, the pre-game stretch is gone
    STATE["g"] = game(SERIES)
    if not open_game(pg):
        return [label + ": game sheet didn't draw"]
    r = read(pg, START)
    print(label, "start known:", {k: r.get(k) for k in ("left", "want_left", "n", "lab0")}, "points drawn:", len(r.get("pts") or []))
    if r.get("none"):
        return [label + ": no chart"]
    if r["left"] != r["want_left"]:
        probs.append(f"{label}: axis starts at {r['left']}, not the game start {r['want_left']}")
    if len(r["pts"]) != LIVE_N or r["n"] != LIVE_N:
        probs.append(f"{label}: drew {len(r['pts'])} points and scrubs {r['n']}, wanted only the {LIVE_N} in-game samples (the {PRE_N} pre-game ones must not be drawn)")
    if not (35 <= r["pts"][0][0] <= 37.5):
        probs.append(f"{label}: the line should start at the axis edge (x=36), got {r['pts'][0][0]}")
    if min(x for x, _ in r["pts"]) < 35.5:
        probs.append(label + ": something is drawn left of the axis")
    if r["at0"] != 0 or r["lab0"].split(" · ")[0] != r["want_left"]:
        probs.append(f"{label}: looking back to the far left should land on the kickoff sample, got {r['at0']} / {r['lab0']}")
    # markers: the first play is the baseline (not drawn); the others at their time on the same scale as the line
    t1 = SERIES[-1]["ts"]
    iw = r["W"] - 36 - 8
    want = [36 + (p["ts"] - START) / (t1 - START) * iw for p in PLAYS[1:]]
    if len(r["marks"]) != 3 or any(abs(a - b) > 1 for a, b in zip(r["marks"], want)):
        probs.append(f"{label}: score markers {r['marks']} should sit at {[round(x, 1) for x in want]}")
    if r["side"] > 1:
        probs.append(f"{label}: sideways scroll {r['side']}px")
    if SHOTS:
        pg.evaluate("document.querySelector('#sheet .chartbox').scrollIntoView({block:'center'})"); time.sleep(.9)
        pg.screenshot(path=os.path.join(SHOTS, f"chart-start-{label}.png"))
    # ---- 2. no start from the Mac: first in-play sample
    STATE["g"] = game(SERIES, start=None)
    pg.evaluate("S.gameSig=null;drawGame()"); time.sleep(.8)
    r = read(pg, live[0]["ts"])
    if r.get("none") or r["left"] != r["want_left"] or len(r["pts"]) != LIVE_N:
        probs.append(f"{label}: with no start the axis should begin at the first in-play sample: {r.get('left')} vs {r.get('want_left')}, {len(r.get('pts') or [])} points")
    # ---- 3. no start and no in-play marking: the first score change
    unmarked = [dict(x, state=None) for x in live]
    STATE["g"] = game(unmarked, start=None)
    pg.evaluate("S.gameSig=null;drawGame()"); time.sleep(.8)
    r = read(pg, PLAYS[0]["ts"])
    if r.get("none") or r["left"] != r["want_left"]:
        probs.append(f"{label}: with no start and no in-play samples the axis should begin at the first score change: {r.get('left')} vs {r.get('want_left')}")
    elif len(r["pts"]) != LIVE_N - 2:     # the samples at 0 s and 100 s are before the first score change (120 s)
        probs.append(f"{label}: expected {LIVE_N - 2} points after the first score change, got {len(r['pts'])}")
    # ---- 4. not started: a note, no line
    fut = NOW + 3 * 3600
    STATE["g"] = game(pre, plays=[], start=fut, state="pre")
    pg.evaluate("S.gameSig=null;drawGame()"); time.sleep(.8)
    r = pg.evaluate("({svg:!!document.querySelector('#sheet .chartbox svg'),t:document.querySelector('#sheet .chartbox').textContent})")
    want_t = pg.evaluate("t=>new Date(t*1000).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})", fut)
    if r["svg"] or "Kicks off at " + want_t not in r["t"]:
        probs.append(f"{label}: a game that has not started should say 'Kicks off at {want_t}' with no line: {r}")
    STATE["g"] = game(pre, plays=[], start=None, state="pre", starts="Today 7:30 PM")
    pg.evaluate("S.gameSig=null;drawGame()"); time.sleep(.8)
    r = pg.evaluate("({svg:!!document.querySelector('#sheet .chartbox svg'),t:document.querySelector('#sheet .chartbox').textContent})")
    if r["svg"] or "Starts Today 7:30 PM" not in r["t"]:
        probs.append(f"{label}: an unstarted game of unknown start should show its 'starts' label with no line: {r}")
    if SHOTS:
        pg.screenshot(path=os.path.join(SHOTS, f"chart-start-{label}-notstarted.png"))
    pg.unroute("**/app/api/game*")
    return probs


with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, probs = [], []
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
    for scheme in ("dark", "light"):
        pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=scheme)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        probs += run(pg, scheme)
        pg.close()
    print("errs:", errs)
    if errs:
        probs.append("JS errors")
    if probs:
        print("PROBLEMS:", probs)
    else:
        print("PASS chart starts at kickoff")
    br.close()
