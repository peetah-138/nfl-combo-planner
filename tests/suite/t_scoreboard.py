# The profit scoreboard (#138) and the smart-sell scorecard (#115): read-only analytics and logging, in real dollars.
#  A  single bets from Kalshi's fills and settlements: fees counted, NO bets and sales before settlement right
#  B  the ledger: combos and singles, one row each, rewritten only when something changed
#  C  the board: week / month / all time, ROI after fees, days up and down, breakdowns, "too few to trust"
#  D  the decision log: a skip is written once per bet and reason (no 12-second spam), sales are never trimmed,
#     the device label says mac / phone / pi
#  E  after a sale: what holding would have paid, per league and reason (sold too early vs sold right)
import os, time, json, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SELL_LOG = os.path.join(E.HERE, "sell.jsonl")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
now = time.time()
iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
near = lambda a, b: a is not None and abs(a - b) < 0.006


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def fill(t, action, side, n, yes, fee, ts):
    return {"ticker": t, "action": action, "side": side, "count": n, "yes_price_dollars": f"{yes:.2f}",
            "no_price_dollars": f"{1 - yes:.2f}", "fee_cost": f"{fee:.2f}", "created_time": iso(ts)}


W, N, S, O = "KXNBAGAME-26NOV20BOSNYK-BOS", "KXNHLGAME-26NOV20TORMTL-MTL", "KXNFLSPREAD-26NOV22KCBUF-KC3", "KXNBAGAME-26NOV21LALGSW-LAL"
C = "KXNBATOTAL-26NOV20BOSNYK-220"
fills = {W: [fill(W, "buy", "yes", 10, 0.40, 0.07, now - 9000)],                                 # held, won
         N: [fill(N, "buy", "no", 5, 0.70, 0.04, now - 8000), fill(N, "sell", "no", 5, 0.50, 0.03, now - 6000)],  # NO, sold
         S: [fill(S, "buy", "yes", 4, 0.60, 0.05, now - 7000), fill(S, "buy", "no", 4, 0.70, 0.04, now - 5000)],  # closed by buying NO
         O: [fill(O, "buy", "yes", 3, 0.55, 0.02, now - 4000)],                                  # still open
         C: [fill(C, "buy", "yes", 6, 0.50, 0.05, now - 9000)]}                                  # held, lost
settles = {W: {"ticker": W, "revenue_dollars": "10.00", "settled_time": iso(now - 3000)},
           C: {"ticker": C, "revenue_dollars": "0.00", "settled_time": iso(now - 3000)}}


def a():
    L = E._single_ledger(fills, settles, now)
    w, n, s = L.get(W), L.get(N), L.get(S)
    ok("A1 a held single that won: cost includes the fee, payout counted", w and near(w["cost"], 4.07) and near(w["back"], 10) and w["status"] == "won")
    ok("A2 a NO bet sold before the end: cost at the NO price, both fees, sold", n and near(n["cost"], 1.5 + 0.07) and near(n["back"], 2.5)
       and n["status"] == "sold" and n["side"] == "no" and near(n["n_sold"], 5) and near(n["sell_fees"], 0.03))
    ok("A3 closed by buying NO: counted as a sale at 1 - the NO price", s and near(s["cost"], 2.4 + 0.09) and near(s["back"], 2.8) and s["status"] == "sold")
    ok("A4 a bet still held is not in the ledger (not finished)", O not in L)
    ok("A5 kinds and leagues from the ticker", w["kind"] == "win" and s["kind"] == "spread" and L[C]["kind"] == "total" and w["league"] == "nba")
section("A", a)

combo_bets = [{"ticker": "KXMVE-C1", "legs": [{"ticker": "KXNBAGAME-26NOV20BOSNYK-BOS"}, {"ticker": "KXNBAGAME-26NOV20LALGSW-GSW"}],
               "cost": 5.10, "pays": 20, "status": "lost", "back": 0, "settled_at": now - 2000},
              {"ticker": "KXMVE-C2", "legs": [{"ticker": "KXNHLGAME-26NOV20TORMTL-TOR"}, {"ticker": "KXNHLGAME-26NOV20BUFOTT-BUF"}],
               "cost": 4.05, "pays": 15, "status": "cashed", "back": 9.0, "cashed_at": now - 2500},
              {"ticker": "KXMVE-C3", "legs": [{"ticker": "KXNBAGAME-26NOV21LALGSW-GSW"}], "cost": 3, "pays": 9, "status": "pending", "back": 0}]
