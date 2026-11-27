# CHECK: group=engine
# The momentum shadow recorder (mom_record in the engine): write-only, off the selling path.
#  A  rows land in mom_shadow / mom_after / mom_peak (synthetic DB: the dev Mac has no history, hard rule 9)
#  B  an error inside the recorder never reaches selling: take_profit_reason / single_sell_reason answer the same
#  C  the log lines: "MOMENTUM would sell" once per episode, "NO SELL ... blocked by ..." every 10 min per bet
#  D  the kill switch, the throttle, and pruning/caps
#  E  nothing reads the tables back into a decision; the card text says what smart sell really waits for
import os, re, io, threading, tempfile, importlib.util, traceback, contextlib
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
REPO = os.environ.get("REPO") or os.path.abspath("../..")
T = "KXMVE-TEST1"


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def reset():
    E.mom_flush()
    for k in ("q", "peak", "peak_saved", "seen", "told", "ep", "last", "pos"):
        E.MOM[k].clear()
    E.MOM["pend"].clear(); E.MOM["labeled"].clear(); E.MOM["ops"].clear(); E.MOM["prune"] = 0.0
    for tb in ("mom_shadow", "mom_after", "mom_peak"):
        E.store_x(f"delete from {tb}")


def R(sql, args=()):
    E.mom_flush()                                  # the recorder writes on a background thread: run its queue now
    return E.store_rows(sql, args)


def count(tb):
    return R(f"select count(*) n from {tb}")[0]["n"]


def say(fn):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = fn()
    return r, buf.getvalue()


NO = {"sell": False, "reason": None, "threshold": 0.0, "floor": 4.0}


def rec(q, o_net, now_shift=0.0, d=NO, t=T, real=True, live=True):
    return E.mom_record("combo", t, live, q, 10.0, 5.0, o_net, o_net if real else 0.0, real, 3.0, d)


class _Clock:
    def __init__(self, v): self.v = v
    def time(self): return self.v[0]
    def __getattr__(self, k): return getattr(_real_time, k)


import time as _real_time


def clock(v):
    E.time = _Clock(v)


def a_rows():
    reset()
    clock(t0 := [1000.0])
    r1 = rec(0.61, 4.9)
    t0[0] += 40
    r2 = rec(0.44, 4.91)                      # a fall of 17 points: verdict flips, so a row is written
    ok("A both evaluations wrote a row (first sight, then a changed verdict)", r1 and r2 and count("mom_shadow") == 2, count("mom_shadow"))
    row = R("select q, q_peak_w, dq, z, o_net, cost, real_flag, today_sell, today_reason, why_not, m_protect, m_cut, paused from mom_shadow order by ts desc limit 1")[0]
    ok("A the row carries q, its recent high, the drop, z, the net offer, cost, today's call and why not",
       row["q"] == 0.44 and row["q_peak_w"] == 0.61 and row["dq"] == -0.17 and row["z"] > 2 and row["o_net"] == 4.91 and row["cost"] == 5.0
       and row["real_flag"] == 1 and row["today_sell"] == 0 and row["today_reason"] == "hold" and row["why_not"] == "q<50%" and row["m_protect"] == 1 and row["paused"] == 0, row)
    ok("A a flagged row also opens a mom_after row", count("mom_after") == 1)
    ok("A the peak is persisted", R("select o_peak from mom_peak where ticker=?", (T,))[0]["o_peak"] >= 4.9)
    for secs in (31, 40, 240, 700, 2800):
        t0[0] += secs
        rec(0.44, 4.5 + secs / 1000)
    after = R("select o30, o60, o300, o900, o3600, o_min from mom_after")[0]
    ok("A mom_after fills the later offers as time passes (+30 s .. +60 min) and tracks the lowest", all(after[k] is not None for k in ("o30", "o60", "o300", "o900", "o3600")) and after["o_min"] <= 4.54, after)
    # a restart forgets memory but not the peak
    E.MOM["peak"].clear(); E.MOM["peak_saved"].clear(); t0[0] += 5
    rec(0.44, 4.0); E.mom_flush()
    ok("A after a restart the saved peak is picked up again (shadow dict only)", E.MOM["peak"][T] >= 4.91 and T not in (E.MINE.get("peak") or {}))
    E.mom_settle(T, "lost", 0)
    ok("A the settlement label lands on the flagged rows", R("select outcome, payout from mom_after")[0] == {"outcome": "lost", "payout": 0.0})


