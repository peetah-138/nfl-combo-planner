# Games already under way in the daily panel (Pete's call): eligible when priced live from a fresh score (never the
# pre-game price), the switch, buying with a fresh recheck, Kalshi refusals are skips, finished games never bought.
import os, time, tempfile, importlib.util, json
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
import datetime as _dt; _u = _dt.datetime.now(_dt.timezone.utc); E.PACIFIC = _dt.timezone(_dt.timedelta(hours=round(12 - _u.hour - _u.minute / 60)))
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp(); E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.REBUILD_FLAG = os.path.join(E.HERE, "flag"); E.HELD_FILE = os.path.join(E.HERE, "held.json")
E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.fetch_account = lambda **k: ([], 300.0, None)
E.account_events = lambda *a, **k: set()
E.fetch_scores = lambda *a, **k: None                       # no network: the tests set the score cache themselves
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
day = E.ticker_day("KXNBAGAME-" + time.strftime("%y%b%d", time.gmtime()).upper() + "BOSNYK") or _dt.date.today()
tag = day.strftime("%y%b%d").upper()


def game(home, away, p_home, p_away, bid_gap=0.02, kick=None, sport="NBA"):
    ev = f"KX{sport}GAME-{tag}{away}{home}"
    E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(kick if kick is not None else now - 3600))
    return ev, [{"ticker": f"{ev}-{home}", "event": ev, "pick": home, "p": p_home, "bid": p_home - bid_gap, "src": "Pinnacle",
                 "fair": 0.5, "abbr": home},
                {"ticker": f"{ev}-{away}", "event": ev, "pick": away, "p": p_away, "bid": p_away - bid_gap, "src": "Pinnacle",
                 "fair": 0.5, "abbr": away}]


def score(sport, ev, home, away, hs, as_, frac, state="in", at=None):
    by = (E.SCORES_BY.get(sport) or {}).get("by") or {}
    for me, op, a, b in ((home, away, hs, as_), (away, home, as_, hs)):
        by["@" + me] = [{"frac": frac, "me": a, "opp": b, "abbr": me, "opp_abbr": op, "opp_name": "@" + op, "state": state,
                         "detail": "Q3 5:00", "start": "", "sport": sport, "game": ev, "day": day, "wp": None, "brk": False}]
    E.SCORES_BY[sport] = {"at": now if at is None else at, "by": by}


def closing(t, fair, kick=None):
    E._close_table()
    E.store_x("insert or replace into closes values(?,?,?,?,?,?,?,null)", (t, "nba", t.rsplit("-", 1)[0], fair, fair, kick or now - 3600, now - 3700))


# ---- the live model
m = E.live_model_chance
ok("model: even game, level score at the start = 50%", abs(m("nba", 0.5, 0, 1.0) - 0.5) < 0.01)
ok("model: the pre-game chance at tip-off comes back", abs(m("nba", 0.7, 0, 1.0) - 0.7) < 0.01 and abs(m("nhl", 0.6, 0, 1.0) - 0.6) < 0.01)
ok("model: a 10-point lead late is nearly safe, early it isn't", m("nba", 0.5, 10, 0.05) > 0.95 and 0.6 < m("nba", 0.5, 10, 0.9) < 0.85)
ok("model: hockey, a goal up in the third is a big favourite", 0.75 < m("nhl", 0.5, 1, 0.25) < 0.95)
ok("model: soccer counts a draw as not winning", m("soccer", 0.45, 0, 0.3) < 0.45)

