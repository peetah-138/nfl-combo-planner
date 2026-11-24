# CHECK: group=engine
# Smart Buy stage 2 (issue #137): the skip-only gate and its learning dial per league. Fakes only: no network (the
# results Kalshi settled come from a stand-in), no money, temp files.
import os, time, tempfile, importlib.util, json, random, copy
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.MAIN_SAVED = os.path.join(E.HERE, "main.json"); E.SB_DIAL_FILE = os.path.join(E.HERE, "sb.json")
E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json")
E.leg_score = lambda l: None
E.SMART_CACHE.update(at=time.time() + 1e6, d={})
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()


class NoNet:
    RequestException = E.requests.RequestException

    def __getattr__(self, name):
        def call(*a, **k):
            raise E.requests.RequestException("no network in this test")
        return call


E.requests = NoNet()


def dial(d):
    E.save_json(E.SB_DIAL_FILE, d)
    E.SB_GATE.update(dial=None, dial_at=0)


def setting(v):
    E.save_json(E.MAIN_SAVED, v)


# ---- the switch: on by default; the old preview's stored 'off' was a default, not a choice
setting({})
ok("Smart Buy is on by default", E.smart_buy_on() is True)
setting({"smart_buy": False})
ok("the old preview switch's stored 'off' (a default, not a choice) doesn't turn the gate off", E.smart_buy_on() is True)
setting({"smart_buy_gate": False})
ok("Pete's 'off' on the Smart Buy switch is kept", E.smart_buy_on() is False)
ok("the switch is a shared setting the web app saves", "smart_buy_gate" in E.SHARED_KEYS and "smart_buy" not in E.SHARED_KEYS)
setting({})

# ---- a fake simulator: each candidate's expected dollars on $5 come from its id
EVS = {}
SIMS = []


def fake_sim(spec_, **k):
    SIMS.append(spec_["id"])
    return {"ev": EVS.get(spec_["id"], 0.5), "route": "hold", "p_exit": 0.3, "win": 0.5}


real_sim = E.simulate_exit
E.simulate_exit = fake_sim
TAG = time.strftime("%y%b%d", time.gmtime(now)).upper()


def cand(i, ev, lg="NBA", stake=5.0, kind="single"):
    t = f"KX{lg}GAME-{TAG}T{i:03d}-A"
    cid = f"{kind}:{t}"
    EVS[cid] = ev
    return {"id": cid, "kind": kind, "code": lg.lower(), "stake": stake, "chance": 0.55, "ret": 0.08, "price": 0.5,
            "kick": now + 3 * 3600, "legs": [{"ticker": t, "event": t.rsplit("-", 1)[0], "p": 0.5, "fair": 0.55}]}


# ---- learning: strictness 0 passes everything, without even simulating
dial({})
SIMS.clear()
xs = [cand(i, -2.0) for i in range(5)]
k, s = E.smart_buy_filter(xs, now)
ok("learning (no results yet): every bet passes", k == xs and not s)
ok("...and nothing is simulated for it", not SIMS)
d0 = E.sb_dial(["KXNBAGAME-26NOV21BOSNYK-BOS"], now)
ok("the dial says learning, level 0", d0["state"] == "learning" and d0["level"] == 0 and d0["key"] is None)
dial({"nba": {"n": 12, "level": 4}})
ok("a league with 12 of its own results is still learning, at 0 (its stored level doesn't count yet)",
   E.sb_dial(["KXNBAGAME-26NOV21BOSNYK-BOS"], now)["level"] == 0)

# ---- active: a league with 30+ of its own results uses its dial
dial({"nba": {"n": 40, "level": 4, "own": True}})        # bar: +$0.10 on $5
good, bad, edge = cand(1, 0.30), cand(2, -0.05), cand(3, 0.10)
k, s = E.smart_buy_filter([good, bad, edge], now)
ok("active: a bet expected to make less than the bar is skipped, the others kept (the bar itself passes)",
   [c["id"] for c in k] == [good["id"], edge["id"]] and [x["id"] for x in s] == [bad["id"]])
ok("the skip carries a short plain reason with the bet named", s[0]["why"] and "NBA's bar right now: +$0.10" in s[0]["why"]
   and "$5" in s[0]["why"] and s[0]["text"])
