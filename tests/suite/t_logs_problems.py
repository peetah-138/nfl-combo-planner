# CHECK: group=engine
"""tools/read_prod_logs.py --problems (#379): the preset keeps only refused/check/failed/held/Traceback lines, and the
client stays read-only (it only ever sends GET to /api/logs). Nothing here touches a real Mac: the answer is faked."""
import sys, os, json, threading, http.server, subprocess
TOOL = os.path.join(os.environ["REPO"], "tools", "read_prod_logs.py")
LINES = ["buy ok", "order REFUSED by kalshi", "price check skipped", "all fine", "sell FAILED: timeout", "order held for review",
         "Traceback (most recent call last):", "tick"]
SEEN = []


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        SEEN.append(("GET", self.path.split("?")[0]))
        body = json.dumps({"lines": [{"t": 1700000000 + i, "text": t} for i, t in enumerate(LINES)], "status": {}, "source": "console"}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        SEEN.append(("POST", self.path)); self.send_response(405); self.end_headers()

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
env = dict(os.environ, CW_LOGS_URL=f"http://127.0.0.1:{srv.server_port}", CW_LOGS_TOKEN="not-a-real-code")
bad = []


def run(*args):
    return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=env, timeout=30)


r = run("--problems")
got = r.stdout.splitlines()
if r.returncode != 0 or got != [LINES[1], LINES[2], LINES[4], LINES[5], LINES[6]]:
    bad.append(f"--problems kept the wrong lines: {got} {r.stderr[:200]}")
if "not-a-real-code" in r.stdout + r.stderr:
    bad.append("the code was printed")
r = run("--problems", "--grep", "x")
if r.returncode == 0:
    bad.append("--problems with --grep should be refused")
r = run("--problems", "--source", "db", "--tables")
if r.returncode == 0:
    bad.append("--problems with --source db should be refused")
if not SEEN or any(m != "GET" or p != "/api/logs" for m, p in SEEN):
    bad.append(f"the client sent something other than GET /api/logs: {SEEN}")
for b in bad:
    print("FAIL " + b)
if not bad:
    print("PASS --problems keeps only refused/check/failed/held/Traceback lines, refuses --grep and db, stays GET-only")
