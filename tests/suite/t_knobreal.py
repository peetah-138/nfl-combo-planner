# CHECK: group=engine
# Issue #228 PR4 (#285): self-tuning's judge replays each bet against its REAL market record (_replay_real): a combo
# sells only at a real Kalshi offer recorded near that moment (or, with none, the estimate) that reaches smart sell's own
# slip (auto_slip, split from your Cash out retries' CASH_SLIP) times its line, never under cost unless cutting a loss;
# a single sells at its recorded bid, never into a gap wider than LIVE_SPREAD. So the two estimate allowances and the
# slip are judged too. Loosening steps are judged with a haircut on any price that isn't a real recorded one
# (KNOB_HAIRCUT); tightening steps are not. Sold real combos join the evidence with what holding paid (sale_outcomes);
# a panel combo is counted once. auto_slip: with the switch off (or nothing learned) exactly today's 97%.
import os, time, tempfile, importlib.util, json, random
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SB_DIAL_FILE = os.path.join(E.HERE, "sb.json"); E.SB_GATE["dial"] = None
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json"); E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.KNOBS_FILE = os.path.join(E.HERE, "knobs.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
rng = random.Random(285)


def switch(on):
    E.CFG["knobs_live"] = on
    E.save_json(E.MAIN_SAVED, {"knobs_live": on})
    E.KNOB_SWITCH["on"] = None
    E.KNOB_STATE_CACHE["d"] = None


def set_knobs(st):
    json.dump(st, open(E.KNOBS_FILE, "w"))
    E.KNOB_STATE_CACHE["d"] = None


NBA = "KXNBAGAME-26NOV21BOSNYK-BOS"
D = E.kalshi_discount(True)

# ---- 1. singles with nothing recorded: exactly the plain replay
diff = 0
for i in range(600):
    c = {"id": i, "kind": "single", "stake": 5.0, "price": rng.uniform(0.2, 0.8), "kick": now - 9000, "pl": rng.choice([-5.0, 4.0]),
         "legs": [{"ticker": NBA, "p": 0.5}]}
    xs = [rng.uniform(0.03, 0.97) for _ in range(rng.randint(3, 12))]
    path = [(now - 8000 + j * 60, {NBA: x}) for j, x in enumerate(xs)]
    kw = dict(fl=rng.choice([1.2, 1.5, 1.8]), lm=rng.choice([0.6, 1.0, 1.6]), loss=rng.choice([None, 0.2]),
              trail=rng.random() < .7, tp=rng.choice([0, 0.5]))
    if E._replay(c, path, **kw) != E._replay_real(c, path, mk={}, **kw):
        diff += 1
ok(f"a single with no recorded bid replays exactly as the plain replay (600 paths, {diff} differ)", diff == 0)

# ---- 2. a combo against real offers
P, cost = 20.0, 5.0
cb = {"id": "KXMVE-1", "kind": "combo", "stake": cost, "pays": P, "kick": now - 9000, "pl": -cost,
      "legs": [{"ticker": NBA}]}
qs = [0.55, 0.6, 0.62, 0.64, 0.66, 0.68]                     # a combo drifting up
path = [(now - 8000 + j * 60, {NBA: q}) for j, q in enumerate(qs)]
plain = E._replay(cb, path, fl=1.5)
ok("plain replay: it sells on the estimate at the first step over the line", plain is not None and plain[1] == "smart")
t_sell = None
for ts, cur in path:                                          # when the plain replay sells, and its line there
    est = D * cur[NBA] * P
    lam = E.SWING_BASE * E.SWING.get("nba", 1.0)
    fl2 = max(cur[NBA] * P - lam * P * (cur[NBA] * (1 - cur[NBA])) ** 0.5, 1.5 * cost)
    if est >= fl2:
        t_sell, line = ts, fl2
        break
low = E._replay_real(cb, path, fl=1.5, mk={"offers": [(t_sell - 5, line * 0.9)]})
ok("a real offer that came in under 97% of the line at that moment: no sale there (live passes it up)",
   low is None or low[0] != plain[0])