def b_swallow():
    reset()
    clock([5000.0])
    db = E.STORE["db"]
    E.STORE["db"] = None
    ok("B no history open: False, no raise", rec(0.6, 4.0) is False)
    E.STORE["db"] = db
    class Broken:
        in_transaction = False
        def execute(self, *a, **k): raise RuntimeError("closed")
    E.STORE["db"] = Broken(); E.MOM["db"] = None
    try:
        ok("B a broken connection is swallowed", isinstance(say(lambda: rec(0.6, 4.0))[0], bool))
    finally:
        E.STORE["db"] = db; E.MOM["db"] = None
    ok("B junk input is swallowed", say(lambda: E.mom_record("combo", T, True, "x", None, None, None, None, None, None, {}))[0] is False)
    # the selling functions answer the same with a recorder that blows up
    h = {"left": 1, "pays": 10.0, "p": 0.7, "cost": 5.0, "legs_left": [(0.7, True, 0)], "need": [(("yes", "KXA-1"), "")], "hold": 6.0}
    E.MINE["hold"][T] = h
    E.MINE["cash"][T] = {"offer": 7.5, "frac": 1.0, "rfq": "real", "at": E.time.time()}
    E.CFG.update(smart_sell=True, ride=2)
    ref = E.take_profit_reason(T, h)
    def boom(*a, **k): raise RuntimeError("recorder bug")
    old = E.mom_record
    E.mom_record = boom
    try:
        got = E.take_profit_reason(T, h)
        x = {"t": "KXS-1", "n": 10, "cost": 4.0, "chance": 0.8, "state": "live", "kind": "win", "side": "yes", "sport": "nba"}
        s1 = E.single_sell_reason(x, 0.6, 0.62)
    finally:
        E.mom_record = old
    s2 = E.single_sell_reason(x, 0.6, 0.62)
    ok("B a recorder that raises changes neither the combo answer nor the single answer", got == ref and s1 == s2, (got, ref, s1, s2))
    ok("B and the live hooks do record on the normal path", count("mom_shadow") >= 1)


def c_log():
    reset()
    clock(t0 := [9000.0])
    _, o1 = say(lambda: rec(0.61, 4.9))
    t0[0] += 30
    _, o2 = say(lambda: rec(0.44, 4.95))
    t0[0] += 30
    _, o3 = say(lambda: rec(0.43, 4.96))
    ok("C 'MOMENTUM would sell' appears on the fall", "MOMENTUM would sell " + T in o2 and "rule=protect" in o2 and "q 61%->44%" in o2 and "(today: hold, q<50%)" in o2, o2)
    ok("C and only once per episode", "MOMENTUM" not in o3 and "MOMENTUM" not in o1)
    ok("C NO SELL names what blocks it, and is not repeated inside 10 minutes", "NO SELL " + T + ": blocked by lock-in not armed (peak $4.90 < $" in o1 and "NO SELL" not in o2 + o3)
    t0[0] += 601
    _, o4 = say(lambda: rec(0.43, 4.96))
    ok("C NO SELL comes back after 10 minutes", "NO SELL " + T in o4, o4)
    _, o5 = say(lambda: rec(0.7, 6.0, t="KXMVE-OTHER", real=False))
    ok("C no real quote is a reason too", "blocked by no real quote" in o5, o5)


