# CHECK: group=engine
# tools/signal_events.py (news + context report) on a synthetic history file: read-only (byte-identical afterwards),
# aggregates only (no ticker, team, player or date string in the output), cells under 20 hidden, missing tables and
# columns and files degrade with a message, the event study and the 70/30 residual test run on planted effects.
import os, io, re, json, hashlib, random, sqlite3, tempfile, importlib.util, contextlib, traceback
REPO = os.environ.get("REPO") or os.path.abspath("../..")
spec = importlib.util.spec_from_file_location("SE", os.path.join(REPO, "tools", "signal_events.py"))
X = importlib.util.module_from_spec(spec); spec.loader.exec_module(X)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
TMP = tempfile.mkdtemp()
digest = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def build(path, news=60, games=600, tables=True):
    db = sqlite3.connect(path)
    if not tables:
        db.execute("create table other(a)"); db.commit(); db.close(); return
    db.executescript("""
    create table sig_news(id integer primary key, ekey text, ts real, news_ts real, league text, team text, player text,
      pos text, kind text, old_status text, new_status text, material int, game_event text, ticker text, bid real, ask real,
      fair_book real, fair_src text, px_age real);
    create table sig_news_fu(news_id integer, horizon int, ts real, delay_s real, bid real, ask real, fair_book real, fair_age real);
    create table sig_ctx(ts real, phase text, mins_to_start real, league text, game_event text, home_ticker text,
      home_fair real, home_rest real, away_rest real, home_b2b int, away_b2b int, home_g7 int, away_g7 int,
      away_travel_mi real, away_tz int, indoor int, neutral int, wx_wind real, wx_temp real, wx_precip real);
    create table closes(ticker text primary key, outcome text);""")
    for i in range(news):
        league = "nba" if i < 50 else "nhl"
        db.execute("insert into sig_news values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (i, f"k{i}", 1e6 + i, 1e6 + i, league, "Secret Team", "Secret Player", "G", "new", None, "Out", 1,
                    f"EV{i}", f"KXSECRET-{i}", 0.50, 0.52, 0.55, "odds", 5.0))
        for h in (5, 15, 60):                      # books move 5 pts, Kalshi only 2 pts: gap 3 pts
            db.execute("insert into sig_news_fu values(?,?,?,?,?,?,?,?)", (i, h, 1e6 + i + h * 60, h * 60.0, 0.52, 0.54, 0.60, 10.0))
    rng = random.Random(4)
    for g in range(games):
        fair = rng.uniform(0.3, 0.7)
        rest = rng.choice([-2, -1, 0, 1, 2])
        # true win chance = books + 0.10 per rest day (a planted effect the books miss)
        p = min(0.95, max(0.05, fair + 0.10 * rest))
        win = rng.random() < p
        t = f"KXSECRETHOME-{g}"
        db.execute("insert into sig_ctx values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (1e6 + g * 100, "pre2h", 120, "nba", f"EV{g}", t, fair, 3 + max(rest, 0), 3 + max(-rest, 0), 0, 0, 3, 3,
                    rng.uniform(0, 2000), 0, 0, 0, None, None, None))
        db.execute("insert into closes values(?,?)", (t, "yes" if win else "no"))
    db.commit(); db.close()


def run(args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = X.main(args)
    return code, buf.getvalue()


def a_main():
    p = os.path.join(TMP, "a.db"); build(p)
    out = os.path.join(TMP, "a.json"); before = digest(p)
    code, text = run(["--db", p, "--out", out, "--boot", "100"])
    ok("A exits 0 and writes the summary file", code == 0 and os.path.isfile(out), code)
    s = json.load(open(out))
    ev = s["event_study"]; cells = ev["cells"]
    ok("A event study: 50-event league shown, 10-event league hidden at n<20", "nba material +5min" in cells and cells["nba material +5min"].get("n") == 50 and cells["nhl material +5min"]["note"] == "n<20, hidden", list(cells)[:3])
    c = cells["nba material +15min"]
    ok("A event study: kalshi +2 pts, books +5 pts, gap +3 pts", abs(c["kalshi_move_toward_news"] - 0.02) < 1e-6 and abs(c["sharp_move_toward_news"] - 0.05) < 1e-6 and abs(c["gap_sharp_minus_kalshi"] - 0.03) < 1e-6, c)
    ok("A event study: a game-level range is given", isinstance(c["gap_95"], list) and len(c["gap_95"]) == 2, c)
    nba = s["residual_test"]["leagues"]["nba"]
    f = nba["factors"]
    ok("A residual test: the planted rest effect gains out of sample, the range above 0", f["rest_diff"]["brier_gain_out_of_sample"] > 0 and f["rest_diff"]["brier_gain_95"][0] > 0, f["rest_diff"])
    ok("A residual test: a factor with no values is reported, not invented", f["wind"]["note"] == "no values recorded yet", f["wind"])
    ok("A residual test: scored on the last 30% of games only", 150 <= f["rest_diff"]["test_games"] <= 190, f["rest_diff"])
    blob = open(out).read() + text
    ok("A privacy: no ticker, team, player or event id in the output", not re.search(r"KX|Secret|EV\d", blob), re.findall(r"KX\w*|Secret\w*", blob)[:3])
    ok("A the history file is byte-identical afterwards", digest(p) == before)
    ok("A says safe to send", "safe to send" in text)


def b_degrade():
    p = os.path.join(TMP, "b.db"); build(p, tables=False)
    code, text = run(["--db", p, "--boot", "50"])
    ok("B an empty history file does not crash; each part says skipped with the reason", code == 0 and text.count("skipped") >= 2 and "sig_news is missing" in text, text[:200])
    p2 = os.path.join(TMP, "b2.db"); build(p2, news=5, games=5)
    code, text = run(["--db", p2, "--boot", "50"])
    ok("B tiny tables: counts under 20 print n<20, hidden", code == 0 and "n<20, hidden" in text, text[:200])
    db = sqlite3.connect(p2); db.execute("alter table sig_ctx drop column wx_precip"); db.commit(); db.close()
    code, text = run(["--db", p2, "--boot", "50"])
    ok("B a missing column is named, not a crash", code == 0 and "lacks column(s) wx_precip" in text, text[:300])
    code, text = run(["--db", os.path.join(TMP, "nope.db")])
    ok("B a missing file gives a clear message and a non-zero exit", code == 2 and "not found" in text or code == 2, (code, text[:100]))
    junk = os.path.join(TMP, "junk.db"); open(junk, "w").write("not a database at all" * 50)
    code, text = run(["--db", junk])
    ok("B a file that is not a database is handled", code == 2 and "Traceback" not in text, (code, text[:100]))


def c_readonly():
    p = os.path.join(TMP, "c.db"); build(p)
    db = X.open_ro(p)
    try:
        db.execute("create table zz(a)"); wrote = True
    except sqlite3.OperationalError:
        wrote = False
    db.close()
    ok("C the connection is read-only: a write is refused", not wrote)
    src = open(os.path.join(REPO, "tools", "signal_events.py")).read()
    ok("C opens with mode=ro; no network, no engine import, no write SQL", "mode=ro" in src and not re.search(r"import (requests|urllib\.request|socket)|nfl_combo_planner|\b(insert into|update \w+ set|delete from|drop table|create table)\b", src))


for n, fn in (("A", a_main), ("B", b_degrade), ("C", c_readonly)):
    section(n, fn)
