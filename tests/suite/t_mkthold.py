# CHECK: group=engine
# Issue #345: mkt_learn's held-out check. The books' weight must also beat Kalshi's mid on the newest 30% of the
# league's settled markets BY GAME DATE; it can only take a weight away, never add or raise one.
import os, time, tempfile, importlib.util, random
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db"))
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
E._mkt_table()


def load(truth, n=2500, ids=None, kicks=None):
    """truth(i, mid, fb) -> chance of yes. Row i's game is the i-th oldest unless `kicks` says otherwise."""
    E.store_x("delete from mkt_fair")
    E.MKT_W.update(at=0, w={})
    rng = random.Random(11)
    rows = []
    for i in range(n):
        fb = rng.uniform(0.3, 0.7)
        mid = min(max(fb + rng.choice((-0.08, 0.08)), 0.05), 0.95)
        y = rng.random() < truth(i, mid, fb)
        kick = (kicks(i) if kicks else now - 40 * 86400 + i * 1300)
        rid = ids(i) if ids else f"side:T{i:05d}"
        rows.append((rid, kick - 3600, "nba", "nba", "win", "pre", f"T{i}", kick, mid, mid, fb, mid, 0.0, 0, 0, 0, 0, 2.0,
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
#    rows inserted newest-first still vetoes; and books right only in the newest games are NOT vetoed on a stale tail
r = load(lambda i, mid, fb: fb if i < 1750 else mid, ids=lambda i: f"side:T{99999 - i:05d}")
ok("holdout: ordered by game date, not by id", r["w"] == 0.0 and r["vetoed"])
r = load(lambda i, mid, fb: mid if i < 1750 else fb)
ok("holdout: books wrong in old games but right in the newest 30% is never a held-out veto", not r["vetoed"])

# 4. too few held-out markets: nothing is earned (a small holdout proves nothing)
old_min = E.MKT["hold_min"]
E.MKT["hold_min"] = 10 ** 6
r = load(lambda i, mid, fb: fb)
ok("holdout: a holdout smaller than hold_min earns nothing", r["w"] == 0.0 and r["vetoed"])
E.MKT["hold_min"] = old_min

# 5. stricter only: across several noisy datasets the weight is 0 or exactly the in-sample best, never different
for seed, frac in enumerate((0.0, 0.2, 0.5, 1.0)):
    r = load(lambda i, mid, fb, f=frac: (mid + f * (fb - mid)) if i % 2 else fb)
    rows = [x for x in E._mkt_settled() if x["lg"] == "nba"]
    ys = {x["id"]: x["outcome"] == "yes" for x in rows}
    best = max(E.MKT["grid"][1:], key=lambda w: sum(E._ll(x["mid"], ys[x["id"]]) - E._ll(E.mkt_anchor(x["mid"], x["fair_book"], w), ys[x["id"]]) for x in rows))
    ok(f"holdout: stricter only (case {seed}): weight is 0 or the in-sample best", r["w"] in (0.0, best))

# 6. under min_n nothing is earned and nothing is called vetoed
r = load(lambda i, mid, fb: fb, n=150)
ok("holdout: under 200 markets the mid stays the fair, not 'vetoed'", r["w"] == 0.0 and not r["vetoed"])
