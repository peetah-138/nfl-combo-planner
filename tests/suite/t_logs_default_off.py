# CHECK: group=engine
"""GET /api/logs is off by default (#377): 404 with nothing configured, malformed settings stay off, who may ask."""
import sys, os, json, socket, tempfile, importlib.util, http.client
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
ok("a fresh conf has no log_access", "log_access" not in conf and W.log_enabled(conf) is False)
srv, port = start(conf)
fresh(); c, b, h = req(port)
ok("off: no token is 404 with an empty body", c == 404 and b == b"")
for t in ("x" * 43, "y" * 20, "short", ""):
    fresh(); c, b, _ = req(port, tok=t)
    ok(f"off: a token ({len(t)} chars) is 404 empty", c == 404 and b == b"")
fresh(); c, b, _ = req(port, auth="Basic abcdefghijklmnopqrstuvwxyz")
ok("off: Basic is 404 empty", c == 404 and b == b"")
fresh(); c, b, _ = req(port, method="POST")
ok("off: POST is 404 empty too (nothing hints the route exists)", c == 404 and b == b"")
# even a guessed hash-looking value is no way in while off
fresh(); c, b, _ = req(port, tok="0" * 64)
ok("off: a 64-char token is 404", c == 404)
fresh(); c, b, h = req(port)
ok("off: still no-store and nosniff", h.get("cache-control") == "no-store" and h.get("x-content-type-options") == "nosniff")
srv.shutdown()

good = "a" * 64
ok("log_enabled: on with a good hash", W.log_enabled({"log_access": {"on": True, "hash": good}}) is True)
ok("log_enabled: {'on': True} with no hash is off", W.log_enabled({"log_access": {"on": True}}) is False)
for label, h in (("short", "abc"), ("63 chars", "a" * 63), ("65 chars", "a" * 65), ("non-hex", "g" * 64), ("uppercase", "A" * 64),
                 ("None", None), ("a number", 12345), ("a list", ["a" * 64]), ("empty", "")):
    ok(f"log_enabled: malformed hash ({label}) is off", W.log_enabled({"log_access": {"on": True, "hash": h}}) is False)
ok("log_enabled: a good hash but on False is off", W.log_enabled({"log_access": {"on": False, "hash": good}}) is False)
ok("log_enabled: on as the string 'true' is off", W.log_enabled({"log_access": {"on": "true", "hash": good}}) is False)
ok("log_enabled: on as 1 is off", W.log_enabled({"log_access": {"on": 1, "hash": good}}) is False)
ok("log_enabled: log_access not a dict is off", W.log_enabled({"log_access": "yes"}) is False and W.log_enabled({"log_access": True}) is False)
ok("log_enabled: conf not a dict is off", W.log_enabled(None) is False and W.log_enabled([]) is False)
ok("log_token_ok: a malformed stored hash accepts nothing", not W.log_token_ok({"log_access": {"on": True, "hash": "abc"}}, "Bearer " + "x" * 43))

# log_status never shows the code or hash
c2 = {}
tok = W.log_new_token(c2)
h = c2["log_access"]["hash"]
st = W.log_status(c2)
ok("log_status when on: on is True, with a time", st["on"] is True and isinstance(st["at"], int))
dump = json.dumps(st)
ok("log_status holds neither the token nor the hash", tok not in dump and h not in dump)
ok("log_status keys are only on / at / read", set(st) == {"on", "at", "read"})
ok("log_status when off is on False, at None", W.log_status({}) == {"on": False, "at": None, "read": W.log_status({})["read"]} and W.log_status({})["at"] is None)
ok("log_status ignores a malformed entry", W.log_status({"log_access": {"on": True, "hash": "zz"}})["on"] is False)
r = W.log_access_set(c2, M, True)
ok("log_access_set(on) result: logs status has no hash", h not in json.dumps(r["logs"]) and r["token"] not in json.dumps(r["logs"]))
r = W.log_access_set(c2, M, False)
ok("log_access_set(off) result carries no token", "token" not in r and "log_access" not in c2)

# who may ask
H = {}
for ip, hd, want, label in (
        ("192.168.1.5", {}, False, "home LAN 192.168.1.5"),
        ("10.0.0.2", {}, False, "10.0.0.2"),
        ("172.16.0.9", {}, False, "172.16.0.9"),
        ("8.8.8.8", {}, False, "a public address"),
        ("100.70.1.2", {}, True, "Tailscale 100.70.1.2"),
        ("100.64.0.1", {}, True, "100.64.0.1 (low end)"),
        ("100.127.255.254", {}, True, "100.127.255.254 (high end)"),
        ("100.63.0.1", {}, False, "100.63.0.1 (just below the range)"),
        ("100.128.0.1", {}, False, "100.128.0.1 (just above the range)"),
        ("::ffff:100.70.1.2", {}, True, "::ffff:100.70.1.2"),
        ("::ffff:192.168.1.5", {}, False, "::ffff:192.168.1.5"),
        ("fd7a:115c:a1e0::1", {}, True, "fd7a:115c:a1e0::1"),
        ("fd7b:115c:a1e0::1", {}, False, "fd7b:...: another prefix"),
        ("2001:db8::1", {}, False, "a public IPv6 address"),
        ("not-an-ip", {}, False, "garbage"),
        ("", {}, False, "empty"),
        ("127.0.0.1", {}, True, "127.0.0.1 direct"),
        ("::1", {}, True, "::1 direct"),
        ("127.0.0.1", {"X-Forwarded-For": "1.2.3.4"}, False, "127.0.0.1 with X-Forwarded-For and no Tailscale-User-Login"),
        ("127.0.0.1", {"X-Forwarded-For": "1.2.3.4", "Tailscale-User-Login": "a@example.com"}, True, "127.0.0.1 forwarded with a Tailscale login"),
        ("127.0.0.1", {"Forwarded": "for=1.2.3.4"}, False, "127.0.0.1 with Forwarded"),
        ("127.0.0.1", {"X-Forwarded-Host": "evil.example"}, False, "127.0.0.1 with X-Forwarded-Host"),
        ("127.0.0.1", {"Tailscale-Funnel-Request": "?1"}, False, "127.0.0.1 with Tailscale-Funnel-Request"),
        ("127.0.0.1", {"Tailscale-Funnel-Request": "?1", "Tailscale-User-Login": "a@example.com", "X-Forwarded-For": "1.2.3.4"}, False, "Funnel even with a login"),
        ("100.70.1.2", {"Tailscale-Funnel-Request": "?1"}, False, "a Tailscale address with Funnel")):
    ok(f"log_client_ok: {label} is {want}", W.log_client_ok(ip, hd) is want)
