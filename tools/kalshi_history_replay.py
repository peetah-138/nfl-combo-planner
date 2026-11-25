#!/usr/bin/env python3
"""Early-exit value test on Kalshi's PUBLIC settled single-game markets. Offline research only.

Two jobs, one file (design: docs/KALSHI_HISTORY_REPLAY.md, pass bar: docs/EXIT_REPLAY.md and the early-exit design):

    python3 tools/kalshi_history_replay.py fetch  --sports NFL NBA        # download + cache public data
    python3 tools/kalshi_history_replay.py report --out summary.json      # replay the exit rules on the cache

HARD RULES (a test enforces the network ones):
  * It uses ONLY Kalshi's public, unauthenticated market-data GETs (market lists, 1-minute candlesticks). There is no
    key, no login, no signing, no order, no portfolio call. The request function refuses any other path and never
    sends an auth header.
  * At most one request per second, backs off on 429/5xx, and caches every response on disk, so a rerun costs nothing.
  * The cache lives OUTSIDE the repo (default ~/dev/research/kalshi-history/), is private research data and is never
    redistributed. The output holds group aggregates only (no tickers, no dates of single games).
  * It changes nothing in the app's trading code, never reads ~/combowatch or any history database, never starts the
    watcher.
"""
import argparse
import bisect
import datetime as dt
import gzip
import json
import math
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.elections.kalshi.com/trade-api/v2"
USER_AGENT = "kalshi-history-research/1.0 (offline research; public market-data endpoints only; <=1 req/s)"
MIN_GAP_S = 1.1                      # politeness: never more than one request a second
ALLOWED_PATHS = (                    # the ONLY paths the fetcher may ask for (public market data)
    "/historical/cutoff",
    "/historical/markets",
    "/markets",
    "/series/",
)
FEE_RATE = 0.07                      # Kalshi's standard taker fee rate (the engine's FEE_RATE)
ORDER_N = 100                        # contracts per replayed order (fee rounding is per order)
HIDE_N = 20                          # a group with fewer games than this is never shown
BOOT = 2000                          # bootstrap resamples
SEED = 7
CACHE_DEFAULT = Path.home() / "dev" / "research" / "kalshi-history"

# series tickers per sport: game winner / spread / total. A series that does not exist just lists zero markets.
SPORTS = {
    "NFL": {"game": "KXNFLGAME", "spread": "KXNFLSPREAD", "total": "KXNFLTOTAL"},
    "NBA": {"game": "KXNBAGAME", "spread": "KXNBASPREAD", "total": "KXNBATOTAL"},
    "NHL": {"game": "KXNHLGAME", "spread": "KXNHLSPREAD", "total": "KXNHLTOTAL"},
    "MLB": {"game": "KXMLBGAME", "spread": "KXMLBSPREAD", "total": "KXMLBTOTAL"},
    "NCAAF": {"game": "KXNCAAFGAME", "spread": "KXNCAAFSPREAD", "total": "KXNCAAFTOTAL"},
    "NCAAMB": {"game": "KXNCAAMBGAME", "spread": "KXNCAAMBSPREAD", "total": "KXNCAAMBTOTAL"},
}
# typical game length (hours from start to the market's close_time). Kalshi's game markets close when the result is
# known, so the start is close_time minus this. Only used to place the start; see docs for the check against the data.
GAME_HOURS = {"NFL": 3.0, "NBA": 2.5, "NHL": 2.6, "MLB": 3.0, "NCAAF": 3.3, "NCAAMB": 2.0}
TOP_PER_EVENT = 2                    # spread/total: keep the N most-traded lines of a game (winner keeps both teams)
CANDLE_HOURS = 36                    # candles fetched: this long before close (covers T-24h entries plus the game)


