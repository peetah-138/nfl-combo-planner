"""Basketball discovery run (OFFLINE RESEARCH ONLY).  See docs/BASKETBALL_DISCOVERY.md for the pre-registration.

    python tools/research/basketball_discovery.py [--out results.md] [--leagues nba,mbb]

Reads the built tables written by basketball_data.py (outside the repo), trains on earlier seasons and scores on later
held-out seasons (expanding window: train < Y, test = Y, for Y in TEST_YEARS), and writes AGGREGATE tables only.
Nothing here touches the app, its keys or its history.

Everything that decides "is it real" is fixed in the constants below and in the docs BEFORE the first run:
  * features are whitelists (BASE_FEATS / RICH_FEATS); an assert refuses any outcome column
  * the scan looks at HELD-OUT residuals of the BASELINE model only (so a segment asks "does it add anything beyond
    game state?"); the richer model is used for permutation importance only
  * scan = one Benjamini-Hochberg family per league and per question (win probability, totals); the pre-registered
    anecdotes are a second, separate family; every hypothesis count is printed
  * survivor = BH q < 0.05 AND |effect| >= MIN_EFFECT AND >= 4 testable held-out seasons with the same sign in at
    least 4 AND the same segment has the same sign with one-sided p < 0.05 in the OTHER league
"""
import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discovery_common as dc  # noqa: E402

BUILT = Path(os.environ.get("BBALL_BUILT", str(Path.home() / "dev/research/basketball/built")))
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
GEOM = {"nba": {"T": 2880.0, "plen": 720.0}, "mbb": {"T": 2400.0, "plen": 1200.0}}
OUTCOME_COLS = {"home_win", "home_margin", "final_total", "went_ot", "fouls", "dev", "y", "p", "game_id", "season"}
BASE_FEATS = ["margin", "tl", "mscaled", "pre_term", "zan", "poss", "tf_h", "tf_a", "bonus_h", "bonus_a", "pre_margin", "pre_total"]
RICH_EXTRA = ["neutral", "is_post", "rest_h", "rest_a", "b2b_h", "b2b_a", "run", "mchg5", "mchg10", "pace_pts", "pace_prior_h",
              "pace_prior_a", "ft_h", "ft_a", "crew_dev", "crew_fouls", "t"]
RICH_FEATS = BASE_FEATS + RICH_EXTRA
GAME_CONST = ("pre_margin", "pre_total", "neutral", "is_post", "rest_h", "rest_a", "b2b_h", "b2b_a", "pace_prior_h", "pace_prior_a",
              "crew_dev", "crew_fouls")
MIN_EFFECT_WP = 1.0       # win-probability points
MIN_EFFECT_TOT = 1.0      # total points
MIN_GAMES = 100
MIN_GAMES_SEASON = 40
Q = 0.05
HGB_PARAMS = dict(max_iter=120, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=3000, l2_regularization=5.0,
                  early_stopping=False, random_state=0)


def check_whitelist(feats):
    bad = OUTCOME_COLS & set(feats)
    assert not bad, "outcome columns in the feature list: %s" % sorted(bad)


# ------------------------------------------------------------------ data
def load(lg):
    g = pd.read_parquet(BUILT / f"{lg}_games.parquet")
    s = pd.read_parquet(BUILT / f"{lg}_snaps.parquet")
    T = GEOM[lg]["T"]
    s = s[s.pre_margin.notna()].copy()           # a game with no pre-game line is not usable (NBA 2019)
    s["y"] = s.home_win.astype(np.float32)
    s["mscaled"] = s.margin / np.sqrt(s.tl + 1.0)
    s["pre_term"] = s.pre_margin * s.tl / T
    s["zan"] = (s.margin + s.pre_term) / np.sqrt(s.tl / T)     # the analytic model's standardised lead, as a head start for the trees
    s["b2b_h"] = (s.rest_h == 1).astype(np.float32)
    s["b2b_a"] = (s.rest_a == 1).astype(np.float32)
    s["phase"] = np.minimum((4 * s.t / T).astype(int), 3)
    return g, s


# ------------------------------------------------------------------ win-probability models
def norm_cdf(z):
    from math import erf
    return 0.5 * (1.0 + np.vectorize(erf)(np.asarray(z) / np.sqrt(2.0)))


