# CHECK: group=engine
# (#8) Buy-timing evidence: exact bucket boundaries, missing data, the flat timing_log rows (price at build / at buy / close,
# hours before start, full auto or not, fees, result), bounded storage, and that a failure in the recorder never raises
# (it runs from panel_settle, never on the buy path). Plus tools/timing_report.py: same buckets as the engine, exact sums,
# "too few" flags, missing numbers never counted as zero, read-only.
import os, time, json, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
REPO = os.environ.get("REPO") or os.path.abspath("../..")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
spec = importlib.util.spec_from_file_location("TR", os.path.join(REPO, "tools", "timing_report.py"))
TR = importlib.util.module_from_spec(spec); spec.loader.exec_module(TR)
DB = os.path.join(tempfile.mkdtemp(), "h.db")
E.store_open(DB); E.HERE = tempfile.mkdtemp()
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
H = 3600
K = 1_900_000_000.0

# 1. bucket boundaries, exact (a boundary belongs to the later bucket, like the scoreboard)
cases = [(0, "lt1h"), (1, "lt1h"), (H - 1, "lt1h"), (H, "1-6h"), (6 * H - 1, "1-6h"), (6 * H, "6-24h"),
         (24 * H - 1, "6-24h"), (24 * H, "24h+"), (5 * 24 * H, "24h+"), (-1, "live"), (-3 * H, "live")]
for secs, want in cases:
    got = E.timing_bucket(K, K - secs)
    ok(f"bucket {secs}s before -> {want}", got[0] == want and TR.bucket_of(K, K - secs) == want, got)
ok("hours value exact", E.timing_bucket(K, K - 5400) == ("1-6h", 1.5))
ok("live flag wins over a long lead", E.timing_bucket(K, K - 30 * H, True)[0] == "live" and TR.bucket_of(K, K - 30 * H, True) == "live")
for bad in ((None, K), (K, None), (0, K), (K, 0), ("x", K), (float("nan"), K), (K, float("inf")), (-5, K)):
    ok(f"missing/odd times {bad} -> (None, None)", E.timing_bucket(*bad) == (None, None) and TR.bucket_of(*bad) is None)

# 2. one row, pure
single = {"id": "s1", "kind": "single", "state": "bought", "league": "NBA", "kick": K, "bought_at": K - 2 * H, "stake": 5.0,
          "paid": 0.50, "legs": [{"ticker": "KXNBAGAME-A", "p": 0.52}], "clv": 0.1538, "result": "won", "pl": 4.2, "pl_real": 4.0}
r = E.timing_row("real", "2026-11-26", single, {"2026-11-26|s1"}, {"KXNBAGAME-A": 0.60}, 0.31, K)
ok("single row exact", r and r["key"] == "real|2026-11-26|s1" and r["bucket"] == "1-6h" and r["hours"] == 2.0 and r["auto"] == 1
   and r["p_build"] == 0.52 and r["p_buy"] == 0.5 and r["close"] == 0.6 and r["clv_buy"] == 0.2 and r["fees"] == 0.31
   and r["stake"] == 5.0 and r["pl"] == 4.2 and r["pl_real"] == 4.0 and r["league"] == "NBA" and r["mode"] == "real", r)
r = E.timing_row("real#2", "2026-11-26", single, set(), {}, None, K)
ok("not full auto, no close, no fees -> None, not zero", r["auto"] == 0 and r["close"] is None and r["clv_buy"] is None
   and r["fees"] is None and r["mode"] == "real")
r = E.timing_row("paper", "2026-11-26", dict(single, swap_of=None), {"2026-11-26|s1"}, {"KXNBAGAME-A": 0.6}, None, K)
ok("paper is never full auto", r["auto"] == 0)
r = E.timing_row("real", "2026-11-26", dict(single, id="s2", swap_of="s1"), {"2026-11-26|s1"}, {}, None, K)
ok("a swap of a full-auto bet is full auto", r["auto"] == 1)
combo = {"id": "c1", "kind": "combo", "state": "bought", "kick": K, "bought_at": K - 30 * H, "stake": 2.0, "pays": 20.0,
         "legs": [{"ticker": "T1", "p": 0.5}, {"ticker": "T2", "p": 0.4}]}
