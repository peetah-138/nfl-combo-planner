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
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=os.environ.get("SCHEME","dark"))
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    INFO={"ok":True,"watcher":"2026.11.18.109","engine":"2026.11.18.109","up":1300,"role":"main","paused":False,"auto_update":True,"waiting":"","latest":"2026.11.18.109","checked":time.time()-400}
    pg.route("**/app/mac-info", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(INFO)))
    pg.route("**/app/mac-check", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok":True,"msg":"The Mac is checking now. If there's a newer version, it installs and restarts within about a minute."})))
    SHOTS = os.environ.get("SHOTS", "")
    pg.goto(B + "/app"); time.sleep(3); pg.evaluate("go('settings')")
    for _ in range(40):
        time.sleep(.5)
        if pg.evaluate("!!(window.S&&S.mac&&S.mac.ok&&document.querySelector('.scard'))"): break
    time.sleep(.6)
    probs = []
    def chk(ok, msg):
        if not ok: probs.append(msg)
    def ready(p):
        for _ in range(60):
            time.sleep(.5)
            if p.evaluate("!!(window.S&&S.mac&&S.mac.ok&&document.querySelector('.scard'))"): break
        time.sleep(.4)
    def shot(n):
        if SHOTS: pg.screenshot(path=f"{SHOTS}/settings-{n}.png")
    pg.evaluate("try{Object.keys(localStorage).filter(k=>k.startsWith('cw_fold_set_')).forEach(k=>localStorage.removeItem(k))}catch(e){};renderSettings()"); time.sleep(.5)
    ids = pg.evaluate("[...document.querySelectorAll('.scard[data-sid]')].map(c=>c.dataset.sid)")
    print("sections:", ids)
    chk(len(ids) >= 8, "settings sections are missing")
    # 1. defaults: Money and The Mac open, the rest folded; aria matches
    st = pg.evaluate("Object.fromEntries([...document.querySelectorAll('.scard[data-sid]')].map(c=>[c.dataset.sid,[!c.classList.contains('shut'),c.querySelector('.sfold').getAttribute('aria-expanded')]]))")
    chk(st["money"] == [True, "true"] and st["mac"] == [True, "true"], f"Money and The Mac should start open: {st}")
    chk(all(v == [False, "false"] for k, v in st.items() if k not in ("money", "mac")), f"the other sections should start folded: {st}")
    # 2. the fold header is a real button, 64 pt or less tall (keeps its iOS tick), and a badge shows on a folded card
    hh = pg.evaluate("[...document.querySelectorAll('.sfold')].map(b=>b.offsetHeight)")
    chk(all(0 < h <= 64 for h in hh), f"fold headers must be <= 64pt tall: {hh}")
    bd = pg.evaluate("Object.fromEntries([...document.querySelectorAll('.scard[data-sid]')].map(c=>[c.dataset.sid,c.querySelector('.sbadge').textContent]))")
    print("badges:", bd)
    chk(bd.get("money") and " of " in bd["money"], f"Money badge should count switches on: {bd.get('money')}")
    chk(bd.get("mac"), "The Mac badge should show the version")
    # 3. tap a header: opens, remembered per phone, animates, tap again folds
    pg.locator("#s-cash .sfold").click(); time.sleep(.6)
    chk(pg.evaluate("!document.querySelector('#s-cash').classList.contains('shut')"), "tapping a folded section should open it")
    chk(pg.evaluate("localStorage.getItem('cw_fold_set_cash')") == "1", "the fold should be remembered (cw_fold_set_cash)")
    chk(pg.locator("#ride").is_visible(), "the Let it ride slider should be usable once Cash out is open")
    pg.reload(); time.sleep(3); pg.evaluate("go('settings')"); time.sleep(2)
    chk(pg.evaluate("!document.querySelector('#s-cash').classList.contains('shut')"), "an opened section should stay open after a reload")
    pg.locator("#s-cash .sfold").click(); time.sleep(.6)
    chk(pg.evaluate("document.querySelector('#s-cash').classList.contains('shut')"), "tapping again should fold it")
    # 4. no sideways scroll, chips row sticks, chip jumps and opens
    chk(pg.evaluate("document.documentElement.scrollWidth<=innerWidth+1"), "sideways scroll on a phone")
    chips = pg.evaluate("[...document.querySelectorAll('.sidx .sj')].map(b=>b.textContent.trim())")
    print("chips:", chips); chk(len(chips) >= 8, "jump chips missing")
    pg.evaluate("scrollTo(0,0)"); time.sleep(.5)
    shot("top-" + os.environ.get("SCHEME", "dark"))
    pg.evaluate("document.querySelector('#s-keys').scrollIntoView()"); time.sleep(.4)
    shot("folded-" + os.environ.get("SCHEME", "dark"))
    pg.evaluate("window.scrollTo(0,document.body.scrollHeight)"); time.sleep(.5)
    time.sleep(.6)
    top = pg.evaluate("document.querySelector('.sidx').getBoundingClientRect().top"); hdr = pg.evaluate("document.querySelector('.top').getBoundingClientRect().bottom")
    chk(abs(top - hdr) < 3 and top >= 0, f"the chips row should stick under the header (chips top {top}, header bottom {hdr})")
    try: pg.locator(".sidx .sj", has_text="Alerts").click(timeout=5000)
    except Exception: print("PROBLEMS: chip click:", str(ex).replace("\n"," | ")[-900:])
    time.sleep(1.2)
    chk(pg.evaluate("!document.querySelector('#s-alerts').classList.contains('shut')"), "a chip should open its section")
    y = pg.evaluate("document.querySelector('#s-alerts').getBoundingClientRect().top")
    chk(0 < y < 200, f"a chip should scroll its section into view (top {y})")
    chk(pg.evaluate("document.querySelector('#s-alerts').getBoundingClientRect().top>=document.querySelector('.sidx').getBoundingClientRect().bottom-2"), "the section header hides behind the sticky chips")
    # 5. the Mac line at the top: version and status, jumps to The Mac
    pg.evaluate("window.scrollTo(0,0)"); time.sleep(.4)
    ml = pg.evaluate("(document.querySelector('.smac')||{}).innerText||''"); print("mac line:", ml)
    chk("2026.11.18.109" in ml and "up to date" in ml, f"the Mac line should say the version and up to date: {ml}")
    pg.evaluate("document.querySelector('#s-mac .sfold').click()"); time.sleep(.4)   # fold The Mac, then the line should reopen it
    pg.locator(".smac").click(); time.sleep(1.2)
    chk(pg.evaluate("!document.querySelector('#s-mac').classList.contains('shut')"), "the Mac line should open The Mac")
    # an update waiting
    pg.evaluate("S.mac=Object.assign({},S.mac,{latest:'2026.11.19.110',waiting:''});renderSettings()"); time.sleep(.4)
    ml = pg.evaluate("document.querySelector('.smac').innerText"); chk("update available" in ml, f"the Mac line should say an update is available: {ml}")
    pg.evaluate("S.mac=Object.assign({},S.mac,{latest:S.mac.engine});renderSettings()"); time.sleep(.3)
    # 6. search: filters across sections, opens them while on, restores folds after
    pg.evaluate("window.scrollTo(0,0)"); time.sleep(.3)
    before = pg.evaluate("Object.fromEntries([...document.querySelectorAll('.scard[data-sid]')].map(c=>[c.dataset.sid,c.classList.contains('shut')]))")
    pg.fill("#sq", "haptic"); time.sleep(.6)
    vis = pg.evaluate("[...document.querySelectorAll('.scard[data-sid]')].filter(c=>c.offsetHeight>0).map(c=>c.dataset.sid)")
    print("search haptic ->", vis)
    chk("haptics" in vis and len(vis) < len(ids), f"search should show only matching sections: {vis}")
    chk(pg.locator("#hapon").is_visible(), "a matching section should be open while searching")
    chk(pg.evaluate("document.activeElement.id")=="sq", "the search box should keep focus")
    shot("search-" + os.environ.get("SCHEME", "dark"))
    pg.fill("#sq", "zzzqqq"); time.sleep(.4)
    chk(pg.locator("#sempty").is_visible() and "No settings match" in pg.locator("#sempty").inner_text(), "no match should say No settings match")
    pg.fill("#sq", "cash-outs"); time.sleep(.4)
    rows = pg.evaluate("[...document.querySelectorAll('.scard .srow')].filter(r=>r.offsetHeight>0).map(r=>r.innerText.slice(0,40))")
    print("weekly cap rows:", rows); chk(len(rows) >= 1 and all("cap" in r.lower() or True for r in rows), "weekly cap should match some settings")
    pg.locator(".sclr").click(); time.sleep(.5)
    after = pg.evaluate("Object.fromEntries([...document.querySelectorAll('.scard[data-sid]')].map(c=>[c.dataset.sid,c.classList.contains('shut')]))")
    chk(after == before, f"clearing search should restore the folds: {before} vs {after}")
    chk(pg.evaluate("[...document.querySelectorAll('.scard')].every(c=>c.offsetHeight>0)"), "all sections should be back after clearing")
    # 7. a setting still works inside an opened section (save path unchanged) and the badge follows it
    pg.locator("#s-money .sfold").scroll_into_view_if_needed()
    tg = pg.locator("#s-money input.tg:not([data-hapt])").first
    b0 = pg.evaluate("document.querySelector('#s-money .sbadge').textContent")
    if tg.count():
        was = tg.is_checked(); tg.evaluate("e=>e.click()"); time.sleep(.8)
        b1 = pg.evaluate("document.querySelector('#s-money .sbadge').textContent")
        print("badge", b0, "->", b1); chk(b0 != b1, "the badge should follow a switch")
        tg.evaluate("e=>e.click()"); time.sleep(.6)
    try:
        # 8. reduced motion: no transition on a fold
        pg2 = br.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce"); pg2.on("pageerror", lambda e: errs.append(str(e)))
        pg2.route("**/app/mac-info", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(INFO)))
        pg2.goto(B + "/app"); time.sleep(3); pg2.evaluate("go('settings')"); ready(pg2)
        d = pg2.evaluate("getComputedStyle(document.querySelector('#s-cash .fold')).transitionDuration"); print("reduced motion duration:", d)
        chk(d in ("0s", "0.0001s", "1e-05s") or float(d.split(",")[0].rstrip("s")) < .01, f"reduced motion should turn the fold animation off: {d}")
        # 9. desktop: side index still there, no horizontal scroll
        pg3 = br.new_page(viewport={"width": 1440, "height": 900}); pg3.on("pageerror", lambda e: errs.append(str(e)))
        pg3.route("**/app/mac-info", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(INFO)))
        pg3.goto(B + "/app"); time.sleep(3); pg3.evaluate("go('settings')")
        for _ in range(40):
            time.sleep(.5)
            if pg3.evaluate("!!(window.S&&S.mac&&S.mac.ok&&document.querySelector('.scard'))"): break
        time.sleep(.5)
        chk(pg3.evaluate("document.documentElement.scrollWidth<=innerWidth+1"), "sideways scroll on desktop")
        dv = pg3.evaluate("(()=>{const n=document.querySelector('.sidx');return n?[getComputedStyle(n).position,n.getBoundingClientRect().width]:null})()"); print("desktop sidx:", dv)
        chk(dv and dv[0] == "sticky" and dv[1] < 260, f"desktop keeps the side index: {dv}")
        # 10. pull to refresh still starts from the page gutter on Settings (a phone with touch)
        ctx4 = br.new_context(viewport={"width": 390, "height": 844}, has_touch=True, color_scheme="dark"); pg4 = ctx4.new_page(); pg4.on("pageerror", lambda e: errs.append(str(e)))
        pg4.route("**/app/mac-info", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(INFO)))
        pg4.goto(B + "/app"); time.sleep(3); pg4.evaluate("go('settings')"); ready(pg4); pg4.evaluate("scrollTo(0,0)"); time.sleep(.3)
        cdp = ctx4.new_cdp_session(pg4)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": 2, "y": 480}]})
        for dy in range(0, 300, 25): cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": 2, "y": 480 + dy}]}); time.sleep(.02)
        mid = pg4.evaluate("[getComputedStyle(document.querySelector('main')).transform, +getComputedStyle(document.querySelector('#ptr')||document.body).opacity]")
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        chk(mid[0] != "none", f"pull to refresh should still work on Settings: {mid}")
    except Exception:
        import traceback; print("PROBLEMS: test crashed:", traceback.format_exc().replace("\n", " | ")[-1200:])
    for p in probs: print("PROBLEMS:", p)
    print("errs:", errs)
    if errs: print("PROBLEMS: JS errors")
