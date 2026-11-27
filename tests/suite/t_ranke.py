# CHECK: group=engine
# rank-e: display and ranking only. (#243) Best bets rank, size and simulate on the chance corrected by YOUR record
# (calib_fair), not the books' raw one; (#204) the flip note states expected dollars after fees on that same chance and
# never calls a flip good when they fall; (#265) a loss guard both the stop-loss switch and the learned loss cut use is
# judged on the decision that is really running. Nothing is bought or sold here.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E._held_all = lambda: []
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.MAIN_SAVED = os.path.join(E.HERE, "main.json"); E.SIZING_FILE = os.path.join(E.HERE, "s.json")
E.leg_score = lambda l: None
E.injury_note = lambda code, *teams, hours=48: ([], False)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
TAG = time.strftime("%y%b%d", time.gmtime(now + 86400)).upper()
SENT = []
E.kalshi_send = lambda *a, **k: SENT.append(a) or (_ for _ in ()).throw(AssertionError("display only: never sends"))
E.sizing_base = lambda *a, **k: (1000.0, {})
SIMS = []


def fake_sim(spec_, **k):
    SIMS.append(spec_)
    return {"ev": 1.0, "route": "sell", "p_exit": 0.6, "win": 0.6, "hold_profit": 0.3, "exit_mins": 40.0, "stake": 5.0, "n": 1}


E.simulate_exit = fake_sim


def side(code, pick, p, fair):
    ev = f"KXNBAGAME-{TAG}{code}"
    E.KICKOFF[ev] = E.dt.datetime.fromtimestamp(now + 20 * 3600, E.dt.timezone.utc).isoformat()
    return {"ticker": f"{ev}-{code[:3]}", "event": ev, "pick": pick, "p": p, "fair": fair, "src": "book", "line_at": now - 60, "tie": False}


def game(code, a, b, pa, fa):
    return {f"KXNBAGAME-{TAG}{code}": [side(code, a, pa, fa), dict(side(code, b, round(1 - pa, 2), round(1 - fa, 2)),
            ticker=f"KXNBAGAME-{TAG}{code}-{code[3:]}")]}


def calib(rows):
    E.CALIB.update(at=time.time(), m=rows)


# A: your record says the 65-80% band wins less than the books say; the 50-65% band is right
gA, gB = game("AAABBB", "Aces", "Bees", 0.60, 0.72), game("CCCDDD", "Cats", "Dogs", 0.50, 0.60)
games = {**gA, **gB}
TA, TB = gA[next(iter(gA))][0]["ticker"], gB[next(iter(gB))][0]["ticker"]
calib({})
E.BEST_LOOK = 1
E.SB_GATE.pop("sims", None); SIMS.clear()
E.best_bets_feed(games, [], [], now)
ok("A: with no record the books' chance ranks (the Aces' bigger raw edge is looked at first)",
   len(SIMS) == 1 and SIMS[0]["id"] == "single:" + TA)
calib({"all": [(0.65, 0.80, 0.72, 0.66, 3000)]})
E.SB_GATE.pop("sims", None); SIMS.clear()
f = E.best_bets_feed(games, [], [], now)
ok("A: on your record the Aces' edge shrinks, so the Cats rank first and are the ones looked at",
   len(SIMS) == 1 and SIMS[0]["id"] == "single:" + TB)
ok("A: what is simulated uses the corrected chance (the Aces' 72% would read lower; the Cats stay 60%)",
   abs(SIMS[0]["legs"][0]["q0"] - 0.60) < 1e-6)
E.BEST_LOOK = 30
E.SB_GATE.pop("sims", None); SIMS.clear()
f = E.best_bets_feed(games, [], [], now)
a = next(x for x in f["items"] if x["ticker"] == TA)
ok("A: a shown row carries the corrected chance and keeps the books' one beside it",
   a["chance_book"] == 0.72 and a["chance"] < 0.72 and a["fair"] == a["chance"])

# B: an edge that exists only on the books' chance is dropped
calib({"all": [(0.0, 1.0, 0.60, 0.40, 3000)]})
E.SB_GATE.pop("sims", None); SIMS.clear()
f = E.best_bets_feed(games, [], [], now)
ok("B: a bet with no edge left on your record is not listed, and is never simulated", f["items"] == [] and not SIMS)
ok("B: the feed still says how many it checked", f["looked"]["single"] >= 2)
calib({})

# C: a combo ranks on the corrected chance too
legs = [{"ticker": TA, "event": "e1", "pick": "Aces", "p": 0.60, "fair": 0.72}, {"ticker": TB, "event": "e2", "pick": "Cats", "p": 0.50, "fair": 0.60}]
c = E._cand("combo", "nba", legs, 0.72 * 0.60, 0.10, "", pct=1.10, fair_mult=round(1 / (0.72 * 0.60), 3))
calib({"all": [(0.65, 0.80, 0.72, 0.66, 3000)]})
r = E._best_calibrate(c)
ok("C: a combo's chance is the corrected legs multiplied, its return follows, the book's chance is kept",
   r is not None and r["chance"] < c["chance"] and r["ret"] < 0.10 and r["chance_book"] == c["chance"]
   and abs(r["ret"] - (1.10 * r["chance"] / c["chance"] - 1)) < 1e-3)
