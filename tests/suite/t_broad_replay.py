# CHECK: group=engine
# tools/exit_replay.py --broad: the replay on the watch-all recorder's own tables. The test database is made by running the
# ENGINE's recorder (so the replay is checked against what the recorder really writes, scale and columns included), then
# labelled with the engine's own label copier. Read-only (file byte-identical), aggregates only (no ticker, date or id),
# n<20 games hidden, fees both ways, per sport x price bucket, game-level range and the 70/30 split, missing tables degrade.
import os, io, re, hashlib, sqlite3, tempfile, importlib.util, contextlib, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
REPO = os.environ.get("REPO") or os.path.abspath("../..")
spec = importlib.util.spec_from_file_location("X", os.path.join(REPO, "tools", "exit_replay.py"))
X = importlib.util.module_from_spec(spec); spec.loader.exec_module(X)
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
TMP = tempfile.mkdtemp()
NOW = 1_800_000_000


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def build(path, nba=100, nhl=5, implied=3):
    """nba games: the ask is 40c and the bid 38c at the first sighting, the bid then runs to 60c and the market LOSES (so a
    +10c exit beats holding by a lot); nhl games the same but few of them; some markets are labelled by the price-implied rule."""
    E.STORE["db"] = None
    E.store_open(path)
    E.BP["ids"].clear(); E.BP["tbl"] = None
    E._bp_tables()
    n = 0
    for sport, count in (("nba", nba), ("nhl", nhl)):
        for g in range(count):
            t = f"KX{sport.upper()}GAME-26NOV{10 + g // 5:02d}TEAM{g:03d}-AAA"
            ev = f"KX{sport.upper()}GAME-26NOV{10 + g // 5:02d}TEAM{g:03d}"
            kick = NOW + g * 1000 + 7200
            metas = {t: (ev, kick, "win", sport, NOW)}
            rows = [(t, NOW + g * 1000 + k * 300, b, a, 100, 600 if k == 0 else None, 1 if k == 0 else None,
                     None, None, None, 0, None, None, None)
                    for k, (b, a) in enumerate(((380, 400), (390, 410), (450, 470), (600, 620), (610, 630)))]
            E._bp_write(rows, metas, NOW + g * 1000)
            n += 1
    E.store_x("create table if not exists closes(ticker text primary key, sport text, event text, fair real, price real, kick real, ts real, outcome text)")
    for r in E.store_rows("select ticker, kick from bp_mkt"):
        E.store_x("insert into closes values(?,?,?,?,?,?,?,?)", (r["ticker"], "x", "e", 0.5, 0.4, r["kick"], NOW, "no"))
    E.store_x("create table if not exists live_fairs(ticker text, ts real, sport text, fair real, how text, outcome text)")
    E.bp_maintain(NOW + 2 * 86400)                         # copies the labels (the games are long over by then)
    E.store_x("update bp_mkt set rs=9 where id in (select id from bp_mkt order by id desc limit ?)", (implied,))
    E.STORE["db"].execute("pragma wal_checkpoint(truncate)")
    return n


