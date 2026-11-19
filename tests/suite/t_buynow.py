# The panel buys right after Pete approves it (issue #51), not ~45 minutes before each game. Every safeguard stays:
# the fresh price recheck (swap or skip), the start rules, Pause, unknown outcome = "check" never retried, no double
# buy from two passes at once, games under way switched off after approval = skipped. Fake Kalshi throughout.
import os, sys, time, tempfile, threading, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
import datetime as _dt; _u = _dt.datetime.now(_dt.timezone.utc); E.PACIFIC = _dt.timezone(_dt.timedelta(hours=round(12 - _u.hour - _u.minute / 60)))
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.REBUILD_FLAG = os.path.join(E.HERE, "panel_rebuild.flag"); E.REBUILD_STATE = os.path.join(E.HERE, "combo_rebuild.json")
E.BUY_FLAG = os.path.join(E.HERE, "panel_buy.flag")
E.fetch_account = lambda **k: ([], 300.0, None)
E.account_events = lambda *a, **k: set()
E.kalshi_send = lambda *a, **k: {}
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
BOOK = {}
BOUGHT = []
E.book_depth = lambda t, max_age=60: BOOK.get(t, {"ask": 0.50, "bid": 0.49})
E.buy_single = lambda t, n, px: (BOUGHT.append((t, n, px)) or (n, None))


def mk(t, ev, f, p, k, code="nba"):
    l = {"ticker": t, "event": ev, "pick": t, "p": p, "fair": f}; E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(k))
    return E._cand("single", code, [l], f, (f - p - E.single_fee(p)) / (p + E.single_fee(p)), "w", price=p)


def fresh_panel(cands):
    E.store_x("delete from panel", ())
    E.PANEL_POOL.clear(); E.PANEL_POOL["nba"] = (time.time(), cands)
    BOUGHT.clear(); BOOK.clear()
    p = E.build_panel(); E.panel_save_draft(p, "real")
    return p


def items():
    return {c["id"]: c for c in E.panel_get("real")["items"]}


# the lead-time code is gone; no bet carries a buy time
src = open("wahome/engine.py").read()
ok("no lead-time setting or best-lead code left", "buy_before" not in src and "def best_combo_lead" not in src)
A = mk("A1", "KXNBAGAME-A", .60, .50, now + 9 * 3600)        # a game many hours away
B = mk("B1", "KXNBAGAME-B", .62, .52, now + 10 * 3600)
p = fresh_panel([A, B])
ok("the draft has bets and none carries a buy time", len(p["items"]) == 2 and not any("buy_at" in c for c in p["items"]))

# Pause blocks, even right after approval
okA, msg = E.panel_approve(None, "all", at=p["at"])
ok("approve says it buys now, not shortly before the game", okA and "buys them now" in msg and "Pause" in msg and "45" not in msg and "before its game" not in msg)
ok("approve wakes the Mac's buying pass", os.path.exists(E.BUY_FLAG))
ok("the watcher's check clears the request", E.buy_asked() and not os.path.exists(E.BUY_FLAG) and not E.buy_asked())
E.panel_exec(paused=True, may_trade=True)
ok("Pause wins: nothing bought", not BOUGHT and all(c["state"] == "scheduled" for c in items().values()))
ok("...and the card can say it's paused", all(c.get("hold") == "paused" for c in items().values()))
E.panel_exec(paused=False, may_trade=False)
ok("can't trade (the Pi / no key): nothing bought", not BOUGHT and all(c["state"] == "scheduled" for c in items().values()))

# the next pass buys both at once, hours before their games, at a rechecked price
E.panel_exec()
st = items()
ok("bought on the next pass, games 9-10 hours away", len(BOUGHT) == 2 and all(c["state"] == "bought" for c in st.values()))
ok("...and the paused note is gone", not any(c.get("hold") for c in st.values()))
ok("bought at the price checked right then", all(px == .50 for _, _, px in BOUGHT) and all(c.get("bought_at") for c in st.values()))
E.panel_exec()
ok("never bought twice", len(BOUGHT) == 2)

# the price check at buy time still turns a bet down
p = fresh_panel([A, B])
E.panel_approve(None, "all", at=p["at"])
BOOK["A1"] = {"ask": 0.59, "bid": 0.57}
E.panel_exec()
st = items()
ok("price moved on Kalshi at buy time: not bought", [t for t, _, _ in BOUGHT] == ["B1"] and st[A["id"]]["state"] == "failed"
   and "price moved" in st[A["id"]]["note"])

# no longer qualifies in the newest prices: swapped for a similar bet (bought on the next pass), or skipped
p = fresh_panel([A])
E.panel_approve(None, "all", at=p["at"])
C = mk("C1", "KXNBAGAME-C", .61, .51, now + 9.5 * 3600)
E.PANEL_POOL["nba"] = (time.time(), [dict(A, ret=-0.05), C])
E.buy_asked()
E.panel_exec()
st = items()
ok("price slipped before buying: swapped in a similar bet", st[A["id"]]["state"] == "swapped" and st.get(C["id"], {}).get("state") == "scheduled")
ok("the swap asks for another pass right away", E.buy_asked())
E.panel_exec()
ok("the swapped-in bet is bought on that pass", [t for t, _, _ in BOUGHT] == ["C1"] and items()[C["id"]]["state"] == "bought")
p = fresh_panel([A])
E.panel_approve(None, "all", at=p["at"])
E.PANEL_POOL["nba"] = (time.time(), [dict(A, ret=-0.05)])
E.panel_exec()
ok("nothing similar qualifies: skipped, nothing bought", not BOUGHT and items()[A["id"]]["state"] == "skipped")

