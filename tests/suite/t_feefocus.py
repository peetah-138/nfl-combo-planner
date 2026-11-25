# CHECK: group=engine
# tools/fee_focus.py (fees and "few strategic bets"), on a synthetic history file: read-only (mode=ro, byte-identical
# afterwards), aggregates only (no ticker or date string in what it prints or writes), cells under 20 bets hidden,
# missing tables degrade with a message, the combo fee ratio is read right, and the top-N simulation runs on a 70/30 split.
import os, io, re, json, math, hashlib, sqlite3, tempfile, importlib.util, contextlib, traceback
REPO = os.environ.get("REPO") or os.path.abspath("../..")
os.sys.path.insert(0, os.path.join(REPO, "tools"))
spec = importlib.util.spec_from_file_location("FF", os.path.join(REPO, "tools", "fee_focus.py"))
F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
TMP = tempfile.mkdtemp()


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def build(path, paper=True, combo_mult=1.0):
    db = sqlite3.connect(path)
    db.executescript("""
    create table ledger(ticker text primary key, kind text, league text, side text, cost real, back real, fees real,
      sold_back real, sell_fees real, n_sold real, status text, opened real, closed real, legs text, outcome text,
      held real, seen real, nf int);
    create table sell_log(ts real, ticker text, result text, why text, kind text, side text, offer real, cost real,
      pays real, frac real, chance real, by text, combo text, outcome text, held real, done real);""")
    if paper:
        db.execute("create table sb_paper(bet text primary key, ts real, day text, league text, sport text, kind text, "
                   "source text, grade text, role text, price real, fair real, ev real, pays real, stake real, plain real, "
                   "outcome real, clv real, at real, game text)")
    base = 1_700_000_000
    for i in range(60):                       # singles: 100 contracts at 0.40 held, fee = exact rounded formula
        n, p = 10 + i % 7, 0.40
        fee = math.ceil(round(0.07 * n * p * (1 - p) * 100, 6)) / 100
        win = i % 2 == 0
        t = f"KXNBAGAME-26NOV{i:03d}AAABBB-T"
        db.execute("insert into ledger values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (t, "single", "nba", "yes", n * p + fee, n if win else 0.0, fee, 0, 0, 0, "won" if win else "lost",
                    base + i * 86400, base + i * 86400 + 9000, json.dumps([t]), None, None, None, 1))
        if not win:
            db.execute("insert into sell_log(ticker, pays) values(?,?)", (t, float(n)))
    for i in range(30):                       # combos: entry fee = combo_mult x the formula, sold early
        n, p = 8, 0.30
        fee = round(0.07 * n * p * (1 - p) * combo_mult, 2)
        sf = 0.05
        t = f"KXMVE-C{i}"
        db.execute("insert into ledger values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (t, "combo", "nfl", "yes", n * p + fee + sf, 0, fee + sf, n * 0.4, sf, n, "sold",
                    base + i * 86400, base + i * 86400 + 5000, json.dumps([t + "-A", t + "-B"]), None, None, None, 1))
    if paper:
        for i in range(300):                  # 60 days x 5 bets; the higher the ev the likelier the win
            day = f"2026-10-{1 + i // 5:02d}" if i // 5 < 30 else f"2026-11-{i // 5 - 29:02d}"
            ev = 0.01 * (i % 5)
            win = (i * 7) % 10 < 3 + (i % 5)
            price = 0.45
            plain = (5 / price - 5) * 0.97 if win else -5.0
            db.execute("insert into sb_paper values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (json.dumps([f"KXNBAGAME-26NOV{i:03d}AAABBB-T"]), base + i * 17000, day, "nba", "bball", "single",
                        "live", "A" if i % 5 > 2 else "B", "stake", price, 0.5, ev, 11.0, 5.0, plain, plain, None, base,
                        f"game{i // 2}"))
    db.commit(); db.close()


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def runit(path, out=None):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code, summ = F.run(path, out, 60)
    return code, summ, buf.getvalue()


P = os.path.join(TMP, "h.db"); OUT = os.path.join(TMP, "o.json")
build(P)
before = sha(P)
code, S, text = runit(P, OUT)


