# CHECK: group=engine
# Auto-hedge gets guards (issue #27): it only buys the other side of a combo's last game while that game is in play on
# a fresh score, not at a break, when it locks in at least what the combo cost, after the same reading held on 3+
# checks over 3+ minutes, and on a price re-read from the order book right before buying. A hedge with an unknown
# outcome is marked "check" and never retried. No real orders: every trading call is faked here.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl"); E.HEDGES = os.path.join(E.HERE, "hedges.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
_real_time = time.time
now = time.time()
T = "KXNBAGAME-26NOV19LALBOS-LAL"
T2 = "KXNBAGAME-26NOV19LALBOS-BOS"
E.CFG.update(auto_sell=True, auto_hedge=True, prefer_hedge=True, hedge_cap=100, stop_loss=False, smart_sell=True,
             ride=2, take_profit=0, lock_trail=False, auto_cap=5)
E.MINE["all_games"] = {"g": [{"ticker": T, "pick": "Lakers", "p": 0.7}, {"ticker": T2, "pick": "Celtics", "p": 0.3}]}
h = {"label": "Combo 1", "need": [(("yes", T), "Lakers")], "pre_of": {T: 0.6}, "ch_of": {T: 0.7},
     "legs_left": [(0.7, True, 0)], "cost": 10, "p": 0.7, "pays": 20, "won_some": True, "left": 1}

# ---- the sums: 20 Celtics at 30c cost $6.30 with the fee and lock in $13.70; a fresh price replaces the board's
E.MINE["hold"] = {"C1": dict(h)}
hg = E.hedge_for("C1")
ok("hedge_for: 20 of the other side at the board price", hg and hg["ticker"] == T2 and hg["n"] == 20 and abs(hg["locked"] - 13.7) < 1e-9)
ok("hedge_for: a fresh price replaces the board's", abs(E.hedge_for("C1", price=0.5)["cost"] - 10.35) < 1e-9)

# ---- fakes: score feed, cash-out, account, order book, Kalshi
SC = {"sc": None}
E.leg_score = lambda l: SC["sc"]
E.SCORES_BY["nba"] = {"at": now, "by": {}}
live = {"state": "in", "frac": 0.3, "detail": "Q4 6:00", "brk": False}
BOOK = {"b": {"bid": 0.29, "ask": 0.3, "spread": 0.01}}
books_read = []
E.book_depth = lambda tk, max_age=60: (books_read.append((tk, max_age)), BOOK["b"])[1]
sent, sold, logs = [], [], []
SEND = {"f": lambda m, p, b: {"fill_count": b["count"]}}
E.kalshi_send = lambda m, p, b=None, params=None: (sent.append((p, b)), SEND["f"](m, p, b))[1]
E.can_trade = lambda: True
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 5.0)
E.get_cash_offer = lambda t, f=1.0: {"offer": 13.0, "frac": 1.0, "rfq": "x", "contracts": 20, "at": E.time.time()}
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], None)
E.sold_today = lambda: 0
E.smart_sell_singles = lambda: []
E.accept_cash = lambda t, floor=None: (sold.append(t), "✅ sold")[1]
E.drop_cash = lambda t: E.MINE["cash"].pop(t, None)
E.haptic = lambda *a: None
real_log = E.log_decision
E.log_decision = lambda rec: (logs.append(rec), real_log(rec))
E.MINE["busy"] = False; E.MINE.setdefault("selling", set()); E.MINE["cash"] = {}
plan = {"acts": {}}


def tick(dt_, sc, **hx):
    SC["sc"] = sc
    E.time.time = lambda: now + dt_
    E.SCORES_BY["nba"]["at"] = now + dt_
    E.MINE["hold"] = {"C1": dict(h, **hx)}
    E.MINE["tp_asked"] = {}; E.MINE["cash"] = {}
    return E.auto_sell_now(plan)


def reset():
    sent.clear(); sold.clear(); logs.clear(); books_read.clear()
    E.MINE["sl_streak"] = {}; E.MINE["cut_told"] = {}
    E.save_json(E.HEDGES, {})


def held(guard):
    return any(r.get("result") == "held" and r.get("hedge") and r.get("guard") == guard for r in logs)


