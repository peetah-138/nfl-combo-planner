# CHECK: group=page secs=30
"""Results polish (display only): one money format (dollars and cents), the profit tile first with Settled folded in so nothing
wraps, win green / loss red, 44px filter and range taps, history rows result-first. Exact strings; no computed number changes."""
import sys, os, time, threading, json, re
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
from playwright.sync_api import sync_playwright
problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
HIST = [{"t": "A", "day": "2026-11-20", "week": "2026-11-16", "status": "won", "sports": ["nba"], "picks": ["Aces to win"], "cost": 5, "back": 14, "pl": 9, "sports_": []},
        {"t": "B", "day": "2026-11-21", "week": "2026-11-16", "status": "lost", "sports": ["nba"], "picks": ["Bees to win"], "cost": 54, "back": 0, "pl": -54}]
RES = {"pl": -45, "roi": -.7627, "settled": 2, "won": 1, "cashed": 0, "best": 9, "history": HIST, "weeks": [{"week": "2026-11-16", "pl": -45, "n": 2}], "board": {"n": 0}}
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, has_touch=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(B + "/app"); time.sleep(2.5)
        got = pg.evaluate("[rmoney(9),rmoney(54),rmoney(9.4),rmoney(1234.5),srmoney(9),srmoney(-54),srmoney(0),srmoney(null),rcls(-1),rcls(0)]")
        if got != ["$9.00", "$54.00", "$9.40", "$1,234.50", "+$9.00", "\u2212$54.00", "$0.00", "\u2014", "down", "up"]: bad(f"{scheme}: money format {got}")
        pg.evaluate("(r=>{S.res=r;S.an=null;S.view='results';renderResults()})(" + json.dumps(RES) + ")"); time.sleep(1.2)
        tiles = pg.evaluate("[...document.querySelectorAll('.kpis.rk .kpi')].map(k=>k.innerText.replace(/\\s+/g,' ').trim())")
        want = ["Profit / loss \u2212$45.00 2 settled combos", "Return on stake \u221276%", "Best result +$9.00", "Won 1", "Cashed out 0"]
        if tiles != want: bad(f"{scheme}: tiles {tiles}")
        if pg.evaluate("document.querySelector('.kpis.rk .rkh b').className") != "down": bad(f"{scheme}: loss tile is not red")
        hn = pg.evaluate("[...document.querySelectorAll('.hrow2 .hn')].map(k=>k.innerText.replace(/\\s+/g,' ').trim())")
        if hn != ["Result \u2212$54.00 Paid $54.00 Got back $0.00", "Result +$9.00 Paid $5.00 Got back $14.00"]: bad(f"{scheme}: history rows {hn}")
        for sel in (".hfilters .chip", ".hsort", ".plc .rng2 button"):
            for h in pg.evaluate("[...document.querySelectorAll('%s')].map(b=>Math.round(b.getBoundingClientRect().height))" % sel):
                if h < 44: bad(f"{scheme}: {sel} is {h}px tall"); break
        if pg.evaluate("document.querySelectorAll('.kpis.rk .kpi').length&&[...document.querySelectorAll('.kpis.rk .kpi')].some(k=>k.scrollWidth>k.clientWidth+1)"): bad(f"{scheme}: a tile overflows")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{scheme}: sideways scroll on Results")
        pg.evaluate("S.res=null;S.an=null;S.lerr={};renderResults()")
        if not pg.evaluate("document.querySelectorAll('#main .kpi.skel').length===5&&!!document.querySelector('#main .kpi.skel.rkh')"): bad(f"{scheme}: loading skeleton wrong")
        pg.evaluate("(r=>{S.res=r;renderResults()})(" + json.dumps(dict(RES, settled=0, history=[], board=None)) + ")")
        if pg.evaluate("!!document.querySelector('.kpis.rk')"): bad(f"{scheme}: empty results still show tiles")
        if errs: bad(f"{scheme}: JS errors {errs[:3]}")
        ctx.close()
    br.close()
print("PROBLEMS" if problems else "ALL OK", len(problems))
sys.exit(1 if problems else 0)
