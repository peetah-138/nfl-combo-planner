# CHECK: group=engine
# The learned loss cut (smart sell, per league) gets the stop-loss switch's guards (issue #27): it can only sell at a
# loss late in a game, on a fresh score, not at a break, after a big fall from the pregame chance that held 3+ checks
# over 3+ minutes. Off until a league's own record turns it on (never borrowed). No real orders: every trading call
# is faked here.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl"); E.PREGAME = os.path.join(E.HERE, "pregame.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
_real_time = time.time
now = time.time()
T = "KXNBAGAME-26NOV19LALBOS-LAL"
S1 = "KXNBAGAME-26NOV19NYKMIA-NYK"
E.CFG.update(smart_sell=True, ride=2, take_profit=0, lock_trail=False, stop_loss=False, auto_hedge=False, auto_cap=5)

# ---- off by default, and never borrowed
ok("no data: no loss cut at all", E.smart_params([T])["loss"] is None and E.SMART_DEFAULT["loss"] is None)
E.save_json(E.SMART_FILE, {"soccer": {"floor": 1.5, "lam": 1.0, "loss": 0.15, "n": 40},
                           "all": {"floor": 1.5, "lam": 1.0, "loss": 0.2, "n": 90}}); E.SMART_CACHE["at"] = 0
ok("a league short on data never borrows its sport's loss cut", E.smart_params(["KXEPLGAME-26NOV22ARSCHE-ARS"])["loss"] is None)
ok("...nor everyone's", E.smart_params([T])["loss"] is None and E.smart_params([T])["key"] == "all")
E.save_json(E.SMART_FILE, {"nba": {"floor": 1.5, "lam": 1.0, "loss": 0.2, "n": 40}}); E.SMART_CACHE["at"] = 0
ok("a league's own record turns it on", E.smart_params([T])["loss"] == 0.2)

# ---- the guards, on a faked score feed
SC = {"sc": None}
E.leg_score = lambda l: SC["sc"]
E.SCORES_BY["nba"] = {"at": now, "by": {}}
E.leg_start = lambda l, s: E.dt.datetime.fromtimestamp(now - 3600, E.dt.timezone.utc)
live = {"state": "in", "frac": 0.4, "detail": "Q3 7:12", "brk": False}
early = dict(live, frac=0.75, detail="Q2 12:00")
h = {"label": "Combo 1", "need": [(("yes", T), "Lakers")], "pre_of": {T: 0.6}, "ch_of": {T: 0.15},
     "legs_left": [(0.15, True, 0)], "cost": 10, "p": 0.15, "pays": 20, "won_some": False, "left": 1}
ok("take_profit_reason never cuts without the guards (the default)", E.take_profit_reason("C1", h)[0] is None)
ok("...and does once they held", E.take_profit_reason("C1", h, True)[0] == "cut loss")

# ---- auto cash-out, combos: the cut only once every guard held
sold, logs = [], []
E.can_trade = lambda: True
E.get_cash_offer = lambda t, f=1.0: {"offer": 2.5, "frac": 1.0, "rfq": "x", "contracts": 20, "at": E.time.time()}
E.fresh_offer = lambda t: None
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], None)
E.sold_today = lambda: 0
real_sss = E.smart_sell_singles
E.smart_sell_singles = lambda: []
E.accept_cash = lambda t: (sold.append(t), "✅ sold")[1]
real_log = E.log_decision
E.log_decision = lambda rec: (logs.append(rec), real_log(rec))
E.MINE["busy"] = False; E.MINE.setdefault("selling", set()); E.MINE["cash"] = {}
plan = {"acts": {}}


def tick(dt_, sc):
    SC["sc"] = sc
    E.time.time = lambda: now + dt_
    E.SCORES_BY["nba"]["at"] = now + dt_
    E.MINE["hold"] = {"C1": dict(h)}
    return E.auto_sell_now(plan)


E.CFG["auto_sell"] = True
for k in range(5):
    tick(k * 100, early)
ok("under the cut-off but early in the game: never cut", not sold)
held = [r for r in logs if r.get("result") == "held"]
ok("...and the hold is logged once, with the guard that stopped it", len(held) == 1 and held[0]["guard"] == "too early in the game")
tick(600, dict(live, detail="Half", brk=True))
ok("halftime: never", not sold)
tick(700, live); tick(800, live)
ok("late, a big fall, but not yet held 3+ minutes: not yet", not sold)
SC["sc"] = live
E.SCORES_BY["nba"]["at"] = now - 1000
E.time.time = lambda: now + 900
E.MINE["hold"] = {"C1": dict(h)}
E.auto_sell_now(plan)
ok("a stale score feed: never, and the count starts again", not sold and "cut:C1" not in E.MINE["sl_streak"])
tick(1000, live); tick(1100, live)
ok("...two checks in: still not", not sold)
out = tick(1200, live)
ok("every guard held for 3+ minutes: the learned cut sells", sold == ["C1"] and out and "Cut a loss" in out[0])
ok("it is logged as a cut, not the stop-loss switch", any(r.get("result") == "sold" and r["why"] == "cut loss" and not r.get("stop_loss") for r in logs))

sold.clear(); E.MINE["sl_streak"] = {}
E.CFG["auto_sell"] = False                              # what Pause does
for k in range(6):
    tick(2000 + k * 100, live)
ok("auto cash-out off / paused: no cut", not sold)
E.CFG.update(auto_sell=True, ride=4)                    # "Ride it out"
for k in range(6):
    tick(3000 + k * 100, live)
