#!/usr/bin/env python3
"""Does bad weather predict NFL totals / yards / kicking better than Kalshi's price? (research only, no trading)

Offline. Public key-free endpoints only (Kalshi public market data, Iowa Environmental Mesonet ASOS, public domain).
No keys, no orders, never touches the planner. Pre-registration and results live in
~/dev/research/nfl-weather/RESULT.md (local only). Subcommands:

  weather   fetch IEM ASOS (wind, temp, precip) for the outdoor stadiums' nearest airports (<= 1 request/s)
  fetch     list + 1-minute candles for the selected Kalshi markets (<= 1 request/s, resumable cache)
  analyze   Part A (plain effect vs sportsbook line, big sample) and Part B (net-of-fee Kalshi backtest)

Run with the research venv:  ~/dev/research/venv-nfl/bin/python -I tools/research/nfl_weather.py <cmd>
"""
import argparse
import csv
import datetime as dt
import gzip
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

API = "https://api.elections.kalshi.com/trade-api/v2"
IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
UA = "nfl-weather-research/1.0 (offline research; public data only; <=1 req/s)"
GAP_S = 1.1
ROOT = Path.home() / "dev" / "research" / "nfl-weather"
NFLV = Path.home() / "dev" / "research" / "nfl" / "raw"
ERA_START = "2025-08-01"
FEE_RATE = 0.07
ORDER_N = 10
BOOT = 10000
SEED = 11
ENTRY_BEFORE_KICK_S = 1800
LAG_S = 60
STALE_S = 7200
WIND_MPH, COLD_F, PRECIP_IN = 15.0, 32.0, 0.01
ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# nearest airport (ICAO without the K for IEM) for each outdoor home stadium
STATIONS = {
    "BAL": "BWI", "BUF": "BUF", "CAR": "CLT", "CHI": "MDW", "CIN": "LUK", "CLE": "CLE", "DAL": "DFW",
    "DEN": "DEN", "GB": "GRB", "HOU": "IAH", "IND": "IND", "JAX": "JAX", "KC": "MKC", "LA": "LAX", "LAC": "LAX",
    "MIA": "MIA", "NE": "BOS", "NYG": "EWR", "NYJ": "EWR", "PHI": "PHL", "PIT": "PIT", "SEA": "SEA",
    "SF": "SJC", "TB": "TPA", "TEN": "BNA", "WAS": "DCA", "ARI": "PHX", "ATL": "ATL", "DET": "DTW", "LV": "LAS",
    "MIN": "MSP", "NO": "MSY",
}
# series -> (subject rule, strikes kept per subject, subjects kept per event or None, bet side, flag used)
TYPES = {
    "B1_total": ("KXNFLTOTAL", 2, None, "under", "BAD"),
    "B2_passyds": ("KXNFLPASSYDS", 2, None, "under", "BAD"),
    "B3_rushyds": ("KXNFLRSHYDS", 1, 4, "over", "BAD"),
    "B4_recyds": ("KXNFLRECYDS", 1, 4, "under", "BAD"),
    "B5_teamyds": ("KXNFLTEAMYDS", 2, None, "under", "BAD"),
    "B6_teamfg": ("KXNFLFG", 2, None, "under", "WIND"),
    "B7_teampts": ("KXNFLTEAMTOTAL", 2, None, "under", "BAD"),
}


def check_id(x):
    if not isinstance(x, str) or not ID_RE.match(x) or ".." in x:
        raise ValueError("unsafe identifier: %r" % (x,))
    return x


# ----------------------------------------------------------------------------------------------- polite client
class Http:
    def __init__(self):
        self.last, self.n, self.backoffs = 0.0, 0, 0

    def get(self, url, tries=6, text=False):
        delay = 5.0
        for a in range(tries):
            w = GAP_S - (time.monotonic() - self.last)
            if w > 0:
                time.sleep(w)
            self.last = time.monotonic()
            self.n += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    b = r.read().decode()
                    return b if text else json.loads(b)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code in (429, 500, 502, 503, 504) and a < tries - 1:
                    self.backoffs += 1
                    time.sleep(delay)
                    delay = min(delay * 2, 300)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError):
                if a < tries - 1:
                    self.backoffs += 1
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise


