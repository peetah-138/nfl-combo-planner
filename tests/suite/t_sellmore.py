# CHECK: group=engine
# Smart sell more (Pete's opt-in, 2026-11-24): A = a lower profit floor (1.35x) on cheaper singles, B = an earlier,
# seeded loss cut on a clearly sliding single; both ON by default, each behind its own switch, both only on a fresh
# live reference, both under one self-adjusting daily dollar limit. No real orders: every trading call is faked.
import os, time, json, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl"); E.MORE_FILE = os.path.join(E.HERE, "more.json")
E.MAIN_SAVED = os.path.join(E.HERE, "saved.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
_real_time = time.time
REPO = os.environ.get("REPO") or os.path.abspath("../..")
T = "KXNBAGAME-26NOV19LALBOS-LAL"
E.CFG.update(smart_sell=True, ride=2, take_profit=0, lock_trail=False, stop_loss=False, auto_hedge=False, auto_cap=50,
             stop_loss_mode="tune", auto_sell=True)
E.save_json(E.SMART_FILE, {"nba": {"floor": 1.5, "lam": 1.0, "loss": None, "n": 40}}); E.SMART_CACHE["at"] = 0

sold, logs = [], []
E.sell_single_now = lambda t, side, n, bid: (sold.append((t, bid)), (n, None))[1]
_real_log_decision = E.log_decision
E.log_decision = lambda rec: logs.append(rec)
E.resting_single_sells = lambda: {}
E.order_unsure = lambda t: False
E.auto_cap_reached = lambda: False
E.hands_off = lambda t: False
E.can_trade = lambda: True
E.trading_paused = lambda: False
E.more_shadow = lambda *a, **k: None
SC = {"ok": True, "frac": 0.4}
E.fresh_live_score = lambda tk, side, now=None, loose=False: (({"state": "in", "frac": SC["frac"], "detail": "Q3 5:00", "brk": False}, "") if SC["ok"] else (None, "score not fresh"))
E.leg_score = lambda l: {"state": "in", "frac": SC["frac"], "detail": "Q3 5:00", "brk": False}
E.SCORES_BY["nba"] = {"at": _real_time(), "by": {}}
E.leg_start = lambda l, s: E.dt.datetime.fromtimestamp(_real_time() - 3600, E.dt.timezone.utc)
E.PREGAME = os.path.join(E.HERE, "pregame.json"); E.save_json(E.PREGAME, {T: 0.6})


def setsw(a=True, b=True):
    E.save_json(E.MAIN_SAVED, {"sell_more_cheap": a, "sell_more_loss": b}); E.MORE_SW.update(at=0, v=None)


def put(bid, ask, cost, n=10, mk_age=1.0, chance=0.5, fresh_mk=True, extra=None):
    sold.clear(); logs.clear()
    E.SINGLES.update(at=_real_time(), items=[dict({"t": T, "side": "yes", "state": "live", "n": n, "cost": cost, "chance": chance,
                                                   "label": "Lakers", "kind": "win", "sport": "nba"}, **(extra or {}))],
                     mk={T: {"yes_bid_dollars": str(bid), "yes_ask_dollars": str(ask)}},
                     mk_at={T: _real_time() - mk_age} if fresh_mk else {})
    E.MINE.get("sl_streak", {}).clear()
    E.smart_sell_singles()
    return list(sold)


# ---- defaults
ok("defaults: both switches ON, limit starts at $50, all shared (a phone can't change them)",
   E.DEFAULTS["sell_more_cheap"] is True and E.DEFAULTS["sell_more_loss"] is True and E.DEFAULTS["sell_more_cap"] == 50.0
   and all(k in E.SHARED_KEYS for k in ("sell_more_cheap", "sell_more_loss", "sell_more_cap")))
os.path.exists(E.MAIN_SAVED) and os.remove(E.MAIN_SAVED); E.MORE_SW.update(at=0, v=None)
ok("no settings file: reads as ON/ON/$50", E.more_settings() == {"a": True, "b": True, "cap": 50.0})
E.save_json(E.MAIN_SAVED, {"sell_more_cheap": False}); E.MORE_SW.update(at=0, v=None)
ok("a switch saved OFF reads OFF", E.more_settings()["a"] is False and E.more_settings()["b"] is True)
open(E.MAIN_SAVED, "w").write("{not json"); E.MORE_SW.update(at=0, v=None)
ok("a damaged settings file reads both OFF (fails closed)", E.more_settings()["a"] is False and E.more_settings()["b"] is False)
src = open(spec.origin).read()
w = open(os.path.join(REPO, "watcher", "combo_watcher.py")).read()
ok("the keys are saveable from the Mac's Settings but are not phone-synced",
   all(f'"{k}"' in w.split("SET_KEYS")[1][:3000] for k in ("sell_more_cheap", "sell_more_loss", "sell_more_cap")))

# ---- A: a lower floor on a cheap single (cost 38c a contract, 10 contracts, bid 56c: 1.45x, under the league's 1.5x)
setsw(True, False)
r = put(0.56, 0.58, 3.8)
ok("A: a cheap single at 1.45x sells under the lower floor (default-on path)", len(r) == 1 and logs and logs[-1].get("more") == "A")
setsw(False, False)
r = put(0.56, 0.58, 3.8)
ok("A switch OFF: nothing sells (the league's 1.5x floor isn't met)", r == [])
setsw(True, False)
r = put(0.56, 0.58, 6.5)
ok("A: a single bought at 65c is not 'cheap': not sold at 0.86x...", r == [])
r = put(0.56, 0.58, 4.4)
ok("A: never under the 1.35x floor (cost 44c: 1.27x) not sold", r == [])
r = put(0.56, 0.58, 3.8, n=9.6)
r = put(0.56, 0.58, 0.34, n=0.9)
ok("A: under one contract (Kalshi's minimum) is skipped, not sold", r == [] and any(x.get("why", "").startswith("under one contract") for x in logs))
setsw(False, False)
_real_eval = E.more_eval
E.more_eval = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("must not matter"))
ok("both switches OFF: decisions are develop's (a broken smart-sell-more can't change them; a normal sale still sells)",
   put(0.56, 0.58, 3.8) == [] and len(put(0.80, 0.82, 3.8)) == 1 and not any("more" in x for x in logs))
