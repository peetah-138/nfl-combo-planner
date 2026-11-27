# The check list's test names and how they are split up. run_checks.sh reads this; so does CI (one job per shard).
#   python checklist.py static                -> the static checks written as scripts (st_*.py; the static group)
#   python checklist.py static                -> the static checks written as scripts (st_*.py; the static group)
#   python checklist.py engine [i/N]          -> every engine test (t_*.py), or only shard i of N
#   python checklist.py page [i/N]            -> the page tests (test_*.py), or only shard i of N
#   python checklist.py lanes K name ...      -> the names spread over K lanes, one line per lane
#   python checklist.py retry                 -> the page tests allowed one automatic retry (CI only, CHECK_RETRY=1)
# There is NO list to edit: a test registers itself. Every t_*.py / test_*.py in this folder starts (in its first 15
# lines) with a header comment, so adding a test means adding one file and nothing else (no shared file, no merge
# conflict between parallel PRs):
#     # CHECK: group=static                    a static check written as a script (st_*.py), run in the static group
#     # CHECK: group=engine                    an engine test (t_*.py), run one after another
#     # CHECK: group=page secs=45              a page test (test_*.py), run in parallel lanes and CI shards
#     # CHECK: group=page secs=16 retry        ...and allowed ONE automatic rerun in CI (CHECK_RETRY=1)
#     # CHECK: group=none                      a helper that matches the names but is not a test (test_webapp_pw.py)
# group must agree with the file name (st_ = static, t_ = engine, test_ = page). secs = rough seconds the page test takes on a CI
# runner; only the balance of the split depends on it (a missing or stale number never drops or doubles a test;
# unknown = DEFAULT). The longest test (test_hsw, ~160 s) sets the floor for a shard's time, so 5 shards of 3 lanes
# is about as fast as it gets: more shards would only add runners. `retry` is for a test that is timing-bound by
# nature (a flaky test should be fixed at the root first): test_rebuild_ui's own race is fixed, but on a badly
# overloaded machine the web app's background warm-up can keep the engine lock for minutes and the progress poll gets
# no answer.
# Tests are listed in name order (they don't depend on each other). Splits are deterministic: longest first, each to
# the lightest bin (ties: lowest bin), using the seconds above. Every test lands in exactly one shard and one lane
# (t_shards.py checks it, and that every file has a valid header).
import glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = 45
GROUPS = ("static", "engine", "page", "none")
_HEADER = re.compile(r"^#\s*CHECK:(.*)$")


def header(path):
    """The CHECK header of a test file: ({"group": ..., "secs": int or None, "retry": bool}, []) or (None, problems)."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = [next(f, "") for _ in range(15)]
    except OSError as err:
        return None, ["can't be read: %s" % err]
    found = [m.group(1) for m in (_HEADER.match(l.rstrip()) for l in lines) if m]
    if len(found) != 1:
        return None, ["needs exactly one '# CHECK: group=... ' line in its first 15 lines (has %d)" % len(found)]
    meta, bad = {"group": None, "secs": None, "retry": False}, []
    for tok in found[0].split():
        k, _, v = tok.partition("=")
        if k == "group" and v in GROUPS:
            meta["group"] = v
        elif k == "secs" and v.isdigit() and int(v) > 0:
            meta["secs"] = int(v)
        elif k == "retry" and not v:
            meta["retry"] = True
        else:
            bad.append("bad token %r (use group=engine|page|none, secs=N, retry)" % tok)
    if meta["group"] is None:
        bad.append("has no group=engine|page|none")
    return (meta, []) if not bad else (None, bad)


def discover():
    """Every t_*.py / test_*.py here: ({name: meta}, {name: [problems]}). A test with a bad or missing header is
    still run, by its file name's group (t_ = engine, test_ = page), so a mistake never silently drops a test."""
    tests, problems = {}, {}
    for path in sorted(glob.glob(os.path.join(HERE, "st_*.py")) + glob.glob(os.path.join(HERE, "t_*.py")) + glob.glob(os.path.join(HERE, "test_*.py"))):
        name = os.path.basename(path)[:-3]
        want = "static" if name.startswith("st_") else "engine" if name.startswith("t_") else "page"
        meta, bad = header(path)
        if meta and meta["group"] not in (want, "none"):
            bad = ["group=%s doesn't match its file name (%s)" % (meta["group"], want)]
        if meta and meta["group"] == "none" and (meta["secs"] or meta["retry"]):
            bad = ["group=none takes no secs or retry"]
        if meta and meta["group"] in ("engine", "static") and (meta["secs"] or meta["retry"]):
            bad = ["engine and static tests take no secs or retry"]
        if bad:
            problems[name] = bad
        tests[name] = (meta if not bad else None) or {"group": want, "secs": None, "retry": False}
    return tests, problems


TESTS, PROBLEMS = discover()
STATIC = sorted(n for n, m in TESTS.items() if m["group"] == "static")
ENGINE = sorted(n for n, m in TESTS.items() if m["group"] == "engine")
PAGE = sorted(n for n, m in TESTS.items() if m["group"] == "page")
SECS = {n: m["secs"] for n, m in TESTS.items() if m["group"] == "page" and m["secs"]}
RETRY = [n for n in PAGE if TESTS[n]["retry"]]


def secs(name):
    return SECS.get(name, DEFAULT)


def split(names, n):
    """names -> n bins, longest first into the lightest bin; the same input always gives the same bins."""
    n = max(1, int(n))
    bins, load = [[] for _ in range(n)], [0.0] * n
    for t in sorted(dict.fromkeys(names), key=lambda t: (-secs(t), t)):
        k = min(range(n), key=lambda b: (load[b], b))
        bins[k].append(t); load[k] += secs(t)
    return bins


def shard(names, spec):
    """spec "i/N" (1-based) -> the names in shard i; "" or "1/1" -> all of them, in their listed order."""
    if not spec:
        return list(names)
    i, n = (int(x) for x in spec.split("/"))
    if not 1 <= i <= n:
        raise ValueError("shard %s is out of range" % spec)
    keep = set(split(names, n)[i - 1])
    return [t for t in names if t in keep]


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["static"]:
        print(" ".join(STATIC))
    elif a[:1] == ["engine"]:
        print(" ".join(shard(ENGINE, a[1] if len(a) > 1 else "")))
    elif a[:1] == ["page"]:
        print(" ".join(shard(PAGE, a[1] if len(a) > 1 else "")))
    elif a[:1] == ["lanes"]:
        for b in split(a[2:], int(a[1])):
            print(" ".join(b))
    elif a[:1] == ["retry"]:
        print(" ".join(RETRY))
    else:
        sys.exit("usage: checklist.py static | engine [i/N] | page [i/N] | lanes K names... | retry")
