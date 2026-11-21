# CHECK: group=engine
import os, importlib.util, datetime as dt
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = dt.datetime.now(dt.timezone.utc)
ago = lambda h: now - dt.timedelta(hours=h)

ok("not started: no status", E.run_status("tennis", now + dt.timedelta(hours=1), now) is None and E.run_status("tennis", None) is None)
r = E.run_status("tennis", ago(0.7), now)
ok("a tennis match under way says how long, never just 'Live'", r["phase"] == "on" and "Started 42 min ago" in r["text"] and "no live score" in r["text"])
r = E.run_status("tennis", ago(5.5), now)
ok("tennis 5h30m in: probably finished, waiting on Kalshi", r["phase"] == "probably_over" and "Probably finished" in r["text"]
   and "5h 30m" in r["text"] and "waiting on Kalshi" in r["text"] and r["short"] == "Probably over")
for sp, edge in (("tennis", 4.0), ("ufc", 3.0), ("euroleague", 2.75), ("ahl", 3.5)):
    ok(f"{sp}: on just inside {edge}h, probably over just past it",
       E.run_status(sp, ago(edge - .1), now)["phase"] == "on" and E.run_status(sp, ago(edge + .1), now)["phase"] == "probably_over")
ok("every sport with no score source has a match length", all(s in E.DONE_HOURS for s in ("tennis", "ufc", "euroleague", "ahl")))
ok("a score source that says live wins over the clock", E.run_status("tennis", ago(9), now, "in")["phase"] == "on")
r = E.run_status("nba", ago(1), now, "post")
ok("a score source that says final: over, waiting to settle", r["phase"] == "over" and "settle" in r["text"])
ok("unknown sport gets a sensible default", E.run_status("curling", ago(1), now)["phase"] == "on" and E.run_status("curling", ago(6), now)["phase"] == "probably_over")
ok("ago_text reads plainly", E.ago_text(30) == "1 min" and E.ago_text(25 * 60) == "25 min" and E.ago_text(3 * 3600 + 600) == "3h 10m"
   and E.ago_text(5 * 3600) == "5h" and E.ago_text(50 * 3600) == "2 days")
ok("when_label: past times say 'Started … ago'", E.when_label(ago(0.5)).startswith("Started 30 min ago"))
ok("when_label: future times still read as a time", not E.when_label(now + dt.timedelta(hours=30)).startswith("Started"))

# pick_state (money logic) is unchanged: a started game is still "live" for the engine
src = open("wahome/engine.py").read()
ok("the display status is separate from pick_state", "def run_status" in src and "def pick_state" in src)
