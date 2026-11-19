"""AHL live scores from the league's own public feed (ESPN has no AHL scoreboard). The network is faked."""
import os, importlib.util, datetime as dt
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)


def game(gid, day, ord_, home, hcode, hgoals, vis, vcode, vgoals, status, per, clock, short=None, long_=None, inter="0", iso=None):
    """One row shaped like the feed's scorebar (only the fields the engine reads, plus a few it ignores)."""
    return {"ID": gid, "Date": day, "Ord": ord_ + ".000000", "GameDateISO8601": iso or "", "GameStatus": status,
            "GameStatusString": "Final" if status in ("3", "4") else "7:00PM", "GameStatusStringLong": long_ or "7:00 PM EST",
            "Period": per, "PeriodNameShort": short or per, "GameClock": clock, "Intermission": inter,
            "HomeCity": home[0], "HomeNickname": home[1], "HomeLongName": f"{home[0]} {home[1]}", "HomeCode": hcode, "HomeGoals": hgoals,
            "VisitorCity": vis[0], "VisitorNickname": vis[1], "VisitorLongName": f"{vis[0]} {vis[1]}", "VisitorCode": vcode, "VisitorGoals": vgoals}


GAMES = [
    game("1", "2026-11-19", "2026-11-19 19:00:00", ("Hershey", "Bears"), "HER", "0", ("Charlotte", "Checkers"), "CLT", "0", "1", "1", "00:00",
         iso="2026-11-19T19:00:00-05:00"),                                                       # not started
    game("2", "2026-11-19", "2026-11-19 19:00:00", ("Cleveland", "Monsters"), "CLE", "2", ("Hamilton", "Hammers"), "HAM", "1", "2", "2", "07:42"),
    game("3", "2026-11-19", "2026-11-19 19:05:00", ("Wilkes-Barre/Scranton", "Penguins"), "WBS", "3", ("Syracuse", "Crunch"), "SYR", "3", "2", "4", "02:34", short="OT"),
    game("4", "2026-11-19", "2026-11-19 19:00:00", ("Hartford", "Wolf Pack"), "HFD", "1", ("Providence", "Bruins"), "PRO", "0", "2", "1", "00:00", inter="1"),
    game("5", "2026-11-18", "2026-11-18 19:00:00", ("Bakersfield", "Condors"), "BAK", "3", ("Colorado", "Eagles"), "COL", "4", "4", "4", "00:00",
         short="OT", long_="Final SO"),
    game("6", "2026-11-18", "2026-11-18 19:00:00", ("Rockford", "IceHogs"), "RFD", "2", ("Chicago", "Wolves"), "CHI", "4", "3", "3", "00:00", long_="Final"),
    game("7", "2026-11-19", "2026-11-19 21:00:00", ("Calgary", "Wranglers"), "CGY", "0", ("Coachella Valley", "Firebirds"), "CV", "0", "1", "1", "00:00",
         iso="2026-11-19T19:00:00-06:00"),                                                       # the feed's own ISO offset is an hour off here
]


class Resp:
    def __init__(self, body, ok=True):
        self.body, self.ok, self.status_code = body, ok, 200 if ok else 503

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class Net:
    """requests stand-in: records every URL; answers the AHL feed from `feed`, ESPN with no games."""
    RequestException = E._requests.RequestException

    def __init__(self):
        self.calls, self.feed = [], None

    def get(self, url, params=None, **kw):
        self.calls.append((url, dict(params or {})))
        if "hockeytech.com" in url:
            if isinstance(self.feed, Exception):
                raise self.feed
            return self.feed
        return Resp({"events": []})


net = Net(); E.requests = net
net.feed = Resp({"SiteKit": {"Scorebar": GAMES}})
E.set_league("ahl")

