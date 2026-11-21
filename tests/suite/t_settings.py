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
ok("Settings labels it a manual override and mentions the learned loss cut",
   "Manual override: sell at a loss when a game turns" in W and "learns when cutting a loss beats holding" in W)
