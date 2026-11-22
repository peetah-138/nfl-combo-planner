# CHECK: group=engine
"""Live scores for tennis, EuroLeague and UFC from Kalshi's public live data (ESPN has none). Display only.
The network is faked from real response shapes in fixtures/kalshi_live.json (captured with plain unauthenticated GETs)."""
import os, json, copy, inspect, importlib.util, datetime as dt
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))
FX = json.load(open("fixtures/kalshi_live.json"))
LIVE = {x["milestone_id"]: x for x in FX["live_datas"]}


def ms_for(event, mid=None, title=None):
    """A milestone answer for `event`: the real one captured for it, or a captured in-play one re-labelled for it."""
    if event in FX["milestones_by_event"]:
        return copy.deepcopy(FX["milestones_by_event"][event])
    m = copy.deepcopy(FX["milestones_extra"][mid])
    m["primary_event_tickers"] = m["related_event_tickers"] = [event]
    if title:
        m["title"] = title
    return [m]


# fake events -> milestones (in-play samples are an ITF match and an NBL game; Kalshi feeds ATP and EuroLeague the same way)
MS = {"KXATPMATCH-26NOV19DEBBLA": ms_for("KXATPMATCH-26NOV19DEBBLA", "ab815e1a-4c83-45d2-a39e-47d093719fd5"),
      "KXATPMATCH-26NOV19RATWAR": ms_for("KXATPMATCH-26NOV19RATWAR", "9eb53e5e-8968-4b2f-8c54-5a8998bd008a"),
      "KXEUROLEAGUEGAME-26NOV190330ADEILL": ms_for("KXEUROLEAGUEGAME-26NOV190330ADEILL", "9c500ee8-1afb-56c0-90b0-0b6a078cbf8a"),
      "KXEUROLEAGUESPREAD-26NOV181200RMABJK": ms_for("KXEUROLEAGUEGAME-26NOV181200RMABJK")}
for e in ("KXATPMATCH-26NOV17ZVESHE", "KXEUROLEAGUEGAME-26NOV181200RMABJK", "KXUFCFIGHT-26NOV14GANHOK", "KXUFCFIGHT-26NOV21NURLOR"):
    MS[e] = ms_for(e)


class Resp:
    def __init__(self, body, code=200, headers=None):
        self.body, self.status_code, self.ok, self.headers = body, code, code < 400, headers or {}

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class Net:
    """requests stand-in: answers /milestones and /live_data/batch from the fixtures; records every call."""
    RequestException = E._requests.RequestException
    ConnectionError = E._requests.ConnectionError

    def __init__(self):
        self.calls, self.mode, self.live = [], "ok", copy.deepcopy(LIVE)

    def get(self, url, params=None, headers=None, **kw):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        if self.mode == "down":
            raise self.ConnectionError("down")
        if self.mode == "429":
            return Resp({}, 429, {"Retry-After": "40"})
        if "/milestones" in url:
            return Resp({"milestones": MS.get(params.get("related_event_ticker"), []), "cursor": ""})
        if "/live_data/batch" in url:
            if self.mode == "odd":
                return Resp({"something": "else"})
            ids = params.get("milestone_ids") or []
            return Resp({"live_datas": [self.live[i] for i in ids if i in self.live]})
        return Resp({"events": []})


net = Net(); E.requests = net
E.set_league("tennis")
EVS = list(MS)
n = E.kalshi_live_refresh(EVS, max_age=8)
ok("one milestone lookup per game, one batch call for all of them",
   sum("/milestones" in u for u, _, _ in net.calls) == len(EVS) and sum("/live_data/batch" in u for u, _, _ in net.calls) == 1 and n >= 6)
ok("only Kalshi's public endpoints, no key or signature headers",
   all(u.startswith(E.KALSHI + "/milestones") or u.startswith(E.KALSHI + "/live_data/batch") for u, _, _ in net.calls)
   and all(set(h) <= {"Accept"} for _, _, h in net.calls))
ok("never touches account endpoints", not any("/portfolio" in u or "/communications" in u for u, _, _ in net.calls))
sc = lambda t, side="yes": E.kalshi_score({"ticker": t, "side": side})

