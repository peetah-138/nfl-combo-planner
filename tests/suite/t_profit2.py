# CHECK: group=engine
# Profit leaks from the audit (issue #142), second batch: each check fails on the code before the fix.
#  A  combos priced under fair (95-100%) stay only when smart sell is likely to cash them out for a profit (Pete,
#     2026-11-20), whatever the league's Smart Buy dial says; can't tell = left out. Panel, swaps and Buy ideas.
#  B  a real panel bet's profit comes from Kalshi's own record (fills, sales, fees), not 'held to the end on the stake'
#  C  standing orders: watch mode counts a fill only when the ask trades through; never priced over the calibrated
#     chance; their profit counts the fee
#  D  the weekly smart-sell tuner picks a step on half the games and must win on the other half too
import os, time, json, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.MAIN_SAVED = os.path.join(E.HERE, "main.json"); E.SB_DIAL_FILE = os.path.join(E.HERE, "sb.json")
E.SMART_FILE = os.path.join(E.HERE, "smart.json")
E.injury_note = lambda code, *teams, hours=48: ([], False)
E.leg_score = lambda l: None
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()


class NoNet:
    RequestException = E.requests.RequestException

    def __getattr__(self, name):
        def call(*a, **k):
            raise E.requests.RequestException("no network in this test")
        return call


E.requests = NoNet()


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def combo(i, pct, code="nba"):
    legs = [{"ticker": f"KXNBAGAME-26NOV23G{i:02d}{k}-A", "event": f"KXNBAGAME-26NOV23G{i:02d}{k}", "pick": f"T{i}{k}",
             "p": 0.5, "fair": 0.52} for k in "XY"]
    return {"id": f"combo:{i}", "kind": "combo", "code": code, "legs": legs, "chance": 0.27, "pct": pct,
            "fair_mult": 3.7, "stake": 2.0, "kick": now + 7200}


SIM = {}
real_sim = E._sb_sim


def fake_sim(c, now_=None):
    v = SIM.get(c["id"], "none")
    if v == "boom":
        raise RuntimeError("simulator broke")
    if v is None:
        return None
    return {"route": v, "ev": 0.6 if v != "none" else -0.3, "win": 0.27, "p_exit": 0.6 if v == "sell" else 0.1}


