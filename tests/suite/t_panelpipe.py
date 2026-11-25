# CHECK: group=engine
# Issue #341: the daily panel's pipeline. (A) ESPN's scoreboard refuses a date range now, so free lines are read one day
# at a time and game-winner picks get an outside line again: singles and 2-5 leg combos reach the pool; every step's
# rejections are counted (the funnel) and said in plain English. (B) Kalshi's mid as fair, logged beside ours, on paper.
# (C) the cost-carry paper test. (D) at least 2 combos of each length 2-5 that clear the same cut-off. Nothing here may
# write the panel or quotes tables, buy, accept or change a stake.
import os, time, tempfile, importlib.util, copy
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
import datetime as _dt
# Pin the clock to noon Pacific (issue: these fixtures put kickoffs at now+3h/+4h, and the panel's "today" ends at 4 a.m.
# Pacific, so a run between 1 and 4 a.m. Pacific, e.g. CI at 11:54 UTC, saw those games as tomorrow's). Time still moves.
import datetime as _rdt, types as _types
_real_time = time.time
_OFF = _rdt.datetime(2026, 11, 24, 20, 0, tzinfo=_rdt.timezone.utc).timestamp() - _real_time()
time.time = lambda: _real_time() + _OFF


class _FDT(_rdt.datetime):
    @classmethod
    def now(cls, tz=None):
        return _rdt.datetime.fromtimestamp(time.time(), tz)


E.dt = _types.SimpleNamespace(**{k: getattr(_rdt, k) for k in dir(_rdt) if not k.startswith("__")}); E.dt.datetime = _FDT
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp(); E.SIZING_FILE = os.path.join(E.HERE, "s.json")
E.CUTOFF_FILE = os.path.join(E.HERE, "c.json"); E.REBUILD_FLAG = os.path.join(E.HERE, "flag"); E.HELD_FILE = os.path.join(E.HERE, "held.json")
E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.fetch_account = lambda **k: ([], 300.0, None)
E.account_events = lambda *a, **k: set()
E.fetch_scores = lambda *a, **k: None
E.injury_note = lambda code, *teams, hours=48: ([], False)
E.game_context = lambda *a, **k: []
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()


# ---- (A) the root cause: ESPN answers a date range with a 400; one request per day works
class Resp:
    def __init__(self, code, body):
        self.status_code, self._b, self.ok = code, body, code == 200

    def json(self):
        return self._b


def espn_ev(i, home, away, ml_home="-150", ml_away="+130"):
    start = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(now + 3 * 3600 + i * 60))
    return {"id": f"ev{i}", "date": start, "competitions": [{"status": {"type": {"state": "pre"}},
            "odds": [{"provider": {"name": "Draft Kings"}, "moneyline": {"home": {"close": {"odds": ml_home}},
                                                                        "away": {"close": {"odds": ml_away}}}}],
            "competitors": [{"homeAway": "home", "team": {"displayName": home}},
                            {"homeAway": "away", "team": {"displayName": away}}]}]}


asked = []


class FakeReq:
    RequestException = E._requests.RequestException

    def get(self, url, params=None, **kw):
        asked.append((url, dict(params or {})))
        if "espn.com" in url:
            d = str((params or {}).get("dates") or "")
            if "-" in d:
                return Resp(400, {"code": 400, "message": "Failed to get events endpoint."})
            today = _dt.date.today().strftime("%Y%m%d")
            return Resp(200, {"events": [espn_ev(0, "Boston Celtics", "New York Knicks"),
                                         espn_ev(1, "Miami Heat", "Chicago Bulls")] if d == today else
                                        [espn_ev(0, "Boston Celtics", "New York Knicks")]})   # same game again: deduped
        return Resp(200, [])                          # Polymarket: nothing


real_requests = E.requests
E.requests = FakeReq()
snap = E.free_snapshot(["nba"])
ok("free lines: this read's days are counted per league", E.ESPN_FREE.get("nba", {}).get("ok") == E.ESPN_DAYS[True])
E.requests = real_requests
espn = [p for u, p in asked if "espn.com" in u]
ok("free lines: ESPN asked one day at a time, never a range (ESPN answers a range with a 400)",
   espn and all("-" not in str(p.get("dates")) for p in espn) and len(espn) == E.ESPN_DAYS[True])
