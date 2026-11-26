# CHECK: group=engine
# The cautious default loss cut (12.5%) is applied at READ time only, combos only. It is never written to smart.json or to
# self-tuning's live values, so turning `loss_cut_default` off fully restores the old behaviour, singles are never cut by it.
# (The firing record saying src "default" is checked in t_cutloss_default.py.)
import os, time, tempfile, importlib.util, json
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.MAIN_SAVED = os.path.join(E.HERE, "main.json"); E.KNOBS_FILE = os.path.join(E.HERE, "knobs.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
T = "KXNBAGAME-26NOV19LALBOS-LAL"
E.CFG.update(smart_sell=True, ride=2, take_profit=0, lock_trail=True, loss_cut_default=True, knobs_live=True)
E.save_json(E.MAIN_SAVED, {"knobs_live": True}); E.KNOB_SWITCH["on"] = None; E.KNOB_STATE_CACHE["d"] = None
ok("self-tuning switch on (the usual case)", E.knob_switch_on() is True)

def add_item(i, code, path):
    t = f"KX{code.upper()}GAME-26NOV{10 + i % 9:02d}T{i:03d}-AAA"
    kick = now - 86400 * 3 - i * 600
    for k, ch in enumerate(path):
        E.store_x("insert into ticks values(?,?,?,?,?)", (kick + 60 * (k + 1), t, ch, "sim", "active"))
    return {"id": f"paper:{t}", "kind": "single", "code": code, "legs": [{"ticker": t, "p": .5, "pick": t}], "stake": 5.0,
            "price": .5, "paid": .5, "kick": kick, "state": "paper", "result": "lost", "pl": -5.0}
items = [add_item(i, "nba", [.52, .6, .7, .78, .6, .4, .2, 0.0]) for i in range(40)]
E._panel_table()
E.store_x("insert or replace into panel values(?,?,?,?,?)", ("2026-11-15", "paper", now - 86400 * 3, "paper", json.dumps({"at": now - 86400 * 3, "items": items})))
E.smart_tune(force=True)
d = E.load_json(E.SMART_FILE, {})
ok("smart_tune ran and saw the league", (d.get("nba") or {}).get("n") == 40)
ok("nothing moved: smart.json holds no loss value for any league (the default is never saved)",
   all((e.get("loss") is None) and not e.get("loss_off") for k, e in d.items() if not k.startswith("_")))
E.SMART_CACHE["at"] = 0
p = E.smart_params([T])
ok("...so the combo still gets the default at read time, marked as such", p["loss"] == 0.125 and p.get("loss_src") == "default")
ok("...and singles never get it", E.smart_params([T], single=True)["loss"] is None)
ok("exit_settings: a single Smart Buy candidate never gets the default, a combo does",
   E.exit_settings([T], single=True)["loss"] is None and E.exit_settings([T])["loss"] == 0.125)
E.CFG["loss_cut_default"] = False
E.SMART_CACHE["at"] = 0
ok("switch off after a tune: the old 'never' is back for combos", E.smart_params([T])["loss"] is None)
E.CFG["loss_cut_default"] = True

E.save_json(E.SMART_FILE, {}); E.SMART_CACHE["at"] = 0
json.dump({"groups": {"nba": {"lv": {"smart_loss": 0.2}, "lat": {"smart_loss": now - 9}, "lstep_at": now - 9}},
           "brake": {}, "settings": {}}, open(E.KNOBS_FILE, "w")); E.KNOB_STATE_CACHE["d"] = None
ok("before the brake: nba's own 20% applies", E.smart_params([T])["loss"] == 0.2)
E._knob_brake_sales = lambda st, now_, live: {"nba": [1]}
E.knob_brake_check = lambda sales: "test: sold under what holding was worth"
E.knob_brake_pass(now, force=True)
S = E.knob_state()
ok("the brake fired for nba", "nba" in S["brake"])
lv = (S["groups"].get("nba") or {}).get("lv") or {}
ok("brake reset deletes the own loss value instead of saving the default", "smart_loss" not in lv)
E.KNOB_STATE_CACHE["d"] = None
p = E.smart_params([T])
ok("...so the default applies again at read time", p["loss"] == 0.125 and p.get("loss_src") == "default")
ok("...never to singles", E.smart_params([T], single=True)["loss"] is None)
E.CFG["loss_cut_default"] = False
ok("switch off after a brake: the old 'never' is back", E.smart_params([T])["loss"] is None)
E.CFG["loss_cut_default"] = True

json.dump({"groups": {}, "brake": {}, "settings": {}}, open(E.KNOBS_FILE, "w")); E.KNOB_STATE_CACHE["d"] = None
E.knob_tune(now, force=True)
S = E.knob_state()
ok("stepper with nothing to move saves no default loss value",
   all((g or {}).get("lv", {}).get("smart_loss") != 0.125 for g in (S.get("groups") or {}).values()))