hi = E._replay_real(cb, path, fl=1.5, mk={"offers": [(t_sell - 5, line * 1.05)]})
ok("a real offer over the line: it sells at THAT offer, not the estimate", hi is not None and abs(hi[0] - round(line * 1.05 - cost, 2)) < 0.011)
nxt = E._replay_real(cb, path, fl=1.5, mk={"offers": [(t_sell + 30, line * 1.02)]})
ok("no offer yet: it takes the one Kalshi really gave next (live asks for one)", nxt is not None
   and abs(nxt[0] - round(line * 1.02 - cost, 2)) < 0.011)
o98 = line * 0.975
ok("the slip (auto_slip): an offer at 97.5% of the line sells at the start (97%), not at 98%",
   E._replay_real(cb, path, fl=1.5, mk={"offers": [(t_sell - 5, o98)]}) is not None
   and (E._replay_real(cb, path, fl=1.5, ex={"cash_slip": 0.98}, mk={"offers": [(t_sell - 5, o98)]}) or (0, ""))[0]
   != round(o98 - cost, 2))
sub = E._replay_real(cb, path, fl=1.2, mk={"offers": [(path[0][0], cost * 0.9)]})
ok("never under what was paid unless it is a loss cut (live's own guard)", sub is None or sub[0] >= -1e-9)
# the estimate allowance: an estimate just under the line, a real offer over it later
q0 = 0.6
lam = E.SWING_BASE * E.SWING.get("nba", 1.0)
fl2 = max(q0 * P - lam * P * (q0 * (1 - q0)) ** 0.5, 1.5 * cost)
P2 = 0.97 * 1.5 * cost / (D * q0)                           # the estimate is 97% of the line (1.5x what was paid):
cb2 = dict(cb, pays=P2)                                      # inside the 95% allowance, outside 100%
fl2b = max(q0 * P2 - lam * P2 * (q0 * (1 - q0)) ** 0.5, 1.5 * cost)
path2 = [(now - 8000 + j * 60, {NBA: q0}) for j in range(3)]
offers2 = [(now - 8000 + 120 + 10, fl2b * 1.01)]               # the offer Kalshi gave when the app asked
a = E._replay_real(cb2, path2, fl=1.5, mk={"offers": offers2})
b = E._replay_real(cb2, path2, fl=1.5, ex={"est_smart": 1.0}, mk={"offers": offers2})
ok("the estimate allowance is judged now: at 95% it asks and takes the real offer; at 100% it never acts",
   fl2b == 1.5 * cost and a is not None and abs(a[0] - round(fl2b * 1.01 - cost, 2)) < 0.011 and b is None)

# ---- 3. singles at the recorded bid, and the gap
cs = {"id": "s", "kind": "single", "stake": 5.0, "price": 0.5, "kick": now - 9000, "pl": -5.0, "legs": [{"ticker": NBA, "p": 0.5}]}
xs = [0.5, 0.6, 0.75, 0.9, 0.93, 0.95]
ps = [(now - 8000 + j * 60, {NBA: x}) for j, x in enumerate(xs)]
r0 = E._replay(cs, ps)
book_lo = [(ts - 10, cur[NBA] - 0.05, cur[NBA] - 0.03) for ts, cur in ps]
r1 = E._replay_real(cs, ps, mk={"book": book_lo})
ok("a single sells at its recorded bid (5 cents under the chance here), not at the chance",
   r0 is not None and (r1 is None or r1[0] < r0[0]))
book_wide = [(ts - 10, cur[NBA] - 0.01, cur[NBA] + 0.07) for ts, cur in ps]
ok("never into a gap wider than 6 cents", E._replay_real(cs, ps, mk={"book": book_wide}) is None)
book_old = [(ts - 1000, cur[NBA] - 0.05, cur[NBA] - 0.03) for ts, cur in ps]       # all far older than 180 s
ok("a bid older than smart sell's 180 s isn't used (the chance, as the plain replay)",
   E._replay_real(cs, ps, mk={"book": book_old}) == E._replay(cs, ps))

