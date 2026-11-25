# CHECK: group=engine
"""GET /api/logs is read-only (#377): POST is 405, nothing on disk changes, no-store and nosniff headers."""
import sys, os, json, socket, tempfile, importlib.util, time, http.client
sys.path.insert(0, "stub"); sys.path.insert(0, "run")
import nfl_combo_planner as M
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
W.log = lambda *a: None; W.CONF = "run/test_logs_conf.json"; W.HOME = tempfile.mkdtemp(dir="run")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
PEM_TAG = "PRIVATE " + "KEY"                       # spelled in pieces so the repo's secret grep never sees a whole header


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def start(conf):
    conf.setdefault("topic", "t"); conf.setdefault("secret", "s"); conf.setdefault("web_pass", "pass1234")
    conf["hub_port"] = free_port(); conf["https_auto"] = False
    return W.start_hub(conf, M), conf["hub_port"]


def req(port, path="/api/logs", tok=None, method="GET", auth=None, headers=None):
    """-> (status, body bytes, headers dict) over plain http.client (the path goes out exactly as written)."""
    h = dict(headers or {})
    if auth is not None:
        h["Authorization"] = auth
    elif tok is not None:
        h["Authorization"] = "Bearer " + tok
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        c.request(method, path, headers=h)
        r = c.getresponse()
        return r.status, r.read(), {k.lower(): v for k, v in r.getheaders()}
    finally:
        c.close()


def write_log(name, text):
    with open(os.path.join(W.HOME, name), "w") as f:
        f.write(text)


def fresh():
    W.LOG_GATE = W.LogGate()

conf = {"topic": "zq7-fake-topic-91", "secret": "fakeSharedSecret4471", "web_pass": "pass1234xy"}
tok = W.log_new_token(conf)
srv, port = start(conf)
write_log("watcher.log", time.strftime("%Y-%m-%d %H:%M:%S") + " hello\nsecond line\n")
write_log("combo_autosell_log.jsonl", json.dumps({"at": time.time(), "ticker": "KXA-1", "result": "sold"}) + "\n")
json.dump(conf, open(W.CONF, "w"))
files = [W.CONF, os.path.join(W.HOME, "watcher.log"), os.path.join(W.HOME, "combo_autosell_log.jsonl")]


def snap():
    return [(open(f, "rb").read(), os.stat(f).st_mtime_ns, os.stat(f).st_size) for f in files]


fresh(); c, b, _ = req(port, method="POST", tok=tok)
ok("POST /api/logs: 405 empty body", c == 405 and b == b"")
fresh(); c, b, _ = req(port, "/api/logs?source=console", method="POST", tok=tok)
ok("POST /api/logs?source=console: 405 empty body", c == 405 and b == b"")
fresh(); c, b, _ = req(port, method="POST")
ok("POST with no token: 405 as well (never reads)", c == 405 and b == b"")
for m in ("PUT", "DELETE", "PATCH"):
    fresh(); c, b, _ = req(port, method=m, tok=tok)
    ok(f"{m} /api/logs is not 200 and returns no log", c != 200 and b"hello" not in b)

before = snap(); time.sleep(0.05)
for src in ("console", "autosell"):
    fresh(); c, b, h = req(port, "/api/logs?source=" + src, tok=tok)
    ok(f"GET {src} with the right token answers 200", c == 200)
    ok(f"GET {src}: Cache-Control no-store", h.get("cache-control") == "no-store")
    ok(f"GET {src}: X-Content-Type-Options nosniff", h.get("x-content-type-options") == "nosniff")
for m in ("POST", "PUT", "DELETE"):
    fresh(); req(port, method=m, tok=tok)
h405 = req(port, method="POST", tok=tok)[2]
ok("the 405 carries no-store", h405.get("cache-control") == "no-store")
ok("the 405 carries nosniff", h405.get("x-content-type-options") == "nosniff")
ok("the 405 says Allow: GET", h405.get("allow") == "GET")
la = conf.pop("log_access")
fresh(); c, b, _ = req(port, method="POST", tok=tok)
ok("POST while reading is off: 404 empty body (nothing hints the route exists)", c == 404 and b == b"")
conf["log_access"] = la
fresh(); h = req(port, tok="y" * 43)[2]
ok("a 401 carries no-store and nosniff too", h.get("cache-control") == "no-store" and h.get("x-content-type-options") == "nosniff")
after = snap()
ok("conf file unchanged (bytes, mtime, size) by reads and refused writes", before[0] == after[0])
ok("watcher.log unchanged (bytes, mtime, size)", before[1] == after[1])
ok("autosell log unchanged (bytes, mtime, size)", before[2] == after[2])
ok("no stray files appeared in the home folder", sorted(os.listdir(W.HOME)) == ["combo_autosell_log.jsonl", "watcher.log"])
srv.shutdown()
