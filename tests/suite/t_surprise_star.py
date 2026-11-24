# CHECK: group=engine
"""Surprise me star filter: a combo with a pick under way never carries the star ("★ Value pick") or the guess
"Likely about X% of fair" (that guess comes from past pre-game Kalshi prices). Fixed where the label is assigned
(value_label in value_combos, combo_star for Build's saved list), not only in the page."""
import os, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))

LIVE = set()
E.started = lambda x: x.get("ticker") in LIVE


def side(ev, team, p, fair):
    return {"ticker": f"{ev}-{team}", "event": ev, "pick": team, "p": p, "fair": fair, "src": "pinnacle"}


games = {f"EV{i}": [side(f"EV{i}", f"T{i}", 0.40, 0.50 + i * .01)] for i in range(5)}

# 1. pre-game: starred as before
v = E.value_combos(games, 5, k=3)
ok("pre-game combos are value picks", v and all(c["kind"] == "value" and c["tier"] == "Value" for c in v))

# 2. one leg under way (allowed through live_ok): no star on any combo that holds it
LIVE.add("EV0-T0")
v = E.value_combos(games, 5, k=8, live_ok={"EV0"})
withlive = [c for c in v if any(l["ticker"] == "EV0-T0" for l in c["legs"])]
without = [c for c in v if all(l["ticker"] != "EV0-T0" for l in c["legs"])]
ok("there are combos with the live leg", len(withlive) > 0)
ok("a combo with a live leg is not starred", all(c["kind"] != "value" and c["tier"] == "Live pick" for c in withlive))
ok("combos with no live leg keep the star", all(c["kind"] == "value" for c in without))
ok("per_n extras follow the same rule", all(c["kind"] != "value" for c in E.value_combos(games, 5, k=2, live_ok={"EV0"}, per_n=2)
                                           if c.get("extra") and any(l["ticker"] == "EV0-T0" for l in c["legs"])))

# 3. combo_star: a saved starred combo loses the star once a leg starts
saved = {"kind": "value", "tier": "Value", "legs": [side("EV1", "T1", .4, .5), side("EV2", "T2", .4, .5)]}
ok("pre-game saved combo keeps its star", E.combo_star(saved) == ("value", "Value", False))
LIVE.add("EV2-T2")
ok("same combo once a leg is live: no star", E.combo_star(saved) == ("mix", "Live pick", True), E.combo_star(saved))
ok("a non-star combo keeps its own kind/tier", E.combo_star({"kind": "safer", "tier": "Safer", "legs": saved["legs"]}) == ("safer", "Safer", True))
ok("never raises on junk", E.combo_star({}) [2] is False and E.combo_star({"legs": None})[2] is False)

# 4. the watcher view: no guess for a live combo (source check, the view is a closure inside webapp_main)
src = open("wtest/combo_watcher.py").read()
i = src.index("def combo_view(")
body = src[i:i + 900]
ok("combo_view uses combo_star and drops est/pred when live", "A.combo_star(c)" in body and "None if live else A.predict_quote" in body and "if live else A.est_offer" in body)
