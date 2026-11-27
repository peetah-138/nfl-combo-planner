# CHECK: group=engine
# rank-e-144: #312 (auto cash-out weighs a hedge before skipping a below-cost sale), #482 (totals curve never narrower
# than the league's fitted width), #287 (learned in-play green bar, paper only), #286/#243 (pregame idea fair, Best bets
# board age and dollar pre-cut). Every Kalshi call is faked; nothing is sent.
# Combo cost floor counts Kalshi's selling fee (issues #382, #383), the way singles net it (`single_fee`): a combo
# cash-out offer exactly at cost no longer passes the floor, on the first offer or on a retry's fresh offer, and an
# unreadable offer (no contracts) is no sale. 20 contracts at $10 cost = 50 cents each: the fee is 35 cents.
# Every Kalshi call is faked.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl"); E.HEDGES = os.path.join(E.HERE, "hedges.json")
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
_real_time = time.time
now = _real_time()
T = "KXNBAGAME-26NOV19LALBOS-LAL"
E.CFG.update(flex_sell=False, auto_sell=True, auto_hedge=False, stop_loss=False, smart_sell=True, ride=2, take_profit=0,
             lock_trail=False, auto_cap=5)
h = {"label": "Combo 1", "need": [(("yes", T), "Lakers")], "pre_of": {T: 0.6}, "ch_of": {T: 0.7},
     "legs_left": [(0.7, True, 0)], "cost": 10, "p": 0.7, "pays": 20, "won_some": True, "left": 1}

E.can_trade = lambda: True
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 9.0)
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], None)
E.smart_sell_singles = lambda: []
E.haptic = E.loading = lambda *a: None
E.resting_sells = lambda: {}
E.drop_cash = lambda t: E.MINE["cash"].pop(t, None)
E._cash_pause = lambda s: None
SC = {"sc": {"state": "in", "me": 21, "opp": 17, "brk": False}}
E.leg_score = lambda l: dict(SC["sc"]) if SC["sc"] else None
asks, accepts, logs = [], [], []
OFFER = {"o": 13.0, "n": 20}
SCRIPT = {"s": []}
E.get_cash_offer = lambda t, f=1.0: (asks.append(t), {"offer": OFFER["o"], "frac": 1.0, "rfq": "x", "quote": "q",
                                                       "contracts": OFFER.get("n", 20), "at": E.time.time()})[1]


def fake_accept(o, t=None):
    accepts.append(o["offer"])
    st = SCRIPT["s"].pop(0) if SCRIPT["s"] else "cancelled"
    if st == "unknown":
        E.mark_rfq_unsure(t, "sell", "test")
    if st == "failed":
        E.ACCEPT_ERR[t] = "quote expired"
    return st


E.accept_once = fake_accept
real_log = E.log_decision
E.log_decision = lambda rec: (logs.append(rec), real_log(rec))
plan = {"acts": {}}


def tick(dt_, script=(), cash=None, **hold):
    SCRIPT["s"] = list(script)
    E.time.time = lambda: now + dt_
    E.MINE["hold"] = {"C1": dict(h, **hold)}
    E.MINE["tp_asked"] = {}; E.MINE.pop("real_asks", None); E.MINE["cash"] = {"C1": dict(cash, at=now + dt_)} if cash else {}; E.MINE["busy"] = False; E.MINE.setdefault("selling", set())
    asks.clear(); accepts.clear(); logs.clear()
    try:
        return E.auto_sell_now(plan)
    finally:
        E.time.time = _real_time


def reset():
    E.COMBO_WAIT.clear(); E.MINE["combo_fail_told"] = {}; SC["sc"] = {"state": "in", "me": 21, "opp": 17, "brk": False}
    E.save_json(E.ORDER_LEDGER, {}); E._ORDER_SHARED.unsure.clear()   # Pete cleared the order block



