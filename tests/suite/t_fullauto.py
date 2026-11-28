# CHECK: group=engine
# Full auto (issue #7), the real master switch. OFF by default and fail closed: off (or an unreadable file) sends nothing;
# it won't turn on without the paper gate or an explicit override (and records which); it respects the daily cap, the
# open-bet limit, Pause and can_trade; a losing streak makes it cautious (smaller, pickier, never off) and the daily-loss pause trips and ends with the day;
# an unreadable positions read blocks buying. Everything goes through panel_approve / panel_add / panel_exec: Kalshi is
# fake and every call is recorded, so nothing is ever sent.
import os, threading, time, tempfile, json, importlib.util
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
E.fa_set(True, limits={"cap": max(2, cap), "max_open": 30, "day_loss": 100})   # (#632) this scenario tests the cap; the loss room has its own tests
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
E.fa_set(True, limits={"cap": 100, "max_open": 30, "day_loss": 100})
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
ok("3 losses in a row goes cautious (soft brake), and says why", st["caution"]["level"] == 1 and "3 losing" in st["caution"]["why"] and st["on"] is True and not st["brake"])
ok("cautious: it is not paused and not off (it may still act, smaller)", r is None or isinstance(r, dict))
v = E.full_auto_view()
ok("the card shows cautious 50% and why", v["caution"]["level"] == 1 and v["caution"]["pct"] == 50 and "3 losing" in v["caution"]["why"] and v["brake"] is None and v["on"] is True)
okR, _, _ = E.fa_set(True, reset_brake=True)
ok("resetting returns to normal at once and the old losses don't re-trip it", okR and E.fa_check(E.fa_state())["caution"]["level"] == 0 and E.fa_state()["caution"]["level"] == 0)
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
ok("loss-cut exits (real P/L under zero) count toward the brake", E.fa_state()["caution"]["level"] == 1)

# a bet panel_exec swapped in (new id, swap_of = ours) is ours too: its loss counts, and a swap chain too
reset_state()
p = fresh(4); E.fa_set(True, limits={"cap": 100, "max_open": 30, "streak": 2, "day_loss": 100})
E.full_auto_pass(now=time.time()); E.panel_exec()
a_, b_ = day_items()[:2]
E._set_items(day, "real", {a_["id"]: {"state": "swapped"},
    "swp1": dict(a_, id="swp1", swap_of=a_["id"], state="swapped", _new=True),
    "swp2": dict(a_, id="swp2", swap_of="swp1", state="bought", result="lost", pl=-a_["stake"], bought_at=time.time(), _new=True),
    b_["id"]: {"state": "bought", "result": "lost", "pl": -b_["stake"], "bought_at": time.time() + 1}})
v = E.fa_check(now=time.time())
ok("swapped-in bet (and a swap of a swap) counts toward the streak and P/L", v["streak"] == 2 and v["pl"] <= -(a_["stake"] + b_["stake"]) + 0.01)
E.full_auto_pass(now=time.time())
ok("so the streak brake trips on swapped bets", E.fa_state()["caution"]["level"] == 1)
ok("a bet that was never full auto's is not counted", E.fa_check(st=dict(E.fa_state(), bets={}), now=time.time())["streak"] == 0)

# fullauto-harden-144: a swap chain of any depth is followed (and a cycle can't hang it)
reset_state()
p = fresh(4); E.fa_set(True, limits={"cap": 100, "max_open": 30, "streak": 9, "day_loss": 100})
E.full_auto_pass(now=time.time()); E.panel_exec()
a_ = day_items()[0]
ch = {a_["id"]: {"state": "swapped"}}
for i in range(1, 7):
    ch[f"deep{i}"] = dict(a_, id=f"deep{i}", swap_of=(a_["id"] if i == 1 else f"deep{i-1}"), state="swapped" if i < 6 else "bought",
                          result=None if i < 6 else "lost", pl=None if i < 6 else -a_["stake"], bought_at=time.time(), _new=True)
