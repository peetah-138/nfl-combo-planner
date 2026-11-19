# Per-league learning (issue #13): combo cut-offs, fair-price calibration and the panel's pay index learn per
# league (each soccer league apart), borrowing league -> sport -> everyone. With no league-level data the
# outputs must be exactly what they were before (checked against the old code, kept verbatim below).
import os, time, tempfile, importlib.util, json
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.CUTOFF_FILE = os.path.join(E.HERE, "cut.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()

# ---- the code as it was before leagues had their own (version 2026.11.18.118), verbatim
OLD = r'''
def _cut_key(code, n):
    return f"{code}:{'2' if n <= 2 else '3-4' if n <= 4 else '5-7' if n <= 7 else '8+'}"


def combo_cutoff(code, n):
    d = load_json(CUTOFF_FILE, {})
    return float((d.get(_cut_key(code, n)) or {}).get("level", 95)) / 100


def adjust_cutoffs(force=False):
    d = load_json(CUTOFF_FILE, {})
    if not force and time.time() - d.get("_at", 0) < 7 * 86400:
        return []
    if not STORE["db"]:
        return []
    rows = store_rows("select sport, n, pct, pays, stake, legs, outcome, ts from quotes where pct is not null and ts > ?",
                      (time.time() - 60 * 86400,))
    trip = exit_factor()
    groups = defaultdict(list)
    for r in rows:
        legs = json.loads(r["legs"] or "[]")
        cl = close_prices([x[0] for x in legs])
        r = dict(r)
        if legs and len(cl) == len(legs) and all(x[1] for x in legs):
            r["val"] = r["pays"] / r["stake"] * math.prod(cl[x[0]] for x in legs) * trip
        elif r["outcome"] in ("won", "lost"):
            r["val"] = (r["pays"] / r["stake"] if r["outcome"] == "won" else 0) * trip
        else:
            continue
        for sp in (r["sport"] or "").split(","):
            groups[_cut_key(sp, r["n"] or 2)].append(r)
    moved = []
    for key, rs in groups.items():
        cur = float((d.get(key) or {}).get("level", 95))
        L = cur / 100
        above = [r["val"] for r in rs if L <= r["pct"] < L + 0.05]
        below = [r["val"] for r in rs if L - 0.05 <= r["pct"] < L]
        avg = lambda xs: sum(xs) / len(xs)
        new, why = cur, ""
        if len(above) >= 25 and avg(above) < 0.97:
            step = 3 if len(above) >= 40 and avg(above) < 0.85 else 2
            new, why = min(cur + step, 110), f"raised: combos just over the bar were worth {avg(above):.0%} of their cost by game time"
        elif len(below) >= 25 and avg(below) >= 1.0 and cur > 85:
            step = 3 if len(below) >= 40 and avg(below) >= 1.05 else 2
            new, why = max(cur - step, 85), f"lowered: combos it skipped just under the bar were worth {avg(below):.0%} of their cost by game time"
        if new != cur:
            d[key] = {"level": new, "why": why, "at": int(time.time()), "n": len(rs)}
            moved.append(f"{key} {cur:.0f}% → {new:.0f}% ({why})")
        else:
            d.setdefault(key, {"level": cur, "why": "", "n": len(rs)})["n"] = len(rs)
    d["_at"] = time.time()
    save_json(CUTOFF_FILE, d)
    return moved


def calibration():
    if time.time() - CALIB["at"] < 3600 or not STORE["db"]:
        return CALIB["m"]
    _close_table()
    rows = store_rows("select sport, fair, outcome from closes where outcome in ('yes','no')")
    by = defaultdict(list)
    for r in rows:
        by[r["sport"]].append((r["fair"], r["outcome"] == "yes"))
    out = {}
    for sp, xs in by.items():
        bands = []
        for lo in (0.0, 0.3, 0.45, 0.55, 0.7, 0.85):
            hi = {0.0: 0.3, 0.3: 0.45, 0.45: 0.55, 0.55: 0.7, 0.7: 0.85, 0.85: 1.01}[lo]
            b = [(f, w) for f, w in xs if lo <= f < hi]
            if b:
                bands.append((lo, hi, sum(f for f, _ in b) / len(b), sum(w for _, w in b) / len(b), len(b)))
        out[sp] = bands
    CALIB.update(at=time.time(), m=out)
    return out


def calib_fair(code, fair):
    for lo, hi, mf, wr, n in calibration().get(code, []):
        if lo <= fair < hi:
            k = n / (n + 300)
            return min(max(fair + k * (wr - mf), 0.01), 0.99)
    return fair


def sport_pay_index():
    if not STORE["db"]:
        return {}
    rows = store_rows("select sport, pct from quotes where pct is not null and ts > ?", (time.time() - 45 * 86400,))
    by = defaultdict(list)
    for r in rows:
        by[r["sport"] or ""].append(r["pct"])
    allv = [p for v in by.values() for p in v]
    if len(allv) < 20:
        return {}
    mid = statistics.median(allv)
    return {k: round(statistics.median(v) / mid, 3) for k, v in by.items() if len(v) >= 10 and "," not in k}
'''
O = dict(vars(E))
O["CALIB"] = {"at": 0, "m": {}}
exec(OLD, O)


def fresh_calib():
    E.CALIB.update(at=0, m={}); O["CALIB"].update(at=0, m={})


def same_cut(code, n, legs):
    O["CUTOFF_FILE"] = E.CUTOFF_FILE
    return E.combo_cutoff(code, n, legs) == O["combo_cutoff"](code, n)


EPL = ["KXEPLGAME-26NOV22ARSCHE-ARS", "KXEPLGAME-26NOV22LIVMCI-LIV"]
LIGA = ["KXLALIGAGAME-26NOV22RMABAR-RMA", "KXLALIGAGAME-26NOV22ATMSEV-ATM"]
SERIEA = ["KXSERIEAGAME-26NOV22INTMIL-INT", "KXSERIEAGAME-26NOV22JUVROM-JUV"]
NBA = ["KXNBAGAME-26NOV18LALBOS-LAL", "KXNBAGAME-26NOV18NYKMIA-NYK"]
NHL = ["KXNHLGAME-26NOV18SJSVGK-SJS"]
AHL = ["KXAHLGAME-26NOV191900HERCHA-HER"]
SHAPES = [("soccer", EPL), ("soccer", LIGA), ("soccer", SERIEA), ("soccer", [EPL[0], LIGA[0]]), ("nba", NBA),
          ("nhl", NHL * 2), ("ahl", AHL * 2), ("nfl", ["KXNFLGAME-26NOV22KCBUF-KC"] * 3), ("mix", [NBA[0], NHL[0]])]
FAIRS = [0.05, 0.2, 0.31, 0.44, 0.5, 0.52, 0.6, 0.69, 0.72, 0.8, 0.86, 0.95]

# ---- 1. nothing learned yet: exactly as before
fresh_calib()
ok("no data: every cut-off is the 95% start, as before",
   all(same_cut(c, n, l) and E.combo_cutoff(c, n, l) == 0.95 for c, l in SHAPES for n in (2, 3, 5, 8)))
ok("no data: fair prices pass straight through, as before",
   all(E.calib_fair(c, f, l[0]) == O["calib_fair"](c, f) == f for c, l in SHAPES for f in FAIRS))

# ---- 2. an old cut-off file (sport keys only) is read exactly as before; leagues use their sport's level
old_file = {"soccer:2": {"level": 90, "why": "lowered: ...", "n": 80}, "soccer:3-4": {"level": 97, "why": "", "n": 12},
            "nba:2": {"level": 92, "why": "lowered: ...", "n": 60}, "nhl:3-4": {"level": 98, "why": "raised: ...", "n": 70},
            "nfl:5-7": {"level": 100, "why": "raised: ...", "n": 44}, "_at": now - 3 * 86400}
E.save_json(E.CUTOFF_FILE, old_file)
ok("old cut-off file: every sport and league reads the same level as before",
   all(same_cut(c, n, l) for c, l in SHAPES for n in (2, 3, 5, 8)))
ok("old cut-off file: the Premier League and La Liga use soccer's 90% (thin leagues = their sport)",
   E.combo_cutoff("soccer", 2, EPL) == 0.90 and E.combo_cutoff("soccer", 2, LIGA) == 0.90 and E.combo_cutoff("soccer", 2) == 0.90)
ok("legs given as leg dicts or [ticker, p, fair] rows work too",
   E.combo_cutoff("soccer", 2, [{"ticker": t} for t in EPL]) == 0.90 and E.combo_cutoff("soccer", 2, [[t, .5, .5] for t in EPL]) == 0.90)

# a league entry that is still thin (under 30 quotes, never moved) is ignored; one with its own record is used
d = dict(old_file, **{"epl:2": {"level": 99, "why": "", "n": 12}})
E.save_json(E.CUTOFF_FILE, d)
ok("a thin league entry (12 quotes) is not used: still soccer's level", E.combo_cutoff("soccer", 2, EPL) == 0.90)
d["epl:2"] = {"level": 87, "why": "lowered: ...", "n": 45}
E.save_json(E.CUTOFF_FILE, d)
ok("a league with its own record uses its own level (Premier League 87%)", E.combo_cutoff("soccer", 2, EPL) == 0.87)
ok("...while La Liga, Serie A and a cross-league soccer combo keep soccer's 90%",
   E.combo_cutoff("soccer", 2, LIGA) == 0.90 and E.combo_cutoff("soccer", 2, SERIEA) == 0.90
   and E.combo_cutoff("soccer", 2, [EPL[0], LIGA[0]]) == 0.90)
ok("...and other sports are untouched", all(same_cut(c, n, l) for c, l in SHAPES if c != "soccer" for n in (2, 3, 5, 8)))
d["all:2"] = {"level": 93, "why": "", "n": 300}
E.save_json(E.CUTOFF_FILE, d)
ok("a sport with no cut-off of its own never borrows everyone's below 95% (everyone's 93% -> NFL/AHL pairs 95%)",
   E.combo_cutoff("nfl", 2, ["KXNFLGAME-1-A"] * 2) == 0.95 and E.combo_cutoff("ahl", 2, AHL) == 0.95)
d["all:2"] = {"level": 98, "why": "raised: ...", "n": 300}
E.save_json(E.CUTOFF_FILE, d)
ok("...but borrows it upward (everyone's raised to 98% -> NFL pairs 98%)", E.combo_cutoff("nfl", 2, ["KXNFLGAME-1-A"] * 2) == 0.98)
d["all:2"] = {"level": 93, "why": "", "n": 300}
E.save_json(E.CUTOFF_FILE, d)
ok("...but a sport with its own keeps it (NBA 92%), and a league with its own keeps that (EPL 87%)",
   E.combo_cutoff("nba", 2, NBA) == 0.92 and E.combo_cutoff("soccer", 2, EPL) == 0.87)
d["all:2"] = {"level": 93, "why": "", "n": 12}
E.save_json(E.CUTOFF_FILE, d)
ok("everyone's level isn't borrowed while it's thin", E.combo_cutoff("nfl", 2, ["KXNFLGAME-1-A"] * 2) == 0.95)
s = {r["group"] for r in E.cutoff_summary()}
ok("Settings lists sports and leagues with their own levels, not thin ones",
   {"soccer:2", "nba:2", "epl:2", "nfl:5-7"} <= s and "all:2" not in s)


# ---- 3. the weekly adjustment: sports move exactly as before; leagues learn on their own
def quote(sport, legs, pct, won, ts=None):
    E.store_x("insert into quotes(ts, source, sport, n, legs, stake, pays, fair, kalshi, pct, hours) values(?,?,?,?,?,?,?,?,?,?,?)",
              (ts or now - 5 * 86400, "shadow", sport, len(legs), json.dumps([[t, .5, .5] for t in legs]), 5.0,
               20.0, 20.0, 19.0, pct, 3.0))
    E.store_x("update quotes set outcome=? where rowid=last_insert_rowid()", ("won" if won else "lost",))


for i in range(45):                    # EPL pairs priced just over 90%: they keep losing (worth far under cost)
    quote("soccer", [f"KXEPLGAME-26NOV{10 + i % 9:02d}A{i:03d}-A", f"KXEPLGAME-26NOV{10 + i % 9:02d}B{i:03d}-B"], 0.92, i % 9 == 0)
for i in range(60):                    # La Liga pairs at the same price win often: soccer as a whole is fine
    quote("soccer", [f"KXLALIGAGAME-26NOV{10 + i % 9:02d}A{i:03d}-A", f"KXLALIGAGAME-26NOV{10 + i % 9:02d}B{i:03d}-B"], 0.92, i % 2 == 0)
for i in range(5):                     # a few Serie A pairs (thin)
    quote("soccer", [f"KXSERIEAGAME-26NOV{10 + i:02d}A{i:03d}-A", f"KXSERIEAGAME-26NOV{10 + i:02d}B{i:03d}-B"], 0.91, i % 2 == 0)
for i in range(30):                    # NBA pairs just under 92% that would have done well
    quote("nba", [f"KXNBAGAME-26NOV{10 + i % 9:02d}A{i:03d}-A", f"KXNBAGAME-26NOV{10 + i % 9:02d}B{i:03d}-B"], 0.90, i % 3 != 0)
for i in range(6):                     # a cross-sport combo (NBA + NHL): NHL pairs have no cut-off of their own yet
    quote("nba,nhl", [f"KXNBAGAME-26NOV11C{i:03d}-A", f"KXNHLGAME-26NOV11C{i:03d}-B"], 0.95, False)

E.save_json(E.CUTOFF_FILE, old_file)
O["CUTOFF_FILE"] = os.path.join(E.HERE, "old_cut.json")
E.save_json(O["CUTOFF_FILE"], old_file)
old_moved = O["adjust_cutoffs"](force=True)
new_moved = E.adjust_cutoffs(force=True)
old_d, new_d = E.load_json(O["CUTOFF_FILE"], {}), E.load_json(E.CUTOFF_FILE, {})
strip = lambda e: {k: v for k, v in e.items() if k != "at"}
had = [k for k in old_file if not k.startswith("_")]
ok("weekly adjustment: every sport already in the file ends exactly where the old code puts it",
   all(strip(old_d[k]) == strip(new_d.get(k, {})) for k in had))
ok("weekly adjustment: the old moves are all still made", set(old_moved) <= set(new_moved))
ok("nothing in the old file is lost (NFL 5-7 legs, NHL 3-4 still there)", new_d.get("nfl:5-7") == old_file["nfl:5-7"]
   and new_d.get("nhl:3-4") == old_file["nhl:3-4"])
ok("soccer pairs as a whole didn't move (90%), as before", new_d["soccer:2"]["level"] == old_d["soccer:2"]["level"] == 90)
ok("the Premier League learned on its own: its losing pairs raised its bar from soccer's 90% to 93%",
   new_d["epl:2"]["level"] == 93 and "raised" in new_d["epl:2"]["why"] and E.combo_cutoff("soccer", 2, EPL) == 0.93
   and any(m.startswith("epl:2 90% → 93%") for m in new_moved))
ok("La Liga (60 quotes) now has its own level, starting from soccer's", new_d["laliga:2"]["level"] == 90
   and E._cut_own(new_d["laliga:2"]) and E.combo_cutoff("soccer", 2, LIGA) == 0.90)
ok("Serie A (5 quotes) still uses soccer's level", not E._cut_own(new_d.get("seriea:2"))
   and E.combo_cutoff("soccer", 2, SERIEA) == E.combo_cutoff("soccer", 2) == 0.90)
ok("everyone's group is tracked (146 quotes in pairs)", new_d["all:2"]["n"] == 146)
ok("thin leagues and sports already in the file match the old code's answer after the adjustment",
   all(E.combo_cutoff(c, n, l) == O["combo_cutoff"](c, n) for c, l in SHAPES
       if (c, l) not in (("soccer", EPL),) and c in ("soccer", "nba") for n in (2, 3, 5)))
ok("a sport new to the file (NHL pairs, 6 quotes) borrows everyone's only upward: 95%, not everyone's 92%",
   new_d["all:2"]["level"] == 92 and new_d["nhl:2"]["level"] == 95 and E.combo_cutoff("nhl", 2, NHL * 2) == 0.95)
ok("...and that borrowed level is marked borrowed, not saved as NHL's own", new_d["nhl:2"].get("borrowed") is True
   and not E._cut_own(new_d["nhl:2"]))
ok("Settings doesn't show the borrowed marker", all("borrowed" not in r for r in E.cutoff_summary()))
ok("Settings lists the leagues with their own record", {"epl:2", "laliga:2"} <= {r["group"] for r in E.cutoff_summary()}
   and "seriea:2" not in {r["group"] for r in E.cutoff_summary()})
ok("not again until next week", E.adjust_cutoffs() == [])
# a second week: a thin league follows its sport when the sport moves, and doesn't freeze at an old level
nd = E.load_json(E.CUTOFF_FILE, {})
nd["soccer:2"]["level"] = 88
E.save_json(E.CUTOFF_FILE, nd)
ok("a thin league follows its sport's level when the sport moves (no frozen copy)", E.combo_cutoff("soccer", 2, SERIEA) == 0.88
   and E.combo_cutoff("soccer", 2, EPL) == 0.93)

# a borrowed sport level follows everyone's live (upward only) and is never frozen; with its own 30+ quotes
# it becomes the sport's own, and only then can its own record take it down (to the 85% floor)
nd = E.load_json(E.CUTOFF_FILE, {})
nd["all:2"] = {"level": 99, "why": "raised: ...", "n": 300}
E.save_json(E.CUTOFF_FILE, nd)
ok("a borrowed sport (NHL pairs) follows everyone's when it rises (99%), no frozen copy", E.combo_cutoff("nhl", 2, NHL * 2) == 0.99)
nd["all:2"] = {"level": 85, "why": "lowered: ...", "n": 300}
E.save_json(E.CUTOFF_FILE, nd)
ok("...and stays at 95% when everyone's drops to the 85% floor", E.combo_cutoff("nhl", 2, NHL * 2) == 0.95)
nd["_at"] = 0
E.save_json(E.CUTOFF_FILE, nd)
E.adjust_cutoffs(force=True)
nd = E.load_json(E.CUTOFF_FILE, {})
ok("a second weekly pass keeps it borrowed at 95% (not everyone's 85%)", nd["nhl:2"]["level"] == 95 and nd["nhl:2"].get("borrowed"))
for i in range(40):                    # NHL pairs of its own, just under 95%, that would have done well
    quote("nhl", [f"KXNHLGAME-26NOV{10 + i % 9:02d}H{i:03d}-A", f"KXNHLGAME-26NOV{10 + i % 9:02d}I{i:03d}-B"], 0.93, i % 3 != 0)
E.adjust_cutoffs(force=True)
nd = E.load_json(E.CUTOFF_FILE, {})
ok(f"with 30+ quotes of its own, NHL learns from 95% and its own record can lower it ({nd['nhl:2']['level']:.0f}%)",
   nd["nhl:2"]["level"] < 95 and "lowered" in nd["nhl:2"]["why"] and not nd["nhl:2"].get("borrowed")
   and E.combo_cutoff("nhl", 2, NHL * 2) == nd["nhl:2"]["level"] / 100)
E.store_x("delete from quotes where sport='nhl'")
nd["nhl:2"] = {"level": 95, "why": "", "n": 3, "borrowed": True}
nd["_at"] = 0
E.save_json(E.CUTOFF_FILE, nd)
for i in range(31):                    # 31 quotes of its own, all well over the bar: no move, but now its own record
    quote("nhl", [f"KXNHLGAME-26NOV{10 + i % 9:02d}J{i:03d}-A", f"KXNHLGAME-26NOV{10 + i % 9:02d}K{i:03d}-B"], 1.2, True)
E.adjust_cutoffs(force=True)
nd = E.load_json(E.CUTOFF_FILE, {})
ok("at 30+ quotes without a move, the sport keeps 95% as its own starting level (no longer borrowed)",
   nd["nhl:2"]["level"] == 95 and "borrowed" not in nd["nhl:2"] and E._cut_own(nd["nhl:2"]))

# ---- 4. calibration: per league, borrowing soccer's nudge when short on games
def close(sport, ticker, fair, won):
    E.store_x("insert or replace into closes values(?,?,?,?,?,?,?,?)", (ticker, sport, ticker.split("-")[0] + "-" + ticker.split("-")[1],
                                                                         fair, fair, now - 86400, now - 86400, "yes" if won else "no"))


E._close_table()
for i in range(400):                   # EPL favorites (60-70%) win only half the time
    close("soccer", f"KXEPLGAME-26OCT{i % 28 + 1:02d}F{i:04d}-A", 0.65, i % 2 == 0)
for i in range(300):                   # La Liga favorites win as the books said
    close("soccer", f"KXLALIGAGAME-26OCT{i % 28 + 1:02d}F{i:04d}-A", 0.65, i % 100 < 65)
for i in range(500):                   # NBA: favorites win a bit more than the books say
    close("nba", f"KXNBAGAME-26OCT{i % 28 + 1:02d}F{i:04d}-A", 0.75, i % 100 < 80)
fresh_calib()
sh = lambda n: n / (n + 300)
# everyone's record by band: 55-70% = EPL 400 (won 200) + La Liga 300 (won 195); 70-85% = NBA 500 (won 80%)
dev65 = (200 + 195) / 700 - 0.65
all65 = sh(700) * dev65
all75 = sh(500) * (0.80 - 0.75)
ok("a sport alone in its band is exactly as before (its own games aren't counted twice via everyone's)",
   all(E.calib_fair("soccer", f) == O["calib_fair"]("soccer", f) for f in (0.6, 0.69))
   and all(E.calib_fair("nba", f, NBA[0]) == E.calib_fair("nba", f) == O["calib_fair"]("nba", f) for f in (0.72, 0.8)))
ok("a sport with no games in a band borrows the others' nudge (soccer 72% favorites get NBA's)",
   abs(E.calib_fair("soccer", 0.72) - (0.72 + all75)) < 1e-9 and abs(E.calib_fair("nba", 0.6) - (0.6 + all65)) < 1e-9)
soc = O["calib_fair"]("soccer", 0.65)
ok("Serie A (no games of its own) gets exactly soccer's nudge",
   all(E.calib_fair("soccer", f, SERIEA[0]) == E.calib_fair("soccer", f) for f in FAIRS))
epl, liga = E.calib_fair("soccer", 0.65, EPL[0]), E.calib_fair("soccer", 0.65, LIGA[0])
ok(f"the Premier League's own record pulls its favorites lower than soccer's ({epl:.3f} < {soc:.3f})", epl < soc < 0.65)
ok(f"La Liga's record pulls its favorites back toward the books ({liga:.3f} > {soc:.3f})", soc < liga <= 0.65)
want = soc + sh(400) * ((0.5 - 0.65) - (soc - 0.65))
ok("the league moves from soccer's nudge by n/(n+300) of the gap (same shrink as before)", abs(epl - want) < 1e-9)
ok("a sport with no games of its own (NHL, AHL) gets exactly everyone's nudge (league -> sport -> everyone)",
   abs(E.calib_fair("nhl", 0.75, NHL[0]) - (0.75 + all75)) < 1e-9 and abs(E.calib_fair("ahl", 0.65, AHL[0]) - (0.65 + all65)) < 1e-9
   and E.calib_fair("nhl", 0.75, NHL[0]) > 0.75)
ok("a band nobody has games in still passes the books' chance straight through",
   all(E.calib_fair(c, f, l[0]) == f for c, l in SHAPES for f in (0.05, 0.2, 0.31, 0.44, 0.5, 0.52, 0.86, 0.95)))
for i in range(60):                    # a few NHL favorites (70-85%) that won only 70%: NHL now shares NBA's band
    close("nhl", f"KXNHLGAME-26OCT{i % 28 + 1:02d}F{i:04d}-A", 0.75, i % 10 < 7)
fresh_calib()
nhl = 0.75 + all75 + sh(60) * (-0.05 - all75)
ok(f"a sport short on data (NHL, 60 games) starts from the other sports' nudge and moves toward its own ({E.calib_fair('nhl', 0.75, NHL[0]):.4f})",
   abs(E.calib_fair("nhl", 0.75, NHL[0]) - nhl) < 1e-9)
nba = 0.75 + sh(60) * -0.05 + sh(500) * (0.05 - sh(60) * -0.05)
ok(f"a sport with plenty (NBA, 500) is ruled by its own record, barely moved by NHL's ({E.calib_fair('nba', 0.75):.4f})",
   abs(E.calib_fair("nba", 0.75) - nba) < 1e-9 and abs(E.calib_fair("nba", 0.75) - O["calib_fair"]("nba", 0.75)) < 0.01)

# ---- 5. the panel's pay index (its sport priorities) by league
E.store_x("delete from quotes")
for i in range(30):
    quote("nba", [f"KXNBAGAME-26NOV{10 + i % 9:02d}A{i:03d}-A"] * 2, 0.95, True, ts=now - 86400)
for i in range(12):
    quote("soccer", [f"KXEPLGAME-26NOV{10 + i % 9:02d}A{i:03d}-A"] * 2, 0.80, True, ts=now - 86400)
for i in range(4):
    quote("soccer", [f"KXLALIGAGAME-26NOV{10 + i % 9:02d}A{i:03d}-A"] * 2, 1.00, True, ts=now - 86400)
idx, oidx = E.sport_pay_index(), O["sport_pay_index"]()
ok("pay index: every sport's value is exactly as before", all(idx[k] == v for k, v in oidx.items()))
ok("pay index: the Premier League (12 quotes) has its own, La Liga (4) doesn't", "epl" in idx and "laliga" not in idx)
ok("a Premier League combo uses its league's index; La Liga uses soccer's; NBA its own",
   E.pay_index_of(idx, "soccer", EPL) == idx["epl"] and E.pay_index_of(idx, "soccer", LIGA) == idx["soccer"]
   and E.pay_index_of(idx, "nba", NBA) == idx["nba"] and E.pay_index_of(idx, "nfl", []) == 1.0)
E.store_x("delete from quotes where sport='soccer' and legs like '%KXEPL%'")
idx2, oidx2 = E.sport_pay_index(), O["sport_pay_index"]()
ok("no league with enough quotes: identical to before", idx2 == oidx2)
ok("the panel's tie-break uses the league's index", "pay_index_of(idx, code, c[\"legs\"])" in open("wahome/engine.py").read())
