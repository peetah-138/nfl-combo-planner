# CHECK: group=page secs=4
"""The Live hero's "worth now if sold" follows the live leg prices (display only, Refs #80). The engine adds a
separate `offer_live` field to each combo view and sums it into `cash_now` when there is no fresh real quote; the
page shows it as the hero's "≈" number and on the combo row, keeping the tilde. Here we drive the SPA with scripted
/app/api/live answers (no real engine build) and assert the wiring: the hero and row show the live-priced number,
the tilde stays, and when a real quote is present the real number wins. Nothing real is touched."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright


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


# One pending combo, no real quote (offer_real false). offer = the old frozen estimate (8.00),
# offer_live = the new live-priced one (9.34). The hero must show 9.34 with a tilde, not 8.00.
def live_payload(offer_live=9.34, offer_real=False, extra_offer=None):
    c = {"t": "KXMVE-1", "i": 1, "label": "Combo 1", "group": "pending", "kind": "playing",
         "sports": ["nba"], "p": 0.22, "pays": 41.2, "cost": 5.0, "back": 0, "live": True,
         "hold_value": 9.06, "won_some": False, "offer": 8.00, "offer_real": offer_real,
         "offer_live": offer_live, "fair_value": 9.06, "overpay": None, "offer_age": None,
         "verdict": "hold", "why": "", "threshold": None, "moment": None, "hedge": None,
         "self": False, "own": False,
         "legs": [{"ticker": "KXNBAGAME-X-BOS", "name": "Celtics", "opp": "Knicks", "chance": .62, "live": .70,
                   "res": None, "state": "live", "phase": "on", "note": "", "short": "", "score": "", "sc": None,
                   "src": "", "starts": "", "sport": "nba", "side": "yes", "url": ""},
                  {"ticker": "KXNBAGAME-Y-DEN", "name": "Nuggets", "opp": "Lakers", "chance": .55, "live": .65,
                   "res": None, "state": "live", "phase": "on", "note": "", "short": "", "score": "", "sc": None,
                   "src": "", "starts": "", "sport": "nba", "side": "yes", "url": ""}]}
    # cash_now follows offer_live when there's no real quote (what the engine does), else offer.
    cash_now = (offer_live if (not offer_real and offer_live is not None) else c["offer"])
    if extra_offer is not None:
        cash_now = extra_offer
    return {"at": time.time(), "balance": 211.0, "combos": [c], "today": {}, "singles": [],
            "auto_sell": False, "riding": 1, "staked": 5.0, "chance_one": 0.22, "best": 41.2,
            "cash_now": round(cash_now, 2), "hold_value": 9.06, "locked": 0, "week_pl": 0.0,
            "games": [], "risk": None, "todo": [],
            "fresh": {"now": time.time(), "built": time.time() - 2, "scores": 3, "fast": True}}


state = {"p": live_payload()}


def answer(route):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(state["p"]))


fails = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/app/api/live*", answer)
    pg.goto(B + "/app")
    pg.evaluate("go('live')")

    # The hero's big number is driven by cash_now (=offer_live here). It rolls to data-v; wait for the roll.
    ok = until(pg, "!!document.querySelector('[data-num=\"h:worth\"]')", 20)
    print("hero number present:", ok)
    if not ok:
        fails.append("no hero number")
    else:
        ok = until(pg, "Math.abs(parseFloat(document.querySelector('[data-num=\"h:worth\"]').dataset.v)-9.34)<0.01", 8)
        hv = pg.evaluate("document.querySelector('[data-num=\"h:worth\"]').dataset.v")
        print("hero follows the live-priced estimate (9.34):", ok, "| data-v:", hv)
        if not ok:
            fails.append(f"hero number is {hv}, not the live-priced 9.34")
        # the tilde stays (it is still an estimate, not a real quote)
        pre = pg.evaluate("document.querySelector('[data-num=\"h:worth\"]').dataset.pre")
        txt = pg.evaluate("document.querySelector('[data-num=\"h:worth\"]').textContent")
        print("tilde kept:", pre, repr(txt))
        if "≈" not in (pre or "") and "≈" not in (txt or ""):
            fails.append("the hero lost its tilde")

    # the combo row shows the live-priced number too (data-num o:<t>), with the tilde
    ok = until(pg, "!!document.querySelector('[data-num=\"o:KXMVE-1\"]')", 10)
    if ok:
        ok = until(pg, "Math.abs(parseFloat(document.querySelector('[data-num=\"o:KXMVE-1\"]').dataset.v)-9.34)<0.01", 6)
        rv = pg.evaluate("document.querySelector('[data-num=\"o:KXMVE-1\"]').dataset.v")
        print("combo row follows the live-priced estimate:", ok, "| data-v:", rv)
        if not ok:
            fails.append(f"combo row offer is {rv}, not 9.34")
    else:
        fails.append("no combo row offer element")

    # When a real Kalshi quote arrives (offer_real true), the real number wins and offer_live is ignored.
    state["p"] = live_payload(offer_live=9.34, offer_real=True, extra_offer=8.00)
    # offer stays 8.00 (the "real" offer value on the row); force a reload of the view
    pg.evaluate("load('live',true)")
    ok = until(pg, "document.querySelector('[data-num=\"o:KXMVE-1\"]')&&!document.querySelector('[data-num=\"o:KXMVE-1\"]').dataset.pre.includes('≈')", 8)
    rpre = pg.evaluate("(document.querySelector('[data-num=\"o:KXMVE-1\"]')||{}).dataset?document.querySelector('[data-num=\"o:KXMVE-1\"]').dataset.pre:'?'")
    print("real quote drops the tilde and shows the real number:", ok, "| pre:", repr(rpre))
    if not ok:
        fails.append("a real quote did not take over from offer_live")

    pg.screenshot(path="offerlive_hero.png")
    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
        fails.append("page scrolls sideways")
    print("errs:", errs)
    if errs:
        fails.append("JS errors: " + str(errs))
    br.close()

if fails:
    print("PROBLEMS:", "; ".join(fails))
else:
    print("PASS offer_live wiring on the Live hero")
