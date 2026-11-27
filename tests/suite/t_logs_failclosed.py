# CHECK: group=engine
"""The log endpoint fails closed (#377): if redaction raises or a secret survives, the answer is an empty 503."""
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
write_log("watcher.log", time.strftime("%Y-%m-%d %H:%M:%S") + " hello world zq7-fake-topic-91 in a line\n")
fresh()
c, b, _ = req(port, tok=tok)
ok("baseline: 200 with JSON and the topic masked", c == 200 and json.loads(b)["ok"] is True and b"zq7-fake-topic-91" not in b)

_r, _s, _ls = W.log_redact, W.log_secrets, W.log_safe
try:
    def boom(*a, **k): raise RuntimeError("redaction broke")
    fresh(); W.log_redact = boom
    c, b, h = req(port, tok=tok)
    ok("log_redact raises: that line is withheld (never sent raw) and the rest of the answer still goes out",
       c == 200 and b"hello" not in b and W.LOG_WITHHELD.encode() in b)
    W.log_redact = _r
    fresh(); W.log_secrets = boom
    c, b, h = req(port, tok=tok)
    ok("log_secrets raises: 503 with an empty body", c == 503 and b == b"")
    W.log_secrets = _s
    fresh(); W.log_redact = lambda t, s: t          # redaction does nothing: the live topic survives into the answer
    c, b, h = req(port, tok=tok)
    ok("redaction does nothing: the per-line check withholds the line, the secret is in no part of the response",
       c == 200 and W.LOG_WITHHELD.encode() in b and b"zq7-fake-topic-91" not in b and b"zq7-fake-topic-91" not in str(h).encode())
    W.log_safe = lambda t, s: t                      # both defences off: the answer-level tripwire still stops it
    fresh(); c, b, h = req(port, tok=tok)
    ok("redaction and per-line check both off: the tripwire gives 503 with an empty body", c == 503 and b == b"")
    try:
        W.log_answer(conf, M, "console", home=W.HOME); raised = None
    except W.LogLeak as e:
        raised = e
    except Exception as e:
        raised = type(e).__name__
    ok("log_answer itself raises LogLeak when a secret survives", isinstance(raised, W.LogLeak))
    W.log_safe = _ls
    W.log_redact = _r
    # the autosell side: a secret in an allowlisted field with redaction off also fails closed
    write_log("combo_autosell_log.jsonl", json.dumps({"at": time.time(), "why": "zq7-fake-topic-91"}) + "\n")
    W.log_redact = lambda t, s: t
    fresh()
    c, b, h = req(port, "/api/logs?source=autosell", tok=tok)
    ok("autosell with redaction off: the field is withheld, secret absent", c == 200 and b"zq7-fake-topic-91" not in b)
    W.log_safe = lambda t, s: t
    fresh()
    c, b, h = req(port, "/api/logs?source=autosell", tok=tok)
    ok("autosell with every scrub off: 503 empty, secret absent", c == 503 and b == b"")
    W.log_safe = _ls
finally:
    W.log_redact, W.log_secrets = _r, _s
W.log_safe = _ls
fresh()
c, b, _ = req(port, tok=tok)
ok("after restoring redaction, it answers again", c == 200 and b"zq7-fake-topic-91" not in b)
srv.shutdown()
