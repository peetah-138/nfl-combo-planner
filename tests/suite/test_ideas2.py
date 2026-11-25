# CHECK: group=page secs=60
"""Live "Buy ideas" ration, dismiss, collapse and detail page (GitHub #141). The ideas come from the real engine
(live_ideas: ranked by expected dollars, with stable ids) and the dismissals go through the web app's real
/app/api/act and the engine's real dismissal file. At phone sizes (390 and 360, touch) and desktop it checks: only the top
three show with the rest under 'N more ideas'; the X, a swipe left, Not now and Clear all dismiss (the card slides out,
the server remembers, Undo brings it back, a reload keeps it hidden; Get price then Pass closes the idea the same way, #211); a swipe that is mostly vertical never dismisses and
the page still scrolls; the three Live sections fold with the count badge kept and the state remembered across a
reload; tapping a card body pushes a detail page (price vs fair, edge, chance, stake and expected profit, why it was
picked, how the price moved, whether you could sell it, the game page) while its buttons keep doing their own thing;
the empty state; no sideways scroll; and the see-through haptic switches sit only on compact controls (the X, the fold
and 'more' buttons), never on a whole card. Saves screenshots (SHOTS dir, if set). Prints PROBLEMS on any failure."""
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
    A.book_depth = lambda t, max_age=60: {"bid": .31, "ask": .32, "spread": .01, "ask_size": 240, "thin": False}   # Kalshi's public book, faked
    AA["A"] = A
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("SHOTS") or ""
from playwright.sync_api import sync_playwright
import upwait
problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def until(fn, secs=4):
    for _ in range(int(secs / .1)):
        try:
            if fn(): return True
        except Exception:
            pass
        time.sleep(.1)
    return False
def wait(pg, js, secs=8):
    for _ in range(int(secs / .1)):
        try:
            if pg.evaluate(js): return True
        except Exception:
            pass
        time.sleep(.1)
    return False

A = AA["A"]
if not A.STORE.get("db"):
    A.store_open()
iso = lambda secs: (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=secs)).isoformat()
D = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=5)).strftime("%y%b%d").upper()
A.LEAGUE["code"] = "nba"
A.CFG["accept_pct"] = 95
ROWS = {}
def single(tag, stake, pays, pct):
    ev = f"KXNBAGAME-{D}{tag}"; tk = f"{ev}-{tag[:3]}"
    A.KICKOFF[ev] = iso(7200); A.PICK_NAME[tk] = tag
    return tk, A.store_suggestion({"legs": [{"ticker": tk, "event": ev, "pick": tag, "p": .3, "fair": .4}], "fair": 25.0}, {"pays": float(pays), "stake": stake}, pct)
def seed():
    A.store_x("delete from suggestions")
    try: os.remove(A.IDEA_DISMISS)
    except OSError: pass
    t, _ = single("BBB", 3.3, 10, 1.20); ROWS["Bt"] = t     # an earlier, dearer quote...
    single("BBB", 3.0, 10, 1.30)                       # ...then the re-offer: two quotes, so the detail page draws a price line
    ROWS["Ct"], ROWS["C"] = single("CCC", 10.0, 30, 1.08)
    ROWS["At"], ROWS["A"] = single("AAA", 6.0, 20, 1.10)
    legs = []
    for tag in ("DDD", "FFF"):
        ev = f"KXNBAGAME-{D}{tag}"; A.KICKOFF[ev] = iso(7200)
        legs.append({"ticker": f"{ev}-{tag[:3]}", "event": ev, "pick": tag, "p": .5, "fair": .6})
    sid = A.store_suggestion({"legs": legs, "fair": 30.0}, {"pays": 40.0, "stake": 5.0}, 0.97)
    A._exit_shadow_table()                             # at 97% of fair it shows once smart sell likely profits (#142)
    A.store_x("insert into exit_shadow(ts, cand, source, tickers, ev, new) values(?,?,?,?,?,?)",
              (time.time(), f"idea:idea:{sid}", "idea", json.dumps([l["ticker"] for l in legs]), 0.5, 1))
    single("EEE", 4.0, 12, 0.98)                       # no edge left: below the bar
