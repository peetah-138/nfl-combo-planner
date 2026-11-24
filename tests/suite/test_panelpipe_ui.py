# CHECK: group=page secs=60
# Issue #341 on the page: the panel's "Why so few?" sheet lists the Mac's funnel; Results shows the two paper tests
# (Kalshi's price as fair, combos as the cheap way in). No sideways scroll on a phone, no JS errors, light and dark.
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
import upwait
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright

P = json.load(open("panel_fixture2.json"))
WHY = ["NBA: 10 games not started; 1 with no outside line (Kalshi's price alone, so no single or combo); 0 singles priced "
       "under their chance; 9 combos priced, 0 at the cut-off or better.", "Under the bar: 3 combos.",
       "Not picked: 2 on a game already covered."]
P["panel"]["stats"]["pool"] = {"combo": 1, "single": 2, "line": 3}
P["panel"]["stats"]["funnel"] = {"why": WHY}
MKT = {"min_n": 200, "today": {"n": 82, "claimed": 4, "vanish": 3},
       "groups": [{"lg": "nba", "name": "NBA", "kind": "win", "phase": "pre", "n": 240, "ll_mid": 0.661, "ll_book": 0.668,
                   "w": 0.0, "claimed": 12, "vanish": 9, "van_pl": -11.5, "kept": 3, "kept_pl": 4.2},
                  {"lg": "nba", "name": "NBA", "kind": "combo", "phase": "pre", "n": 30, "ll_mid": 0.52, "ll_book": 0.55,
                   "w": 0.0, "claimed": 30, "vanish": 22, "van_pl": -18.0, "kept": 8, "kept_pl": 6.0}]}
CARRY = {"stake": 5.0, "rows": [{"kind": "sep", "n": 2, "quotes": 14, "ratio": 1.012, "clear": 9, "paper": 9, "settled": 6, "won": 2,
                                 "pl": 1.4, "staked": 30.0},
                                {"kind": "same", "n": 2, "quotes": 5, "ratio": 0.93, "clear": 0, "paper": 0, "settled": 0, "won": 0,
                                 "pl": 0.0, "staked": 0.0}]}
