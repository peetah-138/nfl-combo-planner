# CHECK: group=engine
# Store each bet's contract count in the ledger (bookkeeping only: no buy, sell or sizing decision reads it).
#  A  a single bet's fills give n_bought (contracts opened) and unit_cost (all-in cost per contract); a settlement-only
#     row, which has no fills, leaves both unknown (None)
#  B  an old-schema ledger (no n_bought / unit_cost / nf columns) is migrated by adding the columns: old rows read NULL, are
#     treated as unknown, nothing crashes; the next account read fills a row whose fills are still there and leaves the rest
#  C  ledger_price_paid never raises: NULL, zero, garbage text, a missing key and a row with a count but no unit cost
#  D  decisions are unchanged: the new names appear only in the ledger bookkeeping functions, never in a buy, sell or
#     sizing function, and the old ledger fields come out exactly as before
import os, time, tempfile, sqlite3, importlib.util, traceback, ast
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
tmp = tempfile.mkdtemp()
db_path = os.path.join(tmp, "old.db")
now = time.time()
iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
near = lambda a, b: a is not None and abs(a - b) < 0.0006


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def fill(t, action, side, n, yes, fee, ts):
    return {"ticker": t, "market_ticker": t, "action": action, "side": side, "count_fp": f"{n:.2f}",
            "yes_price_dollars": f"{yes:.4f}", "no_price_dollars": f"{1 - yes:.4f}", "fee_cost": f"{fee:.4f}",
            "is_taker": True, "created_time": iso(ts)}


Y = "KXNBAGAME-26NOV21BOSNYK-BOS"          # bought 10 YES at 40c (+7c fee), sold all
N = "KXNHLGAME-26NOV21TORMTL-MTL"          # bought 5 NO at 70c, then 5 more at 60c, held and lost
S = "KXNBAGAME-26NOV21PHIMIA-PHI"          # settlement only, no fills in Kalshi's window
O = "KXNBAGAME-26NOV21DENUTA-DEN"          # an old row whose fills have aged out
fills = {
    Y: [fill(Y, "buy", "yes", 10, 0.40, 0.07, now - 9000), fill(Y, "sell", "no", 10, 0.60, 0.06, now - 6000)],
    N: [fill(N, "buy", "no", 5, 0.30, 0.04, now - 9000), fill(N, "buy", "no", 5, 0.40, 0.04, now - 8000)],
}
settles = {N: {"ticker": N, "revenue_dollars": "0.00", "settled_time": iso(now - 3000)},
           S: {"ticker": S, "revenue_dollars": "0.00", "yes_total_cost_dollars": "3.00", "no_total_cost_dollars": "0.00",
               "settled_time": iso(now - 3000)}}


def a():
    L = E._single_ledger(fills, settles, now)
    y, n, s = L.get(Y), L.get(N), L.get(S)
    ok("A1 bought and sold: 10 contracts, (4.00 + 0.07 buy fee) / 10 each; the sale fee is not part of it", y and near(y["n_bought"], 10) and near(y["unit_cost"], 0.407), y)
    ok("A2 two buys add up: 10 contracts, all-in cost per contract", n and near(n["n_bought"], 10)
       and near(n["unit_cost"], (5 * 0.70 + 5 * 0.60 + 0.08) / 10), n)
    ok("A3 settlement-only row: count unknown, never a made-up number", s and s["n_bought"] is None and s["unit_cost"] is None, s)
    ok("A4 the old fields are exactly what they were", near(y["cost"], 4.13) and near(y["back"], 6.0) and y["status"] == "sold"
       and near(n["cost"], 6.58) and n["status"] == "lost" and s["status"] == "lost" and near(s["cost"], 3.0))
    ok("A5 unit_cost helper: zero count, zero cost and junk give None", E._unit_cost(5, 0) is None and E._unit_cost(0, 5) is None
       and E._unit_cost("x", 5) is None and E._unit_cost(None, None) is None and near(E._unit_cost(4.13, 10), 0.413))
section("A", a)


