# CHECK: group=page
# Long shots on Build (issue #341), phone size, dark: the engine's vetted long shots show as a section on top of Build
# (hit %, expected dollars, the route to profit, the stake, each pick), Get price asks the Mac with the shown picks and
# a fresh quote turns the button into Buy (green when it clears) with a draining bar, Buy goes through the usual combo
# accept; with nothing vetted the empty state sits with the board, and the random combos live under 'Surprise me'.
# No sideways scroll. Fakes only (the act answers are stubbed in the page; nothing reaches Kalshi).
import sys, os, threading, time
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
LEGS = [{"ticker": f"KXNBAGAME-26NOV29T{i}U{i}-T{i}", "event": f"KXNBAGAME-26NOV29T{i}U{i}", "pick": n, "p": 0.73, "fair": 0.74}
        for i, n in enumerate(["Celtics", "Knicks", "Bucks", "Nuggets", "Thunder", "Cavaliers", "Magic"])]
REC = [{"id": "longshot:" + "+".join(sorted(l["ticker"] for l in LEGS)), "legs": LEGS, "n": 7, "chance": 0.1219,
        "price": 0.11, "pct": 1.06, "pays": 42.1, "stake": 4.6, "exp": 1.35, "p_exit": 0.52, "route": "sell", "win": 0.12}]
CALLS = []


def load():
    A = real_load()

    def lb(games, now=None, quote=None, paused=None, skip=(), budget=None):
        CALLS.append(paused)
        return [dict(r) for r in REC], {"looked": 4, "quoted": 2, "why": None, "skipped": {}}
    A.longshot_build = lb
    return A


W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("LS_SHOTS") or "."
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    pg.add_init_script(__import__("upwait").COUNT_FETCHES)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/app"); pg.wait_for_function("typeof S==='object'", timeout=60000)
    pg.evaluate("localStorage.removeItem('cw_bsec');S.bsec={}")
    __import__("upwait").go_and_hold(pg, "build")
    # the Mac works long shots out in the background: the next Build load carries them
    for _ in range(30):
        if pg.evaluate("((S.build&&S.build.longshots||{}).recs||[]).length"):
            break
        pg.evaluate("load('build').catch(()=>{})"); time.sleep(1)
    if not pg.evaluate("((S.build&&S.build.longshots||{}).recs||[]).length"):
        print("PROBLEMS: the Build API never carried the long shots:", pg.evaluate("S.build&&S.build.longshots"))
    pg.evaluate("window.load=async()=>{};renderBuild()")
    if CALLS and any(c is not False for c in CALLS):
        print("PROBLEMS: long shots were worked out without the Pause switch read fresh:", CALLS)
    n = pg.locator(".lscard").count()
    if n != 1:
        print("PROBLEMS: expected one long-shot card on top of Build, got", n)
    else:
        txt = pg.locator(".lscard").first.inner_text()
        for want in ("Long shot", "7 picks", "12%", "to hit", "+$1.35", "expected", "$4.60", "pays $42",
                     "Likely to cash out early for a profit: 52%", "Celtics", "Magic", "Get price"):
            if want.lower() not in txt.lower():
                print("PROBLEMS: the long-shot card is missing", repr(want), "|", txt.replace("\n", " / ")[:300])
        if pg.locator(".sech[data-k='ls']").count() != 1:
            print("PROBLEMS: no 'Long shots' section header")
        h = pg.evaluate("Math.min(...[...document.querySelectorAll('.lscard .btn')].map(b=>b.getBoundingClientRect().height))")
        if h < 36:
            print("PROBLEMS: the card's button is too short:", h)
        if pg.evaluate("document.documentElement.scrollWidth>window.innerWidth+1"):
            print("PROBLEMS: sideways scroll on a phone")
        pg.locator(".lscard").first.scroll_into_view_if_needed(); time.sleep(.8)
        pg.screenshot(path=os.path.join(SHOTS, "longshots_card.png"))
        # Get price: the shown picks go to the Mac; a quote that clears = green Buy; Buy = the usual combo accept
        ACTS = []

        def act(route):
            try:
                b = __import__("json").loads(route.request.post_data or "{}")
            except Exception:
                b = {}
            if b.get("a") in ("longshot", "buy"):
                ACTS.append(b)
                body = {"ok": True, "i": 9, "pays": 43.2, "stake": 4.6, "pct": 1.07, "clears": True} if b["a"] == "longshot" \
                    else {"ok": True, "pays": 43.2}
                route.fulfill(status=200, content_type="application/json", body=__import__("json").dumps(body))
            else:
                route.continue_()
        pg.route("**/app/api/act", act)
        pg.locator(".lscard .btn.pri").first.click()
        pg.wait_for_function("document.querySelector('.lscard .btn.pri.yes')", timeout=10000)
        acts = ACTS
        if not acts or acts[0].get("a") != "longshot" or sorted(acts[0].get("legs") or []) != sorted(l["ticker"] for l in LEGS):
            print("PROBLEMS: Get price didn't send the long shot's own picks:", acts)
        btxt = pg.locator(".lscard .btn.pri").first.inner_text()
        if "Buy" not in btxt or "$43" not in btxt or pg.locator(".lscard .qline .qt").count() != 1:
            print("PROBLEMS: a fresh quote should show Buy $4.60 → $43 with a draining bar:", btxt)
        time.sleep(.6); pg.screenshot(path=os.path.join(SHOTS, "longshots_quote.png"))
        pg.locator(".lscard .btn.pri").first.click()
        pg.wait_for_function("document.querySelector('.okcard')", timeout=10000)
        acts = ACTS
        if not any(a.get("a") == "buy" and a.get("i") == 9 for a in acts):
            print("PROBLEMS: Buy didn't go through the combo accept with the quoted combo's number:", acts)
        pg.evaluate("closeModal&&closeModal()"); time.sleep(.4)
        if "bought" not in pg.locator(".lscard").first.inner_text().lower():
            print("PROBLEMS: the card should say you bought it")
    # nothing vetted: no card on top; the empty state sits with the board; random combos under 'Surprise me'
    pg.evaluate("S.build=Object.assign({},S.build,{longshots:{recs:[],why:'No long shot clears every check right now.'}});S.adv=true;renderBuild()")
    if pg.locator(".lscard").count():
        print("PROBLEMS: a long-shot card drawn with nothing vetted")
    if "No long shot" not in (pg.locator(".lsempty").first.inner_text() if pg.locator(".lsempty").count() else ""):
        print("PROBLEMS: the empty state should say why there's no long shot")
    if pg.locator(".sech", has_text="Surprise me").count() != 1 or pg.locator(".sech", has_text="More combo ideas").count():
        print("PROBLEMS: the random combos should sit under 'Surprise me' (and 'More combo ideas' is gone)")
    if pg.evaluate("document.documentElement.scrollWidth>window.innerWidth+1"):
        print("PROBLEMS: sideways scroll on a phone (empty state)")
    pg.locator(".lsempty").first.scroll_into_view_if_needed(); time.sleep(.5)
    pg.screenshot(path=os.path.join(SHOTS, "longshots_empty.png"))
    print("errs:", errs)
    if errs:
        print("PROBLEMS: page errors", errs)
    br.close()
