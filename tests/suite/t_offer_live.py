"""The display-only live-priced estimate (Refs #80): the Live hero's "worth now if sold" number made to
follow the live Kalshi leg prices instead of the frozen Monte-Carlo chance. `live_offer_est` is pure
(no network, no account); nothing here changes what is bought or sold. It also statically asserts that no
trading/selling/panel path reads the new `offer_live` field — those must stay on
kalshi_discount(live)*h["p"]*h["pays"] and MINE["cash"]."""
import os, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))

# Pin the discount so the maths is deterministic (kalshi_discount reads a learned file; force the defaults).
E.DISCOUNT_FILE = os.path.abspath("wahome/_no_such_discount.json")   # <5 samples -> 0.88 pre, 0.82 live
PRE, LIVE = 0.88, 0.82
assert abs(E.kalshi_discount(False) - PRE) < 1e-9 and abs(E.kalshi_discount(True) - LIVE) < 1e-9


def leg(res=None, live=None):
    return {"res": res, "live": live}


def view(legs, pays=10.0, live=False, rough=False):
    return {"pays": pays, "live": live, "legs": legs}, {"rough": rough}


def close(a, b):
    return a is not None and b is not None and abs(a - b) < 0.011


# 1. Two open live legs, cross-game: product of the two live prices times the discount times pays.
v, h = view([leg(live=0.8), leg(live=0.5)], pays=10.0, live=True)
ok("two live legs -> product", close(E.live_offer_est(h, v), LIVE * 0.8 * 0.5 * 10.0), E.live_offer_est(h, v))

# 2. A won leg counts as 1 (does not drag the product down).
v, h = view([leg(res="yes"), leg(live=0.5)], pays=10.0, live=True)
ok("won leg counts as 1", close(E.live_offer_est(h, v), LIVE * 1.0 * 0.5 * 10.0), E.live_offer_est(h, v))

# 3. A NO-side leg: the engine already stores 1-p in `live`, so we just multiply it as given.
v, h = view([leg(live=0.3), leg(live=0.9)], pays=10.0, live=True)   # 0.3 might be a NO leg's 1-p; treated the same
ok("no-side leg uses stored live", close(E.live_offer_est(h, v), LIVE * 0.3 * 0.9 * 10.0))

# 4. A missing live price on an open leg -> fall back (None), so the hero keeps the old frozen number.
v, h = view([leg(live=0.8), leg(live=None)], pays=10.0, live=True)
ok("missing live falls back to None", E.live_offer_est(h, v) is None)

# 5. A lost leg forces the whole thing to 0 (matches the frozen estimate: p is 0 once a leg is lost).
v, h = view([leg(res="no"), leg(live=0.9)], pays=10.0, live=True)
ok("lost leg -> 0", E.live_offer_est(h, v) == 0.0)

# 6. Same-game ("rough") combos fall back: their legs are correlated and can't be multiplied independently.
v, h = view([leg(live=0.8), leg(live=0.8)], pays=10.0, live=True, rough=True)
ok("rough combo falls back to None", E.live_offer_est(h, v) is None)

# 7. Never above pays (even with absurd inputs it is clamped to the payout).
v, h = view([leg(live=1.0), leg(res="yes")], pays=10.0, live=True)
r = E.live_offer_est(h, v)
ok("never above pays", r is not None and r <= 10.0 + 1e-9, r)

# 8. Never negative.
v, h = view([leg(live=0.0), leg(live=0.5)], pays=10.0, live=True)
r = E.live_offer_est(h, v)
ok("never negative", r is not None and r >= 0.0, r)

# 9. Pre-game discount used when the combo is not live.
v, h = view([leg(live=0.8), leg(live=0.5)], pays=10.0, live=False)
ok("pre-game discount when not live", close(E.live_offer_est(h, v), PRE * 0.8 * 0.5 * 10.0))

# 10. Robustness: a garbage view never raises, it returns None.
ok("garbage view -> None, never raises", E.live_offer_est({}, {"pays": "x", "legs": None}) is None)
ok("missing hold -> None", E.live_offer_est(None, {"pays": 10.0, "legs": [leg(live=0.5)]}) is None)

# 11. All legs won (nothing open) -> discount * 1 * pays, still <= pays.
v, h = view([leg(res="yes"), leg(res="yes")], pays=10.0, live=False)
ok("all won -> discount*pays", close(E.live_offer_est(h, v), PRE * 10.0))

# ---- live_view actually wires offer_live into each view and into cash_now (the hero total),
# preferring it over the frozen `offer` when there is no fresh real quote, and falling back otherwise.
def fleg(res=None, live=None, tk="KXNBAGAME-X-BOS"):   # a full leg dict live_view's downstream loop needs
    return {"res": res, "live": live, "ticker": tk, "side": "yes", "name": "Celtics", "opp": "Knicks",
            "sport": "nba", "state": "live", "score": "", "sc": None, "starts": "", "phase": "", "note": "",
            "short": "", "chance": 0.6}


def run_live_view(legs, cash=None):
    t = "KXMVE-1"
    E.MINE["hold"] = {t: {"label": "Combo 1", "p": 0.22, "pays": 10.0, "cost": 5.0, "hold": 2.2,
                          "left": len(legs), "won_some": False}}
    E.MINE["cash"] = {t: cash} if cash else {}
    E.MINE["locked"] = 0
    v = {"t": t, "group": "pending", "p": 0.22, "pays": 10.0, "cost": 5.0, "live": True, "legs": legs}
    out = E.live_view([], [v], {}, 0.22, 100.0)
    return v, out


