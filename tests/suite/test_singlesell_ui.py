# CHECK: group=page secs=30
"""Sell a single bet by Pete's tap (issue #238): Live's single cards show "Get new price" and "Sell"; the price refresh
updates the card's Worth now; Sell opens a sheet (what comes back after the fee, profit, holding's chance, warnings),
needs two taps, then shows the Sold moment; a thin market says Sell anyway; an unclear answer says Check Kalshi. The
web app's answers are scripted at the page's request layer (nothing is priced or sold). Phone (390x844, touch, dark)
and desktop. Saves screenshots (SHOTS dir, if set). Prints PROBLEMS on any failure."""
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
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("SHOTS") or ""
from playwright.sync_api import sync_playwright
def bad(m): print("PROBLEMS:", m)
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
T0 = "KXNCAAMBTOTAL-26NOV21DUKEUNC-157"
SING = [
 {"t": T0, "kind": "total", "sport": "ncaamb", "side": "yes", "label": "Over 157.5 points", "game": "Duke at North Carolina: Total Points",
  "event": "KXNCAAMBTOTAL-26NOV21DUKEUNC", "n": 16, "cost": 9.6, "pays": 16, "worth": 15.04, "chance": 0.97, "state": "live", "res": None,
  "score": "UNC 70-69 DUKE 2H 6:10", "starts": "", "how": "On track · 139 so far, on pace for 168, line 157.5", "url": "", "own": False, "self": False, "sell_at": None},
 {"t": "KXNHLTOTAL-26NOV21BOSNYR-7", "kind": "total", "sport": "nhl", "side": "yes", "label": "Over 7.5 goals", "game": "Boston at New York R: Total Goals",
  "event": "KXNHLTOTAL-26NOV21BOSNYR", "n": 8, "cost": 3.2, "pays": 8, "worth": 2.4, "chance": 0.31, "state": "pre", "res": None,
  "score": "", "starts": "Tonight 7:00 PM", "how": "", "url": "", "own": True, "self": False, "sell_at": None},
 {"t": "KXNBASPREAD-26NOV20BOSMIA-BOS12", "kind": "spread", "sport": "nba", "side": "yes", "label": "Boston wins by over 12.5 points", "game": "Boston at Miami: Spread",
  "event": "KXNBASPREAD-26NOV20BOSMIA", "n": 10, "cost": 4.0, "pays": 10, "worth": 0, "chance": 0, "state": "done", "res": "no",
  "score": "", "starts": "", "how": "", "url": "", "own": False, "self": False, "sell_at": None}]
def Q(**kw):
    q = {"ok": True, "q": "0123456789abcdef", "t": T0, "pick": "Over 157.5 points", "game": "Duke at North Carolina: Total Points",
         "sport": "ncaamb", "kind": "total", "live": True, "side": "yes", "bid": .95, "ask": .97, "gap": .02, "depth": 400, "px": .95,
         "have": 16, "n": 16, "fee": .07, "got": 15.13, "cost": 9.6, "profit": 5.53, "chance": .97, "pays": 16, "worth": 15.2,
         "thin": False, "clears": True, "blocked": None, "warn": [], "secs": 20, "self": False}
    q.update(kw)
    return q
