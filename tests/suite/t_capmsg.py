# CHECK: group=engine
# The over-the-cap message (issue #71): its words follow the window the cap really counts (today / this week (Wed to
# Mon) / games still to play for the Mix; never "this weekend", Pete's decision on #71), it names the Settings item to
# change ("Weekly cap", renamed from "Weekend cap") and says how much room is left. The rule itself (week_spend, the
# cap amount, the windows) is untouched.
import os, tempfile, datetime as dt, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
from wsrc import watcher_text   # the watcher file plus its web app files (watcher/spa/)
W = watcher_text()
E.HERE = tempfile.mkdtemp(); E.SAVED = E.MAIN_SAVED = os.path.join(E.HERE, "combo_settings.json")

THU, FRI, SAT, MON, WED = (dt.date(2026, 11, d) for d in (19, 20, 21, 23, 18))
E.set_league("nfl")
ok("NFL on a Thursday says this week (Tue to Mon)", E.cap_window(THU) == "this week (Tue to Mon)")
ok("NFL on a Wednesday says this week", E.cap_window(WED) == "this week (Tue to Mon)")
ok("NFL on Friday, Saturday and Monday also says this week (Tue to Mon), never this weekend",
   all(E.cap_window(d) == "this week (Tue to Mon)" for d in (FRI, SAT, MON)))
ok("NFL cap is called the Weekly cap", E.cap_label() == "Weekly cap")
ok("the words match the counting: a Tuesday game is in the coming Sunday's week, Monday's in the one before",
   E.sunday_of(dt.date(2026, 11, 24)) == dt.date(2026, 11, 29) and E.sunday_of(MON) == dt.date(2026, 11, 22)
   and E.sunday_of(WED) == dt.date(2026, 11, 22))
E.set_league("ncaaf")
ok("college football on a Saturday says this week (Tue to Mon)", E.cap_window(SAT) == "this week (Tue to Mon)")
E.set_league("soccer")
ok("soccer on a Saturday says this week (Tue to Mon)", E.cap_window(SAT) == "this week (Tue to Mon)")
E.set_league("ufc")
ok("UFC says this week (Tue to Mon) and the Weekly cap", E.cap_window(FRI) == "this week (Tue to Mon)"
   and E.cap_label() == "Weekly cap")
E.set_league("nba")
ok("NBA says today and calls it the Daily cap", E.cap_window(THU) == "today" and E.cap_label() == "Daily cap")
E.CFG["next_day"] = True
ok("a daily league on tomorrow's games says tomorrow", E.cap_window(THU) == "tomorrow")
E.CFG["next_day"] = False
E.set_league("mix")
ok("the Mix says games still to play and calls it the Mix cap", E.cap_window(THU) == "on games still to play" and E.cap_label() == "Mix cap")

# the full sentence: what it would reach, the cap, the room left, the setting to change
E.set_league("nfl"); E.CFG["budget"] = 50
m = E.cap_msg(49.0, 5.0)
ok("message says the new total and the cap", "$54" in m and "$50 cap" in m)
ok("message says how much room is left", "$1 left" in m)
ok("message names the Settings item and the league", "Settings > Money > Weekly cap" in m and "NFL" in m)
ok("message names the real window (this week, Tue to Mon) and never says weekend",
   "spending this week (Tue to Mon) to" in m and "weekend" not in m.lower())
mm = E.manual_cap_msg("nfl", 49.0, 5.0, 50.0)
ok("a manual buy's message (Buy straight, Live-idea singles) says the Weekly cap and the window too",
   "Weekly cap" in mm and "that week (Tue to Mon)" in mm and "weekend" not in mm.lower() and "$1 left" in mm)
ok("room left is never negative", "$0 left" in E.cap_msg(60.0, 5.0))
ok("message says how far to raise the cap, in the slider's $10 steps (#112)", "raise it to at least $60" in m and "at least $54" not in m)
E.set_league("nba"); E.CFG["budget"] = 50
m = E.cap_msg(48.0, 7.29)
ok("a daily league's message says today and the Daily cap",
   "spending today to" in m and "Settings > Money > Daily cap" in m and "weekend" not in m)

# the real taps: Get price (get_offer) and Buy (accept_offer) use it, and never reach Kalshi when over the cap
E.set_league("nfl"); E.CFG["budget"] = 50
E.CTX.update(combos=[{"legs": []}], stake=5, offers={1: {"stake": 5.0}})
E.week_spend = lambda: 49.0
E.kalshi_send = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not reach Kalshi when over the cap"))
r = E.get_offer(1)
ok("Get price over the cap refuses with the new words",
   "$54" in r.get("error", "") and "$1 left" in r["error"] and "Settings > Money > Weekly cap" in r["error"])
r = E.accept_offer(1)
ok("Buy over the cap refuses with the new words", "$54" in r.get("error", "") and "Weekly cap" in r["error"])
E.week_spend = lambda: 10.0
try:
    r = E.get_offer(1)
    went_on = "over your" not in r.get("error", "")
except IndexError:
    went_on = True              # got past the cap check (the fake combo has no legs, so it fails later): fine
ok("under the cap the cap message does not appear", went_on)
r = E.get_offer(1, 80)
ok("a stake above the whole cap names the cap setting",
   "$80 is more than your whole $50 cap" in r["error"] and "Weekly cap" in r["error"])
src = open("wahome/engine.py").read()
ok("old wording is gone from the engine", "take this {slate_word()}" not in src and "Raise the cap in settings" not in src)
ok("the web app's single-bet idea uses its own league's cap message", "A.single_cap_block(tk" in W
   and "That would go over your" not in W)
ok("no screen calls the cap the Weekend cap any more", "Weekend cap" not in W and "Weekend cap" not in src
   and "'Weekly cap'" in W and "spends in one '+(mode==='day'?'day':mode==='mix'?'mix':'week (Tue to Mon)')" in W)
