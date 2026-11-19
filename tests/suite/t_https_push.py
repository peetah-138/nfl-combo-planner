"""Secure address (Tailscale) and web push coverage. Nothing here touches the real Tailscale: every command line is a
fake script in a temp folder, the network is faked, and push sends are recorded instead of sent."""
import os, sys, json, tempfile, importlib.util, time

TMP = tempfile.mkdtemp()
os.environ["COMBOWATCH_HOME"] = os.path.join(TMP, "home")
os.makedirs(os.environ["COMBOWATCH_HOME"])
sys.argv = ["combo_watcher.py"]
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)

SHIPPED = (W.TS_CLI_PATHS, W.TS_CLI_PATHS_LATE, W.TS_APP_BIN, W.TS_WAIT)
LOGS = []
W.log = lambda *a: LOGS.append(" ".join(str(x) for x in a))

# ---- a fake Tailscale command line: it only works like the real one when it is started the way launchd would
FAKE = os.path.join(TMP, "fakebin")
os.makedirs(FAKE)
CLI = os.path.join(FAKE, "tailscale")
open(CLI, "w").write('#!' + sys.executable + '''
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
dev_null = os.path.samestat(os.fstat(0), os.stat(os.devnull))
if os.environ.get("TAILSCALE_BE_CLI") != "1" or not dev_null:
    print("The Tailscale GUI failed to start"); sys.exit(1)
mode = open(os.path.join(here, "mode")).read().strip()
if sys.argv[1:3] == ["status", "--json"]:
    sys.stdout.write(open(os.path.join(here, "status.json")).read()); sys.exit(0)
if sys.argv[1] == "serve":
    sys.stdout.write(open(os.path.join(here, "serve.txt")).read()); open(os.path.join(here, "served"), "w").write(" ".join(sys.argv[1:])); sys.exit(0)
sys.exit(2)
''')
os.chmod(CLI, 0o755)


def scenario(status, serve="", mode="x"):
    for n, c in (("status.json", status), ("serve.txt", serve), ("mode", mode)):
        open(os.path.join(FAKE, n), "w").write(c)
    try:
        os.remove(os.path.join(FAKE, "served"))
    except OSError:
        pass


NAME = "mac.example.ts.net."
RUNNING = json.dumps({"BackendState": "Running", "Self": {"DNSName": NAME}, "CertDomains": ["mac.example.ts.net"]})
RUNNING_NOCERT = json.dumps({"BackendState": "Running", "Self": {"DNSName": NAME}})


class Resp:
    def __init__(self, text="Combo Hub sw", code=200):
        self.content, self.ok, self.status_code = text.encode(), code == 200, code


GET = {"mode": "up"}
real_get = W.requests.get


def fake_get(url, **kw):
    m = GET["mode"]
    if m == "up":
        return Resp()
    if m == "ssl":
        raise W.requests.exceptions.SSLError("tls not ready")
    raise W.requests.exceptions.ConnectionError("refused")


W.requests.get = fake_get
W.TS_CLI_PATHS = (CLI,)
W.TS_CLI_PATHS_LATE = ()
W.TS_APP_BIN = os.path.join(TMP, "no-such-app-binary")
W.TS_WAIT, W.TS_PROBE_SLEEP = 0.3, 0.05
os.environ["PATH"] = os.path.join(TMP, "emptybin")           # shutil.which must not find the real tailscale
os.makedirs(os.environ["PATH"])


def run():
    LOGS.clear()
    conf = {}
    r = W.tailscale_https(conf, 8765)
    return r, conf.get("https") or {}, list(LOGS)


# ---- which command line gets picked
a, b, c = (os.path.join(TMP, n) for n in ("a_tailscale", "b_tailscale", "c_app"))
for f in (a, b, c):
    open(f, "w").write("x")
W.TS_CLI_PATHS, W.TS_CLI_PATHS_LATE, W.TS_APP_BIN = (a,), (b,), c
ok("cli: the wrapper in /usr/local/bin style paths comes first", W.tailscale_cli() == a)
os.remove(a)
ok("cli: then later paths", W.tailscale_cli() == b)
os.remove(b)
ok("cli: the app's raw binary is the last resort", W.tailscale_cli() == c)
os.remove(c)
ok("cli: none found gives None", W.tailscale_cli() is None)
src = open("wtest/combo_watcher.py").read()
ok("cli: shipped order prefers /usr/local/bin/tailscale, app binary last",
   SHIPPED[0][0] == "/usr/local/bin/tailscale" and SHIPPED[2].endswith("Tailscale.app/Contents/MacOS/Tailscale")
   and "/usr/local/bin/tailscale" not in SHIPPED[1])
W.TS_CLI_PATHS, W.TS_CLI_PATHS_LATE, W.TS_APP_BIN = (CLI,), (), os.path.join(TMP, "nope")

