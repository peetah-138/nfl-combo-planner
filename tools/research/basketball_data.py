"""Turn ESPN-derived play-by-play (hoopR / sportsdataverse releases) into one row per game and one row per
(game, minute) "snapshot" for NBA and men's college basketball.  OFFLINE RESEARCH ONLY: reads local parquet files
outside the repo (default ~/dev/research/basketball/raw, see basketball_fetch.py), writes built tables next to them.
Never touches the app, its keys or its history.

Leak rules (every game-level feature is known BEFORE tip-off; every snapshot feature is known at that minute):
  * team rolling form / pace and referee effects use only games on strictly earlier dates (shift(1) after sorting by date)
  * pre-game strength is the market spread (NBA) or ESPN's pre-game win probability (college; it has no market line)
  * pre-game total is the market closing total (NBA, where the closing-lines file has it) or a rolling team proxy
  * the label (home win, final total) is only ever used as the target, never as a feature

Data caveats written down here because they matter: possession is DERIVED from event types (approximate), the free
throw order is unknown in the college feed, and officials / rest days come from the schedule and officials files.
"""
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path(os.environ.get("BBALL_RAW", str(Path.home() / "dev/research/basketball/raw")))
BUILT = Path(os.environ.get("BBALL_BUILT", str(Path.home() / "dev/research/basketball/built")))

# regulation geometry: (periods, seconds per period)
LEAGUES = {"nba": {"nreg": 4, "plen": 720.0, "foul_thr": 4, "bonus_at": 5},
           "mbb": {"nreg": 2, "plen": 1200.0, "foul_thr": 3, "bonus_at": 7}}
OT_LEN = 300.0
SNAP_STEP = 60.0
SHRINK_K = 30.0


def reg_seconds(lg):
    c = LEAGUES[lg]
    return c["nreg"] * c["plen"]


# ------------------------------------------------------------------ event level
def prep_events(p, lg):
    """p = one raw pbp frame (any seasons).  Returns events sorted by game, with elapsed seconds, scores, team fouls,
    player foul-trouble counts, derived possession and the current unanswered run."""
    c = LEAGUES[lg]
    cols = ["game_id", "game_play_number", "type_text", "period_number", "clock_minutes", "clock_seconds", "home_score",
            "away_score", "scoring_play", "score_value", "team_id", "home_team_id", "away_team_id", "athlete_id_1",
            "season", "season_type", "game_spread", "home_favorite", "game_spread_available"]
    if lg == "mbb":
        cols.append("pregame_home_prob")
    p = p[[x for x in cols if x in p.columns]].copy()
    p = p.sort_values(["game_id", "game_play_number"], kind="mergesort").reset_index(drop=True)
    p["period_number"] = p.period_number.fillna(1).astype(int).clip(lower=1)
    per = p.period_number.values
    plen = np.where(per <= c["nreg"], c["plen"], OT_LEN)
    start = np.where(per <= c["nreg"], (per - 1) * c["plen"], c["nreg"] * c["plen"] + (per - c["nreg"] - 1) * OT_LEN)
    clock = (p.clock_minutes.fillna(0).values * 60 + p.clock_seconds.fillna(0).values).clip(0, None)
    el = start + np.clip(plen - clock, 0, plen)
    p["elapsed"] = pd.Series(el).groupby(p.game_id.values).cummax().values
    p["hs"] = p.home_score.fillna(0).astype(float)
    p["as_"] = p.away_score.fillna(0).astype(float)
    g = p.game_id.values
    ishome = (p.team_id.values == p.home_team_id.values)
    isaway = (p.team_id.values == p.away_team_id.values)
    tt = p.type_text.fillna("")

    # ---- fouls
    is_foul = tt.str.contains("Foul", regex=False) & ~tt.str.contains("Technical|Flagrant|Turnover", regex=True)
    if lg == "nba":
        team_foul = is_foul & ~tt.str.contains("Offensive", regex=False)
    else:
        team_foul = is_foul
    if lg == "mbb":  # the college feed repeats some foul rows
        dup = is_foul & p.duplicated(["game_id", "period_number", "clock_minutes", "clock_seconds", "athlete_id_1", "team_id", "type_text"])
        is_foul &= ~dup
        team_foul &= ~dup
    p["tf_h"] = 0
    p["tf_a"] = 0
    for side, mask in (("h", ishome), ("a", isaway)):
        m = (team_foul & mask).astype(int)
        p["tf_" + side] = m.groupby([p.game_id, p.period_number]).cumsum().values
    # player foul trouble: players at/over the threshold, by team
    pf = is_foul & p.athlete_id_1.notna()
    cnt = pf.astype(int).groupby([p.game_id, p.athlete_id_1.fillna(-1)]).cumsum()
    cross = (pf & (cnt == c["foul_thr"])).astype(int)
    for side, mask in (("h", ishome), ("a", isaway)):
        p["ft_" + side] = (cross * mask).groupby(p.game_id).cumsum().values

    # ---- scoring runs
    dh = p.groupby("game_id").hs.diff().fillna(p.hs).clip(lower=0).values
    da = p.groupby("game_id").as_.diff().fillna(p.as_).clip(lower=0).values
    scorer = np.where(dh > 0, 1, np.where(da > 0, -1, 0))
    pts = dh + da
    s = pd.Series(np.where(scorer != 0, scorer, np.nan))
    s_ff = s.groupby(g).ffill()
    # a new run starts when the scorer differs from the previous scorer (within the game)
    prev = s_ff.groupby(g).shift(1)
    newrun = (scorer != 0) & ((prev.isna()) | (prev.values != scorer))
    run_id = pd.Series(newrun.astype(int)).groupby(g).cumsum().values
    run_pts = pd.Series(pts * (scorer != 0)).groupby([g, run_id]).cumsum().values
    sr = np.where(scorer != 0, run_pts * scorer, np.nan)
    p["run"] = pd.Series(sr).groupby(g).ffill().fillna(0).values  # signed: + = home run

    # ---- possession (approximate; +1 home has the ball, -1 away, nan unknown)
    poss = np.full(len(p), np.nan)
    teamsign = np.where(ishome, 1.0, np.where(isaway, -1.0, np.nan))
    made_fg = (p.scoring_play.fillna(False).values.astype(bool)) & ~tt.str.contains("Free", regex=False).values & (scorer != 0)
    poss[made_fg] = -scorer[made_fg]
    poss_d = tt.isin(["Defensive Rebound", "Offensive Rebound", "Steal"]).values & ~np.isnan(teamsign)
    poss[poss_d] = teamsign[poss_d]
    to = tt.str.contains("Turnover", regex=False).values & ~np.isnan(teamsign)
    poss[to] = -teamsign[to]
    if lg == "nba":
        lastft = tt.str.extract(r"Free Throw - (\d) of (\d)")
        lastft_m = (lastft[0] == lastft[1]).values & (scorer != 0)
        poss[lastft_m] = -scorer[lastft_m]
    p["poss"] = pd.Series(poss).groupby(g).ffill().fillna(0).values
    return p


