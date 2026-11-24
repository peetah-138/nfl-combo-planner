# CHECK: group=engine
# Two fixes from the #332 analysis. No real orders and no Kalshi: every fill is a fixture, every trading call is faked.
#  A  (#333) the ledger reads a single bet's sale as a sale, in the shape Kalshi's V2 fills really use: a sale of YES
#     reported as "sell no" at the YES price (as the app's combo cash-outs always were), a sale of NO reported as
#     "sell yes", the legacy "sell yes"/"sell no", buying NO, closing by buying the other side, and fills that carry
#     only the YES-book direction (book_side / outcome_side)
#  B  (#333) a row the old code wrote wrong is put right on the next account read; unchanged rows are not rewritten
#  C  (#334) smart sell never offers a leftover under one contract (Kalshi's minimum), and after 3 failed identical
#     sales it waits 10 minutes, then an hour after every further failure, logged once; success resets it
import os, time, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SELL_LOG = os.path.join(E.HERE, "sell.jsonl")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
near = lambda a, b: a is not None and abs(a - b) < 0.006
now = time.time()
iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def fill(t, action, side, n, yes, fee, ts, **kw):
    """A fill in Kalshi's dollar shape (count_fp, *_dollars), as /portfolio/fills sends it."""
    f = {"ticker": t, "market_ticker": t, "action": action, "side": side, "count_fp": f"{n:.2f}",
         "yes_price_dollars": f"{yes:.4f}", "no_price_dollars": f"{1 - yes:.4f}", "fee_cost": f"{fee:.4f}",
         "is_taker": True, "created_time": iso(ts)}
    if action is None:
        f.pop("action")
    f.update(kw)
    return f


Y = "KXNBAGAME-26NOV21BOSNYK-BOS"          # bought YES, smart sold: V2 reports the sale as "sell no" at the YES price
Q = "KXNHLGAME-26NOV21TORMTL-MTL"          # bought NO, smart sold: V2 reports it as "sell yes"
L1 = "KXNBAGAME-26NOV21LALGSW-LAL"         # legacy "sell yes" of a YES bet (as before)
L2 = "KXNFLSPREAD-26NOV22KCBUF-KC3"        # bought NO, legacy "sell no" (as before)
X = "KXNBATOTAL-26NOV21BOSNYK-220"         # bought YES, closed by buying NO at 70c (YES 30c)
B = "KXNBAGAME-26NOV21PHIMIA-PHI"          # fills with only the YES-book direction: bid, then ask
P = "KXNBAGAME-26NOV21DENUTA-DEN"          # part sold, the rest held and won
fills = {
    Y: [fill(Y, "buy", "yes", 10, 0.40, 0.07, now - 9000), fill(Y, "sell", "no", 10, 0.60, 0.06, now - 6000)],
    Q: [fill(Q, "buy", "no", 5, 0.30, 0.04, now - 9000), fill(Q, "sell", "yes", 5, 0.20, 0.03, now - 6000)],
    L1: [fill(L1, "buy", "yes", 4, 0.50, 0.03, now - 9000), fill(L1, "sell", "yes", 4, 0.70, 0.02, now - 6000)],
    L2: [fill(L2, "buy", "no", 6, 0.45, 0.04, now - 9000), fill(L2, "sell", "no", 6, 0.35, 0.03, now - 6000)],
    X: [fill(X, "buy", "yes", 3, 0.50, 0.02, now - 9000), fill(X, "buy", "no", 3, 0.30, 0.02, now - 6000)],
    B: [fill(B, None, None, 2, 0.40, 0.01, now - 9000, book_side="bid"),
        fill(B, None, None, 2, 0.55, 0.01, now - 6000, book_side="ask")],
    P: [fill(P, "buy", "yes", 4, 0.50, 0.03, now - 9000), fill(P, "sell", "no", 2, 0.80, 0.02, now - 6000)],
}
settles = {P: {"ticker": P, "revenue_dollars": "2.00", "settled_time": iso(now - 3000)}}


