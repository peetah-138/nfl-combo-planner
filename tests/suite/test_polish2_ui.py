# CHECK: group=page secs=40
"""UI polish batch 2 (display only; issues #436 #454 #455 #437 #440 #281). At phone size, dark and light, fixtures only:
Pass / Buying / Try again / Copy code / Done buttons are 44px tall; a Buying... button says it is busy and its spinner is
hidden from screen readers; the one-time code sheet is a labelled modal dialog; a cash-out wait reads
"about 41 min from now" (not game time); range sliders let a vertical swipe scroll the page. Screenshots go to SHOTS."""
import sys, os, time, threading, json, re
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
SHOTS = os.environ.get("SHOTS") or ""
from playwright.sync_api import sync_playwright
problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        try:
            if pg.evaluate(js): return True
        except Exception:
            pass
        time.sleep(.2)
    return False
def shot(pg, name):
    if SHOTS:
        pg.screenshot(path=os.path.join(SHOTS, name))

FAKE = "fake-code-for-the-screenshot-0123456789ab"
ITEM = {"id": "single:KXNBAGAME-26NOV22AAABBB-AAA", "kind": "single", "code": "nba", "icon": "🏀", "league": "NBA", "game": "Aces vs Bees",
        "pick": "Aces to beat Bees", "ticker": "KXNBAGAME-26NOV22AAABBB-AAA", "i": None, "kick": time.time() + 7200, "price": .5, "fair": .58,
        "chance": .58, "edge": .0585, "stake": 12.0, "ev": 1.84, "route": "sell", "p_exit": .62, "win": .58, "exit_mins": 41.0,
        "exposure": None, "legs": []}
def build(route):
    r = route.fetch()
    try:
        d = r.json(); d["best"] = {"items": [ITEM], "why": None, "looked": {"single": 1}}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(d))
    except Exception:
        route.continue_()
def mac(route):
    body = json.loads(route.request.post_data or "{}")
    if body.get("a") == "logaccess":
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"ok": True, "msg": "x", "token": FAKE, "url": "http://100.64.0.1:8765", "logs": {"on": True, "at": int(time.time()), "read": None}}))
    route.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"ok": True, "up": 5000, "engine": "v", "watcher": "v", "ts": "100.64.0.1", "role": "main", "pass": "x",
         "auto_update": True, "https": {"state": "no-daemon"}, "log": [], "logs": {"on": False}}))

