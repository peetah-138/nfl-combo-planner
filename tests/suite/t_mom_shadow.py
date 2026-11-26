# CHECK: group=engine
# The momentum shadow recorder (mom_record in the engine): write-only, off the selling path.
#  A  rows land in mom_shadow / mom_after / mom_peak (synthetic DB: the dev Mac has no history, hard rule 9)
#  B  an error inside the recorder never reaches selling: take_profit_reason / single_sell_reason answer the same
#  C  the log lines: "MOMENTUM would sell" once per episode, "NO SELL ... blocked by ..." every 10 min per bet
#  D  the kill switch, the throttle, and pruning/caps
#  E  nothing reads the tables back into a decision; the card text says what smart sell really waits for
import os, re, io, tempfile, importlib.util, traceback, contextlib
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
    for k in ("q", "peak", "peak_saved", "seen", "told", "ep"):
        E.MOM[k].clear()
    E.MOM["pend"].clear(); E.MOM["labeled"].clear(); E.MOM["prune"] = 0.0
    for tb in ("mom_shadow", "mom_after", "mom_peak"):
        E.store_x(f"delete from {tb}")


def count(tb):
    return E.store_rows(f"select count(*) n from {tb}")[0]["n"]


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
    row = E.store_rows("select q, q_peak_w, dq, z, o_net, cost, real_flag, today_sell, today_reason, why_not, m_protect, m_cut, paused from mom_shadow order by ts desc limit 1")[0]
    ok("A the row carries q, its recent high, the drop, z, the net offer, cost, today's call and why not",
       row["q"] == 0.44 and row["q_peak_w"] == 0.61 and row["dq"] == -0.17 and row["z"] > 2 and row["o_net"] == 4.91 and row["cost"] == 5.0
       and row["real_flag"] == 1 and row["today_sell"] == 0 and row["today_reason"] == "hold" and row["why_not"] == "q<50%" and row["m_protect"] == 1 and row["paused"] == 0, row)
    ok("A a flagged row also opens a mom_after row", count("mom_after") == 1)
    ok("A the peak is persisted", E.store_rows("select o_peak from mom_peak where ticker=?", (T,))[0]["o_peak"] >= 4.9)
    for secs in (31, 40, 240, 700, 2800):
        t0[0] += secs
        rec(0.44, 4.5 + secs / 1000)
    after = E.store_rows("select o30, o60, o300, o900, o3600, o_min from mom_after")[0]
    ok("A mom_after fills the later offers as time passes (+30 s .. +60 min) and tracks the lowest", all(after[k] is not None for k in ("o30", "o60", "o300", "o900", "o3600")) and after["o_min"] <= 4.54, after)
    E.mom_settle(T, "lost", 0)
    ok("A the settlement label lands on the flagged rows", E.store_rows("select outcome, payout from mom_after")[0] == {"outcome": "lost", "payout": 0.0})
    # a restart forgets memory but not the peak
    E.MOM["peak"].clear(); E.MOM["peak_saved"].clear(); t0[0] += 5
    rec(0.44, 4.0)
    ok("A after a restart the saved peak is picked up again (shadow dict only)", E.MOM["peak"][T] >= 4.91 and T not in (E.MINE.get("peak") or {}))


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
        rec(0.6, 4.0, t="KXMVE-P")
    finally:
        E.MOM["cap"] = old_cap
    ok("D old rows (past 60 days) and rows over the cap are pruned", not E.store_rows("select 1 from mom_shadow where ticker='old'") and count("mom_shadow") <= 11, count("mom_shadow"))


def e_unread():
    src = open(os.path.join(REPO, "nfl_combo_planner.py")).read()
    a, b = src.index("# ---- momentum shadow (design"), src.index("\n\nSINGLE_RESTING = {")
    outside = src[:a] + src[b:]
    ok("E nothing outside the recorder mentions the tables", not re.search(r"mom_(shadow|after|peak)\b", outside.replace('"mom_shadow": True', '').replace('"mom_shadow"', '').replace("mom_settle", "")))
    ok("E inside it the tables are never selected from for a decision (only the peak, into the recorder's own dict)", not re.search(r"select[^\n\"']*from\s+mom_(shadow|after)\b", src[a:b].replace("select count(*) n from mom_shadow", "").replace("select rowid from mom_shadow", ""), re.I))
    ok("E no order call in the recorder", not re.search(r"place_order|sell_order|cash_out|accept_offer|auto_sell|requests\.", src[a:b]))
    h = {"left": 1, "pays": 10.0, "p": 0.38, "cost": 5.0, "legs_left": [(0.38, True, 0)], "need": [(("yes", "KXA-1"), "")], "hold": 3.0}
    E.MINE["hold"][T] = h; E.MINE["cash"].pop(T, None); E.MINE.setdefault("peak", {}).pop(T, None)
    E.CFG.update(smart_sell=True, ride=2, lock_trail=True)
    before = dict(E.MINE["peak"])
    v = E.smart_trigger(T, h)
    ok("E the card text names the real bar and why it is blocked, plain English", "won't sell while the win chance is 38%, under 50%" in v["smart_txt"] and (v["smart_at"] is None or "waits until the offer reaches $" in v["smart_txt"]), v)
    ok("E it touches no peak", E.MINE["peak"] == before)
    h["p"] = 0.7
    v = E.smart_trigger(T, h)
    ok("E with no real offer it says it needs one", "needs a real Kalshi offer" in v["smart_txt"], v)
    js = open(os.path.join(REPO, "watcher", "spa", "live.js")).read()
    ok("E the old let-it-ride number is labelled 'wait line' on the card", "wait line" in js and "Wait line" in js and "smart_txt" in js)


for n, f in (("a", a_rows), ("b", b_swallow), ("c", c_log), ("d", d_switch_bounds), ("e", e_unread)):
    section(n, f)
