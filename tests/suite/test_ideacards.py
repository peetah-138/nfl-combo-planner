"""Live "Buy ideas" cards say which game they are for (GitHub #129): league icon + name, the matchup, start time (or the live
score), the pick in plain words, Kalshi's price vs fair, the edge, the stake and expected profit, the chance to win and how
fresh the price is. The ideas come from the real engine (saved with store_suggestion, read with live_suggestions): a
moneyline single, a spread, a total and a combo, plus an older idea with no extra fields. Checks the words on each card,
that a tap on the card body opens the game page (through the web app's real /app/api/game) while the buttons keep doing
what they did, no sideways scroll at 360/390/430 and desktop, and no JS errors. Saves screenshots (SHOTS dir, if set).
Prints PROBLEMS on any failure."""
import sys, os, time, threading, json, datetime as dt
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
AA = {}
def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    A.open_singles = lambda: []
    AA["A"] = A
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("SHOTS") or ""
from playwright.sync_api import sync_playwright
problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        try:
            if pg.evaluate(js): return True
        except Exception:
            pass
        time.sleep(.2)
    return False

A = AA["A"]
if not A.STORE.get("db"):
    A.store_open()
iso = lambda secs: (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=secs)).isoformat()
BAY, TCU = "KXNCAAFGAME-26NOV21BAYTCU-BAY", "KXNCAAFGAME-26NOV21BAYTCU-TCU"
A.PICK_NAME[BAY], A.PICK_NAME[TCU] = "Baylor Bears", "TCU Horned Frogs"
A.KICKOFF["KXNCAAFGAME-26NOV21BAYTCU"] = iso(7200)
A.KICKOFF["KXNBAGAME-26NOV21LALDEN"] = iso(3600)
A.LEAGUE["code"] = "ncaaf"
A.store_x("delete from suggestions")
ids = {}
ids["single"] = A.store_suggestion({"legs": [{"ticker": BAY, "event": "KXNCAAFGAME-26NOV21BAYTCU", "pick": "Baylor Bears", "p": .30, "fair": .40}],
                                    "fair": 25.0}, {"pays": 20.0, "stake": 6.3}, .40 / .315)
ids["spread"] = A.store_suggestion({"legs": [{"ticker": "KXNCAAFSPREAD-26NOV21OKLTEX-OKL8", "event": "KXNCAAFSPREAD-26NOV21OKLTEX", "pick": "Oklahoma Sooners win by 7.5+",
                                              "p": .3, "fair": .38, "kind": "spread", "line": 7.5, "start": iso(7200), "game": "Oklahoma Sooners at Texas Longhorns"}], "fair": 20.0},
                                   {"pays": 10.0, "stake": 3.3}, .38 / .33)
ids["total"] = A.store_suggestion({"legs": [{"ticker": "KXNHLTOTAL-26NOV21NJDSTL-7", "event": "KXNHLTOTAL-26NOV21NJDSTL", "pick": "Over 7.5 (Devils at Blues)",
                                             "p": .4, "fair": .48, "kind": "total", "line": 7.5, "start": iso(5400), "game": "Devils at Blues"}], "fair": 20.0},
                                  {"pays": 10.0, "stake": 4.2}, .48 / .42)
ids["combo"] = A.store_suggestion({"legs": [{"ticker": "KXNBAGAME-26NOV21LALDEN-DEN", "event": "KXNBAGAME-26NOV21LALDEN", "pick": "Denver Nuggets", "p": .5, "fair": .6},
                                            {"ticker": "KXNHLGAME-26NOV21NJDSTL-NJD", "event": "KXNHLGAME-26NOV21NJDSTL", "pick": "New Jersey Devils", "p": .4, "fair": .5}],
                                   "fair": 30.0}, {"pays": 40.0, "stake": 5.0}, 1.2)
