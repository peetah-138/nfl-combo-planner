# CHECK: group=page secs=66
"""Slice 3 of the live game page (issue #72): the BOX SCORE, TEAM STATS, INJURY REPORT, LAST 5 GAMES and SEASON LEADERS tabs.
Display only. The game answer's detail block is built by the real engine from fixtures/espn_game_tabs.json (trimmed copies of
real public ESPN responses) through a fake network, then served to the page; nothing real is touched. Covers each tab's render,
the box-score team switch (and it surviving a redraw), team-stat bars (widths, and numbers/bars moving when the game changes
them), injury status colours, last-5 rows, leaders with jersey badges, empty and not-available states, tabs hidden when their
data is absent, feed text staying text, press feedback, reduced motion, no JS errors, and no sideways scroll on a phone
(390x844) or desktop. Writes phone screenshots of every tab when GT_SHOTS_DIR is set."""
import sys, os, time, threading, json, copy
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
    return A


W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright

# ---- the detail block, made by the real engine from the real (trimmed) ESPN shapes
espec = importlib.util.spec_from_file_location("E3", "wahome/engine.py"); E = importlib.util.module_from_spec(espec); espec.loader.exec_module(E)
FX = json.load(open("fixtures/espn_game_tabs.json"))
EV = "401873066"


class Resp:
    def __init__(self, body, code=200):
        self.body, self.status_code, self.ok, self.headers = body, code, code < 400, {}

    def json(self):
        return self.body


class Net:
    RequestException = E._requests.RequestException

    def get(self, url, params=None, **kw):
        for kind in ("schedule", "leaders"):
            if "/" + kind in url:
                tid = url.split("/teams/")[1].split("/")[0]
                return Resp(copy.deepcopy(FX[kind][tid]))
        if "/athletes/" in url:
            aid = url.rstrip("/").split("/athletes/")[1]
            return Resp(copy.deepcopy(FX["athletes"][aid])) if aid in FX["athletes"] else Resp({}, 404)
        return Resp({}, 404)


E.requests = Net()
DETAIL = E.game_extras(E._parse_game_detail(copy.deepcopy(FX["summary"]), EV), "football/nfl", EV, budget=8)
assert all(k in DETAIL for k in ("box", "tstats", "inj", "last5", "leaders")), list(DETAIL)
TK = "KXNFLGAME-26NOV20INDHOU-IND"
SHOTS = os.environ.get("GT_SHOTS_DIR")
TABS = ["Overview", "Box score", "Team stats", "Injury report", "Last 5 games", "Season leaders"]


def game(detail=None, chance=.24):
    d = copy.deepcopy(DETAIL if detail is None else detail)
    d["situation"] = {"down": 2, "distance": 6, "yardLine": 31, "isRedZone": False, "homeTimeouts": 3, "awayTimeouts": 2,
                      "downDistanceText": "2nd & 6 at IND 31", "possessionText": "IND 31", "lastPlayText": "J.Taylor left end for 4 yards.", "lastPlayType": "Rush"}
    return {"leg": {"ticker": TK, "t": TK, "sport": "nfl", "state": "live", "phase": "on", "on": True, "name": "Colts", "opp": "Texans",
                    "kind": "win", "chance": chance, "live": chance, "side": "yes",
                    "sc": {"abbr": "IND", "opp_abbr": "HOU", "me": 3, "opp": 26, "detail": "Q4 2:10"}},
            "combos": [], "story": {"ticks": [{"ts": time.time() - 60 * i, "chance": chance} for i in range(4)], "plays": []},
            "whatif": None, "detail": d, "fresh": {"now": time.time(), "built": time.time() - 2, "scores": 3, "fast": True}}


state = {"g": game()}


def answer(route):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(state["g"]))


def until(pg, js, secs=10):
    end = time.time() + secs
    while time.time() < end:
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        time.sleep(.1)
    return False


def open_game(pg):
    pg.goto(B + "/app"); time.sleep(.6)
    pg.evaluate(f"S.boxSide=null;openGame('{TK}')")
    return until(pg, "!!document.querySelector('#sheet .board2')")


def redraw(pg):
    pg.evaluate("window.__mark=document.querySelector('#sheet .board2')")
    pg.evaluate("S.gameSig=null;drawGame()")
    return until(pg, "document.querySelector('#sheet .board2')&&document.querySelector('#sheet .board2')!==window.__mark", 8)


def pick(pg, k):
    pg.evaluate(f"document.querySelector('#sheet .gtab[data-tab={k}]').scrollIntoView({{inline:'center'}})")
    pg.click(f"#sheet .gtab[data-tab={k}]")
    return until(pg, f"!document.querySelector('#sheet .gpanel[data-tab={k}]').hidden&&document.querySelector('#sheet .gpanel[data-tab={k}]').children.length>0", 4)


def sideways(pg):
    return pg.evaluate("""(()=>{const sh=document.querySelector('#sheet');const d=document.documentElement;
      return {page:d.scrollWidth-innerWidth,sheet:sh.scrollWidth-sh.clientWidth};})()""")


def txt(pg, sel):
    return pg.evaluate(f"[...document.querySelectorAll('#sheet {sel}')].map(e=>e.textContent.replace(/\\s+/g,' ').trim())")