held = {"KXMVE-C1": {"fees": 0.10, "first_ts": now - 9000}, "KXMVE-C2": {"fees": 0.08, "sold": 9.0, "sell_fees": 0.03, "sold_n": 15, "first_ts": now - 9000}}


def b():
    n1 = E.ledger_note(combo_bets, held, fills, settles, now)
    n2 = E.ledger_note(combo_bets, held, fills, settles, now)
    rows = {r["ticker"]: r for r in E._ledger_rows()}
    ok("B1 finished combos and singles each get one row; pending ones don't", set(rows) == {"KXMVE-C1", "KXMVE-C2", W, N, S, C} and n1 == 6)
    ok("B2 nothing changed: nothing rewritten", n2 == 0)
    ok("B3 a cashed combo is 'sold' with its proceeds and the sale's fee", rows["KXMVE-C2"]["status"] == "sold" and near(rows["KXMVE-C2"]["sold_back"], 9.0)
       and rows["KXMVE-C2"]["league"] == "nhl" and rows["KXMVE-C1"]["league"] == "nba")
section("B", b)


def c():
    E._app_table()
    E.store_x("insert or ignore into app_bets values(?,?,?)", ("__seeded__", now - 1e6, "before"))
    E.store_x("insert or ignore into app_bets values(?,?,?)", (N, now, "manual"))
    E.store_x("insert or ignore into app_bets values(?,?,?)", ("KXMVE-C1", now, "combo"))
    E._panel_table()
    body = {"at": now - 9000, "items": [{"id": "x", "kind": "single", "stake": 4, "pl": 5.9, "result": "won", "legs": [{"ticker": W}],
                                          "ret": 0.08, "chance": 0.45, "kick": now - 8000, "bought_at": now - 9000, "clv": 0.02},
                                         {"id": "y", "kind": "combo", "market": "KXMVE-C2", "stake": 4, "pl": 4.9, "result": "won", "origin": "extra",
                                          "legs": [{"ticker": "KXNHLGAME-26NOV20TORMTL-TOR"}], "ret": 0.12, "chance": 0.3, "kick": now - 3600 * 30, "bought_at": now - 3600 * 56}]}
    E.store_x("insert or replace into panel values(?,?,?,?,?)", (E._panel_day(now), "real", now, "done", json.dumps(body)))
    E.BOARD["at"] = 0
    bd = E.profit_board(now)
    al = bd["periods"]["all"]
    rows = E._ledger_rows()
    want_pl = round(sum(r["back"] - r["cost"] for r in rows), 2)
    want_st = sum(r["cost"] for r in rows)
    ok("C1 all-time profit = every finished bet's money back minus its cost (fees in)", near(al["pl"], want_pl) and al["n"] == 6)
    ok("C2 ROI is profit over money staked", near(al["roi"], want_pl / want_st))
    ok("C3 this week and this month include today's bets", bd["periods"]["week"]["n"] == 6 and bd["periods"]["month"]["n"] == 6)
    ok("C4 days up / down, best and worst day", al["days"] >= 1 and (al["up"] + al["down"]) >= 1 and al["best"] and al["worst"])
    ty = {r["k"]: r for r in al["by"]["type"]}
    ok("C5 by bet type: combos, single games, spreads, totals", set(ty) >= {"combo", "win", "spread", "total"} and ty["combo"]["n"] == 2)
    ok("C6 small groups are marked too few to trust", all(r["few"] for r in al["by"]["type"]) and al["few"])
    src = {r["k"]: r["n"] for r in al["by"]["source"]}
    ok("C7 by source: panel, extras, Buy straight, app, you on Kalshi", src.get("panel") == 1 and src.get("extra") == 1 and src.get("manual") == 1
       and src.get("app") == 1 and src.get("own") == 2, src)
    en = {r["k"]: r["n"] for r in al["by"]["end"]}
    ok("C8 by how it ended: sold by you, held won, held lost", en.get("you") == 3 and en.get("won") == 1 and en.get("lost") == 2, en)
    ok("C9 each breakdown has a plain sentence; small samples say so", "Too few" in al["say"]["type"])
    q = al["quality"]["real"]
    ok("C10 price quality: edge band, CLV, timing from the panel's own record", q["edge"] and q["clv_n"] == 1 and any(t["name"] == "A day or more before" for t in q["timing"]))
    ok("C11 running total ends at the all-time profit", bd["curve"] and near(bd["curve"][-1][1], want_pl))
    E.store_x("insert into pulse values(?,?,?)", (now - 60, 12.5, 10.0))
    E.BOARD["at"] = 0
    ok("C12 open bets are a separate estimate, not in the profit", E.profit_board(now)["open"]["worth"] == 12.5 and near(E.profit_board(now)["periods"]["all"]["pl"], want_pl))
    big = [{"pl": 1.0 + (i % 3) * 0.1, "cost": 5.0} for i in range(40)]
    good = E._board_group([dict(r, closed=now, opened=now - 3600) for r in big], lambda r: "A", {"A": "Spreads"})
    ok("C13 a group clearly ahead over 40 bets gets 'keep it'", "keep it" in E._board_say(good, "bet type"))
