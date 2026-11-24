# CHECK: group=engine
# ESPN's per-day scoreboard reads run inside odds.lock (issue #351). One total deadline (ESPN_DEADLINE) means a hung
# ESPN can't hold the lock for the sum of the day timeouts: days not back by then count as unread (ESPN_FREE bad),
# the days that did answer are kept, and nothing raises. Fakes only: no network.
import os, time, threading, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
release = threading.Event()


class R:
    ok = True

    def __init__(self, evs):
        self._e = evs

    def json(self):
        return {"events": self._e}


def fake_get(url, params=None, timeout=None, **kw):
    day = params["dates"]
    if day == f"{E.dt.date.today() + E.dt.timedelta(days=1):%Y%m%d}":
        release.wait(30)                         # ESPN hangs on this day
        return R([{"id": "late"}])
    return R([{"id": "e" + day}])


keep = E.requests
E.requests = type("Q", (), {"get": staticmethod(fake_get), "RequestException": keep.RequestException})
E.ESPN_DEADLINE = 1
try:
    t0 = time.time()
    evs = E.espn_scoreboard("football/nfl", {}, 4, code="t_deadline")
    took = time.time() - t0
    ids = sorted(e["id"] for e in evs)
    cnt = E.ESPN_FREE["t_deadline"]
    ok(f"a hung day: the read returns at the deadline ({took:.1f}s), keeps the 3 answered days, counts 1 unread "
       f"({ids}, {cnt})", took < 5 and len(ids) == 3 and "late" not in ids and cnt["ok"] == 3 and cnt["bad"] == 1)
finally:
    release.set()
    E.requests = keep
