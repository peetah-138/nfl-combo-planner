# CHECK: group=engine
# The 'Never sell at a loss' choice was removed (Pete's explicit decision, #479). A saved 'never' (any device, an old
# settings file, an old phone) reads as 'Let it tune itself', never as Allow and never a crash; auto cash-out no longer
# passes a cost floor for it, and a single with an unknown cost or a sale just under cost is no longer skipped for it.
# Every other loss guard is untouched. No real orders: every trading call is faked.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)


ok("the choices are Let it tune itself and Allow (guarded) only", E.SL_MODES == ("tune", "allow") and "never" not in E.SL_MODE_SAY)
for saved, old_sw, want in (("never", True, "tune"), ("never", False, "tune"), ("never", None, "tune"), ("tune", True, "tune"),
                            ("allow", False, "allow"), (None, True, "allow"), (None, False, "tune"), ("NEVER", False, "tune"),
                            ({"x": 1}, False, "tune"), (7, True, "allow")):
    E.CFG.update(stop_loss_mode=saved, stop_loss=old_sw)
    if E.sl_mode() != want:
        break
ok("a saved 'never' reads as 'tune' on every path (not 'allow', no crash); unreadable values read as before", E.sl_mode() == want)
E.CFG.update(stop_loss_mode="never", stop_loss=True)
ok("a saved 'never' beats a stale old 'on' switch: still 'tune'", E.sl_mode() == "tune")
E.CFG.update(stop_loss_mode=None, stop_loss=False)

# ---- the save/merge helper: an incoming or stored 'never' becomes 'tune'
def sync(cur, inc):
    c = dict(cur); E.sl_sync(c, inc); return c
ok("a phone sending 'never' is saved as 'tune' (old switch off)", sync({"stop_loss": True, "stop_loss_mode": "allow"}, {"stop_loss_mode": "never"})
   == {"stop_loss": False, "stop_loss_mode": "tune"})
ok("a stored 'never' stays 'tune' when an old page sends only 'off' or nothing useful",
   sync({"stop_loss": False, "stop_loss_mode": "never"}, {"stop_loss": False})["stop_loss_mode"] == "tune"
   and sync({"stop_loss": False, "stop_loss_mode": "never"}, {"stop_loss": True, "stop_loss_mode": None})["stop_loss_mode"] != "allow")

# ---- sl_allowed treats a saved 'never' as 'tune' (not allowed unless the league's own record says so; never 'allow')
E.CFG.update(stop_loss_mode="never", stop_loss=True)
E.knob_switch_on = lambda: False
ok("sl_allowed with a saved 'never': follows 'tune' (off here), not Allow", E.sl_allowed(["KXNBAGAME-26NOV19LALBOS-LAL"]) is False)

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
E.CFG["flex_sell"] = False                     # today's rule: only the old retry bar
offer(); msg = E.accept_cash("C1")
ok("no floor (every choice now): the 3% retry rule as before", acc == [10.1, 9.9] and msg.startswith("✅"))
src = open(spec.origin).read()
ok("auto cash-out no longer passes a cost floor for any setting",
   'accept_cash(t, floor=h["cost"]' not in src and 'mode == "never"' not in src and "sl_mode() == \"never\"" not in src
   and 'sl_mode() != "never"' not in src and 'mode != "never"' not in src)

# ---- singles: a saved 'never' no longer skips an unknown cost or a sale just under cost
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
fee = E.single_fee(0.5, 3)
ok("saved 'never': an unknown cost is no longer skipped by this setting", run(None) and run(0))
ok("saved 'never': proceeds just under cost after the fee are no longer skipped by this setting",
   run(round(3 * (0.5 - fee) + 0.001, 4)))
E.CFG.update(stop_loss_mode="allow")
ok("Allow: the same (as before)", run(round(3 * (0.5 - fee) + 0.001, 4)))
