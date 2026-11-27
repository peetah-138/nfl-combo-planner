"""Sport-neutral helpers for the offline "discovery" research (basketball now, NFL in parallel).  OFFLINE ONLY.

Nothing here touches the app, its keys or its history.  Needs numpy + pandas only (no scipy, no sklearn) so the
same file can be imported by every league's analysis.

What is in here, and why (plain English):
  * bh_fdr            Benjamini-Hochberg false-discovery-rate control.  Every scan must print how many hypotheses it
                      tested, because "5 of 2,000 look real" means something different from "5 of 12".
  * game_level_table  Rows inside one game are strongly correlated (the same game appears at 40 clock times), so every
                      test is run on ONE number per game (the mean residual in the segment) and the standard error is
                      across games.  That is the cluster-robust way to avoid fooling ourselves.
  * segment_scan      group the game-level numbers by a segment definition and test mean != 0, per segment.
  * season_stability  the same effect measured season by season (sign agreement, min/max, how many seasons are
                      testable), so a one-year fluke does not pass.
  * perm_importance   permutation importance on HELD-OUT rows; features that are constant within a game are shuffled
                      between games (not between rows), otherwise the shuffle breaks the game's own structure.
  * decay_slope       does the effect shrink season after season?  Weighted least-squares slope with its standard error.
  * logloss/brier/calibration  scoring of probabilities.
"""
import math

import numpy as np
import pandas as pd

EPS = 1e-6


# ---------------------------------------------------------------- scoring
def clip_p(p):
    return np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)


def logloss(y, p):
    y = np.asarray(y, dtype=float)
    p = clip_p(p)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y, p):
    y = np.asarray(y, dtype=float)
    return float(np.mean((np.asarray(p, dtype=float) - y) ** 2))


def calibration_table(y, p, bins=10):
    """Equal-width probability bins: mean predicted, observed rate, n.  Plus the expected calibration error."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    rows = []
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        rows.append({"bin": "%.1f-%.1f" % (b / bins, (b + 1) / bins), "n": int(m.sum()),
                     "mean_pred": float(p[m].mean()), "observed": float(y[m].mean())})
    t = pd.DataFrame(rows)
    ece = float((t.n * (t.mean_pred - t.observed).abs()).sum() / t.n.sum()) if len(t) else float("nan")
    return t, ece


# ---------------------------------------------------------------- multiple testing
def normal_two_sided_p(t):
    """Two-sided p from a z/t statistic using the normal tail (game counts here are in the hundreds or more)."""
    t = np.asarray(t, dtype=float)
    out = np.ones_like(t)
    ok = np.isfinite(t)
    out[ok] = [math.erfc(abs(x) / math.sqrt(2.0)) for x in t[ok]]
    return out


def bh_fdr(p, q=0.05):
    """Benjamini-Hochberg.  Returns (qvalues, reject_mask, n_tests).  NaN p-values are not counted as tests."""
    p = np.asarray(p, dtype=float)
    ok = np.isfinite(p)
    n = int(ok.sum())
    qv = np.full(p.shape, np.nan)
    rej = np.zeros(p.shape, dtype=bool)
    if n == 0:
        return qv, rej, 0
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order] * n / (np.arange(n) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    qs = np.empty(n)
    qs[order] = np.minimum(ranked, 1.0)
    qv[ok] = qs
    rej[ok] = qs <= q
    return qv, rej, n


# ---------------------------------------------------------------- game-clustered segment tests
def game_level_table(df, seg_cols, value_col, game_col="game_id", season_col="season"):
    """One row per (game, segment): the mean of value_col over that game's rows in the segment."""
    keys = [game_col, season_col] + list(seg_cols)
    g = df.groupby(keys, observed=True, sort=False)[value_col].agg(["mean", "size"]).reset_index()
    return g.rename(columns={"mean": "v", "size": "rows"})


