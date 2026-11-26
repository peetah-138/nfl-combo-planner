# CHECK: group=page secs=45
"""fun-1 (#413, #140): Live's big number is Kalshi's value (combos' cost plus singles' worth) with our estimate small beside it and no
hero chart; result moments wait for a tap on a big Nice button (no auto-close); a changed score glows its Live row and survives a repaint,
and is off for reduced motion; a failed button shows its reason inline (role=status) and outlasts the 2 s button revert. Scripted
answers only: nothing is priced or bought. SHOTS dir (if set) gets phone screenshots. Prints PROBLEMS on any failure."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("SHOTS") or ""
def bad(m): print("PROBLEMS:", m)
from playwright.sync_api import sync_playwright
def leg(i, name, res=None):
    return {"ticker": f"KXNFLGAME-26NOV29T{i:02d}-T{i:02d}", "name": name, "opp": "Rival", "chance": .67, "live": .7, "res": res, "state": "live",
            "phase": "", "note": "", "short": "", "score": "", "sc": None, "src": "", "starts": "Sun 9:30 AM", "sport": "nfl", "side": "yes", "url": ""}
def combo(i, names, cost, pays, offer):
    return {"t": f"KXMVECOMBO{i}", "i": i, "label": " + ".join(names), "group": "pending", "kind": "waiting", "sports": ["nfl"], "p": .2, "pays": pays,
            "cost": cost, "back": 0, "live": True, "hold_value": cost, "won_some": False, "offer": offer, "offer_real": i % 2 == 0, "offer_live": offer,
            "fair_value": cost, "overpay": None, "offer_age": None, "verdict": "hold", "why": "", "threshold": None, "moment": None, "hedge": None,
            "nudge": None, "self": False, "own": False, "legs": [leg(i * 10 + k, n) for k, n in enumerate(names)]}
cs = [combo(1, ["Chiefs", "Bills"], 5.0, 40.0, 4.2), combo(2, ["Eagles", "Lions", "Rams"], 4.0, 60.0, 3.6)]
now = time.time(); t0 = int(now - 16 * 3600)
P = {"at": now, "balance": 211.0, "combos": cs, "today": {}, "singles": [{"t": "KXS1", "kind": "win", "sport": "nfl", "side": "yes", "label": "Chiefs to win", "game": "Chiefs at Bills", "event": "KXE", "n": 10, "cost": 5.0, "pays": 10, "worth": 6.1, "chance": .6, "state": "live", "res": None, "score": "", "starts": "", "how": "", "url": "", "own": False, "self": False, "sell_at": None}],
     "auto_sell": True, "riding": 2, "staked": 9.0, "chance_one": .4, "best": 60.0, "cash_now": 7.8, "hold_value": 9.0, "locked": 0, "week_pl": 0.0, "games": [], "risk": None, "todo": [],
     "pnl": {"pts": [[t0 + i * 6000, v, 14] for i, v in enumerate([0, -.8, -1.9, -1.2, .6, 1.4, 2.0, 1.1])], "t0": t0, "rough": None, "end": int(now)},
     "fresh": {"now": now, "built": now - 2, "scores": 3, "fast": True}}

def until(pg, js, secs=8):
    for _ in range(int(secs / .2)):
        try:
            if pg.evaluate(js): return True
        except Exception:
            pass
        time.sleep(.2)
    return False
def shot(pg, name):
    if SHOTS: pg.screenshot(path=os.path.join(SHOTS, name))
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=scheme, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/app/api/live*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(P)))
        pg.goto(B + "/app"); pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=30000)
        pg.evaluate("go('live')"); pg.wait_for_selector(".trow", timeout=20000); time.sleep(1.5)
        tag = scheme
        # ---- #413: Kalshi's value is the big number; our estimate is small; no chart
        h = pg.evaluate("({big:document.querySelector('.hv .big').dataset.v,lbl:document.querySelector('.hv .hl').textContent,est:!!document.querySelector('.hv .hest [data-num=\"h:worth\"]'),chart:!!document.querySelector('.hv .sparkw,.hv .spark,.rng2'),delta:document.querySelector('.hv .delta').textContent})")
        print(tag, "hero:", h)
        if abs(float(h["big"]) - 15.10) > .01: bad(f"{tag}: the big number should be Kalshi's value (5.00 + 4.00 + 6.10 = 15.10), got {h['big']}")
        if "Kalshi" not in h["lbl"]: bad(f"{tag}: the hero label should say Kalshi")
        if not h["est"]: bad(f"{tag}: our estimate should sit small beside the big number")
        if h["chart"]: bad(f"{tag}: the hero chart should be gone")
        shot(pg, f"live_hero_after_{scheme}.png")
        # ---- #140 (b): a changed score glows the row, and the glow survives a repaint
        pg.evaluate("S.live.combos[0].legs[0].score='7-3';S.live.combos[0].legs[0].sc=null;renderLive();afterPaint()")
        g1 = until(pg, "!!document.querySelector('.trow.burst')", 3)
        pg.evaluate("renderLive()"); time.sleep(.2)
        g2 = pg.evaluate("!!document.querySelector('.trow.burst')")
        if not (g1 and g2): bad(f"{tag}: a changed score should glow its Live row (and keep glowing through a repaint): {g1} {g2}")
        shot(pg, f"live_score_burst_{scheme}.png")
        # ---- #140 (a): the Bought moment stays until tapped, ends on a big Nice button
        pg.evaluate("okSheet('Bought','$40.00 if it hits','Chiefs + Bills. It shows on Live within a minute.')")
        until(pg, "!!document.querySelector('#sheet .okcard .nice')", 5); time.sleep(.8); shot(pg, f"result_bought_{scheme}.png"); time.sleep(5.6)
        n = pg.evaluate("(()=>{const b=document.querySelector('#sheet .okcard .nice');if(!b)return null;const r=b.getBoundingClientRect();return {h:r.height,w:r.width,txt:b.textContent,tag:b.tagName}})()")
        print(tag, "nice:", n)
        if not n: bad(f"{tag}: the Bought moment closed by itself or has no Nice button")
        else:
            if n["tag"] != "BUTTON" or n["txt"] != "Nice": bad(f"{tag}: the button should be a real Nice button: {n}")
            if n["h"] < 44 or n["h"] > 64: bad(f"{tag}: the Nice button should be 44-64px tall (so the tap tick lands): {n['h']}")
            pg.locator("#sheet .okcard .nice").click(); time.sleep(.8)
            if pg.evaluate("document.querySelector('#modal').classList.contains('on')"): bad(f"{tag}: tapping Nice should close the moment")
        # a Check Kalshi result is not a celebration: no Nice
        pg.evaluate("okSheet('Check Kalshi',null,'Look at Kalshi before trying again.',true)"); time.sleep(.6)
        if pg.evaluate("document.querySelector('#sheet .okcard .nice')&&document.querySelector('#sheet .okcard .nice').textContent")!="OK": bad(f"{tag}: Check Kalshi should end on OK, not Nice")
        pg.evaluate("closeModal()")
        # the big win stays until tapped
        pg.evaluate("bigWin({label:'Chiefs + Bills',pays:80,cost:5,t:'KXMVECOMBO1'})"); time.sleep(1.2); shot(pg, f"result_bigwin_{scheme}.png")
        if not pg.evaluate("!!document.querySelector('.bigwin .nice')"): bad(f"{tag}: the big win should end on a Nice button")
        pg.evaluate("document.querySelector('.bigwin .nice').click()"); time.sleep(.7)
        if pg.evaluate("!!document.querySelector('.bigwin')"): bad(f"{tag}: Nice should close the big win")
        # ---- #140 (c): a failed button says why under itself and outlasts the 2.2 s revert; survives a repaint
        pg.evaluate("go('live')"); time.sleep(.8)
        pg.evaluate("btnFail('.trow','The price moved. Nothing was bought.',document.querySelector('.trow button'))"); time.sleep(2.6)
        e = pg.evaluate("(()=>{const e=document.querySelector('.berr');return e?{role:e.getAttribute('role'),txt:e.textContent,h:e.getBoundingClientRect().height}:null})()")
        pg.evaluate("renderLive()"); time.sleep(.3)
        e2 = pg.evaluate("!!document.querySelector('.berr')")
        print(tag, "error:", e, e2)
        if not e or e["role"] != "status" or "price moved" not in e["txt"]: bad(f"{tag}: the inline reason should show with role=status: {e}")
        if not e2: bad(f"{tag}: the inline reason should survive a repaint")
        if e and e["h"] < 44: bad(f"{tag}: the reason should be at least 44px tall")
        pg.evaluate("document.querySelector('.berr')&&document.querySelector('.berr').scrollIntoView({block:'center'})"); time.sleep(.3)
        shot(pg, f"error_inline_{scheme}.png")
        if pg.evaluate("document.querySelector('#toast')&&document.querySelector('#toast').classList.contains('on')"): bad(f"{tag}: a button error should not also raise the 6 s toast")
        if errs: bad(f"{tag}: page errors {errs}")
        ctx.close()
    # reduced motion: no score burst animation
    ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", reduced_motion="reduce", has_touch=True)
    pg = ctx.new_page(); pg.route("**/app/api/live*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(P)))
    pg.goto(B + "/app"); pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=30000)
    pg.evaluate("go('live')"); pg.wait_for_selector(".trow", timeout=20000); time.sleep(1)
    pg.evaluate("S.live.combos[0].legs[0].score='7-3';renderLive();afterPaint()"); time.sleep(.4)
    if pg.evaluate("!!document.querySelector('.trow.burst')"): bad("reduced motion: a changed score should not glow")
    br.close()
print("done")
