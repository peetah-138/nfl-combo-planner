# CHECK: group=page secs=39
"""Slice 2 of the live game page (issue #72): the game-page TAB framework and the PLAY-BY-PLAY tab on the pushed game page.
Display only. The game answer (with its ESPN-derived `detail.pbp` block, in the exact shape the engine's _parse_pbp makes) is
scripted; nothing real is touched. Covers: the tab row and sliding underline, tab switching, the selection (and a stepped
play) surviving the page's redraws, prev/next stepping moving the strip's ball, Back to live, quarter and drive collapse,
scoring/turnover tint, the tab hidden when drives are absent (and no tabs for other sports), the per-play illustrations,
reduced motion (text and ball spot still update, nothing animates), feed text/colour safety, no JS errors, and no sideways
scroll on the phone (390x844) and desktop. Writes phone and desktop screenshots of the tab when PBP_SHOTS_DIR is set."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
bets = []


def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: (bets, 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    return A


W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright

TK = "KXNFLGAME-26NOV20INDHOU-IND"
SHOTS = os.environ.get("PBP_SHOTS_DIR")
def pct(side, ytz):                       # the ball's left %, in % of the grass box = yards from the left goal line (home attacks left, away right)
    return ytz if side == "home" else 100 - ytz


def P(id, q, clk, dn, txt, ty, a, as_, b, bs, sc=False, to=False, pen=False, ep="", edd="", ed=None, yd=0):
    return {"id": id, "q": q, "clk": clk, "dn": dn, "txt": txt, "ty": ty, "yd": yd, "a": a, "as": as_, "b": b, "bs": bs,
            "ep": ep, "edd": edd, "ed": ed, "sc": sc, "to": to, "pen": pen}


def drives(odd_text="J.Taylor left end to IND 31 for 4 yards."):
    d1 = {"id": "d1", "team": "IND", "side": "away", "q": 1, "res": "Touchdown", "sum": "4 plays, 75 yards", "sc": True, "to": False, "cur": False, "plays": [
        P("p1", 1, "15:00", "", "K.Fairbairn kicks 65 yards from HST 35 to IND 0. S.McGowan to IND 25.", "Kickoff", 65, "home", 75, "away", ep="IND 25", edd="1st & 10 at IND 25", ed=10, yd=25),
        P("p2", 1, "14:32", "1st & 10", "D.Jones pass short middle to A.Dulin to IND 40 for 15 yards.", "Pass Reception", 75, "away", 60, "away", ep="IND 40", edd="1st & 10 at IND 40", ed=10, yd=15),
        P("p3", 1, "14:02", "1st & 10", "J.Taylor up the middle to HST 45 for 15 yards.", "Rush", 60, "away", 45, "away", ep="HOU 45", edd="1st & 10 at HOU 45", ed=10, yd=15),
        P("p4", 1, "13:40", "1st & 10", "D.Jones pass deep right to A.Pittman for 45 yards, TOUCHDOWN.", "Passing Touchdown", 45, "away", 0, "away", sc=True, yd=45)]}
    d2 = {"id": "d2", "team": "HOU", "side": "home", "q": 1, "res": "Interception", "sum": "3 plays, 17 yards", "sc": False, "to": True, "cur": False, "plays": [
        P("p5", 1, "12:51", "1st & 10", "C.Stroud sacked at HST 17 for -8 yards (J.Clowney).", "Sack", 75, "home", 83, "home", ep="HOU 17", edd="2nd & 18 at HOU 17", ed=18, yd=-8),
        P("p6", 1, "12:40", "", "Official Timeout at 12:40.", "Official Timeout", None, None, None, None),
        P("p7", 1, "12:30", "3rd & 3", "C.Stroud pass deep right intended for N.Collins INTERCEPTED by A.Haulcy at IND 25.", "Pass Interception Return", 50, "home", 73, "away", to=True, ep="IND 27", edd="1st & 10 at IND 27", ed=10, yd=2)]}
    d3 = {"id": "d3", "team": "IND", "side": "away", "q": 2, "res": "Field Goal", "sum": "2 plays, 20 yards", "sc": True, "to": False, "cur": False, "plays": [
        P("p8", 2, "9:00", "3rd & 8", "PENALTY on HST-A.Ersery, Offside, 5 yards.", "Penalty", 40, "away", 35, "away", pen=True, ep="HOU 35", edd="3rd & 3 at HOU 35", ed=3, yd=5),
        P("p9", 2, "8:40", "4th & 3", "S.Shrader 52 yard field goal is GOOD.", "Field Goal Good", 35, "away", 0, "away", sc=True, yd=52)]}
    d4 = {"id": "d4", "team": "HOU", "side": "home", "q": 2, "res": "Punt", "sum": "1 play, 0 yards", "sc": False, "to": False, "cur": False, "plays": [
        P("p10", 2, "8:20", "4th & 11", "R.Sanchez punts 47 yards to IND 22, fair catch.", "Punt", 60, "home", 78, "away", ep="IND 22", edd="1st & 10 at IND 22", ed=10, yd=47)]}
    d5 = {"id": "d5", "team": "IND", "side": "away", "q": 2, "res": "", "sum": "1 play, 4 yards", "sc": False, "to": False, "cur": True, "plays": [
        P("p11", 2, "6:50", "1st & 10", odd_text, "Rush", 73, "away", 69, "away", ep="IND 31", edd="2nd & 6 at IND 31", ed=6, yd=4)]}
    return [d1, d2, d3, d4, d5]


def game(pbp, sport="nfl", chance=.24, home_color="#03202f", detail=True):
    g = {"leg": {"ticker": TK, "t": TK, "sport": sport, "state": "live", "phase": "on", "on": True,
                 "name": "Colts", "opp": "Texans", "kind": "win", "chance": chance, "live": chance, "side": "yes",
                 "sc": {"abbr": "IND", "opp_abbr": "HOU", "me": 3, "opp": 0, "detail": "Q2 6:50"}},
         "combos": [], "story": {"ticks": [{"ts": time.time() - 60 * i, "chance": chance} for i in range(4)], "plays": []},
         "whatif": None, "fresh": {"now": time.time(), "built": time.time() - 2, "scores": 3, "fast": True}}
    if detail:
        g["detail"] = {
            "situation": {"down": 2, "distance": 6, "yardLine": 31, "isRedZone": False, "homeTimeouts": 3, "awayTimeouts": 2, "myTimeouts": 2,
                          "theirTimeouts": 3, "possession": True, "downDistanceText": "2nd & 6 at IND 31", "possessionText": "IND 31",
                          "lastPlayText": "J.Taylor left end to IND 31 for 4 yards.", "lastPlayType": "Rush"},
            "board": {"home": {"abbr": "HOU", "name": "Houston Texans", "color": home_color, "alt": "#a71930", "score": 0, "record": "7-3", "homeAway": "home"},
                      "away": {"abbr": "IND", "name": "Indianapolis Colts", "color": "#002c5f", "alt": "#a2aaad", "score": 3, "record": "3-7", "homeAway": "away"},
                      "period": 2, "displayClock": "6:50", "state": "in", "completed": False, "broadcast": "CBS"},
            "drive": {"teamId": "11", "teamAbbr": "IND", "ballYardsToEndzone": 69, "downDistanceText": "2nd & 6 at IND 31"}}
        if pbp is not None:
            g["detail"]["pbp"] = pbp
    return g


def full():
    return {"drives": drives(), "n": 11, "cut": 0}


state = {"g": game(full())}


def answer(route):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(state["g"]))


def until(pg, js, secs=12):
    end = time.time() + secs
    while time.time() < end:
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        time.sleep(.12)
    return False


def open_game(pg, label, probs):
    pg.route("**/app/api/game*", answer)
    pg.goto(B + "/app"); time.sleep(.6)
    pg.evaluate(f"openGame('{TK}')")
    if not until(pg, "!!document.querySelector('#sheet .board2')"):
        probs.append(label + ": game sheet didn't draw"); return False
    return True


BALL = "(parseFloat((document.querySelector('#sheet .fstrip .fball')||{style:{}}).style.left)||-1)"
CARD_TEXT = "(document.querySelector('#sheet #pbp-card .pctx')||{}).textContent||''"


def ball_ok(pg, want):
    return abs(pg.evaluate(BALL) - want) < .15


def redraw(pg, chance):
    """Force a repaint of the game sheet by changing the answer, and prove it really repainted (a new panel element)."""
    pg.evaluate("window.__mark=document.querySelector('#sheet .board2')")
    state["g"] = game(state["g"]["detail"].get("pbp") if state["g"].get("detail") else None, chance=chance) if state["g"].get("detail") else state["g"]
    pg.evaluate("S.gameSig=null;drawGame()")
    return until(pg, "document.querySelector('#sheet .board2')&&document.querySelector('#sheet .board2')!==window.__mark", 8)


def run(pg, label, phone, shots=None):
    probs = []
    state["g"] = game(full())
    if not open_game(pg, label, probs):
        return probs
    # ---- the tab row: Overview and Play-by-play only (no empty placeholder tabs), overview selected, scrolling row with an underline
    if not until(pg, "document.querySelectorAll('#sheet .gtab').length>0"):
        probs.append(label + ": no tab row on a football game with drives"); return probs
    names = pg.evaluate("[...document.querySelectorAll('#sheet .gtab')].map(b=>b.textContent.trim())")
    if names != ["Overview", "Play-by-play"]:
        probs.append(label + ": wrong tabs " + repr(names))
    if not pg.evaluate("document.querySelector('#sheet .gtab.on').dataset.tab==='overview'"):
        probs.append(label + ": overview isn't selected first")
    ox = pg.evaluate("getComputedStyle(document.querySelector('#sheet .gtabs')).overflowX")
    if ox not in ("auto", "scroll"):
        probs.append(label + ": the tab row doesn't scroll sideways (overflow-x=" + ox + ")")
    if not pg.evaluate("document.querySelector('#sheet .gtabs>.gtabind')!==null"):
        probs.append(label + ": no sliding indicator inside the scrolling row")
    # the field strip stays above the tabs, and the overview keeps its old content (chance chart, your bets)
    if not pg.evaluate("!!document.querySelector('#sheet .fstrip .fld')&&document.querySelector('#sheet .fstrip').compareDocumentPosition(document.querySelector('#sheet .gtabs'))&4"):
        probs.append(label + ": field strip missing or not above the tabs")
    if not pg.evaluate("!!document.querySelector('#sheet .gpanel[data-tab=overview] .chartbox')&&!!document.querySelector('#sheet .gpanel[data-tab=overview] .dkpis')&&document.querySelector('#sheet .gpanel[data-tab=overview]').textContent.includes('Your bets on this game')"):
        probs.append(label + ": the overview lost its chart/bets")
    if not pg.evaluate("document.querySelector('#sheet .gpanel[data-tab=pbp]').hidden"):
        probs.append(label + ": the play-by-play panel shows before it is chosen")
    live_ball = pct("away", 69)
    if not ball_ok(pg, live_ball):
        probs.append(label + ": live ball isn't at the live spot: %s vs %.2f" % (pg.evaluate(BALL), live_ball))

    # ---- switch to play-by-play: panel shows, overview hides, underline slides under it
    pg.click("#sheet .gtab[data-tab=pbp]"); time.sleep(.5)
    if not pg.evaluate("document.querySelector('#sheet .gtab.on').dataset.tab==='pbp'&&!document.querySelector('#sheet .gpanel[data-tab=pbp]').hidden&&document.querySelector('#sheet .gpanel[data-tab=overview]').hidden"):
        probs.append(label + ": switching to play-by-play didn't swap the panels")
    ind = pg.evaluate("(()=>{const b=document.querySelector('#sheet .gtab.on'),i=document.querySelector('#sheet .gtabind');return [b.offsetLeft,b.offsetWidth,parseFloat(i.style.left),parseFloat(i.style.width)];})()")
    if abs(ind[0] - ind[2]) > 1.5 or abs(ind[1] - ind[3]) > 1.5:
        probs.append(label + ": the underline isn't under the chosen tab " + repr(ind))
    if "Illustrations only, no player tracking" not in pg.evaluate("document.querySelector('#sheet .pbp').innerText"):
        probs.append(label + ": the honest illustration label is missing")
    # latest play card shows the newest play, live
    if "left end" not in pg.evaluate(CARD_TEXT):
        probs.append(label + ": the card isn't the latest play: " + pg.evaluate(CARD_TEXT))
    if not pg.evaluate("document.querySelector('#sheet .plive').hidden") or not pg.evaluate("document.querySelector('#sheet [data-step=next]').disabled"):
        probs.append(label + ": live card should hide Back to live and disable next")
    if "Latest play" not in pg.evaluate("document.querySelector('#sheet #pbp-card .pcs').textContent"):
        probs.append(label + ": card doesn't say Latest play")
    # quarters newest first, drives, plays
    qs = pg.evaluate("[...document.querySelectorAll('#sheet .pq span')].map(e=>e.textContent)")
    if qs != ["2nd Quarter", "1st Quarter"]:
        probs.append(label + ": quarter sections wrong: " + repr(qs))
    dr = pg.evaluate("[...document.querySelectorAll('#sheet .pdr')].map(e=>e.innerText.replace(/\\s+/g,' ').trim())")
    if not any("IND" in x and "1 play, 4 yards" in x for x in dr):
        probs.append(label + ": the current drive header (offence, N plays, M yards) is wrong: " + repr(dr))

    # ---- selection survives a redraw, and the underline does not re-animate on a same-tab redraw: the row is rebuilt, so sample
    #      the COMPUTED left/width on every frame (the inline style alone looks right even while the box glides in from 0)
    pg.evaluate("""(()=>{window.__ls=[];let n=0;const tick=()=>{const i=document.querySelector('#sheet .gtabind');
      if(i){const c=getComputedStyle(i);window.__ls.push([parseFloat(c.left),parseFloat(c.width)]);}if(n++<40)requestAnimationFrame(tick);};requestAnimationFrame(tick);})()""")
    if not redraw(pg, .31):
        probs.append(label + ": the page didn't repaint on a new answer")
    time.sleep(.9)
    want = pg.evaluate("(()=>{const b=document.querySelector('#sheet .gtab.on');return [b.offsetLeft,b.offsetWidth];})()")
    ls = pg.evaluate("window.__ls")
    if want[0] < 20 or len(ls) < 10 or any(abs(l - want[0]) > .6 or abs(w - want[1]) > .6 for l, w in ls):
        probs.append(label + ": the tab underline moved on a same-tab redraw (computed left/width per frame vs %r): %r" % (want, [x for x in ls if abs(x[0] - want[0]) > .6 or abs(x[1] - want[1]) > .6][:6]))
    if not pg.evaluate("document.querySelector('#sheet .gtab.on').dataset.tab==='pbp'&&!document.querySelector('#sheet .gpanel[data-tab=pbp]').hidden"):
        probs.append(label + ": the chosen tab was lost on a redraw")

    # ---- stepping: prev moves the card and the strip's ball
    pg.click("#sheet [data-step=prev]"); time.sleep(.2)      # the punt (p10): ball ends at IND 22 (ytz 78, IND's end zone)
    if "punts 47" not in pg.evaluate(CARD_TEXT):
        probs.append(label + ": prev didn't step to the punt: " + pg.evaluate(CARD_TEXT))
    time.sleep(.9)
    if not ball_ok(pg, pct("away", 78)):
        probs.append(label + ": stepping to the punt didn't move the ball to its end spot: %s vs %.2f" % (pg.evaluate(BALL), pct("away", 78)))
    if pg.evaluate("document.querySelector('#sheet .plive').hidden") or "Replay" not in pg.evaluate("document.querySelector('#sheet #pbp-card .pcs').textContent"):
        probs.append(label + ": stepping should show Back to live and a Replay label")
    if not pg.evaluate("!!document.querySelector('#sheet .fstrip .situ .rpl')"):
        probs.append(label + ": the strip doesn't mark itself as a replay")
    # the stepped state survives a redraw (the user isn't yanked back to live)
    if not redraw(pg, .33):
        probs.append(label + ": no repaint while stepped")
    if "punts 47" not in pg.evaluate(CARD_TEXT) or not ball_ok(pg, pct("away", 78)):
        probs.append(label + ": a redraw yanked the stepped play back to live")
    pg.click("#sheet [data-step=prev]"); time.sleep(.2)       # the field goal (p9): ball in the right end zone? IND attacks right: ytz 0 -> far right goal line
    if "field goal is GOOD" not in pg.evaluate(CARD_TEXT) or not ball_ok(pg, pct("away", 0)):
        probs.append(label + ": FG step wrong: " + pg.evaluate(CARD_TEXT)[:40] + " ball " + str(pg.evaluate(BALL)))
    pg.click("#sheet [data-step=prev]"); time.sleep(.2)       # the penalty (p8)
    pg.click("#sheet [data-step=prev]"); time.sleep(.2)       # the interception (p7): turnover flips the end zone: ball at IND 27 (HOU's side of ball: away ytz 73)
    if "INTERCEPTED" not in pg.evaluate(CARD_TEXT) or not ball_ok(pg, pct("away", 73)):
        probs.append(label + ": INT step wrong: " + pg.evaluate(CARD_TEXT)[:40] + " ball " + str(pg.evaluate(BALL)))
    if not pg.evaluate("document.querySelector('#sheet #pbp-card').classList.contains('to')"):
        probs.append(label + ": the turnover card isn't tinted")
    pg.click("#sheet [data-step=prev]"); time.sleep(.2)       # the timeout (p6): no ball movement, keeps the sack's spot (HOU ytz 83)
    if "Timeout" not in pg.evaluate(CARD_TEXT) or not ball_ok(pg, pct("home", 83)):
        probs.append(label + ": the timeout moved the ball or wasn't shown: " + str(pg.evaluate(BALL)))
    # click a play row to jump to it (the touchdown), then step to the very first play and check prev disables
    pg.evaluate("document.querySelector('#sheet .pq[data-k=q1]').getAttribute('aria-expanded')==='true'||document.querySelector('#sheet .pq[data-k=q1]').click()")
    until(pg, "!!document.querySelector('#sheet .pdr[data-k=dd1]')", 3)
    for _ in range(12):
        if pg.evaluate("document.querySelector('#sheet [data-step=prev]').disabled"):
            break
        pg.click("#sheet [data-step=prev]"); time.sleep(.08)
    if "kicks 65" not in pg.evaluate(CARD_TEXT) or not pg.evaluate("document.querySelector('#sheet [data-step=prev]').disabled"):
        probs.append(label + ": stepping back didn't reach the first play with prev disabled")
    # next walks forward; reaching the newest play is live again
    for _ in range(12):
        if pg.evaluate("document.querySelector('#sheet [data-step=next]').disabled"):
            break
        pg.click("#sheet [data-step=next]"); time.sleep(.08)
    if not pg.evaluate("document.querySelector('#sheet .plive').hidden") or "left end" not in pg.evaluate(CARD_TEXT):
        probs.append(label + ": stepping forward to the newest play should be live again")
    time.sleep(.9)
    if not ball_ok(pg, live_ball):
        probs.append(label + ": the live ball spot wasn't restored")
    # Back to live from a stepped play
    pg.click("#sheet [data-step=prev]"); pg.click("#sheet [data-step=prev]"); time.sleep(.2)
    pg.click("#sheet .plive"); time.sleep(.9)
    if "left end" not in pg.evaluate(CARD_TEXT) or not ball_ok(pg, live_ball) or not pg.evaluate("document.querySelector('#sheet .plive').hidden"):
        probs.append(label + ": Back to live didn't return to the newest play and spot")
    # a row click steps to that play (the field goal), highlighted
    pg.evaluate("document.querySelector('#sheet .pq[data-k=q2]').getAttribute('aria-expanded')==='true'||document.querySelector('#sheet .pq[data-k=q2]').click()")
    pg.evaluate("(()=>{const d=document.querySelector('#sheet .pdr[data-k=dd3]');if(d&&d.getAttribute('aria-expanded')!=='true')d.click();})()")
    pg.evaluate("pbpGo('p9')"); time.sleep(.2)
    if "field goal is GOOD" not in pg.evaluate(CARD_TEXT) or pg.evaluate("document.querySelectorAll('#sheet .pp.cur').length")!=1:
        probs.append(label + ": jumping to a play from the list didn't work")
    # leaving the tab puts the strip back to live
    pg.click("#sheet .gtab[data-tab=overview]"); time.sleep(.9)
    if not ball_ok(pg, live_ball) or pg.evaluate("!!document.querySelector('#sheet .fstrip .rpl')"):
        probs.append(label + ": leaving play-by-play left the strip in replay")
    pg.click("#sheet .gtab[data-tab=pbp]"); time.sleep(.3)

    # ---- collapse: a quarter hides its drives; a drive hides its plays
    pg.evaluate("document.querySelectorAll('#sheet .pq[aria-expanded=false]').forEach(b=>b.click())")
    pg.evaluate("document.querySelectorAll('#sheet .pdr[aria-expanded=false]').forEach(b=>b.click())")
    nplays = pg.evaluate("document.querySelectorAll('#sheet .pp').length")
    if nplays != 11:
        probs.append(label + ": with everything open expected 11 plays, saw %d" % nplays)
    pg.evaluate("document.querySelector('#sheet .pdr[data-k=dd1]').click()")
    if pg.evaluate("document.querySelectorAll('#sheet .pp').length") != 7 or pg.evaluate("document.querySelector('#sheet .pdr[data-k=dd1]').getAttribute('aria-expanded')") != "false":
        probs.append(label + ": collapsing a drive didn't hide just its plays")
    pg.evaluate("document.querySelector('#sheet .pq[data-k=q2]').click()")
    if pg.evaluate("document.querySelectorAll('#sheet .pdr').length") != 2:
        probs.append(label + ": collapsing a quarter didn't hide its drives (%s left)" % pg.evaluate("document.querySelectorAll('#sheet .pdr').length"))
    # the collapse choice survives a redraw
    if not redraw(pg, .35) or pg.evaluate("document.querySelectorAll('#sheet .pdr').length") != 2:
        probs.append(label + ": a quarter collapse didn't survive a redraw")
    pg.evaluate("document.querySelector('#sheet .pq[data-k=q2]').click()")
    pg.evaluate("document.querySelectorAll('#sheet .pdr[aria-expanded=false]').forEach(b=>b.click())")

    # ---- tint: scoring and turnover plays differ from a plain play
    bgs = pg.evaluate("""(()=>{const c=s=>{const e=document.querySelector(s);return e?getComputedStyle(e).backgroundColor:null;};
      return {sc:c('#sheet .pp.sc'),to:c('#sheet .pp.to'),plain:c('#sheet .pp:not(.sc):not(.to)'),nsc:document.querySelectorAll('#sheet .pp.sc').length,nto:document.querySelectorAll('#sheet .pp.to').length};})()""")
    if bgs["nsc"] != 2 or bgs["nto"] != 1:
        probs.append(label + ": scoring/turnover rows wrong: " + repr(bgs))
    if bgs["sc"] in (None, bgs["plain"]) or bgs["to"] in (None, bgs["plain"]) or bgs["sc"] == bgs["to"]:
        probs.append(label + ": scoring/turnover plays aren't tinted differently: " + repr(bgs))
    if not pg.evaluate("document.querySelector('#sheet .pdr.sc')&&document.querySelector('#sheet .pdr.to')"):
        probs.append(label + ": scoring/turnover drives aren't flagged")

    # ---- safety: feed text is escaped, and a hostile colour can't reach a style attribute
    if pg.evaluate("document.querySelectorAll('#sheet .ppt b, #sheet .ppt img, #sheet .pct b').length") != 0:
        probs.append(label + ": feed text produced elements (not escaped)")

    # ---- no sideways scroll with the tab fully open
    sw = pg.evaluate("[document.documentElement.scrollWidth-innerWidth,document.querySelector('#sheet').scrollWidth-document.querySelector('#sheet').clientWidth]")
    if max(sw) > 1:
        probs.append(label + ": sideways scroll (page/sheet overflow %s)" % sw)
    geo = pg.evaluate("""(()=>{const f=document.querySelector('#sheet .fld').getBoundingClientRect(),b=document.querySelector('#sheet .fstrip .fball'),g=document.querySelector('#sheet .grass').getBoundingClientRect();
      const r=b?b.getBoundingClientRect():null;const fifty=[...document.querySelectorAll('#sheet .ruler span')].find(e=>e.textContent==='50').getBoundingClientRect();
      return {fld:[f.left,f.width],grass:[g.left,g.width],ball:r&&(r.left+r.width/2),fifty:fifty.left+fifty.width/2,left:b&&b.style.left};})()""")
    # the ball (and the other things in the grass) line up with the yard ruler: at 31 yards the ball sits under the ruler's 30-40 gap, and the 50 is the strip's middle
    if geo["ball"] is None or abs(geo["fifty"] - (geo["fld"][0] + geo["fld"][1] / 2)) > 1.5:
        probs.append(label + ": the ruler's 50 isn't at the middle of the field: %r" % geo)
    ez = geo["fld"][1] / 12
    live_x = geo["fld"][0] + ez + (geo["fld"][1] - 2 * ez) * 31 / 100
    if geo["ball"] is None or abs(geo["ball"] - live_x) > 2:
        probs.append(label + ": the ball isn't over the right yard line (31 yards from the left goal): %.1f vs %.1f" % (geo["ball"] or -1, live_x))
    if shots and SHOTS:
        pg.evaluate("document.querySelector('#sheet').scrollTop=0")
        # step once so the screenshot shows a replay with the ball moved
        pg.evaluate("pbpGo('p7')"); time.sleep(1.2)
        pg.evaluate("document.querySelector('#sheet').scrollTop=document.querySelector('#sheet .fstrip').offsetTop-70"); time.sleep(.3)
        pg.screenshot(path=os.path.join(SHOTS, shots))
    pg.evaluate("closeModal()")
    return probs


def run_fx(pg, label):
    """The per-play illustrations (motion on): each play type adds its own effect to the strip, right when it is stepped to."""
    probs = []
    state["g"] = game(full())
    if not open_game(pg, label, probs):
        return probs
    pg.click("#sheet .gtab[data-tab=pbp]"); time.sleep(.3)
    probe = """(id)=>{pbpGo(id);const q=s=>document.querySelectorAll('#sheet .fstrip '+s).length;
      return {proj:q('.fproj'),trail:q('.ftrail'),red:q('.ftrail.red'),flag:q('.fflag'),tag:[...document.querySelectorAll('#sheet .fstrip .ftag')].map(e=>e.textContent).join('|'),
              td:q('.ez.tdflash'),turn:q('.fball.turn')};}"""
    for pid, want, what in (("p2", lambda r: r["proj"] == 1, "a pass draws a flying ball"),
                            ("p3", lambda r: r["trail"] == 1 and r["red"] == 0, "a run draws a trail"),
                            ("p5", lambda r: r["red"] == 1 and "SACK" in r["tag"], "a sack draws a red trail and a SACK tag"),
                            ("p8", lambda r: r["flag"] == 1, "a penalty pops a flag"),
                            ("p9", lambda r: r["proj"] == 1 and "FIELD GOAL" in r["tag"], "a field goal kicks and says so"),
                            ("p10", lambda r: r["proj"] == 1, "a punt kicks"),
                            ("p7", lambda r: r["turn"] == 1 and "TURNOVER" in r["tag"], "an interception flags the turnover"),
                            ("p4", lambda r: r["td"] == 1 and "TOUCHDOWN" in r["tag"] and r["proj"] == 1, "a touchdown pass flies and flashes the end zone"),
                            ("p6", lambda r: r["proj"] + r["trail"] + r["flag"] == 0 and r["tag"] == "", "a timeout animates nothing")):
        # step to a neighbour first so pbpGo(id) is a real change, then to the play under test
        other = "p1" if pid != "p1" else "p2"
        pg.evaluate(f"pbpGo('{other}')"); time.sleep(.05)
        r = pg.evaluate(probe, pid)
        if not want(r):
            probs.append(label + ": " + what + " -> " + repr(r))
    if SHOTS:                                                  # a frame mid-animation (a deep touchdown pass), for a look
        pg.evaluate("pbpGo('p1')"); time.sleep(.3)
        pg.evaluate("document.querySelector('#sheet').scrollTop=document.querySelector('#sheet .fstrip').offsetTop-70")
        pg.evaluate("pbpGo('p4')"); time.sleep(.45)
        pg.screenshot(path=os.path.join(SHOTS, "pbp_fx_phone.png"))
    time.sleep(2.3)
    left = pg.evaluate("document.querySelectorAll('#sheet .fstrip .fproj,.ftrail,.fflag,.ftag').length")
    if left:
        probs.append(label + ": illustration elements weren't cleaned up (%d left)" % left)
    pg.evaluate("closeModal()")
    return probs


def run_absent(pg, label):
    """Drives absent / odd: no tabs, the page works exactly as before; other sports get no tabs either; a stale chosen tab falls back."""
    probs = []
    # football, detail present but no pbp
    state["g"] = game(None)
    if not open_game(pg, label, probs):
        return probs
    if pg.evaluate("document.querySelectorAll('#sheet .gtab').length") != 0 or pg.evaluate("document.querySelectorAll('#sheet .gpanel').length") != 0:
        probs.append(label + ": tabs shown with no drives")
    if not pg.evaluate("!!document.querySelector('#sheet .fstrip .fld')&&!!document.querySelector('#sheet .chartbox')&&!!document.querySelector('#sheet .dkpis')"):
        probs.append(label + ": the page lost its strip/chart when drives are absent")
    # pbp with empty/odd drives is the same as absent
    for odd in ({"drives": [], "n": 0, "cut": 0}, {"drives": [{"id": "x", "plays": []}], "n": 0, "cut": 0}, {"drives": "nope"}, "junk"):
        state["g"] = game(odd)
        pg.evaluate("S.gameSig=null;drawGame()"); time.sleep(.5)
        if pg.evaluate("document.querySelectorAll('#sheet .gtab').length") != 0:
            probs.append(label + ": tabs shown for odd pbp " + repr(odd)[:40])
    # not football: no tabs even if (absurdly) a pbp block arrives
    state["g"] = game(full(), sport="nba", detail=True)
    pg.evaluate("S.gameSig=null;drawGame()"); time.sleep(.5)
    if pg.evaluate("document.querySelectorAll('#sheet .gtab').length") != 0:
        probs.append(label + ": a non-football game got tabs")
    # football game: choose pbp, then the drives vanish -> falls back to the overview with no error
    state["g"] = game(full(), sport="nfl")
    pg.evaluate("S.gameSig=null;drawGame()")
    until(pg, "document.querySelectorAll('#sheet .gtab').length===2", 5)
    pg.click("#sheet .gtab[data-tab=pbp]"); time.sleep(.3)
    state["g"] = game(None)
    pg.evaluate("S.gameSig=null;drawGame()"); time.sleep(.6)
    if pg.evaluate("document.querySelectorAll('#sheet .gtab').length") != 0 or not pg.evaluate("!!document.querySelector('#sheet .chartbox')"):
        probs.append(label + ": the page didn't recover when the drives disappeared")
    # college football gets the same tabs
    state["g"] = game(full(), sport="ncaaf")
    pg.evaluate("S.gameSig=null;drawGame()")
    if not until(pg, "document.querySelectorAll('#sheet .gtab').length===2", 5):
        probs.append(label + ": college football didn't get the football tabs")
    # hostile feed text and colour
    state["g"] = game({"drives": drives(odd_text="<img src=x onerror=window.__pwn=1><b>bold</b> & \"q\""), "n": 11, "cut": 0}, home_color="red;background:url(//evil)")
    pg.evaluate("S.gameSig=null;drawGame()")
    until(pg, "document.querySelectorAll('#sheet .gtab').length===2", 5)
    pg.click("#sheet .gtab[data-tab=pbp]"); time.sleep(.4)
    if pg.evaluate("!!window.__pwn") or pg.evaluate("document.querySelectorAll('#sheet .pbp img, #sheet .pbp b > b').length") != 0:
        probs.append(label + ": feed text reached the DOM as markup")
    if "<img" not in pg.evaluate("document.querySelector('#sheet .pctx').textContent"):
        probs.append(label + ": the hostile text should show as plain text")
    dots = pg.evaluate("[...document.querySelectorAll('#sheet .pdot')].map(e=>e.getAttribute('style'))")
    if any("evil" in (x or "") or "red;" in (x or "") for x in dots):
        probs.append(label + ": a feed colour reached a style attribute unchecked: " + repr(dots[:2]))
    pg.evaluate("closeModal()")
    return probs


def swipe(cdp, x0, x1, y, steps=12):
    """A real finger drag (touchStart, touchMove..., touchEnd) through Chrome's input pipeline."""
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x0, "y": y}]})
    for i in range(1, steps + 1):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x0 + (x1 - x0) * i / steps, "y": y}]}); time.sleep(.02)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def run_swipe(ctx, pg, label):
    """Swipe-back is the pushed sheet's edge gesture, but it listened on the whole sheet: a sideways swipe on the (overflowing) tab
    row closed the page instead of scrolling the row. With real touch events: a rightward swipe ON the row scrolls it and the sheet
    stays; a rightward swipe anywhere else still closes the sheet."""
    probs = []
    state["g"] = game(full())
    if not open_game(pg, label, probs):
        return probs
    pg.evaluate("""(()=>{const r=document.querySelector('#sheet .gtabs');for(let i=0;i<6;i++){const b=document.createElement('button');b.type='button';b.className='gtab';b.textContent='Extra tab '+i;r.insertBefore(b,r.querySelector('.gtabind'));}
      r.scrollLeft=r.scrollWidth;})()""")
    time.sleep(.4)
    row = pg.evaluate("(()=>{const r=document.querySelector('#sheet .gtabs'),b=r.getBoundingClientRect();return {over:r.scrollWidth>r.clientWidth,sl:r.scrollLeft,x:b.left,w:b.width,y:b.top+b.height/2};})()")
    if not row["over"] or row["sl"] < 50:
        probs.append(label + ": couldn't set up an overflowing, scrolled tab row " + repr(row)); return probs
    cdp = ctx.new_cdp_session(pg)
    swipe(cdp, row["x"] + 30, row["x"] + row["w"] - 20, row["y"]); time.sleep(.6)
    after = pg.evaluate("({on:document.querySelector('#modal').classList.contains('on'),sl:document.querySelector('#sheet .gtabs')&&document.querySelector('#sheet .gtabs').scrollLeft,tx:document.querySelector('#sheet').style.transform})")
    if not after["on"]:
        probs.append(label + ": swiping the tab row right closed the page " + repr(after))
    if after["sl"] is None or after["sl"] >= row["sl"] - 20:
        probs.append(label + ": swiping the tab row right didn't scroll it (scrollLeft %s -> %s)" % (row["sl"], after["sl"]))
    if after["tx"]:
        probs.append(label + ": the sheet followed the finger while the row was swiped " + repr(after["tx"]))
    # the same swipe on the plain page body (the header block) is the ordinary swipe-back and still closes the sheet
    ym = pg.evaluate("(()=>{const b=document.querySelector('#sheet .dhead').getBoundingClientRect();return b.top+b.height/2;})()")
    swipe(cdp, 15, 330, ym); time.sleep(.8)
    if pg.evaluate("document.querySelector('#modal').classList.contains('on')"):
        probs.append(label + ": an ordinary rightward swipe elsewhere no longer closes the page")
    return probs


