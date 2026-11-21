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
 {"ticker": "KXMVE-5", "legs": [L(0, "BOS"), L(1, "DEN")], "cost": 5.0, "pays": 14, "status": "won", "back": 14, "week": "2026-11-17", "full_pays": 14, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-6", "legs": [L(3, "PHX"), L(2, "MIL")], "cost": 6.0, "pays": 30, "status": "cashed", "back": 11.4, "week": "2026-11-17", "full_pays": 30, "lg": "nba", "lgs": ["nba"]}]
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
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 430, "height": 932}, device_scale_factor=2, color_scheme="dark", has_touch=True, is_mobile=True)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/app"); time.sleep(6)
    pg.evaluate("go('build')"); time.sleep(9); print("main:", pg.evaluate("document.querySelector('main').innerText")[:300].replace("\n"," | "), pg.evaluate("JSON.stringify(S.build&&[S.build.lg,S.build.board.length])"))
    pg.evaluate("setLg('mix')"); time.sleep(12)
    pg.evaluate("S.adv=true;renderBuild()"); time.sleep(.5)
    print("lg", pg.evaluate("S.lg"), "btns", pg.locator(".pickbtn").count(), "disabled", pg.locator(".pickbtn[disabled]").count())
    for _ in range(40):                       # let the board finish easing in (and any refresh land) before tapping
        time.sleep(.25)
        if pg.locator(".pickbtn").count() >= 3 and not pg.evaluate("!!document.querySelector('.stag')"): break
    time.sleep(.5)
    pg.locator(".pickbtn").nth(0).tap(); time.sleep(.5); pg.locator(".pickbtn").nth(2).tap(); time.sleep(.5)
    print("slip", pg.evaluate("S.slip"), "on:", pg.locator(".pickbtn.on").count())
    print("slip card y", pg.evaluate("document.querySelector('.slip').getBoundingClientRect().top+scrollY"), "page h", pg.evaluate("document.body.scrollHeight"))
    pg.screenshot(path="tap_m.png")
    # issue #61: every leg says its sport, who it plays and (when known) when, one leg per row; flipping still works by tapping the row
    rows = pg.evaluate("[...document.querySelectorAll('.slip .lrow')].map(e=>[e.querySelector('.li').innerText.trim(),e.querySelector('b').innerText,e.querySelector('small').innerText])")
    print("slip rows:", rows)
    if len(rows) != 2 or any(not r[0] or " vs " not in " " + r[2] or "NBA" not in r[2] for r in rows): print("PROBLEMS: slip legs should show icon, matchup and league", rows)
    bar = pg.evaluate("(document.querySelector('.slipbar span')||{}).innerText||''")
    print("slip bar:", bar)
    if "\U0001F3C0" not in bar: print("PROBLEMS: the slip bar should show the sport icon", bar)
    crow = pg.evaluate("[...document.querySelectorAll('.ccard .lrow.flip')].map(e=>[e.querySelector('.li').innerText.trim(),e.querySelector('small').innerText,e.querySelector('.lp').innerText])")
    print("combo idea rows:", crow[:4])
    if not crow or any(not r[0] or "vs" not in r[1] or "NBA" not in r[1] or "%" not in r[2] for r in crow): print("PROBLEMS: combo idea legs should show icon, matchup, league and chance", crow[:4])
    if pg.evaluate("document.documentElement.scrollWidth>window.innerWidth+1||[...document.querySelectorAll('.ccard,.slip')].some(e=>e.scrollWidth>e.clientWidth+1)"): print("PROBLEMS: leg rows overflow sideways")
    if not pg.evaluate("[...document.querySelectorAll('.board .mrow .when .wlg')].length>0"): print("PROBLEMS: board rows should show the league")
    before = pg.evaluate("S.build.combos[0].legs.map(l=>l.pick).join('+')")
    pg.locator(".ccard").nth(0).locator(".lrow.flip").nth(0).scroll_into_view_if_needed(); pg.locator(".ccard").nth(0).locator(".lrow.flip").nth(0).tap(); time.sleep(3)
    # the tap must reach flipLeg: the legs change, or the Mac answers (a flip that would duplicate another idea is refused with a toast)
    if pg.evaluate("S.build.combos[0].legs.map(l=>l.pick).join('+')") == before and not pg.evaluate("!!document.querySelector('.toast')||!!(S.flips&&S.flips[S.build.combos[0].i])"): print("PROBLEMS: tapping a leg row should still flip it")
    t = pg.evaluate("S.build.combos[0].legs[0].ticker"); i = pg.evaluate("S.build.combos[0].i")
    b = pg.evaluate("S.build.combos[0].legs.map(l=>l.pick).join('+')")
    pg.evaluate(f"flipLeg({i},'{t}')"); time.sleep(3)
    print("flip:", b, "->", pg.evaluate("S.build.combos[0].legs.map(l=>l.pick).join('+')"), pg.evaluate("JSON.stringify(S.flips)"))
    print("toast:", pg.evaluate("(document.querySelector('.toast')||{}).innerText"))
    pg.locator(".ccard").nth(0).scroll_into_view_if_needed(); time.sleep(.3); pg.screenshot(path="flip_m.png")
    print("errs:", errs)