# ---- tennis in play: sets as the score, the set's games, the game's points and who serves, from the pick's side
d = sc("KXATPMATCH-26NOV19DEBBLA-DEB")
ok("tennis live: state in, sets 0-0", d and d["state"] == "in" and (d["me"], d["opp"]) == (0, 0) and d["src"] == "kalshi")
ok("tennis live: set, games, points and server read plainly", d and d["detail"] == "Set 1 · 0–2 · 40–15 · serving", d and d["detail"])
b = sc("KXATPMATCH-26NOV19DEBBLA-BLA")
ok("the other player's side: games and points flipped, not serving", b and b["detail"] == "Set 1 · 2–0 · 15–40" and b["abbr"] == "BLA" and b["opp_abbr"] == "DEB")
nb = sc("KXATPMATCH-26NOV19DEBBLA-DEB", "no")
ok("betting against a player reads from the other side", nb and nb["abbr"] == "BLA" and nb["detail"] == b["detail"])
w = sc("KXATPMATCH-26NOV19RATWAR-RAT")
ok("tennis not begun: state pre", w and w["state"] == "pre")
# ---- tennis finished
z = sc("KXATPMATCH-26NOV17ZVESHE-ZVE"); s = sc("KXATPMATCH-26NOV17ZVESHE-SHE")
ok("tennis final: sets 2-0 and the set scores", z and z["state"] == "post" and (z["me"], z["opp"]) == (2, 0) and z["detail"] == "6–2 7–6", z and z["detail"])
ok("tennis final: winner known for each side (display)", z["won"] is True and s and s["won"] is False and (s["me"], s["opp"]) == (0, 2))
# ---- EuroLeague
r = sc("KXEUROLEAGUEGAME-26NOV181200RMABJK-RMA"); j = sc("KXEUROLEAGUEGAME-26NOV181200RMABJK-BJK")
ok("EuroLeague final: away team listed first, points from each side", r and (r["me"], r["opp"]) == (79, 83) and j and (j["me"], j["opp"]) == (83, 79))
ok("EuroLeague final: 'Final', winner the home side", r["detail"] == "Final" and r["state"] == "post" and r["won"] is False and j["won"] is True)
sp = sc("KXEUROLEAGUESPREAD-26NOV181200RMABJK-RMA5")
ok("a spread pick finds its team", sp and sp["abbr"] == "RMA" and (sp["me"], sp["opp"]) == (79, 83))
a = sc("KXEUROLEAGUEGAME-26NOV190330ADEILL-ADE")
ok("basketball between quarters reads 'End Q1', score from the pick's side", a and a["state"] == "in" and a["detail"] == "End Q1" and (a["me"], a["opp"]) == (26, 23), a)
net.live["9c500ee8-1afb-56c0-90b0-0b6a078cbf8a"]["details"].update(match_status="SecondQuarter", genius_phase="SecondQuarter", period=2, period_remaining_time="07:42")
E.KLIVE["live"].pop("9c500ee8-1afb-56c0-90b0-0b6a078cbf8a")
E.kalshi_live_refresh(["KXEUROLEAGUEGAME-26NOV190330ADEILL"], max_age=8)
a = sc("KXEUROLEAGUEGAME-26NOV190330ADEILL-ILL")
ok("basketball clock reads like ESPN's ('Q2 7:42'), so the page's clock can run", a and a["detail"] == "Q2 7:42" and (a["me"], a["opp"]) == (23, 26), a and a["detail"])
# ---- UFC
g = sc("KXUFCFIGHT-26NOV14GANHOK-GAN"); h = sc("KXUFCFIGHT-26NOV14GANHOK-HOK")
ok("UFC final: how it ended and the round, no made-up points", g and g["state"] == "post" and g["me"] is None and g["detail"] == "Decision · R5" and g["won"] is True and h["won"] is False, g)
ok("UFC: no points, so display_score(points=True) leaves it out", E.display_score({"ticker": "KXUFCFIGHT-26NOV14GANHOK-GAN", "side": "yes"}) is None
   and E.display_score({"ticker": "KXUFCFIGHT-26NOV14GANHOK-GAN", "side": "yes"}, points=False)["detail"] == "Decision · R5")