ch[a_["id"]]["swap_of"] = "deep6"                  # a real cycle through one of full auto's own bets: a_ -> deep1 .. deep6 -> a_
E._set_items(day, "real", ch)
v = E.fa_check(now=time.time())
ok("a swap chain 6 deep still counts the final loss as ours", v["streak"] == 1 and v["pl"] <= -a_["stake"] + 0.01)

# old losses stay in bankroll-free and the streak (they used to drop out after 10 days)
later = time.time() + 30 * 86400
vl = E.fa_check(now=later)
ok("a loss from 30 days ago still counts toward bankroll free and the streak", vl["streak"] == 1 and vl["pl"] == v["pl"] and vl["free"] == v["free"])
ok("...but spend and open bets are only the recent view", vl["spent"] == 0 and vl["open"] == 0)

# a limits-save or reset from a stale tab never turns it on; only the explicit turn-on does
reset_state()
okS, msgS, _ = E.fa_set(True, limits={"cap": 5}, explicit_on=False)
ok("limits-save with on=true while off is ignored (stays off, limits unchanged)", not okS and E.fa_state()["on"] is False and E.fa_state()["cap"] != 5)
okS, _, _ = E.fa_set(True, reset_brake=True, explicit_on=False)
ok("a reset with on=true while off does not turn it on", not okS and E.fa_state()["on"] is False)
okS, _, _ = E.fa_set(True, override=True, explicit_on=True)
ok("the explicit turn-on still works", okS and E.fa_state()["on"] is True)
okS, _, _ = E.fa_set(True, limits={"cap": 7}, explicit_on=False)
ok("once it is on, a limits-save from a tab still saves", okS and E.fa_state()["on"] is True and E.fa_state()["cap"] == 7)
E.fa_set(False)
okS, _, _ = E.fa_set(False, limits={"cap": 9})
ok("a stale off tab's Save limits (on=false) leaves full auto off", okS and E.fa_state()["on"] is False and E.fa_state()["cap"] == 9)
# the turn-on decision is re-checked inside the file lock: if it was switched off between the early check and the write
_fs = E.fa_state
_n = [0]
def _flip():
    _n[0] += 1
    return dict(_fs(), on=True) if _n[0] == 1 else _fs()
E.fa_state = _flip
okS, _, _ = E.fa_set(True, limits={"cap": 11}, override=True, explicit_on=False)
E.fa_state = _fs
ok("a racing limits-save can't set on=true inside the write step", not okS and E.fa_state()["on"] is False and E.fa_state()["cap"] != 11)
okS, _, _ = E.fa_set(True, explicit_on="yes")
ok("only a real True counts as the explicit turn-on", not okS and E.fa_state()["on"] is False)
reset_state()

# two passes at once can't overspend the cap
reset_state(); fresh(6); E.fa_set(True, limits={"cap": 30, "max_open": 30})
ts = [threading.Thread(target=E.full_auto_pass, kwargs={"now": time.time()}) for _ in range(4)]
[t.start() for t in ts]; [t.join() for t in ts]
v = E.fa_check(now=time.time())
ok("four passes at once stay inside the daily cap", 0 < v["spent"] <= 30.01)

# the spend cap is per panel day: tomorrow starts at zero
v2 = E.fa_check(now=time.time() + 86400)
ok("today's spend is not carried into the next day", v["spent"] > 0 and v2["spent"] == 0 and v2["room"] == 30)

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

# ---- (#144 soft brake) confidence level: cautious, never off; two-way; never above normal
E.buy_single = lambda t, n, px: (BOUGHT.append((t, n, px)) or (n, None)); E._held_all = lambda: []   # back to the fakes
E._positions_strict = lambda *a, **k: []
def settle(items, results, t0):
    for i, (c, r) in enumerate(zip(items, results)):
        pl = -c["stake"] if r == "L" else 1.0
        E._set_items(day, "real", {c["id"]: {"state": "bought", "result": "lost" if r == "L" else "won", "pl": pl, "bought_at": t0 + i}})

