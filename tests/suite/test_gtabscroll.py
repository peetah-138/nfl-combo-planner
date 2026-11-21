"""The game page's tab row scrolls sideways on an iPhone (GitHub #218). Two causes, both fixed and both checked here at 390x844:
1. Every tab carried a see-through haptic switch (method N, #60), and WebKit's switch grabs a drag that starts on it as a
   slide of its own knob: the row, nothing but tabs, could not be dragged sideways. Controls inside sideways strips now get
   no switch (HSWX). Checked: no switch inside the tab row (or any other sideways-scrolling strip on any screen) on an
   iPhone, and in WebKit (Safari's engine) a drag that starts on a tab no longer flips a switch.
2. Every live redraw scrolled the row back to the chosen tab, so a row scrolled away snapped back within seconds; and a
   redraw replaced the row under the finger. Checked with real touch events (Chromium CDP): a drag scrolls the row, a redraw
   leaves it where the finger left it, no redraw happens while the finger is on it, and a tap still opens a tab.
Swipe-back and the tab haptics elsewhere are covered by test_pbptabs / test_hsw. Prints PROBLEMS."""
exec(open("test_gametabs.py").read().split("with sync_playwright() as pw:")[0])

STRIPS = r"""(()=>{const out=[];for(const e of document.querySelectorAll('main *,#sheet *')){const o=getComputedStyle(e).overflowX;
  if((o==='auto'||o==='scroll')&&e.scrollWidth>e.clientWidth+1&&e.querySelector('.hsw'))out.push(e.tagName+'.'+e.className+' ('+e.querySelectorAll('.hsw').length+' switches)');}
 return out;})()"""


def drag(cdp, x0, x1, y, steps=14):
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x0, "y": y}]})
    for i in range(1, steps + 1):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x0 + (x1 - x0) * i / steps, "y": y}]}); time.sleep(.02)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def row(pg):
    return pg.evaluate("(()=>{const r=document.querySelector('#sheet .gtabs'),b=r.getBoundingClientRect();return {over:r.scrollWidth-r.clientWidth,sl:r.scrollLeft,x:b.left,w:b.width,y:b.top+b.height/2,"
                       "sw:r.querySelectorAll('.hsw').length,tab:(r.querySelector('.gtab.on')||{}).dataset.tab};})()")