def final_scores(ev):
    last = ev.groupby("game_id").agg(h=("hs", "max"), a=("as_", "max"), n=("elapsed", "size"), el=("elapsed", "max"))
    return last


# ------------------------------------------------------------------ game level
def load_schedule(lg, seasons):
    fr = []
    for y in seasons:
        f = RAW / lg / f"sched_{y}.parquet"
        if f.exists():
            fr.append(pd.read_parquet(f, columns=["game_id", "season", "season_type", "game_date", "neutral_site", "home_id", "away_id",
                                                   "home_score", "away_score", "home_winner", "status_type_completed"]))
    s = pd.concat(fr, ignore_index=True)
    s = s[s.status_type_completed.fillna(False).astype(bool)].drop_duplicates("game_id")
    s["date"] = pd.to_datetime(s.game_date)
    return s


def rest_table(s):
    """days since each team's previous game (game_date is already the US Eastern calendar date), 7 cap."""
    long = pd.concat([s[["game_id", "date", "home_id"]].rename(columns={"home_id": "team"}).assign(side="h"),
                      s[["game_id", "date", "away_id"]].rename(columns={"away_id": "team"}).assign(side="a")])
    long = long.sort_values(["team", "date", "game_id"])
    prev = long.groupby("team").date.shift(1)
    long["rest"] = ((long.date - prev).dt.days).clip(upper=7).fillna(7)
    out = long.pivot(index="game_id", columns="side", values="rest")
    out.columns = ["rest_" + c for c in out.columns]
    return out.reset_index()


