# CHECK: group=engine
import os, time, tempfile, importlib.util, json, datetime as dt
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()

# A fake NFL week: a Thursday night game and two Sunday-early games (the covered checkpoint), then two Sunday-late
# games (the later checkpoint the survivor is carried into). Prices are Kalshi's own, scaled to 100%.
# Anchor the week on the coming Sunday (Monday keeps the prior Sunday, like week_of).
today = dt.date.today()
SUN = today - dt.timedelta(days=1) if today.weekday() == 0 else today + dt.timedelta(days=(6 - today.weekday()) % 7)
THU = SUN - dt.timedelta(days=3)
# kickoffs: Thursday 20:15, Sunday-early 13:00 and 13:05, Sunday-late 16:25 and 16:30 (local-ish unix times)
def ts(d, h, m=0):
    return dt.datetime(d.year, d.month, d.day, h, m).timestamp()

GAMES = {
    THU: [{"event": "KXNFLGAME-THU-KCBUF", "kick": ts(THU, 20, 15),
           "sides": [{"ticker": "KXNFLGAME-THU-KCBUF-KC", "abbr": "KC", "p": 0.60},
                     {"ticker": "KXNFLGAME-THU-KCBUF-BUF", "abbr": "BUF", "p": 0.40}]}],
    SUN: [{"event": "KXNFLGAME-SUNE-DALNYG", "kick": ts(SUN, 13, 0),
           "sides": [{"ticker": "KXNFLGAME-SUNE-DALNYG-DAL", "abbr": "DAL", "p": 0.55},
                     {"ticker": "KXNFLGAME-SUNE-DALNYG-NYG", "abbr": "NYG", "p": 0.45}]},
          {"event": "KXNFLGAME-SUNE-PHIWAS", "kick": ts(SUN, 13, 5),
           "sides": [{"ticker": "KXNFLGAME-SUNE-PHIWAS-PHI", "abbr": "PHI", "p": 0.65},
                     {"ticker": "KXNFLGAME-SUNE-PHIWAS-WAS", "abbr": "WAS", "p": 0.35}]},
          {"event": "KXNFLGAME-SUNL-SFSEA", "kick": ts(SUN, 16, 25),
           "sides": [{"ticker": "KXNFLGAME-SUNL-SFSEA-SF", "abbr": "SF", "p": 0.58},
                     {"ticker": "KXNFLGAME-SUNL-SFSEA-SEA", "abbr": "SEA", "p": 0.42}]},
          {"event": "KXNFLGAME-SUNL-GBMIN", "kick": ts(SUN, 16, 30),
           "sides": [{"ticker": "KXNFLGAME-SUNL-GBMIN-GB", "abbr": "GB", "p": 0.70},
                     {"ticker": "KXNFLGAME-SUNL-GBMIN-MIN", "abbr": "MIN", "p": 0.30}]}],
}
E._cover_games = lambda day: GAMES.get(day, [])
E._cover_kicks = lambda day: []                     # kickoffs come straight from GAMES above
E.week_of = lambda t: SUN                            # all legs anchor on this week's Sunday
E._cover_r_buy = lambda: 0.85
E.kalshi_discount = lambda live=False: 0.90

# --- 1. multi-day slot building: Thursday is its own first checkpoint, Sunday-early a second, Sunday-late a third
slots = E._cover_week_slots(SUN)
ok("slots span multiple days, earliest first", [s["day_label"] for s in slots] == ["Thursday", "Sunday", "Sunday"]
   and len(slots) == 3 and len(slots[0]["games"]) == 1 and len(slots[1]["games"]) == 2 and len(slots[2]["games"]) == 2)

# --- 2. first pass writes one open cover row, keyed on the week's Sunday, status 'open', slots stored in `early`
RES = {}
E.fetch_results = lambda tickers: {t: RES[t] for t in tickers if t in RES}
early_kick = slots[0]["kick_start"]
E.time.time = lambda: early_kick - 1800             # 30 min before the first (Thursday) kickoff
did = E.cover_pass(log=lambda *a: None)
row = E.store_rows("select * from cover")
ok("one cover row written, status 'open', keyed on the week's Sunday",
   len(row) == 1 and row[0]["sunday"] == SUN.isoformat() and row[0]["status"] == "open")
