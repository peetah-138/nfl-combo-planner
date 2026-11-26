# CHECK: group=engine
# Every new sell switch must reach the engine: its key has to be in the engine's SHARED_KEYS and WATCHER_SYNCED, the
# watcher's SYNCED and SET_KEYS lists, and the Settings screen (settings.js). A key dropped from any one of them (a merge
# that kept one side's list) means the Settings switch is saved but never reaches the engine. (Pete, 2026-11-25)
import os, re, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
W = open("wtest/combo_watcher.py").read()
JS = open("wtest/spa/settings.js").read()
def tup(src, name):
    m = re.search(r"^\s*" + name + r"\s*=\s*\((.*?)\)\s*$", src, re.S | re.M)
    return set(re.findall(r'"([a-z_0-9]+)"', m.group(1))) if m else set()
SYNC, SETK = tup(W, "SYNCED"), tup(W, "SET_KEYS")
# every new key (by prefix) that exists in DEFAULTS, plus the ones that must exist
NO_SCREEN_ROW = {"flex_backstop"}     # a number with no Settings row on purpose (still synced and saved)
EXPECT = {"flex_sell", "flex_learn", "flex_backstop", "sell_more_cheap", "sell_more_cap", "learned_guards"}
NEW = {k for k in E.DEFAULTS if k.startswith(("flex_", "sell_more", "learned_guards"))} | EXPECT
ok("the new sell keys exist in DEFAULTS", EXPECT <= set(E.DEFAULTS), sorted(EXPECT - set(E.DEFAULTS)))
for k in sorted(NEW):
    ok(f"{k}: in SHARED_KEYS", k in E.SHARED_KEYS)
    ok(f"{k}: in the engine's WATCHER_SYNCED", k in E.WATCHER_SYNCED)
    ok(f"{k}: in the watcher's SYNCED", k in SYNC)
    ok(f"{k}: in the watcher's SET_KEYS", k in SETK)
    ok(f"{k}: on the Settings screen", k in NO_SCREEN_ROW or ("'" + k + "'") in JS or ('"' + k + '"') in JS)

# combo_sell_fee (#382/#383, #428) is Mac-file-only on purpose (release 507 review): a config switch in DEFAULTS that is in
# no sync list and has no Settings row. If someone adds it to Settings later, this check must be changed with it, so the
# decision is never made by accident (a key in only some of the lists would be saved but never reach the engine).
ok("combo_sell_fee: exists in DEFAULTS (default on)", E.DEFAULTS.get("combo_sell_fee") is True)
ok("combo_sell_fee: Mac-file-only: in no sync list, no SET_KEYS, no Settings row",
   "combo_sell_fee" not in E.SHARED_KEYS and "combo_sell_fee" not in E.WATCHER_SYNCED and "combo_sell_fee" not in SYNC
   and "combo_sell_fee" not in SETK and "combo_sell_fee" not in JS)
