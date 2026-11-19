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
threading.Thread(target=W.webapp_main, daemon=True).start(); time.sleep(3)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
VW, VH = int(os.environ.get("VW", 1440)), int(os.environ.get("VH", 900)); TAG = os.environ.get("TAG", "d")
def cb(i,g,cost,pays,back,full,sp,wk): return {"t":f"C{i}","label":f"Combo {i}","group":g,"cost":cost,"pays":pays,"back":back,"full":full,"sports":[sp],"legs":[{"ticker":"X","name":"Zverev","res":"yes","state":None,"sport":sp}],"preview":"","week":wk,"sort":i,"p":0,"live":False,"verdict":"hold"}
CS=[cb(1,"cashed",3.15,0,4.43,19,"tennis","2026-11-18"),cb(8,"lost",5,16,0,16,"nba","2026-11-17"),cb(22,"lost",4.46,8333,0,8333,"nfl","2026-11-16"),cb(21,"cashed",15,0,99,400,"nfl","2026-11-16"),cb(2,"cashed",3.01,0,.19,12,"nhl","2026-11-15"),cb(9,"won",5,14,0,14,"nba","2026-11-14")]
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for W,H,tag in ((1280,900,"desk"),(390,844,"phone")):
        pg = br.new_page(viewport={"width": W, "height": H}, device_scale_factor=2, color_scheme="dark")
        errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(B + "/app"); time.sleep(3); pg.evaluate("go('live')"); time.sleep(4); pg.evaluate("window.load=async()=>{}")
        pg.evaluate("localStorage.removeItem('cw_sf');S.sf={o:'all',sp:'all',sort:'new'};S.live={at:Date.now()/1000,combos:"+json.dumps(CS)+",riding:0,staked:0,chance_one:0,best:0,cash_now:0,today:{},auto_sell:true,singles:[],pulse:[]};S.filter='done';renderLive()"); time.sleep(1)
        t = pg.locator(".tbl").inner_text()
        print(tag, "pills:", [x for x in ("+$1.28","−$5","+$84","−$2.82","+$9.00") if x in t], "| net:", pg.locator(".snet").inner_text())
        if "+$1.28" not in t or "−$5" not in t or "+$84" not in t: print("PROBLEMS: settled rows don't show profit/loss")
        pg.locator(".sbar .chip").filter(has_text=re.compile("^Loss$")).click(); time.sleep(.4)
        n = pg.locator(".tbl .trow").count(); print(tag, "loss filter rows:", n)
        if n != 3: print("PROBLEMS: loss filter wrong")
        pg.locator(".sbar .chip").filter(has_text=re.compile("^All$")).click(); pg.locator(".sbar .chip", has_text="Biggest profit").click(); time.sleep(.4)
        first = pg.locator(".tbl .trow .name b").first.inner_text(); print(tag, "biggest profit first:", first)
        if "Combo 21" not in first: print("PROBLEMS: sort wrong")
        pg.locator(".sbar .chip", has_text="Newest").click(); time.sleep(.3)
        pg.screenshot(path=f"settled_{tag}.png"); print("errs:", errs)
