# CHECK: group=page
# Settings › The Mac: the sportsbook odds credits row (remaining, pace, run-out, reset, low mode), on a phone, from
# the Mac's read-only status (/app/mac-info, faked here). No JS errors, no sideways scroll, plain English.
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
now = time.time()
BASE = {"ok": True, "watcher": "2026.11.21.128", "engine": "2026.11.21.128", "up": 1300, "role": "main", "paused": False,
        "auto_update": True, "waiting": "", "latest": "2026.11.21.128", "checked": now - 400}
DEC1 = 1796083200   # 2026-12-01 00:00 UTC
CASES = {
    "ok": {"remaining": 412, "used": 88, "last": 2, "at": now - 300, "per_day": 9.5, "runs_out": now + 43 * 86400,
           "reset": DEC1, "reset_guess": True, "low": False, "why": None, "saving": False},
    "low": {"remaining": 31, "used": 469, "last": 2, "at": now - 60, "per_day": 24, "runs_out": now + 1.3 * 86400,
            "reset": DEC1, "reset_guess": True, "low": True, "why": "floor", "saving": True},
    "out": {"remaining": 0, "used": 500, "last": 0, "at": now - 60, "per_day": None, "runs_out": None,
            "reset": DEC1, "reset_guess": False, "low": True, "why": "out", "saving": True},
    "none": {"none": True},
    "nokey": None,
}
problems = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=scheme)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        cur = {"k": "ok"}
        pg.route("**/app/mac", lambda r: r.fulfill(status=200, content_type="application/json",   # the Mac's own screen
                                                   body=json.dumps(dict(BASE, odds=CASES[cur["k"]], pass_="x", log=[]))))
        pg.route("**/app/mac-info", lambda r: r.fulfill(status=200, content_type="application/json",
                                                        body=json.dumps(dict(BASE, odds=CASES[cur["k"]]))))
        pg.goto(B + "/app"); time.sleep(2); pg.evaluate("go('settings')")
        for k in CASES:
            cur["k"] = k
            pg.evaluate("S.mac=null;(document.getElementById('s-mac')||{remove(){}}).remove();load('settings')")
            txt, drawn = "", False
            for _ in range(200):          # wait for the Mac card drawn from this case's answer (not the last one's)
                time.sleep(.3)
                if pg.evaluate("!!(S.mac&&S.mac.ok&&document.getElementById('s-mac'))"):
                    drawn = True
                    txt = pg.evaluate("(document.getElementById('oddsrow')||{}).textContent||''")
                    break
            if not drawn:
                problems.append(f"{scheme} {k}: the Mac card never drew")
            print(scheme, k, "->", txt.replace("\n", " | "))
            if txt:
                vis = pg.evaluate("(()=>{const e=document.getElementById('oddsrow');e.scrollIntoView();const r=e.getBoundingClientRect();"
                                  "return r.height>0&&r.width>0&&getComputedStyle(e).visibility!=='hidden'})()")
                if not vis:
                    problems.append(f"{scheme} {k}: the row isn't visible")
            wide = pg.evaluate("document.documentElement.scrollWidth>innerWidth+1")
            if wide:
                problems.append(f"{scheme} {k}: sideways scroll")
            if k == "ok" and not ("412 of 500 left" in txt and "about 9.5 a day" in txt and "resets about Dec 1" in txt
                                  and "lasts past the reset" in txt and "Running low" not in txt):
                problems.append(f"ok row wrong: {txt}")
            if k == "low" and not ("31 of 500 left" in txt and "runs out" in txt and "Running low" in txt):
                problems.append(f"low row wrong: {txt}")
            if k == "out" and not ("Used up" in txt and "resets Dec 1" in txt and "about Dec" not in txt):
                problems.append(f"out row wrong: {txt}")
            if k == "none" and "next sportsbook check" not in txt:
                problems.append(f"none row wrong: {txt}")
            if k == "nokey" and txt:
                problems.append(f"row shown without a key: {txt}")
            if k in ("ok", "low") and scheme == "dark":
                el = pg.locator("#oddsrow")
                el.scroll_into_view_if_needed(); time.sleep(.7)
                pg.locator(".scard", has=el).first.screenshot(path=os.path.join(os.environ.get("SHOT_DIR", "."), f"oddscredits_{k}.png"))
            if k == "low":
                bar = pg.evaluate("getComputedStyle(document.querySelector('#oddsrow .bar i')).width")
                if not bar or bar == "0px":
                    problems.append("low: the bar didn't draw")
        print("errs:", errs)
        pg.close()
    br.close()
if problems:
    print("PROBLEMS:", problems)
else:
    print("odds credits row: all good")
