# The update path with the web app in its own files (GitHub #124), end to end through the real update_if_newer and
# spa_repair against a fake GitHub (commit API, file list with git's own hashes, raw files). A copy of the watcher
# runs from a throwaway home; nothing here touches ~/combowatch or the repo. Cases: a normal update (new engine,
# watcher and web app swapped in, nothing left over), a file missing on GitHub, a file arriving changed or cut
# short, a manifest naming a file GitHub doesn't have, a script that doesn't parse, a shell without its
# placeholder, no exact commit, a failed install (web app put back), the phone-approved path, the first update
# from a version without a spa folder, and the repair after an older updater installed the watcher alone.
import hashlib, importlib.util, json, os, shutil, sys, tempfile, types
import requests
ok = lambda n, c, *a: print(("PASS " if c else "FAIL ") + n, *(a if not c else ()))
SRC = os.path.abspath("wtest")
REPO = os.environ.get("REPO") or os.path.dirname(os.path.dirname(SRC))
SHA = "0123456789abcdef0123456789abcdef01234567"
OLD = open(os.path.join(SRC, "combo_watcher.py")).read().split('WATCHER_VERSION = "')[1].split('"')[0]
NEW = OLD + "9"
ENGINE_SRC = open(os.path.join(REPO, "nfl_combo_planner.py")).read()
LOG = []


def home():
    """A fresh throwaway home with the current watcher, engine and web app files, and the watcher imported from it."""
    h = tempfile.mkdtemp(prefix="spaupd")
    os.environ["COMBOWATCH_HOME"] = h
    shutil.copy(os.path.join(SRC, "combo_watcher.py"), h)
    shutil.copytree(os.path.join(SRC, "spa"), os.path.join(h, "spa"))
    open(os.path.join(h, "engine.py"), "w").write(ENGINE_SRC)
    sys.argv = [os.path.join(h, "combo_watcher.py")]
    spec = importlib.util.spec_from_file_location("W", os.path.join(h, "combo_watcher.py"))
    W = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(W)
    W.log = lambda *a: LOG.append(" ".join(str(x) for x in a))
    return h, W


