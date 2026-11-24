# CHECK: group=page secs=15
"""Settings › Cash out & hedging › "Selling at a loss" (issue #228 PR5): the old on/off override is now three choices in
plain words (Never sell at a loss / Let it tune itself / Allow (guarded)). An old saved 'on' shows Allow, an old 'off'
shows Let it tune itself; a tap saves the choice on the Mac (and keeps the old switch in step for older copies: on only
for Allow); the words under it follow the choice; no sideways scroll at a phone size, in dark and light. Prints
PROBLEMS."""
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])
import requests

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)

def saved():
    v = requests.get(B + "/app/api/settings?lg=nba", headers={"X-CW": "x"}).json().get("values", {})
    return v.get("stop_loss_mode"), v.get("stop_loss")

def wait_for(fn, want, secs=6):
    for _ in range(int(secs / .2)):
        if fn() == want: return True
        time.sleep(.2)
    return False

def open_settings(pg):
    pg.evaluate("S.set=null;go('settings')")
    for _ in range(75):
        if pg.evaluate("!!document.querySelector('#slrow .slseg button')"): return True
        time.sleep(.2)
    return False

ON = "[...document.querySelectorAll('#slrow .slseg button.on')].map(b=>b.textContent)"
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=scheme,
                             has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        requests.post(B + "/app/api/settings", headers={"X-CW": "x"}, json={"lg": "nba", "values": {"stop_loss_mode": "tune", "auto_sell": True}})
        requests.post(B + "/app/api/settings", headers={"X-CW": "x"}, json={"lg": "nba", "values": {"stop_loss": True}})
        if saved()[0] != "tune": bad(f"an old page's 'on' loosened the choice ({saved()})")
        pg.goto(B + "/app"); time.sleep(2)
        if not open_settings(pg):
            bad("no 'Selling at a loss' choice on Settings"); break
        if pg.evaluate("document.querySelector('#s-cash').classList.contains('shut')"):
            pg.evaluate("sTog('cash')"); time.sleep(.8)            # open the Cash out & hedging card
        names = pg.evaluate("[...document.querySelectorAll('#slrow .slseg button')].map(b=>b.textContent)")
        if names != ["Never sell at a loss", "Let it tune itself", "Allow (guarded)"]: bad(f"the choices read {names}")
        if pg.evaluate("document.querySelector('#slrow b').textContent") != "Selling at a loss": bad("the row isn't titled 'Selling at a loss'")
        if "Manual override" in pg.evaluate("document.body.innerText"): bad("the old 'Manual override' switch is still shown")
        old = pg.evaluate("(()=>{const k=S.set.values,a=[k.stop_loss,k.stop_loss_mode];k.stop_loss=true;k.stop_loss_mode=null;"
                          "const r=[slMode()];k.stop_loss=false;r.push(slMode());k.stop_loss=a[0];k.stop_loss_mode=a[1];return r})()")
        if old != ["allow", "tune"]: bad(f"an old saved on/off reads as {old}, not allow/tune")
        for want, words, old in (("never", "Nothing sells for less than you paid", False),
                                 ("tune", "own results show", False), ("allow", "late in a game", True)):
            pg.evaluate(f"document.querySelector('#slrow button[data-slm={want}]').click()")
            time.sleep(.3)
            if pg.evaluate(ON) != [{"never": "Never sell at a loss", "tune": "Let it tune itself", "allow": "Allow (guarded)"}[want]]:
                bad(f"after tapping {want} the highlighted choice is {pg.evaluate(ON)}")
            if words not in pg.evaluate("document.querySelector('#slrow small').textContent"):
                bad(f"the words under {want} don't say '{words}'")
            if not wait_for(saved, (want, old)): bad(f"tapping {want} saved {saved()}, not {(want, old)}")
        sw = pg.evaluate("document.documentElement.scrollWidth")
        if sw > 391: bad(f"{scheme}: the page scrolls sideways ({sw}px)")
        bw = pg.evaluate("Math.max(...[...document.querySelectorAll('#slrow .slseg button')].map(b=>b.getBoundingClientRect().right))")
        if bw > 390: bad(f"{scheme}: a choice runs off the screen ({bw}px)")
        pg.screenshot(path=f"slmode_{scheme}.png")
        requests.post(B + "/app/api/settings", headers={"X-CW": "x"}, json={"lg": "nba", "values": {"stop_loss_mode": "bogus"}})
        if saved()[0] != "allow": bad(f"an unknown value was saved ({saved()})")
        print(scheme, "JS errors:", errs[:3])
        if errs: bad(f"JS errors: {errs[:2]}")
        ctx.close()
    # older copies: a saved stop_loss_mode = None with stop_loss off reads as Let it tune itself
    requests.post(B + "/app/api/settings", headers={"X-CW": "x"}, json={"lg": "nba", "values": {"stop_loss_mode": "tune"}})
    if problems: print("PROBLEMS", len(problems))
    else: print("all good")
    br.close()
