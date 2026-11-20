"""Build combo idea cards (GitHub #65): (1) the button row always fits inside its card, at 360, 390 and 430 pt, in every
state: Get price, price asked, Buy, Buy anyway $5 -> $7.29, Buying (confirming with Kalshi) and Bought; "Not this one"
never runs off the edge and no label is clipped. (2) the Get price button doesn't flicker or get replaced: once a price is
asked for (or a buy is under way) a refresh tick (load, renderBuild, the countdown) keeps the very same button element,
with the same opacity; only the "Ns left" number changes inside it, and nothing is redrawn every second. Prices and buys
are held in the page by a fake fetch (never a real order). Prints PROBLEMS."""
import requests
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        if pg.evaluate(js): return True
        time.sleep(.2)
    return False

# act calls are answered here, held until the test releases them (pending quote / pending buy), never real
HOLD = r"""(()=>{const real=window.fetch.bind(window);window.__held={};window.__acts=[];
 window.fetch=(u,o)=>{if(String(u).includes('/app/api/act')&&o&&o.body){let b={};try{b=JSON.parse(o.body)}catch(e){}window.__acts.push(b.a);
   if(b.a==='quote'||b.a==='buy')return new Promise(res=>{window.__held[b.a]=out=>res(new Response(JSON.stringify(out),{status:200,headers:{'Content-Type':'application/json'}}));});
   return Promise.resolve(new Response(JSON.stringify({ok:true,msg:'ok'}),{status:200,headers:{'Content-Type':'application/json'}}));}
  return real(u,o);};})()"""
