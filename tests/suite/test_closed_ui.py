# CHECK: group=page secs=40
"""Pete, 2026-11-23: "we should have the ability to tap into the ones that have already closed and see the details of
that." A closed (sold, settled or expired) combo or single has a read-only detail page (/app/api/closed): what it was,
what was paid and got back, profit or loss, when and why it closed, its picks and the auto-sell's attempts. Tapping a
Results row opens it, a notification link to a closed bet opens it (never a silent Live), and an id found nowhere shows
'We can't find that bet'. Phone size (390x844), dark and light; set CW_SHOTS to save screenshots."""
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

TC, TS = "KXMVENFLMULTIGAMEEXTENDED-S2026CLOSED1", "KXNCAAMBTOTAL-26NOV21DUKEUNC-157"
CLOSED = {
    TC: {"found": True, "t": TC, "kind": "combo", "label": "Combo 5", "status": "cashed", "cost": 2.19, "back": 3.61, "pl": 1.42, "pl_pct": 64.84, "stamp": "SOLD EARLY", "sports": ["nba"], "chance": 0.72, "pays": 40.0,
         "closed": "Sun Nov 22, 3:12 PM", "why": "Cashed out automatically: took the profit",
         "picks": [{"name": "Lakers", "res": "yes", "t": "a"}, {"name": "not Celtics", "res": None, "t": "b"}],
         "attempts": [{"when": "2026-11-22 15:11", "result": "held", "why": "smart", "note": "Buyer backed out", "offer": 3.5,
                       "tries": [{"offer": 3.5, "quote": "cancelled", "error": "buyer backed out"}]},
                      {"when": "2026-11-22 15:12", "result": "sold", "why": "smart", "note": "✅ Combo 5 cashed out for about $3.61: +$1.42 profit (paid $2.19).", "offer": 3.61, "tries": []}],
         "chart": {"offers": [{"ts": 1 + i * 600, "p": .3, "hold": 2.0 + i * .1, "offer": 2.0 + i * .12, "real_offer": None, "verdict": "hold"} for i in range(8)], "ticks": {}}},
    TS: {"found": True, "t": TS, "kind": "single", "label": "Over 157.5 points", "game": "Duke at North Carolina: Total Points", "status": "lost",
         "cost": 9.6, "back": 0.0, "pl": -9.6, "pl_pct": -100.0, "stamp": "LOST", "sports": ["ncaamb"], "pays": 16, "closed": "", "why": "Settled: a pick lost", "picks": [{"name": "Over 157.5 points", "res": "no", "t": TS}],
         "attempts": [], "chart": {"offers": [], "ticks": {}}}}
LIVE = {"at": time.time(), "balance": 211.0, "combos": [], "today": {}, "singles": [], "auto_sell": True, "riding": 0, "staked": 0,
        "chance_one": 0, "best": 0, "cash_now": 0, "hold_value": 0, "locked": 0, "week_pl": 0.0, "games": [], "risk": None, "todo": [],
        "fresh": {"now": time.time(), "built": time.time() - 2, "scores": 3, "fast": True}}
RES = {"balance": 211.0, "settled": 1, "won": 0, "cashed": 1, "staked": 2.19, "returned": 3.61, "pl": 1.42, "roi": .6, "best": 1.42, "weeks": [],
       "history": [{"t": TC, "status": "cashed", "cost": 2.19, "back": 3.61, "pl": 1.42, "pays": 40.0, "week": "2026-W47", "day": "2026-11-22",
                    "bought": "2026-11-21", "cashed": "2026-11-22", "picks": ["Lakers", "not Celtics"], "sports": ["nba"]}]}
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


def closed_route(r):
    t = r.request.url.split("t=")[-1].split("&")[0]
    from urllib.parse import unquote
    d = CLOSED.get(unquote(t))
    if d:
        r.fulfill(status=200, content_type="application/json", body=json.dumps(d))
    else:
        r.continue_()          # the real server: an id found nowhere answers found:false