def sub(pg, sel, inner):
    """Texts of `inner` inside the FIRST element matching `sel` on the sheet."""
    return pg.evaluate("([s,i])=>{const e=document.querySelector('#sheet '+s);return e?[...e.querySelectorAll(i)].map(x=>x.textContent.replace(/\\s+/g,' ').trim()):[];}", [sel, inner])


def shot(pg, name):
    if SHOTS:
        pg.evaluate("document.querySelector('#sheet').scrollTop=document.querySelector('#sheet .gtabs').offsetTop-60"); time.sleep(.9)
        pg.screenshot(path=os.path.join(SHOTS, name))


def run(pg, label, phone):
    probs = []
    state["g"] = game()
    pg.route("**/app/api/game*", answer)
    if not open_game(pg):
        return [label + ": game sheet didn't draw"]
    names = txt(pg, ".gtab")
    if names != TABS:
        probs.append(label + ": wrong tab row " + repr(names))
    if phone and not pg.evaluate("(()=>{const b=document.querySelector('#sheet .gtabs');return b.scrollWidth>b.clientWidth+20;})()"):
        probs.append(label + ": the six tabs should overflow the phone row (it scrolls sideways)")

    # ---- box score: IND first (away), passing/rushing/receiving tables, jersey badges; the switch shows HOU
    if not pick(pg, "box"):
        probs.append(label + ": box score didn't open")
    heads = txt(pg, ".gpanel[data-tab=box] .ghead")
    if heads[:3] != ["Passing", "Rushing", "Receiving"]:
        probs.append(label + ": box tables " + repr(heads))
    cols = sub(pg, ".gpanel[data-tab=box] .gstat", "thead th")
    if cols[1:] != ["C/ATT", "YDS", "TD", "INT", "SACKS"]:
        probs.append(label + ": passing columns " + repr(cols))
    first = sub(pg, ".gpanel[data-tab=box] .gstat", "tbody tr:first-child td")[:3]
    if first != ["Daniel Jones#17", "12/27", "144"]:
        probs.append(label + ": first passing row " + repr(first))
    if not pg.evaluate("document.querySelector('#sheet .bxsw button.on').dataset.side==='away'"):
        probs.append(label + ": the box switch should start on the away team")
    if probs == [] and phone:
        shot(pg, "box_score_phone.png")
    pg.click("#sheet .bxsw button[data-side=home]"); time.sleep(.35)
    hp = sub(pg, ".gpanel[data-tab=box] .gstat", "tbody tr:first-child td")[:1]
    if hp != ["C.J. Stroud#7"]:
        probs.append(label + ": team switch didn't show HOU's passer: " + repr(hp))
    if not pg.evaluate("document.querySelector('#sheet .bxsw button.on').dataset.side==='home'&&document.querySelector('#sheet .bxsw button[data-side=home]').getAttribute('aria-pressed')==='true'"):
        probs.append(label + ": the switch didn't mark HOU as chosen")
    ind = pg.evaluate("(()=>{const o=document.querySelector('#sheet .bxsw button.on'),i=document.querySelector('#sheet .bxsw .segind');return i?[o.offsetLeft,parseFloat(i.style.left)]:null;})()")
    if not ind or abs(ind[0] - ind[1]) > 1.5:
        probs.append(label + ": the switch's sliding pill isn't under HOU " + repr(ind))
    if not redraw(pg) or not pg.evaluate("document.querySelector('#sheet .bxsw button.on').dataset.side==='home'&&document.querySelector('#sheet .gtab.on').dataset.tab==='box'"):
        probs.append(label + ": a redraw lost the box tab or the team switch")
    sw = sideways(pg)
    if sw["page"] > 0 or sw["sheet"] > 0:
        probs.append(label + ": box score scrolls sideways %r" % sw)

    # ---- team stats: 13 rows, label in the middle, share bars at the right widths; a change rolls the number and slides the bar
    if not pick(pg, "tstats"):
        probs.append(label + ": team stats didn't open")
    rows = txt(pg, ".gpanel[data-tab=tstats] .tsv span")
    if len(rows) != 13 or rows[0] != "Total yards" or rows[-1] != "Time of possession":
        probs.append(label + ": team stat rows " + repr(rows))
    tv = sub(pg, ".gpanel[data-tab=tstats] .tsr", ".tsv b")
    if tv != ["167", "354"]:
        probs.append(label + ": total yards numbers " + repr(tv))
    time.sleep(.9)
    w = pg.evaluate("(()=>{const b=document.querySelector('#sheet .gpanel[data-tab=tstats] .h2bar');const i=b.querySelectorAll('i');return [parseFloat(i[0].style.width),parseFloat(i[1].style.width),i[0].getBoundingClientRect().width,i[1].getBoundingClientRect().width];})()")
    if abs(w[0] - 167 / 521 * 100) > .2 or abs(w[0] + w[1] - 100) > .01 or not (w[2] < w[3]):
        probs.append(label + ": total yards bar widths " + repr(w))
    cols_ = pg.evaluate("[...document.querySelectorAll('#sheet .gpanel[data-tab=tstats] .tsr .h2bar i')].slice(0,2).map(i=>getComputedStyle(i).backgroundColor)")
    if len(set(cols_)) != 2:
        probs.append(label + ": the two sides' bar colours should differ " + repr(cols_))
    d2 = copy.deepcopy(DETAIL)
    d2["tstats"][0].update({"a": "300", "an": 300.0})
    state["g"] = game(d2)
    pg.evaluate("window.__fl=0;new MutationObserver(m=>m.forEach(x=>{if(x.target.classList&&x.target.classList.contains('fl-up'))window.__fl++;})).observe(document.querySelector('#sheet'),{subtree:true,attributes:true,attributeFilter:['class']})")
    redraw(pg)
    mid = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#sheet .gpanel[data-tab=tstats] .h2bar i')).width)")
    time.sleep(1.0)
    w2 = pg.evaluate("[parseFloat(document.querySelector('#sheet .gpanel[data-tab=tstats] .h2bar i').style.width),document.querySelector('#sheet .gpanel[data-tab=tstats] .tsv b').textContent]")
    if abs(w2[0] - 300 / 654 * 100) > .2 or w2[1] != "300":
        probs.append(label + ": a changed stat didn't update its bar/number " + repr(w2))
    if not pg.evaluate("window.__fl>0"):
        probs.append(label + ": the changed number didn't roll with a flash")
    full = pg.evaluate("document.querySelector('#sheet .gpanel[data-tab=tstats] .h2bar').getBoundingClientRect().width")
    if not (mid < full * 300 / 654 - 2):
        probs.append(label + ": the bar jumped instead of sliding (mid-transition width %.1f of %.1f)" % (mid, full * 300 / 654))
    state["g"] = game()
    redraw(pg)
    if probs == [] and phone:
        shot(pg, "team_stats_phone.png")

    # ---- injury report: both teams, worst first, status colours
    if not pick(pg, "inj"):
        probs.append(label + ": injury report didn't open")
    n = pg.evaluate("document.querySelectorAll('#sheet .gpanel[data-tab=inj] .injr').length")
    if n != 10:
        probs.append(label + ": injury rows %d" % n)
    st = pg.evaluate("[...document.querySelectorAll('#sheet .gpanel[data-tab=inj] .ist')].map(e=>e.textContent+':'+e.className)")
    if not st or not st[0].startswith("Out:") or "bad" not in st[0] or not any(x.startswith("Doubtful:") and "warn" in x for x in st) or not any(x.startswith("Questionable:") and " q" in x for x in st):
        probs.append(label + ": injury status colours " + repr(st[:6]))
    if "back around Nov 29" not in pg.evaluate("document.querySelector('#sheet .gpanel[data-tab=inj]').textContent"):
        probs.append(label + ": the estimated return date is missing")
    if phone:
        shot(pg, "injury_report_phone.png")

    # ---- last 5 games: five rows per team, newest first, W/L tiles, records
    if not pick(pg, "last5"):
        probs.append(label + ": last 5 didn't open")
    l5 = txt(pg, ".gpanel[data-tab=last5] .l5r")
    if len(l5) != 10:
        probs.append(label + ": last-5 rows %d" % len(l5))
    if not any(r == "L@ CLE24–27Nov 15" for r in l5):
        probs.append(label + ": HOU's loss at CLE row missing " + repr(l5[5:7]))
    hd = txt(pg, ".gpanel[data-tab=last5] .ghead")
    if not hd or "(3-8)" not in hd[0] or "Indianapolis Colts" not in hd[0]:
        probs.append(label + ": last-5 header " + repr(hd))
    if pg.evaluate("document.querySelectorAll('#sheet .gpanel[data-tab=last5] .wl.w').length+document.querySelectorAll('#sheet .gpanel[data-tab=last5] .wl.l').length") != 10:
        probs.append(label + ": W/L tiles missing")
    if phone:
        shot(pg, "last5_phone.png")

    # ---- season leaders: three categories, names with jersey badges, stat lines, commas, bars
    if not pick(pg, "leaders"):
        probs.append(label + ": leaders didn't open")
    cats = txt(pg, ".gpanel[data-tab=leaders] .ldc")
    if cats != ["Passing yards", "Rushing yards", "Receiving yards"]:
        probs.append(label + ": leader categories " + repr(cats))
    time.sleep(.8)
    p0 = sub(pg, ".gpanel[data-tab=leaders] .ldr", ".ldp")
    if len(p0) != 2 or not p0[0].startswith("1,974") or "#17" not in p0[0] or "205/351, 7 TD, 13 INT" not in p0[0] or "C.J. Stroud#7" not in p0[1]:
        probs.append(label + ": passing leaders " + repr(p0))
    if pg.evaluate("document.querySelectorAll('#sheet .gpanel[data-tab=leaders] .h2bar').length") != 3:
        probs.append(label + ": leader bars missing")
    if phone:
        shot(pg, "season_leaders_phone.png")
    for k in ("tstats", "inj", "last5", "leaders"):
        pick(pg, k)
        sw = sideways(pg)
        if sw["page"] > 0 or sw["sheet"] > 0:
            probs.append(label + ": tab %s scrolls sideways %r" % (k, sw))
    # press feedback + haptic come from the global listener: the switch buttons and tabs are in its reach
    if not pg.evaluate("document.querySelector('#sheet .gtab[data-tab=leaders]').matches(TAP)"):
        probs.append(label + ": tabs not in the press-feedback set")
    pg.evaluate("closeModal()"); time.sleep(.3)
    pg.unroute("**/app/api/game*")
    return probs