ok("free lines: the teams come back (the bug left this empty, so no pick had an outside line)",
   {"Boston Celtics", "New York Knicks", "Miami Heat", "Chicago Bulls"} <= set(snap["fair"]))
ok("free lines: a game listed on two days is counted once", len(snap["games"]["Boston Celtics"]) == 1)
ok("free lines: devigged, read time kept", abs(snap["fair"]["Boston Celtics"][0] + snap["fair"]["New York Knicks"][0] - 1) < 1e-6
   and snap["games"]["Boston Celtics"][0]["at"] > now - 60)
E.requests = type("Down", (), {"RequestException": E._requests.RequestException,
                               "get": lambda self, *a, **k: (_ for _ in ()).throw(E._requests.ConnectionError("down"))})()
ok("free lines: ESPN down = empty, never raises, counted for this read only",
   E.free_snapshot(["nba"])["fair"] == {} and E.ESPN_FREE["nba"]["bad"] == E.ESPN_DAYS[True] and E.ESPN_FREE["nba"]["ok"] == 0)
E.requests = real_requests

# ---- a league of pre-game games with outside lines: singles, combos (2-5 legs) and closing prices
tag = time.strftime("%y%b%d", time.gmtime(now)).upper()
TEAMS = [("BOS", "NYK"), ("MIA", "CHI"), ("DEN", "PHX"), ("LAL", "GSW"), ("DAL", "HOU"), ("MIL", "TOR"), ("ATL", "ORL"),
         ("SAC", "POR")]


def make_games():
    games = {}
    for i, (h, a) in enumerate(TEAMS):
        ev = f"KXNBAGAME-{tag}{a}{h}"
        E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 3 * 3600 + i * 600))
        games[ev] = [{"ticker": f"{ev}-{h}", "event": ev, "pick": h, "abbr": h, "p": 0.48, "bid": 0.46, "fair": 0.56,
                      "src": "Draft Kings", "line_at": now, "edge": 0.08, "exp": ""},
                     {"ticker": f"{ev}-{a}", "event": ev, "pick": a, "abbr": a, "p": 0.53, "bid": 0.51, "fair": 0.44,
                      "src": "Draft Kings", "line_at": now, "edge": -0.09, "exp": ""}]
    return games


G = make_games()
E.fetch_markets = lambda: []
E.week_games = lambda markets, loose=False, weeks=1: ({e: [dict(x) for x in sd] for e, sd in G.items()}, {}, None)
E.attach_fair = lambda games, book: (len(games), {})
E.load_book_state = lambda snap: {}
E.line_candidates = lambda code, everything=False: []
E.predict_quote = lambda c: None
E.thin_legs = lambda legs: False
E.LEAGUE_CODE = "nba"
E.set_league("nba")
cands = E.panel_collect(E.empty_snapshot(), "nba", log=lambda *a: None)
kinds = {}
for c in cands:
    kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
lens = sorted({len(c["legs"]) for c in cands if c["kind"] == "combo"})
ok("pool by kind: game-winner singles reach the panel pool", kinds.get("single", 0) >= 1)
ok("pool by kind: combos reach the panel pool, 2 to 5 legs", kinds.get("combo", 0) >= 4 and lens[:1] == [2] and 5 in lens)
ok("closing prices are recorded for sides with an outside line", E.store_rows("select count(*) n from closes")[0]["n"] == 16)
f = E.PANEL_FUNNEL.get("nba") or {}
ok("funnel: collection counts games, lines missing, singles, combos and the cut-off",
   f.get("games") == 8 and f.get("no_line") == 0 and f.get("singles") == kinds.get("single") and f.get("combos_built", 0) >= kinds.get("combo", 0)
   and "combo_cut" in f and f.get("cands") == kinds)

# (D) at least 2 of each length that clears the same cut-off; the first six are exactly the old six
per_len = {}
for c in cands:
    if c["kind"] == "combo":
        per_len[len(c["legs"])] = per_len.get(len(c["legs"]), 0) + 1
