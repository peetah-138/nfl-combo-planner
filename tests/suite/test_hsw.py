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

def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        if pg.evaluate(js): return True
        time.sleep(.2)
    return False

IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
INIT = r"""window.__hits=[];window.__hit=(el,e)=>{window.__hits.push({k:el.dataset.hk,t:e&&e.target&&e.target.className,tr:e&&e.isTrusted});};"""

# every visible control: covered by exactly one switch of its own, and a tap at its centre lands on a switch inside it
COVER = r"""(()=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[hidden]')&&!(e.closest('#modal')&&!$('#modal').classList.contains('on'));};
 const hosts=[...document.querySelectorAll(HSWQ)].filter(e=>vis(e)&&!e.closest(HSWNO)&&!e.querySelector(HSWIN)&&!e.disabled&&getComputedStyle(e).pointerEvents!=='none');
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
   if(!t.classList.contains('hsw')){hit.push(nm+' @'+fx+','+fy+' -> '+t.tagName+'.'+(t.getAttribute('class')||''));break;}}});
 return {n:hosts.length,inview,miss:miss.slice(0,6),twice:twice.slice(0,6),box:box.slice(0,6),hit:hit.slice(0,8),nhit:hit.length};})()"""

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
        pg.goto(B + "/app")
        wait(pg, "document.querySelectorAll('.hsw').length>3", 25); time.sleep(2)
        if not pg.evaluate("hswOn()&&document.documentElement.classList.contains('hswon')"): bad(f"{tag}: method N isn't on")
        for view in ("live", "games", "build", "results", "settings"):
            pg.evaluate(f"go('{view}')"); time.sleep(5 if view == "build" else 3)
            if view == "build": pg.evaluate("S.adv=true;renderBuild()"); time.sleep(.8)
            for sy in (0, 650, 1300, 0):   # the whole page, a screen at a time (back to the top last)
                pg.evaluate(f"window.scrollTo(0,{sy})"); time.sleep(.4)
                c = pg.evaluate(COVER)
                print(tag, view, sy, "controls:", c["n"], "in view:", c["inview"], "| no switch:", c["miss"], "| two:", c["twice"], "| box off:", c["box"], "| misses:", c["nhit"], c["hit"][:4])
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
            if len(keys) < (1 if view in ("games", "results") else 3): bad(f"{tag} {view}: too few controls to tap-test ({len(keys)})")
            pg.evaluate(f"go('{view}')"); time.sleep(.5)

        # the pushed game page (a sheet) is covered too
        pg.evaluate("go('games')"); time.sleep(3)
        g = pg.locator(".gc").first.bounding_box()
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
        pg.evaluate("go('live')"); time.sleep(2)
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
            pg.evaluate("go('build')"); time.sleep(4); pg.evaluate("S.adv=true;renderBuild()"); time.sleep(.8)
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

        # performance: 300 new controls get one switch each, in one batch, quickly; a re-render never doubles them
        perf = pg.evaluate("""(async()=>{const d=document.createElement('div');d.id='pz';d.innerHTML=Array.from({length:300},(_,i)=>`<div class="trow" onclick="__hit(this,event)"><span>row ${i}</span><button class="btn">b${i}</button></div>`).join('');
          const t0=performance.now();hswScan(d);const sync=performance.now()-t0;const n1=d.querySelectorAll('.hsw').length;
          d.querySelectorAll('.hsw').forEach(s=>s.remove());document.querySelector('main').appendChild(d);const t1=performance.now();await new Promise(z=>setTimeout(z,0));const obs=performance.now()-t1;
          const n2=d.querySelectorAll('.hsw').length;d.querySelectorAll('button').forEach(b=>{b.textContent=b.textContent;});await new Promise(z=>setTimeout(z,0));
          hswScan(d);hswScan(d);const n3=d.querySelectorAll('.hsw').length,dup=[...d.querySelectorAll('.trow,button')].filter(e=>e.querySelectorAll(':scope>.hsw').length!==1).length;d.remove();
          return {sync:Math.round(sync),obs:Math.round(obs),n1,n2,n3,dup,total:document.querySelectorAll('.hsw').length};})()""")
        print(tag, "300 rows + 300 buttons:", perf)
        if perf["n1"] != 600 or perf["n2"] != 600 or perf["n3"] != 600 or perf["dup"]: bad(f"{tag}: switches missing or doubled on 600 new controls: {perf}")
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
