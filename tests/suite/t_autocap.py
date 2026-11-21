"""Auto cash-outs a day can be Unlimited (issue #217): unlimited never blocks, a number still does, the sentinel
survives a settings round trip, and an older process reads it as a cap it never reaches."""
import os, re, json, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
from wsrc import watcher_text
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SELF_SELL = os.path.join(E.HERE, "ss.json"); E.SELL_LOG = os.path.join(E.HERE, "sell.log")
E.leg_score = lambda l: None
E.CFG.update(smart_sell=True, take_profit=0, lock_trail=True, auto_sell=True, auto_cap=5)

U = E.AUTO_CAP_UNLIMITED
ok("the default stays 5 a day", E.DEFAULTS["auto_cap"] == 5)
ok("Unlimited is a clear sentinel well over the slider's numbers", U == 1000 and U > E.AUTO_CAP_MAX == 10)
ok("auto_cap_limit: numbers are numbers, over 10 is Unlimited, junk is the default 5",
   E.auto_cap_limit(1) == 1 and E.auto_cap_limit(10) == 10 and E.auto_cap_limit(U) is None
   and E.auto_cap_limit(11) is None and E.auto_cap_limit("1000") is None and E.auto_cap_limit(1000.0) is None
   and E.auto_cap_limit(None) == 5 and E.auto_cap_limit("lots") == 5 and E.auto_cap_limit(float("inf")) == 5)


def sales(n, result="sold"):
    open(E.SELL_LOG, "w").close()
    for i in range(n):
        E.log_decision({"combo": f"S{i}", "ticker": f"S{i}", "result": result, "offer": 5.0, "why": "smart"})


def item(t, q, n=10, cost=5.6):
    return {"t": t, "kind": "spread", "sport": "nfl", "side": "yes", "label": t, "n": n, "cost": cost, "chance": q, "state": "live"}


orders = []
def fake_send(method, path, body=None, params=None):
    if method == "GET":
        return {"orders": []}
    orders.append(body)
    return {"order": {"status": "executed", "fill_count": body["count"]}}
E.kalshi_send = fake_send


def sell_one(t):
    orders.clear(); E.MINE.get("peak", {}).clear()
    E.SINGLES.update(at=time.time(), items=[item(t, .9)], mk={t: {"yes_bid_dollars": "0.88", "yes_ask_dollars": "0.89"}})
    E.smart_sell_singles()
    return any(o.get("ticker") == t for o in orders)


E.CFG["auto_cap"] = U
sales(10)
ok("Unlimited: the 11th automatic sale of the day goes through", not E.auto_cap_reached() and sell_one("ELEVENTH"))
sales(49)
ok("Unlimited: the 50th goes through too", sell_one("FIFTIETH"))
sales(60, "check")
ok("Unlimited: even 60 'check' sales never block", not E.auto_cap_reached() and sell_one("SIXTYFIRST"))

E.CFG["auto_cap"] = 10
sales(10)
ok("a number cap still blocks: 10 sold today, cap 10, no 11th", E.auto_cap_reached() and not sell_one("CAPPED"))
sales(9)
ok("...and under it, the sale goes through", sell_one("UNDER"))
E.CFG["auto_cap"] = 3
sales(2); E.log_decision({"combo": "C", "ticker": "C", "result": "check", "offer": 5.0, "why": "smart"})
ok("a 'check' sale still counts toward a number cap", E.auto_cap_reached() and not sell_one("AFTERCHECK"))
E.CFG["auto_cap"] = "garbage"
sales(5)
ok("an unreadable cap is the default 5 (never unlimited)", E.auto_cap_reached())

# the combo path's message names the cap; with Unlimited it is never reached
src = open("wahome/engine.py", encoding="utf-8").read()
ok("every engine cap check goes through auto_cap_reached (no int(CFG['auto_cap']) left)",
   'int(CFG.get("auto_cap"' not in src and src.count("auto_cap_reached()") >= 3)

# a settings round trip keeps the sentinel
E.SAVED = E.MAIN_SAVED = os.path.join(E.HERE, "combo_settings.json")
E.CFG["auto_cap"] = U; E.save_cfg()
saved = json.load(open(E.SAVED))
E.CFG["auto_cap"] = 5
E.set_league("nfl")
ok("saved and loaded again: still Unlimited", saved.get("auto_cap") == U and E.CFG["auto_cap"] == U and E.auto_cap_limit() is None)
ok("it is shared and synced to the watcher as before", "auto_cap" in E.SHARED_KEYS and "auto_cap" in E.WATCHER_SYNCED)

# an older process (the 130 rule, verbatim): reads the sentinel as a big cap, never zero, never crashes
old_rule = lambda cfg, sold: sold >= int(cfg.get("auto_cap", 5))
ok("an older process: 1000 a day, so the 11th and 50th sales are allowed",
   not old_rule({"auto_cap": U}, 10) and not old_rule({"auto_cap": U}, 49) and not old_rule(json.loads(json.dumps({"auto_cap": U})), 999))

# the web app's settings save turns anything over 10 into the sentinel; the phone's Settings has the stop too
W = watcher_text()
ok("web app save: over 10 is stored as AUTO_CAP_UNLIMITED",
   'k == "auto_cap" and v is not None and A.auto_cap_limit(v) is None' in W and "v = A.AUTO_CAP_UNLIMITED" in W)
ok("the SPA slider: top stop 11 shows and saves as Unlimited",
   "auto_cap:[1,11,1]" in W and "AUTO_CAP_UNL=1000" in W and "return 'Unlimited'" in W)
ok("the phone's Settings slider has an Unlimited stop and saves the sentinel",
   re.search(r'slider\("auto_cap".*?AUTO_CAP_MAX \+ 1.*?"Unlimited"', src, re.S) is not None
   and 'CFG["auto_cap"] = AUTO_CAP_UNLIMITED' in src)
