# CHECK: group=engine
# Build's "Best bets today" (issue #63): ONE ranked, recommend-only feed. A bet is listed only with BOTH an edge at a fair
# price after fees AND a likely route to profit under smart sell's exit policy; ranked by expected dollars at the
# suggested stake; fails closed (unreadable balance, an unmodellable bet, any error = not listed); display only (nothing
# is ever sent to Kalshi from here). The simulator is faked (an expected-dollars table by bet id); no network, no money.
import os, time, tempfile, importlib.util, copy
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.MAIN_SAVED = os.path.join(E.HERE, "main.json"); E.SIZING_FILE = os.path.join(E.HERE, "s.json")
E.leg_score = lambda l: None
E.injury_note = lambda code, *teams, hours=48: ([], False)      # no injury news (never the network)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
TAG = time.strftime("%y%b%d", time.gmtime(now + 86400)).upper()

SENT = []
E.kalshi_send = lambda *a, **k: SENT.append(a) or (_ for _ in ()).throw(AssertionError("the feed must never send an order"))
real_base = E.sizing_base
ok("0: reading the sizing base for display writes nothing (the panel's own state is left alone)", (lambda: (
    E.save_json(E.SIZING_FILE, {"month": "2000-01", "base": 50}),
    real_base(1000.0, save=False),
    E.load_json(E.SIZING_FILE, {}) == {"month": "2000-01", "base": 50})[-1])())
E.sizing_base = lambda *a, **k: (1000.0, {})

EVS = {}
SIMS = []


def fake_sim(spec_, **k):
    SIMS.append(spec_["id"])
    e = EVS.get(spec_["id"])
    if e is None:
        return None
    ev, route = e
    return {"ev": ev, "route": route, "p_exit": 0.6 if route == "sell" else 0.1, "win": 0.6, "hold_profit": 0.3,
            "exit_mins": 40.0, "stake": 5.0, "n": 1}


E.simulate_exit = fake_sim
E.SB_GATE.pop("sims", None)


def side(code, pick, p, fair, kick_h=20, tie=False):
    ev = f"KXNBAGAME-{TAG}{code}"
    E.KICKOFF[ev] = E.dt.datetime.fromtimestamp(now + kick_h * 3600, E.dt.timezone.utc).isoformat()
    return {"ticker": f"{ev}-{code[:3]}", "event": ev, "pick": pick, "p": p, "fair": fair, "src": "book", "line_at": now - 60,
            "tie": tie}


def game(code, a, b, pa, fa):
    return {f"KXNBAGAME-{TAG}{code}": [side(code, a, pa, fa), dict(side(code, b, round(1 - pa, 2), round(1 - fa, 2)),
            ticker=f"KXNBAGAME-{TAG}{code}-{code[3:]}")]}


def tick(g):
    return {s["pick"]: s["ticker"] for sd in g.values() for s in sd}


# a few games: every home pick has a 0.06 edge (0.50 price, 0.58 fair, minus the fee)
g1 = game("AAABBB", "Aces", "Bees", 0.50, 0.58)
g2 = game("CCCDDD", "Cats", "Dogs", 0.50, 0.58)
g3 = game("EEEFFF", "Eels", "Fox", 0.50, 0.58)
games = {**g1, **g2, **g3}
T = {**tick(g1), **tick(g2), **tick(g3)}
for t, ev in ((T["Aces"], 1.20), (T["Cats"], 0.60), (T["Eels"], 0.90)):
    EVS["single:" + t] = (ev, "sell" if t != T["Cats"] else "hold")
EVS["single:" + T["Eels"]] = (0.90, "none")        # an edge but no route to profit (no exit chance, low win chance)

f = E.best_bets_feed(games, [], [], now)
ids = [x["ticker"] for x in f["items"]]
ok("A: only bets with an edge AND a route are listed (no route = out, even with an edge)", set(ids) == {T["Aces"], T["Cats"]})
ok("A: ranked by expected dollars at the stake, biggest first", ids == [T["Aces"], T["Cats"]]
   and f["items"][0]["ev"] > f["items"][1]["ev"] > 0)
a = f["items"][0]
ok("A: each row carries the plain facts the card shows (price, fair, edge, stake, dollars, route)",
   a["kind"] == "single" and a["price"] == 0.5 and a["fair"] == 0.58 and a["edge"] > 0.025 and a["stake"] >= 2
   and a["route"] == "sell" and a["p_exit"] == 0.6 and a["game"] == "Aces vs Bees" and a["pick"] and a["league"] != "x")
ok("A: expected dollars = the simulator's dollars on $5 scaled to the stake", abs(a["ev"] - round(1.20 * a["stake"] / 5, 2)) < 0.011)
ok("A: nothing was sent to Kalshi (display only)", not SENT)
ok("A: no games' sides with an unfair price slip in (the Bees at 0.50/0.42 have no edge)", T["Bees"] not in ids)