ok("core: at least 2 combos of each length 2-5 when they clear the cut-off", all(per_len.get(n, 0) >= 2 for n in (2, 3, 4, 5)))
ok("core: every combo still clears its own cut-off (no bar lowered)",
   all(c["pct"] >= E.combo_cutoff("nba", len(c["legs"]), c["legs"]) for c in cands if c["kind"] == "combo"))
built = E.value_combos(E.week_games([])[0], k=6, per_n=2)
old6 = [c for c in E.value_combos(E.week_games([])[0], k=6)]
ok("core: the old search comes back first and unchanged", [frozenset(l["ticker"] for l in c["legs"]) for c in built[:len(old6)]] ==
   [frozenset(l["ticker"] for l in c["legs"]) for c in old6] and not any(c.get("extra") for c in built[:len(old6)])
   and all(c.get("extra") for c in built[len(old6):]))
low = [dict(c, value_pct=0.5) for c in built]
ok("core: nothing under the cut-off is ever added", E.core_combos(low, "nba") == [])
mixed = [dict(c, value_pct=(2.0 if len(c["legs"]) == 3 else 0.5)) for c in built]
got = E.core_combos(mixed, "nba")
ok("core: extras only of a length still short, and only from those that clear", got and all(len(c["legs"]) == 3 for c in got)
   and sum(1 for c in got if c.get("core")) <= 2 and len(got) >= 2)

# (A) the funnel through build_panel, and the plain-English sheet
p = E.build_panel(codes=["nba"])
st = p["stats"]
fun = st.get("funnel") or {}
ok("build_panel: the pool by kind includes singles and combos", st["pool"].get("single", 0) >= 1 and st["pool"].get("combo", 0) >= 1)
ok("build_panel: the funnel carries the choice's numbers", "pool" in fun and "left" in fun and "trim" in fun and "drop" in fun
   and fun.get("collect", {}).get("nba", {}).get("games") == 8)
why = fun.get("why") or []
ok("funnel words: one line per league plus the choice, plain English", why and why[0].startswith("NBA: 8 games not started")
   and all(isinstance(w, str) and w.endswith(".") for w in why))
ok("build_panel: the panel stays inside its budget", p["stats"]["stake"] <= p["budget"] + 0.01)
ok("funnel words: a missing line and a cut-off are named",
   "no outside line" in " ".join(E.funnel_words({"collect": {"nba": {"games": 3, "no_line": 2, "combos_built": 4, "combo_cut": 4}}})))
ok("funnel words: what the choice left out", "Not picked: 2 on a game already covered" in
   " ".join(E.funnel_words({"left": {"overlap": 2}, "trim": 1, "bar": {"combo": 3}})))
logs = []
E.panel_pass(log=lambda *a: logs.append(" ".join(map(str, a))))
ok("panel_pass: the funnel goes in the log", any(x.startswith("panel funnel: NBA") for x in logs))
n_logs = len(logs)
E.panel_pass(log=lambda *a: logs.append(" ".join(map(str, a))))
ok("panel_pass: the same funnel isn't logged again", sum(1 for x in logs[n_logs:] if x.startswith("panel funnel")) == 0)

# choose_panel's core nudge: same budget, same stakes, never over budget
pool = [c for c in cands if E._qualifies(c)]
for budget in (6.0, 20.0, 60.0):
    pk, ss = E.choose_panel(pool, budget, 300.0, size=10)
    ok(f"choose_panel (budget {budget:g}): inside the budget, stakes are the bets' own sizes",
       sum(c["stake"] for c in pk) <= budget + 0.01 and all(abs(c["stake"] - E._size(c, 300.0)) < 1e-9 for c in pk))

# ---- (B) market-anchored fair: logs only, never changes a candidate
before = copy.deepcopy(cands)
E.MKT_SEEN.clear()
n = E.mkt_fair_shadow("nba", E.week_games([])[0], cands)
ok("market fair: every priced side and every combo candidate logged", n == 16 + kinds["combo"])
ok("market fair: candidates untouched", cands == before)
r = E.store_rows("select * from mkt_fair where id=?", (f"side:KXNBAGAME-{tag}NYKBOS-BOS",))[0]
ok("market fair: mid, our fair, the anchored fair (books' weight 0 until earned)",
   abs(r["mid"] - 0.47) < 1e-6 and abs(r["fair_book"] - 0.56) < 1e-6 and abs(r["fair_mkt"] - 0.47) < 1e-6 and r["w"] == 0)
