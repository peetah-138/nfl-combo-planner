# Kalshi refusals shown honestly (issue #134), in the web app: when Kalshi refuses for the account or region, a calm banner
# says so under the header ("Kalshi isn't allowing orders for your account right now") and a tap opens Kalshi's own message
# in FULL, selectable and copyable, with plain words that it is Kalshi's rule and not the app's. A refused tap answers with
# Kalshi's words in a sheet (never a clipped toast, never "your API key needs write access"). The panel card says the bet is
# waiting. The banner goes away when the Mac clears the note. Phone (dark and light) and desktop; no JS errors, no sideways
# scroll. The Mac's state is the real file the engine reads (fake Kalshi, nothing is sent anywhere).
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
NEV = ("Nevada residents are not currently allowed to open positions in Sports markets on Kalshi. This applies to your "
       "account because of the state you registered in. You can still close positions you already hold, and you can "
       "trade in other categories where they are available to you. See the Kalshi help center for details.")
FILE = os.path.join(os.path.abspath("wahome"), "combo_kalshi_block.json")
problems = []


def state(scope="buy", on=True, holding=True):
    now = time.time()
    e = {"active": on, "msg": NEV, "code": "forbidden_for_region", "status": 403, "what": "order", "at": now - 60,
         "first": now - 600, "count": 3, "streak": 2, "hold_until": now + (1800 if holding else -5), "codes": {"forbidden_for_region": 3}}
    json.dump({scope: e, "last": {"scope": scope, "msg": NEV, "code": "forbidden_for_region", "at": now - 60}}, open(FILE, "w"))


def clear():
    if os.path.exists(FILE):
        os.remove(FILE)


def wait(pg, js, n=60):
    for _ in range(n):
        if pg.evaluate(js):
            return True
        time.sleep(.25)
    return False