ok("...and its stake and games (for the extras budget)", s[0]["stake"] == 5.0 and s[0]["events"])
setting({"smart_buy_gate": False})
SIMS.clear()
k, s = E.smart_buy_filter([good, bad, edge], now)
ok("the off switch fully disables it: everything passes, nothing is simulated", len(k) == 3 and not s and not SIMS)
setting({})
early = {"id": "early:x", "kind": "early", "code": "nba", "stake": 4, "legs": [{"ticker": "KXNBAGAME-26NOV21BOSNYK-BOS", "p": 0.7, "fair": 0.7}]}
ok("a bet the simulator can't model (sell-early) passes untouched", E.smart_buy_gate(early, now) == (True, None))
E.simulate_exit = lambda *a, **k: 1 / 0
ok("a gate error passes the bet through today's rules (never raises)", E.smart_buy_gate(cand(4, -3.0), now)[0] is True)
E.simulate_exit = fake_sim

# ---- borrowing: a league short of results uses its sport's dial, then everyone's; never under the start (0)
EPL = "KXEPLGAME-26NOV21ARSCHE-ARS"
dial({"soccer": {"n": 40, "level": 2}, "all": {"n": 90, "level": 5}, "epl": {"n": 10, "level": 0}})
d = E.sb_dial([EPL], now)
ok("the Premier League with 10 results borrows soccer's dial (learning, from soccer)", d["level"] == 2 and d["key"] == "soccer" and d["state"] == "learning")
dial({"all": {"n": 90, "level": 5}})
ok("...and everyone's when soccer has none", E.sb_dial([EPL], now)["level"] == 5)
dial({"all": {"n": 90, "level": -3}})
ok("a borrowed level is never under the start", E.sb_dial([EPL], now)["level"] == 0)
dial({"soccer": {"n": 40, "level": 5}, "epl": {"n": 35, "level": 1, "own": True}})
ok("with its own 30+ results a league can be looser than its sport (only its own record loosens it)",
   E.sb_dial([EPL], now)["level"] == 1 and E.sb_dial([EPL], now)["state"] == "active")

# ---- the skip-only invariant, property-tested: output is a subset of the input, same order, same dicts, same stakes
rng = random.Random(137)
viol = 0
for trial in range(400):
    dial({lg: {"n": rng.choice([0, 10, 30, 80]), "level": rng.randint(-1, E.SB_DIAL_MAX + 2), "own": True}
          for lg in ("nba", "nhl", "nfl", "soccer", "all") if rng.random() < 0.8})
    setting({} if rng.random() < 0.8 else {"smart_buy_gate": False})
    items = [cand(trial * 20 + i, rng.uniform(-1, 1), lg=rng.choice(["NBA", "NHL", "NFL"]),
                  stake=rng.choice([2, 3.5, 5, 9]), kind=rng.choice(["single", "line"])) for i in range(rng.randint(0, 12))]
    snap = copy.deepcopy(items)
    k, s = E.smart_buy_filter(items, now)
    it = iter(items)
    subseq = all(any(x is y for y in it) for x in k)
    if not (subseq and len(k) + len(s) == len(items) and items == snap
            and all(x["stake"] == y["stake"] for x in k for y in snap if y["id"] == x["id"])
            and {x["id"] for x in s}.isdisjoint({x["id"] for x in k})):
        viol += 1
E.SB_GATE.setdefault("sims", {}).clear()
ok("400 random panels: the gate's output is always a subset of its input, in order, with identical stakes", viol == 0)
setting({})

# ---- build_panel: the gate runs after the choice, so the panel is a subset of the ungated one with the same stakes
E.sizing_base = lambda: (300.0, None)
E.spent_earlier_today = lambda now=None: 0.0
E.account_events = lambda: set()
E.day_items = lambda day: []
E.sport_pay_index = lambda: {}
pool = []
for i in range(10):
    c = cand(500 + i, [0.4, -0.3, 0.2, -0.6, 0.5, 0.05, 0.3, -0.1, 0.6, 0.25][i], stake=None)
    c.pop("stake")
    c.update(last=now + 60, kick=now + 1800, chance=0.5 + i / 100, ret=0.05 + i / 200, why="test")
    pool.append(c)