def a():
    L = E._single_ledger(fills, settles, now)
    y = L.get(Y)
    ok("A1 YES bet sold, V2 'sell no' at the YES price: cost is the buy only, the sale is money back",
       y and near(y["cost"], 4.0 + 0.13) and near(y["back"], 6.0) and y["status"] == "sold" and y["side"] == "yes"
       and near(y["n_sold"], 10) and near(y["sold_back"], 6.0) and near(y["sell_fees"], 0.06), y)
    q = L.get(Q)
    ok("A2 NO bet sold, V2 'sell yes': cost at the NO price, back at 1 - the YES price",
       q and near(q["cost"], 3.5 + 0.07) and near(q["back"], 4.0) and q["status"] == "sold" and q["side"] == "no", q)
    ok("A3 legacy 'sell yes' of a YES bet: as before", L.get(L1) and near(L[L1]["cost"], 2.05) and near(L[L1]["back"], 2.8)
       and L[L1]["status"] == "sold")
    ok("A4 legacy 'sell no' of a NO bet: as before", L.get(L2) and near(L[L2]["cost"], 6 * 0.55 + 0.07)
       and near(L[L2]["back"], 6 * 0.65) and L[L2]["status"] == "sold" and L[L2]["side"] == "no")
    ok("A5 closed by buying the other side: a sale at 1 - the NO price", L.get(X) and near(L[X]["cost"], 1.54)
       and near(L[X]["back"], 0.9) and L[X]["status"] == "sold")
    ok("A6 fills with only the book side (bid, then ask): bought then sold", L.get(B) and near(L[B]["cost"], 0.82)
       and near(L[B]["back"], 1.1) and L[B]["status"] == "sold" and L[B]["side"] == "yes", L.get(B))
    p = L.get(P)
    ok("A7 half sold (V2 'sell no'), the rest held and won: sale and payout both back",
       p and near(p["cost"], 2.05) and near(p["back"], 1.6 + 2.0) and p["status"] == "won" and near(p["n_sold"], 2), p)
    ok("A8 fill_yes_delta: a sell closes what is held whichever side it names",
       E.fill_yes_delta({"action": "sell", "side": "no"}, 5, 2) == -2 and E.fill_yes_delta({"action": "sell", "side": "yes"}, -5, 2) == 2
       and E.fill_yes_delta({"action": "sell", "side": "yes"}, 0, 2) == -2 and E.fill_yes_delta({"action": "buy", "side": "no"}, 5, 2) == -2
       and E.fill_yes_delta({"outcome_side": "no"}, 0, 2) == -2 and E.fill_yes_delta({"side": "bid"}, 0, 2) == 2)
section("A", a)