# ---- which games under way are eligible
E._close_table()
ev, sides = game("BOS", "NYK", 0.69, 0.33)
closing(sides[0]["ticker"], 0.55); closing(sides[1]["ticker"], 0.45)
score("nba", ev, "BOS", "NYK", 64, 60, 0.5)
games = {ev: [dict(x) for x in sides]}
live, why = E.panel_live_games(games)
x = games[ev][0]
ok("fresh score: the game under way is eligible", ev in live and x.get("live") and x.get("live_how") == "live model")
ok("its fair is the live chance, not the pre-game one", abs(x["fair"] - 0.55) > 0.05 and abs(x["fair"] - E.live_model_chance("nba", 0.55, 4, 0.5) / (E.live_model_chance("nba", 0.55, 4, 0.5) + E.live_model_chance("nba", 0.45, -4, 0.5))) < 0.02)
ok("both sides add up to 100%", abs(sum(s["fair"] for s in games[ev]) - 1) < 0.002)
score("nba", ev, "BOS", "NYK", 64, 60, 0.5, at=now - E.LIVE_SCORE_AGE - 5)
g2 = {ev: [dict(x) for x in sides]}; live, why = E.panel_live_games(g2)
ok("stale score: not eligible", ev not in live and "fresh" in why.get(ev, "") and not g2[ev][0].get("live"))
E.SCORES_BY.pop("nba")
g2 = {ev: [dict(x) for x in sides]}; live, why = E.panel_live_games(g2)
ok("no score: not eligible", ev not in live)
score("nba", ev, "BOS", "NYK", 101, 90, 0.0, state="post")
g2 = {ev: [dict(x) for x in sides]}; live, why = E.panel_live_games(g2)
ok("finished game: never eligible", ev not in live and "over" in why.get(ev, ""))
score("nba", ev, "BOS", "NYK", 64, 60, 0.5)
g2 = {ev: [dict(x, bid=x["p"] - 0.1) for x in sides]}; live, why = E.panel_live_games(g2)
ok("jumpy live price (wide gap): not eligible", ev not in live and "jumpy" in why.get(ev, ""))
g2 = {ev: [dict(sides[0], p=0.95, bid=0.93), dict(sides[1], p=0.07, bid=0.05)]}; live, why = E.panel_live_games(g2)
ok("Kalshi far from the live chance: left out, not a bargain", ev not in live and "disagree" in why.get(ev, ""))
E.store_x("delete from closes")
g2 = {ev: [dict(x) for x in sides]}; live, why = E.panel_live_games(g2)
ok("no pre-game line to start from: not eligible", ev not in live and "pre-game" in why.get(ev, ""))
closing(sides[0]["ticker"], 0.55); closing(sides[1]["ticker"], 0.45)
eev, esides = game("RMA", "BAR", 0.6, 0.42, sport="EUROLEAGUE")
g2 = {eev: esides}; live, why = E.panel_live_games(g2)
ok("EuroLeague under way: excluded (no score feed we trust), and says why", eev not in live and "EuroLeague" in why.get(eev, ""))
ok("the reason is shown in Results", "EuroLeague" in E.LIVE_EXCLUDED_WHY and "tennis" in E.LIVE_EXCLUDED_WHY)
x = dict(sides[0], fair=0.7, line_live=True, line_at=now - 30)
f, how, _ = E.live_side_fair(x)
ok("a fresh live sportsbook line is used when there is one", how == "live sportsbook line" and f == 0.7)
f, how, _ = E.live_side_fair(dict(x, line_at=now - E.LIVE_LINE_AGE - 5))
ok("...but not a stale one (the live model instead)", how == "live model")
f, how, _ = E.live_side_fair(dict(x, line_live=False))
ok("a pre-game line on a game under way is never the price", how == "live model" and abs(f - 0.7) > 0.01)
ok("live chances are recorded for each league's calibration", E.store_rows("select count(*) n from live_fairs")[0]["n"] >= 2)

# ---- the panel: built, approved and bought, with a fresh recheck
games = {ev: [dict(x) for x in sides]}
live, _ = E.panel_live_games(games)
bos = games[ev][0]
c = E._cand("single", "nba", [bos], bos["fair"], (bos["fair"] - bos["p"] - E.single_fee(bos["p"])) / (bos["p"] + E.single_fee(bos["p"])), "w", price=bos["p"])
ok("a candidate on a game under way is marked live", c.get("live") and c["legs"][0].get("live") and c["legs"][0].get("pre") == 0.55 and c["kick_pre"] is None)
E.KICKOFF["KXNBAGAME-PREX"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 9000))
pre_c = E._cand("single", "nba", [dict(sides[1], ticker="KXNBAGAME-PREX-NYK", event="KXNBAGAME-PREX", fair=0.6, p=0.5, live=False)], 0.6, 0.15, "w", price=0.5)
ok("a live candidate qualifies on edge like any other", E._qualifies(c) == (c["ret"] >= E.PANEL["min_edge"]))
c["ret"] = max(c["ret"], 0.06)
E.PANEL_POOL = {"nba": (now, [c, pre_c])}
E.panel_pass()
d = E.panel_get("real")
ok("the panel includes the game under way", d and any(i["id"] == c["id"] for i in d["items"]))
li = next(i for i in (d or {}).get("items", []) if i["id"] == c["id"])
ok("...bought right away: no buy time to wait for", "buy_at" not in li)
okA, msg = E.panel_approve(None, "all")
p = E.panel_get("real")
ok("approving schedules it", okA and next(i for i in p["items"] if i["id"] == c["id"])["state"] == "scheduled")
bought = []
E.book_depth = lambda t, max_age=60: {"ask": 0.66, "bid": 0.64}
E.buy_single = lambda t, n, px: (bought.append((t, n, px)) or (n, None))
E.panel_exec(paused=True, may_trade=True)
ok("Pause wins: nothing bought while paused", not bought and next(i for i in E.panel_get("real")["items"] if i["id"] == c["id"])["state"] == "scheduled")
score("nba", ev, "BOS", "NYK", 64, 60, 0.5, at=now - E.LIVE_SCORE_AGE - 5)
E.PANEL_POOL = {"nba": (time.time(), [c, pre_c])}
E.panel_exec(paused=False, may_trade=True)
it = next(i for i in E.panel_get("real")["items"] if i["id"] == c["id"])
ok("stale score at buy time: skipped, nothing bought, never 'check'", not bought and it["state"] == "skipped" and "fresh" in it.get("note", ""))
E._set_items(E._panel_day(), "real", {c["id"]: {"state": "scheduled", "note": ""}})
score("nba", ev, "BOS", "NYK", 64, 60, 0.5)
E.book_depth = lambda t, max_age=60: {"ask": 0.9, "bid": 0.88}
E.panel_exec(paused=False, may_trade=True)
it = next(i for i in E.panel_get("real")["items"] if i["id"] == c["id"])
ok("the price recheck still runs right before buying", not bought and it["state"] == "skipped" and "price" in it.get("note", ""))
E._set_items(E._panel_day(), "real", {c["id"]: {"state": "scheduled", "note": ""}})
E.book_depth = lambda t, max_age=60: {"ask": 0.6, "bid": 0.59}
E.panel_exec(paused=False, may_trade=True)
it = next(i for i in E.panel_get("real")["items"] if i["id"] == c["id"])
ok("fresh score and a good price: bought", bought and it["state"] == "bought" and it.get("live"))
ok("...with the chance worked out again just now", it["legs"][0].get("fair") and it["legs"][0].get("live"))
# a finished game is never bought
E._set_items(E._panel_day(), "real", {c["id"]: {"state": "scheduled", "note": ""}}); bought.clear()
score("nba", ev, "BOS", "NYK", 101, 90, 0.0, state="post")
E.panel_exec(paused=False, may_trade=True)
it = next(i for i in E.panel_get("real")["items"] if i["id"] == c["id"])
ok("finished game: never bought", not bought and it["state"] == "skipped")
score("nba", ev, "BOS", "NYK", 64, 60, 0.5)