def segment_scan(gl, seg_cols, season_col="season", min_games=100):
    """Test mean(v) != 0 per segment across games.  gl comes from game_level_table.  Returns a frame with the effect
    (same units as value_col), standard error across games, z, p, n_games."""
    grp = gl.groupby(list(seg_cols), observed=True, sort=False)["v"]
    out = grp.agg(effect="mean", sd="std", n_games="size").reset_index()
    out = out[out.n_games >= min_games].copy()
    out["se"] = out.sd / np.sqrt(out.n_games)
    out["z"] = out.effect / out.se.replace(0, np.nan)
    out["p"] = normal_two_sided_p(out.z.values)
    return out


def season_stability(gl, seg_cols, season_col="season", min_games_season=40):
    """Per segment: the effect in each season, how many seasons are testable, how many share the pooled sign."""
    s = gl.groupby(list(seg_cols) + [season_col], observed=True, sort=False)["v"].agg(["mean", "size"]).reset_index()
    s = s[s["size"] >= min_games_season]
    pooled = gl.groupby(list(seg_cols), observed=True, sort=False)["v"].mean().rename("pooled").reset_index()
    s = s.merge(pooled, on=list(seg_cols))
    s["same_sign"] = np.sign(s["mean"]) == np.sign(s["pooled"])
    agg = s.groupby(list(seg_cols), observed=True, sort=False).agg(
        seasons=("mean", "size"), same_sign=("same_sign", "sum"),
        min_eff=("mean", "min"), max_eff=("mean", "max")).reset_index()
    return agg, s


# ---------------------------------------------------------------- permutation importance
def perm_importance(predict, X, y, features, game_ids=None, game_const=(), repeats=3, seed=0, loss=logloss):
    """Increase in held-out loss when one feature is shuffled.  predict(X) -> probabilities.
    Features in game_const hold one value per game: they are shuffled between games, not rows."""
    rng = np.random.default_rng(seed)
    base = loss(y, predict(X))
    res = {}
    gids = None if game_ids is None else np.asarray(game_ids)
    if gids is not None:
        ug, first = np.unique(gids, return_index=True)
        inv = np.searchsorted(ug, gids)
    for f in features:
        deltas = []
        for _ in range(repeats):
            Xp = X.copy()
            if gids is not None and f in game_const:
                vals = X[f].values[first]
                Xp[f] = vals[rng.permutation(len(ug))][inv]
            else:
                Xp[f] = X[f].values[rng.permutation(len(X))]
            deltas.append(loss(y, predict(Xp)) - base)
        res[f] = float(np.mean(deltas))
    return base, res


# ---------------------------------------------------------------- decay
def decay_slope(seasons, effects, ses):
    """Weighted least-squares slope of effect on season (per season), with its standard error.  Returns
    (slope, se, z).  Needs 3+ seasons.  A negative slope on a positive effect (or the reverse) is decay."""
    x = np.asarray(seasons, dtype=float)
    yv = np.asarray(effects, dtype=float)
    se = np.asarray(ses, dtype=float)
    ok = np.isfinite(yv) & np.isfinite(se) & (se > 0)
    if ok.sum() < 3:
        return float("nan"), float("nan"), float("nan")
    x, yv, w = x[ok], yv[ok], 1.0 / se[ok] ** 2
    xm = np.sum(w * x) / np.sum(w)
    sxx = np.sum(w * (x - xm) ** 2)
    slope = np.sum(w * (x - xm) * (yv - np.sum(w * yv) / np.sum(w))) / sxx
    sl_se = math.sqrt(1.0 / sxx)
    return float(slope), float(sl_se), float(slope / sl_se)


def md_table(df, floatfmt="%.3f"):
    """Small markdown table writer (no tabulate dependency)."""
    if df is None or len(df) == 0:
        return "_none_\n"
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, (float, np.floating)):
                cells.append("" if not np.isfinite(v) else floatfmt % v)
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"
