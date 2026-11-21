# CHECK: group=engine
"""Tests can never touch the real Tailscale (issue #54): a test run once ran the real `tailscale serve`, re-pointing
Pete's real secure address at a fake hub. A SHIM `tailscale` records every call it gets; nothing here reaches the real
one (its paths are replaced), and the shim is the only command line this process can find."""
import os, sys, tempfile, importlib.util, threading

TMP = tempfile.mkdtemp()
os.environ["COMBOWATCH_HOME"] = os.path.join(TMP, "home")           # a test home, as every harness uses
os.makedirs(os.environ["COMBOWATCH_HOME"])
os.environ.pop("COMBO_NO_TAILSCALE", None)                           # worst case: the harness forgot the flag
sys.argv = ["combo_watcher.py"]
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
LOGS = []
W.log = lambda *a: LOGS.append(" ".join(str(x) for x in a))

BIN = os.path.join(TMP, "shimbin")
os.makedirs(BIN)
CALLS = os.path.join(TMP, "calls.txt")
SHIM = os.path.join(BIN, "tailscale")
open(SHIM, "w").write('#!' + sys.executable + '''
import os, sys
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "calls.txt"), "a").write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:3] == ["status", "--json"]:
    print('{"BackendState": "Running", "Self": {"DNSName": "mac.example.ts.net."}, "CertDomains": ["mac.example.ts.net"]}')
''')
os.chmod(SHIM, 0o755)
W.TS_CLI_PATHS, W.TS_CLI_PATHS_LATE = (SHIM,), ()                    # the real command lines are out of reach
W.TS_APP_BIN = os.path.join(TMP, "no-such-app")
os.environ["PATH"] = BIN + ":" + os.environ.get("PATH", "")          # and the shim is first on PATH
W.TS_WAIT, W.TS_PROBE_SLEEP = 0.2, 0.05


class Resp:
    content, ok, status_code = b"nope", False, 404


W.requests.get = lambda *a, **k: Resp()


def calls():
    try:
        return [x for x in open(CALLS).read().splitlines() if x]
    except OSError:
        return []


def reached(words=("serve", "funnel", "cert")):
    return [c for c in calls() if c.split()[0] in words]


def refuses(fn):
    try:
        fn()
        return False
    except OSError:
        return True


# 1. the exact old failure: the secure-address check in a test home, no flag set, a port like the simulated Mac's
conf = {}
W.tailscale_https(conf, 8797)
ok("a test home never reaches `tailscale serve`", not reached() and not calls())
ok("it says why instead (state off-in-tests)", (conf.get("https") or {}).get("state") == "off-in-tests")

# 2. the loop returns at once instead of retrying
t = threading.Thread(target=W.https_loop, args=({}, 8797), daemon=True)
t.start()
t.join(3)
ok("https_loop returns at once in a test home", not t.is_alive() and not calls())

# 3. the hard net in tailscale_run: every subcommand is refused, state-changing or not
for args in (["serve", "--bg", "8797"], ["funnel", "8797"], ["cert", "x"], ["status", "--json"], ["serve", "reset"]):
    ok(f"tailscale_run refuses `{args[0]}` in a test home", refuses(lambda: W.tailscale_run(SHIM, args, 5)))
ok("the shim never heard from any of it", not calls())

# 4. the flag alone blocks even a real-looking home
os.environ["COMBO_NO_TAILSCALE"] = "1"
W.HOME = os.path.expanduser("~/combowatch")
ok("COMBO_NO_TAILSCALE=1 blocks even the real home", bool(W.tailscale_blocked()))
ok("and tailscale_run refuses with only the flag", refuses(lambda: W.tailscale_run(SHIM, ["serve", "--bg", "8797"], 5)) and not calls())

# 5. the fake-CLI switch (used by the secure-address test) admits only scripts in a temp folder, never a real path
W.TS_FAKE_OK = True
ok("the fake-CLI switch still refuses a real path", refuses(lambda: W.tailscale_run("/usr/local/bin/tailscale", ["serve", "--bg", "1"], 5)))
W.TS_FAKE_OK = False

# 6. the real watcher is unchanged: its real home and no flag -> allowed, and the command line runs (the shim here)
os.environ.pop("COMBO_NO_TAILSCALE")
ok("a real install home (~/combowatch) is not blocked", W.tailscale_blocked() == "")
W.HOME = "/var/lib/combowatch"
ok("the Pi's home is not blocked either", W.tailscale_blocked() == "")
W.HOME = os.path.expanduser("~/combowatch")
p = W.tailscale_run(SHIM, ["status", "--json"], 10)
ok("in a real home the command line still runs", p.returncode == 0 and calls() == ["status --json"])
conf = {}
W.tailscale_https(conf, 8797)
ok("and the secure address check still asks for `serve` there (shim only)", any(c.startswith("serve") for c in calls()))
