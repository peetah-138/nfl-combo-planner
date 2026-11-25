# CHECK: group=engine
# tools/espn_wp_scorecard.py (issue #483) on synthetic history files with a known answer: read-only (the file is
# byte-identical afterwards), aggregates only (no ticker or date string in what it prints or writes), groups under 20 games
# hidden, missing tables / files degrade with a message, the right sources win and the pass bar needs 2+ leagues.
import os, io, re, json, hashlib, sqlite3, tempfile, importlib.util, contextlib, traceback, sys
REPO = os.environ.get("REPO") or os.path.abspath("../..")
sys.path.insert(0, os.path.join(REPO, "tools"))
spec = importlib.util.spec_from_file_location("S", os.path.join(REPO, "tools", "espn_wp_scorecard.py"))
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
TMP = tempfile.mkdtemp()


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def build(path, leagues=(("nba", 80), ("ncaamb", 80), ("nhl", 5)), informative_wp=True, tables=True):
    db = sqlite3.connect(path)
    if tables:
        db.executescript("""
        create table wp_shadow(ts real, ticker text, league text, wp real, play_id text, play_age real, feed_age real,
          model real, blend real, fair real, bid real, ask real, mid real, lead int, frac real);
        create table wp_outcome(ticker text primary key, outcome text, ts real);
        create table wp_hist(ts real, league text, game text, seq int, play_id text, home_wp real, tie real, wall real, home text, away text);""")
    k = 0
    for lg, n in (leagues if tables else ()):
        for i in range(n):
            g = f"KXGAME-26NOV{k:04d}ZZZ"
            k += 1
            for side, yes in (("A", True), ("B", False)):
                t = f"{g}-{side}"
                wp = (0.9 if yes else 0.1) if informative_wp else None
                # the blend is wrong in odd games (it likes both sides at 55c), right-neutral in even games
                blend = 0.55 if i % 2 else 0.5
                for j in range(2):
                    db.execute("insert into wp_shadow values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (1_000_000 + k * 100 + j * 10, t, lg, wp, "p1", 5.0 + j, 3.0, 0.5, blend, 0.5, 0.48, 0.5, 0.49, 2, 0.5))
                db.execute("insert into wp_outcome values(?,?,?)", (t, "yes" if yes else "no", 2_000_000))
    db.commit(); db.close()


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def a_known_answer():
    p = os.path.join(TMP, "a.db"); build(p)
    before = sha(p)
    out = os.path.join(TMP, "out.json")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = S.main(["--db", p, "--out", out, "--boot", "200"])
    txt = buf.getvalue() + open(out).read()
    res = json.load(open(out))
    ok("A runs and exits 0", rc == 0)
    ok("A the history file is byte-identical afterwards (read-only)", sha(p) == before)
    ok("A no ticker, game id or date string anywhere in what it prints or writes", not re.search(r"KXGAME|26NOV|\d{4}-\d{2}-\d{2}", txt))
    nba = res["leagues"]["nba"]
    ok("A a league of 80 games is shown with its game count", nba["games"] == 80, nba.get("games"))
    ok("A the group under 20 games is hidden", res["leagues"]["nhl"] == {"detail": "n<20, hidden"}, res["leagues"].get("nhl"))
    sc = nba["scores"]
    ok("A ESPN wp Brier is exactly 0.01 (0.1 off every time)", abs(sc["wp"]["brier"] - 0.01) < 1e-9, sc["wp"])
    ok("A mid and model (always 0.5) score 0.25 (mid 0.49)", abs(sc["mid"]["brier"] - 0.25) < 2e-3 and abs(sc["model"]["brier"] - 0.25) < 1e-9)
    ok("A the blend (half the games 0.55) is between", 0.25 < sc["blend"]["brier"] < 0.2530 and sc["wp"]["brier"] < sc["blend"]["brier"])
    ok("A log score: wp beats the 0.5 sources", sc["wp"]["logscore"] < sc["mid"]["logscore"] and abs(sc["mid"]["logscore"] - 0.6931) < 1e-3, sc["mid"])
    ok("A a bootstrap range comes with each score", len(sc["wp"]["brier_range"]) == 2 and sc["wp"]["brier_range"][0] <= sc["wp"]["brier"] <= sc["wp"]["brier_range"][1])
    tr = nba["trade"]
    ok("A 70/30 split of the games by time", tr["train_games"] == 56 and tr["test_games"] == 24, (tr["train_games"], tr["test_games"]))
    w = tr["sources"]["wp"]
    ok("A wp's rule wins every bet: net per $1 positive with its range above 0", w["net_per_dollar"] > 0.5 and w["range"][0] > 0, w)
    ok("A the blend's rule (it buys both sides in odd games) loses", tr["sources"]["blend"]["net_per_dollar"] < 0, tr["sources"]["blend"])
    ok("A mid and model never disagree with the ask: no bet, reported as skipped", "skipped" in tr["sources"]["mid"] and "skipped" in tr["sources"]["model"])
    ok("A wp beats the blend by well over 1c per $1", w["vs_blend"] > 0.01 and w["passes"] is True, w)
    v = res["verdict"]["wp"]
    ok("A passes in both big leagues so the verdict passes", sorted(v["passes_in"]) == ["nba", "ncaamb"] and v["passes"] is True, v)
    ok("A the others do not pass", not res["verdict"]["mid"]["passes"] and not res["verdict"]["model"]["passes"])
    ok("A coverage: wp present, play age median shown for the big leagues, only yes/no for the small", res["coverage"]["nba"]["has_wp"] and res["coverage"]["nba"]["play_age_median_s"] > 0
       and res["coverage"]["nhl"] == {"has_wp": True, "detail": "n<20, hidden"}, res["coverage"])


def b_one_league_is_not_enough():
    p = os.path.join(TMP, "b.db"); build(p, leagues=(("nba", 80),))
    res = S.run(p, None, 100)
    ok("B passing in one league is not a pass", res["verdict"]["wp"]["passes"] is False and res["verdict"]["wp"]["passes_in"] == ["nba"], res["verdict"])


def c_coverage_without_wp():
    p = os.path.join(TMP, "c.db"); build(p, informative_wp=False)
    res = S.run(p, None, 100)
    ok("C a league with no wp says so", res["coverage"]["nba"]["has_wp"] is False and res["coverage"]["nba"]["share_rows_with_wp"] == 0, res["coverage"]["nba"])
    ok("C and scores nothing for wp rather than crashing", "verdict" in res)


def d_degrade():
    p = os.path.join(TMP, "d.db"); build(p, tables=False)
    res = S.run(p, None, 50)
    ok("D missing tables give a message, not a crash", "skipped" in res and "wp_shadow" in res["skipped"], res.get("skipped"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = S.main(["--db", os.path.join(TMP, "nope.db")])
    ok("D a missing file is a message and exit 1", rc == 1 and "skipped" in buf.getvalue())
    p2 = os.path.join(TMP, "d2.db"); db = sqlite3.connect(p2)
    db.execute("create table wp_shadow(ts real, ticker text)"); db.commit(); db.close()
    ok("D a table lacking columns is a message", "lacks" in S.run(p2, None, 50)["skipped"])


def e_write_is_refused():
    p = os.path.join(TMP, "e.db"); build(p, leagues=(("nba", 3),))
    db = S.X.open_ro(p)
    try:
        db.execute("insert into wp_outcome values('x','yes',1)")
        ok("E the connection is read-only", False)
    except sqlite3.OperationalError as err:
        ok("E the connection is read-only", "readonly" in str(err))
    db.close()
    src = open(os.path.join(REPO, "tools", "espn_wp_scorecard.py")).read()
    ok("E the tool has no network and no write SQL", not re.search(r"requests|urllib|http\.client|insert\s+into|delete\s+from|update\s+\w+\s+set|drop\s+table", src, re.I))


for n, f in (("a", a_known_answer), ("b", b_one_league_is_not_enough), ("c", c_coverage_without_wp), ("d", d_degrade), ("e", e_write_is_refused)):
    section(n, f)
