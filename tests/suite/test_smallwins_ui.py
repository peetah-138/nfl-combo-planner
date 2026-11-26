# CHECK: group=page secs=60
"""Small polish batch (issues #404 #405 #406 #408 #353 #368 #403 #402 #275), phone size 390x844, dark and light. Display
and taps only; the Mac's answers are faked in the page and nothing is priced or bought.
 #404 the Comebacks header is a button with a real focus ring and keeps focus when it opens; the body slides in once.
 #405 a Skipped card is no longer a role=button around the Details button: the fresh-price tap is its own button; the
      Results rows are role=button rows with a tab stop and answer Enter and Space.
 #408 no id is written inside an inline handler (it rides in data-*); a hostile id still opens that very item.
 #406 a closed bet whose page could not reach the Mac says so and offers Try again (not "no record").
 #403 a reprice that fails keeps its reason on the card; #402 no haptic after an await in pReprice and ovAdd.
 #353 a long shot whose price fails shows the reason on the card; an unknown outcome stays "Check Kalshi".
 #368 Add anyway: moved cards slide (flipSnap/flipPlay), the greyed one fades up. #275 a refusal shakes once."""
import sys, os, time, threading, json, re
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("SHOTS") or ""
from playwright.sync_api import sync_playwright
fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def until(pg, js, secs=12):
    end = time.time() + secs
    while time.time() < end:
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        time.sleep(.15)
    return False


def shot(pg, name, scheme):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pg.screenshot(path=os.path.join(SHOTS, f"{name}_{scheme}.png"))


# ---- source checks (#408, #402): the page's own code, assembled
src = W.SPA if hasattr(W, "SPA") else ""
check("the assembled page has the small-wins script", "function flipPlay" in src and "function pRepFail" in src)
check("#408 no ticker or event id is interpolated into an inline handler",
      not re.search(r"on(?:click|keydown)=\"[^\"]*(?:openCombo|openGame|pick)\('\$\{", src))
m = re.search(r"async function pReprice\(.*?\n? renderBuild\(\);", src, re.S)
body = m.group(0) if m else ""
check("#402 pReprice fires no haptic after its await", bool(body) and "hap(" not in body.split("await", 1)[-1])
m = re.search(r"async function ovAdd\(.*?flipPlay\(snap\);\}", src, re.S)
body = m.group(0) if m else ""
check("#402 ovAdd fires no haptic after its await", bool(body) and "hap(" not in body.split("await", 1)[-1])

DATA = {"leagues": [{"league": "nba", "name": "NBA", "n": 34, "pred_old": 0.41, "pred_new": 0.27, "actual": 0.24,
                     "old_pass": 12, "new_pass": 7, "held": 5, "held_rec": 1, "held_pnl": -12.4, "few": False}],
        "other": None, "table": 412}
P = json.load(open("panel_fixture.json"))
P["panel"]["status"] = "approved"
for i, c in enumerate(P["panel"]["items"][:2]):
    c["state"], c["note"] = ["skipped", "failed"][i], ["no longer priced well enough, and nothing similar qualified", "Kalshi wouldn't price it (timeout)"][i]
TC = "KXMVENFLMULTIGAMEEXTENDED-S2026CLOSED1"
RES = {"balance": 211.0, "settled": 1, "won": 0, "cashed": 1, "staked": 2.19, "returned": 3.61, "pl": 1.42, "roi": .6, "best": 1.42, "weeks": [],
       "history": [{"t": TC, "status": "cashed", "cost": 2.19, "back": 3.61, "pl": 1.42, "pays": 40.0, "week": "2026-W47", "day": "2026-11-22",
                    "bought": "2026-11-21", "cashed": "2026-11-22", "picks": ["Lakers", "not Celtics"], "sports": ["nba"]}]}
CLOSED = {"found": True, "t": TC, "kind": "combo", "label": "Combo 5", "status": "cashed", "cost": 2.19, "back": 3.61, "pl": 1.42,
          "pl_pct": 64.84, "stamp": "SOLD EARLY", "sports": ["nba"], "chance": 0.72, "pays": 40.0, "closed": "Sun Nov 22, 3:12 PM",
          "why": "Cashed out automatically: took the profit", "picks": [{"name": "Lakers", "res": "yes", "t": "a"}], "attempts": [],
          "chart": {"offers": [], "ticks": {}}}