DEMO = """(()=>{const old=document.getElementById('p2demo');if(old)old.remove();const d=document.createElement('div');d.id='p2demo';
 d.style.cssText='position:fixed;inset:70px 12px auto 12px;z-index:60;background:var(--bg);padding:10px;border-radius:14px;border:1px solid var(--line)';
 const x={id:'i1',n:1},q={};S.ibuy={};
 d.innerHTML='<div class="dcard" style="margin:0 0 10px"><b>Buy idea buttons (ready)</b><div id="a">'+ideaButtons(x,q,true,12,false)+'</div></div>'
  +'<div class="dcard" style="margin:0 0 10px"><b>Buy idea buttons (Buying...)</b><div id="b">'+(S.ibuy.i1=1,ideaButtons(x,q,false,0,false))+'</div></div>'
  +'<div id="c">'+errCard('live')+'</div><div class="srow" id="d"><div class="l"><b>Secure address</b><small>Try again row</small></div><button class="btn">Try again</button></div>';
 document.body.appendChild(d);})()"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, has_touch=True, device_scale_factor=2)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__haps=[];localStorage.clear();localStorage.setItem('cw_view','build');localStorage.setItem('cw_lg','nba');localStorage.setItem('cw_pview','nba')")
        pg.route(re.compile(r".*/app/api/build\?.*"), build)
        pg.route("**/app", lambda route: (lambda r: route.fulfill(response=r, body=r.text().replace("LOCAL=false", "LOCAL=true")))(route.fetch()))
        pg.route("**/app/mac", mac)
        pg.goto(B + "/app")
        if not wait(pg, "S.build&&S.build.best&&document.querySelector('#main .bfrow')", 40):
            bad(f"{scheme}: best bets didn't render"); ctx.close(); continue
        time.sleep(.8)
        t = pg.evaluate("document.querySelector('#main .bfrow').innerText")
        if "about 41 min from now" not in t: bad(f"{scheme}: the cash-out wait should read 'about 41 min from now': {t[:200]!r}")
        if "41 min in" in t: bad(f"{scheme}: old 'min in' wording is back")
        pg.evaluate("document.querySelector('#main .bfrow').scrollIntoView({block:'center'})"); time.sleep(.4)
        shot(pg, f"best_bets_wording_{scheme}.png")
        # 44px tap targets on the real button markup
        pg.evaluate(DEMO); time.sleep(.5)
        hs = pg.evaluate("[...document.querySelectorAll('#p2demo .btn')].map(b=>[b.innerText.trim(),Math.round(b.getBoundingClientRect().height)])")
        for name, h in hs:
            if h < 44: bad(f"{scheme}: {name!r} button is {h}px tall (want 44+)")
        if len(hs) < 6: bad(f"{scheme}: expected 6+ demo buttons, got {hs}")
        if not pg.evaluate("!!document.querySelector('#b button[aria-busy=\"true\"]')"): bad(f"{scheme}: the Buying... button should say aria-busy")
        if pg.evaluate("[...document.querySelectorAll('.spin')].some(s=>s.getAttribute('aria-hidden')!=='true')"): bad(f"{scheme}: a spinner is readable by screen readers")
        shot(pg, f"tap_targets_{scheme}.png")
        pg.evaluate("document.getElementById('p2demo').remove()")
        # the one-time code sheet: dialog role, a name, 44px buttons
        pg.evaluate("go('settings')")
        row = pg.locator("#logrow")
        if not wait(pg, "!!document.querySelector('#logrow')", 20): bad(f"{scheme}: no log row"); ctx.close(); continue
        shot_row = None
        pg.locator("#logrow input").click(); time.sleep(1.4)
        if not pg.locator("#lc").count(): bad(f"{scheme}: no code sheet")
        else:
            role = pg.evaluate("[document.getElementById('sheet').getAttribute('role'),document.getElementById('sheet').getAttribute('aria-modal'),document.getElementById('sheet').getAttribute('aria-label')]")
            if role != ["dialog", "true", "Code for the dev Mac"]: bad(f"{scheme}: the sheet should be a labelled modal dialog: {role}")
            txt = pg.evaluate("document.getElementById('sheet').innerText")
            if "nfl-combo-logs-token" not in txt: bad(f"{scheme}: the code sheet lost its keychain name: {txt[:300]!r}")
            for h in pg.evaluate("[...document.querySelectorAll('#sheet .btn')].map(b=>Math.round(b.getBoundingClientRect().height))"):
                if h < 44: bad(f"{scheme}: a code sheet button is {h}px tall")
            shot(pg, f"code_sheet_{scheme}.png")
            pg.locator("button", has_text="Done").click(); time.sleep(1.2)
        # Settings: sliders let a vertical swipe scroll the page
        ta = pg.evaluate("[...document.querySelectorAll('input[type=range]')].map(i=>getComputedStyle(i).touchAction)")
        if ta and any(x != "pan-y" for x in ta): bad(f"{scheme}: range sliders should be touch-action pan-y: {set(ta)}")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{scheme}: sideways scroll on Settings")
        pg.evaluate("window.scrollTo(0,0)"); time.sleep(.3)
        shot(pg, f"settings_{scheme}.png")
        if errs: bad(f"{scheme}: JS errors {errs[:3]}")
        ctx.close()
    br.close()
print("PROBLEMS" if problems else "ALL OK", len(problems))
sys.exit(1 if problems else 0)
