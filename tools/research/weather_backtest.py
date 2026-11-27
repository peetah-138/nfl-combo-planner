#!/usr/bin/env python3
"""Offline backtest of Kalshi daily high-temperature markets against an NWS NBS forecast archive.

Research only (issue #494). Public key-free endpoints, no login, never trades, reads no keys or app data.
Data is cached OUTSIDE the repo (default ~/dev/research/kalshi-nonsports/wx, override with WX_DIR) and is never committed.

Stages (run in order):  markets  mos  cli  select  candles  analyze
Sources: Kalshi public market-data API (markets, 1-minute candles); Iowa Environmental Mesonet MOS archive
(NBS bulletins, public domain) and IEM CLI JSON (NWS daily climate reports). Requests are rate limited.
"""
import csv, gzip, io, json, math, os, random, sys, threading, time, urllib.request, urllib.error
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

WX = os.path.expanduser(os.environ.get("WX_DIR", "~/dev/research/kalshi-nonsports/wx"))
KB = "https://api.elections.kalshi.com/trade-api/v2"
IEM = "https://mesonet.agron.iastate.edu"
UA = {"User-Agent": "research-backtest/1.0", "Accept-Encoding": "gzip"}
RATE = float(os.environ.get("WX_RATE", "2.0"))  # global requests per second

# ---- PRE-REGISTERED PARAMETERS (see weather_result.md) ----
CITIES = {  # city: (kalshi series, MOS/CLI station)
    "NYC": ("KXHIGHNY", "KNYC"), "CHI": ("KXHIGHCHI", "KMDW"), "MIA": ("KXHIGHMIA", "KMIA"),
    "AUS": ("KXHIGHAUS", "KAUS"), "LAX": ("KXHIGHLAX", "KLAX"), "DEN": ("KXHIGHDEN", "KDEN"),
    "PHL": ("KXHIGHPHIL", "KPHL")}
START, END = date(2025, 6, 1), date(2026, 11, 24)
TRAIN_FRAC = 0.70
HIST_CUTOFF = "2026-09-26"  # Kalshi /historical/cutoff market_settled_ts
WINDOW_DAYS, MIN_ERR, SIGMA_FLOOR = 60, 20, 1.5
NMARK = 3
ORDER_N = 10
VARIANTS = [(t, e) for t in ("T1", "T2") for e in (0.03, 0.06)]
LAG = 60
MIN_FILLS = 300
SPLIT_AB = date(2026, 9, 1)
NBOOT = 10000

_lock, _last = threading.Lock(), [0.0]


def http(url):
    for a in range(6):
        with _lock:
            w = 1.0 / RATE - (time.time() - _last[0])
            if w > 0:
                time.sleep(w)
            _last[0] = time.time()
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60)
            b = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                b = gzip.decompress(b)
            return b.decode()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(10 * (a + 1))
        except Exception:
            time.sleep(5 * (a + 1))
    raise RuntimeError("failed " + url)


