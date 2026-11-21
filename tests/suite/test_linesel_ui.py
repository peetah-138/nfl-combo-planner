# Spreads & totals on Build (issue #117 B): recommendation cards only (never the old table of every strike), each with
# the game, the pick, price vs fair, the edge after the fee, the route to profit, the stake that fills and the expected
# dollars; the plain empty state; and Results' 'your bar and the close' table. Phone size, dark; fakes only.
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
now = time.time()
REC = [{"ticker": "KXNBASPREAD-26NOV21LALBOS-BOS3", "event": "KXNBASPREAD-26NOV21LALBOS", "kind": "spread", "rec": True,
        "pick": "Celtics win by 3.5+", "game": "Lakers at Celtics", "p": 0.45, "fair": 0.53, "edge": 0.0627, "min_edge": 0.04,
        "stake": 14.6, "n": 31, "per": 0.4673, "exp": 2.31, "hold_exp": 2.03, "depth": 400, "capped": "stake",
        "p_exit": 0.58, "win": 0.53, "route": "sell", "line": 3.5, "book_line": -4.5, "kick": now + 7200},
       {"ticker": "KXNBATOTAL-26NOV21LALBOS-220", "event": "KXNBATOTAL-26NOV21LALBOS", "kind": "total", "rec": True,
        "pick": "Over 220.5 (Lakers at Celtics)", "game": "Lakers at Celtics", "p": 0.30, "fair": 0.37, "edge": 0.0553,
        "min_edge": 0.045, "stake": 9.6, "n": 30, "per": 0.32, "exp": 1.5, "hold_exp": 1.5, "depth": 30, "capped": "depth",
        "p_exit": 0.2, "win": 0.37, "route": "hold", "line": 220.5, "book_line": 221.5, "kick": now + 7200}]


def load():
    A = real_load()
    A.line_recommend = lambda code, now=None: ([dict(x) for x in REC], {"priced": 40, "skipped": {"route": 3}}) if code == "nba" \
        else ([], {"priced": 0, "skipped": {}})
    return A


W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme="dark")
    pg.add_init_script(__import__("upwait").COUNT_FETCHES)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/app"); pg.wait_for_function("typeof S==='object'", timeout=60000)
    pg.evaluate("localStorage.removeItem('cw_bsec');S.bsec={};S.lg='nba';try{localStorage.setItem('cw_lg','nba')}catch(e){}")
    __import__("upwait").go_and_hold(pg, "build")
    try:
        pg.wait_for_function("S.build&&S.build.lg==='nba'&&(S.build.lines||[]).length===2", timeout=60000)
    except Exception:
        print("PROBLEMS: the Build API never carried the recommended spreads/totals:", pg.evaluate("S.build&&{lg:S.build.lg,n:(S.build.lines||[]).length}"))
    pg.evaluate("S.adv=true;renderBuild()")
    pg.wait_for_function("document.querySelectorAll('.lrec').length===2", timeout=15000)
    n = pg.evaluate("document.querySelectorAll('.lrec').length")
    txt = pg.locator(".lrec").first.inner_text(); txt2 = pg.locator(".lrec").nth(1).inner_text()
    print("cards:", n, "|", txt.replace("\n", " / ")[:300])
    if pg.locator(".lrow2").count():
        print("PROBLEMS: the old table of every strike is still drawn")
    for want in ("Lakers at Celtics", "Celtics win by 3.5+", "+$2.31", "45¢", "53%", "6.3¢", "Likely to cash out early for a profit: 58%", "$15", "31 contracts"):
        if want.lower() not in txt.lower():
            print("PROBLEMS: the first card is missing", repr(want))
    for want in ("Profit if it holds: 37% to win", "all Kalshi has inside the edge", "Your bar here: 4.5¢"):
        if want not in txt2:
            print("PROBLEMS: the second card is missing", repr(want))
    if pg.evaluate("[...document.querySelectorAll('.lrec .ret')].map(e=>e.textContent)")[0].find("+$2.31") < 0:
        print("PROBLEMS: expected dollars aren't on the card's corner")
    if pg.evaluate("document.documentElement.scrollWidth>window.innerWidth+1"):
        print("PROBLEMS: sideways scroll on a phone")
    h = pg.evaluate("Math.min(...[...document.querySelectorAll('.lrec .btn')].map(b=>b.getBoundingClientRect().height))")
    if h < 44:
        print("PROBLEMS: the card's button is under 44 pt:", h)
    pg.locator(".lrec").first.scroll_into_view_if_needed(); pg.screenshot(path="linesel_cards.png")
    # best bets: a recommended strike ranks by its expected return, with its route
    bb = pg.evaluate("bestBets(S.build).filter(b=>b.k==='line').map(b=>Math.round(b.score*1000))")
    if bb != [round(2.31 / 14.6 * 1000), round(1.5 / 9.6 * 1000)] and sorted(bb) != sorted([round(2.31 / 14.6 * 1000), round(1.5 / 9.6 * 1000)]):
        print("PROBLEMS: best bets don't score spreads/totals by expected dollars per dollar:", bb)
    # empty state: checked, nothing clears
    pg.evaluate("S.build=Object.assign({},S.build,{lines:[],lines_priced:40});renderBuild()")
    e = pg.locator(".lempty")
    if not e.count() or "No spread or total clears your bar right now." not in e.inner_text() or "40 checked" not in e.inner_text():
        print("PROBLEMS: the empty state isn't shown plainly:", e.inner_text() if e.count() else None)
    if pg.locator(".lrec").count():
        print("PROBLEMS: cards drawn with nothing recommended")
    pg.screenshot(path="linesel_empty.png")
    pg.evaluate("S.build=Object.assign({},S.build,{lines:[],lines_priced:0});renderBuild()")
    if pg.locator(".lempty").count() or pg.locator(".sech[data-k='lines']").count():
        print("PROBLEMS: a sport with no spread/total markets still shows the section")
    # Results: your bar and the close
    html = pg.evaluate("""lineSel([{lg:'nba',name:'NBA',kind:'spread',bar:.045,src:'sport',why:'strikes just over 4.0¢ lost $12.00 ($1 each) over 12 games',clv_n:52,clv:-.012,blocked:['far above']},
                                  {lg:'nhl',name:'NHL',kind:'total',bar:.04,src:'start',why:null,clv_n:0,clv:null,blocked:[]}])""")
    for want in ("your bar and the close", "4.5¢", "borrowed from its sport", "−1.2¢", "far above", "the starting bar", "none"):
        if want not in html:
            print("PROBLEMS: Results' bar table is missing", repr(want))
    if pg.evaluate("lineSel([])") != "" or pg.evaluate("lineSel(null)") != "":
        print("PROBLEMS: an empty bar table should draw nothing")
    print("errs:", errs)
    br.close()
