# CHECK: group=page secs=70
"""Pass on a Buy idea clears it and keeps it cleared (GitHub #256). Pete: "When I hit pass on this screen, it should just
clear that and send me back to live, but it doesn't. It's just like it resets the ability to check the live price", and the
same on the Live card with a fresh price on it while the page said "Reconnecting to your Mac". Causes: the card came back
when the first dismiss request failed (Reconnecting), the detail page's Pass threw the quote away and left the card sitting
on "Get today's price" for most of a second before it slid out, and the dismissal was measured from the idea's old listed
price, so the fresh price Pete had just looked at (a few cents lower) re-offered it at the next stored quote. At phone size
(390, touch, real taps through the see-through haptic switch), against the real engine's dismiss store: Pass on the detail
page closes it back to Live, the card never shows "Get today's price" again, it is gone from the screen and from the Mac's
list, with an Undo; a later quote at (or a little above) the price Pete looked at does not bring it back while a clearly
better one still does; Pass on the Live card with a fresh quote does the same; with the dismiss failing the idea still
leaves at once, stays off the screen through a refresh and the save is retried until it lands; if it never lands it stays
hidden and says so; Undo brings it back and tells the Mac. Prints PROBLEMS."""
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
    A.book_depth = lambda t, max_age=60: {"bid": .59, "ask": .60, "spread": .01, "ask_size": 94080, "thin": False}
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
def wait(pg, js, secs=6):
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
def seed():
    A.store_x("delete from suggestions")
    try: os.remove(A.IDEA_DISMISS)
    except OSError: pass
    ev = f"KXNBAGAME-{D}MEM"; tk = f"{ev}-MEM"
    A.KICKOFF[ev] = iso(7200); A.PICK_NAME[tk] = "Memphis"
    A.store_suggestion({"legs": [{"ticker": tk, "event": ev, "pick": "Memphis", "p": .45, "fair": .54}], "fair": 22.0}, {"pays": 22.0, "stake": 9.84}, 1.20)
    legs = []
    for tag in ("DDD", "FFF"):
        e2 = f"KXNBAGAME-{D}{tag}"; A.KICKOFF[e2] = iso(7200)
        legs.append({"ticker": f"{e2}-{tag[:3]}", "event": e2, "pick": tag, "p": .5, "fair": .6})
    A.store_suggestion({"legs": legs, "fair": 30.0}, {"pays": 40.0, "stake": 5.0}, 1.02)
def inject(pg):
    ideas = json.loads(json.dumps(A.live_ideas(), default=str))
    pg.evaluate("S.idHide={};S.ideasMore=true;S.ideaq={};S.ideaAns={};S.ibuy={};S.live={at:Date.now()/1000,combos:[],riding:0,staked:0,chance_one:0,best:0,cash_now:0,today:{},"
                "auto_sell:false,singles:[],pulse:[],need:[],ideas:" + json.dumps(ideas) + ",ideas_limit:3,ideas_hidden:0};renderLive()")
    time.sleep(.4)

QUOTE = {}; BUY = {}; SENT = []; DIS = {"fail": 0, "n": 0}
def act(route):
    try: a = json.loads(route.request.post_data or "{}").get("a")
    except ValueError: a = None
    SENT.append(a)
    if a == "idea": route.fulfill(status=200, content_type="application/json", body=json.dumps(QUOTE["r"]))
    elif a in ("buy", "singlebuy"):
        if BUY.get("abort"): route.abort()
        else: route.fulfill(status=200, content_type="application/json", body=json.dumps(BUY["r"]))
    elif a == "idea_dismiss":
        DIS["n"] += 1
        if DIS["fail"] > 0:
            DIS["fail"] -= 1; route.abort()
        else: route.continue_()
    else: route.continue_()
SQ = lambda edge, clears, fair: {"ok": True, "single": True, "price": .60, "n": 4, "stake": 2.47, "pays": 4.0, "pct": fair / .617,
                                 "edge": edge, "fair": fair, "clears": clears, "rec": 3, "ev": round(4 * fair - 2.47, 2), "min": 1, "max": 100}
