import sys, os, time, threading, re, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
tk_ev = sorted({m["event_ticker"] for m in mk})
def L(i, team): ev = tk_ev[i]; return {"ticker": f"{ev}-{team}", "event_ticker": ev, "event": ev, "side": "yes"}
bets = [
 {"ticker": "KXMVE-1", "legs": [L(0, "BOS"), L(1, "DEN"), L(2, "MIL")], "cost": 5.0, "pays": 41.2, "status": "pending", "back": 0, "week": "2026-11-17", "full_pays": 41.2, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-2", "legs": [L(0, "NYK"), L(3, "GSW"), L(1, "LAL"), L(2, "CHI")], "cost": 4.93, "pays": 980, "status": "pending", "back": 0, "week": "2026-11-17", "full_pays": 980, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-3", "legs": [L(3, "PHX"), L(1, "DEN")], "cost": 8.0, "pays": 19.5, "status": "pending", "back": 0, "week": "2026-11-17", "full_pays": 19.5, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-4", "legs": [L(0, "BOS"), L(2, "CHI")], "cost": 5.0, "pays": 22, "status": "lost", "back": 0, "week": "2026-11-12", "full_pays": 22, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-5", "legs": [L(0, "BOS"), L(1, "DEN")], "cost": 5.0, "pays": 14, "status": "won", "back": 0, "week": "2026-11-10", "full_pays": 14, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-6", "legs": [L(3, "PHX"), L(2, "MIL")], "cost": 6.0, "pays": 30, "status": "cashed", "back": 11.4, "week": "2026-11-05", "full_pays": 30, "lg": "nba", "lgs": ["nba"]}]
def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: (bets, 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    A.MINE["cash"]["KXMVE-3"] = {"rfq": "r", "quote": "q", "offer": 15.8, "price": .81, "contracts": 19.5, "frac": 1.0, "at": time.time() + 3600}
    A.MINE["cash"]["KXMVE-1"] = {"rfq": "estimate", "offer": 9.1, "frac": 1.0, "at": time.time()}
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
VW, VH = int(os.environ.get("VW", 1440)), int(os.environ.get("VH", 900)); TAG = os.environ.get("TAG", "d")
SING=[{"t":"KXNFLSPREAD-26NOV22BUFKC-KC7","kind":"spread","sport":"nfl","side":"yes","label":"Kansas City wins by over 6.5 points","game":"Buffalo at Kansas City: Spread","event":"KXNFLSPREAD-26NOV22BUFKC","n":10,"cost":5.2,"pays":10,"worth":7.0,"chance":0.72,"state":"live","res":None,"score":"KC 24-14 BUF Q3 4:12","starts":"","how":"Covering now · +10, needs more than 6.5","url":"","own":False,"self":False,"sell_at":8.4},
 {"t":"KXNHLGAME-26NOV18SJSVGK-SJS","kind":"win","sport":"nhl","side":"yes","label":"San Jose to win","game":"San Jose vs Vegas Winner?","event":"KXNHLGAME-26NOV18SJSVGK","n":6,"cost":3,"pays":6,"worth":2.4,"chance":0.42,"state":"pre","res":None,"score":"","starts":"Tonight 7:00 PM","how":"","url":"","own":True,"self":False,"sell_at":None}]
def wait(pg, js, secs=20):           # wait for a state on the page, not a fixed time (slow runners vary a lot)
    t = time.time()
    while time.time() - t < secs:
        try:
            if pg.evaluate(js): return True
        except Exception: pass
        time.sleep(.1)
    return False
# Count the page's own loads; once the first Live load is over, stop the page refreshing itself, so the bets this
# test draws are never replaced by a load that was still in flight (the old flake: a fixed 6 s was sometimes short).
SETTLE = """(()=>{const L=window.load;window.__loads=0;window.__done=0;
  window.load=async(...a)=>{window.__loads++;try{return await L(...a)}finally{window.__loads--;window.__done++}};})()"""
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for W,H,tag in ((390,844,"phone"),(1280,900,"desk")):
        pg = br.new_page(viewport={"width": W, "height": H}, device_scale_factor=2, color_scheme="dark")
        errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
        ACTS=[]
        pg.route("**/app/api/act", lambda r: (ACTS.append(r.request.post_data), r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok":True,"msg":"Got it."}))))
        pg.goto(B + "/app"); pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=30000)
        pg.evaluate(SETTLE); pg.evaluate("go('live')")
        if not wait(pg, "window.__done>0&&window.__loads===0", 60): print("PROBLEMS: Live never finished loading")
        pg.evaluate("window.load=async()=>{}")
        pg.evaluate("(s=>{if(!S.live||S.live.error)S.live={at:Date.now()/1000,combos:[],riding:0,staked:0,chance_one:0,best:0,cash_now:0,today:{}};S.live.singles=s;S.live.auto_sell=true;if(S.live.combos[0])S.live.combos[0].own=true;S.filter='all';renderLive()})("+json.dumps(SING)+")"); wait(pg, "document.querySelectorAll('.srow1').length===2", 5)
        n=pg.locator(".srow1").count(); txt=pg.locator(".stbl").inner_text() if pg.locator(".stbl").count() else ""
        print(tag,"single rows:",n,"| covering shown:","Covering now" in txt,"| tags:", "You, on Kalshi" in txt and "From the app" in txt, "| note:", pg.locator("text=leave them alone").count())
        if n!=2 or "Covering now" not in txt: print("PROBLEMS: singles not shown right")
        pg.evaluate("(s=>{S.live.singles=s;S.live.auto_sell=true;renderLive()})("+json.dumps(SING)+")"); wait(pg, "document.querySelectorAll('.stbl .ss').length===2", 5)
        chips = pg.locator(".stbl .ss"); print(tag, "smart sell chips:", chips.count(), "| first:", chips.first.inner_text())
        if chips.count() != 2 or "Smart sell" not in chips.first.inner_text() or "8.40" not in chips.first.inner_text(): print("PROBLEMS: smart sell chip missing")
        chips.first.click(); wait(pg, "/sell it/.test(document.querySelector('.stbl .ss').innerText)&&!!(document.querySelector('.toast')||{}).innerText", 10)
        t1 = pg.locator(".stbl .ss").first.inner_text(); toast = pg.evaluate("(document.querySelector('.toast')||{}).innerText")
        print(tag, "after tap:", t1, "| toast:", toast)
        if "sell it" not in t1 or not toast: print("PROBLEMS: switching to I'll sell it didn't take")
        pg.locator(".stbl .ss").first.click(); wait(pg, "/Smart sell/.test(document.querySelector('.stbl .ss').innerText)", 10)
        if "Smart sell" not in pg.locator(".stbl .ss").first.inner_text(): print("PROBLEMS: switching back didn't take")
        if pg.locator(".srow1").first.evaluate("e=>e.classList.contains('open')") : pass
        pg.evaluate("(s=>{S.live.singles=s;S.live.auto_sell=true;S.filter='nhl';renderLive()})("+json.dumps(SING)+")"); wait(pg, "document.querySelectorAll('.srow1').length===1", 5)
        nn=pg.locator(".srow1").count(); print("nhl rows:", nn, pg.evaluate("S.filter"), pg.evaluate("(S.live.singles||[]).length"))
        if nn!=1: print("PROBLEMS: sport chip doesn't filter singles")
        pg.evaluate("S.filter='all';renderLive()"); wait(pg, "document.querySelectorAll('.srow1').length===2", 5)
        pg.locator(".stbl").scroll_into_view_if_needed(); pg.screenshot(path=f"singles_{tag}.png")
        ow = pg.evaluate("document.documentElement.scrollWidth>innerWidth+1")
        if ow: print("PROBLEMS: page scrolls sideways")
        pg.route("**/app/api/game?*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"leg":dict(SING[0],live=.72,sc={"me":24,"opp":14,"abbr":"KC","opp_abbr":"BUF","detail":"Q3"}),"combos":[{"t":SING[0]["t"],"label":SING[0]["label"],"p":.72,"pays":10,"cost":5.2,"legs":1,"single":True,"how":"Covering now"}],"story":{"ticks":[],"plays":[]},"whatif":None})))
        pg.evaluate("(s=>{S.live.singles=s;S.filter='all';renderLive()})("+json.dumps(SING)+")"); wait(pg, "document.querySelectorAll('.srow1').length===2", 5)
        pg.locator(".srow1").first.click()
        sheet = ""
        for _ in range(120):                    # wait for the game sheet itself, not a fixed time
            time.sleep(.25)
            sheet = pg.evaluate("(document.querySelector('#sheet')||{}).innerText||''")
            if "your bets on this game" in sheet.lower(): break
        print(tag, "game sheet:", sheet[:120].replace("\n"," | "))
        if "chance it covers" not in sheet.lower() or "your bets on this game" not in sheet.lower(): print("PROBLEMS: tapping a spread doesn't open its game")
        pg.evaluate("closeModal()")
        print("acts:", ACTS[:2]); print("errs:", errs)
        if len(ACTS) < 2 or '"selfsell"' not in ACTS[0]: print("PROBLEMS: the switch didn't reach the Mac")
        if errs: print("PROBLEMS: js errors")
