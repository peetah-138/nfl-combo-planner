"""Issue #91: Results "Profit by day" AND "Profit by week" group each bet by when the money moved
(cash-out / settlement), not the game/slate date. This page test boots the web app with a combo that
was CASHED OUT early (game Sunday Nov 22, cashed out Wed Nov 18) and checks end to end that:
 - the api_results "day" and "week" come from the Nov 18 cash-out, not the Nov 22 game date;
 - tapping a day/week bar's sheet shows the buy date and the cash-out date, so the grouping explains itself.
Display only: the bet, its P/L and all buy/sell logic are untouched. Prints PROBLEMS on any failure."""
import sys, os, time, threading, json, datetime as dt
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine


def local_ts(y, m, d, hh=14):
    return time.mktime(dt.datetime(y, m, d, hh, 0, 0).timetuple())


EV = "KXNFLGAME-26NOV22BUFKC"              # a Sunday Nov 22 NFL game (week_of -> 2026-11-22)
LEG = {"ticker": EV + "-KC", "event_ticker": EV, "event": EV, "side": "yes"}
CASH_TS = local_ts(2026, 11, 18)          # cashed out the Wednesday before the game
BUY_DAY = "2026-11-10"
# A cashed-early NFL combo (dates from Nov 18), plus a won and a lost one in other weeks for extra bars.
bets = [
 {"ticker": "KXMVE-CASH", "legs": [dict(LEG)], "cost": 15.0, "pays": 0, "status": "cashed", "back": 99.0,
  "week": "2026-11-22", "cashed_at": CASH_TS, "settled_at": None, "full_pays": 0, "lg": "nfl", "lgs": ["nfl"]},
 {"ticker": "KXMVE-WON", "legs": [dict(LEG)], "cost": 5.0, "pays": 14.0, "status": "won", "back": 0,
  "week": "2026-11-22", "cashed_at": None, "settled_at": local_ts(2026, 11, 22), "full_pays": 14,
  "lg": "nfl", "lgs": ["nfl"]},
 {"ticker": "KXMVE-LOST", "legs": [dict(LEG)], "cost": 5.0, "pays": 10.0, "status": "lost", "back": 0,
  "week": "2026-11-15", "cashed_at": None, "settled_at": local_ts(2026, 11, 15), "full_pays": 10,
  "lg": "nfl", "lgs": ["nfl"]}]


def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: (bets, 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    # Give the cashed combo a buy date (bought) the way the real flow records first_seen in the bets DB.
    # Open the store at the same path webapp_main will use (store_open is idempotent) so the row is there
    # when api_results reads first_seen.
    try:
        A.store_open(os.path.join(os.environ["COMBOWATCH_HOME"], "combo_history.db"))
        A.store_x("insert or replace into bets(combo, first_seen, cost, pays, legs, sports, status) "
                  "values(?,?,?,?,?,?,?)", ("KXMVE-CASH", local_ts(2026, 11, 10), 15.0, 0.0, "[]", "nfl", "cashed"))
    except Exception as err:
        print("seed bought:", err, flush=True)
    return A


W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
problems = []
bad = lambda m: problems.append(m)


def wait(pg, js, secs=10):
    t = time.time()
    while time.time() - t < secs:
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        time.sleep(.2)
    return False


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/app"); time.sleep(3)

    # ---- the api_results payload: day and week bucket by the Nov 18 cash-out, not the Nov 22 game ----
    pg.evaluate("go('results')")
    if not wait(pg, "!!(S.res&&S.res.history)", 15):
        bad("Results didn't load")
    res = pg.evaluate("S.res") or {}
    hist = {h["t"]: h for h in (res.get("history") or [])}
    weeks = res.get("weeks") or []
    cash = hist.get("KXMVE-CASH")
    print("cashed hist row:", {k: cash.get(k) for k in ("day", "week", "bought", "cashed")} if cash else None)
    if not cash:
        bad("the cashed combo is missing from the Results history")
    else:
        if cash["day"] != "2026-11-18":
            bad(f"the cashed combo's day is not its Nov 18 cash-out: {cash['day']}")
        if cash["week"] != "2026-11-22":
            bad(f"the cashed combo's week isn't the realized week (Sunday of Nov 18): {cash['week']}")
        if cash.get("cashed") != "2026-11-18":
            bad(f"the cashed combo doesn't carry its cash-out date for the sheet: {cash.get('cashed')}")
        if cash.get("bought") != BUY_DAY:
            bad(f"the cashed combo doesn't carry its buy date for the sheet: {cash.get('bought')}")
    # The won bet settled Nov 22; its week is the Nov 22 week. No bet should sit in a week keyed by a game
    # that nobody's money moved in before it settled -- i.e. the weeks must be realized weeks.
    wkeys = {w["week"] for w in weeks}
    print("week keys:", sorted(wkeys))
    if "2026-11-22" not in wkeys:
        bad(f"the Nov 22 realized week bar is missing: {sorted(wkeys)}")

    # ---- the detail sheet: tap a day bar and confirm it shows the buy date and the cash-out date ----
    if not wait(pg, "!!document.querySelector('[data-scrub=pl]')", 15):
        bad("the profit chart didn't draw")
    pg.locator(".plc .rng2 button", has_text="Day").click(); time.sleep(.6)
    # open the Nov 18 day bar's sheet via barSheet on its bucket (robust against bar geometry)
    pg.evaluate("(()=>{const bars=plBars(S.res);const b=bars.find(x=>x.k==='2026-11-18');if(b)barSheet(b);})()")
    time.sleep(.6)
    sheet = pg.evaluate("(()=>{const s=document.querySelector('#sheet');return s?s.innerText:'';})()")
    print("day sheet text:", json.dumps(sheet[:400]))
    if not pg.evaluate("$('#modal').classList.contains('on')"):
        bad("tapping the Nov 18 day bar didn't open a sheet")
    if "Cashed out" not in sheet:
        bad(f"the day detail sheet doesn't show the cash-out date: {sheet[:200]}")
    if "Bought" not in sheet:
        bad(f"the day detail sheet doesn't show the buy date: {sheet[:200]}")
    pg.evaluate("closeModal()"); time.sleep(.3)

    # ---- the same transparency in the WEEK detail sheet ----
    pg.locator(".plc .rng2 button", has_text="Week").click(); time.sleep(.5)
    pg.evaluate("(()=>{const bars=plBars(S.res);const b=bars.find(x=>x.k==='2026-11-22');if(b)barSheet(b);})()")
    time.sleep(.6)
    wsheet = pg.evaluate("(()=>{const s=document.querySelector('#sheet');return s?s.innerText:'';})()")
    print("week sheet text:", json.dumps(wsheet[:400]))
    if "Cashed out" not in wsheet or "Bought" not in wsheet:
        bad(f"the week detail sheet doesn't show the buy and cash-out dates: {wsheet[:200]}")
    pg.evaluate("closeModal()"); time.sleep(.3)

    if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
        bad("Results scrolls sideways on a phone")
    print("errs:", errs)
    if errs:
        bad(f"JS errors {errs[:3]}")
    ctx.close(); br.close()

print("PROBLEMS: " + " | ".join(problems) if problems else "all real-date (issue #91) checks passed")
