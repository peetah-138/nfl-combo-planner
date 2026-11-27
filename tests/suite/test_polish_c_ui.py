# CHECK: group=page secs=40
"""Polish C (display only; issues #542 #545). At phone size, dark and light, fixtures only: the real-offer-ask Settings text names
every sale the switch covers (lock-in and the guarded stop-loss included); the inline error box fades in once and a repaint
rebuilds it already settled; on an iPhone an error buzz that came after an await is owed to the next real tap."""
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


with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, has_touch=True, device_scale_factor=2,
                             user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148")
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__haps=[];localStorage.clear();localStorage.setItem('cw_view','build');localStorage.setItem('cw_lg','nba');localStorage.setItem('cw_pview','nba')")
        pg.route("**/app", lambda route: (lambda r: route.fulfill(response=r, body=r.text().replace("LOCAL=false", "LOCAL=true")))(route.fetch()))
        pg.goto(B + "/app")
        if not wait(pg, "typeof btnFail==='function'&&typeof hapOwed==='function'&&document.querySelector('#main')", 40):
            bad(f"{scheme}: app didn't load"); ctx.close(); continue
        time.sleep(.8)
        # #542: wording
        full = pg.evaluate("fetch('/app').then(r=>r.text())")
        full = full if isinstance(full, str) else ""
        m = re.search(r"Off: automatic selling never asks Kalshi for an offer[^']*", full)
        if not m or "guarded stop-loss" not in m.group(0) or "lock-in" not in m.group(0):
            bad(f"{scheme}: the Off text should name lock-in and the guarded stop-loss: {m and m.group(0)[:160]}")
        # #545: berr fades once
        pg.evaluate("(()=>{const d=document.createElement('div');d.id='bhost';d.style.cssText='margin:120px 12px 0';const b=document.createElement('button');b.className='btn yes';b.id='bb';b.textContent='Buy';d.appendChild(b);document.getElementById('main').prepend(d);})()")
        pg.evaluate("btnFail('#bhost','The price moved. Nothing was bought.',document.getElementById('bb'))")
        a1 = pg.evaluate("getComputedStyle(document.querySelector('.berr')).animationName")
        if a1 != "fadein": bad(f"{scheme}: the first error box should fade in: {a1}")
        time.sleep(.4)
        pg.evaluate("paintErr()")
        a2 = pg.evaluate("[getComputedStyle(document.querySelector('.berr')).animationName,document.querySelectorAll('.berr').length]")
        if a2 != ["none", 1]: bad(f"{scheme}: a repainted error box should stay still: {a2}")
        shot(pg, f"error_box_{scheme}.png")
        pg.evaluate("btnFail('#bhost','A new try failed too.',document.getElementById('bb'))")
        if pg.evaluate("getComputedStyle(document.querySelector('.berr')).animationName") != "fadein": bad(f"{scheme}: a new failure should fade in again")
        # #545: error buzz owed to the next tap on iPhone
        pg.evaluate("window.__haps=[];S.tapAt=-1e9;hap('error')")
        pg.evaluate("window.__haps.length=0")
        pg.click("#bb")
        time.sleep(.3)
        h = pg.evaluate("window.__haps")
        if "error" not in h: bad(f"{scheme}: the error buzz owed from after an await should play on the next tap: {h}")
        pg.evaluate("window.__haps=[]")
        pg.click("#bb"); time.sleep(.2)
        if "error" in pg.evaluate("window.__haps"): bad(f"{scheme}: an owed buzz should play only once")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{scheme}: sideways scroll")
        if errs: bad(f"{scheme}: JS errors {errs[:3]}")
        ctx.close()
    br.close()
print("PROBLEMS" if problems else "ALL OK", len(problems))
sys.exit(1 if problems else 0)