stored = json.loads(row[0]["early"])
ok("the slate's checkpoints are stored as slots (no schema change)", len(stored) == 3 and stored[0]["day_label"] == "Thursday")

# a second pass the same week (now on Sunday, a different weekday) must NOT make a new row
E.time.time = lambda: ts(SUN, 10, 0)
E.cover_pass(log=lambda *a: None)
ok("a later pass the same week reuses the one row (week-keyed, not day-keyed)", len(E.store_rows("select * from cover")) == 1)

# --- 3. the covered (first) checkpoint settles: Thursday KC wins (the favourite, so the value-pick survives)
RES.update({"KXNFLGAME-THU-KCBUF-KC": "yes", "KXNFLGAME-THU-KCBUF-BUF": "no"})
E.cover_pass(log=lambda *a: None)
st = json.loads(E.store_rows("select * from cover")[0]["result"])
ok("survivor recorded once the first checkpoint settles", st["survivor"] == ["KC"] and st["cost_both"] == 5.0 * 2 ** 1)
ok("survivor's full-slate combo payout computed (gross, with the combo haircut)", st["survivor_pays"] > 0)

# --- 4. cover_ticks records state='sim' ticks for the survivor's still-live later legs (value-picked sides)
#     fake an evolving, climbing path so the smart-sell replay has something to sell into.
later_tks = sorted({max(g["sides"], key=lambda x: x["p"])["ticker"] for s in stored[1:] for g in s["games"]})
class R:
    def __init__(s, d): s.d = d
    def raise_for_status(s): pass
    def json(s): return s.d
asked = []
def fake_get(url, params=None, timeout=None):
    tks = (params or {}).get("tickers", "").split(",")
    asked.append(tks)
    return R({"markets": [{"ticker": t, "yes_bid_dollars": "0.80", "yes_ask_dollars": "0.82", "status": "active"} for t in tks]})
E.requests.get = fake_get
E.store_x("delete from ticks")
saved = E.cover_ticks(log=lambda *a: None)
tk = E.store_rows("select * from ticks where state='sim'")
ok("cover_ticks writes state='sim' ticks for the survivor's later legs", saved == len(later_tks)
   and {r["ticker"] for r in tk} == set(later_tks) and all(0.02 <= r["chance"] <= 0.98 for r in tk))

# build a rising recorded path on the survivor's later legs so sim_exit fires a positive 'smart' exit
E.store_x("delete from ticks")
combo = E._cover_survivor_combo(stored[0]["games"],
                                [max(g["sides"], key=lambda x: x["p"]) for g in stored[0]["games"]],
                                [g for s in stored[1:] for g in s["games"]], 0.85, 5.0)
for i, ch in enumerate([0.55, 0.72, 0.9, 0.97]):
    for l in combo["legs"]:
        E.store_x("insert into ticks values(?,?,?,?,?)", (combo["kick"] - 290 + i * 60, l["ticker"], ch, "sim", "active"))
sim = E.sim_exit(combo)
ok("sim_exit returns a positive exit as the survivor's later legs come good", sim and sim[0] > 0)

# --- 5. the later checkpoints settle (value-picks hold), the week finishes, beat_cost is decided
for s in stored[1:]:
    for g in s["games"]:
        fav = max(g["sides"], key=lambda x: x["p"])
        for x in g["sides"]:
            RES[x["ticker"]] = "yes" if x["ticker"] == fav["ticker"] else "no"
E.time.time = lambda: ts(SUN, 20, 0)                # Sunday night, everything settled
E.cover_pass(log=lambda *a: None)
done = E.store_rows("select * from cover")[0]
res = json.loads(done["result"])
ok("the week finishes with status 'done'", done["status"] == "done")
ok("per-checkpoint worth recorded for the settled later slots", any(c["worth"] > 0 for c in res["checkpoints"]))
ok("a replay exit is recorded on a checkpoint", any(c.get("replay_exit") for c in res["checkpoints"]))
best = max((c["replay_exit"]["exit"] for c in res["checkpoints"] if c.get("replay_exit")), default=None)
ok("beat_cost set from whether the best exit cleared the doubled cost",
   res["beat_cost"] == (best > res["cost_both"] + res["fees_both"])
   and res["sim_pl"] == round(best - res["cost_both"] - res["fees_both"], 2))

