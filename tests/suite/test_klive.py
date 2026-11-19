"""Live scores for tennis, EuroLeague and UFC (Kalshi's public live data, display only) on the real web app: the Live
data carries them, the Live page shows sets/games/points, quarters and clock, a fight's round, 'Not started yet' for a
match running late, and the game sheet says where the score came from. Kalshi is faked from real response shapes."""
import sys, os, time, threading, json, copy
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
FX = json.load(open("fixtures/kalshi_live.json"))
LIVE = {x["milestone_id"]: x for x in FX["live_datas"]}


def ms_for(event, mid=None):
    if event in FX["milestones_by_event"]:
        return copy.deepcopy(FX["milestones_by_event"][event])
    m = copy.deepcopy(FX["milestones_extra"][mid])
    m["primary_event_tickers"] = m["related_event_tickers"] = [event]
    return [m]


MS = {"KXATPMATCH-26NOV19DEBBLA": ms_for("KXATPMATCH-26NOV19DEBBLA", "ab815e1a-4c83-45d2-a39e-47d093719fd5"),
      "KXATPMATCH-26NOV19RATWAR": ms_for("KXATPMATCH-26NOV19RATWAR", "9eb53e5e-8968-4b2f-8c54-5a8998bd008a"),
      "KXEUROLEAGUEGAME-26NOV190330ADEILL": ms_for("KXEUROLEAGUEGAME-26NOV190330ADEILL", "9c500ee8-1afb-56c0-90b0-0b6a078cbf8a"),
      "KXUFCFIGHT-26NOV14GANHOK": ms_for("KXUFCFIGHT-26NOV14GANHOK")}
LIVE["9c500ee8-1afb-56c0-90b0-0b6a078cbf8a"]["details"].update(match_status="ThirdQuarter", period=3, period_remaining_time="04:18", clock_running=True)
KCALLS = []
base_get = requests.get


def kl_get(url, params=None, **k):
    if "kalshi" in url and ("/milestones" in url or "/live_data" in url):
        KCALLS.append((url, dict(k.get("headers") or {})))
        if "/milestones" in url:
            return R({"milestones": MS.get((params or {}).get("related_event_ticker"), []), "cursor": ""})
        return R({"live_datas": [LIVE[i] for i in (params or {}).get("milestone_ids") or [] if i in LIVE]})
    return base_get(url, params=params, **k)


requests.get = kl_get
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine


def L(t):
    ev = t.rsplit("-", 1)[0]
    return {"ticker": t, "event_ticker": ev, "event": ev, "side": "yes"}


bets = [{"ticker": "KXMVE-T1", "legs": [L("KXATPMATCH-26NOV19DEBBLA-DEB"), L("KXEUROLEAGUEGAME-26NOV190330ADEILL-ADE")], "cost": 3.0, "pays": 12.0,
         "status": "pending", "back": 0, "week": "2026-11-19", "full_pays": 12.0, "lg": "mix", "lgs": ["tennis", "euroleague"]},
        {"ticker": "KXMVE-T2", "legs": [L("KXUFCFIGHT-26NOV14GANHOK-GAN")], "cost": 2.0, "pays": 5.0,
         "status": "pending", "back": 0, "week": "2026-11-19", "full_pays": 5.0, "lg": "ufc", "lgs": ["ufc"]},
        {"ticker": "KXMVE-T3", "legs": [L("KXATPMATCH-26NOV19RATWAR-RAT")], "cost": 2.0, "pays": 4.0,
         "status": "pending", "back": 0, "week": "2026-11-19", "full_pays": 4.0, "lg": "tennis", "lgs": ["tennis"]}]
NAMES = {"KXATPMATCH-26NOV19DEBBLA-DEB": "Debru", "KXEUROLEAGUEGAME-26NOV190330ADEILL-ADE": "Adelaide",
         "KXUFCFIGHT-26NOV14GANHOK-GAN": "Ciryl Gane", "KXATPMATCH-26NOV19RATWAR-RAT": "Rathi"}
state = {}


def load():
    A = real_load()
    state["A"] = A
    A.fetch_account = lambda max_age=60, every_league=False: (bets, 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    now = time.time()
    for t, nm in NAMES.items():
        ev = t.rsplit("-", 1)[0]
        A.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - (20 if "RATWAR" in t else 50) * 60))
        A.PICK_NAME[t] = nm
        A.MARKET_INFO[t] = {"status": "open", "exp": "", "live": None, "name": nm}
    return A


W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); time.sleep(3)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright


def until(pg, js, secs=12):
    end = time.time() + secs
    while time.time() < end:
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        time.sleep(.2)
    return False


