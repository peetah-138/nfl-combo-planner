"""Simulated Mac: the real watcher (main loop, hub, shadow, panel, history, updates) against fake Kalshi/ESPN/
GitHub for ~60 seconds with sleeps sped up. Fails on any 'failed', 'skipped', 'Traceback' or error in the log,
and checks that a newer version on GitHub gets installed."""
import os, sys, json, shutil, tempfile, threading, datetime as dt, re, importlib.util, traceback
SP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.environ.get("REPO") or os.path.dirname(os.path.dirname(SP))
home = tempfile.mkdtemp(prefix="macsim")
os.environ["COMBOWATCH_HOME"] = home
shutil.copy(f"{REPO}/nfl_combo_planner.py", f"{home}/engine.py")
for f in ("combo_settings.json", "kalshi_private_key.pem"):
    if os.path.exists(f"{SP}/run/{f}"):
        shutil.copy(f"{SP}/run/{f}", f"{home}/{f}")
s = json.load(open(f"{home}/combo_settings.json")); s.update(kalshi_key_id="fake-key-id", auto_sell=True, odds_key="")
s["kalshi_key_file"] = f"{home}/kalshi_private_key.pem"
json.dump(s, open(f"{home}/combo_settings.json", "w"))
json.dump({"topic": "t", "secret": "s", "hub_port": 8797, "webapp": False, "shadow": True, "auto_update": True, "hub": True},
          open(f"{home}/watcher.json", "w"))
VERSION = re.search(r'^VERSION = "([^"]+)"', open(f"{REPO}/nfl_combo_planner.py").read(), re.M).group(1)
import requests
now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
mk = []
def add(series, day, a, b, pa, hrs):
    ev = f"{series}-{day.strftime('%y%b%d').upper()}{a}{b}"
    exp = (now + dt.timedelta(hours=hrs)).isoformat() + "Z"
    for t, p in ((a, pa), (b, 1 - pa)):
        mk.append({"ticker": f"{ev}-{t}", "event_ticker": ev, "yes_sub_title": t, "yes_ask_dollars": f"{p + .02:.2f}",
                   "yes_bid_dollars": f"{p:.2f}", "last_price_dollars": f"{p:.2f}", "expected_expiration_time": exp, "status": "active"})
d0 = dt.date.today()
for i, (a, b) in enumerate([("BOS", "NYK"), ("DEN", "LAL"), ("MIL", "CHI")]):
    add("KXNBAGAME", d0, a, b, .6 - .05 * i, 5 + i)
for i, (a, b) in enumerate([("COL", "SJ"), ("VGK", "DAL")]):
    add("KXNHLGAME", d0, a, b, .62 - .05 * i, 4 + i)
sun = d0 + dt.timedelta(days=(6 - d0.weekday()) % 7)
for i, (a, b) in enumerate([("BUF", "KC"), ("DET", "GB"), ("SF", "SEA"), ("PHI", "DAL")]):
    add("KXNFLGAME", sun, a, b, .55 + .04 * i, 24 * ((sun - d0).days) + 3 + 3 * (i % 2))
GH = {"v": VERSION + "9" if os.environ.get("UPD") else VERSION}
class R:
    def __init__(s, o, code=200, raw=None):
        s._o, s.status_code, s.ok = o, code, code < 400
        s.content = raw if raw is not None else json.dumps(o).encode(); s.text = s.content.decode(); s.headers = {}
    def json(s): return s._o
    def raise_for_status(s): pass
    def iter_lines(s, *a, **k): real_sleep(1); return iter(())
    def __enter__(s): return s
    def __exit__(s, *a): return False
CALLS = []
def fake(method, url, params=None, data=None, json_=None, **k):
    CALLS.append((method, url.split("?")[0][-60:]))
    if url.startswith("http://127.0.0.1"): raise requests.ConnectionError("no local servers in this test")
    if "raw.githubusercontent" in url or "github" in url:
        if "api.github.com" in url and "/commits/" in url: return R(None, raw=b"0123456789abcdef0123456789abcdef01234567")
        if url.endswith("version.txt"): CALLS.append(("SHA", "pinned" if "/0123456789abcdef" in url else "main")); return R(None, raw=GH["v"].encode())
        if url.endswith("nfl_combo_planner.py"): return R(None, raw=open(f"{REPO}/nfl_combo_planner.py").read().replace(f'VERSION = "{VERSION}"', f'VERSION = "{GH["v"]}"').encode())
        if url.endswith("combo_watcher.py"): return R(None, raw=open(f"{REPO}/watcher/combo_watcher.py").read().replace(f'WATCHER_VERSION = "{VERSION}"', f'WATCHER_VERSION = "{GH["v"]}"').encode())
        return R({}, 404)
    if "kalshi" in url:
        path = url.split("/trade-api/v2")[-1].split("?")[0]
        if path.startswith("/markets") and method == "GET":
            st = (params or {}).get("series_ticker", "")
            if path.count("/") >= 2:
                tk = path.split("/")[2]; m = next((x for x in mk if x["ticker"] == tk), None)
                return R({"market": m} if m else {}, 200 if m else 404)
            return R({"markets": [m for m in mk if st and m["ticker"].startswith(st)], "cursor": ""})
        if path == "/portfolio/balance": return R({"balance": 20000})
        if path.startswith("/portfolio"): return R({"fills": [], "settlements": [], "positions": [], "market_positions": [], "event_positions": [], "orders": [], "cursor": ""})
        if path.startswith("/communications"): return R({"rfqs": [], "quotes": []})
        if path.startswith("/multivariate") or path.startswith("/series") or path.startswith("/events"):
            return R({"multivariate_contracts": [], "series": [], "events": [], "cursor": ""})
        return R({})
    if "espn" in url: return R({"events": []})
    if "ntfy" in url: return R({"id": "x", "event": "message"})
    return R({})