def run_empty(pg, label):
    """Empty and not-available states; tabs hidden when their data is absent; feed text stays text."""
    probs = []
    d = copy.deepcopy(DETAIL)
    d["inj"] = {"away": [], "home": []}
    d["last5"] = {"away": {"rec": "", "g": [], "na": True}, "home": {"rec": "4-6", "g": []}}
    d["leaders"] = [{"k": "pass", "l": "Passing yards", "away": {"v": 10, "line": "", "n": "", "j": ""}}]
    d["box"]["away"][0]["r"][0]["n"] = '<img src=x onerror="window.__x=1">Bad'
    d.pop("tstats")
    state["g"] = game(d)
    pg.route("**/app/api/game*", answer)
    if not open_game(pg):
        return [label + ": game sheet didn't draw"]
    names = txt(pg, ".gtab")
    if "Team stats" in names or names != ["Overview", "Box score", "Injury report", "Last 5 games", "Season leaders"]:
        probs.append(label + ": a tab with no data should be hidden " + repr(names))
    pick(pg, "inj")
    if txt(pg, ".gpanel[data-tab=inj] .gempty") != ["No injuries reported.", "No injuries reported."]:
        probs.append(label + ": a real empty injury report should say no injuries reported for each team: " + repr(txt(pg, ".gpanel[data-tab=inj] .gempty")))
    pick(pg, "last5")
    t = pg.evaluate("document.querySelector('#sheet .gpanel[data-tab=last5]').textContent")
    if "aren’t available right now" not in t or "No finished games yet" not in t:
        probs.append(label + ": last-5 empty/not-available words missing: " + t[:200])
    pick(pg, "leaders")
    t = pg.evaluate("document.querySelector('#sheet .gpanel[data-tab=leaders]').textContent")
    if "Not available" not in t or "—" not in t:
        probs.append(label + ": a missing leader side should say not available: " + t[:200])
    if pg.evaluate("document.querySelector('#sheet .gpanel[data-tab=leaders] .h2bar').classList.contains('even')") is not True:
        probs.append(label + ": a one-sided leader bar should be even and quiet")
    pick(pg, "box")
    if pg.evaluate("window.__x===1||!!document.querySelector('#sheet .gpanel[data-tab=box] img')") or "<img" not in pg.evaluate("document.querySelector('#sheet .gpanel[data-tab=box] .pn').textContent"):
        probs.append(label + ": feed text was not escaped")
    # a non-football game or no detail: no tabs at all
    g2 = game(); g2["leg"]["sport"] = "nba"; state["g"] = g2
    redraw(pg)
    if pg.evaluate("document.querySelectorAll('#sheet .gtab').length"):
        probs.append(label + ": other sports should get no tab row")
    pg.evaluate("closeModal()"); time.sleep(.3)
    pg.unroute("**/app/api/game*")
    return probs