# ---------------------------------------------------------------- A: combos under fair need a likely profitable exit
def part_a():
    E.save_json(E.MAIN_SAVED, {})
    E.save_json(E.SB_DIAL_FILE, {})                    # every league still learning: dial 0 (skips nothing, as before)
    E.SB_GATE.update(dial=None, dial_at=0)
    E._sb_sim = fake_sim
    try:
        a, b, c, d, e, f = combo(1, 0.97), combo(2, 0.97), combo(3, 1.03), combo(4, 0.96), combo(5, 0.98), combo(6, 0.99)
        SIM.update({"combo:1": "none", "combo:2": "sell", "combo:3": "none", "combo:4": None, "combo:5": "boom",
                    "combo:6": "hold"})
        items = [a, b, c, d, e, f]
        kept, skipped = E.smart_buy_filter([dict(x) for x in items], now)
        ids = [x["id"] for x in kept]
        ok("A1 a combo at 97% of fair with no likely profitable exit is left out, even while the league is learning",
           "combo:1" not in ids)
        ok("A2 ...one at 97% that smart sell likely cashes out for a profit stays", "combo:2" in ids)
        ok("A3 ...one at 103% of fair is judged as before (a learning league skips nothing)", "combo:3" in ids)
        ok("A4 ...one that can't be simulated is left out (fail closed)", "combo:4" not in ids)
        ok("A5 ...and so is one whose simulation breaks", "combo:5" not in ids)
        ok("A6 ...a good hold at 99% stays", "combo:6" in ids)
        ok("A7 skip-only: the same dicts in the same order with the same stakes",
           [x["id"] for x in kept] == ["combo:2", "combo:3", "combo:6"] and all(x["stake"] == 2.0 for x in kept))
        why = {x["id"]: x["why"] for x in skipped}
        ok("A8 the reason is plain words", "pays 97% of what it's worth" in (why.get("combo:1") or "") and "smart sell" in why["combo:1"])
        ok("A9 a single is never touched by this rule",
           E.smart_buy_gate({"id": "single:x", "kind": "single", "legs": [{"ticker": "KXNBAGAME-26NOV23Z-A"}],
                             "pct": 0.9}, now)[0] is True)
        E.save_json(E.MAIN_SAVED, {"smart_buy_gate": False})
        ok("A10 Smart Buy switched off: off means off (nothing skipped)", E.smart_buy_gate(dict(a), now)[0] is True)
        E.save_json(E.MAIN_SAVED, {})
        # a swapped-in bet is a skip, never the next one down (the gate is the one _replacement uses)
        ok("A11 a swap to an under-fair combo with no likely exit is refused by the gate _replacement uses",
           E.smart_buy_gate(dict(a), now)[0] is False)
        # the shadow log records the verdict the gate gave
        spec_ = {"tickers": [l["ticker"] for l in a["legs"]], "league": "nba", "type": "combo", "kind": "combo",
                 "pays_per": 0.97 * 3.7}
        sim = {"win": 0.27, "p_exit": 0.1, "p_sell": 0.1, "exit_profit": None, "hold_profit": -0.15, "ev": -0.3,
               "exit_mins": None, "route": "none"}
        row = E._sb_row(a, spec_, sim, "panel", "panel:x", now, True, "cand", None, 0.27, -0.03)
        ok("A12 the shadow log records the skip, so the card's counts are honest", row[22] and "97%" in row[22])
    finally:
        E._sb_sim = real_sim
    # Buy ideas: a combo idea under fair needs the shadow's verdict that smart sell likely profits
    E._exit_shadow_table()
    i1 = {"id": 101, "idea_id": "i1", "legs": ["KXNBAGAME-26NOV23Q1-A", "KXNBAGAME-26NOV23Q2-A"], "pct": 0.97, "picks": "Q1 + Q2"}
    i2 = {"id": 102, "idea_id": "i2", "legs": ["KXNBAGAME-26NOV23Q3-A", "KXNBAGAME-26NOV23Q4-A"], "pct": 0.97, "picks": "Q3 + Q4"}
    i3 = {"idea_id": "i3", "legs": ["KXNBAGAME-26NOV23Q5-A", "KXNBAGAME-26NOV23Q6-A"], "pct": 1.04, "picks": "Q5 + Q6"}
    i4 = {"idea_id": "i4", "legs": ["KXNBAGAME-26NOV23Q7-A"], "pct": 0.97, "picks": "Q7"}
    E.store_x("insert into exit_shadow(ts, cand, source, tickers, ev, new) values(?,?,?,?,?,?)",
              (now - 60, "idea:idea:102", "idea", json.dumps(i2["legs"]), 0.5, 1))
    E.store_x("insert into exit_shadow(ts, cand, source, tickers, ev, new) values(?,?,?,?,?,?)",   # an older, cheaper
              (now - 30, "idea:idea:99", "idea", json.dumps(i1["legs"]), 0.5, 1))                # quote of i1's picks
    kept, skipped = E.smart_buy_ideas_gate([dict(i1), dict(i2), dict(i3), dict(i4)], now)
    ids = [x["idea_id"] for x in kept]
    ok("A13 Buy ideas: a combo idea at 97% isn't offered until smart sell looks likely to profit on it",
       "i1" not in ids and "i2" in ids)
    ok("A14 ...ideas at or over fair, and single ideas, are as before", "i3" in ids and "i4" in ids)
    ok("A15 ...and the skip says why (a quote not checked yet says so)",
       any(s["id"] == "i1" and "97%" in s["why"] and "still checking" in s["why"] for s in skipped))
    ok("A16 ...judged on the quote shown, never an older quote of the same picks", "i1" not in ids)
    real_dial = E.sb_dial
    E.sb_dial = lambda *a, **k: 1 / 0
    try:
        kept, skipped = E.smart_buy_ideas_gate([dict(i1), dict(i2), dict(i3), dict(i4)], now)
    finally:
        E.sb_dial = real_dial
    ok("A17 the ideas gate failing still leaves under-fair combo ideas out (fail closed), the rest as before",
       [x["idea_id"] for x in kept] == ["i3", "i4"] and {s["id"] for s in skipped} == {"i1", "i2"})
    # buy time: a combo predicted at fair or better that Kalshi quotes under fair
    E._sb_sim = fake_sim
    try:
        SIM["combo:7"] = "none"
        c7 = combo(7, 1.02)
        ok("A18 buy time: Kalshi's quote at 96% with no likely profitable exit is skipped before any accept",
           "96%" in (E._sb_quote_under_fair(c7, 0.96) or ""))
        SIM["combo:7"] = "sell"
        ok("A19 ...a likely cash-out at that price is bought; a quote at fair or better is untouched",
           E._sb_quote_under_fair(c7, 0.96) is None and E._sb_quote_under_fair(c7, 1.01) is None)
        SIM["combo:7"] = "boom"
        ok("A20 ...a broken check is a skip", E._sb_quote_under_fair(c7, 0.96) is not None)
        E.save_json(E.MAIN_SAVED, {"smart_buy_gate": False})
        ok("A21 ...Smart Buy off: off", E._sb_quote_under_fair(c7, 0.96) is None)
        E.save_json(E.MAIN_SAVED, {})
    finally:
        E._sb_sim = real_sim
    src = open("wahome/engine.py").read()
    b = src[src.index("def _buy_panel_bet"):]
    b = b[:b.index("\ndef ")]
    ok("A22 the panel's buy runs that check after the quote and before accept_offer",
       b.index("_sb_quote_under_fair(") < b.index("accept_offer("))


