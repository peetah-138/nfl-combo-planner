# CHECK: group=engine
# 'Never sell at a loss' (#228 PR5, release 134 review): a combo cash-out whose buyer backs out never retries below
# what you paid, and a single with an unknown cost (or a sale just under cost once the order's rounded fee is paid)
# is skipped. With any other choice the retry rule is exactly as before. No real orders: every trading call is faked.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)

# ---- combo: the buyer backs out, the fresh offer is within 3% of the agreed price but under cost
acc = []
E.accept_once = lambda o, t=None: (acc.append(o["offer"]), "executed" if len(acc) > 1 else "cancelled")[1]
E.get_cash_offer = lambda t, f: {"offer": 9.9, "frac": 1.0, "rfq": "r2", "quote": "q2", "contracts": 20, "at": time.time()}
E.resting_sells = lambda: {}
E.loading = lambda *a, **k: None
E.haptic = lambda *a, **k: None
def offer():
    E.MINE["cash"]["C1"] = {"offer": 10.1, "frac": 1.0, "rfq": "r1", "quote": "q1", "contracts": 20, "at": time.time()}
E.MINE["hold"]["C1"] = {"label": "Combo 1", "cost": 10.0, "pays": 20}
offer(); msg = E.accept_cash("C1", floor=10.0)
ok("Never: a fresh offer under what you paid is not taken (nothing sold)", acc == [10.1] and not msg.startswith("✅"))
acc.clear(); offer(); msg = E.accept_cash("C1")
ok("no floor (the other choices, your own tap): the 3% retry rule as before", acc == [10.1, 9.9] and msg.startswith("✅"))
acc.clear(); offer(); msg = E.accept_cash("C1", floor=9.5)
ok("Never: a fresh offer still above cost is taken", acc == [10.1, 9.9] and msg.startswith("✅"))
src = open(spec.origin).read()
ok("auto cash-out passes the floor only under Never",
   'accept_cash(t, floor=h["cost"] * o.get("frac", 1.0)) if mode == "never" else accept_cash(t)' in src)

# ---- singles under Never: unknown cost, and the order's rounded fee
sold, logs = [], []
E.sell_single_now = lambda t, side, n, bid: (sold.append(t), (n, None))[1]
E.log_decision = lambda rec: logs.append(rec)
E.resting_single_sells = lambda: {}
E.order_unsure = lambda t: False
E.auto_cap_reached = lambda: False
E.hands_off = lambda t: False
E.single_sell_reason = lambda x, bid, ask, cut_ok=False: ("smart", 1.0)
E.CFG.update(stop_loss_mode="never", smart_sell=True)
def run(cost, n=3, bid=0.5):
    sold.clear()
    E.SINGLES.update(at=time.time(), items=[{"t": "KXNBAGAME-26NOV19LALBOS-LAL", "side": "yes", "state": "live", "n": n,
                                             "cost": cost, "chance": 0.5, "label": "Lakers", "kind": "win"}],
                     mk={"KXNBAGAME-26NOV19LALBOS-LAL": {"yes_bid_dollars": str(bid), "yes_ask_dollars": str(bid + 0.02)}})
    E.smart_sell_singles()
    return bool(sold)
ok("Never: a single with an unknown cost is not sold", not run(None) and not run(0))
fee = E.single_fee(0.5, 3)
ok("Never: proceeds after the order's rounded fee just under cost: not sold", not run(round(3 * (0.5 - fee) + 0.001, 4)))
ok("Never: proceeds after the fee at or above cost: sold", run(round(3 * (0.5 - fee) - 0.01, 4)))
E.CFG.update(stop_loss_mode="allow")
ok("Allow: a sale just under cost isn't blocked by this check (as before)", run(round(3 * (0.5 - fee) + 0.001, 4)))
