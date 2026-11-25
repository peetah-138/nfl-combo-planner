# CHECK: group=engine
# The panel's "today" ends at 4 a.m. Pacific (that is intended: late West Coast games belong to the evening before).
# Tests that put a kickoff a few hours after the wall clock used to fail when CI ran between 1 and 4 a.m. Pacific (the
# kickoff then landed after the cut). This pins the clock at the boundary and checks the rule itself, both sides of it,
# so a test can never be fooled by the time of day again, and the rule can't drift unnoticed.
import os, time, tempfile, importlib.util, datetime as rdt
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.injury_note = lambda code, *teams, hours=48: ([], False)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db"))
E.HERE = tempfile.mkdtemp(); E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.fetch_account = lambda **k: ([], 300.0, None)
E.account_events = lambda *a, **k: set()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
PT = E.PACIFIC


def at(h, m=0, day=25):                     # a Pacific wall-clock time on 2026-11-<day> (no DST change in November)
    return rdt.datetime(2026, 11, day, h, m, tzinfo=PT).timestamp()


# the boundary itself
ok("03:59 Pacific: today ends at 4 a.m. today", E._local_day_end(at(3, 59)) == at(4))
ok("04:00 Pacific: today ends at 4 a.m. tomorrow", E._local_day_end(at(4)) == at(4, 0, 26))
ok("12:00 Pacific: today ends at 4 a.m. tomorrow", E._local_day_end(at(12)) == at(4, 0, 26))
ok("03:59 still belongs to the day before", E._panel_day(at(3, 59)) == "2026-11-24")
ok("04:00 is the new day", E._panel_day(at(4)) == "2026-11-25")


def leg(t, ev, pick, p, fair): return {"ticker": t, "event": ev, "pick": pick, "p": p, "fair": fair}


def single(i, kick):
    ev = f"KXNBAGAME-C{i}"
    E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(kick))
    return E._cand("single", "nba", [leg(f"C{i}-A", ev, "Alpha", .50, .56)], .56, .08, "why", price=.50)


def todays(now, kicks):                     # how many of these kickoffs make the panel's pool for the day at `now`
    E.PANEL_POOL = {"nba": (now, [single(i, k) for i, k in enumerate(kicks)])}
    return E.build_panel(codes=["nba"], now=now, budget=100)["stats"]["pool"].get("single", 0)


# 02:00 Pacific: a 03:30 game is today's, a 04:30 game (and anything "3 hours ahead", 05:00) is tomorrow's. This is
# exactly what made fixtures at now+3h fail when CI ran at 03:54 Pacific.
now = at(2)
ok("02:00: a 03:30 game is today's", todays(now, [at(3, 30)]) == 1)
ok("02:00: a 04:30 game is tomorrow's", todays(now, [at(4, 30)]) == 0)
ok("02:00: a game 3h ahead (05:00) is tomorrow's", todays(now, [now + 3 * 3600]) == 0)
# noon Pacific: games +3h and +4h are both today's, at any date, so the fixtures other tests use are stable
now = at(12)
ok("12:00: games 3h and 4h ahead are both today's", todays(now, [now + 3 * 3600, now + 4 * 3600]) == 2)
ok("12:00: a game after 4 a.m. tomorrow is not", todays(now, [at(5, 0, 26)]) == 0)
