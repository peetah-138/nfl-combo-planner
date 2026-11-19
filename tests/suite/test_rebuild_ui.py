# Build page while a fresh panel is put together: no "10 minutes" promise, a Look now button, live progress from the
# Mac's notes (redrawn in place every 2 s), and the new panel (or the reason there isn't one) dropping in by itself.
import sys, os, time, threading, re, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
ENG = {}
def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    ENG["A"] = A
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); time.sleep(3)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
PROB = []
def check(name, cond):
    print(("ok   " if cond else "PROBLEMS: ") + name)
    if not cond: PROB.append(name)
def wait(pg, js, secs=8):
    t = time.time()
    while time.time() - t < secs:
        try:
            if pg.evaluate(js): return True
        except Exception: pass
        time.sleep(.2)
    return False
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 390, "height": 844}, color_scheme="dark", has_touch=True, is_mobile=True)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/app"); time.sleep(4)
    for _ in range(40):
        if ENG.get("A") and ENG["A"].STORE.get("db"): break
        time.sleep(.25)
    A = ENG["A"]
    A.store_x("delete from panel", ())
    for f in (A.REBUILD_FLAG, A.REBUILD_STATE):
        try: os.remove(f)
        except OSError: pass
    pg.evaluate("S.pview='all';go('build')")
    check("empty panel says there's no panel yet", wait(pg, "/No panel yet today/.test(($('#pblock')||{}).innerText||'')", 15))
    txt = pg.evaluate("$('#pblock').innerText")
    check("no 10-minute promise", "10 minutes" not in txt and "Check back shortly" not in txt)
    pg.locator("#pblock button", has_text="Look now").tap()
    t0 = time.time()
    while not os.path.exists(A.REBUILD_FLAG) and time.time() - t0 < 4: time.sleep(.1)
    check("Look now asks the Mac (flag written)", os.path.exists(A.REBUILD_FLAG))
    check("page shows it's starting", wait(pg, "/Putting together a fresh panel/.test($('#pblock').innerText)&&/Starting/.test($('#pblock').innerText)", 6))
    pg.evaluate("window.__card=document.querySelector('#pblock .rbcard')")
    # the Mac picks it up and works through the sports
    A.rebuild_asked(); A._rebuild_note(state="running", at=time.time(), sport="nba", i=1, n=6)
    check("progress names the sport and count", wait(pg, "/Looking at NBA… 2 of 6 sports/.test($('#pblock').innerText)", 6))
    check("progress bar moved", pg.evaluate("parseFloat(document.querySelector('#pblock .rbtrack i').style.width)") > 10)
    check("progress redraws in place (no full page redraw)", pg.evaluate("window.__card===document.querySelector('#pblock .rbcard')"))
    A._rebuild_note(state="running", at=time.time(), sport="", i=6, n=6, step="choosing")
    check("then says it's picking the mix", wait(pg, "/Picking the best mix/.test($('#pblock').innerText)", 6))
    # done: a draft appears by itself
    fx = json.load(open("panel_fixture.json"))["panel"]; now = time.time()
    fx["at"] = now; fx["status"] = "draft"
    for c in fx["items"]:
        c["kick"] = now + 3 * 3600; c["buy_at"] = now + 2 * 3600; c.pop("state", None)
    fx.pop("status", None)
    A.panel_save_draft(fx, "real")
    A._rebuild_note(state="done", at=now, found=len(fx["items"]), kind="panel", why="", n=6)
    check("new panel drops in by itself", wait(pg, "/Approve \\d+ bet/.test($('#pblock').innerText)", 8))
    check("tells you it's ready", wait(pg, "/fresh panel is ready/.test((document.querySelector('.toast')||{}).innerText||'')", 4))
    check("progress polling stopped", wait(pg, "!S.rbT", 4))
    # a rebuild that found nothing says why
    A.store_x("delete from panel", ())
    A._rebuild_note(state="done", at=time.time(), found=0, kind="panel", games=6, n=6,
                    why="Checked 6 upcoming games: none is priced better than its real chance right now (Kalshi is in line with the sportsbooks).")
    pg.evaluate("load('build')")
    check("nothing found: says why", wait(pg, "/No bets clear the bar right now/.test($('#pblock').innerText)&&/Checked 6 upcoming games/.test($('#pblock').innerText)", 8))
    check("and offers to look again", pg.locator("#pblock button", has_text="Look again now").count() == 1)
    check("still no 10-minute promise", "10 minutes" not in pg.evaluate("$('#pblock').innerText"))
    check("no sideways scroll on a phone", not pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"))
    if os.environ.get("SHOTS"): pg.screenshot(path=os.environ["SHOTS"])
    print("errs:", errs)
print("PROBLEMS" if PROB else "all good")
