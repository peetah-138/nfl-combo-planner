# CHECK: group=engine
# Issue #345: mkt_learn's held-out check. The books' weight must also beat Kalshi's mid on the newest 30% of the
# league's settled markets BY GAME DATE; it can only take a weight away, never add or raise one.
import os, time, tempfile, shutil, importlib.util, random
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
TMP = tempfile.mkdtemp()
E.store_open(os.path.join(TMP, "h.db"))
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
now = time.time()
E._mkt_table()


def load(truth, n=2500, ids=None, kicks=None):
    """truth(i, mid, fb) -> chance of yes. Row i's game is the i-th oldest; `kicks(i, t)` may override its kick (None = no kick, the log time is used)."""
    E.store_x("delete from mkt_fair")
    E.MKT_W.update(at=0, w={})
    rng = random.Random(11)
    rows = []
    for i in range(n):
        fb = rng.uniform(0.3, 0.7)
        mid = min(max(fb + rng.choice((-0.08, 0.08)), 0.05), 0.95)
        y = rng.random() < truth(i, mid, fb)
        t = now - 40 * 86400 + i * 1300
        kick = kicks(i, t) if kicks else t
        rid = ids(i) if ids else f"side:T{i:05d}"
        rows.append((rid, (kick or t + 3600) - 3600, "nba", "nba", "win", "pre", f"T{i}", kick, mid, mid, fb, mid, 0.0, 0, 0, 0, 0, 2.0,
                     "yes" if y else "no"))
    E._mkt_insert(rows)
    return E.mkt_learn().get("nba|win|pre") or {}


# 1. the books are right the whole time: the weight is earned and the held-out check agrees
r = load(lambda i, mid, fb: fb)
ok("holdout: books right throughout -> weight earned", r["w"] > 0 and r["hold_gain"] > 0 and not r["vetoed"])
ok("holdout: the newest 30% (by count) was kept back", r["hold_n"] == int(2500 * 0.30))

# 2. the books were right in the oldest 70% and wrong in the newest 30%: in-sample it still passes the old bar, the
#    held-out check takes the weight away and says so
r = load(lambda i, mid, fb: fb if i < 1750 else mid)
ok("holdout: still clears the in-sample bar", r["gain"] >= E.MKT["gain"] and r["gain"] >= E.MKT["se"] * r["se"])
ok("holdout: ... but the newest games disagree, so the weight is 0 and vetoed", r["w"] == 0.0 and r["vetoed"] and r["hold_gain"] <= 0)
s = E.mkt_fair_summary()
ok("holdout: the summary says it was vetoed", s["groups"][0]["vetoed"] is True and s["groups"][0]["w"] == 0.0)

# 3. newest means game date, not insertion order or id order: the same story with the ids running backwards and the
#    still vetoes (ids sort the opposite way to game dates); and books right only in the newest games are NOT vetoed on a stale tail
r = load(lambda i, mid, fb: fb if i < 1750 else mid, ids=lambda i: f"side:T{99999 - i:05d}")
ok("holdout: ordered by game date, not by id", r["w"] == 0.0 and r["vetoed"])
r = load(lambda i, mid, fb: mid if i < 1750 else fb)
ok(f"holdout: books wrong in old games, right in the newest 30%: weight 0, not vetoed (got w={r['w']} vetoed={r['vetoed']})",
   r["w"] == 0.0 and not r["vetoed"])

# 3c. no kick: the log time orders the rows; the same story still vetoes
r = load(lambda i, mid, fb: fb if i < 1750 else mid, kicks=lambda i, t: None)
ok("holdout: kick=None falls back to the log time", r["w"] == 0.0 and r["vetoed"])
# 3d. every game has the same kick: the id breaks the tie (ids rise with i here, so the high ids are the newest)
k0 = now - 10 * 86400
r = load(lambda i, mid, fb: fb if i < 1750 else mid, kicks=lambda i, t: k0)
ok("holdout: tied kick is broken by id", r["w"] == 0.0 and r["vetoed"])
r = load(lambda i, mid, fb: fb if i < 1750 else mid, kicks=lambda i, t: k0, ids=lambda i: f"side:T{99999 - i:05d}")
ok(f"holdout: tied kick, ids reversed: the tail is a different set, so no veto (got w={r['w']} vetoed={r['vetoed']})",
   not r["vetoed"])
