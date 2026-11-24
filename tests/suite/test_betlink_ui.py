# CHECK: group=page secs=30
"""Tapping a trade notification opens that bet (Pete, 2026-11-23): a link '#b=<ticker>' opens the single bet's page
the way tapping its row does (a fresh start and an app that is already open), and an unknown, finished or malformed
link just leaves you on Live. Phone-size page (390x844); scripted /app/api/live and /app/api/game answers, nothing real."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright

T0 = "KXNCAAMBTOTAL-26NOV21DUKEUNC-157"
SING = [{"t": T0, "kind": "total", "sport": "ncaamb", "side": "yes", "label": "Over 157.5 points", "game": "Duke at North Carolina: Total Points",
         "event": "KXNCAAMBTOTAL-26NOV21DUKEUNC", "n": 16, "cost": 9.6, "pays": 16, "worth": 15.04, "chance": 0.97, "state": "live", "res": None,
         "score": "UNC 70-69 DUKE 2H 6:10", "starts": "", "how": "", "url": "", "own": False, "self": False, "sell_at": None}]
LIVE = {"at": time.time(), "balance": 211.0, "combos": [], "today": {}, "singles": SING, "auto_sell": True, "riding": 0, "staked": 9.6,
        "chance_one": 0, "best": 16, "cash_now": 0, "hold_value": 0, "locked": 0, "week_pl": 0.0, "games": [], "risk": None, "todo": [],
        "fresh": {"now": time.time(), "built": time.time() - 2, "scores": 3, "fast": True}}
fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


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


def page(br):
    p = br.new_page(viewport={"width": 390, "height": 844})
    errs = []
    p.on("pageerror", lambda e: errs.append(str(e)))
    p.route("**/app/api/live*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(LIVE)))
    p.route("**/app/api/game*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": False})))
    return p, errs


with sync_playwright() as pw:
    br = pw.chromium.launch()
    for name, h, want in (("a bet you hold", "#b=" + T0, True), ("a malformed link", "#b=%3Cimg%20src%3Dx%3E", False), ("an empty link", "#b=", False)):
        p, errs = page(br)
        p.goto(B + "/app" + h)
        if want:
            check(f"start from {name}: its page opens", until(p, "S.gameOpen===%s&&!!document.querySelector('#modal.on')" % json.dumps(T0), 15))
        else:
            until(p, "!!document.querySelector('.stbl')", 15)
            p.wait_for_timeout(1500)
            check(f"start from {name}: just Live, nothing opened", p.evaluate("S.view==='live'&&!S.gameOpen&&!document.querySelector('#modal.on')"))
        check(f"start from {name}: the link is taken off the address", p.evaluate("location.hash===''"))
        check(f"start from {name}: no JS errors", not errs)
        if errs:
            print(errs)
        if want and p.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
            fails.append("page scrolls sideways")
        p.close()
    p, errs = page(br)
    p.goto(B + "/app#b=KXNBAGAME-GONE-1")
    check("a bet nobody has a record of: the 'we can't find that bet' page, not a silent Live",
          until(p, "!!document.querySelector('#modal.on')&&document.querySelector('#sheet').innerText.includes(\"We can't find that bet\")", 15))
    check("that page has no JS errors", not errs)
    p.close()
    # an app that is already open follows the link
    p, errs = page(br)
    p.goto(B + "/app")
    until(p, "!!document.querySelector('.stbl')", 15)
    p.evaluate("location.hash='#b='+encodeURIComponent(%s)" % json.dumps(T0))
    check("an open app follows '#b=<ticker>' to the bet", until(p, "S.gameOpen===%s" % json.dumps(T0), 8))
    p.evaluate("closeModal()")
    until(p, "!document.querySelector('#modal.on')", 4)
    p.evaluate("location.hash='#b=KXNBAGAME-GONE-1'")
    check("an open app given a gone bet shows the not-found page", until(p, "document.querySelector('#sheet').innerText.includes(\"We can't find that bet\")", 8))
    check("open app: no JS errors", not errs)
    br.close()

if fails:
    print("PROBLEMS:", "; ".join(fails))
else:
    print("PASS bet links open the bet, and fall back to Live")
