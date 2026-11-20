"""The bottom tab bar never moves (GitHub #59: "Bottom tab bar jumps up on the Games tab"). Pete's iPhone Home Screen app showed
the bar about 90 px above the bottom on the Games tab (the empty "No games to watch" card), with the header tucked as if the page
were scrolled, and the empty card's icon square blank. On an iPhone the page's height can stay out of step with what is on screen
(after the keyboard closes, after coming back to the app), and the header's "tucked" flag was only re-read on scroll events.
Fixes under test: the bar is moved down by however much taller the visible area is than the page (`tbSet`, `--tbo`), the header
flag is re-read from the page itself on every tab switch, resize and second (`hcSync`), and the empty cards draw an icon.
On a phone (390x844), frame by frame (requestAnimationFrame) from the tap until 1.2 s later, on every tab, with games and with
none, after scrolling down and switching tabs, and after a keyboard-sized resize and back: the bar's bottom edge must be the
bottom of the screen in every frame, and the header must not stay tucked on an unscrolled page. A simulated "visible area
taller than the page" (as iOS reports it after the keyboard closes) must still leave the bar flush with the screen bottom, and a
shorter one (the keyboard) must not move it. Prints PROBLEMS."""
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
P = open("panel_fixture.json").read()
BAR = r"""(() => { const t = document.querySelector('#tabbar').getBoundingClientRect(), vv = window.visualViewport;
 return { bottom: Math.round(t.bottom), want: Math.round(vv.height + vv.offsetTop), hc: document.body.classList.contains('hc'), sy: Math.round(scrollY) }; })()"""
FRAMES = r"""new Promise(res => { const s = [], t0 = performance.now();
 const f = () => { const t = Math.round(performance.now() - t0); s.push([t, %s]); if (t < 1200) requestAnimationFrame(f); else res(s); }; f(); })""" % BAR

def frames(pg, act, label):
    pg.evaluate(act)
    out = pg.evaluate(FRAMES)
    off = [o for o in out if abs(o[1]["bottom"] - o[1]["want"]) > 1]
    if off: bad(f"{label}: tab bar not flush with the screen bottom at {off[0][0]} ms (bottom {off[0][1]['bottom']}, screen {off[0][1]['want']})")
    return out

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark", has_touch=True, is_mobile=True)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/app/api/panel?*", lambda r: r.fulfill(status=200, content_type="application/json", body=P))
    pg.add_init_script("localStorage.setItem('cw_view','live')")
    pg.goto(B + "/app")
    for _ in range(100):
        if pg.evaluate("!!(S.live&&S.live.combos)"): break
        time.sleep(.2)
    time.sleep(1.5)
    # every tab, with games
    for v in ("games", "build", "results", "settings", "live"):
        frames(pg, f"go('{v}')", f"go {v}"); time.sleep(.4)
    # Games with nothing to watch
    pg.route("**/app/api/games*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"games": [], "at": None, "fresh": {"now": time.time(), "built": time.time(), "scores": None, "fast": False}})))
    pg.evaluate("S.games=null;S.view='live'")
    frames(pg, "go('games')", "empty games"); time.sleep(.4)
    ic = pg.evaluate("getComputedStyle(document.querySelector('#main .empty'),'::before').content")
    print("empty card icon:", ic)
    if ic in ('""', "none", "normal", "''") or len(ic.strip('"')) == 0: bad(f"the empty card's icon square is blank (content {ic})")
    # scroll down on a long tab, then switch to the short empty one and others
    pg.evaluate("go('live')"); time.sleep(1.2); pg.evaluate("window.scrollTo(0, 400)"); time.sleep(.5)
    r = pg.evaluate(BAR); print("scrolled live:", r)
    if not r["hc"]: print("(header was not tucked after scrolling; fine)")
    out = frames(pg, "go('games')", "scrolled live -> empty games")
    if out[-1][1]["hc"]: bad("header stayed tucked on the empty Games tab")
    pg.evaluate("go('live')"); time.sleep(1.2); pg.evaluate("window.scrollTo(0, 400)"); time.sleep(.5)
    frames(pg, "go('settings')", "scrolled live -> settings"); time.sleep(.4)
    # a tucked flag left behind with the page at the top (what the phone showed): the next tab switch must clear it
    pg.evaluate("go('live')"); time.sleep(1); pg.evaluate("window.scrollTo(0,0);document.body.classList.add('hc')")
    pg.evaluate("go('games')"); time.sleep(.5)
    if pg.evaluate("document.body.classList.contains('hc')"): bad("header still tucked after a tab switch on an unscrolled page")
    pg.evaluate("document.body.classList.add('hc')"); time.sleep(1.4)
    if pg.evaluate("document.body.classList.contains('hc')"): bad("header still tucked a second later on an unscrolled page")
    # the visible area reported taller than the page (iOS after the keyboard closes): the bar follows the visible bottom
    pg.evaluate("go('games')"); time.sleep(.6)
    pg.evaluate("tbSet({height: innerHeight + 90, offsetTop: 0})")
    r = pg.evaluate("(() => ({ b: Math.round(document.querySelector('#tabbar').getBoundingClientRect().bottom), ih: innerHeight }))()")
    print("visible area 90 px taller:", r)
    if abs(r["b"] - (r["ih"] + 90)) > 1: bad(f"bar not flush with a taller visible area: bottom {r['b']}, visible bottom {r['ih'] + 90}")
    pg.evaluate("tbSet({height: innerHeight - 300, offsetTop: 0})")   # a keyboard: the bar stays put (behind it)
    r = pg.evaluate("(() => ({ b: Math.round(document.querySelector('#tabbar').getBoundingClientRect().bottom), ih: innerHeight }))()")
    if abs(r["b"] - r["ih"]) > 1: bad(f"bar moved for a keyboard-sized visible area: bottom {r['b']}, page bottom {r['ih']}")
    pg.evaluate("tbSet()"); time.sleep(.3)
    frames(pg, "go('build')", "after the simulated sizes -> build")
    # a keyboard-sized window and back
    cdp = ctx.new_cdp_session(pg)
    cdp.send("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 500, "deviceScaleFactor": 2, "mobile": True}); time.sleep(.6)
    cdp.send("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True}); time.sleep(.8)
    frames(pg, "go('games')", "after a window resize and back -> games")
    if errs: bad(f"JS errors {errs[:3]}")
    br.close()

print("PROBLEMS: " + " | ".join(problems) if problems else "all tab-bar checks passed")
