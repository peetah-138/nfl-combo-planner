# CHECK: group=engine
# Issue #309 (money-j): the registry says how each knob is borrowed. knob_live_value borrows a value from the sport / everyone
# for every live knob that has a stricter side, never looser than the start (knob_stricter), so a live knob marked
# borrow "none" described it wrongly. They are now "chain-stricter" (a label only: no number or decision changes).
import os, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)

wrong = [n for n in E.KNOB_LIVE if E.KNOB_BY[n].get("stricter") and E.KNOB_BY[n].get("borrow") == "none"]
ok("no live knob that borrows (stricter only) is labelled borrow 'none': %s" % wrong, not wrong)
# the behaviour the label describes: a looser borrowed value is the start, a stricter one is kept
k = E.KNOB_BY["tp_min_gain"]; s = k["start"]
loose, strict = (s - k["step"], s + k["step"]) if k["stricter"] == "up" else (s + k["step"], s - k["step"])
ok("a looser borrowed value gives the start", E.knob_stricter("tp_min_gain", loose) == s)
ok("a stricter borrowed value is kept", E.knob_stricter("tp_min_gain", strict) == strict)