def d_switch_bounds():
    reset()
    clock(t0 := [10000000.0])
    E.CFG["mom_shadow"] = False
    try:
        ok("D the kill switch writes nothing", rec(0.5, 4.0) is False and count("mom_shadow") == 0)
    finally:
        E.CFG["mom_shadow"] = True
    ok("D it defaults ON and is a known setting", E.MOM["on"] is True and E.DEFAULTS.get("mom_shadow") is True)
    rec(0.6, 4.0); t0[0] += 10
    ok("D throttled: an unchanged verdict 10 s later writes nothing", rec(0.6, 4.0) is False)
    t0[0] += 121
    ok("D and again after 120 s", rec(0.6, 4.0) is True)
    old_cap = E.MOM["cap"]
    E.store_x("delete from mom_shadow")
    for i in range(30):
        E.store_x("insert into mom_shadow(ts, ticker) values(?,?)", (t0[0] - 100 + i, "x"))
    E.store_x("insert into mom_shadow(ts, ticker) values(?,?)", (1.0, "old"))
    E.MOM["cap"] = 10; E.MOM["prune"] = 0.0; t0[0] += 1000
    try:
        rec(0.6, 4.0, t="KXMVE-P"); E.mom_flush()
    finally:
        E.MOM["cap"] = old_cap
    E.mom_flush()
    ok("D old rows (past 60 days) and rows over the cap are pruned", not R("select 1 from mom_shadow where ticker='old'") and count("mom_shadow") <= 11, count("mom_shadow"))


def e_unread():
    src = open(os.path.join(REPO, "nfl_combo_planner.py")).read()
    a, b = src.index("# ---- momentum shadow (design"), src.index("\n\nSINGLE_RESTING = {")
    outside = src[:a] + src[b:]
    ok("E nothing outside the recorder mentions the tables", not re.search(r"mom_(shadow|after|peak)\b", outside.replace('"mom_shadow": True', '').replace('"mom_shadow"', '').replace("mom_settle", "")))
    ok("E inside it the tables are never selected from for a decision (only the peak, into the recorder's own dict)", not re.search(r"select[^\n\"']*from\s+mom_(shadow|after)\b", src[a:b].replace("select count(*) n from mom_shadow", "").replace("select ts from {tb} order by ts", ""), re.I))
    ok("E no order call in the recorder", not re.search(r"place_order|sell_order|cash_out|accept_offer|auto_sell|requests\.", src[a:b]))


def setup_trade(auto=True, paused=False, self_=False, cap=False):
    E.CFG.update(auto_sell=auto, smart_sell=True, ride=2, lock_trail=True)
    E.can_trade = lambda: True
    E.TRADING_PAUSED = (lambda: True) if paused else None
    E.hands_off = lambda t: self_
    E.auto_cap_reached = lambda: cap


def mk(p, offer=None):
    h = {"left": 1, "pays": 10.0, "p": p, "cost": 5.0, "legs_left": [(p, True, 0)], "need": [(("yes", "KXA-1"), "")], "hold": 3.0}
    E.MINE["hold"][T] = h; E.MINE.setdefault("peak", {}).pop(T, None)
    E.MINE["cash"].pop(T, None)
    if offer:
        E.MINE["cash"][T] = {"offer": offer, "frac": 1.0, "rfq": "real", "at": E.time.time()}
    return h