def server_picks():
    return [r["picks"].split(" + ")[0] for r in A.live_ideas()]
SING = [{"t": "KXNFLSPREAD-26NOV22BUFKC-KC7", "kind": "spread", "sport": "nfl", "side": "yes", "label": "Kansas City wins by over 6.5 points", "game": "Buffalo at Kansas City: Spread",
         "event": "KXNFLSPREAD-26NOV22BUFKC", "n": 10, "cost": 5.2, "pays": 10, "worth": 7.0, "chance": 0.72, "state": "live", "res": None, "score": "KC 24-14 BUF Q3 4:12", "starts": "",
         "how": "Covering now · +10", "url": "", "own": False, "self": False, "sell_at": 8.4}]
def inject(pg, extra=""):
    ideas = json.loads(json.dumps(A.live_ideas(), default=str))
    pg.evaluate("S.sf={o:'all',sp:'all',sort:'new'};S.filter='all';S.idHide={};S.ideasMore=false;S.ideaq={};S.live={at:Date.now()/1000,combos:[],riding:0,staked:0,chance_one:0,best:0,cash_now:0,today:{},"
                "auto_sell:false,singles:" + json.dumps(SING) + ",pulse:[],need:[],ideas:" + json.dumps(ideas) + ",ideas_limit:3,ideas_hidden:0};" + extra + "renderLive()")
    time.sleep(.5)
