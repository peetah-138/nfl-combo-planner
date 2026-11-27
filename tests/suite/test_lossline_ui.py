# CHECK: group=page secs=30
"""Smart sell as one block on a pending combo card: a "Take profit" line and a "Loss cut" line, in plain words, at phone
width, dark and light (display only; the server words are scripted at the page). Saves screenshots (SHOTS dir, if set)."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("SHOTS") or ""
from playwright.sync_api import sync_playwright
def bad(m): print("PROBLEMS:", m)
def shot(pg, name):
    if SHOTS:
        for n, k in ((1, 0), (2, 3)):   # cards 1-3, then 4-5, scrolled under the sticky header
            pg.evaluate("(k=>{const r=document.querySelectorAll('.sslines')[k];r&&window.scrollTo(0,r.getBoundingClientRect().top+scrollY-150)})(" + str(k) + ")")
            time.sleep(.3)
            pg.screenshot(path=os.path.join(SHOTS, name.replace(".png", f"_{n}.png")))
LEG = {"ticker": "KXNBAGAME-X-BOS", "name": "Celtics", "opp": "Knicks", "chance": .4, "live": .4, "res": None,
       "state": "live", "phase": "on", "note": "", "short": "", "score": "", "sc": None, "src": "", "starts": "",
       "sport": "nba", "side": "yes", "url": ""}
def card(i, label, p, profit, loss, chip):
    return {"t": f"KXMVE-{i}", "i": i, "label": label, "group": "pending", "kind": "playing", "sports": ["nba"],
            "p": p, "pays": 13, "cost": 6, "back": 0, "live": True, "hold_value": 3.0, "won_some": False,
            "offer": 2.4, "offer_real": True, "offer_live": None, "fair_value": 3.0, "overpay": 0, "offer_age": 5,
            "verdict": "hold", "why": "", "threshold": None, "thr_over": True, "moment": None, "hedge": None,
            "self": False, "own": False, "legs": [LEG], "smart_txt": "x", "smart_at": 7.0, "smart_over": False,
            "smart_chip": chip, "smart_state": "", "smart_profit": profit, "loss_chip": loss}
CARDS = [
    card(1, "Celtics and Knicks", .11, "Take profit: waiting, win chance 11% is below the 50% needed", "Loss cut: off (this league hasn't earned it yet)", "waiting, win chance 11% is below the 50% needed"),
    card(2, "Lakers and Suns", .38, "Take profit: waiting, win chance 38% is below the 50% needed", "Loss cut: waiting for half the game", "waiting, win chance 38% is below the 50% needed"),
    card(3, "Bucks and Heat", .7, "Take profit: waiting, offer $4.10 is below the $7.00 it sells at", "Loss cut: armed at 20% win chance", "waiting, offer $4.10 is below the $7.00 it sells at"),
    card(4, "Nets and Jazz", .15, "Take profit: off (Auto cash-out is off in Settings)", "Loss cut: off (Auto cash-out is off in Settings)", ""),
    card(5, "Kings and Hawks", .3, "Take profit: won't sell now (paused)", "Loss cut: armed at 20% win chance (Pause is on, nothing sells)", "won't sell now (paused)"),
]
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=scheme, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(B + "/app"); pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=30000)
        __import__("upwait").go_and_hold(pg, "live")
        pg.evaluate("(cs=>{if(!S.live||S.live.error)S.live={at:Date.now()/1000,combos:[],riding:0,staked:0,chance_one:0,best:0,cash_now:0,today:{}};S.live.singles=[];S.live.auto_sell=true;S.filter='all';S.live.combos=cs;renderLive()})(" + json.dumps(CARDS) + ")")
        time.sleep(.6)
        blocks = pg.evaluate("[...document.querySelectorAll('.sslines')].map(e=>e.innerText)")
        btns = pg.evaluate("[...document.querySelectorAll('.trow .ss')].map(e=>e.innerText)")
        print(scheme, blocks, btns)
        if len(blocks) != 5 or not all("Take profit:" in b and "Loss cut:" in b for b in blocks):
            bad(f"{scheme}: every pending combo shows both Smart sell lines ({blocks})")
        if "this league hasn't earned it yet" not in blocks[0] or "waiting for half the game" not in blocks[1] or "armed at 20%" not in blocks[2]:
            bad(f"{scheme}: loss states are wrong ({blocks})")
        if any("win chance" in b or "needs" in b for b in btns) or not all(b.strip().endswith("Smart sell") for b in btns):
            bad(f"{scheme}: the Smart sell button is just the name once the two lines exist ({btns})")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
            bad(f"{scheme}: the page scrolls sideways")
        shot(pg, f"smart_sell_lines_{scheme}.png")
        print(scheme, "JS errors:", errs)
        ctx.close()
    br.close()
