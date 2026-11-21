# The Live hero chart's profit line (#221): display only, built from the history file, never raises.
#  A  empty history; every bet open all window; a bet bought mid-window; a bet open at the start with a gain (rebased)
#  B  sold early (no spike or dip as it leaves, cash placed where its stake left), settled win via the over/limbo
#     columns, settled loss from `bets` alone, bought and sold between two pulse rows
#  C  rough history (rows from before pulse_more), the flat run to now after a 0/0 row, thinning keeps the end
#  D  record_view writes pulse_more and one 0/0 row once everything is gone; errors and the cache
import os, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.HERE = tempfile.mkdtemp()
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
T = 2_000_000_000.0
S0 = T - 16 * 3600
near = lambda a, b: a is not None and abs(a - b) < 0.006


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def fresh():
    E.STORE["db"] = None
    E.STORE.pop("ledger_ok", None)
    E.store_open(os.path.join(tempfile.mkdtemp(), "h.db"))
    E._ledger_table()
    E.PNL.clear()


def pulse(ts, worth, staked, more=None):
    E.store_x("insert into pulse values(?,?,?)", (ts, worth, staked))
    if more is not None:
        E.store_x("insert into pulse_more values(?,?,?)", (ts, more[0], more[1]))


def ledger(t, cost, back, closed):
    E.store_x("insert into ledger(ticker, kind, cost, back, status, closed) values(?,?,?,?,?,?)",
              (t, "win", cost, back, "won" if back else "lost", closed))


def ser(**kw):
    return E.pnl_series(now=T, max_age=0, **kw)


def a():
    fresh()
    v = ser()
    ok("A1 no history: an empty series, not an error", v["pts"] == [] and v["t0"] is None)
    fresh()
    pulse(S0 - 60, 10, 10, (0, 0)); pulse(T - 3600, 12, 10, (0, 0)); pulse(T - 60, 9, 10, (0, 0))
    v = ser(); p = v["pts"]
    ok("A2 all open: starts at $0 at the window's start", p[0][0] == round(S0) and p[0][1] == 0 and near(p[0][2], 10), p[:2])
    ok("A3 all open: P/L follows worth − cost (+$2, then −$1), staked 10", near(p[1][1], 2) and near(p[-1][1], -1) and near(p[-1][2], 10), p)
    fresh()
    pulse(S0 - 60, 10, 10, (0, 0)); pulse(T - 3600, 14.8, 15, (0, 0))
    p = ser()["pts"]
    ok("A4 a bet bought mid-window counts from what was paid (−$0.20), staked steps 10 → 15",
       near(p[-1][1], -0.2) and near(p[0][2], 10) and near(p[-1][2], 15), p)
    fresh()
    pulse(S0 - 60, 14, 10, (0, 0)); pulse(T - 3600, 15, 10, (0, 0))
    p = ser()["pts"]
    ok("A5 open at the start with a $4 gain: rebased to $0, then +$1 (its worth then is the basis)",
       p[0][1] == 0 and near(p[-1][1], 1), p)
section("A", a)


def b():
    fresh()                                          # sold early: $10 in, worth 12.8, cashed out for $13 ($10.10 with fees)
    sell = T - 5 * 3600
    pulse(S0 - 60, 10, 10, (0, 0)); pulse(sell - 120, 12.8, 10, (0, 0)); pulse(sell + 60, 0, 0, (0, 0))
    ledger("KXMVE-SOLD", 10.10, 13.0, sell - 30)
    v = ser(); p = v["pts"]
    at = {q[0]: q[1] for q in p}
    ok("B1 sold early: +$2.80 before, +$2.90 after (the sale's real gain over its last worth), no spike or dip",
       near(at.get(round(sell - 120)), 2.8) and near(at.get(round(sell + 60)), 2.9) and max(at.values()) <= 2.91 and min(at.values()) >= 0, p)
    ok("B2 its cash is placed where its stake left the pulse, not 90 s earlier", round(sell - 30) not in at, sorted(at))
    ok("B3 nothing open after: the line runs flat to now, staked $0", p[-1][0] == round(T) and near(p[-1][1], 2.9) and p[-1][2] == 0
       and v["end"] == round(T), p[-2:])
    fresh()                                          # a single bought mid-window, game over (limbo), then paid
    pulse(S0 - 60, 0, 0, (0, 0)); pulse(T - 4 * 3600, 4.5, 5, (0, 0)); pulse(T - 3 * 3600, 0, 0, (10, 5))
    pulse(T - 3 * 3600 + 600, 0, 0, (10, 5)); pulse(T - 2 * 3600, 0, 0, (0, 0))
    ledger("KXNBAGAME-26X-BOS", 5.07, 10.0, T - 2 * 3600 - 50)
    p = ser()["pts"]
    vals = [q[1] for q in p if q[0] >= T - 3 * 3600]
    ok("B4 settled win: −$0.50 while open, +$5 once over (waiting on Kalshi), +$4.93 paid, never a dip",
       near([q[1] for q in p if q[0] == round(T - 4 * 3600)][0], -0.5) and near(vals[0], 5) and near(p[-1][1], 4.93)
       and min(vals) >= 4.9, p)
    fresh()                                          # settled loss known only from the Mac's `bets` row
    pulse(S0 - 60, 3, 5, (0, 0)); pulse(T - 3600, 0, 0, (0, 0))
    E.store_x("insert into bets(combo, first_seen, cost, pays, status, back, settled) values(?,?,?,?,?,?,?)",
              ("KXMVE-LOST", S0 - 9000, 5, 20, "lost", 0, T - 3600 - 40))
    p = ser()["pts"]
    ok("B5 settled loss from `bets`: open at the start worth $3 on $5, lost: −$3 (from its worth then)", near(p[-1][1], -3), p)
    fresh()                                          # bought and sold between two pulse rows: counted when Kalshi says
    pulse(S0 - 60, 10, 10, (0, 0)); pulse(T - 3600, 10, 10, (0, 0)); pulse(T - 1800, 10, 10, (0, 0))
    ledger("KXNHLGAME-26X-TOR", 4.0, 5.5, T - 2700)
    p = ser()["pts"]
    at = {q[0]: q[1] for q in p}
    ok("B6 bought and sold between rows: +$1.50 from its own time", near(at.get(round(T - 2700)), 1.5) and near(p[-1][1], 1.5), p)
    ok("B7 a bet that finished before the window isn't counted", ledger("KXOLD", 5, 0, S0 - 100) or near(ser()["pts"][-1][1], 1.5))