# --- 6. the one-sided baseline differs from the full cover-both-sides result
ok("one_sided_pl is present and differs from sim_pl (it only risks $5, not the doubled cost)",
   "one_sided_pl" in res and res["one_sided_pl"] != res["sim_pl"])

# --- 7. cover_summary surfaces the aggregate sim_pl / one_sided_pl / beat count
summ = E.cover_summary()
ok("cover_summary returns sim_pl, one_sided_pl and the beat count",
   summ["n"] == 1 and "sim_pl" in summ and "one_sided_pl" in summ and summ["beat"] in (0, 1)
   and abs(summ["sim_pl"] - res["sim_pl"]) < 0.01)

# --- 8. SAFETY: cover_pass swallows an injected exception and never raises (it runs inside the live panel_loop)
boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
_orig_cover_pass, _orig_cover_ticks = E._cover_pass, E._cover_ticks
E._cover_pass = boom
out = E.cover_pass(log=lambda *a: None)
ok("cover_pass swallows an injected exception without raising (panel_loop safety)", out == [])
E._cover_ticks = boom
ok("cover_ticks swallows an injected exception without raising", E.cover_ticks(log=lambda *a: None) == 0)

# --- 9. an open row saved by an older version (a plain list of games, no checkpoints) or left open 10+ days is marked
#        stale instead of raising KeyError every round, and a good row is left alone
E.store_x("insert into cover values(?,?,?,?,?,?,?,?)", ("2020-01-05", time.time(), json.dumps([{"event": "X", "kick": 1, "sides": []}]), None, 0.85, 0.9, "open", None))
old = E.store_rows("select * from cover where sunday='2020-01-05'")[0]
ok("an old-shape open cover row gives no checkpoints", E._cover_row_slots(old, time.time()) is None)
ok("...and an old-shape row's resolve returns quietly", E._cover_resolve(old, time.time(), None) == [])
ok("...and is marked stale", E.store_rows("select status from cover where sunday='2020-01-05'")[0]["status"] == "stale")
E.store_x("insert into cover values(?,?,?,?,?,?,?,?)", ("2020-01-12", time.time() - 11 * 86400, json.dumps(slots), None, 0.85, 0.9, "open", None))
aged = E.store_rows("select * from cover where sunday='2020-01-12'")[0]
ok("a row open for 10+ days is marked stale", E._cover_row_slots(aged, time.time()) is None
   and E.store_rows("select status from cover where sunday='2020-01-12'")[0]["status"] == "stale")
fresh_row = dict(aged); fresh_row["ts"] = time.time()
ok("a current row with checkpoints is kept", bool(E._cover_row_slots(fresh_row, time.time())))

# ======== #340: a dead combo is worth $0 from the checkpoint that killed it on; the lean variant ========
# A fresh week: Sunday-early (covered, 2 games: one close, one lopsided), then two later checkpoints. The survivor's
# Sunday-late pick LOSES, the Monday pick wins. Old code: the Monday checkpoint still showed the combo's worth and the
# replay sold it on the lost pick's last (stale) price.
SUN2 = "2031-01-05"
k0 = time.time() - 3 * 86400
def gm(ev, kick, a, pa, b, pb):
    return {"event": ev, "kick": kick, "sides": [{"ticker": f"{ev}-{a}", "abbr": a, "p": pa}, {"ticker": f"{ev}-{b}", "abbr": b, "p": pb}]}
S0 = [gm("X-CLOSE", k0, "AAA", 0.55, "BBB", 0.45), gm("X-LOP", k0 + 60, "CCC", 0.82, "DDD", 0.18)]
S1 = [gm("X-LATE", k0 + 4 * 3600, "EEE", 0.60, "FFF", 0.40)]
S2 = [gm("X-MON", k0 + 30 * 3600, "GGG", 0.65, "HHH", 0.35)]
SL = [{"slot_key": 1, "day_label": "Sunday", "kick_start": k0, "games": S0},
      {"slot_key": 2, "day_label": "Sunday", "kick_start": k0 + 4 * 3600, "games": S1},
      {"slot_key": 3, "day_label": "Monday", "kick_start": k0 + 30 * 3600, "games": S2}]
