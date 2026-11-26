# CHECK: group=engine
# Money batch D (issues #421, #452, #450). Guards only; each change makes the app do less or read fresher.
#  #421  autosell_pass (standing take-profit sells) now stops on Pause, and an unreadable Pause counts as paused
#  #452  the retired legacy order fallback carries the forced reduce_only, as the V2 body does
#  #450  a guard check (fetch_account(max_age=0)) asks the hub to skip its 3 second floor; every other read does not
#  #536  that flag is per call (an argument), not a module global a concurrent read can clear
# Kalshi and the network are faked; nothing is sent.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.MAIN_SAVED = os.path.join(E.HERE, "no_shared_settings.json")
from wsrc import watcher_text
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))

# ---- #421: the standing take-profit pass respects Pause
REAL_FA = E.fetch_account
E.AUTOSELL = True
E.can_trade = lambda: True
E.CFG.update(tp_auto=True, tp_follow=True)
PLACED, READS = [], []
E.place_take_profit = lambda t, pays, cost, p=None: (PLACED.append(t), "🎯 placed")[1]
E.combo_chance_now = lambda a: 0.8
E.resting_sells = lambda: {}
E.MINE["hold"] = {}; E.MINE["busy"] = False; E.MINE["selling"] = set()
E.fetch_account = lambda **k: (READS.append(1), ([{"ticker": "C1", "status": "pending", "pays": 20, "cost": 8.0}], 300.0, None))[1]
E.hands_off = lambda t: False
E.TRADING_PAUSED = lambda: False
out = E.autosell_pass()
ok("#421 control: not paused, the pass places its take-profit sell", PLACED == ["C1"] and out == ["C1"], (PLACED, out))
PLACED.clear(); READS.clear()
E.TRADING_PAUSED = lambda: True
out = E.autosell_pass()
ok("#421 Pause on: nothing is placed and the account is not even read", not PLACED and not READS and out == [], (PLACED, READS, out))


def boom():
    raise RuntimeError("pause file unreadable")
E.TRADING_PAUSED = boom
out = E.autosell_pass()
ok("#421 an unreadable Pause counts as paused: nothing is placed", not PLACED and out == [], (PLACED, out))
E.TRADING_PAUSED = lambda: False

# ---- #452: the legacy fallback keeps reduce_only
T = "KXNFLGAME-26NOV30AB-A"
sell = E.order_intent({"ticker": T, "action": "sell", "side": "yes", "count": 3, "yes_price": 40,
                       "time_in_force": "immediate_or_cancel", "client_order_id": "abc"})
ok("#452 setup: a legacy sell is a reduce-only intent that carries its legacy body", sell["reduce_only"] and sell["legacy"] is not None)
lb = E.order_legacy_body(sell)
ok("#452 the legacy fallback of a sell carries reduce_only (it did not before)", lb.get("reduce_only") is True and lb["action"] == "sell", lb)
flagged = E.order_intent({"ticker": T, "action": "buy", "side": "no", "count": 3, "no_price": 60, "reduce_only": True,
                          "time_in_force": "immediate_or_cancel", "client_order_id": "abd"})
ok("#452 a legacy-shaped body that asked for reduce_only keeps it on the fallback",
   flagged["reduce_only"] and E.order_legacy_body(flagged).get("reduce_only") is True)
buy = E.order_intent({"ticker": T, "action": "buy", "side": "yes", "count": 3, "yes_price": 40,
                      "time_in_force": "immediate_or_cancel", "client_order_id": "abe"})
ok("#452 control: a plain buy gets no reduce_only on the fallback", "reduce_only" not in E.order_legacy_body(buy))
v2sell = E.order_intent({"ticker": T, "side": "ask", "count": "3", "price": "0.4000", "reduce_only": True,
                         "time_in_force": "immediate_or_cancel"})
ok("#452 the built legacy body for a V2 sell still carries it too", E.order_legacy_body(v2sell).get("reduce_only") is True)

# ---- #450: a guard check (max_age=0) is a must-be-fresh read at the hub
SEEN = []
E.fetch_account = REAL_FA
E.hub_up = lambda: True
def hub_call(op, timeout=0, **kw):
    SEEN.append(dict(kw))
    return {"value": [[], 7.0, "n"]}
E.hub_call = hub_call
E.ACCT_CACHE.update(at=time.time(), value=([], 1.0, "old"))
E.fetch_account(max_age=0, every_league=True)
ok("#450 max_age=0 asks the hub for a must-be-fresh read", SEEN == [{"fresh": True}], SEEN)
SEEN.clear()
E.ACCT_CACHE.update(at=0, value=None)
E.fetch_account(max_age=15, every_league=True)
ok("#450 an ordinary read does not set the flag", SEEN == [{}], SEEN)
# #536: the flag travels with the call (no module global). A read that another thread runs between a guard's start and
# its hub call (here: inside hub_up, which the guard's own _fetch_account reaches first) used to clear the flag.
ok("#536 there is no module-global fresh flag any more", not hasattr(E, "ACCT_FRESH"))
SEEN.clear()
E.ACCT_CACHE.update(at=0, value=None)
INNER = {"on": False}
def hub_up_racing():
    if not INNER["on"]:
        INNER["on"] = True
        E.ACCT_CACHE.update(at=0, value=None)
        E.fetch_account(max_age=15, every_league=True)       # an ordinary read starts and finishes meanwhile
    return True
E.hub_up = hub_up_racing
E.hub_call = hub_call
E.ACCT_CACHE.update(at=0, value=None)
E.fetch_account(max_age=0, every_league=True)
ok("#536 a concurrent ordinary read cannot clear a guard's must-be-fresh flag", SEEN == [{}, {"fresh": True}], SEEN)
SEEN.clear(); INNER["on"] = False
E.ACCT_CACHE.update(at=0, value=None)
E.fetch_account(max_age=0, every_league=True)
E.ACCT_CACHE.update(at=0, value=None)
E.fetch_account(max_age=15, every_league=True)
ok("#536 a guard read before an ordinary one: the ordinary read is not fresh-flagged", SEEN[-1] == {}, SEEN)
E.hub_call = lambda op, timeout=0, **kw: (_ for _ in ()).throw(RuntimeError("down"))
E.hub_up = lambda: True
try:
    E.fetch_account(max_age=0, every_league=True)
except RuntimeError:
    pass
SEEN.clear()
E.hub_call = hub_call
E.ACCT_CACHE.update(at=0, value=None)
E.fetch_account(max_age=15, every_league=True)
ok("#450 ... after a guard read that raised, the next ordinary read is still not flagged", SEEN == [{}], SEEN)
E.hub_up = lambda: False

hub = watcher_text().split('if op == "account":')[1].split('if op == "pots":')[0]
ok("#450 the hub reads Kalshi now when asked (fresh), skipping the floor hold-back",
   'req.get("fresh")' in hub and "moved = fresh or" in hub and "and not fresh" in hub)
ok("#450 without the flag the old floor is unchanged", "max_age=15 if held or not moved else 0" in hub and E.HUB_FRESH_FLOOR == 3)