now = time.time()
A.store_x("insert into suggestions(id, ts, lg, legs, picks, n, pct, pays, stake, fair, kick, live) values(?,?,?,?,?,?,?,?,?,?,?,?)",
          ("oldone", now - 40, "nba", json.dumps(["KXNBAGAME-26NOV21PHXGSW-PHX"]), "Phoenix Suns", 1, 1.2, 10.0, 6.0, 20.0, now + 3600, 0))
ideas = json.loads(json.dumps(A.live_suggestions(limit=20), default=str))
if len(ideas) != 5: bad(f"expected 5 ideas from the engine, got {len(ideas)}")
LIVE = ("S.sf={o:'all',sp:'all',sort:'new'};S.filter='all';S.live={at:Date.now()/1000,combos:[],riding:0,staked:0,chance_one:0,best:0,cash_now:0,today:{},"
        "auto_sell:false,singles:[],pulse:[],need:[],ideas:" + json.dumps(ideas) + "};localStorage.removeItem('cw_hide');renderLive()")
def card(pg, id_):
    return pg.locator(f"#idea-{id_}")

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for W_, H, tag, touch in ((360, 740, "phone360", True), (390, 844, "phone390", True), (430, 932, "phone430", True), (1280, 900, "desk", False)):
        ctx = br.new_context(viewport={"width": W_, "height": H}, device_scale_factor=2, color_scheme="dark", has_touch=touch)
        pg = ctx.new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script(__import__("upwait").COUNT_FETCHES)
        pg.goto(B + "/app"); __import__("upwait").go_and_hold(pg, "live")   # every load in flight done (the boot one too), then held still
        pg.evaluate(LIVE); time.sleep(1)
        # ---- the words on each card
        want = {
            "single": ["College football", "Baylor Bears to win", "Baylor Bears at TCU Horned Frogs", "Starts", "Kalshi price", "32¢", "Fair price", "40¢",
                       "+27% expected", "Chance to win", "40%", "Expected profit", "+$1.7", "old"],
            "spread": ["Oklahoma Sooners wins by 8 or more", "Oklahoma Sooners at Texas Longhorns", "Starts", "Expected profit"],
            "total": ["Over 7.5 total goals", "Devils at Blues", "Starts", "Kalshi price", "Fair price"],
            "combo": ["Nuggets to win", "Lakers at Nuggets", "Devils to win", "Devils at Blues", "NBA", "NHL"],
        }
        for k, words in want.items():
            c = card(pg, ids[k])
            if c.count() != 1:
                bad(f"{tag}: no card for the {k} idea"); continue
            txt = c.inner_text()
            for w in words:
                if w.lower() not in txt.lower(): bad(f"{tag}: the {k} card should say '{w}': {txt.replace(chr(10), ' | ')[:400]}")
            if "Not now" not in txt or "price" not in txt.lower(): bad(f"{tag}: the {k} card lost its Not now / price buttons: {txt.replace(chr(10), ' | ')[-120:]}")
        old = card(pg, "oldone")
        if old.count() != 1 or "Suns" not in old.inner_text(): bad(f"{tag}: the older idea should still show a card")
        # ---- nothing wider than the screen
        wide = pg.evaluate("document.documentElement.scrollWidth>innerWidth+1")
        if wide: bad(f"{tag}: sideways scroll on Live with the idea cards")
        over = pg.evaluate("[...document.querySelectorAll('.dcard.idea')].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>e.id)")
        if over: bad(f"{tag}: idea cards wider than themselves: {over}")
        if SHOTS:
            pg.locator(".dcard.idea").first.scroll_into_view_if_needed(); time.sleep(.3)
            pg.screenshot(path=os.path.join(SHOTS, f"after_{tag}.png"), full_page=True)
        # ---- the buttons still do their own thing and don't open the game page (the Mac's answers are scripted here)
        SENT = []
        def act(route):
            try: SENT.append(json.loads(route.request.post_data or "{}").get("a"))
            except ValueError: SENT.append(None)
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": False, "msg": "No price came in. Try again in a minute."}))
        pg.route("**/app/api/act", act)
        pg.locator(f"#ib-{ids['single']}").click(); time.sleep(.8)
        if pg.evaluate("document.querySelector('#modal').classList.contains('on')"): bad(f"{tag}: tapping Get today's price opened the game page")
        if SENT != ["idea"]: bad(f"{tag}: Get today's price should ask the Mac for the idea's price: {SENT}")
        pg.unroute("**/app/api/act")
        pg.evaluate(LIVE); time.sleep(.6)
        card(pg, ids["single"]).get_by_text("Not now").click(); time.sleep(.6)
        if card(pg, ids["single"]).count(): bad(f"{tag}: Not now should drop the idea")
        if pg.evaluate("document.querySelector('#modal').classList.contains('on')"): bad(f"{tag}: tapping Not now opened the game page")
        pg.evaluate(LIVE); time.sleep(.6)
        # ---- tapping the card body opens the game page (the web app's real game route)
        card(pg, ids["total"]).locator(".igame").first.click(); time.sleep(.5)
        if not wait(pg, "document.querySelector('#modal').classList.contains('on')", 6): bad(f"{tag}: tapping the total card didn't open the game page")
        else:
            wait(pg, "!!document.querySelector('#sheet .dhead')||/not found/i.test(document.querySelector('#sheet').innerText)", 15)
            st = pg.evaluate("document.querySelector('#sheet').innerText")
            if "not found" in st.lower(): bad(f"{tag}: the idea's game page said 'Game not found'")
            elif "Over 7.5" not in st and "Devils" not in st: bad(f"{tag}: the game page doesn't show the idea's game: {st[:200]}")
            if SHOTS and tag == "phone390": pg.screenshot(path=os.path.join(SHOTS, "after_gamepage.png"))
            pg.evaluate("closeModal()"); time.sleep(.5)
        # a combo opens the game of the leg that was tapped
        card(pg, ids["combo"]).locator(".ileg").nth(1).click(); time.sleep(.5)
        if not wait(pg, "document.querySelector('#modal').classList.contains('on')&&S.gameOpen==='KXNHLGAME-26NOV21NJDSTL-NJD'", 6): bad(f"{tag}: tapping a combo leg didn't open that leg's game")
        pg.evaluate("closeModal()"); time.sleep(.5)
        # a price below fair reads as a loss, not a green "+-4%"
        pg.evaluate("S.live.ideas=[{id:'neg',n:2,picks:'A + B',sport:'NBA',ts:Date.now()/1000-30,pct:.96,stake:10,pays:50,fair:52,price_c:20,fair_c:19.2,edge:-.04,chance:.192,profit:-.4,legs_info:[]}];renderLive()"); time.sleep(.4)
        nt = card(pg, "neg").inner_text()
        if "+-" in nt or "\u22124% expected" not in nt or "\u2212$0.40" not in nt: bad(f"{tag}: a below-fair idea should show a minus edge and loss: {nt.replace(chr(10), ' | ')[:300]}")
        if pg.evaluate("document.querySelector('#idea-neg .ifacts b.up')&&[...document.querySelectorAll('#idea-neg .ifacts b.up')].length"): bad(f"{tag}: a below-fair idea shows a green number")
        # a card with no extra fields (older Mac) still draws and doesn't break
        pg.evaluate("S.live.ideas=[{id:'bare',n:1,picks:'Suns',sport:'NBA',ts:Date.now()/1000-30,pct:1.1,stake:5,pays:9,fair:9}];renderLive()"); time.sleep(.4)
        if pg.locator("#idea-bare").count() != 1: bad(f"{tag}: a bare idea (no new fields) should still show")
        print(tag, "errs:", errs)
        if errs: bad(f"{tag}: JS errors: {errs}")
        ctx.close()
    br.close()
if problems:
    print("PROBLEMS:", "; ".join(problems))
else:
    print("all good")