ok("market fair: a claimed single edge that vanishes against the mid is a shadow skip",
   r["claimed"] == 1 and r["vanish"] == 1 and r["edge_book"] > 0 and r["edge_mkt"] < 0)
ok("market fair: at most once per market per 30 minutes", E.mkt_fair_shadow("nba", E.week_games([])[0], cands) == 0)
E.MKT_SEEN.clear()
E.mkt_fair_shadow("nba", E.week_games([])[0], cands)
ok("market fair: before the game only the latest row per market is kept",
   E.store_rows("select count(*) n from mkt_fair")[0]["n"] == n)
ok("market fair: phase is kept (never pooled)", {x["phase"] for x in E.store_rows("select phase from mkt_fair")} == {"pre"})

# weights are earned only with enough settled markets that the books predicted better
E._mkt_table()
E.store_x("delete from mkt_fair")
import random
rng = random.Random(3)
rows = []
for i in range(2500):                                 # the books know better than the mid: the truth is the books' chance
    fb = rng.uniform(0.3, 0.7)
    mid = min(max(fb + rng.choice((-0.08, 0.08)), 0.05), 0.95)
    y = rng.random() < fb
    rows.append((f"side:T{i}", now - 86400, "nba", "nba", "win", "pre", f"T{i}", now - 3600, mid, mid, fb, mid, 0.0, 0, 0, 0, 0, 2.0,
                 "yes" if y else "no"))
E._mkt_insert(rows)
w = E.mkt_learn()
ok("market fair: the books earn a weight where their log loss beats the mid by enough", (w.get("nba|win|pre") or {}).get("w", 0) > 0)
E.store_x("delete from mkt_fair where rowid in (select rowid from mkt_fair limit 2350)")
w = E.mkt_learn()
ok("market fair: under 200 settled markets the mid stays the fair", (w.get("nba|win|pre") or {}).get("w") == 0)
s = E.mkt_fair_summary()
ok("market fair: the summary has its groups", s and s["groups"] and s["groups"][0]["kind"] == "win" and s["groups"][0]["n"] == 150)

# ---- (C) cost-carry: paper only
E._carry_table()
leg = lambda t, ev, p, b: {"ticker": t, "event": ev, "p": p, "bid": b}
a, b_ = leg("KXNBAGAME-X1-AAA", "KXNBAGAME-X1", 0.51, 0.49), leg("KXNBAGAME-X2-BBB", "KXNBAGAME-X2", 0.49, 0.47)
ok("carry: a quote at or under the product of the mids is paper-bought", E.carry_note([a, b_], 0.24, "shadow") == "paper")
ok("carry: once per set of picks a day", E.carry_note([a, b_], 0.23, "shadow") == "logged")
ok("carry: a dearer quote is only logged", E.carry_note([a, leg("KXNBAGAME-X3-C", "KXNBAGAME-X3", 0.5, 0.48)], 0.30, "shadow") == "logged")
ok("carry: a long shot isn't this test", E.carry_note([a, leg("KXNBAGAME-X4-D", "KXNBAGAME-X4", 0.2, 0.18)], 0.05, "shadow") is None)
ok("carry: a thin pick (wide gap) isn't priced", E.carry_note([a, leg("KXNBAGAME-X5-E", "KXNBAGAME-X5", 0.5, 0.3)], 0.2, "shadow") is None)
ok("carry: 4 legs aren't this test", E.carry_note([a, b_, a, b_], 0.05, "shadow") is None)
tot = leg("KXNBATOTAL-X1-T220", "KXNBATOTAL-X1", 0.5, None)
ok("carry: a same-game quote is logged, never paper-bought", E.carry_note([a, tot], 0.2, "shadow") == "logged" and
   E.store_rows("select paper, kind from carry where kind='same'")[0]["paper"] == 0)