def run_nits(pg, label, phone):
    """The release-review nits: injuries empty vs missing, fewer-is-better bars, team data still loading (skeleton, then it fills in)."""
    probs = []
    pg.route("**/app/api/game*", answer)

    def show(d, tab):
        state["g"] = game(d)
        if not open_game(pg):
            return False
        return pick(pg, tab)

    # ---- injuries: a real empty list, ESPN sending nothing, and one side of each
    d = copy.deepcopy(DETAIL); d["inj"] = {"away": [], "home": []}
    if not show(d, "inj"):
        return [label + ": injury tab didn't open"]
    if txt(pg, ".gpanel[data-tab=inj] .gempty") != ["No injuries reported.", "No injuries reported."]:
        probs.append(label + ": two real empty lists: " + repr(txt(pg, ".gpanel[data-tab=inj] .gempty")))
    if "No injuries listed" in pg.evaluate("document.querySelector('#sheet').textContent"):
        probs.append(label + ": the old 'No injuries listed' wording is still there")
    d = copy.deepcopy(DETAIL); d.pop("inj")
    if not show(d, "inj"):
        probs.append(label + ": the injury tab should still show when ESPN sent no injury data")
    else:
        if txt(pg, ".gpanel[data-tab=inj] .gempty") != ["Injury report isn’t available right now."] * 2:
            probs.append(label + ": missing injury data should say not available: " + repr(txt(pg, ".gpanel[data-tab=inj] .gempty")))
        if pg.evaluate("document.querySelectorAll('#sheet .gpanel[data-tab=inj] .injr').length"):
            probs.append(label + ": injury rows from nowhere")
    d = copy.deepcopy(DETAIL); d["inj"] = {"away": d["inj"]["away"]}
    if not show(d, "inj"):
        probs.append(label + ": half an injury report didn't open")
    else:
        got = txt(pg, ".gpanel[data-tab=inj] .gempty")
        n = pg.evaluate("document.querySelectorAll('#sheet .gpanel[data-tab=inj] .injr').length")
        if got != ["Injury report isn’t available right now."] or n != 5:
            probs.append(label + ": one known side and one unknown: %r rows %d" % (got, n))
    sw = sideways(pg)
    if sw["page"] > 0 or sw["sheet"] > 0:
        probs.append(label + ": injury tab scrolls sideways %r" % sw)
    if phone:
        shot(pg, "injury_unavailable_phone.png")

    # ---- team stats: fewer is better on turnovers, sacks, penalties; ties stay neutral; the leader's side carries the longer bar
    state["g"] = game()
    if not open_game(pg) or not pick(pg, "tstats"):
        return probs + [label + ": team stats didn't open"]
    time.sleep(1.0)
    rows = pg.evaluate("""(()=>{const o={};document.querySelectorAll('#sheet .gpanel[data-tab=tstats] .tsr').forEach(r=>{
      const l=r.querySelector('.tsv span').childNodes[0].textContent,b=r.querySelectorAll('.tsv b'),i=r.querySelectorAll('.h2bar i');
      o[l]={lo:r.classList.contains('lo'),tag:!!r.querySelector('.lob'),a:b[0].className,h:b[1].className,w:[parseFloat(i[0].style.width),parseFloat(i[1].style.width)],even:r.querySelector('.h2bar').classList.contains('even'),
      px:[i[0].getBoundingClientRect().width,i[1].getBoundingClientRect().width]};});return o;})()""")
    sk = rows.get("Sacked", {})
    if not (sk.get("lo") and sk.get("tag") and sk["h"] == "lead" and sk["a"] == "lag" and abs(sk["w"][0] - 100 / 3) < .2 and sk["px"][0] < sk["px"][1]):
        probs.append(label + ": Sacked 2 vs 1 (fewer is better): home should lead with the longer bar " + repr(sk))
    pe = rows.get("Penalties", {})
    if not (pe.get("lo") and pe["a"] == "lead" and pe["h"] == "lag" and abs(pe["w"][0] - 4 / 6 * 100) < .2 and pe["px"][0] > pe["px"][1]):
        probs.append(label + ": Penalties 2 vs 4: away should lead with the longer bar " + repr(pe))
    to = rows.get("Turnovers", {})
    if not (to.get("lo") and to["a"] == "" and to["h"] == "" and to["even"] and abs(to["w"][0] - 50) < .01):
        probs.append(label + ": Turnovers 1 vs 1 is a tie: nobody leads, the bar is even " + repr(to))
    ty = rows.get("Total yards", {})
    if not (not ty.get("lo") and not ty.get("tag") and ty["h"] == "lead" and ty["a"] == "lag" and ty["px"][0] < ty["px"][1]):
        probs.append(label + ": Total yards 167 vs 354 (more is better): home leads " + repr(ty))
    tp = rows.get("Time of possession", {})
    if not (not tp.get("lo") and tp["h"] == "lead"):
        probs.append(label + ": time of possession is higher-is-better " + repr(tp))
    if sorted(k for k, v in rows.items() if v["tag"]) != ["Penalties", "Sacked", "Turnovers"]:
        probs.append(label + ": only the fewer-is-better rows carry the tag " + repr([k for k, v in rows.items() if v["tag"]]))
    # flip a lower-is-better row: 0 vs 3 turnovers -> away leads with a nearly full bar; changing it keeps the animation (the bar slides)
    d = copy.deepcopy(DETAIL)
    tr = next(r for r in d["tstats"] if r["k"] == "turnovers")
    tr.update({"a": "0", "an": 0.0, "h": "3", "hn": 3.0, "ld": "a"})
    state["g"] = game(d)
    redraw(pg); time.sleep(1.0)
    tw = pg.evaluate("""(()=>{const r=[...document.querySelectorAll('#sheet .gpanel[data-tab=tstats] .tsr')].find(x=>x.querySelector('.tsv span').textContent.startsWith('Turnovers'));
      const i=r.querySelectorAll('.h2bar i'),b=r.querySelectorAll('.tsv b');return [parseFloat(i[0].style.width),b[0].className,b[1].className,r.querySelector('.h2bar').classList.contains('even'),getComputedStyle(i[0]).transitionDuration];})()""")
    if not (tw[0] == 96 and "lead" in tw[1].split() and "lag" in tw[2].split() and tw[3] is False and tw[4] not in ("0s", "0ms")):
        probs.append(label + ": 0 vs 3 turnovers: away leads with a long bar that still animates " + repr(tw))
    sw = sideways(pg)
    if sw["page"] > 0 or sw["sheet"] > 0:
        probs.append(label + ": team stats scrolls sideways %r" % sw)
    if phone:
        shot(pg, "team_stats_lower_phone.png")

    # ---- team data still loading: skeletons on Last 5 / Season leaders, then the poll fills them in by itself
    d = copy.deepcopy(DETAIL); d.pop("last5"); d.pop("leaders"); d["gxp"] = True
    state["g"] = game(d)
    if not open_game(pg):
        return probs + [label + ": the game page didn't open while team data was loading"]
    names = txt(pg, ".gtab")
    if names != TABS:
        probs.append(label + ": the tab row while loading " + repr(names))
    if not pick(pg, "last5") or pg.evaluate("document.querySelectorAll('#sheet .gpanel[data-tab=last5] .gskr').length") < 5:
        probs.append(label + ": Last 5 should show a skeleton while loading")
    if "isn’t available" in pg.evaluate("document.querySelector('#sheet .gpanel[data-tab=last5]').textContent") or "aren’t available" in pg.evaluate("document.querySelector('#sheet .gpanel[data-tab=last5]').textContent"):
        probs.append(label + ": Last 5 says 'not available' while it is only loading")
    if not pick(pg, "leaders") or pg.evaluate("document.querySelectorAll('#sheet .gpanel[data-tab=leaders] .gskr').length") < 3:
        probs.append(label + ": Season leaders should show a skeleton while loading")
    for k in ("box", "tstats", "inj"):
        pick(pg, k)
        if pg.evaluate(f"document.querySelectorAll('#sheet .gpanel[data-tab={k}] .gskr').length"):
            probs.append(label + ": %s comes with the summary and needs no skeleton" % k)
    pick(pg, "last5")
    sw = sideways(pg)
    if sw["page"] > 0 or sw["sheet"] > 0:
        probs.append(label + ": the loading skeleton scrolls sideways %r" % sw)
    if phone:
        shot(pg, "last5_loading_phone.png")
    state["g"] = game()                                      # the Mac's fetch landed: the page's own quick re-poll fills the tab in
    if not until(pg, "document.querySelectorAll('#sheet .gpanel[data-tab=last5] .l5r').length===10", 9):
        probs.append(label + ": the page didn't fill Last 5 in by itself when the team data arrived")
    elif pg.evaluate("document.querySelector('#sheet .gtab.on').dataset.tab") != "last5":
        probs.append(label + ": the quiet redraw moved the open tab")
    pick(pg, "leaders")
    if pg.evaluate("document.querySelectorAll('#sheet .gpanel[data-tab=leaders] .gskr').length") or not pg.evaluate("document.querySelectorAll('#sheet .gpanel[data-tab=leaders] .ldr').length") == 3:
        probs.append(label + ": Season leaders didn't fill in")
    # a long 'still loading' that never lands (the Mac gives up saying so): no skeleton forever, the tabs hide
    d = copy.deepcopy(DETAIL); d.pop("last5"); d.pop("leaders")
    state["g"] = game(d)
    open_game(pg)
    if txt(pg, ".gtab") != ["Overview", "Box score", "Team stats", "Injury report"]:
        probs.append(label + ": with no team data and no 'loading' flag those two tabs hide " + repr(txt(pg, ".gtab")))
    pg.evaluate("closeModal()"); time.sleep(.3)
    pg.unroute("**/app/api/game*")
    return probs


