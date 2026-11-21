"""A newer version on the Mac reaches the open page (GitHub #150): the page carries a version placeholder the web
app fills in, update.js is in the manifest and loads before boot, the service worker file changes with every release and
can never serve a cached page (no fetch handler), and the version note is stamped in at serve time."""
import sys, json, importlib.util
sys.path.insert(0, "stub"); sys.path.insert(0, "run")
import nfl_combo_planner as M
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
ok("the page, watcher and engine agree on one version", W.WATCHER_VERSION == M.VERSION)

ok("page: carries the version placeholder the web app fills in", 'PAGE_VER="__CWVER__"' in W.SPA)
man = json.load(open("wtest/spa/MANIFEST.json")) if __import__("os").path.exists("wtest/spa/MANIFEST.json") else json.load(open("../watcher/spa/MANIFEST.json"))
js = man["js"]
ok("manifest: update.js is listed, after settings.js and before boot.js", "update.js" in js and js.index("settings.js") < js.index("update.js") < js.index("boot.js"))
ok("page: the version check is hooked into every freshness block", "verSeen(f.ver)" in W.SPA and "function verSeen" in W.SPA)
ok("page: the pill's tap fires the haptic itself (no await before it)", "function verTap(){hap('light');verReload(true);}" in W.SPA)
ok("page: busy checks cover sheets, quotes, buys, taps, fingers and scrubs",
   all(k in W.SPA for k in ("S.scrub", "S.buying", "S.pSend", "S.qpend", "S.bpend", "S.busy", "#modal", "verFingers")))
sw = W.SW_JS
ok("sw: has no fetch handler and caches nothing, so it can't serve an old page", "'fetch'" not in sw and "caches." not in sw)
ok("sw: carries a version stamp filled in at serve time", "// app-version: @@VER@@" in sw)
a, b = sw.replace("@@VER@@", "2026.11.21.130"), sw.replace("@@VER@@", "2026.11.21.131")
ok("sw: a new release changes the worker's bytes (so browsers install it)", a != b and "2026.11.21.131" in b)
src = open("wtest/combo_watcher.py").read()
ok("server: the version is in the freshness block and the page is filled in", '"ver": str(getattr(A, "VERSION"' in src and '.replace("__CWVER__"' in src)
ok("server: the worker is stamped with WATCHER_VERSION when served", 'SW_JS.replace("@@VER@@", WATCHER_VERSION)' in src)
