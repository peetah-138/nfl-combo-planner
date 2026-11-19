import sys, os, time, threading, re, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
tk_ev = sorted({m["event_ticker"] for m in mk})
def L(i, team): ev = tk_ev[i]; return {"ticker": f"{ev}-{team}", "event_ticker": ev, "event": ev, "side": "yes"}
bets = [
 {"ticker": "KXMVE-1", "legs": [L(0, "BOS"), L(1, "DEN"), L(2, "MIL")], "cost": 5.0, "pays": 41.2, "status": "pending", "back": 0, "week": "2026-11-17", "full_pays": 41.2, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-2", "legs": [L(0, "NYK"), L(3, "GSW"), L(1, "LAL"), L(2, "CHI")], "cost": 4.93, "pays": 980, "status": "pending", "back": 0, "week": "2026-11-17", "full_pays": 980, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-3", "legs": [L(3, "PHX"), L(1, "DEN")], "cost": 8.0, "pays": 19.5, "status": "pending", "back": 0, "week": "2026-11-17", "full_pays": 19.5, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-4", "legs": [L(0, "BOS"), L(2, "CHI")], "cost": 5.0, "pays": 22, "status": "lost", "back": 0, "week": "2026-11-12", "full_pays": 22, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-5", "legs": [L(0, "BOS"), L(1, "DEN")], "cost": 5.0, "pays": 14, "status": "won", "back": 14, "week": "2026-11-17", "full_pays": 14, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-6", "legs": [L(3, "PHX"), L(2, "MIL")], "cost": 6.0, "pays": 30, "status": "cashed", "back": 11.4, "week": "2026-11-17", "full_pays": 30, "lg": "nba", "lgs": ["nba"]}]
def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: (bets, 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    A.MINE["cash"]["KXMVE-3"] = {"rfq": "r", "quote": "q", "offer": 15.8, "price": .81, "contracts": 19.5, "frac": 1.0, "at": time.time() + 3600}
    A.MINE["cash"]["KXMVE-1"] = {"rfq": "estimate", "offer": 9.1, "frac": 1.0, "at": time.time()}
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); time.sleep(3)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
VW, VH = int(os.environ.get("VW", 1440)), int(os.environ.get("VH", 900)); TAG = os.environ.get("TAG", "d")
with sync_playwright() as pw:
    br = pw.chromium.launch()
    SKIP = re.compile(r"Buy|Approve|Add .* to today|Cash out|Sell|Hedge|Pause|Stop buying|Restart|Turn on|I moved it|Update now|Change passcode|Remove|Turn off|Delete|Sign out|Keep|Go|Accept", re.I)
    problems = []
    for vw, vh in ((390, 844), (1400, 900)):
        pg = br.new_page(viewport={"width": vw, "height": vh}, color_scheme="dark")
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.dismiss())
        pg.goto(B + "/app"); time.sleep(5)
        for view in ("live", "games", "build", "results", "settings"):
            pg.evaluate(f"go('{view}')"); time.sleep(6 if view == "build" else 3)
            labels = pg.evaluate("""[...document.querySelectorAll('main button, main .chip, main .trow, main .pitem .x')].filter(b=>b.offsetParent).map((b,i)=>[i,(b.innerText||b.title||'').trim().slice(0,40)])""")
            clicked = 0
            for i, label in labels[:60]:
                if SKIP.search(label or ""): continue
                n0 = len(errs)
                try:
                    pg.evaluate(f"(()=>{{const b=[...document.querySelectorAll('main button, main .chip, main .trow, main .pitem .x')].filter(b=>b.offsetParent)[{i}];if(b)b.click();}})()")
                except Exception as e:
                    problems.append(f"{vw} {view} '{label}': {e}")
                time.sleep(.35); clicked += 1
                if len(errs) > n0: problems.append(f"{vw} {view} '{label}': {errs[-1]}")
                if pg.evaluate("S.view") != view: pg.evaluate(f"go('{view}')"); time.sleep(1.5)
                pg.evaluate("typeof closeModal==='function'&&closeModal()")
            print(vw, view, "clicked", clicked)
        pg.close()
    print("PROBLEMS:" if problems else "no JS errors from any button", *problems[:20], sep="\n  ")
