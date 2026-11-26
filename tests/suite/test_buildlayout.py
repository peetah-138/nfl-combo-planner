# CHECK: group=page secs=75
"""Build layout (issues #248, #249): the combo date range lives on Build (at the top, under the league chips) instead of Settings, and
the "Your combo" slip sits right under the games board on one-column screens (the sticky side column on wide ones).
Checks, at phone (dark and light) and desktop sizes: the date range is above the board and saves through the same settings
call (/app/api/settings with the league; scripted here, nothing real is saved), a refused save puts the old choice back,
every league mode (day, week, mix) offers its own choices, Settings no longer has the rows and points to Build, the slip is
in the main column right after the board (never inside the side column) when narrow, inside the aside when wide, the
slip bar and a quote (data-ph) still work, one slip only (no duplicate ids), no sideways scroll, haptic switches on the
new buttons. Saves screenshots (SHOTS dir, if set). Prints PROBLEMS on any failure."""
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
def shot(pg, name, sel=None):
    """the viewport (scrolled to sel when given) and, beside it, the whole page"""
    if not SHOTS: return
    pg.evaluate("typeof toastHide==='function'&&toastHide()"); time.sleep(.6)   # a clean picture: no toast over it
    if sel: pg.evaluate("s=>{const e=document.querySelector(s);if(e)e.scrollIntoView({block:'center'})}", sel); time.sleep(.3)
    pg.evaluate('window.scrollTo(0,0)'); time.sleep(.3)
    pg.screenshot(path=os.path.join(SHOTS, name.replace('.png', '_top.png')))   # the top: league chips + date bar
    if sel: pg.evaluate("s=>{const e=document.querySelector(s);if(e)e.scrollIntoView({block:'center'})}", sel); time.sleep(.3)
    pg.screenshot(path=os.path.join(SHOTS, name))
    pg.screenshot(path=os.path.join(SHOTS, name.replace('.png', '_full.png')), full_page=True)
SAVES = []; SAVE_OK = {"ok": True}
def settings_route(route):
    if route.request.method != "POST": return route.continue_()
    try: body = json.loads(route.request.post_data or "{}")
    except ValueError: body = {}
    SAVES.append(body)
    return route.fulfill(status=200, content_type="application/json", body=json.dumps(SAVE_OK))
def act(route):
    try: body = json.loads(route.request.post_data or "{}")
    except ValueError: body = {}
    a = body.get("a")
    if a == "custom": return route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "i": 9001}))
    if a == "quote": return route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "pays": 31.2, "stake": 5, "pct": 1.01, "clears": True, "ev": .4, "rec": 5, "min": 2, "max": 20, "room": 50}))
    return route.continue_()
