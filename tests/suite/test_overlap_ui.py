# CHECK: group=page secs=60
"""Overlap guard on the page (issue #359). The web app runs for real; the account read is patched so Pete holds two open
combos on Boston-New York (2 bets: over the line) and one each on Denver and Milwaukee. Checks at phone size (390x844,
dark and light): the Boston game is greyed and last on the board with its pick buttons disabled, the note says how
many bets and the money at risk, Add anyway is a 44pt target that ticks at once and sends the game back with the next
request (and only from this page: a reload brings the grey back); every Surprise card on that game is greyed with no
Get price, and every card keeps its own number whether the game is greyed or not (rule 7); Best bets lists the game as
left out; a quote's warning line shows on the combo card; greyed Buy ideas, long shots and panel extras have no buy
button and an extra on a greyed game isn't counted in Add N; the Mac refuses a panel extra on a greyed game unless the
request carries Pete's Add anyway; Settings › Money has the switch and two sliders. No JS errors, no sideways scroll.
Nothing is priced or bought: quotes are answered by the test. Saves screenshots (SHOTS dir, if set)."""
import sys, os, time, threading, json, re
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
BOS, DEN, MIL = (f"KXNBAGAME-{tk}{g}" for g in ("BOSNYK", "DENLAL", "MILCHI"))
REF = {}
ADDED = []


def bet(a, b, cost):
    return {"status": "pending", "cost": cost, "legs": [{"ticker": a + "-" + a[-6:-3], "event": a},
                                                       {"ticker": b + "-" + b[-6:-3], "event": b}]}


def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    A.ACCT_CACHE.update(at=time.time(), value=([bet(BOS, DEN, 3.0), bet(BOS, MIL, 3.0)], 211.03, "test"))
    A.panel_extras = lambda real=None: {"items": [{"id": "extra:bos", "legs": [{"ticker": BOS + "-BOS", "event": BOS}]},
                                                  {"id": "extra:phx", "legs": [{"ticker": f"KXNBAGAME-{tk}PHXGSW-PHX"}]}]}
    A.panel_add = lambda ids, view, stakes=None: (ADDED.append(list(ids)) or True, f"Added {len(ids)}.")
    REF["A"] = A
    return A


W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
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
        os.makedirs(SHOTS, exist_ok=True)
        pg.screenshot(path=os.path.join(SHOTS, name))

