import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SELF_SELL = os.path.join(E.HERE, "ss.json"); E.SELL_LOG = os.path.join(E.HERE, "sell.log")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
E.leg_score = lambda l: None
E.CFG.update(smart_sell=True, take_profit=0, lock_trail=True, auto_sell=True, auto_cap=5)

def item(t, q, n=10, cost=5.6, side="yes", state="live", kind="spread"):
    return {"t": t, "kind": kind, "sport": "nfl", "side": side, "label": t, "n": n, "cost": cost, "chance": q, "state": state}

why, fl = E.single_sell_reason(item("A", .9), .88, .89)
ok("covering late, bid 88c on a 56c spread: smart sell takes it", why == "smart" and 8 < fl < 8.7)
why, fl = E.single_sell_reason(item("B", .6, state="pre"), .58, .60)
ok("before the game at about the price paid: holds", why is None)
why, fl = E.single_sell_reason(item("C", .45), .44, .46)
ok("an underdog right now: holds (never sells a long shot cheap)", why is None)
why, fl = E.single_sell_reason(item("D", .9, state="over"), .97, .99)
ok("game over, waiting to settle: holds for the full $1", why is None)
# lock-in after a run-up
E.CFG["smart_sell"] = False
x = item("L", .8, cost=4.0)
E.single_sell_reason(x, .80, .81)            # peak about $7.9 (armed: over 60% of the payout and 1.5x cost)
why, fl = E.single_sell_reason(dict(x, chance=.62), .62, .63)
ok("fell 20% from a big high, still a profit: locks it in", why == "lock in" and abs(fl - 4.4) < .01)
why, fl = E.single_sell_reason(dict(x, chance=.42), .42, .43)
ok("...but never at a loss", why is None)
E.CFG["smart_sell"] = True

# the selling pass
orders = []
def fake_send(method, path, body=None, params=None):
    if method == "GET":
        return {"orders": [{"ticker": "REST", "action": "sell"}]}
    orders.append(body)
    return {"order": {"status": "executed", "fill_count": body["count"]}}
E.kalshi_send = fake_send
E.SINGLES.update(at=time.time(), items=[item("SELLME", .9), item("NOSIDE", .92, side="no"), item("MINE", .9),
                                        item("THIN", .9), item("REST", .9), item("HOLD", .55)],
                 mk={"SELLME": {"yes_bid_dollars": "0.88", "yes_ask_dollars": "0.89"},
                     "NOSIDE": {"no_bid_dollars": "0.90", "no_ask_dollars": "0.91"},
                     "MINE": {"yes_bid_dollars": "0.88", "yes_ask_dollars": "0.89"},
                     "THIN": {"yes_bid_dollars": "0.88", "yes_ask_dollars": "0.97"},
                     "REST": {"yes_bid_dollars": "0.88", "yes_ask_dollars": "0.89"},
                     "HOLD": {"yes_bid_dollars": "0.54", "yes_ask_dollars": "0.56"}})
E.set_self_sell("MINE", True)
msgs = E.smart_sell_singles()
sold = {o["ticker"]: o for o in orders}
ok("sells the ones smart sell picks, yes and no sides", set(sold) == {"SELLME", "NOSIDE"})
ok("sell orders are sell-only, at the bid, fill-now-or-cancel", sold["SELLME"]["action"] == "sell" and sold["SELLME"]["yes_price"] == 88
   and sold["NOSIDE"]["side"] == "no" and sold["NOSIDE"]["no_price"] == 90 and all(o["reduce_only"] and o["time_in_force"] == "immediate_or_cancel" for o in orders))
ok("skips I'll sell it, thin markets and ones with a sell order waiting", not {"MINE", "THIN", "REST", "HOLD"} & set(sold))
ok("you're told what it sold", len(msgs) == 2 and all(m.startswith("🤖") for m in msgs))
orders.clear(); E.SINGLES["at"] = time.time() - 600
ok("never acts on old prices", E.smart_sell_singles() == [] and not orders)
E.CFG["auto_cap"] = 2; E.SINGLES["at"] = time.time(); E.MINE.get("peak", {}).clear()
E.SINGLES["items"] = [item("SELLME2", .9)]; E.SINGLES["mk"]["SELLME2"] = {"yes_bid_dollars": "0.88", "yes_ask_dollars": "0.89"}
E.smart_sell_singles()
ok("the daily cap on automatic sales covers singles too", not orders)
# runs as part of auto cash-out, only when that's on
E.CFG["auto_cap"] = 9; E.can_trade = lambda: True; E.MINE["hold"] = {}; E.MINE["busy"] = False
E.CFG["auto_sell"] = False; E.SINGLES["at"] = time.time()
E.auto_sell_now({"acts": {}}); ok("auto cash-out off: nothing sold", not orders)
E.CFG["auto_sell"] = True; E.SINGLES["at"] = time.time()
E.auto_sell_now({"acts": {}}); ok("auto cash-out on: singles are smart-sold", any(o["ticker"] == "SELLME2" for o in orders))