reset_state()
p = fresh(8); E.fa_set(True, limits={"cap": 100, "max_open": 30, "streak": 3, "day_loss": 100})
E.full_auto_pass(now=time.time()); E.panel_exec()
day = E._panel_day(); its = day_items(); t0 = time.time() - 500
settle(its[:3], "LLL", t0)
nw = time.time()
E.full_auto_pass(now=nw)
st = E.fa_state()
v = E.fa_check(st, now=nw)
ok("soft brake: trip makes it cautious, still ON, no pause, logged", st["on"] is True and st["caution"]["level"] == 1 and not st["brake"]
   and any(h.get("ev") == "caution" and "Cautious (50%)" in h.get("text", "") for h in st["history"]))
ok("scaling: the daily cap is halved and room follows it", v["cap"] == 50.0 and v["cap_normal"] == 100 and v["room"] == round(50.0 - v["spent"], 2))
ok("scaling: bet size is half, never under $2, never above normal", E._fa_scaled(10.0, 0.5) == 5.0 and E._fa_scaled(3.0, 0.5) == 2.0
   and E._fa_scaled(2.0, 0.5) == 2.0 and E._fa_scaled(10.0, 1.0) == 10.0 and E._fa_scaled(10.0, 0.25) == 2.5)
ok("the bar goes up one notch (tighten-only)", v["caution"]["bar_extra"] == 0.5 and E._fa_knob(0, "bar") == 0.0)
ok("every level of the ladder is at or below normal", all(r["size"] <= 1 and r["cap"] <= 1 and r["bar"] >= 0 for r in E.FA_LADDER) and E.FA_LADDER[0] == {"size": 1.0, "cap": 1.0, "bar": 0.0})
# the pass really sizes down: a fresh draft panel approved while cautious carries smaller stakes
reset_state(); E.store_x("delete from panel", ())
p = fresh(6); E.fa_set(True, limits={"cap": 100, "max_open": 30, "streak": 9, "day_loss": 100})
normal = {c["id"]: c["stake"] for c in E.panel_get("real")["items"]}
E._fa_update(lambda s: s.update(caution={"level": 1, "base_at": time.time(), "since": time.time(), "why": "test"}))
E.full_auto_pass(now=time.time())
got = [c for c in day_items() if c.get("state") in ("scheduled", "bought", "buying")]
ok("cautious pass approves bets at no more than half their normal size (min $2)", got and all(c["stake"] <= max(2.0, normal[c["id"]] * 0.5) + 0.01 and c["stake"] <= normal[c["id"]] for c in got))
# recovery, steps and floor, on the pure function with made-up settled bets (the engine's real panel is too small for 12 bets)
def bet(i, r):
    return (day, {"id": f"b{i}", "bought_at": 1000 + i, "result": "lost" if r == "L" else "won", "pl": -5.0 if r == "L" else 1.0})
def ev(level, seq, now_=1500, base=999, since=1000):
    st_ = {"streak": 3, "caution": {"level": level, "base_at": base, "since": since, "why": "t"}}
    after_ = [bet(i, r) for i, r in enumerate(seq)]
    run_ = 0
    for _, c in reversed(after_):
        if c["result"] != "lost":
            break
        run_ += 1
    return E._fa_caution_eval(st_, after_, run_, now_)