# ---- fail closed
E.SB_GATE.pop("sims", None)
EVS.pop("single:" + T["Aces"])
f = E.best_bets_feed(games, [], [], now)
ok("B: a bet the simulator can't model is left out (never guessed)", T["Aces"] not in [x["ticker"] for x in f["items"]])
E.SB_GATE.pop("sims", None)
E.sizing_base = lambda *a, **k: (None, {"guess": True})
f = E.best_bets_feed(games, [], [], now)
ok("B: an unreadable Kalshi balance recommends nothing and says why", f["items"] == [] and "balance" in f["why"])
E.sizing_base = lambda *a, **k: (1000.0, {})
real = E._sb_sim
E._sb_sim = lambda *a, **k: 1 / 0
f = E.best_bets_feed(games, [], [], now)
ok("B: a simulator error never raises and lists nothing", f["items"] == [] and f["why"])
E._sb_sim = real
E.SB_GATE.pop("sims", None)
near = game("SSSTTT", "Seals", "Tigers", 0.50, 0.58)
for s_ in near.values():
    for x in s_:
        E.KICKOFF[x["event"]] = E.dt.datetime.fromtimestamp(now + 3600, E.dt.timezone.utc).isoformat()
EVS["single:" + tick(near)["Seals"]] = (1.2, "sell")
fresh_near = E.best_bets_feed(near, [], [], now)
for s_ in near.values():
    for x in s_:
        x["line_at"] = now - 3 * 3600
f = E.best_bets_feed(near, [], [], now)
ok("B: a game starting soon is listed on a fresh line but not on one hours old", len(fresh_near["items"]) == 1 and f["items"] == [])

# ---- the news guard (a pick priced well under its chance right after fresh injury news) leaves a bet out
E.SB_GATE.pop("sims", None)
EVS["single:" + T["Aces"]] = (1.2, "sell")
E.injury_note = lambda code, *teams, hours=48: (["Aces: Star (G) Out"], True)
f = E.best_bets_feed(games, [], [], now)
ok("B: fresh injury news with a big gap between price and chance = left out", T["Aces"] not in [r["ticker"] for r in f["items"]])
E.injury_note = lambda code, *teams, hours=48: ([], False)
E.SB_GATE.pop("sims", None)

# ---- empty state
f = E.best_bets_feed({}, [], [], now)
ok("C: nothing at all: 'Nothing clears your bar right now'", f["items"] == [] and f["why"].startswith("Nothing clears your bar right now"))
E.SB_GATE.pop("sims", None)
for k in list(EVS):
    EVS[k] = (0.01, "none")
f = E.best_bets_feed(games, [], [], now)
ok("C: edges but no route: the empty message names how many were checked", f["items"] == [] and "checked" in f["why"])

# ---- spreads and totals: they arrive already vetted by line_recommend (#117: learned bar, fillable size, exit route)
EVS.clear()
E.SB_GATE.pop("sims", None)
ev = f"KXNBASPREAD-{TAG}GGGHHH"
E.KICKOFF[f"KXNBAGAME-{TAG}GGGHHH"] = E.dt.datetime.fromtimestamp(now + 20 * 3600, E.dt.timezone.utc).isoformat()


def line(strike, p, fair, stake=14.6, exp=2.31, rec=True, route="sell"):
    e = round(fair - p - E.single_fee(p), 4)
    return {"ticker": f"{ev}-GGG{strike}", "event": ev, "pick": f"Gnus win by {strike}+", "fair": fair, "p": p, "rec": rec,
            "edge": e, "kind": "spread", "line": strike, "game": "Gnus at Hogs", "min_edge": 0.04, "stake": stake, "n": 31,
            "exp": exp, "capped": "stake", "route": route, "p_exit": 0.58, "win": fair, "exit_mins": 30.0,
            "start": E.dt.datetime.fromtimestamp(now + 20 * 3600, E.dt.timezone.utc).isoformat()}


good, notrec, nostake, noexp = line(3.5, 0.40, 0.50), line(5.5, 0.30, 0.285, rec=False), line(6.5, 0.40, 0.50, stake=0), line(7.5, 0.40, 0.50, exp=0)
f = E.best_bets_feed({}, [good, notrec, nostake, noexp], [], now)
lt = [x["ticker"] for x in f["items"]]
ok("D: only vetted recommendations are listed (not a raw strike, no stake, no expected dollars)", lt == [good["ticker"]])
it = f["items"][0]
ok("D: a vetted spread keeps its own fillable stake, expected dollars, route and bar (no re-pricing)",
   it["kind"] == "line" and it["game"] == "Gnus at Hogs" and it["stake"] == 14.6 and it["ev"] == 2.31 and it["route"] == "sell"
   and it["n"] == 31 and it["min_edge"] == 0.04 and it["edge"] == good["edge"] and "(Gnus at Hogs)" in it["pick"])
