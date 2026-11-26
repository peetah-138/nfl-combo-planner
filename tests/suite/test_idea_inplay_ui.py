# CHECK: group=page secs=45
"""A single-game Buy idea whose game is UNDER WAY (GitHub #255, Pete's ruling: option 2). The fresh price's fair chance comes
only from a live line or the live model; with neither there is no fair price. At phone size (390, touch, see-through
haptic switches on) on the real engine's ideas, with the Mac's quote answer faked at the route: a live line = the card and
the detail page say 'live line' under Fair chance and a green Buy; the live model on a thin market = 'live model', the
caution, a yellow Buy anyway; no live fair = 'none', a dash for the fair chance and the edge, 'No fair price to check
this against', a working yellow Buy anyway (never green, never 'no longer a good bet' math); before the game = unchanged
(the sportsbooks' chance, green); a combo with a game under way and only a pre-game chance = yellow Buy anyway with the
same words. Screenshots with SHOTS=dir. Prints PROBLEMS."""
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
    A._held_all = lambda: []   # no singles held (the combo-vs-held-single guard reads the account)
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


LQ = lambda **k: dict({"ok": True, "single": True, "price": .60, "n": 4, "stake": 2.47, "pays": 4.0, "pct": .66 / .6168,
                       "edge": round(.66 - .6168, 4), "fair": .66, "clears": True, "rec": 3, "ev": round(4 * .66 - 2.47, 2),
                       "min": 1, "max": 100, "live": True, "how": "live sportsbook line", "fair_src": "live line",
                       "nofair": None, "warn": [{"k": "live", "t": "This game is under way. Our chance is live (live line), not the pre-game one."}]}, **k)
def card(pg, pick):
    return pg.evaluate("(()=>{const x=S.live.ideas.find(i=>i.picks.startsWith('%s'));const c=document.querySelector('.iw[data-id=\"'+x.id+'\"]');return c?c.innerText:''})()" % pick)
def card_btn(pg, pick):
    return pg.evaluate("(()=>{const x=S.live.ideas.find(i=>i.picks.startsWith('%s'));const c=document.querySelector('.iw[data-id=\"'+x.id+'\"]');"
                       "const b=c&&[...c.querySelectorAll('.dbtns .btn')].find(b=>/Buy/.test(b.innerText));return b?{t:b.innerText,yes:b.classList.contains('yes'),warn:b.classList.contains('warn'),dis:b.disabled}:null})()" % pick)
def card_price(pg, pick):
    pg.evaluate("closeModal&&closeModal()"); time.sleep(.4)
    pg.evaluate("S.ideaq={};renderLive()"); time.sleep(.2)
    pid = pg.evaluate("S.live.ideas.find(i=>i.picks.startsWith('%s')).id" % pick)
    pg.evaluate("priceIdea('%s')" % pid)
    return wait(pg, "(()=>{const q=S.ideaq['%s'];return !!q&&/Pass/.test(document.querySelector('.iw[data-id=\"%s\"]').innerText)})()" % (pid, pid), 5)
