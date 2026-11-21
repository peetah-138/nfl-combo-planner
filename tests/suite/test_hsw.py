# CHECK: group=page secs=160
"""Method N, the default haptic (GitHub #60): on iOS 27 only the finger's own tap on a real <input type=checkbox switch>
ticks, so every tappable control carries a see-through switch that covers it (.hsw, its first child).
Checked on every tab at phone (iPhone, touch) and desktop (forced on) sizes: each control has one switch covering its
box and the switch is what a tap at the control's centre hits; nothing moves when the switches go in; a tap reaches the
control's own handler exactly once (and lands on the switch); links still open once; disabled buttons stay dead; a
scroll that starts on a control clicks nothing; Haptics off and reduced motion remove the switches; no sideways scroll
or JS errors; 300 new controls get their switches quickly and none twice. Prints PROBLEMS on any failure."""
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)

import upwait
# Counts the page's view transitions in flight (a tab change paints inside one; until it ends, a tap or elementFromPoint
# hits the transition's overlay, not the controls)
VT = r"""(()=>{const s=document.startViewTransition;if(!s)return;window.__vt=0;document.startViewTransition=function(cb){const t=s.call(document,cb);window.__vt++;
  const end=()=>{window.__vt--};t.finished.then(end,end);return t;};})()"""

def frames(pg, n=2):
    """n animation frames, then every finite CSS animation/transition finished (the header tucking in after a scroll,
    a tab's entrance stagger): the box checks compare positions, and WebKit moves a running transition along between
    two reads in the same script. Endless ones (a spinner, the live dot) don't count."""
    pg.evaluate("n=>new Promise(z=>{const f=k=>k?requestAnimationFrame(()=>f(k-1)):z();f(n)})", n)
    pg.wait_for_function("""document.getAnimations().every(a=>a.playState!=='running'||!isFinite(a.effect.getComputedTiming().endTime))""", timeout=15000)

def show(pg, view):
    """Opens a tab and waits for state, not a fixed time: its own loads done (Results' analytics included), the tab's
    view transition over; then the page is held still (no background refresh), so the checks below never race a redraw
    that swaps every control for a new one (the old fixed sleeps lost that race now and then on a busy runner)."""
    upwait.go_and_hold(pg, view)
    pg.wait_for_function("!(window.__vt>0)", timeout=30000); frames(pg)

def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        if pg.evaluate(js): return True
        time.sleep(.2)
    return False

IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
INIT = r"""window.__hits=[];window.__hit=(el,e)=>{window.__hits.push({k:el.dataset.hk,t:e&&e.target&&e.target.className,tr:e&&e.isTrusted});};"""