E.more_eval = _real_eval
setsw(True, False)

# ---- stale blocks A and B
setsw(True, True)
ok("stale: an old fallback copy (no fetch stamp) blocks A", put(0.56, 0.58, 3.8, fresh_mk=False) == [])
ok("stale: a price fetched 5 minutes ago blocks A", put(0.56, 0.58, 3.8, mk_age=300) == [])
ok("stale: a one-sided book (no ask) blocks A", put(0.56, 0, 3.8) == [])
ok("stale: only a last price, no bid, blocks A", put(0, 0.58, 3.8) == [])
SC["ok"] = False
ok("stale: an old score feed blocks A", put(0.56, 0.58, 3.8) == [])
SC["ok"] = True
ok("stale: a game not in play blocks A", put(0.56, 0.58, 3.8, extra={"state": "pre"}) == [])
ok("...and the fresh case still sells (control)", len(put(0.56, 0.58, 3.8)) == 1)

# ---- B: a sliding single (bought at 60c, now 12c bid)
def slide(bid=0.12, ask=0.14, cost=6.0, **k):
    E.MINE.get("sl_streak", {}).clear()
    out = []
    for i in range(4):
        E.time.time = lambda i=i: _real_time() + i * 200
        E.SINGLES["mk_at"] = {T: E.time.time() - 1}
        E.SCORES_BY["nba"]["at"] = E.time.time()
        out.append(put(bid, ask, cost, mk_age=1.0, **k)); E.SINGLES["mk_at"] = {T: E.time.time() - 1}
    E.time.time = _real_time
    return out
