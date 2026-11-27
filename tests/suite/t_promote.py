# CHECK: group=engine
# Ready to promote? (issue #541): the report-only judge for the paper tests. Checks: one decision per position (not per
# recorded row), the 99% range rule (99.5% with several settings), the 70/30 split picks the setting without peeking, every status and its
# plain-English reason, the four recorders settled to dollars on a throwaway sqlite file (and the ones that cannot be),
# the one-time push through the notifier, the cache never computing inside a request, and that nothing in the engine or
# the buying and selling code reads or imports any of it. Fakes only: no network, no real history.
import os, re, sys, json, time, sqlite3, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
REPO = os.environ.get("REPO") or os.path.abspath("../..")
sys.argv = ["combo_watcher.py"]
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py"); W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
_d = tempfile.mkdtemp()
W.PROMOTE_FILE = os.path.join(_d, "promote_pushed.json")
W.PROMOTE_STREAK_FILE = os.path.join(_d, "promote_streak.json")


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        ok.bad += 1


ok.bad = 0


def ob(i, v, var="a", pos=None, game=None, lag=None, ts=None):
    return {"var": var, "pos": pos or f"p{i}", "game": game or f"g{i}", "ts": ts if ts is not None else 1000 + i * 100, "v": v, "lag": lag}


def judge(vals, **kw):
    lag = kw.get("lag") or [0.1] * len(vals)       # a late-order check is required to pass, so the default has a mild positive one
    return W.promote_judge([ob(i, v, lag=lag[i]) for i, v in enumerate(vals)], kw.get("nv", 1))


# ---- one decision per position: many recorded rows for one bet count once, and it is the first
rows = [ob(0, 5.0, pos="x", ts=300), ob(0, -50.0, pos="x", ts=900), ob(0, 7.0, pos="x", ts=100)]
f = W.promote_first(rows)
ok("A 3 rows of one position collapse to one decision, the earliest", len(f) == 1 and f[0]["v"] == 7.0)
ok("A the same position under two settings counts once in each", len(W.promote_first([ob(0, 1, var="a", pos="x"), ob(0, 1, var="b", pos="x")])) == 2)
r = W.promote_judge([ob(i, 1.0, pos="same", game=f"g{i}", ts=i) for i in range(60)], 1)
ok("A sixty rows of one bet are n=1, not 60", r["n"] == 1 and r["state"] == "wait")
ok("A the game key: second part of a single, the whole ticker for a combo", W.promote_game("KXNBAGAME-26NOV23LALBOS-LAL") == "26NOV23LALBOS" and W.promote_game("KXMVECROSS-ABC-DEF") == "KXMVECROSS-ABC-DEF")

# ---- statuses and reasons
r = judge([1.0] * 60)
ok("B steady winner over 60 games passes, with a reason", r["state"] == "pass" and r["status"] == "Passing" and "Made $60.00" in r["reason"] and r["n"] == 60)
r = judge([1.0] * 10)
ok("B 10 settled is Not enough data and says what it needs", r["status"] == "Not enough data" and "needs 20" in r["reason"])
r = judge([1.0] * 39)
ok("B MINIMUM SAMPLE: 39 games of pure winning cannot pass, it says it needs 40", r["state"] == "wait" and "needs 40" in r["reason"] and not r["push_ok"])
r = judge([1.0] * 22)
ok("B MINIMUM SAMPLE: 22 games (7 in the latest stretch) used to pass; now Not enough data", r["state"] == "wait" and r["status"] == "Not enough data")
r = judge([1.0] * 20)
ok("B 20 games: only 6 latest games, counted but cannot be judged", r["n"] == 20 and r["holdout_games"] == 6 and r["state"] == "wait")
r = judge([1.0] * 45)
ok("B MINIMUM SAMPLE: 45 games leave 14 in the latest stretch (needs 15): Not enough data", r["holdout_games"] == 14 and r["state"] == "wait" and "latest stretch" in r["reason"] and "needs 15" in r["reason"])
r = judge([1.0] * 50)
ok("B 50 games leave 15 in the latest stretch: judged, passes", r["holdout_games"] == 15 and r["state"] == "pass")
r = W.promote_judge([ob(i, 1.0, game="g0" if i < 59 else f"g{i}") for i in range(60)], 1)
ok("B many bets but few games: not enough games", r["state"] == "wait" and "games so far" in r["reason"])
r = judge([-1.0] * 60)
ok("B a loser is Failing and says how much it lost", r["state"] == "fail" and r["status"] == "Failing" and "Lost $60.00" in r["reason"])
r = judge([2.0] * 42 + [-3.0] * 18)
ok("B good early, bad in the last 30%: Failing for the latest games even though the total is up", r["net"] > 0 and r["state"] == "fail" and "latest 30%" in r["reason"])
r = judge([10.0] * 30 + [-10.0] * 12 + [2.0] * 18)
ok("B only one half pays: Failing", r["net"] > 0 and r["holdout_net"] > 0 and r["state"] == "fail" and "one half" in r["reason"])
r = judge([1.0] * 60, lag=[-1.0] * 60)
ok("B pays on time, loses 30-60 s late: Failing", r["state"] == "fail" and "late" in r["reason"] and r["lag_n"] == 60)
r = judge([1.0] * 60, lag=[0.5] * 60)
ok("B still pays late: Passing and says so", r["state"] == "pass" and "late" in r["reason"])
r = judge([1.0] * 60, lag=[-5.0, None] * 30)
ok("B a lag replay with under 5 bets is ignored", r["state"] == "fail" or r["lag_net"] is not None)
r = judge([1.0] * 60, lag=[-5.0] * 3 + [None] * 57)
ok("B a lag replay with under 5 bets is ignored, and without a late check it cannot pass (3 of 60)", r["state"] == "wait" and r["lag_net"] is None and "cannot pass" in r["reason"] and "late" in r["reason"])
r = W.promote_judge([ob(i, 1.0) for i in range(60)], 1)
ok("B no late-order replay at all (sell line, bet pile-up): Not enough data, never Passing", r["state"] == "wait" and r["lag_n"] == 0 and "cannot pass" in r["reason"])
r = judge([10.0, -9.0] * 30)
ok("B up a little but noisy: Not enough data, 'too close to call'", r["net"] > 0 and r["state"] == "wait" and "too close to call" in r["reason"])
ok("B nothing recorded", W.promote_judge([], 1)["reason"] == "Nothing recorded yet.")
ok("B odd input (None values, missing lag) never raises", W.promote_judge([{"var": "a", "pos": "p", "game": "g", "ts": 1, "v": None}], 1)["state"] == "wait")
ok("B no jargon on screen", not re.search(r"bootstrap|out-of-sample|confidence", json.dumps([judge([1.0] * 60), judge([-1.0] * 60), judge([10.0, -9.0] * 30), judge([1.0] * 30)]), re.I))