calib({})
r0 = E._best_calibrate(c)
ok("C: with an empty record nothing changes", r0["chance"] == c["chance"] and abs(r0["ret"] - 0.10) < 1e-3)
ok("C: the feed never sent anything", not SENT)

# D: the flip verdict in dollars
L1 = [{"ticker": TA, "fair": 0.70, "p": 0.60}]
L2 = [{"ticker": TB, "fair": 0.70, "p": 0.69}]
calib({})
ev1, ev2 = E.flip_ev(L1, 20.0), E.flip_ev(L2, 20.0)
ok("D: expected dollars after the fee at the stake (positive when fair beats price plus fee, tiny when it barely does)",
   ev1 > 0 and ev2 < ev1 and abs(ev1 - 20 / 0.6 * (0.70 - 0.60 - E.single_fee(0.60))) < 1e-9)
calib({"all": [(0.65, 0.80, 0.72, 0.60, 3000)]})
ok("D: and on your record, where that band wins less, the same flip is worth less", E.flip_ev(L1, 20.0) < ev1)
ok("D: an unpriced leg gives no dollars (never a guess)", E.flip_ev([{"ticker": TA, "fair": 0.7}], 20.0) is None)
calib({})
# a flip to a favourite: likelier to hit, but the price eats the edge -> not "Good flip"
Gm = {"KXNBAGAME-%sHHHIII" % TAG: [dict(side("HHHIII", "Hawks", 0.40, 0.45)), dict(side("HHHIII", "Ibis", 0.62, 0.55), ticker="KXNBAGAME-%sHHHIII-III" % TAG)]}
hh = Gm["KXNBAGAME-%sHHHIII" % TAG]
old = {"kind": "value", "legs": [dict(hh[0], event=hh[0]["event"])], "fair": 20 / 0.45, "min": 1, "kalshi": 20 / 0.40, "tier": ""}
E.CTX.update(combos=[old], all_games=Gm, games=Gm, stake=20.0, offers={}, card_notes={})
E.pickable = lambda x: True
E.save_combo = lambda *a, **k: None
E.simulate = lambda combos, g: (0, [0.45 if combos[0] is old else 0.55, 0.55] if False else [0.45, 0.55])
E.simulate = lambda combos, g: (0, [0.45, 0.55])
ok_, note = E.flip_pick(1, hh[0]["ticker"])
ok("D: the flip note states expected dollars before and after, after fees, on your record",
   ok_ and "Expected profit at $20" in note and "after fees" in note)
ok("D: a likelier flip whose expected dollars fall is not called a Good flip", "Good flip" not in note)

# E: the loss-guard judge counts the decision that is running (#265)
T1 = TA
c1 = {"stake": 10.0, "pl": -10.0, "pays": 20.0, "legs": [{"ticker": T1, "p": 0.6}]}
slp = [(now + 100 * k, {T1: (ch, "AAA 40-50 BBB " + sc)}) for k, (ch, sc) in enumerate(
    [(0.3, "Q3 6:00"), (0.3, "Q3 5:00"), (0.3, "Q3 4:00"), (0.3, "Q3 3:00"), (0.1, "Q4 5:00"), (0.0, "Final")])]
base = {"sl_prog": 0.5, "sl_drop": 0.2, "sl_checks": 3, "sl_span": 180, "sl_gap": 300}
off = E.knob_judge("sl", [(c1, None, slp)], dict(base, sl_auto=0), "sl_drop", 0.25)
ok("E: switch off and no cut: a step of a shared guard changes nothing (a feature that is off cannot justify it)",
   off[0][1] == 0.0)
on = E.knob_judge("sl", [(c1, None, slp)], dict(base, sl_auto=1), "sl_drop", 0.25)
ok("E: switch on: the step is judged on the switch's replay as before",
   abs(on[0][1] - (E._knob_res_sl(c1, slp, dict(base, sl_drop=0.25), {}) - E._knob_res_sl(c1, slp, base, {}))) < 1e-9)
seen = []
real = E._knob_res_replay
E._knob_res_replay = lambda c_, path, slp_, v, cache, hair=False: seen.append(v["sl_drop"]) or (-5.0 if v["sl_drop"] < 0.22 else -1.0)
cutv = dict(base, sl_auto=0, smart_loss=0.15, smart_floor=1.5, smart_lam=0.35)
cut = E.knob_judge("sl", [(c1, [("p",)], slp)], cutv, "sl_drop", 0.25)
E._knob_res_replay = real
ok("E: loss cut on (switch off): the step is judged on the cut's real price replay", seen and abs(cut[0][1] - 4.0) < 1e-9)
ok("E: the live loss guards, the tuner and the cut itself are untouched (judge only)",
   {"sl_prog", "sl_drop", "sl_checks", "sl_span", "sl_gap"} <= set(E.KNOB_LIVE))