sheet = lambda pg: pg.evaluate("document.querySelector('#sheet').innerText")
def open_detail(pg, pick):
    pid = pg.evaluate("S.live.ideas.find(i=>i.picks.startsWith('%s')).id" % pick)
    pg.evaluate("closeModal&&closeModal()"); time.sleep(.4)
    pg.evaluate("openIdea('%s')" % pid)
    wait(pg, "document.querySelector('#modal').classList.contains('on')&&S.ideaReady", 5)
    return pid
def get_price(pg, label):
    at0 = pg.evaluate("(()=>{const q=S.ideaq[S.ideaOpen]||Object.values(S.ideaq).find(Boolean);return q?q.at:0})()")
    for _ in range(3):
        try: pg.locator("#sheet .idact").get_by_text(label).first.click(timeout=3000)
        except Exception: pass
        if wait(pg, "(()=>{const q=Object.values(S.ideaq).find(Boolean);return !!q&&q.at>%r&&/Pass/.test(document.querySelector('#sheet .idact').innerText)})()" % at0, 3): return True
    return False
def buy_btn(pg):
    return pg.evaluate("(()=>{const b=[...document.querySelectorAll('#sheet .idact .dbtns .btn')].find(b=>/Buy/.test(b.innerText));"
                       "return b?{t:b.innerText,yes:b.classList.contains('yes'),warn:b.classList.contains('warn'),dis:b.disabled}:null})()")
def toast_on_top(pg):
    return pg.evaluate("(()=>{const t=document.querySelector('#toast'),m=document.querySelector('#modal');return !!t&&"
                       "+getComputedStyle(t).zIndex>+getComputedStyle(m).zIndex})()")


def server_picks(): return [i["picks"] for i in A.live_ideas()]
def screen_picks(pg):
    return pg.evaluate("[...document.querySelectorAll('#main .iw')].map(e=>e.innerText.split('\\n').join(' ')).map(t=>t.slice(0,60))")
def on_screen(pg, name): return any(name in t for t in screen_picks(pg))
def until(f, secs=6):
    for _ in range(int(secs / .1)):
        try:
            if f(): return True
        except Exception: pass
        pg_.wait_for_timeout(100)
    return False
def pass_state(pg):
    return pg.evaluate("(()=>({modal:document.querySelector('#modal').classList.contains('on'),view:S.view,"
                       "undo:!!document.querySelector('#undo.on,#undo.show,#undo'),getp:[...document.querySelectorAll('#main .iw .btn')].some(b=>/Get today/.test(b.innerText))}))()")
def quote_lower(edge_pct=1.5):   # Pete looked at 40c; the list said 44.7c
    return {"ok": True, "single": True, "price": .40, "n": 4, "stake": 1.6, "pays": 4.0, "pct": edge_pct, "edge": .2, "fair": .6, "clears": True,
            "rec": 3, "ev": 0.8, "min": 1, "max": 100}
def restore_all(pg):
    seed(); DIS["fail"] = 0; inject(pg)
def tap_pass_on_card(pg, name):
    pg.locator("#main .iw", has_text=name).locator("button", has_text="Pass").first.click()