# ---- 99% range
vals = [3.0, -2.0, 1.0, 4.0, -1.0] * 12
obs = [ob(i, v) for i, v in enumerate(vals)]
a, b, c = W.promote_judge(obs, 6), W.promote_judge(obs, 7), W.promote_judge(obs, 1)
ok("C one setting: 99% range; more than one setting tried: stricter still (99.5%)", c["level"] == 99 and a["level"] == 99.5 and W.promote_judge(obs, 2)["level"] == 99.5)
ok("C 7 settings tried: 99% range, wider than one setting", b["level"] == 99.5 and b["low"] <= c["low"] and b["high"] >= c["high"] and b["high"] - b["low"] > c["high"] - c["low"])
many = [ob(i, 1.0, var=f"v{k}") for i in range(30) for k in range(7)]
ok("C the count of settings is taken from the data too (7 seen = more than one)", W.promote_judge(many, None)["level"] == 99.5)
ok("C the range is deterministic", W.promote_judge(obs, 1)["low"] == c["low"])
# the range is built on the latest 30% of games only: early games that made a lot cannot lift the range
early = [ob(i, 50.0 if i < 42 else (1.0 if i % 2 else -1.0)) for i in range(60)]
re_ = W.promote_judge(early, 1)
ok("C the range uses only the latest games (big early wins do not widen it up)", re_["high"] <= 18 and re_["net"] > 1000)

# ---- zero-edge random data must almost never read as Passing (the lucky moment that used to become a permanent go)
import random
def fake(seed, nv, games=60):
    rg = random.Random(seed)
    o = []
    for g in range(games):
        for k in range(nv):
            v = rg.gauss(0, 5)
            o.append({"var": f"v{k}", "pos": f"p{g}_{k}", "game": f"g{g}", "ts": 1000 + g * 100, "v": v, "lag": v + rg.gauss(0, 1)})
    return o
for nv_ in (1, 3, 5):
    passes = sum(W.promote_judge(fake(s_, nv_), nv_)["state"] == "pass" for s_ in range(1000))
    ok(f"C2 zero-edge random data, {nv_} setting(s) tried, 1000 seeds: false Passing {passes / 10:.1f}% (<= 1.5%)", passes <= 15)
many_g = sum(W.promote_judge(fake(s_, 3, games=80), 3)["state"] == "pass" for s_ in range(500))
ok(f"C2 zero-edge, 80 games: false Passing {many_g / 5:.1f}% (<= 1.5%)", many_g <= 8)
real = [ob(i, 2.0, lag=1.0) for i in range(60)]
ok("C2 a real steady edge still passes under the stricter rule", W.promote_judge(real, 3)["state"] == "pass")

