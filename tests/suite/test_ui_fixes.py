# CHECK: group=page secs=61
import sys, os, time, threading, re, json
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


def leg(name, sp, phase="", note="", short="", state="live", res=None):
    return {"ticker": "X-" + name, "name": name, "res": res, "state": state, "sport": sp, "phase": phase, "note": note, "short": short, "chance": .5, "live": None}


def combo(i, legs, sp="tennis", group="pending"):
    return {"t": f"C{i}", "label": f"Combo {i}", "group": group, "cost": 3, "pays": 12, "back": 0, "full": 12, "sports": [sp], "legs": legs,
            "preview": "", "week": "2026-11-18", "sort": i, "p": .25, "live": True, "verdict": "hold", "offer": 2.5}


CS = [combo(1, [leg("Novak Djokovic", "tennis", "probably_over", "Probably finished · started 5h 30m ago, waiting on Kalshi", "Probably over"),
                leg("Jannik Sinner", "tennis", "probably_over", "Probably finished · started 5h 30m ago, waiting on Kalshi", "Probably over")]),
      combo(2, [leg("Andrey Rublev", "tennis", "on", "Started 42 min ago · no live score", "Started 42 min ago"), leg("Suns", "nba", state="pre")])]
IDEAS = [{"id": "9001", "n": 2, "picks": "Knights + Suns", "sport": "NBA", "ts": time.time() - 60, "pct": .97, "stake": 5, "pays": 40, "fair": 41, "kick": time.time() + 3600}]
LIVE = ("S.sf={o:'all',sp:'all',sort:'new'};S.filter='all';S.live={at:Date.now()/1000,combos:" + json.dumps(CS) +
        ",riding:2,staked:6,chance_one:.5,best:24,cash_now:5,today:{},auto_sell:false,singles:[],pulse:[],ideas:[],need:[]};renderLive()")

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for W_, H, tag in ((390, 844, "phone"), (1280, 900, "desk")):
        pg = br.new_page(viewport={"width": W_, "height": H}, device_scale_factor=2, color_scheme="dark"); pg.add_init_script(__import__("upwait").COUNT_FETCHES)   # counts requests from the boot load on
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(B + "/app"); pg.wait_for_function("typeof S==='object'&&typeof go==='function'", timeout=60000)
        pg.evaluate("go('live')"); __import__("upwait").quiet(pg, "S.view==='live'&&!!S.live", 40)   # was fixed 3 s + 4 s
        # ---- #26: no header menu, no classic screens, Reload lives in Settings
        html = pg.content()
        menus = pg.locator(".menu, #menu, [onclick*=menuSheet]").count()
        print(tag, "menu buttons:", menus, "| classic text:", "Classic screens" in html)
        if menus or "Classic screens" in html or "menuSheet" in html: print("PROBLEMS: header menu / classic screens still there")
        if pg.evaluate("typeof menu!=='undefined'||typeof menuSheet!=='undefined'||typeof admin!=='undefined'"): print("PROBLEMS: menu code still defined")
        r = pg.evaluate("fetch('/app/classic').then(r=>r.status)"); print(tag, "/app/classic status:", r)
        if r == 200: print("PROBLEMS: /app/classic still served")
        pg.evaluate("go('settings')")         # wait for Settings to draw (was a fixed 3 s; a slow runner needed more)
        __import__("upwait").quiet(pg, "S.view==='settings'&&document.body.innerText.includes('Reload the page')", 40)
        n = pg.get_by_text("Reload the page").count(); print(tag, "reload buttons in Settings:", n)
        if n < 1: print("PROBLEMS: no Reload the page button in Settings")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): print("PROBLEMS: sideways scroll in settings")
        # ---- #24: honest status for sports with no score source
        __import__("upwait").go_and_hold(pg, "live")   # waits for Live's own load, then holds still
        pg.evaluate(LIVE); time.sleep(1)
        t = pg.locator(".tbl").inner_text(); print(tag, "rows:", t.replace("\n", " | ")[:300])
        if "probably finished" not in t.lower(): print("PROBLEMS: finished-looking tennis combo doesn't say so")
        if "started 42 min ago" not in t.lower(): print("PROBLEMS: running tennis combo doesn't say how long")
        print(tag, "legend count:", pg.locator(".legend").count())
        if pg.locator(".legend").count():
            ly = pg.evaluate("document.querySelector('.legend').getBoundingClientRect().top"); ty = pg.evaluate("document.querySelector('.tbl').getBoundingClientRect().top")
            if ly > ty: print("PROBLEMS: legend sits below the combos instead of above")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): print("PROBLEMS: sideways scroll on live")
        # ---- #22: every toast fades, even when the page re-renders around it
        pg.evaluate("toast('Kalshi isn\\'t listing that game right now.',1500)")
        pg.evaluate("renderLive();renderLive()"); time.sleep(.4)
        on = pg.evaluate("$('#toast').classList.contains('on')"); print(tag, "toast on:", on)
        if not on: print("PROBLEMS: toast didn't show")
        for _ in range(3):
            time.sleep(.5); pg.evaluate("renderLive()")
        time.sleep(1.2)
        st = pg.evaluate("[$('#toast').classList.contains('on'), $('#toast').hidden]"); print(tag, "toast after 3.1s [on, hidden]:", st)
        if st[0] or not st[1]: print("PROBLEMS: toast never faded")
        # a stuck toast (timer lost, as iOS can do) is swept by the deadline check
        pg.evaluate("toast('stuck?',1000);clearTimeout($('#toast')._h)"); time.sleep(3.2)
        st = pg.evaluate("$('#toast').classList.contains('on')"); print(tag, "toast with lost timer still on:", st)
        if st: print("PROBLEMS: toast with a lost timer never faded")
        # tapping a toast dismisses it
        pg.evaluate("toast('tap me',30000)"); time.sleep(.9); pg.locator("#toast").click(force=True); time.sleep(.5)
        if pg.evaluate("$('#toast').classList.contains('on')"): print("PROBLEMS: tapping a toast doesn't dismiss it")
        # ---- #22: a Buy idea whose game Kalshi no longer lists turns calm and drops off
        pg.evaluate("localStorage.removeItem('cw_hide');S.ideaGone={};window.api=async()=>({ok:false,gone:true,msg:'Kalshi isn\\'t listing that game right now.'});"
                    "S.live.ideas=" + json.dumps(IDEAS) + ";renderLive()"); time.sleep(1)
        pg.locator("#ib-9001").click(); time.sleep(.8)
        g = pg.locator(".dcard.gone").count(); txt = pg.locator(".dcard.gone").inner_text() if g else ""
        print(tag, "gone card:", g, "|", txt.replace("\n", " ")[:120])
        if g != 1 or "not available" not in txt.lower(): print("PROBLEMS: unlisted idea doesn't show a calm 'not available' state")
        if pg.locator("#ib-9001").count(): print("PROBLEMS: the Buy button is still there on an unlisted idea")
        time.sleep(5.2)
        st = pg.evaluate("[!!document.querySelector('#idea-9001'), $('#toast').classList.contains('on')]"); print(tag, "after 6s [idea still listed, toast on]:", st)
        if st[0]: print("PROBLEMS: unlisted idea never dropped off the list")
        if st[1]: print("PROBLEMS: toast still on after 6s")
        pg.screenshot(path=f"uifix_{tag}.png"); print(tag, "errs:", errs)
