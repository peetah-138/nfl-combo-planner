"""A newer version on the Mac (GitHub #150, display only): the page learns the running version from every Live answer,
reloads by itself only when idle (with an 'Updated to' note after), shows a tap-to-refresh pill when busy (never
reloads under a sheet, a pending quote/buy, a finger), has no reload loop, and Settings shows the version. Nothing real."""
import sys, os, time, threading, re, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
tk_ev = sorted({m["event_ticker"] for m in mk})
def L(i, team): ev = tk_ev[i]; return {"ticker": f"{ev}-{team}", "event_ticker": ev, "event": ev, "side": "yes"}
bets = [{"ticker": "KXMVE-1", "legs": [L(0, "BOS"), L(1, "DEN")], "cost": 5.0, "pays": 41.2, "status": "pending", "back": 0,
         "week": "2026-11-17", "full_pays": 41.2, "lg": "nba", "lgs": ["nba"]}]
state = {}
def load():
    A = real_load()
    state["A"] = A
    A.fetch_account = lambda max_age=60, every_league=False: (bets, 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    return A
W.load_engine = load
# the fake ESPN answers with NO events (nothing under way) until a test flips `espn["live"]`, then the one bet's game is in progress
espn = {"live": False}
_net = requests.get
def _espn_get(url, params=None, **k):
    if "espn.com" in url and espn["live"]:
        st = {"period": 2, "displayClock": "5:42", "type": {"state": "in", "name": "STATUS_IN_PROGRESS", "shortDetail": "Q2 5:42"}}
        tm = lambda i, n, ab, ha, s: {"id": i, "homeAway": ha, "score": str(s),
                                      "team": {"id": i, "displayName": n, "shortDisplayName": n.split()[-1], "location": n.rsplit(" ", 1)[0], "abbreviation": ab}}
        return R({"events": [{"id": "e1", "date": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "status": st,
                              "competitions": [{"status": st, "competitors": [tm("1", "Boston Celtics", "BOS", "away", 54), tm("2", "New York Knicks", "NYK", "home", 49)]}]}]})
    return _net(url, params=params, **k)
requests.get = _espn_get
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright


def until(pg, js, secs=12):
    end = time.time() + secs
    while time.time() < end:
        try:
            if pg.evaluate(js): return True
        except Exception: pass
        time.sleep(.15)
    return False
def still(pg, js, secs=3.2):   # the condition holds the whole time (nothing reloaded, nothing changed)
    end = time.time() + secs
    while time.time() < end:
        try:
            if not pg.evaluate(js): return False
        except Exception: return False
        time.sleep(.2)
    return True
NEWV = "2099.01.01.1"
SHOTS = os.environ.get("CW_SHOTS")
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    def fresh_page():
        pg.goto(B + "/app"); until(pg, "!!(S.live&&S.live.fresh)", 25)
        pg.evaluate("try{sessionStorage.clear()}catch(e){}; window.__m=1; window.__haps=[]; const h=window.hap; window.hap=function(k){window.__haps.push(k||'light');return h.apply(this,arguments)}")
    # the page itself: the version is filled in, never cached
    resp = pg.request.get(B + "/app")
    A = state["A"]
    html = resp.text()
    print("page version filled in:", f'PAGE_VER="{A.VERSION}"' in html, "| placeholder gone:", "__CWVER__" not in html, "| cache:", resp.headers.get("cache-control"))
    if f'PAGE_VER="{A.VERSION}"' not in html or "__CWVER__" in html: print("PROBLEMS: the page's version isn't filled in")
    if "no-store" not in (resp.headers.get("cache-control") or ""): print("PROBLEMS: the page isn't no-store")
    fresh_page()
    f = pg.evaluate("S.live.fresh")
    print("live carries the running version:", f.get("ver"))
    if f.get("ver") != A.VERSION: print("PROBLEMS: fresh.ver missing or wrong")
    if pg.evaluate("PAGE_VER") != A.VERSION: print("PROBLEMS: PAGE_VER differs from the server")
    # same version: no pill, no reload
    if not still(pg, "window.__m===1&&!document.querySelector('#verpill.on')", 2.5): print("PROBLEMS: a pill or reload with the same version")
    # settings row
    pg.evaluate("go('settings')"); until(pg, "!!document.querySelector('#verrow')", 10)
    row = pg.evaluate("(document.querySelector('#verrow')||{}).textContent")
    print("version row:", repr(row))
    if not re.search(r"App version\s*" + re.escape(A.VERSION) + r"\s*\(page: same\)", row or ""): print("PROBLEMS: settings version row", row)
    row2 = pg.evaluate("(()=>{const d=document.createElement('div');d.innerHTML=verRow('" + NEWV + "');return d.textContent})()")
    print("differing row:", repr(row2))
    if NEWV not in row2 or A.VERSION not in row2 or "page: same" in row2: print("PROBLEMS: a differing page version isn't shown")
    if SHOTS: pg.evaluate("document.querySelector('#verrow').scrollIntoView({block:'center'})"); time.sleep(.5); pg.screenshot(path=SHOTS + "/settings_version.png")
    pg.evaluate("go('live')")

    # 1. a sheet is open: pill, and NO reload, however long we wait; closing the sheet then reloads quietly
    fresh_page()
    pg.evaluate("modal('<h3>Pretend quote</h3><p>x</p>')")
    pg.evaluate(f"verSeen('{NEWV}')")
    ok = until(pg, "!!document.querySelector('#verpill.on')", 3)
    print("sheet open -> pill:", ok, repr(pg.evaluate("(document.querySelector('#verpill')||{}).textContent")))
    if not ok: print("PROBLEMS: no pill while a sheet is open")
    if "New version ready: tap to refresh" not in (pg.evaluate("(document.querySelector('#verpill')||{}).textContent") or ""): print("PROBLEMS: pill words")
    if SHOTS: time.sleep(.6); pg.screenshot(path=SHOTS + "/pill.png")
    if not still(pg, "window.__m===1", 4): print("PROBLEMS: the page reloaded with a sheet open")
    pg.evaluate("closeModal()")
    ok = until(pg, "window.__m!==1", 9)
    print("sheet closed -> reloads by itself:", ok)
    if not ok: print("PROBLEMS: no reload once idle")

    # 2. busy in other ways: a quote on its way, a buy on its way, a live price, a finger down, a scrub, an armed Approve
    fresh_page()
    pg.evaluate("window.load=async()=>{}")   # the page's own refreshes would put the real version back mid-case
    cases = {"quote in flight": "S.qpend={1:{t:Date.now()}}", "buy in flight": "S.buying=true", "tap in flight": "S.busy={x:true}",
             "price on screen": "S.quotes={1:{at:Date.now()/1000}}", "scrubbing": "S.scrub=true",
             "approve on its way": "S.pSend=true", "finger down": "dispatchEvent(new PointerEvent('pointerdown'))"}
    for name, js in cases.items():
        pg.evaluate(js); pg.evaluate(f"S.srvVer='';S.verIdleAt=0;verSeen('{NEWV}')")
        until(pg, "!!document.querySelector('#verpill.on')", 3)
        held = still(pg, "window.__m===1&&!!document.querySelector('#verpill.on')", 2.8)
        print(name + " -> pill, no reload:", held, pg.evaluate("[window.__m,!!document.querySelector('#verpill.on'),S.srvVer,verBusy(),JSON.stringify(S.quotes)]") if not held else "")
        if not held: print("PROBLEMS: reloaded or no pill while: " + name)
        pg.evaluate("S.qpend={};S.buying=false;S.busy={};S.quotes={};S.scrub=false;S.pSend=false;dispatchEvent(new PointerEvent('pointerup'))")
        pg.evaluate("S.srvVer=PAGE_VER;verSeen(PAGE_VER)"); time.sleep(.3)

    # 3. tapping the pill: the light haptic comes straight from the tap, then it reloads
    fresh_page()
    pg.evaluate("modal('<p>sheet</p>')"); pg.evaluate(f"verSeen('{NEWV}')"); until(pg, "!!document.querySelector('#verpill.on')", 3)
    n = pg.evaluate("(()=>{__haps.length=0;document.getElementById('verpill').click();return __haps.length})()")
    print("haptic fired inside the tap:", n, pg.evaluate("__haps.slice()"))
    if n < 1 or "light" not in pg.evaluate("__haps.slice()"): print("PROBLEMS: the pill's haptic didn't fire inside the tap")
    ok = until(pg, "window.__m!==1", 6)
    print("tap -> reloads:", ok)
    if not ok: print("PROBLEMS: the pill didn't reload")

    # 4. the real path: the Mac's answer says a newer version while the page is idle -> reload, then an 'Updated to' note
    fresh_page()
    def newer(route):
        r = route.fetch(); d = r.json()
        if isinstance(d.get("fresh"), dict): d["fresh"]["ver"] = NEWV
        route.fulfill(response=r, body=json.dumps(d), headers={**r.headers, "content-type": "application/json"})
    pg.route("**/app/api/live*", newer)
    pg.evaluate("load('live',true)")
    ok = until(pg, "window.__m!==1", 12)
    print("idle + newer version from the Mac -> reloads:", ok, "" if ok else pg.evaluate("[S.srvVer,S.live&&S.live.fresh&&S.live.fresh.ver,verBusy(),S.verIdleAt,!!document.querySelector('#verpill.on')]"))
    if not ok: print("PROBLEMS: no reload from a newer fresh.ver")
    pg.unroute("**/app/api/live*", newer)
    pg.goto(B + "/app"); until(pg, "!!S.live", 20)
    # 5. after a reload for an update the page says so once
    pg.evaluate("localStorage.setItem('cw_upd',JSON.stringify({v:PAGE_VER,at:Date.now()}))")
    pg.reload(); ok = until(pg, "/Updated to /.test(($('#toast')||{}).textContent||'')", 6)
    print("'Updated to' toast:", ok, repr(pg.evaluate("($('#toast')||{}).textContent")))
    if not ok: print("PROBLEMS: no 'Updated to' toast after the reload")
    if pg.evaluate("localStorage.getItem('cw_upd')") is not None: print("PROBLEMS: the update note wasn't cleared")

    # 6. no reload loop: already reloaded for this version a moment ago and still different -> the pill stays, no reload
    fresh_page()
    pg.evaluate(f"sessionStorage.setItem('cw_vrl',JSON.stringify({{v:'{NEWV}',at:Date.now()}}))")
    pg.evaluate(f"verSeen('{NEWV}')")
    until(pg, "!!document.querySelector('#verpill.on')", 6)
    held = still(pg, "window.__m===1&&!!document.querySelector('#verpill.on')", 4)
    print("no reload loop:", held)
    if not held: print("PROBLEMS: a reload loop isn't guarded")
    # 7. an unreadable version never triggers anything
    fresh_page(); pg.evaluate("verSeen('');verSeen(null);verSeen('<b>x</b>')")
    if not still(pg, "window.__m===1&&!document.querySelector('#verpill.on')", 2.5): print("PROBLEMS: a junk version triggered something")
    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): print("PROBLEMS: page scrolls sideways")
    print("errs:", errs)
    if errs: print("PROBLEMS: JS errors")
    br.close()