# ---- the environment the CLI is started with (the fake refuses to answer otherwise)
scenario(RUNNING)
GET["mode"] = "up"
r, h, lg = run()
ok("env: works only with TAILSCALE_BE_CLI=1 and stdin closed (fake CLI answered)", r == "https://mac.example.ts.net" and h.get("state") == "on")
ok("env: success is logged", any("https on:" in x for x in lg))
p = W.tailscale_run(CLI, ["status", "--json"], 10)
ok("env: tailscale_run passes TAILSCALE_BE_CLI and DEVNULL stdin", p.returncode == 0 and "Running" in p.stdout)
import subprocess
bad = subprocess.run([CLI, "status", "--json"], capture_output=True, text=True, stdin=subprocess.DEVNULL, env={"PATH": "/usr/bin"})
ok("env: the fake really fails without TAILSCALE_BE_CLI", bad.returncode == 1 and "GUI failed to start" in bad.stdout)

# ---- every way out says what is wrong, and logs it
W.TS_CLI_PATHS = (os.path.join(TMP, "gone"),)
r, h, lg = run()
ok("no-cli: state and log line", r is None and h.get("state") == "no-cli" and any("no Tailscale command line" in x for x in lg))
W.TS_CLI_PATHS = (CLI,)

open(os.path.join(FAKE, "status.json"), "w").write("")
r, h, lg = run()
ok("no-status: empty output is reported, not 'not signed in'", h.get("state") == "no-status" and "Couldn't read Tailscale's status" in h.get("detail", ""))
ok("no-status: logged with the exit code", any("gave nothing usable" in x for x in lg))
scenario("this is not json {")
r, h, lg = run()
ok("bad JSON: no-status with the first characters", h.get("state") == "no-status" and "this is not json" in h.get("detail", "") and any("this is not json" in x for x in lg))

scenario(json.dumps({"BackendState": "NeedsLogin", "Self": {}}))
r, h, lg = run()
ok("signed out: says NeedsLogin", h.get("state") == "signed-out" and "NeedsLogin" in h.get("detail", "") and any("isn't running" in x for x in lg))
scenario(json.dumps({"BackendState": "Running", "Self": {}}))
r, h, lg = run()
ok("no name: MagicDNS hint", h.get("state") == "no-name" and "MagicDNS" in h.get("detail", "") and any("no machine name" in x for x in lg))

LINK = "https://login.tailscale.com/f/serve?node=abc123"
scenario(RUNNING_NOCERT, f"\nServe is not enabled on your tailnet.\nTo enable, visit:\n\n         {LINK}\n")
GET["mode"] = "down"
r, h, lg = run()
ok("need-enable: the one-time link is parsed", r is None and h.get("state") == "need-enable" and h.get("link") == LINK)
ok("need-enable: serve was run with the hub port", open(os.path.join(FAKE, "served")).read().strip() == "serve --bg 8765")
ok("need-enable: logged", any("https not on yet: need-enable" in x for x in lg))

scenario(RUNNING_NOCERT, "")
r, h, lg = run()
ok("need-enable without a link: exact click path in the detail",
   h.get("state") == "need-enable" and not h.get("link") and "HTTPS certificates are not enabled in Tailscale admin" in h.get("detail", "")
   and "HTTPS Certificates" in h["detail"] and "Enable HTTPS..." in h["detail"] and "admin/dns" in h["detail"] and h.get("admin", "").endswith("/admin/dns"))

scenario(RUNNING, "")
GET["mode"] = "ssl"
r, h, lg = run()
ok("a TLS error is 'certificate still being issued', not failed", r is None and h.get("state") == "issuing" and "certificate" in h.get("detail", ""))
GET["mode"] = "down"
r, h, lg = run()
ok("nothing answering with certificates on is 'failed' and logged", h.get("state") == "failed" and any("https not on yet: failed" in x for x in lg))

# the wait for the first certificate is long enough: it succeeds on a late probe
W.TS_WAIT, W.TS_PROBE_SLEEP = 3, 0.05
n = {"c": 0}
def late(url, **kw):
    n["c"] += 1
    if n["c"] >= 8:
        return Resp()
    raise W.requests.exceptions.SSLError("not yet")
W.requests.get = late
scenario(RUNNING, "")
r, h, lg = run()
ok("late certificate: keeps probing until it is up", r == "https://mac.example.ts.net" and n["c"] >= 8)
ok("the shipped wait is about two minutes", SHIPPED[3] >= 120)
W.requests.get = fake_get
W.TS_WAIT = 0.3

# ---- it keeps retrying until it is on
seq, sleeps = [], []
states = iter(["no-status", "need-enable", "on", "on"])
cur = {}
def fake_https(conf, port):
    conf["https"] = {"state": next(states)}
    seq.append(conf["https"]["state"])
class Stop(Exception):
    pass
def fake_sleep(s):
    sleeps.append(s)
    if len(sleeps) >= 4:
        raise Stop()
