# CHECK: group=page secs=60
"""Queue UI 3 (#290 #195 #518), phone only, scripted answers (nothing is priced or bought):
#195 the Live hero's change pill rolls only when a single's price can move it, and the 'If sold now' estimate rolls only when some
estimated combo was priced live; #290 each Smart Buy league line is a status line plus ONE progress line, with CLV / 'skips helping'
shown only when that holds the league back; #518 the expected-profit words ('based on how your past bets did'). Made-up teams.
SHOTS dir (if set) gets 390x844 screenshots, dark and light. Prints PROBLEMS on any failure."""
exec(open("test_fun1_ui.py").read().split("def until")[0])
import copy
def until(pg, js, secs=8):
    for _ in range(int(secs / .2)):
        try:
            if pg.evaluate(js): return True
        except Exception:
            pass
        time.sleep(.2)
    return False
def shot(pg, name):
    if SHOTS: pg.screenshot(path=os.path.join(SHOTS, name))

def payload(singles, real, live):
    p = copy.deepcopy(P)
    p["combos"] = [combo(1, ["Foxes", "Herons"], 5.0, 40.0, 4.2), combo(2, ["Otters", "Wolves", "Bears"], 4.0, 60.0, 3.6)]
    for c in p["combos"]:
        c["offer_real"] = real
        if not live: c["offer_live"] = None
    p["singles"] = p["singles"] if singles else []
    for s in p["singles"]:
        s["label"] = "Foxes to win"; s["game"] = "Foxes at Herons"
    if not singles:
        p["staked"] = 9.0
    return p