ok("UFC in a fight: the round, and 'no clock' rather than a fake one", E._kfight({"widget_status": "live", "current_round": 2}, 3) == "Round 2 of 3 · no clock")
ok("UFC: a clock is shown if the feed ever sends one", E._kfight({"widget_status": "live", "current_round": 1, "round_time_left": "03:12"}, 5) == "Round 1 of 5 · 3:12 left")
ok("a game Kalshi has no live block for yet: nothing shown (the old honest status stays)", sc("KXUFCFIGHT-26NOV21NURLOR-NUR") is None)
# ---- can't tell the side, or not our sport: say nothing
ok("a pick whose code isn't in the game's code: no score", sc("KXATPMATCH-26NOV19DEBBLA-XYZ") is None)
ok("ESPN sports never use Kalshi's data", sc("KXNBAGAME-26NOV19BOSNYK-BOS") is None)
before = len(net.calls)
E.kalshi_live_refresh(["KXNBAGAME-26NOV19BOSNYK", "KXNHLGAME-26NOV19COLSJ"])
ok("no Kalshi live-data calls for ESPN sports", len(net.calls) == before)

# ---- display only: the money path never sees it
ok("leg_score (what smart sell, early results and the buy rules read) is unchanged: no tennis score",
   E.leg_score({"ticker": "KXATPMATCH-26NOV19DEBBLA-DEB", "side": "yes"}) is None and "tennis" not in E.SCORES_BY)
ok("display_score shows it", E.display_score({"ticker": "KXATPMATCH-26NOV19DEBBLA-DEB", "side": "yes"})["detail"].startswith("Set 1"))
money = ["single_sell_reason", "smart_sell_singles", "auto_sell_now", "swing_lambda", "what_if", "screen_live", "pick_state", "started",
         "legs_left_of", "take_profit_reason", "panel_exec", "panel_pass", "build_panel", "choose_panel", "fetch_scores", "leg_score",
         "leg_start", "turning_against", "sim_exit", "_replay", "smart_tune", "accept_offer", "get_offer", "kalshi_send"]
leaks = [f for f in money if hasattr(E, f) and any(k in inspect.getsource(getattr(E, f)) for k in ("kalshi_score", "display_score", "KLIVE", "klive"))]
ok("no buy/sell/panel/started-game function reads Kalshi's live data", not leaks and all(hasattr(E, f) for f in ("single_sell_reason", "smart_sell_singles", "pick_state", "started", "leg_score")), leaks)
src = inspect.getsource(E.mine_page)
ok("early results before Kalshi settles still come only from leg_score", "sc = leg_score(l)                       # already from the side the pick needs" in src)
src = inspect.getsource(E.open_singles)
ok("singles keep their state from the old score source (smart sell reads it)",
   'live = bool(sc) and str(sc.get("state") or "") in ("in", "live")' in src and 'sc = leg_score(_score_leg(t, kind, side, code))' in src)

# ---- caching and politeness
before = len(net.calls)
E.kalshi_live_refresh(EVS, max_age=8)
ok("a second refresh inside the cache time makes no calls", len(net.calls) == before)
for v in E.KLIVE["live"].values():
    v["at"] -= 20
E.kalshi_live_refresh(EVS, max_age=8)
new = net.calls[before:]
ok("after the cache time: one batch call, milestone mapping kept", len(new) == 1 and "/live_data/batch" in new[0][0])
E.KLIVE["ms"].clear(); E.KLIVE["live"].clear(); net.calls.clear()
many = [f"KXATPMATCH-26NOV19A{i:02d}B{i:02d}" for i in range(20)]
E.kalshi_live_refresh(many)
ok("at most 8 new game lookups per refresh", sum("/milestones" in u for u, _, _ in net.calls) == E.KLIVE_NEW_MAX)
net.calls.clear()
E.kalshi_live_refresh(many)
ok("games Kalshi doesn't know are not asked again for a while", sum("/milestones" in u for u, _, _ in net.calls) == E.KLIVE_NEW_MAX
   and all(E.KLIVE["ms"][e]["id"] is None for e in many if e in E.KLIVE["ms"]))

# ---- failures: last good copy, back off
E.KLIVE["ms"].clear(); E.KLIVE["live"].clear(); E.KLIVE.update(cool=0.0, fails=0)
E.kalshi_live_refresh(EVS, max_age=8)
good = sc("KXATPMATCH-26NOV19DEBBLA-DEB")
for v in E.KLIVE["live"].values():
    v["at"] -= 20
