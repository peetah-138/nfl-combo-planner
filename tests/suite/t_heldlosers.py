# CHECK: group=engine
# Results › How it ended: the plain lines on bets held to the end (#461). Display only: wins vs losses, the break-even
# win rate from what was paid, and whether lost holds ever traded above their cost (combos' real offers).
#  A  _in_n: a rate as 'N in M' or a percent
#  B  _held_summary on made-up rows: counts, break-even, small sample, price history, and every empty / zero case
#  C  profit_board end to end from a seeded ledger + bets + offers (no change to any other group's numbers)
import os, time, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SELL_LOG = os.path.join(E.HERE, "sell.jsonl")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
now = time.time()


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def row(end, cost, pay=None, best=None, kind="combo", t="X"):
    return {"ticker": t, "kind": kind, "end": end, "cost": cost, "pay_known": pay, "best_offer": best}


def a():
    ok("A1 three in four", E._in_n(0.75) == "3 in 4")
    ok("A2 close to a simple fraction", E._in_n(0.34) == "1 in 3")
    ok("A3 otherwise a percent", E._in_n(0.02) == "2%" and E._in_n(0.5) == "1 in 2")
section("A", a)


def b():
    ok("B1 nothing held to the end: no summary, no crash", E._held_summary([]) is None
       and E._held_summary([row("smart", 5), row("you", 5)]) is None)
    rs = [row("won", 3, 10, t="a")] * 5 + [row("lost", 3, 4, best=3.5, t="b")] * 3 + [row("lost", 3, 4, best=2.0, t="c")] * 4 \
        + [row("lost", 3, None, kind="win", t="d")] * 5          # 5 won, 12 lost; the 5 singles have no price
    s = E._held_summary(rs)
    ok("B2 counts", s["n"] == 17 and s["won"] == 5 and s["lost"] == 12 and s["few"], s)
    ok("B3 break-even = paid per $1 of payout over the bets with a known payout (12 priced of 17)",
       abs(s["be"] - (5 * 3 + 7 * 3) / (5 * 10 + 7 * 4)) < 0.001 and s["priced"] == 12 and "price known for 12 of 17" in s["line"], s)
    ok("B4 the line is plain and starts with the record", s["line"].startswith("Won 5 of 17; at these prices you needed about "), s["line"])
    h = s["hist"]
    ok("B5 price history: 3 of 7 traded above cost, range, 5 singles with no price history",
       h["lost"] == 12 and h["seen"] == 7 and h["above"] == 3 and h["none"] == 5 and h["lo"] == h["hi"] == 0.5
       and "3 of 7 traded above what you paid before closing" in h["line"] and "5 with no price history" in h["line"], h)
    ok("B6 a range when the gaps differ", E._held_summary([row("lost", 2, 5, best=2.4), row("lost", 2, 5, best=5.1)])["hist"]["line"].count("to $3.10") == 1)
    ok("B7 small sample flags: the whole line under 20, the lost group under 20",
       s["few"] and h["few"] and not E._held_summary([row("won", 3, 10)] * 20)["few"])
    z = E._held_summary([row("lost", 3, None, kind="win")])
    ok("B8 no payout known anywhere: no break-even and no division by zero", z["be"] is None and "no break-even" in z["line"] and z["hist"]["seen"] == 0
       and "No price history" in z["hist"]["line"], z)
    ok("B9 a zero payout is not divided by", E._held_summary([row("won", 3, 0)])["be"] is None)
    ok("B10 nobody traded above cost: says so, no range", "0 of 1 traded above" in E._held_summary([row("lost", 3, 4, best=2.0)])["hist"]["line"]
       and "beat cost" not in E._held_summary([row("lost", 3, 4, best=2.0)])["hist"]["line"])
    ok("B11 only wins held: no lost line", "hist" not in E._held_summary([row("won", 3, 10)]))
    ok("B12 break-even never above 100%", E._held_summary([row("won", 12, 10)])["be"] == 1.0)
section("B", b)


def c():
    E._ledger_table()
    ins = ("insert or replace into ledger(ticker, kind, league, side, cost, back, fees, sold_back, sell_fees, n_sold, status, opened, closed, legs, seen) "
           "values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
    E.store_x(ins, ("KXMVE-W", "combo", "nba", "yes", 3.0, 10.0, .1, 0, 0, 0, "won", now - 9000, now - 3000, "[]", now))
    E.store_x(ins, ("KXMVE-L1", "combo", "nba", "yes", 3.0, 0.0, .1, 0, 0, 0, "lost", now - 9000, now - 3000, "[]", now))
    E.store_x(ins, ("KXMVE-L2", "combo", "nba", "yes", 3.0, 0.0, .1, 0, 0, 0, "lost", now - 9000, now - 3000, "[]", now))
    E.store_x(ins, ("KXNBAGAME-26NOV20BOSNYK-BOS", "win", "nba", "yes", 4.0, 0.0, .1, 0, 0, 0, "lost", now - 9000, now - 3000, "[]", now))
    for t, pays in (("KXMVE-W", 10), ("KXMVE-L1", 10), ("KXMVE-L2", 10)):
        E.store_x("insert or ignore into bets(combo, first_seen, cost, pays, legs, status) values(?,?,?,?,?,?)", (t, now - 9000, 3.0, pays, "[]", "pending"))
    E.store_x("insert into offers values(?,?,?,?,?,?,?,?)", (now - 5000, "KXMVE-L1", .3, 10, 1, 4.2, 1, "x"))
    E.store_x("insert into offers values(?,?,?,?,?,?,?,?)", (now - 5000, "KXMVE-L2", .3, 10, 1, 9.0, 0, "x"))     # not a real offer: ignored
    E.BOARD["at"] = 0
    bd = E.profit_board(now)
    hs = bd["periods"]["all"]["held"]
    ok("C1 board carries the held summary", hs and hs["n"] == 4 and hs["won"] == 1 and hs["lost"] == 3, hs)
    ok("C2 break-even from the three priced combos: $9 paid for $30", hs["priced"] == 3 and abs(hs["be"] - 0.3) < 0.001, hs)
    ok("C3 one lost combo had a real offer above cost; the other had none; the single has no history",
       hs["hist"]["above"] == 1 and hs["hist"]["seen"] == 1 and hs["hist"]["none"] == 2 and hs["hist"]["hi"] == 1.2, hs["hist"])
    en = {r["k"]: r for r in bd["periods"]["all"]["by"]["end"]}
    ok("C4 the 'How it ended' rows are as before", en["won"]["n"] == 1 and en["lost"]["n"] == 3 and "vs_n" not in en["lost"])
    E.store_x("delete from ledger")
    E.BOARD["at"] = 0
    ok("C5 an empty ledger: no held summary, no crash", (E.profit_board(now) or {}).get("periods", {}).get("all", {}).get("held") is None)
section("C", c)