# ---- 4. the haircut: loosening steps only
ok("which way a step goes: a lower floor, a higher risk weight, a lower least chance, the loss cut on, a lower slip "
   "all loosen; their opposites don't",
   E.knob_loosens("smart_floor", 1.5, 1.4) and not E.knob_loosens("smart_floor", 1.5, 1.6)
   and E.knob_loosens("smart_lam", 1.0, 1.15) and not E.knob_loosens("smart_lam", 1.0, 0.85)
   and E.knob_loosens("exit_q_min", 0.5, 0.45) and E.knob_loosens("smart_loss", None, 0.15)
   and not E.knob_loosens("smart_loss", 0.15, None) and E.knob_loosens("auto_slip", 0.97, 0.96)
   and not E.knob_loosens("exit_est_smart", 0.95, 0.96) and E.knob_loosens("exit_est_smart", 0.95, 0.94))
hc = E._replay_real(cs, ps, mk={"hair": True})
ok("with the haircut a single with no recorded bid sells 3 cents under its chance (the plain replay: 1 cent)",
   r0 is not None and hc is not None and hc[0] < r0[0])
hcb = E._replay_real(cb, path, fl=1.5, mk={"hair": True})
ok("...and a combo with no real offer sells at 97% of its estimate",
   hcb is not None and E._replay_real(cb, path, fl=1.5, mk={}) is not None and hcb[0] < E._replay_real(cb, path, fl=1.5, mk={})[0])
ok("a real recorded price is never cut", E._replay_real(cb, path, fl=1.5, mk={"offers": [(t_sell - 5, line * 1.05)], "hair": True}) == hi)
SEEN = []
real_res = E._knob_res_replay
E._knob_res_replay = lambda c, path, slp, vals, cache, hair=False: SEEN.append(hair) or 0.0
rows = [({"id": 1, "kick": now, "stake": 5.0, "pl": 0.0}, [], [])]
cur = {n["name"]: n["start"] for n in E.KNOBS if n["cls"] == "tunable"}
E.knob_judge("replay", rows, cur, "smart_floor", 1.4)
lo = list(SEEN); SEEN.clear()
E.knob_judge("replay", rows, cur, "smart_floor", 1.6)
ok("the judge: a loosening step replays both sides with the haircut, a tightening one without",
   lo == [True, True] and SEEN == [False, False])
E._knob_res_replay = real_res
# a loosening step that looks good on optimistic prices but not on the haircut
bets = []
for i in range(30):
    c = {"id": i, "kind": "single", "stake": 5.0, "price": 0.5, "kick": now - 30 * 86400 + i * 3600, "pl": 5.0 * 0.85 if i % 2 else -5.0,
         "legs": [{"ticker": NBA, "p": 0.5}]}
    bets.append((c, [(now - 8000 + j * 60, {NBA: x}) for j, x in enumerate((0.5, 0.6, 0.66, 0.66))], []))
vals = dict(cur, sl_prog=0.5, sl_drop=0.2)
opt = sum(E._knob_res_replay(c, p, s, dict(vals, smart_floor=1.2), {}, False) - E._knob_res_replay(c, p, s, vals, {}, False)
          for c, p, s in bets)
hrt = sum(d for _, d, _ in E.knob_judge("replay", bets, vals, "smart_floor", 1.2, {}))
ok(f"a lower floor (a bet it sells, the current one rides) judged on the haircut gains less than on optimistic "
   f"prices (${hrt:.2f} vs ${opt:.2f})", opt != 0 and hrt < opt - 1)

# ---- 5. the evidence: sold combos join with what holding paid; a panel combo counts once
E._ledger_table(); E._panel_table()
E.store_x("insert into bets(combo, first_seen, cost, pays, legs, status, back, settled) values(?,?,?,?,?,?,?,?)",
          ("KXMVE-SOLD", now - 5 * 86400, 5.0, 20.0, json.dumps([NBA]), "cashed", 8.0, now - 4 * 86400))
E.store_x("insert into bets(combo, first_seen, cost, pays, legs, status, back, settled) values(?,?,?,?,?,?,?,?)",
          ("KXMVE-OPEN", now - 5 * 86400, 5.0, 20.0, json.dumps([NBA]), "cashed", 8.0, now - 4 * 86400))
