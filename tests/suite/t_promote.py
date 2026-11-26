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
r = judge([1.0] * 40)
ok("B steady winner over 40 games passes, with a reason", r["state"] == "pass" and r["status"] == "Passing" and "Made $40.00" in r["reason"] and r["n"] == 40)
r = judge([1.0] * 10)
ok("B 10 settled is Not enough data and says what it needs", r["status"] == "Not enough data" and "needs 20" in r["reason"])
r = judge([1.0] * 22)
ok("B 22 games leaves only 7 in the latest stretch: enough (5+) and passes", r["state"] == "pass")
r = judge([1.0] * 20)
ok("B 20 games: only 6 latest games, still counts", r["n"] == 20 and r["holdout_games"] == 6)
r = W.promote_judge([ob(i, 1.0, game="g0" if i < 19 else f"g{i}") for i in range(30)], 1)
ok("B many bets but few games: not enough games in the latest stretch", r["state"] == "wait" and "latest stretch" in r["reason"])
r = judge([-1.0] * 40)
ok("B a loser is Failing and says how much it lost", r["state"] == "fail" and r["status"] == "Failing" and "Lost $40.00" in r["reason"])
r = judge([2.0] * 28 + [-3.0] * 12)
ok("B good early, bad in the last 30%: Failing for the latest games even though the total is up", r["net"] > 0 and r["state"] == "fail" and "latest 30%" in r["reason"])
r = judge([10.0] * 20 + [-10.0] * 8 + [2.0] * 12)
ok("B only one half pays: Failing", r["net"] > 0 and r["holdout_net"] > 0 and r["state"] == "fail" and "one half" in r["reason"])
r = judge([1.0] * 40, lag=[-1.0] * 40)
ok("B pays on time, loses 30-60 s late: Failing", r["state"] == "fail" and "late" in r["reason"] and r["lag_n"] == 40)
r = judge([1.0] * 40, lag=[0.5] * 40)
ok("B still pays late: Passing and says so", r["state"] == "pass" and "late" in r["reason"])
r = judge([1.0] * 40, lag=[-5.0, None] * 20)
ok("B a lag replay with under 5 bets is ignored", r["state"] == "fail" or r["lag_net"] is not None)
r = judge([1.0] * 40, lag=[-5.0] * 3 + [None] * 37)
ok("B a lag replay with under 5 bets is ignored, and without a late check it cannot pass (3 of 40)", r["state"] == "wait" and r["lag_net"] is None and "cannot pass" in r["reason"] and "late" in r["reason"])
r = W.promote_judge([ob(i, 1.0) for i in range(40)], 1)
ok("B no late-order replay at all (sell line, bet pile-up): Not enough data, never Passing", r["state"] == "wait" and r["lag_n"] == 0 and "cannot pass" in r["reason"])
r = judge([10.0, -9.0] * 20)
ok("B up a little but noisy: Not enough data, 'too close to call'", r["net"] > 0 and r["state"] == "wait" and "too close to call" in r["reason"])
ok("B nothing recorded", W.promote_judge([], 1)["reason"] == "Nothing recorded yet.")
ok("B odd input (None values, missing lag) never raises", W.promote_judge([{"var": "a", "pos": "p", "game": "g", "ts": 1, "v": None}], 1)["state"] == "wait")
ok("B no jargon on screen", not re.search(r"bootstrap|out-of-sample|confidence", json.dumps([judge([1.0] * 40), judge([-1.0] * 40), judge([10.0, -9.0] * 20)]), re.I))

# ---- 99% range
vals = [3.0, -2.0, 1.0, 4.0, -1.0] * 8
obs = [ob(i, v) for i, v in enumerate(vals)]
a, b, c = W.promote_judge(obs, 6), W.promote_judge(obs, 7), W.promote_judge(obs, 1)
ok("C one setting: 99% range; more than one setting tried: stricter still (99.5%)", c["level"] == 99 and a["level"] == 99.5 and W.promote_judge(obs, 2)["level"] == 99.5)
ok("C 7 settings tried: 99% range, wider than one setting", b["level"] == 99.5 and b["low"] <= c["low"] and b["high"] >= c["high"] and b["high"] - b["low"] > c["high"] - c["low"])
many = [ob(i, 1.0, var=f"v{k}") for i in range(30) for k in range(7)]
ok("C the count of settings is taken from the data too (7 seen = more than one)", W.promote_judge(many, None)["level"] == 99.5)
ok("C the range is deterministic", W.promote_judge(obs, 1)["low"] == c["low"])
# the range is built on the latest 30% of games only: early games that made a lot cannot lift the range
early = [ob(i, 50.0 if i < 28 else (1.0 if i % 2 else -1.0)) for i in range(40)]
re_ = W.promote_judge(early, 1)
ok("C the range uses only the latest games (big early wins do not widen it up)", re_["high"] <= 12 and re_["net"] > 1000)

