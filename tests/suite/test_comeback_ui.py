# CHECK: group=page
# In-play comebacks card (issue #348), phone size, dark: Results > What's working shows a folded "In-play comebacks"
# card; opened, each league's checked count, predicted (old -> new) vs actual, what the new model held back, and the
# other side's paper record with the plain note that nothing is shown or bought from it. Empty state says when checks
# get scored. No sideways scroll, no page errors. Display only (fake analytics data injected into the page).
import sys, os, threading, time
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("CB_SHOTS") or "."
DATA = {"leagues": [{"league": "nba", "name": "NBA", "n": 34, "pred_old": 0.41, "pred_new": 0.27, "actual": 0.24,
                     "old_pass": 12, "new_pass": 7, "held": 5, "held_rec": 1, "held_pnl": -12.4, "few": False,
                     "picks": {"this": 4, "other": 2, "neither": 28}, "pick_pnl": 3.1, "pick_n": 6},
                    {"league": "ncaamb", "name": "Men's college basketball", "n": 6, "pred_old": 0.38, "pred_new": 0.3,
                     "actual": 0.33, "old_pass": 2, "new_pass": 2, "held": 0, "held_rec": 0, "held_pnl": 0, "few": True}],
        "other": {"n": 21, "pass": 3, "actual": 0.19, "pass_actual": 0.33, "pass_pnl": 1.2, "pnl": -4.1}, "table": 412}
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/app"); pg.wait_for_function("typeof S==='object'", timeout=60000)
    __import__("upwait").go_and_hold(pg, "results")
    pg.wait_for_function("S.res", timeout=60000)
    pg.evaluate("window.load=async()=>{}")
    js = "d=>{S.an=Object.assign({at:Date.now()/1000},S.an||{},{comeback:d});S.cbOpen=false;renderResults();}"
    pg.evaluate(js, DATA)
    if pg.locator(".cbp").count() != 1:
        print("PROBLEMS: no In-play comebacks card on Results")
    else:
        head = pg.locator(".cbh").inner_text()
        if "In-play comebacks" not in head or "40 scored" not in head:
            print("PROBLEMS: folded header should name the card and the count:", head)
        if pg.locator(".cbp .antbl").count():
            print("PROBLEMS: the card should start folded")
        pg.locator(".cbh").click()
        pg.wait_for_function("document.querySelector('.cbp .antbl')", timeout=5000)
        txt = pg.locator(".cbp").inner_text()
        for want in ("NBA", "34", "41% → 27%", "24%", "1 recovered", "would have made −$12.40", "too few to trust", "paper only",
                     "21 checked", "3 would have cleared", "Nothing is shown or bought",
                     "Which side, game by game", "the side checked 4, the other side 2, neither 28", "+$3.10"):
            if want not in txt:
                print("PROBLEMS: the open card is missing", repr(want), "|", txt.replace("\n", " / ")[:400])
        h = pg.evaluate("document.querySelector('.cbh').getBoundingClientRect().height")
        if h < 44:
            print("PROBLEMS: the card's header is under 44px:", h)
        if pg.evaluate("document.documentElement.scrollWidth>window.innerWidth+1"):
            print("PROBLEMS: sideways scroll on a phone")
        pg.locator(".cbp").scroll_into_view_if_needed(); time.sleep(.5)
        pg.screenshot(path=os.path.join(SHOTS, "comeback_card.png"))
    pg.evaluate(js, {"leagues": [], "other": None, "table": 0})
    pg.evaluate("S.cbOpen=true;renderResults()")
    if "No in-play checks scored yet" not in (pg.locator(".cbp").inner_text() if pg.locator(".cbp").count() else ""):
        print("PROBLEMS: the empty state should say checks are scored after each game")
    if pg.evaluate("document.documentElement.scrollWidth>window.innerWidth+1"):
        print("PROBLEMS: sideways scroll on a phone (empty)")
    pg.locator(".cbp").scroll_into_view_if_needed(); time.sleep(.4)
    pg.screenshot(path=os.path.join(SHOTS, "comeback_empty.png"))
    # #438: closing slides the body shut instead of snapping (still there partway, gone after), and is instant with reduced motion
    pg.evaluate(js, DATA); pg.evaluate("S.cbOpen=true;renderResults()")
    pg.locator(".cbh").click(); time.sleep(.08)
    mid = pg.evaluate("(()=>{const b=document.querySelector('.cbbody');return b?b.getBoundingClientRect().height:-1})()")
    time.sleep(.5)
    if mid <= 0:
        print("PROBLEMS: the body vanished at once instead of sliding shut (height partway:", mid, ")")
    if pg.locator(".cbbody").count() or pg.evaluate("S.cbOpen") or pg.evaluate("S.cbClosing"):
        print("PROBLEMS: the card did not finish closing")
    if pg.locator(".cbh").get_attribute("aria-expanded") != "false":
        print("PROBLEMS: the header does not say it is closed")
    pg.locator(".cbh").click(); time.sleep(.5)
    if not pg.locator(".cbbody").count():
        print("PROBLEMS: it did not open again after a slide-close")
    pg.emulate_media(reduced_motion="reduce")
    pg.locator(".cbh").click(); time.sleep(.1)
    if pg.locator(".cbbody").count():
        print("PROBLEMS: with reduced motion the close should be immediate")
    pg.emulate_media(reduced_motion="no-preference")
    # #455: the Buying row is announced as a status and busy; its spinner is hidden from assistive tech
    row = pg.evaluate("""(()=>{S.ibuy={x1:1};const d=document.createElement('div');d.innerHTML=ideaButtons({id:'x1',n:1},{},false,0,false);const r=d.firstElementChild;
      return {role:r.getAttribute('role'),busy:r.getAttribute('aria-busy'),spin:[...r.querySelectorAll('.spin')].every(e=>e.getAttribute('aria-hidden')==='true')}})()""")
    if row != {"role": "status", "busy": "true", "spin": True}:
        print("PROBLEMS: the Buying row is not role=status / aria-busy with a hidden spinner:", row)
    print("errs:", errs)
    if errs:
        print("PROBLEMS: page errors", errs)
    br.close()
