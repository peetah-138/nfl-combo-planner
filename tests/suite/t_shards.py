# CHECK: group=engine
# The check list's split (checklist.py, run_checks.sh, CI's parallel jobs): every test runs, in exactly one shard
# and one lane, the same way every time, and CI's jobs together cover every group and every page shard.
import os, re, glob
import checklist as C

bad = 0
def check(name, cond):
    global bad
    print(("PASS " if cond else "FAIL ") + name)
    bad += not cond

here = os.path.dirname(os.path.abspath(__file__))
files_t = sorted(os.path.basename(f)[:-3] for f in glob.glob(os.path.join(here, "t_*.py")))
files_p = sorted(os.path.basename(f)[:-3] for f in glob.glob(os.path.join(here, "test_*.py")))
# tests register themselves: a "# CHECK: group=... [secs=N] [retry]" header in each file (see checklist.py); no list to edit
check("every t_*.py file has a valid CHECK header (%s)" % "; ".join("%s: %s" % kv for kv in sorted(C.PROBLEMS.items())[:3]), not C.PROBLEMS)
files_s = sorted(os.path.basename(f)[:-3] for f in glob.glob(os.path.join(here, "st_*.py")))
check("every static check file is discovered once", sorted(C.STATIC) == files_s and len(set(C.STATIC)) == len(C.STATIC) and files_s)
check("every engine test file is discovered once", sorted(C.ENGINE) == files_t and len(set(C.ENGINE)) == len(C.ENGINE))
helpers = [t for t in files_p if C.TESTS[t]["group"] == "none"]
check("every page test file is discovered once (only the helper test_webapp_pw is group=none)",
      sorted(C.PAGE + helpers) == files_p and len(set(C.PAGE)) == len(C.PAGE) and helpers == ["test_webapp_pw"])
check("every discovered test is in exactly one of static / engine / page / helper", len(C.TESTS) == len(C.STATIC) + len(C.ENGINE) + len(C.PAGE) + len(helpers))
check("secs only name page tests", set(C.SECS) <= set(C.PAGE))
import tempfile
with tempfile.TemporaryDirectory() as d:        # the header parser itself: what it accepts and what it refuses
    def hdr(text):
        p = os.path.join(d, "x.py"); open(p, "w").write(text); return C.header(p)
    check("header: a good page header is read", hdr("# CHECK: group=page secs=30 retry\nimport os\n")[0] == {"group": "page", "secs": 30, "retry": True})
    check("header: a header below some leading lines is found", hdr("#!/usr/bin/env python3\n# CHECK: group=engine\n")[0] == {"group": "engine", "secs": None, "retry": False})
    check("header: none is refused", hdr("import os\n")[0] is None)
    check("header: two are refused", hdr("# CHECK: group=page\n# CHECK: group=engine\n")[0] is None)
    check("header: no group is refused", hdr("# CHECK: secs=5\n")[0] is None)
    check("header: a typo is refused, not ignored", hdr("# CHECK: group=page secz=5\n")[0] is None and hdr("# CHECK: group=pages\n")[0] is None)
    check("header: secs must be a positive number", hdr("# CHECK: group=page secs=0\n")[0] is None and hdr("# CHECK: group=page secs=x\n")[0] is None)
check("retry list only names page tests", set(C.RETRY) <= set(C.PAGE))

ok_union = ok_disjoint = ok_same = ok_order = True
for n in range(1, 13):
    parts = [C.shard(C.PAGE, "%d/%d" % (i, n)) for i in range(1, n + 1)]
    flat = [t for p in parts for t in p]
    ok_union &= sorted(flat) == sorted(C.PAGE)
    ok_disjoint &= len(flat) == len(set(flat))
    ok_same &= parts == [C.shard(C.PAGE, "%d/%d" % (i, n)) for i in range(1, n + 1)]
    ok_order &= all(p == [t for t in C.PAGE if t in p] for p in parts)
check("shards 1..12: together they are the whole page list", ok_union)
check("shards 1..12: no test is in two shards", ok_disjoint)
check("shards are the same every time", ok_same)
check("a shard keeps the listed order", ok_order)
check("no shard spec = every page test", C.shard(C.PAGE, "") == C.PAGE)
try:
    C.shard(C.PAGE, "4/3"); check("an out-of-range shard is refused", False)
except ValueError:
    check("an out-of-range shard is refused", True)

ok_lanes = True
for k in range(1, 9):
    for spec in ("", "1/4", "3/4"):
        names = C.shard(C.PAGE, spec)
        lanes = C.split(names, k)
        flat = [t for b in lanes for t in b]
        ok_lanes &= len(lanes) == k and sorted(flat) == sorted(names) and len(flat) == len(set(flat))
check("lanes split a shard with nothing lost or doubled", ok_lanes)
w = [sum(C.secs(t) for t in C.shard(C.PAGE, "%d/5" % i)) for i in range(1, 6)]
check("five shards are balanced within the longest test (%s s)" % w, max(w) - min(w) <= max(C.secs(t) for t in C.PAGE))

repo = os.environ.get("REPO") or os.path.abspath(os.path.join(here, "..", ".."))
rc = open(os.path.join(repo, "tests", "run_checks.sh")).read()
check("run_checks.sh reads the lists from checklist.py (no second copy)", "checklist.py engine" in rc and "checklist.py page" in rc and "checklist.py static" in rc
      and not re.search(r"\bt_review t_review2\b|PAGE=\"test_", rc))
ci = open(os.path.join(repo, ".github", "workflows", "ci.yml")).read()
m = re.search(r"shard:\s*\[([\d,\s]+)\]", ci); tot = re.search(r"CHECK_SHARD:\s*\$\{\{\s*matrix\.shard\s*\}\}/(\d+)", ci)
nums = sorted(int(x) for x in m.group(1).split(",")) if m else []
check("CI runs every page shard once (1..N)", bool(tot) and nums == list(range(1, int(tot.group(1)) + 1)))
groups = set(g for line in re.findall(r"CHECK_GROUPS:\s*\"?([a-z ,]+)\"?", ci) for g in re.split(r"[ ,]+", line) if g)
check("CI runs the static, engine, sim and pages groups", {"static", "engine", "sim", "pages"} <= groups)
check("CI never narrows the run (no CHECK_ONLY)", "CHECK_ONLY" not in ci)
check("CI keeps the required check named exactly 'checks'", re.search(r"(?m)^  checks:\n    name: checks\n", ci) is not None)
need = re.search(r"(?ms)^  checks:\n.*?needs:\s*\[([^\]]+)\]", ci)
jobs = set(re.findall(r"(?m)^  ([a-z0-9_-]+):\n", ci.split("\njobs:\n", 1)[-1])) - {"checks"}
check("the 'checks' job runs even when a shard fails (else a skipped check would count as passed)",
      re.search(r"(?ms)^  checks:\n.*?if: \$\{\{ always\(\) \}\}", ci) is not None)
check("the 'checks' job waits for every other job", bool(need) and {j.strip() for j in need.group(1).split(",")} == jobs)
print("all good" if not bad else "PROBLEMS")