net.mode = "odd"
E.kalshi_live_refresh(EVS, max_age=8)
ok("an odd answer keeps the last good copy", sc("KXATPMATCH-26NOV19DEBBLA-DEB") == {**good, "age": sc("KXATPMATCH-26NOV19DEBBLA-DEB")["age"]})
net.mode = "429"
E.kalshi_live_refresh(EVS, max_age=8)
ok("429: backs off (Retry-After honoured) and keeps the last good copy",
   E.KLIVE["cool"] - __import__("time").time() > 30 and sc("KXATPMATCH-26NOV19DEBBLA-DEB")["detail"] == good["detail"])
net.calls.clear(); net.mode = "ok"
E.kalshi_live_refresh(EVS, max_age=8)
ok("no calls at all while backing off", not net.calls)
E.KLIVE["cool"] = 0
net.mode = "down"
E.kalshi_live_refresh(EVS, max_age=8)
ok("unreachable: backs off, last good copy kept", E.KLIVE["cool"] > __import__("time").time() and E.KLIVE["fails"] >= 1
   and sc("KXATPMATCH-26NOV19DEBBLA-DEB") is not None)
for v in E.KLIVE["live"].values():
    v["at"] -= 3600
ok("a copy over 15 minutes old is not shown as live", sc("KXATPMATCH-26NOV19DEBBLA-DEB") is None)
net.mode = "ok"; E.KLIVE.update(cool=0.0, fails=0)

# ---- honest status words (run_status, display only)
now = dt.datetime.now(dt.timezone.utc)
ago = lambda h: now - dt.timedelta(hours=h)
r = E.run_status("tennis", ago(0.5), now, "pre")
ok("due but not begun: 'Not started yet', never 'Live'", r["phase"] == "waiting" and r["text"].startswith("Not started yet") and r["short"] == "Not started yet")
r = E.run_status("tennis", ago(2), now, "post", "6–2 7–6")
ok("finished: 'Match over', the score, waiting on Kalshi", r["phase"] == "over" and r["text"] == "Match over · 6–2 7–6 · waiting on Kalshi to settle")
r = E.run_status("ufc", ago(0.2), now, "in", "Round 2 of 3 · no clock")
ok("a fight in progress says its round", r["phase"] == "on" and r["text"] == "Round 2 of 3 · no clock")
ok("finished long after the usual length still reads 'over', not 'probably over'", E.run_status("tennis", ago(9), now, "post")["phase"] == "over")
E.KLIVE["live"].clear()
E.kalshi_live_refresh(["KXATPMATCH-26NOV19DEBBLA"], max_age=8)
ok("kalshi_live_on: a match in play counts (the web app refreshes faster then)", E.kalshi_live_on() is True)
E.KLIVE["live"].clear()
ok("kalshi_live_on: nothing in play", E.kalshi_live_on() is False)

