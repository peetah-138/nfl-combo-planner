#!/usr/bin/env python3
"""NFL trend discovery on nflverse play-by-play (offline research; never touches the app, its keys or its trading code).

Pete's goal: "figure out trends that DO matter". This script finds out, on 25+ seasons of public football data, which
game situations the market-style baseline gets systematically wrong, which extra facts (rest, weather, referee, QB,
pace, penalties, ...) add real predictive power, which of those effects are stable from season to season, and which
fade. Most candidates fail; the output says so, with counts. Design and caveats: docs/NFL_DISCOVERY.md.

Data stays OUTSIDE the repo (default ~/dev/research/nfl, override with NFL_RESEARCH_DIR). Source: nflverse
(https://github.com/nflverse), play-by-play releases and nfldata games.csv, licensed CC-BY-4.0: credit "nflverse".

    python3 tools/research/nfl_discovery.py fetch                   # polite, cached download (key-free)
    python3 tools/research/nfl_discovery.py run --results-md docs/results/nfl-discovery-first-run.md
    python3 tools/research/nfl_discovery.py run --synthetic         # end-to-end demo on made-up data with a planted effect

Needs numpy, pandas, pyarrow, scikit-learn (lightgbm optional): see tools/research/requirements-research.txt and use a
venv OUTSIDE the app's own (for example ~/dev/research/venv-nfl). The pure-Python helpers (multiple-testing control,
stability, decay) import without them.

Method in one paragraph (the review checklist is in the doc): one row per play, state at the START of the play (nflverse
`total_*_score` is the score AFTER the play and is never used; `posteam_score`/`defteam_score` are start-of-play). The
baseline and the richer model are retrained walk-forward: to score season S they only ever saw seasons that ended at
least two seasons before S (the two seasons in between pick the number of trees). The scan unit is ONE observation per
game per snapshot clock (kickoff, end of Q1, half, start of Q4, 10:00, 5:00, 2:00 left), so plays of one game are never
counted as independent evidence. All hypotheses scanned are counted, p-values are Benjamini-Hochberg adjusted over the
whole family, and a survivor must also be big enough and keep the same sign in >=70% of seasons.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
except ImportError:                                           # the pure-Python helpers below still work
    np = pd = None

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DATA_ROOT = Path(os.environ.get("NFL_RESEARCH_DIR", "~/dev/research/nfl")).expanduser()
PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{y}.parquet"
GAMES_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
USER_AGENT = "nfl-discovery-research/1 (offline research, polite, cached)"
ATTRIBUTION = ("Data: nflverse (https://github.com/nflverse), play-by-play releases and nfldata games.csv, "
               "licensed CC-BY-4.0. Credit: nflverse contributors.")
FIRST_SEASON = 1999
FETCH_DELAY = 1.0                                             # seconds between downloads

# Snapshot clocks (elapsed regulation seconds) at which a game is sampled once for the situation scan.
SNAPS = (0, 900, 1800, 2700, 3000, 3300, 3480)
SNAP_LABEL = {0: "At kickoff", 900: "At the end of the 1st quarter", 1800: "At halftime",
              2700: "Entering the 4th quarter", 3000: "With 10:00 left", 3300: "With 5:00 left",
              3480: "With 2:00 left"}
ALPHA = 0.05                                                  # false discovery rate for Benjamini-Hochberg
MIN_EFFECT_WP = 2.0                                           # survivors must be >= 2 win-probability points
TRADABLE_WP = 4.0                                             # rough: Kalshi round-trip fee + spread is ~3-4 points
STABLE_SHARE = 0.70                                           # same sign in >= 70% of seasons
MIN_SEASON_N = 15                                             # a season counts toward stability with >= 15 games
SCRIM = ("pass", "run", "punt", "field_goal", "qb_kneel", "qb_spike")

PLAY_COLS = ["game_id", "play_id", "qtr", "game_seconds_remaining", "half_seconds_remaining", "down", "ydstogo",
             "yardline_100", "goal_to_go", "posteam", "posteam_score", "defteam_score", "posteam_timeouts_remaining",
             "defteam_timeouts_remaining", "play_type", "pass_attempt", "rush_attempt", "penalty", "penalty_team",
             "penalty_yards", "interception", "fumble_lost", "home_wp"]

# Column groups. BASE is state plus the pre-game closing line; each candidate group is tested on top of it.
BASE = ["sd", "sd_per_sqrt", "t_left", "half_left", "qtr", "poss_home", "down", "ydstogo", "yardline_100",
        "goal_to_go", "home_to", "away_to", "spread_line", "total_line", "spread_x_t"]
GROUPS = {
    "rest": ["home_rest", "away_rest", "rest_diff"],
    "venue": ["neutral", "roof_dome", "div_game", "playoff"],
    "weather": ["temp_f", "wind_mph"],
    "referee": ["ref_home_edge", "ref_total_edge", "ref_n_prior"],
    "qb": ["home_qb_starts", "away_qb_starts", "home_qb_changed", "away_qb_changed"],
    "pace": ["home_pass_rate", "away_pass_rate", "plays_per_min"],
    "scoring_run": ["run_10m"],
    "penalties": ["pen_cnt_diff", "pen_yds_diff"],
    "turnovers": ["to_margin"],
}
PLAY_LEVEL_GROUPS = ("pace", "scoring_run", "penalties", "turnovers")      # vary within a game; the rest are per game
LEAKY = {"result", "y_home", "home_wp", "home_score", "away_score", "total_pts", "sd_end", "total_home_score",
         "total_away_score"}
MONOTONE_UP = ("sd", "sd_per_sqrt", "spread_line", "run_10m_none")


# ------------------------------------------------------------------ pure-Python statistics (no numpy needed)
def norm_sf2(z):
    """Two-sided normal tail probability of |z|."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def bh_adjust(pvals):
    """Benjamini-Hochberg adjusted p-values (q-values), same order as the input. Controls the false discovery rate
    over EVERYTHING in the list, so pass every hypothesis that was scanned, not only the interesting ones."""
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    q = [0.0] * m
    prev = 1.0
    for rank in range(m, 0, -1):                              # step-up from the largest p
        i = order[rank - 1]
        prev = min(prev, pvals[i] * m / rank)
        q[i] = prev
    return q


def sign_stability(per_season, overall_sign, min_n=MIN_SEASON_N):
    """per_season: {season: (mean, n)}. Share of seasons (with n >= min_n) whose mean has the overall sign, and how
    many seasons that is: (share, n_seasons). A zero mean counts as disagreeing."""
    ok = [(m, n) for m, n in per_season.values() if n >= min_n]
    if not ok or overall_sign == 0:
        return 0.0, len(ok)
    same = sum(1 for m, _ in ok if m * overall_sign > 0)
    return same / len(ok), len(ok)


def ols_slope(xs, ys):
    """Least-squares slope of ys on xs and its standard error: (slope, se). None when under 3 points."""
    n = len(xs)
    if n < 3:
        return None, None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None, None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    rss = sum((y - my - b * (x - mx)) ** 2 for x, y in zip(xs, ys))
    se = math.sqrt(rss / (n - 2) / sxx) if n > 2 else None
    return b, se