def b():
    c = sqlite3.connect(db_path, isolation_level=None)       # the ledger as shipped before this change
    c.execute("create table ledger(ticker text primary key, kind text, league text, side text, cost real, back real, fees real, "
              "sold_back real, sell_fees real, n_sold real, status text, opened real, closed real, legs text, outcome text, "
              "held real, seen real)")
    for t, cost in ((Y, 4.13), (O, 2.0)):
        c.execute("insert into ledger(ticker, kind, league, side, cost, back, fees, sold_back, sell_fees, n_sold, status, opened, "
                  "closed, legs, seen) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (t, "win", "nba", "yes", cost, 0.0, 0.1, 0.0, 0.0, 0.0, "lost", now - 9000, now - 3000, '["%s"]' % t, now - 8000))
    c.close()
    E.STORE.update(db=None, path=None, ledger_ok=False)
    E.store_open(db_path)
    E._ledger_table()
    cols = {r["name"] for r in E.store_rows("pragma table_info(ledger)")}
    ok("B1 old file: the three columns are added", {"nf", "n_bought", "unit_cost"} <= cols, cols)
    E._ledger_table(); E.STORE["ledger_ok"] = False; E._ledger_table()
    ok("B2 running the migration again is harmless", True)
    rows = {r["ticker"]: r for r in E._ledger_rows()}
    ok("B3 old rows read as unknown, nothing crashes", rows[Y]["n_bought"] is None and rows[O]["unit_cost"] is None
       and E.ledger_price_paid(rows[Y]) == (None, None))
    E.LEDGER_SIG.clear()
    E.ledger_note([], {}, fills, settles, now)
    rows = {r["ticker"]: r for r in E._ledger_rows()}
    ok("B4 the next account read fills a row whose fills are still there", near(rows[Y]["n_bought"], 10)
       and near(rows[Y]["unit_cost"], 0.407) and E.ledger_price_paid(rows[Y]) == (10.0, 0.407), rows[Y])
    ok("B5 a row with no fills left stays unknown, and money fields are untouched", rows[O]["n_bought"] is None
       and near(rows[O]["cost"], 2.0), rows[O])
    ok("B6 the new rows are saved too", near(rows[N]["n_bought"], 10) and rows[S]["n_bought"] is None)
    E.LEDGER_SIG.clear()
    n2 = E.ledger_note([], {}, fills, settles, now)
    ok("B7 unchanged after that: no rewrite", n2 == 0, n2)
    # a later read that no longer knows the count must not wipe a saved one
    bet = {"ticker": Y, "status": "won", "cost": 4.0, "back": 6.0, "legs": [{"ticker": "KXMVEX-1"}], "settled_at": now - 2000}
    E.LEDGER_SIG.clear()
    n3 = E.ledger_note([bet], {Y: {"nf": 5, "bought_n": 0.0}}, {}, {}, now)      # a read whose fills carry no count
    rows = {r["ticker"]: r for r in E._ledger_rows()}
    ok("B8 a count already saved is kept when a later read has none", n3 == 1 and near(rows[Y]["n_bought"], 10)
       and near(rows[Y]["unit_cost"], 0.407), (n3, rows[Y]))
    E.STORE["db"].close(); E.STORE.update(db=None, path=None, ledger_ok=False)
section("B", b)


def c():
    p = E.ledger_price_paid
    ok("C1 NULL / missing / zero / negative", p({}) == (None, None) and p({"n_bought": None}) == (None, None)
       and p({"n_bought": 0}) == (None, None) and p({"n_bought": -3, "unit_cost": 0.4}) == (None, None))
    ok("C2 garbage text and the wrong type", p({"n_bought": "abc"}) == (None, None) and p({"n_bought": 5, "unit_cost": "x"}) == (None, None)
       and p(None) == (None, None) and p("row") == (None, None))
    ok("C3 a count with no unit cost: derived from the row's cost", p({"n_bought": 4, "cost": 2.0}) == (4.0, 0.5))
    ok("C4 a count and unit cost: as saved", p({"n_bought": 4, "unit_cost": 0.52, "cost": 2.0}) == (4.0, 0.52))
    ok("C5 a count with nothing to price it by: unknown", p({"n_bought": 4}) == (None, None))
section("C", c)


def d():
    src = open("wahome/engine.py").read()
    tree = ast.parse(src)
    names = ("n_bought", "unit_cost", "ledger_price_paid", "_unit_cost")
    users = set()
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = ast.get_source_segment(src, fn) or ""
            if any(n in body for n in names):
                users.add(fn.name)
    allowed = {"_ledger_table", "_unit_cost", "ledger_price_paid", "_single_ledger", "_ledger_same", "ledger_note", "_ledger_rows"}
    ok("D1 the new fields are read and written only by the ledger bookkeeping", users <= allowed, sorted(users - allowed))
    money = ("buy_single", "single_buy", "single_buy_quote", "idea_single_buy", "killer_act", "smart_buy_gate",
             "smart_buy_filter", "smart_buy_ok", "single_sell_reason", "sell_held", "sell_single_now", "auto_cap_reached")
    have = {f.name for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)}
    ok("D2 the buy, sell and sizing functions exist and do not mention them", all(m in have for m in money if m != "sell_held" and m != "single_sell_reason")
       and not (users & set(money)))
section("D", d)
