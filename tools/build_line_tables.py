#!/usr/bin/env python3
"""Build the spread/total margin tables the engine ships (issue #117, part A) and the backtest evidence its gate uses.

Provenance: final scores from ESPN's free public scoreboard (site.api.espn.com .../scoreboard?dates=YYYYMMDD) and
each game's pre-game sportsbook line from ESPN's public odds feed (sports.core.api.espn.com .../competitions/<id>/odds,
provider "ESPN BET": spread, total, their prices, moneylines). No keys, no accounts, no paid data. Seasons 2023-24 to
now for NFL, college football (FBS), NBA, men's and women's college basketball (Division I, a fixed random sample of
9,000 games each), NHL and seven soccer leagues. The AHL and EuroLeague aren't on ESPN, and ESPN's odds feed has no
lines for Serie A, Bundesliga or Ligue 1: they borrow their sport's.

What ships is small: per league, a curve width (sd = a + b * |line|) and a few dozen weights (how much more or less
often a margin or total happens than a smooth curve says: NFL 3 and 7, no ties in basketball, empty-net 2-goal
hockey wins), shrunk toward the sport's weights (30 games' worth of expected count), plus each league's backtest
(leave-one-season-out: fit on the other seasons, price the held-out one with the engine's own code, old model vs
new on the same strikes). Nothing scraped is committed; the cache stays wherever --cache points.

  python3 tools/build_line_tables.py scrape --cache DIR          # slow and polite (a few hours the first time)
  python3 tools/build_line_tables.py build --cache DIR [--write] # fit + backtest; --write updates the engine block

Needs `requests` and `numpy` (the engine itself needs neither numpy nor this file).
"""
import argparse
import datetime as dt
import importlib.util
import json
import math
import os
import random
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "nfl_combo_planner.py")
UA = {"User-Agent": "Mozilla/5.0 (score research script)"}
SOCCER = {"epl": "eng.1", "laliga": "esp.1", "seriea": "ita.1", "bundesliga": "ger.1", "ligue1": "fra.1",
          "mls": "usa.1", "ligamx": "mex.1"}
_EU = [("2023-08-11", "2024-05-26"), ("2024-08-16", "2025-05-25"), ("2025-08-15", "2026-05-24"), ("2026-08-14", "2026-11-18")]
LEAGUES = {
    "nfl": ("football", "nfl", {}, [("2023-09-05", "2024-02-12"), ("2024-09-04", "2025-02-10"), ("2025-09-03", "2026-02-09"),
                                    ("2026-09-08", "2026-11-18")]),
    "ncaaf": ("football", "college-football", {"groups": "80"}, [("2023-08-26", "2024-01-09"), ("2024-08-24", "2025-01-21"),
                                                                 ("2025-08-23", "2026-01-20"), ("2026-08-29", "2026-11-18")]),
    "nba": ("basketball", "nba", {}, [("2023-10-24", "2024-04-14"), ("2024-10-22", "2025-04-13"), ("2025-10-21", "2026-04-12"),
                                      ("2026-10-20", "2026-11-18")]),
    "ncaamb": ("basketball", "mens-college-basketball", {"groups": "50", "limit": "500"},
               [("2023-11-06", "2024-03-17"), ("2024-11-04", "2025-03-16"), ("2025-11-03", "2026-03-15"), ("2026-11-02", "2026-11-18")]),
    "ncaawb": ("basketball", "womens-college-basketball", {"groups": "50", "limit": "500"},
               [("2023-11-06", "2024-03-17"), ("2024-11-04", "2025-03-16"), ("2025-11-03", "2026-03-15"), ("2026-11-02", "2026-11-18")]),
    "nhl": ("hockey", "nhl", {}, [("2023-10-10", "2024-04-18"), ("2024-10-04", "2025-04-17"), ("2025-10-07", "2026-04-16"),
                                  ("2026-10-06", "2026-11-18")]),
    "mls": ("soccer", "usa.1", {}, [("2024-02-21", "2024-11-10"), ("2025-02-22", "2025-11-09"), ("2026-02-21", "2026-11-10")]),
    "ligamx": ("soccer", "mex.1", {}, [("2024-01-12", "2024-05-26"), ("2024-07-05", "2024-12-15"), ("2025-01-10", "2025-05-25"),
                                       ("2025-07-11", "2025-12-14"), ("2026-01-09", "2026-05-24"), ("2026-07-10", "2026-11-18")]),
}
for _c in ("epl", "laliga", "seriea", "bundesliga", "ligue1"):
    LEAGUES[_c] = ("soccer", SOCCER[_c], {}, _EU)