E.store_x("insert into bets(combo, first_seen, cost, pays, legs, status, back, settled) values(?,?,?,?,?,?,?,?)",
          ("KXMVE-PANEL", now - 5 * 86400, 5.0, 20.0, json.dumps([NBA]), "won", 20.0, now - 4 * 86400))
E.store_x("insert into ledger(ticker, kind, cost, back, n_sold, outcome, held) values(?,?,?,?,?,?,?)",
          ("KXMVE-SOLD", "combo", 5.0, 8.0, 20.0, "won", 20.0))
E.store_x("insert into ledger(ticker, kind, cost, back, n_sold) values(?,?,?,?,?)", ("KXMVE-OPEN", "combo", 5.0, 8.0, 20.0))
E.store_x("insert into bets(combo, first_seen, cost, pays, legs, status, back, settled) values(?,?,?,?,?,?,?,?)",
          ("KXMVE-MINE", now - 5 * 86400, 5.0, 20.0, json.dumps([NBA]), "cashed", 8.0, now - 4 * 86400))
E.store_x("insert into ledger(ticker, kind, cost, back, n_sold, outcome, held) values(?,?,?,?,?,?,?)",
          ("KXMVE-MINE", "combo", 5.0, 8.0, 20.0, "won", 20.0))
E._ledger_table()
for t_ in ("KXMVE-SOLD", "KXMVE-OPEN"):
    E.store_x("insert into sell_log(ts, ticker, result, kind, offer, cost, pays, frac) values(?,?,?,?,?,?,?,?)",
              (now - 4 * 86400, t_, "sold", "combo", 8.0, 5.0, 20.0, 1.0))
body = {"items": [{"id": "p1", "kind": "combo", "market": "KXMVE-PANEL", "stake": 5.0, "pays": 20.0, "result": "won",
                   "pl": 15.0, "kick": now - 5 * 86400, "legs": [{"ticker": NBA}]}]}
E.store_x("insert into panel(mode, ts, body) values(?,?,?)", ("real", now - 5 * 86400, json.dumps(body)))
items = E._knob_items(60)
ids = [c.get("id") for c in items]
sold = [c for c in items if c.get("id") == "KXMVE-SOLD"]
ok("a cashed-out real combo is judged too, riding to the end = what holding paid (sale_outcomes: won, +$15)",
   len(sold) == 1 and sold[0]["pl"] == 15.0 and sold[0]["sold"])
ok("...one whose result isn't known yet is left out, and so is one you cashed out yourself (not smart sell's)",
   "KXMVE-OPEN" not in ids and "KXMVE-MINE" not in ids)
ok("a panel combo counts once (the panel's copy, not the bets table's)", ids.count("p1") == 1 and "KXMVE-PANEL" not in ids)
ok("smart_tune's own evidence is unchanged (no cashed bets in it)", not any(c.get("id") == "KXMVE-SOLD" for c in E._tune_items(60)))
E.store_x("insert into offers values(?,?,?,?,?,?,?,?)", (now - 8000, "KXMVE-SOLD", 0.6, 20.0, 9.0, 8.5, 1, "hold"))
E.store_x("insert into offers values(?,?,?,?,?,?,?,?)", (now - 7900, "KXMVE-SOLD", 0.6, 20.0, 9.0, 8.0, 0, "hold"))
mk = E._knob_market(sold[0], [(now - 8100, {}), (now - 7000, {})])
ok("its market record: the real offers only", mk == {"offers": [(now - 8000, 8.5)]})
E._price_table()
E.store_x("insert into price_path(ts, ticker, bid, ask) values(?,?,?,?)", (now - 8000, NBA, 0.40, 0.44))
mk_y = E._knob_market({"kind": "single", "legs": [{"ticker": NBA, "side": "yes"}]}, [(now - 8100, {}), (now - 7000, {})])
mk_n = E._knob_market({"kind": "single", "legs": [{"ticker": NBA, "side": "no"}]}, [(now - 8100, {}), (now - 7000, {})])
ok("a single's record: its bid and ask; a NO pick (its recorded chance is the YES price) replays as before",
   mk_y == {"book": [(now - 8000, 0.40, 0.44)]} and mk_n == {})