def run_reduced(pg, label):
    """Reduced motion: the text and ball spot still update when stepping, but no illustration element is ever made and the
    ball doesn't glide."""
    probs = []
    state["g"] = game(full())
    if not open_game(pg, label, probs):
        return probs
    pg.click("#sheet .gtab[data-tab=pbp]"); time.sleep(.3)
    ind_tr = pg.evaluate("getComputedStyle(document.querySelector('#sheet .gtabind')).transitionDuration")
    if ind_tr not in ("0s", "0s, 0s"):
        probs.append(label + ": the tab underline still animates under reduced motion: " + ind_tr)
    pg.evaluate("""(()=>{let n=0;const ob=new MutationObserver(m=>m.forEach(x=>x.addedNodes.forEach(a=>{if(a.classList&&/fproj|ftrail|fflag|ftag/.test(a.className))n++;})));
      ob.observe(document.querySelector('#sheet'),{childList:true,subtree:true});window.__fx=()=>n;return 0;})()""")
    pg.click("#sheet [data-step=prev]"); time.sleep(.3)
    if "punts 47" not in pg.evaluate(CARD_TEXT):
        probs.append(label + ": the card text didn't update under reduced motion")
    if not ball_ok(pg, pct("away", 78)):
        probs.append(label + ": the ball spot didn't update under reduced motion")
    for pid in ("p4", "p7", "p8", "p5", "p9"):
        pg.evaluate(f"pbpGo('{pid}')"); time.sleep(.05)
    if pg.evaluate("window.__fx()") != 0:
        probs.append(label + ": illustration elements were created under reduced motion")
    tr = pg.evaluate("""(()=>{const s=getComputedStyle(document.querySelector('#sheet .fstrip .fball'));return (s.transitionProperty||'')+'|'+(s.transitionDuration||'');})()""")
    if "left" in tr and "0s" not in tr.split("|")[1]:
        probs.append(label + ": the ball still glides under reduced motion: " + tr)
    if not pg.evaluate("document.querySelector('#sheet .fstrip').classList.contains('noanim')"):
        probs.append(label + ": strip lacks noanim")
    # the controls still work
    pg.click("#sheet .plive"); time.sleep(.2)
    if "left end" not in pg.evaluate(CARD_TEXT):
        probs.append(label + ": Back to live failed under reduced motion")
    pg.evaluate("closeModal()")
    return probs


with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []
    probs = []
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
    pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    pg.on("pageerror", lambda e: errs.append(str(e)))
    probs += run(pg, "phone", True, "pbp_phone.png")
    probs += run_fx(pg, "phone")
    probs += run_absent(pg, "phone")
    pg.close()
    pg = br.new_page(viewport={"width": 1280, "height": 900}, color_scheme="dark")
    pg.on("pageerror", lambda e: errs.append(str(e)))
    probs += run(pg, "desktop", False, "pbp_desktop.png")
    pg.close()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", has_touch=True)
    tpg = ctx.new_page(); tpg.on("pageerror", lambda e: errs.append(str(e)))
    probs += run_swipe(ctx, tpg, "swipe")
    ctx.close()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", reduced_motion="reduce")
    rpg = ctx.new_page(); rpg.on("pageerror", lambda e: errs.append(str(e)))
    probs += run_reduced(rpg, "reduced")
    ctx.close()
    print("errs:", errs)
    if errs:
        probs.append("JS errors")
    if probs:
        print("PROBLEMS:", probs)
    br.close()