def b():
    E._ledger_table()
    # the row the old code wrote for Y: the sale's dollars added to the cost, nothing back, still "lost"/open-ish
    E.store_x("insert into ledger(ticker, kind, league, side, cost, back, fees, sold_back, sell_fees, n_sold, status, opened, "
              "closed, legs, seen, nf) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (Y, "win", "nba", "yes", 10.13, 0.0, 0.13, 0.0, 0.0, 0.0, "lost", now - 9000, now - 3000, '["%s"]' % Y, now - 8000, 2))
    E.LEDGER_SIG.clear()                                    # a fresh process (the update restarts the watcher)
    n1 = E.ledger_note([], {}, fills, settles, now)
    rows = {r["ticker"]: r for r in E._ledger_rows()}
    y = rows.get(Y)
    ok("B1 the wrong row is recomputed from the fills and put right", y and near(y["cost"], 4.13) and near(y["back"], 6.0)
       and y["status"] == "sold" and near(y["seen"], now - 8000), y)
    E.LEDGER_SIG.clear()                                    # another restart: the saved rows already say this
    n2 = E.ledger_note([], {}, fills, settles, now)
    ok("B2 unchanged rows are not written again, even after a restart", n1 == len(E._single_ledger(fills, settles, now)) and n2 == 0, (n1, n2))
    E.LEDGER_SIG.clear()
    E.store_x("update ledger set back=0 where ticker=?", (L1,))
    n3 = E.ledger_note([], {}, fills, settles, now)
    ok("B3 only the changed row is rewritten", n3 == 1 and near({r["ticker"]: r for r in E._ledger_rows()}[L1]["back"], 2.8), n3)
section("B", b)


def c():
    sells, logs, notes = [], [], []
    fail = {"err": "Kalshi didn't take the order: market closed"}
    E.sell_single_now = lambda t, side, n, bid, coid=None: (sells.append((t, n)), (0, fail["err"]) if fail["err"] else (int(n), None))[1]
    E.log_decision = lambda rec: logs.append(rec)
    E.console_note = lambda m: notes.append(m)
    E.resting_single_sells = lambda: set()
    E.order_unsure = lambda t: False
    E.auto_cap_reached = lambda: False
    E.hands_off = lambda t: False
    E.sell_held = lambda out: False
    E.single_sell_reason = lambda x, bid, ask, cut_ok=False: ("smart", 1.0)
    E.CFG.update(stop_loss_mode="allow", smart_sell=True)
    T = "KXNBAGAME-26NOV21LALBOS-LAL"

    def run(n, at=None):
        E.SINGLES.update(at=at or time.time(), items=[{"t": T, "side": "yes", "state": "live", "n": n, "cost": 0.4, "chance": 0.6,
                                                 "label": "Lakers", "kind": "win"}],
                         mk={T: {"yes_bid_dollars": "0.60", "yes_ask_dollars": "0.62"}})
        real = E.time.time
        if at:
            E.time.time = lambda: at
        try:
            E.smart_sell_singles()
        finally:
            E.time.time = real

    for _ in range(20):
        run(0.92)
    ok("C1 a 0.92-contract leftover is never offered to Kalshi", sells == [], sells[:3])
    ok("C2 ...and logs no failures, only a skip saying why",
       not [r for r in logs if r.get("result") == "failed"] and any("under one contract" in (r.get("why") or "") for r in logs))
    sells.clear(); logs.clear(); E.SELL_FAILS.clear()
    for _ in range(12):
        run(3)
    ok("C3 after 3 failed identical sales it stops trying", len(sells) == 3, len(sells))
    waits = [r for r in logs if "waiting 10 min" in (r.get("why") or "")]
    ok("C4 the wait is logged once", len(waits) == 1 and len([m for m in notes if "waiting 10 min" in m]) == 1, (len(waits), notes))
    run(3, at=time.time() + 590)
    ok("C5 still waiting just under 10 minutes later", len(sells) == 3)
    run(3, at=time.time() + 610)
    ok("C6 tries again after 10 minutes", len(sells) == 4)
    run(3, at=time.time() + 620)
    run(3, at=time.time() + 610 + 3500)
    ok("C7 a failure after the wait: an hour before the next try", len(sells) == 4 and any("waiting 60 min" in (r.get("why") or "") for r in logs))
    run(3, at=time.time() + 610 + 3700)
    ok("C8 tries again after the hour", len(sells) == 5)
    fail["err"] = None
    E.SELL_FAILS[T]["until"] = 0
    run(3)
    ok("C9 a sale that goes through clears the count", len(sells) == 6 and T not in E.SELL_FAILS)
    sells.clear(); fail["err"] = "Kalshi didn't take the order: x"
    for _ in range(2):
        run(3)
    run(2)
    ok("C10 a different size is a different sale (counted afresh)", len(sells) == 3 and E.SELL_FAILS[T]["key"] == ("yes", 2))
    sells.clear(); E.SELL_FAILS.clear(); fail["err"] = "check: no answer"
    for _ in range(5):
        run(3)
    ok("C11 an unclear order ('check') is not a failure to back off from (rule 8 handles it as before)",
       not E.SELL_FAILS and len(sells) == 5)
    sells.clear(); E.SELL_FAILS.clear(); fail["err"] = "x"
    E.auto_cap_reached = lambda: True
    for _ in range(5):
        run(3)
    ok("C12 the daily cap still stops every sale (guards unchanged)", sells == [])
section("C", c)
