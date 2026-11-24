# CHECK: group=engine
# Every sale's success message states the result against what was paid (Pete, 2026-11-23): a combo cash-out (your tap
# and each automatic reason: Took the profit, Take profit, Locked in, Checkpoint, Cut a loss, Stop-loss), an automatic
# single sale (Take profit, Locked in, Smart sell, Cut a loss) and your own single Sell. Unknown cost keeps the old words
# with "(cost unknown)". Wording only: the sale, its price and the logged decision are unchanged. All Kalshi calls are
# faked; nothing is sent.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl"); E.HEDGES = os.path.join(E.HERE, "hedges.json")
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
now = time.time()
T = "KXNBAGAME-26NOV19LALBOS-LAL"
E.CFG.update(auto_sell=True, auto_hedge=False, stop_loss=False, smart_sell=True, ride=2, take_profit=0, lock_trail=False, auto_cap=9)
E.can_trade = lambda: True
E.haptic = E.loading = lambda *a: None
E.resting_sells = lambda: {}
E.drop_cash = lambda t: E.MINE["cash"].pop(t, None)
E._cash_pause = lambda s: None
E.accept_once = lambda o, t=None: "executed"
REAL_SINGLES = E.smart_sell_singles
E.smart_sell_singles = lambda: []        # the combo pass below must not run the singles pass
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], None)
E.leg_score = lambda l: {"state": "in", "me": 21, "opp": 17, "brk": False}
HOLD = {"label": "Combo 5", "need": [(("yes", T), "Lakers")], "pre_of": {T: 0.6}, "ch_of": {T: 0.7},
        "legs_left": [(0.7, True, 0)], "cost": 2.19, "p": 0.7, "pays": 20, "won_some": True, "left": 1}

# ---- combo, your own tap (accept_cash): profit, loss, half, unknown cost
def tap(offer, cost, frac=1.0):
    E.MINE["hold"] = {"C1": dict(HOLD, cost=cost)}
    E.MINE["cash"] = {"C1": {"offer": offer, "frac": frac, "rfq": "x", "quote": "q", "contracts": 20, "at": E.time.time()}}
    E.MINE["selling"] = set()
    return E.accept_cash("C1")
m = tap(3.61, 2.19)
ok("combo tap, profit: keeps the proceeds and adds the profit and cost", m == "✅ Combo 5 cashed out for about $3.61: +$1.42 profit (paid $2.19).", m)
m = tap(3.60, 4.40)
ok("combo tap, loss: says loss, no 'cut' words on your own tap", m == "✅ Combo 5 cashed out for about $3.60: -$0.80 loss (paid $4.40).", m)
m = tap(2.00, 4.40, frac=0.5)
ok("half a combo: judged against half the cost", m == "✅ Half of Combo 5 cashed out for about $2: -$0.20 loss (paid $2.20).", m)
m = tap(3.61, 0)
ok("cost unknown: old wording plus '(cost unknown)', no number made up", m == "✅ Combo 5 cashed out for about $3.61 (cost unknown).", m)
E.MINE["hold"] = {}
E.MINE["cash"] = {"C1": {"offer": 3.61, "frac": 1.0, "rfq": "x", "quote": "q", "contracts": 20, "at": E.time.time()}}
m = E.accept_cash("C1")
ok("no hold record at all: '(cost unknown)', still a sale", m.startswith("✅") and m.endswith("(cost unknown)."), m)
ok("the message still starts with the check mark the callers test for", tap(3.61, 2.19).startswith("✅"))

# ---- combo, automatic: every lead keeps its reason and gains the result
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 12.0)
E.get_cash_offer = lambda t, f=1.0: {"offer": 13.0, "frac": 1.0, "rfq": "x", "quote": "q", "contracts": 20, "at": E.time.time()}
plan = {"acts": {}}
def auto(cost, why="smart", offer=13.0, **cfg):
    E.CFG.update(cfg)
    E.take_profit_reason = lambda t, h, cut_ok=False: (why, 12.0)
    E.get_cash_offer = lambda t, f=1.0: {"offer": offer, "frac": 1.0, "rfq": "x", "quote": "q", "contracts": 20, "at": E.time.time()}
    E.MINE["hold"] = {"C1": dict(HOLD, cost=cost)}
    E.MINE["tp_asked"] = {}; E.MINE["cash"] = {"C1": dict(E.get_cash_offer("C1"))}; E.MINE["busy"] = False; E.MINE["selling"] = set()
    E.COMBO_WAIT.clear()
    return E.auto_sell_now(plan)
out = auto(8.0)
ok("auto 'Took the profit': reason kept, proceeds kept, +profit and cost added",
   len(out) == 1 and out[0].startswith("🤖 Took the profit: locking it in now beats the risk of holding. ✅ Combo 5 cashed out for about $13: ")
   and out[0].endswith("+$5 profit (paid $8)."), out)