SPORT = {lg: v[0] for lg, v in LEAGUES.items()}
SPORT_LGS = defaultdict(list)
for _lg, _s in SPORT.items():
    SPORT_LGS[_s].append(_lg)
MAX_GAMES = 9000
SD0 = {"football": {"spread": 14.0, "total": 11.0}, "basketball": {"spread": 11.0, "total": 15.0}}
C_SHRINK = 30.0


# ------------------------------------------------------------------ scrape (polite, cached)
_LOCK, _PAUSE = threading.Lock(), {"until": 0.0}


def _get(url, params=None):
    import requests
    for attempt in range(6):
        wait = _PAUSE["until"] - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(url, params=params, headers=UA, timeout=20)
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 404:
            return None
        if r.status_code == 429 or r.status_code >= 500:
            ra = r.headers.get("Retry-After")
            with _LOCK:
                _PAUSE["until"] = max(_PAUSE["until"], time.time() + (float(ra) if ra and ra.isdigit() else 5 * 2 ** attempt))
            continue
        try:
            return r.json()
        except ValueError:
            return None
    return None


def _days(a, b):
    d, e = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    while d <= e:
        yield d
        d += dt.timedelta(days=1)


def _board(cache, lg, day):
    sport, path, q, _ = LEAGUES[lg]
    fn = os.path.join(cache, "raw", lg, day.strftime("%Y%m%d") + ".json")
    if os.path.exists(fn):
        return
    js = _get(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{path}/scoreboard", dict(q, dates=day.strftime("%Y%m%d")))
    if js is None:
        return
    out = []
    for ev in js.get("events") or []:
        c = (ev.get("competitions") or [{}])[0]
        if not (((c.get("status") or ev.get("status") or {}).get("type") or {}).get("completed")):
            continue
        tm = {x.get("homeAway"): x for x in c.get("competitors") or []}
        try:
            hs, as_ = float(tm["home"].get("score")), float(tm["away"].get("score"))
        except (KeyError, TypeError, ValueError):
            continue
        out.append({"id": ev.get("id"), "date": ev.get("date"), "home": tm["home"]["team"].get("abbreviation"),
                    "away": tm["away"]["team"].get("abbreviation"), "hs": hs, "as": as_})
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    with open(fn, "w") as f:
        json.dump(out, f)
    time.sleep(0.15)


def _odds(cache, lg, gid):
    sport, path, _, _ = LEAGUES[lg]
    fn = os.path.join(cache, "odds", lg, f"{gid}.json")
    if os.path.exists(fn):
        return
    js = _get(f"https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{path}/events/{gid}/competitions/{gid}/odds",
              {"lang": "en", "region": "us"})
    out = []
    for it in (js or {}).get("items") or []:
        h, a = it.get("homeTeamOdds") or {}, it.get("awayTeamOdds") or {}
        out.append({"prov": (it.get("provider") or {}).get("name"), "details": it.get("details"), "spread": it.get("spread"),
                    "ou": it.get("overUnder"), "over": it.get("overOdds"), "under": it.get("underOdds"),
                    "hml": h.get("moneyLine"), "aml": a.get("moneyLine"), "hso": h.get("spreadOdds"), "aso": a.get("spreadOdds"),
                    "draw": (it.get("drawOdds") or {}).get("moneyLine") if isinstance(it.get("drawOdds"), dict) else None})
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    with open(fn, "w") as f:
        json.dump(out, f)
    time.sleep(0.15)


def scrape(cache, lgs):
    with ThreadPoolExecutor(3) as ex:
        for lg in lgs:
            list(ex.map(lambda d, lg=lg: _board(cache, lg, d), [d for a, b in LEAGUES[lg][3] for d in _days(a, b)]))
            ids = []
            rd = os.path.join(cache, "raw", lg)
            for fn in sorted(os.listdir(rd)):
                with open(os.path.join(rd, fn)) as f:
                    ids += [g["id"] for g in json.load(f)]
            if lg in ("ncaamb", "ncaawb"):             # ~6,000 games a season: a fixed random 12,000 is plenty
                random.Random(7).shuffle(ids)
                ids = ids[:12000]
            list(ex.map(lambda g, lg=lg: _odds(cache, lg, g), ids))
            print(lg, "scraped", len(ids), "games", flush=True)


# ------------------------------------------------------------------ load
def _am(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    return 100 / (a + 100) if a >= 100 else -a / (-a + 100) if a <= -100 else None


def _dv(a, b):
    pa, pb = _am(a), _am(b)
    return pa / (pa + pb) if pa and pb else None


def load(cache, lg):
    out = []
    rd, od = os.path.join(cache, "raw", lg), os.path.join(cache, "odds", lg)
    if not os.path.isdir(rd):
        return out
    for fn in sorted(os.listdir(rd)):
        with open(os.path.join(rd, fn)) as f:
            games = json.load(f)
        for g in games:
            p = os.path.join(od, f"{g['id']}.json")
            if not os.path.exists(p):
                continue
            with open(p) as f:
                odds = json.load(f)
            o = next((x for x in odds if x.get("prov") and "live" not in x["prov"].lower()
                      and (x.get("spread") is not None or x.get("ou") is not None)), None)
            if not o:
                continue
            d = dt.datetime.fromisoformat(g["date"].replace("Z", "+00:00")).date()
            try:
                S = float(o["spread"]) if o.get("spread") is not None else None
                T = float(o["ou"]) if o.get("ou") is not None and float(o["ou"]) > 0 else None
            except (TypeError, ValueError):
                continue
            s_old = S                                  # the engine's own parse of ESPN's "details" ("KC -3.5";
            hit = re.match(r"([A-Z]{2,5})\s+([+-]?\d+(?:\.\d+)?)", o.get("details") or "")   # hockey/soccer: a moneyline)
            if hit:
                s_old = float(hit.group(2)) if hit.group(1) == g["home"] else -float(hit.group(2))
            rec = {"lg": lg, "id": g["id"], "date": d.isoformat(), "season": d.year if d.month >= 7 else d.year - 1,
                   "hs": g["hs"], "as": g["as"], "S": S, "S_old": s_old, "T": T,
                   "p_over": _dv(o.get("over"), o.get("under")), "p_hcover": _dv(o.get("hso"), o.get("aso"))}
            ph, pa, pd = _am(o.get("hml")), _am(o.get("aml")), _am(o.get("draw"))
            if ph and pa and (SPORT[lg] != "soccer" or pd):
                s = ph + pa + (pd if SPORT[lg] == "soccer" else 0)
                rec.update(p_home=ph / s, p_away=pa / s, p_draw=(pd / s) if SPORT[lg] == "soccer" else 0.0)
            out.append(rec)
    if len(out) > MAX_GAMES:
        random.Random(7).shuffle(out)
        out = sorted(out[:MAX_GAMES], key=lambda r: r["date"])
    return out


# ------------------------------------------------------------------ fit (numpy)
def _np():
    import numpy as np
    return np


def _cdf(z):
    """Normal CDF on numpy arrays (Abramowitz-Stegun 7.1.26, error < 2e-7): fast enough to fit 9,000 games."""
    np = _np()
    x = np.abs(z) / math.sqrt(2)
    t = 1 / (1 + 0.3275911 * x)
    e = 1 - t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429)))) * np.exp(-x * x)
    return 0.5 * (1 + np.sign(z) * e)


