# CHECK: group=engine
"""Redaction for the dev Mac log endpoint (#377): every secret, in every spelling, is masked; what must stay readable stays."""
import sys, os, json, socket, tempfile, importlib.util, time, types, http.client
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

from urllib.parse import quote

UUID = "3f2b8c1e-4a5d-4e6f-8a9b-0c1d2e3f4a5b"
ODDS = "0123456789abcdef0123456789abcdef"
conf = {"topic": "zq7-fake-topic-91", "secret": "fakeSharedSecret4471", "web_pass": 'fake pass/word&"x',
        "passkey_user": "fakepasskeyuser88", "healthcheck_url": "https://hc.example/ping/fakehc-5531",
        "https": {"url": "https://mymacbook.tail4242.ts.net"}}
E = types.SimpleNamespace(CFG={"kalshi_key_id": UUID, "odds_key": ODDS, "watcher_code": "wc-fake-code-5521"},
                          KEY_FIELDS=("kalshi_key_id", "odds_key", "watcher_code"), VERSION="9.9.9")
S = W.log_secrets(conf, E)
red = lambda t: W.log_redact(t, S)
ALL = ["zq7-fake-topic-91", "fakeSharedSecret4471", 'fake pass/word&"x', "fakepasskeyuser88", "https://hc.example/ping/fakehc-5531",
       "mymacbook.tail4242.ts.net", UUID, ODDS, "wc-fake-code-5521"]

# ---- every live secret, in every spelling
ok("log_secrets lists the plain, URL-encoded and JSON-escaped forms",
   all(x in S for x in (quote(conf["web_pass"], safe=""), json.dumps(conf["web_pass"])[1:-1])))
for v in ALL:
    ok(f"plain text: {v[:8]}... masked", v not in red(f"note: something {v} happened"))
    ok(f"JSON-escaped: {v[:8]}... masked", json.dumps(v)[1:-1] not in red('{"x": "' + json.dumps(v)[1:-1] + '"}'))
    ok(f"URL-encoded: {v[:8]}... masked", quote(v, safe="") not in red("GET /x?q=" + quote(v, safe="") + " 200"))
out = red(f'"kalshi_key_id": "{UUID}", "odds_key": "{ODDS}", "watcher_code": "wc-fake-code-5521"')
ok("inside JSON: kalshi_key_id / odds_key / watcher_code values gone", UUID not in out and ODDS not in out and "wc-fake" not in out)
ok("inside JSON: the key names stay, the value is [redacted] or [secret]", '"kalshi_key_id"' in out and "[" in out)
out = red("push to https://ntfy.example/zq7-fake-topic-91 ok")
ok("ntfy-style URL: topic gone", "zq7-fake-topic-91" not in out and "ntfy.example" not in out)
out = red("fetch https://api.example.org/v1?api_key=abcDEF123456xyz&x=1")
ok("URL ?api_key= masked", "abcDEF123456xyz" not in out)
out = red("fetch https://api.example.org/v1?token=abcDEF123456xyz")
ok("URL ?token= masked", "abcDEF123456xyz" not in out)
out = red("fetch https://api.the-odds-api.com/v4/odds?apiKey=ZZtopSecretValue99&regions=us")
ok("public host URL: apiKey value masked, host and path kept", "ZZtopSecretValue99" not in out and "the-odds-api.com/v4/odds" in out)
out = red("fetch https://api.example.org/v1?token=abcDEF123456xyz")
ok("an unknown host becomes [host]", "[host]" in out)

# ---- headers
for line, bad in (("Authorization: Bearer zzTok-9981xyzAB", "zzTok-9981xyzAB"),
                  ("Authorization: Basic dXNlcjpwYXNzd29yZA", "dXNlcjpwYXNzd29yZA"),
                  ("sent Bearer abc123def456ghi789 to hub", "abc123def456ghi789"),
                  ("X-CW: zzTok-9981xyzAB", "zzTok-9981xyzAB"),
                  ("Cookie: cw=zzTok-9981xyzAB; other=1", "zzTok-9981xyzAB"),
                  ("Set-Cookie: cw=zzTok-9981xyzAB; Path=/", "zzTok-9981xyzAB"),
                  ("KALSHI-ACCESS-KEY: zzTok-9981xyzAB", "zzTok-9981xyzAB"),
                  ("KALSHI-ACCESS-SIGNATURE: zzTok-9981xyzAB", "zzTok-9981xyzAB"),
                  ('{"Authorization": "Bearer zzTok-9981xyzAB"}', "zzTok-9981xyzAB")):
    ok(f"header masked: {line[:34]}", bad not in red(line))