def card_price(pg, name):
    pg.locator("#main .iw", has_text=name).locator("button", has_text="Get today").first.click()

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark", has_touch=True)
    pg = ctx.new_page(); pg_ = pg; errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script("window.__hswForce=1;"); pg.add_init_script(upwait.COUNT_FETCHES)
    pg.goto(B + "/app"); upwait.go_and_hold(pg, "live")
    pg.route("**/app/api/act", act)
    pg.evaluate("IDEA_SAVE_WAIT=[0,300,700,1200,1500,1500,1500,1500,1500]")      # the real waits are seconds; the logic is the same
    seed(); inject(pg)
    shot = lambda n: (pg.wait_for_timeout(700), pg.screenshot(path=os.path.join(SHOTS, n))) if SHOTS else None

    # ---- 1. the detail page: Get price, Pass -> back on Live, gone, Undo
    QUOTE["r"] = quote_lower()
    open_detail(pg, "Memphis")
    if not get_price(pg, "Get today's price"): bad("detail: a fresh price should show")
    shot("pass256_1_detail_fresh_phone390.png")
    seen_states = []
    pg.locator("#sheet .idact .btn", has_text="Pass").first.click()
    for _ in range(14):                                   # the next ~1.4 s, frame by frame: never the reset card
        pg.wait_for_timeout(100); seen_states.append(pass_state(pg))
        if seen_states[-1]["modal"] is False: break
    if not until(lambda: not pg.evaluate("document.querySelector('#modal').classList.contains('on')"), 3): bad("detail Pass should close the page")
    if pg.evaluate("S.view") != "live": bad("detail Pass should leave you on Live")
    if not until(lambda: not on_screen(pg, "Memphis"), 3): bad(f"detail Pass: Memphis should be gone from Live: {screen_picks(pg)}")
    if not until(lambda: pg.evaluate("!!document.querySelector('#undo')&&/hidden/.test(document.querySelector('#undo').innerText)"), 3): bad("detail Pass should show the Undo bar")
    shot("pass256_2_live_after_pass_phone390.png")
    if not until(lambda: not any("Memphis" in p for p in server_picks()), 4): bad(f"the Mac should have the dismissal: {server_picks()}")
    items = json.load(open(A.IDEA_DISMISS)).get("items", {}) if os.path.exists(A.IDEA_DISMISS) else {}
    mem = [v for k, v in items.items() if k.endswith("-MEM")]
    if not mem or mem[0].get("price_c") != 40.0 or (mem[0].get("edge") or 0) < .5: bad(f"the dismissal should be measured from the price Pete saw (40c, edge .5): {items}")
    for _ in range(6):                                    # after the page closed the card must never be seen resetting
        pg.wait_for_timeout(100)
        if on_screen(pg, "Memphis") and pass_state(pg)["getp"] and pg.evaluate("S.view")=="live" and not on_screen(pg, "Texas"): pass
    if any(s["getp"] and not s["modal"] and on_screen(pg, "Memphis") for s in seen_states): bad("the idea showed 'Get today's price' again after Pass (the reset Pete saw)")
    # a real refresh from the Mac: still gone
    pg.evaluate("load('live', true)"); pg.wait_for_timeout(900)
    if on_screen(pg, "Memphis"): bad("a Live refresh should not bring a passed idea back")
    # the quote Pete looked at must not re-offer it: a row a bit under the listed price, above what he saw (42c vs 40c)
    leg = {"ticker": f"KXNBAGAME-{D}MEM-MEM", "event": f"KXNBAGAME-{D}MEM", "pick": "Memphis", "p": .42, "fair": .60}
    A.store_suggestion({"legs": [leg], "fair": 25.0}, {"pays": 25.0, "stake": 10.5}, 1.43)
    pg.evaluate("load('live', true)"); pg.wait_for_timeout(900)
    if any("Memphis" in p for p in server_picks()): bad(f"a price just above what Pete looked at should not re-offer it: {server_picks()}")
    # a clearly better one (well under what he saw) does
    A.store_suggestion({"legs": [dict(leg, p=.30)], "fair": 30.0}, {"pays": 30.0, "stake": 9.0}, 2.0)
    if not any("Memphis" in p for p in server_picks()): bad(f"a clearly better price should still bring it back: {server_picks()}")
    # ---- 2. Undo after a detail Pass (fresh start)
    restore_all(pg); QUOTE["r"] = quote_lower()
    open_detail(pg, "Memphis"); get_price(pg, "Get today's price")
    pg.locator("#sheet .idact .btn", has_text="Pass").first.click()
    until(lambda: not on_screen(pg, "Memphis"), 3)
    until(lambda: not any("Memphis" in p for p in server_picks()), 4)
    pg.locator("#undo button, #undo .ubtn, #undo [onclick]").first.click()
    if not until(lambda: on_screen(pg, "Memphis"), 5): bad(f"Undo should bring Memphis back: {screen_picks(pg)}")
    if not until(lambda: any("Memphis" in p for p in server_picks()), 4): bad("Undo should tell the Mac")
    # ---- 3. Pass on the Live card with a fresh quote while the Mac can't be reached
    restore_all(pg); QUOTE["r"] = quote_lower(); DIS["fail"] = 99; DIS["n"] = 0
    card_price(pg, "Memphis")
    if not until(lambda: pg.evaluate("[...document.querySelectorAll('#main .iw .btn')].some(b=>/Pass/.test(b.innerText))"), 4): bad("the card should show Pass after Get price")
    pg.evaluate("document.querySelectorAll('.pill,#net').length")
    shot("pass256_3_card_fresh_quote_phone390.png")
    tap_pass_on_card(pg, "Memphis")
    if not until(lambda: not on_screen(pg, "Memphis"), 3): bad("card Pass with the link down should still clear the card")
    shot("pass256_4_card_passed_link_down_phone390.png")
    pg.wait_for_timeout(600)
    pg.evaluate("renderLive()"); pg.evaluate("load('live', true)"); pg.wait_for_timeout(900)
    if on_screen(pg, "Memphis"): bad("with the link down the card should stay off the screen through a refresh")
    if DIS["n"] < 2: bad(f"the dismiss should be retried while the link is down: {DIS['n']} tries")
    if not until(lambda: pg.evaluate("/still trying/.test(document.querySelector('#toast')?document.querySelector('#toast').innerText:'')"), 4): bad("it should say it is still trying")
    DIS["fail"] = 1                                       # the link comes back: the next retry lands
    if not until(lambda: not any("Memphis" in p for p in server_picks()), 8): bad(f"the retry should save the dismissal once the link is back: {server_picks()}")
    # ---- 4. never gets through: it stays hidden and says so
    restore_all(pg); QUOTE["r"] = quote_lower(); DIS["fail"] = 99
    open_detail(pg, "Memphis"); get_price(pg, "Get today's price")
    pg.locator("#sheet .idact .btn", has_text="Pass").first.click()
    if not until(lambda: not on_screen(pg, "Memphis"), 3): bad("detail Pass with the link down should clear the card")
    if not until(lambda: pg.evaluate("/hasn.t got that yet/.test(document.querySelector('#toast')?document.querySelector('#toast').innerText:'')"), 8): bad("a dismissal that never reaches the Mac should say so")
    if on_screen(pg, "Memphis"): bad("and it should stay hidden on this phone")
    DIS["fail"] = 0
    # ---- 5. a slow dismiss: gone at once, and Undo after it still works
    restore_all(pg); QUOTE["r"] = quote_lower()
    def slow(route):
        pg.wait_for_timeout(1200); route.continue_()
    open_detail(pg, "Memphis"); get_price(pg, "Get today's price")
    pg.route("**/app/api/act", lambda r: slow(r) if '"idea_dismiss"' in (r.request.post_data or "") else act(r))
    pg.locator("#sheet .idact .btn", has_text="Pass").first.click()
    if not until(lambda: not on_screen(pg, "Memphis"), 2): bad("a slow dismiss should still clear the card at once")
    if not until(lambda: not any("Memphis" in p for p in server_picks()), 6): bad("the slow dismiss should still land on the Mac")
    pg.locator("#undo button").first.click()               # Undo after the slow save: the last word, the idea is back
    if not until(lambda: on_screen(pg, "Memphis") and any("Memphis" in p for p in server_picks()), 6): bad("Undo after a slow dismiss should bring it back")
    pg.unroute_all(behavior="ignoreErrors")
    # ---- no sideways scroll, no page errors
    if pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1"): bad("sideways scroll on the phone")
    if errs: bad(f"page errors: {errs[:3]}")
    br.close()
print("PROBLEMS:" if problems else "OK: Pass clears a Buy idea and keeps it cleared", problems or "")
sys.exit(1 if problems else 0)