def write_gz(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt") as f:
        json.dump(obj, f, separators=(",", ":"))


def read_gz(p):
    with gzip.open(p, "rt") as f:
        return json.load(f)


# ----------------------------------------------------------------------------------------------- games
def norm_team(t):
    return t.replace("JAC", "JAX").replace("LAR", "LA")


def era_games():
    """Kalshi-era outdoor games from nflverse with a UTC kickoff; keyed for event-ticker matching."""
    out = []
    for r in csv.DictReader(open(NFLV / "games.csv")):
        if r["gameday"] < ERA_START or r["roof"] not in ("outdoors", "open"):
            continue
        hh, mm = (r["gametime"] or "13:00").split(":")
        d = dt.datetime.fromisoformat(r["gameday"]).replace(hour=int(hh), minute=int(mm), tzinfo=ZoneInfo("America/New_York"))
        r["kick"] = int(d.timestamp())
        out.append(r)
    return out


def event_game(event, games_by_key):
    t = event.split("-")[1]
    d = dt.datetime.strptime(t[:7], "%y%b%d").date()
    for dd in (d, d - dt.timedelta(days=1)):
        g = games_by_key.get((dd.isoformat(), norm_team(t[7:])))
        if g:
            return g
    return None


def games_index(games):
    return {(g["gameday"], g["away_team"] + g["home_team"]): g for g in games}


# ----------------------------------------------------------------------------------------------- weather (IEM)
def cmd_weather(a):
    games = era_games()
    stations = sorted({STATIONS[g["home_team"]] for g in games if g["home_team"] in STATIONS})
    h = Http()
    d0, d1 = ERA_START, (dt.date.today() + dt.timedelta(days=1)).isoformat()
    for st in stations:
        f = ROOT / "wx" / (st + ".csv")
        if f.exists():
            continue
        q = {"station": st, "data": ["tmpf", "sknt", "p01i"], "tz": "UTC", "format": "onlycomma", "latlon": "no",
             "missing": "M", "trace": "T", "report_type": ["3", "4"],
             "year1": d0[:4], "month1": d0[5:7], "day1": d0[8:10], "year2": d1[:4], "month2": d1[5:7], "day2": d1[8:10]}
        url = IEM + "?" + urllib.parse.urlencode(q, doseq=True)
        body = h.get(url, text=True)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body or "")
        print("wx", st, len((body or "").splitlines()), "lines")


