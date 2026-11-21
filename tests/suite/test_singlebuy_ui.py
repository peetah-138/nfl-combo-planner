"""Buy straight (issue #113): the Build slip's Single bet / Combo switch, the game page's pinned buy buttons and the buy
sheet (render, stake presets, warning / blocked states, the 20 s price life, arm-then-confirm for big stakes, the Bought
moment, a refusal, an unclear answer). The quote and buy answers are scripted at the page's own request layer (nothing is
priced or bought); one real request checks the web app's action answers in plain words. Phone (390x844, touch, dark and
light) and desktop. Saves screenshots (SHOTS dir, if set). Prints PROBLEMS on any failure."""
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
threading.Thread(target=W.webapp_main, daemon=True).start(); time.sleep(3)
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
def shot(pg, name):
    if SHOTS:
        pg.screenshot(path=os.path.join(SHOTS, name))

def Q(**kw):   # a quote as the web app answers it
    q = {"ok": True, "q": "0123456789abcdef", "t": "KXNBAGAME-X-DEN", "pick": "Denver Nuggets", "opp": "Los Angeles Lakers",
         "game": "", "sport": "nba", "kind": "win", "live": False, "ask": .72, "bid": .70, "gap": .02, "depth": 500, "fee": .0141,
         "per": .7341, "fair": .80, "how": "sportsbooks + your record", "nofair": None, "edge": .0659, "ret": .0898,
         "sug": 17.35, "stake": 10, "n": 13, "cost": 9.54, "pays": 13.0, "profit": 3.46, "spent": 10, "budget": 100, "room": 90,
         "blocked": None, "warn": [], "clears": True, "secs": 20, "arm": 25, "max": 100, "presets": [3, 5, 10]}
    q.update(kw); return q
ST = {"quote": Q(), "buy": {"ok": True, "filled": 13, "price": .72, "cost": 9.54, "pays": 13, "msg": "Bought 13 at 72¢: pays $13 if it wins."}}
SENT = []
def act(route):
    try:
        body = json.loads(route.request.post_data or "{}")
    except ValueError:
        body = {}
    if body.get("real") or body.get("a") not in ("singlequote", "singlebuy"):
        return route.continue_()
    SENT.append(body)
    if body["a"] == "singlequote":
        q = dict(ST["quote"]); q["t"] = body.get("t") or q["t"]
        if body.get("stake") not in (None, ""):
            q["stake"] = float(body["stake"])
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(q))
    return route.fulfill(status=200, content_type="application/json", body=json.dumps(ST["buy"]))
GT = "KXNFLGAME-26NOV20HOUIND-IND"
GAME = {"leg": {"ticker": GT, "name": "Indianapolis Colts", "opp": "Houston Texans", "sport": "nfl", "state": "pre", "kind": "win",
                "chance": .24, "sc": None, "starts": "Tonight 8:15 PM", "note": "", "phase": "", "url": ""},
        "combos": [], "story": {"ticks": [], "plays": []}, "whatif": None, "detail": None,
        "buy": [{"t": GT, "name": "Indianapolis Colts", "ask": .24, "mult": 3.96}, {"t": "KXNFLGAME-26NOV20HOUIND-HOU", "name": "Houston Texans", "ask": .77, "mult": 1.28}],
        "fresh": None}
def game(route):
    return route.fulfill(status=200, content_type="application/json", body=json.dumps(GAME))
def sheet(pg):
    return pg.evaluate("""(()=>{const b=document.querySelector('#sbx');if(!b)return null;const btn=b.querySelector('#sbbuy');
      return {txt:b.innerText,btn:btn&&btn.innerText,cls:btn&&btn.className,dis:!!(btn&&btn.disabled),warn:[...b.querySelectorAll('.sbw')].map(e=>e.dataset.w),
       on:[...b.querySelectorAll('.sbst .chip.on')].map(e=>e.innerText)};})()""")
