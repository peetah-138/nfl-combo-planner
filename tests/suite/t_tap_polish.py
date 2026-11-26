# CHECK: group=engine
# iPhone tap/layout polish (issues #186 #178 #272 #273 #274): the engine's plain words and average fill price, plus a
# read of the web app's own files for the tap fixes a page test can't time cheaply (the page half is test_tap_polish.py).
# Display only: nothing here prices, sizes, buys or sells. Fakes only: no network.
import os, re, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
SPA = "wtest/spa"   # the web app files, copied next to the tests by run_checks.sh
src = lambda f: open(os.path.join(SPA, f), encoding="utf-8").read()

# #186: the average price when a stake spans levels; plain words for strike bands
asks = [(0.45, 10), (0.46, 20), (0.50, 500)]
f = E.line_fill("T", 0.53, 0.04, 1000, asks=asks)
ok("fill: avg is the average ask paid before the fee (10@45c + 20@46c = 45.67c)", abs(f["avg"] - round((10 * .45 + 20 * .46) / 30, 4)) < 1e-9 and f["best"] == 0.45)
ok("fill: nothing filled = no average", E.line_fill("T", 0.50, 0.04, 100, asks=asks)["avg"] is None)
ok("every strike band has plain words", all(E.line_bucket_words(b) != b for b in ("far below", "below", "at the line", "above", "far above")))
ok("'far above' reads 'well past the line'", E.line_bucket_words("far above") == "well past the line" and E.line_bucket_words("odd") == "odd")
bk = re.search(r"BUCKET_WORDS=\{([^}]*)\}", src("results.js"))
ok("Results maps the same five bands", bool(bk) and all(w in bk.group(1) for w in E.LINE_BUCKET_WORDS.values()))
ok("the card shows 'avg N¢' only when it differs", "avgc" in src("build.js") and ".avgc" in src("bestbets.css"))

# #178: Smart Buy's Bigger stakes line is short, the rest behind a tap
r = src("results.js")
ok("Bigger stakes: the short line sits in a <summary>, the other figures behind it", "<details class=\"sbmore\"><summary>${head}</summary>${more}</details>" in r and "settled`," in r)

# #272: a tappable toast can't take a tap meant for a sheet button
ok("toast: no tap while a sheet is open (JS drops it, CSS stops stragglers)", "#modal.on')))" in src("common.js") and "body:has(#modal.on) .toast.tap.on{pointer-events:none}" in src("app.css"))

# #273: Undo wakes the sleeping save at once and says so; an undone-before-sent save needs no Mac round trip to succeed
i = src("ideas.js")
ok("undo: the save's sleep can be woken (job.wake) and Undo shows 'Bringing it back...' at once", "job.wake=" in i and "j.wake()" in i and "Bringing it back..." in i)
ok("undo: a dismiss that never reached the Mac is undone locally, with no failure toast", "ends.every(e=>e==='undone')" in i)

# #274: Build date range
b, c = src("build_sections.js"), src("build.css")
ok("dates: 44pt targets on the chips and the segmented buttons", "daychips .chip{min-height:44px" in c and ".dayrange .seg button{min-height:44px}" in c)
ok("dates: one Sunday note (the subtitle), chips in order Thursday, Saturday, Monday",
   "dsun" not in b and b.index("'Wed & Thu':'Thursday'") < b.index("'Saturday'") < b.index("'Monday'") and b.count("Sunday is always in") == 1)
ok("dates: the card stays up while the new board loads, picks-cleared note, inline error",
   "S.dayHold=" in b and "S.dayHold" in src("build.js") and "Picks cleared for the new dates." in b and "S.dayErr" in b and "role=\"alert\"" in b)
