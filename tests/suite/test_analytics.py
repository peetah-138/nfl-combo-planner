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
AN={"at":time.time()-120,"levels":[{"band":"80–85%","n":12,"hit":0.2,"exp":0.25,"ride":-0.21,"gt":-0.15,"gt_n":10,"lab_n":3,"lab_ride":-0.4,"lab_smart":0.1},
 {"band":"95–100%","n":44,"hit":0.3,"exp":0.29,"ride":0.03,"gt":None,"gt_n":0,"lab_n":0,"lab_ride":None,"lab_smart":None}],
 "types":[{"mode":"real","what":"Spreads & totals","n":6,"won":4,"pl":3.2,"roi":0.12,"clv":0.02,"smart":0.14,"sim_n":4},{"mode":"paper","what":"Combos","n":9,"won":2,"pl":-8,"roi":-0.18,"clv":None,"smart":-0.05,"sim_n":6}],
 "sports":[{"mode":"real","what":"NHL","n":6,"won":4,"pl":3.2,"roi":0.12,"clv":0.02,"smart":0.1,"sim_n":2}],
 "exits":[{"what":"Rode to the end","n":10,"pl":-12,"roi":-0.2},{"what":"Cashed out early","n":7,"pl":9,"roi":0.25}],"auto":{"smart":3,"lock in":1},"cut_held":{"too early in the game":2,"halftime or a break":1},"hedge_held":{"score feed stale":2,"wouldn't lock in what you paid":1},
 "tuning":[{"key":"nhl","name":"NHL","floor":1.5,"lam":1,"loss":0.15,"n":40,"own":True,"sl_prog":0.5,"sl_drop":0.2,"sl_n":0,"sl_own":False,"sl_why":""}],
 "notes":["Combos priced 95–100% of fair have done best so far: +3% riding to the end over 44 quotes.","Not enough results yet for 80–85% (30+ each before reading much into them)."]}
SING=[{"t":"S1","kind":"spread","sport":"nfl","side":"yes","label":"KC wins by over 6.5","game":"BUF at KC","event":"E","n":10,"cost":5.2,"pays":10,"worth":7.0,"chance":0.72,"state":"live","res":None,"score":"","starts":"","how":"","url":"","own":True,"self":False,"sell_at":8.4}]
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/app/api/analytics", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(AN)))
    pg.goto(B + "/app"); time.sleep(3); pg.evaluate("go('results')"); time.sleep(8)
    print("card:", pg.locator(".an").count(), "| rows:", pg.locator(".an .anrow:not(.h)").count())
    if pg.locator("text=What's working").count() != 1 or pg.locator(".an .anrow:not(.h)").count() != 2: print("PROBLEMS: analytics card missing")
    for tab, want in (("Bet types", "Spreads & totals"), ("Sports", "NHL"), ("Selling", "Cashed out early")):
        pg.locator(".ant button", has_text=tab).click(); time.sleep(.3)
        if pg.locator(".an", has_text=want).count() != 1: print("PROBLEMS: tab", tab, "didn't show", want)
    if pg.locator(".an", has_text="3 smart").count() != 1: print("PROBLEMS: auto-sale counts missing")
    ch = pg.locator(".an .cut-held").inner_text()
    if "2 too early in the game" not in ch or "1 halftime or a break" not in ch: print("PROBLEMS: loss cuts held back by the guards missing:", ch)
    hh = pg.locator(".an .hedge-held").inner_text()
    if "Auto-hedges the guards held back" not in hh or "3" not in hh or "2 score feed stale" not in hh or "fresh live score" not in hh: print("PROBLEMS: auto-hedges held back by the guards missing:", hh)
    sel = pg.locator(".an").inner_text()
    if "late, confirmed" not in sel or "Selling at a loss (a learned cut" not in sel or "after 50% of the game" not in sel:
        print("PROBLEMS: the loss cut's guards aren't shown in Results > Selling")
    pg.locator(".ant button", has_text="Combo price levels").click(); time.sleep(.3)
    pg.locator(".an").scroll_into_view_if_needed(); pg.locator(".an").screenshot(path="an_phone.png")
    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): print("PROBLEMS: Results scrolls sideways on a phone")
    pg.evaluate("go('live')"); time.sleep(6); pg.evaluate("window.load=async()=>{}")
    pg.evaluate("(s=>{S.live={at:Date.now()/1000,combos:[{t:'C',group:'pending',cost:3,pays:19,offer:2.94,offer_real:false,legs:[],sports:['tennis'],label:'Combo 3',p:.17,live:true,sort:0,verdict:'hold'}],riding:1,staked:3,chance_one:.17,best:19,cash_now:2.94,today:{},auto_sell:true,singles:s};renderLive()})("+json.dumps(SING)+")"); time.sleep(1.2)
    k = pg.locator(".kpis").inner_text().replace("\n"," | "); print("kpis:", k)
    if "2 bets" not in k or "$8.20" not in k or "$9.94" not in k or "$29" not in k: print("PROBLEMS: Live top numbers don't include singles")
    print("errs:", errs)