def analytic_p(df, sigma, T):
    frac = (df.tl.values / T)
    mu = df.margin.values + df.pre_margin.values * frac
    return np.clip(norm_cdf(mu / (sigma * np.sqrt(frac))), 1e-4, 1 - 1e-4)


def fit_sigma(tr, T):
    best = None
    sub = tr.iloc[:: max(1, len(tr) // 150000)]
    for sg in np.arange(8.0, 22.01, 0.5):
        ll = dc.logloss(sub.y.values, analytic_p(sub, sg, T))
        if best is None or ll < best[0]:
            best = (ll, sg)
    return best[1]


def fit_hgb(tr, feats):
    from sklearn.ensemble import HistGradientBoostingClassifier
    check_whitelist(feats)
    # training uses every second snapshot (120 s grid): rows inside a game are near duplicates, so this loses almost nothing
    tr = tr[(tr.t % 120) == 0]
    m = HistGradientBoostingClassifier(**HGB_PARAMS)
    m.fit(tr[feats].astype(np.float32), tr.y)
    return m


def predict(m, df, feats):
    check_whitelist(feats)
    return m.predict_proba(df[feats].astype(np.float32))[:, 1]


def game_cluster_diff(df, la, lb):
    """mean(la - lb) per game, then mean and SE across games."""
    d = pd.DataFrame({"g": df.game_id.values, "d": la - lb}).groupby("g").d.mean()
    return float(d.mean()), float(d.std() / np.sqrt(len(d))), len(d)


def point_loss(y, p):
    p = dc.clip_p(p)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def run_winprob(lg, s, log):
    T = GEOM[lg]["T"]
    rows, calib, imps = [], [], []
    scanned = []
    for Y in TEST_YEARS:
        tr, te = s[s.season < Y], s[s.season == Y].copy()
        if tr.season.nunique() < 1 or len(te) == 0:
            continue
        t0 = time.time()
        sig = fit_sigma(tr, T)
        te["p_an"] = analytic_p(te, sig, T)
        mb = fit_hgb(tr, BASE_FEATS)
        te["p_base"] = predict(mb, te, BASE_FEATS)
        mr = fit_hgb(tr, RICH_FEATS)
        te["p_rich"] = predict(mr, te, RICH_FEATS)
        y = te.y.values
        _, ece_b = dc.calibration_table(y, te.p_base.values)
        d_rb, se_rb, ng = game_cluster_diff(te, point_loss(y, te.p_rich.values), point_loss(y, te.p_base.values))
        d_ba, se_ba, _ = game_cluster_diff(te, point_loss(y, te.p_base.values), point_loss(y, te.p_an.values))
        rows.append({"season": Y, "games": te.game_id.nunique(), "sigma_pts": sig,
                     "ll_analytic": dc.logloss(y, te.p_an), "ll_base": dc.logloss(y, te.p_base), "ll_rich": dc.logloss(y, te.p_rich),
                     "brier_analytic": dc.brier(y, te.p_an), "brier_base": dc.brier(y, te.p_base), "brier_rich": dc.brier(y, te.p_rich),
                     "ece_base": ece_b, "base_minus_analytic_ll": d_ba, "se_ba": se_ba, "rich_minus_base_ll": d_rb, "se_rb": se_rb})
        ct, _ = dc.calibration_table(y, te.p_base.values)
        ct["season"] = Y
        calib.append(ct)
        # permutation importance of the RICH model on this held-out season (sampled games, game-level shuffles for game constants)
        gs = te.game_id.drop_duplicates().sample(min(1200, te.game_id.nunique()), random_state=1)
        sm = te[te.game_id.isin(gs)]
        Xs = sm[RICH_FEATS].astype(np.float32).reset_index(drop=True)
        base, res = dc.perm_importance(lambda X: mr.predict_proba(X)[:, 1], Xs, sm.y.values, RICH_FEATS,
                                       game_ids=sm.game_id.values, game_const=GAME_CONST, repeats=2, seed=Y)
        for f, v in res.items():
            imps.append({"season": Y, "feature": f, "delta_logloss": v})
        scanned.append(te[["game_id", "season", "t", "tl", "phase", "y", "p_base", "margin", "poss", "run", "mchg5", "tf_h", "tf_a",
                           "bonus_h", "bonus_a", "ft_h", "ft_a", "rest_h", "rest_a", "neutral", "pre_margin", "pace_pts",
                           "pace_prior_h", "pace_prior_a", "pre_total", "home_pts", "away_pts"]])
        log("  %s %d: sigma=%.1f ll analytic %.4f base %.4f rich %.4f  (%.0fs)" % (lg, Y, sig, rows[-1]["ll_analytic"], rows[-1]["ll_base"],
                                                                                   rows[-1]["ll_rich"], time.time() - t0))
    per = pd.DataFrame(rows)
    imp = pd.DataFrame(imps)
    cal = pd.concat(calib)
    return per, cal, imp, pd.concat(scanned, ignore_index=True)


# ------------------------------------------------------------------ perspective views and the scan
def perspective(te, lg):
    """Stack a home view (sign +1) and an away view (sign -1) so 'own' means the team the effect is measured for.
    A segment is only defined where it applies to ONE side (the other side is excluded), so the two views of a game
    never cancel each other.  Mirror segments (opp_X) are not separate hypotheses: they are exactly the negative."""
    T = GEOM[lg]["T"]
    out = []
    for sign in (1, -1):
        h = sign == 1
        v = pd.DataFrame({
            "game_id": te.game_id.values, "season": te.season.values, "t": te.t.values, "phase": te.phase.values,
            "sign": sign, "val": 100.0 * sign * (te.y.values - te.p_base.values),
            "own_margin": sign * te.margin.values, "own_run": sign * te.run.values, "own_mchg5": sign * te.mchg5.values,
            "own_poss": (sign * te.poss.values == 1),
            "own_bonus": (te.bonus_h if h else te.bonus_a).values == 1, "opp_bonus": (te.bonus_a if h else te.bonus_h).values == 1,
            "own_ft": (te.ft_h if h else te.ft_a).values, "opp_ft": (te.ft_a if h else te.ft_h).values,
            "own_rest": (te.rest_h if h else te.rest_a).values, "opp_rest": (te.rest_a if h else te.rest_h).values,
            "own_pre": sign * te.pre_margin.values, "neutral": te.neutral.values == 1,
            "pace_ratio": te.pace_pts.values / (0.5 * (te.pace_prior_h.values + te.pace_prior_a.values) / (T / 60.0)),
            "own_pts": (te.home_pts if h else te.away_pts).values, "opp_pts": (te.away_pts if h else te.home_pts).values,
            "tl": te.tl.values})
        out.append(v)
    return pd.concat(out, ignore_index=True)


def win_segments(v, lg):
    """name -> boolean mask over the stacked view.  Same names in both leagues (that is what replication matches on)."""
    seg = {}
    base = {
        "b2b_team_only": (v.own_rest == 1) & (v.opp_rest != 1),
        "own_run10": v.own_run >= 10,
        "own_gain8_last5": v.own_mchg5 >= 8,
        "own_in_bonus_only": v.own_bonus & ~v.opp_bonus,
        "own_foul_trouble_only": (v.own_ft >= 1) & (v.opp_ft == 0),
        "own_has_ball": v.own_poss,
        "underdog_fast_game": (v.own_pre <= -3) & (v.pace_ratio > 1.08),
        "underdog_slow_game": (v.own_pre <= -3) & (v.pace_ratio < 0.92),
    }
    for nm, m in base.items():
        seg[nm + "|all"] = m
        for ph in range(4):
            seg[nm + "|ph%d" % ph] = m & (v.phase == ph)
    home = (v.sign == 1) & ~v.neutral
    seg["home_team|all"] = home
    for ph in range(4):
        seg["home_team|ph%d" % ph] = home & (v.phase == ph)
    # lead buckets: diagnostics of the baseline's calibration (home view only), not trend claims
    edges = [-1e9, -15, -8, -3, 3, 8, 15, 1e9]
    names = ["trail15+", "trail8-15", "trail3-8", "within3", "lead3-8", "lead8-15", "lead15+"]
    hv = v.sign == 1
    for i, nm in enumerate(names):
        m = hv & (v.own_margin > edges[i]) & (v.own_margin <= edges[i + 1])
        for ph in range(4):
            seg["lead_%s|ph%d" % (nm, ph)] = m & (v.phase == ph)
    return seg


def game_level(v, masks, valcol="val"):
    parts = []
    for nm, m in masks.items():
        if m.sum() == 0:
            continue
        d = v.loc[m, ["game_id", "season", valcol]]
        gl = d.groupby(["game_id", "season"], sort=False)[valcol].mean().reset_index().rename(columns={valcol: "v"})
        gl["seg"] = nm
        parts.append(gl)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["game_id", "season", "v", "seg"])


def scan(gl, min_effect, label):
    """Run the segment scan on a game-level table and apply the survivor rules (replication is added later)."""
    res = dc.segment_scan(gl, ["seg"], min_games=MIN_GAMES)
    q, rej, n = dc.bh_fdr(res.p.values, Q)
    res["q"] = q
    res["bh_reject"] = rej
    stab, per = dc.season_stability(gl, ["seg"], min_games_season=MIN_GAMES_SEASON)
    res = res.merge(stab, on="seg", how="left")
    res["stable"] = (res.seasons >= 4) & (res.same_sign >= 4)
    res["material"] = res.effect.abs() >= min_effect
    res["pre_repl"] = res.bh_reject & res.stable & res.material
    return res, n, per


def add_replication(a, b):
    """Replication = the same segment, other league, same sign, one-sided p < 0.05 (pre-specified, not a second BH pass)."""
    m = a[["seg", "effect", "z"]].merge(b[["seg", "effect", "z"]], on="seg", how="left", suffixes=("", "_other"))
    one_sided = m.z_other.fillna(0) * np.sign(m.effect)
    a = a.copy()
    a["other_effect"] = m.effect_other.values
    a["other_z"] = m.z_other.values
    a["replicates"] = ((np.sign(m.effect_other) == np.sign(m.effect)) & (one_sided > 1.645)).values
    a["survivor"] = a.pre_repl & a.replicates
    return a


# ------------------------------------------------------------------ pre-registered anecdotes (win probability)
def anecdote_masks(v, lg):
    """Exact operational definitions, fixed in the docs before the first run.  Each is evaluated at ONE snapshot per game
    (so a game contributes one number) from the perspective of the team named."""
    T = GEOM[lg]["T"]
    half, q3end, late5, late2 = T / 2, 0.75 * T, T - 300, T - 120
    q1end = GEOM[lg]["plen"] if lg == "nba" else 600.0
    m = {}
    mx = np.maximum(v.own_pts, v.opp_pts)
    reached = (mx >= 20)
    # first to 20 points: at the first snapshot where either side has 20, the side with 20+ while the other has fewer
    key = pd.Series(v.game_id.values * 2 + (v.sign.values == 1), index=v.index)
    order = np.lexsort((v.t.values, key.values))
    r = reached.values[order]
    k = key.values[order]
    c = pd.Series(r.astype(int)).groupby(k).cumsum().values
    first = np.zeros(len(v), bool)
    first[order] = r & (c == 1)
    m["A1_first_to_20_leader"] = first & (v.own_pts >= 20) & (v.opp_pts < 20)
    at = lambda sec: (v.t == sec)  # noqa: E731
    m["A2_halftime_lead_1_to_6"] = at(half) & v.own_margin.between(1, 6)
    m["A3_halftime_trail_15plus"] = at(half) & (v.own_margin <= -15)
    m["A4_b2b_team_start_2nd_half"] = at(half) & (v.own_rest == 1) & (v.opp_rest >= 2)
    m["A5_rested3plus_vs_b2b_at_half"] = at(half) & (v.own_rest >= 3) & (v.opp_rest == 1)
    m["A6_gained6plus_last5_into_final_stretch"] = at(q3end) & (v.own_mchg5 >= 6)
    m["A7_foul_trouble_only_at_half"] = at(half) & (v.own_ft >= 1) & (v.opp_ft == 0)
    m["A8_in_bonus_close_last5"] = at(late5) & v.own_bonus & ~v.opp_bonus & (v.own_margin.abs() <= 5)
    m["A9_home_team_clutch_within3_last5"] = at(late5) & (v.sign == 1) & ~v.neutral & (v.own_margin.abs() <= 3)
    m["A10_run10_in_final_quarter"] = (v.t >= q3end) & (v.own_run >= 10)
    m["A11_lead12plus_at_half"] = at(half) & (v.own_margin >= 12)
    m["A12_ball_trailing_by_1_to_3_last2"] = at(late2) & v.own_poss & v.own_margin.between(-3, -1)
    m["A13_leads_after_first_period"] = at(q1end) & (v.own_margin >= 1)
    return m


def run_scan_wp(lg, te, log):
    v = perspective(te, lg)
    seg = win_segments(v, lg)
    gl = game_level(v, seg)
    res, n, per = scan(gl, MIN_EFFECT_WP, "scan")
    an = anecdote_masks(v, lg)
    glA = game_level(v, an)
    resA, nA, perA = scan(glA, MIN_EFFECT_WP, "anecdotes")
    log("  %s win-prob scan: %d hypotheses tested (BH family 1); anecdotes: %d (family 2)" % (lg, n, nA))
    return res, n, per, resA, nA, perA


# ------------------------------------------------------------------ totals
def run_totals(lg, s, g, log):
    T = GEOM[lg]["T"]
    s = s[s.pre_total.notna()].copy()
    rows, resid_parts, sd_rows = [], [], []
    for Y in TEST_YEARS:
        tr, te = s[(s.season < Y)], s[s.season == Y].copy()
        if len(tr) == 0 or len(te) == 0:
            continue
        for d in (tr, te):
            frac = d.tl.values / T
            d["X0"] = d.pre_total.values * frac
            d["X1"] = d.pace_pts.values * d.tl.values / 60.0
            d["X2"] = np.abs(d.margin.values) * frac
            d["X3"] = frac
            d["X4"] = frac * d.is_post.values
            d["rem"] = d.final_total.values - d.total_pts.values
        cols = ["X0", "X1", "X2", "X3", "X4"]
        trs = tr[(tr.t % 120) == 0]
        beta, *_ = np.linalg.lstsq(trs[cols].values.astype(float), trs.rem.values.astype(float), rcond=None)
        te["pred_ols"] = te[cols].values.astype(float) @ beta
        te["res"] = te.rem - te.pred_ols
        te["res_anchor"] = te.rem - te.X0
        te["res_pace"] = te.rem - te.X1
        # GBM on the residual with the rich features: does anything beyond the simple projection help out of sample?
        from sklearn.ensemble import HistGradientBoostingRegressor
        feats = [f for f in RICH_FEATS if f not in ("margin", "mscaled", "pre_term")] + ["total_pts"]
        check_whitelist(feats)
        trs = trs.assign(res=trs.rem.values - trs[cols].values.astype(float) @ beta)
        gb = HistGradientBoostingRegressor(max_iter=100, learning_rate=0.08, max_leaf_nodes=31, min_samples_leaf=400, l2_regularization=1.0,
                                           early_stopping=False, random_state=0)
        gb.fit(trs[feats].astype(np.float32), trs.res)
        te["pred_gb"] = gb.predict(te[feats].astype(np.float32))
        te["res_gb"] = te.res - te.pred_gb
        for ph in range(4):
            d = te[te.phase == ph]
            rows.append({"season": Y, "phase": ph, "n_games": d.game_id.nunique(),
                         "rmse_anchor": float(np.sqrt((d.res_anchor ** 2).mean())), "rmse_pace": float(np.sqrt((d.res_pace ** 2).mean())),
                         "rmse_ols": float(np.sqrt((d.res ** 2).mean())), "rmse_gbm": float(np.sqrt((d.res_gb ** 2).mean())),
                         "w_anchor": beta[0], "w_pace": beta[1],
                         "ot_bump": float(d.res[d.went_ot == 1].mean() - d.res[d.went_ot == 0].mean()) if (d.went_ot == 1).any() else np.nan})
        keep = te[["game_id", "season", "t", "tl", "phase", "res", "res_gb", "margin", "total_pts", "pace_pts", "pre_total", "pace_prior_h",
                   "pace_prior_a", "rest_h", "rest_a", "neutral", "is_post", "crew_dev", "crew_fouls", "went_ot", "ft_h", "ft_a",
                   "tf_h", "tf_a"]].copy()
        resid_parts.append(keep)
        log("  %s totals %d: rmse anchor %.2f pace %.2f ols %.2f gbm %.2f (progress 1/2)" % (
            lg, Y, rows[-4 + 1]["rmse_anchor"], rows[-4 + 1]["rmse_pace"], rows[-4 + 1]["rmse_ols"], rows[-4 + 1]["rmse_gbm"]))
    per = pd.DataFrame(rows)
    R = pd.concat(resid_parts, ignore_index=True)
    # distribution of the final total about the pre-game total (the issue #482 width question), per season
    gg = g[g.pre_total.notna() & g.season.isin(TEST_YEARS)].copy()
    gg["dev"] = gg.final_total - gg.pre_total
    dist = gg.groupby("season").dev.agg(n="size", mean="mean", sd="std", skew="skew", kurt=lambda x: x.kurt()).reset_index()
    # same on regulation-only games (no OT) so the OT bump is visible as its own term
    d2 = gg[gg.went_ot == 0].groupby("season").dev.agg(sd_noOT="std", mean_noOT="mean").reset_index()
    dist = dist.merge(d2, on="season")
    dist["pre_total_src"] = gg.groupby("season").pre_total_src.first().values
    return per, R, dist


def total_segments(R, T):
    pace_ratio = R.pace_pts / (R.pre_total / (T / 60.0))
    b2b_h, b2b_a = R.rest_h == 1, R.rest_a == 1
    base = {
        "b2b_either_team": b2b_h ^ b2b_a, "b2b_both": b2b_h & b2b_a, "rested3_both": (R.rest_h >= 3) & (R.rest_a >= 3),
        "neutral_site": R.neutral == 1, "postseason": R.is_post == 1,
        "crew_over_lean": R.crew_dev > 0.5, "crew_under_lean": R.crew_dev < -0.5,
        "crew_whistle_heavy": R.crew_fouls > 0.5, "crew_whistle_light": R.crew_fouls < -0.5,
        "fast_vs_prior": pace_ratio > 1.08, "slow_vs_prior": pace_ratio < 0.92,
        "foul_trouble_any": (R.ft_h + R.ft_a) >= 1,
        "heavy_team_fouls": (R.tf_h + R.tf_a) >= (8 if T > 2500 else 12),
    }
    seg = {}
    for nm, m in base.items():
        seg[nm + "|all"] = m
        for ph in range(4):
            seg[nm + "|ph%d" % ph] = m & (R.phase == ph)
    close, blow = R.margin.abs() <= 5, R.margin.abs() >= 20
    seg["close_game|ph3"] = close & (R.phase == 3)
    seg["blowout20|ph2"] = blow & (R.phase == 2)
    seg["blowout20|ph3"] = blow & (R.phase == 3)
    return seg


def totals_anecdotes(R, T, lg):
    half, q1end = T / 2, (720.0 if lg == "nba" else 600.0)
    pace_ratio = R.pace_pts / (R.pre_total / (T / 60.0))
    return {
        "T1_fast_first_period_over": (R.t == q1end) & (pace_ratio > 1.10),
        "T2_slow_first_period_under": (R.t == q1end) & (pace_ratio < 0.90),
        "T3_physical_first_half_late_points": (R.t == half) & ((R.tf_h + R.tf_a) >= (6 if lg == "nba" else 8)),
        "T4_back_to_back_either_at_half": (R.t == half) & ((R.rest_h == 1) ^ (R.rest_a == 1)),
        "T5_close_game_late_over": (R.t == T - 300) & (R.margin.abs() <= 5),
        "T6_blowout_slows_down": (R.t == half) & (R.margin.abs() >= 20),
    }


def run_scan_totals(lg, R, log):
    T = GEOM[lg]["T"]
    R = R.copy()
    R["val"] = R.res
    seg = total_segments(R, T)
    gl = game_level(R, seg)
    res, n, per = scan(gl, MIN_EFFECT_TOT, "totals scan")
    an = totals_anecdotes(R, T, lg)
    glA = game_level(R, an)
    resA, nA, perA = scan(glA, MIN_EFFECT_TOT, "totals anecdotes")
    log("  %s totals scan: %d hypotheses tested (BH family 3); totals anecdotes: %d (family 4)" % (lg, n, nA))
    return res, n, per, resA, nA, perA


# ------------------------------------------------------------------ decay tracker
def decay_table(per, res, top=12):
    """per: season-level means with counts (from dc.season_stability).  slope per season for the segments with the largest |z|."""
    out = []
    pick = res.sort_values("z", key=lambda x: -x.abs()).head(top).seg.tolist()
    for sgm in pick:
        d = per[per.seg == sgm]
        if len(d) < 3:
            continue
        eff = d["mean"].values
        out.append({"seg": sgm, "seasons": len(d), "first": float(eff[0]), "last": float(eff[-1])})
    return pd.DataFrame(out)


def season_effects(gl, segs):
    g = gl[gl.seg.isin(segs)].groupby(["seg", "season"]).v.agg(["mean", "std", "size"]).reset_index()
    g["se"] = g["std"] / np.sqrt(g["size"])
    rows = []
    for sgm, d in g.groupby("seg"):
        d = d[d["size"] >= MIN_GAMES_SEASON]
        sl, se, z = dc.decay_slope(d.season.values, d["mean"].values, d.se.values)
        rows.append({"seg": sgm, "seasons": len(d), "effect_by_season": " ".join("%.1f" % x for x in d["mean"].values),
                     "slope_per_season": sl, "slope_se": se, "slope_z": z})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ report
def fmt_scan(res, n, k=12):
    t = res.sort_values("p").head(k)[["seg", "n_games", "effect", "se", "q", "seasons", "same_sign"]].copy()
    return dc.md_table(t, "%.3f")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path.home() / "dev/research/basketball/results/first_run.md"))
    ap.add_argument("--leagues", default="nba,mbb")
    a = ap.parse_args()
    leagues = a.leagues.split(",")
    lines = []

    def log(x):
        print(x, flush=True)

    def w(x=""):
        lines.append(x)

    store = {}
    for lg in leagues:
        log("== %s: loading" % lg)
        g, s = load(lg)
        log("  snapshots %d, games %d, seasons %s" % (len(s), s.game_id.nunique(), sorted(s.season.unique())))
        per, cal, imp, te = run_winprob(lg, s, log)
        resW, nW, perW, resA, nA, perA = run_scan_wp(lg, te, log)
        tper, R, dist = run_totals(lg, s, g, log)
        resT, nT, perT, resTA, nTA, perTA = run_scan_totals(lg, R, log)
        store[lg] = dict(g=g, per=per, cal=cal, imp=imp, resW=resW, nW=nW, perW=perW, resA=resA, nA=nA, perA=perA,
                         tper=tper, dist=dist, resT=resT, nT=nT, perT=perT, resTA=resTA, nTA=nTA, perTA=perTA, te=te, R=R, s=s)
    if len(leagues) == 2:
        for k_res, k_per in (("resW", "perW"), ("resA", "perA"), ("resT", "perT"), ("resTA", "perTA")):
            a_, b_ = store["nba"][k_res], store["mbb"][k_res]
            store["nba"][k_res] = add_replication(a_, b_)
            store["mbb"][k_res] = add_replication(b_, a_)
    # ---- write the report (aggregate numbers only)
    w("# Basketball discovery: first run (aggregate results only)")
    w("")
    w("Held-out seasons: %s (train on all earlier seasons, expanding window). Hypothesis counts are printed per family." % TEST_YEARS)
    for lg in leagues:
        st = store[lg]
        g = st["g"]
        w("")
        w("## %s" % lg.upper())
        w("Games built: %d over seasons %d-%d; snapshots at 60 s steps of regulation." % (len(g), g.season.min(), g.season.max()))
        w("")
        w("### 1. Baseline win probability (state only) per held-out season")
        cols = ["season", "games", "sigma_pts", "ll_analytic", "ll_base", "ll_rich", "brier_analytic", "brier_base", "brier_rich", "ece_base"]
        w(dc.md_table(st["per"][cols], "%.4f"))
        w("Paired log-loss difference per game (negative = first is better), game-clustered SE:")
        w(dc.md_table(st["per"][["season", "base_minus_analytic_ll", "se_ba", "rich_minus_base_ll", "se_rb"]], "%.5f"))
        w("Baseline calibration (all held-out seasons pooled):")
        c = st["cal"].groupby("bin").apply(lambda d: pd.Series({"n": d.n.sum(), "mean_pred": np.average(d.mean_pred, weights=d.n),
                                                                "observed": np.average(d.observed, weights=d.n)}), include_groups=False).reset_index()
        w(dc.md_table(c, "%.3f"))
        w("### 2. Permutation importance of the richer model (increase in held-out log loss when the feature is shuffled, x1e4)")
        pv = st["imp"].pivot(index="feature", columns="season", values="delta_logloss") * 1e4
        pv["mean"] = pv.mean(axis=1)
        pv = pv.sort_values("mean", ascending=False).reset_index()
        w(dc.md_table(pv, "%.1f"))
        w("### 3. Residual scan of the baseline (win-probability points)")
        w("Hypotheses tested (BH family, scan): **%d**.  Survivors need BH q<%.2f, |effect|>=%.1f pt, 4+ testable seasons with same sign in 4+, and same sign with one-sided p<0.05 in the other league." % (st["nW"], Q, MIN_EFFECT_WP))
        r = st["resW"]
        w("BH rejections: %d; pass stability+size: %d; survivors after replication: %d" % (r.bh_reject.sum(), r.pre_repl.sum(), r.survivor.sum() if "survivor" in r else 0))
        w("Smallest p-values (top 12):")
        t = r.sort_values("p").head(12)[["seg", "n_games", "effect", "se", "q", "seasons", "same_sign", "replicates"] if "replicates" in r else ["seg", "n_games", "effect", "se", "q"]]
        w(dc.md_table(t, "%.3f"))
        w("### 4. Pre-registered win-probability anecdotes")
        w("Hypotheses tested (separate BH family): **%d**" % st["nA"])
        ra = st["resA"].sort_values("p")
        w(dc.md_table(ra[["seg", "n_games", "effect", "se", "q", "seasons", "same_sign", "bh_reject", "replicates"] if "replicates" in ra else ["seg", "n_games", "effect", "se", "q"]], "%.3f"))
        w("### 5. Totals: pre-game anchor vs pace projection vs OLS vs GBM (held-out RMSE of points still to come, by game progress quartile)")
        w(dc.md_table(st["tper"], "%.3f"))
        w("Final total minus the pre-game total (all games incl. OT; skew/kurt are excess kurtosis), per season:")
        w(dc.md_table(st["dist"], "%.3f"))
        w("### 6. Totals residual scan (total points, residual of the OLS pace+anchor baseline)")
        w("Hypotheses tested (BH family, totals scan): **%d**; anecdotes (own family): **%d**" % (st["nT"], st["nTA"]))
        rt = st["resT"]
        w("BH rejections: %d; survivors after stability, size and replication: %d" % (rt.bh_reject.sum(), rt.survivor.sum() if "survivor" in rt else 0))
        w(dc.md_table(rt.sort_values("p").head(12)[["seg", "n_games", "effect", "se", "q", "seasons", "same_sign", "replicates"] if "replicates" in rt else ["seg", "n_games", "effect", "se", "q"]], "%.3f"))
        w(dc.md_table(st["resTA"].sort_values("p")[["seg", "n_games", "effect", "se", "q", "seasons", "same_sign", "bh_reject"]], "%.3f"))
        w("### 7. Decay tracker (effect by held-out season, slope per season; 5 seasons is low power, a non-significant slope is NOT evidence of no decay)")
        rW = st["resW"].sort_values("p").head(10).seg.tolist()
        glW = game_level(perspective(st["te"], lg), {k: v for k, v in win_segments(perspective(st["te"], lg), lg).items() if k in rW})
        w(dc.md_table(season_effects(glW, rW), "%.3f"))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    log("wrote %s" % out)
    pd.to_pickle({lg: {k: v for k, v in st.items() if k not in ("s", "te", "R", "g")} for lg, st in store.items()}, out.with_suffix(".pkl"))


if __name__ == "__main__":
    main()