ok("normal + 3 losses -> cautious 50%, with a history line", ev(0, "LLL", base=0, since=0)["level"] == 1 and "Cautious (50%)" in ev(0, "LLL", base=0, since=0)["events"][0])
ok("normal + 2 losses stays normal", ev(0, "LL", base=0, since=0)["level"] == 0)
ok("cautious + 2 more losses -> 25% (the floor)", ev(1, "LL")["level"] == 2)
ok("the floor holds: many more losses never go lower, never off", ev(2, "LLLLLL")["level"] == 2 and E.FA_LADDER[2]["size"] > 0)
ok("one win: progress 1 of 2, no step yet", ev(2, "W")["level"] == 2 and ev(2, "W")["wins"] == 1 and ev(2, "W")["wins_need"] == 2)
ok("two wins step up one level (25% -> 50%)", ev(2, "WW")["level"] == 1)
ok("four wins from the floor return to normal, then stop (never above normal)", ev(2, "WWWW")["level"] == 0 and ev(0, "WWWW", base=0, since=0)["level"] == 0 and ev(0, "WWWW", base=0, since=0)["factor"] == 1.0)
ok("a loss between wins resets the count", ev(1, "WLW")["level"] == 1 and ev(1, "WLW")["wins"] == 1)
ok("a no-loss exit that made money counts as a win; the level never exceeds normal", all(ev(l, "W" * 9)["level"] >= 0 for l in (0, 1, 2)))
# batches: bets that settle between two passes give the same answer as one at a time
def one_by_one(level, seq, **kw):
    cs = {"level": level, "base_at": kw.get("base", 999), "since": 1000}
    for i, r in enumerate(seq):
        e_ = E._fa_caution_eval({"streak": 3, "caution": cs}, [bet(i, r)] if True else [], 0, 1500)
        cs = e_["saved"]
    return cs["level"]
ok("batch: 4 losses then 2 wins settled together is cautious then back to normal, same as one at a time",
   ev(0, "LLLLWW", base=0, since=0)["level"] == one_by_one(0, "LLLLWW", base=0) == 0)
ok("batch: 3 losses then a win still ends cautious, not normal", ev(0, "LLLW", base=0, since=0)["level"] == 1)
ok("batch: cautious with 2 losses then 2 wins goes down to 25% then up to 50%", ev(1, "LLWW")["level"] == 1)
ok("batch: cautious with 2 losses then 1 win ends at 25%", ev(1, "LLW")["level"] == 2)
ok("batch result is the same fed one bet at a time", all(ev(l, q, base=0)["level"] == one_by_one(l, q, base=0) for l in (0, 1, 2) for q in ("LLLLWW", "LLWW", "WWLLL", "LLLWWLL")))
# pushes are neutral: no win, no loss
def push(i):
    return (day, {"id": f"b{i}", "bought_at": 1000 + i, "result": "push", "pl": 0.0})
def evp(level, seq):
    after_ = [push(i) if r == "P" else bet(i, r) for i, r in enumerate(seq)]
    return E._fa_caution_eval({"streak": 3, "caution": {"level": level, "base_at": 999, "since": 1000}}, after_, 0, 1500)
ok("a push does not count as a win (no recovery)", evp(1, "WPP")["level"] == 1 and evp(1, "WPP")["wins"] == 1 and evp(1, "WPW")["level"] == 0)
ok("a push does not break a losing run or count as one", evp(0, "LLPL")["level"] == 1 and evp(0, "LLP")["level"] == 0)
# out-of-order settling: the first-bought bet settles last; every bet counts once, ordered by settle time
def oo(level, seq, settle_order, saved=None, now_=1500):
    after_ = []
    for i, r in enumerate(seq):
        d_, c_ = bet(i, r)
        c_["settled_at"] = 2000 + settle_order[i]
        after_.append((d_, c_))
    cs = saved or {"level": level, "base_at": 999, "since": 1000}
    return E._fa_caution_eval({"streak": 4 if level == 0 else 3, "caution": cs}, after_, 0, now_)
