# CHECK: group=engine
# The transition (GitHub #124): a Mac on 2026.11.21.126 updates to the split release with its OWN, old updater
# (fixtures/updater_126.py.txt, verbatim from origin/main), which installs only the engine and watcher files and
# never watcher/spa/. This proves, against a fake GitHub, that:
#   1. the old updater installs the new release (the new watcher passes its checks),
#   2. the first start of the new watcher, with no spa folder and GitHub unreachable, imports, serves the real app
#      from its built-in copy (never a blank page or a crash), and starts the repair,
#   3. once GitHub answers, the repair fetches and checks the spa folder, asks for a restart, and the next start
#      serves the same app from the folder,
#   4. a Pi on approved updates gets through the same way once the phone approves the web app's files.
import hashlib, importlib.util, json, os, re, subprocess, sys, tempfile, time, types
import requests
ok = lambda n, c, *a: print(("PASS " if c else "FAIL ") + n, *(a if not c else ()))
SRC = os.path.abspath("wtest")
REPO = os.environ.get("REPO") or os.path.dirname(os.path.dirname(SRC))
SHA = "0123456789abcdef0123456789abcdef01234567"
OLD = re.search(r'^WATCHER_VERSION = "([^"]+)"', open(os.path.join(SRC, "combo_watcher.py")).read(), re.M).group(1)
NEW = OLD + "9"
WSRC = open(os.path.join(SRC, "combo_watcher.py")).read().replace(f'WATCHER_VERSION = "{OLD}"', f'WATCHER_VERSION = "{NEW}"').encode()
ESRC = open(os.path.join(REPO, "nfl_combo_planner.py")).read().replace(f'VERSION = "{OLD}"', f'VERSION = "{NEW}"').encode()
SPA_FILES = {n: open(os.path.join(SRC, "spa", n), "rb").read() for n in os.listdir(os.path.join(SRC, "spa"))}
LOG = []
NET = {"up": True}


class R:
    def __init__(s, body=None, code=200, raw=None):
        s._o, s.status_code, s.ok = body, code, code < 400
        s.content = raw if raw is not None else json.dumps(body).encode()
        s.text = s.content.decode("utf-8", "replace")

    def json(s):
        return s._o


def blob(b):
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def get(url, params=None, **k):
    if not NET["up"]:
        raise requests.ConnectionError("GitHub unreachable (test)")
    if "/commits/main" in url:
        return R(raw=SHA.encode())
    if url.endswith("/contents/watcher/spa"):
        return R([{"name": n, "type": "file", "sha": blob(b)} for n, b in SPA_FILES.items()]) if (params or {}).get("ref") == SHA else R({}, 404)
    if url.endswith("version.txt"):
        return R(raw=NEW.encode())
    if url.endswith("nfl_combo_planner.py"):
        return R(raw=ESRC)
    if url.endswith("watcher/combo_watcher.py"):
        return R(raw=WSRC)
    if "/watcher/spa/" in url and f"/{SHA}/" in url:
        n = url.split("/watcher/spa/")[1]
        return R(raw=SPA_FILES[n]) if n in SPA_FILES else R({}, 404)
    return R({}, 404)


FAKE = types.SimpleNamespace(get=get, RequestException=requests.RequestException, ConnectionError=requests.ConnectionError)


def old_mac(conf):
    """A home laid out as on a Mac running 126: engine, watcher, settings, no spa folder."""
    h = tempfile.mkdtemp(prefix="mac126")
    open(os.path.join(h, "engine.py"), "w").write(open(os.path.join(REPO, "nfl_combo_planner.py")).read())
    open(os.path.join(h, "combo_watcher.py"), "w").write("# the 126 watcher (stand-in: only its updater runs here)\n")
    json.dump(conf, open(os.path.join(h, "watcher.json"), "w"))
    return h


def run_old_updater(h, conf):
    """The 126 updater, exactly as shipped, run as if from h/combo_watcher.py."""
    ns = {"requests": FAKE, "re": re, "time": time, "hashlib": hashlib, "os": os, "sys": sys,
          "log": lambda *a: LOG.append(" ".join(str(x) for x in a)), "ENGINE": os.path.join(h, "engine.py"),
          "REPO": "https://raw.githubusercontent.com/peetah-138/nfl-combo-planner/main/", "LATEST_SEEN": {},
          "__file__": os.path.join(h, "combo_watcher.py"), "__name__": "updater_126"}
    exec(compile(open("fixtures/updater_126.py.txt").read(), "updater_126", "exec"), ns)
    return ns["update_if_newer"](types.SimpleNamespace(VERSION=OLD), conf)


def first_start(h):
    """Import the watcher now in h, as launchd starts it after the update (its import-time log captured)."""
    os.environ["COMBOWATCH_HOME"] = h
    sys.argv = [os.path.join(h, "combo_watcher.py")]
    spec = importlib.util.spec_from_file_location("Wt%d" % len(LOG), os.path.join(h, "combo_watcher.py"))
    W = importlib.util.module_from_spec(spec)
    import builtins
    real = builtins.print
    builtins.print = lambda *a, **k: LOG.append(" ".join(str(x) for x in a))
    try:
        spec.loader.exec_module(W)
    finally:
        builtins.print = real
    W.log = lambda *a: LOG.append(" ".join(str(x) for x in a))
    W.requests = FAKE
    return W


