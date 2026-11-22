# CHECK: group=page secs=11
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
 {"ticker": "KXMVE-5", "legs": [L(0, "BOS"), L(1, "DEN")], "cost": 5.0, "pays": 14, "status": "won", "back": 0, "week": "2026-11-10", "full_pays": 14, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-6", "legs": [L(3, "PHX"), L(2, "MIL")], "cost": 6.0, "pays": 30, "status": "cashed", "back": 11.4, "week": "2026-11-05", "full_pays": 30, "lg": "nba", "lgs": ["nba"]}]
def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: (bets, 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    A.MINE["cash"]["KXMVE-3"] = {"rfq": "r", "quote": "q", "offer": 15.8, "price": .81, "contracts": 19.5, "frac": 1.0, "at": time.time() + 3600}
    A.MINE["cash"]["KXMVE-1"] = {"rfq": "estimate", "offer": 9.1, "frac": 1.0, "at": time.time()}
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
VW, VH = int(os.environ.get("VW", 1440)), int(os.environ.get("VH", 900)); TAG = os.environ.get("TAG", "d")
AN={"at":time.time()-120,"levels":[{"band":"80–85%","n":12,"hit":0.2,"exp":0.25,"ride":-0.21,"gt":-0.15,"gt_n":10,"lab_n":3,"lab_ride":-0.4,"lab_smart":0.1},
 {"band":"95–100%","n":44,"hit":0.3,"exp":0.29,"ride":0.03,"gt":None,"gt_n":0,"lab_n":0,"lab_ride":None,"lab_smart":None}],
 "types":[{"mode":"real","what":"Spreads & totals","n":6,"won":4,"pl":3.2,"roi":0.12,"clv":0.02,"smart":0.14,"sim_n":4},{"mode":"paper","what":"Combos","n":9,"won":2,"pl":-8,"roi":-0.18,"clv":None,"smart":-0.05,"sim_n":6}],
 "live":[{"mode":"real","what":"NBA","n":3,"won":2,"pl":1.4,"roi":0.09,"clv":None,"smart":0.05,"sim_n":2}],"live_excluded":"EuroLeague, UFC and tennis games stay out once they've started.",
 "sports":[{"mode":"real","what":"NHL","n":6,"won":4,"pl":3.2,"roi":0.12,"clv":0.02,"smart":0.1,"sim_n":2}],
 "exits":[{"what":"Rode to the end","n":10,"pl":-12,"roi":-0.2},{"what":"Cashed out early","n":7,"pl":9,"roi":0.25}],"auto":{"smart":3,"lock in":1},"cut_held":{"too early in the game":2,"halftime or a break":1},"hedge_held":{"score feed stale":2,"wouldn't lock in what you paid":1},
 "tuning":[{"key":"nhl","name":"NHL","floor":1.5,"lam":1,"loss":0.15,"n":40,"own":True,"sl_prog":0.5,"sl_drop":0.2,"sl_n":0,"sl_own":False,"sl_why":""}],
 "lines":[{"lg":"nfl","name":"NFL","kind":"spread","on":True,"why":"Beat the old model on 1,001 past games","bt_games":1001,"bt_old":0.6149,"bt_new":0.6104,"live_n":12,"live_old":0.66,"live_new":0.64},
  {"lg":"nhl","name":"NHL","kind":"total","on":False,"why":"Didn't clearly beat the old model on 3,000 past games","bt_games":3000,"bt_old":0.68,"bt_new":0.679,"live_n":0,"live_old":None,"live_new":None}],
 "notes":["Combos priced 95–100% of fair have done best so far: +3% riding to the end over 44 quotes.","Not enough results yet for 80–85% (30+ each before reading much into them)."]}
SING=[{"t":"S1","kind":"spread","sport":"nfl","side":"yes","label":"KC wins by over 6.5","game":"BUF at KC","event":"E","n":10,"cost":5.2,"pays":10,"worth":7.0,"chance":0.72,"state":"live","res":None,"score":"","starts":"","how":"","url":"","own":True,"self":False,"sell_at":8.4}]
def wait(pg, js, secs=30):           # wait for a state on the page, not a fixed time (slow runners vary a lot)
    t = time.time()
    while time.time() - t < secs:
        try:
            if pg.evaluate(js): return True
        except Exception: pass
        time.sleep(.1)
    return False
def saved(key, want, secs=15):        # the Mac's copy of a setting, polled until it says `want`
    t = time.time(); v = None
    while time.time() - t < secs:
        try:
            v = __import__('requests').get(B + "/app/api/settings?lg=nba", headers={"X-CW": "x"}, timeout=5).json().get("values", {}).get(key)
        except Exception as e:
            v = "unreachable: %s" % type(e).__name__
        if v is want: break
        time.sleep(.2)
    return v
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark"); pg.add_init_script(__import__("upwait").COUNT_FETCHES)   # counts requests from the boot load on
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/app/api/analytics", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(AN)))
    pg.goto(B + "/app"); pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=30000)
    pg.evaluate("go('results')"); wait(pg, "document.querySelectorAll('.an .anrow:not(.h)').length>=2", 40)
    print("card:", pg.locator(".an").count(), "| rows:", pg.locator(".an .anrow:not(.h)").count())
    if pg.locator("text=What's working").count() != 1 or pg.locator(".an .anrow:not(.h)").count() != 2: print("PROBLEMS: analytics card missing")
    for tab, want in (("Bet types", "Spreads & totals"), ("Sports", "NHL"), ("Selling", "Cashed out early")):
        pg.locator(".ant button", has_text=tab).click(); wait(pg, "(document.querySelector('.an')||{innerText:''}).innerText.includes(%s)" % json.dumps(want), 5)
        if pg.locator(".an", has_text=want).count() != 1: print("PROBLEMS: tab", tab, "didn't show", want)
    pg.locator(".ant button", has_text="Bet types").click(); wait(pg, "(document.querySelector('.an')||{innerText:''}).innerText.includes('Bought during the game')", 5)
    lt = pg.locator(".an").inner_text()
    if "Bought during the game, by league" not in lt or "NBA" not in lt or "EuroLeague, UFC and tennis" not in lt:
        print("PROBLEMS: bets bought during games aren't their own group by league in What's working:", lt[-300:])
    if "Spreads & totals: old vs new pricing" not in lt or "0.615 → 0.610" not in lt or "(1,001)" not in lt or "Beat the old model" not in lt \
            or "Didn't clearly beat" not in lt or pg.locator(".an .tag.good", has_text="New").count() != 1:
        print("PROBLEMS: Results › What's working doesn't show spreads/totals old vs new with sample sizes and which model is on:", lt[-500:])
    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): print("PROBLEMS: Bet types tab scrolls sideways on a phone")
    pg.locator(".ant button", has_text="Selling").click(); wait(pg, "!!document.querySelector('.an .cut-held')", 5)
    if pg.locator(".an", has_text="3 smart").count() != 1: print("PROBLEMS: auto-sale counts missing")
    ch = pg.locator(".an .cut-held").inner_text()
    if "2 too early in the game" not in ch or "1 halftime or a break" not in ch: print("PROBLEMS: loss cuts held back by the guards missing:", ch)
    hh = pg.locator(".an .hedge-held").inner_text()
    if "Auto-hedges the guards held back" not in hh or "3" not in hh or "2 score feed stale" not in hh or "fresh live score" not in hh: print("PROBLEMS: auto-hedges held back by the guards missing:", hh)
    sel = pg.locator(".an").inner_text()
    if "late, confirmed" not in sel or "Selling at a loss (a learned cut" not in sel or "after 50% of the game" not in sel:
        print("PROBLEMS: the loss cut's guards aren't shown in Results > Selling")
    pg.locator(".ant button", has_text="Combo price levels").click(); time.sleep(.3)
    pg.locator(".an").scroll_into_view_if_needed(); pg.locator(".an").screenshot(path="an_phone.png")
    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): print("PROBLEMS: Results scrolls sideways on a phone")
    pg.evaluate("go('settings')"); wait(pg, "[...document.querySelectorAll('label.srow')].some(e=>e.innerText.includes('Smarter spread/total pricing'))", 40)
    row = pg.locator("label.srow", has_text="Include games already under way")
    if row.count() != 1 or not row.locator("input").is_checked() or "EuroLeague" not in row.inner_text():
        print("PROBLEMS: Settings › Money has no 'Include games already under way' switch (on by default, naming the leagues left out)")
    else:
        row.locator("input").click(); v = saved("panel_live", False)
        if v is not False: print("PROBLEMS: turning off 'Include games already under way' didn't save:", v)
        row.locator("input").click()
        if saved("panel_live", True) is not True: print("PROBLEMS: turning 'Include games already under way' back on didn't save")
    row = pg.locator("label.srow", has_text="Smarter spread/total pricing")
    if row.count() != 1 or not row.locator("input").is_checked() or "beaten the old model" not in row.inner_text():
        print("PROBLEMS: Settings › Money has no 'Smarter spread/total pricing' switch (auto by default)")
    else:
        row.locator("input").click(); v = saved("line_model", False)
        if v is not False: print("PROBLEMS: turning off 'Smarter spread/total pricing' didn't save:", v)
        row.locator("input").click(); time.sleep(1.5)
    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): print("PROBLEMS: Settings scrolls sideways on a phone")
    # Smart Buy (issue #137 stage 2): a switch in Settings › Money, on by default; on = a folded card in What's working
    row = pg.locator("label.srow", has_text="Smart Buy")
    if row.count() != 1 or not row.locator("input").is_checked() or "Skips bets that are unlikely to be profitable" not in row.inner_text() \
            or "keeps learning from every result" not in row.inner_text() or "preview" in row.inner_text():
        print("PROBLEMS: Settings › Money has no 'Smart Buy' switch (on by default, saying it skips unlikely bets and keeps learning)")
    else:
        row.locator("input").click(); v = saved("smart_buy_gate", False)
        if v is not False: print("PROBLEMS: turning off 'Smart Buy' didn't save:", v)
        row.locator("input").click()
        if saved("smart_buy_gate", True) is not True: print("PROBLEMS: turning 'Smart Buy' back on didn't save")
    SBP = {"on": False, "days": 7, "stake": 5, "markets": 42, "prices": 900,
           "rows": [{"name": "NBA", "kind": "Single games", "n": 48, "ok": 20, "p_exit": 0.52, "ev": 0.41, "sell": 25, "hold": 10},
                    {"name": "NFL", "kind": "Spreads & totals", "n": 12, "ok": 3, "p_exit": 0.31, "ev": -0.2, "sell": 2, "hold": 4}],
           "calib": [{"name": "NBA", "kind": "Single games", "n": 9, "pred": 0.5, "actual": 0.44}],
           "gate": [{"league": "nba", "name": "NBA", "state": "active", "own": 41, "need": 30, "level": 2, "from": None,
                     "skipped": 7, "saved": 12.5, "why": "the 7 bets it would skip lost $12.50 on $5 each",
                     "optin": {"n": 34, "n_need": 50, "ahead": 8.2, "days_up": 0.6, "days": 5, "clv": 0.012, "beats": True, "met": False}},
                    {"league": "nfl", "name": "NFL", "state": "learning", "own": 12, "need": 30, "level": 0, "from": None,
                     "skipped": 0, "saved": 0, "why": None,
                     "optin": {"n": 12, "n_need": 50, "ahead": -3.0, "days_up": 0.4, "days": 3, "clv": None, "beats": None, "met": False}}]}
    AN["smart_buy"] = SBP
    pg.evaluate("go('results')"); wait(pg, "document.querySelectorAll('.an .anrow:not(.h)').length>=2", 40)
    if pg.locator(".an .sbp").count(): print("PROBLEMS: the Smart Buy preview shows with its switch off")
    AN["smart_buy"] = dict(SBP, on=True); pg.evaluate("S.an=null"); pg.evaluate("load('results',true)")
    wait(pg, "!!document.querySelector('.an .sbp')", 20)
    hd = pg.locator(".an .sbp .sbh")
    if hd.count() != 1 or hd.get_attribute("aria-expanded") != "false" or "1 league active" not in hd.inner_text() \
            or pg.locator(".an .sbp .antbl").count():
        print("PROBLEMS: the Smart Buy preview isn't a folded card with the counts:", hd.inner_text() if hd.count() else "missing")
    else:
        bb = hd.bounding_box()
        if bb["height"] < 44: print("PROBLEMS: the Smart Buy preview's header is under 44pt tall:", bb)
        hd.click(); wait(pg, "!!document.querySelector('.an .sbp .antbl')", 5)
        sb = pg.locator(".an .sbp").inner_text()
        if "Predicted vs what happened" not in sb or "52%" not in sb or "too few to trust" not in sb or "Learning (12 of 30)" not in sb \
                or "Active · strictness 2 · skipped 7 · shadow saved $12.50" not in sb or "Bigger stakes: not yet · 34 of 50 settled" not in sb \
                or "It only ever skips" not in sb or "preview" in sb.lower() \
                or pg.locator(".an .sbp .sbh").get_attribute("aria-expanded") != "true":
            print("PROBLEMS: the opened Smart Buy preview doesn't show leagues, cash-out chance, sample sizes and predicted vs actual:", sb[:400])
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): print("PROBLEMS: the Smart Buy preview scrolls sideways on a phone")
    __import__("upwait").go_and_hold(pg, "live")   # waits for every load in flight, then holds still
    pg.evaluate("(s=>{S.live={at:Date.now()/1000,combos:[{t:'C',group:'pending',cost:3,pays:19,offer:2.94,offer_real:false,legs:[],sports:['tennis'],label:'Combo 3',p:.17,live:true,sort:0,verdict:'hold'}],riding:1,staked:3,chance_one:.17,best:19,cash_now:2.94,today:{},auto_sell:true,singles:s};renderLive()})("+json.dumps(SING)+")"); wait(pg, "(document.querySelector('.kpis')||{innerText:''}).innerText.includes('2 bets')", 5); time.sleep(.8)   # numbers roll ~0.65 s
    k = pg.locator(".kpis").inner_text().replace("\n"," | "); print("kpis:", k)
    if "2 bets" not in k or "$8.20" not in k or "$9.94" not in k or "$29" not in k: print("PROBLEMS: Live top numbers don't include singles")
    item = {"id": "single:X", "kind": "single", "live": True, "kick": time.time() - 1800, "buy_at": time.time(), "stake": 4,
            "chance": .7, "price": .66, "ret": .05, "legs": [{"pick": "Boston", "ticker": "X"}], "why": "w", "state": "scheduled"}
    h = pg.evaluate("c=>panelItem(c,'scheduled',true)", item)
    if "Under way" not in h or "won't buy" in h:
        print("PROBLEMS: a panel bet priced live on a game under way shows as 'Game started · won't buy':", h[:200])
    h = pg.evaluate("c=>panelItem(c,'scheduled',true)", dict(item, live=False))
    if "won't buy" not in h: print("PROBLEMS: a pre-game-priced bet on a started game no longer says it won't be bought")
    # Smart Buy's calm skipped line under the panel and the Buy ideas, with a tap to see the plain reasons
    h = pg.evaluate("()=>sbSkipLine([{text:'Bruins vs Flyers',why:'expects to lose about $0.05 per $5, even selling smartly'}],'panel')")
    if "Smart Buy skipped 1 bet · Why?" not in h or pg.evaluate("()=>sbSkipLine([],'ideas')") != "":
        print("PROBLEMS: the Smart Buy skipped line is wrong (or shows with nothing skipped):", h[:200])
    pg.evaluate("()=>{sbSkipLine([{text:'<b>x</b>',why:'w <i>y</i>'}],'ideas');sbSkipOpen('ideas')}")
    wait(pg, "!!document.querySelector('#sheet .sbrow')", 5)
    if pg.locator("#sheet .sbrow b").inner_text() != "<b>x</b>" or "still tracked" not in pg.locator("#sheet").inner_text():
        print("PROBLEMS: the Smart Buy reasons sheet doesn't list the skipped bets safely (escaped) with a plain note")
    pg.evaluate("closeModal()")
    print("errs:", errs)