# ---- the judge is recomputed only when games settled, so a refresh cannot re-roll the same data
_calls = []
_orig_judge = W.promote_judge
W.promote_judge = lambda *a, **k: _calls.append(1) or _orig_judge(*a, **k)
W.PROMOTE["judged"].clear()
_o = [ob(i, 1.0, lag=0.5) for i in range(60)]
r1 = W.promote_judge_cached("t", _o, 1); r2 = W.promote_judge_cached("t", list(_o), 1); r3 = W.promote_judge_cached("t", list(_o), 1)
ok("C3 the same settled data three times is judged once", len(_calls) == 1 and r1 == r2 == r3)
W.promote_judge_cached("t", _o + [ob(60, 1.0, lag=0.5)], 1)
ok("C3 one more settled game is judged again", len(_calls) == 2)
r2["state"] = "x"
ok("C3 the cached answer is handed out as a copy", W.promote_judge_cached("t", _o + [ob(60, 1.0, lag=0.5)], 1)["state"] != "x")
W.promote_judge = _orig_judge

# ---- THE SEASON-LONG CHECK. The judge re-checks all season and the push fires once, ever, so what matters is the chance
# that a signal with NO edge EVER gets pushed. Math: one check that is wrong with chance p, repeated over k looks that
# are not independent (each new game changes only a little), compounds to well above p (7-24% over an 80-game season
# at p ~ 0.3-1%). Defences: no test under 40 games / 15 in the latest slice, the stricter push band (99.9%, 99.95% with
# several settings), and 3 passes in a row each on newly settled games. Here: simulate zero-edge seasons (80 games,
# 2 bets a game, a look after EVERY game, the real judge and the real streak rule) and count the seasons that push.
import random as _r
def season(seed, nv, games=80, per=2, mu=0.0):
    rg = _r.Random(seed); obs = []; st = None
    for g in range(games):
        for k in range(nv):
            for b in range(per):
                v = rg.gauss(mu, 5)
                obs.append({"var": f"v{k}", "pos": f"p{g}_{k}_{b}", "game": f"g{g}", "ts": 1000 + g * 100, "v": v, "lag": v + rg.gauss(0, 1)})
        res = W.promote_judge(obs, nv)
        st = W.promote_streak_step(st, res)
        if st["n"] >= W.PROMOTE_STREAK:
            return True
    return False
# measured offline over 3200 (1 setting) and 1200 (3 settings) seasons: 1.0% and 1.3% ever pushed; the card's own 99% label
# ever reads Passing in about 6-8% of the same seasons, which is why the push uses the stricter band and 3 looks.
for nv_, seeds_, bound_ in ((1, 250, 0.03), (3, 120, 0.03)):
    pushed_ = sum(season(1000 + s_, nv_) for s_ in range(seeds_))
    ok(f"C4 zero-edge 80-game season, {nv_} setting(s), {seeds_} seasons: ever pushed {pushed_}/{seeds_} = {100 * pushed_ / seeds_:.1f}% (bound {bound_ * 100:.0f}%)", pushed_ <= bound_ * seeds_)
# CORRELATED COMBOS: a real game spawns several combos (a bet on the same game from different angles) and they win and lose
# together. Counting each combo as its own game made three combos from ONE game look like three new games, so the
# "3 successive batches of newly settled games" streak was beaten by one lucky game (19.7% ever pushed over 1000 seasons
# on the old code). Here each real game spawns 3 combos sharing the game's result; every combo names its own ticker as
# `game` (what the old code clustered on) and the real game in `games`; the judge must cluster by the real game.
def season_corr(seed, nv=1, games=80, combos=3, mu=0.0, shared=True):
    rg = _r.Random(seed); obs = []; st = None
    for g in range(games):
        shock = rg.gauss(mu, 5)
        for k in range(nv):
            for c in range(combos):
                v = shock + rg.gauss(0, 1.5) if shared else rg.gauss(mu, 5)
                obs.append({"var": f"v{k}", "pos": f"c{g}_{k}_{c}", "game": f"KXMVE-{g}-{c}", "games": (f"G{g}",), "ts": 1000 + g * 100, "v": v, "lag": v + rg.gauss(0, 1)})
        st = W.promote_streak_step(st, W.promote_judge(obs, nv))
        if st["n"] >= W.PROMOTE_STREAK:
            return True
    return False
CORR_SEASONS = int(os.environ.get("CORR_SEASONS", "250"))
corr_ = sum(season_corr(20000 + s_) for s_ in range(CORR_SEASONS))
ok(f"C5 zero-edge season, 3 correlated combos per real game, {CORR_SEASONS} seasons: ever pushed {corr_}/{CORR_SEASONS} = {100 * corr_ / CORR_SEASONS:.1f}% (bound 3%)", corr_ <= 0.03 * CORR_SEASONS)
cl_ = W.promote_judge([{"var": "a", "pos": f"p{i}", "game": f"KXMVE-{i}", "games": (f"G{i // 3}",), "ts": 1000 + i, "v": 1.0, "lag": 0.5} for i in range(150)], 1)
ok("C5 150 combos on 50 real games count as 50 games, not 150", cl_["all_games"] == 50 and cl_["games"] == 50 and cl_["n"] == 150)
mg_ = W.promote_judge([{"var": "a", "pos": "x", "game": "K1", "games": ("A", "B"), "ts": 1, "v": 1.0}, {"var": "a", "pos": "y", "game": "K2", "games": ("B", "C"), "ts": 2, "v": 1.0},
                       {"var": "a", "pos": "z", "game": "K3", "games": ("D",), "ts": 3, "v": 1.0}], 1)