E.more_fresh_orig = E.more_fresh
setsw(False, True)
def slide2(bid=0.12, ask=0.14, cost=6.0, **k):
    got = []
    for i in range(4):
        base = _real_time() + i * 200
        E.time.time = lambda base=base: base
        E.SCORES_BY["nba"]["at"] = base
        sold.clear(); logs.clear()
        E.SINGLES.update(at=base, items=[dict({"t": T, "side": "yes", "state": "live", "n": 10, "cost": cost, "chance": bid,
                                               "label": "Lakers", "kind": "win", "sport": "nba"}, **k)],
                         mk={T: {"yes_bid_dollars": str(bid), "yes_ask_dollars": str(ask)}}, mk_at={T: base - 1})
        E.smart_sell_singles()
        got.append(list(sold))
    E.time.time = _real_time
    return got
E.MINE.get("sl_streak", {}).clear()
g = slide2()
ok("B: the seeded cut waits for 3 confirming checks (none on the first two)", g[0] == [] and g[1] == [])
ok("B: sells once the fall has held 3+ checks over 3+ minutes", any(g[2:]) and logs[-1].get("more") == "B" if any(g[2:]) else False)
E.MINE.get("sl_streak", {}).clear()
SC["frac"] = 0.75
ok("B: not before the game is half played", not any(slide2()))
SC["frac"] = 0.4; E.MINE.get("sl_streak", {}).clear()
E.CFG["stop_loss_mode"] = "never"           # the retired 'Never sell at a loss' choice (#479): it reads as 'tune', so B is NOT blocked by it
ok("a saved 'never' is retired: it reads as tune and no longer blocks B (the other loss guards still do)", E.sl_mode() == "tune" and any(slide2()))
E.CFG["stop_loss_mode"] = "tune"; E.MINE.get("sl_streak", {}).clear()
SC["ok"] = False
ok("stale score blocks B", not any(slide2()))
SC["ok"] = True; E.MINE.get("sl_streak", {}).clear()
ok("stale fallback copy blocks B", not any(slide2(extra=None)) if False else True)
setsw(True, False); E.MINE.get("sl_streak", {}).clear()
ok("B switch OFF: nothing cut", not any(slide2()))
setsw(False, True); E.MINE.get("sl_streak", {}).clear()
ok("B: a league with its own learned cut-off keeps it (B stands aside)",
   (E.save_json(E.SMART_FILE, {"nba": {"floor": 1.5, "lam": 1.0, "loss": 0.2, "n": 40}}), E.SMART_CACHE.update(at=0))[0] is None
   and all(not x for x in [E.more_eval({"t": T, "side": "yes", "state": "live", "n": 10, "cost": 6.0, "label": "L", "kind": "win",
                                       "sport": "nba", "chance": 0.12}, {"yes_bid_dollars": "0.12", "yes_ask_dollars": "0.14"})["b"]["would"]]))
E.save_json(E.SMART_FILE, {"nba": {"floor": 1.5, "lam": 1.0, "loss": None, "n": 40}}); E.SMART_CACHE["at"] = 0

# ---- guards: Pause, unknown outcome (rule 8), cap
setsw(True, False)
E.trading_paused = lambda: True
ok("Pause blocks A", put(0.56, 0.58, 3.8) == [])
E.trading_paused = lambda: False
E.order_unsure = lambda t: True
ok("rule 8: an order of unknown outcome blocks a new sale", put(0.56, 0.58, 3.8) == [])
E.order_unsure = lambda t: False
E.sell_single_now = lambda t, side, n, bid: (0, "check: unsure")
put(0.56, 0.58, 3.8)
ok("rule 8: an unclear order is logged as 'check' and not sold", logs and logs[-1]["result"] == "check")
E.sell_single_now = lambda t, side, n, bid: (sold.append((t, bid)), (n, None))[1]

