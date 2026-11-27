# CHECK: group=engine
# The cautious default loss cut (option A): a COMBO in a league with no record of its own may be cut at a 12.5% win chance,
# under every existing guard (fresh score, not a break, past half the game, pick under 50% and 20+ points below its
# pregame chance, 3+ checks over 3+ minutes, a real offer). A league's own value replaces it; the switch
# `loss_cut_default` off restores the old "never". No real orders: every trading call is faked here.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl"); E.PREGAME = os.path.join(E.HERE, "pregame.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
T = "KXNBAGAME-26NOV19LALBOS-LAL"
E.CFG.update(smart_sell=True, ride=2, take_profit=0, lock_trail=False, stop_loss=False, auto_hedge=False, auto_cap=5,
             auto_sell=True, loss_cut_default=True)
E.save_json(E.SMART_FILE, {}); E.SMART_CACHE["at"] = 0

# ---- what the settings say
p = E.smart_params([T])
ok("default on, no record: a combo gets 12.5%, marked as the default", p["loss"] == 0.125 and p.get("loss_src") == "default" and E.LOSS_CUT_DEFAULT == 0.125)
ok("...the same in a league that never had a record (soccer)", E.smart_params(["KXEPLGAME-26NOV22ARSCHE-ARS"])["loss"] == 0.125)
ok("singles never get the default", E.smart_params([T], single=True)["loss"] is None)
E.CFG["loss_cut_default"] = False
ok("switch off: the old 'never' is back", E.smart_params([T])["loss"] is None and "loss_src" not in E.smart_params([T]))
E.CFG["loss_cut_default"] = True
E.save_json(E.SMART_FILE, {"nba": {"floor": 1.5, "lam": 1.0, "loss": 0.2, "n": 40}}); E.SMART_CACHE["at"] = 0
p = E.smart_params([T])
ok("a league's own tuned value overrides the default", p["loss"] == 0.2 and "loss_src" not in p)
E.save_json(E.SMART_FILE, {"nba": {"floor": 1.5, "lam": 1.0, "loss": None, "n": 40}}); E.SMART_CACHE["at"] = 0
ok("a stored None nothing chose (an untouched league's entry) still gets the default", E.smart_params([T])["loss"] == 0.125)
E.save_json(E.SMART_FILE, {"nba": {"floor": 1.5, "lam": 1.0, "loss": None, "loss_off": True, "n": 40}}); E.SMART_CACHE["at"] = 0
ok("...but a league whose own tuning chose 'stop cutting' stays off", E.smart_params([T])["loss"] is None)
E.save_json(E.SMART_FILE, {"all": {"floor": 1.5, "lam": 1.0, "loss": 0.2, "n": 90}}); E.SMART_CACHE["at"] = 0
ok("a borrowed loss cut is still never borrowed: the default, not everyone's 20%", E.smart_params([T])["loss"] == 0.125)
E.save_json(E.SMART_FILE, {}); E.SMART_CACHE["at"] = 0

# ---- the guards, on a faked score feed (same set-up as t_cutloss.py)
SC = {"sc": None}
E.leg_score = lambda l: SC["sc"]
E.SCORES_BY["nba"] = {"at": now, "by": {}}
E.leg_start = lambda l, s: E.dt.datetime.fromtimestamp(now - 3600, E.dt.timezone.utc)
live = {"state": "in", "frac": 0.4, "detail": "Q3 7:12", "brk": False}
early = dict(live, frac=0.75, detail="Q2 12:00")
def hold(p):
    return {"label": "Lakers combo", "need": [(("yes", T), "Lakers")], "pre_of": {T: 0.6}, "ch_of": {T: p},
            "legs_left": [(p, True, 0)], "cost": 10, "p": p, "pays": 20, "won_some": False, "left": 1}