# ---- klive_events: only sports ESPN lacks, only games started or about to
E.KICKOFF["KXATPMATCH-26NOV25AAABBB"] = (now + dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
E.KICKOFF["KXATPMATCH-26NOV19CCCDDD"] = (now - dt.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
evs = E.klive_events([{"ticker": "KXATPMATCH-26NOV25AAABBB-AAA", "event": "KXATPMATCH-26NOV25AAABBB"},
                      {"ticker": "KXATPMATCH-26NOV19CCCDDD-CCC", "event": "KXATPMATCH-26NOV19CCCDDD"},
                      {"ticker": "KXNBAGAME-26NOV19BOSNYK-BOS", "event": "KXNBAGAME-26NOV19BOSNYK"}])
ok("asks only about started tennis/EuroLeague/UFC games, not ones days away or ESPN sports", evs == {"KXATPMATCH-26NOV19CCCDDD"}, evs)

# ---- singles on Live (GitHub #95): a held tennis single shows Kalshi's score and opponent, and NOTHING that trades moves
import time
MKT = {"KXATPMATCH-26NOV19DEBBLA-DEB": {"ticker": "KXATPMATCH-26NOV19DEBBLA-DEB", "event_ticker": "KXATPMATCH-26NOV19DEBBLA",
          "title": "Debrecen vs Blake: Winner?", "yes_sub_title": "Debrecen", "status": "active",
          "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.44", "no_bid_dollars": "0.56"},
       "KXATPMATCH-26NOV19RATWAR-RAT": {"ticker": "KXATPMATCH-26NOV19RATWAR-RAT", "event_ticker": "KXATPMATCH-26NOV19RATWAR",
          "title": "Rat vs War: Winner?", "yes_sub_title": "Rat", "status": "active",
          "yes_bid_dollars": "0.55", "yes_ask_dollars": "0.59", "no_bid_dollars": "0.41"},
       "KXNBAGAME-26NOV19BOSNYK-BOS": {"ticker": "KXNBAGAME-26NOV19BOSNYK-BOS", "event_ticker": "KXNBAGAME-26NOV19BOSNYK",
          "title": "Boston at New York Winner?", "yes_sub_title": "Boston", "status": "active",
          "yes_bid_dollars": "0.50", "yes_ask_dollars": "0.54", "no_bid_dollars": "0.46"}}


class MResp:
    def __init__(self, d): self.d, self.ok = d, True
    def raise_for_status(self): pass
    def json(self): return self.d


_net_get = net.get
def get_with_markets(url, params=None, headers=None, **kw):
    if url.endswith("/markets"):
        return MResp({"markets": [MKT[t] for t in (params or {}).get("tickers", "").split(",") if t in MKT]})
    return _net_get(url, params=params, headers=headers, **kw)
net.get = get_with_markets
nowu = dt.datetime.now(dt.timezone.utc)
E.KICKOFF["KXATPMATCH-26NOV19DEBBLA"] = (nowu - dt.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")     # under way
E.KICKOFF["KXATPMATCH-26NOV19RATWAR"] = (nowu + dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")       # hours away
E.KICKOFF["KXNBAGAME-26NOV19BOSNYK"] = (nowu + dt.timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
E.ACCT_POS.update(at=time.time(), items=[{"ticker": t, "position_fp": "8", "market_exposure_dollars": "4.00"} for t in MKT])
DEB = "KXATPMATCH-26NOV19DEBBLA-DEB"


def singles_run(live):
    """open_singles with Kalshi's live data (the in-play match above) or without it (Kalshi unreachable, no cached copy)."""
    E.KLIVE["live"].clear(); E.KLIVE["ms"].clear(); E.KLIVE.update(cool=0.0, fails=0)
    net.mode = "ok" if live else "down"
    E.SINGLES["at"] = 0
    out = [dict(x) for x in E.open_singles()]
    net.mode = "ok"; E.KLIVE.update(cool=0.0, fails=0)
    return out


withk = singles_run(True)
ks = E.kalshi_score({"ticker": DEB, "side": "yes"})            # Kalshi's own score for it, read while its live data is cached
nok = singles_run(False)
a = next(x for x in withk if x["t"] == DEB); b = next(x for x in nok if x["t"] == DEB)
ok("a held in-play tennis single shows Kalshi's score: source and opponent", a["src"] == "kalshi" and ks is not None
   and a["opp"] == (ks.get("opp_name") or ks.get("opp_abbr")) and a["opp"] == "BLA" and a["sc"]["abbr"] == "DEB", (a["src"], a["opp"], ks))
ok("without Kalshi's live data the same single has no opponent, no score, no source", b["opp"] == "" and b["sc"] is None and b["src"] == "" and b["on"] is False)
ok("the in-play single is flagged as playing from Kalshi's data (display only)", a["on"] is True)
nu = lambda xs: [(x["t"], x["state"], x["chance"], x["sell_at"], x["starts"]) for x in xs]
ok("KEY: with or without Kalshi's live data: state, chance, sell_at and starts are identical", nu(withk) == nu(nok), (nu(withk), nu(nok)))
ok("KEY: the order of the singles (smart sell walks it) is identical", [x["t"] for x in withk] == [x["t"] for x in nok])
ok("KEY: state for the in-play tennis single is unchanged (still 'pre': the money path has no score for it)", a["state"] == b["state"] == "pre")
sellw = [E.single_sell_reason(dict(x), 0.45, None, track=False) for x in withk]
sellwo = [E.single_sell_reason(dict(x), 0.45, None, track=False) for x in nok]
ok("KEY: single_sell_reason answers are identical with and without the live data", sellw == sellwo, (sellw, sellwo))
differ = {k for x, y in zip(withk, nok) for k in x if x[k] != y[k]}
ok("only the display fields differ (opp, sc, on, src, and the words that describe the score)",
   {"opp", "sc", "on", "src"} <= differ and differ <= {"opp", "sc", "on", "src", "score", "how", "note", "phase", "short"}, sorted(differ))
others = [(x, y) for x, y in zip(withk, nok) if x["t"] != DEB]
ok("the other singles (not in play) are untouched, field for field", all(x == y for x, y in others), [(x["t"]) for x, y in others if x != y])
