# CHECK: group=page secs=25
"""Dismiss on the hedge card (display only): the card has a thumb-sized Dismiss next to Hedge; tapping it hides the card at once,
sends ONE hedge_dismiss action (never go/hedgego/any order action), and the card stays hidden when the Mac says
hedge_dismissed (a reload). A dismissed hedge that comes back (flag cleared) shows again. Moments rows can be cleared
and stay cleared across a reload. Scripted /app/api/live and /app/api/act answers; nothing real is touched. Screenshots at
390px light and dark go to CW_SHOTS when set."""
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

T = "KXMVENFLMULTIGAMEEXTENDED-S2026HEDGE1"


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


def combo(dismissed=False):
    return {"t": T, "i": 3, "label": "Chicago + Las Vegas", "group": "pending", "kind": "waiting", "sports": ["nfl"],
            "p": .4, "pays": 7.45, "cost": 2.0, "back": 0, "live": False, "hold_value": 3.41, "hold_ce": 3.41, "won_some": True,
            "offer": 3.39, "offer_real": False, "offer_live": None, "fair_value": 3.41, "overpay": None, "offer_age": None,
            "verdict": "hold", "why": "", "threshold": 3.46, "moment": None, "nudge": None, "self": False, "own": False,
            "hedge": {"name": "Cleveland", "cost": 7.45, "locked": 3.11, "price": .5, "done": 0}, "hedge_dismissed": dismissed,
            "legs": [leg(0, "yes"), leg(1, "yes"), leg(2)]}


def payload(c):
    return {"at": time.time(), "balance": 211.0, "combos": [c], "today": {}, "singles": [], "auto_sell": True,
            "riding": 1, "staked": 2.0, "chance_one": .4, "best": 7.45, "cash_now": 3.39, "hold_value": 3.41,
            "locked": 0, "week_pl": 0.0, "games": [], "risk": None, "todo": [],
            "fresh": {"now": time.time(), "built": time.time() - 2, "scores": 3, "fast": True}}


state = {"dismissed": False}
acts = []
fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def act(route):
    d = json.loads(route.request.post_data or "{}")
    acts.append(d.get("a"))
    if d.get("a") == "hedge_dismiss":
        state["dismissed"] = True
    route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "msg": "Hedge hidden."}))


with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        acts.clear(); state["dismissed"] = False
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=scheme)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/app/api/live*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(payload(combo(state["dismissed"])))))
        pg.route("**/app/api/act", act)
        pg.goto(B + "/app")
        pg.evaluate("go('live')")
        until(pg, "!!document.querySelector('.dcard.warn')", 20)
        time.sleep(.8)
        check(f"{scheme}: the hedge card shows", "lock in" in pg.evaluate("document.querySelector('main').innerText"))
        box = pg.evaluate("(()=>{const b=document.querySelector('.hdis');const r=b&&b.getBoundingClientRect();return r?[r.width,r.height]:null})()")
        check(f"{scheme}: Dismiss is thumb-sized (44px+ tall, 70px+ wide)", bool(box) and box[1] >= 43.9 and box[0] >= 70)
        card = pg.evaluate("document.querySelector('.dcard.warn').innerText")
        check(f"{scheme}: the hedge card names its numbers (Hedge costs, Locks in, You paid) and has no let-it-ride jargon", all(w in card for w in ("HEDGE COSTS", "LOCKS IN", "YOU PAID")) and "let-it-ride" not in card.lower())
        check(f"{scheme}: the hedge card says a dismissed card comes back on a 20% / 50 cent change", "comes back" in card and "20%" in card and "50¢" in card)
        check(f"{scheme}: no sideways scroll", not pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"))
        if SHOTS:
            os.makedirs(SHOTS, exist_ok=True)
            pg.screenshot(path=os.path.join(SHOTS, f"hedge_card_{scheme}.png"))
        pg.click(".hdis")
        until(pg, "!document.querySelector('.dcard.warn')", 5)
        check(f"{scheme}: tapping Dismiss hides the card at once", not pg.evaluate("!!document.querySelector('.dcard.warn')"))
        time.sleep(.4)
        check(f"{scheme}: exactly one hedge_dismiss action was sent, and no order action", acts == ["hedge_dismiss"])
        pg.reload(); pg.evaluate("go('live')"); time.sleep(2)
        check(f"{scheme}: after a reload the card stays hidden", "lock in" not in pg.evaluate("document.querySelector('main').innerText"))
        # the Mac says it has changed a lot: the card is back (the flag is the Mac's call)
        state["dismissed"] = False
        pg.evaluate("load('live',true)"); until(pg, "!!document.querySelector('.dcard.warn')", 8)
        check(f"{scheme}: when the Mac clears the flag the card comes back", pg.evaluate("!!document.querySelector('.dcard.warn')"))
        # Moments rows can be cleared
        pg.evaluate("S.events=[{kind:'advice',text:'Hedge Chicago + Las Vegas: lock in $3.11',at:Date.now()/1000,combo:'" + T + "'},{kind:'alert',text:'Another note',at:Date.now()/1000}];renderLive()")
        n0 = pg.evaluate("document.querySelectorAll('.moment').length")
        mb = pg.evaluate("(()=>{const b=document.querySelector('.momx');const r=b&&b.getBoundingClientRect();return r?[r.width,r.height]:null})()")
        check(f"{scheme}: Moments rows have a thumb-sized clear button", n0 == 2 and bool(mb) and mb[0] >= 43.9 and mb[1] >= 43.9)
        if SHOTS:
            pg.screenshot(path=os.path.join(SHOTS, f"moments_{scheme}.png"), full_page=True)
        pg.click(".momx")
        time.sleep(.3)
        check(f"{scheme}: clearing a Moments row removes just that row", pg.evaluate("document.querySelectorAll('.moment').length") == n0 - 1)
        pg.reload(); pg.evaluate("go('live')"); time.sleep(1.5)
        pg.evaluate("S.events=[{kind:'advice',text:'Hedge Chicago + Las Vegas: lock in $3.11',at:Date.now()/1000},{kind:'alert',text:'Another note',at:Date.now()/1000}];renderLive()")
        txt = pg.evaluate("[...document.querySelectorAll('.moment')].map(e=>e.innerText).join('|')")
        check(f"{scheme}: a cleared Moments row stays cleared after a reload", "lock in $3.11" not in txt and "Another note" in txt)
        check(f"{scheme}: no page errors", not errs)
        ctx.close()
    br.close()
print("ALL OK" if not fails else "FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