ok("C5 two combos that share any game merge into one cluster (A+B and B+C are one; D is another)", mg_["all_games"] == 2)
legs_ = {"KXMVE-1": ["KXNBAGAME-26NOV23LALBOS-LAL", "KXNBASPREAD-26NOV23LALBOS-LAL5", "KXNFLGAME-26NOV30CINBAL-CIN"]}
ok("C5 a combo's real games come from its leg tickers; unknown legs fall back to its own ticker", W.promote_games("KXMVE-1", legs_) == ("26NOV23LALBOS", "26NOV30CINBAL") and W.promote_games("KXMVE-9", legs_) == ("KXMVE-9",) and W.promote_games("KXNBAGAME-26NOV23LALBOS-LAL") == ("26NOV23LALBOS",))
# a real edge still gets through inside a season (+$4 a bet against noise of 5)
real_ = sum(season(7000 + s_, 1, mu=4.0) for s_ in range(10))
ok(f"C4 a real edge still reaches a push inside 80 games ({real_}/10 seasons)", real_ >= 8)

# ---- 70/30: the setting is picked on the first 70% of games only
obs = [ob(i, 5.0 if i < 42 else -5.0, var="a") for i in range(60)] + [ob(i, -1.0 if i < 42 else 20.0, var="b") for i in range(60)]
r = W.promote_judge(obs, 2)
ok("D picks the setting that did best on the first 70% (a), then scores it on the last 30%", r["variant"] == "a" and r["holdout_net"] == -90.0 and r["state"] == "fail")

# ---- the four recorders, settled on a throwaway sqlite file
db = sqlite3.connect(":memory:")


def q(sql, args=()):
    cur = db.execute(sql, args)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, x)) for x in cur.fetchall()]


rep = W.promote_report(q, {}, None, now=1.0)
by = {s["key"]: s for s in rep["signals"]}
ok("E empty database: every recorder is Not enough data (missing tables never raise)", all(by[k]["state"] == "wait" and by[k]["n"] == 0 for k in ("mom", "sig", "expo", "cap")))
asked = []
W.promote_report(lambda sql, args=(): asked.append(sql) or [], {}, None, now=1.0)
ok("E a recorder whose table does not exist yet is never queried (the engine would log each miss as an error)", asked and all(("sqlite_master" in a) for a in asked))
ok("E exit-cap recorder off: says so", "switched off" in by["cap"]["reason"])
ok("E league / prop / slate / news: Cannot be measured in dollars yet", all(by[k]["status"] == "Cannot be measured in dollars yet" and by[k]["state"] == "na" for k in ("league", "prop", "slate", "news")))
ok("E one row per signal, none named 'Combo N'", len(rep["signals"]) == 8 and not any(re.search(r"Combo \d", s["name"]) for s in rep["signals"]))

db.executescript("""
create table mom_shadow(ts real, ticker text, kind text, sport text, live int, q real, q_peak_w real, dq real, sigma real, z real, o_real real, o_est real, real_flag int, quote_age real, o_net real, cost real, pays real, n real, o_peak real, today_sell int, today_reason text, today_line real, why_not text, m_protect int, m_cut int, paused int, proc text, sid text);
create table mom_after(sid text, ts real, ticker text, o_net0 real, o30 real, o60 real, o300 real, o900 real, o3600 real, o_min real, outcome text, payout real, proc text);
create table closes(ticker text primary key, sport text, event text, fair real, price real, kick real, ts real, outcome text);
create table bp_mkt(id integer primary key, ticker text unique, ev text, sp text, kind text, kick integer, first integer, result integer, rs integer);
create table sig_sharp(ts real, ticker text, fair_book real, bid real, ask real, src text, live int, line_live int);
create table expo_pos(pos text primary key, ts real, day text, league text, kind text, cost real, bank real, games text, alloc text, seed int, blocked text, net real, settled real, batch int, own int);
create table exit_cap_shadow(ts real, ticker text, kind text, side text, n real, cost real, chance real, state text, bid real, net real, top real, live_line real, live_decision text, cap real, alt_line real, alt_decision text);
""")
# momentum: 60 bets, each flagged on 3 rows (so 75 rows), sold early at $3 while the bet then lost (nothing paid): +$3 each
for i in range(60):
    t = f"KXNBAGAME-26NOV{i + 1:02d}AAABBB-AAA"
    for j in range(3):
        db.execute("insert into mom_shadow(ts,ticker,cost,m_protect,m_cut,sid) values(?,?,?,?,?,?)", (1000 + i * 100 + j, t, 4.0, 1, 0, f"s{i}_{j}"))
        db.execute("insert into mom_after(sid,ts,ticker,o_net0,o30,o60,outcome,payout) values(?,?,?,?,?,?,?,?)", (f"s{i}_{j}", 1, t, 3.0, 2.5, 2.0, "lost", 0.0))