f = E.best_bets_feed({}, [good], [], now)
ok("D: ranked with the rest by expected dollars", f["items"][0]["ev"] == 2.31)
ok("D: the 'looked' count includes every row seen", E.best_bets_feed({}, [good, notrec], [], now)["looked"]["line"] == 2)
E.sizing_base = lambda *a, **k: (None, {"guess": True})
f = E.best_bets_feed(games, [good], [(1, {"kind": "value", "legs": [side("KKKLLL", "Kites", 0.60, 0.64)], "fair": 3.0}, 1.08)], now)
ok("D: with an unreadable balance only the vetted line shows (its stake is its own); singles and combos are out",
   [x["kind"] for x in f["items"]] == ["line"])
f = E.best_bets_feed(games, [], [], now)
ok("D: unreadable balance and nothing vetted says so plainly", f["items"] == [] and "balance" in f["why"])
E.sizing_base = lambda *a, **k: (1000.0, {})

# ---- combos: value combos only, priced at or above fair and above the cut-off
E.SB_GATE.pop("sims", None)
EVS.clear()
l1, l2 = side("KKKLLL", "Kites", 0.60, 0.64), side("MMMNNN", "Moths", 0.55, 0.58)
combo = {"kind": "value", "legs": [l1, l2], "fair": 5 / (0.64 * 0.58)}
EVS["combo:" + "+".join(sorted([l1["ticker"], l2["ticker"]]))] = (0.7, "hold")
cut = E.CFG["accept_pct"] / 100
f = E.best_bets_feed({}, [], [(1, combo, 1.08)], now)
ok("E: a value combo that should pay above fair, with a route, is listed", len(f["items"]) == 1 and f["items"][0]["kind"] == "combo"
   and f["items"][0]["i"] == 1 and f["items"][0]["ev"] > 0)
ok("E: one that pays under fair is not", E.best_bets_feed({}, [], [(1, combo, 0.97)], now)["items"] == [])
ok("E: a combo with no predicted price yet is not", E.best_bets_feed({}, [], [(1, combo, None)], now)["items"] == [])
ok("E: only 'value' combos qualify", E.best_bets_feed({}, [], [(1, dict(combo, kind="safer"), 1.08)], now)["items"] == [])

# ---- the cap on rows and the inputs stay as they were
E.SB_GATE.pop("sims", None)
many = {}
for i in range(10):
    many.update(game(f"X{i:02d}YYY", f"T{i}", f"U{i}", 0.50, 0.58))
for sd in many.values():
    EVS["single:" + sd[0]["ticker"]] = (0.5 + len(EVS) / 100, "sell")
before = copy.deepcopy(many)
f = E.best_bets_feed(many, [], [], now)
ok("F: at most BEST_MAX rows, biggest expected dollars first", len(f["items"]) == E.BEST_MAX
   and [x["ev"] for x in f["items"]] == sorted((x["ev"] for x in f["items"]), reverse=True))
ok("F: the inputs are not changed", many == before)
ok("F: never sent anything", not SENT)

# ---- (#414) a market Pete holds, just bought or has an unclear order on is left out of the pick lists (display only)
E.RECENT_BUYS.clear()
E.SINGLES["items"] = []
g414 = game("HELDAA", "Heldteam", "Otherteam", 0.50, 0.58)
held_t = g414[f"KXNBAGAME-{TAG}HELDAA"][0]["ticker"]
ok("414: nothing held -> held_markets is empty", E.held_markets() == set())
E.SINGLES["items"] = [{"t": held_t, "event": f"KXNBAGAME-{TAG}HELDAA", "cost": 1.68, "state": "pre"}]
ok("414: an open single on the account is held", held_t in E.held_markets())
E.SINGLES["items"] = [{"t": held_t, "event": "x", "cost": 1.68, "state": "done"}]
ok("414: a finished single is not held", held_t not in E.held_markets())
E.SINGLES["items"] = []
E.RECENT_BUYS[held_t] = time.time()
ok("414: a buy in the last few minutes is held", held_t in E.held_markets())
E.RECENT_BUYS[held_t] = time.time() - E.RECENT_BUY_SECS - 5
ok("414: an old buy is forgotten", held_t not in E.held_markets() and held_t not in E.RECENT_BUYS)
E.save_json(E.ORDER_LEDGER, {f"{held_t}|bid|b": {"ts": time.time(), "why": "unclear"}})
ok("414: an unclear order (check) is held", held_t in E.held_markets())
E.save_json(E.ORDER_LEDGER, {})
E._ORDER_SHARED.unsure.clear()
ok("414: held_markets never sends anything", not SENT)
