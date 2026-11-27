# CHECK: group=engine
# Full auto (issue #7), the real master switch. OFF by default and fail closed: off (or an unreadable file) sends nothing;
# it won't turn on without the paper gate or an explicit override (and records which); it respects the daily cap, the
# open-bet limit, Pause and can_trade; the losing-streak and daily-loss brakes trip, say why and stay tripped until reset;
# an unreadable positions read blocks buying. Everything goes through panel_approve / panel_add / panel_exec: Kalshi is
# fake and every call is recorded, so nothing is ever sent.
import os, time, tempfile, json, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.injury_note = lambda code, *teams, hours=48: ([], False)
import datetime as _dt; _u = _dt.datetime.now(_dt.timezone.utc); E.PACIFIC = _dt.timezone(_dt.timedelta(hours=round(12 - _u.hour - _u.minute / 60)))
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.REBUILD_FLAG = os.path.join(E.HERE, "panel_rebuild.flag"); E.REBUILD_STATE = os.path.join(E.HERE, "combo_rebuild.json")
E.BUY_FLAG = os.path.join(E.HERE, "panel_buy.flag")
E.fetch_account = lambda **k: ([], 300.0, None)
E.account_events = lambda *a, **k: set()
SENT = []
E.kalshi_send = lambda *a, **k: (SENT.append((a, k)) or {})          # every Kalshi call is recorded, none leaves
E.book_depth = lambda t, max_age=60: {"ask": 0.50, "bid": 0.49}
BOUGHT = []
BUY_REAL = E.buy_single
E.buy_single = lambda t, n, px: (BOUGHT.append((t, n, px)) or (n, None))
E.can_trade = lambda: True
HELD_REAL = E._held_all
E._held_all = lambda: []
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()


def mk(t, ev, f, p, k):
    l = {"ticker": t, "event": ev, "pick": t, "p": p, "fair": f}; E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(k))
    return E._cand("single", "nba", [l], f, (f - p - E.single_fee(p)) / (p + E.single_fee(p)), "w", price=p)


def fresh(n=5):
    """A new draft panel of n different games (a clean slate for each case)."""
    E._panel_table()
    E.store_x("delete from panel", ())
    cs = [mk(f"T{i}", f"KXNBAGAME-G{i}", .60 + i / 100, .50, now + 9000) for i in range(n)]
    E.PANEL_POOL = {"nba": (time.time(), cs)}
    E.panel_pass()
    return E.panel_get("real")


def reset_state():
    try:
        os.remove(E._fa_path())
    except OSError:
        pass
    E.TRADING_PAUSED = None
    BOUGHT.clear(); SENT.clear()


def day_items():
    return E.panel_get("real")["items"]


# ---- off by default: nothing is approved, nothing sent
reset_state()
p = fresh()
ok("full auto is off with no file", E.fa_state()["on"] is False and E.full_auto_view()["on"] is False)
ok("off: the pass does nothing", E.full_auto_pass(now=now) is None and E.panel_get("real")["status"] == "draft")
E.panel_exec()
ok("off: nothing bought, nothing sent to Kalshi", not BOUGHT and not SENT)
open(E._fa_path(), "w").write("{not json")
ok("an unreadable file means off", E.fa_state()["on"] is False and E.full_auto_pass(now=now) is None)
open(E._fa_path(), "w").write(json.dumps({"on": "yes"}))
ok("only a real true turns it on", E.fa_state()["on"] is False)
reset_state()

# ---- turning on: the paper gate, or an explicit override that is recorded
E.panel_record = lambda: {"paper": {"ready": False, "bets": 12, "pl": 3.0, "days": 4, "days_up": 3, "clv": None}, "real": {}}
okA, msgA, xa = E.fa_set(True)
ok("turning on without the gate is refused and asks for the override", not okA and xa.get("needs_override") and not E.fa_state()["on"])
okB, msgB, _ = E.fa_set(True, override="yes")
ok("only an explicit True overrides", not okB and not E.fa_state()["on"])
E.can_trade = lambda: False
okC, _, _ = E.fa_set(True, override=True)
ok("a computer that can't trade can't turn it on", not okC and not E.fa_state()["on"])
E.can_trade = lambda: True
okD, msgD, _ = E.fa_set(True, override=True)
st = E.fa_state()
ok("override turns it on and records the choice", okD and st["on"] and st["gate"] == "overridden" and st["paper"]["bets"] == 12
   and st["history"][-1]["ev"] == "on" and st["history"][-1]["gate"] == "overridden")
