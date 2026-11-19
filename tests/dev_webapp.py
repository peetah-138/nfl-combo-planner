"""The dev web app: the real planner app (watcher.webapp_main) on http://127.0.0.1:18800/app, running against a fake
internet (tests/suite/fakenet.py) with a few seeded bets. Start it with ./dev.sh, not directly: dev.sh makes the
throwaway home folder this checks for. Safe by construction, see DEV.md:
  - refuses to run unless COMBOWATCH_HOME is a throwaway folder dev.sh made (never ~/combowatch)
  - refuses ports 8765/8766 and a busy port
  - no Kalshi key anywhere, so trading is impossible, and no hub, so nothing is routed to the real one
  - every outgoing request is answered from memory; any local address except this app's own is refused"""
import os, sys, json, time, socket, shutil, threading, importlib.util

HOME = os.path.realpath(os.environ.get("COMBOWATCH_HOME") or "")
PORT = int(os.environ.get("CW_WEBAPP_PORT") or 0)
REAL = os.path.realpath(os.path.expanduser("~/combowatch"))
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def die(msg):
    print("dev environment refused to start:", msg, file=sys.stderr)
    sys.exit(2)


if not HOME or HOME == REAL or HOME.startswith(REAL + os.sep) or REAL.startswith(HOME + os.sep):
    die(f"COMBOWATCH_HOME must be a throwaway folder made by dev.sh, not {HOME or 'unset'}")
if not os.path.basename(HOME).startswith("combodev.") or not os.path.exists(os.path.join(HOME, ".devhome")):
    die(f"{HOME} is not a dev home (no .devhome marker). Use ./dev.sh")
if PORT in (0, 8765, 8766) or not 1024 <= PORT <= 65535:
    die(f"CW_WEBAPP_PORT must be a free dev port (not 8765/8766), got {PORT or 'unset'}")
with socket.socket() as s:
    if s.connect_ex(("127.0.0.1", PORT)) == 0:
        die(f"port {PORT} is already in use")
for f in ("kalshi_private_key.pem", "combo_keys.json"):
    if os.path.exists(os.path.join(HOME, f)):
        die(f"{f} found in the dev home: no Kalshi keys allowed here")
if json.load(open(os.path.join(HOME, "combo_settings.json"))).get("kalshi_key_id"):
    die("combo_settings.json has a kalshi_key_id: trading must be impossible in dev")

sys.path.insert(0, os.path.join(HERE, "suite"))
import requests, fakenet
fakenet.install(PORT)
os.environ["COMBOWATCH_NTFY"] = "http://127.0.0.1:9"      # notifications go nowhere (and the fake refuses it anyway)

shutil.copy(os.path.join(REPO, "watcher", "combo_watcher.py"), os.path.join(HOME, "combo_watcher.py"))   # never run from the repo path
sys.argv = [os.path.join(HOME, "combo_watcher.py"), "--webapp"]
spec = importlib.util.spec_from_file_location("W", os.path.join(HOME, "combo_watcher.py"))
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)
assert W.HOME == HOME and W.WEBAPP_PORT == PORT, "watcher is not using the dev home/port"

ev = {s: sorted({m["event_ticker"] for m in fakenet.markets() if m["event_ticker"].startswith(s)}) for s in fakenet.GAMES}
nba, nhl = ev["KXNBAGAME"], ev["KXNHLGAME"]


def leg(events, i, team):
    return {"ticker": f"{events[i]}-{team}", "event_ticker": events[i], "event": events[i], "side": "yes"}


today = time.strftime("%Y-%m-%d")
BETS = [
    {"ticker": "KXMVE-1", "legs": [leg(nba, 0, "BOS"), leg(nba, 1, "DEN"), leg(nba, 2, "MIL")], "cost": 5.0, "pays": 41.2, "status": "pending", "back": 0, "week": today, "full_pays": 41.2, "lg": "nba", "lgs": ["nba"]},
    {"ticker": "KXMVE-2", "legs": [leg(nba, 0, "NYK"), leg(nba, 3, "GSW"), leg(nba, 1, "LAL"), leg(nba, 2, "CHI")], "cost": 4.93, "pays": 980, "status": "pending", "back": 0, "week": today, "full_pays": 980, "lg": "nba", "lgs": ["nba"]},
    {"ticker": "KXMVE-3", "legs": [leg(nhl, 0, "COL"), leg(nhl, 1, "VGK")], "cost": 8.0, "pays": 19.5, "status": "pending", "back": 0, "week": today, "full_pays": 19.5, "lg": "nhl", "lgs": ["nhl"]},
    {"ticker": "KXMVE-4", "legs": [leg(nba, 0, "BOS"), leg(nba, 2, "CHI")], "cost": 5.0, "pays": 22, "status": "lost", "back": 0, "week": "2026-11-12", "full_pays": 22, "lg": "nba", "lgs": ["nba"]},
    {"ticker": "KXMVE-5", "legs": [leg(nba, 0, "BOS"), leg(nba, 1, "DEN")], "cost": 5.0, "pays": 14, "status": "won", "back": 14, "week": today, "full_pays": 14, "lg": "nba", "lgs": ["nba"]},
    {"ticker": "KXMVE-6", "legs": [leg(nba, 3, "PHX"), leg(nba, 2, "MIL")], "cost": 6.0, "pays": 30, "status": "cashed", "back": 11.4, "week": today, "full_pays": 30, "lg": "nba", "lgs": ["nba"]},
]

real_load = W.load_engine
ENGINE = []


def load():
    A = real_load()
    ENGINE.append(A)
    A.fetch_account = lambda max_age=60, every_league=False: (BETS, 211.03, "dev")     # seeded bets, never the account
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    A.hub_call = lambda *a, **k: None                       # no hub, ever
    A.MINE["cash"]["KXMVE-3"] = {"rfq": "estimate", "offer": 15.8, "price": .81, "contracts": 19.5, "frac": 1.0, "at": time.time()}
    return A


W.load_engine = load
URL = f"http://127.0.0.1:{PORT}/app"


def announce():
    time.sleep(3)
    A = ENGINE[0]
    if A.hub_conf() or A.can_trade():      # last check on the two things that must never be true here
        print("DEV SAFETY CHECK FAILED: hub configured or trading possible. Stopping.", file=sys.stderr, flush=True)
        os._exit(3)
    print(f"DEV ENVIRONMENT READY: {URL}  (fake data, trading impossible, no hub, home {HOME})", flush=True)


threading.Thread(target=announce, daemon=True).start()
sys.exit(W.webapp_main() or 0)