# does every button in every card's row sit inside the card, with its text not clipped, and the page not scroll sideways
FIT = r"""(()=>{const out=[];document.querySelectorAll('#main .ccard').forEach(c=>{const cr=c.getBoundingClientRect();
 c.querySelectorAll('.brow .btn').forEach(b=>{const r=b.getBoundingClientRect();
  if(r.left<cr.left-.5||r.right>cr.right+.5)out.push('outside card: '+b.textContent.trim().slice(0,30)+' '+Math.round(r.right-cr.right)+'px');
  if(b.scrollWidth>b.clientWidth+1)out.push('clipped: '+b.textContent.trim().slice(0,30));
  if(r.width<40)out.push('too narrow: '+b.textContent.trim().slice(0,30));});
 if(c.scrollWidth>c.clientWidth+1)out.push('card wider than itself');});
 if(document.documentElement.scrollWidth>innerWidth+1)out.push('page scrolls sideways');return out;})()"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw in (360, 390, 430):
        ctx = br.new_context(viewport={"width": vw, "height": 844}, has_touch=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.dismiss())
        tag = f"{vw}pt"; pg.set_default_timeout(8000)
        pg.route("**/app/api/act", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "msg": "ok"})))
        pg.add_init_script("if(!sessionStorage.getItem('k')){localStorage.clear();sessionStorage.setItem('k','1');}localStorage.setItem('cw_view','build')")
        pg.add_init_script(HOLD)
        pg.goto(B + "/app")
        if not wait(pg, "!!(S.build&&S.build.combos&&S.build.combos.length)", 40): bad(f"{tag}: Build never loaded combos"); ctx.close(); continue
        pg.evaluate("S.adv=true;S.bsec.combos=true;S.bsec.games=false;renderBuild()"); time.sleep(.6)
        n = pg.evaluate("document.querySelectorAll('#main .ccard').length"); ci = pg.evaluate("S.build.combos.find(c=>!c.bought).i")
        print(tag, "combo cards:", n, "first:", ci)
        if n < 1: bad(f"{tag}: no combo cards to test"); ctx.close(); continue

        # ---- 1. the row fits in every state
        def state(label, js):
            pg.evaluate(js); time.sleep(.25)
            miss = pg.evaluate(FIT)
            print(tag, label, "->", miss or "fits")
            if miss: bad(f"{tag} {label}: {miss}")
        now = "Date.now()/1000"
        state("Get price", "S.quotes={};S.qpend={};S.bpend={};renderBuild()")
        state("price asked", f"S.qpend={{{ci}:Date.now()}};renderBuild()")
        state("Buy", f"S.qpend={{}};S.quotes={{{ci}:{{pays:30.5,stake:5,pct:1.02,clears:true,cut:95,at:{now}}}}};renderBuild()")
        state("Buy anyway $5 -> $7.29", f"S.quotes={{{ci}:{{pays:7.29,stake:5,pct:.82,clears:false,cut:95,at:{now}}}}};renderBuild()")
        txt = pg.evaluate(f"document.querySelector('#b{ci}').textContent.trim()")
        if "Buy anyway" not in txt or "7.29" not in txt: bad(f"{tag}: the Buy anyway button reads '{txt}'")
        state("Buying... confirming with Kalshi", f"S.bpend={{{ci}:Date.now()}};renderBuild()")
        if "Buying… confirming with Kalshi" not in pg.evaluate(f"document.querySelector('#b{ci}').textContent"): bad(f"{tag}: the Buying button lost its words")
        if not pg.evaluate(f"document.querySelector('#b{ci}').disabled && document.querySelector('#b{ci}').parentNode.querySelector('.sec').disabled"):
            bad(f"{tag}: while buying, the button and 'Not this one' should both be disabled")
        state("Bought", f"S.bpend={{}};S.quotes={{}};S.build.combos.find(c=>c.i=={ci}).bought=true;renderBuild()")
        pg.evaluate(f"S.build.combos.find(c=>c.i=={ci}).bought=false;renderBuild()")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{tag}: Build scrolls sideways")

        # ---- 2. Get price: the same button, not flickering, while a price is pending and across refreshes
        pg.evaluate("S.quotes={};S.qpend={};S.bpend={};renderBuild()"); time.sleep(.3)
        # every animation frame: is the button still the same element, and what is its opacity (a flicker shows here)
        pg.evaluate("window.__btn0=document.getElementById('q%d')" % ci)
        pg.locator(f"#q{ci}").tap(); time.sleep(.5)                   # the tap's own dimming (0.18 s) is over
        pg.evaluate("window.__fr=[];window.__run=true;(function f(){const b=document.getElementById('q%d');"
                    "window.__fr.push([b===window.__btn0,b?getComputedStyle(b).opacity:'gone']);if(window.__run)requestAnimationFrame(f);})()" % ci)
        st = pg.evaluate(f"({{same:document.getElementById('q{ci}')===window.__btn0,dis:window.__btn0.disabled,txt:window.__btn0.textContent.trim(),op:getComputedStyle(window.__btn0).opacity,asks:window.__acts.filter(a=>a==='quote').length}})")
        print(tag, "pending:", st)
        if not (st["same"] and st["dis"] and "Asking Kalshi" in st["txt"]): bad(f"{tag}: tapping Get price didn't leave one waiting button: {st}")
        # a second tap on the waiting button must not ask twice
        pg.evaluate(f"void quote({ci})"); time.sleep(.1)
        if pg.evaluate("window.__acts.filter(a=>a==='quote').length") != 1: bad(f"{tag}: a second tap asked Kalshi for a second price")
        ticks = []
        for k in range(4):                                            # refresh ticks while the price is pending
            pg.evaluate("renderBuild()" if k % 2 == 0 else "load('build')"); time.sleep(.9 if k % 2 else .2)
            ticks.append(pg.evaluate(f"({{same:document.getElementById('q{ci}')===window.__btn0,conn:window.__btn0.isConnected,dis:window.__btn0.disabled,txt:window.__btn0.textContent.trim(),op:getComputedStyle(window.__btn0).opacity}})"))
        print(tag, "ticks:", ticks)
        for t in ticks:
            if not (t["same"] and t["conn"] and t["dis"] and "Asking Kalshi" in t["txt"] and t["op"] == st["op"]):
                bad(f"{tag}: the Get price button was replaced or changed while a price was pending: {t} (was opacity {st['op']})"); break
        fr = pg.evaluate("window.__fr.slice()")
        print(tag, "frames while pending:", len(fr), "distinct (same, opacity):", sorted({tuple(x) for x in fr}))
        if len(fr) < 10 or any(not x[0] or x[1] != st["op"] for x in fr): bad(f"{tag}: the Get price button flickered (a frame without it, or a different opacity): {sorted({tuple(x) for x in fr})}")
        # the price arrives: a Buy button, one redraw, then it stays put while the countdown runs
        pg.evaluate("window.__run=false")
        pg.evaluate("window.__held.quote({ok:true,pays:30.5,stake:5,pct:1.02,clears:true,cut:95})")
        wait(pg, f"!!document.getElementById('b{ci}')", 6); time.sleep(.3)
        pg.evaluate(f"window.__btn1=document.getElementById('b{ci}');window.__qs0=document.querySelector('.qs').textContent;"
                    "window.__bar_p0=(document.getAnimations().find(a=>a.effect&&a.effect.target&&a.effect.target.classList.contains('qt'))||{effect:{getComputedTiming:()=>({progress:null})}}).effect.getComputedTiming().progress;"
                    "window.__fr=[];window.__run=true;(function f(){const b=document.querySelector('.ccard[data-i=\"%d\"] .btn.pri');window.__fr.push([b===window.__btn1,b?getComputedStyle(b).opacity:'gone']);if(window.__run)requestAnimationFrame(f);})()" % ci)
        time.sleep(2.4)
        pg.evaluate("renderBuild()"); pg.evaluate("load('build')"); time.sleep(.8)
        cd = pg.evaluate(f"({{same:document.getElementById('b{ci}')===window.__btn1,q0:window.__qs0,q1:document.querySelector('.qs').textContent,txt:window.__btn1.textContent.trim(),"
                         "bar:(document.getAnimations().find(a=>a.effect&&a.effect.target&&a.effect.target.classList.contains('qt'))||{effect:{getComputedTiming:()=>({progress:null})}}).effect.getComputedTiming().progress,bar0:window.__bar_p0,want:(Date.now()/1000-S.quotes[%d].at)/20,newCls:!!document.querySelector('.qline.new')})" % ci)
        fr = pg.evaluate("window.__run=false;window.__fr.slice()")
        print(tag, "countdown:", cd, "frames:", len(fr), sorted({tuple(x) for x in fr}))
        if not cd["same"] or any(not x[0] for x in fr): bad(f"{tag}: the Buy button was replaced while the countdown ran: {cd}")
        if cd["bar"] is None or cd["bar0"] is None or not (cd["bar"] > cd["bar0"] + .08) or abs(cd["bar"] - cd["want"]) > .08 or cd["newCls"]:
            bad(f"{tag}: the draining bar restarted or jumped on a refresh (or the entrance replayed): {cd}")
        if int(cd["q1"]) >= int(cd["q0"]): bad(f"{tag}: the 'Ns left' number didn't count down in place: {cd}")
        # a buy under way keeps its button too
        pg.evaluate("window.__btn1.click()"); time.sleep(.3)
        pg.evaluate("renderBuild();load('build')"); time.sleep(1.0)
        by = pg.evaluate(f"({{same:document.getElementById('b{ci}')===window.__btn1,dis:window.__btn1.disabled,txt:window.__btn1.textContent.trim(),sec:window.__btn1.parentNode.querySelector('.sec').disabled}})")
        print(tag, "buying:", by)
        if not (by["same"] and by["dis"] and "Buying" in by["txt"] and by["sec"]): bad(f"{tag}: the Buying button was replaced or still tappable: {by}")
        miss = pg.evaluate(FIT)
        if miss: bad(f"{tag} live Buying: {miss}")
        pg.evaluate("window.__held.buy({ok:false,msg:'Test: not bought.'})"); time.sleep(.6)
        if pg.evaluate(f"!!S.bpend[{ci}]||S.buying"): bad(f"{tag}: a finished buy left the card stuck on Buying")
        # an expired quote puts Get price back (one redraw)
        pg.evaluate(f"S.quotes={{{ci}:{{pays:30,stake:5,pct:1,clears:true,cut:95,at:Date.now()/1000-19.2}}}};renderBuild();qTick()"); time.sleep(2.4); pg.evaluate("qTick()"); time.sleep(.3)
        if not pg.evaluate(f"!!document.getElementById('q{ci}')&&!document.getElementById('b{ci}')"): bad(f"{tag}: an expired quote didn't go back to Get price")
        if pg.evaluate("document.querySelectorAll('#main .qs').length"): bad(f"{tag}: an expired quote still shows a countdown")
        bought = pg.evaluate("window.__acts.filter(a=>a==='buy').length")
        print(tag, "buy taps reaching the page's fake:", bought, "errs:", errs)
        if errs: bad(f"{tag}: JS errors {errs[:3]}")
        ctx.close()
    br.close()

print("PROBLEMS: " + " | ".join(problems) if problems else "all Build button checks passed")
