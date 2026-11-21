# The web app's files (GitHub #124): watcher/spa/ holds the page as plain files, MANIFEST.json lists them in load
# order, and combo_watcher.py joins them at import into the same SPA and LOGIN_HTML strings as before. This checks
# every file is there, listed exactly once and non-empty, each script parses, the assembly is deterministic and
# complete, and that missing or broken files never stop the watcher from importing (it serves a holding page and
# knows it must fetch them). The one-time proof that the split was a pure move is tools/verify_spa_split.py.
import hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile
ok = lambda n, c, *a: print(("PASS " if c else "FAIL ") + n, *(a if not c else ()))
HERE = os.path.abspath("wtest")
REPO = os.environ.get("REPO") or os.path.dirname(os.path.dirname(HERE))
os.environ["COMBOWATCH_HOME"] = tempfile.mkdtemp(prefix="spafiles")
LOGS = []


def load(folder):
    """Import a copy of the watcher from folder (its spa folder sits next to it), capturing the import-time log."""
    sys.argv = [os.path.join(folder, "combo_watcher.py")]
    spec = importlib.util.spec_from_file_location("W%d" % len(LOGS), os.path.join(folder, "combo_watcher.py"))
    W = importlib.util.module_from_spec(spec)
    import builtins
    real = builtins.print
    builtins.print = lambda *a, **k: LOGS.append(" ".join(str(x) for x in a))
    try:
        spec.loader.exec_module(W)
    finally:
        builtins.print = real
    return W


W = load(HERE)
SPA = os.path.join(HERE, "spa")
m = json.load(open(os.path.join(SPA, "MANIFEST.json")))
listed = [m["shell"], *m["css"], *m["js"], m["login"]]
on_disk = sorted(n for n in os.listdir(SPA) if n != "MANIFEST.json")
ok("every file in the spa folder is listed in MANIFEST.json exactly once", sorted(listed) == on_disk and len(set(listed)) == len(listed),
   set(on_disk) ^ set(listed))
ok("the repo's spa folder is the one under test", sorted(os.listdir(os.path.join(REPO, "watcher", "spa"))) == sorted(os.listdir(SPA)))
ok("every listed file is non-empty UTF-8 with plain newlines",
   all((lambda b: b.strip() and b"\r" not in b and b.decode("utf-8"))(open(os.path.join(SPA, n), "rb").read()) for n in listed))
bad = [n for n in m["js"] if subprocess.run(["node", "--check", os.path.join(SPA, n)], capture_output=True).returncode]
ok("node --check passes on every js file on its own", not bad, bad)
ok("the watcher imported its web app without a problem", W.SPA_PROBLEM == "", W.SPA_PROBLEM)
spa, login = W.spa_assemble()
ok("assembly is deterministic (twice the same bytes) and is what the module exports",
   (spa, login) == W.spa_assemble() and spa == W.SPA and login == W.LOGIN_HTML)
ok("no placeholder survives the assembly", "@@SPA_CSS@@" not in spa and "@@SPA_JS@@" not in spa)
shell = open(os.path.join(SPA, m["shell"])).read()
ok("each css/js file is included exactly once, in manifest order",
   all(spa.count(open(os.path.join(SPA, n)).read()) == 1 for n in m["css"] + m["js"])
   and spa.index(open(os.path.join(SPA, m["js"][0])).read()) < spa.index(open(os.path.join(SPA, m["js"][-1])).read()))
ok("the page still carries the placeholders the server fills in", all(k in spa for k in ("__CWTOK__", "__CWLOCAL__")))
ok("the login page still carries its placeholders", all(k in login for k in ("__MSG__", "__FID__", "__HTTPS__", "__ICON__")))
f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False); f.write(W.spa_scripts(spa)); f.close()
ok("node --check passes on the assembled script", subprocess.run(["node", "--check", f.name], capture_output=True).returncode == 0)
ok("spa_node_check agrees (node is on this computer)", W.spa_node_check(spa, login) is True)
print("assembled SPA sha256", hashlib.sha256(spa.encode()).hexdigest(), "LOGIN_HTML", hashlib.sha256(login.encode()).hexdigest())


def broken(how):
    """A copy of the watcher whose spa folder is damaged in one way; returns the imported module."""
    d = tempfile.mkdtemp(prefix="spabad")
    shutil.copy(os.path.join(HERE, "combo_watcher.py"), d)
    if how != "no folder":
        shutil.copytree(SPA, os.path.join(d, "spa"))
    s = os.path.join(d, "spa")
    if how == "missing file":
        os.remove(os.path.join(s, "game.js"))
    elif how == "empty file":
        open(os.path.join(s, "live.js"), "w").close()
    elif how == "bad manifest":
        open(os.path.join(s, "MANIFEST.json"), "w").write("{not json")
    elif how == "path in manifest":
        mm = dict(m, js=m["js"] + ["../../etc/passwd"]); json.dump(mm, open(os.path.join(s, "MANIFEST.json"), "w"))
    elif how == "no placeholder":
        open(os.path.join(s, "index.html"), "w").write(shell.replace("@@SPA_JS@@\n", ""))
    elif how == "placeholder in a piece":
        with open(os.path.join(s, "boot.js"), "a") as fh:
            fh.write("@@SPA_JS@@\n")
    return load(d)


for how in ("no folder", "missing file", "empty file", "bad manifest", "path in manifest", "no placeholder", "placeholder in a piece"):
    n0 = len(LOGS)
    B = broken(how)
    ok(f"{how}: the watcher still imports, serves the holding page and knows to fetch the files",
       B.SPA_PROBLEM and B.SPA == B.SPA_FALLBACK and B.LOGIN_HTML == B.SPA_FALLBACK and callable(B.main), B.SPA_PROBLEM)
    ok(f"{how}: it says so loudly in the log", any("WEB APP FILES MISSING OR BROKEN" in x for x in LOGS[n0:]), LOGS[n0:])
B = broken("no folder")
ok("the holding page works with the login page's placeholder replacing (nothing to fill, nothing breaks)",
   B.LOGIN_HTML.replace("__MSG__", "x").replace("__FID__", "") == B.SPA_FALLBACK and "finishing an update" in B.SPA_FALLBACK)
src = open(os.path.join(HERE, "combo_watcher.py")).read()
ok("main() starts the repair only when the files were missing or broken",
   "if SPA_PROBLEM:" in src.split("\ndef main():")[1][:400] and "spa_repair_start()" in src.split("\ndef main():")[1][:400])
ok("the installers' --install-spa runs the same repair", '"--install-spa" in sys.argv' in src)