def hsw(pg, tag, sel, what):
    """the light pass forces the see-through haptic switches on (HT.N, #116): every Buy straight control in sel has
    exactly one switch of its own and a tap at its centre lands on it; the other passes have none."""
    r = pg.evaluate("""(sel=>{const out=[];[...document.querySelectorAll(sel)].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&!e.disabled;}).forEach(e=>{
      const sw=e.querySelectorAll(':scope>.hsw'),deep=e.querySelectorAll('.hsw').length,nm=(e.innerText||'').trim().slice(0,20);const a=e.getBoundingClientRect();
      const t=document.elementFromPoint(a.left+a.width/2,a.top+a.height/2);out.push({nm,n:sw.length,deep,hit:!!(t&&sw[0]===t),inv:a.top>=0&&a.bottom<=innerHeight});});return out;})""", sel)
    if not r: bad(f"{tag}: no {what} found to check the haptic switches"); return
    for c in r:
        if tag == "light":
            if c["n"] != 1 or c["deep"] != 1: bad(f"{tag}: {what} {c['nm']!r} should carry exactly one haptic switch: {c}")
            elif c["inv"] and not c["hit"]: bad(f"{tag}: a tap on {what} {c['nm']!r} should land on its haptic switch: {c}")
        elif c["deep"]: bad(f"{tag}: {what} {c['nm']!r} has a haptic switch with the overlay off: {c}")

