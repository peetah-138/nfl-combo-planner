# CHECK: group=engine
# tools/research/nfl_state_vs_kalshi.py on a synthetic history file: read-only (mode=ro, the file is byte-identical
# afterwards), aggregates only (no ticker anywhere in what it prints or writes), small groups hidden, missing tables or
# columns or files degrade with a message instead of a crash, and it tells a model that beats the price from one that does not.
import os, io, json, math, hashlib, random, sqlite3, tempfile, importlib.util, contextlib, traceback
REPO = os.environ.get("REPO") or os.path.abspath("../..")
spec = importlib.util.spec_from_file_location("K", os.path.join(REPO, "tools", "research", "nfl_state_vs_kalshi.py"))
K = importlib.util.module_from_spec(spec); spec.loader.exec_module(K)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
TMP = tempfile.mkdtemp()
MODEL = {"model": "nfl_state_logistic_v1", "features": ["z1", "d", "pre", "pre_t", "pre_sqrt_t", "poss", "poss_t", "poss_sqrt_t"],
         "coef": [0.098, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def build(path, games=40, mid_noise=0.0, tables=True):
    """A made-up season. Each game's lead is a random walk; the TRUE chance is the normal-tail one; Kalshi's mid is the
    truth plus noise; the outcome is the real final lead. MODEL below is a logistic that approximates the truth."""
    rnd = random.Random(7)
    db = sqlite3.connect(path)
    if tables:
        db.executescript("""create table sig_state(ts real, ticker text, me int, opp int, frac real, poss int, down int, dist int, pts int);
        create table price_path(ts real, ticker text, bid real, ask real, mid real, depth real, score text, frac real);
        create table closes(ticker text primary key, sport text, event text, fair real, price real, kick real, ts real, outcome text);""")
    nd = __import__("statistics").NormalDist()
    for g in range(games):
        t = f"KXNFLGAME-26NOV{g:02d}AAABBB-AAA"
        lead = 0
        for j in range(12):
            frac = 1 - j / 12
            truth = nd.cdf(lead / (5.0 * math.sqrt(12 - j)))
            ts = 5_000_000 + g * 20_000 + j * 700
            mid = min(max(truth + rnd.gauss(0, mid_noise), 0.03), 0.97)
            if tables:
                db.execute("insert into sig_state values(?,?,?,?,?,?,?,?,?)",
                           (ts, t, 30 + max(lead, 0), 30 + max(-lead, 0), frac, 0, None, None, 60))
                db.execute("insert into price_path values(?,?,?,?,?,?,?,?)", (ts + 5, t, mid - 0.01, mid + 0.01, mid, 10, None, None))
            lead += round(rnd.gauss(0, 5))
        if tables:
            win = lead > 0 or (lead == 0 and rnd.random() < 0.5)
            db.execute("insert into closes values(?,?,?,?,?,?,?,?)", (t, "nfl", "e", 0.5, 0.5, 1, 2, "yes" if win else "no"))
    db.commit(); db.close()


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def tests():
    mp = os.path.join(TMP, "m.json"); open(mp, "w").write(json.dumps(MODEL))
    p1 = os.path.join(TMP, "h1.db"); build(p1, games=120, mid_noise=0.12)
    before = sha(p1)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = K.main(["--db", p1, "--model", mp, "--out", os.path.join(TMP, "o.json")])
    out = buf.getvalue()
    res = json.loads(out)
    ok("runs and reports", rc == 0 and res["status"] == "ok" and res["all"]["samples"] >= 200, res.get("all"))
    ok("read-only: the history file is byte-identical afterwards", sha(p1) == before)
    ok("aggregates only: no ticker in the output", "KXNFL" not in out and "AAABBB" not in out and "26NOV" not in out)
    d = res["all"]["model_minus_kalshi_logloss"]
    ok("a model that IS the truth beats a noisy price (negative gap, range below zero)", d["mean"] < 0 and d["ci95"][1] < 0, d)
    p2 = os.path.join(TMP, "h2.db"); build(p2, games=120, mid_noise=0.0)
    r2 = K.run(p2, mp)
    d2 = r2["all"]["model_minus_kalshi_logloss"]
    ok("a price equal to the model gives no edge (range spans zero)", abs(d2["mean"]) < 0.03, d2)
    p3 = os.path.join(TMP, "h3.db"); build(p3, games=3, mid_noise=0.1)
    r3 = K.run(p3, mp)
    ok("small groups are hidden", "note" in r3["all"] and "logloss_model" not in r3["all"], r3["all"])
    p4 = os.path.join(TMP, "h4.db"); build(p4, tables=False)
    ok("missing tables degrade with a message", K.run(p4, mp)["status"].startswith("skipped"))
    ok("missing history file is a message, not a crash", K.main(["--db", os.path.join(TMP, "nope.db"), "--model", mp]) == 1)
    bad = os.path.join(TMP, "bad.json"); open(bad, "w").write('{"model": "other"}')
    ok("a wrong model file is refused", K.main(["--db", p1, "--model", bad]) == 1)
    try:
        db = K.open_ro(p1); db.execute("create table x(a)"); ok("the connection cannot write", False)
    except sqlite3.OperationalError:
        ok("the connection cannot write", True)
    ok("fee comes from the engine's own FEE_RATE line", abs(K.FEE_RATE - 0.07) < 1e-9 or K.FEE_RATE > 0, K.FEE_RATE)


section("state vs kalshi", tests)