RES = {"balance": 100.0, "settled": 0, "won": 0, "cashed": 0, "staked": 0, "returned": 0, "pl": 0.0, "roi": None,
       "best": 0, "weeks": [], "history": [], "shadow": None, "accuracy": None, "accuracy_text": "",
       "edge": {}, "backtest": None, "model": None, "by_tier": {}, "proof": None, "killer": None,
       "cover": None, "panel": None, "mkt": MKT, "carry": CARRY}

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, scheme in ((390, 844, "dark"), (390, 844, "light"), (1400, 900, "dark")):
        pg = br.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=2, color_scheme=scheme)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script(upwait.COUNT_FETCHES)
        pg.route("**/app/api/results", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(RES)))
        pg.route("**/app/api/analytics", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"at": 0})))
        pg.goto(B + "/app")
        upwait.go_and_hold(pg, "build")
        pg.evaluate("p=>{S.panel=p;renderBuild()}", P)
        pg.wait_for_function("!!document.querySelector('.fnwhy')", timeout=10000)
        line = pg.locator(".panel").inner_text()
        if "Qualifying today: 1 combo · 2 single games · 0 sell-early favorites · 3 spreads or totals." not in line:
            print("PROBLEMS: the pool line is wrong:", line[-300:])
        want = "Why so few?" if len(P["panel"]["items"]) < 4 else "How these were picked"
        if pg.locator(".fnwhy").inner_text().strip() != want:
            print("PROBLEMS: the funnel link should read", want, "got", pg.locator(".fnwhy").inner_text())
        pg.locator(".fnwhy").click()
        pg.wait_for_function("document.querySelectorAll('#sheet .fnrow').length===3", timeout=10000)
        sh = pg.locator("#sheet").inner_text()
        if "How today's panel was narrowed" not in sh or "1 with no outside line" not in sh or "Not picked: 2 on a game already covered." not in sh:
            print("PROBLEMS: the funnel sheet doesn't list the steps:", sh[:400])
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
            print("PROBLEMS: the funnel sheet scrolls sideways", vw, scheme)
        pg.evaluate("closeModal()")
        # an empty panel still links to the funnel (the #341 case: nothing qualified)
        pg.evaluate("f=>{S.panel={panel:null,view:'all',funnel:f};renderBuild()}", {"at": time.time(), "why": WHY})
        pg.wait_for_function("!!document.querySelector('.fnwhy')", timeout=10000)
        if pg.locator(".fnwhy").inner_text().strip() != "Why so few?":
            print("PROBLEMS: the empty panel's funnel link is missing")
        # no funnel from an older Mac: no button
        pg.evaluate("p=>{p=JSON.parse(JSON.stringify(p));delete p.panel.stats.funnel;S.panel=p;renderBuild()}", P)
        if pg.locator(".fnwhy").count():
            print("PROBLEMS: a 'Why so few?' button shows with no funnel")

        pg.evaluate("window.load=window.__ldw")
        upwait.go_and_hold(pg, "results")
        pg.wait_for_function("!!document.querySelector('.mktcard')&&!!document.querySelector('.carrycard')", timeout=15000)
        m = pg.locator(".mktcard").inner_text()
        if "Kalshi's price as fair" not in m or "Kalshi's price predicted better" not in m or "12 claimed edges (none survive Kalshi's own price yet)" not in m \
                or "Claimed edges gone on Kalshi's price: 22 of 30" not in m or "(estimated price)" not in m or "−$12" not in m:
            print("PROBLEMS: the market-fair card is wrong:", repr(m[:600]))
        if "82 markets logged, 4 with a claimed edge, 3 of those gone" not in m or "200+" not in m:
            print("PROBLEMS: the market-fair card's last 24 hours line is wrong:", repr(m[:600]))
        if "the books move" in m:
            print("PROBLEMS: a weight of 0 is shown as the books moving Kalshi's price")
        c = pg.locator(".carrycard").inner_text()
        if "Combos as the cheap way in" not in c or "Separate games · 2 picks · 14 quotes · pays +1.2% vs Kalshi's prices" not in c or \
                "+$1.40" not in c or "2/6 won" not in c or "Same game · 2 picks · 5 quotes · pays −7.0% vs Kalshi's prices" not in c:
            print("PROBLEMS: the carry card is wrong:", repr(c[:600]))
        col = pg.evaluate("getComputedStyle(document.querySelector('.carrycard b.up')).color")
        if col == pg.evaluate("getComputedStyle(document.querySelector('.carrycard h3')).color"):
            print("PROBLEMS: the carry card's profit isn't coloured")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
            print("PROBLEMS: Results scrolls sideways with the paper cards", vw, scheme)
        if os.environ.get("CW_SHOT_DIR"):
            pg.locator(".mktcard").screenshot(path=os.environ["CW_SHOT_DIR"] + f"/mkt_{vw}_{scheme}.png")
            pg.locator(".carrycard").screenshot(path=os.environ["CW_SHOT_DIR"] + f"/carry_{vw}_{scheme}.png")
        if vw != 1400 or scheme != "dark":           # empty states: once is enough
            pg.close()
            print(vw, scheme, "errs:", errs)
            if errs:
                print("PROBLEMS: JS errors", errs)
            continue
        pg.evaluate("window.load=window.__ldw")
        RES2 = dict(RES, mkt={"min_n": 200, "today": {}, "groups": []}, carry={"stake": 5, "rows": []})
        pg.unroute("**/app/api/results")
        pg.route("**/app/api/results", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(RES2)))
        upwait.go_and_hold(pg, "build"); pg.evaluate("window.load=window.__ldw"); upwait.go_and_hold(pg, "results")
        pg.wait_for_function("!!document.querySelector('.mktcard')", timeout=15000)
        if "No settled markets yet" not in pg.locator(".mktcard").inner_text() or "No quotes yet" not in pg.locator(".carrycard").inner_text():
            print("PROBLEMS: the paper cards' empty states are missing")
        print(vw, scheme, "errs:", errs)
        if errs:
            print("PROBLEMS: JS errors", errs)
        pg.close()
    br.close()
print("done")
