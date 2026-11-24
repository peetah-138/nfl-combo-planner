# CHECK: group=page secs=8
"""Live: a tied game is never red (GitHub #320, display only). Pete saw "New York Jets 0–0" in red (and the leg row's ring
red) at NYJ 0-0 LAC, Q1 15:00, chance 40%: legCls let the chance (<= 40%) decide a level score. Now a known score decides:
ahead = up (green), behind = down (red), level = tied ('live'); only a leg with no numeric score falls back to the chance.
Checks legCls directly, the combo row's chips, the open combo's leg ring, the legend (Tied, no Losing now) and the Games
card, at phone (390x844, touch) and desktop. Optional SHOT=<path> saves a phone screenshot. Prints PROBLEMS on any failure."""
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
    A.open_singles = lambda: []
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        if pg.evaluate(js): return True
        time.sleep(.2)
    return False

def leg(tk, name, opp, me, them, ch, detail="Q1 15:00", sport="nfl"):
    return {"ticker": tk, "name": name, "opp": opp, "sport": sport, "state": "live", "phase": "", "res": None,
            "sc": {"me": me, "opp": them, "abbr": name[:3].upper(), "opp_abbr": opp[:3].upper(), "detail": detail},
            "score": f"{me}–{them} · {detail}", "chance": ch, "live": ch, "note": "", "short": "", "starts": ""}
LEGS = [leg("KXNFLGAME-26NOV22NYJLAC-NYJ", "New York Jets", "Los Angeles Chargers", 0, 0, .40),   # Pete's case
        leg("KXNFLGAME-26NOV22BUFMIA-BUF", "Buffalo Bills", "Miami Dolphins", 14, 14, .30, "Q3 4:10")]   # level later on, low chance
COMBO = {"t": "KXMVETIED-1", "group": "pending", "cost": 5, "pays": 40, "offer": 3.1, "offer_real": False, "legs": LEGS,
         "sports": ["nfl"], "label": "Combo 2", "p": .12, "live": True, "sort": 0, "verdict": "hold", "self": False}
LIVE = ("(c)=>{S.sf={o:'all',sp:'all',sort:'new'};S.filter='all';S.open={};S.open[c.t]=true;S.live={at:Date.now()/1000,combos:[c],"
        "riding:1,staked:5,chance_one:.12,best:40,cash_now:3.1,today:{},auto_sell:true,singles:[]};S.view='live';renderLive();"
        "const row=document.querySelector('#main .trow[data-key=\"c:'+c.t+'\"]');"
        "return {chips:[...(row?row.querySelectorAll('.legs .leg'):[])].map(e=>({cls:e.className,txt:e.textContent,tip:e.title})),"
        "marks:[...document.querySelectorAll('#main .exp .lrow .mark')].map(e=>e.className),"
        "legend:[...document.querySelectorAll('#main .legend .leg')].map(e=>e.className+'|'+e.textContent)};}")
# [score me, score opp, chance, expected]
CASES = [[0, 0, .40, "live"], [0, 0, .20, "live"], [0, 0, .80, "live"], [14, 14, .30, "live"], [7, 3, .30, "up"], [3, 7, .70, "down"],
         [None, None, .30, "down"], [None, None, .70, "up"], [None, None, .50, "live"], [1, None, .30, "down"]]
UNIT = """(cs)=>cs.map(([me,opp,ch,want])=>{const sc=me===null&&opp===null?null:{me,opp};
  return [legCls({state:'live',phase:'',sc,live:ch}),want];})"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, tag in ((390, 844, "phone"), (1280, 900, "desk")):
        ctx = br.new_context(viewport={"width": vw, "height": vh}, color_scheme="dark", has_touch=(tag == "phone"))
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("localStorage.clear();localStorage.setItem('cw_view','live')")
        pg.goto(B + "/app")
        if not wait(pg, "typeof legCls==='function'&&typeof renderLive==='function'&&!!document.querySelector('#main')", 20): bad(f"{tag}: the page didn't load")
        time.sleep(1)
        for i, (got, want) in enumerate(pg.evaluate(UNIT, CASES)):
            if got != want: bad(f"{tag}: legCls case {CASES[i]} gave {got!r}, want {want!r}")
        # finished / waiting legs are unchanged
        other = pg.evaluate("[legCls({res:'yes'}),legCls({res:'no'}),legCls({state:'pre',sc:{me:0,opp:3},live:.2}),legCls({state:'live',phase:'waiting',sc:{me:0,opp:0},live:.2})]")
        if other != ["won", "lost", "", ""]: bad(f"{tag}: won/lost/pre/waiting legs changed: {other}")
        out = pg.evaluate(LIVE, COMBO)
        chips = out["chips"]
        if len(chips) != 2: bad(f"{tag}: expected 2 leg chips, got {chips}")
        for c in chips:
            if " down" in " " + c["cls"] or "Losing" in c["tip"]: bad(f"{tag}: a tied leg's chip is red/losing: {c}")
            if " live" not in " " + c["cls"] or c["tip"] != "Tied or close": bad(f"{tag}: a tied leg's chip should be the tied colour: {c}")
        if not any("Jets 0–0" in c["txt"] for c in chips): bad(f"{tag}: the Jets chip should still show 0–0: {chips}")
        if len(out["marks"]) != 2 or any("down" in m or "live" not in m for m in out["marks"]): bad(f"{tag}: the open combo's leg rings should be tied, not red: {out['marks']}")
        if any("Losing" in x for x in out["legend"]) or not any("Tied" in x for x in out["legend"]): bad(f"{tag}: legend should list Tied and not Losing now: {out['legend']}")
        # Games tab card for the same tied game is not red either
        gc = pg.evaluate("""(l)=>{S.games={games:[{name:l.name,opp:l.opp,sport:'nfl',ticker:l.ticker,combos:1,pays:40,kind:'win',state:'live',phase:'',
            sc:l.sc,chance:.40,singles:[],spark:[]}],fresh:null};S.view='games';render();const e=document.querySelector('#main .gc');return e?e.className:null;}""", LEGS[0])
        if not gc or "ldown" in gc or "llive" not in gc: bad(f"{tag}: the Games card for a tied game should not be red: {gc}")
        # back to Live for the screenshot
        pg.evaluate(LIVE, COMBO); time.sleep(.9)
        if tag == "phone":
            if pg.evaluate("document.documentElement.scrollWidth>document.documentElement.clientWidth+1"): bad("phone: the page scrolls sideways")
            if os.environ.get("SHOT"):
                pg.evaluate("(()=>{const r=document.querySelector('#main .legend')||document.querySelector('#main .trow');if(r)r.scrollIntoView({block:'start'});})()"); time.sleep(.4)
                pg.screenshot(path=os.environ["SHOT"])
        print(f"{tag}: chips={[c['cls'] for c in chips]} marks={out['marks']} JS errors: {errs}")
        if errs: bad(f"{tag}: JS errors {errs}")
        ctx.close()
    br.close()
print("PROBLEMS: " + " | ".join(problems) if problems else "all tied-leg checks passed")
