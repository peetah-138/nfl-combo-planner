# Issue #62: "Add to today's panel" on the New-since-you-approved card sends once, says Adding… then Added, and the
# card leaves at once, even if a refresh from the Mac still lists the bet. Taps while it's on its way do nothing.
import sys, os, time, threading, json
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
threading.Thread(target=W.webapp_main, daemon=True).start(); time.sleep(3)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
FIX = open("panel_fixture4.json").read()
from playwright.sync_api import sync_playwright
probs = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 390, "height": 844}, color_scheme="dark", has_touch=True, is_mobile=True)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    acts = []

    def on_act(route):
        body = route.request.post_data or ""
        if "panel_add" in body:
            acts.append(json.loads(body))
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "msg": "Added 1 to today's panel. The Mac is buying it now."}))
        else:
            route.continue_()
    pg.route("**/app/api/act", on_act)
    # the Mac's panel answer still lists the extra (a refresh that left before the add was saved)
    pg.route("**/app/api/panel*", lambda r: r.fulfill(status=200, content_type="application/json", body=FIX))
    pg.goto(B + "/app"); time.sleep(5); pg.evaluate("go('build')"); time.sleep(6)
    pg.evaluate("S.panel=" + FIX + ";renderBuild()"); time.sleep(.4)
    if not pg.locator("text=New since you approved").count():
        probs.append("extras card not shown")
    pg.locator("button", has_text="Add 1 to today").first.tap(); time.sleep(.4)
    if not pg.locator("button", has_text="Tap again to add").count():
        probs.append("first tap didn't arm the button")
    # the confirming tap, then two more straight away (a double tap, an impatient thumb)
    state = pg.evaluate("""()=>{const b=[...document.querySelectorAll('button')].find(x=>/Tap again to add/.test(x.textContent));
      b.click();const s={dis:b.disabled,txt:b.textContent};b.click();b.click();panelAdd(b,'extra');return s;}""")
    print("after the confirming tap:", state)
    if not state["dis"] or "Adding" not in state["txt"]:
        probs.append("button not disabled / not 'Adding…' after the tap: %r" % state)
    seen_added = False
    for _ in range(20):
        time.sleep(.1)
        if pg.locator("button", has_text="Added").count():
            seen_added = True; break
    if not seen_added:
        probs.append("never showed 'Added'")
    time.sleep(2.5)
    print("add requests sent:", len(acts))
    if len(acts) != 1:
        probs.append(f"{len(acts)} add requests sent, want exactly 1")
    left = pg.locator("text=New since you approved").count()
    print("extras card after add:", left)
    if left:
        probs.append("the extras card stayed after Add")
    # the page refreshing again (the Mac's answer still lists it) doesn't bring the card back
    pg.evaluate("load('build')"); time.sleep(1.5)
    if pg.locator("text=New since you approved").count() or pg.locator("button", has_text="Add 1 to today").count():
        probs.append("the card came back on a refresh")
    if len(acts) != 1:
        probs.append("a refresh sent another add")
    print("errs:", errs)
    br.close()
if probs:
    print("PROBLEMS:", probs)
