# CHECK: group=engine
# #375 paper test: smart sell's profit line (floor x cost) is above what a favorite bought above ~1/floor can sell for,
# so it can never take a profit. exit_cap_shadow RECORDS what a capped line would have done beside today's rule.
#  A  default OFF: nothing is written
#  B  ON: a favorite whose line is out of reach gets a row (decision, price, time) for today's rule and the capped rule
#  C  the live decision is byte-for-byte the same with the switch on or off (single_sell_reason over a grid, the
#     peaks and settings it could touch, and smart_sell_singles' orders and log), and nothing live passes `cap`
#  D  it never raises, writes nothing for a reachable line, is throttled, and nothing reads the table back
import os, re, time, copy, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
src = open(spec.origin).read()
T = "KXNBAGAME-26NOV19LALBOS-LAL"


def fav(cost=8.0, n=10.0, chance=0.9, state="live"):
    return {"t": T, "ticker": T, "side": "yes", "state": state, "n": n, "cost": cost, "chance": chance, "label": "Lakers",
            "kind": "win", "sport": "nba"}


def rows():
    try:
        return E.store_rows("select * from exit_cap_shadow order by ts")
    except Exception:
        return []


E.CFG.update(smart_sell=True, ride=2)
E.MINE.setdefault("peak", {})
BID = 0.93
# ---- A: off by default
ok("A the switch defaults to OFF", E.CFG.get("exit_cap_shadow") is False)
E.EXIT_CAP_SEEN.clear()
ok("A off: no row, False", E.exit_cap_shadow(fav(), BID, now=1000.0) is False and not rows())

# ---- B: on
E.CFG["exit_cap_shadow"] = True
x = fav()
top = E.sell_top(10.0, single=True)
live_why, live_line = E.single_sell_reason(x, BID, None, track=False)
ok("B setup: today's line is above what the bet can sell for (so smart sell can never fire)",
   live_why is None and E.sell_line_shown(live_line, top)[1], (live_why, live_line, top))
ok("B on: a row is written", E.exit_cap_shadow(x, BID, now=1000.0) is True)
r = rows()
ok("B one row with the time, the sale price after fees, today's answer and the paper answer",
   len(r) == 1 and r[0]["ts"] == 1000.0 and r[0]["ticker"] == T and r[0]["live_decision"] == "hold"
   and abs(r[0]["net"] - round(10 * (BID - E.single_fee(BID, 10)), 4)) < 1e-9 and r[0]["alt_decision"] in ("hold", "smart"), r)
ok("B the paper line is capped under the top sale price", r and r[0]["cap"] < r[0]["top"] and r[0]["alt_line"] <= r[0]["cap"] + 1e-9, r)
# a bid high enough that the capped line is met: the paper rule would sell
E.EXIT_CAP_SEEN.clear()
E.exit_cap_shadow(x, 0.97, now=2000.0)
hi = [q for q in rows() if q["ts"] == 2000.0]
ok("B a bid above the capped line: the paper rule says smart, today's says hold", hi and hi[0]["alt_decision"] == "smart"
   and hi[0]["live_decision"] == "hold", hi)

# ---- C: the live decision is untouched
grid = [fav(cost=c, n=n, chance=q, state=s) for c in (3.0, 6.0, 8.0, 9.0) for n in (4.0, 10.0) for q in (0.3, 0.55, 0.9)
        for s in ("live", "pre")]
bids = (0.2, 0.55, 0.93, 0.97)


def snapshot():
    return [E.single_sell_reason(g, b, None, track=False) for g in grid for b in bids]


E.CFG["exit_cap_shadow"] = False
off = snapshot()
E.CFG["exit_cap_shadow"] = True
peak0, cfg0 = copy.deepcopy(E.MINE["peak"]), {k: v for k, v in E.CFG.items() if k != "exit_cap_shadow"}
on = snapshot()
for g in grid:
    for b in bids:
        E.exit_cap_shadow(g, b, now=3000.0 + b)           # the recorder runs between the live calls
on2 = snapshot()
ok("C single_sell_reason answers are identical with the switch off, on, and after the recorder ran", off == on == on2)
ok("C the recorder touched no peak and no other setting", E.MINE["peak"] == peak0 and
   {k: v for k, v in E.CFG.items() if k != "exit_cap_shadow"} == cfg0)