r_ = oo(0, "LLLL", [3, 0, 1, 2])
ok("out of order: 4 losses where the first-bought settles last still trip to Cautious", r_["level"] == 1)
# the first three settle (the first-bought one is still open), then it settles in a later pass
a1 = E._fa_caution_eval({"streak": 4, "caution": {"level": 0, "base_at": 999, "since": 1000}}, [bet(1, "L"), bet(2, "L"), bet(3, "L")], 0, 1500)
a2 = E._fa_caution_eval({"streak": 4, "caution": a1["saved"]}, [bet(0, "L"), bet(1, "L"), bet(2, "L"), bet(3, "L")], 0, 1500)
ok("out of order: a bet bought earlier but settled in a later pass is counted (not skipped)", a1["level"] == 0 and a2["level"] == 1)
a3 = E._fa_caution_eval({"streak": 4, "caution": a2["saved"]}, [bet(0, "L"), bet(1, "L"), bet(2, "L"), bet(3, "L")], 0, 1500)
ok("re-running the same pass does not double count", a3["level"] == 1 and a3["events"] == [] and a3["saved"]["wl"] == a2["saved"]["wl"])
b1 = E._fa_caution_eval({"streak": 3, "caution": {"level": 0, "base_at": 999, "since": 1000}}, [bet(1, "W"), bet(2, "L")], 0, 1500)
b2 = E._fa_caution_eval({"streak": 3, "caution": b1["saved"]}, [bet(0, "L"), bet(1, "W"), bet(2, "L")], 0, 1500)
ok("out of order: a late-settling loss adds to the run once", b2["saved"]["wl"] == 2 and b1["saved"]["wl"] == 1)
big = [bet(i, "W") for i in range(260)]
g = E._fa_caution_eval({"streak": 3, "caution": {"level": 0, "base_at": 0, "since": 0}}, big, 0, 1500)
g2 = E._fa_caution_eval({"streak": 3, "caution": g["saved"]}, big, 0, 1500)
ok("the counted list stays bounded and pruned bets are not recounted", len(g["saved"]["seen"]) <= E.FA_SEEN_MAX and g2["events"] == [] and not g2["changed"])
# after the counted list is full, a long-open bet bought earlier but settled later still counts
many = []
for i in range(260):
    d_, c_ = bet(i + 10, "W"); c_["settled_at"] = 3000 + i; many.append((d_, c_))
h1 = E._fa_caution_eval({"streak": 2, "caution": {"level": 0, "base_at": 0, "since": 0}}, many, 0, 4000)
late = []
for i, k in enumerate((0, 1)):
    d_, c_ = bet(k, "L"); c_["settled_at"] = 3500 + i; late.append((d_, c_))     # bought long before the dropped ones, settled after
h2 = E._fa_caution_eval({"streak": 2, "caution": h1["saved"]}, many + late, 0, 4000)
ok("after 200+ counted bets, two long-open losses settling later still trip Cautious", len(h1["saved"]["seen"]) == E.FA_SEEN_MAX and h2["level"] == 1)
# calm days: 3 days with no loss step up one level (saved each pass, so the next step needs 3 more)
c2 = {"level": 2, "base_at": 0, "since": 5000, "why": "t"}
e0 = E._fa_caution_eval({"streak": 3, "caution": c2}, [], 0, 5000 + 86400)
e1 = E._fa_caution_eval({"streak": 3, "caution": c2}, [], 0, 5000 + 3.1 * 86400)
e2 = E._fa_caution_eval({"streak": 3, "caution": e1["saved"]}, [], 0, 5000 + 3.1 * 86400 + 3.1 * 86400)
ok("calm days: not yet after 1 day", e0["level"] == 2 and e0["calm_days_left"] is not None)
ok("calm days: 3 days steps up one level", e1["level"] == 1)
ok("calm days: another 3 days is back to normal", e2["level"] == 0)
# manual reset from cautious
E._fa_update(lambda s: s.update(caution={"level": 2, "base_at": 0, "since": nw, "why": "test"}))
okR, _, _ = E.fa_set(True, reset_brake=True)
ok("manual reset returns to normal immediately", okR and E.fa_check(now=time.time())["caution"]["level"] == 0)
# daily loss limit unchanged by caution: still pauses until the next day
reset_state()
p = fresh(4); E.fa_set(True, limits={"cap": 100, "max_open": 30, "streak": 10, "day_loss": 2})
E.full_auto_pass(now=time.time()); E.panel_exec()
day = E._panel_day(); c = day_items()[0]
E._set_items(day, "real", {c["id"]: {"state": "bought", "result": "lost", "pl": -3.0, "bought_at": time.time()}})
E._fa_update(lambda s: s.update(caution={"level": 1, "base_at": 0, "since": time.time(), "why": "x"}))
vv = E.fa_check(now=time.time())
ok("the daily loss limit still pauses (cautious or not) and ends with the day", vv["brake"] and vv["brake"]["kind"] == "day" and any("Paused itself" in b for b in vv["blockers"])
   and E.fa_check(now=time.time() + 2 * 86400)["brake"] is None)