E.PANEL_POOL.clear()
E.PANEL_POOL["nba"] = (now, pool)
dial({})
off = E.build_panel(now=now)
dial({"nba": {"n": 50, "level": 4, "own": True}})
on = E.build_panel(now=now)
st_off = {c["id"]: c["stake"] for c in off["items"]}
ok("build_panel with an active dial: a subset of the ungated panel, every stake identical",
   off["items"] and all(c["id"] in st_off and c["stake"] == st_off[c["id"]] for c in on["items"]))
ok("...the bets under the bar are gone and listed as skipped", on.get("sb_skipped") and
   all(EVS[x["id"]] < 0.10 for x in on["sb_skipped"]) and all(EVS[c["id"]] >= 0.10 for c in on["items"])
   and len(on["items"]) + len(on["sb_skipped"]) == len(off["items"]))
ok("...and nothing new was picked in their place", {c["id"] for c in on["items"]} <= set(st_off))
ok("...and the card's numbers describe only the bets left", on["stats"]["stake"] == round(sum(c["stake"] for c in on["items"]), 2))
dial({})
ok("learning: build_panel is exactly as before", json.dumps(E.build_panel(now=now)["items"], sort_keys=True) == json.dumps(off["items"], sort_keys=True))

# ---- the swap at buy time: a replacement the gate would skip means a skip, never a second-best pick
E.PANEL_POOL["nba"] = (time.time(), [dict(c) for c in pool])
base = dict(pool[0], stake=5)
p_ = {"items": [base]}
dial({})
alt0 = E._replacement(base, p_)
EVS[alt0["id"]] = -1.0
E.SB_GATE.setdefault("sims", {}).clear()
dial({"nba": {"n": 50, "level": 4, "own": True}})
ok("a swap Smart Buy would skip: no swap at all (not the next one down)", alt0 and E._replacement(base, p_) is None)
EVS[alt0["id"]] = 0.9
E.SB_GATE.setdefault("sims", {}).clear()
ok("...and a swap that passes goes ahead as before", E._replacement(base, p_)["id"] == alt0["id"])

# ---- the dial's steps: the evidence is the band (the bets a step changes), and it must be clear
rows = [(0.5, 2.0)] * 30 + [(-0.5, -5.0)] * 10 + [(-0.5, 4.0)] * 2       # the low-EV bets mostly lost
k1, why = E._sb_step(rows, 0)
ok("tightens one step when the bets the next level would skip clearly lost money", k1 == 1 and "lost" in why)
ok("...and stays when the next step changes nothing", E._sb_step(rows, 1)[0] == 1)
rows2 = [(0.5, 1.0)] * 30 + [(0.05, 3.0)] * 12                           # bets between the $0 and +$0.10 bars won
k3, why3 = E._sb_step(rows2, 4)
ok("relaxes toward skipping nothing when the skipped bets clearly made money", k3 == 3 and "made" in why3)
ok("a band that's about even keeps the current level", E._sb_step([(0.5, 1.0)] * 30 + [(0.05, 4.5), (0.05, -5.0)] * 8, 4)[0] == 4)
ok("too few bets in the band: no step", E._sb_step([(0.5, 1.0)] * 30 + [(-0.5, -5.0)] * 9, 0)[0] == 0)
ok("a small average loss (under $0.25 on $5): no step", E._sb_step([(0.5, 1.0)] * 30 + [(-0.5, -0.1)] * 20, 0)[0] == 0)
noisy = [(0.5, 1.0)] * 30 + [(-0.5, 4.5)] * 5 + [(-0.5, -5.0)] * 7       # lost on average, but not clearly
ok("a loss that isn't clear (under 2 standard errors): no step", E._sb_step(noisy, 0)[0] == 0)
ok("under 100 results the dial stops at 3 (bar $0: it only skips bets expected to lose)",
   E._sb_step([(0.5, 1.0)] * 40 + [(0.05, -5.0)] * 20, 3)[0] == 3 and E._sb_step([(0.5, 1.0)] * 90 + [(0.05, -5.0)] * 20, 3)[0] == 4)
ok("never above the top or below 0", E._sb_step([(-9, -5.0)] * 140, E.SB_DIAL_MAX)[0] == E.SB_DIAL_MAX
   and E._sb_step([(-9, 5.0)] * 40, 0)[0] == 0)

# ---- results come in, and the dial learns from them (end to end, fake Kalshi results)
E._exit_shadow_table()
E.store_x("delete from exit_shadow")
RES = {}