def f_card():
    clock([_real_time.time()])
    setup_trade()
    h = mk(0.38)
    before = dict(E.MINE["peak"])
    v = E.smart_trigger(T, h)
    ok("F low win chance: the text says it won't sell and the chip does not promise a sale", "won't sell while the win chance is 38%, under 50%" in v["smart_txt"] and v["smart_chip"] == "waiting, win chance 38% is below the 50% needed" and v["smart_state"] == "", v)
    ok("F it touches no peak", E.MINE["peak"] == before)
    h = mk(0.7)
    v = E.smart_trigger(T, h)
    ok("F no real offer: text and chip say a real Kalshi offer of the bar is needed", "ask Kalshi for a real offer once the estimate reaches $" in v["smart_txt"] and v["smart_chip"].startswith("will ask Kalshi") and v["smart_chip"].endswith(chr(36)+"%.2f" % v["smart_at"]), v)
    h = mk(0.7, offer=9.0)
    v = E.smart_trigger(T, h)
    ok("F offer at the bar and every gate open: it says it should sell next check", v["smart_state"] == "go" and "set up to sell once a real offer meets the bar" in v["smart_txt"], v)
    ok("F lock-in is said in plain words", "Lock in arms" not in v["smart_txt"] and (v["lock_at"] is None or isinstance(v["lock_at"], float)))
    h = mk(0.7, offer=1.0)
    v = E.smart_trigger(T, h)
    ok("F an offer under the bar is just reported", v["smart_state"] == "" and "it is $1.00 now" in v["smart_txt"] and v["smart_chip"].startswith("waiting, offer $1.00 is below the $"), v)
    for name, kw, word in (("Pause", {"paused": True}, "paused"), ("the daily limit", {"cap": True}, "daily limit used")):
        setup_trade(**kw); h = mk(0.7, offer=9.0)
        v = E.smart_trigger(T, h)
        ok(f"F {name}: at the bar it does NOT promise a sale", v["smart_state"] == "reached" and "should sell" not in v["smart_txt"] and word in v["smart_chip"] and "won't sell on its own right now" in v["smart_txt"], v)
    setup_trade(paused=True); h = mk(0.7, offer=1.0)
    v = E.smart_trigger(T, h)
    ok("F Pause with the offer under the bar: the chip does not say 'sells at'", "sells at" not in v["smart_chip"] and "paused" in v["smart_chip"], v)
    ok("F Pause: no Lock in promise, the pause reason is shown instead", v["lock_at"] is None and "Pause is on" in v["smart_txt"], v)
    setup_trade(); E._HEDGE_UNSURE_MEM[T] = 1
    try:
        v = E.smart_trigger(T, mk(0.7, offer=9.0))
    finally:
        E._HEDGE_UNSURE_MEM.pop(T, None)
    ok("F a hedge needing a look stops the 'set up to sell' promise", v["smart_state"] == "reached" and "hedge" in v["smart_txt"], v)
    setup_trade(auto=False); h = mk(0.7, offer=9.0)
    v = E.smart_trigger(T, h)
    ok("F Auto cash-out off: nothing is said about a bar that never fires", v["smart_txt"] == "" and v["smart_chip"] == "" and v["smart_state"] == "", v)
    setup_trade(self_=True); h = mk(0.7, offer=9.0)
    v = E.smart_trigger(T, h)
    ok("F set to I'll sell it: nothing is said either", v["smart_txt"] == "" and v["smart_state"] == "", v)
    setup_trade(); E.CFG["smart_sell"] = False; h = mk(0.7)
    v = E.smart_trigger(T, h)
    ok("F smart sell off but lock in / take profit on: it does not say nothing sells", "Smart sell is off." in v["smart_txt"] and "Lock in" in v["smart_txt"] and "Nothing else sells" not in v["smart_txt"], v)
    E.CFG.update(lock_trail=False, take_profit=0); h = mk(0.7)
    v = E.smart_trigger(T, h)
    ok("F and with those off too it says so", "Nothing else sells this combo" in v["smart_txt"], v)
    E.CFG.update(lock_trail=True, smart_sell=True)
    js = open(os.path.join(REPO, "watcher", "spa", "live.js")).read()
    ok("F the card calls the old number plain words (Sell at / sells once the offer reaches), not the let-it-ride line, and has plain lock-in words", "let-it-ride line" not in js.lower() and "<div>Sell at<b>" in js and "sells once the offer reaches" in js and "wait line" not in js.lower() and "Protects a profit once the offer has reached" in js and "Lock in arms once" not in js)
    ok("F the card hides the smart text when selling is off or yours, and the badge follows the bar", "smart_txt&&!c.self&&S.live.auto_sell!==false" in js and "SET TO SELL" in js and "Ready to sell" in js and "x.smart_chip" in js)
    setup_trade(); E.hands_off = lambda t: bool(t) and t in E.self_sell_set(); E.auto_cap_reached = E.auto_cap_reached


