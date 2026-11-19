"""Robustness of the display-only live-score code (review #37: H1, M3, L4) and the web app's tap lock and request
limit (L1, L2). A bad or slow live-score feed must never stop or delay auto cash-out; nothing here changes what
is bought or sold. Everything is faked; nothing touches the network or a real account."""
import os, sys, json, copy, time, threading, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))
FX = json.load(open("fixtures/kalshi_live.json"))
LIVE = {x["milestone_id"]: x for x in FX["live_datas"]}


def ms_for(event, mid=None):
    if event in FX["milestones_by_event"]:
        return copy.deepcopy(FX["milestones_by_event"][event])
    m = copy.deepcopy(FX["milestones_extra"][mid])
    m["primary_event_tickers"] = m["related_event_tickers"] = [event]
    return [m]


TEN, EUR = "KXATPMATCH-26NOV19DEBBLA", "KXEUROLEAGUEGAME-26NOV190330ADEILL"
TMID, EMID = "ab815e1a-4c83-45d2-a39e-47d093719fd5", "9c500ee8-1afb-56c0-90b0-0b6a078cbf8a"
MS = {TEN: ms_for(TEN, TMID), EUR: ms_for(EUR, EMID)}


class Resp:
    def __init__(self, body, code=200):
        self.body, self.status_code, self.ok, self.headers = body, code, code < 400, {}

    def json(self):
        return self.body


class Net:
    RequestException = E._requests.RequestException
    ConnectionError = E._requests.ConnectionError

    def __init__(self):
        self.live, self.delay, self.calls = copy.deepcopy(LIVE), 0.0, []

    def get(self, url, params=None, headers=None, **kw):
        self.calls.append(url)
        if self.delay and ("/milestones" in url or "/live_data" in url):      # only the live-score lookups are slow
            time.sleep(self.delay)
        if "/milestones" in url:
            return Resp({"milestones": MS.get((params or {}).get("related_event_ticker"), []), "cursor": ""})
        if "/live_data/batch" in url:
            return Resp({"live_datas": [self.live[i] for i in (params or {}).get("milestone_ids") or [] if i in self.live]})
        return Resp({"markets": [], "events": []})


net = Net(); E.requests = net
E.set_league("tennis")


def L(t):
    ev = t.rsplit("-", 1)[0]
    return {"ticker": t, "event_ticker": ev, "event": ev, "side": "yes"}


bets = [{"ticker": "KXMVE-R1", "legs": [L(TEN + "-DEB"), L(EUR + "-ADE")], "cost": 3.0, "pays": 12.0, "status": "pending",
         "back": 0, "week": "2026-11-19", "full_pays": 12.0, "lg": "mix", "lgs": ["tennis", "euroleague"]}]
now = time.time()
for t in (TEN + "-DEB", EUR + "-ADE"):
    E.KICKOFF[t.rsplit("-", 1)[0]] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 50 * 60))
    E.MARKET_INFO[t] = {"status": "open", "exp": "", "live": .55, "name": t}
E.fetch_account = lambda max_age=60, every_league=False: (bets, 200.0, "test")
E.fetch_results = lambda t: {}
E.resting_sells = lambda: {}
E.fetch_markets = lambda *a, **k: []
E.week_games = lambda *a, **k: ({}, {}, None)
E.auto_cash_checks = lambda: []
E.present = lambda *a, **k: None
E.notify = lambda *a, **k: None
E.in_pythonista = lambda: False
E.MINE.update(all_games={}, days={}, book={}, notes=[], live=True)
SOLD = []
E.auto_sell_now = lambda plan: SOLD.append(time.time()) or []


# ---- H1: a malformed live_data payload: no score for that game, logged once, auto cash-out still runs
bad = net.live[TMID]["details"]
bad["competitor1_round_scores"] = ["oops", {"score": "6"}]          # a non-dict item
bad["competitor2_round_scores"] = [{"score": "x"}, {"score": "?"}]   # non-numeric scores
bad["competitor1_overall_score"] = "one"
net.live[EMID]["details"].update(period="Q3", away_points="lots", match_status="ThirdQuarter")
E.KLIVE["ms"].clear(); E.KLIVE["live"].clear(); E.KLIVE.update(cool=0.0, fails=0)
E.kalshi_live_refresh([TEN, EUR], max_age=5)
ok("the malformed live data was stored (so the page build meets it)", E.KLIVE["live"].get(TMID, {}).get("d") is not None)
try:
    E._kalshi_score({"ticker": TEN + "-DEB", "side": "yes"})
    raised = False
except Exception:
    raised = True
ok("the raw reader does trip on it (the case the review found)", raised)
ok("kalshi_score: a bad field means no score for that game", E.kalshi_score({"ticker": TEN + "-DEB", "side": "yes"}) is None
   and E.kalshi_score({"ticker": EUR + "-ADE", "side": "yes"}) is None)
ok("display_score never raises", E.display_score({"ticker": TEN + "-DEB", "side": "yes"}, points=False, pre=True) is None)
ok("safe_run_status never raises", E.safe_run_status("tennis", "not a time") is None)
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    for _ in range(5):
        E.kalshi_score({"ticker": TEN + "-DEB", "side": "yes"})
