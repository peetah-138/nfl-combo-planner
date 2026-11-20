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
   res["beat_cost"] == (best > res["cost_both"]) and res["sim_pl"] == round(best - res["cost_both"], 2))

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
E._cover_pass = boom
out = E.cover_pass(log=lambda *a: None)
ok("cover_pass swallows an injected exception without raising (panel_loop safety)", out == [])
E._cover_ticks = boom
ok("cover_ticks swallows an injected exception without raising", E.cover_ticks(log=lambda *a: None) == 0)