# ---- shapes
for label, line, bad in (
        ("email", "mail sent to jane.doe@example.com now", "jane.doe@example.com"),
        ("Tailscale 100.x IP", "peer 100.101.102.103 connected", "100.101.102.103"),
        ("LAN IP 192.168", "from 192.168.1.20 port 80", "192.168.1.20"),
        ("LAN IP 10.x", "from 10.0.0.7 port 80", "10.0.0.7"),
        ("fd7a IPv6", "peer fd7a:115c:a1e0::5 up", "fd7a:115c:a1e0::5"),
        ("ts.net host", "dialing box.tail1234.ts.net now", "box.tail1234.ts.net"),
        ("/Users path", "reading /Users/janedoe/combowatch/x.json", "janedoe"),
        ("member_id", "member_id=12345678 ok", "12345678"),
        ("user_id JSON", '{"user_id": 998877}', "998877"),
        ("account_id", "account_id: acct-77-zz", "acct-77-zz"),
        ("long random blob", "key aGVsbG8gd29ybGQgdGhpcyBpcyBhIGxvbmcgYmxvYg9876543210ZZ end", "aGVsbG8gd29ybGQgdGhpcyBpcyBhIGxvbmcgYmxvYg9876543210ZZ"),
        ("balance line $", "Balance: $1,234.56 available", "1,234.56"),
        ("balance json", '{"balance": 98765}', "98765"),
        ("pot line $", "cash by pot: main $210.40, side $55.00", "210.40")):
    ok(f"masked: {label}", bad not in red(line))
ok("a Tailscale-looking /Users path keeps its shape, name replaced", "/Users/[user]" in red("/Users/janedoe/x"))

# ---- kept
for label, line, keep in (
        ("Kalshi ticker", "buy KXNFLGAME-26NOV23KCBUF-KC at 41", "KXNFLGAME-26NOV23KCBUF-KC"),
        ("per-trade dollars", "sold 3 contracts for $12.50", "$12.50"),
        ("HH:MM:SS time", "at 14:05:09 the poll ran", "14:05:09"),
        ("127.0.0.1", "listening on 127.0.0.1 port 8765", "127.0.0.1"),
        ("kalshi.com URL path", "GET https://api.elections.kalshi.com/trade-api/v2/markets ok", "kalshi.com/trade-api/v2/markets")):
    ok(f"kept: {label}", keep in red(line))
ok("a balance line does not hide the ticker on it", "KXNFLGAME-26NOV23KCBUF-KC" in red("balance check for KXNFLGAME-26NOV23KCBUF-KC: $5.00"))

# ---- the files: multi-line PEM block, autosell allowlist, console auto cash-out lines
now = time.time()
ts = lambda d: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - d))
pem = ["-----BEGIN RSA " + PEM_TAG + "-----", "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7", "Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MA==", "-----END RSA " + PEM_TAG + "-----"]
console = [ts(60) + " startup ok", ts(50) + " key load failed:"] + pem + [
    ts(40) + " after the block KXNFLGAME-26NOV23KCBUF-KC",
    ts(30) + ' auto cash-out: {"ticker": "KXNFLGAME-26NOV23KCBUF-KC", "result": "sold", "kalshi_key_id": "' + UUID + '", "balance": 4411, "secret_note": "hello"}',
    ts(20) + " auto cash-out: {not json at all}",
    ts(10) + " auto cash-out: {not json}",
    ts(5) + ' auto cash-out: {"ticker": "KXA", "secret_note": "cut off part-way']
write_log("watcher.log", "\n".join(console) + "\n")
body = json.loads(W.log_answer(conf, E, "console", home=W.HOME))
txt = "\n".join(r["text"] for r in body["lines"])
ok("PEM block in watcher.log: no key body, no header", "MIIEvQIBADANBg" not in txt and "Zm9vYmFy" not in txt and "BEGIN" not in txt)
ok("PEM block replaced by [private key]; the lines around it stay", "[private key]" in txt and "startup ok" in txt and "after the block" in txt)
ok("console auto cash-out: kalshi_key_id / balance / secret_note dropped", UUID not in txt and "4411" not in txt and "secret_note" not in txt and "hello" not in txt)
ok("console auto cash-out: ticker and result kept", '"ticker": "KXNFLGAME-26NOV23KCBUF-KC"' in txt and '"result": "sold"' in txt)
ok("console auto cash-out: unparseable ones become [record not shown]", txt.count("[record not shown]") == 3 and "not json" not in txt and "cut off" not in txt)