def run_warm(pg, label):
    """Games tab: a live football card warms its game page data (once, politely); a hover or press does too; others don't."""
    probs = []
    calls = []
    fr = {"now": time.time(), "built": time.time() - 2, "scores": 3, "fast": True}

    def card(tk, sport="nfl", state_="live", name="Colts"):
        return {"name": name, "opp": "Texans", "sport": sport, "state": state_, "phase": "on", "ticker": tk, "combos": 1, "pays": 10.0, "singles": [],
                "sc": {"abbr": "IND", "opp_abbr": "HOU", "me": 3, "opp": 6, "detail": "Q2 4:10"}, "chance": .4, "spark": []}
    cards = [card(TK), card("KXNBAGAME-26NOV20LALBOS-LAL", "nba", "live", "Lakers"), card("KXNFLGAME-26NOV22KCDEN-KC", "nfl", "pre", "Chiefs"),
             card("KXNFLGAME-26NOV20DALPHI-DAL", "nfl", "live", "Cowboys")]

    def games(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"games": cards, "at": time.time(), "fresh": fr}))

    def warm(route):
        from urllib.parse import urlparse, parse_qs
        calls.append(parse_qs(urlparse(route.request.url).query).get("t", [""])[0])
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "known": True}))
    pg.route("**/app/api/games*", games)
    pg.route("**/app/api/game_warm*", warm)
    pg.goto(B + "/app"); pg.wait_for_timeout(600)
    pg.evaluate("go('games')")
    if not until(pg, "document.querySelectorAll('#main .gc').length===4", 8):
        return [label + ": the Games cards didn't draw"]
    pg.evaluate("S.lastLoad=Date.now()+3600000")   # hold the page's 5 s fallback poll off: its redraw would re-warm mid-test
    pg.wait_for_timeout(1600)
    if sorted(calls) != sorted([TK, "KXNFLGAME-26NOV20DALPHI-DAL"]):
        probs.append(label + ": showing the cards should warm the two LIVE football games only, once each: " + repr(calls))
    n = len(calls)
    pg.hover("#main .gc[data-gk='%s']" % TK); pg.wait_for_timeout(500)
    pg.dispatch_event("#main .gc[data-gk='%s']" % TK, "pointerdown"); pg.wait_for_timeout(300)      # a press (not a tap: that would open the game)
    pg.evaluate("go('build')"); pg.wait_for_timeout(400); pg.evaluate("go('games')"); pg.wait_for_timeout(1500)
    if len(calls) != n:
        probs.append(label + ": a hover, a press and a redraw within a minute must not warm the same game again (%d -> %d)" % (n, len(calls)))
    # a press on a card that was not warmed at render (the page's own cap) warms it; a non-football or pre-game card never does
    pg.evaluate("S.lastLoad=Date.now()+3600000")
    pg.evaluate("S.warm={};S.warmN=[]")
    pg.hover("#main .gc[data-gk='KXNBAGAME-26NOV20LALBOS-LAL']"); pg.wait_for_timeout(400)
    pg.hover("#main .gc[data-gk='KXNFLGAME-26NOV22KCDEN-KC']"); pg.wait_for_timeout(400)
    if len(calls) != n:
        probs.append(label + ": a basketball or not-yet-started card was warmed " + repr(calls[n:]))
    pg.hover("#main .gc[data-gk='KXNFLGAME-26NOV20DALPHI-DAL']"); pg.wait_for_timeout(500)
    if calls[n:] != ["KXNFLGAME-26NOV20DALPHI-DAL"]:
        probs.append(label + ": hovering a live football card should warm it " + repr(calls[n:]))
    # the page's own caps: 6 warm-ups per 5 minutes, 2 at a time, once a minute per game, a failed one waits longer
    pg.evaluate("S.warm={};S.warmN=[];S.warmBusy=0")
    calls.clear()
    pg.evaluate("for(let i=0;i<10;i++)warmGame('KXNFLGAME-26NOV20T'+i+'-X')"); pg.wait_for_timeout(800)
    if len(calls) > 2:
        probs.append(label + ": more than 2 warm-ups at once: %d" % len(calls))
    for i in range(10):
        pg.evaluate("warmGame('KXNFLGAME-26NOV20U%d-X')" % i); pg.wait_for_timeout(150)
    pg.wait_for_timeout(500)
    if len(calls) > 6:
        probs.append(label + ": more than 6 warm-ups in 5 minutes: %d" % len(calls))
    pg.evaluate("S.warm={};S.warmN=[]")
    pg.route("**/app/api/game_warm*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": False, "known": True})))
    pg.evaluate("warmGame('KXNFLGAME-26NOV20W0-X')"); pg.wait_for_timeout(500)
    if pg.evaluate("S.warm['KXNFLGAME-26NOV20W0-X']-Date.now()") > 70000:
        probs.append(label + ": a game the Mac merely throttled should be asked again after the normal minute, not 3 minutes")
    pg.unroute("**/app/api/game_warm*")
    pg.route("**/app/api/game_warm*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": False})))
    pg.evaluate("warmGame('KXNFLGAME-26NOV20V0-X')"); pg.wait_for_timeout(500)
    if pg.evaluate("S.warm['KXNFLGAME-26NOV20V0-X']-Date.now()") < 150000:
        probs.append(label + ": a game the Mac would not warm should wait 3 minutes before asking again")
    pg.evaluate("go('live')"); pg.wait_for_timeout(300)
    pg.unroute("**/app/api/games*"); pg.unroute("**/app/api/game_warm*")
    return probs


