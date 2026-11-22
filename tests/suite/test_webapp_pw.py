# CHECK: group=none
import sys, os, json, time, threading, datetime as dt, re
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
import requests
today = dt.date.today(); tk = today.strftime("%y%b%d").upper()
exp = (dt.datetime.utcnow() + dt.timedelta(hours=6)).isoformat() + "Z"
mk = []
for a, b, an, bn, pa in [("BOS", "NYK", "Boston Celtics", "New York Knicks", .62), ("DEN", "LAL", "Denver Nuggets", "Los Angeles Lakers", .70),
                         ("MIL", "CHI", "Milwaukee Bucks", "Chicago Bulls", .58), ("PHX", "GSW", "Phoenix Suns", "Golden State Warriors", .55)]:
    ev = f"KXNBAGAME-{tk}{a}{b}"
    for t, n, p in ((a, an, pa), (b, bn, 1 - pa)):
        mk.append({"ticker": f"{ev}-{t}", "event_ticker": ev, "yes_sub_title": n, "yes_ask_dollars": f"{p + 0.02:.2f}",
                   "yes_bid_dollars": f"{p:.2f}", "expected_expiration_time": exp, "status": "active"})
class R:
    def __init__(s, o, code=200): s._o, s.status_code, s.ok, s.text, s.content, s.headers = o, code, code < 400, json.dumps(o), json.dumps(o).encode(), {}
    def json(s): return s._o
    def raise_for_status(s): pass
real_get = requests.get
def fake_get(url, params=None, **k):
    if url.startswith("http://127.0.0.1"): return real_get(url, params=params, **k)
    if "kalshi" in url and "/markets" in url:
        st = (params or {}).get("series_ticker", "")
        return R({"markets": [m for m in mk if m["ticker"].startswith(st)] if st else [], "cursor": ""})
    if "github" in url: return R({}, 404)
    return R({"events": [], "markets": []})
requests.get = fake_get
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start()
time.sleep(2)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844})
    pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/app"); time.sleep(10)
    def shot(name):
        pg.screenshot(path=f"wa_{name}.png"); t = pg.evaluate("document.body.innerText")[:160].replace("\n", " | ")
        print(name, "->", t)
    shot("start")
    pg.click("#cwbar button:has-text('Build')"); time.sleep(6)
    pg.click("text=NBA"); time.sleep(7); shot("nba")
    b = pg.locator("button:has-text('Build combos'), a:has-text('Build combos'), .btn:has-text('Build combos')").last
    b.click(); time.sleep(14); shot("built")
    print("Get-offer buttons:", pg.locator("text=/Get offer|New price|Get Kalshi/").count())
    br.close()