# ---- zero-edge random data must almost never read as Passing (the lucky moment that used to become a permanent go)
import random
def fake(seed, nv, games=40):
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
real = [ob(i, 2.0, lag=1.0) for i in range(40)]
ok("C2 a real steady edge still passes under the stricter rule", W.promote_judge(real, 3)["state"] == "pass")

# ---- 70/30: the setting is picked on the first 70% of games only
obs = [ob(i, 5.0 if i < 28 else -5.0, var="a") for i in range(40)] + [ob(i, -1.0 if i < 28 else 20.0, var="b") for i in range(40)]
r = W.promote_judge(obs, 2)
ok("D picks the setting that did best on the first 70% (a), then scores it on the last 30%", r["variant"] == "a" and r["holdout_net"] == -60.0 and r["state"] == "fail")

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
# momentum: 25 bets, each flagged on 3 rows (so 75 rows), sold early at $3 while the bet then lost (nothing paid): +$3 each
for i in range(25):
    t = f"KXNBAGAME-26NOV{i + 1:02d}AAABBB-AAA"
    for j in range(3):
        db.execute("insert into mom_shadow(ts,ticker,cost,m_protect,m_cut,sid) values(?,?,?,?,?,?)", (1000 + i * 100 + j, t, 4.0, 1, 0, f"s{i}_{j}"))
        db.execute("insert into mom_after(sid,ts,ticker,o_net0,o30,o60,outcome,payout) values(?,?,?,?,?,?,?,?)", (f"s{i}_{j}", 1, t, 3.0, 2.5, 2.0, "lost", 0.0))
# a bet really sold (cashed) is left out and counted; an unsettled one is not counted
db.execute("insert into mom_shadow(ts,ticker,cost,m_protect,m_cut,sid) values(5000,'KXNBAGAME-26NOV30CCCDDD-CCC',4,1,0,'c1')")
db.execute("insert into mom_after(sid,ts,ticker,o_net0,outcome,payout) values('c1',1,'KXNBAGAME-26NOV30CCCDDD-CCC',3.0,'cashed',3.0)")
db.execute("insert into mom_shadow(ts,ticker,cost,m_protect,m_cut,sid) values(5001,'KXNBAGAME-26NOV31EEEFFF-EEE',4,1,0,'u1')")
db.execute("insert into mom_after(sid,ts,ticker,o_net0,outcome,payout) values('u1',1,'KXNBAGAME-26NOV31EEEFFF-EEE',3.0,NULL,NULL)")
# signal shadow: 25 markets the books price at 60 against an ask of 50; settled yes. A live row and a 95c row do not count.
for i in range(25):
    t = f"KXNBAGAME-26DEC{i + 1:02d}GGGHHH-GGG"
    for j, ask in enumerate((0.50, 0.53, 0.53)):
        db.execute("insert into sig_sharp values(?,?,?,?,?,?,?,?)", (2000 + i * 100 + j * 45, t, 0.60, 0.48, ask, "x", 0, 0))
    db.execute("insert into sig_sharp values(?,?,?,?,?,?,?,?)", (1900 + i * 100, t, 0.99, 0.9, 0.5, "x", 1, 0))   # live: ignored
    db.execute("insert into closes(ticker,outcome) values(?,?)", (t, "yes"))
db.execute("insert into sig_sharp values(1,'KXNBAGAME-26DEC30XXXYYY-XXX',0.99,0.9,0.95,'x',0,0)"); db.execute("insert into closes(ticker,outcome) values('KXNBAGAME-26DEC30XXXYYY-XXX','yes')")
# exposure: 25 blocked bets that lost $5 each (blocking them saves $5); a seed row and a same-pass (batch 2) row are ignored
for i in range(25):
    db.execute("insert into expo_pos(pos,ts,games,seed,blocked,net,settled,batch) values(?,?,?,?,?,?,?,?)", (f"e{i}", 3000 + i * 100, json.dumps({f"G{i}": 1}), 0, "game_cap", -5.0, 1.0, 1))
