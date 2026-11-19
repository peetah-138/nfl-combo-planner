"""Makeover phase 3: every remaining screen in the same motion system. Checked on a phone (390x844, touch) in dark and
light, and on a desktop: no JS errors and no sideways scroll anywhere; press feedback + a haptic on everything you can
tap (the phase 1 audit, now also on Build's full board, the panel, an open sheet and the login page); the calm
reconnecting banner with its freshness stamp (and "Back online"); an error card with Try again when a screen can't
load; the header tucking in on scroll; pull to refresh on every tab (rubber band, ring, tick, check); a keyboard-aware
sheet; Let it ride as a slider with haptic detents; Mac buttons that spin then show Done / Didn't work, and Update now
asking first; Build's rolling prices, pick pop, slip bar entrance, quote countdown bar, Buy anyway, fold chevrons,
panel sparklines and the arming Approve button; Results' skeleton, "updated just now" and tab crossfade; the morning
recap's streak note; light mode and reduced motion. No real orders: every action call is faked. Prints PROBLEMS."""
import requests
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        if pg.evaluate(js): return True
        time.sleep(.2)
    return False

P = open("panel_fixture.json").read()
AN = {"at": time.time(), "levels": [{"band": "80–85%", "n": 12, "hit": 0.2, "exp": 0.25, "ride": -0.21, "gt": -0.15, "gt_n": 10, "lab_n": 3, "lab_ride": -0.4, "lab_smart": 0.1},
      {"band": "95–100%", "n": 44, "hit": 0.3, "exp": 0.29, "ride": 0.03, "gt": None, "gt_n": 0, "lab_n": 0, "lab_ride": None, "lab_smart": None}],
      "types": [{"mode": "real", "what": "Spreads & totals", "n": 6, "won": 4, "pl": 3.2, "roi": 0.12, "clv": 0.02, "smart": 0.14, "sim_n": 4}],
      "sports": [{"mode": "real", "what": "NHL", "n": 6, "won": 4, "pl": 3.2, "roi": 0.12, "clv": 0.02, "smart": 0.1, "sim_n": 2}],
      "exits": [{"what": "Rode to the end", "n": 10, "pl": -12, "roi": -0.2}], "auto": {}, "notes": []}
INFO = {"ok": True, "watcher": "v1", "engine": "v1", "up": 1300, "role": "main", "paused": False, "auto_update": True, "waiting": "", "latest": "v1", "checked": time.time() - 400}

AUDIT = r"""(()=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[hidden]')&&!(e.closest('#modal')&&!$('#modal').classList.contains('on'));};
 const all=[...document.querySelectorAll('header *,main *,.tabbar *,#sheet *')].filter(e=>vis(e)&&!e.closest('#hapl'));
 const want=all.filter(e=>e.matches('button,a[href],select,label,input[type=checkbox],input[type=range],[onclick]')||(getComputedStyle(e).cursor==='pointer'&&!e.closest('.sparkw')));
 const miss=want.filter(e=>!e.disabled&&!tapEl(e)).map(e=>e.tagName+'.'+e.className+':'+(e.innerText||'').slice(0,20));
 let nopress=[];want.slice(0,90).forEach(e=>{const t=tapEl(e);if(!t)return;e.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,pointerType:'touch'}));
  if(!t.classList.contains('prs'))nopress.push(t.tagName+'.'+t.className);e.dispatchEvent(new PointerEvent('pointercancel',{bubbles:true}));});
 return {n:want.length,miss,nopress};})()"""
SIDE = "document.documentElement.scrollWidth>innerWidth+1"