def digest(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def go(path, out=None, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code, summary = X.run(path, out, 100, **kw)
    return code, summary, buf.getvalue()


def a_replay():
    p = os.path.join(TMP, "b.db"); build(p)
    E.STORE["db"].close(); E.STORE["db"] = None
    before, out = digest(p), os.path.join(TMP, "out.json")
    code, s, text = go(p, out, broad=True)
    b = s["broad"]
    ok("A runs to the end and says it is safe to send", code == 0 and "safe to send" in text)
    q = b["data_quality"]
    ok("A coverage is counts: 105 markets recorded, all labelled by the resolver copy (closes), 3 relabelled price-implied and left out by default",
       q["markets_recorded"] == 105 and q["labelled_markets"] == 105 and q["markets_replayed"] == 102, q)
    allg = b["all"]
    ok("A every replayable labelled market is one row (100 nba + 5 nhl, minus the 3 implied)", allg["n"] == 102, allg["n"])
    r = allg["rules"]
    ok("A all six exit rules and hold are reported", set(r) == {"hold", "+3c", "+5c", "+10c", "fair", "T-1h", "T-15m"}, set(r))
    ok("A holding a loser from 40c loses about 42c a dollar (entry ask 40c plus fee)", -105 < r["hold"]["cents_per_dollar"] < -90, r["hold"])
    ok("A a +10c exit sells at the 60c bid, net of the exit fee and spread: a large gain over holding", r["+10c"]["minus_hold"] > 80 and r["+10c"]["cents_per_dollar"] > 0, r["+10c"])
    ok("A the game-level range is given", isinstance(r["+10c"]["minus_hold_95"], list))
    ok("A the fair rule (the sharp fair 60c was above the 40c ask) sells at the first bid >= 60c", r["fair"]["minus_hold"] > 80, r["fair"])
    oos = allg["out_of_sample"]
    ok("A 70/30: a rule chosen on the first 70% of games is scored on the last 30%", isinstance(oos, dict) and oos["test_n"] > 0, oos)
    ok("A the nba group is shown and the 5-game nhl group is hidden (n<20)", "rules" in b["by_sport"]["nba"] and b["by_sport"]["nhl"].get("note") == "n<20, hidden", b["by_sport"])
    ok("A price buckets: all entries sit in the 30-60c bucket", set(b["by_price_bucket"]) == {"30-60c"} and "nba 30-60c" in b["by_sport_and_bucket"] and b["by_sport_and_bucket"]["nhl 30-60c"].get("note") == "n<20, hidden")
    ok("A the entry rule and fee note are printed", "first recorded ask" in b["entry_rule"] and "paid on entry and on exit" in b["fee_note"])
    blob = open(out).read() + text
    ok("A privacy: no ticker, KX series, date, team code or market id in the output or file", not re.search(r"KX|\d{2}NOV\d{2}|TEAM\d|AAA", blob), re.findall(r"KX\w*|\d{2}NOV\d{2}", blob)[:3])
    ok("A the history file is byte-identical afterwards (read-only)", digest(p) == before)
    c2, s2, t2 = go(p, None, broad=True, include_implied=True)
    ok("A --include-implied adds the price-implied labels", s2["broad"]["data_quality"]["markets_replayed"] == 105 and s2["broad"]["data_quality"]["labelled_by_source"].get("price_implied") == 3, s2["broad"]["data_quality"])


def b_readonly_and_degrade():
    p = os.path.join(TMP, "ro.db"); build(p, nba=22, nhl=0, implied=0)
    E.STORE["db"].close(); E.STORE["db"] = None
    db = X.open_ro(p)
    try:
        db.execute("insert into bp_mkt(ticker) values('x')"); ok("B a write through the replay's connection is refused", False)
    except sqlite3.OperationalError:
        ok("B a write through the replay's connection is refused", True)
    db.close()
    ok("B the source opens the file with the mode=ro URI and never writes the recorder tables", "mode=ro" in open(os.path.join(REPO, "tools", "exit_replay.py")).read() and not re.search(r"(insert|update|delete|create|alter)\s", open(os.path.join(REPO, "tools", "exit_replay.py")).read().split("def broad_group")[1].split("def combo_section")[0], re.I))
    e = os.path.join(TMP, "e.db"); c = sqlite3.connect(e); c.execute("create table other(a)"); c.commit(); c.close()
    code, s, text = go(e, None, broad=True)
    ok("B a file the recorder never ran on degrades with a message, not a crash", code == 0 and "skipped" in text and "has not run" in text, text[:200])
    code, s, text = go(os.path.join(TMP, "nope.db"), None, broad=True)
    ok("B a missing file is a clear refusal", code == 2)
    d = os.path.join(TMP, "u.db"); build(d, nba=3, nhl=0, implied=0)
    E.STORE["db"].close(); E.STORE["db"] = None
    code, s, text = go(d, None, broad=True)
    ok("B 3 games are never shown (hidden under 20)", s["broad"].get("all", {}).get("note") == "n<20, hidden", s["broad"])


def c_scale_is_the_engines():
    ok("C the tool reads the engine's price scale (so a changed scale cannot silently skew a replay)", X.engine_bp_scale() == E.BP_SCALE == 1000)


for n, f in (("a", a_replay), ("b", b_readonly_and_degrade), ("c", c_scale_is_the_engines)):
    section(n, f)
