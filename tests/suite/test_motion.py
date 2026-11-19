"""Makeover phase 1: press feedback and a haptic on every interactive thing (audited on every screen), distinct
haptic patterns, the push transition into a game/combo page (slide, dimmed page behind, skeleton, Back, swipe back),
the Live hero chart (Day/Week, scrub with readout and haptic ticks), rolling numbers and sliding chance bars.
Phone (390x844, touch) and desktop. Prints PROBLEMS on any failure."""
import sqlite3
import requests
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])

# A week of made-up "worth now" history in this test's own throwaway database (wahome), for the hero chart.
db = sqlite3.connect("wahome/combo_history.db")
db.execute("create table if not exists pulse(ts real, worth real, staked real)")
now = time.time()
db.executemany("insert into pulse values(?,?,?)", [(now - i * 600, round(18 + 6 * ((i * 7919) % 13) / 13 + (2016 - i) / 200, 2), 18.0) for i in range(1008, -1, -1)])
db.commit(); db.close()

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)

def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        if pg.evaluate(js): return True
        time.sleep(.2)
    return False

wk = requests.get(B + "/app/api/pulse?h=168", headers={"X-CW": "x"}).json()
dy = requests.get(B + "/app/api/pulse?h=16", headers={"X-CW": "x"}).json()
print("pulse api: week", len(wk.get("pulse") or []), "day", len(dy.get("pulse") or []))
if not (len(wk.get("pulse") or []) > len(dy.get("pulse") or []) >= 3): bad("the pulse API doesn't give a longer week than day")
if requests.get(B + "/app/api/pulse?h=zz", headers={"X-CW": "x"}).json().get("h") != 16: bad("a bad range isn't handled")

