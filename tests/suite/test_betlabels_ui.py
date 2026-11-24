# CHECK: group=page secs=30
"""Every bet says what it is on (issue #381), at phone size (390px), dark and light: the Live tab's single bets, the game
page's header and "Your bets on this game" rows, and the Games card all show both teams and plain-English bets (total
points on totals, the team name on spreads and moneylines), and a game that can't be named says "game not found".
No horizontal scroll. Prints PROBLEMS only on failure."""
import time
TOT, SPR, SPN_, KS = "KXNCAAMBTOTAL-26NOV23DUKEUNC-144", "KXNCAAMBSPREAD-26NOV23DUKEUNC-DUKE7", "KXNCAAMBSPREAD-26NOV23DUKEUNC-UNC1", "KXNCAAMBTOTAL-26NOV23KANSGONZ-151"
def _s(t, kind, side, label, name="", opp="", game=None):
    return {"t": t, "ticker": t, "name": name or label, "opp": opp, "live": None, "sc": None, "on": False, "src": "", "kind": kind,
            "sport": "ncaamb", "side": side, "label": label, "game": label if game is None else game, "event": t.rsplit("-", 1)[0], "n": 10,
            "cost": 6.0, "pays": 10.0, "worth": 4.5, "chance": .49, "state": "pre", "res": None, "score": "", "starts": "Today 7:00 PM",
            "note": "", "phase": "", "short": "", "how": "", "url": "", "self": False, "sell_at": None}
SINGLES = [_s(TOT, "total", "yes", "Over 144.5 points"),
           _s(SPR, "spread", "no", "Duke wins by over 6.5 points", "Duke", "UNC", "Duke Spread"),
           _s(SPN_, "spread", "yes", "UNC wins by over 0.5 points", "UNC", "Duke", "UNC Spread"),
           _s(KS, "total", "no", "Over 151.5 points")]
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0].replace(
    "    A.fetch_results = lambda t: {}\n", "    A.fetch_results = lambda t: {}\n    A.open_singles = lambda max_age=30: [dict(x) for x in SINGLES]\n", 1))
problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def need(txt, *want, where=""):
    for w in want:
        if w not in txt: bad(f"{where}: missing {w!r} in {txt[:300]!r}")
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=scheme, has_touch=True, is_mobile=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(B + "/app"); time.sleep(2.5)
        pg.evaluate("go('live')")
        for _ in range(50):
            if pg.evaluate("!!document.querySelector('.stbl .srow1')"): break
            time.sleep(.2)
        live = pg.evaluate("document.querySelector('.stbl').innerText")
        need(live, "Over 144.5 total points", "Duke vs UNC", "UNC +6.5 (loses by 6 or fewer, or wins)", "UNC -0.5", "Under 151.5 total points", "game not found", where=f"{scheme} Live")
        if "Over 144.5 points" in live: bad(f"{scheme} Live still shows the bare 'Over 144.5 points'")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth"): bad(f"{scheme} Live scrolls sideways at 390px")
        pg.evaluate(f"openGame('{TOT}')"); time.sleep(3)
        sheet = pg.evaluate("document.querySelector('#sheet').innerText")
        need(sheet, "Game: Duke vs UNC", "Your bet: Over 144.5 total points", "UNC +6.5 (loses by 6 or fewer, or wins)", where=f"{scheme} game page")
        title = pg.evaluate("document.querySelector('#modal').innerText.slice(0,120)")
        if "Duke vs UNC" not in title: bad(f"{scheme} game page title lacks the matchup: {title!r}")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth || document.querySelector('#sheet').scrollWidth>document.querySelector('#sheet').clientWidth+1"):
            bad(f"{scheme} game page scrolls sideways at 390px")
        if not pg.evaluate("document.querySelectorAll('#sheet [data-sss]').length>=3"): bad(f"{scheme} Sell buttons changed or vanished")
        pg.evaluate("closeModal()"); time.sleep(.5)
        pg.evaluate(f"openGame('{KS}')"); time.sleep(3)
        need(pg.evaluate("document.querySelector('#sheet').innerText"), "Under 151.5 total points", "game not found", where=f"{scheme} unresolved game page")
        pg.evaluate("closeModal()"); time.sleep(.4)
        pg.evaluate("go('games')"); time.sleep(2.5)
        games = pg.evaluate("document.querySelector('#main').innerText")
        need(games, "Duke vs UNC", "Over 144.5 total points", where=f"{scheme} Games")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth"): bad(f"{scheme} Games scrolls sideways at 390px")
        if errs: bad(f"{scheme} page errors: {errs[:2]}")
        ctx.close()
    br.close()
if problems: print("PROBLEMS", len(problems))
else: print("betlabels ui: all good")
