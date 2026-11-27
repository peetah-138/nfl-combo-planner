# CHECK: group=page secs=30
"""#361 on the phone: a combo card's price shows the expected profit on the chance corrected by his own record ("on your
record, before fees") when the Mac sends ev_cal, else the books' one as before; "recommended" is still decided by the
books' ev (display only: no sizing change). The slip's amount row does the same. Prices are put in the page (never a real
order). 390x844, dark and light; set SHOTS to save them. Prints PROBLEMS."""
import requests
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        if pg.evaluate(js): return True
        time.sleep(.2)
    return False

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True, color_scheme="dark")
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.dismiss())
    pg.set_default_timeout(8000)
    pg.route("**/app/api/act", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "msg": "ok"})))
    pg.add_init_script("if(!sessionStorage.getItem('k')){localStorage.clear();sessionStorage.setItem('k','1');}localStorage.setItem('cw_view','build')")
    pg.goto(B + "/app")
    if not wait(pg, "!!(S.build&&S.build.combos&&S.build.combos.length)", 40): bad("Build never loaded combos"); br.close(); print("PROBLEMS:", problems); sys.exit(0)
    pg.evaluate("S.adv=true;S.bsec.combos=true;S.bsec.games=false;renderBuild()"); time.sleep(.6)
    ci = pg.evaluate("S.build.combos.find(c=>!c.bought).i")
    def show(q):
        pg.evaluate(f"S.qpend={{}};S.quotes={{{ci}:Object.assign({{pays:30.5,stake:5,pct:1.02,clears:true,cut:95,rec:5,at:Date.now()/1000}},{json.dumps(q)})}};renderBuild()"); time.sleep(.3)
        return pg.evaluate("(()=>{const e=document.querySelector('#main .ccard .stk');return e?e.innerText:''})()")
    t = show({"ev": 0.6, "ev_cal": -0.35})
    if "Expected profit −$0.35 based on how your past bets did, before fees" not in t: bad(f"the calibrated profit should be shown: {t!r}")
    if "recommended" in t.lower().replace("no edge", "") and "Recommended" in t or "no edge" not in t: bad(f"release 507 review: the profit SHOWN decides the tag, so a red shown profit says 'no edge', never Recommended: {t!r}")
    if "down" not in pg.evaluate("document.querySelector('#main .ccard .stkev').className"): bad("a negative calibrated profit should be red")
    SHOTS_DIR = os.environ.get("SHOTS")
    if SHOTS_DIR:
        pg.evaluate("document.querySelector('#main .ccard').scrollIntoView({block:'center'})"); time.sleep(.3)
        pg.screenshot(path=os.path.join(SHOTS_DIR, "evcal_card_dark.png"))
        pg.emulate_media(color_scheme="light"); time.sleep(.4)
        pg.evaluate("document.querySelector('#main .ccard').scrollIntoView({block:'center'})"); time.sleep(.3)
        pg.screenshot(path=os.path.join(SHOTS_DIR, "evcal_card_light.png"))
        pg.emulate_media(color_scheme="dark"); time.sleep(.3)
    t = show({"ev": 0.6})
    if "Expected profit +$0.60 before fees" not in t or "past bets did" in t: bad(f"no ev_cal: the books' profit as before: {t!r}")
    t = show({"ev": 0.6, "ev_cal": None})
    if "Expected profit +$0.60 before fees" not in t: bad(f"ev_cal null: the books' profit as before: {t!r}")
    t = show({"ev": -0.2, "ev_cal": 0.4})
    if "recommended" not in t.lower() or "no edge" in t: bad(f"release 507 review: a positive SHOWN (calibrated) profit says recommended even when the books' is negative: {t!r}")
    if "Expected profit +$0.40 based on how your past bets did" not in t: bad(f"the calibrated profit is shown even when the books' is negative: {t!r}")
    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad("sideways scroll")
    if errs: bad(f"JS errors: {errs[:3]}")
    br.close()
print("PROBLEMS:", problems) if problems else print("ALL GOOD")