def shadow_row(t, ev, kick, pays=9.5):
    E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, kick, price, ev, route, old, new, ver, pays) "
              "values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (kick - 3600, "panel:single:" + t, "panel", "nhl", "single",
                                                      json.dumps([t]), kick, 0.5, ev, "hold", 1, 1, 1, pays))


for i in range(40):
    t = f"KXNHLGAME-26NOV10G{i:03d}-A"
    low = i < 10
    RES[t] = "no" if low else ("yes" if i % 2 else "no")
    shadow_row(t, -0.5 if low else 0.5, now - 3 * 86400)
C = ["KXNHLGAME-26NOV10C1-A", "KXNHLGAME-26NOV10C2-A"]
RES.update({C[0]: "yes", C[1]: "no"})
E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, kick, ev, route, old, new, ver, pays) "
          "values(?,?,?,?,?,?,?,?,?,?,?,?,?)", (now - 3 * 86400, "panel:combo", "panel", "nhl", "combo", json.dumps(C),
                                                now - 3 * 86400 + 3600, 0.5, "none", 1, 1, 1, 20.0))
E.fetch_results = lambda tks: {t: RES[t] for t in tks if t in RES}
dial({})
E.SB_GATE["learn_at"] = 0
got = E.smart_buy_learn(now=now, force=True)
r = E.store_rows("select res, outcome from exit_shadow where tickers=?", (json.dumps(["KXNHLGAME-26NOV10G011-A"]),))[0]
ok("a won single is scored as its payout less the $5 stake", r["res"] == "won" and abs(r["outcome"] - 4.5) < 1e-6)
rc = E.store_rows("select res, outcome from exit_shadow where cand='panel:combo'")[0]
ok("a combo with one losing pick is a loss of the stake", rc["res"] == "lost" and rc["outcome"] == -5.0)
ok("its first time on its own record (41 results) it starts at what it borrowed (0), and says so",
   got.get("nhl", {}).get("own") and got["nhl"]["level"] == 0 and got["nhl"]["n"] == 41)
later = now + 5 * 86400
for i in range(19):                                             # games after that: low-EV bets keep losing
    t = f"KXNHLGAME-26NOV12H{i:03d}-A"
    RES[t] = "no"
    shadow_row(t, -0.4, now + 86400)
got = E.smart_buy_learn(now=later, force=True)
ok("19 new results since it started: not enough for a step yet", got["nhl"]["level"] == 0)
t = "KXNHLGAME-26NOV12H099-A"
RES[t] = "no"
shadow_row(t, -0.4, now + 86400)
got = E.smart_buy_learn(now=later + 10, force=True)
ok("the 20th: the low-EV bets clearly lost, so it tightens one step to 1",
   got["nhl"]["level"] == 1 and "lost" in (got["nhl"].get("why") or ""))
got = E.smart_buy_learn(now=later + 20, force=True)
ok("no new results since the last step: it stays put (one step at a time)", got["nhl"]["level"] == 1)
ok("the sport-wide and everyone's dials learn too", "all" in got and got["all"]["n"] == 61)
E.SB_GATE["learn_at"] = later + 30
ok("it looks again at most hourly unless forced", E.smart_buy_learn(now=later + 40) is not None)
E.fetch_results = lambda tks: 1 / 0
ok("a results failure never raises", E.sb_resolve(now=later + 50) == 0)

# ---- the shadow log keeps recording every candidate with the gate's verdict then (counterfactuals)
E.simulate_exit = real_sim
E.SB_CACHE["seen"].clear()
T = "KXNHLGAME-26NOV21PHIBOS-PHI"
dial({"nhl": {"n": 60, "level": E.SB_DIAL_MAX, "own": True}})
c = {"id": "single:" + T, "kind": "single", "code": "nhl", "legs": [{"ticker": T, "event": "KXNHLGAME-26NOV21PHIBOS", "p": 0.5, "fair": 0.52}],
     "chance": 0.52, "ret": 0.02, "kick": now + 3 * 3600}
E.smart_buy_shadow([c], "panel", now=now)
row = E.store_rows("select skip, strict, pays from exit_shadow where cand=?", ("panel:single:" + T,))
ok("a candidate the gate skips is still logged, with its reason and the level then",
   row and row[0]["strict"] == E.SB_DIAL_MAX and row[0]["skip"] and row[0]["pays"] and abs(row[0]["pays"] - 5 / (0.5 + E.single_fee(0.5))) < 1e-3)
