# CHECK: group=page secs=25
"""Issue #210 on the page: a combo smart sell is looking after gets "cash out" words only when the Mac says smart sell
would sell it now (`nudge`), and a "time to cash out" toast or a notification link ('/#c=<ticker>') opens that combo's
page. Scripted /app/api/live and /app/api/combo answers (no real engine build); nothing real is touched."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("CW_SHOTS", "")
from playwright.sync_api import sync_playwright

T = "KXMVENFLMULTIGAMEEXTENDED-S2026COMBO24"


def until(pg, js, secs=12):
    end = time.time() + secs
    while time.time() < end:
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        time.sleep(.15)
    return False


def leg(i, res=None):
    return {"ticker": f"KXNFLGAME-26NOV29T{i:02d}-T{i:02d}", "name": f"Team {i}", "opp": f"Rival {i}", "chance": .67,
            "live": None, "res": res, "state": "done" if res else "pre", "phase": "", "note": "", "short": "",
            "score": "", "sc": None, "src": "", "starts": "Sun 9:30 AM", "sport": "nfl", "side": "yes", "url": ""}


def combo(nudge=None, verdict="sell", real=False, moment=True):
    return {"t": T, "i": 24, "label": "Combo 24", "group": "pending", "kind": "waiting", "sports": ["nfl"],
            "p": .0147, "pays": 330.0, "cost": 4.99, "back": 0, "live": False, "hold_value": 4.85, "won_some": True,
            "offer": 9.0 if nudge else 4.14, "offer_real": real, "offer_live": None, "fair_value": 4.85,
            "overpay": None, "offer_age": None, "verdict": verdict, "why": "A sure $4.14 beats a 1% shot at $330 for you.",
            "threshold": 4.9, "moment": {"why": "smart", "at": 4.0} if moment else None, "hedge": None,
            "nudge": nudge, "self": False, "own": False, "legs": [leg(0, "yes")] + [leg(i) for i in range(1, 12)]}


def payload(c, todo=()):
    return {"at": time.time(), "balance": 211.0, "combos": [c], "today": {}, "singles": [], "auto_sell": True,
            "riding": 1, "staked": 4.99, "chance_one": .0147, "best": 330.0, "cash_now": 4.14, "hold_value": 4.85,
            "locked": 0, "week_pl": 0.0, "games": [], "risk": None, "todo": list(todo),
            "fresh": {"now": time.time(), "built": time.time() - 2, "scores": 3, "fast": True}}


state = {"p": payload(combo())}
fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/app/api/live*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(state["p"])))
    pg.route("**/app/api/combo*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                       body=json.dumps({"combo": state["p"]["combos"][0],
                                                                        "history": {"offers": [], "ticks": {}}})))
    pg.goto(B + "/app")
    pg.evaluate("go('live')")
    until(pg, "!!document.querySelector('.trow')", 20)

    # Combo 24 as Pete saw it: the old plan says sell on an estimate, smart sell doesn't (no nudge)
    txt = pg.evaluate("document.querySelector('main').innerText")
    check("no 'Good time to cash out' bar for a combo smart sell holds", not pg.evaluate("!!document.querySelector('.moment-bar')"))
    check("no 'check Kalshi's price' Do now card for it", "check Kalshi's price" not in txt)
    check("Live says nothing to do instead", "Nothing to do right now" in txt)
    check("the row says HOLD, not the old plan's SELL", pg.evaluate("document.querySelector('.trow .verdict').textContent.trim()") == "HOLD")
    pg.evaluate("openCombo(%s)" % json.dumps(T))
    until(pg, "document.querySelector('#sheet').innerText.includes('PICKS')||document.querySelector('#sheet').innerText.includes('Picks')", 8)
    sh = pg.evaluate("document.querySelector('#sheet').innerText")
    check("its page says HOLD and leaves out the plan's 'a sure $4.14 beats...' line", "HOLD" in sh and "A sure $4.14" not in sh)
    pg.evaluate("closeModal()")
    until(pg, "!document.querySelector('#modal.on')", 4)

    # smart sell would sell it now, on a real offer: the bar and the Do now card come back
    state["p"] = payload(combo(nudge={"why": "smart", "offer": 9.0}, real=True), todo=[T])
    pg.evaluate("load('live',true)")
    check("with a nudge the moment bar shows", until(pg, "!!document.querySelector('.moment-bar')", 8))
    check("and the Do now cash-out card", until(pg, "document.querySelector('main').innerText.includes('Combo 24: cash out for')", 4))
    # "I'll sell it" combos keep the plan's advice (smart sell isn't looking after them)
    c = combo(); c["self"] = True
    state["p"] = payload(c)
    pg.evaluate("load('live',true)")
    check("an 'I'll sell it' combo still gets the plan's 'check Kalshi's price' card",
          until(pg, "document.querySelector('main').innerText.includes(\"check Kalshi's price\")", 8))
    state["p"] = payload(combo(nudge={"why": "smart", "offer": 9.0}, real=True), todo=[T])
    pg.evaluate("load('live',true)")
    until(pg, "!!document.querySelector('.moment-bar')", 8)

    # the toast from the Mac's live link: tapping it opens the combo
    pg.evaluate("""S.es&&S.es.onmessage({data:JSON.stringify({kind:'advice',combo:%s,text:'Combo 24: smart sell is cashing out at $9.00'})})""" % json.dumps(T))
    check("the advice toast shows and is tappable", until(pg, "document.querySelector('#toast.on.tap')", 4))
    if SHOTS:
        pg.wait_for_timeout(450)
        pg.screenshot(path=os.path.join(SHOTS, "cashnudge_toast.png"))
    pg.click("#toast")
    check("tapping it opens Combo 24's page", until(pg, "S.comboOpen===%s&&document.querySelector('#modal.on')&&document.querySelector('#sheet').innerText.includes('Combo 24')" % json.dumps(T), 8))
    if SHOTS:
        pg.wait_for_timeout(600)
        pg.screenshot(path=os.path.join(SHOTS, "cashnudge_combo.png"))
    pg.evaluate("closeModal()")
    until(pg, "!document.querySelector('#modal.on')", 4)
    pg.evaluate("toast('A plain toast',3000)")
    check("a plain toast is not a button (taps go through)", until(pg, "document.querySelector('#toast.on')&&!document.querySelector('#toast.tap')", 3))

    # an open app follows a notification link
    pg.evaluate("location.hash='#c='+encodeURIComponent(%s)" % json.dumps(T))
    check("an open app follows '#c=<ticker>' to the combo", until(pg, "S.comboOpen===%s" % json.dumps(T), 8))
    check("the link is taken off the address", pg.evaluate("location.hash===''"))
    pg.evaluate("closeModal()")

    # a fresh start from a notification tap
    for name, h, want in (("a known combo", "#c=" + T, True), ("an old or unknown combo", "#c=KXMVE-GONE-1", False),
                          ("a malformed link", "#c=%3Cimg%20src%3Dx%3E", False)):
        p2 = br.new_page(viewport={"width": 390, "height": 844})
        e2 = []
        p2.on("pageerror", lambda e: e2.append(str(e)))
        p2.route("**/app/api/live*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(state["p"])))
        p2.route("**/app/api/combo*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                           body=json.dumps({"combo": state["p"]["combos"][0], "history": {"offers": [], "ticks": {}}})))
        p2.goto(B + "/app" + h)
        if want:
            check(f"start from {name}: its page opens", until(p2, "S.comboOpen===%s&&!!document.querySelector('#modal.on')" % json.dumps(T), 15))
        else:
            until(p2, "!!document.querySelector('.trow')", 15)
            p2.wait_for_timeout(1500)
            check(f"start from {name}: just Live, nothing opened",
                  p2.evaluate("S.view==='live'&&!S.comboOpen&&!document.querySelector('#modal.on')"))
        check(f"start from {name}: no JS errors", not e2)
        if e2:
            print(e2)
        p2.close()

    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
        fails.append("page scrolls sideways")
    check("no JS errors", not errs)
    if errs:
        print(errs)
    br.close()

if fails:
    print("PROBLEMS:", "; ".join(fails))
else:
    print("PASS cash-out nudges and combo links on the page")
