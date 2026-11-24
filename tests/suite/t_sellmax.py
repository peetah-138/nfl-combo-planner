# CHECK: group=engine
# Issue #371 (Pete): Live said "sells at $14+" on a bet that pays $13. A bet can never sell for more than it pays, so
# a sell line above that is a nonsense number on the screen and a rule that silently never fires.
#  A  the singles chip: smart sell's hold line (profit floor x cost) for a single bought at 70c is above the payout;
#     open_singles now shows no number and flags it (sell_over) instead; a reachable line is shown exactly as before
#  B  combos: wait_threshold's room for error (x1 + 2% a pick) goes over the payout when the picks left are near
#     certain; live_view, plan_words and the Pythonista card's text never show it
#  C  the ceiling: Kalshi's 99c top price (a single's after the fee); edge cases
#  D  display only: no sell decision reads the new helpers (the deciders compare with the unclamped line, as before)
import os, tempfile, importlib.util, inspect, re, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json"); E.SELF_SELL = os.path.join(E.HERE, "selfsell.json")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
E.CFG.update(auto_sell=True, smart_sell=True, ride=2, take_profit=0, lock_trail=True, bankroll=500)
E.leg_score = lambda l: None
T = "KXNBAGAME-26NOV23LALBOS-LAL"
C = "KXMVECROSSCATEGORY-S2026ABC-123"


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def single(n=13, cost=9.10, chance=0.8, side="yes"):
    return {"t": T, "n": n, "cost": cost, "chance": chance, "state": "live", "kind": "win", "side": side,
            "sport": "nba", "label": "Lakers"}


def a_singles():
    x = single()                                    # Pete's bet: 13 contracts at 70c, pays $13
    why, fl = E.single_sell_reason(x, 0.82, 0.84, track=False)
    ok("A repro: the old chip line was above the $13 payout (shown as $14+)", why is None and fl > 13 and round(fl) == 14, fl)
    top = E.sell_top(13, single=True)
    shown, over = E.sell_line_shown(fl, top)
    ok("A the line above what it can sell for: no number, flagged", shown is None and over is True)
    for side in ("yes", "no"):
        why2, fl2 = E.single_sell_reason(single(side=side), 0.82, 0.84, track=False)
        ok(f"A {side} side: same answer", E.sell_line_shown(fl2, top) == (None, True))
    cheap = single(n=13, cost=5.20, chance=0.6)     # bought at 40c: its line is reachable and shown as before
    why3, fl3 = E.single_sell_reason(cheap, 0.55, 0.57, track=False)
    ok("A a reachable line is shown exactly as before", fl3 and fl3 < top and E.sell_line_shown(fl3, top) == (round(fl3, 2), False), fl3)
    src = inspect.getsource(E.open_singles)
    ok("A open_singles uses the reachable line for sell_at", "sell_line_shown(" in src and 'x["sell_over"]' in src)


def b_combos():
    h = {"label": "Combo 1", "need": [(("yes", T), "Lakers")], "legs_left": [(0.995, False, 0), (0.995, False, 0),
         (0.995, False, 0)], "cost": 6.0, "p": 0.985, "pays": 13.0, "won_some": True, "left": 1, "hold": 12.0,
         "worth": False}
    E.MINE["hold"] = {C: h}
    E.MINE["cash"] = {}
    thr = E.wait_threshold(C)
    ok("B repro: wait_threshold goes over the payout with near-certain picks left", thr > 13, thr)
    E.open_singles = lambda *a, **k: []
    v = {"t": C, "live": False, "p": 0.985, "pays": 13.0, "cost": 6.0, "group": "pending", "legs": []}
    E.live_view([], [v], None, 0.9, 100.0)
    ok("B live_view: no threshold above the payout, flagged instead", v.get("threshold") is None and v.get("thr_over") is True, v.get("threshold"))
    w = E.plan_words(C, 0, {"offer": 10.0, "frac": 1.0}, h, 500)
    ok("B plan_words never names a cash-out price above the payout", E.money(thr) not in w and "$13" in w, w)
    E.can_trade = lambda: True
    E.in_pythonista = lambda: False
    cb = E.cash_block(C, None)
    ok("B the card's auto cash-out line: no price over the payout, other rules still apply", "no offer can beat waiting" in cb and "other sell rules" in cb and E.money(thr) not in cb, cb)
    h2 = dict(h, legs_left=[(0.55, False, 0)], p=0.55)  # a long shot left: the line is reachable, shown as before
    E.MINE["hold"] = {C: h2}
    v2 = dict(v, p=0.55)
    E.live_view([], [v2], None, 0.5, 100.0)
    t2 = E.wait_threshold(C)
    ok("B a reachable combo line is shown exactly as before", t2 < 13 * 0.99 and v2["threshold"] == round(t2, 2) and v2["thr_over"] is False, (t2, v2.get("threshold")))
    cb2 = E.cash_block(C, None)
    ok("B the card names a reachable price as before", f"offers about ${round(t2, 2):,.2f} or more" in cb2, cb2)
    E.MINE["hold"] = {C: dict(h, won_some=False)}
    ok("B no pick won yet: unchanged wording", "waits until a pick" in E.cash_block(C, None))


def c_ceiling():
    ok("C combo ceiling: 99c a contract", abs(E.sell_top(13) - 12.87) < 1e-9)
    ok("C single ceiling: 99c less the fee", 12.85 < E.sell_top(13, single=True) < 12.87)
    ok("C no line: nothing shown, not flagged", E.sell_line_shown(0, 10) == (None, False) and E.sell_line_shown(None, 10) == (None, False))
    ok("C right at the ceiling: still shown", E.sell_line_shown(12.87, E.sell_top(13)) == (12.87, False))
    ok("C a cent over: flagged", E.sell_line_shown(12.88, E.sell_top(13)) == (None, True))
    ok("C no payout: any line flagged", E.sell_line_shown(1.0, E.sell_top(0)) == (None, True))


def d_display_only():
    deciders = [E.exit_policy, E.single_sell_reason, E.take_profit_reason, E.wait_threshold, E.wait_value,
                E.auto_sell_now, E.plan_cashout, E.tp_ladder, E.cash_nudge]
    used = [f.__name__ for f in deciders if re.search(r"\bsell_(top|line_shown)\(", inspect.getsource(f))]
    ok("D no sell decision reads the display helpers", not used, used)


section("A", a_singles)
section("B", b_combos)
section("C", c_ceiling)
section("D", d_display_only)
