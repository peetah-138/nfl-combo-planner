# CHECK: group=page secs=15
"""Settings' "Auto cash-outs a day, at most" slider has an Unlimited top stop (issue #217): at a phone size, moving it to
the top shows "Unlimited", saves the sentinel 1000, and a reload still shows Unlimited; a number stop still saves the number.
Prints PROBLEMS."""
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])
import requests

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
SL = "document.querySelector('.srow input[type=range][max=\"11\"]')"
OUT = SL + ".nextElementSibling.textContent"

def saved_cap():
    return requests.get(B + "/app/api/settings?lg=nba", headers={"X-CW": "x"}).json().get("values", {}).get("auto_cap")

def move(pg, v):
    pg.evaluate(f"(() => {{ const s = {SL}; s.value = {v}; s.dispatchEvent(new Event('input', {{bubbles: true}}));"
                f" s.dispatchEvent(new Event('change', {{bubbles: true}})); }})()")

def wait_for(fn, want, secs=6):
    for _ in range(int(secs / .2)):
        if fn() == want: return True
        time.sleep(.2)
    return False

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark", has_touch=True, is_mobile=True)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/app"); time.sleep(2)
    pg.evaluate("go('settings')")
    for _ in range(75):
        if pg.evaluate(f"!!{SL}"): break
        time.sleep(.2)
    if not pg.evaluate(f"!!{SL}"):
        bad("no Auto cash-outs slider with an 11th (Unlimited) stop on Settings")
    else:
        lbl = pg.evaluate(SL + ".closest('.srow').querySelector('b').textContent")
        if lbl != "Auto cash-outs a day, at most": bad(f"the 11-stop slider is not the auto cash-out cap ({lbl!r})")
        if pg.evaluate(OUT) == "Unlimited": bad("Unlimited shown before it was chosen")
        move(pg, 11)
        if pg.evaluate(OUT) != "Unlimited": bad(f"top stop reads {pg.evaluate(OUT)!r}, not Unlimited")
        if pg.evaluate("S.set.values.auto_cap") != 1000: bad(f"top stop stored {pg.evaluate('S.set.values.auto_cap')}, not 1000")
        if not wait_for(saved_cap, 1000): bad(f"the Mac saved {saved_cap()} for Unlimited, not 1000")
        pg.evaluate("S.set=null;go('live')"); time.sleep(.8); pg.evaluate("go('settings')")
        for _ in range(75):
            if pg.evaluate(f"!!{SL}"): break
            time.sleep(.2)
        print("after reload:", pg.evaluate(OUT), pg.evaluate(SL + ".value"))
        if pg.evaluate(OUT) != "Unlimited" or pg.evaluate(SL + ".value") != "11": bad("after a reload the slider is not at Unlimited")
        move(pg, 7)
        if pg.evaluate(OUT) != "7": bad(f"a number stop reads {pg.evaluate(OUT)!r}")
        if not wait_for(saved_cap, 7): bad(f"a number stop saved {saved_cap()}, not 7")
        # the server side turns any number over 10 into the sentinel too
        requests.post(B + "/app/api/settings", headers={"X-CW": "x"}, json={"lg": "nba", "values": {"auto_cap": 25}})
        if saved_cap() != 1000: bad(f"a value of 25 sent to the Mac saved {saved_cap()}, not the Unlimited sentinel")
        requests.post(B + "/app/api/settings", headers={"X-CW": "x"}, json={"lg": "nba", "values": {"auto_cap": 5}})
        pg.screenshot(path="autocap_p.png")
    print("JS errors:", errs[:3])
    if problems: print("PROBLEMS", len(problems))
    else: print("all good")
    br.close()
