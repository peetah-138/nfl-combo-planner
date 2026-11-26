# CHECK: group=engine
# Issue #13: per-league learning, in SHADOW. Each league's own numbers (combo cut-off, fair-price nudge, settled-bet
# return), borrowing its sport then everyone with sample-size weighting, are written beside today's numbers in
# `league_shadow` and shown read-only. Nothing a decision reads changes: the decisions are identical before and after
# a run, no settings/learning file is written, and no decision function mentions the shadow.
import os, time, json, tempfile, importlib.util, ast, hashlib
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
H = tempfile.mkdtemp()
E.store_open(os.path.join(H, "h.db")); E.HERE = H
E.CUTOFF_FILE = os.path.join(H, "cut.json"); E.SIZING_FILE = os.path.join(H, "s.json"); E.SMART_FILE = os.path.join(H, "smart.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
close = lambda a, b, t=1e-6: a is not None and abs(a - b) < t

# ---- the blend: sample-size weighting, explainable shares
v, sh = E.lgsh_blend(95.0, [], 30)
ok("blend: no levels = the start, all of it", v == 95.0 and sh == {"start": 1.0})
v, sh = E.lgsh_blend(95.0, [("all", 97.0, 30), ("sport", None, 500), ("league", 90.0, 0)], 30)
ok("blend: a level with no value or no data changes nothing", close(v, 96.0) and sh["sport"] == 0 and sh["league"] == 0)
v, sh = E.lgsh_blend(0.0, [("all", 0.10, 100), ("sport", 0.20, 100), ("league", 0.40, 300)], 100)
exp = 0.0
for val, n in ((0.10, 100), (0.20, 100), (0.40, 300)):
    exp += n / (n + 100) * (val - exp)
ok("blend: each level moves n/(n+k) of the gap, widest to narrowest", close(v, exp))
ok("blend: the shares add to 1 and the league with the most data leads", close(sum(sh.values()), 1.0) and sh["league"] > sh["sport"])
v2, _ = E.lgsh_blend(0.0, [("all", 0.10, 100), ("sport", 0.20, 100), ("league", 0.40, 3)], 100)
ok("blend: a league with 3 results stays near its sport", abs(v2 - E.lgsh_blend(0.0, [("all", 0.10, 100), ("sport", 0.20, 100)], 100)[0]) < 0.01)

# ---- seed: cut-offs, calibration closes, settled bets
json.dump({"all:2": {"level": 97.0, "n": 200}, "soccer:2": {"level": 96.0, "n": 100}, "epl:2": {"level": 90.0, "n": 10},
           "nba:2": {"level": 92.0, "n": 60, "why": "lowered"}, "all:3-4": {"level": 95.0, "n": 200},
           "soccer:3-4": {"level": 96.0, "n": 80}, "epl:3-4": {"level": 93.0, "n": 50}}, open(E.CUTOFF_FILE, "w"))
E._close_table()
import random
rng = random.Random(5)
for lg, pre, n, win in (("epl", "KXEPLGAME", 120, 0.70), ("laliga", "KXLALIGAGAME", 80, 0.55), ("nba", "KXNBAGAME", 150, 0.5)):
    sp = "nba" if lg == "nba" else "soccer"
    for i in range(n):
        f = rng.uniform(0.3, 0.7) if lg != "epl" else 0.5
        E.store_x("insert into closes values(?,?,?,?,?,?,?,?)", (f"{pre}-G{i}-A", sp, f"{pre}-G{i}", f, f, now - 86400, now - 86400,
                                                              "yes" if rng.random() < (win if lg == "epl" else f) else "no"))
E.CALIB["at"] = 0
# bets: legs are tickers; 30 epl bets that lose, 60 nba bets that win a little, 5 mixed (never counted)
for i in range(30):
    E.store_x("insert into bets values(?,?,?,?,?,?,?,?,?,?)", (f"E{i}", now - 86400, 10.0, 25.0, json.dumps([f"KXEPLGAME-E{i}-A"]), "soccer",
                                                              "lost" if i % 3 else "won", 0, now - 3600, 0.4))
for i in range(60):
    E.store_x("insert into bets values(?,?,?,?,?,?,?,?,?,?)", (f"N{i}", now - 86400, 10.0, 20.0, json.dumps([f"KXNBAGAME-N{i}-A"]), "nba",
                                                              "won" if i % 2 else "lost", 0, now - 3600, 0.4))
for i in range(5):
    E.store_x("insert into bets values(?,?,?,?,?,?,?,?,?,?)", (f"M{i}", now - 86400, 10.0, 99.0, json.dumps(["KXNBAGAME-M-A", "KXEPLGAME-M-B"]),
                                                              "mix", "won", 0, now - 3600, 0.4))

# ---- #476 look-ahead: the first run must not backfill. Old quotes (already settled, the cut-offs were learned from them) are skipped
E.store_x("insert into quotes(ts, source, sport, n, legs, stake, pays, fair, kalshi, pct, hours, outcome, resolved) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (now - 90 * 86400, "build", "soccer", 2, json.dumps([["KXEPLGAME-OLD1", 0.5, 0.5], ["KXEPLGAME-OLD2", 0.5, 0.5]]), 10.0, 25.0, 30.0, 25.0, 0.99, 5.0, "won", now - 89 * 86400))
ok("quotes: the first run logs nothing historical", E.lgsh_log_quotes(now) == (0, 0) and E.store_rows("select count(*) n from league_shadow_q")[0]["n"] == 0)
ok("quotes: ... and sets its place at the newest quote", E.store_rows("select v from league_shadow_mark where k='last'")[0]["v"] == E.store_rows("select max(rowid) m from quotes")[0]["m"])
FEE = E.single_fee(10.0 / 25.0, 25) * 25
# ---- quotes for the #476 settle-to-dollars log: epl size 2 (three of them), an nba one, a mixed-sport one, one with no price
def addq(sport, legs, pct, stake=10.0, pays=25.0, outcome=None):
    E.store_x("insert into quotes(ts, source, sport, n, legs, stake, pays, fair, kalshi, pct, hours, outcome, resolved) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (now - 7200, "build", sport, len(legs), json.dumps([[t, 0.5, 0.5] for t in legs]), stake, pays, 30.0, 25.0, pct, 5.0, outcome, now if outcome else None))
cut_now = E.combo_cutoff("soccer", 2, ["KXEPLGAME-X"]) * 100
cut_blend = next(r["shadow"] for r in E.lgsh_rows(now) if r["league"] == "epl" and r["metric"] == "cutoff" and r["key"] == "2")
mid_pct = (cut_now + cut_blend) / 2 / 100                       # between the two cut-offs: today's rule passes it or the blend does, not both
addq("soccer", ["KXEPLGAME-A1", "KXEPLGAME-A2"], mid_pct, outcome="won")        # 1: flips; won, +$15 if bought
addq("soccer", ["KXEPLGAME-B1", "KXEPLGAME-B2"], 0.99, outcome="lost")          # 2: both pass; lost, -$10
addq("soccer", ["KXEPLGAME-C1", "KXEPLGAME-C2"], 0.50, outcome="lost")          # 3: both skip; lost, would have been -$10 (nothing lost)
addq("soccer", ["KXEPLGAME-D1", "KXEPLGAME-D2"], 0.99)                          # 4: not settled yet
addq("nba", ["KXNBAGAME-N1", "KXNBAGAME-N2"], 0.99, outcome="won")              # 5: nba: both pass; +$15
addq("nba,soccer", ["KXNBAGAME-M1", "KXEPLGAME-M2"], 0.99, outcome="won")       # 6: mixed sport: not logged
addq("nba", ["KXNBAGAME-P1", "KXNBAGAME-P2"], None, outcome="won")              # 7: no price recorded: not logged

# ---- decisions before (the snapshot the run must not change)
def decisions():
    cut = [E.combo_cutoff(c, n, legs) for c in ("nba", "soccer", "nhl") for n in (2, 3, 4, 6, 9)
           for legs in (None, ["KXEPLGAME-X"], ["KXNBAGAME-X"])]
    cal = [E.calib_fair(c, f / 20, t) for c in ("nba", "soccer") for f in range(1, 20) for t in (None, "KXEPLGAME-X", "KXNBAGAME-X")]
    size = [E._size({"kind": "combo", "chance": q, "pct": 1.0, "fair_mult": m}, 300.0) for q in (0.2, 0.5, 0.8) for m in (1.5, 3.0, 9.0)]
    smart = [E.smart_params(t) for t in (["KXEPLGAME-X"], ["KXNBAGAME-X"], ["KXNBAGAME-X", "KXEPLGAME-Y"])]
    return json.dumps([cut, cal, size, smart], sort_keys=True, default=str)
def files():
    return {f: hashlib.md5(open(os.path.join(H, f), "rb").read()).hexdigest() for f in sorted(os.listdir(H)) if f.endswith(".json")}
def counts():
    return {t: E.store_rows(f"select count(*) n from {t}")[0]["n"] for t in ("closes", "bets", "quotes", "panel", "knob_shadow", "mkt_fair", "maker")
            if E.store_rows("select 1 from sqlite_master where name=?", (t,))}
before, f0, c0 = decisions(), files(), counts()
ok("shadow: no table yet, the view is empty and the run is not due-blocked", E.league_shadow_view() == {})

# ---- the rows
rows = E.lgsh_rows(now)
by = {(r["league"], r["metric"], r["key"]): r for r in rows}
r = by[("epl", "cutoff", "2")]
ok("cutoff: current is exactly today's combo_cutoff for that league", close(r["current"], E.combo_cutoff("soccer", 2, ["KXEPLGAME-X"]) * 100) and r["current"] == 96.0)   # 10 quotes: today the sport's level
# #477: the file's counts are nested (everyone's 200 holds the sport's 100) and a thin league's entry (10 quotes, not its own
# yet) carries the sport's level beside its own n. Each quote counts once: everyone's 100 beyond the sport, the sport's 100,
# and the thin league not at all.
exp, _ = E.lgsh_blend(95.0, [("all", 97.0, 100), ("sport", 96.0, 100), ("league", None, 0)], 30)
ok("cutoff (#477): each quote counts once, a thin league's borrowed entry counts for nothing", close(r["shadow"], round(exp, 2), 0.01))
old_nested, _ = E.lgsh_blend(95.0, [("all", 97.0, 200), ("sport", 96.0, 100), ("league", 90.0, 10)], 30)
ok("cutoff (#477): and it is not what the old nested blend gave", abs(r["shadow"] - round(old_nested, 2)) > 0.05)
ok("cutoff (#477): the shares still add to 1", close(sum(r["shares"].values()), 1.0, 1e-3) and r["shares"]["league"] == 0 and r["n_own"] == 10)
r = by[("epl", "cutoff", "3-4")]
exp, _ = E.lgsh_blend(95.0, [("all", 95.0, 120), ("sport", 96.0, 30), ("league", 93.0, 50)], 30)
ok("cutoff (#477): a league with its own record: its 50 are taken out of the sport's 80, the sport's 80 out of everyone's 200",
   close(r["shadow"], round(exp, 2), 0.01) and r["shadow"] != r["current"])
ok("cutoff: a soccer league with no entry of its own borrows the sport", close(by[("mls", "cutoff", "2")]["current"], 96.0) and close(by[("mls", "cutoff", "2")]["shadow"], by[("mls", "cutoff", "2")]["current"], 1.0))
r = by[("nba", "cutoff", "2")]
ok("cutoff: a league that is its own sport is shown too (current is its own level)", r["current"] == 92.0 and r["sport"] == "nba")
ok("cutoff: a bucket with no record at all is not invented", ("epl", "cutoff", "8") not in by and ("nba", "cutoff", "8") not in by)
c = [x for x in rows if x["league"] == "epl" and x["metric"] == "calib"]
ok("calib: epl has a row per band it has results in", c and all(x["n_own"] > 0 for x in c))
x = c[0]
m_ = E.calibration()
band = lambda g: next(b for b in m_[g] if f"{b[0]:.2f}" == x["key"][:4])
bl_, bs_, ba_ = band("epl"), band("soccer"), band("all")
f = bl_[2]
ok("calib: current = calib_fair by sport only", close(x["current"], round(E.calib_fair("soccer", f), 4)))
def rest(a, b):                                           # a band without the narrower group's games
    k = a[4] - b[4]
    return ((a[2] * a[4] - b[2] * b[4]) / k, (a[3] * a[4] - b[3] * b[4]) / k, k)
ra, rs_ = rest(ba_, bs_), rest(bs_, bl_)
adj = 0.0
for mf, wr, n_ in (ra, rs_, (bl_[2], bl_[3], bl_[4])):
    adj += n_ / (n_ + 300) * ((wr - mf) - adj)
ok("calib (#477): shadow = everyone-without-sport, then sport-without-league, then the league's own: every game once",
   close(x["shadow"], round(min(max(f + adj, 0.01), 0.99), 4), 1e-4))
nested = 0.0
for mf, wr, n_ in ((ba_[2], ba_[3], ba_[4]), (bs_[2], bs_[3], bs_[4]), (bl_[2], bl_[3], bl_[4])):
    nested += n_ / (n_ + 300) * ((wr - mf) - nested)
ok("calib (#477): ... which is not the nested blend (all, sport, league each on all their games)", abs(x["shadow"] - round(f + nested, 4)) > 1e-4)
ok("calib: epl's own record (it wins more than priced) moves it past the sport-only number", x["shadow"] > x["current"])
r = by[("epl", "record", "60d")]
ok("record: counts only that league's own bets (mixed combos are left out)", r["n_own"] == 30 and r["n_sport"] == 30 and r["n_all"] == 90)
epl_roi = (10 * 25.0 - 300.0) / 300.0                    # 10 of 30 won: $25 back on $10
nba_roi = (30 * 20.0 - 600.0) / 600.0
all_roi = (10 * 25.0 + 30 * 20.0 - 900.0) / 900.0
# #477: everyone's 90 bets hold the sport's 30, and the sport's 30 are all the league's: only the 60 nba bets are everyone-beyond-sport,
# and the sport has nothing beyond the league
exp, _ = E.lgsh_blend(0.0, [("all", nba_roi, 60), ("sport", None, 0), ("league", epl_roi, 30)], 30)
ok("record (#477): shadow is the shrunk return, each bet once, no multiplier invented", close(r["shadow"], round(exp, 4), 1e-4) and r["current"] is None)

# ---- the run: its own table only, once a day, nothing else moves
n = E.league_shadow_run(now)
ok("run: rows written to league_shadow", n == len(rows) and E.store_rows("select count(*) n from league_shadow")[0]["n"] == n)
ok("run: not again within a day", E.league_shadow_run(now + 3600) == 0)
ok("run: forced, or a day later, it writes again", E.league_shadow_run(now + 3600, force=True) == n and E.league_shadow_run(now + 90000) == n)
ok("run: every metric is there", {x["metric"] for x in E.store_rows("select metric from league_shadow")} == {"cutoff", "calib", "record"})

# ---- #476: the per-quote pass/skip under today's cut-off and the blended one, settled to dollars
q = {r["qid"]: r for r in E.store_rows("select * from league_shadow_q")}
ok("quotes: one row per single-sport quote with a price (the mixed-sport and unpriced ones are not logged)", len(q) == 5)
r1, r2, r3, r4, r5 = (q[i] for i in sorted(q))
ok("quotes: the cut-offs logged are today's and the blended one for that league and size",
   close(r1["cut_now"], cut_now) and close(r1["cut_blend"], cut_blend, 0.01) and r1["league"] == "epl" and r5["league"] == "nba" and r5["cut_now"] == 92.0)
ok("quotes: a price between the two cut-offs passes under exactly one of them", r1["pass_now"] != r1["pass_blend"] and r1["pass_now"] == int(cut_now < cut_blend))
ok("quotes: high price passes both, low price skips both", (r2["pass_now"], r2["pass_blend"], r3["pass_now"], r3["pass_blend"]) == (1, 1, 0, 0))
ok("quotes: a settled quote carries its dollars if bought (won +15, lost -10); an unsettled one waits", tuple(round(x, 4) for x in (r1["pnl"], r2["pnl"], r3["pnl"], r5["pnl"])) == tuple(round(x, 4) for x in (15.0 - FEE, -10.0 - FEE, -10.0 - FEE, 15.0 - FEE))
   and r4["outcome"] is None and r4["pnl"] is None)
g = E.lgsh_gate()
e_ = next(x for x in g["leagues"] if x["league"] == "epl")
now_d = (15.0 - FEE if cut_now < cut_blend else 0.0) - 10.0 - FEE              # epl: quote 1 only under the rule that passes it, quote 2 under both, quote 3 under neither
blend_d = (15.0 - FEE if cut_blend < cut_now else 0.0) - 10.0 - FEE
ok("gate: epl dollars under today's rule and the blend, settled quotes only", e_["settled"] == 3 and close(e_["dollars_now"], now_d) and close(e_["dollars_blend"], blend_d)
   and close(e_["diff"], blend_d - now_d) and e_["flips"] == 1)
ok("gate: 'all' adds the nba quote (both pass, +15)", g["all"]["settled"] == 4 and close(g["all"]["dollars_now"], now_d + 15.0 - FEE) and close(g["all"]["dollars_blend"], blend_d + 15.0 - FEE))
E.store_x("update quotes set outcome='won', resolved=? where legs like '%KXEPLGAME-D1%'", (now,))
E.league_shadow_run(now + 3600, force=True)
ok("quotes: a forced run does not log a quote twice, and settles the one that has since settled",
   E.store_rows("select count(*) n from league_shadow_q")[0]["n"] == 5 and E.store_rows("select pnl from league_shadow_q where qid=?", (r4["qid"],))[0]["pnl"] - (15.0 - FEE) < 1e-6)
ok("gate: nothing settled = {}", (E.store_x("update league_shadow_q set outcome=null, pnl=null"), E.lgsh_gate())[1] == {})
E.lgsh_log_quotes(now + 7200)
ok("gate: the next run settles them again", E.lgsh_gate()["all"]["settled"] == 5)
# prune must not reset the place: even with every logged row gone, nothing is re-logged and new quotes still are
E.store_x("update league_shadow_q set ts = ts - ?", (200 * 86400,))
mk = E.store_rows("select v from league_shadow_mark where k='last'")[0]["v"]
E.lgsh_log_quotes(now + 7300)
ok("quotes: pruning every old row does not reset the place or re-log the quotes", E.store_rows("select count(*) n from league_shadow_q")[0]["n"] == 0
   and E.store_rows("select v from league_shadow_mark where k='last'")[0]["v"] == mk)
mx = E.store_rows("select max(rowid) m from quotes")[0]["m"]
addq("nba", ["KXNBAGAME-Z1", "KXNBAGAME-Z2"], 0.99)
ok("quotes: a new quote after the prune is still logged", E.lgsh_log_quotes(now + 7400)[0] == 1)
for i in range(5200):                                    # more than one 5000 batch in a day: the log drains them all
    E.STORE["db"].execute("insert into quotes(ts, source, sport, n, legs, stake, pays, fair, kalshi, pct, hours) values(?,?,?,?,?,?,?,?,?,?,?)",
                          (now, "build", "nba", 2, json.dumps([["KXNBAGAME-B%d" % i, 0.5, 0.5], ["KXNBAGAME-C%d" % i, 0.5, 0.5]]), 10.0, 25.0, 30.0, 25.0, 0.99, 5.0))
E.STORE["db"].commit()
ok("quotes: a busy day is drained in full, not capped at 5000", E.lgsh_log_quotes(now + 7500)[0] == 5200)
E.store_x("delete from quotes where rowid > ?", (mx,))                # put the history back as it was
E.store_x("delete from league_shadow_q where qid > ?", (mx,))
E.store_x("update league_shadow set ts = ts - ?", (200 * 86400,))
E.league_shadow_run(now + 2 * 90000)
ok("run: rows older than 180 days are pruned", E.store_rows("select count(*) n from league_shadow where ts < ?", (now - 100 * 86400,))[0]["n"] == 0)
after = decisions()
ok("NO BEHAVIOUR CHANGE: every cut-off, fair-price nudge, size and smart-sell setting is identical after the run", after == before)
ok("NO BEHAVIOUR CHANGE: no settings or learning file was written or changed", files() == f0)
c1 = counts()
ok("NO BEHAVIOUR CHANGE: the history tables decisions read are untouched", all(c1[t] == c0[t] for t in c0))

# ---- the view
v = E.league_shadow_view()
ok("view: read-only report in shadow mode, leagues that differ first", v["mode"] == "shadow" and v["leagues"] and v["leagues"][0]["differs"] >= 1
   and v["leagues"][0]["differs"] >= v["leagues"][-1]["differs"])
e = next(x for x in v["leagues"] if x["key"] == "epl")
ok("view: a league has its cut-offs, calibration and record side by side", e["cutoff"] and e["calib"] and e["record"]["shadow"] is not None and e["name"] == "Premier League")
ok("view: calling it changes nothing", decisions() == before and files() == f0)
db = E.STORE["db"]; E.STORE["db"] = None
ok("view and run: never raise without a history file", E.league_shadow_view() == {} and E.league_shadow_run(now + 10 ** 6) == 0)
E.STORE["db"] = db

# ---- knob_pass: a shadow failure can never change what the watcher gets back (brake alerts included)
E.LGSH_FAIL = 0
real_run = E.league_shadow_run
def boom(*a, **k):
    E.LGSH_FAIL += 1
    raise RuntimeError("shadow exploded")
E.knob_brake_pass = lambda now=None: ["league X braked"]
E.knob_tune = lambda now=None: ["epl lowered"]
E.league_shadow_run = boom
res = E.knob_pass(now)
ok("knob_pass: league_shadow_run raising was actually hit", E.LGSH_FAIL == 1)
ok("knob_pass: with the shadow raising, the brake messages and steps come back unchanged",
   res == (["brake: league X braked", "self-tuning epl lowered"], ["league X braked"]))
E.league_shadow_run = real_run

# ---- an empty run is remembered (no 60-day re-read every round) and a run is all-or-nothing
E._LGSH_TRIED["at"] = 0
calls = []
real_rows = E.lgsh_rows
E.lgsh_rows = lambda now=None: (calls.append(1), [])[1]
E.store_x("delete from league_shadow")
t0 = now + 10 ** 7
ok("empty run: writes nothing", E.league_shadow_run(t0) == 0)
E.league_shadow_run(t0 + 1800); E.league_shadow_run(t0 + 3600)
ok("empty run: not recomputed again within the day", len(calls) == 1)
E.league_shadow_run(t0 + 90000)
ok("empty run: tried again a day later", len(calls) == 2)
E.lgsh_rows = real_rows
E._LGSH_TRIED["at"] = 0
E.store_x("delete from league_shadow")
bad_rows = [dict(r) for r in real_rows(now)]
bad_rows[-1]["shares"] = object()                      # json.dumps fails on the last row: nothing may be written
E.lgsh_rows = lambda now=None: bad_rows
ok("atomic: a run that fails part-way writes no rows at all",
   E.league_shadow_run(now + 5 * 10 ** 6, force=True) == 0 and E.store_rows("select count(*) n from league_shadow")[0]["n"] == 0)
E.lgsh_rows = real_rows
ok("atomic: the next run writes it whole in one go",
   E.league_shadow_run(now + 5 * 10 ** 6, force=True) == len(bad_rows) == E.store_rows("select count(*) n from league_shadow")[0]["n"])
ok("derived: the ticker prefixes come from SOCCER_LEAGUE", E._LGSH_PRE == {v: k for k, v in E.SOCCER_LEAGUE.items()})

# ---- no decision function reads the shadow: only the shadow's own functions, the watcher hook and the report do
tree = ast.parse(open("wahome/engine.py").read())
allowed = {"lgsh_blend", "_lgsh_say", "_lgsh_league_sport", "lgsh_rows", "_league_shadow_table", "league_shadow_run",
           "league_shadow_view", "knob_pass", "analytics", "_lgsh_minus", "_league_shadow_q_table", "lgsh_log_quotes", "lgsh_gate", "_lgsh_mark", "_lgsh_log_batch", "_lgsh_pnl"}
bad = []
for fn in [x for x in ast.walk(tree) if isinstance(x, ast.FunctionDef)]:
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    names |= {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)
              and ("league_shadow" in n.value or "LGSH" in n.value)}          # SQL text, getattr names, etc.
    hit = {x for x in names if x in ("LGSH", "_LGSH_TRIED", "league_shadow", "league_shadow_run", "league_shadow_view", "lgsh_rows", "lgsh_blend")
           or (isinstance(x, str) and ("league_shadow" in x or "LGSH" in x))}
    if hit and fn.name not in allowed:
        bad.append((fn.name, sorted(hit)))
ok(f"static: no decision function mentions the shadow {bad}", not bad)
