# CHECK: group=engine
"""Issue #224: a college football game outside ESPN's FBS group (Jackson St. at Alcorn St., FCS/SWAC) showed
"Started 3h ago · no live score". Scores now ask ESPN for all of Division I (group 90); Kalshi's public live data
fills in (display only) a game ESPN still has nothing for. Network faked from real responses in
fixtures/fcs_live_score.json (plain unauthenticated GETs, trimmed)."""
import os, json, copy, inspect, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))
FX = json.load(open("fixtures/fcs_live_score.json"))
JK = "KXNCAAFGAME-26NOV21JKSTALCN"
FCS_ID = "401868365"


class Resp:
    def __init__(self, body, code=200):
        self.body, self.status_code, self.ok, self.headers = body, code, code < 400, {}

    def json(self):
        return self.body


class Net:
    RequestException = E._requests.RequestException
    ConnectionError = E._requests.ConnectionError

    def __init__(self, fbs_only=False):
        self.calls, self.fbs_only = [], fbs_only

    def get(self, url, params=None, headers=None, **kw):
        params = dict(params or {})
        self.calls.append((url, params, dict(headers or {})))
        if "espn.com" in url and url.endswith("/scoreboard"):
            evs = copy.deepcopy(FX["espn_groups_90"]["events"])
            if self.fbs_only or str(params.get("groups")) == "80":      # what ESPN's FBS group answers: no FCS game
                evs = [e for e in evs if e["id"] != FCS_ID]
            return Resp({"events": evs})
        if "/milestones" in url:
            ev = params.get("related_event_ticker")
            return Resp({"milestones": [m for m in FX["milestones"] if ev in (m.get("related_event_tickers") or [])],
                         "cursor": ""})
        if "/live_data/batch" in url:
            ids = params.get("milestone_ids") or []
            return Resp({"live_datas": [x for x in FX["live_datas"] if x["milestone_id"] in ids]})
        return Resp({}, 404)


def fresh(net):
    E.requests = net
    E.SCORES_BY.clear()
    E.KLIVE.update(ms={}, live={}, cool=0.0, fails=0)


for m in FX["kalshi_markets"]:
    E.PICK_NAME[m["ticker"]] = m["yes_sub_title"]                # "Jackson St.", "Alcorn St." (Kalshi's names)
E.PICK_NAME["KXNCAAFGAME-26NOV21MOSUJVST-JVST"] = "Jacksonville St."

# ---- the root cause: the scores asked ESPN for FBS only
net = Net(); fresh(net)
E.fetch_scores(max_age=0, code="ncaaf")
espn = [p for u, p, _ in net.calls if "espn.com" in u]
ok("college football scores ask ESPN for all of Division I (group 90)", espn and espn[0].get("groups") == "90", espn)
ok("the free lines and game picking still ask for FBS only (no new game priced or bought)",
   E.SPORTS["ncaaf"]["q"] == {"groups": "80"} and E.LEAGUES["ncaaf"]["espn_q"] == {"groups": "80"}
   and 'sp.get("q")' in inspect.getsource(E.free_snapshot) and "score_q" not in inspect.getsource(E.free_snapshot))

sc = E.leg_score({"ticker": JK + "-JKST", "side": "yes"})
ok("Jackson St. now has ESPN's live score from its own side: 38-14, Q3 9:23",
   sc and (sc["me"], sc["opp"], sc["state"], sc["detail"]) == (38, 14, "in", "Q3 9:23"), sc and (sc["me"], sc["opp"], sc["detail"]))
sc = E.leg_score({"ticker": JK + "-ALCN", "side": "yes"})
ok("the other side reads 14-38", sc and (sc["me"], sc["opp"]) == (14, 38))
sc = E.leg_score({"ticker": JK + "-ALCN", "side": "no"})
ok("betting against Alcorn St. reads from Jackson St.'s side", sc and (sc["me"], sc["opp"]) == (38, 14))
sc = E.leg_score({"ticker": "KXNCAAFGAME-26NOV21MOSUJVST-JVST", "side": "yes"})
ok("Jacksonville St. (a different team) keeps its own game, never Jackson St.'s", sc and sc["game"] != FCS_ID and sc["me"] == 25, sc)
st = E.run_status("ncaaf", E.dt.datetime(2026, 11, 21, 20, 0, tzinfo=E.dt.timezone.utc),
                  now=E.dt.datetime(2026, 11, 21, 22, 34, tzinfo=E.dt.timezone.utc), score_state="in", detail="Q3 9:23")