def a():
    ok("exit 0", code == 0)
    ok("db byte-identical", sha(P) == before)
    k = S["part_a_fees"]["formula_check"]["kinds"]
    ok("singles match the rounded formula", k["single"].get("single_fill_ratio_to_rounded") == 1.0, k["single"])
    ok("single match pct 100", k["single"].get("matches_rounded_formula_pct") == 100.0, k["single"])
    ok("combo ratio ~1.0 with standard fee", abs(k["combo"]["ratio_recorded_to_unrounded_formula"] - 1.0) < 0.05, k["combo"])
    ok("ratio fed to part B", abs(S["combo_fee_ratio_used_in_part_b"]["ratio_to_unrounded_formula"] - 1.0) < 0.1, S["combo_fee_ratio_used_in_part_b"])
    ok("round trip present", "single" in S["part_a_fees"]["round_trip"] and "combo" in S["part_a_fees"]["round_trip"])
section("A", a)


def b():
    pb = S["part_b_few_strategic_bets"]
    ok("paper cells", pb["paper_book"]["rows_settled"] == 300 and "by_grade" in pb["paper_book"])
    sim = pb["top_n_per_day_what_if"]
    m = pb["real_bets_by_paper_grade_and_ev"]
    ok("real bets matched to the paper book by legs", m["rows"] == 60 and set(m["by_grade"]) == {"A", "B"}, m.get("rows"))
    ok("paper_book_as_staked named", "paper_book_as_staked" in pb["top_n_per_day_what_if"])
    ok("sim has 70/30 days", sim.get("days_train") and sim.get("days_test") and sim["days_train"] > sim["days_test"], sim.get("days"))
    ok("sim rules grid", all(f"top{n}_x{m}" in sim["rules"] for n in (1, 2, 3, 5) for m in (1, 2, 3)))
    ok("rule picked on train only", sim["rule_picked_on_train_by_net_per_dollar"] in sim["rules"])
    c = sim["rules"]["top1_x2"]["train"]
    ok("small cell hidden", c.get("note") == F.HIDE_NOTE or c.get("n", 0) >= 20, c)
section("B", b)


def c():
    blob = text + open(OUT).read()
    ok("no ticker", "KXNBA" not in blob and "KXMVE" not in blob)
    ok("no date", not re.search(r"20\d\d-\d\d-\d\d", blob))
    ok("safe line", "safe to send" in text)
section("C", c)


def d():
    c2 = F.cell([("g", 5.0, 1.0)] * 5, 50)
    ok("under 20 hidden", c2 == {"n": 5, "note": F.HIDE_NOTE}, c2)
    ok("cents_up", F.cents_up(0.101) == 0.11 and F.cents_up(0.10) == 0.10)
    ok("bucket pick", F.pick(F.STAKE_B, 3.0) == "$2-5" and F.pick(F.PRICE_B, 0.9) == "85c+")
section("D", d)


def e():
    P2 = os.path.join(TMP, "nopaper.db"); build(P2, paper=False)
    code2, S2, _ = runit(P2)
    ok("no sb_paper degrades", code2 == 0 and "skipped" in S2["part_b_few_strategic_bets"]["paper_book"])
    P3 = os.path.join(TMP, "empty.db"); sqlite3.connect(P3).close()
    code3, S3, t3 = runit(P3)
    ok("empty db degrades", code3 == 0 and "skipped" in S3["part_a_fees"])
    code4, _, t4 = runit(os.path.join(TMP, "nope.db"))
    ok("missing file", code4 == 2 and "cannot open" in t4)
    P5 = os.path.join(TMP, "dbl.db"); build(P5, combo_mult=2.0)
    _, S5, _ = runit(P5)
    r = S5["part_a_fees"]["formula_check"]["kinds"]["combo"]["ratio_recorded_to_unrounded_formula"]
    ok("double combo fee read as ~2", 1.8 < r < 2.3, r)
section("E", e)


def f():
    P6 = os.path.join(TMP, "zero.db"); build(P6, combo_mult=0.0)
    _, S6, _ = runit(P6)
    k = S6["part_a_fees"]["formula_check"]["kinds"]["combo"]
    ok("zero-fee combos read as ratio ~0", k["ratio_recorded_to_unrounded_formula"] < 0.05, k)
    ok("zero-fee rows counted", k["of_which_zero_entry_fee"] == 30, k)
    u = S6["combo_fee_ratio_used_in_part_b"]
    ok("part B uses ~0, not 1", u["ratio_to_unrounded_formula"] < 0.05 and "measured" in u["why"], u)
section("F", f)