# ---- a combo Kalshi won't price (e.g. a game it no longer offers for combos): a skip, never 'check'
cc = E._cand("combo", "nba", [bos, dict(games[ev][1], ticker="KXNBAGAME-OTHER-X", event="KXNBAGAME-OTHER", live=False)], 0.3, 0.1, "w", pct=1.1, fair_mult=3.3)
cc["stake"] = 5


def refuse(*a, **k):
    raise RuntimeError("Kalshi doesn't offer this exact combo")
E.get_offer = refuse
okB, note, _ = E._buy_panel_bet(cc)
ok("Kalshi refusing a combo with a game under way is a plain no-buy (skip), not unknown", okB is False and "wouldn't price" in note)

# ---- the switch
E.save_json(E.MAIN_SAVED, {"panel_live": False})
ok("switch off: read from the shared settings", not E.live_panel_on())
E.store_x("delete from panel")
E.PANEL_POOL = {"nba": (time.time(), [c, pre_c])}
E.panel_pass()
d = E.panel_get("real")
ok("switch off: the panel leaves games under way out", d and not any(i["id"] == c["id"] for i in d["items"]))
g2 = {ev: [dict(x) for x in sides]}
E.save_json(E.MAIN_SAVED, {"panel_live": True})
E.store_x("delete from panel")
E.PANEL_POOL = {"nba": (time.time(), [c, pre_c])}
E.panel_pass(); okA, _ = E.panel_approve(None, "all")
E.save_json(E.MAIN_SAVED, {"panel_live": False})
bought.clear(); E.book_depth = lambda t, max_age=60: {"ask": 0.6, "bid": 0.59}
E.panel_exec(paused=False, may_trade=True)
it = next(i for i in E.panel_get("real")["items"] if i["id"] == c["id"])
ok("switch turned off after approving: the live bet isn't bought", not bought and it["state"] == "skipped" and "switched off" in it.get("note", ""))
E.save_json(E.MAIN_SAVED, {"panel_live": True})

# ---- drafts: a live-priced bet stays while its price is fresh; an old one goes
E.store_x("delete from panel")
E.PANEL_POOL = {"nba": (time.time(), [c])}
E.panel_pass()
v = E.panel_get("view:nba")
E.prune_drafts()
ok("a fresh live-priced draft stays", E.panel_get("view:nba") is not None)
v["at"] = time.time() - E.LIVE_POOL_AGE - 30
E.store_x("update panel set body=? where mode='view:nba'", (json.dumps(v),))
E.PANEL_POOL = {}
E.prune_drafts()
ok("a stale live-priced draft is dropped", E.panel_get("view:nba") is None)
E.PANEL_POOL = {"nba": (time.time() - E.LIVE_POOL_AGE - 30, [c])}
ok("a stale live price never makes the panel", not E.build_panel()["items"])
E.LIVE_NOW["nba"] = True; E.NEXT_KICK["nba"] = None
ok("sports with a game priced live are checked every few minutes", "nba" in E.sports_near())

# ---- Results: bought-during-the-game bets are their own group, by league
E.store_x("delete from panel")
body = {"at": time.time(), "items": [dict(c, state="bought", stake=5, result="won", pl=2.5),
                                     dict(pre_c, state="bought", stake=5, result="lost", pl=-5)]}
E.store_x("insert into panel values(?,?,?,?,?)", (E._panel_day(), "real", time.time(), "approved", json.dumps(body)))
E.ANALYTICS["v"] = None
a = E.analytics(max_age=0)
ok("What's working: live-bought bets grouped by league", [(x["what"], x["n"]) for x in a.get("live", [])] == [("NBA", 1)])
ok("...with the leagues left out named", "EuroLeague" in a.get("live_excluded", ""))