# every visible control: covered by exactly one switch of its own, and a tap at its centre lands on a switch inside it
COVER = r"""(()=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[hidden]')&&!(e.closest('#modal')&&!$('#modal').classList.contains('on'));};
 const all=[...document.querySelectorAll(HSWQ)].filter(e=>vis(e)&&!e.closest(HSWNO)&&!e.querySelector(HSWIN)&&!e.disabled&&getComputedStyle(e).pointerEvents!=='none');
 // #151: big scroll surfaces (whole cards and rows) carry no switch, so a scroll that starts on them is never caught
 const bigs=all.filter(e=>hswBig(e)),hosts=all.filter(e=>!hswBig(e)),bigsw=bigs.filter(e=>e.querySelector(':scope>.hsw')).map(e=>e.tagName+'.'+e.className+':'+(e.innerText||'').trim().slice(0,18));
 const miss=[],twice=[],box=[],hit=[];let inview=0;
 hosts.forEach(h=>{const sw=h.querySelectorAll(':scope>.hsw'),nm=h.tagName+'.'+h.className+':'+(h.innerText||'').trim().slice(0,18);
  if(sw.length!==1){(sw.length?twice:miss).push(nm);return;}
  const a=h.getBoundingClientRect(),b=sw[0].getBoundingClientRect(),cs=getComputedStyle(h);
  const bl=parseFloat(cs.borderLeftWidth)||0,bt=parseFloat(cs.borderTopWidth)||0,br=parseFloat(cs.borderRightWidth)||0,bb=parseFloat(cs.borderBottomWidth)||0;
  if(h.matches('a')&&cs.display==='inline')return;   // an inline link's box is its line fragments
  if(Math.abs(b.left-a.left-bl)>1.5||Math.abs(b.top-a.top-bt)>1.5||Math.abs(b.right-a.right+br)>1.5||Math.abs(b.bottom-a.bottom+bb)>1.5)box.push(nm);
  if(a.right<0||a.bottom<70||a.left>innerWidth||a.top>innerHeight-90)return;inview++;
  // the centre and four inner points: each must land on a switch inside this control (its own or a nested control's)
  for(const [fx,fy] of [[.5,.5],[.2,.3],[.8,.3],[.2,.7],[.8,.7]]){const x=a.left+a.width*fx,y=a.top+a.height*fy;if(x<0||x>innerWidth||y<70||y>innerHeight-90)continue;const t=document.elementFromPoint(x,y);
   if(!t||t===h||!h.contains(t))continue;   // something outside the control covers that point (a sticky bar): not this test's business
   if(bigs.some(g=>g!==h&&h.contains(g)&&g.contains(t)))continue;   // a big card inside this control: that point is scroll surface
   if(!t.classList.contains('hsw')){hit.push(nm+' @'+fx+','+fy+' -> '+t.tagName+'.'+(t.getAttribute('class')||''));break;}}});
 return {n:hosts.length,big:bigs.length,bigsw:bigsw.slice(0,6),inview,miss:miss.slice(0,6),twice:twice.slice(0,6),box:box.slice(0,6),hit:hit.slice(0,8),nhit:hit.length};})()"""