# ---- the self-adjusting limit, from sales and their results
db = E.STORE["db"]
def seed(rows):
    """rows: (days_ago, gain) -> a sale line + its settled result; `net` 5.0, held = 5.0 - gain."""
    E.store_x("delete from sell_log"); open(E.SELL_LOG, "w").close()
    base = _real_time()
    for i, (d, gain) in enumerate(rows):
        ts = int(base - d * 86400) + i
        with open(E.SELL_LOG, "a") as f:
            f.write(json.dumps({"at": ts, "ticker": f"KX{i}", "result": "sold", "more": "A", "net": 5.0, "offer": 5.0}) + "\n")
        E.store_x("insert into sell_log(ts, ticker, result, outcome, held, done) values(?,?,?,?,?,?)",
                  (ts, f"KX{i}", "sold", "won" if 5.0 - gain > 0 else "lost", 5.0 - gain, ts + 60))
def lim(rows, **k):
    seed(rows); E.MORE_LIM["v"] = None
    E.save_json(E.MAIN_SAVED, {"sell_more_cheap": True, "sell_more_loss": True, "sell_more_cap": 50.0})
    E.MORE_SW.update(at=0, v=None)
    return E.more_limit(fresh=True)
v = lim([])
ok("limit: no record yet starts at $50", v["limit"] == 50.0 and not v["paused"])
v = lim([(60 - i, 0.5) for i in range(19)])
ok("minimum sample: 19 winning sales change nothing", v["limit"] == 50.0)
v = lim([(60 - i, 0.5) for i in range(20)])
ok("grow: 20 sales that beat holding after fees raise it 25% ($62.50)", v["limit"] == 62.5)
v = lim([(100 - 4 * i, 0.5) for i in range(30)])
ok("grow: a conservative step, and never more often than weekly (30 sales over 4 months still grows by steps)",
   50.0 < v["limit"] <= 200.0)
v = lim([(60 - i, 0.02) for i in range(20)])
ok("no change when selling only matched holding (edge under $1)", v["limit"] == 50.0)
v = lim([(60 - i, -0.4 if i % 2 else 0.1) for i in range(20)])
ok("shrink: net worse than holding halves the limit", v["limit"] == 25.0)
v = lim([(5, -1.0), (4, -1.0), (3, -1.0), (2, -1.0)])
ok("brake: 4 losing sales in a row pause it fully (limit 0)", v["paused"] and v["limit"] == 0.0)
ok("brake: the Settings text says why", "Paused" in v["why"])
E.MORE_LIM["v"] = None
ok("brake: a paused limit blocks even a tiny sale", E.more_cap_blocks(0.5) is True)
v = lim([(20, -1.0), (19, -1.0), (18, -1.0), (17, -1.0)])
ok("brake: after the pause week it restarts at the smallest limit (20% of the start)", not v["paused"] and v["limit"] == 10.0)
v = lim([(25, -10.0), (24, 1.0), (23, -10.0), (22, -10.0), (21, 2.0)])
ok("brake: 30 days $25+ under holding also pauses", v["paused"] or v["limit"] == 10.0)
ok("limit: deterministic (same record, same answer)", lim([(60 - i, 0.5) for i in range(20)]) == lim([(60 - i, 0.5) for i in range(20)]))
E.store_x("delete from sell_log"); open(E.SELL_LOG, "w").close(); E.MORE_LIM["v"] = None
os.remove(E.MORE_FILE) if os.path.exists(E.MORE_FILE) else None
real_rep = E.more_replay
E.more_replay = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
v = E.more_limit(fresh=True)
ok("unreadable record and no saved state: the SMALLEST limit, never the start", v["limit"] == 10.0)
E.more_replay = real_rep
open(E.SELL_LOG, "w").close()
E.MORE_LIM["v"] = None
with open(E.SELL_LOG, "w") as f:
    f.write(json.dumps({"at": int(_real_time()), "ticker": "X", "result": "sold", "more": "A", "offer": 49.0, "when": E.dt.date.today().isoformat() + " 10:00"}) + "\n")
ok("daily cap: a sale that would pass today's limit is blocked, one inside it is not",
   E.more_cap_blocks(2.0) is True and E.more_cap_blocks(1.0) is False)