E.store_x("update carry set kick=?", (now - 5 * 3600,))
E.fetch_results = lambda ts: {t: ("yes" if "AAA" in t or "BBB" in t else "no") for t in ts}
ok("carry: settled with Kalshi's results", E.carry_resolve() >= 3)
pr = E.store_rows("select outcome, pl, price from carry where paper=1")[0]
k, fee = E.order_contracts(5.0, 0.24)
ok("carry: paper profit counts the taking fee", pr["outcome"] == "yes" and abs(pr["pl"] - round(k - k * (0.24 + fee), 2)) < 1e-6)
cs = E.carry_summary()
ok("carry: the summary splits separate and same-game", {r["kind"] for r in cs["rows"]} == {"sep", "same"})

# carry_pass never runs paused, on the Pi or without trading access, and never accepts
sent = []
E.kalshi_send = lambda m, path, body=None, params=None: (sent.append((m, path)) or
                                                         ({"market_ticker": "MV1"} if "collections" in path else
                                                          {"id": "R1"} if path.endswith("/rfqs") else
                                                          {"quotes": [{"status": "open", "no_bid_dollars": "0.7700"}]} if m == "GET" else {}))
E.find_collection = lambda legs: "COLL"
E.rfq_unsure = lambda *a, **k: False
E.hold_refusal = lambda kind: (False, "")
E.can_trade = lambda: True
G2 = {}
for i, (h, a2) in enumerate(TEAMS[:4]):
    ev = f"KXNBAGAME-{tag}Z{i}{h}"
    E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 2 * 3600))
    G2[ev] = [{"ticker": f"{ev}-{h}", "event": ev, "pick": h, "p": 0.50, "bid": 0.48, "exp": ""},
              {"ticker": f"{ev}-{a2}", "event": ev, "pick": a2, "p": 0.51, "bid": 0.49, "exp": ""}]
E.week_games = lambda markets, loose=False, weeks=1: ({e: [dict(x) for x in sd] for e, sd in G2.items()}, {}, None)
E.TRADING_PAUSED = lambda: True
ok("carry_pass: nothing while paused", E.carry_pass({}, log=lambda *a: None) == [] and not sent)
E.TRADING_PAUSED = None
E.ROLE_BACKUP = True
ok("carry_pass: nothing on the Pi", E.carry_pass({}, log=lambda *a: None) == [] and not sent)
E.ROLE_BACKUP = False
E.time.sleep = lambda s: None
did = E.carry_pass({}, log=lambda *a: None)
ok("carry_pass: one quote, withdrawn, never accepted", did and any(m == "DELETE" and "/rfqs/R1" in pth for m, pth in sent)
   and not any(m == "PUT" or "accept" in pth for m, pth in sent))
rows_c = E.store_rows("select count(*) n from carry where source='carry'")[0]["n"]
E.kalshi_send = lambda m, path, body=None, params=None: (sent.append((m, path)) or
                                                         ({"market_ticker": "MV1"} if "collections" in path else
                                                          {"id": "R2"} if path.endswith("/rfqs") else
                                                          {"quotes": []} if m == "GET" else {}))
E.clear_my_rfqs = lambda t: sent.append(("CLEAR", t))
did2 = E.carry_pass({}, log=lambda *a: None)
ok("carry_pass: no price = an asked row (counts toward the day, never asked again), withdrawn",
   did2 and "no price" in did2[0] and E.store_rows("select count(*) n from carry where source='carry'")[0]["n"] == rows_c + 1
   and ("DELETE", "/communications/rfqs/R2") in sent and not any(x[0] == "CLEAR" for x in sent))   # #350: never withdraws a request that is not its own
ok("carry: asked rows never show as quotes", sum(r["quotes"] for r in E.carry_summary()["rows"]) ==
   E.store_rows("select count(*) n from carry where price is not null")[0]["n"])
E.KICKOFF["KXNBAGAME-X1"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 600))
ok("carry: a quote with a game under way is never logged (no pooling with pregame)",
   E.carry_note([a, leg("KXNBAGAME-X6-F", "KXNBAGAME-X6", 0.5, 0.48)], 0.2, "build") is None)
n_q = E.store_rows("select count(*) n from quotes")[0]["n"] if E.store_rows("select name from sqlite_master where name='quotes'") else 0
ok("carry_pass: the quote never goes in the quotes table (no learning, no cut-offs)", n_q == 0)
ok("paper tests never write the panel", not E.store_rows("select name from sqlite_master where name='panel'") or
   all(r["mode"] != "carry" for r in E.store_rows("select mode from panel")))
