# "Build a fresh panel" starts at once: the flag, the progress notes the page reads, the done/why message, and the
# watcher's rebuild thread picking a request up within seconds. It only makes drafts: never approves or buys.
import os, sys, time, tempfile, threading, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.injury_note = lambda code, *teams, hours=48: ([], False)   # no injury news: never ESPN's real report (netguard)
import datetime as _dt; _u = _dt.datetime.now(_dt.timezone.utc); E.PACIFIC = _dt.timezone(_dt.timedelta(hours=round(12 - _u.hour - _u.minute / 60)))
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.REBUILD_FLAG = os.path.join(E.HERE, "panel_rebuild.flag"); E.REBUILD_STATE = os.path.join(E.HERE, "combo_rebuild.json")
E.fetch_account = lambda **k: ([], 300.0, None)
SENT = []
E.kalshi_send = lambda *a, **k: SENT.append(a) or {}
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()


def mk(t, ev, f, p, k):
    l = {"ticker": t, "event": ev, "pick": t, "p": p, "fair": f}; E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(k))
    return E._cand("single", "nba", [l], f, (f - p - E.single_fee(p)) / (p + E.single_fee(p)), "w", price=p)


ok("nothing to show before any request", E.rebuild_status() is None and not E.rebuild_pending())
ok("Look now asks the Mac", E.panel_look_now()[0] and E.rebuild_pending())
st = E.rebuild_status(); ok("page sees 'asked' straight away", st and st["state"] == "asked" and st["wait"] < 5)

SEEN = []


def collect(code):                                   # stands in for panel_collect: fills that sport's pool
    SEEN.append(E.rebuild_status())
    if code == "nba":
        E.PANEL_POOL["nba"] = (time.time(), [mk("N1", "KXNBAGAME-1", .6, .52, now + 9000), mk("N2", "KXNBAGAME-2", .58, .5, now + 9000),
                                             mk("N3", "KXNBAGAME-3", .62, .53, now + 9000)])
        E.PANEL_GAMES["nba"] = 3
    else:
        E.PANEL_GAMES[code] = 0


E.panel_rebuild(collect, ("nfl", "nba", "nhl"), lock=threading.RLock(), log=lambda *a: None)
ok("request cleared once started", not E.rebuild_pending())
ok("progress names each sport in turn", [(s or {}).get("sport") for s in SEEN] == ["nfl", "nba", "nhl"]
   and all(s["state"] == "running" and s["n"] == 3 for s in SEEN) and [s["i"] for s in SEEN] == [0, 1, 2])
st = E.rebuild_status(); p = E.panel_get("real")
ok("done note with the count", st and st["state"] == "done" and st["found"] == len(p["items"]) > 0 and not st["why"])
ok("result is a draft, not approved", p["status"] == "draft")
ok("nothing was bought", not SENT)

# nothing found: says why
E.store_x("delete from panel", ())
E.PANEL_POOL.clear(); E.PANEL_GAMES.clear()
E.ask_rebuild()
E.panel_rebuild(lambda c: E.PANEL_GAMES.__setitem__(c, 0), ("nba", "nhl"), log=lambda *a: None)
st = E.rebuild_status(); ok("no games left: says so", st["state"] == "done" and st["found"] == 0 and "No games left" in st["why"])
E.panel_rebuild(lambda c: E.PANEL_GAMES.__setitem__(c, 3), ("nba", "nhl"), log=lambda *a: None)
st = E.rebuild_status(); ok("games but no value: says how many were checked", "Checked 6 upcoming games" in st["why"] and E.panel_get("real") is None)

# a stale 'running' note (the Mac stopped mid-way) isn't shown forever
E._rebuild_note(state="running", at=now - 900, sport="nba", i=1, n=6); E.save_json(E.REBUILD_STATE, dict(E.load_json(E.REBUILD_STATE, {}), upd=now - 900))
ok("stale progress is dropped", E.rebuild_status() is None)

# Look now is refused once today's panel is approved
E.PANEL_POOL["nba"] = (time.time(), [mk("N1", "KXNBAGAME-1", .6, .52, now + 9000), mk("N2", "KXNBAGAME-2", .58, .5, now + 9000)])
E.panel_pass(); E.panel_approve(None, "all")
ok("Look now refused on an approved panel", not E.panel_look_now()[0])

# the watcher's rebuild thread picks a request up within seconds (not at the 10-minute round) and times it
sys.argv = ["combo_watcher.py"]
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py"); W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
W.log = lambda *a: None
E.store_x("delete from panel", ())


class Odds:
    lock = threading.RLock()
    def engine(self): return E
    def get(self, code, key): time.sleep(.05); return {}


def fake_collect(snap, code, log=print):
    if code == "nba":
        E.PANEL_POOL["nba"] = (time.time(), [mk("N1", "KXNBAGAME-1", .6, .52, now + 9000), mk("N2", "KXNBAGAME-2", .58, .5, now + 9000),
                                             mk("N3", "KXNBAGAME-3", .62, .53, now + 9000)])
    E.PANEL_GAMES[code] = 3 if code == "nba" else 0


E.panel_collect = fake_collect
threading.Thread(target=W.rebuild_loop, args=(Odds(),), kwargs={"every": 0.2}, daemon=True).start()
time.sleep(.5)
t0 = time.time(); E.ask_rebuild()
while time.time() - t0 < 8 and ((E.rebuild_status() or {}).get("state") != "done"):
    time.sleep(.05)
st = E.rebuild_status() or {}
print(f"rebuild took {time.time() - t0:.1f}s from the tap (fake services)")
ok("watcher thread rebuilt within seconds", st.get("state") == "done" and time.time() - t0 < 5 and st.get("found", 0) > 0)
ok("watcher rebuild left a draft, bought nothing", E.panel_get("real")["status"] == "draft" and not SENT)
ok("panel loop no longer waits for the flag", "rebuild_asked" not in open("wtest/combo_watcher.py").read().split("def panel_loop")[1].split("def rebuild_loop")[0])