section("A", part_a)


# ---------------------------------------------------------------- B: panel P/L from Kalshi's own record
def part_b():
    E._panel_table(); E._ledger_table()
    E.fetch_results = lambda tks: {t: "yes" for t in tks}
    E.close_prices = lambda tks, mid=False: {}
    E.sim_exit = lambda c: None
    day = time.strftime("%Y-%m-%d", time.localtime(now - 86400))
    kick = now - 6 * 3600
    s1 = {"id": "single:S1", "kind": "single", "code": "nba", "state": "bought", "stake": 3.0, "price": 0.40,
          "paid": 0.40, "filled": 7, "kick": kick, "legs": [{"ticker": "KXNBAGAME-26NOV22S1-A", "p": 0.4, "fair": 0.45}]}
    s2 = dict(s1, id="single:S2", filled=3, legs=[{"ticker": "KXNBAGAME-26NOV22S2-A", "p": 0.4, "fair": 0.45}])
    s3 = dict(s1, id="single:S3", legs=[{"ticker": "KXNBAGAME-26NOV22S3-A", "p": 0.4, "fair": 0.45}])
    c1 = {"id": "combo:C1", "kind": "combo", "code": "nba", "state": "bought", "stake": 4.0, "pays": 16.0, "pct": 1.02,
          "fair_mult": 3.9, "market": "KXMVECOMBO-C1", "kick": kick,
          "legs": [{"ticker": "KXNBAGAME-26NOV22C1-A", "p": 0.5, "fair": 0.5}, {"ticker": "KXNBAGAME-26NOV22C2-A", "p": 0.5, "fair": 0.5}]}
    paper = dict(s1, id="single:P1", state="paper", filled=None)
    fee7 = E.single_fee(0.4, 7)
    cost7 = 7 * (0.4 + fee7)
    # S1: smart sell sold it early for $4.10 (all 7 contracts); the game then won. Its own ledger row.
    E.store_x("insert into ledger(ticker, kind, cost, back, fees, sold_back, sell_fees, n_sold, status, closed, legs) "
              "values(?,?,?,?,?,?,?,?,?,?,?)", ("KXNBAGAME-26NOV22S1-A", "win", round(cost7 + 0.07, 2), 4.10, 0.2, 4.10,
                                                 0.07, 7, "sold", now - 7200, "[]"))
    # S3: the same market also bought by hand ($12 more): the row isn't this bet's alone
    E.store_x("insert into ledger(ticker, kind, cost, back, fees, sold_back, sell_fees, n_sold, status, closed, legs) "
              "values(?,?,?,?,?,?,?,?,?,?,?)", ("KXNBAGAME-26NOV22S3-A", "win", 15.0, 37.0, 0.3, 0, 0, 0, "won",
                                                 now - 3600, "[]"))
    # C1: cashed out for $6.50
    E.store_x("insert into ledger(ticker, kind, cost, back, fees, sold_back, sell_fees, n_sold, status, closed, legs) "
              "values(?,?,?,?,?,?,?,?,?,?,?)", ("KXMVECOMBO-C1", "combo", 4.0, 6.5, 0, 6.5, 0, 4, "sold", now - 7200, "[]"))
    body = {"at": now - 86400, "items": [s1, s2, s3, c1]}
    E.store_x("insert or replace into panel values(?,?,?,?,?)", (day, "real", now - 86400, "approved", json.dumps(body)))
    E.store_x("insert or replace into panel values(?,?,?,?,?)", (day, "paper", now - 86400, "paper",
                                                                json.dumps({"at": now - 86400, "items": [paper]})))
    E.panel_settle()
    got = {c["id"]: c for c in json.loads(E.store_rows("select body from panel where day=? and mode='real'", (day,))[0]["body"])["items"]}
    pap = json.loads(E.store_rows("select body from panel where day=? and mode='paper'", (day,))[0]["body"])["items"][0]
    want1 = round(4.10 - round(cost7 + 0.07, 2), 2)
    ok("B1 a single smart sell cashed out early: its real profit is what Kalshi really paid",
       got["single:S1"].get("pl_real") == want1 and got["single:S1"].get("pl_src") == "fills")
    ok("B2 ...while pl and result keep meaning 'held to the end' (what the replays and tuners compare against)",
       got["single:S1"]["pl"] == round(7 - cost7, 2) and got["single:S1"]["result"] == "won")
    ok("B3 a single that only part-filled (3 of the stake's 7 contracts) counts those 3, not the whole stake",
       got["single:S2"]["pl"] == round(3 - 3 * (0.4 + E.single_fee(0.4, 3)), 2) and not got["single:S2"].get("pl_src"))
    ok("B4 a market also bought another way keeps the panel bet's own figure (the row isn't its alone)",
       got["single:S3"]["pl"] == round(7 - cost7, 2) and "pl_real" not in got["single:S3"])
    ok("B5 a combo cashed out early counts its real sale", got["combo:C1"]["pl_real"] == 2.5 and got["combo:C1"]["pl"] == 12.0)
    ok("B6 paper bets are untouched (no fills: held to the end on the stake)",
       pap["pl"] == round(3 / (0.4 + E.single_fee(0.4)) - 3, 2) and not pap.get("pl_src"))
    # the ledger arrives after the result was written: the next pass picks it up
    E.store_x("insert into ledger(ticker, kind, cost, back, fees, sold_back, sell_fees, n_sold, status, closed, legs) "
              "values(?,?,?,?,?,?,?,?,?,?,?)", ("KXNBAGAME-26NOV22S2-A", "win", round(3 * (0.4 + E.single_fee(0.4, 3)), 2),
                                                 1.0, 0.1, 1.0, 0.0, 3, "sold", now - 3600, "[]"))
    E.panel_settle()
    got = {c["id"]: c for c in json.loads(E.store_rows("select body from panel where day=? and mode='real'", (day,))[0]["body"])["items"]}
    ok("B7 a ledger row that arrives later is picked up on the next pass",
       got["single:S2"].get("pl_src") == "fills" and got["single:S2"]["pl_real"] == round(1.0 - round(3 * (0.4 + E.single_fee(0.4, 3)), 2), 2))
    rec = E.panel_record()["real"]
    ok("B8 the real panel's record adds up the real figures",
       rec["pl"] == round(sum(E.panel_pl(c) for c in got.values()), 2) and rec["pl"] != round(sum(c["pl"] for c in got.values()), 2))
    m = time.strftime("%Y-%m", time.localtime(now - 86400))
    if day.startswith(m):
        ok("B9 the monthly skim counts the panel singles' real profit",
           E.month_profit(m) == round(sum(E.panel_pl(c) for c in got.values() if c["kind"] != "combo"), 2))


