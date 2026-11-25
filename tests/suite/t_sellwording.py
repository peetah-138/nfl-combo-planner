# CHECK: group=engine
# Pete's "never sell at a loss" rule (2026-11-23, #382/#383) as the copy says it: auto-sell never sells below what you
# paid EXCEPT to lose less than waiting (the learned loss cut, the guarded stop-loss); a profit-taking sale never retries
# below cost; a loss cut never retries under 97% of its first offer. Wording only: the decision code is untouched.
import os, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
src = open(spec.origin).read()
ok("the auto cash-out explainer names the loss-cut exception and both retry rules",
   "except to cut a loss" in src and "never retries below what you paid" in src and "under 97% of its first offer" in src)
row = next(k for k in E.KNOBS if k.get("name") == "below_cost")
ok("the below_cost knob's description covers the retry rules and the Flexible sell note",
   all(w in row["what"] for w in ("never retries below cost", "97%", "Flexible sell")))
ok("the 97% guard on a loss cut is still in the code (decision logic unchanged)",
   "line = max(line, flex_fallback_bar(ticker, h, agreed, frac))" in src and "base = CASH_SLIP * agreed" in src and E.CASH_SLIP == 0.97)
ok("a profit-taking sale's retry floor is still its cost",
   'None if cutting else h["cost"] * o.get("frac", 1.0)' in src)