def page(br, scheme="dark"):
    p = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=scheme)
    errs = []
    p.on("pageerror", lambda e: errs.append(str(e)))
    p.route("**/app/api/live*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(LIVE)))
    p.route("**/app/api/results*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(RES)))
    p.route("**/app/api/closed*", closed_route)
    return p, errs


SHEET = "document.querySelector('#sheet').innerText"
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        # a notification link to a closed combo
        p, errs = page(br, scheme)
        p.goto(B + "/app#c=" + TC)
        check(f"{scheme}: a link to a closed combo opens its detail", until(p, f"document.querySelector('#modal.on')&&{SHEET}.includes('Combo 5')&&{SHEET}.includes('+$1.42')", 15))
        txt = p.evaluate(SHEET)
        check(f"{scheme}: shows paid, sold-for, why and when", all(x in txt for x in ("$2.19", "$3.61", "took the profit", "Sun Nov 22", "+64.84%", "SOLD EARLY", "72% chance", "COST", "PROFIT")))
        check(f"{scheme}: lists the picks", "Lakers" in txt and "not Celtics" in txt)
        check(f"{scheme}: lists the auto-sell attempts incl. the back-out", "buyer backed out" in txt and "cashed out for about $3.61" in txt)
        check(f"{scheme}: no sideways scroll", not p.evaluate("document.documentElement.scrollWidth>innerWidth+1"))
        if SHOTS:
            p.wait_for_timeout(700); p.screenshot(path=os.path.join(SHOTS, f"closed_combo_{scheme}.png"))
        check(f"{scheme}: no JS errors (combo)", not errs)
        p.close()
        # a closed single
        p, errs = page(br, scheme)
        p.goto(B + "/app#b=" + TS)
        check(f"{scheme}: a link to a closed single opens its detail with the loss in dollars",
              until(p, f"document.querySelector('#modal.on')&&{SHEET}.includes('Over 157.5 points')&&{SHEET}.includes('-$9.60')", 15))
        check(f"{scheme}: says why it closed", "Settled: a pick lost" in p.evaluate(SHEET))
        if SHOTS:
            p.wait_for_timeout(700); p.screenshot(path=os.path.join(SHOTS, f"closed_single_{scheme}.png"))
        check(f"{scheme}: no JS errors (single)", not errs)
        p.close()
    # Results row opens it
    p, errs = page(br)
    p.goto(B + "/app"); p.evaluate("go('results')")
    until(p, "!!document.querySelector('.hrow2')", 20)
    p.click(".hrow2")
    check("tapping a Results row opens the closed detail", until(p, f"{SHEET}.includes('Combo 5')&&{SHEET}.includes('$3.61')", 10))
    check("Results tap: no JS errors", not errs)
    p.close()
    # a hostile ticker (quotes, angle brackets, a script break-out) in a Results row stays inert and still opens that item
    EVIL = "x');window.__pwn=1;//\"><img src=x onerror=window.__pwn=2>"
    p, errs = page(br)
    p.unroute("**/app/api/results*")
    evil_res = dict(RES, history=[dict(RES["history"][0], t=EVIL)])
    p.route("**/app/api/results*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(evil_res)))
    asked = []
    p.on("request", lambda rq: asked.append(rq.url) if "/app/api/closed" in rq.url else None)
    p.goto(B + "/app"); p.evaluate("go('results')")
    until(p, "!!document.querySelector('.hrow2')", 20)
    check("hostile id: row carries it as plain data", p.evaluate("document.querySelector('.hrow2').dataset.t") == EVIL)
    p.click(".hrow2")
    until(p, "!!document.querySelector('#modal.on')", 10); p.wait_for_timeout(500)
    from urllib.parse import unquote
    check("hostile id: opens that very item (asked the server for it)", any(unquote(u.split("t=")[-1]) == EVIL for u in asked))
    check("hostile id: nothing ran and no stray element was made", p.evaluate("window.__pwn") is None and p.evaluate("document.querySelectorAll('img[src=x]').length") == 0)
    p.close()
    # a hostile id in the link is refused before it is used
    p, errs = page(br)
    p.goto(B + "/app#c=" + "x%27);window.__pwn=1;//")
    p.wait_for_timeout(1200)
    check("hostile link: ignored, nothing ran, stays on Live", p.evaluate("window.__pwn") is None and p.evaluate("!document.querySelector('#modal.on')"))
    p.close()
    # unknown id: the real server says found:false
    p, errs = page(br)
    p.goto(B + "/app#c=KXMVE-NOWHERE-9")
    check("an id found nowhere shows 'We can't find that bet' (not Live)", until(p, f"document.querySelector('#modal.on')&&{SHEET}.includes(\"We can't find that bet\")", 15))
    if SHOTS:
        p.wait_for_timeout(500); p.screenshot(path=os.path.join(SHOTS, "closed_notfound_dark.png"))
    check("not-found: no JS errors", not errs)
    p.close()
    # the endpoint itself refuses odd ids and leaks nothing account-level
    p, errs = page(br)
    p.goto(B + "/app")
    r = p.evaluate("fetch('/app/api/closed?t='+encodeURIComponent('<x>')).then(r=>r.json())")
    check("a malformed id answers found:false", r.get("found") is False)
    r = p.evaluate("fetch('/app/api/closed?t=KXMVE-NOWHERE-9').then(r=>r.json())")
    check("an unknown id answers found:false with no account fields", r.get("found") is False and not ({"balance", "cash", "account", "member_id"} & set(r)))
    br.close()

if fails:
    print("PROBLEMS:", "; ".join(fails))
else:
    print("PASS closed bets have a detail page")
