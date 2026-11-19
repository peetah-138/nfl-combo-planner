# The stop-loss switch (issue #27): off by default, and when on it can only sell at a loss late in a game, on a
# fresh score, not at a break, after a big fall from the pregame chance that held 3+ checks over 3+ minutes.
# How late and how big a fall are learned league by league. No real orders: every trading call is faked here.
import os, time, tempfile, importlib.util, json
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
_real_time = time.time
now = time.time()
T = "KXNBAGAME-26NOV19LALBOS-LAL"

ok("the switch is still off by default", E.DEFAULTS.get("stop_loss") is False)
ok("no data: the conservative start (half the game played, a 20-point fall)",
   E.stoploss_params([T]) == {"prog": 0.5, "drop": 0.2, "key": None})

# ---- one pick's guards, on a faked score feed
SC = {}
E.leg_score = lambda l: SC.get("sc")
E.SCORES_BY["nba"] = {"at": now, "by": {}}
pr = E.stoploss_params([T])
def leg(sc, pre=0.6, ch=0.3, at=None):
    SC["sc"] = sc
    E.SCORES_BY["nba"]["at"] = now if at is None else at
    return E.stop_loss_leg(T, "yes", pre, ch, pr, now)
live = {"state": "in", "frac": 0.4, "detail": "Q3 7:12", "brk": False}
ok("late, fresh, a big fall: this pick qualifies", leg(live) == (True, ""))
ok("no score feed: never", leg(None)[1] == "no score feed")
ok("a stale feed: never", leg(live, at=now - 600)[1] == "score feed stale")
ok("a quarter played: too early (Pete wants later than 25%)", leg(dict(live, frac=0.75, detail="Q2 12:00"))[1] == "too early in the game")
ok("40% played: still too early at the start", leg(dict(live, frac=0.6, detail="Q2 7:12"))[1] == "too early in the game")
ok("halftime: never", leg(dict(live, frac=0.5, detail="Half", brk=True))[1] == "halftime or a break")
ok("end of a quarter: never", leg(dict(live, detail="End Q3"))[1] == "halftime or a break")
ok("clock at 0:00: never", leg(dict(live, detail="Q3 0:00"))[1] == "halftime or a break")
ok("an underdog that started under 50% hasn't 'turned': a small fall isn't enough",
   leg(live, pre=0.42, ch=0.35)[1] == "not far enough below its pregame chance")
ok("still the favourite (over 50%): never", leg(live, pre=0.9, ch=0.55)[0] is False)
ok("no pregame chance: never", leg(live, pre=None)[1] == "no pregame chance")
ok("a game not started: never", leg(dict(live, state="pre", frac=1.0))[0] is False)

# ---- the combo check: confirmed over 3+ checks spanning 3+ minutes
h = {"need": [(("yes", T), "Lakers")], "pre_of": {T: 0.6}, "ch_of": {T: 0.3}, "legs_left": [(0.3, True, 0)], "cost": 10}
SC["sc"] = live
E.MINE.pop("sl_streak", None)
def chk(dt_):
    E.SCORES_BY["nba"]["at"] = now + dt_
    return E.stop_loss_check("C1", h, now + dt_)
r = [chk(0), chk(60), chk(120)]
ok("3 checks in 2 minutes: not yet (waiting to confirm)", all(x == (False, "waiting to confirm the drop") for x in r))
ok("3+ checks spanning 3+ minutes: ready", chk(190) == (True, ""))
SC["sc"] = dict(live, detail="Half", brk=True)
ok("a break in between resets the count", chk(250)[0] is False and "C1" not in E.MINE["sl_streak"])
SC["sc"] = live
r = [chk(300), chk(360), chk(420), chk(480)]
ok("it has to hold again from scratch", r[:3] == [(False, "waiting to confirm the drop")] * 3 and r[3] == (True, ""))
E.MINE.pop("sl_streak", None)
r = [chk(0), chk(60), chk(500), chk(560)]
ok("checks more than 5 minutes apart don't chain", all(x[0] is False for x in r))
E.MINE.pop("sl_streak", None)
h2 = dict(h, need=[(("yes", T), "Lakers"), (("yes", "KXNBAGAME-26NOV19NYKMIA-NYK"), "Knicks")],
          pre_of={T: 0.6, "KXNBAGAME-26NOV19NYKMIA-NYK": 0.6}, ch_of={T: 0.3, "KXNBAGAME-26NOV19NYKMIA-NYK": 0.6})
real_ls = E.leg_score
E.leg_score = lambda l: live if l["ticker"] == T else None          # the other game has no score feed
E.leg_start = lambda l, s: E.dt.datetime.fromtimestamp(now - 3600, E.dt.timezone.utc)
ok("another pick's game is on with no score: never", all(E.stop_loss_check("C2", h2, now + k * 70)[0] is False for k in range(6)))
E.leg_score = lambda l: SC.get("sc")