E.store_x("insert into cover values(?,?,?,?,?,?,?,?)", (SUN2, time.time() - 3 * 86400, json.dumps(SL), None, 0.85, 0.9, "open", None))
RES.clear()
RES.update({"X-CLOSE-AAA": "yes", "X-CLOSE-BBB": "no", "X-LOP-CCC": "yes", "X-LOP-DDD": "no",
            "X-LATE-EEE": "no", "X-LATE-FFF": "yes",            # the survivor's later pick (EEE) loses: combo dead
            "X-MON-GGG": "yes", "X-MON-HHH": "no"})
# recorded path: EEE was live at about 0.60 until the Sunday-late game, then never seen again (lost); GGG climbs to 0.97
# after that, so a replay on the stale 0.60 would "sell" a combo that is already dead.
E.store_x("delete from ticks")
kk = k0 + 4 * 3600
for i, (e, g) in enumerate([(0.60, 0.65), (0.58, 0.66), (0.60, 0.65), (0.62, 0.66)]):
    E.store_x("insert into ticks values(?,?,?,?,?)", (kk - 200 + i * 60, "X-LATE-EEE", e, "sim", "active"))
    E.store_x("insert into ticks values(?,?,?,?,?)", (kk - 200 + i * 60, "X-MON-GGG", g, "sim", "active"))
for i, g in enumerate([0.80, 0.90, 0.95, 0.97, 0.97, 0.97]):
    E.store_x("insert into ticks values(?,?,?,?,?)", (kk + 3600 + i * 600, "X-MON-GGG", g, "sim", "active"))
row2 = E.store_rows("select * from cover where sunday=?", (SUN2,))[0]
E._cover_resolve(row2, time.time(), None)
r2 = E.store_rows("select * from cover where sunday=?", (SUN2,))[0]
x = json.loads(r2["result"])
cps = x["checkpoints"]
ok("#340: the week finishes", r2["status"] == "done" and len(cps) == 2)
ok("#340: the checkpoint where the survivor's pick lost is worth $0", cps[0]["worth"] == 0 and cps[0]["alive"] is False)
ok("#340: every checkpoint after the combo died is worth $0 (old code valued Monday on its own)",
   cps[1]["worth"] == 0 and cps[1]["alive"] is False)
ok("#340: the replay never sells a dead combo on its lost pick's stale price", all(c["replay_exit"] is None for c in cps))
dead = E._cover_survivor_combo(S0, [S0[0]["sides"][0], S0[1]["sides"][0]], S1 + S2, 0.85, 5.0)
ok("#340: (the whole stale path WOULD have sold it: the cut-off is what stops it)", E.sim_exit(dead) is not None
   and E.sim_exit(dead, until=kk - 20) is None)
ok("#340: the survivor's early legs (already won) start the replay at 1.0", all(l["p"] == 1.0 for l in dead["legs"][:2])
   and dead["pays"] == round(5.0 / (0.55 * 0.82 * 0.60 * 0.65) * 0.85, 2))
ok("#340: the result is $0 and the P/L is minus the whole cost with fees",
   x["value"] == 0 and x["sim_pl"] == round(-x["cost_both"] - x["fees_both"], 2) and x["beat_cost"] is False
   and x["lost"] == "EEE")
ok("#340: the favourite-side baseline (same survivor) is dead too", x["one_sided_result"] == 0)

# the same week with the later picks all winning: worth is the cumulative value (both later checkpoints counted)
RES.update({"X-LATE-EEE": "yes", "X-LATE-FFF": "no"})
E.store_x("update cover set status='open', result=null where sunday=?", (SUN2,))
E.store_x("delete from ticks")
row2 = E.store_rows("select * from cover where sunday=?", (SUN2,))[0]
E._cover_resolve(row2, time.time(), None)
x = json.loads(E.store_rows("select result from cover where sunday=?", (SUN2,))[0]["result"])
pe = 0.55 * 0.82
pays = 5.0 / (pe * 0.60 * 0.65) * 0.85
ok("#340: alive, a middle checkpoint's worth counts every pick settled so far (cash-out discount, Monday still live)",
   abs(x["checkpoints"][0]["worth"] - round(5.0 * 0.85 / (pe * 0.60) * 0.9, 2)) < 0.011)
ok("#340: alive, the last checkpoint is the full payout (nothing left to sell)",
   abs(x["checkpoints"][1]["worth"] - round(pays, 2)) < 0.011 and x["checkpoints"][1]["alive"] is True)

