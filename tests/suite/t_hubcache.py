"""The hub's read cache (display only): short score ttl, last-good copy, backoff on 429/5xx, and warming that never
keeps an entry alive by itself. Everything is faked; nothing touches the network."""
import os, sys, time, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
sys.argv = ["combo_watcher.py", "--webapp"]
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
KAL = "https://api.elections.kalshi.com/trade-api/v2/markets"


class Resp:
    def __init__(s, code=200, text="{}", headers=None):
        s.status_code, s.ok, s.text, s.headers = code, code < 400, text, headers or {}


calls, plan = [], []


def fake_get(url, params=None, **kw):
    calls.append(url)
    step = plan.pop(0) if plan else Resp(200, '{"events": [1]}')
    if isinstance(step, Exception):
        raise step
    return step


real_get = W.requests.get
W.requests.get = fake_get
try:
    c = W.HubCache(None)
    ok("scores are kept for 6 seconds, prices 12, series 120", c.ttl(ESPN) == 6 and c.ttl(KAL) == 12
       and c.ttl("https://x/trade-api/v2/series/KXNBAGAME") == 120)
    ok("the AHL feed counts as scores", c.ttl("https://lscluster.hockeytech.com/feed/") == 6)

    c.get(ESPN, {"a": 1}); c.get(ESPN, {"a": 1})
    ok("a second ask inside the ttl is served from the cache", len(calls) == 1)
    c.get(ESPN, {"a": 1}, fresh=True)
    ok("fresh=True goes to the source", len(calls) == 2)

    # a host answering 429: serve the last good copy and stop asking for a while
    plan[:] = [Resp(429, "slow down", {"Retry-After": "7"})]
    got = c.get(ESPN, {"a": 1}, fresh=True)
    ok("429: the last good copy is served", got["status"] == 200 and len(calls) == 3)
    n = len(calls)
    got = c.get(ESPN, {"a": 1}, fresh=True)
    ok("429: no new request while backing off", len(calls) == n and got["status"] == 200)
    n_, until = c.cool["site.api.espn.com"]
    ok("backoff honours Retry-After (7s) and counts the failure", n_ == 1 and 6 <= until - time.time() <= 8)
    try:
        c.get(ESPN, {"b": 2})
        ok("backing off with nothing saved says so", False)
    except Exception as err:
        ok("backing off with nothing saved says so", "backing off" in str(err))
    other = c.get(KAL, {"a": 1})
    ok("backoff is per host: Kalshi is unaffected", other["status"] == 200 and c.host(KAL) not in c.cool)

    # the backoff grows, and ends on the first good answer
    c.cool["site.api.espn.com"] = (1, time.time() - 1)
    plan[:] = [Resp(503)]
    c.get(ESPN, {"a": 1}, fresh=True)
    ok("5xx counts too and doubles the wait (10s)", c.cool["site.api.espn.com"][0] == 2
       and 9 <= c.cool["site.api.espn.com"][1] - time.time() <= 11)
    c.cool["site.api.espn.com"] = (2, time.time() - 1)
    plan[:] = [Resp(200, '{"events": [2]}')]
    got = c.get(ESPN, {"a": 1}, fresh=True)
    ok("a good answer clears the backoff and returns the new data", "site.api.espn.com" not in c.cool and "[2]" in got["text"])

    # a network error: last good copy, then a note against the host
    plan[:] = [W.requests.ConnectionError("down")]
    got = c.get(ESPN, {"a": 1}, fresh=True)
    ok("network error: last good copy, host noted", "[2]" in got["text"] and c.cool["site.api.espn.com"][0] == 1)

    # 404/400 (e.g. a date range ESPN refuses) is the caller's business, not a reason to back off
    c2 = W.HubCache(None)
    plan[:] = [Resp(400, "bad")]
    got = c2.get(ESPN, {"dates": "x"})
    ok("a 400 is passed on without backing off", got["status"] == 400 and not c2.cool)
    ok("a bad answer is never saved as the last good copy", not c2.data)

    # warming never counts as asking
    c3 = W.HubCache(None)
    c3.get(ESPN, {"a": 1})
    key = next(iter(c3.wanted)); t0 = c3.wanted[key][0]
    time.sleep(.05)
    c3.get(ESPN, {"a": 1}, fresh=True, touch=False)
    ok("warming doesn't refresh the 'asked for' time (so idle entries expire)", c3.wanted[key][0] == t0)
    c3.get(ESPN, {"a": 1}, fresh=True)
    ok("a real ask does", c3.wanted[key][0] > t0)
finally:
    W.requests.get = real_get

# the warm loop: quick while watched, slow when not, gone after 30 minutes
c4 = W.HubCache(None)
fetched = []
c4.get = lambda u, p, fresh=False, touch=True: fetched.append((u, touch))
c4.FAST = 0
now = time.time()
c4.wanted = {"k1": (now - 5, ESPN, {}), "k2": (now - 600, ESPN, {}), "k3": (now - 2000, ESPN, {})}
c4.data = {"k1": (now - 10, {}), "k2": (now - 30, {}), "k3": (now - 5, {})}
real_sleep = W.time.sleep
n = {"i": 0}


def one_beat(s):
    n["i"] += 1
    if n["i"] > 1:
        raise SystemExit


W.time.sleep = one_beat
try:
    c4.warm()
except SystemExit:
    pass
finally:
    W.time.sleep = real_sleep
ok("warm: watched entry refreshed, quiet one (30s old, under the slow period) left, 30-min-old one dropped",
   len(fetched) == 1 and all(t is False for _, t in fetched) and "k3" not in c4.wanted and "k2" in c4.wanted)