with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, tag in ((390, 844, "phone"), (1280, 900, "desk")):
        pg = br.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=2, color_scheme="dark")
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(B + "/app")
        if not until(pg, "!!(S.live&&S.live.combos&&S.live.combos.length>=3)", 40):
            print("PROBLEMS: Live never loaded the test combos")
        legs = pg.evaluate("Object.fromEntries(S.live.combos.flatMap(c=>c.legs).map(l=>[l.ticker,{sc:l.sc,src:l.src,note:l.note,phase:l.phase,state:l.state,score:l.score}]))")
        deb = legs.get("KXATPMATCH-26NOV19DEBBLA-DEB") or {}
        print(tag, "tennis leg:", deb)
        if not (deb.get("sc") and deb["src"] == "kalshi" and deb["sc"]["detail"] == "Set 1 · 0–2 · 40–15 · serving"):
            print("PROBLEMS: live tennis leg has no Kalshi score (set, games, points, server)")
        if "no live score" in (deb.get("note") or ""):
            print("PROBLEMS: tennis still says 'no live score' while Kalshi has one")
        ade = legs.get("KXEUROLEAGUEGAME-26NOV190330ADEILL-ADE") or {}
        print(tag, "EuroLeague leg:", ade)
        if not (ade.get("sc") and (ade["sc"]["me"], ade["sc"]["opp"]) == (26, 23) and ade["sc"]["detail"] == "Q3 4:18"):
            print("PROBLEMS: EuroLeague leg has no score/quarter/clock")
        gan = legs.get("KXUFCFIGHT-26NOV14GANHOK-GAN") or {}
        print(tag, "UFC leg:", gan)
        if gan.get("sc") or gan.get("phase") != "over" or "Decision" not in (gan.get("note") or ""):
            print("PROBLEMS: finished UFC fight should say it's over and how, with no made-up score")
        rat = legs.get("KXATPMATCH-26NOV19RATWAR-RAT") or {}
        print(tag, "late tennis leg:", rat)
        if rat.get("phase") != "waiting" or not (rat.get("note") or "").startswith("Not started yet"):
            print("PROBLEMS: a match Kalshi says hasn't begun should read 'Not started yet', not live")
        if any(set(h) - {"Accept"} for _, h in KCALLS) or not KCALLS:
            print("PROBLEMS: Kalshi live-data calls missing or carrying more than an Accept header", KCALLS[:2])
        # the page itself
        pg.evaluate("go('live')"); time.sleep(1.5)
        txt = pg.evaluate("document.body.innerText")
        for want in ("0–2 · 40–15", "Q3 4:18", "fight over", "not started yet"):
            if want.lower() not in txt.lower():
                print(f"PROBLEMS: Live page doesn't show '{want}'")
        if rat.get("sc"):
            print("PROBLEMS: a match that hasn't begun shows a 0–0 score")
        if "no live score" in txt:
            print("PROBLEMS: Live page still says 'no live score' for a sport Kalshi covers")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
            print("PROBLEMS: sideways scroll on live")
        pg.screenshot(path=f"klive_live_{tag}.png")
        # the Games page: tiles show the score for games under way, 'Not started yet' isn't counted as live
        pg.evaluate("go('games')")
        if not until(pg, "document.body.innerText.includes('Q3 4:18')", 20):
            print("PROBLEMS: Games page doesn't show the EuroLeague score and clock")
        gt = pg.evaluate("document.body.innerText")
        if "Set 1 · 0–2" not in gt:
            print("PROBLEMS: Games page doesn't show the tennis set")
        playing = pg.evaluate("[...document.querySelectorAll('h2')].map(h=>h.innerText)")
        print(tag, "games headings:", playing)
        if not any(h.lower().startswith("finished") for h in playing) or not any(h.lower().startswith("playing now\n2") or h.lower().replace("\n", " ").startswith("playing now 2") for h in playing):
            print("PROBLEMS: the finished fight should sit under Finished, with 2 playing now")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
            print("PROBLEMS: sideways scroll on games")
        pg.screenshot(path=f"klive_games_{tag}.png")
        pg.evaluate("go('live')"); time.sleep(1)
        # the game sheet says where the score came from
        pg.evaluate("openGame('KXATPMATCH-26NOV19DEBBLA-DEB')")
        if not until(pg, "!!document.querySelector('#sheet .board2')", 15):
            print("PROBLEMS: game sheet didn't open")
        sh = pg.evaluate("(document.querySelector('#sheet')||{}).innerText||''")
        print(tag, "sheet:", sh.replace("\n", " | ")[:200])
        if "score from Kalshi" not in sh or "Set 1" not in sh:
            print("PROBLEMS: game sheet doesn't show the Kalshi score and its source")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"):
            print("PROBLEMS: sideways scroll with the game sheet open")
        time.sleep(1.2)
        pg.screenshot(path=f"klive_sheet_{tag}.png")
        print(tag, "errs:", errs)
        pg.close()
    br.close()
