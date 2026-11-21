"""Makeover phase 2: live game cards on Games (singles and spreads included, score pulse + haptic, chance line, tap
pushes the game page), scrubbing the game page's chance chart, the Sold moment (tap and smart sell; calm for a loss),
the big-hit celebration, Results profit bars by day/week (scrub with haptic ticks, tap a bar for its bets), and the
loading skeletons and empty states. Phone (390x844, touch) and desktop. Prints PROBLEMS on any failure."""
import sys, os, time, threading, json
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
 {"ticker": "KXMVE-3", "legs": [L(3, "PHX"), L(1, "DEN")], "cost": 8.0, "pays": 19.5, "status": "pending", "back": 0, "week": "2026-11-17", "full_pays": 19.5, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-4", "legs": [L(0, "BOS"), L(2, "CHI")], "cost": 5.0, "pays": 22, "status": "lost", "back": 0, "week": "2026-11-12", "full_pays": 22, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-5", "legs": [L(0, "BOS"), L(1, "DEN")], "cost": 5.0, "pays": 14, "status": "won", "back": 0, "week": "2026-11-10", "full_pays": 14, "lg": "nba", "lgs": ["nba"]},
 {"ticker": "KXMVE-6", "legs": [L(3, "PHX"), L(2, "MIL")], "cost": 6.0, "pays": 30, "status": "cashed", "back": 11.4, "week": "2026-11-05", "full_pays": 30, "lg": "nba", "lgs": ["nba"]}]
SPREAD = f"KXNBASPREAD-{tk_ev[0].split('-')[1]}-BOS5"          # a spread on a game that's already in a combo
SING = [{"t": SPREAD, "ticker": SPREAD, "name": "Boston Celtics", "opp": "NYK", "live": None, "sc": None, "kind": "spread", "sport": "nba", "side": "yes",
         "label": "Boston wins by over 4.5", "game": "New York at Boston: Spread", "event": SPREAD.rsplit("-", 1)[0], "n": 10, "cost": 5.2, "pays": 10,
         "worth": 6.0, "chance": .58, "state": "pre", "res": None, "score": "", "starts": "Tonight 7:30 PM", "note": "", "phase": "", "short": "", "how": "", "url": ""},
        {"t": "KXNHLGAME-26NOV18SJSVGK-SJS", "ticker": "KXNHLGAME-26NOV18SJSVGK-SJS", "name": "San Jose", "opp": "VGK", "live": .31,
         "sc": {"me": 1, "opp": 2, "abbr": "SJS", "opp_abbr": "VGK", "detail": "2nd 8:40"}, "kind": "win", "sport": "nhl", "side": "yes",
         "label": "San Jose to win", "game": "San Jose vs Vegas Winner?", "event": "KXNHLGAME-26NOV18SJSVGK", "n": 6, "cost": 3, "pays": 6, "worth": 1.9,
         "chance": .31, "state": "live", "res": None, "score": "SJS 1-2 VGK 2nd 8:40", "starts": "", "note": "", "phase": "", "short": "", "how": "", "url": ""}]