def snapshot(h):
    out = {}
    for root, _, files in os.walk(h):
        for f in files:
            if "__pycache__" not in root and f != ".spa.lock":
                p = os.path.join(root, f)
                out[os.path.relpath(p, h)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


class R:
    def __init__(s, body=None, code=200, raw=None):
        s._o, s.status_code, s.ok = body, code, code < 400
        s.content = raw if raw is not None else json.dumps(body).encode()
        s.text = s.content.decode("utf-8", "replace")

    def json(s):
        return s._o


def github(W, spa, watcher=None, listing=None, serve=None, sha=SHA):
    """Patch W's requests with a fake GitHub serving version NEW at commit sha (or no commit when sha is "")."""
    watcher = watcher if watcher is not None else open(os.path.join(SRC, "combo_watcher.py")).read().replace(
        f'WATCHER_VERSION = "{OLD}"', f'WATCHER_VERSION = "{NEW}"').encode()
    engine = ENGINE_SRC.replace(f'VERSION = "{OLD}"', f'VERSION = "{NEW}"').encode()
    listing = listing if listing is not None else {n: W.git_blob_sha(b) for n, b in spa.items()}
    serve = serve if serve is not None else spa

    def get(url, params=None, **k):
        if "/commits/main" in url:
            return R(raw=sha.encode()) if sha else R(code=503, raw=b"")
        if url.endswith("/contents/watcher/spa"):
            if (params or {}).get("ref") != SHA:
                return R({}, 404)
            return R([{"name": n, "type": "file", "sha": s} for n, s in listing.items()] + [{"name": "x", "type": "dir", "sha": "0"}])
        pinned = f"/{SHA}/" in url
        if url.endswith("version.txt"):
            return R(raw=NEW.encode())
        if url.endswith("nfl_combo_planner.py"):
            return R(raw=engine)
        if url.endswith("watcher/combo_watcher.py"):
            return R(raw=watcher)
        if "/watcher/spa/" in url and pinned:
            n = url.split("/watcher/spa/")[1]
            return R(raw=serve[n]) if n in serve else R({}, 404)
        return R({}, 404)
    W.requests = types.SimpleNamespace(get=get, RequestException=requests.RequestException)


def spa_files(extra_css=b"/* the new version */\n"):
    d = os.path.join(SRC, "spa")
    s = {n: open(os.path.join(d, n), "rb").read() for n in os.listdir(d)}
    s["app.css"] += extra_css
    return s


def digest_of(W, files):
    """The spa_digest these files assemble into (what the phone approves)."""
    d = tempfile.mkdtemp(prefix="spadig")
    for n, b in files.items():
        open(os.path.join(d, n), "wb").write(b)
    return W.spa_digest(*W.spa_assemble(d))


E = types.SimpleNamespace(VERSION=OLD)
AUTO = {"auto_update": True}


def unchanged_case(name, **kw):
    h, W = home()
    before = snapshot(h)
    github(W, kw.pop("spa", None) or spa_files(), **kw)
    n0 = len(LOG)
    r = W.update_if_newer(E, dict(AUTO))
    after = snapshot(h)
    left = [n for n in os.listdir(h) if n.startswith(".spa-new-") or n == "spa.old"]
    ok(f"{name}: nothing is installed, every file in the home is exactly as it was, nothing left over",
       r is False and before == after and not left, r, set(before.items()) ^ set(after.items()), left)
    ok(f"{name}: the log says why and that this version keeps running", any(("skipped" in x or "waiting" in x) for x in LOG[n0:]), LOG[n0:])
    return W


# 1) a normal update: new engine, watcher and web app, all at the one commit
h, W = home()
new = spa_files()
github(W, new)
r = W.update_if_newer(E, dict(AUTO))
ok("normal update: installed and asks for a restart", r is True, LOG[-3:])
ok("normal update: engine and watcher are the new version",
   f'VERSION = "{NEW}"' in open(os.path.join(h, "engine.py")).read() and f'WATCHER_VERSION = "{NEW}"' in open(os.path.join(h, "combo_watcher.py")).read())
ok("normal update: the web app's files are the new ones", all(open(os.path.join(h, "spa", n), "rb").read() == b for n, b in new.items())
   and sorted(n for n in os.listdir(os.path.join(h, "spa")) if n != ".version") == sorted(new))
ok("normal update: they assemble into the new page", "/* the new version */" in W.spa_assemble(os.path.join(h, "spa"))[0])
ok("normal update: the web app folder is stamped with the version it is for", W.spa_stamp(os.path.join(h, "spa")) == NEW)
ok("normal update: no temporary or old folder left behind", not [n for n in os.listdir(h) if n.startswith(".spa-new-") or n == "spa.old"])
ok("normal update: the installed files are private to this user", all(os.stat(os.path.join(h, "spa", n)).st_mode & 0o077 == 0 for n in new))

# 2) missing / changed / incomplete / broken: nothing is replaced
s = spa_files(); lst = {n: W.git_blob_sha(b) for n, b in s.items()}; lst.pop("game.js")
unchanged_case("a file missing from GitHub's list", spa=s, listing=lst)
s = spa_files(); srv = dict(s); srv.pop("live.js")
unchanged_case("a listed file that won't download", spa=s, serve=srv)
s = spa_files(); srv = dict(s); srv["live.js"] = s["live.js"][: len(s["live.js"]) // 2]
unchanged_case("a file cut short in transit", spa=s, serve=srv)
s = spa_files(); srv = dict(s); srv["build.js"] = s["build.js"].replace(b"function", b"functoin", 1)
unchanged_case("a file changed in transit (hash differs from GitHub's)", spa=s, serve=srv)
s = spa_files(); mm = json.loads(s["MANIFEST.json"]); mm["js"].append("brand_new.js"); s["MANIFEST.json"] = json.dumps(mm).encode()
unchanged_case("the manifest names a file GitHub doesn't have", spa=s)
s = spa_files(); s["build.js"] += b"\nfunction broken({\n"
unchanged_case("a script that doesn't parse (node --check)", spa=s)
s = spa_files(); s["index.html"] = s["index.html"].replace(b"@@SPA_JS@@\n", b"")
unchanged_case("a shell without its script placeholder", spa=s)
s = spa_files(); s["MANIFEST.json"] = b"{oops"
unchanged_case("a manifest that isn't JSON", spa=s)
unchanged_case("no exact commit from GitHub", sha="")

# 3) the install itself fails after the web app was swapped: the old web app goes back
h, W = home()
before = snapshot(h)
github(W, spa_files())
os.mkdir(os.path.join(h, "engine.py.new"))            # writing the new engine now fails (a folder is in the way)
r = W.update_if_newer(E, dict(AUTO))
after = snapshot(h)
ok("a failed install: no restart, the old web app files are back, the engine and watcher untouched",
   r is False and before == after and not os.path.exists(os.path.join(h, "spa.old")), set(before.items()) ^ set(after.items()))
ok("a failed install: logged", any("couldn't write the new files" in x for x in LOG[-3:]), LOG[-3:])
ok("a failed install: no temporary folder or half-written file left", not [n for n in os.listdir(h) if n.startswith(".spa-new-")]
   and not os.path.exists(os.path.join(h, "combo_watcher.py.new")))

# 4) the phone-approved path (a Pi or a Mac with automatic updates off) fetches the same files
h, W = home()
github(W, spa_files())
eb = ENGINE_SRC.replace(f'VERSION = "{OLD}"', f'VERSION = "{NEW}"').encode()
wb = open(os.path.join(SRC, "combo_watcher.py")).read().replace(f'WATCHER_VERSION = "{OLD}"', f'WATCHER_VERSION = "{NEW}"').encode()
APPROVED = {"version": NEW, "engine": hashlib.sha256(eb).hexdigest(), "watcher": hashlib.sha256(wb).hexdigest()}
before = snapshot(h)
ok("phone-approved update without the web app's approval: waits, nothing installed",
   W.update_if_newer(E, {"auto_update": False, "approve": dict(APPROVED)}) is False and snapshot(h) == before
   and "hasn't approved this version's web app" in LOG[-1], LOG[-1:])
ok("phone-approved update whose web app differs from what the phone approved: nothing installed",
   W.update_if_newer(E, {"auto_update": False, "approve": dict(APPROVED, spa="0" * 64)}) is False and snapshot(h) == before
   and "approved" in LOG[-1], LOG[-1:])
conf = {"auto_update": False, "approve": dict(APPROVED, spa=digest_of(W, spa_files()))}
ok("phone-approved update: installs the approved files and the web app", W.update_if_newer(E, conf) is True
   and "/* the new version */" in open(os.path.join(h, "spa", "app.css")).read())
h, W = home()
github(W, spa_files())
ok("automatic updates on and the phone's approval lacks the web app digest: installs as an automatic update",
   W.update_if_newer(E, {"auto_update": True, "approve": dict(APPROVED)}) is True
   and "/* the new version */" in open(os.path.join(h, "spa", "app.css")).read())
h, W = home()
github(W, spa_files())
ok("automatic updates on and the phone approved other web app files (e.g. a stale copy): installs anyway",
   W.update_if_newer(E, {"auto_update": True, "approve": dict(APPROVED, spa="0" * 64)}) is True
   and "/* the new version */" in open(os.path.join(h, "spa", "app.css")).read())
h, W = home()
github(W, spa_files())
ok("not approved and automatic updates off: nothing installed", W.update_if_newer(E, {"auto_update": False}) is False
   and "/* the new version */" not in open(os.path.join(h, "spa", "app.css")).read())

# 5) the first update from a version that had no spa folder (the web app was inside the watcher file)
h, W = home()
shutil.rmtree(os.path.join(h, "spa"))
github(W, spa_files())
ok("first update from a version without a spa folder: installs the folder", W.update_if_newer(E, dict(AUTO)) is True
   and W.spa_assemble(os.path.join(h, "spa"))[0].startswith("<!doctype html>"))

# 6) an older updater installed this watcher without its files: it repairs itself, only for its own exact file
h = tempfile.mkdtemp(prefix="spaold")
os.environ["COMBOWATCH_HOME"] = h
shutil.copy(os.path.join(SRC, "combo_watcher.py"), h)
open(os.path.join(h, "engine.py"), "w").write(ENGINE_SRC)
spec = importlib.util.spec_from_file_location("W", os.path.join(h, "combo_watcher.py"))
W = importlib.util.module_from_spec(spec)
import builtins
_print = builtins.print; builtins.print = lambda *a, **k: None
spec.loader.exec_module(W)
builtins.print = _print
W.log = lambda *a: LOG.append(" ".join(str(x) for x in a))
ok("no spa folder at start: the watcher imported, knows it, and serves its built-in copy", bool(W.SPA_PROBLEM)
   and (W.SPA, W.LOGIN_HTML) == W.spa_legacy())
mine = open(os.path.join(h, "combo_watcher.py"), "rb").read()
github(W, spa_files(b""), watcher=mine + b"# a newer one\n")
ok("repair: refuses when GitHub's newest watcher isn't this file (the update brings both)",
   W.spa_repair(dict(AUTO)) is False and not os.path.exists(os.path.join(h, "spa")))
s = spa_files(b""); srv = dict(s); srv["games.js"] = b"x"
github(W, s, watcher=mine, serve=srv)
ok("repair: a damaged download installs nothing", W.spa_repair(dict(AUTO)) is False and not os.path.exists(os.path.join(h, "spa")))
github(W, spa_files(b""), watcher=mine)
ok("repair: with this exact watcher on GitHub, the files are fetched, checked and installed",
   W.spa_repair(dict(AUTO)) is True and W.spa_assemble(os.path.join(h, "spa")) == W.spa_assemble(os.path.join(SRC, "spa")))
shutil.rmtree(os.path.join(h, "spa"))
ok("repair with automatic updates off and no phone approval: installs nothing",
   W.spa_repair({"auto_update": False, "approve": {"version": W.WATCHER_VERSION}}) is False
   and not os.path.exists(os.path.join(h, "spa")))
ok("repair with a phone approval for other files: installs nothing",
   W.spa_repair({"auto_update": False, "approve": {"version": W.WATCHER_VERSION, "spa": "0" * 64}}) is False
   and not os.path.exists(os.path.join(h, "spa")))
ok("repair stamps the folder with this watcher's version", True)
ok("repair with the phone's approval of exactly these files: installed",
   W.spa_repair({"auto_update": False, "approve": {"version": W.WATCHER_VERSION, "spa": digest_of(W, spa_files(b""))}}) is True
   and os.path.isdir(os.path.join(h, "spa")))
shutil.rmtree(os.path.join(h, "spa"))
W.UPDATED.clear()
W.time = types.SimpleNamespace(sleep=lambda s: None, time=__import__("time").time)
W.spa_repair_loop(dict(AUTO))
ok("repair loop: installs and asks the watcher to restart (so Combo Hub serves the files)",
   W.UPDATED.get("now") is True and os.path.isdir(os.path.join(h, "spa")))
ok("nothing left over after the repairs", not [n for n in os.listdir(h) if n.startswith(".spa-new-") or n == "spa.old"])

# 7) main() itself starts the repair first thing when the files were missing, and only then
class Stop(Exception):
    pass


def main_starts_repair(Wm):
    seen = []
    Wm.spa_repair_start = lambda *a: seen.append(True)
    Wm.load_conf = lambda: {}
    Wm.load_engine = lambda: (_ for _ in ()).throw(Stop())     # stop main() right after its first steps
    try:
        Wm.main()
    except Stop:
        pass
    return bool(seen)


ok("main(): files missing at start -> the repair thread starts before anything else", main_starts_repair(W))
_, W2 = home()
ok("main(): files fine -> no repair", not W2.SPA_PROBLEM and not main_starts_repair(W2))

# 8) the phone's approval digest (engine) is exactly the watcher's spa_digest of the same files
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
espec = importlib.util.spec_from_file_location("Eng", "wahome/engine.py")
Eng = importlib.util.module_from_spec(espec)
espec.loader.exec_module(Eng)
files = spa_files(b"")


def eget(url, params=None, **k):
    n = url.split("/watcher/spa/")[-1]
    return R(raw=files[n]) if "/watcher/spa/" in url and n in files else R({}, 404)


Eng.requests = types.SimpleNamespace(get=eget, RequestException=requests.RequestException)
ok("phone: spa_approval_digest equals the watcher's spa_digest of the same files",
   Eng.spa_approval_digest() == digest_of(W, files) == W.spa_digest(W.spa_assemble(os.path.join(SRC, "spa"))[0],
                                                                    W.spa_assemble(os.path.join(SRC, "spa"))[1]))
files = dict(files)
files.pop("live.js")
ok("phone: a file it can't read gives no approval (empty), never a partial one", Eng.spa_approval_digest() == "")

# 9) a folder stamped for another version (an installer's fetch failed after it put in new Python files)
h, W = home()
open(os.path.join(h, "spa", ".version"), "w").write("2000.01.01.1\n")
spec = importlib.util.spec_from_file_location("Wst", os.path.join(h, "combo_watcher.py"))
Wst = importlib.util.module_from_spec(spec)
spec.loader.exec_module(Wst)
Wst.log = lambda *a: LOG.append(" ".join(str(x) for x in a))
ok("another version's web app folder: still served (no holding page) but marked stale",
   Wst.SPA_STALE and not Wst.SPA_PROBLEM and Wst.SPA != Wst.SPA_FALLBACK)
ok("main(): a stale folder -> the repair thread starts", main_starts_repair(Wst))
github(Wst, spa_files(b""), watcher=open(os.path.join(h, "combo_watcher.py"), "rb").read())
ok("repair of a stale folder: this version's files, stamped with this version",
   Wst.spa_repair(dict(AUTO)) is True and Wst.spa_stamp(os.path.join(h, "spa")) == Wst.WATCHER_VERSION)

# 10) node: a recent node's syntax error blocks; an old or broken node is skipped, never blocking updates forever
fake = tempfile.mkdtemp(prefix="fakenode")
path0 = os.environ.get("PATH", "")


def node_says(version, check_exit):
    with open(os.path.join(fake, "node"), "w") as f:
        f.write(f"#!/bin/sh\nif [ \"$1\" = --version ]; then echo {version}; exit 0; fi\nexit {check_exit}\n")
    os.chmod(os.path.join(fake, "node"), 0o755)
    os.environ["PATH"] = fake + os.pathsep + path0


spa, login = W.spa_assemble(os.path.join(SRC, "spa"))
node_says("v12.22.0", 1)
ok("node 12 (too old for today's JavaScript): the check is skipped, not failed", W.spa_node_check(spa, login) is False)
node_says("v20.11.0", 1)
try:
    W.spa_node_check(spa, login)
    blocked = False
except ValueError:
    blocked = True
ok("a recent node that says the script doesn't parse: blocks", blocked)
node_says("garbage", 0)
ok("a node whose version can't be read: skipped", W.spa_node_check(spa, login) is False)
os.environ["PATH"] = path0

# 11) one fetch at a time across processes (the running watcher's repair and an installer's --install-spa)
import fcntl
h, W = home()
with W.spa_locked():
    g = open(os.path.join(h, ".spa.lock"), "a")
    try:
        fcntl.flock(g, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held = False
    except OSError:
        held = True
    g.close()
ok("spa_locked holds a lock file other processes respect", held)
g = open(os.path.join(h, ".spa.lock"), "a")
fcntl.flock(g, fcntl.LOCK_EX | fcntl.LOCK_NB)
ok("and lets go of it afterwards", True)
g.close()
old = os.path.join(h, ".spa-new-fresh")
os.mkdir(old)
github(W, spa_files())
W.update_if_newer(E, dict(AUTO))
ok("a fresh temporary folder (another process mid-download) is never deleted", os.path.isdir(old))

# 12) the phone reads the files at GitHub's newest commit too (a stale main copy can't make its approval wrong)
files = spa_files(b"")
SEEN = []


def eget2(url, params=None, **k):
    SEEN.append(url)
    if "/commits/main" in url:
        return R(raw=SHA.encode())
    n = url.split("/watcher/spa/")[-1]
    return R(raw=files[n]) if f"/{SHA}/watcher/spa/" in url and n in files else R({}, 404)


Eng.requests = types.SimpleNamespace(get=eget2, RequestException=requests.RequestException)
ok("phone: the approval digest is read at the newest commit", Eng.spa_approval_digest() == digest_of(W, files)
   and all(f"/{SHA}/" in u for u in SEEN if "/watcher/spa/" in u))
