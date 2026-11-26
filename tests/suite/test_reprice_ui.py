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
P["panel"]["items"][0].update(kind="combo", pct=1.06, ret=0.06, chance=0.42)      # a combo card: earlier guess 106%
if len(P["panel"]["items"]) > 3:
    P["panel"]["items"][3]["state"], P["panel"]["items"][3]["note"] = "cancelled", "you cancelled it"
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
                      "verdict": "Still wouldn't buy", "at": time.time(), "pct": .99,
                      "why": "Kalshi pays $9.80 for $5.00. Kalshi's price is about 1% under what we think it's worth, so on average you'd lose about 1¢ per $2 if you held it to the end. Selling early could still make a profit, but not often enough to make up for that, so it is left out."}))
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
    if tap and ("+6% expected before fees" not in tap[0]["t"] or "earlier guess" in tap[0]["t"]): probs.append("a combo card says '+X% expected before fees' and, before a fresh price, no 'earlier guess': " + tap[0]["t"][:200])
    if SHOTS:
        pg.evaluate("document.querySelector('.pitem.prp').scrollIntoView({block:'center'})"); time.sleep(.3)
        pg.screenshot(path=os.path.join(SHOTS, "reprice_before_dark.png"))
        pg.emulate_media(color_scheme="light"); time.sleep(.4)
        pg.evaluate("document.querySelector('.pitem.prp').scrollIntoView({block:'center'})"); time.sleep(.3)
        pg.screenshot(path=os.path.join(SHOTS, "reprice_before_light.png"))
        pg.emulate_media(color_scheme="dark"); time.sleep(.3)
    # (#393) the closed-bet detail has its own labelled control on those cards; it must not trigger a reprice
    det = pg.evaluate("[...document.querySelectorAll('.pitem.prp .pdet')].map(e=>({pid:e.dataset.pid,h:e.getBoundingClientRect().height,w:e.getBoundingClientRect().width,t:e.innerText.trim(),own:e.closest('.pitem').dataset.pid}))")
    if len(det) != 2 or any(d["pid"] != d["own"] for d in det): probs.append(f"each tappable card has one Details control carrying its own id ({det})")
    if any(d["h"] < 44 or d["w"] < 44 for d in det): probs.append("a Details control is under the 44px tap size")
    if any(not d["t"].startswith("Details") for d in det): probs.append("the Details control isn't labelled")
    if SHOTS:
        pg.evaluate("document.querySelector('.pitem.prp').scrollIntoView({block:'center'})"); time.sleep(.3)
        pg.screenshot(path=os.path.join(SHOTS, "closed_detail_card_dark.png"))
        pg.emulate_media(color_scheme="light"); time.sleep(.4)
        pg.evaluate("document.querySelector('.pitem.prp').scrollIntoView({block:'center'})"); time.sleep(.3)
        pg.screenshot(path=os.path.join(SHOTS, "closed_detail_card_light.png"))
        pg.emulate_media(color_scheme="dark"); time.sleep(.3)
    pg.locator(".pitem.prp .pdet").first.click(); time.sleep(.8)
    if not pg.evaluate("!!document.querySelector('#modal.on')&&document.querySelector('#modal').innerText.includes('Done')"): probs.append("tapping Details didn't open the closed-bet detail")
    if calls: probs.append(f"tapping Details must not ask the Mac for a price ({calls})")
    if pg.evaluate("Object.keys(S.prepP||{}).length||Object.keys(S.prep||{}).length"): probs.append("tapping Details started or stored a reprice")
    if SHOTS: pg.screenshot(path=os.path.join(SHOTS, "closed_detail_sheet_dark.png"))
    pg.evaluate("closeModal()"); time.sleep(.4)
    # keyboard: Enter on the focused Details control opens the detail, never the reprice
    pg.evaluate("document.querySelector('.pitem.prp .pdet').focus()"); pg.keyboard.press("Enter"); time.sleep(.6)
    if calls: probs.append("Enter on Details triggered a reprice")
    pg.evaluate("closeModal()"); time.sleep(.4)
    # a cancelled card (and a skipped one in an unapproved panel) opens the detail by tapping the whole card; no reprice, no Details link
    cl = pg.evaluate("""(()=>{const its=S.panel.panel.items;const h=(c,ap)=>{const d=document.createElement('div');d.innerHTML=panelItem(c,'x',ap,'approve');return d.firstElementChild};
      const a=h(Object.assign({},its[0],{state:'cancelled'}),true),b=h(Object.assign({},its[0],{state:'skipped'}),false);
      return [a,b].map(e=>({prp:e.classList.contains('prp'),det:!!e.querySelector('.pdet'),oc:e.getAttribute('onclick')||'',cur:e.style.cursor}))})()""")
    if any(x["prp"] or x["det"] or "panelClosed(this.dataset.pid)" not in x["oc"] or "pReprice" in x["oc"] or x["cur"] != "pointer" for x in cl): probs.append(f"other closed cards open the detail from the whole card ({cl})")
    ids = pg.evaluate("[...document.querySelectorAll('.pitem')].map(e=>e.getAttribute('onclick')||'').join('|')")
    if "panelClosed('" in ids: probs.append("an id is interpolated inside an inline handler")
    wait = pg.evaluate("(()=>{const id=document.querySelector('.pitem.prp').dataset.pid;S.prepP={[id]:1};const h=pRepHtml({id});S.prepP={};return h})()")
    if "Getting a fresh price" not in wait: probs.append("no spinner while the price is on its way")
    pg.locator(".pitem.prp").first.click()
    time.sleep(.8)
    got = pg.evaluate("document.querySelector('.pitem.prp .prq')?.innerText||''")
    print("after:", got.replace("\n", " | "), calls)
    if "Still wouldn't buy" not in got or "nothing was bought" not in got: probs.append("the verdict / 'nothing was bought' isn't shown")
    if calls != [{"a": "panel_reprice", "id": tap[0]["id"] if tap else None}]: probs.append(f"the tap must ask only panel_reprice for that card ({calls})")
    stale = pg.evaluate("(()=>{const n=document.querySelector('.pitem.prp .pn');return {c:n.className,t:n.innerText}})()")
    if "stl" not in stale["c"] or "earlier guess: pays" not in stale["t"] or "before fees" not in stale["t"]: probs.append(f"after a fresh price the card's own numbers must be dimmed and labelled earlier ({stale})")
    if "1% under" not in got or "of what it's worth" in got: probs.append("the fresh verdict wording is wrong: " + got[:300])
    if SHOTS:
        pg.evaluate("document.querySelector('.pitem.prp').scrollIntoView({block:'center'})"); time.sleep(.3)
        pg.screenshot(path=os.path.join(SHOTS, "reprice_after_dark.png"))
        pg.emulate_media(color_scheme="light"); time.sleep(.4)
        pg.evaluate("document.querySelector('.pitem.prp').scrollIntoView({block:'center'})"); time.sleep(.3)
        pg.screenshot(path=os.path.join(SHOTS, "reprice_after_light.png"))
        pg.emulate_media(color_scheme="dark"); time.sleep(.3)
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