# nothing moves when the switches go in: every element's box with the switches off vs on
MOVE = r"""(()=>{const els=[...document.querySelectorAll('header *,main *,.tabbar *,#sheet *')].filter(e=>!e.classList.contains('hsw'));
 const snap=()=>els.map(e=>{const r=e.getBoundingClientRect();return [r.left,r.top,r.width,r.height];});
 hapSet(false);const off=snap();hapSet(true);const on=snap();const moved=[];
 els.forEach((e,i)=>{if(off[i].some((v,j)=>Math.abs(v-on[i][j])>.5))moved.push(e.tagName+'.'+e.className+' '+off[i].map(Math.round)+' -> '+on[i].map(Math.round));});
 return {n:els.length,moved:moved.slice(0,6),nmoved:moved.length,sw:document.querySelectorAll('.hsw').length};})()"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    try: wk = pw.webkit.launch()            # Safari's engine: the switch-inside-a-button and tap paths, as close to iOS as a test gets
    except Exception as e: wk = None; print("WebKit not installed here, skipping its pass:", str(e).splitlines()[0][:90])
    for vw, vh, tag in ((390, 844, "phone"), (1280, 900, "desk"), (390, 844, "webkit")):
        if tag == "webkit":
            if not wk: continue
            ctx = wk.new_context(viewport={"width": vw, "height": vh}, has_touch=True, user_agent=IOS, color_scheme="dark")
        elif tag == "phone": ctx = br.new_context(viewport={"width": vw, "height": vh}, has_touch=True, user_agent=IOS, color_scheme="dark")
        else: ctx = br.new_context(viewport={"width": vw, "height": vh}, color_scheme="light")
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/app/api/act", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "msg": "Got it."})))
        pg.add_init_script(INIT + ("" if tag != "desk" else "window.__hswForce=1;") + "localStorage.setItem('cw_view','live');localStorage.removeItem('cw_hapoff')")
        pg.add_init_script(upwait.COUNT_FETCHES); pg.add_init_script(VT)
        pg.goto(B + "/app")
        show(pg, "live")
        if not wait(pg, "document.querySelectorAll('.hsw').length>3", 25): bad(f"{tag}: the switches never went in")
        if not pg.evaluate("hswOn()&&document.documentElement.classList.contains('hswon')"): bad(f"{tag}: method N isn't on")
        for view in ("live", "games", "build", "results", "settings"):
            show(pg, view)
            if view == "build": pg.evaluate("S.adv=true;renderBuild()"); frames(pg)
            for sy in (0, 650, 1300, 0):   # the whole page, a screen at a time (back to the top last)
                pg.evaluate(f"window.scrollTo(0,{sy})"); frames(pg)
                c = pg.evaluate(COVER)
                if c["bigsw"]: bad(f"{tag} {view}: a big card/row carries a switch (it can catch a scroll): {c['bigsw']}")
                print(tag, view, sy, "controls:", c["n"], "big (no switch):", c["big"], "in view:", c["inview"], "| no switch:", c["miss"], "| two:", c["twice"], "| box off:", c["box"], "| misses:", c["nhit"], c["hit"][:4])
                if c["n"] < 5: bad(f"{tag} {view}: found almost no controls ({c['n']})")
                if c["miss"] or c["twice"]: bad(f"{tag} {view}: controls without exactly one switch: {c['miss']} {c['twice']}")
                if c["box"]: bad(f"{tag} {view}: a switch doesn't cover its control's box: {c['box']}")
                if c["nhit"]: bad(f"{tag} {view}: a tap inside a control misses its switch: {c['hit']}")
            m = pg.evaluate(MOVE)
            print(tag, view, "elements:", m["n"], "moved:", m["nmoved"], m["moved"][:3])
            if m["nmoved"]: bad(f"{tag} {view}: the switches moved things: {m['moved']}")
            if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{tag} {view}: sideways scroll")

            # a tap reaches the control's own handler exactly once, through its switch (handlers swapped for counters)
            pg.evaluate("""(()=>{let k=0;document.querySelectorAll('[onclick]').forEach(e=>{e.dataset.hk=++k;e.setAttribute('onclick','__hit(this,event)');});window.__hits.length=0;})()""")
            keys = pg.evaluate("""(()=>{const out=[];for(const e of document.querySelectorAll('main [onclick],.tabbar [onclick]')){if(out.length>=6)break;const s=e.querySelector(':scope>.hsw');if(!s||e.matches('a')||e.querySelector('[onclick]'))continue;
              const r=e.getBoundingClientRect();if(r.width<8||r.height<8||r.top<60||r.bottom>innerHeight-90)continue;const t=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);if(t!==s)continue;out.push(e.dataset.hk);}return out;})()""")
            for k in keys:
                pg.evaluate("window.__hits.length=0")
                bb = pg.locator(f'[data-hk="{k}"]').bounding_box()
                pg.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2) if tag == "desk" else pg.touchscreen.tap(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
                time.sleep(.15)
                h = pg.evaluate("window.__hits.slice()")
                mine = [x for x in h if x["k"] == k]
                if len(mine) != 1 or mine[0]["t"] != "hsw" or not mine[0]["tr"]: bad(f"{tag} {view}: a tap on control {k} reached its handler {len(mine)} times (target {mine[:1]})")
            print(tag, view, "tapped once each:", len(keys))
            # Games: its cards are big scroll surfaces (no switch, #151); the COVER check above asserts that
            if len(keys) < (0 if view == "games" else 1 if view == "results" else 3): bad(f"{tag} {view}: too few controls to tap-test ({len(keys)})")
            pg.evaluate(f"go('{view}')"); frames(pg)   # (held: a redraw from what the page has, no load)

        # the pushed game page (a sheet) is covered too
        show(pg, "games")
        g = pg.locator(".gc").first.bounding_box(timeout=10000)
        if not g: bad(f"{tag}: no game card to open")
        else:
            pg.mouse.click(g["x"] + 30, g["y"] + 20) if tag == "desk" else pg.touchscreen.tap(g["x"] + 30, g["y"] + 20)
            if not wait(pg, "$('#modal').classList.contains('on')&&!!document.querySelector('#sheet .back>.hsw')", 10): bad(f"{tag}: the game page didn't open from its switch, or its Back has no switch")
            time.sleep(1.2); c = pg.evaluate(COVER)
            print(tag, "game page controls:", c["n"], "| no switch:", c["miss"], "| two:", c["twice"], "| box off:", c["box"], "| misses:", c["hit"][:4])
            if c["miss"] or c["twice"] or c["box"] or c["nhit"]: bad(f"{tag}: game page switches: {c}")
            pg.evaluate("closeModal()"); time.sleep(.6)

        # links: no switch (it would take their navigation and long-press menu), still open once; disabled: nothing;
        # a nested button wins over its row; a field appearing inside a control takes its switch away
        show(pg, "live")
        pg.evaluate("""(()=>{const d=document.createElement('div');d.id='tz';d.style.cssText='position:fixed;left:10px;top:120px;z-index:99;background:var(--panel);padding:8px';
          d.innerHTML=`<a id="la" href="#zz" onclick="__hit(this,event)" data-hk="la" style="display:inline-block;padding:10px">hash link</a>
           <a id="lb" href="/app?popup=1" target="_blank" onclick="__hit(this,event)" data-hk="lb" style="display:inline-block;padding:10px">new tab</a>
           <button id="bd" disabled onclick="__hit(this,event)" data-hk="bd">off</button>
           <div class="trow" id="rw" onclick="__hit(this,event)" data-hk="rw" style="display:flex;gap:8px;padding:12px">row text <button id="rb" onclick="event.stopPropagation();__hit(this,event)" data-hk="rb">inner</button></div>`;document.body.appendChild(d);})()""")
        time.sleep(.2)
        pg.evaluate("window.__hits.length=0")
        pg.locator("#la").click(); time.sleep(.2)
        la = pg.evaluate("({h:__hits.map(x=>x.k),hash:location.hash})")
        with ctx.expect_page(timeout=5000) as pop: pg.locator("#lb").click()
        pop.value.close(); time.sleep(.3)
        lb = pg.evaluate("__hits.filter(x=>x.k==='lb').length")
        pg.evaluate("window.__hits.length=0"); pg.locator("#bd").click(force=True); time.sleep(.2)
        bd = pg.evaluate("({h:__hits.length,sw:document.querySelectorAll('#bd>.hsw').length,disp:getComputedStyle(document.querySelector('#bd>.hsw')||document.body).display})")
        pg.evaluate("window.__hits.length=0"); pg.locator("#rb").click(); time.sleep(.2); rb = pg.evaluate("__hits.map(x=>x.k+':'+x.t)")
        pg.evaluate("window.__hits.length=0"); pg.locator("#rw").click(position={"x": 20, "y": 15}); time.sleep(.2); rw = pg.evaluate("__hits.map(x=>x.k+':'+x.t)")
        nol = pg.evaluate("document.querySelectorAll('a[href]>.hsw').length")
        pg.evaluate("document.querySelector('#rw').insertAdjacentHTML('beforeend','<input id=\"rf\" style=\"width:60px\">')"); time.sleep(.1)
        fld = pg.evaluate("({sw:document.querySelectorAll('#rw>.hsw').length,hit:document.elementFromPoint(...(r=>[r.left+r.width/2,r.top+r.height/2])(document.querySelector('#rf').getBoundingClientRect())).id})")
        print(tag, "link switches:", nol, "| field inside a row:", fld)
        if nol: bad(f"{tag}: links must not carry a switch ({nol})")
        if fld["sw"] or fld["hit"] != "rf": bad(f"{tag}: a field that appears inside a control must get its taps (the switch goes): {fld}")
        print(tag, "links:", la, lb, "| disabled:", bd, "| inner:", rb, "| row:", rw)
        if la["h"] != ["la"] or la["hash"] != "#zz": bad(f"{tag}: a link didn't run its onclick once and follow its href: {la}")
        if lb != 1: bad(f"{tag}: a new-tab link ran its onclick {lb} times")
        if bd["h"] or (bd["sw"] and bd["disp"] != "none"): bad(f"{tag}: a disabled button reacted or kept a live switch: {bd}")
        if rb != ["rb:hsw"]: bad(f"{tag}: a button inside a row should get the tap through its own switch, alone: {rb}")
        if rw != ["rw:hsw"]: bad(f"{tag}: the row itself should get its own tap through its switch: {rw}")
        pg.evaluate("history.replaceState(null,'',location.pathname);document.getElementById('tz').remove()")

        # a scroll that starts on a control clicks nothing and flips nothing
        if tag == "phone":   # (CDP touch: Chromium only)
            show(pg, "build"); pg.evaluate("S.adv=true;renderBuild()"); frames(pg)
            pg.evaluate("""(()=>{let k=0;document.querySelectorAll('[onclick]').forEach(e=>{e.dataset.hk=++k;e.setAttribute('onclick','__hit(this,event)');});window.__hits.length=0;window.__swc=0;
              addEventListener('click',e=>{if(e.target.classList.contains('hsw'))window.__swc++;},true);window.scrollTo(0,0);})()""")
            pt = pg.evaluate("""(()=>{for(const s of document.querySelectorAll('main .hsw')){const r=s.getBoundingClientRect();if(r.top>250&&r.bottom<700&&r.height>20&&r.width>60&&document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)===s)return [r.left+r.width/2,r.top+r.height/2];}return null;})()""")
            if not pt: bad("phone: no control to start a scroll on")
            else:
                cdp = ctx.new_cdp_session(pg); y0 = pg.evaluate("scrollY")
                cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": pt[0], "y": pt[1]}]})
                for i in range(1, 13):
                    cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": pt[0], "y": pt[1] - i * 18}]}); time.sleep(.016)
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}); time.sleep(.6)
                sc = pg.evaluate("({dy:scrollY-%f,hits:__hits.length,sw:__swc})" % y0)
                print("phone scroll from a control:", sc)
                if sc["dy"] < 40: bad(f"phone: the drag didn't scroll the page ({sc})")
                if sc["hits"] or sc["sw"]: bad(f"phone: a scroll that started on a control clicked it or flipped its switch ({sc})")
                # and a plain tap at the same place still clicks once
                pg.evaluate("window.scrollTo(0,0);__hits.length=0;window.__swc=0"); time.sleep(.3); pg.touchscreen.tap(pt[0], pt[1]); time.sleep(.2)
                tp = pg.evaluate("({hits:__hits.length,sw:__swc})")
                if tp != {"hits": 1, "sw": 1}: bad(f"phone: a plain tap where the scroll started should click once: {tp}")
            pg.evaluate("go('build')"); time.sleep(1)

        # #151: a vertical drag that starts on a big card or row (a Live combo row, a Games card, a Build card) scrolls
        # the page and clicks nothing: those carry no switch; their compact buttons inside keep theirs. Chromium can't
        # copy iOS's switch catching the touch, so the CSS and DOM that prevent it are checked too.
        if tag == "phone":
            cdp = ctx.new_cdp_session(pg)
            for view, sel in (("live", "main .trow"), ("games", "main .gc"), ("build", "main [onclick]:not(.sech),main .trow")):
                show(pg, view)
                pg.evaluate("""(()=>{let k=0;document.querySelectorAll('[onclick]').forEach(e=>{e.dataset.hk=++k;e.setAttribute('onclick','__hit(this,event)');});window.__hits.length=0;window.__swc=0;
                  if(!window.__swl){window.__swl=1;addEventListener('click',e=>{if(e.target.classList.contains('hsw'))window.__swc++;},true);}
                  document.querySelector('main').style.paddingBottom='1600px';window.scrollTo(0,0);})()""")
                time.sleep(.4)
                info = pg.evaluate("""(sel=>{const nm=e=>e.tagName+'.'+e.className+':'+(e.innerText||'').trim().slice(0,16);
                  const bigs=[...document.querySelectorAll(sel)].filter(e=>e.matches(HSWQ)&&!e.closest(HSWNO)&&hswBig(e));
                  for(const g of bigs){let r=g.getBoundingClientRect();window.scrollTo(0,0);window.scrollTo(0,Math.max(0,scrollY+r.top-160));r=g.getBoundingClientRect();if(r.top<90||r.top>560)continue;
                   // a point on the card's own surface (not on a compact control inside it)
                   for(const [fx,fy] of [[.5,.5],[.15,.5],[.85,.5],[.5,.2],[.5,.8]]){const x=r.left+r.width*fx,y=r.top+Math.min(r.height,180)*fy;const t=document.elementFromPoint(x,y);
                    if(!t||!g.contains(t)||t.classList.contains('hsw'))continue;const h=t.closest(HSWQ);if(h!==g)continue;
                    const inner=[...g.querySelectorAll(HSWQ)].filter(e=>!hswBig(e)&&e.getBoundingClientRect().width>0);
                    return {pt:[x,y],y0:scrollY,name:nm(g),names:bigs.slice(0,6).map(nm),own:g.querySelectorAll(':scope>.hsw').length,inner:inner.length,innersw:inner.filter(e=>e.querySelector(':scope>.hsw')||e.closest(HSWNO)||e.querySelector(HSWIN)).length,n:bigs.length};}}
                  return {pt:null,n:bigs.length,names:bigs.slice(0,4).map(nm)};})""", sel)
                print("phone", view, "big card to scroll from:", info)
                if not info["pt"]: bad(f"phone {view}: no big card or row to start a scroll on ({info})"); continue
                if info["own"]: bad(f"phone {view}: the big card carries a switch: {info}")
                if info["inner"] != info["innersw"]: bad(f"phone {view}: a compact control inside the card lost its switch: {info}")
                time.sleep(.3); x, y = info["pt"]; y0 = pg.evaluate("scrollY")
                cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
                for i in range(1, 13):
                    cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y - i * 18}]}); time.sleep(.016)
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}); time.sleep(.6)
                sc = pg.evaluate("({dy:scrollY-%f,hits:__hits.length,sw:__swc})" % y0)
                print("phone", view, "scroll from a big card:", sc)
                if sc["dy"] < 40: bad(f"phone {view}: a drag from a big card didn't scroll the page ({sc})")
                if sc["hits"] or sc["sw"]: bad(f"phone {view}: a scroll from a big card clicked something ({sc})")
                pg.evaluate("document.querySelector('main').style.paddingBottom='';window.scrollTo(0,0)"); time.sleep(.3)
            # while the finger scrolls, the switches let touches through (html.hswscr), back ~150 ms after the last
            # scroll; the app's own scrolls (no finger) leave them alone
            pg.evaluate("document.querySelector('main').style.paddingBottom='1600px';window.scrollTo(0,0)"); time.sleep(.4)
            pe = "(()=>{const sw=document.querySelector('main .hsw');return {pe:getComputedStyle(sw).pointerEvents,cls:document.documentElement.classList.contains('hswscr'),ta:getComputedStyle(sw).touchAction,hta:getComputedStyle(sw.parentElement).touchAction};})()"
            idle = pg.evaluate(pe)
            app = pg.evaluate("(async()=>{window.scrollBy(0,40);await new Promise(z=>setTimeout(z,60));return document.documentElement.classList.contains('hswscr');})()")
            time.sleep(.3)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": 200, "y": 100}]})
            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": 200, "y": 70}]})
            # each reading is taken in the page right after its scroll event, in one evaluate: the class lives ~150 ms
            # past the last scroll and a momentum scroll counts within 200 ms of the finger's, so readings taken over
            # Python round trips (sleep, then evaluate) went stale on a busy runner. The finger lifting is the page's
            # own touchend listener seeing a touchend (the real one from CDP follows, to release the touch point).
            seq = pg.evaluate("""(async()=>{const PE=%s;const scr=()=>new Promise(z=>{addEventListener('scroll',()=>z(),{once:true,capture:true});window.scrollBy(0,40);});
              await scr();const mid=PE();
              dispatchEvent(new TouchEvent('touchend',{bubbles:true}));await scr();const still=PE();   // momentum after the finger lifts
              return {mid,still};})()""" % ("()=>" + pe))
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            # once the finger is up and the page has had no scroll for 350 ms (the browser may still apply the drag's
            # own scroll after the touchend), the switches take taps again
            after = pg.evaluate("""(async()=>{let last=performance.now();const on=()=>{last=performance.now()};addEventListener('scroll',on,{capture:true});
              const t0=performance.now();while(performance.now()-last<350&&performance.now()-t0<8000)await new Promise(z=>setTimeout(z,50));
              removeEventListener('scroll',on,{capture:true});return Object.assign((%s)(),{waited:Math.round(performance.now()-t0)});})()""" % ("()=>" + pe))
            mid, still = seq["mid"], seq["still"]
            pg.evaluate("document.querySelector('main').style.paddingBottom='';window.scrollTo(0,0)"); time.sleep(.3)
            sc = {"idle": idle, "app": app, "mid": mid, "still": still, "after": after}
            print("phone scrolling class:", sc)
            if idle["pe"] == "none" or after["pe"] == "none" or after["cls"]: bad(f"phone: switches should take taps when the page is still: {sc}")
            if app: bad(f"phone: the app's own scroll (no finger) shouldn't turn the switches off: {sc}")
            if mid["pe"] != "none" or still["pe"] != "none" or not mid["cls"]: bad(f"phone: switches should let touches through while the finger scrolls: {sc}")
            if idle["ta"] != "manipulation" or idle["hta"] != "manipulation": bad(f"phone: switches and their controls must allow native panning (touch-action): {sc}")
            src = pg.evaluate("document.documentElement.outerHTML")
            blk = src[src.index("const HSWQ="):src.index("hswSync();", src.index("const HSWQ="))]
            tl = re.search(r"\['touchstart','touchend','touchcancel'\]\.forEach\(k=>addEventListener\(k,[^\n]*passive:true", blk)
            tm = re.findall(r"addEventListener\('touch\w+'[^\n]*", blk)
            if blk.count("preventDefault") != 1 or any("passive:true" not in x for x in tm) or "pointerdown" in blk or not tl:
                bad("phone: the switch code's touch listeners must be passive and must never block the browser's scrolling")

        # performance: 300 new buttons get one switch each, in one batch, quickly; a re-render never doubles them;
        # their 300 card-sized rows (#151: scroll surfaces) get none, also once laid out
        perf = pg.evaluate("""(async()=>{const d=document.createElement('div');d.id='pz';d.innerHTML=Array.from({length:300},(_,i)=>`<div class="trow" style="min-height:80px" onclick="__hit(this,event)"><span>row ${i}</span><button class="btn">b${i}</button></div>`).join('');
          const t0=performance.now();hswScan(d);const sync=performance.now()-t0;const n1=d.querySelectorAll('.hsw').length;
          d.querySelectorAll('.hsw').forEach(s=>s.remove());document.querySelector('main').appendChild(d);const t1=performance.now();await new Promise(z=>setTimeout(z,0));const obs=performance.now()-t1;
          const n2=d.querySelectorAll('.hsw').length;d.querySelectorAll('button').forEach(b=>{b.textContent=b.textContent;});await new Promise(z=>setTimeout(z,0));
          hswScan(d);hswScan(d);const n3=d.querySelectorAll('.hsw').length,dup=[...d.querySelectorAll('button')].filter(e=>e.querySelectorAll(':scope>.hsw').length!==1).length+[...d.querySelectorAll('.trow')].filter(e=>e.querySelector(':scope>.hsw')).length;d.remove();
          return {sync:Math.round(sync),obs:Math.round(obs),n1,n2,n3,dup,total:document.querySelectorAll('.hsw').length};})()""")
        print(tag, "300 rows + 300 buttons:", perf)
        if perf["n1"] != 300 or perf["n2"] != 300 or perf["n3"] != 300 or perf["dup"]: bad(f"{tag}: switches missing, doubled or on big rows among 600 new controls: {perf}")
        dbl = pg.evaluate("(()=>{const b=document.createElement('button');b.textContent='x';document.querySelector('main').appendChild(b);hswRun([b,b]);const n=b.querySelectorAll('.hsw').length;b.remove();return n;})()")
        if dbl != 1: bad(f"{tag}: a control listed twice in one batch got {dbl} switches")
        # a small row that grows into a card loses its switch; a control revealed later (class change) gets one
        lat = pg.evaluate("""(async()=>{const f=()=>new Promise(z=>requestAnimationFrame(()=>setTimeout(z,30)));const m=document.querySelector('main');
          const r=document.createElement('div');r.className='trow';r.setAttribute('onclick','void 0');r.style.cssText='width:120px;height:40px';r.innerHTML='<span>small</span>';m.appendChild(r);await f();const a=r.querySelectorAll(':scope>.hsw').length;
          r.style.height='120px';r.querySelector('span').textContent='grown';await f();const b=r.querySelectorAll(':scope>.hsw').length;r.remove();
          const w=document.createElement('div');w.style.display='none';w.className='zz';w.innerHTML='<span onclick="void 0" style="display:inline-block;padding:8px">later</span>';m.appendChild(w);
          for(let i=0;i<40;i++)await f();const c=w.querySelectorAll('.hsw').length;w.style.display='';w.className='zz on';await f();await f();const d=w.querySelectorAll('.hsw').length;w.remove();
          return {small:a,grown:b,hidden:c,shown:d};})()""")
        print(tag, "grow/reveal:", lat)
        if lat != {"small": 1, "grown": 0, "hidden": 0, "shown": 1}: bad(f"{tag}: a control that grows or is revealed later has the wrong switch: {lat}")
        if perf["sync"] > 150: bad(f"{tag}: wrapping 600 controls took {perf['sync']} ms")
        if perf["total"] > 1500: bad(f"{tag}: too many switches in the page ({perf['total']})")

        # Haptics off removes every switch (and stops adding them); on brings them back
        pg.evaluate("hapSet(false)"); time.sleep(.2); pg.evaluate("go('live')"); time.sleep(1.5)
        off = pg.evaluate("({n:document.querySelectorAll('.hsw').length,cls:document.documentElement.classList.contains('hswon')})")
        pg.evaluate("hapSet(true)"); time.sleep(.3); on = pg.evaluate("document.querySelectorAll('.hsw').length")
        print(tag, "haptics off:", off, "back on:", on)
        if off["n"] or off["cls"]: bad(f"{tag}: Haptics off left switches: {off}")
        if on < 5: bad(f"{tag}: Haptics on didn't bring the switches back ({on})")
        print(tag, "JS errors:", errs[:3])
        if errs: bad(f"{tag}: JS errors {errs[:3]}")
        ctx.close()

    # reduced motion: no switches at all
    ctx = br.new_context(viewport={"width": 390, "height": 844}, has_touch=True, user_agent=IOS, reduced_motion="reduce")
    pg = ctx.new_page(); pg.goto(B + "/app"); time.sleep(4)
    rm = pg.evaluate("({n:document.querySelectorAll('.hsw').length,on:hswOn()})")
    print("reduced motion:", rm)
    if rm["n"] or rm["on"]: bad(f"reduced motion should have no switches: {rm}")
    # not an iPhone/iPad (and no force): no switches
    ctx2 = br.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    pg2 = ctx2.new_page(); pg2.goto(B + "/app"); time.sleep(4)
    if pg2.evaluate("document.querySelectorAll('.hsw').length"): bad("a non-Apple phone got switches")
    br.close()
    if wk: wk.close()
print("PROBLEMS:" if problems else "no problems", problems)