W.tailscale_https = fake_https
real_sleep = W.time.sleep
W.time.sleep = fake_sleep
try:
    W.https_loop(cur, 8765)
except Stop:
    pass
W.time.sleep = real_sleep
ok("retry: looks again every 5 minutes while not on", sleeps[:2] == [W.TS_RETRY, W.TS_RETRY] and W.TS_RETRY == 300)
ok("retry: slows to a light check once on", sleeps[2:4] == [W.TS_RECHECK] * 2 and seq == ["no-status", "need-enable", "on", "on"])
W.tailscale_https = None
ok("retry: the hub starts the loop, not a one-shot", "target=https_loop, args=(conf, port)" in src and "target=tailscale_https, args=(conf, port)" not in src)

# ---- the Settings copy
ok("copy: 'isn't signed in' is no longer the answer to every failure", "'no-status':" in src and "Tailscale isn\\'t signed in on this Mac." not in src)
ok("copy: names the admin click path", "Enable HTTPS..." in src and "HTTPS Certificates" in src and "login.tailscale.com/admin/dns" in src)

# ---- web push also carries everything that goes to ntfy
SENT, POSTED = [], []
W.PUSH.send = lambda title, body, url="/app", tag=None, urgent=False: SENT.append((title, body, url, tag, urgent)) or 1
class Post:
    ok, status_code = True, 200
W.requests.post = lambda url, **kw: POSTED.append((url, kw.get("headers", {}).get("Title"))) or Post()
W.WEB_SYNC = True
W.hub_base = lambda conf: "https://mac.example.ts.net"
conf = {"topic": "tt"}
W.push(conf, "Panel: bought Lakers combo", priority="default")
ok("push: a panel/extras alert goes to ntfy and web push", len(POSTED) == 1 and len(SENT) == 1 and SENT[0][1] == "Panel: bought Lakers combo")
W.push(conf, "Panel: bought Lakers combo")
ok("push: the same alert twice in a row is web-pushed once (ntfy unchanged)", len(SENT) == 1 and len(POSTED) == 2)
W.push(conf, "pause notice", title="Pause", topic="tt-pause")
ok("push: other topics (pause button etc.) never go to web push", len(SENT) == 1)
W.push(conf, "quiet one", web=False)
ok("push: web=False stays ntfy only", len(SENT) == 1 and len(POSTED) == 4)
W.push(conf, "danger", priority="high", click="/app?x=1")
ok("push: high priority is urgent on web push and the tap opens the page", SENT[-1][4] is True and SENT[-1][2] == "/app?x=1")
W.push(conf, "recap text", title="Recap", priority="low")
ok("push: low priority is not urgent", SENT[-1][4] is False and SENT[-1][0] == "Recap")

SENT.clear(); POSTED.clear(); W._WEB_SEEN.clear()
class FakeE:
    CFG = {"notify_value": True, "notify_price": True, "notify_cash": True, "notify_news": True, "auto_sell": True}
N = W.Notifier(conf, FakeE())
real_localtime = time.localtime
time.localtime = lambda *a: time.struct_time((2026, 11, 18, 12, 0, 0, 2, 322, 0))          # midday, so the "quiet hours" don't hide anything
try:
    N.add("Fair-priced combo found", kind="value", url="/app#x")
    ok("notifier: a buy idea is sent once to web push", [s[0] for s in SENT] == ["Buy idea"] and SENT[0][3] == "idea" and SENT[0][2] == "/app#x" and len(POSTED) == 1)
    SENT.clear(); POSTED.clear()
    N.add("Cash out now! Open the planner to confirm.")
    ok("notifier: an urgent cash alert is sent once, urgent, with the shorter wording",
       len(SENT) == 1 and SENT[0][4] is True and SENT[0][1].endswith("Tap to decide.") and SENT[0][3] == "urgent" and len(POSTED) == 1)
    SENT.clear(); POSTED.clear()
    N.add("Line moved 2 points")
    n_sent = N.flush(now=time.time() + 4000)
    ok("notifier: the digest is sent once", n_sent == 1 and len(SENT) == 1 and SENT[0][3] == "digest" and len(POSTED) == 1)
finally:
    time.localtime = real_localtime
ok("no leftover direct PUSH.send threads in the notifier", src.count("target=PUSH.send") == 1)   # only web_push's own

# ---- the passcode login cookie gets Secure only on https
class H:
    def __init__(self, h): self.headers = h
ok("is_https: Tailscale's forwarding header says https", W.is_https(H({"X-Forwarded-Proto": "https"})) and not W.is_https(H({})) and not W.is_https(H({"X-Forwarded-Proto": "http"})))
ok("the passcode cookie adds Secure on https", 'if is_https(self) else ""' in src)

# ---- Pi: alerts only, nothing here can trade
ok("web push code cannot place orders", "kalshi_send" not in src[src.index("def web_push"):src.index("def sign(")])
print("done")