sold, logs = [], []
E.can_trade = lambda: True
E.get_cash_offer = lambda t, f=1.0: {"offer": 1.2, "frac": 1.0, "rfq": "x", "contracts": 20, "at": E.time.time()}
E.fresh_offer = lambda t: None
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], None)
E.sold_today = lambda: 0
E.smart_sell_singles = lambda: []
E.accept_cash = lambda t, floor=None: (sold.append(t), "✅ sold")[1]
real_log = E.log_decision
E.log_decision = lambda rec: (logs.append(rec), real_log(rec))
E.MINE["busy"] = False; E.MINE.setdefault("selling", set()); E.MINE["cash"] = {}
plan = {"acts": {}}
base = [0]

def run(p, sc, n=6):
    """n checks 100 s apart (a fresh streak each call); True if the combo was sold."""
    sold.clear(); logs.clear(); E.MINE["sl_streak"] = {}; base[0] += 10000
    SC["sc"] = sc
    for k in range(n):
        t = base[0] + k * 100
        E.time.time = lambda t=t: now + t
        E.SCORES_BY["nba"]["at"] = now + t
        E.MINE["hold"] = {"C1": hold(p)}
        E.MINE["cash"] = {}
        E.auto_sell_now(plan)
    return bool(sold)

ok("12% chance, every guard held: the default cut fires", run(0.12, live))
fire = [r for r in logs if r.get("result") == "sold" and r.get("why") == "cut loss"]
lc = fire[0].get("loss_cut") if fire else {}
ok("...and the firing is recorded: legs, win chance, offer vs cost, cut-off, source",
   bool(lc) and lc["legs"] == [T] and lc["chance"] == 0.12 and lc["offer"] == 1.2 and lc["cost"] == 10
   and lc["cutoff"] == 0.125 and lc["src"] == "default")
ok("12.5% exactly fires (at or under)", run(0.125, live))
ok("14% (above 12.5%) never fires", not run(0.14, live))
ok("guard: early in the game, never", not run(0.12, early))
ok("guard: halftime, never", not run(0.12, dict(live, detail="Half", brk=True)))
ok("guard: fewer than 3 checks, never", not run(0.12, live, n=2))
E.get_cash_offer = lambda t, f=1.0: {"offer": 0.1, "frac": 1.0, "rfq": "x", "contracts": 20, "at": E.time.time()}
ok("guard: an offer under 2% of cost, never", not run(0.12, live))
E.get_cash_offer = lambda t, f=1.0: {"offer": 1.2, "frac": 1.0, "rfq": "x", "contracts": 20, "at": E.time.time()}
ok("guard: a stale score feed, never", not (setattr(E, "leg_score", lambda l: None) or run(0.12, live)))
E.leg_score = lambda l: SC["sc"]
E.CFG["auto_sell"] = False
ok("Pause (auto cash-out off): never", not run(0.12, live))
E.CFG["auto_sell"] = True
E.CFG["loss_cut_default"] = False
ok("switch off: the old behaviour, no cut", not run(0.12, live))
E.CFG["loss_cut_default"] = True
E.save_json(E.SMART_FILE, {"nba": {"floor": 1.5, "lam": 1.0, "loss": 0.2, "n": 40}}); E.SMART_CACHE["at"] = 0
ok("a league's own 20% fires where the 12.5% default would not (16%)", run(0.16, live))
fire = [r for r in logs if r.get("result") == "sold" and r.get("why") == "cut loss"]
ok("...and the record says it was the league's own value", bool(fire) and fire[0]["loss_cut"]["src"] == "league" and fire[0]["loss_cut"]["cutoff"] == 0.2)
TK = ["KXNBAGAME-26NOV19LALBOS-LAL"]
E.save_json(E.SMART_FILE, {"nba": {"floor": 1.5, "lam": 1.0, "loss": None, "n": 40}}); E.SMART_CACHE["at"] = 0
ok("a tuned league that merely stored 'no cut' (no explicit off marker) keeps the default", E.smart_params(TK).get("loss") == E.LOSS_CUT_DEFAULT)
E.save_json(E.SMART_FILE, {"nba": {"floor": 1.5, "lam": 1.0, "loss": None, "loss_off": True, "n": 40}}); E.SMART_CACHE["at"] = 0
ok("...but a league the tuner explicitly turned the cut off for stays off", E.smart_params(TK).get("loss") is None)