section("B", part_b)


# ---------------------------------------------------------------- C: standing orders
def part_c():
    E.CFG["maker_mode"] = "watch"
    E.LEAGUE["code"] = "nba"
    t = "KXNBAGAME-26NOV24M1-A"
    kick = now + 10 * 3600
    E.store_x("insert into maker(ts, ticker, pick, mode, price, n, fair, status, order_id, filled, updated, kick) "
              "values(?,?,?,?,?,?,?,?,?,?,?,?)", (now - 600, t, "M1", "watch", 0.45, 10, 0.49, "watching", None, 0, now, kick))
    games = {"KXNBAGAME-26NOV24M1": [{"ticker": t, "event": "KXNBAGAME-26NOV24M1", "pick": "M1", "p": 0.45, "fair": 0.49,
                                      "src": "pinnacle", "start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(kick))}]}
    E.KICKOFF["KXNBAGAME-26NOV24M1"] = games["KXNBAGAME-26NOV24M1"][0]["start"]
    E.sources_agree = lambda snap, pick, fair: (False, "")       # nothing new posted in this check
    sharp = {"parts": {"M1": {"pinnacle": 0.49}}}                   # #344: an odds-service line backs it
    E.maker_pass(games, sharp)
    st = E.store_rows("select status from maker where ticker=?", (t,))[0]["status"]
    ok("C1 watch mode: the ask merely touching the order's price isn't a fill (our place in the queue is unknown)",
       st == "watching")
    games["KXNBAGAME-26NOV24M1"][0]["p"] = 0.44
    E.maker_pass(games, sharp)
    st = E.store_rows("select status from maker where ticker=?", (t,))[0]["status"]
    ok("C2 ...the ask trading a cent through it is", st == "filled")
    real_cal = E.calib_fair
    E.calib_fair = lambda code, f, ticker=None, table="closes": f - 0.05
    ok("C3 a standing order is priced from the calibrated chance when your record says it's lower",
       abs(E.maker_fair({"ticker": t, "fair": 0.6}) - 0.55) < 1e-9)
    E.calib_fair = lambda code, f, ticker=None, table="closes": f + 0.05
    ok("C4 ...never from a higher one (only ever lower)", E.maker_fair({"ticker": t, "fair": 0.6}) == 0.6)
    E.calib_fair = real_cal
    E.store_x("update maker set outcome='won' where ticker=?", (t,))
    s = E.maker_summary()
    ok("C5 standing orders' profit counts the resting order's fee",
       abs(s["pl"] - round(10 * (1 - 0.45) - 10 * E.maker_fee(0.45), 2)) < 0.006)


section("C", part_c)


# ---------------------------------------------------------------- D: the weekly tuner's holdout
def part_d():
    E.CFG["knobs_live"] = False; E.KNOB_SWITCH["on"] = None
    real = (E._tune_items, E._paths, E._sl_paths, E._replay)
    items = [{"id": i, "kind": "single", "stake": 5.0, "kick": now - 3600 * i, "pl": -5.0,
              "legs": [{"ticker": f"KXNBAGAME-26NOV20H{i:03d}-A"}]} for i in range(60)]
    fit = [c for c in items if E._tune_half(c) == 0]
    out = [c for c in items if E._tune_half(c) == 1]
    ok("D1 the bets split into two halves by game (both big enough here)", len(fit) >= 10 and len(out) >= 10)
    fit_ids = {c["id"] for c in fit}
    E._tune_items = lambda days=60: [dict(c) for c in items]
    E._paths = lambda c: [(0, {}), (1, {}), (2, {})]
    E._sl_paths = lambda c: []
    # a lower floor 'wins' only on the half that picks it: on the other half it does nothing (pure noise-fitting)
    E._replay = lambda c, path, fl=1.5, lm=1.0, loss=None, cut_at=None, **k: \
        (5.0, "smart") if (fl < 1.45 and c["id"] in fit_ids) else None
    json.dump({"nba": {"n": 60, "floor": 1.5, "lam": 1.0, "loss": None}}, open(E.SMART_FILE, "w"))
    E.SMART_CACHE["at"] = 0
    E.smart_tune(force=True)
    a = json.load(open(E.SMART_FILE))["nba"]
    ok("D2 a step that only wins on the games that picked it isn't taken", a["floor"] == 1.5)
    E._replay = lambda c, path, fl=1.5, lm=1.0, loss=None, cut_at=None, **k: (5.0, "smart") if fl < 1.45 else None
    json.dump({"nba": {"n": 60, "floor": 1.5, "lam": 1.0, "loss": None}}, open(E.SMART_FILE, "w"))
    E.smart_tune(force=True)
    b = json.load(open(E.SMART_FILE))["nba"]
    ok("D3 a step that wins on both halves still is (one small step)", b["floor"] == 1.4 and "held back" in b.get("why", ""))
    one = [dict(c, legs=[{"ticker": "KXNBAGAME-26NOV20ONE-A"}]) for c in items]   # all on one game: no holdout
    E._tune_items = lambda days=60: [dict(c) for c in one]
    json.dump({"nba": {"n": 60, "floor": 1.5, "lam": 1.0, "loss": None}}, open(E.SMART_FILE, "w"))
    E.smart_tune(force=True)
    ok("D4 bets that can't be split (one game) never move it", json.load(open(E.SMART_FILE))["nba"]["floor"] == 1.5)
    ok("D5 a spread and a game-winner on the same game land in the same half",
       E._tune_half({"legs": [{"ticker": "KXNBASPREAD-26NOV21BOSNYK-BOS5"}]}) ==
       E._tune_half({"legs": [{"ticker": "KXNBAGAME-26NOV21BOSNYK-BOS"}]}))
    E._tune_items, E._paths, E._sl_paths, E._replay = real


section("D", part_d)