ok("C nothing live passes `cap=` to single_sell_reason (only the recorder)",
   len(re.findall(r"(?<!def )single_sell_reason\([^)]*cap=", src)) == 1 and "cap=cap" in src)
ok("C track=True (the live default) is untouched: the recorder always passes track=False",
   src.count("single_sell_reason(x, bid, None, track=False") >= 2)

sold, logs = [], []
E.sell_single_now = lambda t, side, n, bid: (sold.append((t, side, n, bid)), (n, None))[1]
E.log_decision = lambda rec: logs.append({k: v for k, v in rec.items() if k != "at"})
E.resting_single_sells = lambda: {}
E.order_unsure = lambda t: False
E.auto_cap_reached = lambda: False
E.hands_off = lambda t: False
E.sell_held = lambda out: False
E.sell_backoff_left = lambda *a: 0
E.CFG.update(stop_loss_mode="tune")


def run(bid, switch):
    E.CFG["exit_cap_shadow"] = switch
    sold.clear(); logs.clear(); E.MINE["peak"].clear()
    E.SINGLES.update(at=time.time(), items=[fav(cost=8.0, n=10.0, chance=0.9)],
                     mk={T: {"yes_bid_dollars": str(bid), "yes_ask_dollars": str(round(bid + 0.01, 2))}})
    out = E.smart_sell_singles()
    E.open_singles = E.open_singles                    # (not called here: smart_sell_singles reads SINGLES)
    return (list(sold), copy.deepcopy(logs), out, copy.deepcopy(E.MINE["peak"]))


for b in (0.5, 0.93, 0.97):
    ok(f"C smart_sell_singles at a {b} bid: orders, log, messages and peaks identical with the switch on or off",
       run(b, False) == run(b, True))
ok("C and today's rule sold nothing at 93c / 97c (the line is out of reach), with the switch on",
   not run(0.93, True)[0] and not run(0.97, True)[0])

# ---- D: robustness
E.CFG["exit_cap_shadow"] = True
E.EXIT_CAP_SEEN.clear()
n0 = len(rows())
ok("D a reachable line (cheap bet) writes nothing", E.exit_cap_shadow(fav(cost=3.0, chance=0.9), BID, now=5000.0) is False
   and len(rows()) == n0)
ok("D a long shot (under 50%) writes nothing", E.exit_cap_shadow(fav(chance=0.3), BID, now=5000.0) is False)
ok("D junk input never raises", E.exit_cap_shadow(None, BID) is False and E.exit_cap_shadow({}, BID) is False
   and E.exit_cap_shadow({"t": T, "n": "x", "cost": "y", "chance": 0.9}, BID) is False)
ok("D no bid: nothing", E.exit_cap_shadow(fav(), None, now=5000.0) is False)
E.EXIT_CAP_SEEN.clear()
ok("D first write", E.exit_cap_shadow(fav(), BID, now=6000.0) is True)
ok("D same answer 10 s later: throttled", E.exit_cap_shadow(fav(), BID, now=6010.0) is False)
ok("D same answer after the gap: written again", E.exit_cap_shadow(fav(), BID, now=6000.0 + E.EXIT_CAP_EVERY + 1) is True)
ok("D a changed answer is written at once", E.exit_cap_shadow(fav(), 0.97, now=6000.0 + E.EXIT_CAP_EVERY + 5) is True)
db = E.STORE["db"]
E.STORE["db"] = None
ok("D no history open: False, no raise", E.exit_cap_shadow(fav(), BID, now=7000.0) is False)
E.STORE["db"] = db
real = E.single_sell_reason
E.single_sell_reason = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
ok("D a failure inside is swallowed", E.exit_cap_shadow(fav(), BID, now=8000.0) is False)
E.single_sell_reason = real
E.EXIT_CAP_PRUNE["at"] = 0.0
E.store_x("insert into exit_cap_shadow(ts, ticker) values(1.0, 'OLD')")
E.EXIT_CAP_SEEN.clear()
E.exit_cap_shadow(fav(), BID, now=9000.0 + E.EXIT_CAP_KEEP)
ok("D old rows are pruned", not E.store_rows("select 1 from exit_cap_shadow where ticker='OLD'"))
mentions = [m.start() for m in re.finditer(r"exit_cap_shadow", src)]
reads = re.findall(r"select[^\n\"]*from exit_cap_shadow", src, flags=re.I)
ok("D nothing reads the table back into a decision (no select outside the pruning subqueries)",
   all("count(*)" in r or "rowid" in r for r in reads))
