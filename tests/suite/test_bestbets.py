"""Build's "Best bets today" (issue #63): one ranked recommend-only feed. The web app's Build answer is patched at the page's
request layer to carry a scripted feed (the engine's own feed is covered by t_bestbets.py); nothing is priced or bought.
Checks at phone (390x844, dark and light) and desktop: the section sits under the panel, rows are in the order sent with
plain-English route text and expected dollars, the type chips filter, an exposure warning shows real numbers, the old
Spreads & totals board is gone, Buy straight opens the guarded sheet for that very ticker, a combo is priced through its own
card, the empty states explain themselves, no sideways scroll, no JS errors. Saves screenshots (SHOTS dir, if set)."""
import sys, os, time, threading, json, re
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("SHOTS") or ""
from playwright.sync_api import sync_playwright
problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        try:
            if pg.evaluate(js): return True
        except Exception:
            pass
        time.sleep(.2)
    return False
def shot(pg, name):
    if SHOTS:
        pg.screenshot(path=os.path.join(SHOTS, name))

ITEMS = [
    {"id": "single:KXNBAGAME-26NOV22AAABBB-AAA", "kind": "single", "code": "nba", "icon": "🏀", "league": "NBA", "game": "Aces vs Bees",
     "pick": "Aces to beat Bees", "ticker": "KXNBAGAME-26NOV22AAABBB-AAA", "i": None, "kick": time.time() + 7200, "price": .5, "fair": .58,
     "chance": .58, "edge": .0585, "stake": 12.0, "ev": 1.84, "route": "sell", "p_exit": .62, "win": .58, "exit_mins": 41.0,
     "exposure": None, "legs": []},
    {"id": "line:KXNBASPREAD-26NOV22GGGHHH-GGG3", "kind": "line", "code": "nba", "icon": "🏀", "league": "NBA", "game": "Gnus at Hogs",
     "pick": "Gnus win by 3.5+ (Gnus at Hogs)", "ticker": "KXNBASPREAD-26NOV22GGGHHH-GGG3", "i": None, "kick": time.time() + 9000,
     "price": .4, "fair": .5, "chance": .5, "edge": .0745, "stake": 6.0, "ev": 0.71, "route": "hold", "p_exit": .2, "win": .5,
     "exit_mins": None, "exposure": None, "legs": []},
    {"id": "combo:a+b", "kind": "combo", "code": "nba", "icon": "🏀", "league": "NBA", "game": "", "pick": "Kites to beat Owls + Moths to beat Newts",
     "ticker": "KXNBAGAME-26NOV22KKKLLL-KKK", "i": 1, "kick": time.time() + 7200, "price": None, "fair": None, "chance": .37,
     "edge": .08, "stake": 4.0, "ev": 0.44, "route": "hold", "p_exit": .1, "win": .37, "exit_mins": None,
     "exposure": {"n": 7, "of": 9, "team": "Kites", "label": "heavy"}, "legs": []}]
MODE = {"best": {"items": ITEMS, "why": None, "looked": {"single": 3, "line": 2, "combo": 1}}}
SENT = []
def build(route):
    r = route.fetch()
    try:
        d = r.json(); d["best"] = MODE["best"]; d["lines"] = [{"ticker": "X", "game": "NEG", "kind": "spread", "line": 1.5, "pick": "Negative edge (A at B)",
                                                              "p": .5, "fair": .4, "edge": -.11, "book_line": -3}]
        route.fulfill(status=200, content_type="application/json", body=json.dumps(d))
    except Exception:
        route.continue_()
def act(route):
    try:
        body = json.loads(route.request.post_data or "{}")
    except ValueError:
        body = {}
    if body.get("a") in ("singlequote", "quote"):
        SENT.append(body)
        if body["a"] == "singlequote":
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(
                {"ok": False, "msg": "Test: nothing is priced here."}))
        return route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": False, "error": "Test: nothing is priced here."}))
    return route.continue_()

def rows(pg):
    return pg.evaluate("""[...document.querySelectorAll('#main .bfrow')].map(r=>({t:r.innerText,k:r.dataset.key,
      ev:(r.querySelector('.ret [data-num]')||{}).dataset&&r.querySelector('.ret [data-num]').dataset.v,warn:!!r.querySelector('.bfwarn')}))""")
