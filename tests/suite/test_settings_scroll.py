# CHECK: group=page secs=60
"""Settings scrolls on an iPhone (GitHub #281). Method N puts a see-through switch (.hsw) over each tappable control, and a
switch under the finger can stop iOS scrolling (#151). The Settings section headers (.sfold) and the Mac line (.smac) are
full-width buttons; with most sections folded they covered about two thirds of a phone screen with switches, so swiping
the page mostly didn't scroll. Checked at 390x844 with an iPhone user agent (method N on), folded and unfolded:
- a drag that starts on every kind of Settings line (section header, Mac line, a switch row, a slider row, a choice row,
  the moved-to-Build row, the combo-mix rows, the Mac's facts and its buttons row) starts on the line itself, never on a
  see-through switch, a native switch or a slider (WebKit and Chromium);
- that drag scrolls the page by about the dragged amount and taps nothing: no section opens, no setting changes
  (Chromium: real touch events through CDP);
- at most a quarter of any screen of Settings is see-through switch (it was ~65% with the sections folded);
- the section header and the Mac line still work on a tap, and the small controls keep their switches.
Prints PROBLEMS on any failure."""
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])
import upwait

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)

IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
MAC = {"ok": True, "watcher": "2026.11.21.132", "engine": "2026.11.21.132", "latest": "2026.11.21.132", "up": 7400, "auto_update": True,
       "checked": 0, "role": "main", "paused": False}
# every kind of line on the Settings page, as a CSS selector (a row is found by the text it carries when one class covers many kinds)
KINDS = [("section header", ".sfold", ""), ("Mac line", ".smac", ""), ("switch row", "label.srow", ""), ("slider row", ".srow", ".rng:not(.rdet)"),
         ("Let it ride row", ".srow", ".rdet"), ("choice row", ".srow", ".seg"), ("moved-to-Build row", ".srow", "button.btn.ghost"),
         ("combo-mix row", ".mixr", ""), ("Mac facts", ".kv>div", ""), ("Mac buttons row", ".sact", "")]
# the buttons row is mostly its buttons (they keep their switches, by design): its own surface is the padding above them
EDGE = {".sact"}
# a point on the line's own surface (its text side), and what a finger landing there would touch
POINT = r"""(([sel,has,edge])=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&!e.closest('[hidden],.shut');};
 const els=[...document.querySelectorAll('main '+sel)].filter(e=>vis(e)&&(!has||e.querySelector(has)));if(!els.length)return null;const el=els[0];
 window.scrollTo(0,0);let r=el.getBoundingClientRect();window.scrollTo(0,Math.max(0,r.top-260));r=el.getBoundingClientRect();
 const pts=edge?[[.5,4/120],[.25,4/120],[.75,4/120]]:[[.12,.5],[.3,.5],[.5,.5],[.12,.3],[.2,.7]];
 for(const [fx,fy] of pts){const x=r.left+r.width*fx,y=r.top+(edge?120:Math.min(r.height,120))*fy;const t=document.elementFromPoint(x,y);
  if(!t||!el.contains(t)&&t!==el)continue;
  return {x,y,sy:scrollY,t:t.tagName.toLowerCase()+'.'+(t.getAttribute('class')||''),sw:t.classList.contains('hsw'),own:t.classList.contains('hsw')&&t.parentElement===el,
   nat:t.matches('input[switch]:not(.hsw),input[type=range]')};}
 return {x:-1};})"""
# share of a screen that is see-through switch, at the current scroll
COVER = r"""(()=>{let n=0,s=0;const who={};for(let y=140;y<innerHeight-90;y+=8)for(let x=4;x<innerWidth-4;x+=8){const t=document.elementFromPoint(x,y);if(!t)continue;n++;
  if(t.classList.contains('hsw')){s++;const k=t.parentElement.className||t.parentElement.tagName;who[k]=(who[k]||0)+1;}}
 return {pc:n?Math.round(s/n*100):0,who:Object.entries(who).sort((a,b)=>b[1]-a[1]).slice(0,4)};})()"""
STATE = "JSON.stringify([S.set&&S.set.values,[...document.querySelectorAll('.scard[data-sid]')].map(c=>c.classList.contains('shut'))])"

def frames(pg, n=3):
    pg.evaluate("n=>new Promise(z=>{const f=k=>k?requestAnimationFrame(()=>f(k-1)):z();f(n)})", n)

def open_settings(pg, folded):
    pg.evaluate("for(const k of Object.keys(localStorage))if(k.startsWith('cw_fold_set_'))localStorage.removeItem(k)")
    upwait.go_and_hold(pg, "settings")
    pg.wait_for_function("!!document.querySelector('main .sfold')&&!!S.set", timeout=30000)
    if not folded:   # every section on the page, whatever it has (a new one is measured too)
        pg.evaluate("document.querySelectorAll('.scard[data-sid]').forEach(c=>localStorage.setItem('cw_fold_set_'+c.dataset.sid,'1'))")
    pg.evaluate("renderSettings()"); time.sleep(.8)   # (held: a redraw from what the page has, so the fold choice above applies)
    pg.wait_for_function("document.querySelectorAll('main .hsw').length>3", timeout=15000)
    pg.evaluate("document.querySelector('main').style.paddingBottom='1400px'"); frames(pg)   # room to scroll from the last line too

