"""Settings > Test haptics (GitHub #60: no haptics felt on an iPhone running iOS 27 in the Home Screen app).
The card renders with one lettered button per method; every button runs its method synchronously inside its own tap
(and nothing else buzzes: the global tap listener leaves these buttons alone); each shows a "sent" flash; the
switch hap() toggles on an iPhone is laid out on screen (not display:none, not hidden, not parked off-screen) and an
iPhone that reports navigator.vibrate still gets the switch; the Haptics on/off switch silences it and is remembered.
Phone size. Prints PROBLEMS on any failure."""
import sqlite3
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)

SPY = r"""
window.__haps=[];window.__sw=[];window.__vib=[];window.__ev=[];
addEventListener('change',e=>{if(e.target&&e.target.matches&&e.target.matches('input[switch]'))window.__sw.push({id:(e.target.closest('.hapx')||{}).id||'visible',t:performance.now()});},true);
window.__swc=[];addEventListener('click',e=>{if(e.target&&e.target.classList&&e.target.classList.contains('hsw'))window.__swc.push(e.isTrusted);},true);   // the finger landing on a see-through switch (N)
navigator.vibrate=p=>{window.__vib.push(JSON.stringify(p));return true;};
localStorage.setItem('cw_view','settings');
"""
IDS = list("NABCDEFGHIJKLM")

def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        if pg.evaluate(js): return True
        time.sleep(.2)
    return False