def decay_status(per_season, overall, recent=3):
    """Trend tracker for one effect. per_season: {season: (effect, n)} in the effect's own units; overall: the pooled
    effect. Returns {slope, slope_se, recent, first_half, status}. 'retire' = the last `recent` seasons average under
    half the pooled effect or flipped sign; 'fading' = a negative-trend slope (toward zero) more than 2 se from zero;
    otherwise 'holding'. 'too_few_seasons' under 6 usable seasons."""
    pts = sorted((s, e) for s, (e, n) in per_season.items() if n >= MIN_SEASON_N)
    out = {"seasons_used": len(pts)}
    if len(pts) < 6 or overall == 0:
        out.update(slope=None, slope_se=None, recent=None, first_half=None, status="too_few_seasons")
        return out
    sgn = 1.0 if overall > 0 else -1.0
    xs = [s for s, _ in pts]
    ys = [sgn * e for _, e in pts]                            # positive = same direction as the pooled effect
    b, se = ols_slope(xs, ys)
    last = sum(ys[-recent:]) / recent
    half = sum(ys[: len(ys) // 2]) / (len(ys) // 2)
    status = "holding"
    if last < 0.5 * abs(overall):
        status = "retire"
    elif b is not None and se and b < -2 * se:
        status = "fading"
    out.update(slope=round(b, 3) if b is not None else None, slope_se=round(se, 3) if se else None,
               recent=round(sgn * last, 3), first_half=round(sgn * half, 3), status=status)
    return out


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


# ------------------------------------------------------------------ data: polite cached download (outside the repo)
def _need_data_libs():
    if np is None or pd is None:
        sys.exit("numpy/pandas are missing. Use the research venv (tools/research/requirements-research.txt), "
                 "not the app's.")


def ensure_outside_repo(path):
    p = Path(path).expanduser().resolve()
    if REPO in p.parents or p == REPO:
        sys.exit(f"refusing to keep data inside the repo ({p}); use a folder under ~/dev/research")
    return p


def download(url, dest, retries=3):
    """Download url to dest (via a .part file). Returns True when a file was fetched, False on 404."""
    dest = Path(dest)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as r, open(str(dest) + ".part", "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(str(dest) + ".part", dest)
            return True
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return False
            time.sleep(2 ** attempt * 3)
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(2 ** attempt * 3)
    raise RuntimeError(f"download failed after {retries} tries: {url}")


def cmd_fetch(args):
    root = ensure_outside_repo(args.data_dir)
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    last = args.last or time.gmtime().tm_year
    got, cached = [], []
    for y in range(args.first, last + 1):
        dest = raw / f"play_by_play_{y}.parquet"
        if dest.is_file() and dest.stat().st_size > 0 and not args.force:
            cached.append(y)
            continue
        if download(PBP_URL.format(y=y), dest):
            got.append(y)
            time.sleep(FETCH_DELAY)
        else:
            print(f"season {y}: not published (404), skipped")
    gdest = raw / "games.csv"
    if args.force or not gdest.is_file() or gdest.stat().st_size == 0:
        download(GAMES_URL, gdest)
        got.append("games.csv")
    manifest = {"attribution": ATTRIBUTION, "license": "CC-BY-4.0", "fetched_at_utc": time.strftime("%Y-%m-%d %H:%M"),
                "files": {}}
    for f in sorted(raw.iterdir()):
        if f.suffix in (".parquet", ".csv"):
            manifest["files"][f.name] = {"bytes": f.stat().st_size, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"downloaded {got}, already cached {len(cached)} seasons. Folder: {raw}")
    return 0


def load_raw(root, first=FIRST_SEASON, last=None):
    """(plays, games) raw frames from the cached files."""
    _need_data_libs()
    import pyarrow.parquet as pq
    raw = Path(root) / "raw"
    frames = []
    for f in sorted(raw.glob("play_by_play_*.parquet")):
        y = int(f.stem.split("_")[-1])
        if y < first or (last and y > last):
            continue
        have = set(pq.read_schema(f).names)
        d = pd.read_parquet(f, columns=[c for c in PLAY_COLS if c in have])
        frames.append(d)
    if not frames:
        sys.exit(f"no play-by-play files in {raw}: run the fetch command first")
    games = pd.read_csv(raw / "games.csv")
    return pd.concat(frames, ignore_index=True), games


# ------------------------------------------------------------------ features
def build_games(games):
    """Per-game table: label, pre-game facts only (closing line, rest, roof, weather, referee, QB history). Everything
    here is known before kickoff; the referee and QB history use only EARLIER games (no look-ahead)."""
    _need_data_libs()
    g = games.copy()
    g = g[g["result"].notna() & g["spread_line"].notna() & (g["result"] != 0)].copy()
    g["gameday"] = pd.to_datetime(g["gameday"])
    g = g.sort_values(["gameday", "game_id"]).reset_index(drop=True)
    g["y_home"] = (g["result"] > 0).astype(float)
    g["total_pts"] = g["home_score"] + g["away_score"]
    roof = g["roof"].astype("object")
    g["roof_dome"] = np.where(roof.isin(["dome", "closed"]), 1.0, np.where(roof.isin(["outdoors", "open"]), 0.0, np.nan))
    g["temp_f"] = np.where(g["roof_dome"] == 1.0, np.nan, g["temp"])        # indoors: no weather
    g["wind_mph"] = np.where(g["roof_dome"] == 1.0, np.nan, g["wind"])
    g["rest_diff"] = g["home_rest"] - g["away_rest"]
    g["neutral"] = (g["location"] == "Neutral").astype(float)
    g["playoff"] = (g["game_type"] != "REG").astype(float)
    g["div_game"] = g["div_game"].astype(float)
    # referee: shrunken running average of (home margin - spread) and (points - total) over EARLIER games only
    ref = g["referee"].fillna("unknown")
    resid_m = (g["result"] - g["spread_line"]).where(g["total_line"].notna(), 0.0)
    resid_t = (g["total_pts"] - g["total_line"]).fillna(0.0)
    k = 50.0
    for name, series in (("ref_home_edge", resid_m), ("ref_total_edge", resid_t)):
        cum = series.groupby(ref).cumsum() - series
        n_prior = series.groupby(ref).cumcount().astype(float)
        g[name] = cum / (n_prior + k)
        g["ref_n_prior"] = np.minimum(n_prior, 200.0)
    g.loc[g["referee"].isna(), ["ref_home_edge", "ref_total_edge", "ref_n_prior"]] = np.nan
    # QB: number of EARLIER games started by this quarterback; and whether the team changed QB since its last game
    for side, other in (("home", "away"), ("away", "home")):
        pass
    long = []
    for side in ("home", "away"):
        long.append(pd.DataFrame({"game_id": g["game_id"], "gameday": g["gameday"], "side": side,
                                  "team": g[f"{side}_team"], "qb": g[f"{side}_qb_id"]}))
    lg = pd.concat(long, ignore_index=True).sort_values(["gameday", "game_id"], kind="stable")
    lg["starts"] = lg.groupby("qb").cumcount().astype(float)
    lg.loc[lg["qb"].isna(), "starts"] = np.nan
    prev_qb = lg.groupby("team")["qb"].shift(1)
    lg["changed"] = np.where(prev_qb.isna() | lg["qb"].isna(), np.nan, (prev_qb != lg["qb"]).astype(float))
    for side in ("home", "away"):
        part = lg[lg["side"] == side].set_index("game_id")
        g[f"{side}_qb_starts"] = np.minimum(g["game_id"].map(part["starts"]), 100.0)
        g[f"{side}_qb_changed"] = g["game_id"].map(part["changed"])
    keep = ["game_id", "season", "week", "game_type", "gameday", "home_team", "away_team", "y_home", "result",
            "total_pts", "spread_line", "total_line", "home_rest", "away_rest", "rest_diff", "neutral", "roof_dome",
            "div_game", "playoff", "temp_f", "wind_mph", "referee", "ref_home_edge", "ref_total_edge", "ref_n_prior",
            "home_qb_starts", "away_qb_starts", "home_qb_changed", "away_qb_changed"]
    return g[keep].reset_index(drop=True)


def build_plays(plays, gtab):
    """One row per play with the state at the START of the play, plus game facts and prior-play-only in-game features."""
    _need_data_libs()
    pl = plays[plays["play_type"].notna() & plays["posteam"].notna() & plays["game_seconds_remaining"].notna()
               & plays["posteam_score"].notna() & plays["defteam_score"].notna() & plays["qtr"].between(1, 5)].copy()
    pl = pl.merge(gtab, on="game_id", how="inner")
    pl = pl.sort_values(["game_id", "play_id"], kind="stable").reset_index(drop=True)
    gidx = pd.factorize(pl["game_id"])[0]
    pl["gidx"] = gidx
    off_home = (pl["posteam"] == pl["home_team"]).to_numpy()
    ps, ds = pl["posteam_score"].to_numpy(float), pl["defteam_score"].to_numpy(float)
    pl["sd"] = np.where(off_home, ps - ds, ds - ps)                          # home minus away, at the START of the play
    pl["pts_so_far"] = ps + ds
    pl["poss_home"] = np.where(off_home, 1.0, -1.0)
    pl["t_left"] = np.clip(pl["game_seconds_remaining"], 0, 3600) / 3600.0
    pl["half_left"] = pl["half_seconds_remaining"].clip(lower=0, upper=1800) / 1800.0
    pl["sd_per_sqrt"] = pl["sd"] / np.sqrt(pl["t_left"] + 0.02)
    pl["spread_x_t"] = pl["spread_line"] * pl["t_left"]
    pl["down"] = pl["down"].fillna(0.0)
    pl["home_to"] = np.where(off_home, pl["posteam_timeouts_remaining"], pl["defteam_timeouts_remaining"])
    pl["away_to"] = np.where(off_home, pl["defteam_timeouts_remaining"], pl["posteam_timeouts_remaining"])
    el = np.where(pl["qtr"] <= 4, 3600 - pl["game_seconds_remaining"], 3600 + (900 - pl["game_seconds_remaining"]))
    pl["elapsed"] = pd.Series(el).groupby(gidx).cummax().to_numpy()

    def excl_cum(mask):                                       # sum over EARLIER plays of the same game only
        m = pd.Series(np.asarray(mask, dtype=float))
        return (m.groupby(gidx).cumsum() - m).to_numpy()

    is_pass = ((pl["pass_attempt"] == 1) & pl["play_type"].eq("pass")).to_numpy()
    is_run = ((pl["rush_attempt"] == 1) & pl["play_type"].eq("run")).to_numpy()
    for side, mine in (("home", off_home), ("away", ~off_home)):
        p, r = excl_cum(is_pass & mine), excl_cum(is_run & mine)
        pl[f"{side}_pass_rate"] = np.where(p + r >= 8, p / np.maximum(p + r, 1), np.nan)
    scrim = excl_cum(is_pass | is_run)
    pl["plays_per_min"] = np.where(pl["elapsed"] >= 300, scrim / (pl["elapsed"] / 60.0), np.nan)
    pen = (pl["penalty"] == 1).to_numpy()
    pyds = np.where(pen, pl["penalty_yards"].fillna(0).to_numpy(float), 0.0)
    on_home = (pl["penalty_team"] == pl["home_team"]).to_numpy()
    on_away = (pl["penalty_team"] == pl["away_team"]).to_numpy()
    pl["pen_cnt_diff"] = excl_cum(pen & on_home) - excl_cum(pen & on_away)
    pl["pen_yds_diff"] = excl_cum(np.where(on_home, pyds, 0.0)) - excl_cum(np.where(on_away, pyds, 0.0))
    lost = ((pl["interception"] == 1) | (pl["fumble_lost"] == 1)).to_numpy()
    pl["to_margin"] = excl_cum(lost & ~off_home) - excl_cum(lost & off_home)    # opponent's giveaways minus home's
    # scoring in the last 10 minutes of game time (prior state only): home margin now minus home margin 600 s ago
    key = gidx.astype(float) * 1e5 + pl["elapsed"].to_numpy()
    j = np.searchsorted(key, gidx.astype(float) * 1e5 + pl["elapsed"].to_numpy() - 600.0, side="right") - 1
    ok = (j >= 0) & (gidx[np.maximum(j, 0)] == gidx)
    sd = pl["sd"].to_numpy()
    pl["run_10m"] = sd - np.where(ok, sd[np.maximum(j, 0)], 0.0)
    pl.loc[pl["elapsed"] < 300, "run_10m"] = np.nan
    pl["season"] = pl["season"].astype(int)
    return pl


# ------------------------------------------------------------------ models
def have_lightgbm():
    try:
        import lightgbm  # noqa: F401
        return True
    except (ImportError, OSError):                            # OSError: the macOS wheel needs libomp
        return False


def logloss(y, p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y, p):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


class GBM:
    """Gradient boosting with the number of trees chosen on a LATER-than-train validation block (never random rows:
    plays of one game are near-duplicates, a random split would leak)."""

    def __init__(self, feats, cfg):
        self.feats, self.cfg = list(feats), cfg
        self.engine = "lightgbm" if (cfg.get("engine") in ("auto", "lightgbm") and have_lightgbm()) else "sklearn"
        self.best = None
        self.model = None
        self.cal = None

    def fit(self, Xtr, ytr, Xva, yva):
        c = self.cfg
        up = [1 if f in MONOTONE_UP else 0 for f in self.feats]
        if self.engine == "lightgbm":
            import lightgbm as lgb
            self.model = lgb.LGBMClassifier(n_estimators=c["max_iter"], learning_rate=c["lr"], num_leaves=15,
                                            min_child_samples=c["min_leaf"], reg_lambda=1.0, monotone_constraints=up,
                                            random_state=0, verbose=-1)
            self.model.fit(Xtr, ytr, eval_set=[(Xva, yva)],
                           callbacks=[lgb.early_stopping(25, verbose=False)])
            self.best = int(self.model.best_iteration_ or c["max_iter"])
            self._recalibrate(Xva, yva)
            return self
        from sklearn.ensemble import HistGradientBoostingClassifier
        self.model = HistGradientBoostingClassifier(
            max_iter=c["max_iter"], learning_rate=c["lr"], max_leaf_nodes=15, min_samples_leaf=c["min_leaf"],
            l2_regularization=1.0, early_stopping=False, random_state=0, max_bins=128,
            monotonic_cst={f: u for f, u in zip(self.feats, up) if u})
        self.model.fit(Xtr, ytr)
        best, best_ll = 1, float("inf")
        for i, p in enumerate(self.model.staged_predict_proba(Xva), 1):
            ll = logloss(yva, p[:, 1])
            if ll < best_ll - 1e-7:
                best, best_ll = i, ll
        self.best = best
        self._recalibrate(Xva, yva)
        return self

    def _raw(self, X):
        if self.engine == "lightgbm":
            return self.model.predict_proba(X, num_iteration=self.best)[:, 1]
        for i, p in enumerate(self.model.staged_predict_proba(X), 1):
            if i == self.best:
                return p[:, 1]
        return p[:, 1]

    def _recalibrate(self, Xva, yva):
        """Heavily smoothed trees come out under-confident at the extremes (a late 21-point lead priced at 96% that wins
        98%). A two-number logistic stretch (slope, intercept) is fit on the validation seasons, which are earlier than
        every season the model will score, so it is not look-ahead. Without it the scan reports the model's own
        timidity as 'trends'."""
        from sklearn.linear_model import LogisticRegression
        p = np.clip(self._raw(Xva), 1e-5, 1 - 1e-5)
        z = np.log(p / (1 - p)).reshape(-1, 1)
        self.cal = LogisticRegression(C=1e4, max_iter=200).fit(z, np.asarray(yva))

    def predict(self, X):
        p = np.clip(self._raw(X), 1e-5, 1 - 1e-5)
        z = np.log(p / (1 - p)).reshape(-1, 1)
        return self.cal.predict_proba(z)[:, 1]


def walk_forward(pl, feats, test_seasons, cfg):
    """Predict each test season with a model trained ONLY on seasons that ended at least `val` seasons earlier; the
    `val` seasons in between pick the tree count. Returns (pred array aligned with pl, {season: fitted GBM})."""
    seasons = pl["season"].to_numpy()
    y = pl["y_home"].to_numpy()
    bad = set(feats) & LEAKY
    if bad:
        raise ValueError(f"leaky columns in feature list: {sorted(bad)}")
    X = pl[feats]
    pred = np.full(len(pl), np.nan)
    models = {}
    v = cfg["val_seasons"]
    for s in test_seasons:
        tr, va, te = seasons < s - v, (seasons >= s - v) & (seasons < s), seasons == s
        if tr.sum() < 5000 or va.sum() < 500 or te.sum() == 0:
            continue
        assert seasons[tr].max() < seasons[va].min() <= seasons[va].max() < s, "season split broke"
        m = GBM(feats, cfg).fit(X[tr], y[tr], X[va], y[va])
        pred[te] = m.predict(X[te])
        models[s] = m
    return pred, models


K_SPREAD = {"k": 0.14}                                        # logit points per point of spread; fit by fit_spread_k


def fit_spread_k(gtab):
    """Slope of a no-intercept logistic of home win on the closing spread (scale only; used to put the spread on a
    logit scale for the portable model). Fit on all games: a scale, not a predictor, and the model is scale-free."""
    from sklearn.linear_model import LogisticRegression
    m = LogisticRegression(fit_intercept=False, C=1e6).fit(gtab[["spread_line"]], gtab["y_home"])
    return float(m.coef_[0][0])


PORTABLE = ["z1", "d", "pre", "pre_t", "pre_sqrt_t", "poss", "poss_t", "poss_sqrt_t"]


def portable_features(sd, t_left, poss, spread, k):
    """Features for the small logistic model that can run in plain Python on the production Mac: lead, time left,
    possession, pre-game strength. Every feature flips sign when home and away swap, so no intercept is needed."""
    t = np.clip(np.asarray(t_left, float), 0, 1)
    sd = np.asarray(sd, float)
    pre = k * np.asarray(spread, float)
    poss = np.asarray(poss, float)
    cols = [sd / np.sqrt(t + 0.02), sd, pre, pre * t, pre * np.sqrt(t), poss, poss * t, poss * np.sqrt(t)]
    return np.column_stack(cols)


def portable_walk_forward(pl, test_seasons, cfg, k):
    from sklearn.linear_model import LogisticRegression
    seasons = pl["season"].to_numpy()
    y = pl["y_home"].to_numpy()
    F = portable_features(pl["sd"], pl["t_left"], pl["poss_home"], pl["spread_line"], k)
    pred = np.full(len(pl), np.nan)
    for s in test_seasons:
        tr, te = seasons < s - cfg["val_seasons"], seasons == s
        if tr.sum() < 5000 or te.sum() == 0:
            continue
        m = LogisticRegression(fit_intercept=False, C=1e4, max_iter=500).fit(F[tr], y[tr])
        pred[te] = m.predict_proba(F[te])[:, 1]
    return pred


def export_portable(pl, k, path, seasons_note):
    """Fit the portable logistic on every season and write its coefficients (a dozen numbers) as JSON."""
    from sklearn.linear_model import LogisticRegression
    F = portable_features(pl["sd"], pl["t_left"], pl["poss_home"], pl["spread_line"], k)
    m = LogisticRegression(fit_intercept=False, C=1e4, max_iter=500).fit(F, pl["y_home"].to_numpy())
    doc = {"model": "nfl_state_logistic_v1", "features": PORTABLE, "coef": [round(float(c), 6) for c in m.coef_[0]],
           "k_spread": round(k, 5), "trained_on": seasons_note, "attribution": ATTRIBUTION,
           "recipe": ("team-centric: d = my score - opponent score, t = share of game left (0..1), poss = +1 my ball, "
                      "-1 their ball, 0 unknown, pre = logit of my pre-game win chance; z1 = d/sqrt(t+0.02); "
                      "features = [z1, d, pre, pre*t, pre*sqrt(t), poss, poss*t, poss*sqrt(t)]; p = sigmoid(coef . features)")}
    Path(path).write_text(json.dumps(doc, indent=1) + "\n")
    return doc


# ------------------------------------------------------------------ evaluation
def calibration_table(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    rows = []
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        rows.append({"bin": f"{edges[b]:.1f}-{edges[b + 1]:.1f}", "n": int(m.sum()), "mean_pred": round(float(p[m].mean()), 4),
                     "observed": round(float(y[m].mean()), 4)})
    return rows


def cluster_boot(delta, codes, n_boot, seed=0):
    """Mean of delta (per-play loss difference) and a 95% range from resampling whole GAMES."""
    n_games = int(codes.max()) + 1
    s = np.bincount(codes, weights=delta, minlength=n_games)
    n = np.bincount(codes, minlength=n_games).astype(float)
    point = s.sum() / n.sum()
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, n_games, size=(n_boot, n_games))
    vals = s[pick].sum(1) / n[pick].sum(1)
    return float(point), [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def evaluate_models(te, cfg, preds):
    """Log loss / Brier overall, by season and by phase of the game, with calibration tables."""
    y = te["y_home"].to_numpy()
    seasons = te["season"].to_numpy()
    codes = pd.factorize(te["game_id"])[0]
    out = {"models": {}, "by_season": {}, "calibration": {}, "by_phase": {}, "improvement": {}}
    for name, p in preds.items():
        out["models"][name] = {"logloss": round(logloss(y, p), 5), "brier": round(brier(y, p), 5), "rows": int(len(y))}
        out["calibration"][name] = calibration_table(y, p)
    phase = np.select([te["qtr"].to_numpy() <= 1, te["qtr"].to_numpy() == 2, te["qtr"].to_numpy() == 3,
                       te["qtr"].to_numpy() == 4], ["Q1", "Q2", "Q3", "Q4"], "OT")
    for s in sorted(set(seasons)):
        m = seasons == s
        out["by_season"][int(s)] = {k: {"logloss": round(logloss(y[m], p[m]), 5), "brier": round(brier(y[m], p[m]), 5)}
                                    for k, p in preds.items()}
    for ph in ("Q1", "Q2", "Q3", "Q4", "OT"):
        m = phase == ph
        if m.sum():
            out["by_phase"][ph] = {k: round(logloss(y[m], p[m]), 5) for k, p in preds.items()}
    names = list(preds)
    for a, b in itertools.combinations(names, 2):
        # improvement of b over a: loss(a) - loss(b), positive = b better
        pa, pb = np.clip(preds[a], 1e-6, 1 - 1e-6), np.clip(preds[b], 1e-6, 1 - 1e-6)
        la = -(y * np.log(pa) + (1 - y) * np.log(1 - pa))
        lb = -(y * np.log(pb) + (1 - y) * np.log(1 - pb))
        d = la - lb
        point, ci = cluster_boot(d, codes, cfg["n_boot"])
        per = {}
        for s in sorted(set(seasons)):
            m = seasons == s
            pt, c = cluster_boot(d[m], pd.factorize(te["game_id"].to_numpy()[m])[0], cfg["n_boot"], seed=int(s))
            per[int(s)] = {"gain": round(pt, 6), "ci": [round(c[0], 6), round(c[1], 6)]}
        out["improvement"][f"{b} vs {a}"] = {"gain_logloss": round(point, 6), "ci95": [round(ci[0], 6), round(ci[1], 6)],
                                              "seasons_better": sum(1 for v in per.values() if v["gain"] > 0),
                                              "seasons": len(per), "by_season": per}
    return out


def permutation_importance(te, feats, models, cfg):
    """Per season, per feature group: how much held-out log loss gets WORSE when the group's information is destroyed
    (per-game groups are shuffled across whole games; in-game groups are shuffled across plays). Higher = the model
    leans on it more. Marginal shuffling can create unrealistic rows, so read it with the refit ablation."""
    rng = np.random.default_rng(cfg["seed"])
    rows = {}
    for s, model in models.items():
        m = (te["season"] == s).to_numpy()
        part = te[m]
        X = part[feats]
        y = part["y_home"].to_numpy()
        base = logloss(y, model.predict(X))
        gpos = pd.factorize(part["game_id"])[0]
        n_games = int(gpos.max()) + 1
        res = {}
        for grp, cols in GROUPS.items():
            vals = []
            for _ in range(cfg["perm_repeats"]):
                Xp = X.copy()
                if grp in PLAY_LEVEL_GROUPS:
                    Xp[cols] = X[cols].to_numpy()[rng.permutation(len(X))]
                else:
                    first = X[cols].groupby(gpos).first().to_numpy()
                    Xp[cols] = first[rng.permutation(n_games)][gpos]
                vals.append(logloss(y, model.predict(Xp)) - base)
            res[grp] = round(float(np.mean(vals)), 6)
        rows[int(s)] = res
    return rows


# ------------------------------------------------------------------ the situation scan
def pick_snapshots(pl):
    """One row per game per snapshot clock: the first scrimmage play at or after the clock (regulation only)."""
    ok = pl["play_type"].isin(SCRIM) & (pl["qtr"] <= 4)
    parts = []
    for snap in SNAPS:
        sub = pl[ok & (pl["elapsed"] >= snap)]
        first = sub.groupby("gidx", sort=False).head(1).copy()
        first["snap"] = snap
        parts.append(first)
    return pd.concat(parts, ignore_index=True)


def _bin(series, edges, labels):
    return pd.cut(series, bins=edges, labels=labels, right=False).astype("object")


def build_observations(snaps, p_home, ref_rank):
    """Snapshot rows -> observations oriented to a focal team (the leader; the favorite when tied), with the
    residual (outcome minus the baseline's win probability) in that team's favor and the situation dimensions."""
    o = snaps.copy()
    o["p_home"] = p_home
    sd, spread = o["sd"].to_numpy(), o["spread_line"].to_numpy()
    focal_home = np.where(sd != 0, sd > 0, spread >= 0)
    fs = np.where(focal_home, 1.0, -1.0)
    o["focal_home"] = focal_home
    o["resid_home"] = o["y_home"] - o["p_home"]
    o["resid"] = fs * o["resid_home"]                          # focal team's outcome minus its modeled chance
    o["lead"] = np.abs(sd)
    o["spread_f"] = fs * spread
    o["lead_bin"] = np.where(o["lead"] == 0, "tied", _bin(o["lead"], [1, 4, 8, 15, 100], ["l1_3", "l4_7", "l8_14", "l15p"]))
    o["fav"] = np.where(o["spread_f"] >= 1.5, "fav", np.where(o["spread_f"] <= -1.5, "dog", "pickem"))
    o["venue"] = np.where(o["neutral"] == 1, "neutral", np.where(focal_home, "home", "away"))
    ball_home = o["poss_home"].to_numpy() > 0
    o["ball"] = np.where(ball_home == focal_home, "ball", "no_ball")
    o.loc[o["snap"] == 0, "ball"] = None                       # the opening drive says nothing yet
    a = np.abs(spread)
    o["spread_size"] = np.where(a < 3, "close", np.where(a < 7, "mid", "big"))
    o["roof"] = np.where(o["roof_dome"] == 1, "dome", np.where(o["roof_dome"] == 0, "outdoor", None))
    out = o["roof_dome"] == 0
    o["temp"] = np.where(out & o["temp_f"].notna(), np.where(o["temp_f"] <= 35, "cold", np.where(o["temp_f"] <= 60, "cool", "warm")), None)
    o["wind"] = np.where(out & o["wind_mph"].notna(), np.where(o["wind_mph"] >= 15, "windy", "calm"), None)
    my_rest = np.where(focal_home, o["home_rest"], o["away_rest"])
    op_rest = np.where(focal_home, o["away_rest"], o["home_rest"])
    o["rest"] = np.where(my_rest <= 5, "short", np.where(my_rest <= 8, "normal", "long"))
    o["rest_adv"] = np.where(my_rest - op_rest >= 3, "adv", np.where(my_rest - op_rest <= -3, "dis", "even"))
    o["div"] = np.where(o["div_game"] == 1, "div", "nondiv")
    o["playoff_b"] = np.where(o["playoff"] == 1, "post", "reg")
    my_qb = np.where(focal_home, o["home_qb_starts"], o["away_qb_starts"])
    o["qb_exp"] = np.where(np.isnan(my_qb), None, np.where(my_qb < 10, "rookie", "vet"))
    o["ref"] = o["referee"].map(ref_rank)
    run_f = fs * o["run_10m"].to_numpy()
    o["run"] = np.where(np.isnan(run_f), None, np.where(run_f >= 10, "hot", np.where(run_f <= -10, "cold", "none")))
    to_f = fs * o["to_margin"].to_numpy()                       # focal's turnover margin (opponent giveaways - own)
    o["to"] = np.where(to_f >= 2, "plus", np.where(to_f <= -2, "minus", "even"))
    o.loc[o["snap"] == 0, "to"] = None
    pen_f = fs * o["pen_yds_diff"].to_numpy()                   # home minus away penalty yards, focal-signed: positive = focal MORE
    o["pen"] = np.where(pen_f >= 30, "more", np.where(pen_f <= -30, "fewer", "even"))
    o.loc[o["snap"] == 0, "pen"] = None
    pr = np.where(focal_home, o["home_pass_rate"], o["away_pass_rate"])
    o["pace"] = np.where(np.isnan(pr), None, np.where(pr >= 0.65, "pass_heavy", np.where(pr <= 0.45, "run_heavy", "mid")))
    return o


DIMS = ["lead_bin", "fav", "venue", "ball", "spread_size", "roof", "temp", "wind", "rest", "rest_adv", "div",
        "playoff_b", "qb_exp", "ref", "run", "to", "pen", "pace"]
PHRASE = {
    ("lead_bin", "tied"): "the game is tied (team = the pre-game favorite)", ("lead_bin", "l1_3"): "it leads by 1-3",
    ("lead_bin", "l4_7"): "it leads by 4-7", ("lead_bin", "l8_14"): "it leads by 8-14", ("lead_bin", "l15p"): "it leads by 15+",
    ("fav", "fav"): "it is the pre-game favorite", ("fav", "dog"): "it is the pre-game underdog",
    ("fav", "pickem"): "the game is a pick'em",
    ("venue", "home"): "it is at home", ("venue", "away"): "it is on the road", ("venue", "neutral"): "the site is neutral",
    ("ball", "ball"): "it has the ball", ("ball", "no_ball"): "the opponent has the ball",
    ("spread_size", "close"): "the pre-game spread is under 3", ("spread_size", "mid"): "the pre-game spread is 3-7",
    ("spread_size", "big"): "the pre-game spread is 7+",
    ("roof", "dome"): "the game is indoors", ("roof", "outdoor"): "the game is outdoors",
    ("temp", "cold"): "outdoor temperature is 35F or colder", ("temp", "cool"): "outdoor temperature is 36-60F",
    ("temp", "warm"): "outdoor temperature is above 60F",
    ("wind", "windy"): "wind is 15+ mph", ("wind", "calm"): "wind is under 15 mph",
    ("rest", "short"): "it had 5 or fewer days of rest", ("rest", "normal"): "it had 6-8 days of rest",
    ("rest", "long"): "it had 9+ days of rest",
    ("rest_adv", "adv"): "it had 3+ more rest days than the opponent", ("rest_adv", "even"): "rest was about even",
    ("rest_adv", "dis"): "it had 3+ fewer rest days than the opponent",
    ("div", "div"): "it is a division game", ("div", "nondiv"): "it is not a division game",
    ("playoff_b", "post"): "it is a playoff game", ("playoff_b", "reg"): "it is a regular-season game",
    ("qb_exp", "rookie"): "its QB has under 10 prior starts", ("qb_exp", "vet"): "its QB has 10+ prior starts",
    ("run", "hot"): "it outscored the opponent by 10+ in the last 10 minutes",
    ("run", "cold"): "it was outscored by 10+ in the last 10 minutes", ("run", "none"): "no 10-point scoring run in the last 10 minutes",
    ("to", "plus"): "it leads the turnover battle by 2+", ("to", "minus"): "it trails the turnover battle by 2+",
    ("to", "even"): "turnovers are within 1",
    ("pen", "more"): "it has 30+ more penalty yards than the opponent", ("pen", "fewer"): "it has 30+ fewer penalty yards",
    ("pen", "even"): "penalty yards are within 30",
    ("pace", "pass_heavy"): "it has passed on 65%+ of its plays", ("pace", "run_heavy"): "it has passed on 45% or fewer of its plays",
    ("pace", "mid"): "its pass rate is 46-64%",
}


def phrase(dim, b):
    if dim == "ref":
        return f"the referee is crew chief {b}"
    return PHRASE.get((dim, b), f"{dim}={b}")


def label(snap, conds):
    who = "the favorite" if snap == 0 else "the leading team (the favorite if tied)"
    if not conds:
        return f"{SNAP_LABEL[snap]}: any game, from the viewpoint of {who}"
    return f"{SNAP_LABEL[snap]}: {who}, when " + " and ".join(phrase(d, b) for d, b in conds)


def scan(obs, resid_col, min_n, dims=DIMS):
    """Every cell with at least min_n observations: all snapshots x (everything, one condition, two conditions).
    Returns (stats DataFrame, number of cells enumerated). One observation = one game at one snapshot."""
    r = obs[resid_col].to_numpy(float)
    d = pd.DataFrame({"snap": obs["snap"].to_numpy(), "_r": r, "_r2": r * r})
    for c in dims:
        d[c] = obs[c].to_numpy(object)
    recs, enumerated = [], 0

    def add(snap, conds, n, s, ss):
        if n < min_n:
            return
        mean = s / n
        var = max((ss - n * mean * mean) / (n - 1), 1e-12)
        t = mean / math.sqrt(var / n)
        recs.append((snap, conds, int(n), mean, math.sqrt(var), t, norm_sf2(t)))

    for snap, sub in d.groupby("snap"):
        enumerated += 1
        add(snap, (), len(sub), sub["_r"].sum(), sub["_r2"].sum())
        for d1 in dims:
            g1 = sub.groupby(d1).agg(n=("_r", "size"), s=("_r", "sum"), ss=("_r2", "sum"))
            enumerated += len(g1)
            for b, row in g1.iterrows():
                add(snap, ((d1, b),), row["n"], row["s"], row["ss"])
        for d1, d2 in itertools.combinations(dims, 2):
            g2 = sub.groupby([d1, d2]).agg(n=("_r", "size"), s=("_r", "sum"), ss=("_r2", "sum"))
            enumerated += len(g2)
            for (b1, b2), row in g2.iterrows():
                add(snap, ((d1, b1), (d2, b2)), row["n"], row["s"], row["ss"])
    st = pd.DataFrame(recs, columns=["snap", "conds", "n", "mean", "sd", "t", "p"])
    if len(st):
        st["q"] = bh_adjust(st["p"].tolist())
    return st, enumerated


def cell_mask(obs, snap, conds):
    m = (obs["snap"] == snap).to_numpy().copy()
    for d, b in conds:
        m = m & (obs[d] == b).to_numpy()
    return m


def season_detail(obs, snap, conds, resid_col="resid"):
    m = cell_mask(obs, snap, conds)
    sub = obs[m]
    out = {}
    for s, g in sub.groupby("season"):
        out[int(s)] = (float(g[resid_col].mean()) * 100.0, int(len(g)))
    return out


def describe_cell(obs, row, cfg, resid_col="resid"):
    """Full record for one cell: pooled effect, CI, per-season effects, stability, decay, verdict."""
    per = season_detail(obs, row["snap"], row["conds"], resid_col)
    eff = row["mean"] * 100.0
    se = row["sd"] / math.sqrt(row["n"]) * 100.0
    share, n_seasons = sign_stability({s: (m, n) for s, (m, n) in per.items()}, 1 if eff > 0 else -1)
    big = abs(eff) >= cfg["min_effect"]
    stable = share >= STABLE_SHARE and n_seasons >= cfg["min_seasons"]
    return {"label": label(row["snap"], row["conds"]), "snap": int(row["snap"]), "n": int(row["n"]),
            "effect_wp_pts": round(eff, 2), "ci95": [round(eff - 1.96 * se, 2), round(eff + 1.96 * se, 2)],
            "p": float(row["p"]), "q": float(row["q"]), "same_sign_share": round(share, 2), "seasons": n_seasons,
            "big_enough": bool(big), "stable": bool(stable), "tradable_size": bool(abs(eff) >= TRADABLE_WP),
            "survives": bool(row["q"] < ALPHA and big and stable),
            "by_season": {s: {"effect": round(m, 2), "n": n} for s, (m, n) in per.items()},
            "decay": decay_status(per, eff)}


def independent_survivors(obs, cfg, max_rounds=12):
    """Greedy explain-away. Many survivors are one real effect seen through overlapping slices (a dome edge shows up in
    every 'home' and 'road' cell). Take the strongest survivor, subtract its average effect from the games in it,
    rescan everything, repeat. What is left after each round is an independent finding; the rest are echoes."""
    o = obs.copy()
    o["resid_adj"] = o["resid"].to_numpy(float).copy()
    kept = []
    for _ in range(max_rounds):
        st, _n = scan(o, "resid_adj", cfg["min_n"])
        cand = st[st["q"] < ALPHA].sort_values("p")
        det = []
        for _, row in cand.iterrows():
            d = describe_cell(o, row, cfg, "resid_adj")
            if d["survives"]:
                det.append((d, row))
        if not det:
            break
        top, row = min(det, key=lambda t: t[0]["p"])
        top["round"] = len(kept) + 1
        kept.append(top)
        m = cell_mask(o, row["snap"], row["conds"])
        vals = o["resid_adj"].to_numpy(float).copy()
        vals[m] -= vals[m].mean()
        o["resid_adj"] = vals
    return kept


# ------------------------------------------------------------------ pre-registered anecdotes (frozen before the first real run)
# Each: id, plain-English claim, the team whose outcome the claim is about, snapshot, claimed direction (+ = the claimed
# team does BETTER than the baseline thinks), and a mask on the observation table. Totals claims are in points.
def _anecdotes():
    A = []

    def add(aid, text, side, snap, sign, mask):
        A.append({"id": aid, "claim": text, "side": side, "snap": snap, "sign": sign, "mask": mask, "unit": "wp"})

    add("A01", "A team leading at halftime wins more often than the numbers say", "leader", 1800, +1,
        lambda o: (o["lead"] >= 1))
    add("A02", "A halftime lead of 15+ is a lock (the leader is even safer than priced)", "leader", 1800, +1,
        lambda o: (o["lead"] >= 15))
    add("A03", "Never count out a team down 8-14 with 10:00 left: comebacks happen more than priced", "trailer", 3000, +1,
        lambda o: (o["lead"] >= 8) & (o["lead"] < 15))
    add("A04", "In high-scoring games (total 47+) the trailing team comes back more than priced (down 8-14, 10:00 left)",
        "trailer", 3000, +1, lambda o: (o["lead"] >= 8) & (o["lead"] < 15) & (o["total_line"] >= 47))
    add("A05", "Home underdogs of 3+ are better than their price (at kickoff)", "home", 0, +1,
        lambda o: o["spread_line"] <= -3)
    add("A06", "A team on short rest (5 days or fewer) against a rested opponent is worse than priced", "short_rest", 0, -1,
        lambda o: ((o["home_rest"] <= 5) & (o["away_rest"] >= 6)) | ((o["away_rest"] <= 5) & (o["home_rest"] >= 6)))
    add("A07", "A team coming off a long break (9+ days) against an opponent on 8 or fewer is better than priced", "long_rest", 0, +1,
        lambda o: ((o["home_rest"] >= 9) & (o["away_rest"] <= 8)) | ((o["away_rest"] >= 9) & (o["home_rest"] <= 8)))
    add("A08", "Momentum: a team that outscored the other by 10+ in the last 10 minutes keeps rolling (10:00 left)", "hot", 3000, +1,
        lambda o: o["run_10m"].abs() >= 10)
    add("A09", "The turnover battle decides it: +2 or better at halftime wins more than priced", "to_plus", 1800, +1,
        lambda o: o["to_margin"].abs() >= 2)
    add("A10", "Penalty trouble hurts: 30+ more penalty yards than the other team at halftime", "pen_more", 1800, -1,
        lambda o: o["pen_yds_diff"].abs() >= 30)
    add("A11", "Division games are tighter: the favorite does worse than priced in division games (at kickoff)", "fav", 0, -1,
        lambda o: (o["div_game"] == 1) & (o["spread_line"].abs() >= 1.5))
    add("A12", "Cold weather helps the home team (outdoors, 32F or colder, at kickoff)", "home", 0, +1,
        lambda o: (o["roof_dome"] == 0) & (o["temp_f"] <= 32))
    return A


ANECDOTE_TOTALS = [
    {"id": "T01", "claim": "Dome games go over the total", "sign": +1, "unit": "points",
     "mask": lambda g: g["roof_dome"] == 1},
    {"id": "T02", "claim": "Windy games (15+ mph, outdoors) go under the total", "sign": -1, "unit": "points",
     "mask": lambda g: (g["roof_dome"] == 0) & (g["wind_mph"] >= 15)},
    {"id": "T03", "claim": "Freezing games (32F or colder, outdoors) go under the total", "sign": -1, "unit": "points",
     "mask": lambda g: (g["roof_dome"] == 0) & (g["temp_f"] <= 32)},
]


def anecdote_side_resid(o, side):
    """The residual (outcome - model) for the team a claim is about; NaN where the claim has no such team."""
    rh, sd, spread = o["resid_home"].to_numpy(), o["sd"].to_numpy(), o["spread_line"].to_numpy()
    nan = np.full(len(o), np.nan)
    if side == "leader":
        return np.where(sd > 0, rh, np.where(sd < 0, -rh, np.nan))
    if side == "trailer":
        return np.where(sd > 0, -rh, np.where(sd < 0, rh, np.nan))
    if side == "home":
        return rh
    if side == "fav":
        return np.where(spread > 0, rh, np.where(spread < 0, -rh, np.nan))
    if side in ("short_rest", "long_rest"):
        h, a = o["home_rest"].to_numpy(), o["away_rest"].to_numpy()
        home_is = (h <= 5) if side == "short_rest" else (h >= 9)
        away_is = (a <= 5) if side == "short_rest" else (a >= 9)
        return np.where(home_is & ~away_is, rh, np.where(away_is & ~home_is, -rh, np.nan))
    if side == "hot":
        run = o["run_10m"].to_numpy()                          # home margin gained in the last 10 minutes
        return np.where(run >= 10, rh, np.where(run <= -10, -rh, np.nan))
    if side == "to_plus":
        tm = o["to_margin"].to_numpy()                         # opponent giveaways minus home's: positive = home ahead
        return np.where(tm >= 2, rh, np.where(tm <= -2, -rh, np.nan))
    if side == "pen_more":
        py = o["pen_yds_diff"].to_numpy()                      # home minus away penalty yards
        return np.where(py >= 30, rh, np.where(py <= -30, -rh, np.nan))
    return nan


def run_anecdotes(obs, gtest, cfg):
    rows = []
    for a in _anecdotes():
        sub = obs[obs["snap"] == a["snap"]]
        sub = sub[a["mask"](sub)]
        r = anecdote_side_resid(sub, a["side"])
        keep = ~np.isnan(r)
        sub, r = sub[keep], r[keep]
        rows.append((a, sub["season"].to_numpy(), r))
    for t in ANECDOTE_TOTALS:
        sub = gtest[t["mask"](gtest)]
        rows.append((t, sub["season"].to_numpy(), (sub["total_pts"] - sub["total_line"]).to_numpy(float)))
    recs = []
    for a, seasons, r in rows:
        n = len(r)
        scale = 100.0 if a["unit"] == "wp" else 1.0
        if n < 30:
            recs.append({"id": a["id"], "claim": a["claim"], "n": int(n), "unit": a["unit"], "note": "too few games",
                         "p": 1.0})
            continue
        mean = float(r.mean()) * scale
        sd = float(r.std(ddof=1)) * scale
        t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
        per = {int(s): (float(r[seasons == s].mean()) * scale, int((seasons == s).sum())) for s in sorted(set(seasons))}
        share, n_seasons = sign_stability(per, 1 if mean > 0 else -1)
        recs.append({"id": a["id"], "claim": a["claim"], "claimed_sign": a["sign"], "n": int(n), "unit": a["unit"],
                     "effect": round(mean, 2), "ci95": [round(mean - 1.96 * sd / math.sqrt(n), 2), round(mean + 1.96 * sd / math.sqrt(n), 2)],
                     "p": norm_sf2(t), "same_sign_share": round(share, 2), "seasons": n_seasons,
                     "by_season": {s: {"effect": round(m, 2), "n": k} for s, (m, k) in per.items()},
                     "decay": decay_status(per, mean)})
    qs = bh_adjust([x["p"] for x in recs])
    for x, q in zip(recs, qs):
        x["q"] = q
        if "effect" not in x:
            x["verdict"] = "not testable (too few games)"
            continue
        min_eff = cfg["min_effect"] if x["unit"] == "wp" else 1.0
        sig = x["q"] < ALPHA and abs(x["effect"]) >= min_eff and x["same_sign_share"] >= STABLE_SHARE \
            and x["seasons"] >= cfg["min_seasons"]
        if sig and (x["effect"] > 0) == (x["claimed_sign"] > 0):
            x["verdict"] = "SURVIVES (claim holds)"
        elif sig:
            x["verdict"] = "SURVIVES but in the OPPOSITE direction to the claim"
        elif x["p"] < ALPHA:
            x["verdict"] = "nominally significant, fails the family-wide correction or size/stability bar"
        else:
            x["verdict"] = "no evidence (indistinguishable from zero)"
    return recs


# ------------------------------------------------------------------ placebo: does the machinery find false positives?
def placebo_scan(obs, cfg, reps, seed=0):
    """Flip the sign of each game's residuals at random (the same flip for every snapshot of one game), rerun the whole
    scan and count cells that pass BH at ALPHA. Under this null the count should be about zero. Checks the machinery,
    not the data."""
    rng = np.random.default_rng(seed)
    gid = obs["game_id"].to_numpy()
    uniq, inv = np.unique(gid, return_inverse=True)
    counts = []
    for _ in range(reps):
        flip = rng.choice([-1.0, 1.0], size=len(uniq))[inv]
        o = obs.copy()
        o["_pl"] = o["resid"].to_numpy() * flip
        st, _ = scan(o, "_pl", cfg["min_n"])
        counts.append(int((st["q"] < ALPHA).sum()) if len(st) else 0)
    return counts


# ------------------------------------------------------------------ the whole pipeline
DEFAULT_CFG = {"test_start": 2010, "val_seasons": 2, "engine": "auto", "max_iter": 250, "lr": 0.08, "min_leaf": 1500, "scan_model": "gbm", "min_n": 150,
               "min_effect": MIN_EFFECT_WP, "min_seasons": 5, "n_boot": 300, "perm_repeats": 3, "seed": 0,
               "ablate_last": 0, "placebo": 20, "log": print}


def run_pipeline(plays_raw, games_raw, cfg=None):
    """Everything. Returns a JSON-serializable dict of aggregates (no per-game rows)."""
    _need_data_libs()
    c = dict(DEFAULT_CFG)
    c.update(cfg or {})
    log = c["log"]
    t0 = time.time()
    gtab = build_games(games_raw)
    assert np.corrcoef(gtab["spread_line"], gtab["result"])[0, 1] > 0.3, "spread_line sign convention is not home-favored"
    pl = build_plays(plays_raw, gtab)
    seasons = sorted(pl["season"].unique())
    test_seasons = [s for s in seasons if s >= c["test_start"]]
    log(f"plays {len(pl):,}, games {pl['game_id'].nunique():,}, seasons {seasons[0]}-{seasons[-1]}; "
        f"walk-forward test seasons {test_seasons[0]}-{test_seasons[-1]} ({len(test_seasons)})")
    base_feats = list(BASE)
    all_feats = base_feats + [f for cols in GROUPS.values() for f in cols]
    k = fit_spread_k(gtab)
    log("fitting walk-forward baseline ...")
    p0, m0 = walk_forward(pl, base_feats, test_seasons, c)
    log("fitting walk-forward richer model ...")
    p1, m1 = walk_forward(pl, all_feats, test_seasons, c)
    log("fitting portable logistic ...")
    pp = portable_walk_forward(pl, test_seasons, c, k)
    pl["p0"], pl["p1"], pl["pp"] = p0, p1, pp
    te = pl[pl["p0"].notna() & pl["p1"].notna()].reset_index(drop=True)
    res = {"attribution": ATTRIBUTION, "config": {kk: vv for kk, vv in c.items() if kk != "log"},
           "engine": next(iter(m0.values())).engine if m0 else None,
           "data": {"seasons": [int(seasons[0]), int(seasons[-1])], "games": int(pl["game_id"].nunique()),
                    "plays": int(len(pl)), "test_seasons": [int(test_seasons[0]), int(test_seasons[-1])],
                    "test_games": int(te["game_id"].nunique()), "test_plays": int(len(te))}}
    preds = {"baseline_gbm": te["p0"].to_numpy(), "richer_gbm": te["p1"].to_numpy(), "portable_logistic": te["pp"].to_numpy()}
    res["evaluation"] = evaluate_models(te, c, preds)
    ref_ref = te["home_wp"].to_numpy() if "home_wp" in te else None
    if ref_ref is not None and np.isfinite(ref_ref).all():
        yy = te["y_home"].to_numpy()
        res["evaluation"]["reference_nflverse_wp"] = {"logloss": round(logloss(yy, ref_ref), 5),
                                                      "note": "trained on all seasons incl. these: NOT comparable, a ceiling-style reference"}
    log("permutation importance ...")
    res["permutation_importance"] = permutation_importance(te, all_feats, m1, c)
    if c["ablate_last"]:
        res["ablation"] = ablation(pl, base_feats, all_feats, test_seasons[-c["ablate_last"]:], c, log)
    log("situation scan ...")
    snaps = pick_snapshots(te)
    ref_counts = te.drop_duplicates("game_id")["referee"].value_counts()
    ref_rank = {r: f"R{i + 1:02d}" for i, r in enumerate(ref_counts.index[:25])}
    obs = build_observations(snaps, snaps["pp" if c["scan_model"] == "portable" else "p0"].to_numpy(), ref_rank)
    st, enumerated = scan(obs, "resid", c["min_n"])
    cand = st[st["q"] < ALPHA].sort_values("p")
    details = [describe_cell(obs, row, c) for _, row in cand.iterrows()]
    overlapping = sorted([d for d in details if d["survives"]], key=lambda d: (-abs(d["effect_wp_pts"])))
    survivors = independent_survivors(obs, c)
    res["scan"] = {"observations": int(len(obs)), "cells_enumerated": int(enumerated), "hypotheses_tested": int(len(st)),
                   "min_n": c["min_n"], "bh_alpha": ALPHA, "nominal_p_below_0.05": int((st["p"] < 0.05).sum()),
                   "expected_by_chance_at_0.05": round(0.05 * len(st), 1), "bh_rejected": int(len(cand)),
                   "big_enough": int(sum(d["big_enough"] for d in details)),
                   "stable": int(sum(d["stable"] for d in details)),
                   "survivors": survivors, "n_survivors": len(survivors), "n_survivors_overlapping": len(overlapping),
                   "bh_rejected_not_surviving": [d for d in details if not d["survives"]][:15],
                   "smallest_p_overall": [describe_cell(obs, row, c) for _, row in st.sort_values("p").head(10).iterrows()]}
    log(f"scan: {len(st)} hypotheses tested ({enumerated} cells enumerated), {len(cand)} pass BH at {ALPHA}, "
        f"{len(overlapping)} survive size+stability, {len(survivors)} are independent after explaining away overlaps")
    if c["placebo"]:
        counts = placebo_scan(obs, c, c["placebo"], c["seed"])
        res["scan"]["placebo_bh_rejections_per_rep"] = counts
    log("pre-registered anecdotes ...")
    gtest = gtab[gtab["season"].isin(test_seasons)]
    res["anecdotes"] = run_anecdotes(obs, gtest, c)
    res["decay"] = {"tracked": [{"what": d["label"], **d["decay"], "pooled_effect": d["effect_wp_pts"]} for d in survivors[:15]]
                    + [{"what": a["id"] + " " + a["claim"], **a["decay"], "pooled_effect": a["effect"]}
                       for a in res["anecdotes"] if "decay" in a]}
    res["portable_model_k_spread"] = round(k, 5)
    res["_state"] = {"pl": pl, "gtab": gtab, "k": k}
    res["seconds"] = round(time.time() - t0)
    return res


def ablation(pl, base_feats, all_feats, seasons, c, log):
    """Refit the richer model without one group at a time on the last few seasons: how much held-out log loss each group
    buys. Slower than permutation but not fooled by unrealistic shuffled rows."""
    out = {}
    full_p, _ = walk_forward(pl, all_feats, seasons, c)
    for grp, cols in GROUPS.items():
        log(f"ablation: without {grp}")
        feats = [f for f in all_feats if f not in cols]
        p, _ = walk_forward(pl, feats, seasons, c)
        m = pl["season"].isin(seasons).to_numpy() & ~np.isnan(p) & ~np.isnan(full_p)
        y = pl["y_home"].to_numpy()[m]
        out[grp] = round(logloss(y, p[m]) - logloss(y, full_p[m]), 6)
    return {"seasons": [int(s) for s in seasons], "logloss_increase_without_group": out}


# ------------------------------------------------------------------ report
def render_markdown(res):
    d, ev, sc = res["data"], res["evaluation"], res["scan"]
    L = []
    w = L.append
    w("# NFL discovery: first run (aggregates only)\n")
    w(f"{ATTRIBUTION}\n")
    w(f"- Data: seasons {d['seasons'][0]}-{d['seasons'][1]}, {d['games']:,} games, {d['plays']:,} plays. Held-out (walk-forward) seasons "
      f"{d['test_seasons'][0]}-{d['test_seasons'][1]}: {d['test_games']:,} games, {d['test_plays']:,} plays. Engine: {res['engine']}.")
    w("- Every number below is out of sample: a season is only scored by models trained on seasons that ended at least "
      "two seasons earlier.\n")
    w("## 1. How good is the state-only baseline, and what do the extra facts add?\n")
    w("| Model | Log loss | Brier |\n|---|---|---|")
    for k_, v in ev["models"].items():
        w(f"| {k_} | {v['logloss']} | {v['brier']} |")
    if "reference_nflverse_wp" in ev:
        w(f"\nnflverse's own win probability (trained on all seasons including these, so not a fair comparison): "
          f"log loss {ev['reference_nflverse_wp']['logloss']}.")
    w("\nImprovement in log loss (positive = the second model is better), with a 95% range from resampling whole games:\n")
    w("| Comparison | Gain | 95% range | Seasons better |\n|---|---|---|---|")
    for k_, v in ev["improvement"].items():
        w(f"| {k_} | {v['gain_logloss']:+.5f} | [{v['ci95'][0]:+.5f}, {v['ci95'][1]:+.5f}] | {v['seasons_better']}/{v['seasons']} |")
    w("\nBy phase of the game (log loss):\n")
    names = list(ev["models"])
    w("| Phase | " + " | ".join(names) + " |\n|---|" + "---|" * len(names))
    for ph, v in ev["by_phase"].items():
        w(f"| {ph} | " + " | ".join(str(v[n]) for n in names) + " |")
    w("\nCalibration of the baseline on held-out seasons (predicted home win chance vs what happened):\n")
    w("| Predicted | Plays | Mean predicted | Observed |\n|---|---|---|---|")
    for r in ev["calibration"]["baseline_gbm"]:
        w(f"| {r['bin']} | {r['n']:,} | {r['mean_pred']} | {r['observed']} |")
    w("\n## 2. Which extra facts does the richer model lean on?\n")
    pi = res["permutation_importance"]
    groups = list(GROUPS)
    w("Permutation importance (held-out log loss gets worse by this much when the group is scrambled; mean over "
      "seasons, and how many seasons it is positive):\n")
    w("| Group | Mean | Seasons positive |\n|---|---|---|")
    for g in groups:
        vals = [pi[s][g] for s in pi]
        w(f"| {g} | {sum(vals) / len(vals):+.6f} | {sum(1 for v in vals if v > 0)}/{len(vals)} |")
    if "ablation" in res:
        a = res["ablation"]
        w(f"\nRefit ablation on seasons {a['seasons']} (log loss increase when the group is left out):\n")
        for g, v in a["logloss_increase_without_group"].items():
            w(f"- {g}: {v:+.6f}")
    w("\n## 3. Situation scan (where is the baseline systematically wrong?)\n")
    w(f"- Observations: {sc['observations']:,} (one per game per snapshot clock).")
    w(f"- **Hypotheses tested: {sc['hypotheses_tested']:,}** (cells with at least {sc['min_n']} games, out of {sc['cells_enumerated']:,} enumerated).")
    w(f"- Nominal p < 0.05: {sc['nominal_p_below_0.05']:,} (about {sc['expected_by_chance_at_0.05']:,} expected by pure chance).")
    w(f"- Pass Benjamini-Hochberg at {ALPHA}: {sc['bh_rejected']}; also >= {MIN_EFFECT_WP} win-probability points: {sc['big_enough']}; "
      f"also same sign in >= 70% of seasons: {sc['n_survivors_overlapping']} overlapping survivors, which collapse to "
      f"**{sc['n_survivors']} independent findings** once each found effect is subtracted and everything is rescanned.")
    if "placebo_bh_rejections_per_rep" in sc:
        pc = sc["placebo_bh_rejections_per_rep"]
        w(f"- Placebo check (random sign flips per game, {len(pc)} reps): BH rejections per rep {pc} (should be about 0).")
    w("\n### Independent survivors (in the order they were found; each one is subtracted before looking for the next)\n")
    if sc["survivors"]:
        w("| # | Situation | Games | Effect (WP pts) | 95% range | q | Same sign | Size is not tiny? (heuristic only) | Trend |\n|---|---|---|---|---|---|---|---|---|")
        for i, s in enumerate(sc["survivors"][:25], 1):
            w(f"| {i} | {s['label']} | {s['n']} | {s['effect_wp_pts']:+.1f} | {s['ci95']} | {s['q']:.3g} | {s['same_sign_share']:.0%} of {s['seasons']} | "
              f"{'yes' if s['tradable_size'] else 'no, too small'} | {s['decay']['status']} |")
    else:
        w("None. Nothing both passed the multiple-testing correction and was big and stable enough.")
    w("\n### Strongest first-round cells (before the explain-away rounds; some of these are the survivors above)\n")
    for s in sc["smallest_p_overall"][:6]:
        w(f"- {s['label']}: {s['effect_wp_pts']:+.1f} pts (n={s['n']}), q={s['q']:.3g}, same sign {s['same_sign_share']:.0%} of {s['seasons']} seasons")
    w("\n## 4. Pre-registered sportscaster claims\n")
    w(f"{len(res['anecdotes'])} claims fixed in the code before the first run, one multiple-testing family of their own (BH over {len(res['anecdotes'])}).\n")
    w("| ID | Claim | Games | Effect | 95% range | q | Same sign | Verdict |\n|---|---|---|---|---|---|---|---|")
    for a in res["anecdotes"]:
        if "effect" not in a:
            w(f"| {a['id']} | {a['claim']} | {a['n']} | - | - | - | - | {a['verdict']} |")
            continue
        unit = "WP pts" if a["unit"] == "wp" else "pts vs total"
        w(f"| {a['id']} | {a['claim']} | {a['n']} | {a['effect']:+.2f} {unit} | {a['ci95']} | {a['q']:.3g} | "
          f"{a['same_sign_share']:.0%} of {a['seasons']} | {a['verdict']} |")
    w("\n## 5. Decay tracker (effect by season; retire what fades)\n")
    w("| Tracked effect | Pooled | First half | Last 3 seasons | Trend per season | Status |\n|---|---|---|---|---|---|")
    for t in res["decay"]["tracked"]:
        w(f"| {t['what']} | {t['pooled_effect']:+.2f} | {t['first_half']} | {t['recent']} | {t['slope']} | {t['status']} |")
    w("\nEffect-by-season tables for each tracked item are in the JSON output.")
    return "\n".join(L) + "\n"


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items() if k != "_state"}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


# ------------------------------------------------------------------ synthetic data (tests and --synthetic)
def synthetic_raw(n_seasons=14, games_per_season=270, seed=0, dome_effect=6.0, rest_effect=5.0, first_season=2000):
    """Made-up play-by-play + games in nflverse's column layout with PLANTED truths: home teams in domes are worth
    `dome_effect` more points than the spread says in every season (a stable effect); teams on short rest (5 days or fewer, home or away) are
    `rest_effect` points worse than the spread says but only until the 7th season, fading to nothing by the 11th (a decaying effect); everything
    else (referee, wind) is pure noise. Used to prove the pipeline finds a real effect and not a fake one."""
    _need_data_libs()
    rng = np.random.default_rng(seed)
    T = 120
    g_rows, p_rows = [], []
    teams = [f"T{i:02d}" for i in range(24)]
    refs = [f"Ref {i}" for i in range(6)]
    for si in range(n_seasons):
        season = first_season + si
        for gi in range(games_per_season):
            h, a = rng.choice(len(teams), 2, replace=False)
            gid = f"{season}_{gi:03d}_{teams[a]}_{teams[h]}"
            spread = float(np.round(rng.normal(0, 5.5) * 2) / 2)
            dome = float(rng.random() < 0.3)
            h_rest = float(rng.choice([4, 6, 7, 7, 7, 7, 10, 13]))
            a_rest = float(rng.choice([4, 6, 7, 7, 7, 10, 13]))
            decay = min(1.0, max(0.0, 1.0 - (si - 6) / 4.0))   # full strength through the 7th season, gone 4 seasons later
            mu = spread + dome_effect * dome - rest_effect * decay * (float(h_rest <= 5) - float(a_rest <= 5))
            incr = rng.normal(mu / T, 13.0 / math.sqrt(T), T)
            path = np.cumsum(incr)
            tot = np.round(45.0 * (np.arange(1, T + 1) / T) + rng.normal(0, 0.8, T)).clip(min=0)
            tot = np.maximum.accumulate(tot)
            home = np.round((tot + path) / 2.0)
            away = tot - home
            result = int(home[-1] - away[-1])
            if result == 0:
                result = 1
            wind = float(np.where(dome == 1, np.nan, rng.normal(9, 5)))
            temp = float(np.where(dome == 1, np.nan, rng.normal(55, 15)))
            ref = refs[int(rng.integers(len(refs)))]
            g_rows.append({"game_id": gid, "season": season, "game_type": "REG", "week": gi // 16 + 1,
                           "gameday": f"{season}-09-{1 + gi % 28:02d}", "home_team": teams[h], "away_team": teams[a],
                           "home_score": float(home[-1]), "away_score": float(away[-1]), "result": result, "total": 45,
                           "spread_line": spread, "total_line": 45.0, "home_rest": h_rest, "away_rest": a_rest,
                           "div_game": int(rng.random() < 0.3), "roof": "dome" if dome else "outdoors", "temp": temp,
                           "wind": wind, "location": "Home", "referee": ref,
                           "home_qb_id": f"Q{h}", "away_qb_id": f"Q{a}"})
            drive_home = rng.random() < 0.5
            for k in range(T):
                if rng.random() < 0.12:
                    drive_home = not drive_home
                ph = bool(drive_home)
                pts_h, pts_a = (home[k - 1], away[k - 1]) if k else (0.0, 0.0)   # start-of-play score
                gsr = 3600.0 * (1 - k / T)
                pen = rng.random() < 0.04
                p_rows.append({"game_id": gid, "play_id": float(k + 1), "qtr": float(1 + min(3, int(4 * k / T))),
                               "game_seconds_remaining": gsr, "half_seconds_remaining": gsr % 1800.0,
                               "down": float(rng.integers(1, 5)), "ydstogo": float(rng.integers(1, 15)),
                               "yardline_100": float(rng.integers(1, 99)), "goal_to_go": 0.0,
                               "posteam": teams[h] if ph else teams[a],
                               "posteam_score": pts_h if ph else pts_a, "defteam_score": pts_a if ph else pts_h,
                               "posteam_timeouts_remaining": 3.0, "defteam_timeouts_remaining": 3.0,
                               "play_type": "pass" if rng.random() < 0.58 else "run", "pass_attempt": 0.0, "rush_attempt": 0.0,
                               "penalty": float(pen), "penalty_team": teams[h] if (pen and rng.random() < 0.5) else (teams[a] if pen else None),
                               "penalty_yards": 5.0 if pen else 0.0, "interception": float(rng.random() < 0.015),
                               "fumble_lost": float(rng.random() < 0.01), "home_wp": 0.5})
    plays = pd.DataFrame(p_rows)
    plays["pass_attempt"] = (plays["play_type"] == "pass").astype(float)
    plays["rush_attempt"] = (plays["play_type"] == "run").astype(float)
    return plays, pd.DataFrame(g_rows)


# ------------------------------------------------------------------ command line
def cmd_run(args):
    _need_data_libs()
    cfg = dict(DEFAULT_CFG)
    cfg.update({"test_start": args.test_start, "engine": args.engine, "min_n": args.min_n, "ablate_last": args.ablate_last,
                "placebo": args.placebo, "max_iter": args.max_iter, "scan_model": args.scan_model})
    if args.synthetic:
        plays, games = synthetic_raw()
        cfg.update({"test_start": 2005, "max_iter": 150, "lr": 0.15, "min_n": 60, "min_seasons": 4})
        root = ensure_outside_repo(args.data_dir)
    else:
        root = ensure_outside_repo(args.data_dir)
        plays, games = load_raw(root)
    out = root / ("out_synthetic" if args.synthetic else "out")
    out.mkdir(parents=True, exist_ok=True)
    res = run_pipeline(plays, games, cfg)
    state = res.pop("_state")
    (out / "results.json").write_text(json.dumps(jsonable(res), indent=1))
    md = render_markdown(res)
    (out / "results.md").write_text(md)
    if args.results_md:
        dest = Path(args.results_md)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(md)
    if args.export_model and not args.synthetic:
        doc = export_portable(state["pl"], state["k"], args.export_model, f"seasons {res['data']['seasons'][0]}-{res['data']['seasons'][1]}")
        print("portable model written:", args.export_model, doc["coef"])
    print(md)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", default=str(DATA_ROOT), help="research data folder (outside the repo)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="polite cached download of nflverse play-by-play and games.csv")
    f.add_argument("--first", type=int, default=FIRST_SEASON)
    f.add_argument("--last", type=int, default=None)
    f.add_argument("--force", action="store_true")
    r = sub.add_parser("run", help="run the whole discovery pipeline")
    r.add_argument("--test-start", type=int, default=DEFAULT_CFG["test_start"])
    r.add_argument("--engine", default="auto", choices=["auto", "sklearn", "lightgbm"])
    r.add_argument("--min-n", type=int, default=DEFAULT_CFG["min_n"])
    r.add_argument("--max-iter", type=int, default=DEFAULT_CFG["max_iter"])
    r.add_argument("--ablate-last", type=int, default=0, help="refit-ablation on the last N test seasons (slow)")
    r.add_argument("--placebo", type=int, default=DEFAULT_CFG["placebo"])
    r.add_argument("--results-md", default=None)
    r.add_argument("--scan-model", choices=["gbm", "portable"], default="gbm", help="which baseline the scan measures residuals against")
    r.add_argument("--export-model", default=None, help="write the portable logistic's coefficients to this JSON path")
    r.add_argument("--synthetic", action="store_true")
    args = ap.parse_args(argv)
    return cmd_fetch(args) if args.cmd == "fetch" else cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
