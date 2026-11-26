# CHECK: group=engine
"""Queue UI 3 (#518, #195, #290): the log line names a combo by its legs, not joined tickers; source checks for the wording."""
import sys, os
sys.path.insert(0, "stub"); sys.path.insert(0, "run")
import nfl_combo_planner as M
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
rd = lambda f: open(os.path.join("wtest", "spa", f), encoding="utf-8").read()
legs = [{"ticker": "KXNBAGAME-26NOV30AAABBB-AAA", "pick": "Foxes"}, {"ticker": "KXNBAGAME-26NOV30CCCDDD-CCC", "pick": "Herons +2"}]
nm = M.legs_log_name(legs)
ok(f"legs_log_name names the legs ({nm!r})", "Foxes" in nm and "Herons +2" in nm and "KXNBAGAME" not in nm and "Combo" not in nm)
ok("legs_log_name never raises on junk", isinstance(M.legs_log_name(None), str) and isinstance(M.legs_log_name([None, 3]), str))
src = open(M.__file__, encoding="utf-8").read()
ok("the exit-route and suspect log lines use the names, not the tickers", src.count("legs_log_name(legs_now)") == 2 and "'+'.join(l['ticker'] for l in legs_now)" not in src)
b = rd("build.js")
ok("#518 wording: 'based on how your past bets did', no 'on your record'", "based on how your past bets did, before fees" in b and "on your record" not in b)
lv, cm = rd("live.js"), rd("common.js")
ok("#195: the pill rolls only when a single is open; the estimate is data-still when no combo was priced live",
   "heroChg(kd,St,moves,false)" in lv and "data-still" in lv and "el.dataset.still" in cm)
ok("#290: one progress line, a held-back line only when something holds it back; no 'beats plain'",
   'class="sbprog"' in rd("results.js") and "Held back:" in rd("results.js") and "beats plain" not in rd("results.js"))