cards = lambda pg, sel=".ilist .iw": pg.evaluate("[...document.querySelectorAll('%s')].filter(e=>e.getBoundingClientRect().height>30&&!e.closest('.fold.shut')).length" % sel)
def swipe(cdp, x0, y0, x1, y1, steps=10):
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x0, "y": y0}]})
    for i in range(1, steps + 1):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x0 + (x1 - x0) * i / steps, "y": y0 + (y1 - y0) * i / steps}]})
        time.sleep(.016)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for W_, H, tag, touch in ((390, 844, "phone390", True), (360, 740, "phone360", True), (1280, 900, "desk", False)):
        ctx = br.new_context(viewport={"width": W_, "height": H}, device_scale_factor=2, color_scheme="dark", has_touch=touch)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__hswForce=1;"); pg.add_init_script(upwait.COUNT_FETCHES)
        # wait for the page's own loads (the boot one too) before drawing test data in, then hold it still: a Live load
        # still on its way used to land after inject() and replace the seeded ideas with the server's older snapshot
        pg.goto(B + "/app"); upwait.go_and_hold(pg, "live")
        seed(); inject(pg)
        # ---- the ration: the best three, the rest under 'N more ideas'
        txt = pg.locator(".lsec[data-fk=ideas]").inner_text()
        if "buy ideas" not in txt.lower() or "5" not in txt: bad(f"{tag}: the Buy ideas header should show the count (5): {txt!r}")
        if cards(pg) != 3: bad(f"{tag}: only the top 3 ideas should show, got {cards(pg)}")
        first = pg.locator(".ilist .iw").first.inner_text()
        if "BBB" not in first: bad(f"{tag}: the best idea by expected dollars (BBB) should be first: {first[:120]!r}")
        more = pg.locator(".imore")
        if more.count() != 1 or "2 more ideas" not in more.inner_text(): bad(f"{tag}: expected a '2 more ideas' button: {more.inner_text() if more.count() else None}")
        if pg.evaluate("document.querySelector('#imore')&&!document.querySelector('#imore').classList.contains('shut')"): bad(f"{tag}: the rest should be folded by default")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{tag}: sideways scroll with the idea cards")
        if SHOTS: pg.screenshot(path=os.path.join(SHOTS, f"cards_{tag}.png"), full_page=True)
        more.click(); until(lambda: cards(pg) == 5); time.sleep(.3)
        if cards(pg) != 5: bad(f"{tag}: '2 more ideas' should open the other two (5 in all), got {cards(pg)}: " + pg.evaluate("[...document.querySelectorAll('.ilist .iw')].map(e=>[e.innerText.slice(0,14),Math.round(e.getBoundingClientRect().height),!!e.closest('.fold.shut')].join('/')).join(' ; ')"))
        if "below your bar" not in pg.locator(".ilist").nth(1).inner_text().lower(): bad(f"{tag}: the idea under the bar should say so")
        if SHOTS: pg.screenshot(path=os.path.join(SHOTS, f"more_{tag}.png"), full_page=True)
        more.click(); until(lambda: cards(pg) == 3); time.sleep(.3)
        if cards(pg) != 3: bad(f"{tag}: the button should fold them again")
        # ---- stale price reads refreshing
        pg.evaluate("S.live.ideas[1].stale=true;S.live.ideas[1].age=400;renderLive()"); time.sleep(.3)
        if "refreshing" not in pg.locator(".ilist .iw").nth(1).inner_text().lower(): bad(f"{tag}: a price over 2 minutes old should say refreshing")
        inject(pg)
        # ---- overlay haptic switches only on compact controls (the see-through switch is on every control, never on a whole card)
        sw = pg.evaluate("({x:!!document.querySelector('.ilist .ix>.hsw'),f:!!document.querySelector('.lsec .fbtn>.hsw'),m:!!document.querySelector('.imore>.hsw'),c:!!document.querySelector('.dcard.idea>.hsw')})")
        if not (sw["x"] and sw["f"] and sw["m"]): bad(f"{tag}: the X, the fold button and the 'more' button are compact controls and should carry the haptic switch: {sw}")
        if sw["c"]: bad(f"{tag}: a whole card must not carry a haptic switch")
        # ---- a notification naming an idea that sits in the folded section / the 'more' list opens them so it can be seen
        last_id = pg.evaluate("S.live.ideas[4].id")
        pg.evaluate("localStorage.setItem('cw_fold_ideas','0');renderLive()"); time.sleep(.4)
        pg.evaluate("S.hl='%s';ideaReveal(S.hl)" % last_id); time.sleep(.8)
        if not pg.evaluate("(()=>{const e=document.getElementById('idea-%s');return !!e&&e.getBoundingClientRect().height>30&&!e.closest('.fold.shut')})()" % last_id): bad(f"{tag}: an idea named by a notification should be revealed (section and 'more' list opened)")
        pg.evaluate("localStorage.removeItem('cw_fold_ideas');S.hl=null;S.ideasMore=false;renderLive()"); time.sleep(.4)
        # ---- X dismisses: the card slides out, the list closes the gap, the Mac remembers, Undo brings it back
        docy2 = lambda i: pg.evaluate("(()=>{const e=document.querySelectorAll('.ilist .iw')[%d];return e.getBoundingClientRect().top+scrollY})()" % i)
        y_before = docy2(0)
        pg.locator(".ilist .iw").first.locator(".ix").click()
        if not wait(pg, "document.querySelectorAll('.ilist .iw[data-id]').length&&![...document.querySelectorAll('.ilist .iw')].some(e=>/BBB/.test(e.innerText))", 4): bad(f"{tag}: the X should take the BBB card off the list")
        if not until(lambda: "BBB" not in server_picks()): bad(f"{tag}: the Mac should remember the dismissal: {server_picks()}")
        if not wait(pg, "!!document.querySelector('#undo.on')", 3): bad(f"{tag}: an Undo bar should appear")
        elif "Undo" not in pg.locator("#undo").inner_text(): bad(f"{tag}: the bar should offer Undo")
        gap = docy2(0)
        if abs(gap - y_before) > 14: bad(f"{tag}: the list should close the gap (next card moves up to where the first was): {gap} vs {y_before}")
        if "buy ideas" not in pg.locator(".lsec[data-fk=ideas]").inner_text().lower() or "4" not in pg.locator(".lsec[data-fk=ideas]").inner_text(): bad(f"{tag}: the count should drop to 4")
        pg.locator("#undo button").click(); time.sleep(.9)
        if not until(lambda: "BBB" in server_picks()): bad(f"{tag}: Undo should bring it back on the Mac")
        if not wait(pg, "[...document.querySelectorAll('.ilist .iw')].some(e=>/BBB/.test(e.innerText))", 3): bad(f"{tag}: Undo should bring the card back")
        # ---- Not now means dismiss, and a reload keeps it hidden (server side)
        pg.locator(".ilist .iw").first.get_by_text("Not now").click(); time.sleep(.9)
        if not until(lambda: "BBB" not in server_picks()): bad(f"{tag}: Not now should dismiss on the Mac")
        pg.reload(); upwait.go_and_hold(pg, "live")
        got = pg.evaluate("api('/app/api/live').then(r=>({n:(r.ideas||[]).map(i=>i.picks),lim:r.ideas_limit,hid:r.ideas_hidden,id:(r.ideas||[])[0]&&r.ideas[0].idea_id}))")
        if not isinstance(got, dict) or got.get("lim") != 3 or got.get("hid") != 1 or any("BBB" in p for p in got.get("n", [])) or not str(got.get("id", "")).startswith("i"):
            bad(f"{tag}: after a reload the live data should keep it hidden and carry ideas_limit/ideas_hidden/idea_id: {got}")
        seed(); inject(pg)
        # ---- swipe left to dismiss (touch), and a vertical drag that starts on a card still scrolls
        if touch:
            cdp = ctx.new_cdp_session(pg)
            pg.evaluate("window.scrollTo(0,0)"); time.sleep(.2)
            pg.locator(".ilist .iw").nth(1).locator(".dcard").scroll_into_view_if_needed(); time.sleep(.3)
            bb = pg.locator(".ilist .iw").nth(1).locator(".dcard").bounding_box()
            x0, y0 = bb["x"] + bb["width"] * .7, bb["y"] + 50
            sy0 = pg.evaluate("scrollY")
            swipe(cdp, x0, y0, x0 - 40, y0 - 160)             # mostly vertical: must scroll, never dismiss
            time.sleep(.5)
            if pg.evaluate("scrollY") < sy0 + 20: bad(f"{tag}: a vertical drag that starts on a card should still scroll the page (scrollY {sy0} -> {pg.evaluate('scrollY')})")
            if cards(pg) != 3 or "CCC" not in pg.locator(".ilist").first.inner_text(): bad(f"{tag}: a mostly vertical drag must not dismiss anything")
            pg.locator(".ilist .iw").nth(1).locator(".dcard").scroll_into_view_if_needed(); time.sleep(.4)
            bb = pg.locator(".ilist .iw").nth(1).locator(".dcard").bounding_box()
            x0, y0 = bb["x"] + bb["width"] * .8, bb["y"] + 60
            swipe(cdp, x0, y0, x0 - 40, y0)                    # sideways but short: springs back
            time.sleep(.6)
            if cards(pg) != 3 or "CCC" not in pg.locator(".ilist").first.inner_text(): bad(f"{tag}: a short sideways drag should spring back, not dismiss")
            second = pg.locator(".ilist .iw").nth(1).inner_text()
            swipe(cdp, x0, y0, x0 - 200, y0 + 6)               # a clear swipe left
            if not wait(pg, "![...document.querySelectorAll('.ilist .iw')].some(e=>/CCC/.test(e.innerText))", 4): bad(f"{tag}: a swipe left should dismiss the card (it was: {second[:40]!r})")
            time.sleep(.6)
            if not until(lambda: "CCC" not in server_picks()): bad(f"{tag}: the swipe should reach the Mac: {server_picks()} {pg.evaluate('JSON.stringify(S.idHide)')}")
            if pg.evaluate("location.hash").startswith("#game") or pg.evaluate("document.querySelector('#modal').classList.contains('on')"): bad(f"{tag}: a swipe must not open the detail page")
            if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{tag}: sideways scroll after a swipe")
            seed(); inject(pg)
        # ---- Get price, then Pass: closes the idea like the X (GitHub #211). Singles, combos and the detail page.
        seed(); inject(pg, "S.ideasMore=true;"); pg.evaluate("S.ideasMore=true;renderLive()"); time.sleep(.4)
        PSENT = []
        def pact(route):
            try: a = json.loads(route.request.post_data or "{}").get("a")
            except ValueError: a = None
            PSENT.append(a)
            if a == "idea": route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "i": 7, "pays": 10.0, "stake": 3.0, "pct": 1.3, "clears": True, "price": .3, "n": 10, "edge": .05, "fair": .4, "single": True}))
            elif a in ("buy", "singlebuy"): route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": False, "msg": "test: no buy"}))
            else: route.continue_()
        pg.route("**/app/api/act", pact)
        gone = lambda p_: until(lambda: (pg.evaluate("0") or True) and p_ not in server_picks())   # evaluate() lets the route handler above run
        back = lambda p_: until(lambda: (pg.evaluate("0") or True) and p_ in server_picks())
        def quoted(id_):
            pg.evaluate("document.querySelector('[data-ib=\"%s\"]').click()" % id_)
            return wait(pg, "(()=>{const e=document.querySelector('.iw[data-id=\"%s\"] .dbtns');return !!e&&/Pass/.test(e.innerText)&&/Buy/.test(e.innerText)})()" % id_, 5)
        for pick, what in (("BBB", "a single"), ("DDD", "a combo")):
            pid = pg.evaluate("S.live.ideas.find(i=>i.picks.startsWith('%s')).id" % pick)
            if not quoted(pid): bad(f"{tag}: Get price should show Pass and Buy for {what}"); continue
            if not pg.evaluate("!!S.ideaT&&S.ideaTid==='%s'" % pid): bad(f"{tag}: the quote countdown should be running for {what}")
            n0 = len(PSENT)
            pg.evaluate("document.querySelector('.iw[data-id=\"%s\"] .dbtns .btn.ghost').click()" % pid)
            if not wait(pg, "!document.querySelector('.iw[data-id=\"%s\"]')" % pid, 4): bad(f"{tag}: Pass should fold {what} away")
            if not gone(pick): bad(f"{tag}: Pass should put {what} in the Mac's dismiss store: {server_picks()}")
            if "idea_dismiss" not in PSENT[n0:]: bad(f"{tag}: Pass should send idea_dismiss: {PSENT[n0:]}")
            if not wait(pg, "!!document.querySelector('#undo.on')", 3) or "Undo" not in pg.locator("#undo").inner_text(): bad(f"{tag}: Pass should show the Undo bar")
            st = pg.evaluate("({q:S.ideaq['%s'],t:S.ideaT,id:S.ideaTid})" % pid)
            if st["q"] is not None or st["t"] is not None or st["id"] is not None: bad(f"{tag}: Pass should drop the quote and stop its countdown: {st}")
            if "buy" in PSENT[n0:] or "singlebuy" in PSENT[n0:]: bad(f"{tag}: Pass must never buy: {PSENT[n0:]}")
            time.sleep(1.2)
            if pg.evaluate("[...document.querySelectorAll('.ilist .iw')].some(e=>e.innerText.includes('%s'))" % pick): bad(f"{tag}: {what} should stay gone across refreshes")
            pg.locator("#undo button").click(); time.sleep(.9)
            if not back(pick): bad(f"{tag}: Undo should bring {what} back after a Pass")
        # a buy on its way: Pass is off
        seed(); inject(pg); pid = pg.evaluate("S.live.ideas[0].id")
        if quoted(pid):
            pg.evaluate("S.ibuy={'%s':1};renderLive()" % pid); time.sleep(.3)
            if not pg.evaluate("document.querySelector('.iw[data-id=\"%s\"] .dbtns .btn.ghost').disabled" % pid): bad(f"{tag}: Pass should be off while a buy is on its way")
            pg.evaluate("ideaPass('%s',false)" % pid); time.sleep(.8)
            if not pg.evaluate("!!document.querySelector('.iw[data-id=\"%s\"]')&&!!S.ideaq['%s']" % (pid, pid)) or "BBB" not in server_picks(): bad(f"{tag}: Pass must do nothing while a buy is in flight")
            pg.evaluate("S.ibuy={};S.ideaq={};clearInterval(S.ideaT);S.ideaT=null;renderLive()")
        # (#270) a buy still on its way after the countdown ended (no fresh quote) shows Buying..., not Get today's price
        seed(); inject(pg); pid = pg.evaluate("S.live.ideas[0].id")
        pg.evaluate("S.ideaq={};S.ibuy={'%s':1};renderLive()" % pid); time.sleep(.3)
        row = pg.evaluate("(()=>{const e=document.querySelector('.iw[data-id=\"%s\"] .dbtns');return e?{t:e.innerText,p:[...e.querySelectorAll('button')].map(b=>b.disabled)}:null})()" % pid)
        if not row or "Buying" not in row["t"] or "price" in row["t"].lower() or not all(row["p"]): bad(f"{tag}: a buy in flight with no fresh quote should show a disabled Buying row: {row}")
        if SHOTS and tag == "phone390":
            for scheme in ("dark", "light"):
                pg.emulate_media(color_scheme=scheme); time.sleep(.3)
                pg.locator('.iw[data-id="%s"]' % pid).screenshot(path=os.path.join(SHOTS, f"buying_row_{scheme}.png"))
            pg.emulate_media(color_scheme="dark")
        pg.evaluate("S.ibuy={};renderLive()")
        # Pass on the detail page closes the page and dismisses
        seed(); inject(pg); pid = pg.evaluate("S.live.ideas.find(i=>i.picks.startsWith('CCC')).id")
        pg.evaluate("openIdea('%s')" % pid)
        wait(pg, "document.querySelector('#modal').classList.contains('on')&&S.ideaReady", 5)
        for _try in range(3):
            try: pg.locator("#sheet").get_by_text("Get today's price").click(timeout=4000)
            except Exception: pass
            if until(lambda: "idea" in PSENT[-3:], 2): break
        if wait(pg, "/Pass/.test(document.querySelector('#sheet').innerText)", 5):
            for _try in range(3):
                try: pg.locator("#sheet .idact").get_by_text("Pass", exact=True).click(timeout=4000); break
                except Exception: time.sleep(.3)
            if not wait(pg, "!document.querySelector('#modal').classList.contains('on')", 4): bad(f"{tag}: Pass on the detail page should close it")
            if not gone("CCC"): bad(f"{tag}: Pass on the detail page should dismiss the idea: {server_picks()} {PSENT[-6:]}")
        else: bad(f"{tag}: the detail page should show Pass after Get price")
        pg.unroute("**/app/api/act")
        seed(); inject(pg)
        # ---- Clear all
        pg.get_by_text("Clear all").click()
        if not wait(pg, "!document.querySelector('.ilist .iw')", 5): bad(f"{tag}: Clear all should take every card off")
        time.sleep(.8)
        if not until(lambda: not server_picks()): bad(f"{tag}: Clear all should hide everything on the Mac: {server_picks()}")
        if "Nothing clears your bar right now" not in pg.locator(".iempty").inner_text(): bad(f"{tag}: an empty list should say 'Nothing clears your bar right now'")
        if SHOTS and tag == "phone390": pg.screenshot(path=os.path.join(SHOTS, "empty_phone390.png"))
        pg.evaluate("S.live.ideas_hidden=5;renderLive()"); time.sleep(.3)
        if "5 hidden" not in pg.locator(".iempty").inner_text(): bad(f"{tag}: the empty state should offer to show hidden ideas")
        pg.locator(".iempty .linkb").click(); time.sleep(1)
        if not until(lambda: len(server_picks()) == 5): bad(f"{tag}: 'Show again' should bring them all back: {server_picks()} {open(A.IDEA_DISMISS).read()} rows={[r['picks'] for r in A.live_suggestions(limit=50, newest=True)]} held={A._held_idea_markets()}")
        seed(); inject(pg)
        # ---- collapse: each of the three sections folds, keeps its count, remembers across a reload
        for k, name in (("ideas", "Buy ideas"), ("combos", "Your combos"), ("singles", "Single bets")):
            h = pg.locator(f".lsec[data-fk={k}]")
            if h.count() != 1: bad(f"{tag}: no fold header for {k}"); continue
            docy = lambda: pg.evaluate(f"document.querySelector('.lsec[data-fk={k}]').getBoundingClientRect().top+scrollY")
            top0 = docy(); badge0 = h.locator(".n").inner_text()
            h.locator(".fbtn").click(); time.sleep(.6)
            shut = pg.evaluate(f"document.querySelector('.fold[data-fk={k}]').classList.contains('shut')")
            if not shut: bad(f"{tag}: the {k} section should fold")
            if pg.evaluate(f"localStorage.getItem('cw_fold_{k}')") != "0": bad(f"{tag}: the {k} fold should be remembered on this phone")
            if h.locator(".n").inner_text() != badge0 or not h.locator(".n").is_visible(): bad(f"{tag}: the count badge should stay visible when {k} is folded")
            if pg.evaluate(f"document.querySelector('.lsec[data-fk={k}] .fbtn').getAttribute('aria-expanded')") != "false": bad(f"{tag}: aria-expanded should say folded")
            if pg.evaluate(f"document.querySelector('.fold[data-fk={k}]').getBoundingClientRect().height") > 30: bad(f"{tag}: a folded {k} section should take no room")
            if abs(docy() - top0) > 2: bad(f"{tag}: folding {k} moved its own header (layout jump)")
            if SHOTS and k == "ideas" and tag == "phone390": pg.screenshot(path=os.path.join(SHOTS, "folded_phone390.png"), full_page=False)
        pg.reload(); upwait.go_and_hold(pg, "live"); inject(pg)
        for k in ("ideas", "combos", "singles"):
            if not pg.evaluate(f"document.querySelector('.fold[data-fk={k}]').classList.contains('shut')"): bad(f"{tag}: the {k} fold should survive a reload")
        for k in ("ideas", "combos", "singles"):
            pg.locator(f".lsec[data-fk={k}] .fbtn").click(); time.sleep(.5)
            if pg.evaluate(f"document.querySelector('.fold[data-fk={k}]').classList.contains('shut')"): bad(f"{tag}: the {k} section should open again")
            if pg.evaluate(f"localStorage.getItem('cw_fold_{k}')") != "1": bad(f"{tag}: opening {k} should be remembered")
        # ---- the detail page: tap a card body; the buttons keep their own jobs
        SENT = []
        def act(route):
            try: SENT.append(json.loads(route.request.post_data or "{}").get("a"))
            except ValueError: SENT.append(None)
            if SENT[-1] == "idea": route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": False, "msg": "No price came in. Try again in a minute."}))
            else: route.continue_()
        pg.route("**/app/api/act", act)
        card = pg.locator(".ilist .iw").first
        card.locator(".igame").first.click()
        if not wait(pg, "document.querySelector('#modal').classList.contains('on')&&S.ideaOpen", 5): bad(f"{tag}: tapping a card should push the detail page")
        else:
            wait(pg, "/why it was picked/i.test(document.querySelector('#sheet').innerText)&&/easy to sell|harder to sell/i.test(document.querySelector('#sheet').innerText)", 8)
            st = pg.evaluate("document.querySelector('#sheet').innerText")
            for w in ("BBB", "Kalshi price", "Fair price", "Edge", "Chance to win", "Stake", "Expected profit", "Why it was picked", "How the price has moved", "Could you sell it?", "Easy to sell back", "Open the game page", "Get today's price", "Not now"):
                if w.lower() not in st.lower(): bad(f"{tag}: the detail page should say '{w}': {st.replace(chr(10), ' | ')[:500]}")
            if not pg.evaluate("!!document.querySelector('#sheet .imv svg path')"): bad(f"{tag}: the price line should draw (two quotes were saved)")
            if pg.evaluate("document.querySelector('#sheet').scrollWidth>document.querySelector('#sheet').clientWidth+1"): bad(f"{tag}: sideways scroll on the detail page")
            if SHOTS and tag == "phone390": pg.screenshot(path=os.path.join(SHOTS, "detail_phone390.png"))
            for _try in range(3):                              # the sheet repaints when the book arrives; a click that lands mid-repaint is retried
                try: pg.locator("#sheet").get_by_text("Get today's price").click(timeout=4000)
                except Exception: pass
                if until(lambda: "idea" in SENT, 2): break
            if "idea" not in SENT: bad(f"{tag}: the detail page's price button should ask the Mac for the idea's price: {SENT}")
            if not pg.evaluate("document.querySelector('#modal').classList.contains('on')"): bad(f"{tag}: asking for a price shouldn't close the page")
            pg.locator("#sheet").get_by_text("Open the game page").click()
            if not wait(pg, "S.gameOpen==='%s'" % ROWS["Bt"], 5): bad(f"{tag}: 'Open the game page' should open that game")
            pg.evaluate("closeModal()"); time.sleep(.5)
        pg.unroute("**/app/api/act")
        # the buttons on the card itself don't open the page; a combo's leg still opens its game
        pg.evaluate("S.ideaq={}")
        pg.locator(".ilist .iw").first.locator(".ix").click(); time.sleep(.8)
        if pg.evaluate("document.querySelector('#modal').classList.contains('on')"): bad(f"{tag}: the X must not open the detail page")
        # a combo card: tap its body for the detail page (picks listed), tap a leg for that game
        seed(); inject(pg, "S.ideasMore=true;"); pg.evaluate("S.ideasMore=true;renderLive()"); time.sleep(.4)
        combo = pg.locator(".ilist .iw", has_text="DDD").first
        combo.locator("p").first.click()
        if not wait(pg, "document.querySelector('#modal').classList.contains('on')&&/picks/i.test(document.querySelector('#sheet').innerText)", 5): bad(f"{tag}: a combo card should open a detail page that lists its picks")
        elif "no order book" not in pg.evaluate("document.querySelector('#sheet').innerText").lower(): bad(f"{tag}: a combo's detail page should say there is no order book to read")
        pg.evaluate("closeModal()"); time.sleep(.5)
        # ---- empty state
        pg.evaluate("S.live.ideas=[];renderLive()"); time.sleep(.3)
        if "Nothing clears your bar right now" not in pg.locator(".iempty").inner_text() or not pg.locator(".iempty svg").count(): bad(f"{tag}: the empty state needs its message and a calm icon")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{tag}: sideways scroll in the empty state")
        print(tag, "errs:", errs)
        if errs: bad(f"{tag}: JS errors: {errs}")
        ctx.close()
    br.close()
if problems:
    print("PROBLEMS:", "; ".join(problems))
else:
    print("all good")