WARN = "You already have 1 open bet on this game ($3 at risk)."
SENT, URLS = [], []
def act(route):
    try:
        body = json.loads(route.request.post_data or "{}")
    except ValueError:
        body = {}
    if body.get("a") == "quote":
        SENT.append(body)
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"ok": True, "pays": 21.4, "stake": 5, "pct": 1.04, "clears": True, "cut": 95, "rec": 5, "min": 1, "max": 20,
             "room": 50, "ev": .42, "overlap": WARN, "warn": [{"k": "overlap", "t": WARN}]}))
    if body.get("a") in ("buy", "singlebuy", "longshot", "idea_buy"):
        SENT.append(body)
        return route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": False, "msg": "Test: nothing is bought here."}))
    return route.continue_()

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        tag = "phone_" + scheme
        ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, has_touch=True, device_scale_factor=2)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("request", lambda r: URLS.append(r.url) if "/app/api/" in r.url else None)
        pg.add_init_script("window.__haps=[];localStorage.clear();localStorage.setItem('cw_view','build');localStorage.setItem('cw_lg','nba');"
                           "localStorage.setItem('cw_pview','nba');localStorage.setItem('cw_adv','1')")
        pg.route("**/app/api/act", act)
        pg.goto(B + "/app")
        if not wait(pg, "S.build&&S.build.board&&S.build.board.length&&document.querySelector('#main .mrow')", 60):
            bad(f"{tag}: the board didn't render"); ctx.close(); continue
        time.sleep(.6)
        # ---- the board: Boston greyed, last, buttons off, the note and a 44pt Add anyway
        rows = pg.evaluate("[...document.querySelectorAll('#main .board .mrow')].map(r=>({k:r.dataset.key,over:r.classList.contains('over'),"
                           "dis:[...r.querySelectorAll('.pickbtn')].every(b=>b.getAttribute('aria-disabled')==='true'&&!b.onclick),"
                           "t:(r.querySelector('.ovbar')||{}).innerText||''}))")
        over = [r for r in rows if r["over"]]
        if [r["k"] for r in over] != ["b:" + BOS]: bad(f"{tag}: only Boston should be greyed: {[r['k'] for r in over]}")
        elif rows[-1]["k"] != "b:" + BOS: bad(f"{tag}: the greyed game should sit last: {[r['k'] for r in rows]}")
        if over and not over[0]["dis"]: bad(f"{tag}: a greyed game's pick buttons must do nothing")
        if over and "You already have 2 open bets on this game ($6 at risk)." not in over[0]["t"]: bad(f"{tag}: the note should say 2 bets, $6: {over[0]['t']!r}")
        if any(r["t"] for r in rows if not r["over"]): bad(f"{tag}: only the greyed game has a note")
        h = pg.evaluate("(()=>{const b=document.querySelector('#main .mrow.over .ovadd');if(!b)return 0;const r=b.getBoundingClientRect();return Math.min(r.width,r.height)})()")
        if h < 44: bad(f"{tag}: Add anyway should be at least 44pt: {h}")
        # ---- Surprise me: each card on Boston is greyed, with no Get price; numbers never move (rule 7)
        cc = pg.evaluate("""(S.build.combos||[]).map(c=>{const e=document.querySelector('#main .ccard[data-i="'+c.i+'"]');
            return {i:c.i,over:!!c.over,bos:c.legs.some(l=>(l.event||'')===%r||l.ticker.startsWith(%r)),grey:!!e&&e.classList.contains('over'),
                    price:!!e&&[...e.querySelectorAll('button')].some(b=>/Get price|Buy/.test(b.innerText))}})""" % (BOS, BOS))
        if not cc: print(tag, "note: no Surprise cards in this run")
        for c in cc:
            if c["bos"] != c["over"] or c["over"] != c["grey"]: bad(f"{tag}: card {c['i']} touching Boston={c['bos']} should be greyed exactly then: {c}")
            if c["grey"] and c["price"]: bad(f"{tag}: greyed card {c['i']} must have no Get price or Buy")
        same = pg.evaluate("""(async()=>{const a=await api('/app/api/build?lg=nba'),b=await api('/app/api/build?lg=nba&allow=%s');
            const m=d=>JSON.stringify((d.combos||[]).map(c=>[c.i,c.legs.map(l=>l.ticker)]));return [m(a)===m(b),(a.combos||[]).length,(a.combos||[]).some(c=>c.over),(b.combos||[]).some(c=>c.over)]})()""" % BOS)
        if not same[0]: bad(f"{tag}: every card must keep its own number and legs whether a game is greyed or not")
        if same[1] and same[2] and same[3]: bad(f"{tag}: with Add anyway on Boston, nothing should be greyed")
        # ---- Best bets lists the game as left out
        left = pg.evaluate("(document.querySelector('#main .ovleft')||{}).innerText||''")
        if "Left out" not in left or "Add anyway" not in left: bad(f"{tag}: Best bets should list Boston as left out: {left!r}")
        if not pg.evaluate("(S.build.best.over||[]).some(o=>o.event===%r)" % BOS): bad(f"{tag}: best.over should carry Boston")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{tag}: Build scrolls sideways")
        pg.evaluate("document.querySelector('#main .mrow.over').scrollIntoView({block:'center'})"); time.sleep(.4)
        shot(pg, f"1_greyed_game_{tag}.png")
        # ---- Add anyway: ticks at once, the next request carries the game, the grey goes
        n0 = len(URLS)
        tick = pg.evaluate("(()=>{const n=window.__haps.length;document.querySelector('#main .mrow.over .ovadd').click();return window.__haps.length>n})()")
        if not tick: bad(f"{tag}: Add anyway should tick before anything is awaited")
        if not wait(pg, "!document.querySelector('#main .board .mrow.over')", 30): bad(f"{tag}: after Add anyway Boston should be back")
        if not any("allow=" + BOS in u for u in URLS[n0:] if "/app/api/build" in u): bad(f"{tag}: the build request should carry allow={BOS}: {URLS[n0:]}")
        if not any("allow=" + BOS in u for u in URLS[n0:] if "/app/api/panel" in u): bad(f"{tag}: the panel request should carry the allow list too")
        pg.evaluate("document.querySelector('#main .mrow[data-key=\"b:%s\"]').scrollIntoView({block:'center'})" % BOS); time.sleep(.4)
        shot(pg, f"2_after_add_anyway_{tag}.png")
        # ---- a quote's warning line on the combo card (and Rule 7: the quote asks for that card's own legs)
        ci = pg.evaluate("((S.build.combos||[]).find(c=>!c.bought&&!c.over)||{}).i")
        if ci:
            legs = pg.evaluate("S.build.combos.find(c=>c.i===%d).legs.map(l=>l.ticker)" % ci)
            n0 = len(SENT)
            pg.locator(f'#main .ccard[data-i="{ci}"] button', has_text="Get price").first.click()
            if not wait(pg, "!!document.querySelector('#main .ccard[data-i=\"%d\"] .ovq')" % ci, 10): bad(f"{tag}: the quote's warning line should show on the card")
            else:
                t = pg.evaluate("document.querySelector('#main .ccard[data-i=\"%d\"] .ovq').innerText" % ci)
                if WARN not in t: bad(f"{tag}: warning line text: {t!r}")
                if not pg.evaluate("[...document.querySelectorAll('#main .ccard[data-i=\"%d\"] button')].some(b=>/^Buy/.test(b.innerText))" % ci):
                    bad(f"{tag}: the warning never takes the Buy button away")
            q = [s for s in SENT[n0:] if s.get("a") == "quote"]
            if not q or q[0].get("i") != ci or q[0].get("legs") != legs: bad(f"{tag}: the quote should be for card {ci}'s own legs: {q}")
            pg.evaluate("document.querySelector('#main .ccard[data-i=\"%d\"]').scrollIntoView({block:'center'})" % ci); time.sleep(.5)
            shot(pg, f"3_quote_warning_{tag}.png")
        else:
            bad(f"{tag}: no Surprise card to price")
        # ---- the slip quote shows the line too (built in the page: no Kalshi call)
        html = pg.evaluate("(()=>{S.slip=S.build.board[0].sides.slice(0,1).map(s=>s.ticker).concat(S.build.board[1].sides[0].ticker);"
                           "S.custom={i:99,offer:{pays:20,stake:5,at:Date.now()/1000,pct:1.02,clears:true,ev:.3,ov:%r}};return slip(S.build)})()" % WARN)
        if "ovq" not in html or "1 open bet" not in html: bad(f"{tag}: the slip's quote should carry the warning line")
        pg.evaluate("S.slip=[];S.custom=null;renderBuild()")
        # ---- greyed Buy ideas, long shots and panel extras: no buy, not counted
        o = {"n": 2, "risk": 6, "why": "n", "game": BOS, "text": "You already have 2 open bets on this game ($6 at risk)."}
        r = pg.evaluate("""(o=>{S.ideaq=S.ideaq||{};const idea=ideaCard({id:'i1',n:2,picks:'Celtics + Nuggets',sport:'NBA',pct:1.06,legs_info:[],over:o});
            const ls=lsCard({id:'ls1',n:3,chance:.12,legs:[{ticker:'%s-BOS',pick:'Boston Celtics'}],over:o});
            S.pOff=S.pOff||new Set();const its=[{id:'x1',kind:'single',legs:[{ticker:'%s-BOS',pick:'Boston Celtics'}],chance:.6,price:.5,ret:.1,stake:4,over:o},
                {id:'x2',kind:'single',legs:[{ticker:'X-PHX',pick:'Phoenix Suns'}],chance:.6,price:.5,ret:.1,stake:4}];
            const ex=extraBlock({items:its});
            return {idea:idea.includes('ovbar')&&!/>Buy|Get price/.test(idea),ls:ls.includes('ovbar')&&!/Get price|>Buy/.test(ls),
                    ex:ex.includes('ovbar')&&/Add 1 to today/.test(ex),exOrder:ex.indexOf('Phoenix')<ex.indexOf('Boston')}})(%s)""" % (BOS, BOS, json.dumps(o)))
        for k, v in r.items():
            if not v: bad(f"{tag}: greyed {k} check failed")
        # ---- the Mac refuses a panel extra on a greyed game unless Pete tapped Add anyway (once is enough)
        if scheme == "dark":
            ADDED.clear()
            a1 = pg.evaluate("api('/app/api/act',{a:'panel_add',ids:['extra:bos'],view:'extra'})")
            if a1.get("ok") or ADDED: bad(f"panel_add: an extra on a greyed game must not go in without Add anyway: {a1} {ADDED}")
            a2 = pg.evaluate("api('/app/api/act',{a:'panel_add',ids:['extra:bos','extra:phx'],view:'extra'})")
            if ADDED[-1:] != [["extra:phx"]] or "Left out 1" not in (a2.get("msg") or ""): bad(f"panel_add: only Phoenix should go in, and say so: {a2} {ADDED}")
            a3 = pg.evaluate("api('/app/api/act',{a:'panel_add',ids:['extra:bos'],view:'extra',allow:[%r]})" % BOS)
            if not a3.get("ok") or ADDED[-1:] != [["extra:bos"]]: bad(f"panel_add: with Add anyway the extra goes in: {a3} {ADDED}")
            pan = pg.evaluate("api('/app/api/panel?v=all')")
            print("panel extra marked:", json.dumps((pan.get("extra") or {}).get("items"))[:200] if pan.get("extra") else "no extras row (no approved panel)")
            liv = pg.evaluate("api('/app/api/live?allow=%s').then(d=>!!d).catch(e=>String(e))" % BOS)
            if liv is not True: bad(f"live with an allow list should still answer: {liv}")
        # ---- a reload forgets Add anyway: Boston is greyed again
        pg.reload()
        if not wait(pg, "!!document.querySelector('#main .board .mrow.over')", 60): bad(f"{tag}: after a reload Boston should be greyed again (Add anyway is never saved)")
        # ---- Settings › Money: the switch (on) and two sliders
        pg.evaluate("go('settings')")
        if not wait(pg, "document.body.innerText.includes('Hold back games I already have bets on')", 30): bad(f"{tag}: Settings › Money should have the switch")
        else:
            st = pg.evaluate("""(()=>{const l=[...document.querySelectorAll('label.srow')].find(e=>e.innerText.includes('Hold back games'));
                return {on:!!l&&l.querySelector('input').checked,n:document.body.innerText.includes('Held back from'),p:document.body.innerText.includes('Or once this much is riding on it')}})()""")
            if not (st["on"] and st["n"] and st["p"]): bad(f"{tag}: the switch should be on with both sliders: {st}")
            pg.evaluate("[...document.querySelectorAll('label.srow')].find(e=>e.innerText.includes('Hold back games')).scrollIntoView({block:'center'})"); time.sleep(.4)
            shot(pg, f"4_settings_{tag}.png")
        if [s for s in SENT if s.get("a") != "quote"]: bad(f"{tag}: nothing should try to buy: {SENT}")
        if errs: bad(f"{tag}: JS errors: {errs}")
        print(tag, "errs:", errs)
        ctx.close()
    br.close()
if problems:
    print("PROBLEMS:", "; ".join(problems))
else:
    print("all good")
