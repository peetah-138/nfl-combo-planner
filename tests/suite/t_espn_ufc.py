# CHECK: group=engine
"""UFC rounds and clocks from ESPN's free mma/ufc scoreboard (issue #25). Display only: the network is faked from a
trimmed real response (fixtures/espn_ufc.json); live variants edit its status because no fight was on air when it was captured."""
import os, json, copy, inspect, time, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))
FX = json.load(open("fixtures/espn_ufc.json"))


class Resp:
    def __init__(self, body, code=200):
        self.body, self.status_code, self.ok, self.headers = body, code, code < 400, {}

    def json(self):
        return self.body


class Net:
    RequestException = E._requests.RequestException
    ConnectionError = E._requests.ConnectionError

    def __init__(self):
        self.calls, self.mode, self.body = [], "ok", copy.deepcopy(FX)

    def get(self, url, params=None, headers=None, **kw):
        self.calls.append((url, dict(params or {})))
        if self.mode == "down":
            raise self.ConnectionError("down")
        if self.mode == "429":
            return Resp({}, 429)
        if self.mode == "odd":
            return Resp({"nothing": 1})
        return Resp(copy.deepcopy(self.body))


net = Net(); E.requests = net
sc = lambda t, side="yes": E.espn_mma_score({"ticker": t, "side": side})
ks = lambda t, side="yes": E.kalshi_score({"ticker": t, "side": side})
EV = "KXUFCFIGHT-26NOV21NURLOR"

# ---- parsing the real shape
fights = E.espn_mma_parse(FX["events"])
ok("parses every fight on the card", len(fights) == 4 and all(len(f["names"]) == 2 for f in fights))
ok("accents are dropped for the name codes (Procházka -> PRO)", "PRO" in next(f for f in fights if "Procházka" in f["names"][0])["codes"][0])
ok("odd input never raises", E.espn_mma_parse(None) == [] and E.espn_mma_parse([{"competitions": [{"competitors": [{}]}]}, 5, {"competitions": None}]) == [])

# ---- one polite call for the card, then cached
n = E.espn_mma_refresh([EV, "KXUFCFIGHT-26NOV21PROSTI"])
ok("one call to ESPN's UFC scoreboard, no params, nothing for Kalshi", n == 1 and len(net.calls) == 1 and net.calls[0][0].endswith("/mma/ufc/scoreboard")
   and net.calls[0][1] == {} and "kalshi" not in net.calls[0][0].lower())
E.espn_mma_refresh([EV]); ok("a second refresh inside the cache time makes no call", len(net.calls) == 1)

# ---- a finished fight, from each side
a = sc(EV + "-NUR"); b = sc(EV + "-LOR")
ok("finished: winner and the round it ended", a and a["state"] == "post" and a["won"] is True and b["won"] is False and a["detail"] == "Fight over · R2 0:24", a)
ok("no points for a fight", a["me"] is None and a["opp"] is None and a["abbr"] == "NUR" and a["opp_abbr"] == "LOR" and b["abbr"] == "LOR")
ok("betting against a fighter reads from the other side", sc(EV + "-NUR", "no")["abbr"] == "LOR" and sc(EV + "-NUR", "no")["won"] is False)
p = sc("KXUFCFIGHT-26NOV21PROSTI-STI")
ok("a five-round fight, accents in the name", p and p["state"] == "post" and p["won"] is True and p["abbr"] == "STI" and p["detail"] == "Fight over · R2 4:58", p)
ok("a decision shows the full round", sc("KXUFCFIGHT-26NOV21ALBCOS-ALB")["detail"] == "Fight over · R3 4:34")
ok("a code not in the fight: nothing", sc(EV + "-XYZ") is None)
ok("another day's fight with the same names: nothing", sc("KXUFCFIGHT-26DEC19NURLOR-NUR") is None)
ok("not a fight ticker: nothing", sc("KXNBAGAME-26NOV21NURLOR-NUR") is None and sc("KXUFCFIGHT-26NOV21NUR-NUR") is None)

# ---- in the fight: round and clock, then between rounds
live = copy.deepcopy(FX)
for c in live["events"][0]["competitions"]:
    if c["id"] == "401934356":
        c["status"].update(period=2, displayClock="3:12")
        c["status"]["type"].update(state="in", name="STATUS_IN_PROGRESS", completed=False)
        for f in c["competitors"]:
            f["winner"] = False
net.body = live
E.ESPN_MMA["boards"].clear(); E.espn_mma_refresh([EV])
a = sc(EV + "-NUR")
ok("in play: the round, of how many, and the clock", a and a["state"] == "in" and a["detail"] == "Round 2 of 3 · 3:12 in" and a["won"] is None, a)
ok("src flag keeps the page treating it as a display-only feed, via says ESPN", a["src"] == "kalshi" and a["via"] == "espn")
c = next(c for c in live["events"][0]["competitions"] if c["id"] == "401934356"); c["status"]["type"]["name"] = "STATUS_END_PERIOD"
E.ESPN_MMA["boards"].clear(); E.espn_mma_refresh([EV])
ok("between rounds", sc(EV + "-NUR")["detail"] == "End of Round 2 of 3", sc(EV + "-NUR"))
c["status"].update(period=0, displayClock="-"); c["status"]["type"]["name"] = "STATUS_IN_PROGRESS"
E.ESPN_MMA["boards"].clear(); E.espn_mma_refresh([EV])
ok("on air with no round yet: 'In progress', never a made-up clock", sc(EV + "-NUR")["detail"] == "In progress")