with sync_playwright() as pw:
    br = pw.chromium.launch()
    try: wk = pw.webkit.launch()
    except Exception as e: wk = None; print("WebKit not installed here, skipping its pass:", str(e).splitlines()[0][:90])
    for tag in ("chromium", "webkit"):
        if tag == "webkit" and not wk: continue
        ctx = (wk if tag == "webkit" else br).new_context(viewport={"width": 390, "height": 844}, has_touch=True, user_agent=IOS, color_scheme="dark")
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/app/api/settings", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True})) if r.request.method == "POST" else r.continue_())
        pg.route("**/app/mac-info", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(MAC)))
        pg.add_init_script("localStorage.setItem('cw_view','live');localStorage.removeItem('cw_hapoff')"); pg.add_init_script(upwait.COUNT_FETCHES)
        pg.goto(B + "/app")
        if not pg.evaluate("hswOn()"): bad(f"{tag}: method N isn't on for an iPhone")
        cdp = ctx.new_cdp_session(pg) if tag == "chromium" else None
        for folded in (True, False):
            mode = "folded" if folded else "open"
            open_settings(pg, folded)
            # how much of each screen is switch (folded: the headers stack up and fill the screen)
            hmax = pg.evaluate("document.documentElement.scrollHeight-innerHeight-1400")
            for sy in range(0, max(1, hmax) + 1, 600):
                pg.evaluate(f"window.scrollTo(0,{sy})"); frames(pg)
                c = pg.evaluate(COVER)
                print(tag, mode, "scroll", sy, "switch share:", c)
                if c["pc"] > 25: bad(f"{tag} {mode}: {c['pc']}% of the screen at scroll {sy} is see-through switch, which can stop iOS scrolling: {c['who']}")
            seen = 0
            for name, sel, has in KINDS:
                p = pg.evaluate(POINT, [sel, has, sel in EDGE])
                if p is None:
                    if folded and name not in ("section header", "Mac line"): continue   # folded: only the first sections' lines show
                    if name == "moved-to-Build row": continue
                    bad(f"{tag} {mode}: no {name} on Settings to start a drag on"); continue
                if p["x"] < 0: bad(f"{tag} {mode}: couldn't find a point on the {name}'s own surface"); continue
                seen += 1
                if p["sw"] or p["nat"]: bad(f"{tag} {mode}: a drag from the {name} starts on {p['t']} (a switch under the finger can stop iOS scrolling)")
                if not cdp: print(tag, mode, name, "lands on", p["t"]); continue
                frames(pg); before = pg.evaluate(STATE); x, y = p["x"], p["y"]; y0 = pg.evaluate("scrollY")
                cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
                for i in range(1, 13):
                    cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y - i * 18}]}); time.sleep(.016)
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}); time.sleep(.45)
                dy = pg.evaluate("scrollY") - y0; after = pg.evaluate(STATE)
                print(tag, mode, name, "lands on", p["t"], "| dragged 216, scrolled", round(dy))
                if dy < 150: bad(f"{tag} {mode}: a drag from the {name} scrolled {round(dy)}px of 216")
                if after != before: bad(f"{tag} {mode}: a drag from the {name} changed a setting or a section")
            if seen < (2 if folded else 8): bad(f"{tag} {mode}: only {seen} kinds of Settings lines found")
            pg.evaluate("window.scrollTo(0,0)"); frames(pg)

        # the header and the Mac line still work on a tap; small controls keep their switches
        open_settings(pg, True)
        k = pg.evaluate("(()=>{const c=[...document.querySelectorAll('.scard.shut[data-sid]')][0];c.scrollIntoView({block:'center'});return c.dataset.sid;})()"); frames(pg)
        bb = pg.locator(f"#s-{k} .sfold").bounding_box()
        pg.touchscreen.tap(bb["x"] + 40, bb["y"] + bb["height"] / 2); time.sleep(.6)
        if pg.evaluate(f"document.getElementById('s-{k}').classList.contains('shut')"): bad(f"{tag}: a tap on a folded section's header didn't open it")
        # the Mac line: its tap reaches sJump('mac') (counted), which opens The Mac and starts a smooth scroll towards it.
        # Where that smooth scroll ends isn't asserted: Chromium's touch emulation stops it partway (the old code too), and
        # the header tucking back in after scrollTo(0,0) moves the line, so the tap waits for the page to settle first.
        pg.evaluate("window.scrollTo(0,0)"); time.sleep(.5); frames(pg)
        pg.wait_for_function("document.getAnimations().every(a=>a.playState!=='running'||!isFinite(a.effect.getComputedTiming().endTime))", timeout=10000)
        pg.evaluate("(()=>{window.__mj=[];const o=sJump;window.sJump=function(i){__mj.push(i);return o(i);};})()")
        bb = pg.locator(".smac").bounding_box()
        pg.touchscreen.tap(bb["x"] + 40, bb["y"] + bb["height"] / 2)
        try: pg.wait_for_function("__mj.includes('mac')&&scrollY>100&&!document.getElementById('s-mac').classList.contains('shut')", timeout=5000)
        except Exception: bad(f"{tag}: a tap on the Mac line didn't jump to The Mac: " + str(pg.evaluate("[__mj,scrollY]")))
        sm = pg.evaluate("(()=>{const c=[...document.querySelectorAll('main .seg button,main .stp button,main .sact .btn,main #sleagues .chip')].filter(e=>e.offsetWidth);return {n:c.length,sw:c.filter(e=>e.querySelector(':scope>.hsw')).length};})()")
        print(tag, "small controls with a switch:", sm)
        if sm["n"] < 5 or sm["sw"] != sm["n"]: bad(f"{tag}: small Settings controls lost their switches: {sm}")
        print(tag, "JS errors:", errs[:3])
        if errs: bad(f"{tag}: JS errors {errs[:3]}")
        ctx.close()
    br.close()
    if wk: wk.close()
print("PROBLEMS:" if problems else "no problems", problems)
