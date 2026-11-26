# CHECK: group=engine
# tools/combo_trail.py on a synthetic history file and decision log: finds the Nuggets combo (case-insensitive, by team
# name decoded from the leg tickers), skips an unrelated combo and one far from the date, prints legs by name, cost, pays,
# the REAL vs estimate offers, every auto-sell decision with its reason and the ride setting, the peak/cost/line summary,
# at most ~60 timeline lines, saves the same text to --out, never writes to the history file (byte-identical), shows no
# order id / key, and missing tables degrade with a message.
import os, io, re, json, hashlib, sqlite3, tempfile, importlib.util, contextlib, traceback
REPO = os.environ.get("REPO") or os.path.abspath("../..")
spec = importlib.util.spec_from_file_location("X", os.path.join(REPO, "tools", "combo_trail.py"))
X = importlib.util.module_from_spec(spec); spec.loader.exec_module(X)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
TMP = tempfile.mkdtemp()
T0 = 1795_000_000          # an arbitrary base time; the day is taken from the leg ticker, not from this
DAY = "2026-11-23"
NUG, CHI, LAL = "KXNBAGAME-26NOV23DENLAL-DEN", "KXNFLGAME-26NOV23KCDEN-KC", "KXNBAGAME-26NOV23LALBOS-LAL"
COMBO, OTHER, FAR = "KXMVECROSS-AAAA111111", "KXMVECROSS-BBBB222222", "KXMVECROSS-CCCC333333"
SECRET = "0123456789abcdef0123456789abcdef0123456789"


def build(path, tables=True):
    db = sqlite3.connect(path)
    if tables:
        db.executescript("""
        create table bets(combo text primary key, first_seen real, cost real, pays real, legs text, sports text, status text,
          back real, settled real, p_first real);
        create table offers(ts real, combo text, p real, pays real, hold real, offer real, real_offer int, verdict text);
        create table ticks(ts real, ticker text, chance real, state text, score text);
        create table events(ts real, kind text, combo text, text text);
        create table sell_log(ts real, ticker text, result text, why text, kind text, side text, offer real, cost real,
          pays real, frac real, chance real, by text, combo text, outcome text, held real, done real, live int, ask real);
        create table ledger(ticker text primary key, kind text, league text, side text, cost real, back real, fees real,
          sold_back real, sell_fees real, n_sold real, status text, opened real, closed real, legs text, outcome text,
          held real, seen real, nf int, n_bought real, unit_cost real);""")
        db.execute("insert into bets values(?,?,?,?,?,?,?,?,?,?)", (COMBO, T0, 5.0, 40.0, json.dumps([NUG, CHI]), "nba,nfl", "lost", 0, T0 + 9e4, .2))
        db.execute("insert into bets values(?,?,?,?,?,?,?,?,?,?)", (OTHER, T0, 5.0, 20.0, json.dumps([LAL]), "nba", "won", 20, T0 + 9e4, .3))
        db.execute("insert into bets values(?,?,?,?,?,?,?,?,?,?)", (FAR, T0, 5.0, 20.0, json.dumps(["KXNBAGAME-26OCT01DENLAL-DEN"]), "nba", "won", 20, 1.0, .3))
        for i in range(300):          # many offers: the timeline must be sampled, not dumped
            db.execute("insert into offers values(?,?,?,?,?,?,?,?)", (T0 + i * 60, COMBO, .5, 40, 6.0, 3.0 + (i == 151) * 4 if i % 2 else 2.5, i % 2, "hold"))
        db.execute("insert into ticks values(?,?,?,?,?)", (T0 + 5, NUG, 0.0, "final", "99-101"))
        db.execute("insert into events values(?,?,?,?)", (T0 + 9e4, "settled", COMBO, "lost"))
        db.execute("insert into sell_log(ts,ticker,result,why,combo,offer,by) values(?,?,?,?,?,?,?)", (T0 + 30, COMBO, "failed", "no buyer", "Combo 3", 6.5, SECRET))
        db.execute("insert into ledger(ticker,kind,cost,back,status,opened,legs,outcome) values(?,?,?,?,?,?,?,?)", (COMBO, "combo", 5.0, 0, "lost", T0, json.dumps([NUG, CHI]), "lost"))
    db.commit(); db.close()