with sync_playwright() as pw:
    br = pw.chromium.launch()
    # ---- a desktop-like Chromium: the card, every button, sync firing, the flash
    ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", has_touch=True)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script(SPY)
    pg.goto(B + "/app")
    if not wait(pg, "!!document.querySelector('#s-haptics')", 25): bad("the Test haptics card didn't render in Settings")
    time.sleep(.5)
    card = pg.evaluate("""(()=>{const c=document.querySelector('#s-haptics');if(!c)return null;
      return {title:c.querySelector('h3').textContent,sub:c.querySelector('header p').textContent,rows:[...c.querySelectorAll('.hxrow')].map(r=>r.dataset.m),
      ask:c.innerText.includes('Does it tick on every tap now? Tell Claude.'),marks:['A','B','C','D','E','F','J','K'].every(i=>c.querySelector('.hxrow[data-m='+i+']').innerText.includes('Did nothing on iOS 27'))&&['G','H','I'].every(i=>c.querySelector('.hxrow[data-m='+i+']').innerText.includes('Pete confirmed')),tog:!!c.querySelector('#hapon'),nav:[...document.querySelectorAll('.sidx a')].some(a=>a.textContent.includes('Haptics')),
      plain:['vibrate','not expected on iPhone','combo://haptic'].every(t=>c.innerText.includes(t))};})()""")
    print("card:", card)
    if not card: bad("no card"); card = {"rows": []}
    else:
        if card["title"] != "Test haptics" or card["sub"] != "Tap each button. Tell Claude which one you feel.": bad(f"card wording: {card['title']!r} / {card['sub']!r}")
        if card["rows"] != IDS: bad(f"the buttons should be N, A..M, got {card['rows']}")
        if not card["marks"]: bad("G/H/I should say Pete confirmed and A-F/J/K that they did nothing on iOS 27")
        if not card["ask"] or not card["tog"] or not card["nav"] or not card["plain"]: bad(f"card is missing the which-one line, the on/off switch, the side link or the vibrate/app labels: {card}")
    sc = pg.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    if not sc: bad("the Test haptics card makes the page scroll sideways on a phone")

    # no app tick may come from tapping a test button: only the method under test may buzz
    pg.evaluate("__haps.length=0;window.__hapt=[]")
    expect_sync = {"A": 1, "B": 1, "C": 1, "D": 1, "E": 2, "F": 1}      # switch changes inside the tap itself (F's second one comes 120 ms later)
    for i in "ABCDEF":
        row = pg.locator(f'.hxrow[data-m="{i}"]'); row.scroll_into_view_if_needed()
        pg.evaluate("""(i)=>{window.__sw.length=0;window.__t=null;const b=document.querySelector('.hxrow[data-m="'+i+'"] button');
          b.addEventListener('click',()=>{window.__t={hapt:(window.__hapt||[]).slice(-1)[0],sw:window.__sw.length};},{once:true});}""", i)
        row.locator("button").click()
        got = pg.evaluate("window.__t")
        print(i, "inside the tap:", got)
        if not got or got["hapt"] != i: bad(f"{i}: its method didn't run inside its own click (saw {got})")
        elif got["sw"] != expect_sync[i]: bad(f"{i}: expected {expect_sync[i]} switch toggle(s) inside the tap, saw {got['sw']}")
        if i == "F":
            time.sleep(.3)
            if len(pg.evaluate("__sw")) != 2: bad("F: the delayed second tick never came")
        flash = pg.evaluate(f"document.querySelector('.hxrow[data-m=\"{i}\"] .hxs').textContent")
        if flash != "sent ✓": bad(f"{i}: no 'sent' flash ({flash!r})")
        time.sleep(.2)
    if pg.evaluate("__haps.length") != 0: bad(f"tapping test buttons also fired the app's own tick: {pg.evaluate('__haps')}")
    if pg.evaluate("document.querySelectorAll('#hapA').length") != 1 or pg.evaluate("document.querySelectorAll('#hapl').length") != 1: bad("the shared switch elements should exist once each")
    if pg.evaluate("document.querySelectorAll('body>label.hapx').length") > 5: bad("fresh switches (D) are piling up in the page")

    # A is the old way (parked off-screen), B is on screen: that is the thing being compared
    lay = pg.evaluate("""(()=>{const f=id=>{const e=document.getElementById(id),r=e.getBoundingClientRect(),c=getComputedStyle(e);return {l:r.left,w:r.width,in:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&r.width>0,vis:c.visibility,disp:c.display,op:+c.opacity,pe:c.pointerEvents};};return {A:f('hapA'),B:f('hapl')};})()""")
    print("layout:", lay)
    if lay["A"]["in"]: bad("method A should be the old off-screen switch")
    b = lay["B"]
    if not (b["in"] and b["vis"] == "visible" and b["disp"] != "none" and b["op"] > 0 and b["pe"] != "none"): bad(f"the switch hap() uses isn't laid out on screen and visible to iOS: {b}")

    # the native ones: no code, one 'sent', no app tick
    for i in "GHI":
        pg.evaluate("__haps.length=0;window.__hapt=[]"); row = pg.locator(f'.hxrow[data-m="{i}"]'); row.scroll_into_view_if_needed()
        if i == "H": row.locator("input[switch]").click()
        else: row.locator("label.hxbtn").click(position={"x": 30, "y": 12})
        time.sleep(.2)
        n = pg.evaluate("(window.__hapt||[]).filter(x=>x===%r).length" % i)
        if n != 1: bad(f"{i}: a tap counted {n} times (a label clicks twice: label, then its switch)")
        if pg.evaluate("__haps.length") != 0: bad(f"{i}: the app's own tick fired on top of the native switch")
    chk = pg.evaluate("[...document.querySelectorAll('.hxrow[data-m=G] input, .hxrow[data-m=I] input')].map(i=>i.checked)")
    if chk != [True, True]: bad(f"the user's own tap should be the switch toggle for G and I, got {chk}")

    # J on finger down, K on finger up
    pg.evaluate("window.__hapt=[]")
    for i in "JK":
        row = pg.locator(f'.hxrow[data-m="{i}"]'); row.scroll_into_view_if_needed(); bb = row.locator("button").bounding_box()
        pg.mouse.move(bb["x"] + 20, bb["y"] + 10); pg.evaluate("window.__hapt=[]"); pg.mouse.down()
        down = pg.evaluate("window.__hapt.slice()"); pg.mouse.up(); up = pg.evaluate("window.__hapt.slice()")
        print(i, "down:", down, "up:", up)
        if (i == "J" and down != ["J"]) or (i == "K" and (down != [] or up != ["K"])): bad(f"{i}: fires on the wrong touch event (down {down}, up {up})")
    # L and M say so when they can't work here
    pg.locator('.hxrow[data-m="L"] button').click(); l_ok = pg.evaluate("document.querySelector('.hxrow[data-m=L] .hxs').textContent")
    pg.evaluate("Object.defineProperty(navigator,'vibrate',{value:undefined,configurable:true})")
    pg.locator('.hxrow[data-m="L"] button').click(); l_no = pg.evaluate("document.querySelector('.hxrow[data-m=L] .hxs').textContent")
    pg.locator('.hxrow[data-m="M"] button').click(); m_no = pg.evaluate("document.querySelector('.hxrow[data-m=M] .hxs').textContent")
    print("L:", l_ok, "/", l_no, " M:", m_no)
    if l_ok != "sent ✓" or l_no != "not available here" or m_no != "not available here": bad("L/M should say when they can't work on this device")
    pg.locator('.hxrow[data-m="N"] button').click(); n_no = pg.evaluate("document.querySelector('.hxrow[data-m=N] .hxs').textContent")
    if n_no != "not available here" or pg.evaluate("document.querySelectorAll('.hsw').length"): bad(f"N should have no switches and say so off an iPhone ({n_no!r})")
    # the flash goes away by itself
    time.sleep(1.8)
    if pg.evaluate("[...document.querySelectorAll('.hxs')].filter(s=>s.textContent).length"): bad("a 'sent' flash never cleared")
    print("JS errors (desktop):", errs[:3]); ctx.close()

    # ---- an iPhone: hap() must use the switch even when navigator.vibrate exists, and the switch must be on screen
    IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
    ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", has_touch=True, user_agent=IOS)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script(SPY); pg.goto(B + "/app")
    wait(pg, "!!document.querySelector('#s-haptics')", 25); time.sleep(.5)
    pg.evaluate("window.__sw.length=0;window.__vib.length=0;S.hapAt=0;hap('light')")
    r = pg.evaluate("""(()=>{const e=document.getElementById('hapl');if(!e)return null;const r=e.getBoundingClientRect(),c=getComputedStyle(e);
      return {sw:window.__sw.length,vib:window.__vib.length,inview:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&r.width>0&&r.height>0,vis:c.visibility,disp:c.display,op:+c.opacity,pe:c.pointerEvents,
       inp:getComputedStyle(e.querySelector('input')).display,hasSwitch:e.querySelector('input').hasAttribute('switch')};})()""")
    print("iPhone hap('light'):", r)
    if not r: bad("hap() made no switch on an iPhone")
    else:
        if r["sw"] != 1: bad(f"an iPhone that reports navigator.vibrate must still get the switch toggled (toggles {r['sw']})")
        if r["vib"]: bad("an iPhone shouldn't use navigator.vibrate")
        if not r["inview"] or r["vis"] != "visible" or r["disp"] == "none" or r["inp"] == "none" or r["op"] <= 0 or r["pe"] == "none" or not r["hasSwitch"]:
            bad(f"the haptic switch must be laid out on screen and not hidden (iOS ignores hidden ones): {r}")
    # a real tap anywhere lands on that control's own see-through switch (N), once, with no scripted switch on top
    pg.evaluate("window.__sw.length=0;window.__swc.length=0;S.hapAt=0;__haps.length=0")
    pg.locator(".tabbar button").nth(1).click(); time.sleep(.3)
    n = pg.evaluate("({finger:__swc.slice(),scripted:__sw.filter(x=>x.id!=='visible').length,haps:__haps.slice()})")
    print("iPhone tab tap:", n)
    if n["finger"] != [True] or n["scripted"] or n["haps"] != ["selection"]: bad(f"a tab tap should land on its own switch once, with no scripted tick on top: {n}")
    # a pattern's extra ticks (and gestures with no tap) still try the scripted switch (iOS 27 ignores it; older iOS ticks)
    pg.evaluate("window.__sw.length=0;S.hapAt=0;hap('success')"); time.sleep(.3)
    if pg.evaluate("__sw.filter(x=>x.id==='hapl').length") != 2: bad("hap('success') outside a tap should still try two scripted ticks")
    # N (the default): the N button carries its own see-through switch; a tap flips it, runs once, says sent, no scripted tick
    pg.evaluate("go('settings')"); time.sleep(1.5); wait(pg, "!!document.querySelector('.hxrow[data-m=N] button>.hsw')", 10)
    pg.evaluate("window.__sw.length=0;window.__swc.length=0;window.__hapt=[];__haps.length=0;S.hapAt=0"); row = pg.locator('.hxrow[data-m="N"]'); row.scroll_into_view_if_needed()
    row.locator("button").click(); time.sleep(.2)
    nres = pg.evaluate("({hapt:window.__hapt.slice(),sw:__sw.slice(),finger:__swc.slice(),flash:document.querySelector('.hxrow[data-m=N] .hxs').textContent,other:document.querySelectorAll('.hxrow:not([data-m=N]) button>.hsw').length})")
    print("N on an iPhone:", nres)
    if nres["hapt"] != ["N"] or nres["finger"] != [True] or [x for x in nres["sw"] if x["id"] != "visible"] or nres["flash"] != "sent ✓": bad(f"N: the finger's own switch should flip once and the method run once: {nres}")
    if nres["other"]: bad("the other test buttons must not get a see-through switch (it would make them all tick)")
    # Haptics off: silent, remembered
    pg.evaluate("go('settings')"); time.sleep(1.5)
    pg.evaluate("window.__sw.length=0;S.hapAt=0"); pg.locator("#hapon").click(); time.sleep(.2)
    if pg.evaluate("__sw.filter(x=>x.id!=='visible').length"): bad("turning haptics off still buzzed once")   # (#hapon is a real switch: its own flip is the finger's)
    if pg.evaluate("document.querySelectorAll('.hsw').length"): bad("turning haptics off left see-through switches in the page")
    off = pg.evaluate("({s:S.hapOff,ls:localStorage.getItem('cw_hapoff'),on:document.getElementById('hapon').checked})")
    pg.evaluate("window.__sw.length=0;S.hapAt=0;hap('light');S.hapAt=0;hap('success')")
    quiet = pg.evaluate("__sw.length")
    print("off:", off, "toggles while off:", quiet)
    if off["s"] is not True or off["ls"] != "1" or off["on"]: bad(f"the Haptics switch didn't turn off and stay off: {off}")
    if quiet: bad("haptics still fired while turned off")
    pg.locator("#hapon").click(); time.sleep(.2)
    pg.evaluate("window.__sw.length=0;S.hapAt=0;hap('light')")
    if pg.evaluate("__sw.length") != 1 or pg.evaluate("localStorage.getItem('cw_hapoff')") != "": bad("turning haptics back on didn't bring them back")
    if pg.evaluate("document.querySelectorAll('.hsw').length") < 5: bad("turning haptics back on didn't bring the see-through switches back")
    # remembered across a reload
    pg.locator("#hapon").click(); time.sleep(.2); pg.reload(); wait(pg, "!!document.querySelector('#s-haptics')", 25); time.sleep(.5)
    if pg.evaluate("hapOff()") is not True or pg.evaluate("document.getElementById('hapon').checked"): bad("the off setting isn't remembered after a reload")
    print("JS errors (iPhone):", errs[:3])
    br.close()
print("PROBLEMS:" if problems else "no problems", problems)