AUDIT = r"""(()=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[hidden]')&&!(e.closest('#modal')&&!$('#modal').classList.contains('on'));};
 const all=[...document.querySelectorAll('header *,main *,.tabbar *,#sheet *')].filter(e=>vis(e)&&!e.closest('#hapl'));
 const want=all.filter(e=>e.matches('button,a[href],select,label,input[type=checkbox],input[type=range],[onclick]')||(getComputedStyle(e).cursor==='pointer'&&!e.closest('.sparkw')));
 const miss=want.filter(e=>!e.disabled&&!tapEl(e)).map(e=>e.tagName+'.'+e.className+':'+(e.innerText||'').slice(0,20));
 let nopress=[];want.slice(0,80).forEach(e=>{const t=tapEl(e);if(!t)return;e.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,pointerType:'touch'}));
  if(!t.classList.contains('prs'))nopress.push(t.tagName+'.'+t.className);e.dispatchEvent(new PointerEvent('pointercancel',{bubbles:true}));});
 return {n:want.length,miss,nopress};})()"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, tag in ((390, 844, "phone"), (1280, 900, "desk")):
        ctx = br.new_context(viewport={"width": vw, "height": vh}, color_scheme="dark", has_touch=(tag == "phone"))
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/app/api/act", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "msg": "Got it."})))
        pg.add_init_script("window.__vib=[];navigator.vibrate=p=>{window.__vib.push(JSON.stringify(p));return true;};localStorage.setItem('cw_view','live');localStorage.removeItem('cw_rng')")
        pg.goto(B + "/app")
        if not wait(pg, "!!document.querySelector('.sparkw[data-chart]')", 25): bad(f"{tag}: the hero chart didn't draw from the pulse history")
        time.sleep(1)

        # ---- distinct haptic patterns, and one tick per tap
        pats = pg.evaluate("""(async()=>{const out={};for(const k of ['light','success','warning','error']){S.hapAt=0;__vib.length=0;hap(k);await new Promise(z=>setTimeout(z,10));out[k]=__vib[0];}return out;})()""")
        print(tag, "patterns:", pats)
        if len(set(pats.values())) != 4: bad(f"{tag}: haptic patterns aren't distinct: {pats}")
        time.sleep(.3); n0 = pg.evaluate("__haps.length"); chip = pg.locator("main h2 .chip").nth(1); chip.click(); time.sleep(.3)
        got = pg.evaluate(f"__haps.slice({n0})")
        print(tag, "chip tap haptics:", got)
        if got != ["selection"]: bad(f"{tag}: a chip tap should tick exactly once (selection), got {got}")
        pg.evaluate("S.filter='all';renderLive()"); time.sleep(.3)

        # ---- press feedback + haptic coverage on every screen
        for view in ("live", "games", "build", "results", "settings"):
            pg.evaluate(f"go('{view}')"); time.sleep(5 if view == "build" else 3)
            if view == "build": pg.evaluate("S.adv=true;renderBuild()"); time.sleep(.6)
            a = pg.evaluate(AUDIT)
            print(tag, view, "interactive:", a["n"], "| no haptic/press:", a["miss"][:5], "| press not shown:", a["nopress"][:5])
            if a["n"] < 5: bad(f"{tag} {view}: the audit found almost nothing to check ({a['n']})")
            if a["miss"]: bad(f"{tag} {view}: interactive elements without press feedback/haptic: {a['miss'][:6]}")
            if a["nopress"]: bad(f"{tag} {view}: press state didn't show on: {a['nopress'][:6]}")
            n0 = pg.evaluate("__haps.length")
            if tag == "phone":
                pg.locator(".tabbar button").nth(0 if view != "live" else 1).click(); time.sleep(.4)
                if pg.evaluate(f"__haps.slice({n0})")[:1] != ["selection"]: bad(f"{tag} {view}: tab bar tap gave no selection tick")
        pg.evaluate("go('live')"); time.sleep(3); pg.evaluate("window.scrollTo(0,0)"); time.sleep(.4)

        # ---- the hero chart: scrub with readout and haptic ticks; refreshes wait; release restores
        box = pg.locator(".sparkw[data-chart]").bounding_box()
        before = pg.evaluate("document.querySelector('.hv .big').textContent")
        n0 = pg.evaluate("__haps.length"); y = box["y"] + box["height"] / 2
        pg.mouse.move(box["x"] + box["width"] * .2, y); pg.mouse.down()
        for k in range(12): pg.mouse.move(box["x"] + box["width"] * (.2 + k * .05), y); time.sleep(.12)
        st = pg.evaluate("({on:document.querySelector('.sparkw').classList.contains('on'),big:document.querySelector('.hv .big').textContent,read:document.querySelector('.sread').textContent,scrub:S.scrub})")
        pg.evaluate("renderLive()"); still = pg.evaluate("document.querySelector('.sparkw').classList.contains('on')")
        ticks = pg.evaluate(f"__haps.slice({n0}).filter(k=>k==='selection').length")
        pg.mouse.up(); time.sleep(.4)
        after = pg.evaluate("({on:document.querySelector('.sparkw').classList.contains('on'),big:document.querySelector('.hv .big').textContent,scrub:S.scrub})")
        print(tag, "scrub:", st, "ticks:", ticks, "| held during refresh:", still, "| after:", after, "| before:", before)
        if not st["on"] or not st["read"] or not st["big"].startswith("$"): bad(f"{tag}: scrubbing didn't show the line, readout and value")
        if ticks < 3: bad(f"{tag}: scrubbing gave only {ticks} haptic ticks")
        if not still: bad(f"{tag}: a refresh mid-scrub tore the chart down")
        if after["on"] or after["scrub"] or after["big"].replace("≈ ", "") != before.replace("≈ ", ""): bad(f"{tag}: releasing didn't put the live value back")

        # ---- Day / Week
        dpts = pg.evaluate("S.chart.pts.length")
        pg.locator(".rng2 button", has_text="Week").click()
        ok = wait(pg, "S.rng==='week'&&!!S.chart&&S.chart.pts.length>0", 8)
        wpts = pg.evaluate("S.chart?S.chart.pts.length:0"); on = pg.evaluate("document.querySelector('.rng2 button.on').textContent")
        print(tag, "range: day", dpts, "week", wpts, "on:", on)
        if not ok or on != "Week" or wpts <= dpts: bad(f"{tag}: Week range didn't load a longer history")
        pg.locator(".rng2 button", has_text="Day").click(); time.sleep(.6)
        if pg.evaluate("S.rng") != "day": bad(f"{tag}: back to Day didn't take")

        # ---- rolling numbers and sliding bars on Live rows
        roll = pg.evaluate("""(async()=>{const c=S.live.combos.find(x=>x.group==='pending'&&x.p!=null);if(!c)return null;const k='p:'+c.t;c.p=Math.min(.99,c.p+.2);renderLive();
          const el=document.querySelector(`[data-num="${k}"]`),bar=document.querySelector(`[data-bar="pb:${c.t}"]`);const fl=el&&(el.classList.contains('fl-up'));
          const w0=bar&&getComputedStyle(bar).width;await new Promise(z=>setTimeout(z,900));return {fl,moving:w0!==getComputedStyle(bar).width,txt:el.textContent,want:pct(c.p)};})()""")
        print(tag, "roll:", roll)
        if not roll or not roll["fl"] or not roll["moving"] or roll["txt"] != roll["want"]: bad(f"{tag}: chance didn't roll / bar didn't slide: {roll}")
        pg.evaluate("window.load=async()=>{}")          # no refreshes from here on: the page holds still for the checks

        # ---- push into a game: slide, dimmed page, skeleton, then content; Back closes
        t = pg.evaluate("(S.live.games&&S.live.games[0]&&S.live.games[0].ticker)||S.live.combos.find(c=>c.group==='pending').legs[0].ticker")
        pg.evaluate("window.__f0=window.fetch;window.fetch=(u,o)=>String(u).includes('/app/api/game')?new Promise(z=>setTimeout(()=>z(window.__f0(u,o)),700)):window.__f0(u,o)")
        pg.evaluate(f"(openGame('{t}'),1)"); time.sleep(.08)          # not awaited: look at it mid-slide
        mid = pg.evaluate("""(()=>{const tx=new DOMMatrix(getComputedStyle(document.querySelector('#sheet')).transform).m41;
          return {push:$('#modal').classList.contains('push'),on:$('#modal').classList.contains('on'),pushed:document.body.classList.contains('pushed'),
           tx,skel:!!document.querySelector('#sheet .psk'),dur:getComputedStyle(document.querySelector('#sheet')).transitionDuration,back:!!document.querySelector('#sheet .pbar .back')};})()""")
        time.sleep(.5)
        late = pg.evaluate("({skel:!!document.querySelector('#sheet .psk'),tx:new DOMMatrix(getComputedStyle(document.querySelector('#sheet')).transform).m41,main:new DOMMatrix(getComputedStyle(document.querySelector('main')).transform).m41,dim:getComputedStyle(document.querySelector('main')).filter})")
        got = wait(pg, "!!document.querySelector('#sheet .dkpis')&&!document.querySelector('#sheet .psk')", 10)
        print(tag, "push mid:", mid, "| at 0.6s:", late, "| content:", got)
        if not (mid["push"] and mid["on"] and mid["pushed"] and mid["skel"] and mid["back"]): bad(f"{tag}: the push page didn't open with a skeleton and Back: {mid}")
        if not (0 < mid["tx"]): bad(f"{tag}: the page didn't slide in (tx {mid['tx']})")
        if mid["dur"].split(",")[0].strip() != "0.27s": bad(f"{tag}: push isn't ~270 ms ({mid['dur']})")
        if not late["skel"] or abs(late["tx"]) > 1: bad(f"{tag}: the slide should finish with the skeleton still up while loading: {late}")
        if "brightness" not in late["dim"]: bad(f"{tag}: the page behind isn't dimmed")
        if tag == "phone" and not late["main"] < -50: bad(f"{tag}: the page behind didn't slide left ({late['main']})")
        if not got: bad(f"{tag}: the game content never replaced the skeleton")
        pg.evaluate("window.fetch=window.__f0")
        pg.locator("#sheet .pbar .back").click(); time.sleep(.6)
        closed = pg.evaluate("({on:$('#modal').classList.contains('on'),pushed:document.body.classList.contains('pushed'),push:$('#modal').classList.contains('push'),g:S.gameOpen})")
        print(tag, "after Back:", closed)
        if closed["on"] or closed["pushed"] or closed["push"] or closed["g"]: bad(f"{tag}: Back didn't close the page cleanly: {closed}")
        # a bottom sheet right after a push is a plain sheet, not a pushed page
        pg.evaluate(f"openGame('{t}')"); time.sleep(.5); pg.evaluate("closeModal();modal('<h3>Sure?</h3>')"); time.sleep(.5)
        sh = pg.evaluate("({push:$('#modal').classList.contains('push'),wide:$('#sheet').classList.contains('wide'),on:$('#modal').classList.contains('on')})")
        if sh["push"] or sh["wide"] or not sh["on"]: bad(f"{tag}: a confirmation after a push kept the push layout: {sh}")
        pg.evaluate("closeModal()"); time.sleep(.5)
        # the combo page pushes the same way
        ct = pg.evaluate("S.live.combos.find(c=>c.group==='pending').t")
        pg.evaluate(f"openCombo('{ct}')")
        if not wait(pg, "$('#modal').classList.contains('push')&&!!document.querySelector('#sheet .dkpis')", 10): bad(f"{tag}: the combo page didn't push in")
        pg.evaluate("closeModal()"); time.sleep(.5)

        if tag == "phone":           # swipe right from the page to go back
            pg.evaluate(f"openGame('{t}')"); wait(pg, "!!document.querySelector('#sheet .dkpis')", 10)
            cdp = ctx.new_cdp_session(pg)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": 40, "y": 420}]})
            for x in range(60, 300, 30): cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": 424}]}); time.sleep(.03)
            mv = pg.evaluate("document.querySelector('#sheet').style.transform")
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}); time.sleep(.6)
            print(tag, "swipe back: moved", mv, "| open after:", pg.evaluate("$('#modal').classList.contains('on')"))
            if "translateX" not in mv or pg.evaluate("$('#modal').classList.contains('on')"): bad(f"{tag}: swiping right didn't follow the finger and close the page")
            if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{tag}: the page scrolls sideways")
        print(tag, "errs:", errs)
        if errs: bad(f"{tag}: JS errors {errs[:3]}")
        ctx.close()

    # reduced motion: everything still works and nothing animates
    ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", reduced_motion="reduce", has_touch=True)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script("localStorage.setItem('cw_view','live')")
    pg.goto(B + "/app"); wait(pg, "!!document.querySelector('.sparkw[data-chart]')", 25); time.sleep(.5)
    rm = pg.evaluate("({anim:getComputedStyle(document.querySelector('.spark')).animationName,clip:getComputedStyle(document.querySelector('.spark')).clipPath})")
    t = pg.evaluate("(S.live.games&&S.live.games[0]&&S.live.games[0].ticker)||S.live.combos.find(c=>c.group==='pending').legs[0].ticker")
    pg.evaluate(f"openGame('{t}')"); ok = wait(pg, "!!document.querySelector('#sheet .dkpis')", 10)
    tx = pg.evaluate("new DOMMatrix(getComputedStyle(document.querySelector('#sheet')).transform).m41")
    print("reduced motion:", rm, "| page open:", ok, "tx", tx, "| errs", errs)
    if rm["anim"] != "none" or not ok or abs(tx) > 1 or errs: bad("reduced motion: the chart animates or the game page doesn't open")
    ctx.close(); br.close()

db = sqlite3.connect("wahome/combo_history.db"); db.execute("delete from pulse"); db.commit(); db.close()
print("PROBLEMS: " + " | ".join(problems) if problems else "all motion checks passed")