# an older version's saved streak pause becomes caution, not a stop
reset_state()
p = fresh(4); E.fa_set(True, limits={"cap": 100, "max_open": 30, "streak": 3, "day_loss": 100})
E._fa_update(lambda s: s.update(brake={"kind": "streak", "why": "old"}))
vv = E.fa_check(now=time.time())
ok("a legacy streak pause is read as cautious, with no blocker", vv["brake"] is None and vv["caution"]["level"] == len(E.FA_LADDER) - 1 and not any("Paused itself" in b for b in vv["blockers"]))
ok("a legacy pause starts at the lowest level (25%) with a plain note on the card", vv["caution"]["pct"] == 25 and "before this update" in vv["caution"]["why"] and "Back to normal now" in vv["caution"]["why"])
# only a real master switch turns it off
ok("cautious never turns the switch off", E.fa_state()["on"] is True)
okO, _, _ = E.fa_set(False)
ok("the master switch off still turns it off", okO and E.fa_state()["on"] is False)


# ---- release 145 review fixes: a daily-loss brake from an earlier day, a reset during a pass, cautious over a learned bar
reset_state()
today = E._panel_day(time.time())
E._fa_update(lambda s: s.update(brake={"kind": "day", "day": "2000-01-01", "why": "old"}, caution={"level": 0, "base_at": 0, "since": 0, "why": ""}))
ok("a daily-loss brake from an earlier day does not count as cautious (loosening allowed)", E.ap_brake_cautious(E.fa_state()) is False)
ok("... and the card shows no active brake", E.fa_check(now=time.time())["brake"] is None)
E._fa_update(lambda s: s.update(brake={"kind": "day", "day": today, "why": "now"}))
ok("a same-day daily-loss brake still counts as cautious", E.ap_brake_cautious(E.fa_state()) is True)
E._fa_update(lambda s: s.update(brake={"kind": "day", "why": "no day"}))
ok("a day brake with no readable day fails closed", E.ap_brake_cautious(E.fa_state()) is True)
E._fa_update(lambda s: s.update(brake={"kind": "streak", "why": "old"}))
ok("a streak brake still counts as cautious", E.ap_brake_cautious(E.fa_state()) is True)
E._fa_update(lambda s: s.update(brake=None, caution={"level": 1, "base_at": 0, "since": 0, "why": "x"}))
ok("caution level above 0 still counts as cautious", E.ap_brake_cautious(E.fa_state()) is True)
# seed a real $20 loss today against a $20 limit: the daily-loss limit must still block buying the same day
reset_state()
p = fresh(4); E.fa_set(True, limits={"cap": 100, "max_open": 30, "streak": 10, "day_loss": 20})
E.full_auto_pass(now=time.time()); E.panel_exec()
day = E._panel_day(); c = day_items()[0]
E._set_items(day, "real", {c["id"]: {"state": "bought", "result": "lost", "pl": -20.0, "bought_at": time.time()}})
E._fa_update(lambda s: s.update(brake=None, caution={"level": 0, "base_at": 0, "since": 0, "why": ""}))
vv = E.fa_check(now=time.time())
ok("the daily-loss limit still blocks buying the same day ($20 lost, $20 limit)",
   vv["loss_today"] <= -20 and vv["brake"] and vv["brake"]["kind"] == "day" and any("Paused itself" in b for b in vv["blockers"]))