ok("AHL has a score feed and no ESPN path", E.SPORTS["ahl"]["feed"] == "ahl" and not E.SPORTS["ahl"]["espn"])
by = E.fetch_scores(max_age=0)
url, q = net.calls[-1]
ok("one light request to the league's public feed, no ESPN call, a few days either side",
   len(net.calls) == 1 and url == E.AHL_FEED_URL and q["client_code"] == "ahl" and q["view"] == "scorebar"
   and q["numberofdaysback"] == 1 and q["numberofdaysahead"] == 3)
ok("the engine's own cache is filled for the league and the screen's league", E.SCORES_BY["ahl"]["by"] is by and E.SCORES["by_team"] is by)

ok("every team can be found by full name, city, nickname or league code",
   all(by.get(k) for k in ("Cleveland Monsters", "cleveland", "monsters", "@CLE", "Hamilton Hammers", "wolf pack", "@HFD", "wilkesbarrescranton")))
ok("Kalshi's spelling of Charlotte (CHA) finds the feed's CLT", by["@CHA"][0]["abbr"] == "CLT" and by["@CLT"][0]["game"] == "1")

g = E.pick_game(by["Cleveland Monsters"], dt.date(2026, 11, 19))
ok("a game under way: score, period, clock, from the side asked", g["state"] == "in" and (g["me"], g["opp"]) == (2, 1)
   and g["detail"] == "P2 7:42" and g["abbr"] == "CLE" and g["opp_abbr"] == "HAM" and g["opp_name"] == "Hamilton Hammers")
v = E.pick_game(by["Hamilton Hammers"], dt.date(2026, 11, 19))
ok("the visitor sees the score its own way round", (v["me"], v["opp"]) == (1, 2) and v["game"] == g["game"])
ok("share of the game left is worked out from the period and clock", 0.3 < g["frac"] < 0.5)
o = E.pick_game(by["Wilkes-Barre/Scranton Penguins"], dt.date(2026, 11, 19))
ok("overtime reads OT and is nearly over", o["detail"] == "OT 2:34" and o["frac"] <= 0.05 and o["state"] == "in")
ok("between periods", E.pick_game(by["Hartford Wolf Pack"], dt.date(2026, 11, 19))["detail"] == "End P1")
p = E.pick_game(by["Hershey Bears"], dt.date(2026, 11, 19))
ok("not started: state pre, the start time shown, nothing in play", p["state"] == "pre" and p["frac"] == 1.0 and p["detail"] == "7:00 PM EST")
f = E.pick_game(by["Bakersfield Condors"], dt.date(2026, 11, 18))
ok("a shootout final says so and counts as over", f["state"] == "post" and f["detail"] == "Final SO" and f["frac"] == 0.0)
ok("a regulation final", E.pick_game(by["Rockford IceHogs"], dt.date(2026, 11, 18))["detail"] == "Final")
ok("one team on two nights is kept apart by the game's date", E.pick_game(by["Bakersfield Condors"], dt.date(2026, 11, 19)) is None)

c = E.pick_game(by["Calgary Wranglers"], dt.date(2026, 11, 19))
ok("start time comes from Eastern time, not the feed's off ISO text (9 PM Eastern = 02:00 UTC)",
   c["start"] == "2026-11-20T02:00:00Z" and p["start"] == "2026-11-20T00:00:00Z")
ok("the game date is the Eastern date, like Kalshi's tickers", c["day"] == dt.date(2026, 11, 19))
zone = E.FEED_TZ; E.FEED_TZ = None
ok("without time-zone data it falls back to the feed's ISO text", E._feed_start(GAMES[0]) == ("2026-11-20T00:00:00Z", dt.date(2026, 11, 19)))
E.FEED_TZ = zone

