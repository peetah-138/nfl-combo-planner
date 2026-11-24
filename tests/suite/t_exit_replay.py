# CHECK: group=engine
# tools/exit_replay.py (early-exit value test, phase 1), on a synthetic history file: read-only (mode=ro, the file is
# byte-identical afterwards), aggregates only (no ticker or date string anywhere in what it prints or writes), cells under
# 20 bets hidden, missing tables/columns/files degrade with a message instead of a crash, the fee is the engine's own,
# and --combo-fee reads the ledger's real columns (fees summed over fills, n from the sold/won/lost rules).
import os, io, re, json, hashlib, sqlite3, tempfile, importlib.util, contextlib, traceback
REPO = os.environ.get("REPO") or os.path.abspath("../..")
spec = importlib.util.spec_from_file_location("X", os.path.join(REPO, "tools", "exit_replay.py"))
X = importlib.util.module_from_spec(spec); spec.loader.exec_module(X)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
TMP = tempfile.mkdtemp()


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def build(path, with_path=True, nhl=5):
    db = sqlite3.connect(path)
    db.executescript("""
    create table sb_paper(bet text primary key, ts real, day text, league text, sport text, kind text, source text,
      grade text, role text, price real, fair real, ev real, pays real, stake real, plain real, outcome real, clv real,
      at real, game text);
    create table price_path(ts real, ticker text, bid real, ask real, mid real, depth real, score text, frac real);
    create table closes(ticker text primary key, sport text, event text, fair real, price real, kick real, ts real, outcome text);
    create table ledger(ticker text primary key, kind text, league text, side text, cost real, back real, fees real,
      sold_back real, sell_fees real, n_sold real, status text, opened real, closed real, legs text, outcome text,
      held real, seen real, nf int);
    create table sell_log(ts real, ticker text, result text, why text, kind text, side text, offer real, cost real,
      pays real, frac real, chance real, by text, combo text, outcome text, held real, done real);
    create table offers(ts real, combo text, p real, pays real, hold real, offer real, real_offer int, verdict text);
    create table bets(combo text primary key, first_seen real, cost real, pays real, legs text, sports text, status text,
      back real, settled real, p_first real);""")
    for i in range(80 + nhl):
        league = "nba" if i < 80 else "nhl"
        t = f"KXNBAGAME-26NOV{10 + i % 15:02d}AAABBB-T{i}"
        ts = 1_000_000 + i * 5000
        win = i % 4 == 0
        plain = 5.0 / (0.40 + 0.0168) - 5.0 if win else -5.0        # what the bet made held, at the flat $5 test stake
        stake = 0.0 if i % 3 == 1 else 2.0                          # never-staked bets: outcome is 0 even for winners
        db.execute("insert into sb_paper values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (json.dumps([t]), ts, "d", league, "x", "single", "live", "cand", "stake", 0.40, 0.50, 0.05, 12.0, stake,
                    plain, round(plain * stake / 5.0, 4) if stake else 0.0, None, ts, f"game{i // 2}"))
        if with_path:
            kick = ts + 1500
            db.execute("insert into closes values(?,?,?,?,?,?,?,?)", (t, "nba", "e", 0.5, 0.45, kick, kick, "yes"))
            for j in range(1, 31):
                bid = min(0.38 + 0.005 * j, 0.5)
                db.execute("insert into price_path values(?,?,?,?,?,?,?,?)",
                           (ts + 60 * j, t, bid, bid + 0.02, bid + 0.01, 10, "3-2 Q1" if ts + 60 * j >= kick else None, None))
    for k in range(5):                                      # combo ledger rows: entry fee exactly the standard formula
        db.execute("insert into ledger values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (f"C{k}", "combo", "nfl", "yes", 4.0 + 0.168 + 0.02, 0, 0.168 + 0.02, 5.0, 0.02, 10, "sold", 1, 2, "", None, None, None, 0))
    db.execute("insert into ledger values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",     # won, nothing sold
               ("CW", "combo", "nfl", "yes", 4.168, 10.0, 0.168, 0, 0, 0, "won", 1, 2, "", None, None, None, 0))
    db.execute("insert into ledger values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",     # lost: size from sell_log
               ("CL", "combo", "nfl", "yes", 4.168, 0, 0.168, 0, 0, 0, "lost", 1, 2, "", None, None, None, 0))
    db.execute("insert into sell_log(ts, ticker, result, pays) values(1,'CL','declined',10.0)")
    for k in range(2):                                      # a kind with only 2 rows: hidden; and double the fee
        db.execute("insert into ledger values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (f"S{k}", "spread", "nfl", "yes", 4.0 + 0.336, 0, 0.336, 5.0, 0, 10, "sold", 1, 2, "", None, None, None, 0))
    for c in range(25):                                     # real combo buyback offers: 0.85 of hold, rising later
        db.execute("insert into bets values(?,?,?,?,?,?,?,?,?,?)", (f"B{c}", 0, 4.0, 10.0, "[]", "", "won" if c % 2 else "lost", 0, 0, 0.4))
        for q in range(3):
            db.execute("insert into offers values(?,?,?,?,?,?,?,?)", (10 + q, f"B{c}", 0.4, 10.0, 5.0, 4.25 + q, 1, "hold"))
    db.commit(); db.close()


def wal_case():
    p = os.path.join(TMP, "wal.db"); build(p)
    w = sqlite3.connect(p, isolation_level=None); w.execute("pragma journal_mode=wal")
    w.execute("insert into bets values('LIVE',0,1,2,'[]','','pending',0,0,0.4)")     # sits in the -wal, like the watcher's
    before = digest(p)
    code, s, text = go(p)
    ok("B the real file is WAL with the watcher's connection open: still reads, main file untouched", code == 0 and s["singles"]["all"]["n"] == 85 and digest(p) == before, text[-200:])
    w.close()


def digest(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def go(path, out=None, combo_fee=False):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code, summary = X.run(path, out, 100, combo_fee)
    return code, summary, buf.getvalue()


def a_replay():
    p = os.path.join(TMP, "h.db"); build(p)
    before, out = digest(p), os.path.join(TMP, "out.json")
    code, s, text = go(p, out)
    ok("A runs to the end and says it is safe to send", code == 0 and "safe to send" in text)
    allg = (s.get("singles") or {}).get("all") or {}
    ok("A singles: every buy with a path is replayed (85 buys: 80 nba + 5 nhl), never-staked winners included", allg.get("n") == 85, allg.get("n"))
    hold = allg["rules"]["hold"]["cents_per_dollar"]
    ok("A hold uses the flat-stake result (plain), not the stake-scaled outcome: 25% winners at 40c lose about 40c a dollar", -45 < hold < -30, hold)
    r = allg.get("rules") or {}
    ok("A all six exit rules and hold are reported, each with cents per dollar", set(r) == {"hold", "+3c", "+5c", "+10c", "fair", "T-1h", "T-15m"}, set(r))
    ok("A a +3c exit beats holding on this rising synthetic path (exit-minus-hold above 0)", r["+3c"]["minus_hold"] > 0, r.get("+3c"))
    ok("A the game-level range is given for each rule's edge over hold", isinstance(r["+3c"]["minus_hold_95"], list))
    oos = allg.get("out_of_sample")
    ok("A out-of-sample: a rule picked on the first 70% is scored on the last 30%", isinstance(oos, dict) and oos["test_n"] > 0, oos)
    gates = s["data_quality"]
    ok("A data-quality gates are printed first", text.index("data_quality") < text.index("singles"))
    ok("A the gates say 100% have 10+ path points and a spread", gates.get("pct_with_10_or_more_path_points_after_buy") == 100.0 and gates.get("pct_with_spread_seen") == 100.0, gates)
    ph = s["singles"]["placeholders"]
    ok("A measured placeholders: spread 2c pre and in play, widening 1.0, drift reported", ph["spread"]["pre_game_median_cents (SB_SPREAD[0])"] == 2.0 and ph["spread"]["in_play_widening_x (SB_LIVE_WIDEN)"] == 1.0 and ph["pre_close_drift"]["n"] == 85, ph)
    ok("A n<20 cells are hidden (the 5-bet league)", s["singles"]["by_league"]["nhl"] == {"n": 5, "note": "n<20, hidden"}, s["singles"]["by_league"]["nhl"])
    ok("A n>=20 cells are shown (the 80-bet league)", "rules" in s["singles"]["by_league"]["nba"])
    blob = open(out).read() + text
    ok("A privacy: no ticker, no KX series, no game date in the output or the file", not re.search(r"KX|\d{2}(NOV|DEC|JAN)\d{2}|AAABBB|game\d", blob), re.findall(r"KX\w*|\d{2}NOV\d{2}", blob)[:3])
    ok("A the history file is byte-identical afterwards", digest(p) == before)
    ok("A combos: real offers give the discount (offer/hold) and settled combos get their own replay", (s["combos"]["discount"]["n_offers"] == 75) and "exit_replay" in s["combos"], s["combos"])
    ok("A the combo replay keeps its own range and drops the rules a combo has no path for", "fair" not in s["combos"]["exit_replay"].get("rules", {"fair": 1}))


def b_readonly():
    p = os.path.join(TMP, "ro.db"); build(p)
    db = X.open_ro(p)
    try:
        db.execute("create table zz(a)")
        wrote = True
    except sqlite3.OperationalError:
        wrote = False
    ok("B the connection is read-only: a write is refused", not wrote)
    db.close()
    wal_case()
    ok("B the source opens with the mode=ro URI", "mode=ro" in open(os.path.join(REPO, "tools", "exit_replay.py")).read())
    src = open(os.path.join(REPO, "tools", "exit_replay.py")).read()
    ok("B no network, no engine import, no write SQL in the script", not re.search(r"import (requests|urllib\.request|socket)|\b(insert into|update \w+ set|delete from|drop table|create table)\b", src), "")


def c_degrade():
    e = os.path.join(TMP, "empty.db"); sqlite3.connect(e).execute("create table other(a)").connection.commit()
    code, s, text = go(e)
    ok("C an empty history file: no crash, each part says skipped, still ends safe", code == 0 and "skipped" in text and "safe to send" in text, text[-200:])
    p = os.path.join(TMP, "nopath.db"); build(p, with_path=False)
    code, s, text = go(p)
    ok("C no price_path table rows: singles say so, combos still run", code == 0 and s["combos"].get("real_offer_rows") == 75, s.get("singles"))
    q = os.path.join(TMP, "cols.db"); db = sqlite3.connect(q)
    db.execute("create table sb_paper(bet text, ts real)"); db.execute("create table price_path(ts real, ticker text)")
    db.commit(); db.close()
    code, s, text = go(q)
    ok("C a table missing columns degrades with a plain reason", code == 0 and "skipped" in text, text[-200:])
    code, s, text = go(os.path.join(TMP, "nope.db"))
    ok("C a missing file gives a message, not a traceback", code == 2 and "cannot open" in text)
    junk = os.path.join(TMP, "junk.db"); open(junk, "w").write("not a database at all, just text" * 20)
    code, s, text = go(junk)
    ok("C a file that is not a database does not crash", code == 2 and "cannot open" in text, text[-200:])


def d_combo_fee():
    p = os.path.join(TMP, "fee.db"); build(p)
    before = digest(p)
    code, s, text = go(p, None, combo_fee=True)
    k = s["combo_fee"]["kinds"]
    ok("D combo-fee: sold, won and lost rows all join on the ledger's own columns (7 combo rows)", k["combo"]["n"] == 7, k)
    ok("D a fee exactly at the standard formula reads as ratio 1.0 (fees summed across fills, closing fee removed)", k["combo"]["ratio_of_sums"] == 1.0 and k["combo"]["median_ratio"] == 1.0, k["combo"])
    ok("D a kind with under 3 rows is hidden", k["spread"] == {"n": 2, "note": "n<3, hidden"}, k["spread"])
    ok("D aggregates only: no ticker in the output", not re.search(r"\bC\d\b|CW|CL|S\d\b", text.replace("ratio", "")))
    ok("D combo-fee leaves the file untouched", digest(p) == before)
    e = os.path.join(TMP, "e2.db"); sqlite3.connect(e).execute("create table other(a)").connection.commit()
    code, s, text = go(e, None, combo_fee=True)
    ok("D combo-fee on a file with no ledger degrades", code == 0 and "skipped" in text)


def e_fee():
    spec2 = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(E)
    same = all(abs(X.fee_per_contract(p, n) - E.single_fee(p, n)) < 1e-12 for p in (0.05, 0.3, 0.5, 0.77, 0.95) for n in (None, 1, 7, 10, 100))
    ok("E the script's fee is the engine's single_fee (same rate, same per-order rounding)", same and X.FEE_RATE == E.FEE_RATE)


for n, f in (("a", a_replay), ("b", b_readonly), ("c", c_degrade), ("d", d_combo_fee), ("e", e_fee)):
    section(n, f)