ok("a bad field is logged once, not every loop", buf.getvalue().count("live score skipped") == 0)   # already logged above
try:
    page, snap = E.mine_page(live=True)
    built = bool(page)
except Exception as err:
    built = f"{type(err).__name__}: {err}"
ok("the Live page still builds with the bad feed", built is True, built)
SOLD.clear()
try:
    E.live_check(None)
    err = None
except Exception as e_:
    err = f"{type(e_).__name__}: {e_}"
ok("live_check reaches auto cash-out with a malformed live_data payload", err is None and len(SOLD) == 1, err)

# ---- M3: a slow Kalshi never delays the sell
E.KLIVE["ms"].clear(); E.KLIVE["live"].clear(); E.KLIVE.update(cool=0.0, fails=0)
net.live = copy.deepcopy(LIVE); net.delay = 4.0
SOLD.clear()
t0 = time.time()
E.live_check(None)
took = (SOLD[0] - t0) if SOLD else 99
ok("slow score lookups (4 s each) don't delay auto cash-out (budget %.1fs)" % E.KLIVE_BUDGET,
   SOLD and took < E.KLIVE_BUDGET * 2 + 1.5, round(took, 2))
t0 = time.time()
done = E.kalshi_live_kick([TEN, EUR], budget=0.3)
ok("only one background refresh at a time; the caller waits no longer than its budget", not done and time.time() - t0 < 1.0)
net.delay = 0.0
E.KLIVE_JOB["t"].join(30)
ok("the background refresh lands later (last good copy updated for the next build)",
   bool((E.KLIVE["live"].get(TMID) or {}).get("d")))
ok("mine_page and open_singles use the budgeted refresh, not the blocking one",
   "kalshi_live_kick(" in __import__("inspect").getsource(E.mine_page)
   and "kalshi_live_refresh(" not in __import__("inspect").getsource(E.mine_page)
   and "kalshi_live_kick(" in __import__("inspect").getsource(E.open_singles))

# ---- L4: caches are pruned
E.KLIVE["ms"]["OLD-EV"] = {"at": time.time() - 3 * E.KLIVE_MS_TTL, "id": "x"}
E.KLIVE["ms"]["OLD-MISS"] = {"at": time.time() - 3 * E.KLIVE_MS_MISS, "id": None}
E.KLIVE["ms"]["NEW-EV"] = {"at": time.time(), "id": "y"}
E.KLIVE["live"]["old-id"] = {"at": time.time() - 2 * E.KLIVE_LIVE_KEEP, "d": {}}
E.KLIVE["live"]["new-id"] = {"at": time.time(), "d": {}}
E.KLIVE.update(cool=0.0, fails=0)
E.kalshi_live_refresh([TEN], max_age=5)
ok("old milestones, misses and live blocks are forgotten; recent ones kept",
   "OLD-EV" not in E.KLIVE["ms"] and "OLD-MISS" not in E.KLIVE["ms"] and "old-id" not in E.KLIVE["live"]
   and "NEW-EV" in E.KLIVE["ms"] and "new-id" in E.KLIVE["live"])

# ---- L1 and L2: the web app's tap lock and shared request limit
sys.argv = ["combo_watcher.py", "--webapp"]
wspec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(wspec); wspec.loader.exec_module(W)
lock = threading.RLock()
tl = W.TapLock(lock)
held = threading.Event(); release = threading.Event()


def rebuild():                                # a Live rebuild holding the lock
    with lock:
        held.set()
        release.wait(10)


threading.Thread(target=rebuild, daemon=True).start(); held.wait(5)
W.ACT_WAIT = 0.5
seen, t0 = [], time.time()
try:
    with tl.hold():
        did = True
except W.ActBusy:
    did = False
ok("lock timeout: a tap gives up after ACT_WAIT and does nothing (never sent twice)", not did and time.time() - t0 < 2)
got = []


def taker():
    with tl.hold(timeout=5):
        got.append(time.time())


th = threading.Thread(target=taker, daemon=True)
th.start(); time.sleep(0.2)
ok("while a tap waits, Live rebuilds can see it and stand aside", tl.waiting == 1)
release.set(); th.join(5)
ok("the tap gets the lock as soon as the rebuild ends", got and tl.waiting == 0 and not th.is_alive())
src = open("wtest/combo_watcher.py").read()
i = src.index("    def _api_act(d):")
body = src[i:src.index("\n    def ", i + 10)]
ok("api_act takes the lock only through the capped tap lock", body.count("with act_lock():") == 2 and "with alock:" not in body)
ok("a timed-out tap answers 'busy', nothing done", "except ActBusy:" in src and "Nothing was done" in src)
ok("background Live rebuilds stand aside while a tap waits", "if ACT.waiting:" in src)

rl = W.RateLimit(10, 5)
t0 = time.time()
for _ in range(15):
    rl.take()
el = time.time() - t0
ok("shared limiter: a burst, then ~rate a second", 0.8 <= el <= 1.6, round(el, 2))
ok("shared limiter: no token -> no wait when asked not to", W.RateLimit(1, 1).take() and not W.RateLimit(1, 0.5).take(wait=False))
c = W.HubCache(None)
ok("the hub's reads share one limiter (about the old pace)", isinstance(c.limit, W.RateLimit) and c.RATE <= 8
   and "self.limit.take()" in src)
