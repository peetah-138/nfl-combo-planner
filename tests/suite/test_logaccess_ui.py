# CHECK: group=page secs=14
# Settings › This Mac › "Let the dev Mac read logs" (issue #377): off by default, on shows a one-time code sheet with
# Copy, and the on row says when it was last read. The /app/mac answers are faked here (no real code is made).
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("LOG_SHOTS") or "."
from playwright.sync_api import sync_playwright
STATE = {"on": False, "calls": []}
DLG = {"ok": True}
FAKE = "fake-code-for-the-screenshot-0123456789ab"


def mac(route):
    body = json.loads(route.request.post_data or "{}")
    STATE["calls"].append(body.get("a"))
    if body.get("a") == "logaccess":
        STATE["on"] = bool(body.get("on"))
        ans = {"ok": True, "msg": "The dev Mac can no longer read logs." if not STATE["on"] else "Copy the code now",
               "logs": {"on": STATE["on"], "at": int(time.time()), "read": None}}
        if STATE["on"]:
            ans.update(token=FAKE, url="http://100.64.0.1:8765")
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(ans))
    logs = {"on": STATE["on"], "at": int(time.time()) - 600, "read": int(time.time()) - 120} if STATE["on"] else {"on": False}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"ok": True, "up": 5000, "engine": "v", "watcher": "v", "ts": "100.64.0.1", "role": "main", "pass": "x",
         "auto_update": True, "https": {}, "log": [], "logs": logs}))


with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        STATE["on"] = False
        pg = br.new_page(viewport={"width": 390, "height": 844}, color_scheme=scheme)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        dialogs = []
        pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))      # the page must not use the browser confirm()
        pg.route("**/app", lambda route: (lambda r: route.fulfill(response=r, body=r.text().replace("LOCAL=false", "LOCAL=true")))(route.fetch()))
        pg.route("**/app/mac", mac)
        pg.goto(B + "/app"); time.sleep(3); pg.evaluate("go('settings')")
        row = pg.locator("#logrow")
        for _ in range(30):
            time.sleep(.5)
            if row.count():
                break
        print(scheme, "row:", row.count())
        if not row.count():
            print("PROBLEMS: no 'Let the dev Mac read logs' row on this Mac's settings")
            continue
        row.scroll_into_view_if_needed(); time.sleep(.4)
        if pg.locator("#logrow input").is_checked():
            print("PROBLEMS: log reading shows on by default")
        pg.screenshot(path=os.path.join(SHOTS, f"logs_off_{scheme}.png"))
        pg.locator("#logrow input").click(); time.sleep(1.2)
        code = pg.locator("#lc")
        print(scheme, "code sheet:", code.count(), "copy:", pg.locator("button", has_text="Copy code").count())
        if not code.count() or code.text_content() != FAKE:
            print("PROBLEMS: turning it on didn't show the code once")
        pg.screenshot(path=os.path.join(SHOTS, f"logs_code_{scheme}.png"))
        pg.locator("button", has_text="Done").click(); time.sleep(1.5)
        row.scroll_into_view_if_needed(); time.sleep(.4)
        txt = row.text_content() or ""
        print(scheme, "on row:", txt[:120])
        if "last read" not in txt or not pg.locator("#logrow input").is_checked():
            print("PROBLEMS: the on row doesn't say it's on and when it was last read")
        if FAKE in (pg.content() or ""):
            print("PROBLEMS: the code is still on screen after Done")
        pg.screenshot(path=os.path.join(SHOTS, f"logs_on_{scheme}.png"))
        # #378: "Stop reading" asks in the app's own sheet (no browser confirm); Cancel leaves it on, the other button turns it off
        n = STATE["calls"].count("logaccess")
        pg.locator("#logrow input").click(); time.sleep(.8)
        if not pg.evaluate("document.querySelector('#modal.on')&&document.querySelector('#sheet').innerText.includes('Stop the dev Mac reading logs?')"):
            print("PROBLEMS: stopping didn't ask in the app's own sheet")
        small = pg.evaluate("[...document.querySelectorAll('#sheet .btn')].filter(b=>b.getBoundingClientRect().height<44).length")
        if small:
            print("PROBLEMS: a button on the confirm sheet is under 44px")
        pg.screenshot(path=os.path.join(SHOTS, f"logs_stop_sheet_{scheme}.png"))
        pg.locator("#sheet button", has_text="Cancel").click(); time.sleep(.8)
        if not pg.locator("#logrow input").is_checked() or STATE["calls"].count("logaccess") != n:
            print("PROBLEMS: cancelling 'stop' still turned it off")
        pg.locator("#logrow input").click(); time.sleep(.8)
        pg.locator("#sheet button", has_text="Stop reading").click()
        for _ in range(20):
            time.sleep(.5)
            if not pg.locator("#logrow input").is_checked():
                break
        if pg.locator("#logrow input").is_checked() or "logaccess" not in STATE["calls"][-3:]:
            print("PROBLEMS: turning it off didn't stick")
        if dialogs:
            print("PROBLEMS: the page opened a browser confirm:", dialogs)
        print(scheme, "calls:", STATE["calls"], "errs:", errs)
        if errs:
            print("PROBLEMS: page errors", errs)
        STATE["calls"] = []
        pg.close()
    br.close()
