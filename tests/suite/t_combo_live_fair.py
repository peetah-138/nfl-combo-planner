# CHECK: group=engine
# Issue #358: a combo with a game under way is priced on its LIVE fair chance, never the pre-game one against a live
# price (the "131% of fair" quote). combo_live_fair's guards (spread, decided, disagree, no live chance, spreads/totals,
# never raises), get_offer on the live chance (green allowed only when every live guard, the bar and the in-play exit
# test pass; no fair price = never green, nothing stored), the 130% suspect cap (Build and the panel, stricter only), and
# the quote's new keys (bar, fair, why). Fakes only: no network, temp files, a temp history; nothing is bought.
import os, math, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)


def safe(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


E.started = lambda l: bool(l.get("_started"))
BOOK = {}
E.book_depth = lambda t, max_age=60: BOOK.get(t)
LIVE = {}
E.live_side_fair = lambda x, now=None, refresh=True: LIVE.get(x["ticker"], (None, None, "no fresh score"))
A = {"ticker": "KXNBAGAME-X1-A", "event": "KXNBAGAME-X1", "fair": 0.70, "p": 0.40, "pick": "Alpha", "_started": True}
B = {"ticker": "KXNBAGAME-X2-B", "event": "KXNBAGAME-X2", "fair": 0.60, "p": 0.55, "pick": "Beta"}


def t_guards():
    BOOK.clear(); LIVE.clear()
    legs, why = E.combo_live_fair([A, B])
    ok(f"no live book = no fair price, said plainly ({why})", legs is None and "Alpha" in why)
    BOOK[A["ticker"]] = {"ask": 0.42, "bid": 0.30}
    legs, why = E.combo_live_fair([A, B])
    ok(f"a jumpy live price (12c wide) = no fair price ({why})", legs is None and "jumpy" in why)
    BOOK[A["ticker"]] = {"ask": 0.42, "bid": 0.40}
    legs, why = E.combo_live_fair([A, B])
    ok(f"no live chance = no fair price ({why})", legs is None and "no live chance" in why)
    LIVE[A["ticker"]] = (0.97, "model", None)
    ok("a nearly decided game = no fair price", "nearly decided" in (E.combo_live_fair([A, B])[1] or ""))
    LIVE[A["ticker"]] = (0.60, "model", None)
    ok("Kalshi's mid 19c from the live chance = no fair price", "disagree" in (E.combo_live_fair([A, B])[1] or ""))
    LIVE[A["ticker"]] = (0.43, "line", None)
    legs, why = E.combo_live_fair([A, B])
    ok(f"good live state: the started pick gets its live chance and live ask, the other keeps its own ({legs})",
       why is None and legs[0]["fair"] == 0.43 and legs[0]["p"] == 0.42 and legs[0]["live"] and legs[1] is B)
    ok("the pre-game chance is never kept for a started pick", legs[0]["fair"] != A["fair"])
    sp = dict(A, ticker="KXNBASPREAD-X1-A5")
    ok("a spread under way = no fair price", E.combo_live_fair([sp])[0] is None)
    E_bd = E.book_depth
    E.book_depth = lambda *a, **k: 1 / 0
    ok("an error = no fair price, never raises", E.combo_live_fair([A])[0] is None)
    E.book_depth = E_bd
    ok("nothing started = the legs as they were", E.combo_live_fair([B]) == ([B], None))


PRICE = [0.25]
STORED = []


def setup(kind="own", legs=None):
    legs = legs or [dict(A), dict(B)]
    fair = 5 / math.prod(l["fair"] for l in legs)
    E.CTX.clear()
    E.CTX.update(stake=5.0, offers={}, combos=[{"kind": kind, "legs": legs, "fair": fair, "min": fair * 0.95}])
    E.CFG.update(budget=500.0, accept_pct=95)
    E.kalshi_send = lambda m, p, body=None, params=None: ({"market_ticker": "M"} if p.startswith("/multivariate") else
                                                         {"id": "r"} if p == "/communications/rfqs" else
                                                         {"quotes": [{"status": "open", "no_bid_dollars": f"{1 - PRICE[0]:.4f}",
                                                                      "id": "q"}]} if p == "/communications/quotes" else {})
    E.find_collection = lambda legs: "C"
    E.clear_my_rfqs = lambda m: None
    E.rfq_unsure = lambda *a, **k: False
    E.hold_refusal = lambda *a, **k: (None, "")
    E.time.sleep = lambda s: None
    E.carry_note = E.note_quote_time = E.note_buy_ratio = lambda *a, **k: None
    E.store_quote = lambda c, stake, pays, pct: STORED.append((c["fair"], pct))
    E.green_bar = lambda legs: 1.0


def t_offer():
    EXIT = [True]
    E.inplay_exit_ok = lambda c, sim=None, now=None, source=None: (EXIT[0], None if EXIT[0] else "no way out")
    E._sb_sim = lambda c, now: {}
    BOOK.clear(); LIVE.clear(); STORED.clear()
    setup()
    PRICE[0] = 0.42 / 1.31                            # the screenshot: 131% of the PRE-GAME fair (0.70 x 0.60)
    r = E.get_offer(1, 5.0, check_cap=False)
    ok(f"no live chance for the started pick: not green, no %, nothing stored ({r.get('why')}, {r.get('pct')})",
       r["ok"] is False and r["pct"] is None and r["fair"] is None and r["why"] == "nofair" and r["nofair"] and not STORED
       and E.CTX["offers"][1]["p"] is None and r["live"])
    BOOK[A["ticker"]] = {"ask": 0.42, "bid": 0.40}
    LIVE[A["ticker"]] = (0.43, "line", None)          # live chance: 0.43 * 0.60 = 0.258
    PRICE[0] = 0.258 / 1.05                           # 105% of the LIVE fair
    r = E.get_offer(1, 5.0, check_cap=False)
    ok(f"a good live recommendation stays allowed: 105% of the live fair is green ({r.get('pct'):.3f}, {r.get('why')})",
       r["ok"] is True and abs(r["pct"] - 1.05) < 0.01 and abs(r["fair"] - 5 / 0.258) < 0.01 and r["bar"] == 100)
    ok("the quote log and the take-profit get the live fair, not the pre-game one",
       abs(STORED[-1][0] - 5 / 0.258) < 0.01 and abs(E.CTX["offers"][1]["p"] - 0.258) < 0.001)
    EXIT[0] = False
    r = E.get_offer(1, 5.0, check_cap=False)
    ok(f"...but not when the in-play exit test says no ({r.get('why')})", r["ok"] is False and r["why"] == "inplay")
    EXIT[0] = True
    PRICE[0] = 0.258 / 0.97
    r = E.get_offer(1, 5.0, check_cap=False)
    ok(f"under the bar on the live chance: not green, said why ({r.get('why')})", r["ok"] is False and r["why"] == "under")
    PRICE[0] = 0.258 / 1.40
    r = E.get_offer(1, 5.0, check_cap=False)
    ok(f"140% of the live fair is held back as suspect ({r.get('why')})", r["ok"] is False and r["why"] == "suspect")
    # before the start: unchanged except the cap
    STORED.clear()
    pre = [dict(A, _started=False), dict(B)]
    setup(legs=pre)
    PRICE[0] = 0.42 / 1.10
    r = E.get_offer(1, 5.0, check_cap=False)
    ok(f"pre-game 110% of fair: green as before, on the board's fair ({r.get('pct'):.2f})",
       r["ok"] is True and not r["live"] and abs(r["fair"] - 5 / 0.42) < 0.01)
    PRICE[0] = 0.42 / 1.31
    r = E.get_offer(1, 5.0, check_cap=False)
    ok("pre-game 131% of fair: held back as suspect (a wrong chance, not a gift)", r["ok"] is False and r["why"] == "suspect")
    setup(kind="panel", legs=pre)
    r = E.get_offer(1, 5.0, check_cap=False)
    ok("the panel's combo at 131%: never bought either (stricter only)", r["ok"] is False and r["why"] == "suspect")
    PRICE[0] = 0.42 / 1.10
    r = E.get_offer(1, 5.0, check_cap=False)
    ok(f"the panel's combo at 110%: still bought on its own cut-off ({r.get('bar')})", r["ok"] is True and r["bar"] is None)
    setup(kind="panel", legs=[dict(A), dict(B)])
    BOOK.clear()
    r = E.get_offer(1, 5.0, check_cap=False)
    ok("the panel's combo is not re-priced here (it's priced live by live_recheck before its buy)", r["fair"] == 5 / 0.42)


def t_source():
    src = open("wtest/combo_watcher.py", encoding="utf-8").read()
    blk = src[src.index("def combo_offer"):src.index("REPRICE_AT = {}")]
    ok("combo_offer: no recommended size when it isn't green or the expected value isn't positive",
       'if not r.get("ok") or r.get("ev") is None or r["ev"] <= 0:' in blk and 'r["small"]' in blk)
    ok("combo_offer: expected value on the fair the quote used", 'r.get("fair", c.get("fair"))' in blk)


for n, fn in (("guards", t_guards), ("offer", t_offer), ("source", t_source)):
    safe(n, fn)
