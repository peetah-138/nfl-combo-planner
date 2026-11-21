# CHECK: group=page secs=46
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
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": VW, "height": VH}, device_scale_factor=2, color_scheme="dark")
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    def app(route):
        r = route.fetch(); route.fulfill(response=r, body=r.text().replace("LOCAL=false", "LOCAL=true"))
    pg.route("**/app", app)
    pg.route("**/app/mac", lambda route: route.fulfill(content_type="application/json", body=json.dumps(
        {"ok": True, "watcher": "2026.11.17.70", "engine": "2026.11.17.70", "up": 7400, "ts": "100.117.29.11", "pass": "552441",
         "role": "main", "paused": False, "approved": "2026.11.17.70", "log": ["12:00 Kalshi OK: 3 live combos", "12:05 shadow pass: 2 quotes"]})))
    pg.goto(B + "/app"); time.sleep(3)
    pg.evaluate("go('settings')"); time.sleep(4)
    pg.screenshot(path=f"set_{TAG}.png", full_page=True)
    print("text:", pg.evaluate("document.querySelector('main').innerText")[:300].replace("\n", " | "))
    print("before:", pg.evaluate("JSON.stringify([S.set.values.size_auto,S.set.values.safer_count,S.set.lg])")); pg.locator(".tg").nth(0).click(); time.sleep(1.5)
    print("saved label:", pg.evaluate("document.getElementById('saved').innerText"))
    pg.evaluate("bump('safer_count',1,0,10)"); time.sleep(1.5)
    print("after save GET:", json.dumps({k: v for k, v in __import__('requests').get(B + "/app/api/settings?lg=nba", headers={"X-CW": "x"}).json().get("values", {}).items() if k in ("size_auto", "safer_count")}))
    pg.evaluate("sport('nhl')"); time.sleep(30)
    print("main:", pg.evaluate("document.querySelector('main').innerText.slice(0,160)"), pg.evaluate("JSON.stringify(S.set ? S.set.lg : null)"))
    print("nhl:", pg.evaluate("(document.querySelector('.chip.on')||{}).innerText"))
    print("JS errors:", errs[:3])
    br.close()
