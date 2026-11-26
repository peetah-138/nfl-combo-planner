# CHECK: group=page secs=40
"""Batch E polish (display only; issues #196 #213 #214 #246). At phone size, dark and light, fixtures only: the Change-vs-paid
switch keeps a 44px tap area but its highlight is drawn at text height; the "New version ready" pill sits above sheets, has a
44px dismiss x that stays dismissed, shrinks to a dot after about 20 s, and the reloaded page fades in; Get new price / Sell
(.btn.sm) are 44px; "Price it" opens a folded combo section; a tappable toast is a real button for screen readers."""
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
        ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, has_touch=True, device_scale_factor=2)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__haps=[];localStorage.clear();localStorage.setItem('cw_view','build');localStorage.setItem('cw_lg','nba');localStorage.setItem('cw_pview','nba')")
        pg.route("**/app", lambda route: (lambda r: route.fulfill(response=r, body=r.text().replace("LOCAL=false", "LOCAL=true")))(route.fetch()))
        pg.goto(B + "/app")
        if not wait(pg, "typeof verPill==='function'&&typeof chgBar==='function'&&document.querySelector('#main')", 40):
            bad(f"{scheme}: app didn't load"); ctx.close(); continue
        time.sleep(.8)
        # #196: switch highlight is text-height, hit area stays 44
        pg.evaluate("""(()=>{const d=document.createElement('div');d.id='bedemo';d.style.cssText='position:fixed;top:90px;left:12px;right:12px;z-index:40;background:var(--bg);padding:20px 8px';
         d.innerHTML=chgBar()+'<div style="margin-top:20px"><button class="btn yes sm" id="bsm">Sell</button> <button class="btn ghost sm">Get new price</button></div>';document.body.appendChild(d);})()""")
        time.sleep(.4)
        r = pg.evaluate("(()=>{const b=document.querySelector('#bedemo .chgsw button.on');const h=b.getBoundingClientRect().height;const p=parseFloat(getComputedStyle(b,'::before').height);return [h,p]})()")
        if r[0] < 43.9: bad(f"{scheme}: switch hit area is {r[0]}px (want 44+)")
        if not (20 <= r[1] <= 28): bad(f"{scheme}: switch highlight is {r[1]}px tall (want about 24)")
        for h in pg.evaluate("[...document.querySelectorAll('#bedemo .btn.sm')].map(b=>b.getBoundingClientRect().height)"):
            if h < 43.9: bad(f"{scheme}: a .btn.sm is {h}px tall (want 44+)")
        shot(pg, f"switch_and_buttons_{scheme}.png")
        pg.evaluate("document.getElementById('bedemo').remove()")
        # #246: Price it opens a folded combo section; a tappable toast is a real button
        o = pg.evaluate("(()=>{S.bsec.combos=false;try{feedCombo(0)}catch(e){}return S.bsec.combos})()")
        if o is not True: bad(f"{scheme}: Price it should open the folded combo section: {o}")
        t = pg.evaluate("(()=>{toast('tap me',4000,'',()=>{});const t=document.getElementById('toast');return [t.getAttribute('role'),t.tabIndex]})()")
        if t != ["button", 0]: bad(f"{scheme}: a tappable toast should be role=button: {t}")
        t = pg.evaluate("(()=>{toast('plain',4000);const t=document.getElementById('toast');return [t.getAttribute('role'),t.hasAttribute('tabindex')]})()")
        if t != [None, False]: bad(f"{scheme}: a plain toast should not be a button: {t}")
        pg.evaluate("toastHide()")
        # #214: the pill sits above the sheet; #213: x dismisses, dot after ~20 s, reload fades in
        pg.evaluate("window.verSeen=()=>{};window.verPoll=()=>{};S.srvVer='2099.01.01.1';modal('<p>sheet</p>');verPill(true)")   # the app's own version polling would reset the pill; time.sleep(.8)
        z = pg.evaluate("[+getComputedStyle(document.getElementById('verpill')).zIndex,+getComputedStyle(document.getElementById('modal')).zIndex]")
        if not z[0] > z[1]: bad(f"{scheme}: the pill should sit above sheets: {z}")
        shot(pg, f"pill_over_sheet_{scheme}.png")
        x = pg.evaluate("Math.round(document.querySelector('#verpill .vx').getBoundingClientRect().height)")
        if x < 44: bad(f"{scheme}: the pill's x is {x}px tall")
        time.sleep(20.5)
        if not pg.evaluate("document.getElementById('verpill').classList.contains('dot')"): bad(f"{scheme}: pill should shrink to a dot after ~20 s")
        if pg.evaluate("document.getElementById('verpill').getBoundingClientRect().height") < 43.9: bad(f"{scheme}: the dot lost its 44px tap area")
        shot(pg, f"pill_dot_{scheme}.png")
        pg.evaluate("document.querySelector('#verpill .vx').click()"); time.sleep(.6)
        if pg.evaluate("document.getElementById('verpill').classList.contains('on')"): bad(f"{scheme}: x should hide the pill")
        pg.evaluate("verPill(true)"); time.sleep(.5)
        if pg.evaluate("document.getElementById('verpill').classList.contains('on')"): bad(f"{scheme}: the pill came back after the x for the same version")
        pg.evaluate("document.body.classList.remove('verin');localStorage.setItem('cw_upd',JSON.stringify({v:PAGE_VER,at:Date.now()}));verFadeIn()")
        if not pg.evaluate("document.body.classList.contains('verin')"): bad(f"{scheme}: a page reloaded for an update should fade in")
        pg.evaluate("localStorage.removeItem('cw_upd')")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{scheme}: sideways scroll")
        if errs: bad(f"{scheme}: JS errors {errs[:3]}")
        ctx.close()
    br.close()
print("PROBLEMS" if problems else "ALL OK", len(problems))
sys.exit(1 if problems else 0)