r = E.timing_row("real", "d", combo, set(), {"T1": 0.55, "T2": 0.4}, None, K)
ok("combo: price paid per $ of payout, product of legs", r["bucket"] == "24h+" and r["p_buy"] == 0.1 and abs(r["p_build"] - 0.2) < 1e-12
   and r["close"] == 0.22 and r["clv_buy"] == 1.2, r)
r = E.timing_row("real", "d", combo, set(), {"T1": 0.55}, None, K)
ok("a leg with no close: no close, no CLV", r["close"] is None and r["clv_buy"] is None)
r = E.timing_row("real", "d", dict(single, live=True, bought_at=K + 600), set(), {"KXNBAGAME-A": 0.6}, None, K)
ok("a live buy: bucket live, no close or CLV (the close came before it)", r["bucket"] == "live" and r["close"] is None and r["live"] == 1)
ok("an unbought item gives no row", E.timing_row("real", "d", dict(single, state="failed"), set(), {}, None, K) is None
   and E.timing_row("real", "d", {"state": "bought"}, set(), {}, None, K) is None and E.timing_row("real", "d", None, set(), {}, None, K) is None)
r = E.timing_row("real", "d", {"id": "x", "state": "bought", "kind": "single", "legs": []}, set(), {}, None, K)
ok("an item with nothing recorded still makes a row of Nones", r and r["bucket"] is None and r["p_buy"] is None and r["hours"] is None)

# 3. the pass writes, refreshes and stays idempotent
E._panel_table(); E._close_table()
day = E._panel_day()
now = time.time()
past = now - 5 * H
live_c = dict(single, kick=past, bought_at=past - 2 * H, legs=[{"ticker": "KXNBAGAME-A", "p": 0.52}], result=None, pl=None, pl_real=None, clv=None)
E.store_x("insert into panel values(?,?,?,?,?)", (day, "real", now, "approved", json.dumps({"at": now, "items": [live_c, dict(single, id="f", state="failed")]})))
E.store_x("insert into closes values(?,?,?,?,?,?,?,null)", ("KXNBAGAME-A", "nba", "e", 0.6, 0.58, past, now))
E.store_x("insert into close_mids values(?,?,?)", ("KXNBAGAME-A", 0.6, now))
n1 = E.timing_log_pass(now)
rows = E.store_rows("select * from timing_log")
ok("pass wrote exactly the one bought bet", n1 == 1 and len(rows) == 1 and rows[0]["close"] == 0.6 and rows[0]["clv_buy"] == 0.2
   and rows[0]["bucket"] == "1-6h" and rows[0]["result"] is None, rows)
ok("second pass with nothing new writes nothing", E.timing_log_pass(now + 60) == 0)
live_c.update(result="won", pl=4.2)
E.store_x("update panel set body=? where day=? and mode='real'", (json.dumps({"at": now, "items": [live_c]}), day))
ok("a new result is written onto the same row", E.timing_log_pass(now + 120) == 1 and E.store_rows("select count(*) n from timing_log")[0]["n"] == 1
   and E.store_rows("select result, pl from timing_log")[0] == {"result": "won", "pl": 4.2})
ok("first-seen time kept on refresh", E.store_rows("select ts, upd from timing_log")[0] == {"ts": now, "upd": now + 120})