# ---- auto cash-out: the guard is the only way below cost, and Pause/auto cash-out off still win
sold = []
E.can_trade = lambda: True
E.fresh_offer = lambda t: {"offer": 3.0, "frac": 1.0, "rfq": "x", "contracts": 20, "at": time.time()}
E.wait_threshold = lambda t: 2.0
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], None)
E.sold_today = lambda: 0
E.take_profit_reason = lambda t, h: (None, 0.0)
E.smart_sell_singles = lambda: []
E.accept_cash = lambda t: (sold.append(t), "✅ sold")[1]
logs = []
E.log_decision = lambda rec: logs.append(rec)
E.CFG.update(auto_sell=True, stop_loss=True, auto_hedge=False, auto_cap=5)
E.MINE["hold"] = {"C1": dict(h, label="Combo 1", p=0.15, pays=20, won_some=True, left=1)}
E.MINE.pop("sl_streak", None); E.MINE["busy"] = False; E.MINE.setdefault("selling", set())
plan = {"acts": {"C1": 1.0}}
SC["sc"] = dict(live, frac=0.75, detail="Q2 12:00")
E.auto_sell_now(plan)
ok("switch on, but early in the game: no sale below cost", not sold and logs[-1]["why"] == "below what you paid")
SC["sc"] = live
E.time.time = lambda: now
E.auto_sell_now(plan); E.time.time = lambda: now + 70; E.auto_sell_now(plan)
ok("switch on, conditions met but not yet confirmed: no sale", not sold)
E.time.time = lambda: now + 140; E.auto_sell_now(plan)
E.time.time = lambda: now + 200
E.SCORES_BY["nba"]["at"] = now + 200
out = E.auto_sell_now(plan)
ok("switch on and every guard held for 3+ minutes: it sells, and says why", sold == ["C1"] and out and "Stop-loss" in out[0]
   and logs[-1].get("stop_loss") is True)
sold.clear(); E.CFG["stop_loss"] = False; E.MINE.pop("sl_streak", None)
for k in range(6):
    E.time.time = lambda k=k: now + 300 + 70 * k
    E.SCORES_BY["nba"]["at"] = now + 300 + 70 * k
    E.auto_sell_now(plan)
ok("switch off (the default): never below cost", not sold)
E.CFG.update(stop_loss=True, auto_sell=False)
for k in range(6):
    E.time.time = lambda k=k: now + 900 + 70 * k
    E.SCORES_BY["nba"]["at"] = now + 900 + 70 * k
    E.auto_sell_now(plan)
ok("auto cash-out off / paused: the switch does nothing", not sold)
E.time.time = _real_time
E.leg_score = real_ls

# ---- recorded score lines
ok("score lines: progress and breaks", E._sl_played("nba", "LAL 50–60 BOS Q3 6:00") == (0.625, False)
   and E._sl_played("nba", "LAL 50–60 BOS Half") == (0.5, True) and E._sl_played("nba", "LAL 50–60 BOS End Q3")[1] is True
   and E._sl_played("nhl", "SJS 1–2 VGK P2 10:00") == (0.5, False) and E._sl_played("nba", "LAL 99–100 BOS Final")[0] is None
   and E._sl_played("nba", "")[0] is None)

# ---- learning, league by league: 50 NBA combos that slid all game; selling a bit earlier lost less
E.CFG.update(stop_loss=False, auto_sell=False)
def add_combo(i):
    t = f"KXNBAGAME-26NOV{10 + i % 9:02d}T{i:03d}-AAA"
    kick = now - 86400 * 3 - i * 4000
    E.store_x("insert into ticks values(?,?,?,?,?)", (kick - 1000, t, 0.6, "pre", ""))
    seq = [(0.30, "Q2 4:00"), (0.30, "Q2 3:00"), (0.30, "Q2 2:00"), (0.30, "Q2 1:00"), (0.30, "Q2 0:30"), (0.30, "Half"),
           (0.10, "Q3 11:00"), (0.10, "Q3 10:00"), (0.10, "Q3 9:00"), (0.10, "Q3 8:00"), (0.02, "Q4 5:00"), (0.0, "Final")]
    for k, (ch, sc) in enumerate(seq):
        E.store_x("insert into ticks values(?,?,?,?,?)", (kick + 100 * (k + 1), t, ch, "live", "AAA 40–50 BBB " + sc))
    return {"id": f"paper:{t}", "kind": "combo", "legs": [{"ticker": t, "p": 0.6, "pick": t}], "stake": 10.0, "pays": 20.0,
            "kick": kick, "state": "paper", "result": "lost", "pl": -10.0}
items = [add_combo(i) for i in range(50)]
E._panel_table()
E.store_x("insert or replace into panel values(?,?,?,?,?)", ("2026-11-15", "paper", now - 86400 * 3, "paper",
                                                              json.dumps({"at": now - 86400 * 3, "items": items})))
moved = E.smart_tune(force=True)
d = E.load_json(E.SMART_FILE, {})
ok("NBA learns from its own record: one small step earlier (50% → 45%), the fall size left alone",
   d["nba"]["sl_prog"] == 0.45 and d["nba"]["sl_drop"] == 0.2 and d["nba"]["sl_n"] == 50)
ok("the reason is written down", "45%" in d["nba"].get("sl_why", "") and any("Stop-loss" in m for m in moved))
E.SMART_CACHE["at"] = 0
ok("NBA now uses its own setting", E.stoploss_params([T])["prog"] == 0.45)
ok("a league with no data borrows, but never looser than the start",
   E.stoploss_params(["KXNHLGAME-26NOV19SJSVGK-SJS"]) == {"prog": 0.5, "drop": 0.2, "key": "all"})
s = {r["key"]: r for r in E.smart_summary()}
ok("Results › Selling shows each league's stop-loss settings", s["nba"]["sl_prog"] == 0.45 and s["nba"]["sl_own"] and s["nba"]["sl_why"])
E.save_json(E.SMART_FILE, {"nba": {"sl_prog": 0.45, "sl_drop": 0.2, "sl_n": 10}}); E.SMART_CACHE["at"] = 0
ok("too few results: the setting isn't used, the start stays", E.stoploss_params([T])["prog"] == 0.5)
ok("the bounds keep it later than a quarter of the game", E.SL_BOUNDS["prog"][0] > 0.25)
d0 = {}
ok("short of data, the tuner changes nothing", E._sl_tune(d0, [(items[0], E._sl_paths(items[0]))]) == "" and d0["sl_prog"] == 0.5)