ok("with a score the leg no longer says 'no live score'", st and "no live score" not in st["text"], st)
ok("Kalshi's live data isn't asked for a game ESPN already has", not E.klive_events([{"ticker": JK + "-JKST"}])
   and not any("/milestones" in u for u, _, _ in net.calls))

# ---- the display-only fallback: ESPN has no record of the game -> Kalshi's public live data, shown only
net = Net(fbs_only=True); fresh(net)
E.fetch_scores(max_age=0, code="ncaaf")
leg = {"ticker": JK + "-JKST", "side": "yes"}
ok("with ESPN missing the game, leg_score (smart sell, results, buy rules) has nothing", E.leg_score(leg) is None)
evs = E.klive_events([leg])
ok("so the game is asked about on Kalshi's live data", evs == {JK}, evs)
E.kalshi_live_refresh(evs, max_age=8)
ok("only Kalshi's public endpoints, Accept header only",
   all(set(h) <= {"Accept"} for u, _, h in net.calls if "kalshi" in u)
   and not any("/portfolio" in u for u, _, _ in net.calls))
d = E.display_score(leg)
ok("Kalshi's live data shows 38-14, Q3 9:14 from Jackson St.'s side",
   d and (d["me"], d["opp"], d["state"], d["detail"], d["src"]) == (38, 14, "in", "Q3 9:14", "kalshi"), d)
d = E.display_score({"ticker": JK + "-ALCN", "side": "yes"})
ok("and 14-38 from Alcorn St.'s", d and (d["me"], d["opp"]) == (14, 38), d)
ok("leg_score still never sees Kalshi's data (isolation)", E.leg_score(leg) is None
   and not any(k in inspect.getsource(E.leg_score) for k in ("kalshi_score", "KLIVE", "display_score")))
post = copy.deepcopy(FX["live_datas"][0]["details"]); post.update(status="closed", widget_status="finished", quarter=4)
ok("a finished game reads Final", E._kfootball(post, True) == (38, 14, "Final"))
half = dict(post, status="inprogress", widget_status="live", match_status="Halftime", quarter=2)
ok("halftime reads Half", E._kfootball(half, True)[2] == "Half")
mid = E.KLIVE["ms"][JK]["id"]
E.KLIVE["live"][mid]["d"] = {"away_points": None, "home_points": "x", "quarter": "?", "status": "inprogress"}
try:
    got, raised = E.kalshi_score({"ticker": JK + "-JKST"}), False
except Exception:
    got, raised = None, True
ok("a bad feed field means no score for that game, never an error", not raised and got is None, got)

# ---- the 100%: Kalshi's own price (bid 99c / ask $1 -> 99.5%), never shown as a sure thing while it's open
mk = next(m for m in FX["kalshi_markets"] if m["ticker"].endswith("-JKST"))
lp = E.live_price(mk)
ok("Kalshi's mid for Jackson St. is 99.5% (that was the 100%)", abs(lp - 0.995) < 1e-9, lp)
ok("an open pick at 99.5% reads '>99%', a 64% one '64%', a won one '100%'",
   (E.chance_pct(lp), E.chance_pct(0.64), E.chance_pct(1.0)) == (">99%", "64%", "100%"))
ok("smart sell's 'to go your way' words use it", "chance_pct(nxt[0])" in inspect.getsource(E.plan_words))
js = next((open(p).read() for p in ("wtest/spa/common.js", os.path.join(os.environ.get("REPO", "../.."), "watcher/spa/common.js")) if os.path.exists(p)), "")
ok("the web app's pct() never rounds an open pick up to 100%", "x>=.995&&x<1?'>99%'" in js, bool(js))
