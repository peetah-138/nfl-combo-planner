"""Flipping a leg on a Build combo idea (GitHub #104, display only). Tapping a leg row: (1) at once the card is in the
'flip' phase (a loading state: the tapped row folds, the dependent numbers shimmer, Get price is disabled and marked stale)
and any Kalshi quote fetched before is gone, so Buy can't be tapped on an old price; (2) when the answer is held, the card
stays in that state across refreshes and a second tap does nothing; (3) when it arrives the new leg shows, the numbers roll to
the new values, the 'Good flip' note slides in, Get price is back (never a Buy); (4) tapping again undoes it; (5) a failed
flip puts the card back with no quote; (6) no JS errors and no sideways scroll at 390 and desktop; (7) reduced motion gives
a crossfade (no transform animation). The flip answer is held by a fake fetch (never a real order). Prints PROBLEMS."""
import requests
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])

SHOTS = os.environ.get("SHOTS_104", "")
problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        if pg.evaluate(js): return True
        time.sleep(.2)
    return False

# flip/quote/buy answers are held here until the test releases them; everything else answers ok
HOLD = r"""(()=>{const real=window.fetch.bind(window);window.__held={};window.__q={};window.__acts=[];
 window.fetch=(u,o)=>{if(String(u).includes('/app/api/act')&&o&&o.body){let b={};try{b=JSON.parse(o.body)}catch(e){}window.__acts.push(b.a);
   if(b.a==='flip'||b.a==='quote'||b.a==='buy')return new Promise(res=>{const f=out=>res(new Response(JSON.stringify(out),{status:200,headers:{'Content-Type':'application/json'}}));window.__held[b.a]=f;(window.__q[b.a]=window.__q[b.a]||[]).push(f);});
   return Promise.resolve(new Response(JSON.stringify({ok:true,msg:'ok'}),{status:200,headers:{'Content-Type':'application/json'}}));}
  return real(u,o);};})()"""