section("C", c)


def d():
    E.CFG["auto_cap"] = 5
    rec = {"combo": "X", "ticker": "KXMVE-Z", "offer": 4.0, "cost": 5.0, "why": "smart"}
    for _ in range(6):
        E.log_decision(dict(rec, result="skipped", why="below what you paid"))
    lines = open(E.SELL_LOG).read().splitlines()
    ok("D1 the same skip six times is written once", len(lines) == 1)
    E.log_decision(dict(rec, offer=2.0, result="skipped", why="below what you paid"))
    E.log_decision(dict(rec, result="skipped", why="daily cap reached"))
    ok("D2 a new offer band or a new reason is written again", len(open(E.SELL_LOG).read().splitlines()) == 3)
    ok("D3 the Mac's decisions say mac (not pi)", json.loads(lines[0])["by"] == "mac")
    E.ROLE_BACKUP = True
    E.log_decision(dict(rec, ticker="KXMVE-PI", result="skipped", why="x"))
    E.ROLE_BACKUP = False
    ok("D4 the Pi's say pi", json.loads(open(E.SELL_LOG).read().splitlines()[-1])["by"] == "pi")
    E.log_decision(dict(rec, ticker="KXMVE-C2", offer=9.0, pays=15, frac=1.0, kind="combo", side="yes", result="sold"))
    E.log_decision(dict(rec, ticker=N, offer=2.5, cost=1.57, pays=5, frac=1.0, kind="win", side="no", result="sold"))
    for i in range(E.SELL_KEEP + 50):
        with open(E.SELL_LOG, "a") as f:
            f.write(json.dumps({"result": "skipped", "ticker": f"T{i}", "why": "w"}) + "\n")
    E._trim_sell_log()
    body = open(E.SELL_LOG).read()
    ok("D5 trimming keeps every sale", body.count('"result": "sold"') == 2 and len(body.splitlines()) <= E.SELL_KEEP + 2)
    ok("D6 sales are in the history file too", len(E.store_rows("select * from sell_log where result='sold'")) == 2)
    ok("D7 sold_today still counts today's sales", E.sold_today() == 2)
section("D", d)