# 3e. a mix of rows with and without a kick
r = load(lambda i, mid, fb: fb if i < 1750 else mid, kicks=lambda i, t: None if i % 2 else t)
ok("holdout: mixed kick / no-kick rows are still ordered by date", r["w"] == 0.0 and r["vetoed"])

# 4. a slice smaller than hold_min earns nothing (a small holdout proves nothing). Not a bad-slice veto: the slice
#    itself would have passed (hold_gain > 0); the size alone refused it.
old_min = E.MKT["hold_min"]
E.MKT["hold_min"] = 10 ** 6
r = load(lambda i, mid, fb: fb)
ok("holdout: a slice smaller than hold_min earns nothing", r["w"] == 0.0 and r["hold_n"] < E.MKT["hold_min"])
ok("holdout: ... and that is the size rule, not a bad slice (hold_gain > 0)", r["hold_gain"] > 0)
E.MKT["hold_min"] = old_min

# 5. stricter only: across several noisy datasets the weight is 0 or exactly the in-sample best, never different
for seed, frac in enumerate((0.0, 0.2, 0.5, 1.0)):
    r = load(lambda i, mid, fb, f=frac: (mid + f * (fb - mid)) if i % 2 else fb)
    rows = [x for x in E._mkt_settled() if x["lg"] == "nba"]
    ys = {x["id"]: x["outcome"] == "yes" for x in rows}
    best = max(E.MKT["grid"][1:], key=lambda w: sum(E._ll(x["mid"], ys[x["id"]]) - E._ll(E.mkt_anchor(x["mid"], x["fair_book"], w), ys[x["id"]]) for x in rows))
    ok(f"holdout: stricter only (case {seed}): weight is 0 or the in-sample best", r["w"] in (0.0, best))
    old_earned = r["n"] >= E.MKT["min_n"] and r["gain"] >= E.MKT["gain"] and r["gain"] >= E.MKT["se"] * r["se"]
    ok(f"holdout: stricter only (case {seed}): old rule 0 implies new rule 0", old_earned or r["w"] == 0.0)

# 6. under min_n nothing is earned and nothing is called vetoed
r = load(lambda i, mid, fb: fb, n=150)
ok("holdout: under 200 markets the mid stays the fair, not 'vetoed'", r["w"] == 0.0 and not r["vetoed"])


# 7. the off switch (#497): `mkt_hold` is ON by default; off = the in-sample bar alone (the weight the old rule gave);
#    the veto is logged once, naming the group and why
import io, contextlib
ok("mkt_hold: a shared setting, ON by default", E.DEFAULTS["mkt_hold"] is True and "mkt_hold" in E.SHARED_KEYS)
E.CFG["mkt_hold"] = True
E.save_json(E.MAIN_SAVED, {"mkt_hold": True})
buf = io.StringIO()
E._ORDER_SHARED.told.clear()
with contextlib.redirect_stdout(buf):
    r = load(lambda i, mid, fb: fb if i < 1750 else mid)
ok("mkt_hold ON: the late-failing weight is vetoed (as before)", r["w"] == 0.0 and r["vetoed"])
line = [l for l in buf.getvalue().splitlines() if "held back" in l]
ok("mkt_hold ON: the veto is logged with its group and numbers", len(line) == 1 and "nba" in line[0].lower() and "win" in line[0]
   and "pre" in line[0] and "newest 750 of 2500" in line[0], line)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    E.mkt_learn()
ok("mkt_hold ON: the same veto is logged once, not on every pass", "held back" not in buf.getvalue(), buf.getvalue())
E.CFG["mkt_hold"] = False
E.save_json(E.MAIN_SAVED, {"mkt_hold": False})
r = load(lambda i, mid, fb: fb if i < 1750 else mid)
ok("mkt_hold OFF: the in-sample bar alone keeps its weight, nothing vetoed", r["w"] > 0 and not r["vetoed"], r)
r = load(lambda i, mid, fb: mid)
ok("mkt_hold OFF: a group that never earned the in-sample bar still gets 0 (off never adds a weight)", r["w"] == 0.0)
E.CFG["mkt_hold"] = True
E.save_json(E.MAIN_SAVED, {"mkt_hold": True})

shutil.rmtree(TMP, ignore_errors=True)