def team_form(s):
    """leak-free rolling points for / against over a team's previous 15 games (needs 5)."""
    h = pd.DataFrame({"game_id": s.game_id, "date": s.date, "team": s.home_id, "pf": s.home_score, "pa": s.away_score})
    a = pd.DataFrame({"game_id": s.game_id, "date": s.date, "team": s.away_id, "pf": s.away_score, "pa": s.home_score})
    long = pd.concat([h.assign(side="h"), a.assign(side="a")]).sort_values(["team", "date", "game_id"])
    for c in ("pf", "pa"):
        long[c + "_r"] = long.groupby("team")[c].transform(lambda x: x.shift(1).rolling(15, min_periods=5).mean())
    long["n_prior"] = long.groupby("team").cumcount()
    w = long.pivot(index="game_id", columns="side", values=["pf_r", "pa_r", "n_prior"])
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w.reset_index()
    # expected total proxy: each side's scoring blended with the other's conceded
    w["pre_total_proxy"] = (w.pf_r_h + w.pa_r_a) / 2 + (w.pf_r_a + w.pa_r_h) / 2
    w["pace_prior_h"] = w.pf_r_h + w.pa_r_h
    w["pace_prior_a"] = w.pf_r_a + w.pa_r_a
    return w[["game_id", "pre_total_proxy", "pace_prior_h", "pace_prior_a", "n_prior_h", "n_prior_a"]]


def crew_effects(off, games):
    """Leak-free referee-crew features.  games: game_id, date, dev (final total minus pre total, NaN allowed), fouls.
    Each official's shrunk average over STRICTLY EARLIER dates; a crew is the mean of its officials."""
    o = off.merge(games[["game_id", "date", "dev", "fouls"]], on="game_id", how="inner")
    o = o.sort_values(["official_full_name", "date", "game_id"])
    # league mean fouls over earlier dates only
    daily = games.groupby("date").fouls.agg(["sum", "count"]).sort_index()
    cum = daily.cumsum().shift(1)
    lm = (cum["sum"] / cum["count"]).rename("lm_fouls")
    o = o.merge(lm, left_on="date", right_index=True, how="left")
    o["lm_fouls"] = o.lm_fouls.fillna(games.fouls.mean())  # first days only; irrelevant after a few weeks
    grp = o.groupby("official_full_name")
    for src, nm in (("dev", "d"), ("fouls", "f")):
        v = o[src]
        ok = v.notna().astype(int)
        o["_c" + nm] = ok.groupby(o.official_full_name).cumsum().groupby(o.official_full_name).shift(1).fillna(0)
        o["_s" + nm] = v.fillna(0).groupby(o.official_full_name).cumsum().groupby(o.official_full_name).shift(1).fillna(0)
    del grp
    o["crew_dev_o"] = o._sd / (o._cd + SHRINK_K)  # shrunk toward 0 (no effect)
    o["crew_fouls_o"] = (o._sf + SHRINK_K * o.lm_fouls) / (o._cf + SHRINK_K) - o.lm_fouls
    return o.groupby("game_id").agg(crew_dev=("crew_dev_o", "mean"), crew_fouls=("crew_fouls_o", "mean"),
                                    crew_n=("official_full_name", "size")).reset_index()


def sign_check(games):
    """pre_margin must correlate positively with the home margin: guards the spread sign convention."""
    ok = games.dropna(subset=["pre_margin"])
    return float(np.corrcoef(ok.pre_margin, ok.home_margin)[0, 1]) if len(ok) > 50 else float("nan")