def shot(pg, name):                               # the fresh price and its buttons in view
    if SHOTS:
        pg.evaluate("(()=>{const e=document.querySelector('#sheet .inow');if(e)e.scrollIntoView({block:'start'})})()"); time.sleep(.3)
        pg.screenshot(path=os.path.join(SHOTS, name), full_page=False)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark", has_touch=True)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script("window.__hswForce=1;"); pg.add_init_script(upwait.COUNT_FETCHES)
    pg.goto(B + "/app"); upwait.go_and_hold(pg, "live")
    pg.route("**/app/api/act", act)
    seed(); inject(pg)
    # ---- (1) a live line: the source line says so, green Buy
    QUOTE["r"] = LQ()
    if not card_price(pg, "Memphis"): bad("the card should show a fresh price (live line)")
    c = card(pg, "Memphis"); b = card_btn(pg, "Memphis")
    if "live line" not in c.lower(): bad(f"card: Fair chance should say 'live line': {c[-500:]!r}")
    if "66%" not in c or "under way" not in c.lower(): bad(f"card: the live 66% and 'game under way': {c[-500:]!r}")
    if not b or not b["yes"] or b["dis"]: bad(f"card: a live line with an edge = a working green Buy: {b}")
    pg.evaluate("S.ideaq={}"); pid = open_detail(pg, "Memphis")
    if not get_price(pg, "Get today's price"): bad("detail: Get today's price (live line)")
    st = sheet(pg); b = buy_btn(pg)
    if "live line" not in st.lower(): bad(f"detail: Fair chance should say 'live line': {st[-600:]!r}")
    if not b or not b["yes"]: bad(f"detail: live line = green Buy: {b}")
    shot(pg, "idea255_live_line_phone390.png")
    # ---- (2) the live model on a thin market: yellow, the caution shows
    QUOTE["r"] = LQ(how="live model", fair_src="live model", clears=False, warn=[
        {"k": "live", "t": "This game is under way. Our chance is live (live model), not the pre-game one."},
        {"k": "thin", "t": "Thin market: 9¢ between the buy and sell prices, so this price may not be a real one."}])
    pg.evaluate("S.ideaq={};S.ideaSig=null;ideaSheet()"); time.sleep(.3)
    if not get_price(pg, "Get today's price"): bad("detail: Get today's price (live model)")
    st = sheet(pg); b = buy_btn(pg)
    if "live model" not in st.lower() or "thin market" not in st.lower(): bad(f"detail: 'live model' and the thin caution: {st[-700:]!r}")
    if not b or not b["warn"] or "Buy anyway" not in b["t"]: bad(f"detail: thin live market = yellow Buy anyway: {b}")
    if "under your bar" in st.lower() or "market is thin" not in st.lower(): bad(f"detail: a thin live market says thin, not 'under your bar': {st[-700:]!r}")
    # ---- (2b) a live chance below the one when found is not called 'dropped' (live chances move all game)
    QUOTE["r"] = LQ(fair=.45, edge=-.17, pct=.45 / .6168)
    pg.evaluate("S.ideaq={};S.ideaSig=null;ideaSheet()"); time.sleep(.3)
    if not get_price(pg, "Get today's price"): bad("detail: Get today's price (live, lower chance)")
    st = sheet(pg)
    if "has dropped" in st.lower(): bad(f"detail: no 'dropped' line for a live chance: {st[-500:]!r}")
    # ---- (3) no live fair: no edge, no green, a working yellow Buy anyway
    QUOTE["r"] = LQ(fair=None, edge=None, pct=None, ev=None, clears=False, rec=2, how=None, fair_src="none",
                    nofair="no fresh live score", warn=[{"k": "live", "t": "This game is under way. There's no live fair price, so you'd be going on Kalshi's price alone."}])
    pg.evaluate("S.ideaq={};S.ideaSig=null;ideaSheet()"); time.sleep(.3)
    if not get_price(pg, "Get today's price"): bad("detail: Get today's price (no live fair)")
    st = sheet(pg); b = buy_btn(pg)
    if "no fair price to check this against" not in st.lower(): bad(f"detail: 'No fair price to check this against': {st[-700:]!r}")
    if "no longer a good bet" in st.lower() or "under your bar" in st.lower(): bad(f"detail: no edge math without a fair price: {st[-700:]!r}")
    low = st.lower()
    if "fair chance\n—\nno fair price" not in low.replace("\n\n", "\n"): bad(f"detail: Fair chance '—' with 'no fair price' under it: {st[-700:]!r}")
    if "recommended" in low.split("your bet")[-1] or "smallest" not in low: bad(f"detail: no 'recommended' stake without a fair price: {st[-400:]!r}")
    if "NaN" in st or "null" in st: bad("detail: NaN/null on screen")
    if not b or b["yes"] or not b["warn"] or "Buy anyway" not in b["t"] or b["dis"]: bad(f"detail: no live fair = a working yellow Buy anyway, never green: {b}")
    shot(pg, "idea255_no_fair_phone390.png")
    n0 = len(SENT); BUY["r"] = {"ok": False, "msg": "Kalshi refused this (400 code): test."}
    pg.locator("#sheet .idact .dbtns .btn.warn").first.click()
    if not wait(pg, "/Kalshi refused this/.test(document.querySelector('#sheet').innerText)", 5): bad("detail: Buy anyway should send and show the answer")
    if "singlebuy" not in SENT[n0:]: bad(f"Buy anyway should send singlebuy: {SENT[n0:]}")
    if not card_price(pg, "Memphis"): bad("the card should show a fresh price (no live fair)")
    c = card(pg, "Memphis"); b = card_btn(pg, "Memphis")
    if "no fair price to check this against" not in c.lower(): bad(f"card: 'No fair price to check this against': {c[-500:]!r}")
    if not b or b["yes"] or not b["warn"]: bad(f"card: no live fair = yellow, never green: {b}")
    # ---- (4) before the game: unchanged (the sportsbooks' chance, green)
    QUOTE["r"] = LQ(live=False, how="sportsbooks", fair_src="sportsbooks", warn=[], fair=.67, edge=.053, pct=.67 / .6168)
    pg.evaluate("closeModal&&closeModal()"); time.sleep(.4)
    pg.evaluate("S.ideaq={}"); open_detail(pg, "Memphis")
    if not get_price(pg, "Get today's price"): bad("detail: Get today's price (pregame)")
    st = sheet(pg); b = buy_btn(pg)
    if "sportsbooks" not in st.lower() or "under way" in st.lower().split("kalshi's price now")[-1]: bad(f"detail: pregame = sportsbooks, not under way: {st[-600:]!r}")
    if not b or not b["yes"]: bad(f"detail: pregame with an edge = green Buy: {b}")
    shot(pg, "idea255_pregame_phone390.png")
    # ---- (5) a combo with a game under way the board only has pre-game for: yellow Buy anyway, same words
    QUOTE["r"] = {"ok": True, "i": 7, "pays": 40.0, "stake": 5.0, "pct": None, "clears": False, "live": True, "fair_src": "none",
                  "nofair": "DDD is under way and the board only has a pre-game chance"}
    pg.evaluate("closeModal&&closeModal()"); time.sleep(.4)
    pg.evaluate("S.ideaq={}"); open_detail(pg, "DDD")
    if get_price(pg, "Get my price"):
        st = sheet(pg); b = buy_btn(pg)
        if "no fair price to check this against" not in st.lower(): bad(f"combo: 'No fair price to check this against': {st[-500:]!r}")
        if not b or b["yes"] or not b["warn"] or "Buy anyway" not in b["t"]: bad(f"combo: yellow Buy anyway: {b}")
    else: bad("combo: the detail page should get a price")
    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad("sideways scroll")
    if errs: bad(f"page errors: {errs[:3]}")
    br.close()
print("PROBLEMS:" if problems else "PASS: in-play Buy ideas price only on a live fair (#255)", *problems, sep="\n  ")
sys.exit(1 if problems else 0)
