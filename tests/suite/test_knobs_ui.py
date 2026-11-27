# CHECK: group=page secs=25
# Issue #228, PR1: Results › What's working › Selling lists the knob registry, read-only: a folded card (44pt header),
# opened it shows each group, the value now / start / range in plain words, league chips that switch which league's
# learned values are shown (an own record and a borrowed one), the evidence bar and the "never moves by itself" list.
# No setting control inside it (only the fold and the chips). Real knob_view output from the engine under test, at
# phone (dark and light) and desktop sizes; no JS errors, no sideways scroll.
import sys, os, time, threading, json, tempfile
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
ENG = {}
def load():
    A = real_load(); ENG["A"] = A
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
t0 = time.time()
while "A" not in ENG and time.time() - t0 < 30:
    time.sleep(.1)
A = ENG["A"]
A.CFG["knobs_live"] = False; A.KNOB_SWITCH["on"] = False; A.KNOB_SWITCH["at"] = 1e18   # PR1's card: self-tuning off
tmp = tempfile.mkdtemp()
A.SMART_FILE = os.path.join(tmp, "smart.json"); A.SMART_CACHE["at"] = 0
A.SB_DIAL_FILE = os.path.join(tmp, "sb.json"); A.SB_GATE["dial"] = None
json.dump({"nba": {"n": 45, "floor": 1.7, "lam": 1.15, "loss": 0.2, "sl_n": 60, "sl_prog": 0.4, "sl_drop": 0.15},
           "soccer": {"n": 80, "floor": 1.3, "lam": 0.85, "loss": 0.25},
           "epl": {"n": 4}, "all": {"n": 300, "floor": 1.4, "lam": 1.0, "loss": None}}, open(A.SMART_FILE, "w"))
json.dump({"all": {"n": 40, "level": 2}}, open(A.SB_DIAL_FILE, "w"))
KV = A.knob_view()
A.KNOB_SWITCH["on"] = True
KV_LIVE = A.knob_view()                              # PR3: the same card with self-tuning on
A.KNOB_SWITCH["on"] = False
assert KV["live"] is False and KV_LIVE["live"] is True
AN = {"at": time.time() - 60, "levels": [], "types": [], "sports": [], "live": [], "exits": [], "auto": {}, "cut_held": {},
      "hedge_held": {}, "tuning": [], "notes": [], "knobs": KV}
from playwright.sync_api import sync_playwright
def wait(pg, js, secs=30):
    t = time.time()
    while time.time() - t < secs:
        try:
            if pg.evaluate(js): return True
        except Exception: pass
        time.sleep(.1)
    return False
P = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, scheme, tag in ((390, 844, "dark", "phone"), (390, 844, "light", "phone-light"), (1440, 900, "dark", "desktop")):
        pg = br.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=2, color_scheme=scheme)
        pg.add_init_script(__import__("upwait").COUNT_FETCHES)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/app/api/analytics", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(AN)))
        pg.goto(B + "/app"); pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=30000)
        pg.evaluate("go('results')"); wait(pg, "!!document.querySelector('.an .ant')", 40)
        pg.locator(".ant button", has_text="Selling").click()
        if not wait(pg, "!!document.querySelector('.an .knp .knh')", 10):
            P.append(tag + ": no knob card in Results › Selling"); pg.close(); continue
        hd = pg.locator(".an .knp .knh")
        bb = hd.bounding_box()
        if hd.get_attribute("aria-expanded") != "false" or pg.locator(".an .knp .knr").count():
            P.append(tag + ": the knob card isn't folded by default")
        if bb["height"] < 44: P.append(tag + ": the knob card's header is under 44pt: %r" % bb)
        if "never move" not in hd.inner_text(): P.append(tag + ": header has no counts: " + hd.inner_text())
        hd.click(); wait(pg, "document.querySelectorAll('.an .knp .kgh').length>=4", 5)
        # (#261) each group is its own fold, shut by default, with a count summary ("12 numbers · 2 learned")
        if pg.locator(".an .knp .knr:not(.kni)").count() and pg.locator(".an .knp .kgh[aria-expanded=true]").count():
            P.append(tag + ": the groups should start shut")
        gh = pg.locator(".an .knp .kgh")
        if gh.count() < 4 or "numbers" not in gh.first.inner_text(): P.append(tag + ": group headers/counts missing: " + gh.first.inner_text())
        if gh.first.bounding_box()["height"] < 44: P.append(tag + ": a group header is under 44pt")
        if "fh" not in (pg.locator(".an .knp .knh").get_attribute("class") or "").split() or pg.evaluate("getComputedStyle(document.querySelector('.an .knp .knh')).getPropertyValue('all')")=="unset":
            P.append(tag + ": the card header isn't on the shared fold class")
        pg.locator(".an .knp").screenshot(path=os.path.join(os.environ.get("SHOT_DIR", "."), "knobs_folded_%s.png" % tag))
        gh.first.click(); wait(pg, "document.querySelectorAll('.an .knp .kgb .knr').length>0", 5)
        if gh.first.get_attribute("aria-expanded") != "true": P.append(tag + ": a group didn't open")
        for i in range(1, gh.count()):
            if gh.nth(i).get_attribute("aria-expanded") != "true": gh.nth(i).click()
        wait(pg, "document.querySelectorAll('.an .knp .knr').length>20", 5)
        txt = pg.locator(".an .knp").inner_text()
        for want in ("Taking a profit", "Selling at a loss", "Hedging", "Smart Buy", "The bar a change must clear",
                     "Never moves by itself", "Profit floor", "Least chance to take a profit", "Pause stops every order",
                     "The Pi never trades", "Starts at 50% · range 50% to 65% · fixed for now",
                     "Most on one hedge", "Your switches always win", "range $25 to $150", "so none of that is switched on"):
            if want not in txt: P.append(tag + ": missing %r" % want)
        def floor_row():
            return pg.locator('.an .knp .knr[data-k="smart_floor"]').inner_text()
        if "1.4× what you paid" not in floor_row() or "own (300 results)" not in floor_row():
            P.append(tag + ": Everything should show everyone's floor: " + floor_row().replace("\n", " / "))
        chips = pg.locator(".an .knp .knlg button")
        if chips.count() < 3: P.append(tag + ": no league chips")
        pg.locator(".an .knp .knlg button", has_text="NBA").click()
        wait(pg, "(document.querySelector('.an .knp .knr[data-k=\"smart_floor\"]')||{innerText:''}).innerText.includes('1.7')", 5)
        fr = floor_row()
        if "1.7× what you paid" not in fr or "own (45 results)" not in fr: P.append(tag + ": NBA's own floor not shown: " + fr.replace("\n", " / "))
        if pg.locator('.an .knp .knr[data-k="sl_prog"]').inner_text().find("40%") < 0:
            P.append(tag + ": NBA's own loss-guard timing not shown")
        pg.locator(".an .knp .knlg button", has_text="Premier League").click()
        wait(pg, "(document.querySelector('.an .knp .knr[data-k=\"smart_floor\"]')||{innerText:''}).innerText.includes('Soccer')", 5)
        if "borrowed from Soccer" not in floor_row(): P.append(tag + ": the EPL's borrowed floor not shown: " + floor_row().replace("\n", " / "))
        if "cautious default" not in pg.locator('.an .knp .knr[data-k="smart_loss"]').inner_text():
            P.append(tag + ": a league with no loss cut of its own should show the cautious default")
        if pg.locator(".an .knp input, .an .knp select, .an .knp textarea").count():
            P.append(tag + ": the registry card has a setting control (it must be read-only)")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): P.append(tag + ": Results scrolls sideways")
        over = pg.evaluate("[...document.querySelectorAll('.an .knp .knr')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).length")
        if over: P.append(tag + ": %d knob rows run past the screen" % over)
        pg.locator(".an .knp").screenshot(path=os.path.join(os.environ.get("SHOT_DIR", "."), "knobs_%s.png" % tag))
        hd.click(); wait(pg, "!document.querySelector('.an .knp .knr')", 5)
        if pg.locator(".an .knp .knr").count(): P.append(tag + ": folding it again didn't close it")
        # PR3: self-tuning on: the card says so, the exit numbers show per league, a borrowed floor only stricter
        if "Couldn't read the numbers" not in pg.evaluate("knobCard({})"): P.append(tag + ": an empty knob_view should say it couldn't be read")
        if pg.evaluate("knobCard(undefined)") != "": P.append(tag + ": an older server (no knobs key) should show nothing")
        html = pg.evaluate("v=>{const o=S.knOpen,l=S.knLg,g=S.knGrp;S.knOpen=true;S.knLg='epl';S.knGrp={profit:1,loss:1,hedge:1,sell:1,buy:1};const h=knobCard(v);S.knOpen=o;S.knLg=l;S.knGrp=g;return h}", KV_LIVE)
        for want in ("Self-tuning is on", "the newest 30% agree", "never looser than its start", "still a test"):
            if want not in html: P.append(tag + ": live registry card missing %r" % want)
        if "none of that is switched on" in html: P.append(tag + ": live registry card still says it is off")
        if 'data-k="exit_q_min"' not in html or "fixed for now" in html.split('data-k="exit_q_min"')[1].split('class="knr')[0]:
            P.append(tag + ": with self-tuning on the least chance should show per league, not 'fixed for now'")
        if errs: P.append(tag + ": JS errors %r" % errs[:3])
        pg.close()
    br.close()
print("PROBLEMS: " + " | ".join(P) if P else "knobs ui ok")
