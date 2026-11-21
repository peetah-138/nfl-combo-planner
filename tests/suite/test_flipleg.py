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
HOLD = r"""(()=>{const real=window.fetch.bind(window);window.__held={};window.__acts=[];
 window.fetch=(u,o)=>{if(String(u).includes('/app/api/act')&&o&&o.body){let b={};try{b=JSON.parse(o.body)}catch(e){}window.__acts.push(b.a);
   if(b.a==='flip'||b.a==='quote')return new Promise(res=>{window.__held[b.a]=out=>res(new Response(JSON.stringify(out),{status:200,headers:{'Content-Type':'application/json'}}));});
   return Promise.resolve(new Response(JSON.stringify({ok:true,msg:'ok'}),{status:200,headers:{'Content-Type':'application/json'}}));}
  return real(u,o);};})()"""
# the combo as it would come back with leg k flipped to the other team (other ticker, other chance)
MAKE = r"""((i,k)=>{const c=S.build.combos.find(x=>x.i===i);const l=c.legs[k];const n=JSON.parse(JSON.stringify(c));
 n.legs[k]=Object.assign({},l,{ticker:l.ticker+'-FLIP',pick:'Flipped team',fair:.4});n.chance=(c.chance||.2)*0.5;n.fair=(c.fair||10)*1.9;return n;})"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for tag, vp, reduce in (("390", {"width": 390, "height": 844}, "no-preference"), ("desktop", {"width": 1280, "height": 900}, "no-preference"),
                            ("390-reduced", {"width": 390, "height": 844}, "reduce")):
        ctx = br.new_context(viewport=vp, has_touch=vp["width"] < 500, reduced_motion=reduce)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.dismiss())
        pg.set_default_timeout(8000)
        pg.add_init_script("if(!sessionStorage.getItem('k')){localStorage.clear();sessionStorage.setItem('k','1');}localStorage.setItem('cw_view','build')")
        pg.add_init_script(HOLD)
        pg.goto(B + "/app")
        if not wait(pg, "!!(S.build&&S.build.combos&&S.build.combos.length)", 40): bad(f"{tag}: Build never loaded combos"); ctx.close(); continue
        pg.evaluate("S.adv=true;S.bsec.combos=true;S.bsec.games=false;renderBuild()"); time.sleep(.6)
        ci = pg.evaluate("S.build.combos.find(c=>!c.bought&&c.legs.length>1).i"); K = 0
        card = f"#main .ccard[data-i=\"{ci}\"]"
        sel_row = f"{card} .lrow.flip >> nth={K}"
        def shot(n):
            if SHOTS and tag == "390": os.makedirs(SHOTS, exist_ok=True); pg.locator(card).screenshot(path=f"{SHOTS}/{n}.png")
        fit = lambda: pg.evaluate("document.documentElement.scrollWidth>innerWidth+1")
        # a quote is on the card first (a Buy button)
        pg.evaluate(f"S.quotes={{{ci}:{{pays:30.5,stake:5,pct:1.02,clears:true,cut:95,at:Date.now()/1000}}}};renderBuild()"); time.sleep(.3)
        if not pg.evaluate(f"!!document.getElementById('b{ci}')"): bad(f"{tag}: setup: no Buy button before the flip")
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
          note:!!document.querySelector('{card} .flipnote.in'),noteTxt:(document.querySelector('{card} .flipnote')||{{}}).textContent,live:document.querySelector('{card} .fnw').getAttribute('aria-live'),
          q:(()=>{{const b=document.getElementById('q{ci}');return b?{{dis:b.disabled,txt:b.textContent.trim()}}:null}})(),buy:!!document.getElementById('b{ci}'),quote:!!(S.quotes&&S.quotes[{ci}]),
          anim:getComputedStyle(document.querySelector('{card} .lrow.turn')||document.body).animationName}})""")
        print(tag, "arrived:", now)
        if now["pick"] != "Flipped team": bad(f"{tag}: the flipped leg didn't show: {now}")
        if not now["turn"] or not now["note"] or "Tap it again to undo" not in (now["noteTxt"] or ""): bad(f"{tag}: no turn-in or note slide-in: {now}")
        if now["live"] != "polite": bad(f"{tag}: the note isn't in a polite live region")
        if not (now["q"] and not now["q"]["dis"] and now["q"]["txt"] == "Get price") or now["buy"] or now["quote"]: bad(f"{tag}: Buy didn't revert to Get price: {now}")
        if reduce == "reduce" and now["anim"] not in ("lfade",): bad(f"{tag}: reduced motion should crossfade, got {now['anim']}")
        if reduce == "no-preference" and now["anim"] != "lturn": bad(f"{tag}: the new row doesn't turn in: {now['anim']}")
        # the numbers roll (no-preference only): sample the fair payout mid-roll
        if reduce == "no-preference":
            mid = pg.evaluate(f"document.querySelector('{card} [data-num=\"cf:{ci}\"]').textContent")
            fin = pg.evaluate(f"money(S.build.combos.find(c=>c.i=={ci}).fair)")
            print(tag, "fair payout mid-roll:", mid, "final:", fin, "was:", before["fair"])
            if not wait(pg, f"document.querySelector('{card} [data-num=\"cf:{ci}\"]').textContent===money(S.build.combos.find(c=>c.i=={ci}).fair)", 4): bad(f"{tag}: the fair payout never rolled to its new value")
            time.sleep(.4); shot("3_after")
        # a dead old-price tap can't happen: no Buy exists; also an old fetched quote that lands late is dropped (sig changed)
        if pg.evaluate(f"ccSig(S.build.combos.find(c=>c.i=={ci}))") == before["sig"]: bad(f"{tag}: the legs didn't change")
        if fit(): bad(f"{tag}: sideways scroll after the flip")
        # ---- 3. a quote after the flip, then undo: the quote goes, same animation
        pg.evaluate(f"S.quotes={{{ci}:{{pays:30.5,stake:5,pct:1.02,clears:true,cut:95,at:Date.now()/1000}}}};renderBuild()"); time.sleep(.3)
        pg.evaluate("window.__acts.length=0"); pg.locator(sel_row).click()
        if not wait(pg, f"document.querySelector('{card}').dataset.ph==='flip'", 3) or pg.evaluate(f"!!document.getElementById('b{ci}')||!!S.quotes[{ci}]"): bad(f"{tag}: undo tap: no loading state / quote survived")
        pg.evaluate(f"window.__held.flip({{ok:true,verdict:'mid',text:'Flipped back. Tap it again to undo.',combo:(()=>{{const c=JSON.parse(JSON.stringify(S.build.combos.find(x=>x.i=={ci})));c.legs[{K}]=Object.assign({{}},c.legs[{K}],{{ticker:c.legs[{K}].ticker.replace('-FLIP',''),pick:{json.dumps('Original')}}});return c;}})()}})")
        wait(pg, f"document.querySelector('{card}').dataset.ph==='idle'", 5)
        back = pg.evaluate(f"({{sig:ccSig(S.build.combos.find(c=>c.i=={ci})),pick:document.querySelectorAll('{card} .lrow.flip')[{K}].querySelector('b').textContent,turn:!!document.querySelector('{card} .lrow.turn'),buy:!!document.getElementById('b{ci}')}})")
        print(tag, "undone:", back)
        if back["sig"] != before["sig"] or not back["turn"] or back["buy"]: bad(f"{tag}: undo didn't restore the legs with the same turn, or left a Buy: {back}")
        # ---- 4. a failed flip: card back, no quote, a toast, not stuck
        pg.evaluate(f"S.quotes={{{ci}:{{pays:30.5,stake:5,pct:1.02,clears:true,cut:95,at:Date.now()/1000}}}};renderBuild()"); time.sleep(.3)
        pg.locator(sel_row).click(); wait(pg, f"document.querySelector('{card}').dataset.ph==='flip'", 3)
        pg.evaluate("window.__held.flip({ok:false,msg:'Test: could not flip.'})")
        ok = wait(pg, f"document.querySelector('{card}').dataset.ph==='idle'&&!!document.getElementById('q{ci}')&&!document.getElementById('q{ci}').disabled", 5)
        print(tag, "failed flip:", ok, pg.evaluate(f"({{ph:document.querySelector('{card}').dataset.ph,q:!!document.getElementById('q{ci}'),dis:(document.getElementById('q{ci}')||{{}}).disabled,b:!!document.getElementById('b{ci}'),fp:JSON.stringify(S.fpend),acts:window.__acts}})"))
        if not ok or pg.evaluate(f"!!document.getElementById('b{ci}')||!!(S.quotes&&S.quotes[{ci}])||!!(S.fpend&&S.fpend[{ci}])"): bad(f"{tag}: a failed flip left the card stuck or with an old Buy")
        if fit(): bad(f"{tag}: sideways scroll at the end")
        if errs: bad(f"{tag}: JS errors {errs[:3]}")
        ctx.close()
    br.close()

print("PROBLEMS: " + " | ".join(problems) if problems else "all flip-leg checks passed")