# 3b. (#640 #649) later fees / pl / stake refresh a row; one ticker bought twice splits its fees; a buy after the start is live
E.store_x("delete from timing_log"); E.store_x("delete from panel")
E._ledger_table()
E.store_x("insert into ledger(ticker, fees, sell_fees) values('KXNBAGAME-A', 0.30, 0.10)")
a1 = dict(single, id="a1", kick=past, bought_at=past - 2 * H, stake=6.0, result=None, pl=None, pl_real=None, clv=None)
a2 = dict(a1, id="a2", stake=2.0)
E.store_x("insert into panel values(?,?,?,?,?)", (day, "real", now, "approved", json.dumps({"at": now, "items": [a1, a2]})))
E.timing_log_pass(now)
fe = {r["key"]: r["fees"] for r in E.store_rows("select key, fees from timing_log")}
ok("same ticker bought twice: fees split by stake, summing to the ledger once (0.30 + 0.10)",
   len(fe) == 2 and abs(fe[f"real|{day}|a1"] - 0.30) < 1e-9 and abs(fe[f"real|{day}|a2"] - 0.10) < 1e-9, fe)
E.store_x("update panel set body=? where day=? and mode='real'", (json.dumps({"at": now, "items": [a1]}), day))
E.store_x("update ledger set fees=0.50 where ticker='KXNBAGAME-A'")
ok("a fee that arrives later refreshes the row", E.timing_log_pass(now + 60) == 1
   and E.store_rows("select fees from timing_log where key=?", (f"real|{day}|a1",))[0]["fees"] == 0.6)
a1b = dict(a1, pl=1.5, stake=7.0)
E.store_x("update panel set body=? where day=? and mode='real'", (json.dumps({"at": now, "items": [a1b]}), day))
ok("a changed pl or stake alone refreshes the row", E.timing_log_pass(now + 120) == 1
   and E.store_rows("select pl, stake from timing_log where key=?", (f"real|{day}|a1",))[0] == {"pl": 1.5, "stake": 7.0}
   and E.timing_log_pass(now + 180) == 0)
r = E.timing_row("real", "d", dict(single, kick=K, bought_at=K + 600), set(), {"KXNBAGAME-A": 0.6}, None, K)
ok("bought after the start without the live flag: live, no close or CLV", r["live"] == 1 and r["bucket"] == "live"
   and r["close"] is None and r["clv_buy"] is None, r)

# 4. bounded storage
E.store_x("delete from timing_log"); E.store_x("delete from panel")   # (no bought bets left to write)
for i in range(5):
    E.store_x("insert into timing_log(key, ts) values(?,?)", (f"k{i}", now - i))
E.store_x("insert into timing_log(key, ts) values('old', ?)", (now - E.TIMING["keep"] - 1,))
E.TIMING["max_rows"] = 3; E.TIMING_RUN["trim"] = 0.0
E.timing_log_pass(now)   # nothing to write: the trim still runs, once an hour
ok("trim: old row gone and only the newest max_rows kept", sorted(r["key"] for r in E.store_rows("select key from timing_log")) == ["k0", "k1", "k2"])
E.TIMING["max_rows"] = 20000

# 5. a failure never raises (it runs after the buys, from panel_settle)
E.store_x("insert or replace into panel values(?,?,?,?,?)", (day, "real", now, "approved", json.dumps({"at": now, "items": [live_c]})))
E.TIMING_RUN["trim"] = 0.0
def boom(*a, **k):
    raise RuntimeError("boom")
saved = {k: getattr(E, k) for k in ("store_rows", "store_x", "close_prices", "timing_bucket", "timing_row", "fa_state")}
msgs = []
for name in ("store_rows", "store_x", "close_prices", "timing_bucket", "timing_row"):
    setattr(E, name, boom)
    try:
        got = E.timing_log_pass(now + 999, log=msgs.append)
        ok(f"{name} failing: pass returns 0, no raise", got == 0)
    except BaseException as err:
        ok(f"{name} failing: pass returns 0, no raise", False, err)
    for k, v in saved.items():
        setattr(E, k, v)
