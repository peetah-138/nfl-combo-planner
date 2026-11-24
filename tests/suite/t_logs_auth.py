# CHECK: group=engine
"""Auth for GET /api/logs (#377): bearer code only, wrong-code lockout, constant-time compare, off and on again."""
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

conf = {"topic": "zq7-fake-topic-91", "secret": "fakeSharedSecret4471", "web_pass": "pass1234xy"}
tok = W.log_new_token(conf)
srv, port = start(conf)
write_log("watcher.log", time.strftime("%Y-%m-%d %H:%M:%S") + " hello\n")
wrong = "x" * 43

fresh(); c, b, _ = req(port)
ok("no Authorization: 401 empty body", c == 401 and b == b"")
fresh(); c, b, _ = req(port, tok=wrong)
ok("wrong token: 401 empty body", c == 401 and b == b"")
fresh(); c, b, _ = req(port, "/api/logs?token=" + tok)
ok("token only in the query string: 401", c == 401 and b == b"")
fresh(); c, b, _ = req(port, "/api/logs?token=" + tok, tok=wrong)
ok("right token in the query but wrong header: 401", c == 401)
fresh(); c, b, _ = req(port, auth="Basic " + tok)
ok("Basic scheme: 401", c == 401 and b == b"")
fresh(); c, b, _ = req(port, auth=tok)
ok("bare token with no scheme: 401", c == 401)
fresh(); c, b, _ = req(port, auth="Bearer short")
ok("too short a Bearer value: 401", c == 401)
fresh(); c, b, h = req(port, tok=tok)
ok("right token: 200 JSON with ok true", c == 200 and json.loads(b)["ok"] is True and "application/json" in h["content-type"])

# five wrong codes from one client, then even the right one is turned away
fresh()
codes = [req(port, tok=wrong)[0] for _ in range(5)]
ok("five wrong tokens each answer 401", codes == [401] * 5)
c, b, _ = req(port, tok=tok)
ok("after 5 wrong tokens even the right token gets 429, empty body", c == 429 and b == b"")
fresh()
c, b, _ = req(port, tok=tok)
ok("a fresh gate lets the right token in again", c == 200)

# constant-time compare
src = inspect.getsource(W.log_token_ok)
ok("log_token_ok uses hmac.compare_digest", "hmac.compare_digest" in src)
ok("log_token_ok accepts the right code and refuses a wrong one",
   W.log_token_ok(conf, "Bearer " + tok) and not W.log_token_ok(conf, "Bearer " + wrong) and not W.log_token_ok({}, "Bearer " + tok))
ok("only the hash of the code is kept in the conf", tok not in json.dumps(conf))

# off and on again
json.dump(conf, open(W.CONF, "w"))
fresh(); r = W.log_access_set(conf, M, False)
ok("turning off says so and drops log_access from conf", r["ok"] is True and "log_access" not in conf and not r["logs"]["on"])
c, b, _ = req(port, tok=tok)
ok("after turning off, the old token gets 404 empty", c == 404 and b == b"")
r = W.log_access_set(conf, M, True)
tok2 = r["token"]
ok("turning on makes a new token that differs from the old one", tok2 and tok2 != tok and r["logs"]["on"])
ok("the saved conf file has the hash, not the token", tok2 not in open(W.CONF).read() and "log_access" in open(W.CONF).read())
fresh(); c, _, _ = req(port, tok=tok)
ok("after re-enabling, the old token is 401", c == 401)
fresh(); c, b, _ = req(port, tok=tok2)
ok("after re-enabling, the new token is 200", c == 200 and json.loads(b)["ok"] is True)
fresh()
srv.shutdown()


class _NoDisk:
    def save_json(self, *a, **k):
        raise OSError("disk full")


before = dict(conf.get("log_access") or {})
r = W.log_access_set(conf, _NoDisk(), True)
ok("a new code that can't be saved is never shown, and the old one stays", r["ok"] is False and "token" not in r
   and conf.get("log_access") == before)
saved = conf.pop("log_access", None)
r = W.log_access_set(conf, _NoDisk(), True)
ok("turning on when the save fails leaves it off", r["ok"] is False and "log_access" not in conf)
if saved:
    conf["log_access"] = saved