def _binned(mu, sd, xs):
    return _cdf((xs[None, :] + 0.5 - mu[:, None]) / sd[:, None]) - _cdf((xs[None, :] - 0.5 - mu[:, None]) / sd[:, None])


def _loglik(mu, sd, obs, xs, wv):
    np = _np()
    p = _binned(mu, sd, xs) * wv[None, :]
    p /= p.sum(1, keepdims=True)
    idx = np.clip((obs - xs[0]).astype(int), 0, len(xs) - 1)
    return np.log(np.maximum(p[np.arange(len(obs)), idx], 1e-12)).sum()


def _golden(f, lo, hi, it=22):
    g = (math.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(it):
        if fc > fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(d)
    return (a + b) / 2


def _fit_sd(mu, la, obs, xs, wv, a0):
    a, b = a0, 0.0
    for _ in range(3):
        a = _golden(lambda v: _loglik(mu, v + b * la, obs, xs, wv), a0 * 0.3, a0 * 2.0)
        b = _golden(lambda v: _loglik(mu, a + v * la, obs, xs, wv), 0.0, 0.3)
    return a, b


def _counts(mu, sd, obs, xs, absw):
    np = _np()
    p = _binned(mu, sd, xs)
    p /= p.sum(1, keepdims=True)
    ex, ob = p.sum(0), np.zeros(len(xs))
    for o in obs:
        ob[int(o - xs[0])] += 1
    if absw:
        k = np.abs(xs)
        exf, obf = np.zeros(k.max() + 1), np.zeros(k.max() + 1)
        np.add.at(exf, k, ex)
        np.add.at(obf, k, ob)
        return obf, exf
    return ob, ex


def _weights(ob, ex, prior, keys, c=C_SHRINK):
    out = {}
    for i, k in enumerate(keys):
        w = (ob[i] + c * (prior.get(int(k), 1.0) if prior else 1.0)) / (ex[i] + c)
        if abs(w - 1) >= 0.02 and ex[i] + ob[i] > 0.5:
            out[int(k)] = round(min(w, 3.0), 3)
    return out


def fit_points(by_lg, kind, sport):
    np = _np()
    xs = np.arange(-100, 101) if kind == "spread" else np.arange(0, 330)
    absw, key_w = kind == "spread", kind == "spread" or sport == "football"
    no_tie = kind == "spread" and sport == "basketball"
    stats, ob_all, ex_all = {}, None, None
    for lg, games in by_lg.items():
        gs = [g for g in games if g.get("S" if kind == "spread" else "T") is not None]
        if len(gs) < 30:
            continue
        mu = np.array([-g["S"] if kind == "spread" else g["T"] for g in gs])
        la = np.abs(mu)
        obs = np.array([g["hs"] - g["as"] if kind == "spread" else g["hs"] + g["as"] for g in gs])
        a, b = _fit_sd(mu, la, obs, xs, np.ones(len(xs)), SD0[sport][kind])
        o, e = _counts(mu, a + b * la, obs, xs, absw)
        stats[lg] = (mu, la, obs, a, o, e)
        ob_all, ex_all = (o, e) if ob_all is None else (ob_all + o, ex_all + e)
    out = {}
    if not stats:
        return out
    keys = np.arange(len(ob_all)) if absw else xs
    sw = _weights(ob_all, ex_all, None, keys) if key_w else {}
    if no_tie:
        sw[0] = 0.0
    if absw:
        sw = {k: v for k, v in sw.items() if k <= 40}
    sds = []
    for lg, (mu, la, obs, a, o, e) in stats.items():
        w = _weights(o, e, sw, keys) if key_w else {}
        if no_tie:
            w[0] = 0.0
        if lg == "ncaaf" and absw:                     # college football has overtime: no ties
            w[0] = 0.0
        if absw:
            w = {k: v for k, v in w.items() if k <= 40}
        wv = np.array([w.get(int(abs(x)) if absw else int(x), 1.0) for x in xs])
        a, b = _fit_sd(mu, la, obs, xs, wv, a)
        out[lg] = {"sd": [round(a, 3), round(b, 4)], "w": w, "n": int(len(obs))}
        sds.append((a, b, len(obs)))
    n = sum(s[2] for s in sds)
    out["_sport"] = {"sd": [round(sum(s[0] * s[2] for s in sds) / n, 3), round(sum(s[1] * s[2] for s in sds) / n, 4)],
                     "w": sw, "n": n}
    return out


def fit_goals(E, by_lg, sport):
    np = _np()
    stats, alls = {}, [np.zeros(16), np.zeros(16), np.zeros(25), np.zeros(25)]
    for lg, games in by_lg.items():
        om, em, ot_, et = np.zeros(16), np.zeros(16), np.zeros(25), np.zeros(25)
        n = 0
        for g in games:
            b = g.get("_base")
            if not b:
                continue
            m, t = b
            n += 1
            for x, v in m.items():
                if abs(x) < 16:
                    em[abs(x)] += v
            for x, v in t.items():
                if x < 25:
                    et[x] += v
            mm, tt = int(abs(g["hs"] - g["as"])), int(g["hs"] + g["as"])
            if mm < 16:
                om[mm] += 1
            if tt < 25:
                ot_[tt] += 1
        if n < 30:
            continue
        stats[lg] = (om, em, ot_, et, n)
        for i, v in enumerate((om, em, ot_, et)):
            alls[i] += v
    out = {}
    if not stats:
        return out
    swm = _weights(alls[0], alls[1], None, np.arange(16))
    swt = _weights(alls[2], alls[3], None, np.arange(25))
    out["_sport"] = {"spread": {"w": swm}, "total": {"w": swt}, "n": int(sum(s[4] for s in stats.values()))}
    for lg, (om, em, ot_, et, n) in stats.items():
        out[lg] = {"spread": {"w": _weights(om, em, swm, np.arange(16))}, "total": {"w": _weights(ot_, et, swt, np.arange(25))},
                   "n": n}
    return out


def _goal_base(E, g, sport):
    if g.get("T") is None or not g.get("p_home") or not g.get("p_away"):
        return None
    try:
        return E.goals_pmfs(None, None, g["T"], g.get("p_over"), g["p_home"], g["p_away"], g.get("p_draw"), sport == "hockey")
    except (ValueError, ZeroDivisionError):
        return None


def fit_all(E, data):
    """{'leagues': {lg: {'spread': {...}, 'total': {...}}}, 'sports': {sport: {...}}} from the games given."""
    tables = {"leagues": {}, "sports": {}}
    for sport, lgs in SPORT_LGS.items():
        by = {lg: data.get(lg, []) for lg in lgs}
        if sport in ("football", "basketball"):
            for kind in ("spread", "total"):
                f = fit_points(by, kind, sport)
                for lg, v in f.items():
                    dst = tables["sports"].setdefault(sport, {}) if lg == "_sport" else tables["leagues"].setdefault(lg, {})
                    dst[kind] = v
        else:
            f = fit_goals(E, by, sport)
            for lg, v in f.items():
                dst = tables["sports"].setdefault(sport, {}) if lg == "_sport" else tables["leagues"].setdefault(lg, {})
                dst.update(spread=dict(v["spread"], n=v["n"]), total=dict(v["total"], n=v["n"]))
    return tables


# ------------------------------------------------------------------ backtest with the engine's own code
MARGIN_WINDOW = {"football": 0.8, "basketball": 0.8}


def strikes(E, lg, kind, g, home):
    sport = SPORT[lg]
    if kind == "spread":
        if g.get("S") is None:
            return []
        if sport in ("hockey", "soccer"):
            return [1.5, 2.5]
        mu, sd = (-g["S"] if home else g["S"]), E.MARGIN_SD[lg]
        return [k + 0.5 for k in range(0, 80) if abs(k + 0.5 - mu) <= sd * 0.8]
    T = g.get("T")
    if T is None:
        return []
    if sport in ("hockey", "soccer"):
        return [x for x in ([T - 1, T, T + 1] if T % 1 else [T - 1.5, T - 0.5, T + 0.5, T + 1.5]) if x > 0]
    sd = E.TOTAL_SD[lg]
    return [k + 0.5 for k in range(int(T - sd), int(T + sd) + 1) if abs(k + 0.5 - T) <= sd * 0.8]


def old_price(E, lg, kind, L, home, g):
    """Today's engine: line_candidates' distance filter, then line_fair, on ESPN's line as the engine reads it."""
    code = "soccer" if SPORT[lg] == "soccer" else lg
    if code == "soccer":
        return None                                  # the engine gets no soccer lines today (its ESPN path is a list)
    gg = {"spread_home": g["S_old"], "total": g["T"]}
    if kind == "spread":
        if g["S_old"] is None:
            return None
        mu = -g["S_old"] if home else g["S_old"]
        if abs(L - mu) > E.MARGIN_SD.get(code, 2.0) * 0.8:
            return None
    elif g["T"] is None or abs(L - g["T"]) > E.TOTAL_SD.get(code, 1.5) * 0.8:
        return None
    return E.line_fair(code, kind, L, home, gg)


def _ll(p, y):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -math.log(p if y else 1 - p)


def backtest(E, data, lg):
    sport = SPORT[lg]
    rows = []
    games = data[lg]
    for s in sorted({g["season"] for g in games}):
        train = {x: [g for g in gs if g["season"] != s] for x, gs in data.items() if SPORT[x] == sport}
        E.LINE_TABLES = fit_all(E, train)
        E.LINE_CACHE.clear()
        for g in (g for g in games if g["season"] == s):
            eg = {"spread_home": g["S"], "total": g["T"], "p_hcover": g.get("p_hcover"), "p_over": g.get("p_over"),
                  "p_home": g.get("p_home"), "p_away": g.get("p_away"), "p_draw": g.get("p_draw")}
            for kind in ("spread", "total"):
                for home in ((True, False) if kind == "spread" else (True,)):
                    for L in strikes(E, lg, kind, g, home):
                        new = E.margin_prob(lg, kind, L, home, eg)
                        if new is None:
                            continue
                        y = ((g["hs"] - g["as"]) if home else (g["as"] - g["hs"])) > L if kind == "spread" else g["hs"] + g["as"] > L
                        rows.append({"season": s, "id": g["id"], "kind": kind, "y": int(y), "new": new,
                                     "old": old_price(E, lg, kind, L, home, g)})
    return rows


def evidence(rows):
    """Per kind: games, average log loss and Brier of old vs new on the strikes both price, and a game-level
    bootstrap standard error of the log-loss gain."""
    out = {}
    for kind in ("spread", "total"):
        rs = [r for r in rows if r["kind"] == kind]
        both = [r for r in rs if r["old"] is not None]
        d = {"games": len({r["id"] for r in (both or rs)}), "strikes": len(both or rs),
             "seasons": len({r["season"] for r in rs})}
        if both:
            d.update(ll_old=round(sum(_ll(r["old"], r["y"]) for r in both) / len(both), 4),
                     ll_new=round(sum(_ll(r["new"], r["y"]) for r in both) / len(both), 4),
                     br_old=round(sum((r["old"] - r["y"]) ** 2 for r in both) / len(both), 4),
                     br_new=round(sum((r["new"] - r["y"]) ** 2 for r in both) / len(both), 4))
            by = defaultdict(list)
            for r in both:
                by[r["id"]].append(_ll(r["old"], r["y"]) - _ll(r["new"], r["y"]))
            keys, rnd, vals = list(by), random.Random(1), []
            for _ in range(300):
                tot = cnt = 0
                for _ in keys:
                    v = by[keys[rnd.randrange(len(keys))]]
                    tot += sum(v)
                    cnt += len(v)
                vals.append(tot / cnt)
            m = sum(vals) / len(vals)
            d["se"] = round(math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1)), 4)
        elif rs:
            d.update(ll_old=None, ll_new=round(sum(_ll(r["new"], r["y"]) for r in rs) / len(rs), 4),
                     br_old=None, br_new=round(sum((r["new"] - r["y"]) ** 2 for r in rs) / len(rs), 4))
        if rs:
            out[kind] = d
    return out