with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme, size in (("dark", (390, 844)), ("light", (390, 844)), ("dark", (1280, 800))):
        tag = f"{scheme} {size[0]}"
        pg = br.new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=2, color_scheme=scheme)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        clear()
        pg.goto(B + "/app"); time.sleep(1.5)
        if pg.evaluate("!document.getElementById('rsban').hidden"):
            problems.append(f"{tag}: the banner shows with no refusal")

        # ---- the banner appears with the Mac's next answer, in calm plain words
        state("buy")
        pg.evaluate("load('live',true)")
        if not wait(pg, "!document.getElementById('rsban').hidden"):
            problems.append(f"{tag}: the banner never showed")
        txt = pg.evaluate("document.getElementById('rsban').textContent")
        if not ("Kalshi isn't allowing orders for your account right now" in txt and "waiting until" in txt
                and "Tap to read what Kalshi said" in txt) or "API key" in txt:
            problems.append(f"{tag}: banner words: {txt}")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
            problems.append(f"{tag}: sideways scroll with the banner")
        pg.evaluate("document.querySelector('#rsban button').click()")
        if not wait(pg, "!!document.querySelector('#modal.on #sheet .rsheet')"):
            problems.append(f"{tag}: the banner tap didn't open Kalshi's message")
        else:
            got = pg.evaluate("document.querySelector('#sheet .rsmsg').textContent")
            if got != NEV:
                problems.append(f"{tag}: message not whole: {got[:80]}...{got[-40:]}")
            sheet = pg.evaluate("document.querySelector('#sheet').textContent")
            if "Kalshi's rule" not in sheet or "not a problem in the app" not in sheet or "Copy message" not in sheet \
                    or "forbidden_for_region" not in sheet or "write" in sheet:
                problems.append(f"{tag}: sheet words: {sheet[:200]}")
            if pg.evaluate("getComputedStyle(document.querySelector('#sheet .rsmsg')).userSelect") != "text":
                problems.append(f"{tag}: the message can't be selected")
            if pg.evaluate("document.querySelector('#sheet').scrollWidth>document.querySelector('#sheet').clientWidth+1"):
                problems.append(f"{tag}: the sheet scrolls sideways")
            if scheme == "dark" and size[0] == 390:
                time.sleep(.6); pg.screenshot(path=os.path.join(os.environ.get("SHOT_DIR", "."), "refusal_sheet.png"))
            pg.evaluate("closeModal()"); wait(pg, "!document.querySelector('#modal.on')")

        # ---- a refused tap answers with Kalshi's words in a sheet; the clipped toast is held back
        pg.route("**/app/api/act", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"ok": False, "msg": "Kalshi said: x", "error": "Kalshi said: x",
             "refusal": {"msg": NEV, "code": "forbidden_for_region", "status": 403, "restricted": True, "scope": "buy"}})))
        pg.evaluate("api('/app/api/act',{a:'buy',i:1}).then(r=>{if(r.error)toast(r.error,3000,'bad')})")
        if not wait(pg, "!!document.querySelector('#modal.on #sheet .rsheet')"):
            problems.append(f"{tag}: a refused tap didn't show Kalshi's message")
        elif pg.evaluate("document.querySelector('#sheet .rsmsg').textContent") != NEV:
            problems.append(f"{tag}: the refused tap's message isn't whole")
        if pg.evaluate("(()=>{const t=document.getElementById('toast');return t&&t.classList.contains('on')&&!t.hidden})()"):
            problems.append(f"{tag}: a clipped toast showed next to the full message")
        pg.evaluate("closeModal()"); wait(pg, "!document.querySelector('#modal.on')")
        # a held tap (nothing sent) never pops the sheet over and over, only the banner says it
        pg.unroute("**/app/api/act")
        pg.route("**/app/api/act", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"ok": False, "error": "Kalshi isn't allowing orders for your account right now, so nothing was sent.",
             "refusal": {"msg": NEV, "code": "forbidden_for_region", "status": 403, "restricted": True, "held": True}})))
        pg.evaluate("api('/app/api/act',{a:'buy',i:1})"); time.sleep(.8)
        if pg.evaluate("!!document.querySelector('#modal.on #sheet .rsheet')"):
            problems.append(f"{tag}: a held tap opened the sheet")
        pg.unroute("**/app/api/act")
        # an ordinary refusal (not the region) is shown whole too, without the region wording
        pg.route("**/app/api/act", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"ok": False, "error": "Kalshi said: This market is closed to new orders.",
             "refusal": {"msg": "This market is closed to new orders.", "code": "forbidden", "status": 403, "restricted": False}})))
        pg.evaluate("api('/app/api/act',{a:'buy',i:1})")
        wait(pg, "!!document.querySelector('#modal.on #sheet .rsheet')")
        sheet = pg.evaluate("(document.querySelector('#modal.on #sheet')||{}).textContent||''")
        if "This market is closed to new orders." not in sheet or "Kalshi's rule for your account" in sheet:
            problems.append(f"{tag}: ordinary refusal sheet: {sheet[:160]}")
        pg.evaluate("closeModal()"); pg.unroute("**/app/api/act"); wait(pg, "!document.querySelector('#modal.on')")

        # ---- the real server hands the page the note on Build, Settings and the panel, and a real refused act carries it
        got = pg.evaluate("api('/app/api/build?lg=nba').then(r=>r.restrict&&r.restrict.buy)")
        if not (got and got.get("active") and got.get("holding") and got.get("msg") == NEV):
            problems.append(f"{tag}: build didn't carry the restriction: {got}")
        pg.evaluate("go('settings')")
        if not wait(pg, "!!document.querySelector('#main')&&/Last Kalshi refusal/.test(document.getElementById('main').textContent)"):
            problems.append(f"{tag}: Settings > Money has no 'Last Kalshi refusal' row")
        else:
            row = pg.evaluate("document.getElementById('main').textContent")
            if "still in place" not in row or "Nevada residents" not in row:
                problems.append(f"{tag}: settings row words")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
            problems.append(f"{tag}: sideways scroll on Settings")

        # ---- a sell-side note says "sales", and a note the Mac cleared takes the banner away
        pg.evaluate("go('live')")
        state("sell"); pg.evaluate("load('live',true)")
        wait(pg, "/sales/.test(document.getElementById('rsban').textContent)")
        if "sales" not in pg.evaluate("document.getElementById('rsban').textContent"):
            problems.append(f"{tag}: sell banner words")
        clear(); pg.evaluate("load('live',true)")
        if not wait(pg, "document.getElementById('rsban').hidden"):
            problems.append(f"{tag}: the banner stayed after the Mac cleared the note")
        # a note that has run its hold but not been cleared still shows (it will check again on the next buy)
        state("buy", holding=False); pg.evaluate("load('live',true)")
        wait(pg, "!document.getElementById('rsban').hidden")
        if "next one you place will check again" not in pg.evaluate("document.getElementById('rsban').textContent"):
            problems.append(f"{tag}: not-holding words")
        clear()
        print(tag, "errs:", errs)
        if errs:
            problems.append(f"{tag}: JS errors {errs}")
        pg.close()
    br.close()
clear()
if problems:
    print("PROBLEMS:", problems)
else:
    print("kalshi refusals page: all good")
