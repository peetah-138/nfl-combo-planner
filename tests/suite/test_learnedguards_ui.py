# CHECK: group=page secs=15
"""Settings' "Let the selling guards learn" switch (Pete, 2026-11-24): ON by default, in the Cash out card, saves when
flipped off and on again; the Selling at a loss row shows the score-age and break guards read-only (the starting values
until something is learned, and no longer promises a fixed "never"). Phone size, dark and light. Set GUARDS_SHOTS=<folder>
to also save screenshots. Prints PROBLEMS."""
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])
import requests

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
ROW = "[...document.querySelectorAll('.srow')].find(r => r.querySelector('b') && r.querySelector('b').textContent === 'Let the selling guards learn')"

def saved():
    return requests.get(B + "/app/api/settings?lg=nba", headers={"X-CW": "x"}).json().get("values", {}).get("learned_guards")

def wait_for(fn, want, secs=6):
    for _ in range(int(secs / .2)):
        if fn() == want: return True
        time.sleep(.2)
    return False

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=scheme, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(B + "/app"); time.sleep(2)
        pg.evaluate("go('settings')")
        for _ in range(75):
            if pg.evaluate(f"!!({ROW})"): break
            time.sleep(.2)
        if not pg.evaluate(f"!!({ROW})"):
            bad(f"{scheme}: no 'Let the selling guards learn' row on Settings"); ctx.close(); continue
        if not pg.evaluate(f"{ROW}.querySelector('input').checked"): bad(f"{scheme}: the switch is not ON by default")
        if saved() is not True: bad(f"{scheme}: the Mac reports learned_guards {saved()!r} by default, not True")
        if pg.evaluate("document.querySelector('#s-cash').classList.contains('shut')"): pg.evaluate("sTog('cash')")
        time.sleep(.4)
        txt = pg.evaluate("document.querySelector('#slrow') ? document.querySelector('#slrow').textContent : ''")
        if "never at halftime" in txt.lower(): bad(f"{scheme}: the loss row still promises a fixed 'never at halftime'")
        if "150" not in txt and "seconds" not in txt: bad(f"{scheme}: the loss row does not show the score-age value: {txt!r}")
        pg.evaluate(f"{ROW}.scrollIntoView({{block: 'center'}})"); time.sleep(.4)
        if os.environ.get("GUARDS_SHOTS"):
            pg.screenshot(path=os.path.join(os.environ["GUARDS_SHOTS"], f"learned-guards-{scheme}.png"))
        if scheme == "dark":
            pg.evaluate(f"{ROW}.querySelector('input').click()")
            if not wait_for(saved, False): bad(f"flipping it off saved {saved()!r}")
            pg.evaluate(f"{ROW}.querySelector('input').click()")
            if not wait_for(saved, True): bad(f"flipping it back on saved {saved()!r}")
        print(scheme, "JS errors:", errs[:3])
        ctx.close()
    if problems: print("PROBLEMS", len(problems))
