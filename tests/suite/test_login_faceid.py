"""The login page: iOS refuses the Face ID prompt that opens by itself, so the button has to work as the fallback."""
import sys, os, json, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = tempfile.mkdtemp()
sys.argv = ["combo_watcher.py"]
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
from playwright.sync_api import sync_playwright
HOST = "https://mac.example.ts.net"
PAGE = W.LOGIN_HTML.replace("__MSG__", "").replace("__FID__", "1").replace("__HTTPS__", HOST).replace("__ICON__", W.ICON_PNG)
problems, errs, calls = [], [], []
INIT = """
window.__gets=[];
navigator.credentials.get=function(o){const act=navigator.userActivation&&navigator.userActivation.isActive;window.__gets.push(!!act);
  if(!act){const e=new Error('no gesture');e.name='NotAllowedError';return Promise.reject(e);}
  const z=new Uint8Array(8);return Promise.resolve({id:'AAAA',response:{clientDataJSON:z.buffer,authenticatorData:z.buffer,signature:z.buffer}});};
"""
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for size in ({"width": 390, "height": 844}, {"width": 1280, "height": 900}):
        w = size["width"]
        pg = br.new_page(viewport=size)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script(INIT)

        def route(r):
            u = r.request.url.replace(HOST, "")
            if u == "/auth/begin":
                return r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps({"ok": True, "challenge": "AAAA", "rp": "mac.example.ts.net", "ids": ["AAAA"]}))
            if u == "/auth/finish":
                calls.append("finish")
                return r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))
            return r.fulfill(status=200, content_type="text/html", body=PAGE if u in ("/login", "") else "<html><body id=home>in</body></html>")
        pg.route(HOST + "/**", route)
        pg.goto(HOST + "/login"); pg.wait_for_timeout(1200)
        txt = pg.evaluate("document.getElementById('fidt').textContent")
        nudge = pg.evaluate("document.getElementById('fid').classList.contains('nudge')")
        msg = pg.evaluate("document.getElementById('msg').textContent.trim()")
        gets = pg.evaluate("window.__gets")
        if gets != [False]: problems.append(f"{w}: the auto prompt should be tried once, without a tap: {gets}")
        if not nudge or "Tap" not in txt: problems.append(f"{w}: no tap fallback after the refused auto prompt ({txt!r}, nudge={nudge})")
        if msg: problems.append(f"{w}: the refused auto prompt should not show an error ({msg!r})")
        if not pg.locator("#fid").is_visible(): problems.append(f"{w}: the Face ID button is not visible")
        if w == 390 and pg.evaluate("document.documentElement.scrollWidth>innerWidth"): problems.append("sideways scroll on a phone")
        calls.clear()
        pg.click("#fid"); pg.wait_for_timeout(1200)
        if "finish" not in calls: problems.append(f"{w}: tapping the button did not complete Face ID sign-in")
        pg.close()
    br.close()
print("errs:", errs)
if problems:
    print("PROBLEMS:", problems)
else:
    print("login Face ID fallback ok")