SOLD_AT = time.time() + 30          # "sold" just after the page opened (the page only shows sales made while it's open)
def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: (bets, 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    A.open_singles = lambda: [dict(x) for x in SING]
    A.MINE["cash"]["KXMVE-3"] = {"rfq": "r", "quote": "q", "offer": 15.8, "price": .81, "contracts": 19.5, "frac": 1.0, "at": time.time() + 3600}
    with open(A.SELL_LOG, "w") as f:                         # smart sell's own log: one old sale and one new one
        f.write(json.dumps({"combo": "Old sale", "ticker": "OLD", "offer": 9, "cost": 5, "result": "sold", "at": int(time.time() - 3000)}) + "\n")
        f.write(json.dumps({"combo": "San Jose to win", "ticker": "KXSOLD-1", "offer": 2.1, "cost": 3, "result": "sold", "at": int(SOLD_AT)}) + "\n")
        f.write(json.dumps({"combo": "Skipped", "ticker": "SK", "result": "skipped", "at": int(time.time())}) + "\n")
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

# ---- the API: singles ride on game cards (on their game's card, or their own), and recent sales are listed
gs = requests.get(B + "/app/api/games", headers={"X-CW": "x"}).json().get("games") or []
lv = requests.get(B + "/app/api/live", headers={"X-CW": "x"}).json()
print("games:", [(g["name"], g.get("combos"), [s["label"] for s in g.get("singles") or []]) for g in gs])
print("sales:", lv.get("sales"))
bos = next((g for g in gs if g["name"] == "Boston Celtics"), None)
if not bos or not any(s["t"] == SPREAD for s in bos.get("singles") or []): bad("the spread isn't on its game's card")
sjs = next((g for g in gs if g.get("ticker") == SING[1]["t"]), None)
if not sjs or sjs.get("state") != "live" or not sjs.get("sc") or sjs.get("combos"): bad(f"the single on its own game didn't get a live card: {sjs}")
if [s["ticker"] for s in lv.get("sales") or []] != ["OLD", "KXSOLD-1"]: bad(f"recent sales are wrong (skips listed, or sales missing): {lv.get('sales')}")

GAME = {"leg": {"ticker": "T", "name": "Boston Celtics", "opp": "New York Knicks", "sport": "nba", "state": "live", "phase": "", "kind": "win",
                "sc": {"me": 50, "opp": 44, "abbr": "BOS", "opp_abbr": "NYK", "detail": "Q3 4:12"}, "live": .7, "chance": .7},
        "combos": [{"t": "KXMVE-1", "label": "Combo", "p": .3, "pays": 41, "cost": 5, "legs": 3}],
        "story": {"ticks": [{"ts": time.time() - 3600 + i * 120, "chance": .5 + .01 * i} for i in range(30)], "plays": [{"ts": time.time() - 3600, "me": 0, "opp": 0}]}, "whatif": None}

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, tag in ((390, 844, "phone"), (1280, 900, "desk")):
        ctx = br.new_context(viewport={"width": vw, "height": vh}, color_scheme="dark", has_touch=(tag == "phone"))
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        ACTS = []
        def act(r):
            ACTS.append(r.request.post_data)
            a = json.loads(r.request.post_data or "{}").get("a")
            r.fulfill(status=200, content_type="application/json", body=json.dumps(
                {"ok": True, "msg": "✅ Phoenix + Denver cashed out for about $15.80.", "offer": 15.8} if a == "go" else {"ok": True, "msg": "Got it."}))
        pg.route("**/app/api/act", act)
        pg.route("**/app/api/game?*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(GAME)))
        pg.add_init_script("window.__haps=[];localStorage.clear();localStorage.setItem('cw_view','games')")
        pg.goto(B + "/app")
        if not wait(pg, "document.querySelectorAll('.gc').length>=2", 20): bad(f"{tag}: the live game cards didn't draw")
        time.sleep(1)
        sk = pg.evaluate("(()=>{const g=S.games;S.games=null;renderGames();const n=document.querySelectorAll('#main .gsk').length;S.games=g;render();return n;})()")   # the skeleton while Games loads
        if not sk: bad(f"{tag}: Games has no skeleton while loading")
        c = pg.evaluate("""(()=>{const cs=[...document.querySelectorAll('.gc')];return {n:cs.length,live:cs.filter(e=>e.classList.contains('live')).length,
          singles:document.querySelectorAll('.gc .bt.s').length,pts:document.querySelectorAll('.gc .pts').length,line:document.querySelectorAll('.gc .mline').length}})()""")
        print(tag, "cards:", c, "skeleton:", sk)
        if c["live"] < 1 or c["singles"] < 2 or c["pts"] < 2 or c["line"] != c["n"]: bad(f"{tag}: cards miss the live score, chance line or single bets: {c}")
        pg.evaluate("window.__ld=window.load;window.load=async()=>{}")      # hold the page still for the checks
        # ---- someone scores: the card pulses, the number bumps, the phone ticks
        n0 = pg.evaluate("__haps.length")
        pg.evaluate("(()=>{const g=S.games.games.find(x=>x.sc&&x.state==='live');g.sc=Object.assign({},g.sc,{me:g.sc.me+1});g.chance=.4;render();})()"); time.sleep(.15)
        sc = pg.evaluate(f"({{cls:(document.querySelector('.gc.scored')||{{}}).className,bump:!!document.querySelector('.gc .pts.bump'),haps:__haps.slice({n0})}})")
        print(tag, "scored:", sc)
        if not sc["cls"] or "good" not in sc["cls"] or not sc["bump"] or "success" not in sc["haps"]: bad(f"{tag}: a score didn't pulse/bump/tick: {sc}")
        pg.evaluate("(()=>{const g=S.games.games.find(x=>x.sc&&x.state==='live');g.sc=Object.assign({},g.sc,{opp:g.sc.opp+2});render();})()"); time.sleep(.15)
        if "bad" not in (pg.evaluate("(document.querySelector('.gc.scored')||{}).className") or ""): bad(f"{tag}: their score didn't pulse red")
        time.sleep(1.9)
        if pg.evaluate("!!document.querySelector('.gc.scored')"): bad(f"{tag}: the score pulse didn't clear")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{tag}: Games scrolls sideways")
        # ---- tap a card: pushes the game page; drag on its chart: readout and haptic ticks
        pg.locator(".gc").first.click()
        if not wait(pg, "$('#modal').classList.contains('push')&&!!document.querySelector('#sheet [data-scrub=win]')", 10): bad(f"{tag}: tapping a game card didn't push the game page with its chart")
        else:
            time.sleep(.5); bx = pg.locator("#sheet [data-scrub=win]").bounding_box(); n0 = pg.evaluate("__haps.length"); y = bx["y"] + bx["height"] / 2
            pg.mouse.move(bx["x"] + bx["width"] * .2, y); pg.mouse.down()
            for k in range(10): pg.mouse.move(bx["x"] + bx["width"] * (.2 + k * .07), y); time.sleep(.08)
            st = pg.evaluate("({on:document.querySelector('#sheet [data-scrub]').classList.contains('on'),rd:document.querySelector('#sheet .sread').textContent,scrub:S.scrub})")
            ticks = pg.evaluate(f"__haps.slice({n0}).filter(k=>k==='selection').length")
            pg.mouse.up(); time.sleep(.3)
            off = pg.evaluate("({on:document.querySelector('#sheet [data-scrub]').classList.contains('on'),scrub:S.scrub})")
            print(tag, "game scrub:", st, "ticks:", ticks, "after:", off)
            if not st["on"] or "%" not in st["rd"] or not st["scrub"] or ticks < 3: bad(f"{tag}: scrubbing the game chart didn't show a readout / tick: {st} {ticks}")
            if off["on"] or off["scrub"]: bad(f"{tag}: releasing the game chart didn't let go")
        pg.evaluate("closeModal()"); time.sleep(.5)

        # ---- the Sold moment after a tap: drawn check, amount, profit, ticket stub
        pg.evaluate("window.load=window.__ld;go('live')"); wait(pg, "!!(S.live&&S.live.combos)", 15); time.sleep(.5)
        pg.evaluate("window.load=async()=>{}")            # no refreshes while the moments are checked
        n0 = pg.evaluate("__haps.length")
        pg.evaluate("sell('KXMVE-3')"); time.sleep(.5); pg.locator("#sellgo").click()
        ok = wait(pg, "!!document.querySelector('#sheet .okcard.sold')", 5); time.sleep(1)
        so = pg.evaluate(f"({{calm:document.querySelector('#sheet .okcard').classList.contains('okloss'),amt:document.querySelector('#sheet .okcard .amt').textContent,pl:document.querySelector('#sheet .plp').textContent,tkt:!!document.querySelector('#sheet .tkt'),stamp:document.querySelector('#sheet .stamp').textContent,haps:__haps.slice({n0})}})") if ok else None
        print(tag, "sold:", so, "| act:", ACTS[-1:])
        if not ok or so["calm"] or so["amt"] != "$16" or "+$7.80" not in so["pl"] or not so["tkt"] or "success" not in so["haps"]: bad(f"{tag}: the Sold moment after a tap is wrong: {so}")
        if not ACTS or json.loads(ACTS[-1]).get("a") != "go": bad(f"{tag}: cash out didn't send the same 'go' action")
        pg.evaluate("closeModal()"); time.sleep(.5)
        # a failed sale stays a plain message (no Sold moment)
        pg.route("**/app/api/act", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "msg": "That offer expired. Tap Get cash-out offer for a fresh one."})))
        pg.evaluate("sell('KXMVE-3')"); time.sleep(.5); pg.locator("#sellgo").click(); time.sleep(1)
        if pg.evaluate("!!document.querySelector('#sheet .okcard.sold')"): bad(f"{tag}: an expired offer showed the Sold moment")
        pg.evaluate("closeModal()"); time.sleep(.4)
        # smart sell sold something while the page was open (from its log): calm card for a loss; old sales ignored
        pg.evaluate(f"S.t0={SOLD_AT - 60};S.momSeen={{}};liveMoments(S.live,S.live)"); time.sleep(1)
        sm = pg.evaluate("({ok:!!document.querySelector('#sheet .okcard.sold'),calm:!!document.querySelector('#sheet .okcard.okloss'),stamp:(document.querySelector('#sheet .stamp')||{}).textContent,h:(document.querySelector('#sheet .okcard h3')||{}).textContent,stacked:document.querySelector('#sheet .okcard svg').getBoundingClientRect().bottom<=document.querySelector('#sheet .okcard h3').getBoundingClientRect().top})")
        print(tag, "smart sell moment:", sm)
        if not sm["ok"] or not sm["calm"] or not sm["stacked"] or "SMART SELL" not in sm["stamp"] or "San Jose" not in sm["h"]: bad(f"{tag}: smart sell's sale didn't get the calm Sold card: {sm}")
        pg.evaluate("closeModal()"); time.sleep(.4)
        pg.evaluate("liveMoments(S.live,S.live)"); time.sleep(.4)
        if pg.evaluate("$('#modal').classList.contains('on')"): bad(f"{tag}: the same sale showed twice")
        # ---- a win: small one = confetti + toast; big one = the Big hit overlay with a rolling amount
        prev = pg.evaluate("JSON.parse(JSON.stringify(S.live))")
        pg.evaluate("p=>{const d=JSON.parse(JSON.stringify(p));const c=d.combos.find(x=>x.t==='KXMVE-3');c.group='won';liveMoments(p,d);}", prev); time.sleep(.3)
        sw = pg.evaluate("({big:!!document.querySelector('.bigwin'),conf:!!document.querySelector('.confetti'),toast:(document.querySelector('#toast')||{}).textContent})")
        print(tag, "small win:", sw)
        if sw["big"] or not sw["conf"] or "won" not in (sw["toast"] or ""): bad(f"{tag}: a small win should be confetti + a toast: {sw}")
        n0 = pg.evaluate("__haps.length")
        pg.evaluate("p=>{const d=JSON.parse(JSON.stringify(p));const c=d.combos.find(x=>x.t==='KXMVE-1');c.group='won';liveMoments(p,d);}", prev); time.sleep(.5)
        a1 = pg.evaluate("(document.querySelector('.bigwin .amt')||{}).textContent"); time.sleep(1.4)
        bw = pg.evaluate(f"({{on:!!document.querySelector('.bigwin'),amt:(document.querySelector('.bigwin .amt')||{{}}).textContent,haps:__haps.slice({n0}).filter(k=>k==='success').length}})")
        print(tag, "big win:", bw, "mid-roll:", a1)
        if not bw["on"] or bw["amt"] != "$41" or a1 == "$41" or bw["haps"] < 2: bad(f"{tag}: the big hit didn't roll up with a double haptic: {bw} {a1}")
        pg.locator(".bigwin").click(); time.sleep(.6)
        if pg.evaluate("!!document.querySelector('.bigwin')"): bad(f"{tag}: the big hit didn't close on tap")
        pg.evaluate("p=>{const d=JSON.parse(JSON.stringify(p));const c=d.combos.find(x=>x.t==='KXMVE-1');c.group='won';liveMoments(p,d);}", prev); time.sleep(.3)
        if pg.evaluate("!!document.querySelector('.bigwin')"): bad(f"{tag}: the same win celebrated twice")

        # ---- Results: skeleton, profit bars by week/day, scrub with ticks, tap a bar for its bets
        if not pg.evaluate("S.res=null;S.an=null;S.view='results';renderResults();!!document.querySelector('#main .hsk')&&document.querySelectorAll('#main .kpi.skel').length>=3"): bad(f"{tag}: Results has no skeleton while loading")
        pg.evaluate("window.load=window.__ld;go('results')")
        if not wait(pg, "!!document.querySelector('[data-scrub=pl]')", 15): bad(f"{tag}: the profit chart didn't draw")
        time.sleep(1)
        bars = pg.evaluate("document.querySelectorAll('.plc rect.brc').length"); h = pg.evaluate("Math.max(...[...document.querySelectorAll('.plc rect.brc')].map(r=>r.getBoundingClientRect().height))")
        print(tag, "week bars:", bars, "tallest:", h)
        if bars < 2 or h < 40: bad(f"{tag}: the week bars are missing or flat ({bars}, {h}px)")
        bx = pg.locator("[data-scrub=pl]").bounding_box(); y = bx["y"] + bx["height"] / 2; n0 = pg.evaluate("__haps.length")
        pg.mouse.move(bx["x"] + 4, y); pg.mouse.down()
        for k in range(8): pg.mouse.move(bx["x"] + bx["width"] * (k / 8 + .02), y); time.sleep(.06)
        rd = pg.evaluate("({on:document.querySelector('.plc').classList.contains('on'),sel:document.querySelectorAll('.plc rect.brc.sel').length,txt:document.querySelector('.plc .plh small').textContent})")
        ticks = pg.evaluate(f"__haps.slice({n0}).filter(k=>k==='selection').length")
        pg.mouse.up(); time.sleep(.3)
        back = pg.evaluate("({on:document.querySelector('.plc').classList.contains('on'),txt:document.querySelector('.plc .plh small').textContent,modal:$('#modal').classList.contains('on')})")
        print(tag, "bar scrub:", rd, "ticks:", ticks, "after:", back)
        if not rd["on"] or rd["sel"] != 1 or "Week of" not in rd["txt"] or ticks < bars: bad(f"{tag}: scrubbing the bars didn't follow with a readout and a tick per bar: {rd} {ticks}")
        if back["on"] or "Last" not in back["txt"] or back["modal"]: bad(f"{tag}: releasing a drag didn't restore the total (or opened a sheet): {back}")
        pg.mouse.click(bx["x"] + bx["width"] * .9, y); time.sleep(.6)
        sh = pg.evaluate("({on:$('#modal').classList.contains('on'),h:(document.querySelector('#sheet h3')||{}).textContent,rows:document.querySelectorAll('#sheet .blist .hrow2').length})")
        print(tag, "bar tap:", sh)
        if not sh["on"] or "Week of" not in (sh["h"] or "") or sh["rows"] < 1: bad(f"{tag}: tapping a bar didn't open its bets: {sh}")
        pg.evaluate("closeModal()"); time.sleep(.4)
        pg.locator(".plc .rng2 button", has_text="Day").click(); time.sleep(.5)
        dy = pg.evaluate("({r:S.plr,h:document.querySelector('.plc').previousElementSibling.textContent,n:document.querySelectorAll('.plc rect.brc').length,wired:!!document.querySelector('[data-scrub=pl]')._wired})")
        print(tag, "day:", dy)
        if dy["r"] != "day" or "day" not in dy["h"] or dy["n"] < 1 or not dy["wired"]: bad(f"{tag}: the Day range didn't take: {dy}")
        pg.locator(".plc .rng2 button", has_text="Week").click(); time.sleep(.3)
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{tag}: Results scrolls sideways")
        # ---- Build: the panel-shaped skeleton while it loads
        pg.evaluate("S.build=null;S.view='build';renderBuild()")
        if not pg.evaluate("!!document.querySelector('#main .card.hsk')"): bad(f"{tag}: Build has no panel skeleton while loading")
        print(tag, "errs:", errs)
        if errs: bad(f"{tag}: JS errors {errs[:3]}")
        ctx.close()

    # reduced motion: the big hit shows the amount straight away, no rings, no confetti
    ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", reduced_motion="reduce", has_touch=True)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script("window.__haps=[]")
    pg.goto(B + "/app"); time.sleep(3)
    pg.evaluate("bigWin({t:'X',label:'Big',pays:500,cost:5})"); time.sleep(.2)
    rm = pg.evaluate("({amt:document.querySelector('.bigwin .amt').textContent,ring:getComputedStyle(document.querySelector('.bigwin .ring2')).display,conf:!!document.querySelector('.confetti')})")
    print("reduced motion big hit:", rm, errs)
    if rm["amt"] != "$500" or rm["ring"] != "none" or rm["conf"] or errs: bad(f"reduced motion: the big hit still animates: {rm}")
    ctx.close(); br.close()

try: os.remove(os.path.join("wahome", "combo_autosell_log.jsonl"))
except OSError: pass
print("PROBLEMS: " + " | ".join(problems) if problems else "all makeover phase 2 checks passed")
