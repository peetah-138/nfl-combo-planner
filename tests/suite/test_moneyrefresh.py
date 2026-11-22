# CHECK: group=page secs=25
"""Issue #242: after a sale (or any money event) Live and Results catch up within seconds. Through the real web app:
a cashed-out combo stays on Live while the snapshot and the account cache are fresh (the bug), and leaves on the very
next read once the watcher's "money moved" stamp is newer; Results reads the account again too; with no new stamp
nothing is rebuilt. In the page: a Mac tick carrying a newer stamp reads the screen on show again (Results included),
the same stamp twice does not, an open sheet waits; a Sold moment for a sale the Mac made re-reads Live a few seconds
later. The account is scripted; nothing real is touched."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
tk_ev = sorted({m["event_ticker"] for m in mk})
def L(i, team): ev = tk_ev[i]; return {"ticker": f"{ev}-{team}", "event_ticker": ev, "event": ev, "side": "yes"}
bets = [{"ticker": "KXMVE-1", "legs": [L(0, "BOS"), L(1, "DEN")], "cost": 5.0, "pays": 41.2, "status": "pending", "back": 0,
         "week": time.strftime("%Y-%m-%d"), "full_pays": 41.2, "lg": "nba", "lgs": ["nba"]}]
state = {"reads": 0}
def acct():
    state["reads"] += 1
    return [dict(b) for b in bets], 211.03, "test"
def load():
    A = real_load()
    state["A"] = A
    A._fetch_account = acct                 # the real fetch_account and its 60 s cache stay in place
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    A.open_singles = lambda max_age=30: []
    A.MONEY_FLAG = os.path.join(os.path.abspath("."), "combo_money_test.json")
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
H = {"X-CW": "x"}
P = []
def problem(m): P.append(m); print("PROBLEMS:", m)
def group(d, t="KXMVE-1"):
    return next((c.get("group") for c in (d.get("combos") or []) if c.get("t") == t), None)

d0 = requests.get(B + "/app/api/live?fresh=1", headers=H).json()
print("before the sale:", group(d0))
if group(d0) != "pending": problem(f"the combo should start pending: {group(d0)}")
bets[0].update(status="cashed", back=9.1)
d1 = requests.get(B + "/app/api/live", headers=H).json()
print("sold, no stamp (the old behaviour: cached):", group(d1))
time.sleep(.05)
state["A"].money_mark()                      # what the watcher does when it sells
d2 = requests.get(B + "/app/api/live", headers=H).json()
print("after the stamp:", group(d2), "| built moved:", d2["fresh"]["built"] > d1["fresh"]["built"])
if group(d2) != "cashed": problem(f"the sold combo is still shown after the stamp: {group(d2)}")
d3 = requests.get(B + "/app/api/live", headers=H).json()
if d3["fresh"]["built"] != d2["fresh"]["built"]: problem("a read with no new stamp rebuilt Live")
r0 = requests.get(B + "/app/api/results", headers=H).json()
bets.append({"ticker": "KXMVE-2", "legs": [L(0, "BOS")], "cost": 4.0, "pays": 9.0, "status": "lost", "back": 0,
             "week": "2026-11-17", "full_pays": 9.0, "lg": "nba", "lgs": ["nba"]})
r1 = requests.get(B + "/app/api/results", headers=H).json()
time.sleep(.05); state["A"].money_mark()
r2 = requests.get(B + "/app/api/results", headers=H).json()
print("results settled:", r0.get("settled"), r1.get("settled"), r2.get("settled"))
if r2.get("settled") != (r0.get("settled") or 0) + 1: problem("Results didn't read the account again after the stamp")

from playwright.sync_api import sync_playwright
def until(pg, js, secs=8):
    end = time.time() + secs
    while time.time() < end:
        try:
            if pg.evaluate(js): return True
        except Exception: pass
        time.sleep(.1)
    return False
def wait(f, secs=8):
    end = time.time() + secs
    while time.time() < end:
        if f(): return True
        time.sleep(.1)
    return False
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    seen = []; pg.on("request", lambda r: seen.append(r.url.split("/app/api/")[-1].split("?")[0]) if "/app/api/" in r.url else None)
    pg.goto(B + "/app")
    until(pg, "!!(S.live&&S.liveNet)", 25)
    pg.evaluate("go('results')"); until(pg, "!!S.res", 10); time.sleep(.5)
    pg.evaluate("moneyTick(1000)")           # the first tick only sets the baseline
    n = seen.count("results"); time.sleep(.6)
    if seen.count("results") != n: problem("the first tick re-read Results")
    pg.evaluate("moneyTick(2000)")
    got = wait(lambda: seen.count("results") > n)
    print("Results re-read on a newer stamp:", got)
    if not got: problem("a newer money stamp didn't re-read Results")
    n = seen.count("results"); pg.evaluate("moneyTick(2000)"); time.sleep(1)
    if seen.count("results") != n: problem("the same stamp re-read Results again")
    pg.evaluate("modal('<h3 id=other>Other sheet</h3>')"); time.sleep(.3)
    n = seen.count("results"); pg.evaluate("moneyTick(3000)"); time.sleep(1)
    if seen.count("results") != n: problem("a money tick re-read Results under an open sheet")
    pg.evaluate("closeModal()"); time.sleep(.4)
    pg.evaluate("moneyTick(3000)")
    if not wait(lambda: seen.count("results") > n): problem("the waiting stamp wasn't picked up on the next tick")
    pg.evaluate("go('live')"); until(pg, "S.view==='live'", 5); time.sleep(.8)
    pg.evaluate("S._lc=0;window.__load=load;load=function(v,f){if(v==='live')S._lc++;return window.__load(v,f)}")
    pg.evaluate("liveMoments(S.live,Object.assign({},S.live,{sales:[{at:Date.now()/1000,ticker:'KXMVE-9',combo:'Celtics + Nuggets',offer:9.1,cost:5}]}))")
    sold = until(pg, "document.querySelector('#modal').classList.contains('on')", 3)
    early = pg.evaluate("S._lc")
    reread = until(pg, "S._lc>0", 12)
    print("Sold moment shown:", sold, "| Live re-read after it:", reread, "| too early:", early)
    if not sold: problem("no Sold moment for a sale the Mac made")
    if early: problem("Live was re-read at once, not a few seconds later")
    if not reread: problem("Live wasn't re-read after a sale the Mac made")
    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): problem("page scrolls sideways")
    print("errs:", errs)
    if errs: problem("JS errors")
    br.close()
print("ALL GOOD" if not P else f"{len(P)} PROBLEMS")