def fake(pg, acts):
    def act(r):
        body = json.loads(r.request.post_data or "{}"); acts.append(body)
        a = body.get("a")
        out = {"ok": True, "pays": 30, "stake": 5, "pct": .9, "clears": False, "cut": 95} if a == "quote" else {"ok": True, "msg": "Got it."}
        r.fulfill(status=200, content_type="application/json", body=json.dumps(out))
    pg.route("**/app/api/act", act)                                  # never a real order or sale
    pg.route("**/app/api/analytics", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(AN)))
    pg.route("**/app/api/panel?*", lambda r: r.fulfill(status=200, content_type="application/json", body=P))
    pg.route("**/app/mac-info", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(INFO)))
    pg.route("**/app/mac-check", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "msg": "The Mac is checking now."})))
    def sets(r):                                                    # settings changes are answered here, never saved
        if r.request.method == "POST": acts.append(json.loads(r.request.post_data or "{}")); return r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))
        r.continue_()
    pg.route("**/app/api/settings*", sets)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, scheme, tag in ((390, 844, "dark", "phone"), (390, 844, "light", "phone-light"), (1280, 900, "dark", "desk"), (1280, 900, "light", "desk-light")):
        phone = vw < 600
        ctx = br.new_context(viewport={"width": vw, "height": vh}, color_scheme=scheme, has_touch=phone)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.dismiss())
        acts = []; fake(pg, acts)
        pg.add_init_script("window.__haps=[];if(!sessionStorage.getItem('k')){localStorage.clear();sessionStorage.setItem('k','1');}localStorage.setItem('cw_view','live')")
        pg.goto(B + "/app")
        if not wait(pg, "!!(S.live&&S.live.combos)", 25): bad(f"{tag}: Live never loaded")
        time.sleep(1)
        # ---- light mode is really light; dark is dark; the native controls follow
        th = pg.evaluate("({bg:getComputedStyle(document.body).backgroundColor,cs:getComputedStyle(document.documentElement).colorScheme,meta:[...document.querySelectorAll('meta[name=theme-color]')].map(m=>m.media+'|'+m.content)})")
        lum = sum(int(x) for x in re.findall(r"\d+", th["bg"])[:3]) / 3
        print(tag, "theme:", th, "lum", round(lum))
        if (scheme == "light") != (lum > 180) or th["cs"] != scheme or len(th["meta"]) != 2: bad(f"{tag}: the {scheme} theme isn't applied: {th}")

        # ---- every screen: no errors, no sideways scroll, every control has press feedback and a haptic
        for view in ("live", "games", "build", "results", "settings"):
            pg.evaluate(f"go('{view}')"); time.sleep(4.5 if view == "build" else 3)
            if view == "build":
                pg.evaluate("S.panel=" + P + ";S.adv=true;renderBuild()"); time.sleep(.6)
            if view == "settings": wait(pg, "!!S.set&&!!document.querySelector('.scard')", 15); time.sleep(.5)
            a = pg.evaluate(AUDIT)
            print(tag, view, "interactive:", a["n"], "| missing:", a["miss"][:4], "| no press:", a["nopress"][:4])
            if a["n"] < 5: bad(f"{tag} {view}: the audit found almost nothing ({a['n']})")
            if a["miss"] or a["nopress"]: bad(f"{tag} {view}: controls without press feedback/haptic: {a['miss'][:4]} {a['nopress'][:4]}")
            if phone and pg.evaluate(SIDE): bad(f"{tag} {view}: the page scrolls sideways")
        if tag not in ("phone", "desk"):
            print(tag, "errs:", errs)
            if errs: bad(f"{tag}: JS errors {errs[:3]}")
            ctx.close(); continue

        # ---- an open sheet is audited too, and asks before Update now (nothing sent until you confirm)
        pg.evaluate("go('settings')"); wait(pg, "!!document.querySelector('#ride')", 15); time.sleep(.6)
        n_act = len(acts)
        pg.evaluate("macUpdate(document.createElement('button'))"); time.sleep(.6)
        sh = pg.evaluate("({on:$('#modal').classList.contains('on'),t:$('#sheet h3').textContent})")
        a = pg.evaluate(AUDIT)
        if not sh["on"] or "Update the Mac" not in sh["t"]: bad(f"{tag}: Update now didn't ask first: {sh}")
        if a["miss"] or a["nopress"]: bad(f"{tag}: the sheet has controls without press/haptic: {a['miss'][:3]} {a['nopress'][:3]}")
        if phone:
            r = pg.evaluate("getComputedStyle($('#sheet')).borderTopLeftRadius")
            if r != "22px": bad(f"{tag}: the phone sheet isn't a rounded bottom sheet ({r})")
        pg.evaluate("closeModal()"); time.sleep(.4)

        # ---- Let it ride: a slider with a haptic detent at each step; the name pops; the dots follow; it saves
        n0 = pg.evaluate("__haps.length")
        steps = pg.evaluate("""(async()=>{const el=$('#ride'),out=[];for(const v of [0,1,2,3,4]){el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));
          await new Promise(z=>setTimeout(z,130));out.push([el.parentNode.querySelector('output').textContent,[...el.parentNode.querySelectorAll('.tks i')].findIndex(i=>i.classList.contains('at'))]);}
          el.value=3;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return out;})()""")
        ticks = pg.evaluate(f"__haps.slice({n0}).filter(k=>k==='selection').length")
        wait(pg, "/Saved/.test(($('#saved')||{}).textContent||'')", 6)          # polling lets the faked save answer
        print(tag, "ride:", steps, "ticks:", ticks, "saved:", [x for x in acts if "values" in x][-1:])
        if [s[1] for s in steps] != [0, 1, 2, 3, 4] or len({s[0] for s in steps}) != 5: bad(f"{tag}: Let it ride's detents don't move the name/dots: {steps}")
        if ticks < 5: bad(f"{tag}: Let it ride gave {ticks} haptic ticks for 5 detents")
        if not any((x.get("values") or {}).get("ride") == 3 for x in acts): bad(f"{tag}: Let it ride didn't save its value")
        if pg.evaluate("S.set.values.ride") != 3: bad(f"{tag}: Let it ride's value didn't stick")

        # ---- Mac buttons: spin, then Done / Didn't work on the button itself
        pg.route("**/app/mac", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "msg": "Sent."})))
        st = pg.evaluate("""(async()=>{const b=document.createElement('button');b.className='btn';b.textContent='Send test';document.querySelector('main').appendChild(b);
          const p=macDo('testpush',b);const mid={dis:b.disabled,spin:!!b.querySelector('.spin')};await p;return {mid,cls:b.className,txt:b.textContent};})()""")
        print(tag, "mac button:", st)
        if not st["mid"]["dis"] or not st["mid"]["spin"] or "st-ok" not in st["cls"] or "Sent" not in st["txt"]: bad(f"{tag}: a Mac button didn't show working -> done: {st}")
        pg.unroute("**/app/mac"); pg.route("**/app/mac", lambda r: r.abort())
        st = pg.evaluate("""(async()=>{const b=document.createElement('button');b.className='btn';b.textContent='Send test';document.querySelector('main').appendChild(b);await macDo('testpush',b);return {cls:b.className,txt:b.textContent};})()""")
        if "st-bad" not in st["cls"]: bad(f"{tag}: a failed Mac action didn't show on its button: {st}")
        pg.unroute("**/app/mac"); time.sleep(1.8)

        # ---- keyboard-aware sheet: the passcode sheet rides above the keyboard
        pg.evaluate("macPass()"); time.sleep(.5); pg.evaluate("kbSet(300)"); time.sleep(.5)
        kb = pg.evaluate("({pad:getComputedStyle($('#modal')).paddingBottom,bottom:$('#sheet').getBoundingClientRect().bottom,h:innerHeight})")
        pg.evaluate("kbSet(0);closeModal()"); time.sleep(.4)
        print(tag, "keyboard:", kb)
        if kb["pad"] != "300px" or (phone and kb["bottom"] > kb["h"] - 299): bad(f"{tag}: the sheet doesn't rise above the keyboard: {kb}")

        # ---- the reconnecting banner: shows after a moment with the freshness stamp, says Back online, then goes
        pg.evaluate("go('live')"); time.sleep(2)
        pg.evaluate("S.esEver=true;S.live_ok=false;stat()"); time.sleep(.4)
        early = pg.evaluate("!!document.querySelector('#netbar.on')")
        ok = wait(pg, "!!document.querySelector('#netbar.on')", 4); time.sleep(.6)
        nb = pg.evaluate("({t:$('#netbar').textContent,below:$('#netbar').getBoundingClientRect().top>=$('.top').getBoundingClientRect().bottom-1})")
        print(tag, "banner:", nb, "early:", early)
        if early or not ok or "Reconnecting" not in nb["t"] or "Updated" not in nb["t"] or not nb["below"]: bad(f"{tag}: the reconnecting banner is wrong: {nb} early={early}")
        pg.evaluate("S.live_ok=true;stat()"); time.sleep(.3)
        back = pg.evaluate("$('#netbar').className+'|'+$('#netbar').textContent")
        gone = wait(pg, "!document.querySelector('#netbar.on')", 4)
        if "ok" not in back or "Back online" not in back or not gone: bad(f"{tag}: the banner didn't say Back online and leave: {back} {gone}")
        # a failed request counts too
        pg.route("**/app/api/live*", lambda r: r.abort())
        pg.evaluate("load('live',true)")
        if not wait(pg, "!!document.querySelector('#netbar.on:not(.ok)')", 5): bad(f"{tag}: a failed request didn't bring the banner up")
        pg.unroute("**/app/api/live*"); pg.evaluate("load('live',true)")
        if not wait(pg, "!document.querySelector('#netbar.on')", 6): bad(f"{tag}: the banner stayed after the Mac answered")

        # ---- a screen that can't load at all: a calm error card with Try again (no endless skeleton)
        pg.route("**/app/api/games", lambda r: r.abort())
        pg.evaluate("S.games=null;localStorage.removeItem('cw_c_games');go('games')")
        okc = wait(pg, "!!document.querySelector('.card.err button')", 8)
        print(tag, "error card:", okc, pg.evaluate("(document.querySelector('.card.err')||{}).textContent"))
        if not okc: bad(f"{tag}: Games shows no error card when it can't load")
        pg.unroute("**/app/api/games")
        if okc:
            pg.locator(".card.err button").click()
            if not wait(pg, "!document.querySelector('.card.err')&&!!S.games", 10): bad(f"{tag}: Try again didn't bring the screen back")

        # ---- Build: panel cards, rolling prices, the pick pop, slip bar, quote countdown, Buy anyway, folds
        pg.evaluate("go('build')"); wait(pg, "!!(S.build&&S.build.board)", 15); time.sleep(.8)
        pg.evaluate("localStorage.setItem('cw_pxh',JSON.stringify({'single:B':[[Date.now()/1000-3600,.41],[Date.now()/1000-1800,.44]]}));S.pxh=null;S.panel=" + P + ";S.adv=true;renderBuild()"); time.sleep(.5)
        sp = pg.evaluate("({n:document.querySelectorAll('.pitem .psp').length,on:!!document.querySelector('.pitem[data-pid=\"single:B\"] .psp path'),num:document.querySelectorAll('.pitem [data-num^=\"ps:\"]').length})")
        print(tag, "panel:", sp)
        if not sp["on"] or sp["num"] < 4: bad(f"{tag}: panel cards lack the price line / rolling stake: {sp}")
        n0 = pg.evaluate("__haps.length")
        pg.locator(".panel .btn.acc", has_text="Approve").first.click(); time.sleep(.3)
        arm = pg.evaluate(f"({{cls:(document.querySelector('.panel .btn.arm')||{{}}).className,t:(document.querySelector('.panel .btn.arm')||{{}}).textContent,haps:__haps.slice({n0})}})")
        if not arm["cls"] or "Tap again" not in (arm["t"] or "") or "warning" not in arm["haps"]: bad(f"{tag}: Approve didn't arm with a countdown: {arm}")
        if any(x.get("a") == "panel_approve" for x in acts): bad(f"{tag}: one tap approved the panel")
        pg.evaluate("renderBuild()")
        pg.evaluate("pToggle('line:D')"); time.sleep(.1)
        if not pg.evaluate("!!document.querySelector('.pitem.off.tog[data-pid=\"line:D\"]')"): bad(f"{tag}: leaving a bet out has no motion")
        pg.evaluate("pToggle('line:D')")
        roll = pg.evaluate("""(async()=>{const s=S.build.board[0].sides[0];const k='bp:'+s.ticker;s.p=Math.min(.97,(s.p||.4)+.06);renderBuild();
          const el=document.querySelector(`[data-num="${k}"]`);const fl=el&&el.classList.contains('fl-up');await new Promise(z=>setTimeout(z,900));
          return {fl,txt:el&&el.textContent,want:Math.round(s.p*100)+'¢'};})()""")
        print(tag, "price roll:", roll)
        if not roll["fl"] or roll["txt"] != roll["want"]: bad(f"{tag}: a board price didn't roll with a flash: {roll}")
        if pg.evaluate("S.build.board.length") < 2: bad(f"{tag}: the fake board has too few games")
        pk = pg.evaluate("""(()=>{const g=S.build.board[1];const s=g.sides[0];pick(s.ticker,g.event);
          const r={pop:!!document.querySelector('.pickbtn.on.pop'),bar:(document.querySelector('.slipbar')||{}).className||''};renderBuild();r.bar2=(document.querySelector('.slipbar')||{}).className||'';r.pop2=!!document.querySelector('.pickbtn.pop');return r;})()""")
        print(tag, "pick:", pk)
        if not pk["pop"] or (phone and ("in" not in pk["bar"].split() or "in" in pk["bar2"].split())) or pk["pop2"]: bad(f"{tag}: picking a team doesn't pop / the slip bar doesn't slide in once: {pk}")
        pg.evaluate("S.slip=[];S.slipWas=0;S.custom=null;renderBuild()")
        if pg.evaluate("(S.build.combos||[]).length"):
            ci = pg.evaluate("S.build.combos[0].i")
            pg.evaluate(f"S.bsec.combos=true;renderBuild();quote({ci})")
            ok = wait(pg, "!!document.querySelector('.ccard .qline .qt')", 8); time.sleep(.3)
            q = pg.evaluate("({anim:getComputedStyle(document.querySelector('.ccard .qline .qt')).animationName,bad:!!document.querySelector('.ccard .qline.bad'),btn:(document.querySelector('.ccard .btn.warn')||{}).textContent})") if ok else None
            print(tag, "quote:", q)
            if not ok or q["anim"] != "qdrain" or not q["bad"] or "Buy anyway" not in (q["btn"] or ""): bad(f"{tag}: the quote has no countdown bar / Buy anyway: {q}")
            if any(x.get("a") == "buy" for x in acts): bad(f"{tag}: something bought")
            pg.evaluate("S.quotes={};clearInterval(S.qT);renderBuild()")
        pg.evaluate("S.bsec.games=true;renderBuild();secTog('games')"); time.sleep(.45)
        fold = pg.evaluate("({rot:getComputedStyle(document.querySelector('.sech[data-k=games] .chev')).transform,folded:!!document.querySelector('.secfold')})")
        pg.evaluate("secTog('games')"); time.sleep(.05)
        unf = pg.evaluate("!!document.querySelector('.board.unfold')")
        print(tag, "fold:", fold, "unfold:", unf)
        if fold["rot"] in ("none", "matrix(1, 0, 0, 1, 0, 0)") or not fold["folded"] or not unf: bad(f"{tag}: folding a section doesn't turn the chevron / rise in: {fold} {unf}")
        if phone and pg.evaluate(SIDE): bad(f"{tag}: Build scrolls sideways")

        # ---- Results: What's working loads as a skeleton, says "just now", tabs crossfade; numbers roll
        pg.evaluate("go('results')"); wait(pg, "!!S.res", 15); time.sleep(.5)
        if not pg.evaluate("S.an=null;renderResults();!!document.querySelector('.an .ansk')"): bad(f"{tag}: What's working has no loading skeleton")
        upd = pg.evaluate("S.an=" + json.dumps(AN) + ";S.an.at=Date.now()/1000;renderResults();document.querySelector('.an .anh').textContent")
        if "just now" not in upd or "now ago" in upd: bad(f"{tag}: What's working says '{upd}'")
        x = pg.evaluate("anTab('types');({tab:!!document.querySelector('.an .antab'),rows:document.querySelectorAll('.an .anrow:not(.h)').length})")
        if not x["tab"] or x["rows"] < 1: bad(f"{tag}: switching What's working tabs has no motion: {x}")
        pg.evaluate("anTab('levels')")
        if phone and pg.evaluate(SIDE): bad(f"{tag}: Results scrolls sideways")

        # ---- the morning recap's streak note
        pg.evaluate("go('live')"); time.sleep(1.5); pg.evaluate("window.__ld=window.load;window.load=async()=>{}")
        base = "{day:'2026-11-18',bets:[{what:'Avalanche',pl:2.1}],pl:2.1,won:1,lost:0,best:{what:'Avalanche',pl:2.1},note:''"
        sk = {}
        for n in (4, 1, 0):
            pg.evaluate(f"S.recap={base},streak:{n}}};renderLive()"); time.sleep(.2)
            sk[n] = pg.evaluate("(()=>{const s=document.querySelector('.recap .streak');return s?{hot:s.classList.contains('hot'),t:s.textContent,dots:s.querySelectorAll('.dots i').length}:null})()")
        print(tag, "streak:", sk)
        if not sk[4] or not sk[4]["hot"] or sk[4]["dots"] != 4 or "4 days up" not in sk[4]["t"]: bad(f"{tag}: a 4-day streak isn't shown: {sk[4]}")
        if not sk[1] or sk[1]["hot"] or "1 day up" not in sk[1]["t"]: bad(f"{tag}: one good day isn't a gentle note: {sk[1]}")
        if sk[0]: bad(f"{tag}: a down day shows a streak note: {sk[0]}")
        pg.evaluate("S.recap=null;renderLive()")

        # ---- phone: the header tucks in on scroll; pull to refresh works on every tab
        if phone:
            pg.evaluate("window.load=window.__ld")
            pg.evaluate("go('results')"); wait(pg, "!!S.res", 10); time.sleep(.6)
            pg.evaluate("document.querySelector('main').style.minHeight='3000px';scrollTo(0,400)"); time.sleep(.5)
            hc = pg.evaluate("({hc:document.body.classList.contains('hc'),h:document.querySelector('.top').getBoundingClientRect().height})")
            pg.evaluate("scrollTo(0,0)"); time.sleep(.5)
            hx = pg.evaluate("({hc:document.body.classList.contains('hc'),h:document.querySelector('.top').getBoundingClientRect().height})")
            pg.evaluate("document.querySelector('main').style.minHeight=''")
            print(tag, "header:", hc, hx)
            if not hc["hc"] or hx["hc"] or not hc["h"] < hx["h"] - 4: bad(f"{tag}: the header doesn't tuck in on scroll: {hc} {hx}")
            cdp = ctx.new_cdp_session(pg)
            for view in ("results", "build", "settings"):
                pg.evaluate(f"go('{view}')"); time.sleep(3.5); pg.evaluate("scrollTo(0,0)"); time.sleep(.3)
                y0 = 480                     # the left gutter of the page, so the touch starts on no control
                pg.evaluate("window.__lv=[];window.load=(v,f)=>{__lv.push(v+':'+!!f);return window.__ld(v,f);}")
                n0 = pg.evaluate("__haps.length")
                cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": 6, "y": y0}]})
                for dy in range(0, 300, 25): cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": 6, "y": y0 + dy}]}); time.sleep(.02)
                mid = pg.evaluate("""(()=>{window.__done=0;const p=document.querySelector('#ptr');if(p)new MutationObserver(()=>{if(p.classList.contains('done'))window.__done=1;}).observe(p,{attributes:true});
                  return {ring:+(document.querySelector('#ptr circle')||{style:{}}).style.strokeDashoffset,main:getComputedStyle(document.querySelector('main')).transform,op:+getComputedStyle(p).opacity};})()""")
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                done = wait(pg, "window.__done===1", 15)          # the check shows for half a second; record it rather than race it
                h = pg.evaluate(f"__haps.slice({n0})"); lv = pg.evaluate("__lv")
                print(tag, view, "pull:", mid, "loaded:", lv, "haps:", h, "check:", done)
                if mid["main"] == "none" or mid["ring"] > 30 or mid["op"] < .5: bad(f"{tag} {view}: pulling doesn't move the page / fill the ring: {mid}")
                if f"{view}:true" not in lv or not done or "selection" not in h or "success" not in h: bad(f"{tag} {view}: pull to refresh didn't refresh with a tick and a check: {lv} {h} {done}")
                time.sleep(.8)
                pg.evaluate("window.load=window.__ld")
        print(tag, "errs:", errs)
        if errs: bad(f"{tag}: JS errors {errs[:3]}")
        ctx.close()

    # ---- the login page: motion, press feedback, haptics, light and dark, no sideways scroll
    PAGE = W.LOGIN_HTML.replace("__MSG__", "").replace("__FID__", "").replace("__HTTPS__", "").replace("__ICON__", W.ICON_PNG)
    for scheme in ("dark", "light"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, has_touch=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("http://login.test/**", lambda r: r.fulfill(status=200, content_type="text/html", body=PAGE))
        pg.goto("http://login.test/login"); time.sleep(.2)
        lg = pg.evaluate("({anim:getComputedStyle(document.querySelector('.box h1')).animationName,logo:getComputedStyle(document.querySelector('.logo')).animationName,tr:getComputedStyle(document.querySelector('.go')).transitionProperty})")
        time.sleep(.8); pg.locator(".eye").click(); time.sleep(.2)
        h = pg.evaluate("window.__haps||[]")
        print("login", scheme, lg, "haps:", h, "errs:", errs)
        if lg["anim"] != "rise" or lg["logo"] != "pop" or "transform" not in lg["tr"]: bad(f"login {scheme}: no entrance motion/press feedback: {lg}")
        if "light" not in h: bad(f"login {scheme}: tapping gave no haptic")
        if pg.evaluate(SIDE) or errs: bad(f"login {scheme}: sideways scroll or JS errors {errs[:2]}")
        ctx.close()

    # ---- reduced motion: everything still works, nothing animates
    ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", reduced_motion="reduce", has_touch=True)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); acts = []; fake(pg, acts)
    pg.add_init_script("localStorage.setItem('cw_view','live')")
    pg.goto(B + "/app"); wait(pg, "!!(S.live&&S.live.combos)", 25); time.sleep(.5)
    for view in ("games", "build", "results", "settings", "live"):
        pg.evaluate(f"go('{view}')"); time.sleep(2.5)
    pg.evaluate("modal('<h3>Sure?</h3><p>x</p>')"); time.sleep(.3)
    rm = pg.evaluate("({stag:$('#sheet').classList.contains('stag'),fresh:$('#main').classList.contains('fresh')})")
    pg.evaluate("closeModal();S.esEver=true;S.live_ok=false;stat()"); time.sleep(1.6)
    rm["bar"] = pg.evaluate("document.querySelector('#netbar.on')?getComputedStyle(document.querySelector('#netbar i')).animationName+'/'+getComputedStyle(document.querySelector('#netbar')).transitionDuration:'none'")
    print("reduced motion:", rm, "errs:", errs)
    if rm["stag"] or rm["fresh"] or rm["bar"] not in ("none/0s",): bad(f"reduced motion: things still animate: {rm}")
    if errs: bad(f"reduced motion: JS errors {errs[:3]}")
    ctx.close(); br.close()

print("PROBLEMS: " + " | ".join(problems) if problems else "all phase 3 checks passed")
