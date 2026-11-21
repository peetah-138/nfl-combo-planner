# CHECK: group=page secs=20
"""Faster live numbers (display only): the 'Updated Ns ago' stamps, the freshness block from the web app, and the
game sheet that redraws on its own (score, clock, chance), keeps its scroll place, skips needless redraws, and counts
the clock down between updates. The game answers are scripted; nothing real is touched."""
import sys, os, time, threading, re, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
tk_ev = sorted({m["event_ticker"] for m in mk})
def L(i, team): ev = tk_ev[i]; return {"ticker": f"{ev}-{team}", "event_ticker": ev, "event": ev, "side": "yes"}
bets = [{"ticker": "KXMVE-1", "legs": [L(0, "BOS"), L(1, "DEN")], "cost": 5.0, "pays": 41.2, "status": "pending", "back": 0,
         "week": "2026-11-17", "full_pays": 41.2, "lg": "nba", "lgs": ["nba"]}]
state = {}
def load():
    A = real_load()
    state["A"] = A
    A.fetch_account = lambda max_age=60, every_league=False: (bets, 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    return A
W.load_engine = load
# the fake ESPN answers with NO events (nothing under way) until a test flips `espn["live"]`, then the one bet's game is in progress
espn = {"live": False}
_net = requests.get
def _espn_get(url, params=None, **k):
    if "espn.com" in url and espn["live"]:
        st = {"period": 2, "displayClock": "5:42", "type": {"state": "in", "name": "STATUS_IN_PROGRESS", "shortDetail": "Q2 5:42"}}
        tm = lambda i, n, ab, ha, s: {"id": i, "homeAway": ha, "score": str(s),
                                      "team": {"id": i, "displayName": n, "shortDisplayName": n.split()[-1], "location": n.rsplit(" ", 1)[0], "abbreviation": ab}}
        return R({"events": [{"id": "e1", "date": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "status": st,
                              "competitions": [{"status": st, "competitors": [tm("1", "Boston Celtics", "BOS", "away", 54), tm("2", "New York Knicks", "NYK", "home", 49)]}]}]})
    return _net(url, params=params, **k)
requests.get = _espn_get
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright

TK = "KXNBAGAME-26NOV18BOSNYK-BOS"
def game(me, opp, clock, chance, extra=0):
    return {"leg": {"ticker": TK, "t": TK, "sport": "nba", "state": "live", "phase": "on", "name": "Celtics", "opp": "Knicks", "kind": "win",
                    "chance": chance, "live": chance, "side": "yes",
                    "sc": {"abbr": "BOS", "opp_abbr": "NYK", "me": me, "opp": opp, "detail": clock}},
            "combos": [], "story": {"ticks": [{"ts": time.time() - 60 * i, "chance": chance} for i in range(5)], "plays": []},
            "whatif": None, "fresh": {"now": time.time(), "built": time.time() - 2, "scores": 3, "live": True, "fast": True},
            "pad": "x" * extra}

state.update(g=game(54, 49, "Q2 5:42", .62), calls=0)
def answer(route):
    state["calls"] += 1
    route.fulfill(status=200, content_type="application/json", body=json.dumps(state["g"]))

def until(pg, js, secs=12):
    end = time.time() + secs
    while time.time() < end:
        try:
            if pg.evaluate(js): return True
        except Exception: pass
        time.sleep(.15)
    return False

with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/app")
    ok = until(pg, "!!(S.live&&S.live.fresh)", 25)
    print("live carries a freshness block:", ok)
    if not ok: print("PROBLEMS: no freshness block on /app/api/live")
    f = pg.evaluate("S.live.fresh")
    print("fresh:", {k: (round(v, 1) if isinstance(v, float) else v) for k, v in f.items()})
    if not (f.get("built") and 0 <= f["now"] - f["built"] < 120 and f["now"] > 1e9): print("PROBLEMS: freshness times look wrong")
    if "fast" not in f: print("PROBLEMS: no pace flag")
    # this app's score cache is short (8 s with a game on, 30 s otherwise), not the old 45 s; the watcher's trading copy is untouched
    age = state["A"].SCORES_MAX_AGE
    print("web app score cache seconds:", age)
    if age not in (8, 30): print("PROBLEMS: the web app's score cache is", age)
    # ?fresh=1 builds a new snapshot right now
    b0 = pg.evaluate("api('/app/api/live').then(d=>d.fresh.built)")
    time.sleep(1.2)
    b1 = pg.evaluate("api('/app/api/live?fresh=1').then(d=>d.fresh.built)")
    print("fresh=1 rebuilds:", b1 > b0)
    if not b1 > b0: print("PROBLEMS: fresh=1 didn't build a new snapshot")
    # a build that fails serves the last good copy instead of an error
    real_mine = state["A"].mine_page
    def boom(*a, **k): raise RuntimeError("fake build failure")
    state["A"].mine_page = boom
    r = pg.evaluate("api('/app/api/live?fresh=1').then(d=>({ok:!!d.combos,built:d.fresh.built,err:d.error||null})).catch(e=>({ok:false,err:String(e)}))")
    state["A"].mine_page = real_mine
    print("failed build -> last good copy:", r, "| same snapshot:", abs(r.get("built", 0) - b1) < 1e-6)
    if not r.get("ok") or abs(r.get("built", 0) - b1) > 1e-6: print("PROBLEMS: a failed build wasn't covered by the last good copy")
    b2 = pg.evaluate("api('/app/api/live?fresh=1').then(d=>d.fresh.built)")
    if not b2 > b1: print("PROBLEMS: building didn't recover after a failure")

    # the hero stamp (issue #80), against the server's REAL shape. Case 1: NO game is under way (the fake ESPN has no
    # live event) but a scores cache exists (mine_page refetched it for the leg's sport). That cache age is NOT live
    # scores, so the stamp must be the single "Updated N ago" and must not say "scores".
    pg.evaluate("go('live')")
    ok = until(pg, "!!document.querySelector('.hl [data-fr=L]')&&/^Updated /.test(document.querySelector('.hl [data-fr=L]').textContent)")
    txt = pg.evaluate("(document.querySelector('[data-fr=L]')||{}).textContent")
    f = pg.evaluate("S.live.fresh")
    print("no game under way: fresh live/scores:", f.get("live"), f.get("scores") is not None, "| hero stamp:", repr(txt))
    if f.get("live") is not False: print("PROBLEMS: the server says a game is under way when none is")
    if f.get("scores") is None: print("PROBLEMS: this case needs a scores cache to exist (that is the bug's trigger)")
    if not ok: print("PROBLEMS: with no game under way the hero stamp should be a single 'Updated N ago'")
    if re.search(r"scores", txt or "") or not re.search(r"^Updated ", txt or ""):
        print("PROBLEMS: a cache age was labelled as live scores")
    # Case 2: a game IS under way (the fake ESPN now returns one in progress): the server flags live, and the stamp
    # names the prices age AND the scores age separately, never one conflated "Updated N ago" that hides which is stale.
    espn["live"] = True
    state["A"].SCORES_BY.clear()
    pg.evaluate("load('live',true)")
    ok = until(pg, "!!(S.live&&S.live.fresh&&S.live.fresh.live)", 15)
    print("game under way: server flags live:", ok)
    if not ok: print("PROBLEMS: the server didn't flag a game under way")
    ok = until(pg, "!!document.querySelector('.hl [data-fr=L]')&&/^Prices .* · scores /.test(document.querySelector('.hl [data-fr=L]').textContent)", 8)
    txt = pg.evaluate("(document.querySelector('[data-fr=L]')||{}).textContent")
    print("hero stamp:", repr(txt))
    if not ok: print("PROBLEMS: hero stamp doesn't name prices and scores separately")
    if not (re.search(r"Prices\b", txt or "") and re.search(r"scores\b", txt or "")):
        print("PROBLEMS: the stamp must say both 'Prices' and 'scores'")
    # it counts up on its own between loads (no reload): push the whole snapshot (prices + scores) back 20 s
    pg.evaluate("window.load=async()=>{}")
    pg.evaluate("S.fr.L.recv-=20000")
    ok = until(pg, "/Prices \\d+s ago · scores \\d+s ago/.test(document.querySelector('[data-fr=L]').textContent)", 4)
    print("stamp counts on its own:", ok, repr(pg.evaluate("document.querySelector('[data-fr=L]').textContent")))
    if not ok: print("PROBLEMS: the stamp didn't tick")
    # red staleness keys off the PRICES (snapshot) age, not the scores age: a snapshot older than a minute goes red
    pg.evaluate("S.fr.L.recv-=100000")
    until(pg, "document.querySelector('[data-fr=L]').classList.contains('old')", 3)
    print("old stamp muted:", pg.evaluate("document.querySelector('[data-fr=L]').classList.contains('old')"),
          repr(pg.evaluate("document.querySelector('[data-fr=L]').textContent")))
    if not pg.evaluate("document.querySelector('[data-fr=L]').classList.contains('old')"): print("PROBLEMS: stale stamp not marked")
    if not re.search(r"min ago", pg.evaluate("document.querySelector('[data-fr=L]').textContent")): print("PROBLEMS: minutes wording")
    # the prices age the stamp leads with is the snapshot build age (now-built), not the oldest of build/scores:
    # a fresh snapshot (built just now) with stale scores still reads "Prices <small>" but "scores <big>"
    pg.evaluate("S.fr.L={f:{now:1000,built:999,scores:75,live:true,fast:true},recv:Date.now()}")
    pg.evaluate("frTick()")
    txt = pg.evaluate("document.querySelector('[data-fr=L]').textContent")
    print("fresh prices, stale scores:", repr(txt))
    if not re.search(r"Prices (just now|[12]s ago)", txt): print("PROBLEMS: prices age isn't the snapshot build age")
    if not re.search(r"scores 1 min ago|scores 7[0-9]s ago", txt): print("PROBLEMS: scores age not shown separately")
    if pg.evaluate("document.querySelector('[data-fr=L]').classList.contains('old')"):
        print("PROBLEMS: a fresh snapshot went red just because scores are old")
    # when no game is live (no scores age at all) the stamp falls back to a single honest 'Updated N ago'
    pg.evaluate("S.fr.L={f:{now:1000,built:994,scores:null,live:false,fast:false},recv:Date.now()}")
    pg.evaluate("frTick()")
    txt = pg.evaluate("document.querySelector('[data-fr=L]').textContent")
    print("no live scores stamp:", repr(txt))
    if not re.search(r"Updated \d+s ago", txt) or re.search(r"scores", txt):
        print("PROBLEMS: with no live scores the stamp should be a single 'Updated N ago'")
    # ...and so does a scores CACHE with no game under way (non-null scores age, live false): the old bug
    pg.evaluate("S.fr.L={f:{now:1000,built:994,scores:8,live:false,fast:false},recv:Date.now()}")
    pg.evaluate("frTick()")
    txt = pg.evaluate("document.querySelector('[data-fr=L]').textContent")
    print("scores cache, no game stamp:", repr(txt))
    if not re.search(r"^Updated \d+s ago$", txt) or re.search(r"scores", txt):
        print("PROBLEMS: a scores cache with no game under way must not be labelled 'scores'")
    # a just-refreshed prices half says "just now" like the scores half does
    pg.evaluate("S.fr.L={f:{now:1000,built:999.5,scores:1,live:true,fast:true},recv:Date.now()}")
    pg.evaluate("frTick()")
    txt = pg.evaluate("document.querySelector('[data-fr=L]').textContent")
    print("just now stamp:", repr(txt))
    if txt != "Prices just now · scores just now": print("PROBLEMS: both halves should say 'just now' under a few seconds")

    # the Games tab stamp
    pg.evaluate("S.fr.N={f:{now:1000,built:998,scores:1,live:true,fast:true},recv:Date.now()-5000}")
    pg.evaluate("S.games={games:[{name:'Celtics',opp:'Knicks',sport:'nba',state:'live',phase:'on',chance:.62,ticker:'" + TK + "',combos:1,pays:40,spark:[],sc:{me:54,opp:49,detail:'Q2 5:42',abbr:'BOS',opp_abbr:'NYK'}}],at:1,fresh:{now:1000,built:998,scores:1,live:true,fast:true}}")
    pg.evaluate("go('games')"); time.sleep(.8)
    gtxt = pg.evaluate("(document.querySelector('#main [data-fr=N]')||{}).textContent")
    print("games stamp present:", pg.evaluate("!!document.querySelector('#main [data-fr=N]')"), repr(gtxt))
    if not pg.evaluate("!!document.querySelector('#main [data-fr=N]')"): print("PROBLEMS: no stamp on the Games tab")
    # its TEXT, not just its presence: a game is under way, so both halves, each in "Ns ago" form
    if not re.fullmatch(r"Prices \d+s ago · scores \d+s ago", gtxt or ""): print("PROBLEMS: Games-tab stamp text is wrong:", repr(gtxt))
    pg.evaluate("S.fr.N={f:{now:1000,built:998,scores:1,live:false,fast:true},recv:Date.now()-5000}")
    pg.evaluate("frTick()")
    gtxt = pg.evaluate("(document.querySelector('#main [data-fr=N]')||{}).textContent")
    if not re.fullmatch(r"Updated \d+s ago", gtxt or ""): print("PROBLEMS: Games-tab stamp with no game under way should be 'Updated N ago':", repr(gtxt))
    pg.evaluate("S.fr.N={f:{now:1000,built:998,scores:1,live:true,fast:true},recv:Date.now()-5000}")

    # the game sheet
    pg.route("**/app/api/game*", answer)
    pg.evaluate("go('live')"); time.sleep(.5)
    pg.evaluate(f"openGame('{TK}')")
    ok = until(pg, "!!document.querySelector('#sheet .board2')")
    print("game sheet drawn:", ok)
    if not ok: print("PROBLEMS: game sheet didn't draw")
    sc = lambda: pg.evaluate("[...document.querySelectorAll('#sheet .tm2 b')].map(e=>e.textContent).join('-')")
    print("score:", sc(), "| stamp:", repr(pg.evaluate("(document.querySelector('#sheet [data-fr=G]')||{}).textContent")))
    if sc() != "54-49": print("PROBLEMS: wrong score first")
    if not pg.evaluate("/^Prices .* · scores /.test((document.querySelector('#sheet [data-fr=G]')||{}).textContent||'')"): print("PROBLEMS: no 'Prices ... scores ...' stamp in the game sheet of a live game")

    # an unchanged answer doesn't repaint (the node is the same one), and doesn't lose the scroll place
    pg.evaluate("document.querySelector('#sheet .board2').dataset.keep='1'")
    n0 = state["calls"]
    pg.evaluate("drawGame()"); time.sleep(.6)
    kept = pg.evaluate("document.querySelector('#sheet .board2').dataset.keep==='1'")
    print("unchanged answer: no repaint:", kept, "| asked:", state["calls"] - n0)
    if not kept: print("PROBLEMS: sheet repainted though nothing changed")

    # a new score repaints, scroll position kept
    state["g"] = game(57, 49, "Q2 5:30", .66, extra=0)
    pg.evaluate("document.querySelector('#sheet').style.overflow='auto';document.querySelector('#sheet').style.maxHeight='300px'")
    pg.evaluate("document.querySelector('#sheet').scrollTop=120")
    top0 = pg.evaluate("document.querySelector('#sheet').scrollTop")
    pg.evaluate("drawGame()")
    ok = until(pg, "[...document.querySelectorAll('#sheet .tm2 b')].map(e=>e.textContent).join('-')==='57-49'", 5)
    top1 = pg.evaluate("document.querySelector('#sheet').scrollTop")
    print("new score painted:", ok, "| scroll kept:", top0, "->", top1)
    if not ok: print("PROBLEMS: a new score didn't show")
    if top0 > 0 and abs(top1 - top0) > 2: print("PROBLEMS: scroll place lost on redraw")
    # the chance rolls to its new value (~0.65 s): wait for it rather than reading mid-roll
    if not until(pg, "document.querySelector('#sheet .dkpis').innerText.includes('66%')", 5): print("PROBLEMS: chance line didn't update")

    # the clock counts down between updates once it is seen running
    state["g"] = game(57, 49, "Q2 5:20", .66)
    pg.evaluate("drawGame()")
    until(pg, "!!(S.clk&&S.clk['" + TK + "']&&S.clk['" + TK + "'].run)", 5)
    run = pg.evaluate("(S.clk['" + TK + "']||{}).run")
    print("clock seen running:", run)
    if not run: print("PROBLEMS: running clock not noticed")
    pg.evaluate("S.clk['" + TK + "'].recv-=4000")          # four seconds pass with no new answer
    ok = until(pg, "document.querySelector('#sheet [data-clk]').textContent==='Q2 5:16'", 4)
    print("clock ticks locally:", ok, repr(pg.evaluate("document.querySelector('#sheet [data-clk]').textContent")))
    if not ok: print("PROBLEMS: clock didn't count down by itself")
    # a stopped clock (same time twice) stops ticking
    # (the same time twice in a row is normal while it runs, since ESPN moves it every 15-30 s; only after 25 s
    # of the same time is it called stopped)
    state["g"] = game(57, 49, "Q2 5:20", .66)
    pg.evaluate("S.gameAt=0;drawGame()"); time.sleep(.5)
    print("same time soon after: still running:", pg.evaluate("S.clk['" + TK + "'].run"))
    if not pg.evaluate("S.clk['" + TK + "'].run"): print("PROBLEMS: called a running clock stopped too soon")
    pg.evaluate("S.clk['" + TK + "'].recv-=30000")
    pg.evaluate("S.gameAt=0;drawGame()"); time.sleep(.5)
    pg.evaluate("S.clk['" + TK + "'].recv-=6000")
    time.sleep(1.3)
    txt = pg.evaluate("document.querySelector('#sheet [data-clk]').textContent")
    print("stopped clock holds:", repr(txt))
    if txt != "Q2 5:20": print("PROBLEMS: a stopped clock kept counting")

    # the page's own timers keep it fresh: a tick from the Mac, then the slow timer
    n0 = state["calls"]; state["g"] = game(59, 52, "Q2 5:00", .70)
    pg.evaluate("S.gameAt=Date.now()-6000")
    ok = until(pg, "[...document.querySelectorAll('#sheet .tm2 b')].map(e=>e.textContent).join('-')==='59-52'", 6)
    print("self-refresh (timer):", ok, "| calls:", state["calls"] - n0)
    if not ok: print("PROBLEMS: the open sheet didn't refresh itself")
    # not hammering: right after a draw nothing new is asked
    n1 = state["calls"]; time.sleep(2.2)
    print("quiet right after a draw:", state["calls"] - n1)
    if state["calls"] - n1 > 1: print("PROBLEMS: the sheet asks too often")

    # not found keeps what is shown; another sheet taking over is left alone
    pg.evaluate("S.gameSig=null")
    pg.evaluate("modal('<h3 id=other>Other sheet</h3>')"); time.sleep(.2)
    n1 = state["calls"]; pg.evaluate("S.gameAt=0;drawGame()"); time.sleep(.6)
    print("another sheet left alone:", pg.evaluate("!!document.querySelector('#other')"), "| gameOpen cleared:", pg.evaluate("S.gameOpen===null"))
    if not pg.evaluate("!!document.querySelector('#other')"): print("PROBLEMS: the game redraw clobbered another sheet")
    pg.evaluate("closeModal()")
    if pg.evaluate("S.gameSig!==null"): print("PROBLEMS: close didn't reset")

    # phone: no sideways scroll, screenshots
    pg.evaluate("S.gameOpen=null"); pg.evaluate(f"openGame('{TK}')"); until(pg, "!!document.querySelector('#sheet .board2')")
    time.sleep(.6); pg.screenshot(path="livefresh_game.png")
    pg.evaluate("closeModal()"); pg.evaluate("go('live')"); time.sleep(.8); pg.screenshot(path="livefresh_live.png")
    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): print("PROBLEMS: page scrolls sideways")
    print("errs:", errs)
    if errs: print("PROBLEMS: JS errors")
    br.close()