def run(offs, mode=None, script=("executed",), dt_=0, contracts=20, why="smart"):
    global offers
    reset()
    E.SELL_LOG = os.path.join(tempfile.mkdtemp(), "s.jsonl")   # a fresh decision log: the daily cap never interferes
    offers = iter(list(offs))
    OFFER["n"] = contracts
    E.CFG.update(stop_loss_mode=mode or "tune")
    E.take_profit_reason = lambda t, h, cut_ok=False: (why, 9.0)
    E.get_cash_offer = lambda t, f=1.0: (asks.append(t), {"offer": next(offers), "frac": 1.0, "rfq": "x", "quote": "q",
                                                          "contracts": OFFER["n"], "at": E.time.time()})[1]
    out = tick(dt_, script=list(script))
    return out, [r for r in logs if r.get("result") in ("failed", "sold", "skipped")]



# ---- #312: a below-cost sale weighs a hedge that locks in at least the cost first (never sells below cost here)
HG = {"n": 20, "cost": 3.0, "locked": 10.5, "ticker": "HEDGE-T"}
placed, hedge_asked = [], []
E.hedge_for = lambda t, price=None: (hedge_asked.append(t), dict(HG))[1]
E.hedge_guard = lambda t, h_, hg, now=None: (GUARD["ok"], GUARD["why"])
E.hedge_fresh = lambda t, h_, whole: (dict(HG), "") if GUARD["fresh"] else (None, "no fresh price for the hedge")
E.place_hedge = lambda t, hg=None, auto=False: (placed.append(t), "✅ hedged")[1]
E.hedge_cap_now = lambda: 100.0
E.hedge_seen_note = lambda *a, **k: None
GUARD = {"ok": True, "why": "", "fresh": True}
E.CFG.update(auto_hedge=True, hedge_before_loss_skip=True)
out, f = run([10.0])
ok("#312: below cost but a hedge locks in more than the cost: hedged, no sale", placed == ["C1"] and accepts == []
   and any(r.get("result") == "hedged" for r in logs), (placed, logs))
placed.clear(); HG["locked"] = 9.0
out, f = run([10.0])
ok("#312: a hedge that locks in LESS than the cost: skipped as before, nothing hedged or sold", placed == [] and accepts == []
   and f and f[0]["why"] == "below what you paid", (placed, f))
HG["locked"] = 10.5; GUARD.update(ok=False, why="score feed stale")
out, f = run([10.0])
ok("#312: the hedge guards still hold (not ready): skipped, no hedge, no sale", placed == [] and accepts == [], (placed, accepts))
GUARD.update(ok=True, fresh=False)
out, f = run([10.0])
ok("#312: the fresh-price check fails: skipped, no hedge, no sale", placed == [] and accepts == [] and f and f[0]["why"] == "below what you paid")
GUARD.update(fresh=True)
HG["locked"] = 10.5
E.CFG.update(hedge_before_loss_skip=False); hedge_asked.clear()
out, f = run([10.0])
ok("#312: switch off: the old skip, the hedge isn't even looked at", placed == [] and not hedge_asked and f and f[0]["why"] == "below what you paid")
E.CFG.update(hedge_before_loss_skip=True, auto_hedge=False); hedge_asked.clear()
out, f = run([10.0])
ok("#312: auto-hedge off: the old skip", placed == [] and not hedge_asked and f and f[0]["why"] == "below what you paid")
E.CFG.update(auto_hedge=True)
out, f = run([13.0])
ok("#312: a normal above-cost sale is untouched (sells, no hedge)", accepts and placed == [])