NEXT = {"quote": Q(), "sell": {"ok": True, "sold": 16, "price": .95, "got": 15.13, "cost": 9.6, "pick": "Over 157.5 points",
                                "msg": "✅ Sold 16 at 95¢ or better: about $15.13 back after Kalshi's fee."}}
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for VW, VH, tag in ((390, 844, "phone"), (1280, 900, "desk")):
        ctx = br.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=2, color_scheme="dark",
                             has_touch=tag == "phone", is_mobile=tag == "phone")
        pg = ctx.new_page(); pg.add_init_script(__import__("upwait").COUNT_FETCHES)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        ACTS = []
        def act(r):
            d = json.loads(r.request.post_data or "{}"); ACTS.append(d)
            body = NEXT["quote"] if d.get("a") == "sellquote" else NEXT["sell"] if d.get("a") == "singlesell" else {"ok": True, "msg": "Got it."}
            if d.get("a") == "sellquote":
                body = dict(body, t=d.get("t") or T0)
            r.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        pg.route("**/app/api/act", act)
        pg.goto(B + "/app"); pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=30000)
        __import__("upwait").go_and_hold(pg, "live")
        put = "(s=>{if(!S.live||S.live.error)S.live={at:Date.now()/1000,combos:[],riding:0,staked:0,chance_one:0,best:0,cash_now:0,today:{}};S.live.singles=s;S.live.auto_sell=true;S.filter='all';S.sellq={};renderLive()})(" + json.dumps(SING) + ")"
        pg.evaluate(put); wait(pg, "document.querySelectorAll('.srow1').length===3", 8)
        rows = pg.locator(".srow1")
        n_sell = [rows.nth(i).locator("[data-sss]").count() for i in range(rows.count())]
        n_px = [rows.nth(i).locator("[data-ssp]").count() for i in range(rows.count())]
        print(tag, "rows:", rows.count(), "| sell buttons:", n_sell, "| price buttons:", n_px)
        if rows.count() != 3 or n_sell[:2] != [1, 1] or n_px[:2] != [1, 1]:
            bad(f"{tag}: every open single card needs Sell and Get new price ({n_sell}, {n_px})")
        if n_sell[2] or n_px[2]:
            bad(f"{tag}: a settled bet shows a Sell button")
        pg.locator(".stbl").scroll_into_view_if_needed(); shot(pg, f"single_sell_cards_{tag}.png")
        # Get new price: a fresh book read, the card's Worth now follows it
        pg.locator(f"[data-ssp='{T0}']").click()
        wait(pg, f"(document.querySelector(\"[data-key='s:{T0}'] .sacts\")||{{}}).innerText&&/15\\.13/.test(document.querySelector(\"[data-key='s:{T0}'] .sacts\").innerText)", 8)
        line = pg.evaluate(f"document.querySelector(\"[data-key='s:{T0}'] .sacts\").innerText")
        wv = pg.evaluate(f"(document.querySelector(\"[data-num='w:{T0}']\")||{{}}).dataset.v")
        print(tag, "after Get new price:", line.replace("\n", " | "), "| worth:", wv)
        if "95¢" not in line or "$15.13" not in line or wv != "15.2":
            bad(f"{tag}: Get new price didn't update the card ({line!r}, worth {wv})")
        if not any(a.get("a") == "sellquote" and a.get("t") == T0 for a in ACTS):
            bad(f"{tag}: Get new price didn't ask the Mac")
        # Sell: the sheet, two taps, the Sold moment
        ACTS.clear()
        pg.locator(f"[data-sss='{T0}']").click()
        wait(pg, "!!document.querySelector('#ssx #sssell')", 8)
        txt = pg.evaluate("(document.querySelector('#ssx')||{}).innerText||''")
        print(tag, "sheet:", txt[:160].replace("\n", " | "))
        for w in ("you'd get", "$15.13", "if you hold", "97% chance"):
            if w not in txt.lower():
                bad(f"{tag}: the sell sheet doesn't say {w!r}")
        time.sleep(.8); shot(pg, f"single_sell_sheet_{tag}.png")
        pg.locator("#sssell").click()
        armed = pg.evaluate("document.querySelector('#sssell').innerText")
        if "Tap again" not in armed or any(a.get("a") == "singlesell" for a in ACTS):
            bad(f"{tag}: the first tap must only arm the button ({armed!r})")
        shot(pg, f"single_sell_armed_{tag}.png")
        pg.locator("#sssell").click()
        wait(pg, "/Got back/i.test((document.querySelector('#sheet .okcard.sold')||{}).innerText||'')", 8); time.sleep(1)
        sent = [a for a in ACTS if a.get("a") == "singlesell"]
        sold = pg.evaluate("(document.querySelector('#sheet .okcard.sold')||{}).innerText||''")
        print(tag, "sold sheet:", sold[:100].replace("\n", " | "), "| sent:", sent)
        if len(sent) != 1 or sent[0].get("q") != "0123456789abcdef" or sent[0].get("anyway") is not False:
            bad(f"{tag}: the second tap must send the quote once ({sent})")
        if "$15" not in sold or "+$5.53 profit" not in sold or "$9.60" not in sold:
            bad(f"{tag}: no Sold moment after a sale ({sold!r})")
        shot(pg, f"single_sell_sold_{tag}.png")
        pg.evaluate("closeModal()"); time.sleep(.4)
        # a thin market: yellow Sell anyway, the warning shown
        pg.evaluate(put); wait(pg, "document.querySelectorAll('.srow1').length===3", 8)
        NEXT["quote"] = Q(thin=True, clears=False, gap=.1, warn=[{"k": "thin", "t": "Thin market: 10¢ between the buy and sell prices, so this price may be well under what the bet is worth."}])
        ACTS.clear()
        pg.locator(f"[data-sss='{T0}']").click(); wait(pg, "!!document.querySelector('#ssx #sssell')", 8)
        cls = pg.evaluate("document.querySelector('#sssell').className"); bt = pg.evaluate("document.querySelector('#sssell').innerText")
        if "warn" not in cls or "Sell anyway" not in bt or pg.locator("#ssx [data-w='thin']").count() != 1:
            bad(f"{tag}: a thin market must warn and say Sell anyway ({cls}, {bt!r})")
        time.sleep(.8); shot(pg, f"single_sell_thin_{tag}.png")
        NEXT["sell"] = {"ok": False, "check": True, "msg": "Kalshi didn't answer clearly, so this may or may not have sold. Check Kalshi (or Live in a minute) before trying again; the app won't send it again."}
        pg.locator("#sssell").click(); pg.locator("#sssell").click()
        wait(pg, "/Check Kalshi/.test((document.querySelector('#sheet')||{}).innerText||'')", 8)
        sent = [a for a in ACTS if a.get("a") == "singlesell"]
        if len(sent) != 1 or sent[0].get("anyway") is not True:
            bad(f"{tag}: Sell anyway must send anyway: true, once ({sent})")
        if "Check Kalshi" not in pg.evaluate("(document.querySelector('#sheet')||{}).innerText||''"):
            bad(f"{tag}: an unclear sale must say Check Kalshi")
        pg.evaluate("closeModal()"); time.sleep(.4)
        NEXT["quote"], NEXT["sell"] = Q(), {"ok": False, "msg": "The price dropped to 93¢ (you saw 95¢). Nothing was sold. Get a fresh price.", "moved": True}
        pg.evaluate(put); wait(pg, "document.querySelectorAll('.srow1').length===3", 8)
        pg.locator(f"[data-sss='{T0}']").click(); wait(pg, "!!document.querySelector('#ssx #sssell')", 8)
        pg.locator("#sssell").click(); pg.locator("#sssell").click()
        wait(pg, "!!document.querySelector('#ssx [data-w=failed]')", 8)
        if "dropped" not in pg.evaluate("(document.querySelector('#ssx')||{}).innerText||''") or "fresh price" not in pg.evaluate("document.querySelector('#sssell').innerText"):
            bad(f"{tag}: a refused sale must show why and offer a fresh price")
        pg.evaluate("closeModal()"); time.sleep(.4)
        NEXT["sell"] = {"ok": True, "sold": 16, "price": .95, "got": 15.13, "cost": 9.6, "pick": "Over 157.5 points", "msg": "✅ Sold"}
        ow = pg.evaluate("document.documentElement.scrollWidth>innerWidth+1")
        if ow:
            bad(f"{tag}: the page scrolls sideways")
        print(tag, "JS errors:", errs)
        ctx.close()
    br.close()