E._fa_update(lambda s: s.update(brake={"kind": "day", "day": "2000-01-01", "why": "old"}))
ok("a yesterday-dated day brake does not block loosening", E.ap_brake_cautious(E.fa_state()) is False)
E._fa_update(lambda s: s.update(brake={"kind": "day", "day": E._panel_day(time.time()), "why": "now"}))
ok("... while a same-day one does", E.ap_brake_cautious(E.fa_state()) is True)

# a 'Back to normal now' tap during the pass is not overwritten by the pass's older read
reset_state()
E.fa_set(True, override=True, limits={"cap": 100, "max_open": 30, "streak": 3, "day_loss": 100})
E._fa_update(lambda s: s.update(caution={"level": 1, "base_at": 0, "since": time.time(), "why": "x"}))
_orig_check = E.fa_check
def _tap_during(*a, **k):
    v = _orig_check(*a, **k)
    E.fa_set(True, reset_brake=True)                      # Pete taps reset after the pass read its state
    v["caution"] = dict(v["caution"], changed=True, level=2, saved={"level": 2, "base_at": 0, "since": 0, "why": "late"}, events=["late step"])
    return v
E.fa_check = _tap_during
try:
    E._full_auto_pass(now=time.time(), log=lambda *a: None)
finally:
    E.fa_check = _orig_check
ok("a reset during the pass survives (caution stays at normal)", E.fa_state()["caution"]["level"] == 0)

# the cautious bar adds to the learned bar (never below it)
def _combo(pct):
    legs = [{"ticker": "KXNBAGAME-G1-A", "event": "KXNBAGAME-G1"}, {"ticker": "KXNBAGAME-G2-B", "event": "KXNBAGAME-G2"}]
    return {"kind": "combo", "code": "nba", "legs": legs, "pct": pct}
_cut = E.combo_cutoff("nba", 2, _combo(0)["legs"])
_lg = E.bet_key([l["ticker"] for l in _combo(0)["legs"]])
_c = _combo(_cut + 0.0125)                                # clears learned 1.0 alone, not learned 1.0 + cautious 0.5
k0, h0 = E._fa_caution_bar([_c], 1)
k1, h1 = E._fa_caution_bar([_c], 1, {_lg: 1.0})
k2, h2 = E._fa_caution_bar([_combo(_cut + 0.0155)], 1, {_lg: 1.0})
ok("without a learned bar the cautious notch is unchanged", len(k0) == 1 and not h0)
ok("cautious level 1 adds 0.5 on top of a learned +1.0", not k1 and len(h1) == 1 and len(k2) == 1)

# ---- (#633) wording nits, exact text
ok("633: 5%-compounded stake steps show whole percents (0.9025 -> 90%)", E._fal_val_text("stake", 0.9025) == "90% of today's bet size")
ok("633: cap use shows whole percents", E._fal_val_text("capuse", 0.8) == "80% of your daily cap")
ok("633: the Mix league's budget share reads 'mixed-sports budget share'", E._fal_name("share:mix") == "mixed-sports budget share", E._fal_name("share:mix"))
ok("633: money() puts the minus before the dollar sign", E.money(-3.5) == "-$3.50" and E.money(-12) == "-$12")
ok("633: the cap-used-up sentence names spent and cap in plain words",
   any(b.startswith("Today's spending cap is used up: $") and " of $" in b and b.endswith(" spent.") or "spent. Autopilot" in b for b in v["blockers"]), v["blockers"])
