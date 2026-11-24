# CHECK: group=engine
import os, json, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
from wsrc import watcher_text   # the watcher file plus its web app files (watcher/spa/)
W = watcher_text()

# the dead "include my own Kalshi bets" setting is gone everywhere
ok("sell_own is not an engine default", "sell_own" not in E.DEFAULTS)
ok("sell_own is not shared or synced to the watcher", "sell_own" not in E.SHARED_KEYS and "sell_own" not in E.WATCHER_SYNCED)
ok("sell_own is not in the watcher's synced or saved lists", "sell_own" not in W)
# an old saved file that still has it is ignored on load
E.HERE = tempfile.mkdtemp(); E.SAVED = E.MAIN_SAVED = os.path.join(E.HERE, "combo_settings.json")
json.dump({"sell_own": True, "stop_loss": True}, open(E.SAVED, "w"))
E.set_league("nfl")
ok("an old saved sell_own is dropped on load", "sell_own" not in E.CFG)

# stop_loss stays, as a labelled manual override, still synced and still off by default
ok("stop_loss is still off by default", E.DEFAULTS.get("stop_loss") is False)
ok("a saved stop_loss still loads", E.CFG.get("stop_loss") is True)
ok("stop_loss is still shared and synced", "stop_loss" in E.SHARED_KEYS and "stop_loss" in E.WATCHER_SYNCED and "stop_loss" in W)
# #228 PR5: the on/off override became a 3-way choice; an old saved value reads the same as before
ok("Settings shows the 3-way choice in plain words",
   all(w in W for w in ("Selling at a loss", "Never sell at a loss", "Let it tune itself", "Allow (guarded)"))
   and "Manual override: sell at a loss when a game turns" not in W)
ok("the new choice is shared, synced to the watcher and saved by the web app",
   "stop_loss_mode" in E.SHARED_KEYS and "stop_loss_mode" in E.WATCHER_SYNCED and W.count('"stop_loss_mode"') >= 3)
ok("an old saved 'on' reads as Allow (guarded)", E.sl_mode() == "allow")
E.CFG.update(stop_loss=False, stop_loss_mode=None)
ok("an old 'off' (and the default) reads as Let it tune itself", E.sl_mode() == "tune" and E.DEFAULTS["stop_loss_mode"] is None)
for bad in ("on", 1, True, "ALLOW", {"x": 1}):
    E.CFG["stop_loss_mode"] = bad
    if E.sl_mode() != "tune":
        break
ok("anything unreadable reads as Let it tune itself (the old switch off)", E.sl_mode() == "tune")
E.CFG.update(stop_loss=True, stop_loss_mode="never")
ok("a saved choice wins over the old switch", E.sl_mode() == "never")
E.CFG.update(stop_loss=False, stop_loss_mode=None)
