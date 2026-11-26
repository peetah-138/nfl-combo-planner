# CHECK: group=engine
"""Issue #520: a combo is named by its picks ("Nuggets + Chiefs +2"), not "Combo N". Display and log text only: the
market ticker is the id, the old number survives as a secondary field, and nothing trades differently."""
import os, importlib.util, datetime as dt
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))
E.store_open(os.path.abspath("wahome/t_combonames.db"))

ok("a pro team is its nickname", E.short_leg("Denver Nuggets", "nba") == "Nuggets", E.short_leg("Denver Nuggets", "nba"))
ok("...a two-word nickname stays whole", E.short_leg("Toronto Maple Leafs", "nhl") == "Maple Leafs")
ok("...a spread stays on it", E.short_leg("Kansas City Chiefs +2", "nfl") in ("Chiefs +2", "Kansas City Chiefs +2")
   and E.short_leg("Kansas City Chiefs +2", "nfl").endswith("+2"))
ok("...a college team keeps its full name", E.short_leg("Temple Owls", "ncaamb") == "Temple Owls")
ok("...a long player market is cut to 24 characters", len(E.short_leg("Patrick Mahomes over 275.5 passing yards", "nfl")) <= 24)

legs = [[("Nuggets", "nba"), ("Chiefs +2", "nfl")], [("A", "nfl"), ("B", "nfl"), ("C", "nfl"), ("D", "nfl"), ("E", "nfl")]]
n = E.combo_names(legs)
ok("two picks: 'Nuggets + Chiefs +2'", n[0] == "Nuggets + Chiefs +2", n)
ok("five picks: the first three and '+2 more'", n[1] == "A + B + C +2 more", n)
ok("the same pick twice in one combo is named once", E.combo_names([[("Jets", "nfl"), ("Jets", "nfl")]]) == ["Jets"])
d1, d2 = dt.datetime(2026, 11, 23, 13), dt.datetime(2026, 11, 29, 16)
same = E.combo_names([[("Nuggets", "nba")], [("Nuggets", "nba")], [("Nuggets", "nba")]], [d1, d2, d2])
ok("the same name on two kickoff days is told apart by the date", same[0] == "Nuggets (Nov 23)" and same[1] == "Nuggets (Nov 29)" and same[2] == "Nuggets (Nov 29) (2)", same)
ok("a name that is already unique carries no date", E.combo_names([[("Nuggets", "nba")]], [d1]) == ["Nuggets"])
ok("no legs at all still gives a name", E.combo_names([[]]) == ["Combo"])

# the autosell log: `combo` is the picks, the old number rides along as combo_id, picks are there
E.MINE["hold"] = {"KXMVE-X": {"label": "Nuggets + Chiefs +2", "num": "Combo 7"}}
E.MINE["snap"] = {"KXMVE-X": {"label": "Nuggets + Chiefs +2", "num": "Combo 7", "legs": {"a": ("Nuggets", None), "b": ("Chiefs +2", None)}}}
E.SELL_LOG = os.path.abspath("wahome/t_combonames_sell.jsonl")
try:
    os.remove(E.SELL_LOG)
except OSError:
    pass
E.log_decision({"combo": E.MINE["hold"]["KXMVE-X"]["label"], "ticker": "KXMVE-X", "result": "skipped", "why": "waiting: offer below the sell line"})
import json
rec = json.loads(open(E.SELL_LOG).read().splitlines()[-1])
ok("the log line names the combo by its picks", rec["combo"] == "Nuggets + Chiefs +2", rec)
ok("...keeps the old number as a secondary id", rec.get("combo_id") == "Combo 7", rec)
ok("...and lists the picks", rec.get("picks") == ["Nuggets", "Chiefs +2"], rec.get("picks"))
src = open("wahome/engine.py").read()
ok("mine_page labels no card 'Combo {i}' any more (the number is `num`)", 'label": f"Combo {i}"' not in src and "<b>Combo {i}</b>" not in src)