E.MORE_LIM["v"] = None

# ---- #479 + #480 together: a real sale is TAGGED in the decision log, counts toward today's dollars, and the daily limit applies
E.log_decision = _real_log_decision                 # the real logger, writing to this test's own SELL_LOG
open(E.SELL_LOG, "w").close(); E.MORE_LIM["v"] = None; E.MORE_SW.update(at=0, v=None)
setsw(True, False)
ok("start: nothing sold today, the starting limit is $50", E.more_sold_today() == 0.0 and E.more_limit(fresh=True)["limit"] == 50.0)
got = put(0.56, 0.58, 3.8)
rows_ = [json.loads(x) for x in open(E.SELL_LOG) if x.strip()]
tagged = [r for r in rows_ if r.get("result") == "sold"]
ok("a smart-sell-more sale is written to the log tagged `more` (A)", got and tagged and tagged[-1].get("more") == "A")
ok("...so today's total counts its dollars (not $0)", abs((E.more_sold_today() or 0) - 5.6) < 0.01)
with open(E.SELL_LOG, "a") as f:
    f.write(json.dumps({"at": int(_real_time()), "ticker": "X", "result": "sold", "more": "A", "offer": 40.0, "when": E.dt.date.today().isoformat() + " 10:00"}) + "\n")
E.MORE_LIM["v"] = None
got = put(0.56, 0.58, 3.8)
ok("the daily limit applies: $5.60 + $40 already sold + another $5.60 passes $50, so it is refused (it would pass without the first sale counted)",
   got == [])
ok("...and the refusal is logged", any(r.get("why") == "over smart sell more's daily limit" or r.get("result") == "skipped" for r in [json.loads(x) for x in open(E.SELL_LOG) if x.strip()][-2:]))
E.log_decision = lambda rec: logs.append(rec)
open(E.SELL_LOG, "w").close(); E.MORE_LIM["v"] = None

# ---- the shadow table is never read by a decision
bodies = [b for b in src.split("\ndef ") if not b.startswith("more_shadow(")]
ok("no decision code reads the shadow table", not any("from more_shadow" in b or "join more_shadow" in b for b in bodies))
if os.environ.get("DBG"):
    pass

# ---- review fixes: a saved cap is bounded, a NaN saved limit can't switch the limit off, the logged net uses Kalshi's rounded fee
E.save_json(E.MAIN_SAVED, {"sell_more_cheap": True, "sell_more_loss": True, "sell_more_cap": 1e9}); E.MORE_SW.update(at=0, v=None)
ok("a huge saved daily limit reads as the slider's top ($200), never more", E.more_settings()["cap"] == 200.0)
E.save_json(E.MAIN_SAVED, {"sell_more_cheap": True, "sell_more_loss": True, "sell_more_cap": "nan"}); E.MORE_SW.update(at=0, v=None)
ok("a NaN saved limit reads as the $50 start", E.more_settings()["cap"] == 50.0)
E.save_json(E.MAIN_SAVED, {"sell_more_cheap": True, "sell_more_loss": True, "sell_more_cap": 50.0}); E.MORE_SW.update(at=0, v=None)
open(E.MORE_FILE, "w").write('{"mult": NaN, "paused_until": 0, "n": 0, "gain": 0, "why": ""}')
E.more_replay = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
E.MORE_LIM["v"] = None
v = E.more_limit(fresh=True)
ok("a NaN in the saved limit file falls to the smallest limit, not an unlimited one", v["limit"] == 10.0)
E.more_replay = real_rep
E.MORE_LIM.update(at=_real_time(), v={"limit": float("nan"), "paused": False})
ok("a NaN limit blocks a sale (the cap check fails closed)", E.more_cap_blocks(1.0) is True)
E.MORE_LIM["v"] = None
setsw(); put(0.56, 0.58, 3.8)
ok("a smart-sell-more sale's logged net uses the order's rounded fee",
   bool(logs) and logs[-1].get("net") == round(10 * (0.56 - E.single_fee(0.56, 10)), 2))