E.fa_set(False)
ok("off is always allowed", not E.fa_state()["on"])
E.panel_record = lambda: {"paper": {"ready": True, "bets": 60, "pl": 40.0, "days": 20, "days_up": 14, "clv": 0.01}, "real": {}}
okE, _, _ = E.fa_set(True)
ok("with the gate passed it turns on, recorded as passed", okE and E.fa_state()["gate"] == "passed")
okF, _, _ = E.fa_set(True, limits={"cap": 999})
ok("a limit out of range is refused", not okF and E.fa_state()["cap"] == 30.0)
E.fa_set(True, limits={"cap": 12, "max_open": 4})
ok("limits save and clamp", E.fa_state()["cap"] == 12.0 and E.fa_state()["max_open"] == 4 and E.fa_state()["gate"] == "passed")
reset_state()

# ---- the daily cap
p = fresh(6)
stakes = [c["stake"] for c in p["items"]]
cap = round(stakes[0] + stakes[1] + 0.5, 2)
E.fa_set(True, limits={"cap": max(2, cap), "max_open": 30})
res = E.full_auto_pass(now=time.time())
sp = E.panel_get("real")
live = [c for c in sp["items"] if c["state"] == "scheduled"]
ok("on: it approves the draft through panel_approve", res and res["ok"] and sp["status"] == "approved")
ok("the cap is respected", sum(c["stake"] for c in live) <= max(2, cap) + 0.01 and 0 < len(live) < len(p["items"]))
E.panel_exec()
ok("only the approved bets are bought", len(BOUGHT) == len(live))
n0 = len(BOUGHT)
E.PANEL_POOL["nba"] = (time.time(), E.PANEL_POOL["nba"][1] + [mk("X9", "KXNBAGAME-X9", .70, .50, now + 9000)])
E.panel_pass()
v = E.fa_check(E.fa_state(), now=time.time())
E.full_auto_pass(now=time.time()); E.panel_exec()
ok("at the cap: no extras are added, nothing more is bought", len(BOUGHT) == n0 and E.fa_check(E.fa_state())["spent"] <= max(2, cap) + 0.01)
ok("the card says the cap is used up", v["room"] < 2.0 and any("spending cap is used up" in b for b in v["blockers"]))

# ---- room under the cap: extras are added through panel_add
reset_state()
p = fresh(2)
E.fa_set(True, limits={"cap": 100, "max_open": 30})
E.full_auto_pass(now=time.time()); E.panel_exec()
n1 = len(BOUGHT)
X1 = mk("X1", "KXNBAGAME-X1", .72, .50, now + 9000)
E.PANEL_POOL["nba"] = (time.time(), E.PANEL_POOL["nba"][1] + [X1])
E.panel_pass()
r = E.full_auto_pass(now=time.time()); E.panel_exec()
ok("with room left, a new extra is added by panel_add and bought once", r and X1["id"] in {c["id"] for c in day_items() if c["state"] in E.PANEL_LIVE}
   and len(BOUGHT) == n1 + 1)
E.full_auto_pass(now=time.time()); E.panel_exec()
ok("running the pass again buys nothing twice", len(BOUGHT) == n1 + 1)

# ---- the open-bet limit
reset_state()
p = fresh(5)
E.fa_set(True, limits={"cap": 100, "max_open": 2})
E.full_auto_pass(now=time.time()); E.panel_exec()
ok("max open bets is respected", len(BOUGHT) == 2 and E.fa_check(E.fa_state())["slots"] == 0)

# ---- Pause and can_trade
reset_state()
fresh(3); E.fa_set(True)
ok("Pause (from the watcher) blocks it", E.full_auto_pass(paused=True, now=time.time()) is None and E.panel_get("real")["status"] == "draft")
E.TRADING_PAUSED = lambda: True
ok("Pause (the app's) blocks it", E.full_auto_pass(now=time.time()) is None and E.panel_get("real")["status"] == "draft")
ok("the card says Pause is on", any("Pause" in b for b in E.full_auto_view()["blockers"]))
E.TRADING_PAUSED = None
ok("a computer that can't trade is blocked", E.full_auto_pass(may_trade=False, now=time.time()) is None and E.panel_get("real")["status"] == "draft")
# paused after approval: the shared buy path holds the bets, nothing sent
reset_state(); fresh(3); E.fa_set(True)
E.full_auto_pass(now=time.time()); E.panel_exec(paused=True)
ok("approved, then Pause: nothing is bought", not BOUGHT and not SENT)

# ---- an unreadable positions read blocks buying (fail closed)
reset_state()
fresh(3); E.fa_set(True)


def boom():
    raise RuntimeError("positions unreadable")