# through the engine's normal path from a Kalshi pick to its score
tk = "KXAHLGAME-26NOV191900CLEHAM-CLE"
E.PICK_NAME[tk] = "Cleveland"
sc = E.leg_score({"ticker": tk, "side": "yes"})
ok("a Kalshi pick finds its game and score", sc and sc["state"] == "in" and (sc["me"], sc["opp"]) == (2, 1))
sc = E.leg_score({"ticker": tk, "side": "no"})
ok("betting against the team shows the other side's score", sc and sc["abbr"] == "HAM" and (sc["me"], sc["opp"]) == (1, 2))
sc = E.leg_score({"ticker": "KXAHLGAME-26NOV191900HERCHA-HER", "side": "yes"})
ok("a pick found by Kalshi's team code alone", sc and sc["state"] == "pre" and sc["abbr"] == "HER")
ok("the score line a bet shows (score, period and clock)", "CLE 2–1 HAM" in E.score_line(E.leg_score({"ticker": tk, "side": "yes"})) and "P2 7:42" in E.score_line(E.leg_score({"ticker": tk, "side": "yes"})))
ok("a pick from another night gets no score", E.leg_score({"ticker": "KXAHLGAME-26NOV201900CLEHAM-CLE", "side": "yes"}) is None)

# the never-buy-started-games rule still rests on kickoff times, and a feed that says final marks the game over
E.KICKOFF["KXAHLGAME-26NOV191900CLEHAM"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)).isoformat()
E.KICKOFF["KXAHLGAME-26NOV191900HERCHA"] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)).isoformat()
ok("a game past its kickoff is started, one later today is not",
   E.started({"event": "KXAHLGAME-26NOV191900CLEHAM"}) and not E.started({"event": "KXAHLGAME-26NOV191900HERCHA"}))
ok("the start time of a pick's game is known from the feed when nothing else says", E.leg_start({"ticker": "KXAHLGAME-26NOV191900CLEHAM-CLE", "side": "yes"}, {}) is not None)

# caching: inside the window nothing is fetched
n = len(net.calls); E.fetch_scores(max_age=45)
ok("fresh scores are reused, not fetched again", len(net.calls) == n)

# failures keep the last good copy (never a blank), and the next call retries
for label, bad in (("the feed is unreachable", E._requests.ConnectionError("down")),
                   ("the feed answers an error", Resp({}, ok=False)),
                   ("the feed sends nonsense", Resp({"oops": 1})),
                   ("the feed sends broken JSON", Resp(ValueError("bad json"))),
                   ("a game row is malformed", Resp({"SiteKit": {"Scorebar": [{"HomeLongName": "X", "HomeGoals": "x"}]}}))):
    net.feed = bad
    n = len(net.calls)
    again = E.fetch_scores(max_age=0)
    ok(f"{label}: keeps the last good scores", again is by and again["Cleveland Monsters"][0]["me"] == 2 and E.SCORES_BY["ahl"]["by"] is by)
    ok(f"{label}: tries again next time", len(net.calls) == n + 1 and E.SCORES_BY["ahl"]["at"] < __import__("time").time())
net.feed = Resp({"SiteKit": {"Scorebar": [dict(GAMES[1], HomeGoals="3")]}})
ok("when the feed is back the new scores replace the old", E.fetch_scores(max_age=0)["Cleveland Monsters"][0]["me"] == 3)

E.SCORES_BY.pop("ahl"); net.feed = Resp(ValueError("x"))
ok("no scores yet and the feed fails: empty, no crash", E.fetch_scores(max_age=0) == {})

# ESPN leagues are untouched, and leagues with no source still return nothing without a request
n = len(net.calls); E.fetch_scores(max_age=0, code="nba")
ok("NBA still reads ESPN", "espn.com" in net.calls[-1][0] and len(net.calls) > n and all("espn.com" in c[0] for c in net.calls[n:]))
n = len(net.calls)
ok("EuroLeague has no source and makes no request", E.fetch_scores(max_age=0, code="euroleague") == {} and len(net.calls) == n)
ok("the phone's Mac-proxy allowlist includes the feed", E.AHL_FEED_URL.startswith(E.HUB_GET_HOSTS))