# No real quote: offer is the frozen estimate (discount*p*pays = .82*.22*10 = 1.804); offer_live is the
# live-priced one (.82*.8*.5*10 = 3.28). cash_now must follow offer_live, not offer.
v, out = run_live_view([fleg(live=0.8), fleg(live=0.5, tk='KXNBAGAME-Y-DEN')])
ok("live_view sets offer_live separately from offer",
   close(v.get("offer_live"), LIVE * 0.8 * 0.5 * 10.0) and close(v.get("offer"), LIVE * 0.22 * 10.0),
   f"offer_live={v.get('offer_live')} offer={v.get('offer')}")
ok("cash_now follows offer_live when no real quote", close(out["cash_now"], LIVE * 0.8 * 0.5 * 10.0), out["cash_now"])

# An open leg with no live price: offer_live is None, so cash_now falls back to the frozen offer.
v, out = run_live_view([fleg(live=0.8), fleg(live=None, tk='KXNBAGAME-Y-DEN')])
ok("offer_live None when a leg lacks live price", v.get("offer_live") is None)
ok("cash_now falls back to offer on a missing leg price", close(out["cash_now"], LIVE * 0.22 * 10.0), out["cash_now"])

# A fresh real quote wins: cash_now uses the real offer, never offer_live.
v, out = run_live_view([fleg(live=0.8), fleg(live=0.5, tk='KXNBAGAME-Y-DEN')],
                       cash={"rfq": "r", "quote": "q", "offer": 7.5, "price": .75, "contracts": 10, "frac": 1.0,
                             "at": __import__("time").time()})
ok("a real quote drives cash_now, not offer_live", close(out["cash_now"], 7.5), out["cash_now"])

# ---- Static guard: the trading/selling/panel paths must NOT read offer_live. They must keep reading
# MINE["cash"] and est = kalshi_discount(live)*h["p"]*h["pays"]. We scan each function's source text.
import inspect
TRADING = ["take_profit_reason", "auto_sell_now", "single_sell_reason", "smart_sell_singles",
           "plan_cashout", "accept_offer", "hedge_for", "place_hedge", "fresh_offer", "wait_threshold",
           "panel_exec", "panel_approve", "panel_add", "build_panel", "choose_panel", "panel_record",
           "hedge_guard", "hedge_fresh", "stop_loss_check", "cut_loss_single_check"]
bad = []
for name in TRADING:
    fn = getattr(E, name, None)
    if fn is None:
        bad.append(name + "(missing)")        # a renamed function must not silently drop out of the guard
        continue
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):
        bad.append(name + "(no source)")
        continue
    if "offer_live" in src:
        bad.append(name)
ok("no trading/selling function references offer_live", not bad, ",".join(bad))

# The watcher's estimate_offers (parallel estimate) must not reference offer_live either.
wpath = os.path.join(os.environ.get("REPO", "."), "watcher", "combo_watcher.py")
ok("watcher source found for the estimate_offers guard", os.path.exists(wpath), wpath)
wsrc = open(wpath).read() if os.path.exists(wpath) else ""
import re
m = re.search(r"\ndef estimate_offers\(.*?(?=\n(?:def |class )|\Z)", wsrc, re.S)
ok("watcher estimate_offers found", bool(m))
ok("watcher estimate_offers does not read offer_live", bool(m) and "offer_live" not in m.group(0))

# ---- review fixes: freshness, shared-game legs, offer-None row, pulse/hero agreement.
import time
E.MARKET_INFO["KXNBAGAME-A-BOS"] = {"live": 0.8, "at": time.time() - 600}
v, h = view([{"res": None, "live": 0.8, "ticker": "KXNBAGAME-A-BOS"}, leg(live=0.5)], live=True)
ok("a stale leg price (older than the build) -> None", E.live_offer_est(h, v) is None)
E.MARKET_INFO["KXNBAGAME-A-BOS"]["at"] = time.time()
ok("a just-fetched leg price is used", E.live_offer_est(h, v) is not None)
v, h = view([{"res": None, "live": 0.8, "ticker": "KXNBAGAME-26NOV19BOSNYK-BOS"},
             {"res": None, "live": 0.7, "ticker": "KXNBASPREAD-26NOV19BOSNYK-BOS5"}], live=True)
ok("two open legs in one game -> None (correlated)", E.live_offer_est(h, v) is None)
v, h = view([{"res": None, "live": 0.8, "ticker": "KXNBAGAME-26NOV19BOSNYK-BOS"},
             {"res": None, "live": 0.7, "ticker": "KXNBAGAME-26NOV19DENLAL-DEN"}], live=True)
ok("two open legs in different games are multiplied", E.live_offer_est(h, v) is not None)
ok("hero_worth: estimate preferred", E.hero_worth({"offer": 1.8, "offer_live": 3.3, "offer_real": False}) == 3.3)
ok("hero_worth: real quote wins", E.hero_worth({"offer": 7.5, "offer_live": 3.3, "offer_real": True}) == 7.5)
ok("hero_worth: no offer -> adds nothing", E.hero_worth({"offer": None, "offer_live": 3.3, "offer_real": False}) == 0)
ok("the pulse (chart) sum uses hero_worth, same as cash_now", "worth = sum(hero_worth(v) for v in pend)" in
   open(os.path.join(os.environ.get("REPO", "."), "nfl_combo_planner.py")).read())
