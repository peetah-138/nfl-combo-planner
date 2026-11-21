# CHECK: group=page secs=12
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
STATE={"n":0}
def mac(route):
    body=json.loads(route.request.post_data or "{}")
    if body.get("a")=="https":
        STATE["n"]=1; return route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok":True,"msg":"Checking"}))
    h={"state":"no-status","detail":"Couldn't read Tailscale's status: boom"} if STATE["n"]==0 else {"state":"need-enable","link":"https://login.tailscale.com/f/serve?node=abc"}
    route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok":True,"up":100,"engine":"v","watcher":"v","ts":"mac","role":"main","pass":"x","auto_update":True,"https":h,"log":[]}))
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 1280, "height": 900}, color_scheme="dark")
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/app", lambda route: (lambda r: route.fulfill(response=r, body=r.text().replace("LOCAL=false", "LOCAL=true")))(route.fetch()))
    pg.route("**/app/mac", mac)
    pg.goto(B + "/app"); time.sleep(3); pg.evaluate("go('settings')")
    for _ in range(30):
        time.sleep(.5)
        if pg.locator("button", has_text="Try again").count(): break
    b = pg.locator("button", has_text="Try again"); print("try again button:", b.count())
    if not pg.locator("text=Couldn't read Tailscale's status").count() or pg.locator("text=isn't signed in").count(): print("PROBLEMS: a status read failure is not described as what it is")
    if not b.count(): print("PROBLEMS: no secure address row")
    else:
        pg.evaluate("window.__t=[];new MutationObserver(()=>__t.push(document.querySelector('#toast').textContent)).observe(document.querySelector('#toast'),{childList:true,characterData:true,subtree:true})")
        b.first.click(); time.sleep(1); print("while checking:", pg.locator("text=Checking Tailscale").count())
        if not pg.locator("text=Checking Tailscale").count(): print("PROBLEMS: no sign that it's checking")
        for _ in range(30):
            time.sleep(.5)
            if pg.evaluate("(document.querySelector('#toast')||{}).textContent"): break
        t = pg.evaluate("(document.querySelector('#toast')||{}).textContent"); print("toast:", t, pg.evaluate("document.querySelectorAll('.toast').length"))
        print("toasts seen:", pg.evaluate("__t"))
        allow = pg.locator("a", has_text="Allow https").count(); print("allow https link:", allow)
        if not allow or "One step left" not in (t or ""): print("PROBLEMS: the result of the check never showed")
    print("errs:", errs)
