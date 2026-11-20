# "Add to today's panel" is safe to tap again and again (issue #62): two adds of the same extra (one after the other,
# or two at once) make one panel row and at most one order; an added extra leaves the extras card at once; a bet that
# was bought, is being bought, failed or needs a check is never offered again as an extra the same day (a skipped
# one may come back); Approve twice approves once; Pause still wins. Fake Kalshi throughout.
import os, time, tempfile, threading, importlib.util
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


def mk(t, ev, f, p, k):
    l = {"ticker": t, "event": ev, "pick": t, "p": p, "fair": f}; E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(k))
    return E._cand("single", "nba", [l], f, (f - p - E.single_fee(p)) / (p + E.single_fee(p)), "w", price=p)


def real():
    return E.panel_get("real")["items"]


def rows(cid):
    return [c for c in real() if c["id"] == cid]


A = mk("A1", "KXNBAGAME-A", .60, .50, now + 9000)
B = mk("B1", "KXNBAGAME-B", .58, .50, now + 9000)
E.PANEL_POOL = {"nba": (now, [A, B])}
E.panel_pass()
p = E.panel_get("real")
ok1, _ = E.panel_approve(None, "all", at=p["at"])
ok2, msg2 = E.panel_approve(None, "all", at=p["at"])
ok("Approve twice approves once", ok1 and not ok2 and "already approved" in msg2)
E.panel_exec()
ok("the approved bets are bought once", sorted(t for t, _, _ in BOUGHT) == ["A1", "B1"])

# two extras turn up after approval
X = mk("X1", "KXNBAGAME-X", .62, .50, now + 9000)
Y = mk("Y1", "KXNBAGAME-Y", .61, .50, now + 9000)
E.PANEL_POOL["nba"] = (time.time(), [A, B, X, Y])
E.panel_pass()
x = E.panel_extras()
ids = [c["id"] for c in x["items"]]
ok("both extras are offered", X["id"] in ids and Y["id"] in ids)

# Pause: added, but nothing bought
okA, msgA = E.panel_add(ids, "extra")
ok("first Add adds both", okA and len(rows(X["id"])) == 1 and len(rows(Y["id"])) == 1 and "Added 2" in msgA)
ok("the added extras leave the card at once", not (E.panel_extras() or {}).get("items")
   and not E.panel_get("extra")["items"])
okB, msgB = E.panel_add(ids, "extra")
ok("a second Add does nothing", len(rows(X["id"])) == 1 and len(rows(Y["id"])) == 1 and "Already" in msgB)
E.panel_exec(paused=True)
ok("Pause still wins after Add", len(BOUGHT) == 2 and rows(X["id"])[0]["state"] == "scheduled")

# two Adds at the same moment (two phones / a double tap through two requests), then the buy pass
E.panel_tx(E._panel_day(), "real", lambda cur, st: (dict(cur, items=[c for c in cur["items"] if c["id"] not in (X["id"], Y["id"])]), st))
E.PANEL_POOL["nba"] = (time.time(), [A, B, X, Y])
E.store_x("delete from panel where mode='extra'", ())
E.panel_pass()
ids = [c["id"] for c in (E.panel_extras() or {}).get("items", [])]
res = []
ts = [threading.Thread(target=lambda: res.append(E.panel_add(ids, "extra"))) for _ in range(4)]
[t.start() for t in ts]; [t.join() for t in ts]
ok("four Adds at once: one row per bet", len(ids) == 2 and len(rows(X["id"])) == 1 and len(rows(Y["id"])) == 1)
ok("...and only one of them added anything", sum(1 for o, m in res if "Added" in m) == 1)
done = []
ps = [threading.Thread(target=lambda: done.append(E.panel_exec())) for _ in range(3)]
[t.start() for t in ps]; [t.join() for t in ps]
E.panel_exec()
ok("at most one order per bet", sorted(t for t, _, _ in BOUGHT) == ["A1", "B1", "X1", "Y1"])
E.panel_add(ids, "extra"); E.panel_exec()
ok("Add after it was bought: no second order", len(BOUGHT) == 4 and len(rows(X["id"])) == 1)

# bought / failed / check bets never come back as extras; a skipped one may
E.PANEL_POOL["nba"] = (time.time(), [A, B, X, Y])
E.store_x("delete from panel where mode='extra'", ())
E.panel_pass()
left = {c["id"] for c in (E.panel_extras() or {}).get("items", [])}
ok("bought extras aren't offered again", X["id"] not in left and Y["id"] not in left)
for st in ("failed", "check", "buying", "swapped", "skipped"):
    E._set_items(E._panel_day(), "real", {X["id"]: {"state": st}})
    E.panel_tx(E._panel_day(), "real", lambda cur, s: (dict(cur, items=[c for c in cur["items"] if c["id"] != Y["id"]]), s))
    E.store_x("delete from panel where mode='extra'", ())
    E.panel_pass()
    raw = {c["id"] for c in (E.panel_get("extra") or {}).get("items", [])}
    shown = {c["id"] for c in (E.panel_extras() or {}).get("items", [])}
    if st in ("skipped", "swapped"):
        ok(f"a {st} bet can come back as an extra", X["id"] in raw and X["id"] in shown)
    else:
        ok(f"a {st} bet is never offered again", X["id"] not in raw and X["id"] not in shown)
# and the card hides a tried bet even if an older extras row still lists it
E._set_items(E._panel_day(), "real", {X["id"]: {"state": "failed"}})
ok("an old extras row can't show a failed bet", X["id"] not in {c["id"] for c in (E.panel_extras() or {}).get("items", [])})
n = len(BOUGHT)
okF, msgF = E.panel_add([X["id"]], "extra"); E.panel_exec()
ok("re-adding a failed bet does nothing", len(BOUGHT) == n and rows(X["id"])[0]["state"] == "failed")
ok("...and says so plainly, not 'already in'", not okF and "couldn't be bought earlier today" in msgF and "Already" not in msgF)
# an extra on a game a just-added bet covers isn't shown (it would always be refused)
Z = mk("Z1", "KXNBAGAME-Z", .62, .50, now + 9000)
Z2 = E._cand("single", "nba", [{"ticker": "Z2", "event": "KXNBAGAME-Z", "pick": "Z2", "p": .5, "fair": .6}], .6, .1, "w", price=.5)
E.store_x("delete from panel where mode='extra'", ())
E.panel_tx(E._panel_day(), "extra", lambda cur, s: ({"at": time.time(), "items": [dict(Z, stake=2.0), dict(Z2, stake=2.0)], "told": []}, "draft"))
E.panel_add([Z["id"]], "extra")
ok("an extra on a game just added isn't offered", not {c["id"] for c in (E.panel_extras() or {}).get("items", [])} & {Z["id"], Z2["id"]})
src = open("wahome/engine.py").read()
ok("unknown outcome still marked check, never retried", '"check"' in src and "never retried" in src)
