# CHECK: group=engine
"""GET /api/logs reads only its two files (#377): source allowlist, no path tricks, no symlinks."""
import sys, os, json, socket, tempfile, importlib.util, inspect, time, http.client
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

import re, ast
MARK = "MARKER-LINE-IN-WATCHER-LOG"
SECRET_TEXT = "SYMLINK-TARGET-SECRET-4471"
conf = {"topic": "zq7-fake-topic-91", "secret": "fakeSharedSecret4471", "web_pass": "pass1234xy"}
tok = W.log_new_token(conf)
srv, port = start(conf)
write_log("watcher.log", time.strftime("%Y-%m-%d %H:%M:%S") + " " + MARK + "\n")
write_log("combo_autosell_log.jsonl", json.dumps({"at": time.time(), "ticker": "KXA-1"}) + "\n")
write_log("combo_settings.json", json.dumps({"private": SECRET_TEXT}))
write_log("history.db", SECRET_TEXT)

for q in ("?source=../../etc/passwd", "?source=history", "?source=combo_settings", "?source=/etc/passwd", "?source=watcher.log",
          "?source=Console", "?source=console&source=autosell", "?path=/etc/passwd", "?file=watcher.log",
          "?source=console&path=x", "?source=console&file=x", "?limit=5&extra=1", "?SOURCE=console"):
    fresh(); c, b, _ = req(port, "/api/logs" + q, tok=tok)
    ok(f"{q or '(empty)'}: 400 empty body", c == 400 and b == b"")

for path in ("/api/logs/../x", "/api/logs%2f..", "/api/logs/../../etc/passwd", "/api/logs/", "/api/logs/..%2fwatcher.log",
             "/api/logs%2e%2e/watcher.log", "//api/logs/../combo_settings.json", "/api/logs/watcher.log", "/api/logsx"):
    fresh(); c, b, _ = req(port, path, tok=tok)
    ok(f"path {path}: no file contents", MARK.encode() not in b and SECRET_TEXT.encode() not in b and b"root:" not in b)
    ok(f"path {path}: not a log answer", c != 200 or b'"lines"' not in b)

# a symlink named watcher.log must not be followed
other = tempfile.mkdtemp(dir="run")
target = os.path.join(other, "elsewhere.txt")
open(target, "w").write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + SECRET_TEXT + "\n")
os.remove(os.path.join(W.HOME, "watcher.log"))
os.symlink(target, os.path.join(W.HOME, "watcher.log"))
fresh(); c, b, _ = req(port, tok=tok)
ok("symlinked watcher.log: 503 (O_NOFOLLOW)", c == 503)
ok("symlinked watcher.log: empty body, the secret text is not in it", b == b"" and SECRET_TEXT.encode() not in b)
try:
    W.log_answer(conf, M, "console", home=W.HOME); raised = None
except OSError as e:
    raised = e
ok("log_answer on the symlink raises OSError", isinstance(raised, OSError))
os.remove(os.path.join(W.HOME, "watcher.log"))
os.mkdir(os.path.join(W.HOME, "watcher.log"))
fresh(); c, b, _ = req(port, tok=tok)
ok("a directory named watcher.log: 503 empty", c == 503 and b == b"")
os.rmdir(os.path.join(W.HOME, "watcher.log"))
fresh(); c, b, _ = req(port, tok=tok)
ok("a missing watcher.log: 200 with no lines", c == 200 and json.loads(b)["lines"] == [])

# the allowlist itself
for bad in ("history", "combo_settings", "../../etc/passwd", "/etc/passwd", "", "watcher.log", None):
    try:
        W.log_answer(conf, M, bad, home=W.HOME); got = None
    except KeyError:
        got = "KeyError"
    except Exception as e:
        got = type(e).__name__
    ok(f"log_answer(source={bad!r}) raises KeyError", got == "KeyError")
src = inspect.getsource(W)
m = re.search(r"^LOG_SOURCES = (\{[^}]*\})", src, re.M)
d = ast.literal_eval(m.group(1)) if m else {}
ok("LOG_SOURCES in the source has exactly the two keys", sorted(d) == ["autosell", "console"] and len(d) == 2)
ok("they map to watcher.log and combo_autosell_log.jsonl and nothing else",
   d == {"console": "watcher.log", "autosell": "combo_autosell_log.jsonl"} and W.LOG_SOURCES == d)
rd = inspect.getsource(W.log_answer) + inspect.getsource(W.log_tail) + inspect.getsource(W.log_route)
ok("reading goes only through log_tail's single os.open (no other open() in answer, tail or route)",
   rd.count("os.open(") == 1 and "open(" not in rd.replace("os.open(", ""))
for q in ("?source=", "?since=", "?limit="):      # a blank value is a bad question, not the default
    fresh(); c, b, _ = req(port, "/api/logs" + q, tok=tok)
    ok(f"blank value {q}: refused with 400 and an empty body", c == 400 and not b)
srv.shutdown()