# ---- (1) a fresh score is required
reset()
tick(0, live)
tick(100, None)
ok("no score feed: no hedge (it cashes out as if auto-hedge were off)", not sent and sold == ["C1"] and held("no score feed"))
reset()
SC["sc"] = live; E.time.time = lambda: now + 500; E.SCORES_BY["nba"]["at"] = now + 300
E.MINE["hold"] = {"C1": dict(h)}; E.MINE["tp_asked"] = {}
E.auto_sell_now(plan)
ok("a stale score: no hedge", not sent and held("score feed stale"))
ok("...and the count starts again", "hedge:C1" not in E.MINE["sl_streak"])
reset()
tick(0, dict(live, state="post", detail="Final"))
ok("the game isn't in play (over): no hedge", not sent and held("game not under way"))

# ---- (2) not at a break
reset()
tick(0, dict(live, detail="Half", brk=True))
ok("halftime: no hedge", not sent and held("halftime or a break"))
reset()
tick(0, dict(live, detail="End of 3rd"))
ok("end of a period: no hedge", not sent and held("halftime or a break"))

# ---- (4) locks in at least what the combo cost
reset()
E.get_cash_offer = lambda t, f=1.0: {"offer": 14.2, "frac": 1.0, "rfq": "x", "contracts": 20, "at": E.time.time()}
tick(0, live, cost=13.8)   # (#382: the cash-out nets $13.91 after Kalshi's fee, so it still clears the $13.80 cost floor)
E.get_cash_offer = lambda t, f=1.0: {"offer": 13.0, "frac": 1.0, "rfq": "x", "contracts": 20, "at": E.time.time()}
ok("locks in $13.70 on a $13.80 combo (offer $14.20): no hedge, it cashes out", not sent and sold == ["C1"] and held("wouldn't lock in what you paid"))

# ---- (5) confirmed over 3 checks spanning 3+ minutes; the sale waits meanwhile
reset()
tick(0, live); tick(90, live)
ok("one or two readings never hedge, and the sale waits meanwhile", not sent and not sold)
ok("waiting isn't logged as held back", not any(r.get("result") == "held" for r in logs))
tick(150, live)
ok("3 checks but under 3 minutes: not yet", not sent and not sold)
out = tick(240, live)
ok("3+ checks over 3+ minutes: it hedges", len(sent) == 1 and not sold and out and "Auto-hedge" in out[0])
ok("(3) the order book was re-read right before buying (fresh, max_age=0)", (T2, 0) in books_read)
ok("...and the order uses the fresh ask", sent and sent[0][1]["price"] == "0.3000" and sent[0][1]["ticker"] == T2)
ok("logged as hedged", any(r.get("result") == "hedged" for r in logs))
reset()
tick(0, live); tick(100, live); tick(200, dict(live, detail="Half", brk=True)); tick(300, live); tick(400, live)
ok("a break mid-count starts it again", not sent)
tick(500, live)
ok("...then 3 more good checks over 3+ minutes hedge", len(sent) == 1)
reset()
tick(0, live); tick(100, live); tick(450, live)
ok("checks more than 5 minutes apart don't count together", not sent)

# ---- (3) the sums redone on the fresh price
reset()
BOOK["b"] = {"bid": 0.48, "ask": 0.5, "spread": 0.02}
for k in range(3):
    tick(k * 100, live)
ok("the fresh price no longer beats the cash-out: no hedge, it cashes out", not sent and sold == ["C1"]
   and held("no longer beats the cash-out at the fresh price"))
reset()
BOOK["b"] = {"bid": 0.2, "ask": 0.3, "spread": 0.1}
for k in range(3):
    tick(k * 100, live)
ok("a thin hedge-side book: no hedge", not sent and held("hedge side's order book too thin"))
reset()
BOOK["b"] = None
for k in range(3):
    tick(k * 100, live)
ok("no order book: no hedge", not sent and held("no fresh price for the hedge"))
reset()
BOOK["b"] = {"bid": 0.33, "ask": 0.34, "spread": 0.01}      # locks in $12.88: still beats 95% of $13.50
E.get_cash_offer = lambda t, f=1.0: {"offer": 13.5, "frac": 1.0, "rfq": "x", "contracts": 20, "at": E.time.time()}
for k in range(3):
    tick(k * 100, live, cost=13.1)   # (#382: the $13.50 offer nets $13.19 after the fee: above this cost)