# ---- #482: the old totals curve is never narrower than the league's fitted width, and never raises a chance
g = {"total": 172.5}
E.CFG["total_fit_sd"] = True
old = E._phi((172.5 - 163.5) / E.TOTAL_SD["ncaamb"])
new = E.line_fair("ncaamb", "total", 163.5, True, g)
ok(f"#482: CBB over a strike 9 below the book total is priced lower on the fitted width ({old:.3f} -> {new:.3f})", new < old - 0.01)
old2 = E._phi((172.5 - 185.5) / E.TOTAL_SD["ncaamb"])
ok("#482: a strike ABOVE the book total keeps the old (lower) chance: never loosened", E.line_fair("ncaamb", "total", 185.5, True, g) == old2)
E.CFG["total_fit_sd"] = False
ok("#482: switch off = exactly the old curve", E.line_fair("ncaamb", "total", 163.5, True, g) == old)
E.CFG["total_fit_sd"] = True
ok("#482: a league whose fitted width is not wider (NFL 12.8 vs 10 is wider; NBA 17.8 vs 17) only ever goes down",
   all(E.line_fair(c, "total", k, True, {"total": 150.0}) <= E._phi((150.0 - k) / E.TOTAL_SD[c]) + 1e-12
       for c in E.TOTAL_SD for k in (120.0, 140.0, 150.0, 160.0, 180.0)))
ok("#482: no table / junk = no fitted width", E.total_sd_fit("nope") is None)

# ---- #287: the learned in-play bar is paper: flat without a record, and never below the flat bar
b = E.live_single_bar("KXNBAGAME-26NOV19LALBOS-LAL")
ok("#287: no record = the flat bar (1.5 cents)", abs(b["v"] - E.SINGLE_MIN_EDGE * 0.6) < 1e-9 and b["src"] == "start")
E._live_fair_table()
for i in range(40):                                        # 40 settled games where the live model ran 10 points high
    tk = f"KXNBAGAME-26NOV19AA{i:02d}BB{i:02d}-AA{i:02d}"
    E.store_x("insert into live_fairs(ticker, ts, sport, fair, how, outcome) values(?,?,?,?,?,?)",
              (tk, now, "nba", 0.70, "live model", "yes" if i % 10 < 6 else "no"))
E.LIVE_BAR_CACHE["at"] = 0
b = E.live_single_bar("KXNBAGAME-26NOV19AA01BB01-AA01")
ok(f"#287: an over-confident live model asks a higher bar, capped ({b})", b["v"] > b["flat"] and b["v"] <= E.LIVE_BAR["max"] and b["n"] >= 30)
E.CFG["live_bar_learn"] = False
ok("#287: switch off = the flat bar", E.live_single_bar("KXNBAGAME-26NOV19AA01BB01-AA01")["v"] == b["flat"])
E.CFG["live_bar_learn"] = True
ok("#287: paper only: nothing but the quote's live_bar field reads it",
   open("wahome/engine.py", encoding="utf-8").read().count("live_single_bar(") == 2)

# ---- #286 / #243
T = "KXNBAGAME-26NOV30DENLAL-DEN"
side = {"ticker": T, "pick": "Denver", "event": "KXNBAGAME-26NOV30DENLAL", "fair": 0.80, "src": "pinnacle", "fair_at": now - 60}
E.started = lambda s: False
ok("#286: a fresh sportsbook price: used, never above the books", 0 < E.idea_single_fair(T, side, 0.9, {})["fair"] <= 0.80)
ok("#286: a 13-minute-old board price: no fair", E.idea_single_fair(T, dict(side, fair_at=now - 780), 0.9, {})["fair"] is None)
ok("#286: unknown board age: no fair", E.idea_single_fair(T, dict(side, fair_at=None), 0.9, {})["fair"] is None)
ok("#286: Kalshi's own price (no src): no fair", E.idea_single_fair(T, dict(side, src=None), 0.9, {})["fair"] is None)
ok("#286: no board side: never the idea's stored chance", E.idea_single_fair(T, None, 0.9, {})["fair"] is None)
E.CFG["pregame_idea_fair"] = False
ok("#286: switch off = the old pregame fair", E.idea_single_fair(T, None, 0.9, {})["fair"] == 0.9)
E.CFG["pregame_idea_fair"] = True
W = open("wtest/combo_watcher.py", encoding="utf-8").read()
blk = W[W.index('if a == "idea":'):W.index('if a == "singlequote":')]
ok("#286: the idea quote's suggested stake never exceeds the panel's own sizing", "A._size({" in blk and "rec = min(rec," in blk)
ok("#243: Best bets gets the board's age", "fair_at=BUILD.get(\"at\")" in W)