requests.get = lambda url, params=None, **k: fake("GET", url, params=params, **k)
requests.post = lambda url, data=None, json=None, **k: fake("POST", url, data=data, **k)
requests.put = lambda url, data=None, **k: fake("PUT", url, data=data, **k)
requests.delete = lambda url, **k: fake("DELETE", url, **k)
requests.request = lambda method, url, params=None, data=None, **k: fake(method, url, params=params, data=data, **k)
class FakeSession:
    def __init__(s, *a, **k): s.headers = {}
    def get(s, url, **k): return requests.get(url, **k)
    def post(s, url, **k): return requests.post(url, **k)
    def request(s, m, url, **k): return requests.request(m, url, **k)
    def mount(s, *a): pass
    def close(s): pass
requests.Session = FakeSession
import time as T
real_sleep = T.sleep
T.sleep = lambda x: real_sleep(min(x, 0.2))
LOG = []
shutil.copy(f"{REPO}/watcher/combo_watcher.py", f"{home}/combo_watcher.py")   # never let a test touch the repo
sys.argv = [f"{home}/combo_watcher.py"]
spec = importlib.util.spec_from_file_location("W", f"{home}/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
W.log = lambda *a: LOG.append(" ".join(str(x) for x in a))
W.start_webapp = lambda: None
EXITS = []
W.os._exit = lambda c: (EXITS.append(c), (_ for _ in ()).throw(SystemExit(c)))
RET = {}
def run():
    try:
        RET["code"] = W.main()
    except SystemExit as e:
        RET["code"] = f"exit {e.code}"
    except Exception:
        RET["crash"] = traceback.format_exc()
th = threading.Thread(target=run, daemon=True); th.start()
if not os.environ.get("UPD"):                       # a "Build a fresh panel" tap: the rebuild thread starts it at once
    real_sleep(8); open(f"{home}/panel_rebuild.flag", "w").close(); ASKED = T.time()
real_sleep(int(os.environ.get("SECS", 45)))
for _ in range(60):
    if not th.is_alive() or EXITS: break
    real_sleep(1)
bad = [l for l in LOG if re.search(r"failed|skipped|Traceback|Error|refused", l, re.I)
       and not re.search(r"no local servers|sportsbook|odds", l, re.I)]
print("started:", any("started" in l for l in LOG), "| main loop ran:", sum(1 for c in CALLS if "/portfolio/balance" in c[1]), "balance reads")
print("panel/shadow ran:", any("panel" in l.lower() for l in LOG) or "quiet (no qualifying bets is fine)")
print("update installed:", any("updated to" in l for l in LOG), "| exited for restart:", bool(EXITS) or RET.get("code"))
print("watcher file now:", re.search(r'^WATCHER_VERSION = "([^"]+)"', open(f"{home}/combo_watcher.py").read(), re.M).group(1))
print("engine file now:", re.search(r'^VERSION = "([^"]+)"', open(f"{home}/engine.py").read(), re.M).group(1))
if not os.environ.get("UPD"):
    rb = [l for l in LOG if l.startswith("panel rebuild:")]
    print("rebuild on request:", rb[:1] or "never ran", "| flag cleared:", not os.path.exists(f"{home}/panel_rebuild.flag"))
    if not rb: print("PROBLEMS: a requested rebuild never ran")
if RET.get("crash"): print("CRASH:\n" + RET["crash"])
print("PROBLEMS:" if bad else "no problems in the log", *bad[:15], sep="\n  ")
if os.environ.get("UPD"):
    pins = [c[1] for c in CALLS if c[0] == "SHA"]
    print("update read the newest commit:", pins[:3])
    if not pins or pins[0] != "pinned": print("PROBLEMS: update check didn't read the newest commit")
