# CHECK: group=engine
"""nomoney-g-144 (#187): the scoreboard tags Live idea buys apart from Build buys, and its sentence bar rises with the
number of groups tested (combos also need 30 settled bets). Labels and words only; nothing here buys or sells."""
import os, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
ok("source labels: Live buy ideas apart from Build and other app buys",
   E.BOARD_SRC.get("idea") == "Live buy ideas" and E.BOARD_SRC.get("app") == "Build and other app buys"
   and "idea" in list(E.BOARD_SRC))
ok("bar: two groups keep 2.5, ten groups need about 2.8", E._board_bar(2) == E.BOARD_Z and 2.7 < E._board_bar(10) < 2.9)


def row(k, n, z, roi=0.2):
    return {"k": k, "name": k.title(), "n": n, "z": z, "roi": roi, "few": n < E.BOARD_FEW}


say = E._board_say
ok("z 2.6 passes with two groups, not with ten", "keep it" in say([row("a", 40, 2.6), row("b", 40, 0.1)], "league")
   and "keep it" not in say([row(chr(97 + i), 40, 2.6 if i == 0 else 0.1) for i in range(10)], "league"))
ok("combos under 30 bets get no verdict, 30 do",
   "keep it" not in say([row("combo", 25, 3.5)], "bet type") and "keep it" in say([row("combo", 30, 3.5)], "bet type"))
ok("other bet types still judged at 20+", "keep it" in say([row("spread", 25, 3.5)], "bet type"))
src = open("wahome/engine.py", encoding="utf-8").read()
ok("Live idea buy marks its market as an idea buy before ordering",
   'mark_app(t, "idea")' in src and src.index('mark_app(t, "idea")') < src.index("filled, err = buy_single(t, n, price, coid=coid, exact=True)"))
