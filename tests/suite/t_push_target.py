# CHECK: group=engine
"""Tapping a notification must open the Combo Hub page, never an empty file (#79). Covers the service worker text
(default target '/', legacy '/app' mapped), the engine's alert links, and the hub: a page navigation to /app or /app/
redirects to '/', any navigation that finds nothing (or no session) gets a small HTML page and never an empty
octet-stream, while API-style requests (no text/html Accept) and the /app/api/ routes behave exactly as before."""
import sys, re, importlib.util, inspect
sys.path.insert(0, "stub"); sys.path.insert(0, "run")
import nfl_combo_planner as M
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
W.log = lambda *a: None; W.CONF = "run/test_watcher_conf.json"; W.HOME = "run"
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)

# ---- service worker text
sw = W.SW_JS
ok("sw: default target when a push has no url is '/'", "d.url || '/'" in sw and "d.url || '/app'" not in sw)
ok("sw: legacy '/app' and '/app/' payloads are mapped to '/' on tap",
   "u.pathname === '/app' || u.pathname === '/app/'" in sw and "tapTarget(e.notification.data" in sw)
ok("sw: the mapped target keeps the query and #hash and stays on this origin",
   "new URL('/' + u.search + u.hash, self.location.origin)" in sw)
ok("sw: still takes over at once (skipWaiting + clients.claim)", "self.skipWaiting()" in sw and "self.clients.claim()" in sw)
ok("sw: still opens or navigates a window on tap", "openWindow(url)" in sw and "c.navigate(url)" in sw and "showNotification" in sw)
ok("page: an open app follows a #s= or #c= link tapped from a notification (hashchange)",
   "addEventListener('hashchange',()=>{ideaFromHash(true);comboFromHash(true);})" in W.SPA)

# ---- #210: an alert about one combo opens that combo ('/#c=<ticker>'); anything else opens Live as before
class _E:
    MINE = {"hold": {"KXMVE-24": {"label": "Combo 24"}, "KXMVE-2": {"label": "Combo 2"}},
            "snap": {"KXMVE-24": {"label": "Combo 24"}, "KXMVE-2": {"label": "Combo 2"}, "KXMVE-9": {"label": "Combo 9"},
                     "bad<x>": {"label": "Combo 7"}}}
ok("combo_link: an alert naming Combo 24 opens Combo 24", W.combo_link(_E, "🤖 Took the profit: Combo 24 sold for $9.00") == "/#c=KXMVE-24")
ok("combo_link: 'Combo 2' is a whole word (not Combo 24)", W.combo_link(_E, "🎉 Combo 2 hit! Pays $40.") == "/#c=KXMVE-2")
ok("combo_link: a settled combo still in this refresh's list links too", W.combo_link(_E, "❌ Combo 9 is out.") == "/#c=KXMVE-9")
ok("combo_link: two combos named = no link (Live)", W.combo_link(_E, "Cash out Combo 2 ($5), Combo 24 ($9)?") is None)
ok("combo_link: no combo named, or one not on Live = no link", W.combo_link(_E, "⏸ Paused") is None and W.combo_link(_E, "Combo 77 sold") is None)
class _E2:
    MINE = {"hold": {"KXMVE-24": {"label": "Nuggets + Chiefs +2", "num": "Combo 24"}, "KXMVE-2": {"label": "Nuggets", "num": "Combo 2"}}, "snap": {}}
ok("combo_link (#520): an alert naming a combo by its picks opens it", W.combo_link(_E2, "🤖 Took the profit: Nuggets + Chiefs +2 sold for $9.00") == "/#c=KXMVE-24")
ok("combo_link (#520): a short name inside a longer one does not steal the tap", W.combo_link(_E2, "Cash out Nuggets + Chiefs +2 ($5)?") == "/#c=KXMVE-24")
ok("combo_link: a ticker with unsafe characters is never put in a link", W.combo_link(_E, "Combo 7 sold") is None)
ok("combo_link: never raises", W.combo_link(None, "Combo 24") is None)
_sent = []
_push, _pub = W.push, W.BUS.publish
W.push = lambda conf, msg, **kw: _sent.append(kw)
W.BUS.publish = lambda ev: None
_n = W.Notifier({"topic": "t"}, type("E2", (), {"MINE": _E.MINE, "CFG": {}})())
_n.add("🤖 Auto cash-out: Combo 24 sold for $9.00")
ok("Notifier: an urgent alert about one combo is pushed with its link", _sent and _sent[-1].get("click") == "/#c=KXMVE-24")
_n.add("🤖 Auto cash-out paused for today")
ok("Notifier: an urgent alert about no combo keeps the plain tap (Live)", _sent[-1].get("click") is None)
W.push, W.BUS.publish = _push, _pub
ok("sw: carries a version note so the browser sees a changed worker", "service worker (v2" in sw)