E.simulate_exit = fake_sim

# ---- Buy ideas: the shadow's last read of each idea's market decides; unknown ideas stay
E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, ev, route, old, new, ver) values(?,?,?,?,?,?,?,?,?,?,?)",
          (now - 60, "idea:idea:1", "idea", "nba", "single", json.dumps(["KXNBAGAME-26NOV21AAABBB-AAA"]), -0.4, "none", 1, 0, 1))
E.store_x("insert into exit_shadow(ts, cand, source, league, kind, tickers, ev, route, old, new, ver) values(?,?,?,?,?,?,?,?,?,?,?)",
          (now - 60, "idea:idea:2", "idea", "nba", "single", json.dumps(["KXNBAGAME-26NOV21CCCDDD-CCC"]), 0.6, "hold", 1, 1, 1))
ideas = [{"idea_id": "i1", "picks": "AAA", "legs": ["KXNBAGAME-26NOV21AAABBB-AAA"]},
         {"idea_id": "i2", "picks": "CCC", "legs": ["KXNBAGAME-26NOV21CCCDDD-CCC"]},
         {"idea_id": "i3", "picks": "EEE", "legs": ["KXNBAGAME-26NOV21EEEFFF-EEE"]}]
dial({"nba": {"n": 50, "level": 3, "own": True}})
k, s = E.smart_buy_ideas_gate(ideas, now)
ok("ideas: the one expected to lose is skipped with a reason; a good one and an unchecked one stay, in order",
   [x["idea_id"] for x in k] == ["i2", "i3"] and [x["id"] for x in s] == ["i1"] and s[0]["why"])
dial({})
ok("ideas: learning leagues keep every idea", E.smart_buy_ideas_gate(ideas, now)[0] == ideas)
setting({"smart_buy_gate": False})
dial({"nba": {"n": 50, "level": 3, "own": True}})
ok("ideas: the off switch keeps every idea", E.smart_buy_ideas_gate(ideas, now)[0] == ideas)
setting({})

# ---- Results card: a line per league, and the 'not yet' progress toward a later opt-in (bigger stakes)
dial({"nhl": {"n": 61, "level": 1, "own": True, "why": "the 30 bets it now also skips lost $150.00 on $5 each"}})
E.store_x("update exit_shadow set skip='under the bar' where league='nhl' and ev < -0.2")   # what the gate said then
g = E.smart_buy_gate_summary(now=now)
nhl = next((x for x in g if x["league"] == "nhl"), None)
ok("the NHL line: active, strictness 1, how many it really skipped and what those skips saved",
   nhl and nhl["state"] == "active" and nhl["level"] == 1 and nhl["skipped"] == 30 and nhl["saved"] == 150.0 and nhl["why"])
ok("...with the opt-in bar's progress (50 settled, ahead, 55% of days up, CLV, skips helping) shown, not met",
   all(k_ in nhl["optin"] for k_ in ("n", "n_need", "ahead", "days_up", "clv", "beats", "met")) and nhl["optin"]["n_need"] == 50
   and nhl["optin"]["met"] is False and nhl["optin"]["beats"] is True)
nba = next((x for x in g if x["league"] == "nba"), None)
ok("a league with nothing settled yet shows as learning, 0 of 30", nba and nba["state"] == "learning" and nba["own"] == 0 and nba["need"] == 30)
an_src = open("wahome/engine.py").read()
ok("nothing in the gate sizes or adds a bet (no stake is ever written by it)",
   "c[\"stake\"] =" not in an_src[an_src.index("# ================================================================ Smart Buy, stage 2"):
                                 an_src.index("def _sb_pays")])

# ---- review fixes
E.SB_GATE.setdefault("sims", {}).clear()
SIMS.clear()
dial({"nba": {"n": 50, "level": 4, "own": True}})
E.smart_buy_filter([cand(900, 0.3)], now)
E.smart_buy_filter([cand(900, 0.3)], now)
ok("the same bet at the same prices is simulated once in a few minutes (the panel is built several times a pass)", len(SIMS) == 1)
E.SB_GATE["cols"] = False
E._exit_shadow_table()
ok("the result columns are there (and the flag is set only once they all are)", E.SB_GATE["cols"] is True)
