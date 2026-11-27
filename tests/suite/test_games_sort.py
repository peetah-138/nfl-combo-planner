# CHECK: group=page secs=8
"""Games tab order (Pete: "sorted by next game"): playing now first, then upcoming by start time (soonest first; a game with no
start time after the timed ones), then finished (most recent first), across leagues, with a stable tie-break (ticker), whatever
order the Mac sent. Phone (390x844) and desktop; the league mix is shuffled on purpose. Display only. Prints PROBLEMS on any failure."""
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

now = time.time()
def G(tk, sport, state="pre", phase="", start=None, **kw):
    g = {"name": tk.split("-")[-1], "opp": "Them", "sport": sport, "ticker": tk, "combos": 1, "pays": 10, "kind": "win", "state": state, "phase": phase,
         "sc": {"me": 1, "opp": 0, "abbr": "A", "opp_abbr": "B", "detail": "Q1"} if state == "live" or phase == "over" else None,
         "chance": .5, "singles": [], "spark": [], "start_ts": start}
    g.update(kw); return g
H = 3600
CARDS = [   # deliberately shuffled: expected order is the EXPECT list
    G("KXNBAGAME-F2-F2", "nba", "over", "over", now - 5 * H),
    G("KXNFLGAME-U3-U3", "nfl", start=now + 30 * H),
    G("KXNHLGAME-NOTIME-B", "nhl", start=None),
    G("KXNBAGAME-L2-L2", "nba", "live", "", now - 2 * H),
    G("KXNHLGAME-U1-U1", "nhl", start=now + 1 * H),
    G("KXNCAAMBGAME-F1-F1", "ncaamb", "over", "over", now - 1 * H),
    G("KXNFLGAME-TIE-B", "nfl", start=now + 2 * H),
    G("KXNFLGAME-L1-L1", "nfl", "live", "", now - 3 * H),
    G("KXNBAGAME-NOTIME-A", "nba", start=None),
    G("KXNFLGAME-TIE-A", "nfl", start=now + 2 * H),
    G("KXNBAGAME-IDLE-I", "nba", "over", "probably_over", now - 9 * H),
]
EXPECT = ["L1-L1", "L2-L2", "U1-U1", "TIE-A", "TIE-B", "U3-U3", "NOTIME-A", "NOTIME-B", "F1-F1", "F2-F2", "IDLE-I"]
def short(tk): return tk.split("-", 1)[1] if tk.count("-") == 1 else tk.split("-", 1)[1]
PROBE = """(cards)=>{S.games={games:cards,fresh:null};S.view='games';render();
  return [...document.querySelectorAll('#main .gc')].map(e=>e.dataset.gk);}"""
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, tag in ((390, 844, "phone"), (1280, 900, "desk")):
        ctx = br.new_context(viewport={"width": vw, "height": vh}, color_scheme="light", has_touch=(tag == "phone"))
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__haps=[];localStorage.clear();localStorage.setItem('cw_view','games')")
        pg.goto(B + "/app")
        if not wait(pg, "typeof gameCard==='function'&&!!document.querySelector('#main')", 20): bad(f"{tag}: the page didn't load")
        time.sleep(1)
        got = [short(k) for k in pg.evaluate(PROBE, CARDS)]
        if got != EXPECT: bad(f"{tag}: wrong order. got {got} wanted {EXPECT}")
        rev = [short(k) for k in pg.evaluate(PROBE, CARDS[::-1])]
        if rev != EXPECT: bad(f"{tag}: order depends on the order the Mac sent: {rev}")
        heads = pg.evaluate("[...document.querySelectorAll('#main h2')].map(h=>h.textContent.replace(/[0-9]+$/,'').trim())")
        if heads != ["Playing now", "Coming up", "Finished", "Probably finished"]: bad(f"{tag}: section headings changed: {heads}")
        if errs: bad(f"{tag}: JS errors {errs}")
        if tag == "phone":
            import pathlib
            out = os.environ.get("GAMES_SORT_SHOT")
            if out:
                pg.screenshot(path=out, full_page=True)
        ctx.close()
    br.close()
print("PROBLEMS: " + " | ".join(problems) if problems else "all games order checks passed")
