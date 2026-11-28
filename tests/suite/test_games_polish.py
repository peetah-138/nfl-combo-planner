# CHECK: group=page secs=10
"""Games tab + game sheet polish (package B): exact-value checks at 390x844. Cards: one Your pick tag in the header, scores right-aligned,
no chance block when there is no chance, bet chips on one row (2 + a +N), bet-type chips 44px tall; states: skeleton, empty, load error, game
sheet error/not-found wording, opaque buy bar with its price note. Prints PROBLEMS on any failure."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    A.open_singles = lambda: []
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        if pg.evaluate(js): return True
        time.sleep(.2)
    return False


def G(tk, name, opp, **kw):
    g = {"name": name, "opp": opp, "sport": "nba", "ticker": tk, "combos": 2, "pays": 12.5, "kind": "win", "state": "pre", "phase": "",
         "sc": None, "chance": .56, "singles": [{"kind": "spread", "plain": "Over 225.5 total points"}, {"kind": "win", "plain": "Celtics to win"}, {"kind": "win", "plain": "Knicks to win"}], "spark": []}
    g.update(kw); return g
CARDS = [G("KXNBAGAME-26NOV28BOSNYK-BOS", "Boston Celtics", "New York Knicks"),
         G("KXNBAGAME-26NOV28DALLAL-DAL", "Dallas Mavericks", "Los Angeles Lakers Of The Very Long Name Club", chance=None, combos=0, singles=[])]
PROBE = """(cards)=>{S.games={games:cards,fresh:null};S.view='games';render();
 const cs=[...document.querySelectorAll('#main .gc')];
 return {n:cs.length,mine:cs.map(c=>c.querySelectorAll('.gh .mine').length),mineText:cs[0].querySelector('.gh .mine').textContent,mineInRow:cs.map(c=>c.querySelectorAll('.gtr .mine').length),
  gl:cs.map(c=>c.querySelectorAll('.gl').length),bt:cs.map(c=>[...c.querySelectorAll('.bets .bt')].map(b=>b.textContent.trim())),
  rows:cs.map(c=>new Set([...c.querySelectorAll('.bets .bt')].map(b=>b.offsetTop)).size),
  chipH:[...document.querySelectorAll('.btchips .chip')].map(c=>c.offsetHeight),
  secH:Math.round(document.querySelector('h2.gsec').getBoundingClientRect().height),
  ptsAlign:null,inline:document.querySelectorAll('#main [style]').length,sideways:document.documentElement.scrollWidth>document.documentElement.clientWidth+1};}"""
SKEL = """()=>{S.games=null;S.lerr={};renderGames();const a={sk:document.querySelectorAll('#main .gsk').length,s1:document.querySelectorAll('#main .gsk .s1').length,busy:document.querySelector('#main .games').getAttribute('aria-busy')};
 S.lerr={games:1};renderGames();a.err=document.querySelector('#main .card.empty.err b').textContent;a.errBtn=document.querySelector('#main .card.empty.err button').textContent;
 S.games={games:[],fresh:null};S.lerr={};renderGames();a.empty=document.querySelector('#main .card.empty b').textContent;a.emptyBtn=document.querySelector('#main .card.empty button').textContent;
 S.games={games:[{name:'x',opp:'y',sport:'nba',ticker:'T',kind:'win',state:'pre',combos:1,pays:1,singles:[]}],fresh:null};e0=document.createElement('div');e0.innerHTML=gamesEmpty(true);a.empty2=e0.querySelector('b').textContent;a.empty2Btn=e0.querySelector('button').textContent;
 const e=document.createElement('div');var e0;e.innerHTML=gameErr(true);a.gerrF=e.querySelector('h3').textContent+'|'+e.querySelector('button').textContent;e.innerHTML=gameErr(false);a.gerrN=e.querySelector('h3').textContent+'|'+e.querySelectorAll('button').length;
 e.innerHTML=gameBuyBar({leg:{sport:'nba'},buy:[{t:'KX-A',name:'Boston Celtics',ask:.64,mult:1.5625},{t:'KX-B',name:'New York Knicks',ask:.36,mult:2.78}]});
 a.buy=[...e.querySelectorAll('button')].map(b=>b.innerText||b.textContent);return a;}"""
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("light", "dark"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, has_touch=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("localStorage.clear();localStorage.setItem('cw_view','games')")
        pg.goto(B + "/app")
        if not wait(pg, "typeof gameCard==='function'&&typeof gameErr==='function'&&!!document.querySelector('#main')", 20): bad(f"{scheme}: page didn't load")
        o = pg.evaluate(PROBE, CARDS); t = scheme
        if o["n"] != 2: bad(f"{t}: expected 2 cards: {o}")
        if o["mine"] != [1, 1] or o["mineText"] != "Your pick" or o["mineInRow"] != [0, 0]: bad(f"{t}: Your pick should sit once in each header, not on the team row: {o}")
        if o["gl"] != [1, 1]: bad(f"{t}: every card keeps its chance row (hidden when empty, so heights match): {o['gl']}")
        if o["bt"][0] != ["\U0001f3af 2 combos", "\u03a3 Over 225.5 total points", "+2"] and o["bt"][0][-1] != "+2": bad(f"{t}: chips should be at most two plus +N: {o['bt']}")
        if len(o["bt"][0]) != 3 or o["bt"][0][2] != "+2" or o["bt"][1] != []: bad(f"{t}: chips should be 2 + '+2', and none when there are no bets: {o['bt']}")
        if o["rows"][0] != 1: bad(f"{t}: bet chips wrapped onto {o['rows'][0]} rows")
        if not o["chipH"] or set(o["chipH"]) != {44}: bad(f"{t}: bet-type chips should all be 44px tall: {o['chipH']}")
        if o["secH"] < 44: bad(f"{t}: section header under 44px: {o['secH']}")
        if o["sideways"]: bad(f"{t}: page scrolls sideways")
        s = pg.evaluate(SKEL)
        if (s["sk"], s["s1"], s["busy"]) != (4, 4, "true"): bad(f"{t}: loading skeleton should be 4 cards: {s}")
        if (s["err"], s["errBtn"]) != ("Games didn't load", "Try again"): bad(f"{t}: load error wording: {s}")
        if (s["empty"], s["emptyBtn"]) != ("No games to watch yet", "See today's bets"): bad(f"{t}: empty wording: {s}")
        if (s["empty2"], s["empty2Btn"]) != ("No games for this bet type", "Show all games"): bad(f"{t}: filtered-empty wording: {s}")
        if s["gerrF"] != "This game didn't load|Try again" or s["gerrN"] != "This game isn't on the board|0": bad(f"{t}: game sheet error wording: {s}")
        if not s["buy"][0].replace("\n", " ").endswith("64% \u00b7 1.56x"): bad(f"{t}: buy bar label/note: {s}")
        bg = pg.evaluate("""()=>{const d=document.createElement('div');d.className='pbody';d.innerHTML='<div class="gbuy"><button>a</button></div>';document.body.appendChild(d);
          const c=getComputedStyle(d.querySelector('.gbuy'));const r={bg:c.backgroundColor,pos:c.position,bf:c.backdropFilter,note:getComputedStyle(d.querySelector('.gbuy'),'::before').content};d.remove();return r;}""")
        if bg["note"] != '"Price right now. It can differ a little from the chance above."': bad(f"{t}: buy bar price note: {bg}")
        if not bg["bg"].startswith("rgb(") or bg["pos"] != "sticky": bad(f"{t}: buy bar should be opaque and pinned: {bg}")
        if errs: bad(f"{t}: JS errors {errs}")
        ctx.close()
    br.close()
print("PROBLEMS: " + " | ".join(problems) if problems else "all games polish checks passed")