section("B", b)


def c():
    fresh()
    pulse(S0 - 60, 10, 10); pulse(T - 7200, 11, 10); pulse(T - 3600, 12, 10, (0, 0)); pulse(T - 60, 12.5, 10, (0, 0))
    v = ser()
    ok("C1 rows from before pulse_more: rough up to the newest of them", v["rough"] == round(T - 7200), v["rough"])
    fresh()
    pulse(S0 - 60, 10, 10, (0, 0)); pulse(T - 60, 10.5, 10, (0, 0))
    ok("C2 all rows complete: not rough", ser()["rough"] is None)
    fresh()
    for i in range(480):
        pulse(S0 + 60 + i * 120, 10 + (i % 7) * 0.1, 10, (0, 0))
    v = ser(points=150); p = v["pts"]
    ok("C3 thinned to at most 150 points (+ the newest), the newest kept", 100 <= len(p) <= 151 and p[-1][0] == round(S0 + 60 + 479 * 120), len(p))
    ok("C4 no baseline before the window: starts at the first row, at $0", p[0][1] == 0 and p[0][0] == round(S0 + 60), p[0])
    fresh()
    pulse(S0 - 60, 10, 10, (0, 0)); pulse(T - 3 * 3600, 0, 0, (0, 0))
    v = ser()
    ok("C5 a 0/0 row then nothing: the line runs to now", v["end"] == round(T) and v["pts"][-1][0] == round(T))
    pulse(T - 3 * 3600 + 120, 4, 5)                  # an older process (no pulse_more): not "nothing open"
    E.PNL.clear()
    v = ser()
    ok("C6 a row with no pulse_more never claims 'nothing open since'", v["end"] == round(T - 3 * 3600 + 120), v["end"])
section("C", c)


def d():
    fresh()
    E.STORE["last"] = {}
    single = {"t": "KXNBAGAME-26X-BOS", "ticker": "KXNBAGAME-26X-BOS", "state": "done", "res": "yes", "side": "yes",
              "pays": 10, "n": 10, "cost": 5, "worth": None}
    E.record_view({"combos": [], "singles": [single]})
    r = E.store_rows("select p.worth, p.staked, m.xworth, m.xcost from pulse p join pulse_more m on m.ts = p.ts")
    ok("D1 a finished single not yet paid: pulse unchanged (0/0), pulse_more holds $10 due on $5", len(r) == 1 and r[0]["worth"] == 0
       and r[0]["xworth"] == 10 and r[0]["xcost"] == 5, r)
    E.STORE["last"][("pulse",)] -= 200
    E.record_view({"combos": [], "singles": []})
    E.STORE["last"][("pulse",)] -= 200
    E.record_view({"combos": [], "singles": []})
    r = E.store_rows("select p.worth, p.staked, m.xworth, m.xcost from pulse p join pulse_more m on m.ts = p.ts order by p.ts")
    ok("D2 once everything is gone: one 0/0 row, then no more rows", len(r) == 2 and r[1]["xworth"] == 0 and r[1]["staked"] == 0, r)
    ok("D3 a lost limbo single is worth $0; one not decided yet its bid, else its cost",
       E._limbo_worth(dict(single, res="no")) == 0 and E._limbo_worth(dict(single, res=None, worth=3.2)) == 3.2
       and E._limbo_worth(dict(single, res=None)) == 5)
    fresh()
    pulse(S0 - 60, 10, 10, (0, 0)); pulse(T - 60, 11, 10, (0, 0))
    good = E.pnl_series(hours=16, points=150)
    again = E.pnl_series(hours=16, points=150)
    ok("D4 cached: a second call within 20 s is the same answer", good is again)
    real = E.store_rows
    E.store_rows = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk"))
    try:
        E.PNL[(16, 150)]["at"] -= 100
        v = E.pnl_series(hours=16, points=150)
        ok("D5 a read error never raises: the last good series comes back", v is good)
        E.PNL.clear()
        v = E.pnl_series(hours=16, points=150)
        ok("D6 a read error with nothing cached: an empty series", v["pts"] == [])
    finally:
        E.store_rows = real
    db = E.STORE["db"]; E.STORE["db"] = None
    ok("D7 no history file: empty", E.pnl_series(now=T, max_age=0)["pts"] == [])
    E.STORE["db"] = db
    src = open("wahome/engine.py").read()
    body = src[src.index("def _pnl_series("):src.index("def game_story(")]
    ok("D8 read-only: the series never writes a row (only creates missing tables)",
       "insert" not in body.lower() and "update " not in body.lower() and "delete" not in body.lower())
section("D", d)
