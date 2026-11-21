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
SETUP = """([o,w])=>{const d=S.live;const c=d.combos[0];c.group='pending';c.cost=3;c.offer=o;c.offer_live=null;c.offer_real=false;
 d.singles=[{t:'KXS-1',label:'Celtics',kind:'win',sport:'nba',state:'live',cost:5,pays:12,chance:.4,worth:w,game:'Celtics at Knicks',legs:[]}];
 S.view='live';renderLive();}"""
GRAB = """()=>{const q=s=>[...document.querySelectorAll(s)].map(e=>({t:e.textContent.trim(),c:e.className,col:getComputedStyle(e).color}));
 return {combo:q('.trow:not(.srow1) .offer .chg'),single:q('.srow1 .chg'),hero:(document.querySelector('.hv .delta')||{}).textContent,
  heroCls:(document.querySelector('.hv .delta')||{}).className,over:document.documentElement.scrollWidth-document.documentElement.clientWidth}}"""

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
        pg.evaluate("window.load=async()=>{};try{localStorage.removeItem('cw_chg')}catch(e){};S.chg='both'")
        # a loss: paid 3, offer 2.78 -> -7%, -$0.22, red
        pg.evaluate(SETUP, [2.78, 4.00]); until(pg, "!!document.querySelector('.chg')"); time.sleep(.9)
        g = pg.evaluate(GRAB)
        print(w, scheme, "loss:", g)
        c, s = g["combo"][0], g["single"][0]
        if "−7%" not in c["t"] or "−$0.22" not in c["t"] or "down" not in c["c"]: print("PROBLEMS: combo loss text/colour", c)
        if "−20%" not in s["t"] or "−$1" not in s["t"] or "down" not in s["c"]: print("PROBLEMS: single loss text/colour", s)
        if c["col"] == pg.evaluate("getComputedStyle(document.body).color"): print("PROBLEMS: loss not coloured")
        if not g["hero"] or "%" not in g["hero"]: print("PROBLEMS: hero shows no percent", g["hero"])
        if g["over"] > 1: print("PROBLEMS: sideways scroll", g["over"])
        # tabular numerals on the numbers
        if "tabular" not in pg.evaluate("getComputedStyle(document.querySelector('.chg')).fontVariantNumeric"): print("PROBLEMS: not tabular")
        # sign flip: width of the box and the row height must not change; text and class do
        h0 = pg.evaluate("document.querySelector('.trow').getBoundingClientRect().height")
        pg.evaluate(SETUP, [3.30, 6.00]); until(pg, "document.querySelector('.trow:not(.srow1) .chg.up')")
        time.sleep(.9)
        g = pg.evaluate(GRAB); h1 = pg.evaluate("document.querySelector('.trow').getBoundingClientRect().height")
        print(w, scheme, "gain:", g)
        c, s = g["combo"][0], g["single"][0]
        if "+10%" not in c["t"] or "+$0.30" not in c["t"] or "up" not in c["c"]: print("PROBLEMS: combo gain", c)
        if "+20%" not in s["t"] or "up" not in s["c"]: print("PROBLEMS: single gain", s)
        if abs(h0 - h1) > 1: print("PROBLEMS: row height jumped on a sign flip", h0, h1)
        if g["over"] > 1: print("PROBLEMS: sideways scroll after flip", g["over"])
        # flat: -0.4% prints no sign and is neutral
        pg.evaluate(SETUP, [2.995, 5.0]); until(pg, "document.querySelector('.trow:not(.srow1) .chg.flat')")
        g = pg.evaluate(GRAB)
        if "flat" not in g["combo"][0]["c"] or g["combo"][0]["t"].startswith(("+", "−")) and "0%" in g["combo"][0]["t"][:3]: print("PROBLEMS: flat", g["combo"][0])
        # rolling: a new value goes through data-num (the text moves over frames, ends on the value)
        pg.evaluate(SETUP, [2.78, 4.0]); time.sleep(.9)
        pg.evaluate("document.querySelector('.trow:not(.srow1) .offer b').dataset.v")
        if not pg.evaluate("!!document.querySelector('.trow:not(.srow1) .chg [data-num][data-f=chg]')"): print("PROBLEMS: percent is not a rolling number")
        # the switch: % only, $ only, remembered
        pg.evaluate("setChg('pct')"); g = pg.evaluate(GRAB)
        if "$" in g["combo"][0]["t"] or "%" not in g["combo"][0]["t"]: print("PROBLEMS: % only", g["combo"][0])
        pg.evaluate("setChg('usd')"); g = pg.evaluate(GRAB)
        if "%" in g["combo"][0]["t"] or "$" not in g["combo"][0]["t"]: print("PROBLEMS: $ only", g["combo"][0])
        if "%" in (g["hero"] or ""): print("PROBLEMS: hero should drop the % in $ mode", g["hero"])
        if pg.evaluate("localStorage.getItem('cw_chg')") != "usd": print("PROBLEMS: choice not remembered")
        if g["over"] > 1: print("PROBLEMS: sideways scroll in $ mode")
        pg.evaluate("setChg('both')")
        # the switch is a real control: press feedback class path exists (TAP matches buttons) and it is on screen
        if not pg.evaluate("!!document.querySelector('.chgsw button')"): print("PROBLEMS: no switch")
        if os.environ.get("SHOTS"):
            pg.evaluate("document.querySelector('.chgbar').scrollIntoView({block:'start'});window.scrollBy(0,-70)"); time.sleep(.5)
            pg.screenshot(path=os.environ["SHOTS"] + f"/pct_live_{scheme}_{w}.png")
            pg.evaluate("window.scrollTo(0,0)"); time.sleep(.3); pg.screenshot(path=os.environ["SHOTS"] + f"/pct_hero_{scheme}_{w}.png", clip={"x": 0, "y": 60, "width": w, "height": 300})
        # combo detail
        pg.evaluate("S.view='live'")
        def fix(route):
            resp = route.fetch(); j = resp.json()
            if j.get("combo"): j["combo"].update(offer=2.78, offer_real=False, cost=3, group="pending")
            route.fulfill(response=resp, body=json.dumps(j))
        pg.route("**/app/api/combo*", fix)
        r = pg.evaluate("""async()=>{await openCombo(S.live.combos[0].t);await new Promise(r=>setTimeout(r,1500));const e=document.querySelector('.dkpis .chg');return e?e.textContent.trim():null}""")
        pg.unroute("**/app/api/combo*")
        print("detail:", r)
        if not r or "−7%" not in r: print("PROBLEMS: combo detail change", r)
        # reduced motion: still draws the final numbers at once
        pg.emulate_media(reduced_motion="reduce")
        pg.evaluate("closeModal&&closeModal()"); pg.evaluate(SETUP, [2.5, 4.0]); time.sleep(.2)
        if "−17%" not in pg.evaluate(GRAB)["combo"][0]["t"]: print("PROBLEMS: reduced motion value")
        print("errs:", errs)
        ctx.close()
    br.close()