SB = {"on": True, "days": 7, "stake": 5, "markets": 42, "prices": 900, "scored": {"n": 96, "settled": 41, "by": {"panel": {"n": 96, "settled": 41}}},
      "rows": [], "calib": [],
      "gate": [{"league": "a", "name": "Hockey North", "state": "active", "own": 41, "need": 30, "level": 2, "from": None, "skipped": 7, "saved": 12.5,
                "why": "the 7 bets it would skip lost $12.50 on $5 each", "scored": {"n": 96, "settled": 41},
                "optin": {"n": 34, "n_need": 50, "ahead": 8.2, "days_up": 0.6, "days": 5, "clv": 0.012, "beats": True, "met": False, "paper": True}},
               {"league": "b", "name": "Soccer South", "state": "active", "own": 38, "need": 30, "level": 1, "from": None, "skipped": 4, "saved": -2.1,
                "why": None, "scored": {"n": 60, "settled": 30},
                "optin": {"n": 22, "n_need": 50, "ahead": 3.5, "days_up": 0.55, "days": 4, "clv": -0.02, "beats": False, "met": False, "paper": True}},
               {"league": "c", "name": "Hoops West", "state": "learning", "own": 12, "need": 30, "level": 0, "from": None, "skipped": 0, "saved": 0, "why": None,
                "scored": {"n": 12, "settled": 4}, "optin": {"n": 0, "n_need": 50, "ahead": 0, "days_up": 0, "days": 0, "clv": None, "beats": None, "met": False}}]}

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        tag = scheme
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=scheme, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/app/api/live*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(payload(True, True, True))))
        pg.goto(B + "/app"); pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=30000)
        pg.evaluate("go('live')"); pg.wait_for_selector(".trow", timeout=20000); time.sleep(1.2)
        def put(p):
            pg.evaluate("p=>{S.live=p;renderLive();afterPaint()}", p); time.sleep(.3)
        q = lambda js: pg.evaluate(js)
        # ---- #195: the pill
        if not q("!!document.querySelector('.hv .delta [data-num=\"h:dp\"]')"): bad(f"{tag}: with a single open its price can move the pill, so it may roll")
        put(payload(False, True, False))
        if q("!!document.querySelector('.hv .delta [data-num]')"): bad(f"{tag}: no single open = nothing can move the pill, so it must not be a rolling number")
        if not q("document.querySelector('.hv .delta').textContent.includes('vs')"): bad(f"{tag}: the pill should still be drawn")
        # ---- #195: 'If sold now' estimate
        put(payload(False, False, False))
        if q("document.querySelector('[data-num=\"h:worth\"]').dataset.still") != "1": bad(f"{tag}: an estimate no live price moves should be data-still")
        if "≈" not in q("document.querySelector('[data-num=\"h:worth\"]').textContent"): bad(f"{tag}: the estimate keeps its ≈")
        # a still number never rolls: change it and it shows the new value at once, no flash class
        p2 = payload(False, False, False); p2["cash_now"] = 6.9
        for c in p2["combos"]: c["offer"] = c["offer"] - 1
        put(p2); time.sleep(.1)
        if q("document.querySelector('[data-num=\"h:worth\"]').classList.contains('fl-up')||document.querySelector('[data-num=\"h:worth\"]').classList.contains('fl-down')"):
            bad(f"{tag}: a still estimate must not flash")
        put(payload(False, False, True))
        if q("document.querySelector('[data-num=\"h:worth\"]').dataset.still"): bad(f"{tag}: an estimate priced live moves, so it may roll")
        put(payload(False, True, False))
        if q("document.querySelector('[data-num=\"h:worth\"]').dataset.still"): bad(f"{tag}: a real offer is not an estimate")
        put(payload(True, False, False)); time.sleep(.3)
        shot(pg, f"live_hero_still_estimate_{scheme}.png")
        # ---- #290: Smart Buy league lines
        pg.evaluate("go('results')"); time.sleep(.8)
        pg.evaluate("sb=>{S.sbOpen=true;const m=document.getElementById('main');m.innerHTML='<div class=\"card an\"><h3>What\\'s working <span>Smart Buy</span></h3>'+sbCard(sb)+'</div>';}", SB)
        time.sleep(.3)
        t = q("document.querySelector('.sbg').innerText")
        if "Bigger stakes, on paper: 34 of 50 settled · +$8.20 · 60% of days up" not in t: bad(f"{tag}: the progress line should read like the issue's example: {t!r}")
        if "Held back: losing to the closing price and its skips are not helping yet" not in t: bad(f"{tag}: Soccer South is held back by CLV and its skips: {t!r}")
        if t.count("Held back") != 1: bad(f"{tag}: only the league that is held back says so: {t!r}")
        if "CLV" in t or "beats plain" in t.lower(): bad(f"{tag}: no raw CLV figure, no 'beats plain': {t!r}")
        if "Bigger stakes, on paper: 0 of 50 settled" not in t and "Bigger stakes: 0 of 50 settled" not in t: bad(f"{tag}: a league with nothing settled shows just its count: {t!r}")
        for ln in q("[...document.querySelectorAll('.sbl')].map(l=>l.querySelectorAll('div.m,.sbprog,.sbheld').length)"):
            if ln > 4: bad(f"{tag}: a league line has too many lines ({ln})")
        if q("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{tag}: Smart Buy scrolls sideways")
        pg.evaluate("document.querySelector('.sbp').scrollIntoView({block:'start'})"); time.sleep(.3)
        shot(pg, f"smart_buy_leagues_{scheme}.png")
        # ---- #518: the expected-profit words, with a calibrated loss that still shows 'no edge'
        pg.evaluate("go('build')"); time.sleep(.8)
        h = pg.evaluate("()=>stakeCtl({key:'q3',rec:5,cur:5,min:1,max:50,ev:0.6,evShow:-0.35,evNote:'based on how your past bets did, before fees'})")
        pg.evaluate("h=>{document.getElementById('main').innerHTML='<div class=\"card\"><h3>Foxes + Herons <span>Build</span></h3>'+h+'</div>'}", h)
        t = q("document.querySelector('#main .stk').innerText")
        if "based on how your past bets did, before fees" not in t or "on your record" in t: bad(f"{tag}: the new words: {t!r}")
        if "no edge" not in t or "recommended" in t.replace("Recommended", "").lower() and "Recommended" in t: bad(f"{tag}: a red calibrated profit says no edge, never recommended: {t!r}")
        shot(pg, f"expected_profit_words_{scheme}.png")
        if errs: bad(f"{tag}: JS errors {errs[:3]}")
        ctx.close()
    br.close()
print("done")