def cache(name):
    p = os.path.join(WX, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def ev_date(ev):  # KXHIGHNY-26NOV24 -> 2026-11-24
    return datetime.strptime(ev.split("-")[-1], "%y%b%d").date()


def ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def t_times(d):  # decision instants (UTC) for event day d
    return {"T1": datetime(d.year, d.month, d.day, 18) - timedelta(days=1), "T2": datetime(d.year, d.month, d.day, 12)}


# ---------------- stage: markets ----------------
def stage_markets():
    out = {}
    for c, (ser, _) in CITIES.items():
        ms = {}
        for path, extra in (("/historical/markets", ""), ("/markets", "&status=settled")):
            cur = None
            while True:
                u = f"{KB}{path}?series_ticker={ser}&limit=1000{extra}" + (f"&cursor={cur}" if cur else "")
                d = json.loads(http(u))
                for m in d["markets"]:
                    ms[m["ticker"]] = {k: m.get(k) for k in ("ticker", "event_ticker", "strike_type", "floor_strike", "cap_strike",
                                                              "result", "expiration_value", "close_time", "open_time", "rules_primary")}
                cur = d.get("cursor")
                if not cur:
                    break
        out[c] = list(ms.values())
        print(c, len(ms), flush=True)
    json.dump(out, open(cache("markets.json"), "w"))


# ---------------- stage: mos ----------------
def stage_mos():
    res = {}
    for c, (_, st) in CITIES.items():
        rows = []
        for a, b in (("2025-03-01", "2025-09-01"), ("2025-09-01", "2026-03-01"), ("2026-03-01", "2026-11-26")):
            t = http(f"{IEM}/cgi-bin/request/mos.py?station={st}&model=NBS&sts={a}T00:00Z&ets={b}T00:00Z&format=csv")
            for r in csv.DictReader(io.StringIO(t)):
                if r["txn"] and r["ftime"][11:13] == "00":
                    rows.append([r["runtime"], r["ftime"], float(r["txn"]), float(r["xnd"] or "nan")])
        res[c] = rows
        print(c, len(rows), flush=True)
    json.dump(res, open(cache("nbs_x.json"), "w"))


def stage_cli():
    res = {}
    for c, (_, st) in CITIES.items():
        d = {}
        for y in (2025, 2026):
            t = http(f"{IEM}/json/cli.py?station={st}&year={y}")
            for r in json.loads(t)["results"]:
                if r.get("high") not in (None, "M"):
                    d[r["valid"]] = float(r["high"])
        res[c] = d
        print(c, len(d), flush=True)
    json.dump(res, open(cache("cli_high.json"), "w"))


# ---------------- forecasts ----------------
def forecasts():
    """f[city][(day, lead)] = forecast X for local day `day`; lead T1 uses run on day-1 hour 12/13, T2 run on day hour 6/7."""
    raw = json.load(open(cache("nbs_x.json")))
    f = {}
    for c, rows in raw.items():
        best = {}
        for rt, ft, x, _ in rows:
            r = datetime.strptime(rt, "%Y-%m-%d %H:%M:%S")
            tgt = datetime.strptime(ft, "%Y-%m-%d %H:%M:%S").date() - timedelta(days=1)
            if r.date() == tgt - timedelta(days=1) and r.hour in (12, 13):
                k = (tgt, "T1")
            elif r.date() == tgt and r.hour in (6, 7):
                k = (tgt, "T2")
            else:
                continue
            if k not in best or r > best[k][0]:
                best[k] = (r, x)
        f[c] = {k: v[1] for k, v in best.items()}
    return f


def model_params(c, d, lead, f, cli):
    errs = []
    for i in range(2, 2 + WINDOW_DAYS + 40):
        dd = d - timedelta(days=i)
        k = (dd, lead)
        if k in f[c] and dd.isoformat() in cli[c]:
            errs.append(cli[c][dd.isoformat()] - f[c][k])
        if len(errs) >= WINDOW_DAYS:
            break
    if len(errs) < MIN_ERR:
        return None
    m = sum(errs) / len(errs)
    s = math.sqrt(sum((e - m) ** 2 for e in errs) / (len(errs) - 1))
    return m, max(s, SIGMA_FLOOR)


def ncdf(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def pyes(mk, mu, s):
    F = lambda k: ncdf((k + 0.5 - mu) / s)
    st = mk["strike_type"]
    if st == "greater":
        return 1 - F(mk["floor_strike"])
    if st == "less":
        return F(mk["cap_strike"] - 1)
    return F(mk["cap_strike"]) - F(mk["floor_strike"] - 1)


def interval(mk):
    st = mk["strike_type"]
    if st == "greater":
        return mk["floor_strike"] + 1, 1e9
    if st == "less":
        return -1e9, mk["cap_strike"] - 1
    return mk["floor_strike"], mk["cap_strike"]


def dist(x, iv):
    lo, hi = iv
    return 0 if lo <= x <= hi else min(abs(x - lo), abs(x - hi))


def days_range():
    d = START
    while d <= END:
        yield d
        d += timedelta(days=1)


# ---------------- stage: select ----------------
def stage_select():
    ms = json.load(open(cache("markets.json")))
    f = forecasts()
    sel = []
    for c in CITIES:
        ev = defaultdict(list)
        for m in ms[c]:
            if m["strike_type"] in ("greater", "less", "between"):
                ev[ev_date(m["event_ticker"])].append(m)
        for d in days_range():
            if d not in ev or (d, "T1") not in f[c]:
                continue
            x = f[c][(d, "T1")]
            for m in sorted(ev[d], key=lambda m: (dist(x, interval(m)), abs(sum(v for v in interval(m) if abs(v) < 1e8) / max(1, len([v for v in interval(m) if abs(v) < 1e8])) - x)))[:NMARK]:
                sel.append((c, m["ticker"], d.isoformat(), m["close_time"]))
    json.dump(sel, open(cache("selected.json"), "w"))
    print("selected markets", len(sel))


# ---------------- stage: candles ----------------
def parse_candles(txt, windows):
    d = json.loads(txt)
    out, la, lb = {}, None, None
    for c in d.get("candlesticks", []):
        e = c["end_period_ts"]
        ya, yb = c["yes_ask"], c["yes_bid"]
        a = ya.get("close") or ya.get("close_dollars")
        b = yb.get("close") or yb.get("close_dollars")
        la = float(a) if a is not None else la
        lb = float(b) if b is not None else lb
        if any(lo <= e <= hi for lo, hi in windows):
            out[e] = [la, lb]
    return out


def fetch_candle(item):
    c, tk, ds, close = item
    p = cache(f"candles/{tk}.json")
    if os.path.exists(p):
        return
    d = date.fromisoformat(ds)
    tt = {k: ts(v) for k, v in t_times(d).items()}
    win = [(tt["T1"] - 60, tt["T1"] + 180), (tt["T2"] - 60, tt["T2"] + 180)]
    hist = close[:10] < HIST_CUTOFF
    ser = CITIES[c][0]
    urls = [f"{KB}/historical/markets/{tk}/candlesticks", f"{KB}/series/{ser}/markets/{tk}/candlesticks"]
    if not hist:
        urls.reverse()
    q = f"?start_ts={tt['T1'] - 120}&end_ts={tt['T2'] + 240}&period_interval=1"
    for u in urls:
        t = http(u + q)
        if t is not None:
            json.dump(parse_candles(t, win), open(p, "w"))
            return
    json.dump({}, open(p, "w"))


def stage_candles():
    from concurrent.futures import ThreadPoolExecutor
    sel = json.load(open(cache("selected.json")))
    todo = [s for s in sel if not os.path.exists(cache(f"candles/{s[1]}.json"))]
    todo.sort(key=lambda s: s[2], reverse=True)  # newest first
    print("todo", len(todo), flush=True)
    done = [0]

    def run(s):
        fetch_candle(s)
        done[0] += 1
        if done[0] % 500 == 0:
            print("done", done[0], flush=True)

    with ThreadPoolExecutor(4) as ex:
        list(ex.map(run, todo))


# ---------------- analysis ----------------
def fee(n, p):
    return math.ceil(round(0.07 * n * p * (1 - p) * 100, 6)) / 100


def quote(cd, t):
    q = cd.get(str(t))
    return q if q and q[0] is not None and q[1] is not None else None


def build_fills(variants=VARIANTS):
    ms = json.load(open(cache("markets.json")))
    byt = {m["ticker"]: m for c in ms for m in ms[c]}
    sel = json.load(open(cache("selected.json")))
    f, cli = forecasts(), json.load(open(cache("cli_high.json")))
    fills = []  # dict rows, one per (variant-independent) candidate evaluation
    for c, tk, ds, close in sel:
        d = date.fromisoformat(ds)
        p = cache(f"candles/{tk}.json")
        if not os.path.exists(p):
            continue
        cd = json.load(open(p))
        mk = byt[tk]
        if mk["result"] not in ("yes", "no"):
            continue
        for lead, tdt in t_times(d).items():
            if (d, lead) not in f[c]:
                continue
            par = model_params(c, d, lead, f, cli)
            if not par:
                continue
            q = pyes(mk, f[c][(d, lead)] + par[0], par[1])
            for lag in (LAG, 0):
                qq = quote(cd, ts(tdt) + lag)
                if not qq:
                    continue
                ask, bid = qq
                cands = []
                if 0.01 <= ask <= 0.99 and bid is not None:
                    cands.append(("YES", q, ask))
                if 0.01 <= bid <= 0.99 and ask is not None:
                    cands.append(("NO", 1 - q, 1 - bid))
                for side, pw, price in cands:
                    for n in (ORDER_N, 1):
                        edge = pw - price - fee(n, price) / n
                        win = (mk["result"] == "yes") == (side == "YES")
                        net = (1.0 if win else 0.0) - price - fee(n, price) / n
                        fills.append(dict(city=c, day=ds, lead=lead, lag=lag, n=n, side=side, price=price, edge=edge, net=net, tk=tk, q=pw))
    return fills


def boot(rows, q_lo, nb=NBOOT, seed=1):
    by = defaultdict(lambda: [0.0, 0])
    for r in rows:
        by[r["day"]][0] += r["net"]
        by[r["day"]][1] += 1
    ks = list(by)
    rnd = random.Random(seed)
    res = []
    for _ in range(nb):
        s = k = 0
        for _ in ks:
            v = by[ks[rnd.randrange(len(ks))]]
            s += v[0]
            k += v[1]
        res.append(s / k if k else 0.0)
    res.sort()
    return res[int(q_lo * nb)]


def pick(fills, lead, thr, lag, n, lo=None, hi=None, city=None):
    best = {}
    for r in fills:
        if r["lead"] != lead or r["lag"] != lag or r["n"] != n or r["edge"] < thr:
            continue
        if city and r["city"] != city:
            continue
        if lo and r["day"] < lo or hi and r["day"] >= hi:
            continue
        k = (r["tk"])
        if k not in best or r["edge"] > best[k]["edge"]:
            best[k] = r  # one side per market
    return list(best.values())


def stage_analyze():
    fills = build_fills()
    days = sorted({d.isoformat() for d in days_range()})
    cut = days[int(len(days) * TRAIN_FRAC)]
    print("fit days <", cut, "| test days >=", cut)
    fitres = {}
    for lead, thr in VARIANTS:
        r = pick(fills, lead, thr, LAG, ORDER_N, hi=cut)
        fitres[(lead, thr)] = (len(r), sum(x["net"] for x in r) / len(r) if r else 0)
        print("FIT", lead, thr, fitres[(lead, thr)])
    ok = {k: v for k, v in fitres.items() if v[0] >= MIN_FILLS}
    if not ok:
        print("no variant reaches", MIN_FILLS, "fit fills; selecting by best mean anyway (flag)")
        ok = fitres
    chosen = max(ok, key=lambda k: ok[k][1])
    lead, thr = chosen
    print("CHOSEN", chosen)
    test = pick(fills, lead, thr, LAG, ORDER_N, lo=cut)
    mean = lambda r: sum(x["net"] for x in r) / len(r) if r else float("nan")
    print("TEST fills", len(test), "net/contract", mean(test), "n=1", mean(pick(fills, lead, thr, LAG, 1, lo=cut)), "nolag", mean(pick(fills, lead, thr, 0, ORDER_N, lo=cut)))
    print("TEST CI lower (1.25% one-sided)", boot(test, 0.0125), "| 2.5% two-sided", boot(test, 0.025))
    A = [x for x in test if x["day"] < SPLIT_AB.isoformat()]
    B = [x for x in test if x["day"] >= SPLIT_AB.isoformat()]
    print("period A", len(A), mean(A), "| period B", len(B), mean(B))
    for c in CITIES:
        r = [x for x in test if x["city"] == c]
        print("city", c, len(r), mean(r), "lower(5%/28)", boot(r, 0.05 / 28, nb=4000) if r else None)
    for k in sorted(fitres):
        t = pick(fills, k[0], k[1], LAG, ORDER_N, lo=cut)
        print("ALLVARIANTS test (descriptive)", k, len(t), mean(t))
    # diagnostics: mean entry price, side mix, mean model edge
    if test:
        print("mean price", sum(x["price"] for x in test) / len(test), "mean edge", sum(x["edge"] for x in test) / len(test),
              "YES share", sum(x["side"] == "YES" for x in test) / len(test))
    # CLI vs Kalshi settle value mismatch
    ms = json.load(open(cache("markets.json")))
    cli = json.load(open(cache("cli_high.json")))
    mm = defaultdict(lambda: [0, 0, 0.0])
    for c in ms:
        seen = set()
        for m in ms[c]:
            e = m["event_ticker"]
            if e in seen or not str(m["expiration_value"] or "").replace(".", "", 1).isdigit():
                continue
            seen.add(e)
            d = ev_date(e)
            if d.isoformat() in cli[c]:
                k = (c, "A" if d < SPLIT_AB else "B")
                mm[k][0] += 1
                diff = float(m["expiration_value"]) - cli[c][d.isoformat()]
                mm[k][1] += diff != 0
                mm[k][2] += diff
    for k in sorted(mm):
        print("MISMATCH", k, "days", mm[k][0], "differ", mm[k][1], "mean(kalshi-cli)", round(mm[k][2] / mm[k][0], 3))
    # forecast skill diagnostics
    for c in CITIES:
        for lead in ("T1", "T2"):
            e = [cli[c][k[0].isoformat()] - v for k, v in f_cache().get(c, {}).items() if k[1] == lead and k[0].isoformat() in cli[c]]
            if e:
                m = sum(e) / len(e)
                print("ERR", c, lead, "n", len(e), "bias", round(m, 2), "sd", round(math.sqrt(sum((x - m) ** 2 for x in e) / (len(e) - 1)), 2))


_fc = []


def f_cache():
    if not _fc:
        _fc.append(forecasts())
    return _fc[0]


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    {"markets": stage_markets, "mos": stage_mos, "cli": stage_cli, "select": stage_select, "candles": stage_candles, "analyze": stage_analyze}[stage]()