# ---- kalshi_score uses it: ESPN fills in when Kalshi has nothing, owns the clock while on, Kalshi keeps the finish
E.KLIVE["ms"].clear(); E.KLIVE["live"].clear()
c["status"].update(period=1, displayClock="1:05")
E.ESPN_MMA["boards"].clear(); E.espn_mma_refresh([EV])
k = ks(EV + "-NUR")
ok("kalshi_score: Kalshi has nothing, ESPN shows the fight", k and k["via"] == "espn" and k["detail"] == "Round 1 of 3 · 1:05 in", k)
E.KLIVE["ms"][EV] = {"at": time.time(), "id": "m1", "type": "mma", "first": "f1", "second": "f2", "start": "", "rounds": 3}
E.KLIVE["live"]["m1"] = {"at": time.time(), "d": {"widget_status": "live", "current_round": 1}, "type": "mma"}
k = ks(EV + "-NUR")
ok("Kalshi says 'no clock', ESPN has one: the clock wins", k["via"] == "espn" and "1:05" in k["detail"])
E.KLIVE["live"]["m1"]["d"] = {"widget_status": "finished", "winner": "f1", "method_of_victory": "KO/TKO", "final_round": 2, "final_round_time_left": "4:58"}
k = ks(EV + "-NUR")
ok("Kalshi finished (method, winner): that is kept even if ESPN still says 'in'", k.get("via") is None and k["state"] == "post" and k["detail"].startswith("KO/TKO"), k)
E.KLIVE["ms"].clear(); E.KLIVE["live"].clear()

# ---- failures keep the last good copy and back off
net.body = FX
E.ESPN_MMA["boards"].clear(); E.ESPN_MMA["cool"] = 0.0; E.espn_mma_refresh([EV]); good = sc(EV + "-NUR")
for bd in E.ESPN_MMA["boards"].values():
    bd["at"] -= 500
net.mode = "429"; net.calls.clear(); E.espn_mma_refresh([EV])
ok("a 429 keeps the last good copy and pauses", sc(EV + "-NUR")["detail"] == good["detail"] and E.ESPN_MMA["cool"] > time.time() + 30)
net.calls.clear(); E.espn_mma_refresh([EV]); ok("no calls while paused", not net.calls)
E.ESPN_MMA["cool"] = 0.0; net.mode = "odd"; E.espn_mma_refresh([EV])
ok("an odd answer keeps the last good copy", sc(EV + "-NUR")["detail"] == good["detail"])
E.ESPN_MMA["cool"] = 0.0; net.mode = "down"; E.espn_mma_refresh([EV])
ok("unreachable keeps the last good copy", sc(EV + "-NUR") is not None)
for bd in E.ESPN_MMA["boards"].values():
    bd["at"] -= 3600
ok("a copy over 15 minutes old is not shown", sc(EV + "-NUR") is None)
net.mode = "ok"; E.ESPN_MMA["cool"] = 0.0; E.ESPN_MMA["boards"].clear(); net.calls.clear()

# ---- a card ESPN's current board doesn't show gets one dated board, no more than two
E.espn_mma_refresh(["KXUFCFIGHT-26DEC19AAABBB"])
ok("a fight on another day asks for that day's board (current + one dated)", len(net.calls) == 2 and net.calls[1][1] == {"dates": "20261219"})
net.calls.clear(); E.ESPN_MMA["boards"].clear()
E.espn_mma_refresh([f"KXUFCFIGHT-26DEC{d:02d}AAABBB" for d in (5, 12, 19, 26)])
ok("at most the current board and two dated ones per refresh", len(net.calls) == 3)
ok("other sports never ask", E.espn_mma_refresh(["KXNBAGAME-26NOV21BOSNYK", "KXATPMATCH-26NOV21AAABBB"]) == 0)

# ---- display only: the money path never sees it
money = ["single_sell_reason", "smart_sell_singles", "auto_sell_now", "swing_lambda", "what_if", "screen_live", "pick_state", "started",
         "legs_left_of", "take_profit_reason", "panel_exec", "panel_pass", "build_panel", "choose_panel", "fetch_scores", "leg_score",
         "leg_start", "turning_against", "sim_exit", "accept_offer", "get_offer", "kalshi_send"]
leaks = [f for f in money if hasattr(E, f) and any(k in inspect.getsource(getattr(E, f)) for k in ("espn_mma", "ESPN_MMA"))]
ok("no buy/sell/panel/started-game function reads ESPN's UFC data", not leaks, leaks)
ok("leg_score and SCORES_BY never see a fight", E.leg_score({"ticker": EV + "-NUR", "side": "yes"}) is None and "ufc" not in E.SCORES_BY)
