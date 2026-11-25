# CHECK: group=engine
# Pete's "never sell at a loss" rule (2026-11-23, #382/#383) as the copy says it: auto-sell never sells below what you
# paid EXCEPT to lose less than waiting (the learned loss cut, the guarded stop-loss); a profit-taking sale never retries
# below cost; a loss cut never retries under 97% of its first offer. Wording only: the decision code is untouched.
import os, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
src = open(spec.origin).read()
ok("the auto cash-out explainer names the guarded stop-loss exception, its guards and the profit retry rule",
   "guarded stop-loss may sell below cost when the app" in src and "judges that selling now loses less than waiting" in src
   and "97% of its first offer or" in src and "the smart-sell floor" in src
   and "a profit-taking sale never retries below what you paid" in src)
row = next(k for k in E.KNOBS if k.get("name") == "below_cost")
ok("the below_cost knob's description covers the retry rules and the Never setting",
   all(w in row["what"] for w in ("never retries below cost", "97%", "smart-sell floor", "Never setting")))
ok("the 97% guard on a loss cut is still in the code (decision logic unchanged)",
   "line = max(line, CASH_SLIP * agreed)" in src and E.CASH_SLIP == 0.97)
ok("a profit-taking sale's retry floor is still its cost",
   'None if cutting else h["cost"] * o.get("frac", 1.0)' in src)