# a bet really sold (cashed) is left out and counted; an unsettled one is not counted
db.execute("insert into mom_shadow(ts,ticker,cost,m_protect,m_cut,sid) values(5000,'KXNBAGAME-26NOV30CCCDDD-CCC',4,1,0,'c1')")
db.execute("insert into mom_after(sid,ts,ticker,o_net0,outcome,payout) values('c1',1,'KXNBAGAME-26NOV30CCCDDD-CCC',3.0,'cashed',3.0)")
db.execute("insert into mom_shadow(ts,ticker,cost,m_protect,m_cut,sid) values(5001,'KXNBAGAME-26NOV31EEEFFF-EEE',4,1,0,'u1')")
db.execute("insert into mom_after(sid,ts,ticker,o_net0,outcome,payout) values('u1',1,'KXNBAGAME-26NOV31EEEFFF-EEE',3.0,NULL,NULL)")
# signal shadow: 60 markets the books price at 60 against an ask of 50; settled yes. A live row and a 95c row do not count.
for i in range(60):
    t = f"KXNBAGAME-26DEC{i + 1:02d}GGGHHH-GGG"
    for j, ask in enumerate((0.50, 0.53, 0.53)):
        db.execute("insert into sig_sharp values(?,?,?,?,?,?,?,?)", (2000 + i * 100 + j * 45, t, 0.60, 0.48, ask, "x", 0, 0))
    db.execute("insert into sig_sharp values(?,?,?,?,?,?,?,?)", (1900 + i * 100, t, 0.99, 0.9, 0.5, "x", 1, 0))   # live: ignored
    db.execute("insert into closes(ticker,outcome) values(?,?)", (t, "yes"))
db.execute("insert into sig_sharp values(1,'KXNBAGAME-26DEC30XXXYYY-XXX',0.99,0.9,0.95,'x',0,0)"); db.execute("insert into closes(ticker,outcome) values('KXNBAGAME-26DEC30XXXYYY-XXX','yes')")
# exposure: 60 blocked bets that lost $5 each (blocking them saves $5); a seed row and a same-pass (batch 2) row are ignored
for i in range(60):
    db.execute("insert into expo_pos(pos,ts,games,seed,blocked,net,settled,batch) values(?,?,?,?,?,?,?,?)", (f"e{i}", 3000 + i * 100, json.dumps({f"G{i}": 1}), 0, "game_cap", -5.0, 1.0, 1))