# --- the lean variant: only the close game (55%) is covered, the lopsided one's favourite (CCC, 82%) is carried
v = x["variants"]
ok("#340: both variants reported side by side", set(v) == {"full", "lean"})
ok("#340: full cover = 2 games, 4 combos; lean = 1 close game, 2 combos, CCC carried",
   v["full"]["k"] == 2 and v["full"]["combos"] == 4 and v["lean"]["k"] == 1 and v["lean"]["combos"] == 2
   and v["lean"]["carried"] == ["CCC"] and v["lean"]["thr"] == 0.75)
ok("#340: costs include Kalshi's taking fee (stake x 2^k plus a positive fee)",
   v["full"]["stake"] == 20.0 and v["full"]["fees"] > 0 and v["full"]["cost"] == round(20.0 + v["full"]["fees"], 2)
   and v["lean"]["stake"] == 10.0 and 0 < v["lean"]["fees"] < v["full"]["fees"])
ok("#340: lean carries the same survivor, so the same result, for half the cost",
   v["lean"]["result"] == v["full"]["result"] > 0 and v["lean"]["pl"] > v["full"]["pl"])
fee1 = E.single_fee(min(pe * 0.60 * 0.65 / 0.85, 0.99), 5.0 / (pe * 0.60 * 0.65 / 0.85)) * 5.0 / (pe * 0.60 * 0.65 / 0.85)
ok("#340: a combo's fee is single_fee at its price (legs' product over r_buy), rounded per order",
   abs(E._cover_fees([], pe * 0.60 * 0.65, 0.85, 5.0) - round(fee1, 2)) < 0.006)

# an upset in the lopsided game kills every lean combo (full cover still has its survivor)
RES.update({"X-LOP-CCC": "no", "X-LOP-DDD": "yes"})
E.store_x("update cover set status='open', result=null where sunday=?", (SUN2,))
row2 = E.store_rows("select * from cover where sunday=?", (SUN2,))[0]
E._cover_resolve(row2, time.time(), None)
x = json.loads(E.store_rows("select result from cover where sunday=?", (SUN2,))[0]["result"])
v = x["variants"]
ok("#340: an upset in a carried game: lean is $0, minus its cost; full keeps its survivor",
   v["lean"]["result"] == 0 and v["lean"]["pl"] == -v["lean"]["cost"] and v["lean"]["upset"] == ["DDD"]
   and v["lean"]["alive"] is False and v["full"]["result"] > 0)

# cover_math (before kickoff): the lean preview, and the threshold splits games as documented
m = E.cover_math(S0, 0.85, 0.9, later=S1 + S2)
ok("#340: cover_math shows the lean variant before kickoff",
   m["lean"]["k"] == 1 and m["lean"]["combos"] == 2 and abs(m["lean"]["p_alive"] - 0.82) < 1e-9 and m["fees"] > 0)
cl, lp = E.cover_lean_split(S0, 0.85)
ok("#340: the lean threshold is a setting (85% covers both games here)", len(cl) == 2 and not lp)

# a finished week worked out by an older version is redone once, quietly, with the fix (no alert)
old_res = {"cost_both": 20.0, "checkpoints": [{"label": "Monday", "slot_key": 3, "worth": 99.0}], "sim_pl": 79.0, "pl": 79.0}
RES.update({"X-LOP-CCC": "yes", "X-LOP-DDD": "no", "X-LATE-EEE": "no", "X-LATE-FFF": "yes"})
E.store_x("update cover set status='done', result=? where sunday=?", (json.dumps(old_res), SUN2))
E._cover_pass = _orig_cover_pass
alerts = []
E.time.time = lambda: ts(SUN, 20, 0)
E.cover_pass(log=lambda *a: None, alert=alerts.append)
r2 = E.store_rows("select * from cover where sunday=?", (SUN2,))[0]
x = json.loads(r2["result"])
ok("#340: an old finished week is redone with the fix and stays done, without a second alert",
   r2["status"] == "done" and x.get("v") == 2 and x["sim_pl"] < 0 and x["checkpoints"][-1]["worth"] == 0
   and not any(SUN2 in a for a in alerts))

# isolation: the cover test never touches the panel table
E._panel_table()
ok("#340: paper only, the panel table is untouched", E.store_rows("select count(*) n from panel")[0]["n"] == 0)
