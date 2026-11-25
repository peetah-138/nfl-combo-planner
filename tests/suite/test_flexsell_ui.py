# CHECK: group=page secs=15
"""Settings' "Flexible sell price" switch (Pete, 2026-11-24): ON by default, in the Cash out card, saves when flipped off and
on again. Phone size, dark and light. Set FLEX_SHOTS=<folder> to also save screenshots. Prints PROBLEMS."""
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])
import requests

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
ROW = "[...document.querySelectorAll('.srow')].find(r => r.querySelector('b') && r.querySelector('b').textContent === 'Flexible sell price')"

def saved():
    return requests.get(B + "/app/api/settings?lg=nba", headers={"X-CW": "x"}).json().get("values", {}).get("flex_sell")

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
            bad(f"{scheme}: no Flexible sell price row on Settings"); ctx.close(); continue
        if not pg.evaluate(f"{ROW}.querySelector('input').checked"): bad(f"{scheme}: Flexible sell price is not ON by default")
        if saved() is not True: bad(f"{scheme}: the Mac reports flex_sell {saved()!r} by default, not True")
        if pg.evaluate("document.querySelector('#s-cash').classList.contains('shut')"): pg.evaluate("sTog('cash')")
        time.sleep(.4)
        pg.evaluate(f"{ROW}.scrollIntoView({{block: 'center'}})"); time.sleep(.4)
        if os.environ.get("FLEX_SHOTS"):
            pg.screenshot(path=os.path.join(os.environ["FLEX_SHOTS"], f"flexible-sell-{scheme}.png"))
        if scheme == "dark":
            pg.evaluate(f"{ROW}.querySelector('input').click()")
            if not wait_for(saved, False): bad(f"flipping it off saved {saved()!r}")
            pg.evaluate(f"{ROW}.querySelector('input').click()")
            if not wait_for(saved, True): bad(f"flipping it back on saved {saved()!r}")
        print(scheme, "JS errors:", errs[:3])
        ctx.close()
    if problems: print("PROBLEMS", len(problems))
