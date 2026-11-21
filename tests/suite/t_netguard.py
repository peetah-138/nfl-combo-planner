# The engine tests run offline (GitHub #189): run_checks.sh puts suite/netguard on PYTHONPATH, and its sitecustomize
# refuses every request to a host outside this machine before anything is sent. Real ESPN injury news once made
# t_live_panel fail in CI only, at some hours of the day. This checks the guard is really on and leaves localhost alone.
import threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
import sys
ok("the offline guard is loaded (sitecustomize from suite/netguard)",
   "netguard" in (getattr(sys.modules.get("sitecustomize"), "__file__", "") or ""))
for url in ("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries",
            "https://api.elections.kalshi.com/trade-api/v2/markets"):
    t0 = time.time()
    try:
        requests.get(url, timeout=20)
        refused = False
    except requests.ConnectionError as e:
        refused = "offline in tests" in str(e)
    ok(f"an outside host is refused at once, as a ConnectionError ({url.split('/')[2]})", refused and time.time() - t0 < 1)


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
r = requests.get(f"http://127.0.0.1:{srv.server_port}/x", timeout=5)
ok("the tests' own fakes on this machine still answer", r.status_code == 200 and r.text == "ok")
srv.shutdown()