# ---- defaults in code
ok("web_push / Push.send default to '/'", inspect.signature(W.web_push).parameters["url"].default == "/"
   and inspect.signature(W.Push.send).parameters["url"].default == "/")
src_w, src_m = inspect.getsource(W), inspect.getsource(M)
ok("no notification target is '/app' any more (watcher + engine)",
   not re.search(r'url="/app"|click="/app"|or "/app"|"/app#s=|f"/app#s=|"cash", "/app"|"value", "/app"', src_w + src_m))

# ---- the hub
import socket
_s = socket.socket(); _s.bind(("127.0.0.1", 0)); PORT = _s.getsockname()[1]; _s.close()      # a free port, never one another run is using
conf = {"topic": "t", "secret": "s", "hub_port": PORT, "web_pass": "pass1234", "https_auto": False}
srv = W.start_hub(conf, M)
import requests
B = f"http://127.0.0.1:{PORT}"
HTML = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
REMOTE = {"X-Forwarded-For": "1.2.3.4"}          # like a phone arriving over Tailscale (a request from the Mac itself skips the login)
s = requests.Session(); s.headers.update(REMOTE); s.post(B + "/login", data={"pass": "pass1234"}); ck = s.cookies.get("cw")
anon = requests.Session(); anon.headers.update(REMOTE)


def nav(sess, path, hdr=None):
    return sess.get(B + path, headers=dict(HTML, **(hdr or {})), allow_redirects=False)


for who, sess in (("no session", anon), ("signed in", s)):
    for path in ("/app", "/app/"):
        r = nav(sess, path)
        ok(f"hub ({who}): navigation to {path} redirects to '/'", r.status_code == 302 and r.headers.get("Location") == "/")
    r = nav(sess, "/app?x=1")
    ok(f"hub ({who}): /app with a query also redirects, keeping the query: {r.status_code} {r.headers.get('Location')}", r.status_code == 302 and r.headers.get("Location") == "/?x=1")
    for path in ("/nothing-here", "/app/nope", "/app/api/live") + (("/app/events",) if sess is anon else ()):   # signed in, events is a live stream
        r = nav(sess, path)
        body = r.content
        ok(f"hub ({who}): navigation to {path} gets HTML with a link home, not an empty file",
           r.status_code in (403, 404) and r.headers.get("Content-Type", "").startswith("text/html")
           and b"href='/'" in body and len(body) > 100 and r.headers.get("Content-Length") == str(len(body)))
r = nav(anon, "/")
ok("hub: '/' without a session is still the login page", r.status_code == 200 and "Passcode" in r.text)
r = nav(s, "/")
ok("hub: '/' with a session is still the app, not a redirect", r.status_code != 302 and r.status_code != 404)

# the app's own calls and API routes are exactly as before
H = {"X-Forwarded-For": "1.2.3.4"}
r = requests.get(B + "/app/api/live", headers=H)
ok("hub: /app/api/live without a session is still 403 and empty", r.status_code == 403 and r.content == b"")
r = requests.get(B + "/app/api/live", headers=dict(H, Cookie=f"cw={ck}"))
ok("hub: /app/api/live with the cookie but no X-CW token is still 403 and empty", r.status_code == 403 and r.content == b"")
r = requests.get(B + "/app/events", headers={"Accept": "text/event-stream"})
ok("hub: /app/events without a session is still 403 and empty", r.status_code == 403 and r.content == b"")
r = requests.get(B + "/app/", headers=dict(H, Cookie=f"cw={ck}"))
ok("hub: /app/ without text/html or the token (an API-style call) is still 403 and empty", r.status_code == 403 and r.content == b"")
r = requests.get(B + "/app/", headers=dict(H, Cookie=f"cw={ck}", **{"X-CW": ck}))
ok("hub: /app/ with cookie + X-CW is still passed through (not a redirect)", r.status_code != 302)
r = requests.get(B + "/app?frag=1", headers=dict(H, Accept="text/html", Cookie=f"cw={ck}", **{"X-CW": ck}))
ok("hub: /app?frag=1 with cookie + token is still passed through", r.status_code != 302)
r = requests.get(B + "/app?frag=1", headers=dict(H, Accept="text/html"))
ok("hub: /app?frag=1 without a session is not redirected (403)", r.status_code == 403)
r = requests.get(B + "/nothing-here", headers=H)
ok("hub: a non-page 404 is unchanged (empty octet-stream)",
   r.status_code == 404 and r.content == b"" and r.headers.get("Content-Type") == "application/octet-stream")
r = requests.post(B + "/nothing", data=b"x", headers=dict(H, Accept="text/html"))
ok("hub: POSTs are unchanged (still empty 403)", r.status_code == 403 and r.content == b"")
r = requests.post(B + "/app/mac-info", data="{}")
ok("hub: /app/mac-info without a session is still 403", r.status_code == 403)
srv.shutdown()
