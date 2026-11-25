# CHECK: group=engine
# Offline research helpers (tools/research/discovery_common.py): on SYNTHETIC data with a planted effect, the game-clustered
# segment scan with Benjamini-Hochberg control finds the planted segment, keeps null segments out, the season-stability and
# decay helpers behave, and permutation importance ranks the planted feature first. No app code, no network, no real data.
# Needs numpy + pandas (CI installs them from tests/requirements-ci.txt). On a Mac without them it prints a loud SKIP (still a PASS
# line so the list stays green) unless CI is set, where a missing import is a FAIL.
import os, sys, importlib.util

ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
try:
    import numpy as np, pandas as pd
except ImportError as e:
    if os.environ.get("CI"):
        ok("numpy/pandas import in CI (%s)" % e, False)
    else:
        print("SKIP numpy/pandas missing; install with: pip install numpy pandas (the CI job does)")
        ok("synthetic discovery test skipped locally (numpy/pandas not installed)", True)
    sys.exit(0)

repo = os.environ.get("REPO") or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
spec = importlib.util.spec_from_file_location("dc", os.path.join(repo, "tools", "research", "discovery_common.py"))
dc = importlib.util.module_from_spec(spec); spec.loader.exec_module(dc)

rng = np.random.default_rng(12345)
SEASONS = [2022, 2023, 2024, 2025, 2026]
GAMES_PER_SEASON = 700
ROWS = 12                       # rows (snapshots) per game, strongly correlated through a game effect
NULL_SEGS = ["null%02d" % i for i in range(40)]
PLANTED = 3.0                   # points of effect in the planted segment

recs = []
gid = 0
for s in SEASONS:
    for _ in range(GAMES_PER_SEASON):
        gid += 1
        ge = rng.normal(0, 8)                                   # game-level noise shared by all rows of the game
        in_planted = rng.random() < 0.35
        member = {nm: rng.random() < 0.3 for nm in NULL_SEGS}
        for r in range(ROWS):
            v = ge + rng.normal(0, 10) + (PLANTED if in_planted else 0.0)
            recs.append((gid, s, v, in_planted, *[member[nm] for nm in NULL_SEGS]))
df = pd.DataFrame(recs, columns=["game_id", "season", "val", "planted"] + NULL_SEGS)

parts = []
for nm in ["planted"] + NULL_SEGS:
    d = df.loc[df[nm] & (~df.planted if nm != "planted" else True), ["game_id", "season", "val"]]   # null cells exclude the planted games
    g = d.groupby(["game_id", "season"]).val.mean().reset_index().rename(columns={"val": "v"})
    g["seg"] = nm
    parts.append(g)
gl = pd.concat(parts, ignore_index=True)

res = dc.segment_scan(gl, ["seg"], min_games=100)
q, rej, n = dc.bh_fdr(res.p.values, 0.05)
res["q"], res["rej"] = q, rej
ok("hypothesis count is returned (%d tests)" % n, n == 41)
pl = res[res.seg == "planted"].iloc[0]
ok("planted effect is found (effect %.2f, q %.2g)" % (pl.effect, pl.q), bool(pl.rej) and abs(pl.effect - PLANTED) < 0.8)
nulls = res[res.seg != "planted"]
ok("null segments stay out (%d of 40 rejected)" % int(nulls.rej.sum()), int(nulls.rej.sum()) <= 1)

stab, per = dc.season_stability(gl, ["seg"], min_games_season=40)
sp = stab[stab.seg == "planted"].iloc[0]
ok("planted effect has the same sign in all 5 seasons", sp.seasons == 5 and sp.same_sign == 5)

# a game-level standard error is wider than the naive row-level one, because rows share a game effect
d = df[df.planted]
naive = d.val.std() / np.sqrt(len(d))
ok("game-clustered SE is larger than naive row SE (%.3f vs %.3f)" % (pl.se, naive), pl.se > 1.5 * naive)

# Benjamini-Hochberg on a known set: p = [0.001, 0.01, 0.02, 0.04, 0.5, 0.9] -> q = [0.006, 0.03, 0.04, 0.06, 0.6, 0.9]
qv, rj, nn = dc.bh_fdr(np.array([0.001, 0.01, 0.02, 0.04, 0.5, 0.9]), 0.05)
ok("BH known example", nn == 6 and list(rj) == [True, True, True, False, False, False] and np.allclose(qv, [0.006, 0.03, 0.04, 0.06, 0.6, 0.9]))
qv2, rj2, n2 = dc.bh_fdr(np.array([0.3, np.nan, 0.01]), 0.05)
ok("BH ignores NaN p-values and does not count them", n2 == 2 and rj2[2] and not rj2[1])

# decay: an effect that falls 1 point per season is detected; a flat one is not
yrs = np.array(SEASONS, dtype=float)
sl, se, z = dc.decay_slope(yrs, 6.0 - 1.0 * (yrs - 2022), np.full(5, 0.2))
ok("decay slope found (%.2f per season)" % sl, abs(sl + 1.0) < 1e-6 and z < -5)
sl2, se2, z2 = dc.decay_slope(yrs, np.full(5, 2.0), np.full(5, 0.5))
ok("flat effect has no decay slope", abs(sl2) < 1e-9)
ok("decay needs 3+ seasons", np.isnan(dc.decay_slope([2022, 2023], [1, 2], [0.1, 0.1])[0]))

# permutation importance: a model that only uses x1 ranks x1 first, a game-constant feature is shuffled between games
n_games = 400
gids = np.repeat(np.arange(n_games), 10)
x_const = np.repeat(rng.normal(size=n_games), 10)
x1 = rng.normal(size=len(gids)) + x_const
x2 = rng.normal(size=len(gids))
yv = (rng.random(len(gids)) < 1 / (1 + np.exp(-2 * x1))).astype(float)
X = pd.DataFrame({"x1": x1, "x2": x2, "xc": x_const})
pred = lambda M: 1 / (1 + np.exp(-2 * M["x1"].values))
base, imp = dc.perm_importance(pred, X, yv, ["x1", "x2", "xc"], game_ids=gids, game_const=("xc",), repeats=3, seed=1)
ok("permutation importance ranks the used feature first", imp["x1"] > 0.05 and abs(imp["x2"]) < 1e-9 and abs(imp["xc"]) < 1e-9)

# scoring helpers
y = np.array([1, 0, 1, 0, 1, 1, 0, 0], float)
ok("log loss of a perfect-ish forecast is small and of a coin flip is ln2",
   dc.logloss(y, np.where(y == 1, 0.99, 0.01)) < 0.02 and abs(dc.logloss(y, np.full(8, 0.5)) - np.log(2)) < 1e-9)
t, ece = dc.calibration_table(y, np.full(8, 0.5), bins=10)
ok("calibration table of a 0.5 forecast on a 50% base rate has ECE 0", abs(ece) < 1e-9 and int(t.n.sum()) == 8)