E._held_all = boom
ok("a failed positions read: nothing approved", E.full_auto_pass(now=time.time()) is None and E.panel_get("real")["status"] == "draft")
E.panel_exec()
ok("...and nothing bought or sent", not BOUGHT and not SENT)
E._held_all = HELD_REAL
E._positions_strict = boom                    # the real check, reading through the real strict positions read
ok("the real held-bets read fails closed too", E.full_auto_pass(now=time.time()) is None and E.panel_get("real")["status"] == "draft"
   and not BOUGHT and not any(a and a[0] and a[0][0] == "POST" for a in SENT))
E._held_all = lambda: []
E.full_auto_pass(now=time.time())
ok("readable again: it goes", E.panel_get("real")["status"] == "approved")

# ---- the losing-streak brake and the daily loss limit
reset_state()
p = fresh(8); E.fa_set(True, limits={"cap": 100, "max_open": 30, "streak": 3, "day_loss": 100})
E.full_auto_pass(now=time.time()); E.panel_exec()
day = E._panel_day()
items = day_items()
for i, c in enumerate(items[:3]):
    E._set_items(day, "real", {c["id"]: {"state": "bought", "result": "lost", "pl": -c["stake"], "bought_at": time.time() - 100 + i}})
E.panel_pass()
r = E.full_auto_pass(now=time.time())
st = E.fa_state()
ok("3 losses in a row trips the brake and says why", st["brake"] and st["brake"]["kind"] == "streak" and "3 losing" in st["brake"]["why"])
ok("tripped: nothing more is approved or added", r is None)
v = E.full_auto_view()
ok("the card shows the brake", v["brake"] and any("Paused itself" in b for b in v["blockers"]))
okR, _, _ = E.fa_set(True, reset_brake=True)
ok("resetting clears it and the old losses don't re-trip it", okR and E.fa_state()["brake"] is None and E.fa_check(E.fa_state())["brake"] is None)
reset_state()
p = fresh(4); E.fa_set(True, limits={"cap": 100, "max_open": 30, "streak": 10, "day_loss": 2})
E.full_auto_pass(now=time.time()); E.panel_exec()
c = day_items()[0]
E._set_items(day, "real", {c["id"]: {"state": "bought", "result": "lost", "pl": -3.0, "bought_at": time.time()}})
E.full_auto_pass(now=time.time())
st = E.fa_state()
ok("the daily loss limit trips the brake", st["brake"] and st["brake"]["kind"] == "day" and "today" in st["brake"]["why"])
ok("a daily-loss brake ends with the day", E.fa_check(st, now=time.time() + 2 * 86400)["brake"] is None)

# a bet that was sold early (loss cut) counts by what it really made, even when its result says "won"
reset_state()
p = fresh(4); E.fa_set(True, limits={"cap": 100, "max_open": 30, "streak": 2, "day_loss": 100})
E.full_auto_pass(now=time.time()); E.panel_exec()
for i, c in enumerate(day_items()[:2]):
    E._set_items(day, "real", {c["id"]: {"state": "bought", "result": "won", "pl": 1.0, "pl_real": -c["stake"] / 2, "bought_at": time.time() + i}})
E.full_auto_pass(now=time.time())
ok("loss-cut exits (real P/L under zero) count toward the brake", E.fa_state()["brake"] and E.fa_state()["brake"]["kind"] == "streak")

# the real buy path: approved by full auto, then the positions can't be read at buy time: the shared guards refuse, nothing is sent
reset_state(); E._panel_table(); E.store_x("delete from panel", ())
E.PANEL_POOL = {"nba": (time.time(), [mk("KXNBAGAME-26NOV30LALBOS-LAL", "KXNBAGAME-26NOV30LALBOS", .66, .50, now + 9000),
                                      mk("KXNBAGAME-26NOV30NYKMIA-NYK", "KXNBAGAME-26NOV30NYKMIA", .65, .50, now + 9000)])}
E.panel_pass(); E.fa_set(True)
E.full_auto_pass(now=time.time())
ok("(setup) full auto approved real-looking tickers", E.panel_get("real")["status"] == "approved")
E.buy_single = BUY_REAL; E._held_all = HELD_REAL; E._positions_strict = boom
E.panel_exec()
ok("the real buy_single fails closed on an unreadable positions read: no order", not BOUGHT and not any(a[0] == "POST" for a, k in SENT)
   and all(c["state"] == "scheduled" and c.get("hold") == "bets" for c in day_items() if c["state"] != "left out"))

# ---- the switch can't be reached through ordinary settings
E.CFG["full_auto"] = True
reset_state()
ok("a stray full_auto setting does nothing", E.fa_state()["on"] is False)
ok("it is not a shared or synced setting", "full_auto" not in E.SHARED_KEYS and "full_auto" not in getattr(E, "WATCHER_SYNCED", ()))
ok("through all of it nothing real was sent", not SENT)