ok("the failure is logged, not hidden", any("boom" in m for m in msgs) and len(msgs) >= 3)
E.fa_state = boom
ok("an unreadable full-auto file does not stop the log", E.timing_log_pass(now + 2000) >= 0)
E.fa_state = saved["fa_state"]
try:
    E.timing_log_pass(now, log=boom)
    ok("a failing logger cannot raise either", True)
except BaseException as err:
    ok("a failing logger cannot raise either", False, err)
db0 = E.STORE["db"]; E.STORE["db"] = None
ok("no history file: 0, no raise", E.timing_log_pass(now) == 0)
E.STORE["db"] = db0
# panel_settle: a recorder that raised anyway would still be inside panel_settle's own path only after its work; prove it is
# the LAST thing it does and the settle result is unchanged
import inspect
src = inspect.getsource(E.panel_settle)
ok("recorded at the very end of panel_settle, after the settling", src.rstrip().endswith("timing_log_pass()                                      # (#8) record-only buy-timing rows; never raises, never buys\n    return []".rstrip()) or src.index("timing_log_pass") > src.index("_set_items"))
ok("the buy path never calls it", all("timing_log_pass" not in inspect.getsource(getattr(E, f)) for f in ("panel_exec", "full_auto_pass", "panel_pass") if hasattr(E, f)))

# 6. the report
rows = [dict(mode="real", day="d1", kick=K, bought_at=K - 2 * H, stake=10.0, result="won", pl=5.0, pl_real=4.0, clv=0.10, league="NBA"),
        dict(mode="real#1", day="d2", kick=K, bought_at=K - 2 * H, stake=10.0, result="lost", pl=-10.0, pl_real=None, clv=-0.05, league="NBA"),
        dict(mode="real", day="d2", kick=K, bought_at=K - 2 * H, stake=10.0, result=None, pl=None, clv=None, league="NBA"),
        dict(mode="real", day="d2", kick=None, bought_at=K, stake=5.0, result="won", pl=1.0, clv=None, league=None),
        dict(mode="paper", day="d2", kick=K, bought_at=K - 30 * H, stake=5.0, result="won", pl=2.0, clv=0.2, league="NHL")]
rep = TR.build(rows)
b = rep["modes"]["real"]["bucket"]
ok("report: real 1-6h exact sums (pl_real preferred, an open bet adds no dollars, no CLV is not zero)",
   b["1-6h"] == {"n": 3, "settled": 2, "staked": 20.0, "net": -6.0, "roi": -0.3, "clv": 0.025, "clv_n": 2, "auto": 0, "few": True}, b.get("1-6h"))
ok("report: missing kick time goes to Unknown, league None to other", b[None]["n"] == 1 and "other" in rep["modes"]["real"]["league"])
ok("report: paper kept apart", rep["modes"]["paper"]["bucket"]["24h+"]["net"] == 2.0 and rep["n"] == 5 and rep["days"] == 2)
many = [dict(mode="real", day=f"d{i}", kick=K, bought_at=K - 2 * H, stake=1.0, result="won", pl=0.5, league="NBA") for i in range(20)]
ok("report: exactly 20 settled is no longer flagged, 19 is", TR.build(many)["modes"]["real"]["bucket"]["1-6h"]["few"] is False
   and TR.build(many[:19])["modes"]["real"]["bucket"]["1-6h"]["few"] is True)
ok("report renders and flags", "TOO FEW" in TR.render(rep) and "Unknown timing" in TR.render(rep) and "ROI" in TR.render(rep))
ok("report: empty data is a clear message", "No bought bets" in TR.render(TR.build([])))
# read-only: the history file is untouched, and the fallback (panel table) works on it
E.store_x("pragma wal_checkpoint(truncate)")
import hashlib
h0 = hashlib.sha256(open(DB, "rb").read()).hexdigest()
raw = TR.from_db(DB)
ok("report reads the history file without changing it", hashlib.sha256(open(DB, "rb").read()).hexdigest() == h0 and len(raw) >= 1)
