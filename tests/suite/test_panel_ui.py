# CHECK: group=page secs=37
import sys, os, time, threading, re, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
tk_ev = sorted({m["event_ticker"] for m in mk})
def L(i, team): ev = tk_ev[i]; return {"ticker": f"{ev}-{team}", "event_ticker": ev, "event": ev, "side": "yes"}
bets = [
 {"ticker": "KXMVE-1", "legs": [L(0, "BOS"), L(1, "DEN"), L(2, "MIL")], "cost": 5.0, "pays": 41.2, "status": "pending", "back": 0, "week": "2026-11-17", "full_pays": 41.2, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-2", "legs": [L(0, "NYK"), L(3, "GSW"), L(1, "LAL"), L(2, "CHI")], "cost": 4.93, "pays": 980, "status": "pending", "back": 0, "week": "2026-11-17", "full_pays": 980, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-3", "legs": [L(3, "PHX"), L(1, "DEN")], "cost": 8.0, "pays": 19.5, "status": "pending", "back": 0, "week": "2026-11-17", "full_pays": 19.5, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-4", "legs": [L(0, "BOS"), L(2, "CHI")], "cost": 5.0, "pays": 22, "status": "lost", "back": 0, "week": "2026-11-12", "full_pays": 22, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-5", "legs": [L(0, "BOS"), L(1, "DEN")], "cost": 5.0, "pays": 14, "status": "won", "back": 14, "week": "2026-11-17", "full_pays": 14, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-6", "legs": [L(3, "PHX"), L(2, "MIL")], "cost": 6.0, "pays": 30, "status": "cashed", "back": 11.4, "week": "2026-11-17", "full_pays": 30, "lg": "nba", "lgs": ["nba"]}]
def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: (bets, 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    A.MINE["cash"]["KXMVE-3"] = {"rfq": "r", "quote": "q", "offer": 15.8, "price": .81, "contracts": 19.5, "frac": 1.0, "at": time.time() + 3600}
    A.MINE["cash"]["KXMVE-1"] = {"rfq": "estimate", "offer": 9.1, "frac": 1.0, "at": time.time()}
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
VW, VH = int(os.environ.get("VW", 1440)), int(os.environ.get("VH", 900)); TAG = os.environ.get("TAG", "d")
with sync_playwright() as pw:
    br = pw.chromium.launch(); P=open("panel_fixture.json").read()
    for vw,vh,tag in ((390,844,"m"),(1400,900,"d")):
        pg = br.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=2, color_scheme="dark")
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(B + "/app"); time.sleep(5)
        pg.evaluate("go('build')"); time.sleep(8)
        print(tag,"api panel:", pg.evaluate("JSON.stringify(S.panel).slice(0,80)"))
        pg.evaluate("S.panel="+P+";renderBuild()"); time.sleep(.5)
        pg.screenshot(path=f"panel_{tag}.png", full_page=(tag=="m"))
        pg.evaluate("pToggle('line:D')"); time.sleep(.2)
        print(tag,"btn:", pg.evaluate("[...document.querySelectorAll('.panel .btn')].map(b=>b.innerText).join('|')"))
        # issue #51: bought right after approval, so the cards say so (no buy time to wait for)
        pg.evaluate("S.pOff=new Set();const q=JSON.parse(JSON.stringify("+P+"));q.panel.items.forEach(c=>{c.kick=Date.now()/1000+9*3600;delete c.buy_at});S.panel=q;renderBuild()"); time.sleep(.3)
        ch = pg.evaluate("[...document.querySelectorAll('.panel .ps .tag')].map(t=>t.innerText)")
        sub = pg.evaluate("document.querySelector('.panel').innerText")
        print(tag, "draft chips:", ch[:3])
        if not ch or not all(x.lower() == "buys when you approve" for x in ch): print("PROBLEMS: draft cards should say they buy when you approve", ch)
        if "right after you approve" not in sub or "shortly before" in sub: print("PROBLEMS: approve note still talks about waiting")
        pg.evaluate("S.pOff=new Set();const q=JSON.parse(JSON.stringify("+P+"));q.panel.status='approved';q.panel.items.forEach((c,i)=>{c.kick=Date.now()/1000+9*3600;c.state=i?'scheduled':'bought'});S.panel=q;renderBuild()"); time.sleep(.3)
        ch = pg.evaluate("[...document.querySelectorAll('.panel .ps .tag')].map(t=>t.innerText)")
        print(tag, "approved chips:", ch[:3])
        if ch[0].lower() != "bought" or not all(x.lower() == "buying now" for x in ch[1:]) or any("when you" in x for x in ch): print("PROBLEMS: approved cards' chips", ch)
        pg.evaluate("S.pOff=new Set();const q=JSON.parse(JSON.stringify("+P+"));q.panel.status='approved';const h=['paused','price','no key'];q.panel.items.forEach((c,i)=>{c.kick=Date.now()/1000+9*3600;c.state='scheduled';c.hold=h[i]});S.panel=q;renderBuild()"); time.sleep(.3)
        ch = pg.evaluate("[...document.querySelectorAll('.panel .ps .tag')].map(t=>t.innerText.toLowerCase())")
        print(tag, "held chips:", ch[:3])
        if ch[:3] != ["paused · not bought yet", "waiting for a fresh price", "can't trade from here"]: print("PROBLEMS: held cards should say why", ch)
        pg.evaluate("S.pOff=new Set();S.panel="+P+";renderBuild()"); time.sleep(.3)
        # issue #61: every bet says which game it is on (a spread or total used to say only "Over 7.5")
        # drafts saved before the change have no game text: the card still names the game from what it does carry
        old_pg = pg.evaluate("[...document.querySelectorAll('.panel .pitem')].map(e=>[e.dataset.pid,[...e.querySelectorAll('.pg div')].map(d=>d.innerText)])")
        print(tag, "older drafts:", old_pg)
        got = dict(old_pg)
        if got.get("line:D") != ["BOS at LAL"] or got.get("early:A") != ["Avalanche vs Sharks"] or got.get("single:B") != ["Lakers vs Boston Celtics"]:
            print("PROBLEMS: older drafts should still name the game", old_pg)
        # new drafts carry the game and league on each bet (and each leg of a combo), long names included
        pg.evaluate("""(()=>{const q=JSON.parse(JSON.stringify(%s));const g={'early:A':['Avalanche vs Sharks'],'single:B':['Lakers vs Celtics'],
          'combo:C':['Avalanche vs Sharks','Golden Knights vs Kings'],'line:D':['Boston Celtics at Los Angeles Lakers']};
          q.panel.items.forEach(c=>{c.league={nhl:'NHL',nba:'NBA'}[c.code];c.game=(g[c.id]||[''])[0];if(c.kind==='combo')c.legs.forEach((l,i)=>l.game=g[c.id][i]);
          if(c.kind==='line')c.legs[0].pick='Over 220.5 points (Boston Celtics at Los Angeles Lakers)';});
          q.panel.items.push({id:'line:E',kind:'line',code:'ncaaf',league:'CFB',icon:'🎓',legs:[{ticker:'E',pick:'Temple Owls win by 7.5+'}],game:'Temple Owls at Tulane Green Wave and a very long extra name to test wrapping',chance:.4,ret:.2,price:.3,stake:2,kick:Date.now()/1000+9*3600});
          S.pOff=new Set();S.panel=q;renderBuild();})()""" % P); time.sleep(.4)
        new_pg = pg.evaluate("[...document.querySelectorAll('.panel .pitem')].map(e=>[e.dataset.pid,e.querySelector('.pk').innerText,[...e.querySelectorAll('.pg div')].map(d=>d.innerText)])")
        print(tag, "new drafts:", new_pg)
        if len(new_pg) != 5 or any(not x[2] for x in new_pg if x[0] != "combo:C"): print("PROBLEMS: every panel card should name its game", new_pg)
        byid = {x[0]: x for x in new_pg}
        ctitle = pg.evaluate("document.querySelector('.pitem[data-pid=\"combo:C\"] .pm b').innerText")
        if ctitle.split("\n") != ["Avalanche vs Sharks", "Golden Knights vs Kings"] or byid["combo:C"][2]: print("PROBLEMS: each leg of a combo should name its game once, in its title", ctitle, byid["combo:C"])
        if "NHL" not in byid["early:A"][1] or "CFB" not in byid["line:E"][1] or "SPREAD / TOTAL" not in byid["line:D"][1].upper(): print("PROBLEMS: league tag missing", [x[1] for x in new_pg])
        if byid["line:D"][2] != ["Boston Celtics at Los Angeles Lakers"]: print("PROBLEMS: a total should name its game", byid["line:D"])
        titles = pg.evaluate("[...document.querySelectorAll('.panel .pitem')].map(e=>[e.dataset.pid,e.querySelector('.pm b').innerText])")
        if dict(titles)["line:D"] != "Over 220.5 points" or dict(titles)["single:B"] != "Lakers to win": print("PROBLEMS: bet titles", titles)
        over = pg.evaluate("[...document.querySelectorAll('.panel .pitem')].filter(e=>e.scrollWidth>e.clientWidth+1||e.querySelector('.pm').scrollWidth>e.querySelector('.pm').clientWidth+1).map(e=>e.dataset.pid)")
        side = pg.evaluate("document.documentElement.scrollWidth>window.innerWidth+1")
        if over or (tag == "m" and side): print("PROBLEMS: a long game name overflows its card", over, side)
        pg.screenshot(path=f"panelgame_{tag}.png", full_page=(tag == "m"))
        # the buy-timing chip: before approval it says when it buys; after, the buy state (never a bare "buys")
        pg.evaluate("S.pOff=new Set();const q=JSON.parse(JSON.stringify(%s));q.panel.items.forEach(c=>{c.kick=Date.now()/1000+9*3600;delete c.buy_at});S.panel=q;renderBuild()" % P); time.sleep(.3)
        chips = pg.evaluate("[...document.querySelectorAll('.panel .ps .tag')].map(t=>t.innerText.trim().toLowerCase())")
        if any(x == "buys" for x in chips) or any(x != "buys when you approve" for x in chips): print("PROBLEMS: chip wording before approval", chips)
        pg.evaluate("S.pOff=new Set();S.panel="+P+";renderBuild()"); time.sleep(.3)
        print(tag, "errs:", errs)
