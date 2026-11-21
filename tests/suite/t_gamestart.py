# Issue #223: a game's start time. Kalshi's expected settle time is a placeholder for most college football games
# (23:00 UTC on 2026-11-21 whether they kick off at noon or 7:30 PM Eastern), so "settle time minus 3.5 h" put
# Kentucky at Missouri's kick-off at 19:30 UTC, five hours early: Live said "Not started yet · was due 3h ago",
# tagged it live, and smart sell treated it as a game under way. The score feed's own scheduled start (ESPN, real
# shape in fixtures/game_start_223.json) now comes before that estimate, and a feed that shows a game in play or
# over always counts as started.
import os, json, copy, importlib.util, datetime as real_dt, types
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
FX = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "game_start_223.json")))

NOW = [real_dt.datetime(2026, 11, 21, 22, 32, tzinfo=real_dt.timezone.utc)]     # Pete's screenshot, 14:32 Pacific


class FDT(real_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW[0].astimezone(tz) if tz else NOW[0].astimezone().replace(tzinfo=None)


shim = types.SimpleNamespace(**{k: getattr(real_dt, k) for k in dir(real_dt) if not k.startswith("__")})
shim.datetime = FDT
E.dt = shim


class R:
    def __init__(self, d):
        self.d, self.ok, self.status_code = d, True, 200

    def json(self):
        return self.d

    def raise_for_status(self):
        pass


SB = [FX["espn_scoreboard"]]


def fake_get(url, params=None, **k):
    if "college-football/scoreboard" in url:
        return R(copy.deepcopy(SB[0]))
    if url.endswith("/markets"):
        want = set((params or {}).get("tickers", "").split(","))
        return R({"markets": [m for m in FX["kalshi_markets"] if m["ticker"] in want], "cursor": None})
    return R({})


E.requests.get = fake_get
MIZ = next(m for m in FX["kalshi_markets"] if m["ticker"].endswith("-MIZZ"))
EV, T = MIZ["event_ticker"], MIZ["ticker"]
KICK = real_dt.datetime(2026, 11, 22, 0, 30, tzinfo=real_dt.timezone.utc)
EST = real_dt.datetime(2026, 11, 21, 19, 30, tzinfo=real_dt.timezone.utc)
side = {"event": EV, "ticker": T, "exp": MIZ["expected_expiration_time"]}


def reset():
    E.SCORES_BY.clear(); E.FEED_MEMO.clear(); E.KICKOFF.clear(); E.EVENT_TICK.clear(); E.MARKET_INFO.clear()
    E.GAME_EXP.clear(); E.PICK_NAME.clear()


# --- the trap, as it was: no sportsbook kick-off and no score feed loaded = only Kalshi's placeholder estimate
reset()
E.fetch_results([T])                               # what the Live page does for a held combo's legs
ok("the fixture is the real trap: Kalshi's settle time is before the real kick-off",
   E._iso_dt(MIZ["expected_expiration_time"]) < KICK)
ok("with nothing better, the start is Kalshi's estimate (19:30 UTC), marked as an estimate",
   E.game_start(EV, T) == (EST, "estimate"))

# --- the fix: the score feed's scheduled start for this exact game wins over the estimate
E.fetch_scores(max_age=0, code="ncaaf")
t, src = E.game_start(EV, T)
ok("the score feed's start (00:30 UTC, 7:30 PM Eastern) is used, not Kalshi's estimate", t == KICK and src == "feed")
ok("start_dt without a ticker finds the game through a market it has seen", E.start_dt(EV) == KICK)
ok("the game is not started two hours before kick-off", not E.started(side))
ok("pick_state says pre (no 'live' tag, smart sell sees no game under way)", E.pick_state({"ticker": T, "event": EV}, {}) == "pre")
ok("leg_start is the real kick-off", E.leg_start({"ticker": T, "event": EV}, {}) == KICK)
ok("run_status says nothing (not 'Not started yet · was due 3h ago')",
   E.run_status("ncaaf", E.leg_start({"ticker": T, "event": EV}, {}), score_state="pre") is None)
ll = E.legs_left_of([{"ticker": T, "event": EV}], [(None, None, 0.64, None)], {})
ok("the combo's legs left: not playing, starts at the real kick-off (smart sell's 'game under way' input)",
   ll and ll[0][1] is False and abs(ll[0][2] - KICK.timestamp()) < 1)
sp = {"event": EV.replace("GAME-", "SPREAD-"), "ticker": EV.replace("GAME-", "SPREAD-") + "-MIZZ7", "exp": MIZ["expected_expiration_time"]}
ok("a spread on the same game uses the game's start too", E.game_start(sp["event"], sp["ticker"])[0] == KICK and not E.started(sp))

# --- the sportsbooks' kick-off still comes first
E.KICKOFF[EV] = "2026-11-22T00:35:00Z"
ok("the sportsbooks' kick-off is trusted first", E.game_start(EV, T) == (E._iso_dt("2026-11-22T00:35:00Z"), "book"))
E.KICKOFF.clear()

# --- a game in play (or over) on the feed always counts as started, whatever any time says
live = copy.deepcopy(FX["espn_scoreboard"])
c = live["events"][0]["competitions"][0]
c["status"] = {"clock": 600, "displayClock": "10:00", "period": 1,
               "type": {"name": "STATUS_IN_PROGRESS", "state": "in", "completed": False, "detail": "10:00 - 1st", "shortDetail": "10:00 - 1st"}}
SB[0] = live
E.fetch_scores(max_age=0, code="ncaaf"); E.FEED_MEMO.clear()
E.KICKOFF[EV] = "2026-11-22T03:00:00Z"            # even a (wrong) later kick-off can't make a game in play look pre-game
ok("a game the feed shows in play is started, even if a kick-off time says later", E.started(side))
E.KICKOFF.clear()

# --- the reverse trap: a noon kick-off whose placeholder estimate is later than the real start
NOW[0] = real_dt.datetime(2026, 11, 21, 18, 0, tzinfo=real_dt.timezone.utc)
noon = copy.deepcopy(live)
noon["events"][0]["date"] = noon["events"][0]["competitions"][0]["date"] = "2026-11-21T17:00Z"
SB[0] = noon
E.fetch_scores(max_age=0, code="ncaaf"); E.FEED_MEMO.clear()
ok("noon game in play at 18:00 UTC is started (Kalshi's estimate alone would say 19:30)", E.started(side)
   and E.game_start(EV, T)[0] == real_dt.datetime(2026, 11, 21, 17, 0, tzinfo=real_dt.timezone.utc))
NOW[0] = real_dt.datetime(2026, 11, 21, 22, 32, tzinfo=real_dt.timezone.utc)

# --- ESPN's "time to be announced" date is not a kick-off time
tbd = copy.deepcopy(FX["espn_scoreboard"])
tbd["events"][0]["competitions"][0]["timeValid"] = False
SB[0] = tbd
E.fetch_scores(max_age=0, code="ncaaf"); E.FEED_MEMO.clear()
ok("a TBD feed time is ignored (falls back to the estimate)", E.game_start(EV, T)[1] == "estimate")

# --- fail closed: an estimate that has passed while the feed says not started never gets a live price
SB[0] = tbd
E.fetch_scores(max_age=0, code="ncaaf"); E.FEED_MEMO.clear()
E.score_age = lambda sport, now=None: 5
sides = [dict(x, event=EV, p=0.65, bid=0.64, fair=0.6, src="book") for x in
         ({"ticker": m["ticker"]} for m in FX["kalshi_markets"])]
okg, why = E.panel_live_games({EV: sides})
ok("a game the feed shows not started is never priced live for the panel", EV not in okg and "in play" in why.get(EV, ""))
f, how, w = E.live_side_fair(dict(sides[1], pre=0.6), refresh=False)
ok("...and Buy straight's live price refuses it too", f is None and "in play" in (w or ""))
