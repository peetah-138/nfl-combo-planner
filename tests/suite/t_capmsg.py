# The over-the-cap message (issue #71): its words follow the window the cap really counts (today / this week /
# this weekend only on a football slate Fri-Mon / games still to play for the Mix), it names the Settings item to
# change and says how much room is left. The rule itself (week_spend, the cap amount) is untouched.
import os, tempfile, datetime as dt, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
from wsrc import watcher_text   # the watcher file plus its web app files (watcher/spa/)
W = watcher_text()
E.HERE = tempfile.mkdtemp(); E.SAVED = E.MAIN_SAVED = os.path.join(E.HERE, "combo_settings.json")

THU, FRI, SAT, MON, WED = (dt.date(2026, 11, d) for d in (19, 20, 21, 23, 18))
E.set_league("nfl")
ok("NFL on a Thursday says this week, not this weekend", E.cap_window(THU) == "this week")
ok("NFL on a Wednesday says this week", E.cap_window(WED) == "this week")
ok("NFL on Friday, Saturday and Monday says this weekend", all(E.cap_window(d) == "this weekend" for d in (FRI, SAT, MON)))
ok("NFL cap is called the Weekend cap", E.cap_label() == "Weekend cap")
E.set_league("ncaaf")
ok("college football on a Saturday says this weekend", E.cap_window(SAT) == "this weekend")
E.set_league("soccer")
ok("soccer on a Saturday still says this week (not a football slate)", E.cap_window(SAT) == "this week")
E.set_league("ufc")
ok("UFC says this week", E.cap_window(FRI) == "this week")
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
ok("message names the Settings item and the league", "Settings > Money > Weekend cap" in m and "NFL" in m)
ok("room left is never negative", "$0 left" in E.cap_msg(60.0, 5.0))
ok("message says how far to raise the cap", "raise it to at least $54" in m)
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
   "$54" in r.get("error", "") and "$1 left" in r["error"] and "Settings > Money > Weekend cap" in r["error"])
r = E.accept_offer(1)
ok("Buy over the cap refuses with the new words", "$54" in r.get("error", "") and "Weekend cap" in r["error"])
E.week_spend = lambda: 10.0
try:
    r = E.get_offer(1)
    went_on = "over your" not in r.get("error", "")
except IndexError:
    went_on = True              # got past the cap check (the fake combo has no legs, so it fails later): fine
ok("under the cap the cap message does not appear", went_on)
r = E.get_offer(1, 80)
ok("a stake above the whole cap names the cap setting",
   "$80 is more than your whole $50 cap" in r["error"] and "Weekend cap" in r["error"])
src = open("wahome/engine.py").read()
ok("old wording is gone from the engine", "take this {slate_word()}" not in src and "Raise the cap in settings" not in src)
ok("the web app's single-bet idea uses the same message", "A.cap_msg(spent" in W and "That would go over your" not in W)
