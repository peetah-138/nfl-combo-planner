# CHECK: group=engine
# Pete sets his own bet amount (issue #145). The page only says what he wants; the engine checks every amount again
# (own_stake: a real, finite number inside the limits, rounded down to the cent) and never trusts the page: negative,
# zero, NaN, infinite, text, booleans and out-of-range amounts are refused with plain words and nothing is priced or
# bought. Buy straight prices the amount he chose (contracts rounded down, never over the book's depth); the daily
# panel takes his own stakes at Approve / Add, inside the panel budget (over it = nothing approved), the amount it then
# buys is exactly his, and the card's numbers follow (panel_whatif reads only). No new automatic buying: every path
# here is his tap. Fake Kalshi throughout.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
import datetime as _dt; _u = _dt.datetime.now(_dt.timezone.utc); E.PACIFIC = _dt.timezone(_dt.timedelta(hours=round(12 - _u.hour - _u.minute / 60)))
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.REBUILD_FLAG = os.path.join(E.HERE, "panel_rebuild.flag"); E.REBUILD_STATE = os.path.join(E.HERE, "combo_rebuild.json")
E.BUY_FLAG = os.path.join(E.HERE, "panel_buy.flag")
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
E.fetch_account = lambda **k: ([], 300.0, None)
E.account_events = lambda *a, **k: set()
E.kalshi_send = lambda *a, **k: {}
E.haptic = lambda *a: None
ok = lambda n, c, *a: print(("PASS " if c else "FAIL ") + n, *(a if not c else ()))
now = time.time()

# ---- (1) own_stake: the one check every path uses
OS = E.own_stake
ok("no amount = use the recommended size", OS(None) == (None, None) and OS("") == (None, None) and OS("  ") == (None, None))
ok("a plain amount is taken", OS(7) == (7.0, None) and OS("12.5") == (12.5, None))
ok("cents are rounded DOWN, never up", OS(7.999)[0] == 7.99 and OS("3.336")[0] == 3.33 and OS(0.1 + 2.2)[0] == 2.3)
for bad in (-5, 0, "-1", float("nan"), "nan", float("inf"), "inf", "-inf", "abc", "1e400", True, False, [5], {"v": 5}):
    v, why = OS(bad)
    ok(f"refused: {bad!r} ({why})", v is None and why and "Nothing was priced or bought" in why)
ok("under the least: refused with the limit in words", OS(0.5)[0] is None and "$1" in OS(0.5)[1])
ok("over the most: refused, never clamped", OS(100.01)[0] is None and "$100" in OS(100.01)[1] and OS(100) == (100.0, None))
ok("custom limits", OS(1.5, 2, 50)[0] is None and OS(51, 2, 50)[0] is None and OS(50, 2, 50) == (50.0, None))

# ---- (2) get_offer never sends a NaN/infinite amount to Kalshi
SENT = []
E.kalshi_send = lambda *a, **k: (SENT.append(a), {})[1]
E.CTX.update(combos=[{"legs": [{"ticker": "T1", "event": "EV1", "pick": "x", "fair": 0.5}], "fair": 10.0, "min": 1}],
             stake=5, offers={})
for bad in (float("nan"), float("inf")):
    r = E.get_offer(1, amount=bad, check_cap=False)
    ok(f"get_offer({bad}) refused before anything is sent ({r.get('error')})", r.get("error") and not SENT)
E.kalshi_send = lambda *a, **k: {}

# ---- (3) Buy straight prices Pete's amount (single_buy_quote), with its sums and limits
E.set_league("nba")
E.CFG["budget"] = 100.0
E.can_trade = lambda: True
E.market_open = lambda t: (True, {"yes_sub_title": "Denver", "event_ticker": "KXNBAGAME-26NOV30DENLAL",
                                  "expected_expiration_time": "2099-01-01T00:00:00Z"})
E._game_over = lambda t: False
REAL_STARTED = E.started
E.started = lambda x: False
E.single_cap_block = lambda t, cost, now=None: (None, 10.0, 100.0)
DEPTH = {"v": 500}
E.book_depth = lambda t, max_age=60: {"ask": 0.40, "bid": 0.39, "ask_size": DEPTH["v"]}
T = "KXNBAGAME-26NOV30DENLAL-DEN"
X = {"ticker": T, "pick": "Denver", "event": "KXNBAGAME-26NOV30DENLAL", "fair": 0.50, "src": "pinnacle", "fair_at": now,
     "exp": "2099-01-01T00:00:00Z"}
per = 0.40 + E.single_fee(0.40)
q = E.single_buy_quote(X, 13.37)
ok(f"Buy straight at $13.37: that amount, contracts rounded down ({q.get('n')} at {per:.4f})",
   q["ok"] and q["stake"] == 13.37 and q["n"] == int(13.37 / per) and q["cost"] <= 13.37 and q["own"] is True)
ok(f"...with the expected profit in dollars ({q.get('ev')})", abs(q["ev"] - round(q["n"] * q["fair"] - q["cost"], 2)) < 1e-9)
qs = E.single_buy_quote(X, None)
ok("no amount: the suggested size, marked not his own", qs["ok"] and qs["stake"] == round(qs["sug"], 2) and qs["own"] is False)
for bad in (-3, "nan", float("inf"), 0, 500, "lots"):
    r = E.single_buy_quote(X, bad)
    ok(f"Buy straight refuses {bad!r}: nothing quoted ({r.get('msg')})", not r["ok"] and r.get("bad_stake") and "q" not in r)