SHEET = "document.querySelector('#sheet').innerText"

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=scheme)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.bring_to_front()
        pg.route("**/app/api/results*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(RES)))
        mode = {"closed": "net"}

        def closed_route(r):
            if mode["closed"] == "net":
                return r.abort()
            r.fulfill(status=200, content_type="application/json", body=json.dumps(CLOSED))
        pg.route("**/app/api/closed*", closed_route)
        pg.route("**/app/api/analytics*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"at": time.time(), "comeback": DATA})))
        pg.goto(B + "/app"); time.sleep(4)
        pg.evaluate("go('results')"); time.sleep(4)

        # ---- #404 Comebacks header
        INJ = "d=>{S.an=Object.assign({at:Date.now()/1000},S.an||{},{comeback:d});S.cbOpen=false;renderResults();}"
        # Results may still be a skeleton on a slow runner (renderResults draws no card until S.res lands): re-inject until the card is there
        until(pg, "((%s)(%s),!!document.querySelector('.cbp .cbh'))" % (INJ, json.dumps(DATA)), 15)
        check(f"{scheme} #404: the header is a real button with no inline reset", pg.evaluate("(()=>{const b=document.querySelector('.cbp .cbh');return !!b&&b.tagName==='BUTTON'&&!b.getAttribute('style')})()"))
        pg.keyboard.press("Shift+Tab")          # keyboard modality: :focus-visible only applies after a key
        until(pg, "(document.querySelector('.cbh').focus(),document.activeElement.classList.contains('cbh'))", 5)
        ring = pg.evaluate("(()=>{const b=document.querySelector('.cbh'),s=getComputedStyle(b);return {fv:b.matches(':focus-visible'),st:s.outlineStyle,w:parseFloat(s.outlineWidth)}})()")
        check(f"{scheme} #404: keyboard focus draws a ring ({ring})", ring["fv"] and ring["st"] != "none" and ring["w"] >= 2)
        pg.keyboard.press("Enter")
        check(f"{scheme} #404: Enter opens it and focus stays on the header",
              until(pg, "!!document.querySelector('.cbp .antbl')", 5) and pg.evaluate("document.activeElement&&document.activeElement.classList.contains('cbh')"))
        check(f"{scheme} #404: the body animates in once (one-shot, not on every refresh)",
              pg.evaluate("(()=>{const b=document.querySelector('.cbbody');return !!b&&b.classList.contains('cbin')})()")
              and not pg.evaluate("(S.cbJust=false,renderResults(),document.querySelector('.cbbody').classList.contains('cbin'))"))
        pg.evaluate("document.querySelector('.cbh').focus()")
        pg.evaluate("document.querySelector('.cbp').scrollIntoView({block:'center'})"); time.sleep(.5)
        shot(pg, "comebacks_open_focus", scheme)
        # (#438) closing slides shut (the body shrinks over ~220 ms) instead of snapping, then is gone; focus stays on the header
        pg.evaluate("document.querySelector('.cbh').click()")
        time.sleep(.09)
        mid = pg.evaluate("(()=>{const b=document.querySelector('.cbbody');return b?b.getBoundingClientRect().height:-1})()")
        check(f"{scheme} #438: mid-close the body is still there but smaller ({mid})", mid > 0 and pg.evaluate("document.querySelector('.cbh').getAttribute('aria-expanded')")=="false")
        check(f"{scheme} #438: after the slide the body is gone and focus is on the header",
              until(pg, "!document.querySelector('.cbbody')&&document.activeElement.classList.contains('cbh')", 5))
        pg.evaluate("document.querySelector('.cbh').click()"); until(pg, "!!document.querySelector('.cbbody')", 5)
        check(f"{scheme} #404: still 44px tall, no sideways scroll", pg.evaluate("document.querySelector('.cbh').getBoundingClientRect().height>=44&&document.documentElement.scrollWidth<=innerWidth+1"))

        # ---- #405 Results rows
        pg.evaluate("S.res=%s;renderResults()" % json.dumps(RES))
        row = pg.evaluate("(()=>{const r=document.querySelector('.hrow2');return r?{role:r.getAttribute('role'),tab:r.tabIndex,nested:!!r.querySelector('button,a,[role=button]')}:null})()")
        check(f"{scheme} #405: a Results row is a role=button with a tab stop and nothing nested in it ({row})", bool(row) and row["role"] == "button" and row["tab"] == 0 and not row["nested"])
        pg.evaluate("document.querySelector('.hrow2').scrollIntoView({block:'center'});document.querySelector('.hrow2').focus()")
        time.sleep(.3)
        shot(pg, "results_row_focus", scheme)
        mode["closed"] = "ok"
        pg.keyboard.press("Enter")
        check(f"{scheme} #405: Enter on a Results row opens the closed bet", until(pg, f"document.querySelector('#modal.on')&&{SHEET}.includes('Combo 5')", 10))
        pg.evaluate("closeModal()"); time.sleep(.5)
        pg.evaluate("document.querySelector('.hrow2').focus()"); pg.keyboard.press("Space")
        check(f"{scheme} #405: Space on a Results row opens it too", until(pg, f"document.querySelector('#modal.on')&&{SHEET}.includes('Combo 5')", 10))
        pg.evaluate("closeModal()"); time.sleep(.5)

        # ---- #406 closed bet: no answer is not "no record"
        mode["closed"] = "net"
        pg.evaluate("openClosed('KXMVE-NETDOWN-1')")
        check(f"{scheme} #406: a network error says it could not load, with Try again (not 'no record')",
              until(pg, f"document.querySelector('#modal.on')&&{SHEET}.includes(\"Couldn't load that bet\")&&{SHEET}.includes('Try again')", 10)
              and "no record" not in pg.evaluate(SHEET))
        time.sleep(.6)
        shot(pg, "closed_retry_sheet", scheme)
        mode["closed"] = "ok"
        pg.evaluate("S.comboOpen='%s'" % TC)
        pg.evaluate("closedFill('%s','Bet')" % TC)
        check(f"{scheme} #406: Try again (the same call) then shows the bet", until(pg, f"{SHEET}.includes('$3.61')", 10))
        pg.evaluate("closeModal()"); time.sleep(.4)

        # ---- #405/#403/#402 Skipped card: a real fresh-price button, the reason stays on the card when it fails
        pg.evaluate("go('build')"); time.sleep(5)
        calls = []; answer = {"v": "fail"}

        def fake(route):
            b = json.loads(route.request.post_data or "{}")
            if b.get("a") != "panel_reprice":
                return route.continue_()
            calls.append(b)
            if answer["v"] == "net":
                return route.abort()
            if answer["v"] == "fail":
                return route.fulfill(content_type="application/json", body=json.dumps({"ok": False, "msg": "Just priced. Give it a few seconds."}))
            route.fulfill(content_type="application/json", body=json.dumps({"ok": True, "id": b.get("id"), "would": False, "verdict": "Still wouldn't buy",
                          "at": time.time(), "why": "Kalshi pays $9.80 for $5.00: 91% of its fair payout. The panel's bar is 95%."}))
        pg.route("**/app/api/act", fake)
        pg.evaluate("S.panel=" + json.dumps(P) + ";S.prep={};S.prepP={};renderBuild()"); time.sleep(.5)
        pg.evaluate("document.querySelector('.pitem.prp').scrollIntoView({block:'center'})"); time.sleep(.3)
        card = pg.evaluate("(()=>{const c=document.querySelector('.pitem.prp');return {role:c.getAttribute('role'),tab:c.getAttribute('tabindex'),nested:c.querySelectorAll('[role=button]').length,btn:[...c.querySelectorAll('button.prbtn')].map(b=>b.innerText.trim()),det:!!c.querySelector('.pdet'),h:[...c.querySelectorAll('.prbtn,.pdet')].map(b=>Math.round(b.getBoundingClientRect().height))}})()")
        check(f"{scheme} #405: the card is not a button; it holds a real fresh-price button next to Details ({card})",
              card["role"] is None and card["tab"] is None and card["nested"] == 0 and card["btn"] == ["Tap for a fresh price"] and card["det"] and min(card["h"]) >= 44)
        shot(pg, "reprice_card", scheme)
        before = pg.evaluate("document.querySelector('.pitem.prp').getBoundingClientRect().height")
        pg.evaluate("document.querySelector('.pitem.prp .prbtn').click()")
        check(f"{scheme} #403: a failed reprice keeps 'Just priced' and its reason on the card", until(pg, "(document.querySelector('.pitem.prp .prq.fail')||{}).innerText&&document.querySelector('.pitem.prp .prq.fail').innerText.includes('Give it a few seconds')", 8))
        check(f"{scheme} #435: focus lands back on the card's button and the result is spoken in a live region",
              pg.evaluate("document.activeElement&&document.activeElement.classList.contains('prbtn')&&!!document.activeElement.closest('.pitem.prp')")
              and pg.evaluate("(document.getElementById('repLive')||{}).getAttribute&&document.getElementById('repLive').getAttribute('aria-live')")=="polite"
              and "Just priced" in pg.evaluate("document.getElementById('repLive').textContent"))
        txt = pg.evaluate("document.querySelector('.pitem.prp .prq.fail').innerText")
        check(f"{scheme} #403: it says nothing was bought and offers Try again ({txt!r})", "Just priced" in txt and "Nothing was bought" in txt and pg.evaluate("[...document.querySelectorAll('.pitem.prp .prbtn')].some(b=>b.innerText.trim()==='Try again')"))
        check(f"{scheme} #403: stored as would:false with the message", pg.evaluate("(()=>{const r=Object.values(S.prep)[0];return r&&r.would===false&&r.fail===true&&/few seconds/.test(r.why)})()"))
        time.sleep(.5)
        shot(pg, "reprice_failed_inline", scheme)
        answer["v"] = "net"
        pg.evaluate("document.querySelector('.pitem.prp .prbtn').click()")
        check(f"{scheme} #403: a network failure is also written on the card", until(pg, "/Couldn.t get a fresh price/.test((document.querySelector('.pitem.prp .prq.fail')||{}).innerText||'')&&/reach your Mac/.test(document.querySelector('.pitem.prp .prq.fail').innerText)", 8))
        answer["v"] = "ok"
        pg.evaluate("document.querySelector('.pitem.prp .prbtn').click()")
        check(f"{scheme} #403: a good answer replaces the failure", until(pg, "/Still wouldn.t buy/.test((document.querySelector('.pitem.prp .prq')||{}).innerText||'')&&!document.querySelector('.pitem.prp .prq.fail')", 8))
        check(f"{scheme} #403: asked only panel_reprice, once per tap ({len(calls)})", len(calls) == 3 and all(c.get("a") == "panel_reprice" for c in calls))
        # Details still opens the closed-bet detail, never a reprice
        n = len(calls)
        pg.evaluate("document.querySelector('.pitem.prp .pdet').click()"); time.sleep(.8)
        check(f"{scheme} #405: Details opens the detail and does not reprice", pg.evaluate("!!document.querySelector('#modal.on')") and len(calls) == n)
        pg.evaluate("closeModal()"); time.sleep(.4)
        check(f"{scheme} #405: no role=button anywhere on the Build page wraps another button",
              pg.evaluate("[...document.querySelectorAll('[role=button]')].filter(e=>e.querySelector('button,a[href]')).length") == 0)

        # ---- #353 long shots
        rec = {"id": "ls-test", "n": 2, "chance": .31, "exp": 1.2, "stake": 5, "pays": 16, "pct": 1.02, "legs": []}
        pg.evaluate("S.lsChecked={};S.lsErr={};S.lsBusy=null;S.buying=false;S.build=S.build||{};S.build.longshots={recs:[%s]}" % json.dumps(rec))
        pg.unroute("**/app/api/act")

        def ls_fail(route):
            b = json.loads(route.request.post_data or "{}")
            if b.get("a") != "longshot":
                return route.continue_()
            route.fulfill(content_type="application/json", body=json.dumps({"ok": False, "error": "Kalshi didn't answer with a price. Try again in a minute."}))
        pg.route("**/app/api/act", ls_fail)
        pg.evaluate("document.querySelector('#main').insertAdjacentHTML('afterbegin','<div id=\"lsbox\" class=\"cgrid\" style=\"padding:12px\"></div>');window.__lsdraw=()=>{document.getElementById('lsbox').innerHTML=lsCard(lsFind('ls-test'))}; renderBuild=window.__lsdraw; __lsdraw()")
        pg.evaluate("lsQuote('ls-test')")
        check(f"{scheme} #353: a failed long-shot price shows its reason on the card", until(pg, "!!document.querySelector('#lsbox .lsfail')&&document.querySelector('#lsbox .lsfail').innerText.includes('Try again in a minute')", 8))
        check(f"{scheme} #353: it says nothing was bought and shakes once", pg.evaluate("document.querySelector('#lsbox .lsfail').innerText.includes('Nothing was bought')&&document.querySelector('#lsbox .lsfail').classList.contains('pin')")
              and not pg.evaluate("(__lsdraw(),document.querySelector('#lsbox .lsfail').classList.contains('pin'))"))
        pg.evaluate("document.querySelector('#lsbox').scrollIntoView({block:'center'})"); time.sleep(.5)
        shot(pg, "longshot_price_failed", scheme)
        pg.evaluate("S.lsChecked['ls-test']=true;S.build.longshots.recs=[Object.assign({},%s)];__lsdraw()" % json.dumps(rec))
        check(f"{scheme} #353: an unknown outcome stays 'Check Kalshi' after the list is fetched again", "check kalshi" in pg.evaluate("document.getElementById('lsbox').innerText").lower() and "get price" not in pg.evaluate("document.getElementById('lsbox').innerText").lower())
        pg.evaluate("document.getElementById('lsbox').remove()")

        # ---- #368 Add anyway: moved cards slide, the greyed one fades up
        pg.evaluate("""(()=>{const m=document.querySelector('#main');m.insertAdjacentHTML('afterbegin',
          '<div id="flipbox"><div class="ccard over" id="fa"><div class="ovdim"><div class="lrows">Alpha to win</div></div></div><div class="ccard" id="fb" style="height:90px"><div class="lrows">Beta to win</div></div></div>');
          window.__snap=flipSnap();const box=document.getElementById('flipbox');
          box.innerHTML='<div class="ccard" id="fb" style="height:90px"><div class="lrows">Beta to win</div></div><div class="ccard" id="fa"><div class="lrows">Alpha to win</div></div>';flipPlay(window.__snap)})()""")
        anim = pg.evaluate("({a:document.getElementById('fa').getAnimations().length,b:document.getElementById('fb').getAnimations().length})")
        check(f"{scheme} #368: the card that was greyed and moved, and the one it passed, animate ({anim})", anim["a"] >= 1 and anim["b"] >= 1)
        pg.evaluate("document.getElementById('flipbox').remove()")
        # a scroll while the page waits must not make cards slide: nothing moved on the page, so no animation
        pg.evaluate("""(()=>{const m=document.querySelector('#main');m.insertAdjacentHTML('afterbegin','<div id="flipbox" style="height:3000px"><div class="ccard" id="fa" style="height:90px"><div class="lrows">Gamma to win</div></div></div>');
          window.scrollTo(0,0);window.__snap=flipSnap();window.scrollTo(0,200);flipPlay(window.__snap)})()""")
        check(f"{scheme} #368: a scroll during the wait does not slide the cards",
              pg.evaluate("document.getElementById('fa').getAnimations().length")==0)
        pg.evaluate("document.getElementById('flipbox').remove();window.scrollTo(0,0)")
        red = pg.evaluate("(()=>{const m=document.querySelector('#main');m.insertAdjacentHTML('afterbegin','<div id=\"flipbox\"><div class=\"ccard\" id=\"fa\"><div class=\"lrows\">Alpha</div></div></div>');return 1})()")
        check(f"{scheme} #368: Add anyway keeps its width while it shows 'Showing…'",
              pg.evaluate("""(()=>{const d=document.createElement('div');d.innerHTML='<button class="btn ovadd">Add anyway</button><button class="btn ovadd"><span class="spin"></span> Showing…</button>';document.body.appendChild(d);
                const w=[...d.children].map(b=>Math.round(b.getBoundingClientRect().width));d.remove();return Math.abs(w[0]-w[1])<=2})()"""))
        pg.evaluate("document.getElementById('flipbox')&&document.getElementById('flipbox').remove()")

        # ---- #275 a refusal shakes once
        pg.evaluate("S.ideaAns={}")
        a = pg.evaluate("(()=>{ideaAns('z','Kalshi didn\\'t take it, so nothing was bought.','bad');const x={id:'z'};return [ideaAnsHtml(x),ideaAnsHtml(x)]})()")
        check(f"{scheme} #275: a refusal carries the shake class once, then not again", "shk" in a[0] and "shk" not in a[1])
        check(f"{scheme} #275: the shake respects reduced motion",
              "prefers-reduced-motion" in open("wtest/spa/smallwins.css").read() and ".ians.bad.shk" in open("wtest/spa/smallwins.css").read().split("prefers-reduced-motion")[-1])
        check(f"{scheme}: no sideways scroll, no JS errors ({errs[:2]})", not errs and not pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"))
        pg.close()
    br.close()

if fails:
    print("PROBLEMS:", "; ".join(fails))
else:
    print("PASS small polish batch")