def sideways(pg):
    return pg.evaluate("document.documentElement.scrollWidth>innerWidth+1||[...document.querySelectorAll('#sheet .sb,.gbuy,.slipbar')].some(e=>e.scrollWidth>e.clientWidth+2)")

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, tag, scheme in ((390, 844, "phone", "dark"), (390, 844, "light", "light"), (1280, 900, "desk", "dark")):
        ctx = br.new_context(viewport={"width": vw, "height": vh}, color_scheme=scheme, has_touch=(vw < 900), device_scale_factor=2)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__haps=[];localStorage.clear();localStorage.setItem('cw_view','build');localStorage.setItem('cw_lg','nba');localStorage.setItem('cw_pview','nba')" + (";window.__hswForce=1" if tag == "light" else ""))
        pg.route("**/app/api/act", act)
        pg.route(re.compile(r".*/app/api/game\?t=.*"), game)
        pg.goto(B + "/app")
        if not wait(pg, "typeof sbOpen==='function'&&S.build&&S.build.board&&S.build.board.length>1", 40):
            bad(f"{tag}: the Build board didn't load"); ctx.close(); continue
        pg.evaluate("S.adv=true;renderBuild()")
        wait(pg, "document.querySelectorAll('.pickbtn').length>=4", 10)
        time.sleep(.6)
        # ---- (1) the slip: one team picked, the Single bet / Combo switch, Buy straight
        tk = pg.evaluate("S.build.board[0].sides.filter(s=>!s.tie)[0].ticker")
        tk2 = pg.evaluate("S.build.board[1].sides.filter(s=>!s.tie)[0].ticker")
        pg.evaluate(f"pick('{tk}',S.build.board[0].event)")
        time.sleep(.5)
        if tag != "desk":
            if not pg.evaluate("!!document.querySelector('.slipbar .sbtog')"): bad(f"{tag}: the slip bar has no Single bet / Combo switch")
            if "tap 1 more team" not in pg.evaluate("(document.querySelector('.slipbar .sbrow span')||{}).innerText||''"): bad(f"{tag}: combo mode should still say tap 1 more team")
            pg.locator(".slipbar .sbtog button", has_text="Single bet").tap(); time.sleep(.5)
            if pg.evaluate("S.slipMode") != "single": bad(f"{tag}: tapping Single bet didn't switch the slip")
            bar = pg.evaluate("(document.querySelector('.slipbar')||{}).innerText||''")
            if "Buy straight" not in bar: bad(f"{tag}: single mode's slip bar should offer Buy straight: {bar!r}")
            pg.evaluate(f"pick('{tk2}',S.build.board[1].event)"); time.sleep(.4)
            if pg.evaluate("S.slip.length") != 1 or pg.evaluate("S.slip[0]") != tk2: bad(f"{tag}: in single mode a new team should replace the pick: {pg.evaluate('S.slip')}")
            if not pg.evaluate("window.__haps.length>0"): bad(f"{tag}: the switch should tick (haptic)")
            if sideways(pg): bad(f"{tag}: the slip bar scrolls sideways")
            hsw(pg, tag, ".slipbar .sbtog button,.slipbar .sbrow button", "the slip bar's buttons")
            shot(pg, f"1_slip_single_{tag}.png")
            pg.locator(".slipbar .sbtog button", has_text="Combo").tap(); time.sleep(.3)
            if pg.evaluate("S.slipMode") != "combo": bad(f"{tag}: tapping Combo didn't switch back")
            pg.locator(".slipbar .sbtog button", has_text="Single bet").tap(); time.sleep(.3)
            pg.locator(".slipbar button", has_text="Buy straight").tap()
        else:
            if not pg.evaluate("!!document.querySelector('.slip .sbtog')&&!!document.querySelector('#sbslip')"): bad("desk: the slip card should have the switch and Buy straight")
            pg.locator("#sbslip").click()
        # ---- (2) the sheet: render, good quote
        if not wait(pg, "!!document.querySelector('#sbx #sbbuy')", 8): bad(f"{tag}: the buy sheet didn't open"); ctx.close(); continue
        s = sheet(pg)
        if not SENT or SENT[-1].get("a") != "singlequote" or SENT[-1].get("t") not in (tk, tk2): bad(f"{tag}: the sheet should ask for a quote on the picked team: {SENT[-1:]}")
        for want in ("72¢", "80%", "+9%", "13 at 72¢", "$9.54", "$13.00", "$90.00 of $100.00", "20s"[:-1]):
            if want not in s["txt"]: bad(f"{tag}: the sheet should show {want!r}: {s['txt'][:300]!r}")
        if "yes" not in s["cls"] or "Buy $9.54" not in s["btn"]: bad(f"{tag}: a good price should be a green Buy: {s}")
        if not pg.evaluate("!!document.querySelector('#sbbuy .qt')"): bad(f"{tag}: the Buy button should carry the 20 s draining bar")
        if sideways(pg): bad(f"{tag}: the sheet scrolls sideways")
        hsw(pg, tag, "#sbx #sbbuy,#sbx .sbst .chip,#sbx .sbgo button", "the buy sheet's buttons")
        shot(pg, f"2_sheet_good_{tag}.png")
        # presets
        n0 = len(SENT)
        pg.locator("#sbx .sbst .chip", has_text="$5").first.click(); time.sleep(.6)
        if len(SENT) <= n0 or SENT[-1].get("stake") != 5: bad(f"{tag}: the $5 preset should re-price at $5: {SENT[-1:]}")
        if sheet(pg)["on"] != ["$5"]: bad(f"{tag}: the $5 preset should show as chosen: {sheet(pg)['on']}")
        # ---- (3) warnings: yellow Buy anyway
        ST["quote"] = Q(clears=False, fair=.70, edge=-.034, ret=-.046, warn=[{"k": "above", "t": "Kalshi's price is above our 70% chance."}, {"k": "thin", "t": "Thin market: 9¢ between the buy and sell prices."}], gap=.09, sug=2)
        pg.evaluate("sbQuote()"); time.sleep(.6)
        s = sheet(pg)
        if "warn" not in s["cls"] or "Buy anyway" not in s["btn"] or s["warn"] != ["above", "thin"]: bad(f"{tag}: a poor price should be a yellow Buy anyway with its warnings: {s}")
        if "−5%" not in s["txt"]: bad(f"{tag}: a negative edge should read −5%: {s['txt'][:200]!r}")
        shot(pg, f"3_sheet_warn_{tag}.png")
        # live, no fair price
        ST["quote"] = Q(clears=False, live=True, fair=None, how=None, edge=None, ret=None, nofair="no pre-game line to start from",
                        warn=[{"k": "live", "t": "This game is under way. There's no live fair price, so you'd be going on Kalshi's price alone."}])
        pg.evaluate("sbQuote()"); time.sleep(.6)
        s = sheet(pg)
        if "LIVE" not in s["txt"] or "no fair price" not in s["txt"] or "Buy anyway" not in s["btn"]: bad(f"{tag}: a live game with no fair price should say so: {s}")
        shot(pg, f"4_sheet_live_{tag}.png")
        # blocked (over the cap)
        ST["quote"] = Q(clears=False, blocked="That would bring your spending this week to $105, over your $100 cap. You have $5 left.")
        pg.evaluate("sbQuote()"); time.sleep(.6)
        s = sheet(pg)
        if not s["dis"] or "blocked" not in s["warn"] or "over your $100 cap" not in s["txt"]: bad(f"{tag}: over the cap the Buy should be off with the cap message: {s}")
        shot(pg, f"5_sheet_blocked_{tag}.png")
        # ---- (4) arm-then-confirm above the threshold, then the Bought moment
        ST["quote"] = Q(stake=30, n=40, cost=29.36, pays=40, profit=10.64)
        pg.evaluate("sbQuote()"); time.sleep(.6)
        n0 = len(SENT)
        pg.locator("#sbbuy").click(); time.sleep(.3)
        if len(SENT) != n0 or "Tap again" not in (sheet(pg)["btn"] or ""): bad(f"{tag}: a $29 buy should ask for a second tap first: {sheet(pg)}")
        pg.locator("#sbbuy").click()
        if not wait(pg, "!!document.querySelector('#sheet .okcard:not(.bad)')", 6): bad(f"{tag}: a successful buy should show the Bought moment")
        b = [x for x in SENT[n0:] if x.get("a") == "singlebuy"]
        if len(b) != 1 or b[0].get("q") != "0123456789abcdef" or b[0].get("t") not in (tk, tk2) or b[0].get("anyway"): bad(f"{tag}: exactly one buy with the quote on screen: {b}")
        if "Bought" not in pg.evaluate("document.querySelector('#sheet').innerText"): bad(f"{tag}: the moment should say Bought")
        time.sleep(1.2); shot(pg, f"6_bought_{tag}.png")
        pg.evaluate("closeModal()"); time.sleep(.5)
        # ---- (5) a refusal stays in the sheet; an unclear answer is Check Kalshi
        ST["quote"] = Q(); ST["buy"] = {"ok": False, "moved": True, "msg": "The price moved to 75¢ (you saw 72¢). Nothing was bought. Get a fresh price."}
        pg.evaluate(f"sbOpen('{tk}','nba')"); wait(pg, "!!document.querySelector('#sbx #sbbuy')", 6); time.sleep(.3)
        pg.locator("#sbbuy").click(); time.sleep(.8)
        s = sheet(pg)
        if not s or "failed" not in s["warn"] or "price moved" not in s["txt"] or "fresh price" not in (s["btn"] or ""): bad(f"{tag}: a refusal should show why and offer a fresh price: {s}")
        shot(pg, f"7_refused_{tag}.png")
        n0 = len(SENT)
        pg.locator("#sbbuy").click(); time.sleep(.6)
        if not SENT[n0:] or SENT[n0]["a"] != "singlequote": bad(f"{tag}: Get a fresh price should ask for a new quote, never resend the buy: {SENT[n0:]}")
        ST["buy"] = {"ok": False, "check": True, "msg": "Kalshi didn't answer clearly, so this may or may not have been bought."}
        pg.locator("#sbbuy").click()
        if not wait(pg, "!!document.querySelector('#sheet .okcard.bad')", 6) or "Check Kalshi" not in pg.evaluate("document.querySelector('#sheet').innerText"):
            bad(f"{tag}: an unclear answer should say Check Kalshi")
        time.sleep(1.2); shot(pg, f"8_check_{tag}.png")
        pg.evaluate("closeModal()"); time.sleep(.4)
        # ---- (6) the 20 s life: an old quote can't be bought
        ST["buy"] = {"ok": True, "filled": 13, "pays": 13, "msg": "Bought."}
        pg.evaluate(f"sbOpen('{tk}','nba')"); wait(pg, "!!document.querySelector('#sbx #sbbuy')", 6)
        pg.evaluate("S.sb.q.at-=21"); time.sleep(1.4)
        if "fresh price" not in (sheet(pg)["btn"] or ""): bad(f"{tag}: after 20 s the button should be Get a fresh price: {sheet(pg)}")
        pg.evaluate("closeModal()"); time.sleep(.4)
        # a Bought answer that lands after the sheet was closed is still shown
        ST["quote"] = Q()
        pg.evaluate(f"sbOpen('{tk}','nba')"); wait(pg, "!!document.querySelector('#sbx #sbbuy')", 6); time.sleep(.3)
        pg.evaluate("(async()=>{const p=sbBuy(document.querySelector('#sbbuy'));closeModal();await p;})()")
        if not wait(pg, "!!document.querySelector('#sheet .okcard:not(.bad)')&&$('#modal').classList.contains('on')", 6): bad(f"{tag}: a Bought answer after the sheet was closed should still show")
        pg.evaluate("closeModal()"); time.sleep(.4)
        # ---- (7) the game page's pinned buttons open the sheet for that side
        pg.evaluate(f"openGame('{GT}')")
        if not wait(pg, "document.querySelectorAll('#sheet .gbuy button').length===2", 10): bad(f"{tag}: the game page should pin two buy buttons")
        else:
            labels = pg.evaluate("[...document.querySelectorAll('#sheet .gbuy button')].map(b=>b.innerText.replace(/\\s+/g,' '))")
            if "24% · 3.96x" not in labels[0] or "77% · 1.28x" not in labels[1]: bad(f"{tag}: the buttons should read like 'IND · 24% · 3.96x': {labels}")
            if sideways(pg): bad(f"{tag}: the game page scrolls sideways")
            time.sleep(1.4)                  # let the page finish easing in
            gb = pg.evaluate("(()=>{const b=document.querySelector('#sheet .gbuy').getBoundingClientRect();return [b.top,b.bottom,innerHeight]})()")
            if gb[1] > gb[2] + 1 or gb[1] < gb[2] - 120: bad(f"{tag}: the buy buttons should sit pinned at the bottom of the screen: {gb}")
            shot(pg, f"9_game_buttons_{tag}.png")
            hsw(pg, tag, "#sheet .gbuy button", "the game page's buy buttons")
            n0 = len(SENT)
            pg.locator("#sheet .gbuy button").nth(1).click()
            if not wait(pg, "!!document.querySelector('#sbx #sbbuy')", 8): bad(f"{tag}: a game page button should open the buy sheet")
            q = [x for x in SENT[n0:] if x.get("a") == "singlequote"]
            if not q or q[0].get("t") != "KXNFLGAME-26NOV20HOUIND-HOU" or q[0].get("lg") != "nfl": bad(f"{tag}: the HOU button should price HOU (nfl): {q}")
            pg.locator("#sbx .sbgo button", has_text="Cancel").click()
            if not wait(pg, "S.gameOpen==='%s'&&document.querySelectorAll('#sheet .gbuy button').length===2" % GT, 8): bad(f"{tag}: Cancel should go back to the game page")
            time.sleep(.6)
            pg.locator("#sheet .gbuy button").nth(0).click()
            wait(pg, "!!document.querySelector('#sbx #sbbuy')", 8)
            pg.evaluate("closeModal()")              # the backdrop / a drag close the same way
            if not wait(pg, "S.gameOpen==='%s'&&document.querySelectorAll('#sheet .gbuy button').length===2" % GT, 8): bad(f"{tag}: closing the sheet any way should go back to the game page")
            time.sleep(.6)
            pg.evaluate("closeModal()"); time.sleep(.4)
        odd = pg.evaluate("""gameBuyBar({leg:{sport:"nfl');alert(1);('"},buy:[{t:"KXA-1-B",name:'B',ask:.4,mult:2.3},{t:"KX');alert(1);('",name:'C',ask:.6,mult:1.6},{t:"KXA-1-D",name:'D',ask:.5,mult:1.9}]})""")
        if "alert" in odd or odd.count("<button") != 2: bad(f"{tag}: gameBuyBar should drop odd tickers and sport codes: {odd[:300]}")
        # ---- (8) the web app's real action answers in plain words (nothing to buy in the test world)
        r = pg.evaluate("api('/app/api/act',{a:'singlequote',t:'KXNBAGAME-26NOV19ZZZYYY-ZZZ',real:1})")
        if not isinstance(r, dict) or r.get("ok") or not r.get("msg") or "{" in r.get("msg", ""): bad(f"{tag}: the real quote action should refuse in plain words: {r}")
        r = pg.evaluate("api('/app/api/act',{a:'singlebuy',t:'KXNBAGAME-26NOV19ZZZYYY-ZZZ',q:'0000000000000000',real:1})")
        if not isinstance(r, dict) or r.get("ok") or "fresh" not in r.get("msg", ""): bad(f"{tag}: buying an unknown quote should be refused: {r}")
        r = pg.evaluate("api('/app/api/act',{a:'singlebuy',t:'x y',q:'zz',real:1})")
        if not isinstance(r, dict) or r.get("ok"): bad(f"{tag}: a malformed buy should be refused: {r}")
        print(tag, "errs:", errs)
        if errs: bad(f"{tag}: JS errors: {errs}")
        ctx.close()
    br.close()
print("sent:", len(SENT))
if problems:
    print("PROBLEMS:", "; ".join(problems))
else:
    print("all good")
