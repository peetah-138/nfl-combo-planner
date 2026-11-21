# CHECK: group=static
# Static check (GitHub #189): the tests never depend on the real internet. A test that reads ESPN, Kalshi or the odds
# service for real passes or fails with the time of day (t_live_panel read ESPN's live injury report until #220).
#   1. no test calls requests/urllib/http.client/socket with a literal address that isn't this machine;
#   2. the harness keeps its safety flags (no real Tailscale, ntfy on an .invalid host) and runs every engine test
#      under the fake-network guard (netguard/sitecustomize.py);
#   3. the guard itself works: a real address is refused and named in a FAIL line, the machine's own ports still work,
#      the reserved .invalid names are refused quietly. (Nothing here reaches the network: the guard refuses first.)
# (No check name may contain the word in capitals that run_checks.sh greps for: it would count as a failure.)
import ast, glob, os, re, socket, subprocess, sys, threading
from urllib.parse import urlsplit

bad = 0
def check(name, cond, why=""):
    global bad
    print(("PASS " if cond else "FAIL ") + name + ("" if cond or not why else f": {why}"))
    bad += not cond

here = os.path.dirname(os.path.abspath(__file__))
repo = os.environ.get("REPO") or os.path.abspath(os.path.join(here, "..", ".."))
NET = {"get", "post", "put", "patch", "delete", "head", "request", "urlopen", "HTTPConnection", "HTTPSConnection",
       "create_connection", "Request"}
MODS = {"requests", "urllib", "request", "http", "client", "socket", "session", "s"}


def local(host):
    h = (host or "").lower().strip("[]")
    return h in ("", "localhost", "127.0.0.1", "::1", "0.0.0.0") or h.startswith("127.") or h.endswith((".invalid", ".test", ".example", ".localhost"))


def literal(node):
    """The leading constant text of a str / f-string argument (enough to read a URL's host), else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values and isinstance(node.values[0], ast.Constant):
        return node.values[0].value
    if isinstance(node, ast.Tuple) and node.elts:            # socket.create_connection(("host", 443))
        return literal(node.elts[0])
    return None


def host_of(text):
    if "://" in text:
        return urlsplit(text).hostname or ""
    return text.split(":")[0].split("/")[0]


def scan(path):
    try:
        tree = ast.parse(open(path).read(), path)
    except (SyntaxError, UnicodeDecodeError) as e:
        return [f"{os.path.basename(path)}: can't parse ({e})"]
    hits = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or not n.args:
            continue
        f = n.func
        name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
        base = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else \
            f.value.attr if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute) else ""
        if name not in NET or (isinstance(f, ast.Attribute) and base.lower() not in MODS):
            continue
        text = literal(n.args[0])
        if text is None or not re.match(r"^(https?://|wss?://|[a-z0-9.-]+\.[a-z]{2,}(:\d+)?$)", text, re.I):
            continue
        h = host_of(text)
        if h and not local(h):
            hits.append(f"{os.path.relpath(path, here)}:{n.lineno} {name}({text[:60]!r})")
    return hits


files = sorted(glob.glob(os.path.join(here, "*.py")) + glob.glob(os.path.join(here, "macsmoke", "*.py")))
files = [f for f in files if os.path.basename(f) != "st_hermetic.py"]
hits = [h for f in files for h in scan(f)]
check("no test calls a real (non-local) address directly (%d files)" % len(files), not hits and len(files) > 50, "; ".join(hits[:6]))
# the scanner itself: it must catch the shapes it looks for, and leave local ones alone
probe = os.path.join(os.environ.get("TMPDIR", "/tmp"), "st_hermetic_probe_%d.py" % os.getpid())
open(probe, "w").write("import requests, urllib.request, socket\nrequests.get('https://site.api.espn.com/x')\n"
                       "urllib.request.urlopen(f'https://api.elections.kalshi.com/{1}')\nsocket.create_connection(('example.com', 443))\n"
                       "requests.get('http://127.0.0.1:18766/app')\nrequests.post('http://ntfy.invalid/t')\n")
found = scan(probe); os.remove(probe)
check("the scanner catches a real address and ignores local ones", len(found) == 3, found)

rc = open(os.path.join(repo, "tests", "run_checks.sh")).read()
check("the harness turns off the real Tailscale", re.search(r"(?m)^export COMBO_NO_TAILSCALE=1\b", rc) is not None)
m = re.search(r'COMBOWATCH_NTFY="([^"]+)"', rc)
check("the harness points ntfy at a host that can't exist (.invalid)", bool(m) and (urlsplit(m.group(1)).hostname or "").endswith(".invalid"),
      m.group(1) if m else "not set")
check("every engine test runs under the fake-network guard", re.search(r'PYTHONPATH="\$NG" "\$PY" \$t\.py', rc) is not None
      and 'NG="$WORK/netguard' in rc)
smoke = open(os.path.join(here, "macsmoke", "run.py")).read()
check("the simulated Mac keeps Tailscale off too", "COMBO_NO_TAILSCALE" in smoke)

# ---- the guard works (a child Python with the guard on, as run_checks.sh starts each engine test)
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(4); port = srv.getsockname()[1]
def serve():
    for _ in range(4):
        try:
            c, _a = srv.accept(); c.recv(1024); c.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok"); c.close()
        except OSError:
            return
threading.Thread(target=serve, daemon=True).start()
CHILD = """
import socket, sys, urllib.request
out = []
def tryit(name, fn):
    try: fn(); out.append(name + "=open")
    except OSError: out.append(name + "=refused")
tryit("real", lambda: urllib.request.urlopen("https://example.com/", timeout=3))
tryit("ip", lambda: socket.create_connection(("93.184.215.14", 443), timeout=3))
tryit("invalid", lambda: urllib.request.urlopen("http://ntfy.invalid/t", timeout=3))
tryit("local", lambda: urllib.request.urlopen("http://127.0.0.1:%d/" % int(sys.argv[1]), timeout=3).read())
tryit("localhost", lambda: urllib.request.urlopen("http://localhost:%d/" % int(sys.argv[1]), timeout=3).read())
print("RESULT", " ".join(out))
"""
env = dict(os.environ, PYTHONPATH=os.path.join(here, "netguard"))
env.pop("NETGUARD_OFF", None)
r = subprocess.run([sys.executable, "-c", CHILD, str(port)], env=env, capture_output=True, text=True, timeout=60)
res = dict(x.split("=") for x in (re.search(r"RESULT (.*)", r.stdout) or [None, ""])[1].split())
fails = [l for l in r.stdout.splitlines() if l.startswith("FAIL hermetic")]
check("the guard refuses a real host and a real IP address", res.get("real") == "refused" and res.get("ip") == "refused", (res, r.stderr[-300:]))
check("...and names each one in a failing line (so run_checks.sh fails the test)", len(fails) == 2 and "example.com" in fails[0]
      and "93.184.215.14" in fails[1], fails)
check("the machine's own ports still work (the fakes and the test web apps)", res.get("local") == "open" and res.get("localhost") == "open", res)
check("an .invalid host (the harness's ntfy) is refused quietly", res.get("invalid") == "refused" and not any("invalid" in l for l in fails), fails)
srv.close()
sys.exit(1 if bad else 0)
