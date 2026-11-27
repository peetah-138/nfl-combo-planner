# CHECK: group=engine
# money-i-144: #551b (the card's Lock-in line uses the tuned arm numbers the sale uses), #300 (the brake's footing for a
# combo sale counts the discount logged AT the sale, never lower than today's), #302 (an auto_sell_now-level test: a
# learned 0.99 slip and an offer at 0.98 x the line is skipped, 0.995 x sells). No real orders: every Kalshi call is faked.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl"); E.HEDGES = os.path.join(E.HERE, "hedges.json")
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json"); E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.KNOBS_FILE = os.path.join(E.HERE, "knobs.json")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
now = time.time()

# ---- #300: the brake's footing. A combo sold in play; today's discount is 0.80, the one logged at the sale was 0.90.
E._ledger_table()
cols = {r["name"] for r in E.store_rows("pragma table_info(sell_log)")}
ok("the sale log has a `disc` column", "disc" in cols and E.STORE.get("sell_live") is True)
E.save_json(E.DISCOUNT_FILE, {"live": [0.80] * 10, "pre": [0.80] * 10})
row = {"ticker": "KXMVECROSSCATEGORY-X1", "kind": "combo", "offer": 5.0, "pays": 10.0, "frac": 1.0, "chance": 0.7, "live": 1}
a = E.knob_sale_expect(dict(row))
ok("no logged discount: today's (0.80 x 0.7 x 10 = 5.60), as before", a == (5.0, 0.8 * 0.7 * 10), a)
a = E.knob_sale_expect(dict(row, disc=0.90))
ok("a higher discount logged at the sale counts (0.90 x 0.7 x 10 = 6.30): the brake is not gentler", abs(a[1] - 6.3) < 1e-9, a)
a = E.knob_sale_expect(dict(row, disc=0.60))
ok("a LOWER logged discount never lowers the bar below today's (never looser)", abs(a[1] - 5.6) < 1e-9, a)
for bad in (None, "x", 0.2, 1.5, float("nan")):
    a = E.knob_sale_expect(dict(row, disc=bad))
    ok(f"an unusable logged discount ({bad!r}) is ignored", a is not None and abs(a[1] - 5.6) < 1e-9, a)
E.sale_store({"at": now - 50, "ticker": "KXMVECROSSCATEGORY-X1", "result": "sold", "kind": "combo", "offer": 5.0, "cost": 5.0,
              "pays": 10, "chance": 0.7, "live": True, "disc": 0.9})
got = E.store_rows("select disc, live from sell_log")
ok("a sale stores its discount", got == [{"disc": 0.9, "live": 1}], got)
by = E._knob_brake_sales({"brake": {}}, now)
vals = [x for v in by.values() for x in v]
ok("the brake reads it: 5.00 sold against 6.30 expected = -1.30", len(vals) == 1 and abs(vals[0][1] + 1.3) < 0.011, by)

# ---- #551b: the card's Lock-in line uses the tuned arm numbers
E.CFG.update(auto_sell=True, smart_sell=True, ride=2, lock_trail=True)
E.can_trade = lambda: True
E.hands_off = lambda t: False
T = "KXMVE-TEST1"
h = {"left": 1, "pays": 10.0, "p": 0.7, "cost": 3.0, "legs_left": [(0.7, True, 0)], "need": [(("yes", "KXA-1"), "")], "hold": 3.0}
E.MINE["hold"][T] = h; E.MINE.setdefault("peak", {}).pop(T, None); E.MINE["cash"].pop(T, None)
E.knob_exit_prm = lambda tks: {}
v0 = E._smart_trigger(T, h)
E.knob_exit_prm = lambda tks: {"trail_arm": 0.8, "trail_arm_cost": 1.5}
v1 = E._smart_trigger(T, h)
ok("lock-in arm with the starting numbers (0.60 x $10)", v0["lock_at"] == 6.0, v0["lock_at"])
ok("a tuned arm (0.80 x $10) is what the card shows, as the sale uses", v1["lock_at"] == 8.0, v1["lock_at"])

# ---- #302: auto_sell_now with a learned 0.99 slip: an offer at 0.98 x the line is skipped, one at 0.995 x sells
CT = "KXNBAGAME-26NOV19LALBOS-LAL"
E.CFG.update(auto_hedge=False, stop_loss=False, take_profit=0, lock_trail=False, auto_cap=5)
LINE = 12.0
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", LINE)
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], None)
E.smart_sell_singles = lambda: []
E.haptic = E.loading = lambda *a: None
E.resting_sells = lambda: {}
E.drop_cash = lambda t: E.MINE["cash"].pop(t, None)
E._cash_pause = lambda s: None
E.leg_score = lambda l: {"state": "in", "me": 21, "opp": 17, "brk": False}
E.combo_live_fair = lambda legs, now=None: (None, "no live chance in this test")
E.knob_auto_slip = lambda tks: 0.99
accepts = []
E.get_cash_offer = lambda t, f=1.0: {"offer": LINE * 0.995, "frac": 1.0, "rfq": "x", "quote": "q", "contracts": 20, "at": E.time.time()}
E.accept_once = lambda o, t=None: (accepts.append(o["offer"]), "executed")[1]
hh = {"label": "Combo 1", "need": [(("yes", CT), "Lakers")], "pre_of": {CT: 0.6}, "ch_of": {CT: 0.7},
      "legs_left": [(0.7, True, 0)], "cost": 10, "p": 0.7, "pays": 20, "won_some": True, "left": 1}


def run(offer):
    accepts.clear()
    E.COMBO_WAIT.clear(); E.MINE["hold"] = {"C1": dict(hh)}; E.MINE["tp_asked"] = {}; E.MINE.pop("real_asks", None)
    E.MINE["cash"] = {"C1": {"offer": offer, "frac": 1.0, "rfq": "real", "quote": "q", "contracts": 20, "at": E.time.time()}}
    E.MINE["busy"] = False; E.MINE.setdefault("selling", set())
    E.save_json(E.ORDER_LEDGER, {})
    E.get_cash_offer = lambda t, f=1.0: dict(E.MINE["cash"]["C1"]) if "C1" in E.MINE["cash"] else {"offer": offer, "frac": 1.0, "rfq": "real", "quote": "q", "contracts": 20, "at": E.time.time()}
    return E.auto_sell_now({"acts": {}})


out = run(LINE * 0.98)
ok("slip 0.99: a real offer at 0.98 x the line is skipped (nothing accepted)", accepts == [], accepts)
out = run(LINE * 0.995)
ok("slip 0.99: a real offer at 0.995 x the line sells", len(accepts) == 1, (accepts, out))
E.knob_auto_slip = lambda tks: 0.97
out = run(LINE * 0.98)
ok("control: at the starting 0.97 slip the same 0.98 x line offer sells (so the 0.99 skip above is the slip)", len(accepts) == 1, accepts)