def sideways(pg):
    return pg.evaluate("document.documentElement.scrollWidth>innerWidth+1")

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, tag, scheme in ((390, 844, "phone", "dark"), (390, 844, "light", "light"), (1280, 900, "desk", "dark")):
        ctx = br.new_context(viewport={"width": vw, "height": vh}, color_scheme=scheme, has_touch=(vw < 900), device_scale_factor=2)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__haps=[];localStorage.clear();localStorage.setItem('cw_view','build');localStorage.setItem('cw_lg','nba');localStorage.setItem('cw_pview','nba')")
        pg.route(re.compile(r".*/app/api/build\?.*"), build)
        pg.route("**/app/api/act", act)
        MODE["best"] = {"items": ITEMS, "why": None, "looked": {"single": 3, "line": 2, "combo": 1}}
        pg.goto(B + "/app")
        if not wait(pg, "S.build&&S.build.best&&document.querySelector('#main .bfrow')", 40):
            bad(f"{tag}: the Best bets section didn't render"); ctx.close(); continue
        time.sleep(.8)
        head = pg.evaluate("(document.querySelector('.sech[data-k=\"best\"]')||{}).innerText||''")
        if "best bets today" not in head.lower(): bad(f"{tag}: section heading missing: {head!r}")
        if "expected +$2.99" not in head or "$22 in" not in head: bad(f"{tag}: the heading should total the stakes and the expected dollars: {head!r}")
        order = pg.evaluate("[...document.querySelectorAll('#main #pblock, #main .sech[data-k=\"best\"]')].map(e=>e.id||e.dataset.k)")
        if order[:2] != ["pblock", "best"]: bad(f"{tag}: the daily panel should stay on top, the feed right under it: {order}")
        rs = rows(pg)
        if [r["k"] for r in rs] != ["bf:" + x["id"] for x in ITEMS]: bad(f"{tag}: rows should be in the order the Mac ranked them: {[r['k'] for r in rs]}")
        t0, t1, t2 = (r["t"] for r in rs)
        for want in ("Aces to beat Bees", "Aces vs Bees", "50¢", "58%", "5.9¢", "$12", "+$1.84", "Likely to cash out early for a profit: 62%", "41 min"):
            if want.lower() not in t0.lower(): bad(f"{tag}: single row should show {want!r}: {t0[:300]!r}")
        for want in ("Spread / total", "Gnus win by 3.5+", "Profit if it holds: 50% to win", "+$0.71"):
            if want.lower() not in t1.lower(): bad(f"{tag}: spread row should show {want!r}: {t1[:300]!r}")
        for want in ("Combo", "Price it", "7 of your 9 open combos", "heavy", "stake is cut", "+$0.44"):
            if want.lower() not in t2.lower(): bad(f"{tag}: combo row should show {want!r}: {t2[:300]!r}")
        if [r["warn"] for r in rs] != [False, False, True]: bad(f"{tag}: only the combo carries the exposure warning: {[r['warn'] for r in rs]}")
        if pg.evaluate("!!document.querySelector('.lrow2')||document.body.innerText.includes('Negative edge')"):
            bad(f"{tag}: the old all-strikes Spreads & totals board is back (a negative-edge line shows)")
        if pg.evaluate("document.body.innerText.includes('Spreads & totals ')&&!!document.querySelector('.sech[data-k=\"lines\"]')"): bad(f"{tag}: the lines board section should be gone")
        if sideways(pg): bad(f"{tag}: Build scrolls sideways")
        shot(pg, f"1_best_{tag}.png")
        # ---- the type chips filter the feed
        pg.locator("#main .chip", has_text="Spreads & totals").first.click(); time.sleep(.4)
        if [r["k"] for r in rows(pg)] != ["bf:" + ITEMS[1]["id"]]: bad(f"{tag}: the Spreads & totals chip should leave just the spread: {[r['k'] for r in rows(pg)]}")
        pg.locator("#main .chip", has_text="Singles").first.click(); time.sleep(.3)
        pg.locator("#main .chip", has_text="Combos").first.click(); time.sleep(.3)
        if [r["k"] for r in rows(pg)] != ["bf:" + ITEMS[2]["id"]]: bad(f"{tag}: the Combos chip should leave just the combo")
        pg.locator("#main .chip", has_text="All").last.click(); time.sleep(.3)
        if len(rows(pg)) != 3: bad(f"{tag}: All should bring every row back")
        # ---- Buy straight opens the guarded sheet for exactly that ticker
        n0 = len(SENT)
        (pg.locator("#main .bfrow").nth(0).locator("button", has_text="Buy straight").tap() if tag != "desk"
         else pg.locator("#main .bfrow").nth(0).locator("button", has_text="Buy straight").click())
        if not wait(pg, "!!document.querySelector('#sbx')", 8): bad(f"{tag}: Buy straight should open the buy sheet")
        if not any(s.get("a") == "singlequote" and s.get("t") == ITEMS[0]["ticker"] for s in SENT[n0:]): bad(f"{tag}: the sheet should ask for a fresh quote on that very ticker: {SENT[n0:]}")
        pg.evaluate("closeModal&&closeModal()"); time.sleep(.5)
        # ---- a combo is priced through its own card (never bought from the feed)
        n0 = len(SENT)
        pg.locator("#main .bfrow").nth(2).locator("button", has_text="Price it").first.click(); time.sleep(.8)
        if not any(s.get("a") == "quote" and s.get("i") == 1 for s in SENT[n0:]): bad(f"{tag}: Price it should ask for a quote on combo 1: {SENT[n0:]}")
        if not pg.evaluate("S.adv===true&&!!document.querySelector('#main .ccard[data-i=\"1\"]')"): bad(f"{tag}: Price it should open the combo's own card")
        if pg.evaluate("[...document.querySelectorAll('#main .bfrow button')].some(b=>/^Buy \\$/.test(b.innerText))"): bad(f"{tag}: a feed row must never buy a combo itself")
        # ---- empty states say why (never a table of losing lines)
        MODE["best"] = {"items": [], "why": "Nothing clears your bar right now. I checked 6 bets with an edge; none also has a likely way to profit by cashing out early or holding.",
                        "looked": {"single": 4, "line": 2, "combo": 0}}
        pg.evaluate("S.build=null;load('build',true)")
        if not wait(pg, "document.querySelector('#main .sech[data-k=\"best\"]')&&!document.querySelector('#main .bfrow')", 20): bad(f"{tag}: the empty feed should show no rows")
        e = pg.evaluate("(document.querySelector('#main .empty')||{}).innerText||''")
        if "Nothing clears your bar right now" not in e or "checked 6 bets" not in e: bad(f"{tag}: the empty state should explain itself: {e!r}")
        if sideways(pg): bad(f"{tag}: the empty state scrolls sideways")
        shot(pg, f"2_empty_{tag}.png")
        if errs: bad(f"{tag}: JS errors: {errs}")
        print(tag, "errs:", errs)
        ctx.close()
    br.close()
if problems:
    print("PROBLEMS:", "; ".join(problems))
else:
    print("all good")
