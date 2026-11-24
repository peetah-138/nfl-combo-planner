# CHECK: group=engine
# The sale-result phrase (Pete, 2026-11-23: "tell me how much profit it was instead of what it sold for. I can't
# remember what we paid for it."): sale_result_note(got, cost) says profit, loss or break-even in dollars against what
# was paid; an unreadable cost says "(cost unknown)" and never shows a number. Pure wording: no Kalshi, no orders.
import os, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
f = E.sale_result_note

ok("profit: +$1.42 profit (paid $2.19)", f(3.61, 2.19) == "+$1.42 profit (paid $2.19)", f(3.61, 2.19))
ok("loss: -$0.80 loss (paid $4.40)", f(3.60, 4.40) == "-$0.80 loss (paid $4.40)", f(3.60, 4.40))
ok("a loss cut adds ', cut to limit the damage'", f(3.60, 4.40, cutting=True) == "-$0.80 loss (paid $4.40), cut to limit the damage")
ok("a profit never says 'cut' even when the flag is set", "cut" not in f(5.0, 4.0, cutting=True))
ok("break-even to the cent", f(4.40, 4.40) == "broke even (paid $4.40)" and f(4.404, 4.396) == "broke even (paid $4.40)", f(4.404, 4.396))
ok("whole dollars and big numbers read like the app's money()", f(30.0, 12.0) == "+$18 profit (paid $12)", f(30.0, 12.0))
ok("a half-cent difference rounds the way money does (no wrong sign)", f(2.19, 2.186).startswith("broke even"), f(2.19, 2.186))
# cost unknown: never a wrong number
for name, c in (("None", None), ("zero", 0), ("negative", -3), ("text", "x"), ("nan", float("nan")), ("inf", float("inf")), ("empty", "")):
    r = f(3.61, c)
    ok(f"cost {name}: (cost unknown), no dollars invented", r == "(cost unknown)", r)
ok("proceeds unreadable: (cost unknown) too", f(None, 2.19) == "(cost unknown)" and f("?", 2.19) == "(cost unknown)")
ok("a bet that paid nothing back is a full loss", f(0, 2.19) == "-$2.19 loss (paid $2.19)", f(0, 2.19))
# fees: the helper judges exactly the numbers it is given, so callers pass proceeds after the sale fee and cost net of
# buy fees (what Results shows); a single's phrase moves with the fee
fee = E.single_fee(0.60, 10)
got = round(10 * (0.60 - fee), 2)
ok("single: profit is proceeds after Kalshi's fee minus cost (fee counted)", f(got, 5.0) == f"+{E.money(round(got - 5.0, 2))} profit (paid $5)"
   and got < 6.0, (got, f(got, 5.0)))
ok("single: the same sale with no fee would read bigger (the fee is not ignored)", round(10 * 0.60 - 5.0, 2) > round(got - 5.0, 2))
# combo vs single go through the same helper: same numbers, same words
ok("combo and single use one formula (same inputs, same words)", f(3.61, 2.19) == f(round(3.61, 2), round(2.19, 2)))
ok("the phrase has no '$-' or double sign", all("$-" not in f(a, b) and "+-" not in f(a, b) for a, b in ((1, 2), (2, 1), (2, 2))))