DEPTH["v"] = 7.6
q = E.single_buy_quote(X, 50)
ok(f"never more than the book has for sale (7.6 for sale -> {q.get('n')})", q["n"] == 7 and q["cost"] <= 50)
DEPTH["v"] = 500
E.book_depth = lambda t, max_age=60: {"ask": 0.60, "bid": 0.59, "ask_size": 500}
q = E.single_buy_quote(X, 1.0)
ok(f"$1 at 60c buys one contract, never two (rounded down: {q.get('n')} for {q.get('cost')})", q["n"] == 1 and q["cost"] <= 1.0)
E.book_depth = lambda t, max_age=60: {"ask": 0.60, "bid": 0.59, "ask_size": 0.4}
q = E.single_buy_quote(X, 1.0)
ok(f"under one contract for sale: blocked, never rounded up ({q.get('blocked')})", q["n"] == 0 and q["blocked"])

# ---- (4) the daily panel: his stakes at Approve, inside the budget, and the amount bought is his
BOUGHT = []
E.book_depth = lambda t, max_age=60: {"ask": 0.50, "bid": 0.49}
E.buy_single = lambda t, n, px, **k: (BOUGHT.append((t, n, px)) or (n, None))
E.single_cap_block = lambda t, cost, now=None: (None, 0.0, 100.0)
E.started = REAL_STARTED


def mk(t, ev, f, p, k):
    l = {"ticker": t, "event": ev, "pick": t, "p": p, "fair": f}; E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(k))
    return E._cand("single", "nba", [l], f, (f - p - E.single_fee(p)) / (p + E.single_fee(p)), "w", price=p)


A = mk("A1", "KXNBAGAME-A", .60, .50, now + 9000)
B = mk("B1", "KXNBAGAME-B", .58, .50, now + 9000)
E.PANEL_POOL = {"nba": (now, [A, B])}
E.panel_pass()
p = E.panel_get("real")
ok("a draft panel to approve", p and len(p["items"]) == 2, p)
items = {c["id"]: c for c in p["items"]}
bud = float(p.get("budget"))
rec_a = items[A["id"]]["stake"]
w = E.panel_whatif("all", None, {A["id"]: 9.5})
ok(f"what-if at Pete's amount: reads only, stake follows ({w.get('stake')})",
   w["ok"] and abs(w["stake"] - (9.5 + items[B["id"]]["stake"])) < 0.01 and 0 <= w["p_ahead"] <= 1
   and E.panel_get("real")["status"] == "draft" and E.panel_get("real")["items"][0]["stake"] in (rec_a, items[B["id"]]["stake"]))
for bad in ({A["id"]: -2}, {A["id"]: "nan"}, {A["id"]: 1.0}, {A["id"]: 1e9}, "x", [1]):
    okb, why = E.panel_approve(None, "all", at=p["at"], stakes=bad)
    ok(f"Approve refuses stakes {bad!r}: nothing approved ({why})", not okb and E.panel_get("real")["status"] == "draft")
over = bud + 1 if bud + 1 <= 100 else None
if over:
    okb, why = E.panel_approve(None, "all", at=p["at"], stakes={A["id"]: min(100, bud), B["id"]: min(100, bud)})
    ok(f"Approve over the panel budget: nothing approved ({why})", not okb and "budget" in why
       and E.panel_get("real")["status"] == "draft")
oka, why = E.panel_approve(None, "all", at=p["at"], stakes={A["id"]: 3.33, "not-on-the-panel": 50})
cur = {c["id"]: c for c in E.panel_get("real")["items"]}
ok(f"Approve with his amount: approved, his stake kept, the panel's beside it ({why})",
   oka and cur[A["id"]]["stake"] == 3.33 and cur[A["id"]]["own"] is True and cur[A["id"]]["rec_stake"] == rec_a
   and cur[B["id"]]["stake"] == items[B["id"]]["stake"] and "own" not in cur[B["id"]])
st = E.panel_get("real")["stats"]
ok(f"the card's numbers follow his amount ({st.get('stake')})", abs(st["stake"] - (3.33 + items[B["id"]]["stake"])) < 0.01)
E.panel_exec()
got = {t: n for t, n, _ in BOUGHT}
ok(f"the buy uses his amount: {got.get('A1')} contracts for $3.33 at 50c (fee counted), once",
   got.get("A1") == int(3.33 // (0.5 + E.single_fee(0.5))) and sum(1 for t, _, _ in BOUGHT if t == "A1") == 1)
E.panel_exec()
ok("a second pass buys nothing more (claim-before-buy unchanged)", sum(1 for t, _, _ in BOUGHT if t == "A1") == 1)

# ---- (5) Add (extras) with his amount, counted against the same budget
Xc = mk("X1", "KXNBAGAME-X", .62, .50, now + 9000)
E.PANEL_POOL["nba"] = (time.time(), [A, B, Xc])
E.panel_pass()
ex = E.panel_extras()
xid = next((c["id"] for c in (ex or {}).get("items", []) if c["id"] == Xc["id"]), None)
ok("an extra to add", xid)
if xid:
    okx, why = E.panel_add([xid], "extra", stakes={xid: "-4"})
    ok(f"Add refuses a negative amount: nothing added ({why})", not okx and not any(c["id"] == xid for c in E.panel_get("real")["items"]))
    okx, why = E.panel_add([xid], "extra", stakes={xid: 2.75})
    row = next((c for c in E.panel_get("real")["items"] if c["id"] == xid), {})
    ok(f"Add with his amount: added at $2.75 ({why})", okx and row.get("stake") == 2.75 and row.get("own") is True)
    left = bud - sum(c["stake"] for c in E.panel_get("real")["items"] if c.get("state") in E.PANEL_LIVE)
    ok("...and the budget still holds", left >= -0.01)