def g_offpath():
    reset(); clock([_real_time.time()])
    calls = []
    real_x, real_r = E.store_x, E.store_rows
    def slow_x(*a, **k):
        calls.append(("x", threading.current_thread().name)); _real_time.sleep(0.4); return real_x(*a, **k)
    def slow_r(*a, **k):
        calls.append(("r", threading.current_thread().name)); _real_time.sleep(0.4); return real_r(*a, **k)
    E.store_x, E.store_rows = slow_x, slow_r
    E.MOM["db"] = None; E.MOM["prune"] = 0.0
    try:
        t_start = _real_time.time()
        r = rec(0.44, 4.9, t="KXMVE-OFF")
        took = _real_time.time() - t_start
        me = threading.current_thread().name
        ok("G the write is queued, not done, on the selling thread: slow storage cannot stall it", r is True and took < 0.3 and not [c for c in calls if c[1] == me], (took, calls))
    finally:
        E.store_x, E.store_rows = real_x, real_r
    E.mom_flush()
    ok("G the background writer lands it (and made the tables)", E.store_rows("select count(*) n from mom_shadow where ticker='KXMVE-OFF'")[0]["n"] == 1)
    ok("G the queue is bounded", E.MOM["ops_cap"] <= 5000)
    src = open(os.path.join(REPO, "nfl_combo_planner.py")).read()
    a, b = src.index("\ndef mom_record("), src.index("\ndef _mom_after_fill(")
    ok("G mom_record itself never calls the database", not re.search(r"store_x\(|store_rows\(", src[a:b]))


def h_pend():
    reset(); clock(t0 := [2e6])
    for i in range(E.MOM["pend_cap"]):
        E.MOM["pend"].append({"sid": f"x{i}", "t": f"OLD{i}", "t0": t0[0] - 99999, "got": set(), "min": None})
    r = rec(0.44, 4.9, t="KXMVE-NEW", d={"sell": True, "reason": "smart", "threshold": 1.0, "floor": 1.0})
    ok("H expired follow-ups are dropped on the next record (no offer needed), so new ones are accepted", r and [p["t"] for p in E.MOM["pend"]] == ["KXMVE-NEW"], [p["t"] for p in E.MOM["pend"]][:3])
    E.MOM["pend"].clear()
    for i in range(E.MOM["pend_cap"] + 5):
        E.MOM["pend"].append({"sid": f"y{i}", "t": f"Z{i}", "t0": t0[0], "got": set(), "min": None})
    t0[0] += 5; rec(0.45, 4.95, t="KXMVE-NEW2", d={"sell": True, "reason": "smart", "threshold": 1.0, "floor": 1.0})
    ok("H at the cap the oldest make room: the list stays bounded and the newest is kept", len(E.MOM["pend"]) <= E.MOM["pend_cap"] and E.MOM["pend"][-1]["t"] == "KXMVE-NEW2", len(E.MOM["pend"]))
    rec(0.44, 4.9, t="KXMVE-S", d={"sell": True, "reason": "smart", "threshold": 1.0, "floor": 1.0}); E.mom_settle("KXMVE-S", "lost", 0)
    ok("H settling a bet drops its follow-ups", not [p for p in E.MOM["pend"] if p["t"] == "KXMVE-S"])
    idx = {r["name"] for r in R("select name from sqlite_master where type='index'")}
    ok("H mom_after has a ts index", "mom_after_ts" in idx, idx)
    E.store_x("delete from mom_after")
    for i in range(30):
        E.store_x("insert into mom_after(sid,ts,ticker) values(?,?,?)", (f"s{i}", t0[0] - 50 + i, "x"))
    old = E.MOM["cap"]; E.MOM["cap"] = 10; E.MOM["prune"] = 0.0; t0[0] += 1000
    try:
        rec(0.6, 4.0, t="KXMVE-CAP"); E.mom_flush()
    finally:
        E.MOM["cap"] = old
    ok("H mom_after is capped too, oldest first", count("mom_after") <= 10, count("mom_after"))