E.store_x("insert into offers values(?,?,?,?,?,?,?,?)", (now - 7880, "KXMVE-SOLD", 0.6, 20.0, 9.0, 8.5, 1, "hold"))
ok("the same quote written again 2 minutes later is one offer (kept at the time it came in)",
   E._knob_market(sold[0], [(now - 8100, {}), (now - 7000, {})]) == {"offers": [(now - 8000, 8.5)]})
real_p = E._paths
E._paths = lambda c: [(now - 9000 + j * 60, {NBA: x}) for j, x in enumerate((0.5, 0.6, 0.7))]
cut_off = [c for c, _, _ in E._knob_rows(now)["replay"].get("all", []) if c.get("id") == "KXMVE-SOLD"]
E._paths = lambda c: [(now - 9000 + j * 60, {NBA: x}) for j, x in enumerate((0.5, 0.6, 0.99))]
to_end = [c for c, _, _ in E._knob_rows(now)["replay"].get("all", []) if c.get("id") == "KXMVE-SOLD"]
E._paths = real_p
ok("a cashed combo whose prices stop at the sale is left out; one recorded on to the end is judged",
   not cut_off and len(to_end) == 1)

# ---- 6. auto_slip live: off = 97%, on with nothing learned = 97%, a league's own number, the brake keeps a stricter one
switch(False)
set_knobs({"groups": {"nba": {"lv": {"auto_slip": 0.99}, "lat": {"auto_slip": now}}}, "brake": {}, "settings": {}})
LEAGUE_T = ["KXNBAGAME-26NOV21BOSNYK-BOS", "KXNHLGAME-26NOV21PHIBOS-PHI", "KXEPLGAME-26NOV22ARSCHE-ARS",
            "KXNFLGAME-26NOV22KCBUF-KC"]
bad = 0
for i in range(2000):
    if i % 200 == 0:
        set_knobs({"groups": {g: {"lv": {"auto_slip": rng.choice([0.9, 0.95, 0.99, 1.0])}, "lat": {}}
                              for g in ("nba", "nhl", "basketball", "soccer", "all") if rng.random() < .6},
                   "brake": {}, "settings": {}})
    bad += E.knob_auto_slip(rng.sample(LEAGUE_T, rng.randint(1, 2))) != E.CASH_SLIP
ok(f"switch off: every automatic sale's slip is today's 97% whatever is recorded (2000 bets, {bad} differ)", bad == 0)
switch(True)
set_knobs({"groups": {}, "brake": {}, "settings": {}})
ok("switch on, nothing learned: 97%", all(E.knob_auto_slip([t]) == 0.97 for t in LEAGUE_T))
set_knobs({"groups": {"nba": {"lv": {"auto_slip": 0.99}, "lat": {"auto_slip": now}},
                      "all": {"lv": {"auto_slip": 0.93}, "lat": {}}}, "brake": {}, "settings": {}})
ok("a league's own learned slip reaches its sales; everyone's looser one is never borrowed",
   E.knob_auto_slip([NBA]) == 0.99 and E.knob_auto_slip(["KXNHLGAME-26NOV21PHIBOS-PHI"]) == 0.97)
set_knobs({"groups": {"nba": {"lv": {"auto_slip": 0.99}, "lat": {"auto_slip": now}},
                      "nhl": {"lv": {"auto_slip": 0.93}, "lat": {"auto_slip": now}}},
           "brake": {"nba": {"at": now, "until": now + 86400, "mode": "live"},
                     "nhl": {"at": now, "until": now + 86400, "mode": "live"}}, "settings": {}})
ok("while braked: a stricter slip (99%) stays, a looser one (93%) is back at 97%",
   E.knob_auto_slip([NBA]) == 0.99 and E.knob_auto_slip(["KXNHLGAME-26NOV21PHIBOS-PHI"]) == 0.97)