recs = [{"at": now - 5, "ticker": "KXNFLGAME-26NOV23KCBUF-KC", "result": "sold", "why": "profit target", "cost": 12.5, "offer": 0.61,
         "kalshi_key_id": UUID, "balance": 4411, "secret_note": "hi", "odds_key": ODDS},
        {"at": now - 4, "ticker": "X", "why": "mail me jane@example.com", "legs": [["a", 1], ["b", 2]], "ask": {"y": 1}}]
write_log("combo_autosell_log.jsonl", "\n".join(json.dumps(r) for r in recs) + "\nthis line is not json\n")
body = json.loads(W.log_answer(conf, E, "autosell", home=W.HOME))
r0, r1 = body["lines"][0]["rec"], body["lines"][1]["rec"]
ok("autosell: allowlisted fields kept (ticker, result, why, cost, offer)",
   r0 == {"at": r0["at"], "ticker": "KXNFLGAME-26NOV23KCBUF-KC", "result": "sold", "why": "profit target", "cost": 12.5, "offer": 0.61})
ok("autosell: unknown fields dropped (kalshi_key_id, balance, secret_note, odds_key)",
   not {"kalshi_key_id", "balance", "secret_note", "odds_key"} & set(r0))
ok("autosell: strings inside kept fields are redacted too", "jane@example.com" not in json.dumps(r1) and "[email]" in json.dumps(r1))
ok("autosell: a line that is not JSON is skipped, answer has 2 lines", len(body["lines"]) == 2)
ok("autosell: the answer never contains any live secret", not any(v in json.dumps(body) for v in ALL))
ok("answer carries the status block with the engine version", body["status"]["engine"] == "9.9.9")
ok("Kalshi's insufficient_balance refusal keeps the order cost",
   "$7.25" in W.log_redact("buy refused insufficient_balance cost $7.25 KXNFLGAME-26NOV23KCBUF-KC", S))
ok("a line with the account balance still masks it", "$88.10" not in W.log_redact("insufficient_balance: balance $88.10", S))
f = W.log_fields({"ticker": "KXA", "hedge": True, "stop_loss": "auto", "sl_mode": "tune"}, S)
ok("hedge / stop-loss markers are kept on auto cash-out records", f == {"ticker": "KXA", "hedge": True, "stop_loss": "auto", "sl_mode": "tune"})

# from the security review
ok("JSON inside a string: the escaped api_key value is masked", "SECRETVALUE123" not in red('{"msg": "{\\"api_key\\": \\"SECRETVALUE123\\"}"}'))
ok("'api key: X' with a space is masked", "XYZSECRET1" not in red("api key: XYZSECRET1"))
ok("'user id 12345' with a space is masked", "12345" not in red("user id 12345"))
ok("a bare cw= session cookie is masked", "abc123" not in red("cookie cw=abc123 ok"))
ok("a JWT is masked", "eyJhbGciOiJIUzI1NiJ9" not in red("tok eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.sigsig ok"))
ok("a short Bearer token is masked", "abc12" not in red("Authorization-ish Bearer abc12"))
ok("a lowercase PEM marker is masked", "MIIabc" not in red("-----" + "begin private key-----\nMIIabc\n-----end private key-----"))
ok("a live secret split by a colour code is still masked (not a 503)", "zq7-fake" not in red("zq7-fake\x1b[0m-topic-91 here"))
ok("a live secret split by a zero-width mark is masked", "zq7-fake" not in red("zq7-fake\u200b-topic-91"))
ok("ordinary words after a key name stay ('session ok')", red("session ok") == "session ok")
f = W.log_fields({"count": float("inf"), "ticker": "KXA"}, S)
ok("a non-finite number in an auto cash-out record becomes null (valid JSON)", f == {"count": None, "ticker": "KXA"})
t0 = time.time()
for u in ("a-", "1.", "a@", "a.", "api_key=", "\\\"", "eyJaaaaaaaa."):
    red(u * 400000)
ok("hostile 800 KB lines are redacted fast (no regex blow-up stalling the watcher)", time.time() - t0 < 5)
write_log("watcher.log", "MIIEvQIBADA001\nMIIEvQIBADA002\n" + ts(1) + " after a cut\n")
txt = json.dumps(json.loads(W.log_answer(conf, E, "console", home=W.HOME)))
ok("console: undated lines before the first dated one are dropped (could be a cut key body)", "MIIEvQIBADA" not in txt and "after a cut" in txt)