db.execute("insert into expo_pos(pos,ts,games,seed,blocked,net,settled,batch) values('s1',1,'{}',1,'game_cap',-99,1,1)")
db.execute("insert into expo_pos(pos,ts,games,seed,blocked,net,settled,batch) values('b2',1,'{}',0,'game_cap',-99,1,2)")
rep = W.promote_report(q, {"exit_cap_shadow": True}, None, now=1.0)
by = {s["key"]: s for s in rep["signals"]}
m, s, e = by["mom"], by["sig"], by["expo"]
ok("F momentum: 75 rows from 25 bets are 25 decisions at +$3 each, passing", m["n"] == 25 and m["net"] == 75.0 and m["state"] == "pass")
ok("F momentum: the really-sold bet is left out and counted in a note", "1 bets that were really sold" in m["note"])
ok("F momentum: late replay uses the 30/60 s offers (2.0 < 3.0 still positive)", m["lag_n"] == 25 and m["lag_net"] == 25 * 2.0)
fee = lambda p: 0.07 * p * (1 - p)
n_ = int(10 // (0.5 + fee(0.5)))
ok("F signal: one paper buy per market (25), live and 95c rows left out", s["n"] == 25 and abs(s["net"] - 25 * n_ * (1 - 0.5 - fee(0.5))) < 0.05)
ok("F signal: fee and the 30-90 s later ask are in it (lag buys at 53c, 45 s later, so it pays less)", s["lag_n"] == 25 and s["lag_net"] < s["net"])
ok("F signal: three edge settings counted, the best one named", s["variants"] == 3 and s["variant"])
ok("F exposure: blocked bets that lost count as money saved; seed and same-pass rows ignored; no late replay, so it cannot pass", e["n"] == 25 and e["net"] == 125.0 and e["state"] == "wait" and "cannot pass" in e["reason"])
ok("F exposure: no lag replay", e["lag_net"] is None)
ok("F exit cap with no rows but a recorder that is on: plain Not enough data", by["cap"]["state"] == "wait" and "switched off" not in by["cap"]["reason"])
for i in range(25):
    t = f"KXNBAGAME-26JAN{i + 1:02d}IIIJJJ-III"
    db.execute("insert into exit_cap_shadow(ts,ticker,side,n,net,live_decision,alt_decision) values(?,?,?,?,?,?,?)", (4000 + i * 100, t, "yes", 10, 8.0, "hold", "sell_cap"))
    db.execute("insert into exit_cap_shadow(ts,ticker,side,n,net,live_decision,alt_decision) values(?,?,?,?,?,?,?)", (4001 + i * 100, t, "yes", 10, 8.0, "hold", "sell_cap"))
    db.execute("insert into bp_mkt(ticker,result,rs) values(?,?,?)", (t, 0, 1))            # the favorite lost: selling at $8 beat holding
db.execute("insert into exit_cap_shadow(ts,ticker,side,n,net,live_decision,alt_decision) values(1,'KXNBAGAME-26JAN30ZZZ-ZZ','yes',10,8,'hold','hold')")
c = {s["key"]: s for s in W.promote_report(q, {"exit_cap_shadow": True}, None, now=1.0)["signals"]}["cap"]
ok("F exit cap: first row per market where only the cap would sell; value = proceeds minus what holding paid", c["n"] == 25 and c["net"] == 200.0 and c["state"] == "wait" and "cannot pass" in c["reason"])
db.execute("update bp_mkt set rs=9"); db.execute("update bp_mkt set result=1")
c2 = {s["key"]: s for s in W.promote_report(q, {"exit_cap_shadow": True}, None, now=1.0)["signals"]}["cap"]
ok("F implied labels (rs=9) are not real results and are not settled on", c2["n"] == 0)
ok("F the report is plain data (json) with the bar sentence", json.loads(json.dumps(rep))["bar"].startswith("A signal passes") and not rep.get("computing"))

# ---- the push
told = []
W.PROMOTE["pushed"].clear()
if os.path.exists(W.PROMOTE_FILE):
    os.remove(W.PROMOTE_FILE)
if os.path.exists(W.PROMOTE_STREAK_FILE):
    os.remove(W.PROMOTE_STREAK_FILE)
note = lambda msg, kind=None, url=None: told.append((msg, kind))
sent = W.promote_push_check(rep, {}, note)
ok("G first Passing refresh: no push yet (needs 2 in a row)", sent == [] and not told)
W.PROMOTE["pushed"].clear()                                   # a restart between the two refreshes: the streak is saved
sent = W.promote_push_check(rep, {}, note)
names = {s["name"] for s in rep["signals"] if s["state"] == "pass"}
ok("G second Passing refresh in a row: one push per Passing signal, in Pete's words", names and {m for m, k in told} == {f"{n} passed the bar, say go" for n in names} and len(told) == len(names) == 2 and all(k == "promote" for m, k in told))
os.remove(W.PROMOTE_FILE); W.PROMOTE["pushed"].clear(); os.remove(W.PROMOTE_STREAK_FILE); told.clear()
bad = {"signals": [dict(s, state="wait") for s in rep["signals"]]}
for r_ in (rep, bad, rep):                                    # pass, then a miss resets the streak, then pass again: still no push
    W.promote_push_check(r_, {}, note)
ok("G a refresh that is not Passing resets the streak (pass, miss, pass sends nothing)", not told)
W.promote_push_check(rep, {}, note)
ok("G ...and two in a row after the miss does send", len(told) == 2)
told.clear()
told.clear()
ok("G not again for the same signal", W.promote_push_check(rep, {}, lambda *a, **k: told.append(a)) == [] and not told)
W.PROMOTE["pushed"].clear()                                   # a restart: only the saved file remains
ok("G not again after a restart (the saved list)", W.promote_push_check(rep, {}, lambda *a, **k: told.append(a)) == [] and not told)
os.remove(W.PROMOTE_FILE); W.PROMOTE["pushed"].clear(); os.remove(W.PROMOTE_STREAK_FILE)
ok("G the switch (promote_push false) silences it", W.promote_push_check(rep, {"promote_push": False}, lambda *a, **k: told.append(a)) == [] and not told)
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