def _engine():
    """The engine's own pricing code, loaded from a copy in a temp folder (it keeps its files next to itself, so
    loading it in place could write into the repo)."""
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="line_tables_")
    shutil.copy(ENGINE, os.path.join(tmp, "engine.py"))
    os.environ["COMBOWATCH_HOME"] = tmp
    spec = importlib.util.spec_from_file_location("E", os.path.join(tmp, "engine.py"))
    E = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(E)
    return E


def _compact(t):
    """JSON without spaces, as a Python literal (the tables hold only names and numbers, so null is the one word
    that differs)."""
    return json.dumps(t, separators=(",", ":"), sort_keys=True).replace(":null", ":None")


def write_block(tables, ev):
    src = open(ENGINE, encoding="utf-8").read()
    a = src.index("# BEGIN LINE TABLES")
    a = src.index("\n", a) + 1
    b = src.index("# END LINE TABLES")
    block = f"LINE_TABLES = {_compact(tables)}\nLINE_EVIDENCE = {_compact(ev)}\n"
    with open(ENGINE, "w", encoding="utf-8") as f:
        f.write(src[:a] + block + src[b:])


def build(cache, write, lgs=None, out_rows=None):
    E = _engine()
    shipped = json.loads(json.dumps(E.LINE_EVIDENCE))   # a rebuild of some leagues keeps the others' evidence
    data = {lg: load(cache, lg) for lg in LEAGUES}
    data = {lg: gs for lg, gs in data.items() if gs}
    for lg, gs in data.items():
        if SPORT[lg] in ("hockey", "soccer"):
            for g in gs:
                g["_base"] = _goal_base(E, g, SPORT[lg])
    ev = {}
    for lg in (lgs or list(data)):
        if lg not in data:
            continue
        t0 = time.time()
        rows = backtest(E, data, lg)
        ev[lg] = evidence(rows)
        if out_rows:
            with open(os.path.join(out_rows, f"{lg}.json"), "w") as f:
                json.dump(rows, f)
        print(lg, len(data[lg]), "games", json.dumps(ev[lg]), f"{time.time() - t0:.0f}s", flush=True)
    tables = fit_all(E, data)
    if write:
        if lgs:
            ev = dict(shipped, **ev)
        write_block(tables, ev)
        print("engine block updated:", len(_compact(tables)) + len(_compact(ev)), "bytes")
    return tables, ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("scrape", "build"))
    ap.add_argument("--cache", default=os.path.join(os.environ.get("TMPDIR", "/tmp"), "line_tables_cache"))
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--rows", help="folder to save every backtest row (for a closer look)")
    ap.add_argument("leagues", nargs="*")
    a = ap.parse_args()
    if a.what == "scrape":
        scrape(a.cache, a.leagues or list(LEAGUES))
    else:
        build(a.cache, a.write, a.leagues or None, a.rows)


if __name__ == "__main__":
    sys.exit(main())