def run_touch(ctx, pg, label):
    probs = []
    state["g"] = game()
    pg.route("**/app/api/game*", answer)
    if not open_game(pg):
        return [label + ": game sheet didn't draw"]
    if not pg.evaluate("hswOn()"):
        probs.append(label + ": method N isn't on for an iPhone (the switch half of this test means nothing)")
    pg.evaluate("document.querySelector('#sheet').scrollTop=document.querySelector('#sheet .gtabs').offsetTop-80"); time.sleep(.6)
    r0 = row(pg)
    print(label, "row:", r0)
    if r0["over"] < 40:
        return probs + [label + ": the tab row doesn't overflow a phone screen, nothing to scroll " + repr(r0)]
    if r0["sw"]:
        probs.append(label + ": %d haptic switches sit on the tab row; on iOS each one grabs a sideways drag" % r0["sw"])
    cdp = ctx.new_cdp_session(pg)
    drag(cdp, r0["x"] + r0["w"] - 30, r0["x"] + 40, r0["y"]); time.sleep(.3)
    r1 = row(pg)
    print(label, "after a drag left:", r1)
    if r1["sl"] < r0["sl"] + 40:
        probs.append(label + ": a sideways drag on the tab row didn't scroll it (%s -> %s)" % (r0["sl"], r1["sl"]))
    if r1["tab"] != r0["tab"]:
        probs.append(label + ": the drag changed the tab (%s -> %s)" % (r0["tab"], r1["tab"]))
    if not pg.evaluate("document.querySelector('#modal').classList.contains('on')"):
        return probs + [label + ": the drag closed the game page"]
    # a live redraw later: the row stays where the finger left it (it used to snap back to the chosen tab)
    time.sleep(.7)
    state["g"] = game(chance=.31)
    if not redraw(pg):
        probs.append(label + ": the game page didn't redraw")
    time.sleep(.6)
    r2 = row(pg)
    print(label, "after a redraw:", r2)
    if abs(r2["sl"] - r1["sl"]) > 2:
        probs.append(label + ": a redraw moved the scrolled tab row (%s -> %s): it snaps back to the chosen tab" % (r1["sl"], r2["sl"]))
    # no redraw while a finger is on the row; it comes once the finger is off
    pg.evaluate("window.__mark=document.querySelector('#sheet .board2')")
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": r2["x"] + 100, "y": r2["y"]}]})
    state["g"] = game(chance=.36)
    pg.evaluate("S.gameSig=null;drawGame()"); time.sleep(1.0)
    if not pg.evaluate("document.querySelector('#sheet .board2')===window.__mark"):
        probs.append(label + ": the page redrew (replacing the tab row) while a finger was on the row")
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    if not until(pg, "document.querySelector('#sheet .board2')&&document.querySelector('#sheet .board2')!==window.__mark", 4):
        probs.append(label + ": the held redraw never came after the finger lifted")
    # a tap on a tab still opens it (and the row brings a half-hidden chosen tab into view)
    k = pg.evaluate("(()=>{const r=document.querySelector('#sheet .gtabs'),b=r.getBoundingClientRect();for(const t of r.querySelectorAll('.gtab:not(.on)')){const a=t.getBoundingClientRect();if(a.left>=b.left&&a.right<=b.right)return t.dataset.tab;}return null;})()")
    if not k:
        probs.append(label + ": no whole tab in view to tap")
    else:
        bb = pg.locator(f"#sheet .gtab[data-tab={k}]").bounding_box()
        pg.touchscreen.tap(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
        if not until(pg, f"document.querySelector('#sheet .gtab.on').dataset.tab==='{k}'&&!document.querySelector('#sheet .gpanel[data-tab={k}]').hidden", 4):
            probs.append(label + ": tapping the %s tab didn't open it" % k)
    s = pg.evaluate(STRIPS)
    if s:
        probs.append(label + ": haptic switches inside sideways-scrolling strips on the game page: %r" % s[:4])
    pg.evaluate("closeModal()"); time.sleep(.3)
    pg.unroute("**/app/api/game*")
    return probs


def run_screens(pg, label):
    """Every other sideways-scrolling strip in the app: none may carry haptic switches either."""
    probs = []
    pg.goto(B + "/app"); time.sleep(1.5)
    for v in ("live", "games", "build", "results", "settings"):
        pg.evaluate(f"go('{v}')"); time.sleep(3.5 if v in ("build", "results") else 2.5)
        s = pg.evaluate(STRIPS)
        print(label, v, "strips with switches:", s)
        if s:
            probs.append(label + " %s: haptic switches inside sideways-scrolling strips: %r" % (v, s[:4]))
    return probs


def run_webkit(pg, label):
    """Safari's engine: a drag that starts on a tab must not be taken by a switch (it was: the switch grabbed the pointer
    and flipped when let go, wherever the finger ended)."""
    probs = []
    state["g"] = game()
    pg.route("**/app/api/game*", answer)
    if not open_game(pg):
        return [label + ": game sheet didn't draw"]
    pg.evaluate("document.querySelector('#sheet').scrollTop=document.querySelector('#sheet .gtabs').offsetTop-80;"
                "window.__flip=0;addEventListener('click',e=>{if(e.target.classList&&e.target.classList.contains('hsw'))window.__flip++;},true)")
    time.sleep(.5)
    r = row(pg)
    if r["sw"]:
        probs.append(label + ": %d haptic switches on the tab row" % r["sw"])
    b = pg.locator("#sheet .gtab").nth(1).bounding_box()
    x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    pg.mouse.move(x, y); pg.mouse.down()
    for i in range(1, 10):
        pg.mouse.move(x - i * 12, y)
    pg.mouse.up(); time.sleep(.3)
    if pg.evaluate("window.__flip"):
        probs.append(label + ": a sideways drag that started on a tab was taken by its switch (it grabbed the pointer and clicked)")
    pg.evaluate("closeModal()"); time.sleep(.3)
    pg.unroute("**/app/api/game*")
    return probs


with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, probs = [], []
    ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", has_touch=True, user_agent=IOS)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script("localStorage.removeItem('cw_hapoff')")
    probs += run_touch(ctx, pg, "iphone")
    probs += run_screens(pg, "iphone")
    ctx.close()
    try:
        wk = pw.webkit.launch()
    except Exception as e:
        wk = None; print("webkit not installed, skipping its half:", str(e)[:80])
    if wk:
        ctx = wk.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", has_touch=True, user_agent=IOS)
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("localStorage.removeItem('cw_hapoff')")
        probs += run_webkit(pg, "webkit")
        ctx.close(); wk.close()
    print("errs:", errs)
    if errs:
        probs.append("JS errors")
    if probs:
        print("PROBLEMS:", probs)
    else:
        print("PASS the game tab row scrolls sideways")
    br.close()