# the combo as it would come back with leg k flipped to the other team (other ticker, other chance)
MAKE = r"""((i,k)=>{const c=S.build.combos.find(x=>x.i===i);const l=c.legs[k];const n=JSON.parse(JSON.stringify(c));
 n.legs[k]=Object.assign({},l,{ticker:l.ticker.replace(/-[^-]*$/,'-FLIP'),pick:'Flipped team',fair:.4});n.chance=(c.chance||.2)*0.5;n.fair=(c.fair||10)*1.9;return n;})"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for tag, vp, reduce in (("390", {"width": 390, "height": 844}, "no-preference"), ("desktop", {"width": 1280, "height": 900}, "no-preference"),
                            ("390-reduced", {"width": 390, "height": 844}, "reduce")):
        ctx = br.new_context(viewport=vp, has_touch=vp["width"] < 500, reduced_motion=reduce, device_scale_factor=2 if vp["width"] < 500 else 1)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.dismiss())
        pg.set_default_timeout(8000)
        pg.add_init_script("if(!sessionStorage.getItem('k')){localStorage.clear();sessionStorage.setItem('k','1');}localStorage.setItem('cw_view','build')")
        pg.add_init_script(HOLD)
        pg.goto(B + "/app")
        if not wait(pg, "!!(S.build&&S.build.combos&&S.build.combos.length)", 40): bad(f"{tag}: Build never loaded combos"); ctx.close(); continue
        pg.evaluate("S.adv=true;S.bsec.combos=true;S.bsec.games=false;renderBuild()"); wait(pg, "document.querySelectorAll('#main .ccard').length>0", 5)
        ci = pg.evaluate("S.build.combos.find(c=>!c.bought&&c.legs.length>1).i"); K = 0
        card = f"#main .ccard[data-i=\"{ci}\"]"
        sel_row = f"{card} .lrow.flip >> nth={K}"
        def shot(n):
            if SHOTS and tag == "390": os.makedirs(SHOTS, exist_ok=True); pg.locator(card).screenshot(path=f"{SHOTS}/{n}.png")
        fit = lambda: pg.evaluate("document.documentElement.scrollWidth>innerWidth+1")
        # a quote is on the card first (a Buy button)
        pg.evaluate(f"S.quotes={{{ci}:{{pays:30.5,stake:5,pct:1.02,clears:true,cut:95,at:Date.now()/1000}}}};renderBuild()"); wait(pg, f"!!document.getElementById('b{ci}')", 5)
        if not pg.evaluate(f"!!document.getElementById('b{ci}')"): bad(f"{tag}: setup: no Buy button before the flip")
        pg.evaluate(f"window.__orig0=JSON.stringify(S.build.combos.find(c=>c.i=={ci}))")
        before = pg.evaluate(f"({{sig:ccSig(S.build.combos.find(c=>c.i=={ci})),pick:S.build.combos.find(c=>c.i=={ci}).legs[{K}].pick,fair:S.build.combos.find(c=>c.i=={ci}).fair}})")
        # ---- 1. tap the leg: loading state at once, quote gone, Buy not tappable
        if reduce == "no-preference" and tag == "390":
            shot("1_before")
        pg.locator(sel_row).click()
        if not wait(pg, f"document.querySelector('{card}').dataset.ph==='flip'", 3): bad(f"{tag}: the card never went into the flip (loading) phase")
        st = pg.evaluate(f"""({{ph:document.querySelector('{card}').dataset.ph,quote:!!(S.quotes&&S.quotes[{ci}]),buy:!!document.getElementById('b{ci}'),
          q:(()=>{{const b=document.getElementById('q{ci}');return b?{{dis:b.disabled,stale:b.dataset.stale,txt:b.textContent.trim()}}:null}})(),
          wait:!!document.querySelector('{card} .lrow.wait'),dep:document.querySelectorAll('{card} .dep').length,sec:document.querySelector('{card} .sec').disabled,
          shim:getComputedStyle(document.querySelector('{card} .hd .dep')).animationName,qline:!!document.querySelector('{card} .qline')}})""")
        print(tag, "loading:", st)
        if st["quote"] or st["buy"] or st["qline"]: bad(f"{tag}: the old quote/Buy survived the tap: {st}")
        if not (st["q"] and st["q"]["dis"] and st["q"]["stale"] == "1"): bad(f"{tag}: Get price isn't disabled/marked stale while loading: {st}")
        if not st["wait"] or st["dep"] < 3 or not st["sec"]: bad(f"{tag}: no loading look on the row/numbers or 'Not this one' still on: {st}")
        if reduce == "no-preference" and st["shim"] == "none": bad(f"{tag}: the numbers don't shimmer while loading")
        if reduce == "reduce" and pg.evaluate(f"getComputedStyle(document.querySelector('{card} .lrow.wait')).animationName")!="none": bad(f"{tag}: reduced motion still animates the folding row")
        shot("2_loading")
        # held answer: refreshes keep the same card node & state, a second tap sends nothing, a quote can't be asked
        pg.evaluate(f"window.__n0=document.querySelector('{card}')")
        for k in range(3): pg.evaluate("renderBuild()" if k % 2 == 0 else "load('build')"); time.sleep(.5)
        same = pg.evaluate(f"document.querySelector('{card}')===window.__n0&&document.querySelector('{card}').dataset.ph==='flip'")
        if not same: bad(f"{tag}: a refresh replaced the card or dropped the loading state while the answer was pending")
        pg.evaluate(f"void flipLeg({ci},S.build.combos.find(c=>c.i=={ci}).legs[1].ticker);void quote({ci})"); time.sleep(.2)
        n_flip = pg.evaluate("window.__acts.filter(a=>a==='flip').length")
        if n_flip != 1 or pg.evaluate("window.__acts.includes('quote')"): bad(f"{tag}: a second tap sent another flip or asked for a price while loading ({n_flip})")
        if fit(): bad(f"{tag}: sideways scroll while loading")
        # ---- 2. the answer arrives: new leg, rolling numbers, the note slides in, Get price is back
        pg.evaluate(f"window.__held.flip({{ok:true,verdict:'good',text:'Flipped A to B: more likely to hit. Tap it again to undo.',combo:({MAKE})({ci},{K})}})")
        if not wait(pg, f"document.querySelector('{card}').dataset.ph==='idle'", 5): bad(f"{tag}: the card never left the loading phase after the answer")
        time.sleep(.05)
        now = pg.evaluate(f"""({{pick:document.querySelectorAll('{card} .lrow.flip')[{K}].querySelector('b').textContent,turn:!!document.querySelector('{card} .lrow.turn'),
          note:!!document.querySelector('{card} .flipnote.in'),noteTxt:(document.querySelector('{card} .flipnote')||{{}}).textContent,live:document.getElementById('flipsay').getAttribute('aria-live'),say:document.getElementById('flipsay').textContent,inCard:!!document.querySelector('{card} [aria-live]'),
          q:(()=>{{const b=document.getElementById('q{ci}');return b?{{dis:b.disabled,txt:b.textContent.trim()}}:null}})(),buy:!!document.getElementById('b{ci}'),quote:!!(S.quotes&&S.quotes[{ci}]),
          anim:getComputedStyle(document.querySelector('{card} .lrow.turn')||document.body).animationName}})""")
        print(tag, "arrived:", now)
        if now["pick"] != "Flipped team": bad(f"{tag}: the flipped leg didn't show: {now}")
        if not now["turn"] or not now["note"] or "Tap it again to undo" not in (now["noteTxt"] or ""): bad(f"{tag}: no turn-in or note slide-in: {now}")
        if now["live"] != "polite" or "Good flip" not in now["say"] or now["inCard"] or pg.evaluate("document.querySelectorAll('#flipsay').length") != 1: bad(f"{tag}: the page's one polite announcer didn't carry the verdict (or a live region sits in the card): {now}")
        if not (now["q"] and not now["q"]["dis"] and now["q"]["txt"] == "Get price") or now["buy"] or now["quote"]: bad(f"{tag}: Buy didn't revert to Get price: {now}")
        if reduce == "reduce" and now["anim"] not in ("lfade",): bad(f"{tag}: reduced motion should crossfade, got {now['anim']}")
        if reduce == "no-preference" and now["anim"] != "lturn": bad(f"{tag}: the new row doesn't turn in: {now['anim']}")
        # the numbers roll (no-preference only): sample the fair payout mid-roll
        if reduce == "no-preference":
            roll = pg.evaluate("new Promise(res=>{const seen=[];const el=document.querySelector('CARD [data-num=\\'cf:CI\\']');const t0=performance.now();(function f(){seen.push(el.textContent);if(performance.now()-t0<900)requestAnimationFrame(f);else res(seen);})();})".replace("CARD", card).replace("CI", str(ci)))
            uniq = list(dict.fromkeys(roll)); print(tag, "payout texts over frames:", uniq[:8])
            if len(uniq) < 3: bad(f"{tag}: the fair payout didn't roll through values: {uniq}")
            mid = pg.evaluate(f"document.querySelector('{card} [data-num=\"cf:{ci}\"]').textContent")
            fin = pg.evaluate(f"money(S.build.combos.find(c=>c.i=={ci}).fair)")
            print(tag, "fair payout mid-roll:", mid, "final:", fin, "was:", before["fair"])
            if not wait(pg, f"document.querySelector('{card} [data-num=\"cf:{ci}\"]').textContent===money(S.build.combos.find(c=>c.i=={ci}).fair)", 4): bad(f"{tag}: the fair payout never rolled to its new value")
            time.sleep(.4); shot("3_after")
        # a dead old-price tap can't happen: no Buy exists; also an old fetched quote that lands late is dropped (sig changed)
        if pg.evaluate(f"ccSig(S.build.combos.find(c=>c.i=={ci}))") == before["sig"]: bad(f"{tag}: the legs didn't change")
        if fit(): bad(f"{tag}: sideways scroll after the flip")
        # ---- 3. a quote after the flip, then undo: the quote goes, same animation
        pg.evaluate(f"S.quotes={{{ci}:{{pays:30.5,stake:5,pct:1.02,clears:true,cut:95,at:Date.now()/1000}}}};renderBuild()"); wait(pg, f"!!document.getElementById('b{ci}')", 5)
        pg.evaluate("window.__acts.length=0"); pg.locator(sel_row).click()
        if not wait(pg, f"document.querySelector('{card}').dataset.ph==='flip'", 3) or pg.evaluate(f"!!document.getElementById('b{ci}')||!!S.quotes[{ci}]"): bad(f"{tag}: undo tap: no loading state / quote survived")
        pg.evaluate("window.__held.flip({ok:true,verdict:'mid',text:'Flipped back. Tap it again to undo.',combo:(()=>{const c=JSON.parse(window.__orig0);c.legs[%d].pick='Original';return c;})()})" % K)
        wait(pg, f"document.querySelector('{card}').dataset.ph==='idle'", 5)
        back = pg.evaluate(f"({{sig:ccSig(S.build.combos.find(c=>c.i=={ci})),pick:document.querySelectorAll('{card} .lrow.flip')[{K}].querySelector('b').textContent,turn:!!document.querySelector('{card} .lrow.turn'),buy:!!document.getElementById('b{ci}')}})")
        print(tag, "undone:", back)
        if back["sig"] != before["sig"] or not back["turn"] or back["buy"]: bad(f"{tag}: undo didn't restore the legs with the same turn, or left a Buy: {back}")
        # ---- 4. a failed flip: card back, no quote, a toast, not stuck
        pg.evaluate(f"S.quotes={{{ci}:{{pays:30.5,stake:5,pct:1.02,clears:true,cut:95,at:Date.now()/1000}}}};renderBuild()"); wait(pg, f"!!document.getElementById('b{ci}')", 5)
        pg.evaluate("window.__shk=false;new MutationObserver(()=>{if(document.querySelector('.lrow.shake'))window.__shk=true}).observe(document.body,{subtree:true,childList:true,attributes:true})")
        pg.locator(sel_row).click(); wait(pg, f"document.querySelector('{card}').dataset.ph==='flip'", 3)
        pg.evaluate("window.__held.flip({ok:false,msg:'Test: could not flip.'})")
        ok = wait(pg, f"document.querySelector('{card}').dataset.ph==='idle'&&!!document.getElementById('q{ci}')&&!document.getElementById('q{ci}').disabled", 5)
        print(tag, "failed flip:", ok, pg.evaluate(f"({{ph:document.querySelector('{card}').dataset.ph,q:!!document.getElementById('q{ci}'),dis:(document.getElementById('q{ci}')||{{}}).disabled,b:!!document.getElementById('b{ci}'),fp:JSON.stringify(S.fpend),acts:window.__acts}})"))
        if not ok or pg.evaluate(f"!!document.getElementById('b{ci}')||!!(S.quotes&&S.quotes[{ci}])||!!(S.fpend&&S.fpend[{ci}])"): bad(f"{tag}: a failed flip left the card stuck or with an old Buy")
        inl = pg.evaluate(f"({{note:(document.querySelector('{card} .flipnote.bad')||{{}}).textContent,shk:window.__shk,say:document.getElementById('flipsay').textContent}})")
        print(tag, "failure inline:", inl)
        if "Test: could not flip." not in (inl["note"] or "") or "Test: could not flip." not in inl["say"] or (reduce == "no-preference" and not inl["shk"]): bad(f"{tag}: a failed flip didn't show its reason inline, announce it and shake the row: {inl}")
        if fit(): bad(f"{tag}: sideways scroll at the end")

        if tag == "390":
            ORIG = pg.evaluate(f"JSON.stringify(S.build.combos.find(c=>c.i=={ci}))")
            RESET = f"S.quotes={{}};S.qpend={{}};S.bpend={{}};S.fpend={{}};S.flips={{}};S.fturn=null;S.buying=false;window.__acts.length=0;window.__q={{}};S.build.combos[S.build.combos.findIndex(c=>c.i=={ci})]=JSON.parse({json.dumps(ORIG)});renderBuild()"
            PH = lambda: pg.evaluate(f"document.querySelector('{card}').dataset.ph")
            acts = lambda a: pg.evaluate(f"window.__acts.filter(x=>x==={json.dumps(a)}).length")
            def reset():
                pg.evaluate(RESET); wait(pg, f"document.querySelector('{card}').dataset.ph==='idle'", 5); time.sleep(.05)
            def tap_flip(): pg.locator(sel_row).click(); return wait(pg, f"document.querySelector('{card}').dataset.ph==='flip'", 4)
            def release_flip(js="(" + MAKE + f")({ci},{K})"): pg.evaluate(f"window.__q.flip.shift()({{ok:true,verdict:'good',text:'Flipped. Tap it again to undo.',combo:{js}}})")
            rects = lambda: pg.evaluate(f"[...document.querySelectorAll('{card} .brow .btn')].map(b=>{{const r=b.getBoundingClientRect();return [r.left,r.top,r.width,r.height].map(Math.round)}})")
            near = lambda a, b: len(a) == len(b) and all(abs(x - y) <= 1 for p_, q_ in zip(a, b) for x, y in zip(p_, q_))
            # -- layout: nothing moves between idle, loading and arrived (the note's space is reserved up front)
            pg.evaluate("window.__load0=window.load;window.load=async()=>{}")   # no background refresh may reshape the card while it is measured
            reset(); r0 = rects(); tap_flip(); r1 = rects(); release_flip(); wait(pg, f"document.querySelector('{card}').dataset.ph==='idle'", 5); pg.evaluate("Promise.all(document.getAnimations().filter(a=>a.effect&&a.effect.getComputedTiming().endTime!==Infinity).map(a=>a.finished.catch(()=>0)))"); r2 = rects()
            print(tag, "button boxes idle/loading/arrived:", r0, r1, r2)
            if not near(r0, r1) or not near(r0, r2): bad(f"{tag}: the buttons moved during the flip: {r0} {r1} {r2}")
            pg.evaluate("window.load=window.__load0")
            # with a quote showing, the quote's space is kept while loading
            reset(); pg.evaluate(f"S.quotes={{{ci}:{{pays:30.5,stake:5,pct:1.02,clears:true,cut:95,at:Date.now()/1000}}}};renderBuild()"); wait(pg, f"!!document.getElementById('b{ci}')", 5)
            q0 = rects(); tap_flip(); q1 = rects(); print(tag, "with a quote:", q0, q1)
            if not near(q0, q1): bad(f"{tag}: the quote's space collapsed when the flip began: {q0} {q1}")
            release_flip(); wait(pg, f"document.querySelector('{card}').dataset.ph==='idle'", 5)
            # -- a flip while a price is in flight: the late price never becomes a Buy
            reset(); pg.locator(f"#q{ci}").click(); wait(pg, f"document.querySelector('{card}').dataset.ph==='ask'", 4)
            ok1 = tap_flip()
            pg.evaluate("window.__q.quote.shift()({ok:true,pays:30.5,stake:5,pct:1.02,clears:true,cut:95})"); time.sleep(.3)
            mid = pg.evaluate(f"({{buy:!!document.getElementById('b{ci}'),line:!!document.querySelector('{card} .qline'),ph:document.querySelector('{card}').dataset.ph}})")
            release_flip(); wait(pg, f"document.querySelector('{card}').dataset.ph==='idle'", 5)
            end = pg.evaluate(f"({{buy:!!document.getElementById('b{ci}'),q:!!S.quotes[{ci}],get:!!document.getElementById('q{ci}')&&!document.getElementById('q{ci}').disabled}})")
            print(tag, "flip while asking:", ok1, mid, end)
            if not ok1 or mid["buy"] or mid["line"] or mid["ph"] != "flip" or end["buy"] or end["q"] or not end["get"]: bad(f"{tag}: a price that landed during the flip showed or survived it: {mid} {end}")
            # -- a flip while a buy is in flight is blocked, and nothing can buy during a flip
            reset(); pg.evaluate(f"S.bpend={{{ci}:{{t:Date.now(),sig:ccSig(S.build.combos.find(c=>c.i=={ci}))}}}};renderBuild()"); time.sleep(.1)
            pg.locator(sel_row).click(force=True); time.sleep(.3)
            if acts("flip"): bad(f"{tag}: a flip was sent while a buy was in flight")
            reset(); tap_flip(); pg.evaluate(f"void buy({ci},false,null)"); time.sleep(.2)
            if acts("buy"): bad(f"{tag}: buy() went out during a flip")
            release_flip(); wait(pg, f"document.querySelector('{card}').dataset.ph==='idle'", 5)
            # -- a rebuild, a league switch or a missing board during a flip: the answer is never written over them
            reset(); tap_flip()
            pg.evaluate(f"(()=>{{const k=S.build.combos.findIndex(c=>c.i=={ci});const n=JSON.parse({json.dumps(ORIG)});n.legs[0].ticker+='-R';S.build.combos[k]=n;renderBuild();}})()")
            release_flip(); time.sleep(.5)
            res = pg.evaluate(f"({{t:S.build.combos.find(c=>c.i=={ci}).legs[0].ticker.endsWith('-R'),n:!!(S.flips&&S.flips[{ci}]),fp:!!(S.fpend&&S.fpend[{ci}])}})")
            if not (res["t"] and not res["n"] and not res["fp"]): bad(f"{tag}: a flip answer overwrote a rebuilt combo: {res}")
            reset(); tap_flip(); pg.evaluate("window.__lg=S.lg;S.lg='other-league'"); release_flip(); time.sleep(.5); pg.evaluate("S.lg=window.__lg")
            res = pg.evaluate(f"({{t:S.build.combos.find(c=>c.i=={ci}).legs[0].ticker.endsWith('-FLIP')||S.build.combos.find(c=>c.i=={ci}).legs[{K}].ticker.endsWith('-FLIP'),n:!!(S.flips&&S.flips[{ci}])}})")
            if res["t"] or res["n"]: bad(f"{tag}: a flip answer was applied after the league changed: {res}")
            reset(); tap_flip(); pg.evaluate("window.__sb=S.build;S.build=null"); release_flip("JSON.parse(" + json.dumps(ORIG) + ")"); time.sleep(.5); pg.evaluate("S.build=window.__sb;renderBuild()")
            # -- a second flip after the 60 s lapse: the first answer can't clear or overwrite it
            reset(); tap_flip(); pg.evaluate(f"S.fpend[{ci}].t-=61000;renderBuild()"); wait(pg, f"document.querySelector('{card}').dataset.ph==='idle'", 4)
            tap_flip(); n2 = acts("flip")
            release_flip()   # the first (stale) answer
            time.sleep(.4); still = PH(); unchanged = pg.evaluate(f"ccSig(S.build.combos.find(c=>c.i=={ci}))=={json.dumps(before['sig'])}")
            print(tag, "after lapse: flips sent", n2, "phase after stale answer", still)
            if n2 != 2 or still != "flip" or not unchanged: bad(f"{tag}: the stale first answer cleared or overwrote the second flip: {n2} {still} {unchanged}")
            release_flip(); wait(pg, f"document.querySelector('{card}').dataset.ph==='idle'", 5)
            if pg.evaluate(f"ccSig(S.build.combos.find(c=>c.i=={ci}))=={json.dumps(before['sig'])}"): bad(f"{tag}: the second flip's answer wasn't applied")
            reset()
        if errs: bad(f"{tag}: JS errors {errs[:3]}")
        ctx.close()
    br.close()

print("PROBLEMS: " + " | ".join(problems) if problems else "all flip-leg checks passed")