def i_proc_peak():
    reset(); clock(t0 := [3e6])
    rec(0.44, 4.9, d={"sell": True, "reason": "smart", "threshold": 1.0, "floor": 1.0})
    row = R("select proc, sid, ticker from mom_shadow")[0]
    af = R("select sid, proc from mom_after")[0]
    ok("I every row says which process wrote it, with a dedupe key the follow-up row shares", row["proc"] in ("web", "main") and row["sid"].startswith(row["proc"] + ":") and row["sid"].endswith(":" + T) and af["sid"] == row["sid"] and af["proc"] == row["proc"], (row, af))
    old_argv = E.sys.argv
    E.sys.argv = ["combo_watcher.py", "--webapp"]
    try:
        ok("I the web app tags its rows 'web'", E._mom_proc() == "web")
    finally:
        E.sys.argv = old_argv
    # a re-bought single must not inherit the old peak
    reset(); t0[0] += 10
    E.mom_record("single", "KXS-R", True, 0.8, 10, 4.0, 9.0, 9.0, True, 1.0, NO)
    ok("I the first position's peak is kept", E.MOM["peak"]["KXS-R"] == 9.0)
    t0[0] += 30
    E.mom_record("single", "KXS-R", True, 0.8, 10, 6.5, 2.0, 2.0, True, 1.0, NO)     # same ticker, bought again at another cost
    ok("I a new position under the same ticker starts a fresh peak", E.MOM["peak"]["KXS-R"] == 2.0, E.MOM["peak"].get("KXS-R"))
    ok("I and the saved peak of the old one is gone", (R("select o_peak from mom_peak where ticker='KXS-R'") or [{"o_peak": 2.0}])[0]["o_peak"] == 2.0)
    t0[0] += 7 * 3600
    E.mom_record("single", "KXS-R", True, 0.8, 10, 6.5, 1.0, 1.0, True, 1.0, NO)     # nothing seen for hours: also new
    ok("I a position not seen for hours starts fresh too", E.MOM["peak"]["KXS-R"] == 1.0, E.MOM["peak"].get("KXS-R"))
    E.mom_settle("KXS-R", "cashed", 1)
    ok("I settling forgets the peak", "KXS-R" not in E.MOM["peak"] and not R("select 1 from mom_peak where ticker='KXS-R'"))


def j_whynot():
    d = dict(NO, floor=4.2)
    s_, l_ = E.mom_why_not("combo", True, 0.7, 4.0, True, d, 4.0, 10.0, 5.0, o_gross=4.3, o_est=0.0)
    ok("J a combo's offer is judged gross (as the rule does), not after fees: gross 4.30 clears a 4.20 bar", s_ == "peak<arm", (s_, l_))
    s_, l_ = E.mom_why_not("combo", True, 0.7, 3.9, True, d, 4.0, 10.0, 5.0, o_gross=4.1, o_est=0.0)
    ok("J and a gross offer under the bar says so, with the gross number", s_ == "below floor" and "$4.10" in l_ and "$4.20" in l_, (s_, l_))
    s_, l_ = E.mom_why_not("combo", True, 0.55, 4.9, True, d, 4.9, 10.0, 5.0, o_gross=5.0, q_min=0.6)
    ok("J the tuned q_min is used, not the constant", s_ == "q<60%" and "60%" in l_, (s_, l_))
    s_, l_ = E.mom_why_not("combo", True, 0.55, 4.9, True, d, 4.9, 10.0, 5.0, o_gross=5.0)
    ok("J and the default bar is the constant when nothing is tuned", s_ == "peak<arm", (s_, l_))


