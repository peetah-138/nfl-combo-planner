# CHECK: group=page secs=30
# Issue #358 on the phone: an approved panel's Skipped / Didn't buy cards say why in plain words and are one big tap target
# (44px+) for a fresh price; the tap asks only panel_reprice for that card's id and shows the verdict and "nothing was
# bought" inline; other cards are not tappable. The combo quote line names the real bar (qWhy) and the amount control
# never says "recommended" without a positive expected profit. The Mac's answer is faked in the page: nothing is priced.
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("SHOTS")
P = json.load(open("panel_fixture.json"))
P["panel"]["status"] = "approved"
st = ["skipped", "failed", "bought"]
notes = ["no longer priced well enough, and nothing similar qualified", "Kalshi wouldn't price it (timeout)", ""]
for i, c in enumerate(P["panel"]["items"][:3]):
    c["state"], c["note"] = st[i], notes[i]
    c["kick"] = time.time() + 9 * 3600
from playwright.sync_api import sync_playwright
probs = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/app"); time.sleep(4)
    pg.evaluate("go('build')"); time.sleep(5)
    calls = []
    def fake(route):
        b = json.loads(route.request.post_data or "{}")
        if b.get("a") != "panel_reprice":
            return route.continue_()
        calls.append(b)
        route.fulfill(content_type="application/json", body=json.dumps({"ok": True, "id": b.get("id"), "would": False,
                      "verdict": "Still wouldn't buy", "at": time.time(), "pct": .91,
                      "why": "Kalshi pays $9.80 for $5.00: 91% of its fair payout. The panel's bar is 95%."}))
    pg.route("**/app/api/act", fake)
    pg.evaluate("S.panel=" + json.dumps(P) + ";renderBuild()"); time.sleep(.5)
    tap = pg.evaluate("[...document.querySelectorAll('.pitem.prp')].map(e=>({id:e.dataset.pid,h:e.getBoundingClientRect().height,t:e.innerText}))")
    print("tappable:", [(t["id"], round(t["h"])) for t in tap])
    if len(tap) != 2: probs.append(f"exactly the skipped and failed cards are tappable (got {len(tap)})")
    if any(t["h"] < 44 for t in tap): probs.append("a tappable card is under 44px tall")
    if tap and "Why not:" not in tap[0]["t"]: probs.append("the skipped card doesn't say why")
    if tap and "price got worse" not in tap[0]["t"]: probs.append("the skipped note isn't in plain words: " + tap[0]["t"][:200])
    if len(tap) > 1 and "didn't answer with a price" not in tap[1]["t"]: probs.append("the failed note isn't in plain words")
    if tap and "Tap for a fresh price" not in tap[0]["t"]: probs.append("no tap hint")
    if SHOTS:
        pg.evaluate("document.querySelector('.pitem.prp').scrollIntoView({block:'center'})"); time.sleep(.3)
        pg.screenshot(path=os.path.join(SHOTS, "reprice_before.png"))
    wait = pg.evaluate("(()=>{const id=document.querySelector('.pitem.prp').dataset.pid;S.prepP={[id]:1};const h=pRepHtml({id});S.prepP={};return h})()")
    if "Getting a fresh price" not in wait: probs.append("no spinner while the price is on its way")
    pg.locator(".pitem.prp").first.click()
    time.sleep(.8)
    got = pg.evaluate("document.querySelector('.pitem.prp .prq')?.innerText||''")
    print("after:", got.replace("\n", " | "), calls)
    if "Still wouldn't buy" not in got or "nothing was bought" not in got: probs.append("the verdict / 'nothing was bought' isn't shown")
    if calls != [{"a": "panel_reprice", "id": tap[0]["id"] if tap else None}]: probs.append(f"the tap must ask only panel_reprice for that card ({calls})")
    if SHOTS:
        pg.evaluate("document.querySelector('.pitem.prp').scrollIntoView({block:'center'})"); time.sleep(.3)
        pg.screenshot(path=os.path.join(SHOTS, "reprice_after.png"))
    # the quote line and the amount control (#358)
    w = pg.evaluate("""[qWhy({pct:1.31,why:'suspect',cut:95}),qWhy({pct:null,nofair:"Alpha's game is under way"}),qWhy({pct:1.04,cut:100,live:true}),
        qWhy({pct:.9,cut:95,why:'under'}),stakeCtl({key:'cc:9',rec:2,cur:5,ev:-0.4,small:true}),stakeCtl({key:'cc:8',rec:5,cur:5,ev:0.6})]""")
    print("qWhy:", w[:4])
    if "too far over" not in w[0]: probs.append("suspect quote not explained")
    if "No fair price" not in w[1] or "under way" not in w[1]: probs.append("no-fair quote not explained")
    if "on the live chance" not in w[2] or "100% bar" not in w[2]: probs.append("live quote doesn't name the live chance and the real bar")
    if "95% bar" not in w[3]: probs.append("under-bar quote doesn't name the real bar")
    if "recommended" in w[4].lower() or "no edge" not in w[4]: probs.append("no positive expected profit but still 'recommended'")
    if ">recommended<" not in w[5]: probs.append("a green quote with positive expected profit lost 'recommended'")
    if errs: probs.append("page errors: " + "; ".join(errs[:3]))
    br.close()
for p in probs:
    print("PROBLEMS:", p)
print("FAIL reprice ui" if probs else "PASS reprice ui")