def run_tz(pg, label):
    """A Monday night game (01:15 UTC on the Tuesday) shows Monday's date in the phone's own time zone."""
    d = copy.deepcopy(DETAIL)
    d["last5"]["home"]["g"][0]["d"] = "2026-11-17T01:15Z"
    state["g"] = game(d)
    pg.route("**/app/api/game*", answer)
    if not open_game(pg):
        return [label + ": game sheet didn't draw"]
    pick(pg, "last5")
    rows = txt(pg, ".gpanel[data-tab=last5] .l5r")
    probs = [] if rows[5].endswith("Nov 16") else [label + ": a night game shows the next day: " + rows[5]]
    pg.evaluate("closeModal()")
    return probs


def run_reduced(pg, label):
    probs = []
    state["g"] = game()
    pg.route("**/app/api/game*", answer)
    if not open_game(pg):
        return [label + ": game sheet didn't draw"]
    pick(pg, "tstats")
    if pg.evaluate("document.querySelector('#sheet .gpanel[data-tab=tstats]').classList.contains('gin')"):
        probs.append(label + ": the entrance animation ran under reduced motion")
    an = pg.evaluate("getComputedStyle(document.querySelector('#sheet .gpanel[data-tab=tstats] .h2bar i')).transitionDuration")
    if an not in ("0s", "0ms") and not an.startswith("0s"):
        probs.append(label + ": bars still slide under reduced motion: " + an)
    pick(pg, "box")
    pg.click("#sheet .bxsw button[data-side=home]"); time.sleep(.2)
    if sub(pg, ".gpanel[data-tab=box] .gstat", "tbody tr:first-child td")[:1] != ["C.J. Stroud#7"]:
        probs.append(label + ": the switch should still work under reduced motion")
    pg.evaluate("closeModal()")
    return probs


IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
HSW = r"""(()=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&!e.closest('[hidden]');};
 const hosts=[...document.querySelectorAll('#sheet '+HSWQ.split(',').join(',#sheet '))].filter(e=>vis(e)&&!e.closest(HSWNO)&&!e.querySelector(HSWIN)&&!e.disabled);
 const bad=hosts.filter(h=>h.querySelectorAll(':scope>.hsw').length!==1).map(h=>h.tagName+'.'+h.className+':'+(h.textContent||'').trim().slice(0,16));
 return {n:hosts.length,bad:bad.slice(0,6),links:document.querySelectorAll('#sheet a[href]>.hsw').length,
  tabs:[...document.querySelectorAll('#sheet .gtab')].filter(b=>b.querySelectorAll(':scope>.hsw').length===1).length};})()"""


def run_hsw(pg, label):
    """Method N (#60): the box score's team pills and each tab's controls carry one see-through switch, links none, and the
    tabs none (#218: they sit in a sideways-scrolling row); a real touch on a tab opens it, one on a team pill lands on its
    switch and still does its job."""
    probs = []
    state["g"] = game()
    pg.route("**/app/api/game*", answer)
    if not open_game(pg):
        return [label + ": game sheet didn't draw"]
    if not pg.evaluate("hswOn()"):
        return [label + ": method N isn't on for an iPhone"]
    for k in ("overview", "pbp", "box", "tstats", "inj", "last5", "leaders"):
        if pg.evaluate(f"!document.querySelector('#sheet .gtab[data-tab={k}]')"):
            continue
        pg.evaluate(f"document.querySelector('#sheet .gtab[data-tab={k}]').scrollIntoView({{inline:'center',block:'center'}})"); time.sleep(.3)
        bb = pg.locator(f"#sheet .gtab[data-tab={k}]").bounding_box()
        # #218: the tab row scrolls sideways, so its tabs carry no switch (WebKit's switch grabs a sideways drag): a tap lands on the tab
        hit = pg.evaluate("([x,y])=>{const t=document.elementFromPoint(x,y),b=t&&t.closest('.gtab');return b?'tab|'+b.dataset.tab+(t.classList.contains('hsw')?'|hsw':''):(t?t.className:'')}", [bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2])
        if hit != "tab|" + k:
            probs.append(label + ": a tap on the %s tab doesn't land on the tab itself (%s)" % (k, hit))
        pg.touchscreen.tap(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
        if not until(pg, f"document.querySelector('#sheet .gtab.on').dataset.tab==='{k}'&&!document.querySelector('#sheet .gpanel[data-tab={k}]').hidden", 4):
            probs.append(label + ": tapping the %s tab didn't open it" % k)
        time.sleep(.3)
        c = pg.evaluate(HSW)
        if c["bad"] or c["links"]:
            probs.append(label + ": %s tab switches: %r" % (k, c))
        if c["tabs"]:
            probs.append(label + ": tabs in the sideways tab row carry switches on %s: %r" % (k, c))
        if k == "box":
            if pg.evaluate("document.querySelectorAll('#sheet .bxsw button').length") != 2 or pg.evaluate("[...document.querySelectorAll('#sheet .bxsw button')].some(b=>b.querySelectorAll(':scope>.hsw').length!==1)"):
                probs.append(label + ": the team pills lack their switches")
            pg.evaluate("document.querySelector('#sheet .bxsw').scrollIntoView({block:'center'})"); time.sleep(.3)
            hb = pg.locator("#sheet .bxsw button[data-side=home]").bounding_box()
            pg.touchscreen.tap(hb["x"] + hb["width"] / 2, hb["y"] + hb["height"] / 2)
            if not until(pg, "document.querySelector('#sheet .bxsw button.on').dataset.side==='home'", 3):
                probs.append(label + ": tapping a team pill through its switch didn't switch teams")
            elif pg.evaluate("document.querySelector('#sheet .bxsw button.on').querySelectorAll(':scope>.hsw').length") != 1:
                probs.append(label + ": the redrawn team pill lost (or doubled) its switch")
    pg.evaluate("closeModal()"); time.sleep(.3)
    pg.unroute("**/app/api/game*")
    return probs


with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, probs = [], []
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
    pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    pg.on("pageerror", lambda e: errs.append(str(e)))
    probs += run(pg, "phone", True)
    probs += run_empty(pg, "phone-empty")
    probs += run_nits(pg, "phone-nits", True)
    pg.close()
    pg = br.new_page(viewport={"width": 390, "height": 844}, color_scheme="light")
    pg.on("pageerror", lambda e: errs.append(str(e)))
    probs += run(pg, "phone-light", False)
    pg.close()
    pg = br.new_page(viewport={"width": 1280, "height": 900}, color_scheme="dark")
    pg.on("pageerror", lambda e: errs.append(str(e)))
    probs += run(pg, "desktop", False)
    probs += run_nits(pg, "desktop-nits", False)
    pg.close()
    pg = br.new_page(viewport={"width": 390, "height": 844}, color_scheme="dark")
    pg.on("pageerror", lambda e: errs.append(str(e)))
    probs += run_warm(pg, "warm")
    pg.close()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", reduced_motion="reduce")
    rpg = ctx.new_page(); rpg.on("pageerror", lambda e: errs.append(str(e)))
    probs += run_reduced(rpg, "reduced")
    ctx.close()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", timezone_id="America/New_York")
    zpg = ctx.new_page(); zpg.on("pageerror", lambda e: errs.append(str(e)))
    probs += run_tz(zpg, "new-york")
    ctx.close()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", has_touch=True, user_agent=IOS)
    hpg = ctx.new_page(); hpg.on("pageerror", lambda e: errs.append(str(e)))
    hpg.add_init_script("localStorage.removeItem('cw_hapoff')")
    probs += run_hsw(hpg, "iphone-switches")
    ctx.close()
    print("errs:", errs)
    if errs:
        probs.append("JS errors")
    if probs:
        print("PROBLEMS:", probs)
    else:
        print("PASS game tabs (box score, team stats, injuries, last 5, leaders)")
    br.close()