def k_loss_chip():
    """Smart sell is one feature with two plain lines on the card: Take profit and Loss cut (display only, #loss-chip)."""
    clock([_real_time.time()])
    keep = (E.smart_params, E.stoploss_params, E.fresh_live_score, E.game_played)
    try:
        def cfg(loss, prog=0.5, played=None):
            E.smart_params = lambda tks: {"floor": 1.5, "lam": 1.0, "loss": loss, "key": None}
            E.stoploss_params = lambda tks: {"prog": prog, "drop": 0.2, "key": None}
            E.fresh_live_score = lambda *a, **k: ({"state": "in"}, "") if played is not None else (None, "no score feed")
            E.game_played = lambda sc: played
        setup_trade(); h = mk(0.11)
        cfg(None)
        v = E.smart_trigger(T, h)
        ok("K take profit says the live chance and the bar", v["smart_profit"] == "Take profit: waiting, win chance 11% is below the 50% needed", v)
        ok("K loss cut off: this league hasn't earned it", v["loss_chip"] == "Loss cut: off (this league hasn't earned it yet)", v)
        cfg(0.2, played=0.2)
        ok("K loss cut waits for half the game", E.smart_trigger(T, h)["loss_chip"] == "Loss cut: waiting for half the game", E.smart_trigger(T, h))
        cfg(0.2, played=0.7)
        ok("K loss cut armed at its win chance", E.smart_trigger(T, h)["loss_chip"] == "Loss cut: armed at 20% win chance")
        cfg(0.2, prog=0.6, played=0.3)
        ok("K a learned game share is named", E.smart_trigger(T, h)["loss_chip"] == "Loss cut: waiting for 60% of the game")
        cfg(0.2, played=0.7); setup_trade(paused=True)
        ok("K Pause is said on the loss line", "Pause is on" in E.smart_trigger(T, mk(0.11))["loss_chip"])
        setup_trade(auto=False)
        v = E.smart_trigger(T, mk(0.7, offer=9.0))
        ok("K Auto cash-out off: both lines say so, nothing else", "Auto cash-out is off" in v["loss_chip"] and v["smart_profit"].startswith("Take profit: off") and v["smart_txt"] == "", v)
        setup_trade(self_=True)
        ok("K I'll sell it: both lines say so", "you sell" in E.smart_trigger(T, mk(0.7))["loss_chip"])
        setup_trade(); E.CFG["smart_sell"] = False
        ok("K Smart sell off: the loss line says so", "Smart sell is off" in E.smart_trigger(T, mk(0.7))["loss_chip"])
        E.CFG["smart_sell"] = True
        setup_trade(); v = E.smart_trigger(T, mk(0.7, offer=1.0))
        ok("K the offer, not the chance, is what is short", v["smart_profit"].startswith("Take profit: waiting, offer $1.00 is below the $"), v)
        ok("K nothing else changed: no peak or sell state", v["smart_state"] == "")
        js = open(os.path.join(REPO, "watcher", "spa", "live.js")).read()
        ok("K the card shows both lines under one Smart sell block", "ssLines" in js and "x.smart_profit" in js and "x.loss_chip" in js and "ssChip(c)+ssLines(c)" in js)
    finally:
        E.smart_params, E.stoploss_params, E.fresh_live_score, E.game_played = keep


for n, f in (("a", a_rows), ("b", b_swallow), ("c", c_log), ("d", d_switch_bounds), ("e", e_unread), ("f", f_card), ("g", g_offpath), ("h", h_pend), ("i", i_proc_peak), ("j", j_whynot), ("k", k_loss_chip)):
    section(n, f)