# prices too old to judge: waits, doesn't buy blind
p = fresh_panel([A])
E.panel_approve(None, "all", at=p["at"])
E.PANEL_POOL["nba"] = (time.time() - 20 * 60, [A])
E.panel_exec()
ok("stale candidates: waits, nothing bought", not BOUGHT and items()[A["id"]]["state"] == "scheduled")
ok("...says it's waiting for a fresh price, and the Mac looks at that sport again soon",
   items()[A["id"]].get("hold") == "price" and "nba" in E.sports_near())

# a bet approved before this change keeps the buy time it was approved under (no surprise buys on the update)
E._set_items(E._panel_day(), "real", {A["id"]: {"buy_at": time.time() + 3600}})
E.PANEL_POOL["nba"] = (time.time(), [A])
E.panel_exec()
ok("approved under the old timing: waits for its time", not BOUGHT and items()[A["id"]]["state"] == "scheduled")
E._set_items(E._panel_day(), "real", {A["id"]: {"buy_at": time.time() - 1}})

# start rules unchanged: a pre-game bet within 5 minutes of its start is skipped
E.PANEL_POOL["nba"] = (time.time(), [A])
E._set_items(E._panel_day(), "real", {A["id"]: {"kick": time.time() + 120}})
E.panel_exec()
ok("game about to start: skipped, not bought", not BOUGHT and items()[A["id"]]["state"] == "skipped")

# unknown outcome: marked check, never retried
p = fresh_panel([A])
E.panel_approve(None, "all", at=p["at"])
calls = []
real_buy = E.buy_single
E.buy_single = lambda t, n, px: calls.append(t) or (_ for _ in ()).throw(TimeoutError("lost the Mac"))
E.panel_exec(); E.panel_exec()
ok("unknown outcome: 'check', tried once only", calls == ["A1"] and items()[A["id"]]["state"] == "check")
E.buy_single = real_buy

# two passes at once never buy the same bet twice: one nested inside a buy, and two threads
p = fresh_panel([A, B])
E.panel_approve(None, "all", at=p["at"])
inner = []


def nested_buy(t, n, px):
    BOUGHT.append((t, n, px))
    if not inner:
        inner.append(1); E.panel_exec()                  # a second pass while the first one's order is out
    return n, None


E.buy_single = nested_buy
E.panel_exec()
ok("a pass during a purchase doesn't buy it again", sorted(t for t, _, _ in BOUGHT) == ["A1", "B1"])
p = fresh_panel([A, B])
E.panel_approve(None, "all", at=p["at"])


def slow_buy(t, n, px):
    BOUGHT.append((t, n, px)); time.sleep(.3)
    return n, None


E.buy_single = slow_buy
ths = [threading.Thread(target=E.panel_exec) for _ in range(3)]
[t.start() for t in ths]; [t.join() for t in ths]
ok("three passes at once: each bet bought exactly once", sorted(t for t, _, _ in BOUGHT) == ["A1", "B1"]
   and all(c["state"] == "bought" for c in items().values()))
E.buy_single = real_buy

# Add (one sport's picks or the 🆕 extras) is bought right away too
p = fresh_panel([A])
E.panel_approve(None, "all", at=p["at"]); E.panel_exec()
D = mk("D1", "KXNBAGAME-D", .63, .52, now + 8 * 3600)
E.PANEL_POOL["nba"] = (time.time(), [D])
x = E.build_panel(budget=20, exclude=E._events_of(A))
E.store_x("insert or replace into panel values(?,?,?,?,?)", (E._panel_day(x["at"]), "extra", x["at"], "draft", E.json.dumps(x)))
E.buy_asked()
okX, msg = E.panel_add([D["id"]], "extra")
ok("Add says it buys now and wakes the Mac", okX and "buying" in msg and E.buy_asked())
ok("the added bet has no buy time", "buy_at" not in items()[D["id"]])
E.panel_exec()
ok("the added bet is bought on the next pass", "D1" in [t for t, _, _ in BOUGHT] and items()[D["id"]]["state"] == "bought")

# a live bet approved, then games under way switched off: skipped, not bought
p = fresh_panel([A])
E.panel_approve(None, "all", at=p["at"])
E._set_items(E._panel_day(), "real", {A["id"]: {"live": True, "kick_pre": None, "kick": time.time() - 1200}})
was = E.live_panel_on
E.live_panel_on = lambda: False
E.panel_exec()
ok("games under way switched off after approval: live bet skipped", not BOUGHT and items()[A["id"]]["state"] == "skipped")
E.live_panel_on = was

# the watcher's buying loop wakes within seconds of an Approve / Add
sys.argv = ["combo_watcher.py"]
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py"); W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
E.buy_asked()                                         # start clean (the approvals above each asked)
t0 = time.time(); threading.Timer(.4, E.ask_buy).start()
woke = W.panel_wait(E, 30, step=.1)
ok("panel loop wakes within seconds of a tap", woke and .3 < time.time() - t0 < 2 and not os.path.exists(E.BUY_FLAG))
t0 = time.time()
ok("without a tap it waits its full minute", W.panel_wait(E, .5, step=.1) is False and time.time() - t0 >= .5)