# ------------------------------------------------------------------ snapshots
def snapshots(ev, lg):
    """One row per game per SNAP_STEP of regulation, at the state of the last event at or before that time."""
    T = reg_seconds(lg)
    gids, first = np.unique(ev.game_id.values, return_index=True)
    gcodes = np.searchsorted(gids, ev.game_id.values)
    nsnap = int(T // SNAP_STEP) - 1
    ts = np.arange(1, nsnap + 1) * SNAP_STEP
    sg = np.repeat(np.arange(len(gids)), nsnap)
    st = np.tile(ts, len(gids))
    key_ev = gcodes * 1e6 + ev.elapsed.values
    arr = {k: ev[k].values for k in ("hs", "as_", "tf_h", "tf_a", "ft_h", "ft_a", "run", "poss", "period_number")}

    def lookup(tq):
        idx = np.searchsorted(key_ev, sg * 1e6 + tq, side="right") - 1
        ok = (idx >= 0) & (gcodes[np.clip(idx, 0, None)] == sg)
        return np.where(ok, idx, -1)
    i0 = lookup(st)
    i5 = lookup(np.maximum(st - 300.0, 0))
    i10 = lookup(np.maximum(st - 600.0, 0))

    def pick(name, idx, default=0.0):
        a = arr[name]
        return np.where(idx >= 0, a[np.clip(idx, 0, None)], default)
    hs, as_ = pick("hs", i0), pick("as_", i0)
    c = LEAGUES[lg]
    cur_p = np.minimum(st // c["plen"], c["nreg"] - 1).astype(int) + 1  # snapshot's own period (regulation)
    evp = pick("period_number", i0, 1)
    same = evp == cur_p  # the period's foul counters only apply if the last event is inside this period
    snap = pd.DataFrame({
        "game_id": gids[sg], "t": st, "tl": T - st, "period": cur_p,
        "home_pts": hs, "away_pts": as_, "margin": hs - as_,
        "poss": pick("poss", i0),
        "tf_h": np.where(same, pick("tf_h", i0), 0), "tf_a": np.where(same, pick("tf_a", i0), 0),
        "ft_h": pick("ft_h", i0), "ft_a": pick("ft_a", i0),
        "run": pick("run", i0),
        "mchg5": (hs - as_) - (pick("hs", i5) - pick("as_", i5)),
        "mchg10": (hs - as_) - (pick("hs", i10) - pick("as_", i10)),
    })
    snap["total_pts"] = snap.home_pts + snap.away_pts
    snap["pace_pts"] = snap.total_pts / snap.t * 60.0  # points per minute so far
    # bonus: the opponent's team fouls in this period at/over the threshold (home shoots when AWAY is in bonus)
    snap["bonus_h"] = (snap.tf_a >= c["bonus_at"]).astype(int)  # home gets free throws
    snap["bonus_a"] = (snap.tf_h >= c["bonus_at"]).astype(int)
    return snap


# ------------------------------------------------------------------ driver
def build(lg, seasons, force=False):
    BUILT.mkdir(parents=True, exist_ok=True)
    fg, fs = BUILT / f"{lg}_games.parquet", BUILT / f"{lg}_snaps.parquet"
    if fg.exists() and fs.exists() and not force:
        return pd.read_parquet(fg), pd.read_parquet(fs)
    sched = load_schedule(lg, seasons)
    form = team_form(sched)
    rest = rest_table(sched)
    snaps_all, games_all = [], []
    for y in seasons:
        f = RAW / lg / f"pbp_{y}.parquet"
        if not f.exists():
            continue
        ev = prep_events(pd.read_parquet(f), lg)
        ev = ev[ev.season_type.isin([2, 3])]
        fin = final_scores(ev)
        g0 = ev.groupby("game_id").agg(season=("season", "first"), season_type=("season_type", "first"),
                                       spread=("game_spread", "first"), home_fav=("home_favorite", "first"),
                                       spread_ok=("game_spread_available", "first"),
                                       pgp=("pregame_home_prob", "first") if lg == "mbb" else ("season", "first"),
                                       fouls=("tf_h", "size"))
        if lg == "mbb":
            g0["pre_margin"] = np.nan
        else:
            g0["pre_margin"] = np.where(g0.spread_ok.fillna(False).astype(bool), np.where(g0.home_fav.fillna(True), 1.0, -1.0) * g0.spread, np.nan)
        # total fouls per game from the events (counted again below)
        fl = ev[ev.type_text.fillna("").str.contains("Foul", regex=False)].groupby("game_id").size()
        g0["fouls"] = fl.reindex(g0.index).fillna(0).values
        g0 = g0.join(fin)
        g0 = g0.reset_index().merge(sched[["game_id", "date", "neutral_site", "home_id", "away_id", "home_score", "away_score"]], on="game_id", how="inner")
        # quality: the play-by-play must end at the schedule's final score and cover regulation
        bad_score = (g0.h != g0.home_score) | (g0.a != g0.away_score)
        short = g0.el < reg_seconds(lg) - 120
        # the NBA All-Star game (and similar exhibitions) is not a real contest: drop impossible totals
        bad_score = bad_score | ((g0.home_score + g0.away_score) > (330 if lg == "nba" else 280))
        g0["ok"] = ~(bad_score | short)
        g0["drop_score"], g0["drop_short"] = bad_score, short
        games_all.append(g0)
        keep = set(g0.loc[g0.ok, "game_id"])
        evk = ev[ev.game_id.isin(keep)]
        sn = snapshots(evk, lg)
        sn["season"] = y
        snaps_all.append(sn)
    games = pd.concat(games_all, ignore_index=True)
    dropped = games[~games.ok][["season", "drop_score", "drop_short"]].groupby("season").sum()
    games = games[games.ok].copy()
    games["home_win"] = (games.home_score > games.away_score).astype(int)
    games["home_margin"] = games.home_score - games.away_score
    games["final_total"] = games.home_score + games.away_score
    games["went_ot"] = (games.el > reg_seconds(lg) + 1).astype(int)
    games = games.merge(rest, on="game_id", how="left").merge(form, on="game_id", how="left")
    # pre-game strength / total
    if lg == "nba":
        cl = pd.read_parquet(RAW / "nba_closing_lines.parquet", columns=["game_id", "over_under", "home_point"]).drop_duplicates("game_id")
        games = games.merge(cl, on="game_id", how="left")
        # the closing-lines file is the primary spread; its home_point is the home handicap, so margin = -home_point.
        # The play-by-play spread field is only trusted where it agrees with the final margin; for 2019 it does not
        # (correlation about -0.2, a sign/definition problem), so 2019 has no usable pre-game line and is excluded.
        games["pre_margin"] = np.where(games.home_point.notna(), -games.home_point, games.pre_margin)
        games.loc[(games.season == 2019) & games.home_point.isna(), "pre_margin"] = np.nan
        games["pre_total"] = games.over_under
        games["pre_total_src"] = np.where(games.pre_total.notna(), "market", "none")
    else:
        pgp = games.pgp.astype(float).clip(0.01, 0.99)
        # ESPN pre-game win probability expressed as an approximate point margin (college margin sd ~ 11)
        z = np.sqrt(2) * _erfinv(2 * pgp.values - 1)
        games["pre_margin"] = z * 11.0
        games["pre_total"] = games.pre_total_proxy
        games["pre_total_src"] = "proxy"
    games["dev"] = games.final_total - games.pre_total
    # crew effects
    offs = []
    for y in seasons:
        f = RAW / lg / f"off_{y}.parquet"
        if f.exists():
            offs.append(pd.read_parquet(f, columns=["game_id", "official_full_name"]))
    off = pd.concat(offs).dropna().drop_duplicates()
    crew = crew_effects(off, games)
    games = games.merge(crew, on="game_id", how="left")
    games["neutral"] = games.neutral_site.fillna(False).astype(int)
    games["is_post"] = (games.season_type == 3).astype(int)
    games["date"] = pd.to_datetime(games.date)
    keepc = ["game_id", "season", "date", "season_type", "is_post", "neutral", "home_id", "away_id", "home_score", "away_score",
             "home_win", "home_margin", "final_total", "went_ot", "pre_margin", "pre_total", "pre_total_src", "rest_h", "rest_a",
             "pace_prior_h", "pace_prior_a", "n_prior_h", "n_prior_a", "crew_dev", "crew_fouls", "crew_n", "fouls"]
    games = games[keepc]
    sn = pd.concat(snaps_all, ignore_index=True)
    sn = sn.merge(games[["game_id", "home_win", "home_margin", "final_total", "went_ot", "pre_margin", "pre_total", "pre_total_src",
                         "rest_h", "rest_a", "neutral", "is_post", "pace_prior_h", "pace_prior_a", "crew_dev", "crew_fouls"]], on="game_id", how="inner")
    for c in sn.columns:
        if sn[c].dtype == np.float64:
            sn[c] = sn[c].astype(np.float32)
    games.to_parquet(fg)
    sn.to_parquet(fs)
    games.attrs["dropped"] = dropped
    return games, sn


def _erfinv(y):
    """inverse error function (Winitzki approximation refined by two Newton steps); numpy only."""
    y = np.clip(np.asarray(y, dtype=float), -0.999999, 0.999999)
    a = 0.147
    ln = np.log(1 - y * y)
    t = 2 / (np.pi * a) + ln / 2
    x = np.sign(y) * np.sqrt(np.sqrt(t * t - ln / a) - t)
    for _ in range(2):
        err = np.array([math.erf(v) for v in x]) - y
        x = x - err / (2 / np.sqrt(np.pi) * np.exp(-x * x))
    return x


if __name__ == "__main__":
    import sys
    lg = sys.argv[1]
    yrs = list(range(2019, 2027))
    g, s = build(lg, yrs, force=True)
    print(lg, "games", len(g), "snaps", len(s))
    print("sign check pre_margin vs margin: %.3f" % sign_check(g))
    print(g.attrs.get("dropped"))
    print(g.groupby("season").agg(n=("game_id", "size"), pm=("pre_margin", lambda x: x.notna().mean()), pt=("pre_total", lambda x: x.notna().mean()),
                                  crew=("crew_dev", lambda x: x.notna().mean()), ot=("went_ot", "mean")))