def run(db, log, team="nuggets", out=None, date=DAY):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = X.run(db, [log], team, date, out)
    return code, buf.getvalue()


def main():
    p, lp, out = os.path.join(TMP, "h.db"), os.path.join(TMP, "log.jsonl"), os.path.join(TMP, "summary.txt")
    build(p)
    with open(lp, "w") as f:
        for r in ({"combo": "Combo 3", "ticker": COMBO, "result": "skipped", "why": "waiting: offer below the sell line", "offer": 4.1, "line": 7.5, "ride": "Steady", "at": T0 + 100, "order_id": SECRET},
                  {"combo": "Combo 3", "ticker": COMBO, "result": "skipped", "why": "ride setting holds it", "offer": 4.9, "line": 7.5, "ride": "Ride it out", "at": T0 + 200}):
            f.write(json.dumps(r) + "\n")
    # a deadline in the past (the app writes ts as epoch): window comes from the ticker date, so the fixed T0 is fine
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    code, txt = run(p, lp, "NuGGets", out)
    ok("A exit 0 and the Nuggets combo is found by team name, case-insensitive", code == 0 and "Denver Nuggets to win" in txt, txt[:300])
    ok("B legs by name plus the other leg", "Kansas City Chiefs to win" in txt)
    ok("C cost and pays shown", "cost $5.00, pays $40.00" in txt)
    ok("D the app's own 'Combo 3' name is tied back", "Combo 3" in txt)
    ok("E real vs estimate offers both labelled", "REAL Kalshi offer" in txt and "estimate (no Kalshi quote)" in txt)
    ok("F decisions with reason, sell line and ride shown", "SKIPPED" in txt and "offer below the sell line" in txt and "sell line $7.50" in txt and "ride=Steady" in txt and "ride=Ride it out" in txt, txt[-900:])
    ok("G the failed sale from the history file is shown", "FAILED" in txt and "no buyer" in txt)
    ok("H summary: peak real offer, cost, sell line, never reached", "peak real Kalshi offer $7.00" in txt and "highest sell line $7.50" in txt and "never reached the sell line" in txt, txt[-700:])
    ok("I final outcome", "final outcome: lost" in txt and "never auto-sold" in txt)
    ok("J unrelated and far-away combos are left out", "Lakers" not in txt and "Oct" not in txt and "CCCC" not in txt and "BBBB" not in txt)
    tl = [l for l in txt.splitlines() if l.startswith("    ") and re.search(r"\d\d:\d\d:\d\d", l)]
    ok("K timeline sampled to <= 60 lines even with 300 offers", 20 < len(tl) <= 60, len(tl))
    ok("L no order id, key or long token leaked", SECRET not in txt and "order_id" not in txt)
    ok("M saved to --out, same text", open(out).read().strip() == txt.split("\nsaved to")[0].strip())
    ok("N history file byte-identical (read-only)", hashlib.sha256(open(p, "rb").read()).hexdigest() == h0)
    try:
        sqlite3.connect("file:" + p + "?mode=ro", uri=True).execute("create table z(a)")
        ok("O (sanity) ro URI refuses writes", False)
    except sqlite3.OperationalError:
        ok("O (sanity) ro URI refuses writes", True)
    code, txt2 = run(p, lp, "warriors", None)
    ok("P no match prints a clear line", code == 0 and "No combos or bets" in txt2)
    code, txt3 = run(p, lp, "nuggets", None, date="nope")
    ok("Q bad date is a message, not a crash", code == 2)
    p2 = os.path.join(TMP, "empty.db"); build(p2, tables=False)
    code, txt4 = run(p2, os.path.join(TMP, "missing.jsonl"), "nuggets", None)
    ok("R missing tables and log degrade with skipped lines", code == 0 and "skipped:" in txt4)
    src = open(os.path.join(REPO, "tools", "combo_trail.py")).read()
    ok("S source opens mode=ro and has no write SQL or network", "mode=ro" in src and not re.search(r"(insert into|update \w+ set|delete from|create table|alter table|urllib.request|requests|socket)", src, re.I))


try:
    main()
except Exception:
    print("FAIL combo_trail raised: " + traceback.format_exc().strip().splitlines()[-1])