# --------------------------------------------------------------------------------------------- polite public client
class Client:
    """Public GET only. One request a second, back off on 429/5xx, no auth header ever."""

    def __init__(self, sleep=time.sleep, clock=time.monotonic, opener=None):
        self.sleep, self.clock = sleep, clock
        self.opener = opener or urllib.request.urlopen
        self.last = 0.0
        self.requests = 0
        self.backoffs = 0

    @staticmethod
    def allowed(path):
        return path.startswith(ALLOWED_PATHS) and "portfolio" not in path and "/orders" not in path

    def get(self, path, params=None, tries=6):
        if not self.allowed(path):
            raise ValueError("path not allowed (public market data only): " + path)
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        delay = 5.0
        for attempt in range(tries):
            wait = MIN_GAP_S - (self.clock() - self.last)
            if wait > 0:
                self.sleep(wait)
            self.last = self.clock()
            self.requests += 1
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            try:
                with self.opener(req, timeout=40) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                    retry = e.headers.get("Retry-After") if e.headers else None
                    try:
                        delay = max(delay, float(retry))
                    except (TypeError, ValueError):
                        pass
                    self.backoffs += 1
                    self.sleep(delay)
                    delay = min(delay * 2, 300)
                    continue
                if e.code == 404:
                    return None
                raise
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < tries - 1:
                    self.backoffs += 1
                    self.sleep(delay)
                    delay = min(delay * 2, 300)
                    continue
                raise
        return None


