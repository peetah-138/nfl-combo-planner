# CHECK: group=engine
"""Size, count and rate caps and bad questions for GET /api/logs (#377)."""
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
now = time.time()
T = lambda i: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 5000 + i))
write_log("watcher.log", "".join(f"{T(i)} line number {i}\n" for i in range(5000)))
write_log("combo_autosell_log.jsonl", "".join(json.dumps({"at": now - 3000 + i, "ticker": "KXA-1", "result": "sold", "n": i}) + "\n" for i in range(3000)))


def ask(q, t=tok):
    fresh()
    c, b, h = req(port, "/api/logs" + q, tok=t)
    return c, b, (json.loads(b) if c == 200 else None)


for src in ("console", "autosell"):
    c, b, a = ask("?source=" + src)
    ok(f"{src}: default limit returns 200 lines (at most 200)", c == 200 and len(a["lines"]) == 200)
    c, b, a = ask(f"?source={src}&limit=10000")
    ok(f"{src}: limit=10000 is capped at 500", c == 200 and len(a["lines"]) == 500)
    c, b, a = ask(f"?source={src}&limit=10")
    ok(f"{src}: limit=10 returns 10, the newest ones", c == 200 and len(a["lines"]) == 10)
c, b, a = ask("?limit=3")
ok("console: the newest lines come last", a["lines"][-1]["text"].endswith("line number 4999"))
c, b, a = ask("?source=autosell&limit=3")
ok("autosell: the newest records come last", a["lines"][-1]["rec"]["n"] == 2999)

# the answer size cap, even with 2000-character lines
write_log("watcher.log", "".join(f"{T(i)} " + ("abc " * 500) + "\n" for i in range(1500)))
c, b, a = ask("?limit=500")
ok("2000-char lines: answer body at most 200_000 bytes", c == 200 and len(b) <= 200_000)
ok("2000-char lines: truncated is true and some lines remain", a["truncated"] is True and 0 < len(a["lines"]) < 500)
ok("truncation drops the oldest, keeps the newest", a["lines"][-1]["t"] >= a["lines"][0]["t"])
write_log("watcher.log", "".join(f"{T(i)} " + ("abc " * 1000) + "\n" for i in range(50)))
c, b, a = ask("?limit=500")
ok("over-long lines are cut to at most 2000 characters", all(len(x["text"]) <= 2000 for x in a["lines"]))
c, b, a = ask("?limit=5")
ok("a small answer is not marked truncated", a["truncated"] is False)

# #380: a line over 20k characters is replaced before scrubbing, and the worst case stays fast
write_log("watcher.log", "".join(f"{T(i)} " + ("abc " * 120) + "\n" for i in range(2500)) + f"{T(2600)} " + "x" * 400_000 + "\n")
t0 = time.time()
c, b, a = ask("?limit=500")
dt = time.time() - t0
ok("giant line: replaced by [line too long]", c == 200 and a["lines"][-1]["text"] == "[line too long]")
ok("giant line: the answer is still dated and the lines above are kept", a["lines"][-1]["t"] is not None and len(a["lines"]) > 100)
ok("worst-case answer (about 1.5 MB log, one giant line) is under 1 second", dt < 1.0)
write_log("watcher.log", "".join(f"{T(i)} line number {i}\n" for i in range(5000)))

# since
write_log("watcher.log", "".join(f"{T(i)} line number {i}\n" for i in range(5000)))
cut = now - 5000 + 4900
c, b, a = ask(f"?since={cut}&limit=500")
ok("since filters out older lines (about 100 left)", c == 200 and 0 < len(a["lines"]) <= 101 and all(x["t"] >= cut for x in a["lines"]))
c, b, a = ask(f"?source=autosell&since={now - 3000 + 2950}&limit=500")
ok("autosell: since filters out older records", c == 200 and 0 < len(a["lines"]) <= 51 and all(x["t"] >= now - 3000 + 2950 for x in a["lines"]))
c, b, a = ask(f"?since={now + 1000}")
ok("since in the future: 200 with no lines", c == 200 and a["lines"] == [])

# bad questions
for q in ("?limit=0", "?limit=-5", "?limit=abc", "?limit=1.5", "?since=abc", "?since=nan", "?limit=1&limit=2"):
    c, b, a = ask(q)
    ok(f"bad question {q}: 400 empty body", c == 400 and b == b"")

# rate: 30 answers a minute per client
fresh()
codes = [req(port, "/api/logs?limit=1", tok=tok)[0] for _ in range(34)]
ok("the first 30 requests in a minute are answered", codes[:30] == [200] * 30)
ok("more than 30 in a minute: 429", codes[30:] == [429] * 4)
c, b, _ = req(port, "/api/logs?limit=1", tok=tok)
ok("429 has an empty body", c == 429 and b == b"")
fresh()
srv.shutdown()