ok("Ride it out: no cut", not sold)
E.CFG["ride"] = 2
E.save_json(E.SMART_FILE, {}); E.SMART_CACHE["at"] = 0; E.MINE["sl_streak"] = {}
for k in range(6):
    tick(4000 + k * 100, live)
ok("no learned cut for the league: never below cost", not sold)
E.save_json(E.SMART_FILE, {"nba": {"floor": 1.5, "lam": 1.0, "loss": 0.2, "n": 40,
                                   "sl_prog": 0.9, "sl_drop": 0.2, "sl_n": 60}}); E.SMART_CACHE["at"] = 0
for k in range(6):
    tick(5000 + k * 100, live)
ok("it uses the league's learned 'how late' (90% here: 60% played isn't enough)", not sold)
E.save_json(E.SMART_FILE, {"nba": {"floor": 1.5, "lam": 1.0, "loss": 0.2, "n": 40}}); E.SMART_CACHE["at"] = 0

# ---- singles, spreads and totals
x = {"t": S1, "kind": "win", "sport": "nba", "side": "yes", "n": 10, "cost": 5.0, "chance": 0.12, "state": "live",
     "label": "Knicks to win"}
E.MINE["pre_single"] = {}
E.MINE["sl_streak"] = {}
ok("a single with no pregame chance: never", E.cut_loss_single_check(x, 0.2, now)[1] == "no pregame chance")
E.save_json(E.PREGAME, {S1: 0.55})
ok("a game-winner falls back on the saved pregame chance", E.single_pre(x) == 0.55 and round(E.single_pre(dict(x, side="no")), 4) == 0.45)
E.MINE["pre_single"] = {S1: 0.6}
ok("the last chance seen before the game comes first", E.single_pre(x) == 0.6)
SC["sc"] = early
E.SCORES_BY["nba"]["at"] = now
ok("a single early in the game: never", E.cut_loss_single_check(x, 0.2, now)[1] == "too early in the game")
SC["sc"] = live
ok("a single over the cut-off: never", E.cut_loss_single_check(dict(x, chance=0.25), 0.2, now)[1] == "not under the cut-off")
r = []
for k in range(3):
    E.SCORES_BY["nba"]["at"] = now + k * 70
    r.append(E.cut_loss_single_check(x, 0.2, now + k * 70))
ok("a single: held 3 checks but under 3 minutes: not yet", all(v == (False, "waiting to confirm the drop") for v in r))
E.SCORES_BY["nba"]["at"] = now + 200
ok("a single: held 3+ minutes: ready", E.cut_loss_single_check(x, 0.2, now + 200) == (True, ""))

# smart_sell_singles end to end (the real one)
E.smart_sell_singles = real_sss
ssold = []
E.sell_single_now = lambda t, side, n, price: (ssold.append(t), (n, None))[1]
E.resting_single_sells = lambda: set()
E.SINGLES.update(items=[x], mk={S1: {"yes_bid_dollars": "0.11", "yes_ask_dollars": "0.13"}})
E.MINE["sl_streak"] = {}
SC["sc"] = early
for k in range(4):
    E.time.time = lambda k=k: now + 6000 + k * 100
    E.SINGLES["at"] = now + 6000 + k * 100; E.SCORES_BY["nba"]["at"] = now + 6000 + k * 100
    E.smart_sell_singles()
ok("smart sell for singles: early in the game, never cut", not ssold)
SC["sc"] = live
outs = []
for k in range(3):
    E.time.time = lambda k=k: now + 7000 + k * 100
    E.SINGLES["at"] = now + 7000 + k * 100; E.SCORES_BY["nba"]["at"] = now + 7000 + k * 100
    outs += E.smart_sell_singles()
ok("smart sell for singles: cut only once every guard held 3+ minutes", ssold == [S1] and any("Cut a loss" in m for m in outs))
E.time.time = _real_time

# ---- the replay that learns the cut uses the same guards
c = {"id": "x", "kind": "single", "legs": [{"ticker": S1, "p": 0.55}], "stake": 5.0, "paid": 0.5, "kick": now - 5000,
     "result": "lost", "pl": -5.0}
seq = [(0.55, ""), (0.4, "Q2 6:00"), (0.12, "Q2 3:00"), (0.11, "Q2 2:00"), (0.1, "Q2 1:00"), (0.1, "Q2 0:30"),
       (0.1, "Half"), (0.08, "Q3 10:00"), (0.07, "Q3 9:00"), (0.06, "Q3 8:00"), (0.05, "Q3 7:00"), (0.0, "Final")]
for k, (ch, sc) in enumerate(seq):
    E.store_x("insert into ticks values(?,?,?,?,?)", (now - 5000 + 60 * (k + 1), S1, ch, "live", ("NYK 40–60 MIA " + sc) if sc else ""))
path, slp = E._paths(c), E._sl_paths(c)
ok("replay: no guard times given, never a cut", E._replay(c, path, 1.5, 1.0, 0.2) is None)
g = E._cut_guard_ts(c, slp, 0.2, 0.5, 0.2)
first = min(g) if g else 0
ok("replay: the cut waits for the second half and 3+ minutes (not the first-half slide, not halftime)",
   g and first == round(now - 5000 + 60 * 11))
r = E._replay(c, path, 1.5, 1.0, 0.2, cut_at=g)
ok("replay: with the guards it cuts there", r and r[1] == "cut loss")

# ---- Results › Selling
a = E.analytics() if hasattr(E, "analytics") else {}
ok("Results › Selling counts the cuts the guards held back, by reason", (a.get("cut_held") or {}).get("too early in the game", 0) >= 1)