open(E.KNOBS_FILE, "w").write("{junk"); E.KNOB_STATE_CACHE["d"] = None
ok("an unreadable record: 97%", E.knob_auto_slip([NBA]) == 0.97)
set_knobs({"groups": {"nba": {"lv": {"auto_slip": 3.0}, "lat": {}}}, "brake": {}, "settings": {}})
ok("an out-of-range value: 97%", E.knob_auto_slip([NBA]) == 0.97)
ok("the estimate allowances and the slip have a judge now; nothing shared is left among the live knobs",
   all(E.KNOB_JUDGED.get(n) == "replay" for n in ("exit_est_smart", "exit_est_tp", "auto_slip"))
   and not any(E.KNOB_BY[n].get("shared_with") for n in E.KNOB_LIVE))

# ---- 7. the sale log's new columns: an old table (before PR4) gains them; a sale is never lost either way
E.STORE["ledger_ok"] = False
E.store_x("drop table sell_log")
E.store_x("create table sell_log(ts real, ticker text, result text, why text, kind text, side text, offer real, cost real, "
          "pays real, frac real, chance real, by text, combo text, outcome text, held real, done real, "
          "primary key(ts, ticker, result))")
E._ledger_table()
E.sale_store({"at": now - 30, "ticker": "KXNHLGAME-26NOV21PHIBOS-PHI", "result": "sold", "kind": "win", "offer": 7.5,
              "cost": 5.0, "pays": 10, "chance": 0.8, "live": True, "ask": 0.79})
r_ = E.store_rows("select live, ask from sell_log")
ok("an old sale log gains `live` and `ask`; a new sale records them", r_ == [{"live": 1, "ask": 0.79}])
E.STORE["sell_live"] = False                                # the columns couldn't be added (a busy file)
E.sale_store({"at": now - 20, "ticker": "KXNHLGAME-26NOV21PHIBOS-PHI", "result": "sold", "kind": "win", "offer": 7.5,
              "cost": 5.0, "pays": 10, "chance": 0.8, "live": True})
ok("...and if they couldn't be added, the sale is still saved and the brake still reads it",
   len(E.store_rows("select ts from sell_log")) == 2 and len(E._knob_brake_sales({"brake": {}}, now).get("nhl") or []) == 1)
E.STORE["sell_live"] = True
f_ = E.single_fee
ok("the brake's footing for a single: sold at the bid of a 4-cent gap at fair (mid = chance) is not a loss; "
   "5 cents under a 2-cent gap is", (lambda a: a[0] >= a[1] - E.KNOB_EPS)(E.knob_sale_expect(
       {"ticker": "KXNBAGAME-X", "kind": "win", "offer": 7.8, "pays": 10, "frac": 1.0, "chance": 0.8, "ask": 0.82}))
   and (lambda a: a[0] < a[1] - E.KNOB_EPS)(E.knob_sale_expect(
       {"ticker": "KXNBAGAME-X", "kind": "win", "offer": 7.5, "pays": 10, "frac": 1.0, "chance": 0.8, "ask": 0.77})))
switch(True)
set_knobs({"groups": {"nba": {"lv": {"trail_floor": 1.1}, "lat": {"trail_floor": now}},
                      "basketball": {"lv": {"trail_floor": 1.3, "smart_loss": 0.2}, "lat": {}}},
           "brake": {"nba": {"at": now, "until": now + 86400, "mode": "live"}}, "settings": {}})
ok("braked with its own value at the start and a stricter borrowed one: the borrowed one, from its sport",
   E.knob_live_value("trail_floor", "nba", ["nba", "basketball", "all"], E.knob_state_cached(), {}, now) == (1.3, "basketball"))
ok("the loss cut when both are numbers: the lower cut is stricter (fewer cuts); off beats both",
   E.knob_stricter_of("smart_loss", 0.2, 0.15) == 0.15 and E.knob_loosens("smart_loss", 0.15, 0.2)
   and not E.knob_loosens("smart_loss", 0.2, 0.15) and E.knob_stricter_of("smart_loss", 0.2, None) is None)