# ------------------------------------------------------------------------------------------------------ cache + parse
def parse_ts(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return int(dt.datetime.fromisoformat(s).timestamp())
    except ValueError:
        return None


def money(x):
    """Dollar string -> integer ten-thousandths of a dollar (Kalshi quotes to 0.0001); None when absent."""
    if x is None or x == "":
        return None
    try:
        return int(round(float(x) * 10000))
    except (TypeError, ValueError):
        return None


def pick(d, name):
    """A candle price field exists as 'close' (historical) or 'close_dollars' (live)."""
    if not isinstance(d, dict):
        return None
    v = d.get(name)
    return money(v if v is not None else d.get(name + "_dollars"))


def slim_market(m, series):
    """The market fields the replay needs (no rules text), times as epoch seconds."""
    sv = money(m.get("settlement_value_dollars"))
    return {
        "ticker": m.get("ticker"), "event": m.get("event_ticker"), "series": series,
        "open": parse_ts(m.get("open_time")), "close": parse_ts(m.get("close_time")),
        "occ": parse_ts(m.get("occurrence_datetime")), "exp": parse_ts(m.get("expected_expiration_time")),
        "result": m.get("result"), "settle": sv, "vol": float(m.get("volume_fp") or m.get("volume") or 0),
        "strike": m.get("strike_type"), "floor": m.get("floor_strike"), "cap": m.get("cap_strike"),
        "sub": m.get("yes_sub_title"),
    }


def slim_candle(c):
    pr, ya, yb = c.get("price") or {}, c.get("yes_ask") or {}, c.get("yes_bid") or {}
    vol = c.get("volume_fp", c.get("volume"))
    try:
        vol = round(float(vol or 0))
    except (TypeError, ValueError):
        vol = 0
    return [c.get("end_period_ts"), pick(yb, "close"), pick(ya, "close"), pick(yb, "low"), pick(ya, "high"),
            pick(pr, "close"), vol]
CANDLE_FIELDS = ("ts", "bid", "ask", "bid_low", "ask_high", "price", "vol")


def write_gz(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def read_gz(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def list_series(client, cache, series, log=print):
    """Every settled market of a series, live + historical lists, cached. Returns slim markets (route recorded)."""
    f = cache / "lists" / (series + ".json.gz")
    if f.exists():
        return read_gz(f)
    out = {}
    for route, path, extra in (("hist", "/historical/markets", {}), ("live", "/markets", {"status": "settled"})):
        cursor = None
        while True:
            params = {"series_ticker": series, "limit": 1000, **extra}
            if cursor:
                params["cursor"] = cursor
            d = client.get(path, params)
            if not d:
                break
            for m in d.get("markets", []):
                if m.get("result") in ("yes", "no") or m.get("settlement_value_dollars") not in (None, ""):
                    s = slim_market(m, series)
                    s["route"] = route
                    out[s["ticker"]] = s
            cursor = d.get("cursor")
            if not cursor:
                break
    rows = sorted(out.values(), key=lambda r: (r["close"] or 0, r["ticker"]))
    write_gz(f, rows)
    log(f"  {series}: {len(rows)} settled markets listed")
    return rows


def choose(markets, kind):
    """Winner markets: all. Spread/total: the TOP_PER_EVENT most-traded lines of each game (liquid ones)."""
    if kind == "game":
        return list(markets)
    by_event = {}
    for m in markets:
        by_event.setdefault(m["event"], []).append(m)
    keep = []
    for ms in by_event.values():
        ms.sort(key=lambda r: (-r["vol"], r["ticker"]))
        keep.extend(ms[:TOP_PER_EVENT])
    return keep


def fetch_candles(client, cache, m, log=print):
    """1-minute bid/ask candles from CANDLE_HOURS before close to just after it; one request. Cached, resumable."""
    f = cache / "candles" / (m["ticker"] + ".json.gz")
    if f.exists():
        return True
    if not m.get("close"):
        return False
    end = m["close"] + 120
    start = max(m["open"] or 0, end - CANDLE_HOURS * 3600)
    params = {"start_ts": start, "end_ts": end, "period_interval": 1}
    if m["route"] == "hist":
        d = client.get("/historical/markets/" + urllib.parse.quote(m["ticker"]) + "/candlesticks", params)
    else:
        d = client.get("/series/%s/markets/%s/candlesticks" % (m["series"], urllib.parse.quote(m["ticker"])), params)
    if d is None:
        log("  no candles: " + m["ticker"])
        write_gz(f, {"fields": CANDLE_FIELDS, "rows": []})
        return False
    rows = [slim_candle(c) for c in d.get("candlesticks", [])]
    write_gz(f, {"fields": CANDLE_FIELDS, "rows": rows})
    return True


def cmd_fetch(args):
    cache = Path(args.cache).expanduser()
    client = Client()
    kinds = args.kinds
    t0 = time.time()
    for sport in args.sports:
        for kind in kinds:
            series = SPORTS[sport][kind]
            ms = choose(list_series(client, cache, series), kind)
            if args.since:
                lo = int(dt.datetime.fromisoformat(args.since).replace(tzinfo=dt.timezone.utc).timestamp())
                ms = [m for m in ms if (m["close"] or 0) >= lo]
            todo = [m for m in ms if m.get("close") and m.get("settle") is not None
                    and not (cache / "candles" / (m["ticker"] + ".json.gz")).exists()]
            if args.limit:
                todo = todo[:args.limit]
            print(f"{sport} {kind}: {len(ms)} chosen, {len(todo)} to download", flush=True)
            for i, m in enumerate(todo, 1):
                fetch_candles(client, cache, m)
                if i % 100 == 0:
                    print(f"  {sport} {kind}: {i}/{len(todo)} ({client.requests} requests, {client.backoffs} back-offs,"
                          f" {int(time.time() - t0)}s)", flush=True)
    print(f"done: {client.requests} requests, {client.backoffs} back-offs", flush=True)
    return 0


# ----------------------------------------------------------------------------------------------------------- the model
def fee_cents(n, p):
    """Kalshi taker fee for an order of n contracts at price p (dollars): ceil(0.07*n*p*(1-p)) rounded UP to the cent.
    In cents. Rounding up is per order, so a 100-contract order is replayed (ORDER_N)."""
    return math.ceil(round(100.0 * FEE_RATE * n * p * (1 - p), 6))


def cents(x):
    return None if x is None else x / 100.0          # ten-thousandths of a dollar -> cents


def probit(p):
    p = min(0.999, max(0.001, p))
    return statistics.NormalDist().inv_cdf(p)


class Series:
    """One market's candles with carried-forward bid/ask and fast time lookup."""

    def __init__(self, rows):
        rows = [r for r in rows if r[0] is not None]
        rows.sort(key=lambda r: r[0])
        self.ts = [r[0] for r in rows]
        self.bid, self.ask, self.vol = [], [], []
        b = a = None
        for r in rows:
            # a one-sided or void book (bid 0 / ask 1.0000) is "no price", never a tradable one
            if r[1] is not None and r[1] > 0:
                b = r[1]
            elif r[1] == 0:
                b = None
            if r[2] is not None and r[2] < 10000:
                a = r[2]
            elif r[2] == 10000:
                a = None
            self.bid.append(b)
            self.ask.append(a)
            self.vol.append(r[6] or 0)

    def idx(self, t):
        """Index of the last candle ending at or before t (what was observable at t), or None."""
        i = bisect.bisect_right(self.ts, t) - 1
        return i if i >= 0 else None


def hold_value(settle):
    """Dollars a contract pays at settlement: 1, 0 or the settled value (e.g. 0.5 for a tie)."""
    return settle / 10000.0


def trade_outcomes(s, mk, entry_i, rules, lags, kick, first_i=None):
    """Replay every exit rule for one entry. Entry at the ask, exit at the bid, fee both ways, 100 contracts.
    Returns None when the entry has no ask, else {'stake','hold', rule: pnl, ..} in dollars.

    The decision is made from the candle CLOSE (what was observable at that minute's end). Lag shifts the fill to a
    later candle's bid (60 s = next candle). The trigger never looks ahead: a rule fires on the first candle whose bid
    close is >= its target, and the exit is filled at the bid of that candle (lag 0) or of the candle `lag` later."""
    ask = s.ask[entry_i]
    if ask is None or not (0 < ask < 10000):
        return None
    p = ask / 10000.0
    efee = fee_cents(ORDER_N, p) / 100.0
    stake = ORDER_N * p + efee
    cost_per = stake / ORDER_N                       # all-in cost per contract, dollars
    settle = hold_value(mk["settle"])
    out = {"stake": stake, "hold": ORDER_N * settle - stake, "entry_ask": p}
    n = len(s.ts)
    for rule in rules:
        kind, arg = rule
        fire = None
        if kind == "plus":
            target = cost_per + arg / 100.0
            for j in range(entry_i + 1, n):
                if s.ts[j] >= mk["end_trade"]:
                    break
                if s.bid[j] is not None and s.bid[j] / 10000.0 >= target:
                    fire = j
                    break
        else:                                        # "tminus": at kick - arg minutes, sell if bid > all-in cost
            t_exit = kick - arg * 60
            j = s.idx(t_exit)
            if j is not None and j > entry_i and s.bid[j] is not None and s.bid[j] / 10000.0 > cost_per:
                fire = j
        for lag in lags:
            key = (rule, lag)
            if fire is None:
                out[key] = out["hold"]
                continue
            jf = s.idx(s.ts[fire] + lag)
            if jf is None or jf >= n or s.ts[jf] >= mk["end_trade"] or s.bid[jf] is None:
                out[key] = out["hold"]               # could not fill at the lagged time: stay in (never a free fill)
                continue
            b = s.bid[jf] / 10000.0
            out[key] = ORDER_N * b - fee_cents(ORDER_N, b) / 100.0 - stake
    return out


# --------------------------------------------------------------------------------------------------- entries + stats
BUCKETS = ((10, 30), (30, 60), (60, 90))        # entry ask, in cents (same buckets as tools/exit_replay.py)
RULES = (("plus", 3), ("plus", 5), ("plus", 10), ("tminus", 60), ("tminus", 15))
LAGS = (0, 60, 120)                             # seconds the exit is delayed; candles are 1 minute, so 30 s is not testable
ENTRIES = (("T-24h", -24 * 3600), ("T-4h", -4 * 3600), ("live+30m", 30 * 60))
FRESH_S = 600                                   # an entry price must be from a candle at most 10 minutes old


def rule_name(r):
    return ("+%dc" % r[1]) if r[0] == "plus" else ("T-1h" if r[1] == 60 else "T-%dm" % r[1])


def bucket(p_cents):
    for lo, hi in BUCKETS:
        if lo <= p_cents < hi:
            return "%d-%dc" % (lo, hi)
    return None


def game_key(m):
    ev = m["event"] or m["ticker"]
    return ev.split("-", 1)[1] if "-" in ev else ev


def kick_of(m, sport):
    """Estimated start: the market's close time minus a typical game length. A stand-in, stated plainly in the docs."""
    return m["close"] - int(GAME_HOURS[sport] * 3600)


def market_entries(m, sport, kind, s):
    """Every replayed entry for one market. Look-ahead rules: the entry uses only candles at or before the entry time;
    the 'below baseline' flag uses the pre-game mid at kick-5min and is therefore an ORACLE for T-24h/T-4h entries."""
    kick = kick_of(m, sport)
    mk = {"settle": m["settle"], "end_trade": m["close"]}
    base = None
    j = s.idx(kick - 300)
    if j is not None and s.bid[j] is not None and s.ask[j] is not None and kick - 300 - s.ts[j] <= FRESH_S:
        base = (s.bid[j] + s.ask[j]) / 20000.0
    out = []
    for ename, off in ENTRIES:
        t = kick + off
        i = s.idx(t)
        if i is None or t - s.ts[i] > FRESH_S or s.ask[i] is None or s.ts[i] >= m["close"]:
            continue
        b = bucket(s.ask[i] / 100.0)
        if b is None:
            continue
        res = trade_outcomes(s, mk, i, RULES, LAGS, kick)
        if res is None:
            continue
        res["sport"], res["type"], res["entry"], res["bucket"] = sport, kind, ename, b
        res["game"], res["t"] = (sport, game_key(m)), m["close"]
        res["below"] = bool(base is not None and off < 0 and res["entry_ask"] < base)
        out.append(res)
    return out


def load_all(cache, sports, kinds, log=print):
    """Returns (entries, gates, measures). Reads the disk cache only; no network."""
    entries, gate, series_by = [], {}, {}
    for sport in sports:
        g = gate.setdefault(sport, {"chosen": 0, "with_candles": 0, "games": set(), "game_with_spread": set(),
                                    "lo": None, "hi": None, "kick_ok": 0, "kick_n": 0})
        for kind in kinds:
            f = cache / "lists" / (SPORTS[sport][kind] + ".json.gz")
            if not f.exists():
                continue
            for m in choose(read_gz(f), kind):
                if not m.get("close") or m.get("settle") is None:
                    continue
                g["chosen"] += 1
                gk = game_key(m)
                if kind == "game":
                    g["games"].add(gk)
                cf = cache / "candles" / (m["ticker"] + ".json.gz")
                if not cf.exists():
                    continue
                rows = read_gz(cf)["rows"]
                if not rows:
                    continue
                g["with_candles"] += 1
                if kind == "spread":
                    g["game_with_spread"].add(gk)
                g["lo"] = m["close"] if g["lo"] is None else min(g["lo"], m["close"])
                g["hi"] = m["close"] if g["hi"] is None else max(g["hi"], m["close"])
                s = Series(rows)
                entries.extend(market_entries(m, sport, kind, s))
                if kind == "game":
                    series_by.setdefault(sport, []).append((m, s))
    return entries, gate, series_by


def mean_ci(cl, rng, boot):
    """cl: clusters [sA, pA, sB, pB]. Edge = 100*(pA/sA - pB/sB). Returns (edge, net_A, lo, hi) or None."""
    n = len(cl)
    sA, pA, sB, pB = (sum(c[k] for c in cl) for k in range(4))
    if n == 0 or sA <= 0 or sB <= 0:
        return None
    edge, net = 100.0 * (pA / sA - pB / sB), 100.0 * pA / sA
    if n < 2:
        return edge, net, None, None
    vals, idx = [], range(n)
    for _ in range(boot):
        sa = pa = sb = pb = 0.0
        for i in rng.choices(idx, k=n):
            c = cl[i]
            sa += c[0]; pa += c[1]; sb += c[2]; pb += c[3]
        if sa > 0 and sb > 0:
            vals.append(100.0 * (pa / sa - pb / sb))
    if len(vals) < 20:
        return edge, net, None, None
    vals.sort()
    return edge, net, vals[int(0.025 * (len(vals) - 1))], vals[int(round(0.975 * (len(vals) - 1)))]


def clusters(rows, rule, lag):
    """One cluster per game (both sides and all lines of a game together). rule None = hold; 'fair' = only entries
    priced under the pre-game baseline. A = the strategy, B = hold on the same unfiltered entries."""
    d = {}
    for r in rows:
        c = d.setdefault(r["game"], [0.0, 0.0, 0.0, 0.0, r["t"]])
        c[2] += r["stake"]
        c[3] += r["hold"]
        if rule == "fair":
            if r["below"]:
                c[0] += r["stake"]
                c[1] += r["hold"]
        else:
            c[0] += r["stake"]
            c[1] += r["hold"] if rule is None else r[(rule, lag)]
    return sorted(d.values(), key=lambda c: c[4])


def split_clusters(cl, frac=0.7):
    k = int(len(cl) * frac)
    return cl[:k], cl[k:]


def week_of(t):
    return int(t // (7 * 86400))


def stat_cell(ci):
    if ci is None:
        return None
    e, net, lo, hi = ci
    return {"edge_c": round(e, 2), "net_c": round(net, 2), "lo": None if lo is None else round(lo, 2),
            "hi": None if hi is None else round(hi, 2)}


def group_keys(entries):
    sports = sorted({e["sport"] for e in entries})
    types = sorted({e["type"] for e in entries})
    out = []
    for sp in sports + ["ALL"]:
        for ty in types + ["all"]:
            for en in [x[0] for x in ENTRIES]:
                for bk in [b for b in ("%d-%dc" % x for x in BUCKETS)] + ["all"]:
                    out.append((sp, ty, en, bk))
    return out


def in_group(r, key):
    sp, ty, en, bk = key
    return (sp == "ALL" or r["sport"] == sp) and (ty == "all" or r["type"] == ty) and r["entry"] == en and \
        (bk == "all" or r["bucket"] == bk)


def evaluate(entries, boot=BOOT, seed=SEED):
    """Per group: hold, every rule (all lags 0), the rule picked on the first 70% scored on the last 30%, the pass bar."""
    rng = random.Random(seed)
    res = []
    names = [rule_name(r) for r in RULES] + ["fair"]
    for key in group_keys(entries):
        rows = [r for r in entries if in_group(r, key)]
        games = {r["game"] for r in rows}
        if len(games) < HIDE_N:
            continue
        cells = {"hold": stat_cell(mean_ci(clusters(rows, None, 0), rng, boot))}
        for r in RULES:
            cells[rule_name(r)] = stat_cell(mean_ci(clusters(rows, r, 0), rng, boot))
        cells["fair"] = stat_cell(mean_ci(clusters(rows, "fair", 0), rng, boot))
        # --- out of sample: pick on the first 70% of games by time, score on the last 30%
        cl_by = {n: clusters(rows, (RULES[i] if i < len(RULES) else "fair"), 0) for i, n in enumerate(names)}
        tr = {n: split_clusters(v)[0] for n, v in cl_by.items()}
        te = {n: split_clusters(v)[1] for n, v in cl_by.items()}

        def train_edge(n):
            sA = sum(c[0] for c in tr[n]); sB = sum(c[2] for c in tr[n])
            return -1e9 if sA <= 0 or sB <= 0 else 100.0 * (sum(c[1] for c in tr[n]) / sA - sum(c[3] for c in tr[n]) / sB)
        pick = max(names[:len(RULES)], key=train_edge)      # the oracle "fair" filter can never be the pick
        oos = {"picked": pick, "train_games": len(tr[pick]), "test_games": len(te[pick])}
        pick_rule = (RULES[names.index(pick)] if pick != "fair" else "fair")
        if len(te[pick]) >= HIDE_N:
            oos["test"] = stat_cell(mean_ci(te[pick], rng, boot))
            lagged = {}
            for lag in LAGS[1:]:
                if pick == "fair":
                    lagged[lag] = oos["test"]          # a filter has no exit to delay (hold), lag cannot matter
                else:
                    cl = split_clusters(clusters(rows, pick_rule, lag))[1]
                    lagged[lag] = stat_cell(mean_ci(cl, rng, boot))
            oos["lag"] = {str(k): v for k, v in lagged.items()}
            # stability: other sports, or separate weeks, same picked rule, positive on the test games
            sports_pos = None
            if key[0] == "ALL":
                sports_pos = 0
                for sp in sorted({r["sport"] for r in rows}):
                    srows = [r for r in rows if r["sport"] == sp]
                    sc = split_clusters(clusters(srows, pick_rule, 0))[1]
                    ci = mean_ci(sc, rng, 0) if len(sc) >= HIDE_N else None
                    sports_pos += 1 if ci and ci[0] > 0 else 0
            weeks = {}
            for c in te[pick]:
                weeks.setdefault(week_of(c[4]), []).append(c)
            wk = [mean_ci(v, rng, 0) for v in weeks.values() if len(v) >= 10]
            weeks_pos = sum(1 for x in wk if x and x[0] > 0)
            t = oos["test"]
            lag60 = lagged[60]
            oos["stable"] = {"sports_positive": sports_pos, "weeks_scored": len(wk), "weeks_positive": weeks_pos}
            oos["pass"] = bool(t and t["edge_c"] >= 1.0 and t["lo"] is not None and t["lo"] > 0
                               and ((sports_pos or 0) >= 2 or weeks_pos >= 2)
                               and lag60 and lag60["edge_c"] >= 1.0 and lag60["lo"] is not None and lag60["lo"] > 0)
        res.append({"key": list(key), "games": len(games), "entries": len(rows), "cells": cells, "oos": oos})
    return res


def pctl(vals, q):
    if not vals:
        return None
    v = sorted(vals)
    return v[int(round(q * (len(v) - 1)))]


def measure_placeholders(series_by):
    """Measured stand-ins for SB_PRE_CLOSE / SB_PRE_VOL / SB_SPREAD / SB_LIVE_WIDEN from the winner markets' candles."""
    out = {}
    for sport, lst in series_by.items():
        d1, dt_, vols, sp_pre, sp_live, vol_pre, vol_live, kick_ok, kick_n = [], [], [], [], [], [], [], 0, 0
        for m, s in lst:
            kick = kick_of(m, sport)

            def mid(t):
                j = s.idx(t)
                if j is None or t - s.ts[j] > FRESH_S or s.bid[j] is None or s.ask[j] is None:
                    return None
                return (s.bid[j] + s.ask[j]) / 20000.0
            m24, m4, mk_ = mid(kick - 86400), mid(kick - 4 * 3600), mid(kick - 300)
            if None not in (m24, m4, mk_) and all(0.05 < x < 0.95 for x in (m24, m4, mk_)):
                d1.append(probit(m4) - probit(m24))
                dt_.append(probit(mk_) - probit(m24))
                vols.append(probit(mk_) - probit(m24))
            for i, t in enumerate(s.ts):
                if s.bid[i] is None or s.ask[i] is None or not (0.10 < (s.bid[i] + s.ask[i]) / 20000.0 < 0.90):
                    continue
                w = (s.ask[i] - s.bid[i]) / 10000.0
                if kick - 4 * 3600 <= t < kick - 900:
                    sp_pre.append(w)
                elif kick + 600 <= t < m["close"] - 600:
                    sp_live.append(w)
            pv = sum(v for t, v in zip(s.ts, s.vol) if kick - 3600 <= t < kick)
            lv = sum(v for t, v in zip(s.ts, s.vol) if kick <= t < kick + 3600)
            kick_n += 1
            kick_ok += 1 if lv > pv else 0
        res = {"games_for_drift": len(vols)}
        if len(vols) >= HIDE_N:
            res["pre_vol_probit_per_day"] = round(statistics.pstdev(vols), 3)        # moves over ~one day (T-24h to T-5m)
            den = sum(x * x for x in dt_)
            res["pre_close_stand_in"] = round(sum(a * b for a, b in zip(d1, dt_)) / den, 3) if den else None
            res["mean_abs_pre_drift_probit"] = round(statistics.mean(abs(x) for x in dt_), 3)
        if len(sp_pre) >= 200 and len(sp_live) >= 200:
            a, b = statistics.median(sp_pre), statistics.median(sp_live)
            res["median_spread_pre"], res["median_spread_live"] = round(a, 4), round(b, 4)
            res["live_widen"] = round(b / a, 2) if a else None
            res["spread_pre_p25_p75"] = [round(pctl(sp_pre, .25), 4), round(pctl(sp_pre, .75), 4)]
        res["kick_sanity_live_volume_gt_pre"] = round(kick_ok / kick_n, 2) if kick_n else None
        out[sport] = res
    return out


# ------------------------------------------------------------------------------------------------------------ report
def gates(gate):
    out = {}
    for sport, g in gate.items():
        games = len(g["games"])
        out[sport] = {
            "game_winner_games": games, "markets_chosen": g["chosen"], "markets_with_candles": g["with_candles"],
            "pct_with_candles": round(100.0 * g["with_candles"] / g["chosen"], 1) if g["chosen"] else None,
            "pct_games_with_spread_candles": round(100.0 * len(g["game_with_spread"] & g["games"]) / games, 1)
            if games else None,
            "span": [dt.datetime.fromtimestamp(g["lo"], dt.timezone.utc).strftime("%Y-%m-%d"),
                     dt.datetime.fromtimestamp(g["hi"], dt.timezone.utc).strftime("%Y-%m-%d")] if g["lo"] else None,
        }
    return out


def cmd_report(args):
    cache = Path(args.cache).expanduser()
    entries, gate, series_by = load_all(cache, args.sports, args.kinds)
    ev = evaluate(entries, boot=args.boot)
    out = {"gates": gates(gate), "n_entries": len(entries), "groups": ev, "placeholders": measure_placeholders(series_by),
           "variants": [rule_name(r) for r in RULES] + ["fair"], "boot": args.boot,
           "note": "aggregates only: no tickers, no single-game dates"}
    print("DATA QUALITY GATES (read these first)")
    for sp, g in out["gates"].items():
        print(f"  {sp}: {g['game_winner_games']} games, {g['span']}, {g['pct_with_candles']}% of chosen markets have candles,"
              f" {g['pct_games_with_spread_candles']}% of games have spread candles")
    print(f"  entries replayed: {len(entries)}; groups shown: {len(ev)} (groups under {HIDE_N} games hidden)")
    print("\nMEASURED REPLACEMENTS")
    for sp, m in out["placeholders"].items():
        print(f"  {sp}: {json.dumps(m)}")
    print("\nRESULTS: cents per $1 staked, EDGE = rule minus hold on the same entries, 95% range by game (bootstrap)")
    for g in ev:
        k = g["key"]
        print(f"- sport={k[0]} type={k[1]} entry={k[2]} price={k[3]}  games={g['games']}  hold net={g['cells']['hold']['net_c']}")
        for n in out["variants"]:
            c = g["cells"][n]
            if c:
                print(f"    {('fair*' if n == 'fair' else n):6} net {c['net_c']:7.2f}  edge {c['edge_c']:6.2f}  [{c['lo']}, {c['hi']}]")
        o = g["oos"]
        if "test" in o:
            print(f"    picked on first 70%: {o['picked']}; last 30% ({o['test_games']} games) edge {o['test']['edge_c']}"
                  f" [{o['test']['lo']}, {o['test']['hi']}]; lag60 {o['lag']['60']['edge_c']}; stable {o['stable']};"
                  f" PASS={o['pass']}")
    passes = [g for g in ev if g["oos"].get("pass")]
    print("\n  fair* = buy only when the ask is under the pre-game price taken just before the start. For T-24h and T-4h"
          " entries that price is not known at entry (an ORACLE), so fair* is an upper bound, never a tradable rule and"
          " never picked or passed.")
    print(f"\nPASS BAR (>=1c/$1 over hold, range above 0, 2+ sports or 2+ weeks, survives +60 s lag): {len(passes)} of"
          f" {sum(1 for g in ev if 'test' in g['oos'])} scored groups pass. With this many groups some would pass by"
          " luck alone.")
    out["passes"] = len(passes)
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "report"):
        p = sub.add_parser(name)
        p.add_argument("--cache", default=str(CACHE_DEFAULT))
        p.add_argument("--sports", nargs="+", default=["NFL"], choices=sorted(SPORTS))
        p.add_argument("--kinds", nargs="+", default=["game", "spread", "total"], choices=["game", "spread", "total"])
        if name == "fetch":
            p.add_argument("--limit", type=int, default=0, help="download at most N candle files per series (testing)")
            p.add_argument("--since", help="only games closing on/after this date (YYYY-MM-DD)")
        else:
            p.add_argument("--out")
            p.add_argument("--boot", type=int, default=BOOT)
    a = ap.parse_args(argv)
    return cmd_fetch(a) if a.cmd == "fetch" else cmd_report(a)


if __name__ == "__main__":
    sys.exit(main())