def parses(page):
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write("\n".join(re.findall(r"<script>(.*?)</script>", page, re.S)))
    f.close()
    return subprocess.run(["node", "--check", f.name], capture_output=True).returncode == 0


class Stop(Exception):
    pass


ASSEMBLED = None
for kind, conf in (("Mac (automatic updates)", {"auto_update": True}),):
    h = old_mac(conf)
    NET["up"] = True
    r = run_old_updater(h, dict(conf))
    ok(f"{kind}: the 126 updater installs the split release (the new watcher passes its checks)", r is True, LOG[-3:])
    ok(f"{kind}: ...and, as expected, brings no spa folder",
       f'WATCHER_VERSION = "{NEW}"' in open(os.path.join(h, "combo_watcher.py")).read() and not os.path.exists(os.path.join(h, "spa")))

    NET["up"] = False                                   # the worst case: GitHub unreachable at the first start
    n0 = len(LOG)
    W = first_start(h)
    ok(f"{kind}: first start with no spa folder and no GitHub: the watcher imports", callable(W.main) and bool(W.SPA_PROBLEM))
    ok(f"{kind}: ...and serves the real app from its built-in copy (not blank, not the holding page)",
       W.SPA != W.SPA_FALLBACK and W.SPA.startswith("<!doctype html>") and "__CWTOK__" in W.SPA and len(W.SPA) > 300000
       and "__MSG__" in W.LOGIN_HTML and (W.SPA, W.LOGIN_HTML) == W.spa_legacy())
    ok(f"{kind}: ...whose scripts parse (node --check)", parses(W.SPA) and parses(W.LOGIN_HTML))
    ok(f"{kind}: ...and says so in the log", any("built-in copy" in x for x in LOG[n0:]), LOG[n0:])
    seen = []
    W.spa_repair_start = lambda *a: seen.append(a)
    W.load_engine = lambda: (_ for _ in ()).throw(Stop())
    try:
        W.main()
    except Stop:
        pass
    ok(f"{kind}: main() starts the repair before anything else", bool(seen))
    W.time = types.SimpleNamespace(time=time.time, sleep=lambda s: (_ for _ in ()).throw(Stop()))
    W.UPDATED.clear()
    try:
        W.spa_repair_loop(dict(conf))
    except Stop:
        pass
    ok(f"{kind}: with GitHub down the repair just waits (no crash, nothing written, no restart)",
       not os.path.exists(os.path.join(h, "spa")) and not W.UPDATED.get("now")
       and not [x for x in os.listdir(h) if x.startswith(".spa-new-")])

    NET["up"] = True                                    # GitHub answers again
    W.time = types.SimpleNamespace(time=time.time, sleep=lambda s: None)
    W.spa_repair_loop(dict(conf))
    ok(f"{kind}: once GitHub answers, the repair installs the checked spa folder and asks for a restart",
       W.UPDATED.get("now") is True and W.spa_stamp(os.path.join(h, "spa")) == NEW
       and sorted(n for n in os.listdir(os.path.join(h, "spa")) if n != ".version") == sorted(SPA_FILES))
    W2 = first_start(h)
    ASSEMBLED = (W2.SPA, W2.LOGIN_HTML)
    ok(f"{kind}: the restarted watcher serves from the folder, no problem, not stale", not W2.SPA_PROBLEM and not W2.SPA_STALE)
    ok(f"{kind}: the folder's app is byte-identical to the one in the repo", ASSEMBLED == W2.spa_assemble(os.path.join(SRC, "spa")))

# 4) a Pi on phone-approved updates (automatic updates off)
h = old_mac({"auto_update": False})
NET["up"] = True
approve = {"version": NEW, "engine": hashlib.sha256(ESRC).hexdigest(), "watcher": hashlib.sha256(WSRC).hexdigest()}
ok("Pi: the 126 updater installs the approved split release", run_old_updater(h, {"auto_update": False, "approve": approve}) is True)
W = first_start(h)
ok("Pi: first start serves the built-in copy", (W.SPA, W.LOGIN_HTML) == W.spa_legacy())
ok("Pi: without the phone's approval of the web app files, the repair waits (installs nothing)",
   W.spa_repair({"auto_update": False, "approve": approve}) is False and not os.path.exists(os.path.join(h, "spa")))
digest = hashlib.sha256((W.spa_assemble(os.path.join(SRC, "spa"))[0] + "\0" + W.spa_assemble(os.path.join(SRC, "spa"))[1]).encode()).hexdigest()
W.WATCHER_VERSION = NEW
ok("Pi: with the phone's approval (a phone on the new release sends it), the repair installs the folder",
   W.spa_repair({"auto_update": False, "approve": dict(approve, spa=digest)}) is True and os.path.isdir(os.path.join(h, "spa")))
