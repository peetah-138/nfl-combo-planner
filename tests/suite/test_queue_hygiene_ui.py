# CHECK: group=page secs=40
"""Queue hygiene (display only; issues #517 #246). At phone size, dark and light, made-up data: the sell sheet says "contracts wanted" in plain words; a #c= link to a bet that is no longer live opens it with a calm toast; a tappable
toast ticks like a button (TAP selector); the panel header numbers (chance up, Expected, range) carry data-num so they roll
(fmtNum 'sm' = signed money); the report-only CSP header is on /app and no enforcing one is. The onclick-to-data work is covered
by test_onclick_data_ui.py. Nothing here touches buy, sell or sizing."""
import sys, os, time, threading, json, re, urllib.request
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

# the page and the hub's html both carry the report-only policy; nothing enforces one
hd = urllib.request.urlopen(urllib.request.Request(B + "/app")).headers
ro = hd.get("Content-Security-Policy-Report-Only") or ""
if "frame-ancestors 'none'" not in ro or "object-src 'none'" not in ro: bad(f"report-only CSP missing or short: {ro!r}")
if hd.get("Content-Security-Policy") is not None: bad("an enforcing Content-Security-Policy is sent (not yet: the SPA still uses inline handlers)")
if "Content-Security-Policy-Report-Only" not in open("wtest/combo_watcher.py").read().split("def _proxy_send")[1][:600]: bad("the hub's html answer lacks the report-only CSP")

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, has_touch=True, device_scale_factor=2)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        csp = []; pg.on("console", lambda m: csp.append(m.text) if "Content Security Policy" in m.text else None)
        pg.goto(B + "/app")
        if not wait(pg, "typeof toast==='function'&&typeof ssPaint==='function'&&typeof fmtNum==='function'&&document.querySelector('#main')", 40):
            bad(f"{scheme}: app didn't load"); ctx.close(); continue
        time.sleep(.8)
        if not pg.evaluate("fmtNum(-12.5,'sm')===smoney(-12.5)&&fmtNum(3,'sm')===smoney(3)"): bad(f"{scheme}: fmtNum 'sm' should equal smoney")
        # the panel header numbers roll: rendered through the real function with made-up stats
        html = open("wtest/spa/build.js").read()
        for k in ("pn:ahead", "pn:ev", "pn:lo", "pn:hi"):
            if 'data-num="' + k + '"' not in html: bad(f"{scheme}: panel header lacks data-num {k}")
        # a tappable toast gets the press feedback and tick (TAP selector) and a plain one does not
        r = pg.evaluate("""(()=>{toast('tap me',4000,'',()=>{});const t=document.getElementById('toast');const a=!!tapEl(t);toast('plain',4000);return [a,!!tapEl(document.getElementById('toast'))]})()""")
        if r != [True, False]: bad(f"{scheme}: tappable toast should tick, plain should not: {r}")
        pg.evaluate("toastHide()")
        # #c= to a bet that is no longer live: opens its page and says so calmly
        pg.evaluate("""window.__t=[];window.__o=[];const rt=toast;window.toast=(m)=>{__t.push(m);};window.comboOk=()=>true;window.load=async()=>{};window.openClosed=(t)=>{__o.push(t)};
         S.live={combos:[]};S.liveNet=true;S.view='live';location.hash='#c=KXGONE-1';comboFromHash(true);""")
        if not wait(pg, "__o.length>0", 6): bad(f"{scheme}: #c= to a settled bet did not open it")
        if not pg.evaluate("(__t[0]||'').includes('no longer live')"): bad(f"{scheme}: no calm toast for a settled #c= link: {pg.evaluate('__t')}")
        pg.evaluate("window.toast=toast;")
        # the sell sheet wording, made-up numbers
        pg.reload(); wait(pg, "typeof ssPaint==='function'&&document.querySelector('#main')", 40); time.sleep(.6)
        pg.evaluate("""(()=>{modal('<div id="ssx"></div>');S.ss={t:'KXDEMO-1',busy:false,q:{sport:'nfl',pick:'Riverton to win',game:'Riverton at Lakeside',bid:.41,gap:null,depth:3200,got:6.1,fee:.12,profit:1.4,cost:4.7,n:15,have:15,px:.4,chance:.44,pays:15,secs:60,at:Date.now()/1000,clears:true,blocked:null,live:true,warn:[]}};ssPaint();})()""")
        time.sleep(.5)
        txt = pg.evaluate("document.querySelector('#ssx .sbn small').textContent")
        if "contracts wanted" not in txt or "no one buying" in txt: bad(f"{scheme}: sell sheet wording: {txt!r}")
        if "no sellers" in txt or "gap" in txt or re.search(r"\dk wanted", txt): bad(f"{scheme}: old sell sheet wording still there: {txt!r}")
        shot(pg, f"1_sell_sheet_{scheme}.png")
        pg.evaluate("closeModal()")
        pg.evaluate("""window.__t=[];S.live={combos:[]};location.hash='';toast('That bet is no longer live. Here is where it stands.',9000)""")
        time.sleep(.6)
        shot(pg, f"2_settled_link_toast_{scheme}.png")
        pg.evaluate("toastHide()")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{scheme}: sideways scroll")
        if errs: bad(f"{scheme}: JS errors {errs[:3]}")
        ctx.close()
    br.close()
print("PROBLEMS" if problems else "ALL OK", len(problems))
sys.exit(1 if problems else 0)