def e():
    class R:
        def __init__(s, d): s.d = d
        def raise_for_status(s): pass
        def json(s): return s.d
    asked = []

    def get(url, params=None, timeout=None, **k):
        asked.append(params["tickers"])
        return R({"markets": [{"ticker": "KXMVE-C2", "result": "yes", "status": "settled"},
                              {"ticker": N, "result": "no", "status": "settled"}]})
    real = E.requests.get
    E.requests.get = get
    E.sale_import()                                   # (the one-time copy from the file: nothing new, every sale is in already)
    E.store_x("update sell_log set ts=?", (now - 3600,))
    try:
        n = E.sale_outcomes(now, every=0)
    finally:
        E.requests.get = real
    sl = {r["ticker"]: r for r in E.store_rows("select * from sell_log where result='sold'")}
    ok("E1 after the games: holding the combo would have paid all 15", n >= 2 and sl["KXMVE-C2"]["outcome"] == "won" and near(sl["KXMVE-C2"]["held"], 15))
    ok("E2 a NO single whose market said no: holding would have won", sl[N]["outcome"] == "won" and near(sl[N]["held"], 5))
    led = {r["ticker"]: r for r in E._ledger_rows()}
    ok("E3 the ledger's sold bets get the same answer", led["KXMVE-C2"]["outcome"] == "won" and near(led["KXMVE-C2"]["held"], 15))
    sc = E.sell_scorecard()
    nhl = next(r for r in sc["rows"] if r["league"] == "nhl")
    sold = (9.0 - 0.03) + (2.5 - 0.03)                # both NHL smart sales, Kalshi's proceeds after each sale's fee
    ok("E4 scorecard: sold for Kalshi's proceeds after the fee vs what holding paid", near(nhl["sold"], sold) and near(nhl["held"], 20)
       and near(nhl["gain"], sold - 20) and nhl["early"] == 2 and nhl["right"] == 0 and near(nhl["early_usd"], 20 - sold), sc["rows"])
    ok("E5 totals and sample size", sc["total"]["n"] == 2 and sc["total"]["done"] == 2 and sc["total"]["few"])
    E.BOARD["at"] = 0
    bd = E.profit_board(now)
    en = {r["k"]: r for r in bd["periods"]["all"]["by"]["end"]}
    ok("E6 the board now files those two as sold by smart sell, with what holding would have paid", en["smart"]["n"] == 2 and en["smart"]["vs_n"] == 2)
    ok("E7 nothing asked again once every sale has its answer", E.sale_outcomes(now + 1, every=0) == 0)
section("E", e)


def f():                                                 # review fixes
    # a bet sold in two parts counts once on the scorecard
    E.log_decision({"combo": "P", "ticker": "KXMVE-C2", "offer": 1.0, "cost": 5.0, "pays": 15, "frac": 0.5, "kind": "combo",
                    "side": "yes", "why": "lock in", "result": "sold"})
    E.store_x("update sell_log set outcome='won', held=7.5 where ticker='KXMVE-C2' and why='lock in'")
    sc = E.sell_scorecard()
    ok("F1 a bet sold in two parts counts once (Kalshi's proceeds once)", sc["total"]["n"] == 2 and near(sc["total"]["sold"], (9.0 - 0.03) + (2.5 - 0.03)), sc["total"])
    # fewer fills than the saved row (old ones aged out of Kalshi's window) never overwrite it
    before = {r["ticker"]: r for r in E._ledger_rows()}[N]
    E.LEDGER_SIG.clear()
    E.ledger_note([], {}, {N: fills[N][1:]}, {}, now)
    after = {r["ticker"]: r for r in E._ledger_rows()}[N]
    ok("F2 a row rebuilt from fewer fills doesn't replace the saved one", near(after["cost"], before["cost"]) and after["status"] == before["status"])
    # no time anywhere: undated, counted in All time but not this week
    E.ledger_note([], {}, {}, {"KXNHLGAME-26NOV19AAABBB-AAA": {"ticker": "KXNHLGAME-26NOV19AAABBB-AAA", "revenue_dollars": "0", "yes_total_cost_dollars": "2.00"}}, now)
    E.BOARD["at"] = 0
    bd = E.profit_board(now)
    ok("F3 a bet with no date counts in All time only", bd["periods"]["all"]["n"] == bd["periods"]["week"]["n"] + 1)
    ok("F4 nothing changed: the ledger isn't even read", E.ledger_note([], {}, {}, {"KXNHLGAME-26NOV19AAABBB-AAA": {"ticker": "KXNHLGAME-26NOV19AAABBB-AAA", "revenue_dollars": "0", "yes_total_cost_dollars": "2.00"}}, now) == 0)
section("F", f)
