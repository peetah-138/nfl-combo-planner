"""Games tab card (GitHub #95): every card shows BOTH teams and BOTH scores, your side marked YOURS. A college-basketball
card whose full opponent name is empty falls back to the short code on the score (sc.opp_abbr); with neither it still shows
the opponent's score under a neutral "Opponent" label; a card with no opponent score (tennis/UFC on Kalshi's live data)
shows no opponent number at all, never a fake 0 (a real 0 still shows); text is escaped; the score pulse and the chance line
still work. Phone (390x844, touch) and desktop. Prints PROBLEMS on any failure."""
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
threading.Thread(target=W.webapp_main, daemon=True).start(); time.sleep(3)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        if pg.evaluate(js): return True
        time.sleep(.2)
    return False

def G(tk, name, opp, sc, **kw):
    g = {"name": name, "opp": opp, "sport": "ncaamb", "ticker": tk, "combos": 1, "pays": 12.5, "kind": "win", "state": "live", "phase": "",
         "sc": sc, "chance": .56, "singles": [], "spark": [[time.time() - 600 + i * 60, .5 + .01 * i] for i in range(8)]}
    g.update(kw); return g
CARDS = [
    # college basketball: the full opponent name arrives empty, the score carries the short code
    G("KXNCAAMBGAME-26NOV19SCUHOU-SCU", "Santa Clara", "", {"me": 71, "opp": 68, "abbr": "SCU", "opp_abbr": "HOU", "detail": "H2 0:51"}),
    # neither a name nor a code: still show their score, under a neutral label
    G("KXNCAAMBGAME-26NOV19AAABBB-AAA", "Houston", "", {"me": 62, "opp": 40, "abbr": "AAA", "opp_abbr": "", "detail": "H2 8:00"}),
    # the full name wins over the short code; a real 0 is a real score
    G("KXNHLGAME-26NOV19SJSVGK-SJS", "San Jose", "Vegas Golden Knights", {"me": 0, "opp": 0, "abbr": "SJS", "opp_abbr": "VGK", "detail": "1st 12:00"}, sport="nhl"),
    # tennis on Kalshi's live data with no opponent score: a name, but no number and no fake 0
    G("KXATPMATCH-26NOV19DJOALC-DJO", "Djokovic", "", {"me": 1, "opp": None, "abbr": "DJO", "opp_abbr": "ALC", "detail": "Set 2 of 3"}, sport="tennis"),
    # a fight: no score object at all and no opponent: no opponent row, no numbers
    G("KXUFCFIGHT-26NOV19AAABBB-AAA", "Alex Fighter", "", None, sport="ufc"),
    # not started yet: the opponent's name shows, no scores
    G("KXNBAGAME-26NOV19BOSNYK-BOS", "Boston Celtics", "New York Knicks", None, sport="nba", state="pre", starts="Tonight 7:30 PM", short="Tonight 7:30 PM"),
    # text from outside is escaped
    G("KXNCAAMBGAME-26NOV19XSS-XSS", "Evil <b>Team</b>", "<img src=x onerror=window.__xss=1>", {"me": 5, "opp": 4, "abbr": "XSS", "opp_abbr": "<i>Z</i>", "detail": "H1 5:00"}),
]
PROBE = """(cards)=>{S.games={games:cards,fresh:null};S.view='games';render();
  return [...document.querySelectorAll('#main .gc')].map(e=>({gk:e.dataset.gk,me:e.querySelector('.gtr.me .nm')&&e.querySelector('.gtr.me .nm').textContent,
   mine:!!e.querySelector('.gtr.me .mine'),myPts:(e.querySelector('.gtr.me .pts')||{}).textContent,them:e.querySelector('.gtr.them .nm')&&e.querySelector('.gtr.them .nm').textContent,
   oppPts:(e.querySelector('.gtr.them .pts')||{}).textContent,nPts:e.querySelectorAll('.pts').length,chance:!!e.querySelector('.gl .ch b'),line:!!e.querySelector('.mline .sdot'),
   chips:e.querySelectorAll('.bets .bt').length,html:e.innerHTML}));}"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, tag in ((390, 844, "phone"), (1280, 900, "desk")):
        ctx = br.new_context(viewport={"width": vw, "height": vh}, color_scheme="dark", has_touch=(tag == "phone"))
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__haps=[];localStorage.clear();localStorage.setItem('cw_view','games')")
        pg.goto(B + "/app")
        if not wait(pg, "typeof gameCard==='function'&&!!document.querySelector('#main')", 20): bad(f"{tag}: the page didn't load")
        time.sleep(1)
        out = pg.evaluate(PROBE, CARDS)
        by = {c["gk"]: c for c in out}
        if len(out) != len(CARDS): bad(f"{tag}: expected {len(CARDS)} cards, drew {len(out)}")
        g = lambda i: by.get(CARDS[i]["ticker"]) or {}
        c = g(0)    # college basketball, empty opponent name
        if (c.get("me"), c.get("them"), c.get("myPts"), c.get("oppPts")) != ("Santa Clara", "HOU", "71", "68") or not c.get("mine"):
            bad(f"{tag}: the CBB card should show Santa Clara YOURS 71 and HOU 68: {c}")
        c = g(1)    # no name, no code
        if (c.get("them"), c.get("myPts"), c.get("oppPts")) != ("Opponent", "62", "40"): bad(f"{tag}: with no opponent name the row should say Opponent and keep the score: {c}")
        c = g(2)    # full name beats the code, 0-0 shows both zeros
        if (c.get("them"), c.get("myPts"), c.get("oppPts")) != ("Vegas Golden Knights", "0", "0"): bad(f"{tag}: the full name should win and a real 0 should show: {c}")
        c = g(3)    # tennis, no opponent score
        if c.get("them") != "ALC" or c.get("oppPts") not in (None, "") or c.get("nPts") != 1: bad(f"{tag}: a card with no opponent score should show their name and no number: {c}")
        c = g(4)    # a fight, nothing known
        if c.get("them") is not None or c.get("nPts") != 0: bad(f"{tag}: a card with no score and no opponent should show no opponent row or numbers: {c}")
        c = g(5)    # pre-game
        if c.get("them") != "New York Knicks" or c.get("nPts") != 0: bad(f"{tag}: a game not started should show the opponent's name and no scores: {c}")
        c = g(6)    # escaping
        if "<img" in c.get("html", "") or "<b>Team" in c.get("html", "") or pg.evaluate("!!window.__xss"): bad(f"{tag}: opponent text wasn't escaped")
        for i in (0, 1, 2, 3):
            c = g(i)
            if not (c.get("chance") and c.get("line") and c.get("chips")): bad(f"{tag}: card {i} lost its chance, chance line (end dot) or chips: {c}")
        # the score pulse: their score goes up, the card pulses red, and both rows are still there
        pg.evaluate("(()=>{S.games.games[0].sc=Object.assign({},S.games.games[0].sc,{opp:70});render();})()"); time.sleep(.15)
        pl = pg.evaluate("(()=>{const e=document.querySelector('.gc.scored');return e?{cls:e.className,them:(e.querySelector('.gtr.them .nm')||{}).textContent,pts:(e.querySelector('.gtr.them .pts')||{}).textContent}:null})()")
        if not pl or "bad" not in pl["cls"] or pl["pts"] != "70" or pl["them"] != "HOU": bad(f"{tag}: the score pulse broke: {pl}")
        if tag == "phone" and pg.evaluate("document.documentElement.scrollWidth>document.documentElement.clientWidth+1"): bad("phone: the page scrolls sideways")
        print(f"{tag}: cards={len(out)} JS errors: {errs}")
        if errs: bad(f"{tag}: JS errors {errs}")
        ctx.close()
    br.close()
print("PROBLEMS: " + " | ".join(problems) if problems else "all game card opponent checks passed")