ok("the fresh price locks in less than the cost: no hedge", not sent and held("wouldn't lock in what you paid at the fresh price"))
E.get_cash_offer = lambda t, f=1.0: {"offer": 13.0, "frac": 1.0, "rfq": "x", "contracts": 20, "at": E.time.time()}
BOOK["b"] = {"bid": 0.29, "ask": 0.3, "spread": 0.01}

# ---- the $100 cap, Pause, the switch
reset()
E.CFG["hedge_cap"] = 5
for k in range(3):
    tick(k * 100, live)
ok("over the cap: no hedge, cashes out", not sent and set(sold) == {"C1"} and any("over the" in (r.get("hedge_skipped") or "") for r in logs))
E.CFG["hedge_cap"] = 100
reset()
E.CFG["auto_sell"] = False                                 # what Pause does
for k in range(4):
    tick(k * 100, live)
ok("paused (auto cash-out off): no hedge, no sale", not sent and not sold)
E.CFG["auto_sell"] = True
reset()
E.CFG["auto_hedge"] = False
tick(0, live)
ok("auto-hedge off: cashes out straight away, as before", not sent and sold == ["C1"])
E.CFG["auto_hedge"] = True

# ---- rule 8: an unknown outcome is marked "check" and never retried
reset()


def boom(m, p, b):
    raise E._requests.Timeout("no answer")


SEND["f"] = boom
outs = []
for k in range(3):
    outs += tick(k * 100, live)
ok("a hedge that may or may not have gone through is marked 'check'", E.hedge_unsure("C1") and len(sent) == 1)
ok("...with no sale on top, and a plain message", not sold and any("Check Kalshi" in m for m in outs)
   and any(r.get("result") == "hedge check" for r in logs))
for k in range(3, 9):
    tick(k * 100, live)
ok("...never retried (and auto cash-out leaves that combo alone)", len(sent) == 1 and not sold)
reset()
SEND["f"] = lambda m, p, b: (_ for _ in ()).throw(RuntimeError("Kalshi said: market closed (400)"))
for k in range(3):
    tick(k * 100, live)
ok("a clear refusal (400) isn't 'check': it cashes out as before", not E.hedge_unsure("C1") and sold == ["C1"]
   and any(r.get("result") == "hedge failed" for r in logs))
SEND["f"] = lambda m, p, b: {"fill_count": b["count"]}
ok("unknown: a timeout, a lost Mac, a server error", E.hedge_unknown(TimeoutError()) and
   E.hedge_unknown(RuntimeError("Lost contact with your Mac during this trade, so it may or may not have gone through."))
   and E.hedge_unknown(RuntimeError("Kalshi said: oops (502)")))
ok("known: a refusal, no write access, the backup-key prompt", not E.hedge_unknown(RuntimeError("Kalshi said: no (400)"))
   and not E.hedge_unknown(PermissionError("x")) and not E.hedge_unknown(RuntimeError("Your Mac isn't answering (x). Tap again within 2 minutes to place this with your phone's backup key.")))

# ---- the manual Hedge tap is unchanged: it uses the board price, no guards (Pete's own tap)
reset()
E.MINE["hold"] = {"C1": dict(h)}
m = E.place_hedge("C1")
ok("a tapped hedge still buys at the board price", m.startswith("✅") and sent and sent[0][1]["price"] == "0.3000")

# ---- Results › Selling counts the hedges the guards held back, apart from the loss cuts
E.time.time = _real_time
reset()
E.SELL_LOG = os.path.join(E.HERE, "sells2.jsonl")
for g in ("score feed stale", "halftime or a break"):
    E.note_cut_held("C9", "Combo 9", "smart", g, hedge=True)
E.note_cut_held("C9", "Combo 9", "cut loss", "too early in the game")
a = E.analytics(max_age=0)
ok("Results › Selling: hedges held back, by reason", (a.get("hedge_held") or {}).get("score feed stale") == 1
   and (a.get("hedge_held") or {}).get("halftime or a break") == 1)
ok("...not mixed in with the loss cuts", "score feed stale" not in (a.get("cut_held") or {})
   and (a.get("cut_held") or {}).get("too early in the game") == 1)