GEOM = """(()=>{const q=s=>document.querySelector(s),r=e=>e?e.getBoundingClientRect():null;const dr=q('#dayrange'),bd=q('.board'),sl=q('.slip');
 const rows=document.querySelectorAll('.board .mrow'),last=rows[rows.length-1];
 return {dr:dr?r(dr).top+scrollY:null,board:bd?r(bd).top+scrollY:null,lastEnd:last?r(last).bottom+scrollY:null,slip:sl?r(sl).top+scrollY:null,
  inAside:!!(sl&&sl.closest('aside')),n:document.querySelectorAll('.slip').length,ids:document.querySelectorAll('#sbslip').length,
  ideas:(()=>{const h=[...document.querySelectorAll('.sech')].find(e=>/Surprise me/.test(e.innerText));return h?r(h).top+scrollY:null})(),
  side:document.documentElement.scrollWidth>innerWidth+1};})()"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, tag, scheme in ((390, 844, "phone", "dark"), (390, 844, "light", "light"), (1280, 900, "desk", "dark"), (1500, 900, "wide", "dark")):
        ctx = br.new_context(viewport={"width": vw, "height": vh}, color_scheme=scheme, has_touch=(vw < 900), device_scale_factor=2)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__haps=[];localStorage.clear();localStorage.setItem('cw_view','build');localStorage.setItem('cw_lg','nba');localStorage.setItem('cw_pview','nba')" + (";window.__hswForce=1" if tag == "light" else ""))
        pg.route(re.compile(r".*/app/api/settings$"), settings_route)
        pg.route("**/app/api/act", act)
        pg.goto(B + "/app")
        if not wait(pg, "typeof dayRange==='function'&&S.build&&S.build.board&&S.build.board.length>1&&S.build.days", 40):
            bad(f"{tag}: the Build board didn't load"); ctx.close(); continue
        pg.evaluate("S.adv=true;S.slip=[];renderBuild()"); time.sleep(.6)
        # ---- (1) the date range is on Build, above the games board
        g = pg.evaluate(GEOM)
        if g["dr"] is None: bad(f"{tag}: no date range on Build")
        elif g["board"] is None or g["dr"] >= g["board"]: bad(f"{tag}: the date range should sit above the games board: {g}")
        txt = pg.evaluate("document.querySelector('#dayrange').innerText")
        if "Today" not in txt or "Tomorrow" not in txt: bad(f"{tag}: a daily league should offer Today / Tomorrow: {txt!r}")
        if g["side"]: bad(f"{tag}: the page scrolls sideways (empty)")
        shot(pg, f"1_empty_{tag}.png", ".board")
        # saving: same call as Settings, this league
        pg.evaluate("S.slip=[S.build.board[0].sides.filter(s=>!s.tie)[0].ticker];renderBuild()"); time.sleep(.3)
        SAVES.clear(); pg.evaluate("window.__haps=[]")
        pg.locator("#dayrange .daybar button", has_text="Tomorrow").click(); time.sleep(.5)
        if not SAVES or SAVES[-1].get("lg") != "nba" or SAVES[-1].get("values") != {"next_day": True}: bad(f"{tag}: Tomorrow should save next_day through the settings call: {SAVES}")
        if not pg.evaluate("window.__haps.length>0"): bad(f"{tag}: choosing a date should tick (haptic)")
        # other dates = another board: the picks are dropped (a combo is only priced from what is on screen)
        if pg.evaluate("S.slip.length") != 0: bad(f"{tag}: changing the dates should clear the picks")
        if "Picks cleared for the new dates" not in pg.evaluate("(document.querySelector('#toast')||{}).innerText||''"): bad(f"{tag}: changing the dates with picks should say they were cleared (#274)")
        # #274: every date button is a 44pt target; the date card stays on screen while the new board loads
        hs = pg.evaluate("[...document.querySelectorAll('#dayrange button')].map(e=>Math.round(e.getBoundingClientRect().height))")
        if not hs or min(hs) < 44: bad(f"{tag}: date buttons should be 44pt tall: {hs}")
        if not pg.evaluate("(()=>{S.dayHold={lg:S.lg,name:'NBA',days:S.build.days};const keep=S.build;S.build=null;renderBuild();const ok=!!document.querySelector('#dayrange');S.build=keep;renderBuild();return ok})()"): bad(f"{tag}: the date card should stay on screen while the board reloads (#274)")
        # a refused save puts the old choice back
        SAVE_OK.clear(); SAVE_OK.update({"ok": False}); wait(pg, "!!S.build&&!!S.build.days", 20)
        pg.evaluate("S.build.days.next_day=false;renderBuild()"); time.sleep(.3)
        pg.locator("#dayrange .daybar button", has_text="Tomorrow").click(); time.sleep(.7)
        if pg.evaluate("S.build.days.next_day"): bad(f"{tag}: a refused save should put Today back")
        if "Nothing was changed" not in pg.evaluate("(document.querySelector('#dayrange')||{}).innerText||''"): bad(f"{tag}: a refused save should say nothing was changed, inside the date card (#274)")
        SAVE_OK.clear(); SAVE_OK.update({"ok": True})
        if tag == "light":
            r = pg.evaluate("""[...document.querySelectorAll('#dayrange button')].map(e=>({n:e.querySelectorAll(':scope>.hsw').length,deep:e.querySelectorAll('.hsw').length}))""")
            if not r or any(c["n"] != 1 or c["deep"] != 1 for c in r): bad(f"{tag}: every date button should carry exactly one haptic switch: {r}")
        # ---- (2) the slip sits with the board
        wait(pg, "!!S.build&&!!S.build.board", 20)
        pg.evaluate("S.adv=true;S.slip=[];renderBuild()"); time.sleep(.4)
        tk = pg.evaluate("S.build.board[0].sides.filter(s=>!s.tie)[0].ticker"); tk2 = pg.evaluate("S.build.board[1].sides.filter(s=>!s.tie)[0].ticker")
        pg.evaluate(f"pick('{tk}',S.build.board[0].event)"); time.sleep(.5)
        g = pg.evaluate(GEOM)
        if g["n"] != 1 or g["ids"] > 1: bad(f"{tag}: exactly one slip on the page: {g}")
        if tag in ("wide",):
            if not g["inAside"]: bad(f"{tag}: on a wide screen the slip stays in the side column: {g}")
        else:
            if g["inAside"]: bad(f"{tag}: on a narrow screen the slip belongs under the board, not in the side column: {g}")
            elif g["slip"] is None or g["lastEnd"] is None or not (g["lastEnd"] - 2 <= g["slip"] <= g["lastEnd"] + 40): bad(f"{tag}: the slip should sit right under the games board: {g}")
            elif g["ideas"] is not None and g["slip"] >= g["ideas"]: bad(f"{tag}: the slip should come before the combo ideas: {g}")
        if "tap 1 more team" not in pg.evaluate("(document.querySelector('.slipbar .sbrow span')||{}).innerText||''") and tag != "wide" and tag != "desk": bad(f"{tag}: the slip bar should still ask for one more team")
        if g["side"]: bad(f"{tag}: the page scrolls sideways (one pick)")
        shot(pg, f"2_pick_{tag}.png", ".slip")
        # one pick: Buy straight still there; second pick: the price and quote phases still work
        if not pg.evaluate("!!document.querySelector('.slip #sbslip')"): bad(f"{tag}: the slip should offer Buy straight with one pick")
        pg.evaluate(f"pick('{tk2}',S.build.board[1].event)"); time.sleep(.5)
        if "Chance it hits" not in pg.evaluate("document.querySelector('.slip').innerText"): bad(f"{tag}: two picks should show the chance it hits")
        pg.evaluate("quoteSlip()")
        if not wait(pg, "!!S.custom&&!!S.custom.offer", 8): bad(f"{tag}: the slip's price didn't come back")
        time.sleep(.5)
        g = pg.evaluate(GEOM)
        if g["n"] != 1: bad(f"{tag}: one slip after a quote: {g}")
        if g["side"]: bad(f"{tag}: the page scrolls sideways (with a quote)")
        slip_txt = pg.evaluate("document.querySelector('.slip').innerText")
        if "$31" not in slip_txt: bad(f"{tag}: the quote should show in the slip: {slip_txt[:200]!r}")
        shot(pg, f"3_quote_{tag}.png", ".slip")
        # crossing the 1360px line moves the one slip without losing the picks
        if tag == "desk":
            pg.set_viewport_size({"width": 1500, "height": 900}); time.sleep(.6)
            g = pg.evaluate(GEOM)
            if not g["inAside"] or g["n"] != 1 or pg.evaluate("S.slip.length") != 2: bad(f"{tag}: widening should move the slip to the side column and keep both picks: {g}")
            pg.set_viewport_size({"width": 1280, "height": 900}); time.sleep(.6)
            g = pg.evaluate(GEOM)
            if g["inAside"] or g["n"] != 1 or pg.evaluate("S.slip.length") != 2: bad(f"{tag}: narrowing should bring the slip back under the board: {g}")
        # ---- (3) each league mode offers its own dates (week, mix) and saves them
        if tag == "phone":
            for lg, want, click, key in (("nfl", ("Thursday", "Saturday", "Monday", "Sunday"), "Saturday", "saturday"), ("mix", ("Games from",), None, None)):
                pg.evaluate(f"setLg('{lg}')")
                if not wait(pg, f"S.build&&S.build.lg==='{lg}'&&S.build.days&&!!document.querySelector('#dayrange')", 40): bad(f"{tag}: {lg} didn't load"); continue
                time.sleep(.5)
                t = pg.evaluate("document.querySelector('#dayrange').innerText")
                for w in want:
                    if w not in t: bad(f"{tag}: {lg} dates should offer {w!r}: {t!r}")
                if lg == "nfl" and (t.count("Sunday") != 1 or not (t.index("Thursday") < t.index("Saturday") < t.index("Monday"))): bad(f"{tag}: week dates read Thursday, Saturday, Monday with one Sunday note: {t!r}")
                if click:
                    SAVES.clear(); pg.locator("#dayrange button", has_text=click).click(); time.sleep(.5)
                    if not SAVES or SAVES[-1].get("lg") != lg or key not in SAVES[-1].get("values", {}): bad(f"{tag}: {lg} {click} should save {key}: {SAVES}")
                if lg == "mix":
                    n = pg.evaluate("document.querySelectorAll('#dayrange .daybar button').length")
                    if n < 2: bad(f"{tag}: mix should offer its game windows: {n}")
                    shot(pg, f"4_mix_{tag}.png")
            pg.evaluate("setLg('nba')"); time.sleep(.5)
        # ---- (4) Settings no longer has the rows, and points to Build
        if tag in ("phone", "desk"):
            pg.evaluate("go('settings')")
            if not wait(pg, "!!S.set&&!!document.querySelector('.set')", 30): bad(f"{tag}: Settings didn't load")
            else:
                time.sleep(.5)
                body = pg.evaluate("document.querySelector('main').textContent")   # folded sections are still in the page
                if "moved to the Build tab" not in body: bad(f"{tag}: Settings should point to Build for the dates")
                for old in ("Use tomorrow", "Thursday games", "Saturday games", "Monday games", "Same day means"):
                    if old in body: bad(f"{tag}: Settings still has {old!r}")
        if errs: bad(f"{tag}: JS errors {errs[:3]}")
        ctx.close()
    br.close()
if problems:
    print("PROBLEMS:", "; ".join(problems))
else:
    print("all good")
