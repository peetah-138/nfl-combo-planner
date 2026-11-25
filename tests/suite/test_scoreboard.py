# CHECK: group=page
# Results › the profit scoreboard (#138) and smart sell's scorecard (#115), at phone size (dark and light) and desktop:
# real dollars from a seeded ledger through the real profit_board, the period switch rolls the numbers, every breakdown
# tab shows its rows, small groups say "too few to trust", the Selling tab shows each sale against holding, the empty
# state, no JS errors, no sideways scroll. SHOTS=<dir> saves screenshots.
import sys, os, time, threading, json
sys.stdout.reconfigure(line_buffering=True)          # os._exit at the end must not swallow a PROBLEMS line
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
now = time.time()
EMPTY = {"on": False}


def seed(A):
    A._ledger_table()
    kinds = [("KXMVE-%d", "combo", "nba"), ("KXNBAGAME-26NOV%02dBOSNYK-BOS", "win", "nba"), ("KXNFLSPREAD-26NOV%02dKCBUF-KC3", "spread", "nfl"),
             ("KXNHLTOTAL-26NOV%02dTORMTL-6", "total", "nhl")]
    for i in range(34):
        fmt, kind, lg = kinds[i % 4]
        t = fmt % (i + 1)
        cost = [3.1, 5.2, 8.4, 12.0][i % 4]
        won = i % 3 != 0
        sold = i % 5 == 0
        back = round(cost * (1.7 if won else 0) if not sold else cost * 1.3, 2)
        closed = now - (i % 9) * 86400 - 3600
        A.store_x("insert or replace into ledger(ticker, kind, league, side, cost, back, fees, sold_back, sell_fees, n_sold, status, opened, closed, legs, outcome, held, seen) "
                  "values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (t, kind, lg, "yes", cost, back, 0.12, back if sold else 0, 0.03 if sold else 0, 10 if sold else 0,
                                                               "sold" if sold else "won" if won else "lost", closed - 5 * 3600, closed, json.dumps([t]),
                                                               ("won" if i % 2 else "lost") if sold else None, (10.0 if i % 2 else 0.0) if sold else None, closed))
        if sold and i % 10 == 0:
            A.store_x("insert or ignore into sell_log(ts, ticker, result, why, kind, side, offer, cost, pays, frac, by, combo, outcome, held) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (closed, t, "sold", "smart", kind, "yes", back, cost, 10, 1.0, "mac", t, "won" if i % 2 else "lost", 10.0 if i % 2 else 0.0))
    for i in range(0, 34, 4):                                  # #461: combos' recorded payout, and one lost hold that traded above cost
        A.store_x("insert or ignore into bets(combo, first_seen, cost, pays, legs, status) values(?,?,?,?,?,?)", ("KXMVE-%d" % (i + 1), now - 9e5, 3.1, 12.4, "[]", "pending"))
    A.store_x("insert into offers values(?,?,?,?,?,?,?,?)", (now - 8e4, "KXMVE-13", .3, 12.4, 1, 4.0, 1, "x"))
    A.store_x("insert into pulse values(?,?,?)", (now - 60, 23.4, 18.0))


def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    real_pb = A.profit_board
    def pb(now=None, max_age=120):
        if os.environ.get("SB_EMPTY") == "1":
            return {"at": time.time(), "n": 0, "periods": {}, "curve": [], "open": None, "scorecard": {}}
        if not A.STORE.get("seeded"):
            A.STORE["seeded"] = True
            seed(A)
        return real_pb(now, max_age)
    A.profit_board = pb
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
SHOTS = os.environ.get("SHOTS")
P = []
def bad(*a): P.append(" ".join(str(x) for x in a)); print("PROBLEMS:", *a)
def wait(pg, js, secs=30):
    t = time.time()
    while time.time() - t < secs:
        try:
            if pg.evaluate(js): return True
        except Exception: pass
        time.sleep(.1)
    return False
AN = {"at": now - 60, "levels": [], "types": [], "sports": [], "exits": [], "auto": {}, "tuning": [],
      "smart_buy": {"on": True, "rows": [], "calib": [], "gate": [{"name": "NBA", "state": "active", "level": 2, "skipped": 7, "saved": 3.4, "own": 40, "need": 30, "optin": {}}]}}
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme, vw, vh in (("dark", 390, 844), ("light", 390, 844), ("dark", 1280, 900)):
        pg = br.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=2, color_scheme=scheme)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/app/api/analytics", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(AN)))
        pg.goto(B + "/app"); pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=30000)
        pg.evaluate("go('results')")
        if not wait(pg, "!!document.querySelector('.pb .pbbig')", 40): bad(scheme, vw, "scoreboard didn't appear"); continue
        tag = f"{scheme}-{vw}"
        t = pg.locator(".pb").inner_text().lower()
        for want in ("Profit scoreboard", "after", "Kalshi fees", "Days up", "Best day", "Worst day", "Open bets, not counted above", "≈ $23",
                     "Smart Sell vs holding", "Smart Buy skips", "saved $3.40", "Running total"):
            if want.lower() not in t: bad(tag, "scoreboard misses", repr(want))
        if pg.locator(".kpis .kpi").count(): bad(tag, "the old combo-only KPI row still shows next to the scoreboard")
        if vw < 500:
            pg.locator(".pb .seg.pbr button", has_text="All time").click()
            wait(pg, "document.querySelector('.pb .seg.pbr button.on').innerText.includes('All time')", 5)
            if SHOTS: time.sleep(1.0); pg.locator(".pb").screenshot(path=os.path.join(SHOTS, f"scoreboard-top-{tag}.png"))
            for tab, want in (("Bet type", "Combos"), ("League", "NBA"), ("How it ended", "Held to the end: won"), ("Source", "You, on Kalshi"),
                              ("Price quality", "Prices vs the close"), ("Stake", "$5–10")):
                pg.locator(".pb .seg.pbt button", has_text=tab).click()
                if not wait(pg, "(document.querySelector('.pb .pbb')||{innerText:''}).innerText.includes(%s)" % json.dumps(want), 5): bad(tag, "tab", tab, "didn't show", want)
                if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(tag, "tab", tab, "scrolls sideways")
                if pg.evaluate("[...document.querySelectorAll('.pb .seg.pbt button')].some(b=>b.getBoundingClientRect().height>48)"): bad(tag, "breakdown tab labels wrap")
                if tab == "Bet type":
                    bt = pg.locator(".pb .pbb").inner_text()
                    if "too few to trust" not in bt: bad(tag, "small groups aren't marked too few to trust")
                    if "Too few settled bets" not in bt and "luck" not in bt: bad(tag, "no plain sentence under the breakdown")
                    if SHOTS: time.sleep(.6); pg.locator(".pb .pbb").screenshot(path=os.path.join(SHOTS, f"scoreboard-types-{tag}.png"))
                if tab == "How it ended":
                    et = pg.locator(".pb .pbb").inner_text()
                    if "vs holding" not in et: bad(tag, "How it ended has no vs holding column")
                    for want in ("Won ", "to break even", "Could have been sold higher", "traded above what you paid before closing", "small sample", "no price history"):
                        if want.lower() not in et.lower(): bad(tag, "held-to-end lines miss", repr(want))
                    if SHOTS:
                        pg.evaluate("window.scrollTo(0, document.querySelector('.pb .seg.pbt').getBoundingClientRect().top + scrollY - 70)"); time.sleep(.6)
                        pg.screenshot(path=os.path.join(SHOTS, f"held-losers-top-{tag}.png"))
                        pg.evaluate("document.querySelector('.pbhi').scrollIntoView({block:'center'})"); time.sleep(.4)
                        pg.screenshot(path=os.path.join(SHOTS, f"held-losers-lost-{tag}.png"))
            pg.locator(".pb .seg.pbr button", has_text="Week").click()
            wait(pg, "document.querySelector('.pb .seg.pbr button.on').innerText.includes('Week')", 5)
            if "this week" not in pg.locator(".pb .pbsub").inner_text(): bad(tag, "Week range doesn't say this week")
            if pg.evaluate("(()=>{try{return localStorage.getItem('cw_pbr')}catch(e){return null}})()") != "week": bad(tag, "period choice not remembered")
            pg.locator(".pb .seg.pbr button", has_text="All time").click()
            # scorecard in What's working › Selling
            pg.locator(".ant:not(.pbt) button", has_text="Selling").click()
            if not wait(pg, "!!document.querySelector('.an .sc-h')", 5): bad(tag, "Selling tab has no scorecard")
            else:
                st = pg.locator(".an").inner_text().lower()
                for want in ("Smart sell's scorecard", "from selling instead of holding", "too early", "Sales you made yourself"):
                    if want.lower() not in st: bad(tag, "scorecard misses", repr(want))
                if pg.locator(".an .sc-h ~ .antbl .anrow:not(.h)").count() < 2: bad(tag, "scorecard has no row per league and reason")
                if SHOTS: time.sleep(.6); pg.locator(".an").screenshot(path=os.path.join(SHOTS, f"scorecard-selling-{tag}.png"))
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(tag, "Results scrolls sideways")
        if errs: bad(tag, "JS errors:", errs[:3])
        pg.close()
    os.environ["SB_EMPTY"] = "1"
    pg = br.new_page(viewport={"width": 390, "height": 844}, color_scheme="dark")
    pg.goto(B + "/app"); pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=30000)
    pg.evaluate("go('results')")
    if not wait(pg, "!!document.querySelector('.pb.empty')", 30): bad("empty state missing")
    elif "fills in here as your bets settle" not in pg.locator(".pb.empty").inner_text(): bad("empty state words")
    if SHOTS: pg.locator(".pb.empty").screenshot(path=os.path.join(SHOTS, "scoreboard-empty-dark-390.png"))
    br.close()
print("PASS scoreboard page" if not P else "FAIL scoreboard page")
os._exit(0)
