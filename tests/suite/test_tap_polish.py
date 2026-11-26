# CHECK: group=page secs=30
"""Tap polish at phone size (issues #272, #273): (1) a tappable toast (advice -> open a combo) stops taking taps while a
sheet is open, so a thumb aimed at a sheet button can't open something else; it works again with no sheet. (2) Undo after
a Pass wakes the save's sleeping retry at once and shows 'Bringing it back...' instead of waiting up to two minutes, and
when the dismiss never reached the Mac the idea simply comes back with no failure toast. The pages and the dismiss/undo
calls are scripted (nothing real is sent). Saves screenshots (SHOTS dir, if set). Prints PROBLEMS on any failure."""
import sys, os, time, threading, json
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
UNDOS = []
def act(route):
    try: body = json.loads(route.request.post_data or "{}")
    except ValueError: body = {}
    a = body.get("a")
    if a == "idea_dismiss": return route.abort()                      # the link is down: the dismiss never lands
    if a == "idea_undo":
        UNDOS.append(body); return route.abort()                       # ...and the undo can't land either
    return route.continue_()
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, has_touch=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("localStorage.clear();localStorage.setItem('cw_view','live')")
        pg.route("**/app/api/act", act)
        pg.goto(B + "/app")
        if not wait(pg, "typeof toast==='function'&&typeof modal==='function'&&typeof ideaSend==='function'", 40):
            bad(f"{scheme}: the app didn't load"); ctx.close(); continue
        # (1) a tappable toast over an open sheet takes no taps
        pg.evaluate("window.__taps=0;toast('Advice for you',7000,null,()=>{window.__taps++})"); time.sleep(.5)
        pg.evaluate("modal('<h3>Sheet</h3><div class=\"row\"><button class=\"btn acc\" id=\"sheetbtn\">Cash out</button></div>')"); time.sleep(.5)
        pe = pg.evaluate("getComputedStyle(document.querySelector('#toast')).pointerEvents")
        if pe != "none": bad(f"{scheme}: a tappable toast over an open sheet should ignore taps (pointer-events {pe})")
        pg.evaluate("closeModal()"); time.sleep(.6)
        pe = pg.evaluate("getComputedStyle(document.querySelector('#toast')).pointerEvents")
        if pe != "auto": bad(f"{scheme}: with no sheet open the tappable toast should take taps again (pointer-events {pe})")
        pg.evaluate("toast('Opened by tap',1000,null,()=>{})")
        pg.evaluate("modal('<h3>Sheet</h3>')"); pg.evaluate("toast('Advice 2',3000,null,()=>{})"); time.sleep(.4)
        if pg.evaluate("document.querySelector('#toast').classList.contains('tap')"): bad(f"{scheme}: a toast raised while a sheet is open should not be tappable")
        pg.evaluate("closeModal()")
        # (2) Undo wakes the sleeping save at once; with the dismiss never sent, the idea is just back
        pg.evaluate("""(()=>{S.idHide=S.idHide||{};S.idJob=S.idJob||{};toastHide();
          const key='k1',job={undone:false};S.idHide[key]=true;S.idJob[key]=job;
          window.__res=null;job.p=(async()=>{await new Promise(f=>{const h=setTimeout(f,120000);job.wake=()=>{clearTimeout(h);f();};});return job.undone?'undone':'failed';})().then(r=>{window.__res=r;return r;});
          window.__t0=Date.now();window.__done=null;ideaUndo([key]).then(()=>{window.__done=Date.now()-window.__t0;});})()""")
        time.sleep(.3)
        if "Bringing it back" not in pg.evaluate("document.querySelector('#toast').innerText"): bad(f"{scheme}: Undo should say 'Bringing it back...' at once")
        if not wait(pg, "window.__done!==null", 8): bad(f"{scheme}: Undo waited on the sleeping save instead of waking it")
        else:
            if pg.evaluate("window.__res") != "undone": bad(f"{scheme}: the woken save should end 'undone'")
            if pg.evaluate("S.idHide['k1']!==undefined"): bad(f"{scheme}: an undone dismiss that never reached the Mac should be undone locally")
            if "Couldn't bring it back" in pg.evaluate("document.querySelector('#toast').innerText"): bad(f"{scheme}: no failure toast when the dismiss never reached the Mac")
        if errs: bad(f"{scheme}: JS errors {errs[:3]}")
        ctx.close()
    br.close()
if problems:
    print("PROBLEMS:", "; ".join(problems))
else:
    print("ALL OK")