out = auto(8.0, why="take profit", take_profit=50)
ok("auto 'Take profit' carries the profit", len(out) == 1 and out[0].startswith("🤖 Take profit:") and "+$5 profit (paid $8)" in out[0], out)
out = auto(8.0, why="lock in")
ok("auto 'Locked in' carries the profit", len(out) == 1 and out[0].startswith("🤖 Locked in a profit:") and "+$5 profit (paid $8)" in out[0], out)
out = auto(8.0, why="checkpoint")
ok("auto 'Checkpoint' carries the profit", len(out) == 1 and out[0].startswith("🤖 Checkpoint:") and "+$5 profit (paid $8)" in out[0], out)
out = auto(15.0, why="cut loss", offer=13.0, stop_loss=True)
ok("auto 'Cut a loss': -$ loss, paid, and 'cut to limit the damage'",
   len(out) == 1 and out[0].startswith("🤖 Cut a loss:") and "-$2 loss (paid $15), cut to limit the damage." in out[0], out)
out = auto(0, why="smart")
ok("auto sale with unknown cost: '(cost unknown)', old wording, still reported as a sale",
   len(out) == 1 and "cashed out for about $13 (cost unknown)." in out[0] and out[0].startswith("🤖 Took the profit"), out)

# ---- single, automatic (smart_sell_singles)
X = {"t": T, "label": "Lakers to win", "side": "yes", "n": 10.0, "cost": 5.0, "chance": 0.7, "kind": "win", "state": "live"}
LOGS = []
E.log_decision = lambda rec: LOGS.append(rec)
def single(why, cost=5.0, bid=0.60, sold=10.0):
    LOGS.clear()
    x = dict(X, cost=cost)
    E.SINGLES = {"at": time.time(), "items": [x], "mk": {T: {"yes_bid_dollars": f"{bid:.2f}", "yes_ask_dollars": f"{bid + 0.02:.2f}"}}}
    E.sell_held = lambda out: False
    E.hands_off = lambda t: False
    E.single_sell_reason = lambda x, bid, ask, cut_ok=False: (why, 0.5)
    E.resting_single_sells = lambda: set()
    E.order_unsure = lambda t: False
    E.sell_single_now = lambda t, side, n, bid, coid=None: (sold, None)
    E.auto_cap_reached = lambda: False
    E.sell_backoff_left = lambda *a: 0
    out = REAL_SINGLES()
    return out
fee = E.single_fee(0.60)
got = 10.0 * (0.60 - fee)
out = single("take profit")
want = f"+{E.money(round(got - 5.0, 2))} profit (paid $5)"
ok("single 'Take profit': proceeds kept, profit and cost added", len(out) == 1 and out[0] == f"🤖 Take profit: sold Lakers to win for about {E.money(got)}: {want}.", out)
for why, lead in (("lock in", "🤖 Locked in a profit"), ("smart", "🤖 Smart sell")):
    out = single(why)
    ok(f"single '{lead}' carries the profit", len(out) == 1 and out[0].startswith(lead) and "profit (paid $5)." in out[0], out)
out = single("cut loss", cost=9.0)
ok("single 'Cut a loss': loss, paid, and 'cut to limit the damage'", len(out) == 1 and "loss (paid $9), cut to limit the damage." in out[0], out)
out = single("take profit", sold=5.0)
ok("a part-filled single: judged against the share sold (half the cost)", len(out) == 1 and "(paid $2.50)" in out[0], out)
out = single("take profit", cost=0)
ok("single with unknown cost: '(cost unknown)' and no '(paid $0)'", len(out) == 1 and out[0].endswith(" (cost unknown).") and "paid $0" not in out[0], out)

# ---- single, your own Sell (single_sell)
E.hub_conf = lambda: None
q = {"sell": True, "t": T, "side": "yes", "bid": 0.60, "px": 0.60, "n": 10.0, "got": 5.7, "cost": 5.0, "at": time.time(), "thin": False,
     "blocked": None, "used": False, "pick": "Lakers to win", "kind": "win"}
E.sell_single_now = lambda t, side, n, bid, coid=None: (n, None)
def manual(cost):
    E._SQ["q"]["q1"] = dict(q, cost=cost)
    E.book_depth = lambda t, max_age=0: {"bid": 0.60, "ask": 0.62, "spread": .02, "ask_size": 500, "bid_size": 500, "thin": False}
    E.order_unsure = lambda t: False
    return E.single_sell("q1", T, log=lambda *a: None)
r = manual(5.0)
ok("your single Sell: profit after the fee appended to the old sentence", r["ok"] and r["msg"].startswith("✅ Sold 10 at 60¢ or better: about")
   and "back after Kalshi's fee: +" in r["msg"] and r["msg"].endswith("profit (paid $5)."), r.get("msg"))
r = manual(9.0)
ok("your single Sell at a loss says loss", r["ok"] and "loss (paid $9)." in r["msg"] and "cut" not in r["msg"], r.get("msg"))
r = manual(0)
ok("your single Sell, cost unknown: old words plus '(cost unknown)'", r["ok"] and r["msg"].endswith("back after Kalshi's fee (cost unknown)."), r.get("msg"))