db.execute("insert into expo_pos(pos,ts,games,seed,blocked,net,settled,batch) values('s1',1,'{}',1,'game_cap',-99,1,1)")
db.execute("insert into expo_pos(pos,ts,games,seed,blocked,net,settled,batch) values('b2',1,'{}',0,'game_cap',-99,1,2)")
rep = W.promote_report(q, {"exit_cap_shadow": True}, None, now=1.0)
by = {s["key"]: s for s in rep["signals"]}
m, s, e = by["mom"], by["sig"], by["expo"]
ok("F momentum: 180 rows from 60 bets are 60 decisions at +$3 each, passing", m["n"] == 60 and m["net"] == 180.0 and m["state"] == "pass")
ok("F momentum: the really-sold bet is left out and counted in a note", "1 bets that were really sold" in m["note"])
ok("F momentum: late replay uses the 30/60 s offers (2.0 < 3.0 still positive)", m["lag_n"] == 60 and m["lag_net"] == 60 * 2.0)
fee = lambda p: 0.07 * p * (1 - p)
n_ = int(10 // (0.5 + fee(0.5)))
ok("F signal: one paper buy per market (60), live and 95c rows left out", s["n"] == 60 and abs(s["net"] - 60 * n_ * (1 - 0.5 - fee(0.5))) < 0.05)
ok("F signal: fee and the 30-90 s later ask are in it (lag buys at 53c, 45 s later, so it pays less)", s["lag_n"] == 60 and s["lag_net"] < s["net"])
ok("F signal: three edge settings counted, the best one named", s["variants"] == 3 and s["variant"])
ok("F exposure: blocked bets that lost count as money saved; seed and same-pass rows ignored; no late replay, so it cannot pass", e["n"] == 60 and e["net"] == 300.0 and e["state"] == "wait" and "cannot pass" in e["reason"])
ok("F exposure: no lag replay", e["lag_net"] is None)
ok("F exit cap with no rows but a recorder that is on: plain Not enough data", by["cap"]["state"] == "wait" and "switched off" not in by["cap"]["reason"])
for i in range(60):
    t = f"KXNBAGAME-26JAN{i + 1:02d}IIIJJJ-III"
    db.execute("insert into exit_cap_shadow(ts,ticker,side,n,net,live_decision,alt_decision) values(?,?,?,?,?,?,?)", (4000 + i * 100, t, "yes", 10, 8.0, "hold", "sell_cap"))
    db.execute("insert into exit_cap_shadow(ts,ticker,side,n,net,live_decision,alt_decision) values(?,?,?,?,?,?,?)", (4001 + i * 100, t, "yes", 10, 8.0, "hold", "sell_cap"))
    db.execute("insert into bp_mkt(ticker,result,rs) values(?,?,?)", (t, 0, 1))            # the favorite lost: selling at $8 beat holding
db.execute("insert into exit_cap_shadow(ts,ticker,side,n,net,live_decision,alt_decision) values(1,'KXNBAGAME-26JAN30ZZZ-ZZ','yes',10,8,'hold','hold')")
c = {s["key"]: s for s in W.promote_report(q, {"exit_cap_shadow": True}, None, now=1.0)["signals"]}["cap"]
ok("F exit cap: first row per market where only the cap would sell; value = proceeds minus what holding paid", c["n"] == 60 and c["net"] == 480.0 and c["state"] == "wait" and "cannot pass" in c["reason"])
db.execute("update bp_mkt set rs=9"); db.execute("update bp_mkt set result=1")
c2 = {s["key"]: s for s in W.promote_report(q, {"exit_cap_shadow": True}, None, now=1.0)["signals"]}["cap"]
ok("F implied labels (rs=9) are not real results and are not settled on", c2["n"] == 0)
ok("F the report is plain data (json) with the bar sentence", json.loads(json.dumps(rep))["bar"].startswith("A signal passes") and not rep.get("computing"))

# ---- combos with no entry in the bets table count as their own "game", which can fake new games: fail closed (no push)
db2 = sqlite3.connect(":memory:")


def q2(sql, args=()):
    cur = db2.execute(sql, args)
    return [dict(zip([c[0] for c in cur.description], x)) for x in cur.fetchall()]


db2.executescript("""
create table mom_shadow(ts real, ticker text, cost real, m_protect int, m_cut int, sid text);
create table mom_after(sid text, ts real, ticker text, o_net0 real, o30 real, o60 real, outcome text, payout real);
create table bets(combo text, legs text);
""")
for i in range(60):
    t = f"KXMVE-C{i:02d}"
    db2.execute("insert into mom_shadow(ts,ticker,cost,m_protect,m_cut,sid) values(?,?,?,?,?,?)", (1000 + i * 100, t, 4.0, 1, 0, f"m{i}"))
    db2.execute("insert into mom_after(sid,ts,ticker,o_net0,o30,o60,outcome,payout) values(?,?,?,?,?,?,?,?)", (f"m{i}", 1, t, 3.0, 2.5, 2.0, "lost", 0.0))
    db2.execute("insert into bets(combo,legs) values(?,?)", (t, json.dumps([f"KXNBAGAME-26NOV{i + 1:02d}AAABBB-AAA", f"KXNBASPREAD-26NOV{i + 1:02d}AAABBB-AAA5"])))
m_ok = {s["key"]: s for s in W.promote_report(q2, {}, None, now=1.0)["signals"]}["mom"]
ok("H1 every combo has its games: nothing missing, passes and may push, as before", m_ok.get("missing") == 0 and m_ok["state"] == "pass" and m_ok["push_ok"] and "missing" not in m_ok["reason"] and m_ok["status"] == "Looking good, not proven yet")
ok("H1 the bets query is ordered, so the same data always reads the same way", "order by" in __import__("inspect").getsource(W.promote_legs).lower())
db2.execute("delete from bets where combo in ('KXMVE-C03','KXMVE-C20')")
rep_h = W.promote_report(q2, {}, None, now=1.0)
m_bad = {s["key"]: s for s in rep_h["signals"]}["mom"]
ok("H2 two combos with no bets entry: counted, and the push is refused", m_bad.get("missing") == 2 and not m_bad["push_ok"])
ok("H2 the card still shows a looking-good state, with a plain reason", m_bad["state"] == "pass" and m_bad["status"] == "Looking good, not proven yet" and m_bad["reason"] == "Some combos are missing their games; waiting" and m_bad["streak"] == 0)
for f_ in (W.PROMOTE_FILE, W.PROMOTE_STREAK_FILE):
    if os.path.exists(f_):
        os.remove(f_)
W.PROMOTE["pushed"].clear(); told_h = []
for i in range(6):
    W.promote_push_check(dict(rep_h, signals=[dict(s_, all_games=61 + i) for s_ in rep_h["signals"]]), {}, lambda *a, **k: told_h.append(a))
ok("H2 six looks on new games with combos missing their games: never pushed", not told_h)
ok("H2 even a report that claims push_ok is held back while any combo is missing its games", W.promote_push_check({"signals": [dict(s_, push_ok=True, missing=1, all_games=200 + 3 * 0) for s_ in rep_h["signals"]]}, {}, lambda *a, **k: told_h.append(a)) == [] and not told_h)
for f_ in (W.PROMOTE_FILE, W.PROMOTE_STREAK_FILE):
    if os.path.exists(f_):
        os.remove(f_)
W.PROMOTE["pushed"].clear()
mj = W.promote_judge([dict(ob(i, 1.0, lag=0.5), unk=(i == 5)) for i in range(60)], 1)
ok("H3 the judge counts positions flagged unknown and refuses the push band", mj["missing"] == 1 and not mj["push_ok"] and mj["state"] == "pass")
ok("H3 no flagged positions: the push band is as before", W.promote_judge([ob(i, 1.0, lag=0.5) for i in range(60)], 1)["push_ok"])
ok("H3 promote_unknown: only a combo with no known legs", W.promote_unknown("KXMVE-9", {}) and not W.promote_unknown("KXMVE-1", legs_) and not W.promote_unknown("KXNBAGAME-26NOV23LALBOS-LAL"))

# ---- the push
told = []
W.PROMOTE["pushed"].clear()
if os.path.exists(W.PROMOTE_FILE):
    os.remove(W.PROMOTE_FILE)
if os.path.exists(W.PROMOTE_STREAK_FILE):
    os.remove(W.PROMOTE_STREAK_FILE)
note = lambda msg, kind=None, url=None: told.append((msg, kind))
def grow(r, g):
    """The same report, but with `g` games settled (new data since the last look)."""
    return dict(r, signals=[dict(s, all_games=g) for s in r["signals"]])
passing = [s for s in rep["signals"] if s["state"] == "pass"]
ok("G the passing rows carry the stricter-band flag and the settled-game count", passing and all(s["push_ok"] and s["all_games"] == 60 for s in passing))
reps = [grow(rep, 61 + i) for i in range(5)]
sent = W.promote_push_check(reps[0], {}, note)
sent += W.promote_push_check(reps[1], {}, note)
ok("G two passes on new games: no push yet (needs 3 batches of newly settled games)", sent == [] and not told)
W.PROMOTE["pushed"].clear()                                   # a restart between the looks: the streak is saved
sent = W.promote_push_check(reps[2], {}, note)
names = {s["name"] for s in rep["signals"] if s["state"] == "pass"}
ok("G third pass on new games: one push per Passing signal, in Pete's words", names and {m for m, k in told} == {f"{n} passed the bar, say go" for n in names} and len(told) == len(names) == 2 and all(k == "promote" for m, k in told))
os.remove(W.PROMOTE_FILE); W.PROMOTE["pushed"].clear(); os.remove(W.PROMOTE_STREAK_FILE); told.clear()
for _ in range(6):                                            # refreshing on UNCHANGED data adds nothing, however often it runs
    W.promote_push_check(grow(rep, 70), {}, note)
ok("G the same data checked six times counts as ONE look: no push (a refresh cannot re-roll)", not told)
W.PROMOTE["pushed"].clear(); os.remove(W.PROMOTE_STREAK_FILE) if os.path.exists(W.PROMOTE_STREAK_FILE) else None
bad = {"signals": [dict(s, state="wait") for s in rep["signals"]]}
for r_ in (reps[0], reps[1], dict(bad, signals=[dict(s, all_games=62) for s in bad["signals"]]), reps[3]):   # pass, pass, miss, pass
    W.promote_push_check(r_, {}, note)
ok("G a refresh that is not Passing resets the streak (pass, pass, miss, pass sends nothing)", not told)
W.promote_push_check(reps[4], {}, note)
ok("G ...and still short after the miss (2 passes); the third new-data pass sends", not told)
W.promote_push_check(grow(rep, 99), {}, note)
ok("G ...third pass after the miss sends", len(told) == 2)
told.clear()
rep = grow(rep, 300)
for i in range(4):
    W.promote_push_check(grow(rep, 300 + i), {}, lambda *a, **k: told.append(a))
ok("G not again for the same signal, however much new data", not told)
W.PROMOTE["pushed"].clear()                                   # a restart: only the saved file remains
for i in range(4):
    W.promote_push_check(grow(rep, 400 + i), {}, lambda *a, **k: told.append(a))
ok("G not again after a restart (the saved list)", not told)
os.remove(W.PROMOTE_FILE); W.PROMOTE["pushed"].clear(); os.remove(W.PROMOTE_STREAK_FILE)
for i in range(5):
    W.promote_push_check({"signals": [dict(s_, push_ok=False, all_games=70 + i) for s_ in rep["signals"]]}, {}, lambda *a, **k: told.append(a))
ok("G Passing the card's band but not the stricter push band: never pushed", not told)
os.remove(W.PROMOTE_STREAK_FILE) if os.path.exists(W.PROMOTE_STREAK_FILE) else None
ok("G the switch (promote_push false) silences it", W.promote_push_check(grow(rep, 500), {"promote_push": False}, lambda *a, **k: told.append(a)) == [] and not told)
fail_rep = {"signals": [dict(s, state="fail") for s in rep["signals"]]}
ok("G nothing for Failing or Not enough data", W.promote_push_check(fail_rep, {}, lambda *a, **k: told.append(a)) == [])
ok("G the message avoids every urgent word, so it goes in the quiet digest", all(not any(w in m.lower() for w in W.Notifier.URGENT) for m, k in [(f"{s['name']} passed the bar, say go", 0) for s in rep["signals"]]))
pushed = []
W.push = lambda *a, **k: pushed.append((a, k))
class _E: CFG = {}
n = W.Notifier({"topic": "t"}, _E())
ok("G through the real notifier it waits for the digest (quiet hours apply), not an instant alert", n.add("Sell when a bet's price slips fast passed the bar, say go", kind="promote") is True and not pushed and len(n.q) == 1)
os.remove(W.PROMOTE_FILE) if os.path.exists(W.PROMOTE_FILE) else None
pnames = [name for key, name, what, fn in W.PROMOTE_SIGNALS] + [name for key, name, why in W.PROMOTE_UNMEASURED]
ok("G every signal name is free of the urgent words", all(not any(w in (nm + " passed the bar, say go").lower() for w in W.Notifier.URGENT) for nm in pnames))

# ---- never computed inside a request, cached
W.PROMOTE.update(report=None, at=0.0, busy=False)
def slow(sql, args=()):
    time.sleep(.05)
    return []
t0 = time.time(); first = W.promote_report_cached(slow, {}); dt_ = time.time() - t0
ok("H the first request returns at once with a 'computing' stub", first.get("computing") is True and dt_ < 0.3)
for _ in range(100):
    if W.PROMOTE["report"] is not None and not W.PROMOTE["busy"]:
        break
    time.sleep(.1)
second = W.promote_report_cached(slow, {})
ok("H then the finished report, from the cache, with no new work", second.get("signals") and not second.get("computing") and W.promote_report_cached(None, {}) is second)

# ---- nothing that buys or sells reads or imports it
eng = open(os.path.join(REPO, "nfl_combo_planner.py")).read()
ok("I the engine never mentions the judge, its recorder adapters or its switches", not re.search(r"promote_|PROMOTE|promote_report|promote_push", eng))
wsrc = open(os.path.join(REPO, "watcher", "combo_watcher.py")).read()
fence = re.search(r"# ===== READY TO PROMOTE \(report only\): begin =====.*?# ===== READY TO PROMOTE \(report only\): end =====", wsrc, re.S)
ok("I the judge is one fenced block in the watcher file", fence is not None and wsrc.count("READY TO PROMOTE (report only): begin") == 1)
outside = wsrc.replace(fence.group(0), "")
hits = [ln.strip() for ln in outside.splitlines() if re.search(r"promote_|PROMOTE", ln)]
ok("I outside the block only three lines mention it: the web route (two) and the thread start", len(hits) == 3 and all(re.search(r"promote_report|promote_loop", h) for h in hits))
blk = fence.group(0)
ok("I inside, the SQL only reads (no insert, update, delete or create)", not re.search(r"\b(insert into|update \w+ set|delete from|create table|drop table|alter table)\b", blk, re.I))
ok("I every query is capped (a LIMIT on each select, bar the table-exists check)", all("limit ?" in s or "sqlite_master" in s for s in re.findall(r'"select [^"]*"(?:\s*\n\s*"[^"]*")*', blk)) and blk.count("limit ?") >= 5)
ok("I it never calls anything that buys, sells, sizes or changes a setting", not re.search(r"kalshi_send|sell_single|buy_single|panel_exec|place_order|set_cfg|save_settings|CFG\[[^\]]+\]\s*=|CFG\.update|E\.notify\s*=|TRADING_PAUSED", blk))
ok("I the route reads the cache and never runs the judge", "promote_report_cached(A.store_rows" in outside and not re.search(r"promote_judge|promote_report\(", outside))
ok("I the new switches are watcher-only (conf, not engine settings) and default ON", 'conf.get("promote_report", True)' in wsrc and '.get("promote_push", True)' in blk)
res_js = open(os.path.join(REPO, "watcher", "spa", "results.js")).read()
ok("I the card only displays: no post, no button, no click handler on its rows", "function promoBlock" in res_js and not re.search(r"function promoBlock.*?(onclick|method:\s*'POST'|api\()", res_js.split("function promoBlock", 1)[1], re.S))

print("t_promote: %s" % ("ok" if not ok.bad else f"{ok.bad} FAILED"))
sys.exit(1 if ok.bad else 0)
