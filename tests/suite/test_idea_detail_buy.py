# CHECK: group=page secs=50
"""The Buy idea detail page's Buy button (GitHub #252). Pete tapped a green "Buy · 11s" on the detail page and nothing
happened: the button was disabled (no edge left after the fee) while still drawn green with a countdown, and any answer
went to a toast that sat behind the page. At phone size (390, touch, see-through haptic switches on) this opens the
detail page from the real engine's ideas, gets a price (the Mac's answer faked at the route), and checks: no edge left =
no Buy, a plain "No longer a good bet" line and a "Get a new price" button; under the bar = a yellow "Buy anyway"; a
clear edge = a green Buy that a real tap sends, and the page then shows the answer (a refusal in Kalshi's words, an
unreachable Mac, a price that ran out, a bought one) both on the page and in a toast drawn above it; the numbers from
when the idea was found are marked older; the book's size at the ask reads "94k", not "94080". Prints PROBLEMS."""
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

QUOTE = {}; BUY = {}; SENT = []
def act(route):
    try: a = json.loads(route.request.post_data or "{}").get("a")
    except ValueError: a = None
    SENT.append(a)
    if a == "idea": route.fulfill(status=200, content_type="application/json", body=json.dumps(QUOTE["r"]))
    elif a in ("buy", "singlebuy"):
        if BUY.get("abort"): route.abort()
        else: route.fulfill(status=200, content_type="application/json", body=json.dumps(BUY["r"]))
    elif a in ("idea_dismiss",): route.fulfill(status=200, content_type="application/json", body='{"ok":true}')
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

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark", has_touch=True)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script("window.__hswForce=1;"); pg.add_init_script(upwait.COUNT_FETCHES)
    pg.goto(B + "/app"); upwait.go_and_hold(pg, "live")
    pg.route("**/app/api/act", act)
    seed(); inject(pg)
    # ---- Pete's screen: a live single whose fresh price has no edge left
    QUOTE["r"] = SQ(-.049, False, .40)
    pid = open_detail(pg, "Memphis")
    if not wait(pg, "/94k/.test(document.querySelector('#sheet').innerText)", 6): bad(f"the book's size at the ask should read 94k: {sheet(pg)[:600]!r}")
    if "94080" in sheet(pg): bad("the bare 94080 should be gone")
    if not get_price(pg, "Get today's price"): bad("Get today's price should show a fresh price")
    st = sheet(pg); b = buy_btn(pg)
    if "no longer a good bet" not in st.lower(): bad(f"no edge left should say 'No longer a good bet': {st[-700:]!r}")
    if "was 54%" not in st: bad(f"it should name the chance when found (54%) next to the new one: {st[-700:]!r}")
    if b and "Get a new price" not in b["t"] and (b["yes"] or b["dis"]): bad(f"no edge left: no green or dead Buy: {b}")
    if "Get a new price" not in st: bad("no edge left should offer 'Get a new price'")
    if "when this idea was found" not in st.lower(): bad("the older numbers should be marked 'When this idea was found'")
    if "pays if it wins" not in st.lower() or "4 contracts" not in st: bad(f"the fresh price should name contracts and payout: {st[-500:]!r}")
    if SHOTS: pg.screenshot(path=os.path.join(SHOTS, "idea252_noedge_phone390.png"), full_page=False)
    # ---- under the bar: yellow Buy anyway, and it works
    QUOTE["r"] = SQ(.006, False, .62)
    if not get_price(pg, "Get a new price"): bad("Get a new price should re-quote")
    b = buy_btn(pg)
    if not b or not b["warn"] or "Buy anyway" not in b["t"] or b["dis"]: bad(f"under the bar should be a working yellow 'Buy anyway': {b}")
    # ---- a clear edge: green Buy; a real tap (through the see-through switch) sends, and Kalshi's refusal shows on the page
    QUOTE["r"] = SQ(.05, True, .70)
    pg.evaluate("S.ideaq={};S.ideaSig=null;ideaSheet()"); time.sleep(.3)
    if not get_price(pg, "Get today's price"): bad("Get today's price should show a fresh price (2)")
    b = buy_btn(pg)
    if not b or not b["yes"] or b["dis"]: bad(f"a clear edge should be a working green Buy: {b}")
    if SHOTS: pg.screenshot(path=os.path.join(SHOTS, "idea252_green_phone390.png"))
    BUY["r"] = {"ok": False, "msg": "Kalshi refused this (400 code): test refusal words."}
    n0 = len(SENT)
    pg.locator("#sheet .idact .dbtns .btn.yes").first.click()
    if not wait(pg, "/test refusal words/.test(document.querySelector('#sheet').innerText)", 5): bad(f"a refusal should show on the detail page: {sheet(pg)[-400:]!r}")
    if "singlebuy" not in SENT[n0:]: bad(f"the Buy tap should send singlebuy: {SENT[n0:]}")
    if not toast_on_top(pg): bad("the toast should be drawn above the detail page")
    if SHOTS: pg.screenshot(path=os.path.join(SHOTS, "idea252_refused_phone390.png"))
    # ---- the price ran out before the tap: nothing sent, says so
    get_price(pg, "Get today's price")
    pg.evaluate("S.ideaq['%s'].at-=30" % pid); n0 = len(SENT)
    pg.evaluate("buySingle('%s')" % pid)
    if not wait(pg, "/ran out/.test(document.querySelector('#sheet').innerText)", 4): bad("an expired price should say it ran out")
    if "singlebuy" in SENT[n0:]: bad("an expired price must send nothing")
    # ---- the Mac can't be reached
    get_price(pg, "Get today's price"); BUY["abort"] = True
    pg.locator("#sheet .idact .dbtns .btn.yes").first.click()
    if not wait(pg, "/may or may not have gone through/.test(document.querySelector('#sheet').innerText)", 5): bad("an unreachable Mac should say it may or may not have gone through")
    BUY["abort"] = False
    # ---- a double tap sends one
    get_price(pg, "Get today's price"); n0 = len(SENT)
    BUY["r"] = {"ok": True, "pays": 4, "msg": "Bought 4 contracts at 60¢: pays $4 if it wins."}
    pg.evaluate("buySingle('%s');buySingle('%s')" % (pid, pid))
    if not wait(pg, "!document.querySelector('#modal').classList.contains('on')", 5): bad("a bought idea should close the detail page")
    if SENT[n0:].count("singlebuy") != 1: bad(f"a double tap should send one order: {SENT[n0:]}")
    if not wait(pg, "/Bought 4 contracts/.test(document.querySelector('#toast').innerText)", 3): bad("a buy should say what was bought")
    # ---- a combo under the bar: yellow Buy anyway
    seed(); inject(pg)
    QUOTE["r"] = {"ok": True, "i": 7, "pays": 40.0, "stake": 5.0, "pct": .97, "clears": False}
    open_detail(pg, "DDD")
    if get_price(pg, "Get my price"):
        b = buy_btn(pg)
        if not b or not b["warn"] or "Buy anyway" not in b["t"]: bad(f"a combo under the bar should be a yellow 'Buy anyway': {b}")
    else: bad("a combo's detail page should get a price")
    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad("sideways scroll")
    if errs: bad(f"page errors: {errs[:3]}")
    br.close()
print("PROBLEMS:" if problems else "PASS: idea detail Buy answers every tap (#252)", *problems, sep="\n  ")
sys.exit(1 if problems else 0)
