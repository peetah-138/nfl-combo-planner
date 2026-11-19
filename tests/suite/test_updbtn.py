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
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    INFO={"ok":True,"watcher":"2026.11.18.109","engine":"2026.11.18.109","up":1300,"role":"main","paused":False,"auto_update":True,"waiting":"","latest":"2026.11.18.109","checked":time.time()-400}
    pg.route("**/app/mac-info", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(INFO)))
    pg.route("**/app/mac-check", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok":True,"msg":"The Mac is checking now. If there's a newer version, it installs and restarts within about a minute."})))
    pg.goto(B + "/app"); time.sleep(3); pg.evaluate("go('settings')")
    for _ in range(40):
        time.sleep(.5)
        if pg.evaluate("!!(window.S&&S.mac&&S.mac.ok)"): break
    time.sleep(.5)
    print("LOCAL:", pg.evaluate("LOCAL"), "mac:", pg.evaluate("JSON.stringify(S.mac)")[:200])
    btn = pg.locator("button", has_text="Check for an update now")
    print("button:", btn.count())
    if btn.count() != 1: print("PROBLEMS: no update button on the phone's Mac card")
    else:
        btn.scroll_into_view_if_needed(); pg.locator(".scard", has=btn).first.screenshot(path="maccard.png") if pg.locator(".scard", has=btn).count() else None
        btn.click(); time.sleep(3.5)
        t = pg.evaluate("(document.querySelector('.toast')||{}).innerText"); print("toast:", t)
        if not t or "checking" not in t.lower(): print("PROBLEMS: tapping the button did nothing")
    print("errs:", errs)
