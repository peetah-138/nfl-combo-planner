# CHECK: group=page secs=39
"""Percent (and dollar) change vs what was paid (GitHub #100, display only): Live combo rows, single/spread/total
rows, the hero and the combo detail. Values, colours, the sign flip, the %/$/both switch (remembered), rolling numbers,
no sideways scroll at 360 and 390 pt, no JS errors. The numbers are drawn into the page; nothing real is touched."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
tk_ev = sorted({m["event_ticker"] for m in mk})
def L(i, team): ev = tk_ev[i]; return {"ticker": f"{ev}-{team}", "event_ticker": ev, "event": ev, "side": "yes"}
bets = [{"ticker": "KXMVE-1", "legs": [L(0, "BOS"), L(1, "DEN")], "cost": 3.0, "pays": 41.2, "status": "pending", "back": 0,
         "week": "2026-11-17", "full_pays": 41.2, "lg": "nba", "lgs": ["nba"]}]
def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: (bets, 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
import upwait

def until(pg, js, secs=10):
    end = time.time() + secs
    while time.time() < end:
        try:
            if pg.evaluate(js): return True
        except Exception: pass
        time.sleep(.1)
    return False


# one combo (paid 3.00) and one single (paid 5.00); offers are set per case
SETUP = """([o,w,cost])=>{const d=S.live;const c=d.combos[0];c.group='pending';c.cost=cost||3;c.offer=o;c.offer_live=null;c.offer_real=false;
 d.singles=[{t:'KXS-1',label:'Celtics',kind:'win',sport:'nba',state:'live',cost:5,pays:12,chance:.4,worth:w,game:'Celtics at Knicks',legs:[]}];
 S.view='live';renderLive();}"""
# text is innerText (only what is visible, one line per part); colour is compared with the app's own tokens
GRAB = """()=>{const probe=v=>{const e=document.createElement('i');e.style.color='var(--'+v+')';document.body.appendChild(e);const c=getComputedStyle(e).color;e.remove();return c;};
 const P={up:probe('yes'),down:probe('no'),flat:probe('sub')};const nm=c=>Object.keys(P).find(k=>P[k]===c)||c;
 const q=s=>[...document.querySelectorAll(s)].map(e=>({t:e.innerText.trim().split('\\n'),col:nm(getComputedStyle(e).color)}));
 const h=document.querySelector('.hv .delta');
 return {combo:q('.trow:not(.srow1) .offer .chg'),single:q('.srow1 .chg'),hero:h?h.innerText.trim():'',
  heroPre:h?getComputedStyle(h.querySelector('.cd'),'::before').content:'',over:document.documentElement.scrollWidth-document.documentElement.clientWidth}}"""
CH = ".trow:not(.srow1) .offer .chg"

def settle(pg, sel, want, secs=6):
    r = _settle(pg, sel, want, secs)
    if not r: print("PROBLEMS: never settled on", want, pg.evaluate("document.querySelector(%r)&&document.querySelector(%r).innerText" % (sel, sel)))
    return r
def _settle(pg, sel, want, secs=8):
    """the visible text of the first `sel` matches `want` (a JS regex source) on 4 polls in a row: the roll has ended"""
    js = "(()=>{const e=document.querySelector(%r);return !!e&&new RegExp(%r).test(e.innerText.trim().replace(/\\n/g,' | '))})()" % (sel, want)
    end = time.time() + secs; n = 0
    while time.time() < end:
        try: n = n + 1 if pg.evaluate(js) else 0
        except Exception: n = 0
        if n >= 4: return True
        time.sleep(.12)
    return False

def check(cond, msg, *a):
    if not cond: print("PROBLEMS:", msg, *a)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme, w in (("dark", 390), ("light", 360), ("dark", 360)):
        ctx = br.new_context(viewport={"width": w, "height": 844}, device_scale_factor=2, color_scheme=scheme, has_touch=True, is_mobile=True)
        pg = ctx.new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script(upwait.COUNT_FETCHES)
        pg.goto(B + "/app")
        upwait.go_and_hold(pg, "live")
        if not until(pg, "S.live&&S.live.combos&&S.live.combos.length"): print("PROBLEMS: no combo to draw into"); continue
        pg.evaluate("window.load=async()=>{};try{localStorage.removeItem('cw_chg')}catch(e){};setChg('both')")
        tag = f"{w} {scheme}"
        # a loss on an estimate: paid 3, offer 2.78 -> "≈ −7%" and "≈ −$0.22" (cents always), red; a single -20%, -$1.00
        pg.evaluate(SETUP, [2.78, 4.00]); settle(pg, CH, r"^≈ −7% \| ≈ −\$0\.22$"); settle(pg, ".srow1 .chg", r"^−20% \| −\$1\.00$")
        g = pg.evaluate(GRAB); print(tag, "loss:", g)
        c, s = g["combo"][0], g["single"][0]
        check(c["t"] == ["≈ −7%", "≈ −$0.22"] and c["col"] == "down", "combo loss text/colour", c)
        check(s["t"] == ["−20%", "−$1.00"] and s["col"] == "down", "single loss text/colour (a real worth: no approx sign)", s)
        check("%" in g["hero"], "hero shows no percent", g["hero"])
        check(g["heroPre"] == '"≈ "', "hero pill should carry the approx sign on an estimate", g["heroPre"])
        check(g["over"] <= 1, "sideways scroll", g["over"])
        check("tabular" in pg.evaluate("getComputedStyle(document.querySelector('.chg')).fontVariantNumeric"), "not tabular")
        # sign flip: the row's height must not change; text and colour do
        h0 = pg.evaluate("document.querySelector('.trow').getBoundingClientRect().height")
        pg.evaluate(SETUP, [3.30, 6.00]); settle(pg, CH, r"^≈ \+10% \| ≈ \+\$0\.30$"); settle(pg, ".srow1 .chg", r"^\+20% \| \+\$1\.00$")
        g = pg.evaluate(GRAB); h1 = pg.evaluate("document.querySelector('.trow').getBoundingClientRect().height")
        c, s = g["combo"][0], g["single"][0]
        check(c["t"] == ["≈ +10%", "≈ +$0.30"] and c["col"] == "up", "combo gain", c)
        check(s["t"][0] == "+20%" and s["col"] == "up", "single gain", s)
        check(abs(h0 - h1) <= 1, "row height jumped on a sign flip", h0, h1)
        check(g["over"] <= 1, "sideways scroll after flip", g["over"])
        # paid 10, offer 9.97 is -0.3% and -$0.03: the % rounds to 0 (grey, no sign); the $ part still says -$0.03
        pg.evaluate(SETUP, [9.97, 5.0, 10]); settle(pg, CH, r"^≈ 0% \| ≈ −\$0\.03$")
        c = pg.evaluate(GRAB)["combo"][0]
        check(c["t"][0] == "≈ 0%" and c["col"] == "down", "both mode: the cents still say down, so red", c)
        pg.evaluate("setChg('pct')"); c = pg.evaluate(GRAB)["combo"][0]
        check(c["t"] == ["≈ 0%"] and c["col"] == "flat", "0% shown must be grey, never coloured", c)
        pg.evaluate("setChg('both')")
        # symmetric rounding: -0.5% and +0.5% match in magnitude
        r = pg.evaluate("[fmtNum(.005,'chg'),fmtNum(-.005,'chg'),fmtNum(.0049,'chg'),fmtNum(-.0049,'chg'),fmtNum(-.0005,'chgd')]")
        check(r == ["+1%", "−1%", "0%", "0%", "$0.00"], "rounding not symmetric / sign on zero", r)
        # bigger dollars still fit the column
        pg.evaluate(SETUP, [12.5, 4.0, 25]); settle(pg, CH, r"^≈ −50% \| ≈ −\$12\.50$")
        check(pg.evaluate(GRAB)["over"] <= 1, "sideways scroll with bigger dollars")
        # rolling: sample the text every frame while the number moves; it must pass through in-between values
        pg.evaluate(SETUP, [2.78, 4.0]); settle(pg, CH, r"^≈ −7% \| ≈ −\$0\.22$")
        pg.evaluate("window.__s=[];(function f(){const e=document.querySelector('%s .cp');if(e)window.__s.push(e.textContent);if(window.__s.length<80)requestAnimationFrame(f)})()" % CH)
        pg.evaluate(SETUP, [3.30, 4.0]); settle(pg, CH, r"^≈ \+10% \| ≈ \+\$0\.30$")
        seen = set(pg.evaluate("window.__s"))
        print(tag, "rolling samples:", sorted(seen))
        check(len(seen - {"≈ −7%", "≈ +10%"}) >= 1, "the percent did not roll through in-between values", sorted(seen))
        pg.evaluate(SETUP, [2.78, 4.0]); settle(pg, CH, r"^≈ −7% \| ≈ −\$0\.22$")
        # the switch: no redraw (same row node, scroll kept), % only, $ only, remembered, aria-pressed
        pg.evaluate("window.__row=document.querySelector('.trow');window.scrollTo(0,200)")
        pg.evaluate("setChg('pct')"); c = pg.evaluate(GRAB)
        check(c["combo"][0]["t"] == ["≈ −7%"], "% only", c["combo"][0])
        check(pg.evaluate("window.__row===document.querySelector('.trow')&&scrollY>150"), "the switch redrew the page or moved the scroll")
        pg.evaluate("setChg('usd')"); g = pg.evaluate(GRAB)
        check(g["combo"][0]["t"] == ["≈ −$0.22"], "$ only", g["combo"][0])
        check("%" not in g["hero"], "hero should drop the % in $ mode", g["hero"])
        check(pg.evaluate("localStorage.getItem('cw_chg')") == "usd", "choice not remembered")
        check(g["over"] <= 1, "sideways scroll in $ mode")
        check(pg.evaluate("[...document.querySelectorAll('.chgsw button')].every(b=>b.getAttribute('aria-pressed')===String(b.dataset.k==='usd'))"), "aria-pressed wrong")
        pg.evaluate("setChg('both')")
        # hit target at least 44 x 44, and a visible focus ring from the keyboard
        sz = pg.evaluate("[...document.querySelectorAll('.chgsw button')].map(b=>{const r=b.getBoundingClientRect();return [Math.round(r.width),Math.round(r.height)]})")
        check(all(a >= 44 and b >= 44 for a, b in sz), "switch buttons under 44pt", sz)
        pg.keyboard.press("Tab")
        pg.evaluate("document.querySelector('.chgsw button').focus()")
        check(pg.evaluate("document.activeElement.matches(':focus-visible')&&getComputedStyle(document.activeElement).outlineStyle!=='none'"), "no focus ring on the switch")
        # a real tap on the switch
        pg.evaluate("window.scrollTo(0,0)")
        pg.locator(".chgsw button").nth(1).tap(); check(pg.evaluate("S.chg") == "pct", "tapping % did not switch")
        pg.locator(".chgsw button").nth(0).tap(); check(pg.evaluate("S.chg") == "both", "tapping % + $ did not switch")
        if os.environ.get("SHOTS"):
            pg.evaluate("document.querySelector('.chgbar').scrollIntoView({block:'start'});window.scrollBy(0,-70)"); time.sleep(.5)
            pg.screenshot(path=os.environ["SHOTS"] + f"/pct_live_{scheme}_{w}.png")
            pg.evaluate("window.scrollTo(0,0)"); time.sleep(.3); pg.screenshot(path=os.environ["SHOTS"] + f"/pct_hero_{scheme}_{w}.png", clip={"x": 0, "y": 60, "width": w, "height": 300})
        # combo detail: the same offer number as the row (offNow), the approx sign, cents
        def fix(route):
            resp = route.fetch(); j = resp.json()
            if j.get("combo"): j["combo"].update(offer=2.78, offer_live=None, offer_real=False, cost=3, group="pending")
            route.fulfill(response=resp, body=json.dumps(j))
        pg.route("**/app/api/combo*", fix)
        pg.evaluate("openCombo(S.live.combos[0].t)")
        until(pg, "(()=>{const e=document.querySelector('.dkpis .chg .cp');return !!e&&/−7%/.test(e.textContent)})()", 8)
        r = pg.evaluate("(()=>{const e=document.querySelector('.dkpis .chg');return e?e.innerText.trim().split('\\n'):null})()")
        pg.unroute("**/app/api/combo*")
        print(tag, "detail:", r)
        check(r == ["≈ −7%", "≈ −$0.22"], "combo detail change", r)
        # settled view and singles-only: the switch shows whenever a change line does
        pg.evaluate("closeModal()")
        pg.evaluate(SETUP, [2.78, 4.0]); pg.evaluate("S.filter='done';renderLive()")
        check(pg.evaluate("!!document.querySelector('.stbl .chg')&&!!document.querySelector('.chgbar')"), "settled view: single change line without a switch")
        pg.evaluate("S.filter='all';S.live.combos.forEach(c=>c.group='won');renderLive()")
        check(pg.evaluate("!!document.querySelector('.stbl .chg')&&!!document.querySelector('.chgbar')"), "singles only: change line without a switch")
        # reduced motion: the final numbers at once
        pg.emulate_media(reduced_motion="reduce")
        pg.evaluate(SETUP, [2.5, 4.0])
        check(settle(pg, CH, r"^≈ −17% \| ≈ −\$0\.50$"), "reduced motion value", pg.evaluate(GRAB)["combo"])
        print(tag, "errs:", errs)
        if errs: print("PROBLEMS: JS errors", errs)
        ctx.close()
    br.close()