def read_wx(st):
    f = ROOT / "wx" / (st + ".csv")
    rows = []
    if not f.exists():
        return rows
    for r in csv.DictReader(open(f)):
        try:
            t = int(dt.datetime.strptime(r["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc).timestamp())
        except (KeyError, ValueError):
            continue

        def num(k):
            try:
                return 0.0001 if r[k] == "T" else float(r[k])
            except (KeyError, ValueError):
                return None
        rows.append((t, num("tmpf"), num("sknt"), num("p01i")))
    return sorted(rows, key=lambda r: r[0])


def game_weather(g, cache):
    """Observed weather in [kick-30min, kick+3h]: mean sustained wind (mph), temp nearest kickoff, precip inches
    (sum over clock hours of the max hourly p01i). None when no observation."""
    st = STATIONS.get(g["home_team"])
    if not st:
        return None
    if st not in cache:
        cache[st] = read_wx(st)
    k = g["kick"]
    win = [r for r in cache[st] if k - 1800 <= r[0] <= k + 3 * 3600]
    if not win:
        return None
    winds = [r[2] * 1.15078 for r in win if r[2] is not None]
    temps = [(abs(r[0] - k), r[1]) for r in win if r[1] is not None]
    hourly = {}
    for r in win:
        if r[3] is not None:
            hourly[r[0] // 3600] = max(hourly.get(r[0] // 3600, 0.0), r[3])
    if not winds or not temps:
        return None
    w, tmp, p = sum(winds) / len(winds), min(temps)[1], sum(hourly.values())
    f = {"wind": w, "temp": tmp, "precip": p}
    f["WIND"], f["COLD"], f["PRECIP"] = w >= WIND_MPH, tmp <= COLD_F, p >= PRECIP_IN
    f["BAD"] = f["WIND"] or f["COLD"] or f["PRECIP"]
    return f


# ----------------------------------------------------------------------------------------------- Kalshi lists + candles
def list_series(h, series):
    f = ROOT / "cache" / "lists" / (series + ".json.gz")
    if f.exists():
        return read_gz(f)
    raise SystemExit("list for %s missing: run the list step (cache/lists) first" % series)


def subject_of(sub):
    sub = sub or ""
    if ":" in sub:
        return sub.split(":")[0].strip()
    m = re.match(r"^(.*?) over ", sub)
    return m.group(1) if m else "game"


def select_markets(rows, nstrike, nsubj):
    """Per event: keep top subjects (by volume) if nsubj, and per subject the nstrike highest-volume 'over' strikes.
    Volume only: no prices are used to choose."""
    by_ev = {}
    for m in rows:
        if m.get("strike") not in ("greater", "greater_or_equal") or not m.get("close"):
            continue
        by_ev.setdefault(m["event"], {}).setdefault(subject_of(m["sub"]), []).append(m)
    sel = []
    for ev, subs in by_ev.items():
        order = sorted(subs, key=lambda s: -sum(x["vol"] for x in subs[s]))
        for s in (order[:nsubj] if nsubj else order):
            sel += sorted(subs[s], key=lambda x: -x["vol"])[:nstrike]
    return sel


def candle_file(t):
    return ROOT / "cache" / "candles" / (check_id(t) + ".json.gz")


def fetch_candle(h, m):
    f = candle_file(m["ticker"])
    if f.exists():
        return
    end = m["close"] + 120
    start = max(m["open"] or 0, end - 36 * 3600)
    t = urllib.parse.quote(check_id(m["ticker"]), safe="")
    path = ("/historical/markets/%s/candlesticks" % t if m.get("route") == "hist"
            else "/series/%s/markets/%s/candlesticks" % (urllib.parse.quote(check_id(m["series"]), safe=""), t))
    d = h.get(API + path + "?" + urllib.parse.urlencode({"start_ts": start, "end_ts": end, "period_interval": 1}))
    if d is None:
        write_gz(f, {"rows": [], "empty": True})
        return
    if not isinstance(d, dict) or not isinstance(d.get("candlesticks"), list):
        return

    def px(x, k):
        v = (x or {}).get(k)
        v = v if v is not None else (x or {}).get(k + "_dollars")
        try:
            return None if v in (None, "") else int(round(float(v) * 10000))
        except (TypeError, ValueError):
            return None
    write_gz(f, {"rows": [[c.get("end_period_ts"), px(c.get("yes_bid"), "close"), px(c.get("yes_ask"), "close")]
                          for c in d["candlesticks"]]})


def wanted_markets():
    games = era_games()
    gk = games_index(games)
    cache, out = {}, []
    for name, (series, nst, nsu, side, flag) in TYPES.items():
        rows = list_series(None, series)
        for m in select_markets(rows, nst, nsu):
            g = event_game(m["event"], gk)
            if not g:
                continue
            w = game_weather(g, cache)
            if w is None:
                continue
            out.append((name, m, g, w))
    return out


def cmd_fetch(a):
    h = Http()
    todo = [x for x in wanted_markets() if not candle_file(x[1]["ticker"]).exists()]
    if a.only:
        todo = [x for x in todo if x[0] == a.only]
    print("candles to fetch:", len(todo))
    for i, (name, m, g, w) in enumerate(todo, 1):
        fetch_candle(h, m)
        if i % 100 == 0:
            print("  %d/%d (%d requests, %d back-offs)" % (i, len(todo), h.n, h.backoffs), flush=True)
    print("done:", h.n, "requests", h.backoffs, "back-offs")


# ----------------------------------------------------------------------------------------------- scoring
def fee_cents(n, p):
    return math.ceil(round(100.0 * FEE_RATE * n * p * (1 - p), 6))


def quote_at(rows, t):
    best = None
    for ts, b, a in rows:
        if ts is None or ts > t:
            break
        if b is not None and a is not None:
            best = (ts, b, a)
    if best and t - best[0] <= STALE_S:
        return best[1] / 10000.0, best[2] / 10000.0
    return None


def bet(m, side, kick, lag, n):
    """Return (stake, net) in dollars for one contract-equivalent, or None. Buys at the ASK of the side held."""
    f = candle_file(m["ticker"])
    if not f.exists():
        return None
    rows = read_gz(f)["rows"]
    q = quote_at(rows, kick - ENTRY_BEFORE_KICK_S + lag)
    if not q:
        return None
    bid, ask = q
    p = ask if side == "over" else 1 - bid
    if p >= 0.99 or p <= 0.01 or ask <= bid - 1e-9 and False:
        return None
    win = (m["result"] == "yes") if side == "over" else (m["result"] == "no")
    fee = fee_cents(n, p) / 100.0 / n
    return p + fee, (1.0 if win else 0.0) - p - fee


def pick_bets(markets, side, lag, n):
    """markets: [(m, g)] for one event/game. One bet per subject: the strike whose mid is closest to 50c."""
    best = {}
    for m, g in markets:
        q = quote_at(read_gz(candle_file(m["ticker"]))["rows"], g["kick"] - ENTRY_BEFORE_KICK_S + lag) \
            if candle_file(m["ticker"]).exists() else None
        if not q:
            continue
        key = (m["event"], subject_of(m["sub"]))
        d = abs((q[0] + q[1]) / 2 - 0.5)
        if key not in best or d < best[key][0]:
            best[key] = (d, m, g)
    out = []
    for _, m, g in best.values():
        r = bet(m, side, g["kick"], lag, n)
        if r:
            out.append((g["game_id"], g["season"], g["kick"], r[0], r[1]))
    return out


def boot_ratio(bets, rnd, reps=BOOT):
    """Game-cluster bootstrap of sum(net)/sum(stake). Returns (point, [draws])."""
    by = {}
    for gid, _, _, st, net in bets:
        s = by.setdefault(gid, [0.0, 0.0])
        s[0] += net
        s[1] += st
    arr = list(by.values())
    if not arr:
        return None, []
    import numpy as np
    a = np.array(arr)
    pt = a[:, 0].sum() / a[:, 1].sum()
    idx = rnd.integers(0, len(a), size=(reps, len(a)))
    s0, s1 = a[idx, 0].sum(1), a[idx, 1].sum(1)
    return pt, (s0 / s1)


def cmd_analyze(a):
    import numpy as np
    rnd = np.random.default_rng(SEED)
    out = {"partA": part_a(rnd), "partB": {}}
    games = era_games()
    gk = games_index(games)
    cache = {}
    wx = {g["game_id"]: game_weather(g, cache) for g in games}
    k = len(TYPES)
    alpha = 0.05 / k
    for name, (series, nst, nsu, side, flag) in TYPES.items():
        rows = list_series(None, series)
        sel = select_markets(rows, nst, nsu)
        have, per_game = 0, {}
        for m in sel:
            g = event_game(m["event"], gk)
            if not g or wx.get(g["game_id"]) is None or not candle_file(m["ticker"]).exists():
                continue
            have += 1
            per_game.setdefault(g["game_id"], []).append((m, g))
        res = {"markets_with_candles": have, "games_with_data": len(per_game), "side": side, "flag": flag}
        if not per_game:
            out["partB"][name] = res
            continue
        order = sorted(per_game, key=lambda gid: per_game[gid][0][1]["kick"])
        cut = int(len(order) * 0.7)
        fit_ids, test_ids = set(order[:cut]), order[cut:]
        half = len(test_ids) // 2
        halves = (set(test_ids[:half]), set(test_ids[half:]))
        test_ids = set(test_ids)

        def run(ids, bad, lag=LAG_S, n=ORDER_N):
            bets = []
            for gid in ids:
                if wx[gid][flag] == bad:
                    bets += pick_bets(per_game[gid], side, lag, n)
            return bets
        for label, ids in (("fit", fit_ids), ("test", test_ids)):
            bets = run(ids, True)
            pt, d = boot_ratio(bets, rnd)
            res[label] = {"bad_games": len({b[0] for b in bets}), "fills": len(bets), "net_per_$": pt,
                          "lo_bonf": float(np.quantile(d, alpha)) if len(d) else None,
                          "lo_95": float(np.quantile(d, 0.05)) if len(d) else None}
        tb = run(test_ids, True)
        tg = run(test_ids, False)
        res["test_good_baseline"] = {"fills": len(tg), "net_per_$": (boot_ratio(tg, rnd)[0])}
        res["test_halves"] = [(boot_ratio(run(h_, True), rnd)[0], len({b[0] for b in run(h_, True)})) for h_ in halves]
        res["test_seasons"] = {}
        for s in sorted({b[1] for b in tb}):
            res["test_seasons"][s] = boot_ratio([b for b in tb if b[1] == s], rnd)[0]
        res["test_no_lag"] = boot_ratio(run(test_ids, True, lag=0), rnd)[0]
        res["test_n1"] = boot_ratio(run(test_ids, True, n=1), rnd)[0]
        # beats baseline: difference of ratios, game-cluster bootstrap within each group
        p1, d1 = boot_ratio(tb, rnd)
        p0, d0 = boot_ratio(tg, rnd)
        if d1 is not None and len(d1) and len(d0):
            diff = d1 - d0[rnd.permutation(len(d0))]
            res["bad_minus_good"] = {"point": p1 - p0, "lo_95": float(np.quantile(diff, 0.05))}
        # drop the 5 biggest-winning bad games
        byg = {}
        for b in tb:
            byg[b[0]] = byg.get(b[0], 0) + b[4]
        top = set(sorted(byg, key=lambda x: -byg[x])[:5])
        res["test_drop_top5"] = boot_ratio([b for b in tb if b[0] not in top], rnd)[0]
        # secondary: each flag separately for this side (descriptive)
        sec = {}
        for fl in ("WIND", "COLD", "PRECIP"):
            bets = []
            for gid in (fit_ids | test_ids):
                if wx[gid][fl]:
                    bets += pick_bets(per_game[gid], side, LAG_S, ORDER_N)
            sec[fl] = {"games": len({b[0] for b in bets}), "net_per_$": boot_ratio(bets, rnd)[0]}
        res["secondary_flags_fit+test"] = sec
        t = res["test"]
        ok = (t["net_per_$"] is not None and t["net_per_$"] > 0 and t["lo_bonf"] is not None and t["lo_bonf"] > 0
              and all(x[0] is not None and x[0] > 0 for x in res["test_halves"])
              and t["bad_games"] >= 30 and t["fills"] >= 100
              and res.get("test_drop_top5") is not None and res["test_drop_top5"] > 0
              and res.get("bad_minus_good", {}).get("lo_95", -1) > 0.01 * 0 and res["bad_minus_good"]["point"] >= 0.01
              and (res["test_no_lag"] or -1) > 0 and (res["test_n1"] or -1) > 0
              and res["fit"]["net_per_$"] is not None and res["fit"]["net_per_$"] > 0)
        res["verdict"] = ("PASS" if ok else ("INCONCLUSIVE (too few bad-weather test games)" if t["bad_games"] < 30 else "FAIL"))
        out["partB"][name] = res
    (ROOT / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))


# ----------------------------------------------------------------------------------------------- Part A
def part_a(rnd):
    """Plain effect over 2006-2026 outdoor games with a sportsbook closing total, nflverse temp/wind."""
    import numpy as np
    import pandas as pd
    g = pd.read_csv(NFLV / "games.csv", low_memory=False)
    g = g[(g.season >= 2006) & g.roof.isin(["outdoors", "open"]) & g.total_line.notna() & g.total.notna()
          & g.wind.notna() & g.temp.notna()].copy()
    g["resid"] = g.total - g.total_line
    g["WIND"], g["COLD"] = g.wind >= WIND_MPH, g.temp <= COLD_F
    g["BAD"] = g.WIND | g.COLD
    out = {"games": int(len(g)), "seasons": f"{g.season.min()}-{g.season.max()}"}
    ps = []
    for f in ("WIND", "COLD", "BAD"):
        bad, good = g[g[f]], g[~g[f]]

        def bs(x):
            v = x.resid.values
            return v[rnd.integers(0, len(v), size=(BOOT, len(v)))].mean(1)
        db = bs(bad)
        diff = db - bs(good)
        p = float(min(1.0, 2 * min((diff >= 0).mean(), (diff <= 0).mean())))
        ps.append((f, p))
        by = (bad.groupby("season").resid.agg(["mean", "count"]).round(2)).to_dict("index")
        out[f] = {"bad_n": int(len(bad)), "good_n": int(len(good)),
                  "mean_total_bad": float(bad.total.mean()), "mean_line_bad": float(bad.total_line.mean()),
                  "mean_total_good": float(good.total.mean()), "mean_line_good": float(good.total_line.mean()),
                  "resid_bad_vs_line": float(bad.resid.mean()), "resid_bad_ci95": [float(np.quantile(db, .025)), float(np.quantile(db, .975))],
                  "resid_good_vs_line": float(good.resid.mean()), "bad_minus_good_resid": float(bad.resid.mean() - good.resid.mean()),
                  "diff_ci95": [float(np.quantile(diff, .025)), float(np.quantile(diff, .975))], "p_two_sided": p,
                  "seasons_with_bad_resid_below_0": int(sum(1 for v in by.values() if v["mean"] < 0)), "seasons": len(by)}
    # Holm
    srt = sorted(ps, key=lambda x: x[1])
    holm, run = {}, 0.0
    for i, (f, p) in enumerate(srt):
        run = max(run, min(1.0, p * (len(srt) - i)))
        holm[f] = run
    for f in holm:
        out[f]["p_holm"] = holm[f]
    # plain effects from play-by-play: passing / rushing / total yards and FGs per team-game, bad vs good weather
    frames = []
    for s in range(2006, 2027):
        p = NFLV / f"play_by_play_{s}.parquet"
        if p.exists():
            d = pd.read_parquet(p, columns=["game_id", "posteam", "passing_yards", "rushing_yards", "yards_gained",
                                            "play_type", "field_goal_result", "season_type", "pass", "rush"])
            d = d[d.posteam.notna() & d.play_type.isin(["pass", "run", "field_goal"])]
            a = d.groupby(["game_id", "posteam"]).agg(
                pass_yds=("passing_yards", "sum"), rush_yds=("rushing_yards", "sum"),
                fg_made=("field_goal_result", lambda x: int((x == "made").sum())),
                fg_att=("play_type", lambda x: int((x == "field_goal").sum()))).reset_index()
            frames.append(a)
    tg = pd.concat(frames)
    tg["tot_yds"] = tg.pass_yds + tg.rush_yds
    m = tg.merge(g[["game_id", "WIND", "COLD", "BAD"]], on="game_id")
    out["yards_fg_by_weather_per_team_game"] = {}
    for f in ("WIND", "COLD", "BAD"):
        out["yards_fg_by_weather_per_team_game"][f] = {
            "bad_team_games": int(m[f].sum()),
            **{c: {"bad": float(m.loc[m[f], c].mean()), "good": float(m.loc[~m[f], c].mean())}
               for c in ("pass_yds", "rush_yds", "tot_yds", "fg_made")}}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("weather")
    f = sub.add_parser("fetch")
    f.add_argument("--only")
    sub.add_parser("analyze")
    a = ap.parse_args()
    {"weather": cmd_weather, "fetch": cmd_fetch, "analyze": cmd_analyze}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
