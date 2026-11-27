#!/usr/bin/env python3
"""Early-exit value test on Kalshi's PUBLIC settled single-game markets. Offline research only.

Two jobs, one file (design: docs/KALSHI_HISTORY_REPLAY.md, pass bar: docs/EXIT_REPLAY.md and the early-exit design):

    python3 tools/kalshi_history_replay.py fetch  --sports NFL NBA        # download + cache public data
    python3 tools/kalshi_history_replay.py report --out summary.json      # replay the exit rules on the cache

HARD RULES (a test enforces the network ones):
  * It uses ONLY Kalshi's public, unauthenticated market-data GETs (market lists, 1-minute candlesticks). There is no
    key, no login, no signing, no order, no portfolio call. The request function refuses any path that is not an exact
    match of the allowlist (regexes), and never sends an auth header.
  * At most one request per second, backs off on 429/5xx, and caches every response on disk, so a rerun costs nothing.
    A lock file in the cache dir keeps two fetches from running at once.
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
import re
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
ID = r"[A-Za-z0-9._-]+"
ALLOWED_PATHS = tuple(re.compile(p) for p in (   # the ONLY paths the fetcher may ask for (public market data), exact
    r"^/historical/cutoff$",
    r"^/historical/markets$",
    r"^/markets$",
    r"^/historical/markets/" + ID + r"/candlesticks$",
    r"^/series/" + ID + r"/markets/" + ID + r"/candlesticks$",
))
DENY = re.compile(r"portfolio|orders", re.I)
ID_RE = re.compile(r"^" + ID + r"$")
FEE_RATE = 0.07                      # Kalshi's standard taker fee rate (the engine's FEE_RATE)
ORDER_N = 100                        # contracts per replayed order (fee rounding is per order)
HIDE_N = 20                          # a group with fewer games than this is never shown
MIN_PASS_GAMES = 50                  # a group needs at least this many games to be eligible to pass
PASS_WEEK_SHARE = 0.7                # share of scored weeks that must be positive (point estimate)
PASS_MIN_WEEKS = 3                   # ... out of at least this many scored weeks
HINDSIGHT = "hindsight line selection"
BOOT = 2000                          # bootstrap resamples
SEED = 7
RETRY_404_S = 24 * 3600              # an empty candle file cached after a 404 is retried after this long
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
# known, so the start is close_time minus this unless the market's own occurrence time is plausible (see kick_of).
GAME_HOURS = {"NFL": 3.0, "NBA": 2.5, "NHL": 2.6, "MLB": 3.0, "NCAAF": 3.3, "NCAAMB": 2.0}
OCC_WINDOW_H = (1.5, 6.0)            # occurrence time is used as the kickoff only if close - occ is in this window (hours)
TOP_PER_EVENT = 2                    # spread/total: keep the N most-traded lines of a game (HINDSIGHT: full-life volume)
CANDLE_HOURS = 36                    # candles fetched: this long before close (covers T-24h entries plus the game)


# --------------------------------------------------------------------------------------------- polite public client
def check_id(x):
    """A ticker/series that is safe to put in a path or a file name: letters, digits . _ - only, never '..'."""
    if not isinstance(x, str) or not ID_RE.match(x) or not x.strip("."):
        raise ValueError("unsafe identifier: %r" % (x,))
    if ".." in x:
        raise ValueError("unsafe identifier: %r" % (x,))
    return x


def candle_path(m):
    """The public candlestick path for a market (hist or live route). The ticker is validated, then quoted."""
    t = urllib.parse.quote(check_id(m["ticker"]), safe="")
    if m.get("route") == "hist":
        return "/historical/markets/" + t + "/candlesticks"
    return "/series/%s/markets/%s/candlesticks" % (urllib.parse.quote(check_id(m["series"]), safe=""), t)


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
        return (isinstance(path, str) and ".." not in path and not DENY.search(path)
                and any(p.match(path) for p in ALLOWED_PATHS))

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


class FetchLock:
    """A lock file in the cache dir while a fetch runs, so two fetches never write the cache at once."""

    def __init__(self, cache):
        self.path = Path(cache) / ".fetch.lock"

    @staticmethod
    def _alive(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    pid = int(self.path.read_text().strip() or 0)
                except (OSError, ValueError):
                    pid = 0
                if pid and self._alive(pid):
                    raise RuntimeError("another fetch is running (pid %d, lock %s)" % (pid, self.path))
                try:
                    self.path.unlink()                    # stale lock from a dead process
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
            return self
        raise RuntimeError("could not take the fetch lock " + str(self.path))

    def __exit__(self, *a):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        return False


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


def candle_file(cache, ticker):
    return cache / "candles" / (check_id(ticker) + ".json.gz")


def candle_cached(cache, m, now=None):
    """True when the market's candle file is usable. An empty file cached after a 404 (marker key 'empty_404') is
    retried after RETRY_404_S; an empty file from any other cause is not retried; a corrupt file is refetched."""
    f = candle_file(cache, m["ticker"])
    if not f.exists():
        return False
    if f.stat().st_size > 400:                                 # a real file; empty ones are tiny
        return True
    try:
        d = read_gz(f)
    except (OSError, EOFError, ValueError):
        return False
    if d.get("rows"):
        return True
    if d.get("empty_404") and (now if now is not None else time.time()) - d.get("empty_at", 0) > RETRY_404_S:
        return False
    return True


def list_series(client, cache, series, log=print):
    """Every settled market of a series, historical list first then the live list (hist wins on a clash), cached ONLY
    after a clean terminal page. An unexpected body raises and caches nothing. Slim markets, route recorded."""
    check_id(series)
    f = cache / "lists" / (series + ".json.gz")
    if f.exists():
        return read_gz(f)
    out, n_route = {}, {"hist": 0, "live": 0}
    for route, path, extra in (("hist", "/historical/markets", {}), ("live", "/markets", {"status": "settled"})):
        cursor, seen = None, set()
        while True:
            params = {"series_ticker": series, "limit": 1000, **extra}
            if cursor:
                params["cursor"] = cursor
            d = client.get(path, params)
            if not isinstance(d, dict) or not isinstance(d.get("markets"), list):
                raise RuntimeError("unexpected list body from %s for %s: nothing cached" % (path, series))
            for m in d["markets"]:
                tk, ev = check_id(m.get("ticker")), m.get("event_ticker") or ""
                if not tk.startswith(series + "-") or not ev.startswith(series + "-"):
                    raise RuntimeError("market %s / event %s is outside series %s: nothing cached" % (tk, ev, series))
                if not (m.get("result") or m.get("settlement_value_dollars") not in (None, "")):
                    continue                                   # not settled
                if tk in out:
                    continue                                   # prefer the historical record over the live one
                s = slim_market(m, series)
                s["route"] = route
                out[tk] = s
                n_route[route] += 1
            cursor = d.get("cursor")
            if not cursor or cursor in seen:
                break
            seen.add(cursor)
    rows = sorted(out.values(), key=lambda r: (r["close"] or 0, r["ticker"]))
    write_gz(f, rows)
    log(f"  {series}: {len(rows)} settled markets listed (hist {n_route['hist']}, live {n_route['live']})")
    return rows


def prep(rows):
    """Admit settled BINARY markets (result yes/no) that have a close time; count everything dropped. A missing
    settlement value is derived from the yes/no result. Voids and scalar markets drop out (a survivorship caveat).
    This runs BEFORE choose() so the line selection never sees a market that would be excluded anyway."""
    c = {"n_listed": len(rows), "n_nonbinary": 0, "n_no_close": 0, "n_no_settle": 0}
    ok = []
    for m in rows:
        if m.get("result") not in ("yes", "no"):
            c["n_nonbinary"] += 1
            continue
        if not m.get("close"):
            c["n_no_close"] += 1
            continue
        if m.get("settle") is None:
            c["n_no_settle"] += 1                              # listing has no settlement value: derive from result
            m = dict(m, settle=10000 if m["result"] == "yes" else 0)
        ok.append(m)
    return ok, c


def choose(markets, kind):
    """Winner markets: all. Spread/total: the TOP_PER_EVENT most-traded lines of each game. HINDSIGHT: 'most traded'
    is measured over the market's whole life, which includes volume after the entry time, so this is look-ahead."""
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
    """1-minute bid/ask candles from CANDLE_HOURS before close to just after it; one request. Cached, resumable.
    A 404 is cached as an empty file with an extra marker key (retried after 24 h); a bad body is not cached."""
    f = candle_file(cache, m["ticker"])
    if candle_cached(cache, m):
        return True
    if not m.get("close"):
        return False
    end = m["close"] + 120
    start = max(m["open"] or 0, end - CANDLE_HOURS * 3600)
    params = {"start_ts": start, "end_ts": end, "period_interval": 1}
    d = client.get(candle_path(m), params)
    if d is None:
        log("  no candles (404): " + m["ticker"])
        write_gz(f, {"fields": CANDLE_FIELDS, "rows": [], "empty_404": True, "empty_at": int(time.time())})
        return False
    if not isinstance(d, dict) or not isinstance(d.get("candlesticks"), list):
        log("  unexpected candle body, not cached: " + m["ticker"])
        return False
    write_gz(f, {"fields": CANDLE_FIELDS, "rows": [slim_candle(c) for c in d["candlesticks"]]})
    return True


def cmd_fetch(args):
    cache = Path(args.cache).expanduser()
    with FetchLock(cache):
        client = Client()
        t0 = time.time()
        for sport in args.sports:
            for kind in args.kinds:
                series = SPORTS[sport][kind]
                ok, cnt = prep(list_series(client, cache, series))
                if args.since:
                    lo = int(dt.datetime.fromisoformat(args.since).replace(tzinfo=dt.timezone.utc).timestamp())
                    ok = [m for m in ok if (m["close"] or 0) >= lo]
                ms = choose(ok, kind)
                todo = [m for m in ms if not candle_cached(cache, m)]
                if args.limit:
                    todo = todo[:args.limit]
                print(f"{sport} {kind}: {cnt['n_listed']} listed ({cnt['n_nonbinary']} void/scalar and {cnt['n_no_close']}"
                      f" without a close time dropped), {len(ms)} chosen, {len(todo)} to download", flush=True)
                for i, m in enumerate(todo, 1):
                    fetch_candles(client, cache, m)
                    if i % 100 == 0:
                        print(f"  {sport} {kind}: {i}/{len(todo)} ({client.requests} requests, {client.backoffs}"
                              f" back-offs, {int(time.time() - t0)}s)", flush=True)
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


FRESH_S = 600                                       # a quote used for an entry or an exit may be at most 10 minutes old


class Series:
    """One market's candles with carried-forward bid/ask (and the time each carried quote was last seen)."""

    def __init__(self, rows):
        rows = [r for r in rows if r[0] is not None]
        rows.sort(key=lambda r: r[0])
        self.ts = [r[0] for r in rows]
        self.bid, self.ask, self.vol = [], [], []
        self.bid_ts, self.ask_ts = [], []              # when the carried bid / ask was last quoted
        self.bid_low, self.ask_high = [], []           # the raw candle's worst bid / ask (for the worse-fill check)
        b = a = bt = at = None
        for r in rows:
            # a one-sided or void book (bid 0 / ask 1.0000) is "no price", never a tradable one
            if r[1] is not None and r[1] > 0:
                b, bt = r[1], r[0]
            elif r[1] == 0:
                b, bt = None, None
            if r[2] is not None and r[2] < 10000:
                a, at = r[2], r[0]
            elif r[2] == 10000:
                a, at = None, None
            self.bid.append(b)
            self.ask.append(a)
            self.bid_ts.append(bt)
            self.ask_ts.append(at)
            self.bid_low.append(r[3])
            self.ask_high.append(r[4])
            self.vol.append(r[6] or 0)

    def idx(self, t):
        """Index of the last candle ending at or before t (what was observable at t), or None."""
        i = bisect.bisect_right(self.ts, t) - 1
        return i if i >= 0 else None

    def idx_ge(self, t):
        """Index of the first candle ending at or after t (where a delayed order would fill), or None."""
        i = bisect.bisect_left(self.ts, t)
        return i if i < len(self.ts) else None

    def bid_fresh(self, i, t):
        return self.bid[i] is not None and t - self.bid_ts[i] <= FRESH_S

    def ask_fresh(self, i, t):
        return self.ask[i] is not None and t - self.ask_ts[i] <= FRESH_S


def hold_value(settle):
    """Dollars a contract pays at settlement: 1, 0 or the settled value (e.g. 0.5 for a tie)."""
    return settle / 10000.0


def trade_outcomes(s, mk, entry_i, rules, lags, kick, first_i=None):
    """Replay every exit rule for one entry. Entry at the ask, exit at the bid, fee both ways, 100 contracts.
    Returns None when the entry has no ask, else {'stake','hold', rule: pnl, ..} in dollars.

    The decision is made from the candle CLOSE (what was observable at that minute's end) and only on a quote at most
    FRESH_S old. Lag: the exit fills at the bid of the FIRST candle ending at or after fire_ts + lag (lag 0 = the firing
    candle itself); if there is none, or its bid is stale or missing, the order does not fill and the trade holds.
    ('w', rule) keys are the worse-fill sensitivity (entry at the candle's ask_high, exit at its bid_low, lag 0)."""
    ask = s.ask[entry_i]
    if ask is None or not (0 < ask < 10000):
        return None
    p = ask / 10000.0
    efee = fee_cents(ORDER_N, p) / 100.0
    stake = ORDER_N * p + efee
    cost_per = stake / ORDER_N                       # all-in cost per contract, dollars
    settle = hold_value(mk["settle"])
    ah = s.ask_high[entry_i]
    ah_ok = s.ask_ts[entry_i] == s.ts[entry_i] and ah is not None and ask <= ah < 10000
    pw = ah / 10000.0 if ah_ok else p
    stake_w = ORDER_N * pw + fee_cents(ORDER_N, pw) / 100.0
    out = {"stake": stake, "hold": ORDER_N * settle - stake, "entry_ask": p, "stake_w": stake_w,
           "hold_w": ORDER_N * settle - stake_w, "lag_fired": 0, "lag_diff": {lag: 0 for lag in lags if lag}}
    n = len(s.ts)
    for rule in rules:
        kind, arg = rule
        fire = None
        if kind == "plus":
            target = cost_per + arg / 100.0
            for j in range(entry_i + 1, n):
                if s.ts[j] >= mk["end_trade"]:
                    break
                if s.bid_fresh(j, s.ts[j]) and s.bid[j] / 10000.0 >= target:
                    fire = j
                    break
        else:                                        # "tminus": at kick - arg minutes, sell if bid > all-in cost
            t_exit = kick - arg * 60
            j = s.idx(t_exit)
            if j is not None and j > entry_i and s.bid_fresh(j, t_exit) and s.bid[j] / 10000.0 > cost_per:
                fire = j
        if fire is None:
            out[("w", rule)] = out["hold_w"]
        else:
            out["lag_fired"] += 1
            bl = s.bid_low[fire]
            bw = (bl if s.bid_ts[fire] == s.ts[fire] and bl is not None and 0 < bl <= s.bid[fire] else s.bid[fire]) / 10000.0
            out[("w", rule)] = ORDER_N * bw - fee_cents(ORDER_N, bw) / 100.0 - stake_w
        for lag in lags:
            key = (rule, lag)
            if fire is None:
                out[key] = out["hold"]
                continue
            jf = fire if lag == 0 else s.idx_ge(s.ts[fire] + lag)
            if lag and jf != fire:
                out["lag_diff"][lag] += 1
            if jf is None or s.ts[jf] >= mk["end_trade"] or not s.bid_fresh(jf, s.ts[jf]):
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
    """(estimated start, source). The market's own occurrence time is used when close - occ is a plausible game length
    (OCC_WINDOW_H hours); otherwise close minus a typical game length. A stand-in, stated plainly in the docs."""
    occ = m.get("occ")
    if occ and OCC_WINDOW_H[0] * 3600 <= m["close"] - occ <= OCC_WINDOW_H[1] * 3600:
        return occ, "occ"
    return m["close"] - int(GAME_HOURS[sport] * 3600), "fallback"


def kick_check(s, kick):
    """Does the volume pattern agree with the kickoff estimate? True when, in the 12 half-hour bins from kick-3h to
    kick+3h, the 30 min after kick trade more than the 30 min before AND that step up is the biggest of the window.
    None when the window has no volume."""
    bins = []
    for k in range(12):
        lo = kick - 3 * 3600 + k * 1800
        bins.append(sum(s.vol[bisect.bisect_right(s.ts, lo):bisect.bisect_right(s.ts, lo + 1800)]))
    if sum(bins) <= 0:
        return None
    jumps = [bins[k] - bins[k - 1] for k in range(1, 12)]
    return bool(bins[6] > bins[5] and bins[6] - bins[5] >= max(jumps))


def market_entries(m, sport, kind, s, kick=None):
    """Every replayed entry for one market. Look-ahead rules: the entry uses only candles at or before the entry time;
    the 'below baseline' flag uses the pre-game mid at kick-5min and is therefore an ORACLE for T-24h/T-4h entries."""
    if kick is None:
        kick = kick_of(m, sport)[0]
    mk = {"settle": m["settle"], "end_trade": m["close"]}
    base = None
    j = s.idx(kick - 300)
    if j is not None and s.bid_fresh(j, kick - 300) and s.ask_fresh(j, kick - 300):
        base = (s.bid[j] + s.ask[j]) / 20000.0
    out = []
    for ename, off in ENTRIES:
        t = kick + off
        i = s.idx(t)
        if i is None or not s.ask_fresh(i, t) or s.ts[i] >= m["close"]:
            continue
        b = bucket(s.ask[i] / 100.0)
        if b is None:
            continue
        res = trade_outcomes(s, mk, i, RULES, LAGS, kick)
        if res is None:
            continue
        res["sport"], res["type"], res["entry"], res["bucket"] = sport, kind, ename, b
        res["game"], res["t"] = (sport, game_key(m)), m["close"]
        res["day"] = (sport, int(m["close"] // 86400))        # the bootstrap/split cluster: one sport-day block
        res["below"] = bool(base is not None and off < 0 and res["entry_ask"] < base)
        out.append(res)
    return out


def load_all(cache, sports, kinds, kick_shift=0, keep_series=True):
    """Returns (entries, gates, measures). Reads the disk cache only; no network. kick_shift (seconds) moves every
    estimated kickoff, for the jitter check."""
    entries, gate, series_by = [], {}, {}
    for sport in sports:
        g = gate.setdefault(sport, {"chosen": 0, "with_candles": 0, "games": set(), "game_with_spread": set(),
                                    "lo": None, "hi": None, "n_listed": 0, "n_nonbinary": 0, "n_no_close": 0,
                                    "n_no_settle": 0, "keys": {k: set() for k in ("game", "spread", "total")},
                                    "d_occ": [], "d_exp": [], "kick_src": {"occ": 0, "fallback": 0}})
        for kind in kinds:
            f = cache / "lists" / (SPORTS[sport][kind] + ".json.gz")
            if not f.exists():
                continue
            ok, cnt = prep(read_gz(f))
            for k, v in cnt.items():
                g[k] += v
            for m in choose(ok, kind):
                g["chosen"] += 1
                gk = game_key(m)
                g["keys"][kind].add(gk)
                if m.get("occ"):
                    g["d_occ"].append((m["close"] - m["occ"]) / 3600.0)
                if m.get("exp"):
                    g["d_exp"].append((m["close"] - m["exp"]) / 3600.0)
                if kind == "game":
                    g["games"].add(gk)
                cf = candle_file(cache, m["ticker"])
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
                kick, src = kick_of(m, sport)
                g["kick_src"][src] += 1
                entries.extend(market_entries(m, sport, kind, s, kick + kick_shift))
                if kind == "game" and keep_series:
                    series_by.setdefault(sport, []).append((m, s))
    return entries, gate, series_by


def mean_ci(cl, rng, boot):
    """cl: clusters [sA, pA, sB, pB, ...]. Edge = 100*(pA/sA - pB/sB). Returns (edge, net_A, lo, hi) or None."""
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


def clusters(rows, rule, lag, worse=False):
    """One cluster per (sport, day) block: every game, side and line that closes that day resamples together.
    rule None = hold; 'fair' = only entries priced under the pre-game baseline. A = the strategy, B = hold on the same
    unfiltered entries. worse=True uses the worse-fill numbers (entry at ask_high, exit at bid_low, lag 0).
    Cluster = [sA, pA, sB, pB, first close time, set of game keys]."""
    d = {}
    for r in rows:
        c = d.setdefault(r["day"], [0.0, 0.0, 0.0, 0.0, r["t"], set()])
        st, ho = (r["stake_w"], r["hold_w"]) if worse else (r["stake"], r["hold"])
        c[2] += st
        c[3] += ho
        c[4] = min(c[4], r["t"])
        c[5].add(r["game"])
        if rule == "fair":
            if r["below"]:
                c[0] += st
                c[1] += ho
        else:
            c[0] += st
            c[1] += ho if rule is None else (r[("w", rule)] if worse else r[(rule, lag)])
    return sorted(d.values(), key=lambda c: c[4])


def games_of(cl):
    return len(set().union(*(c[5] for c in cl))) if cl else 0


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


def weeks_ok(scored, positive):
    return scored >= PASS_MIN_WEEKS and positive >= PASS_WEEK_SHARE * scored


def stat_reasons(test, lag60, sports_pos, wk_scored, wk_pos):
    """Why the statistical part of the pass bar fails (empty = passes). Eligibility (winner only, game count) is added
    by the caller."""
    r = []
    if not (test and test["edge_c"] >= 1.0 and test["lo"] is not None and test["lo"] > 0):
        r.append("test edge under 1c or range not above 0")
    if not ((sports_pos or 0) >= 2 or weeks_ok(wk_scored, wk_pos)):
        r.append("not stable: need 2+ sports with range above 0, or >= %d%% of >= %d scored weeks positive"
                 % (round(PASS_WEEK_SHARE * 100), PASS_MIN_WEEKS))
    if not (lag60 and lag60["edge_c"] >= 1.0 and lag60["lo"] is not None and lag60["lo"] > 0):
        r.append("fails at 60 s lag")
    return r


def evaluate(entries, boot=BOOT, seed=SEED):
    """Per group: hold, every rule (all lags 0), the rule picked on the first 70% scored on the last 30%, the pass bar.
    Only winner markets can pass: spread/total lines are chosen with hindsight (full-life volume)."""
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
        # --- out of sample: pick on the first 70% of day blocks by time, score on the last 30%
        cl_by = {n: clusters(rows, (RULES[i] if i < len(RULES) else "fair"), 0) for i, n in enumerate(names)}
        tr = {n: split_clusters(v)[0] for n, v in cl_by.items()}
        te = {n: split_clusters(v)[1] for n, v in cl_by.items()}

        def train_edge(n):
            sA = sum(c[0] for c in tr[n]); sB = sum(c[2] for c in tr[n])
            return -1e9 if sA <= 0 or sB <= 0 else 100.0 * (sum(c[1] for c in tr[n]) / sA - sum(c[3] for c in tr[n]) / sB)
        pick = max(names[:len(RULES)], key=train_edge)      # the oracle "fair" filter can never be the pick
        pick_rule = RULES[names.index(pick)]
        oos = {"picked": pick, "train_games": games_of(tr[pick]), "test_games": games_of(te[pick]),
               "train_days": len(tr[pick]), "test_days": len(te[pick])}
        reasons = []
        if key[1] != "game":
            reasons.append(HINDSIGHT)
        if len(games) < MIN_PASS_GAMES:
            reasons.append("under %d games" % MIN_PASS_GAMES)
        if oos["test_games"] >= HIDE_N:
            oos["test"] = stat_cell(mean_ci(te[pick], rng, boot))
            lagged = {}
            for lag in LAGS[1:]:
                cl = split_clusters(clusters(rows, pick_rule, lag))[1]
                lagged[lag] = stat_cell(mean_ci(cl, rng, boot))
            oos["lag"] = {str(k): v for k, v in lagged.items()}
            if key[1] == "game":
                oos["worse"] = stat_cell(mean_ci(split_clusters(clusters(rows, pick_rule, 0, worse=True))[1], rng, boot))
            # stability. Sports: the SAME test games and the SAME pooled pick, scored per sport (no re-split), and a
            # sport counts only when its own range is above 0. Weeks: test-slice weeks with >= 10 games.
            test_games = set().union(*(c[5] for c in te[pick]))
            sports_pos = None
            if key[0] == "ALL":
                sports_pos = 0
                for sp in sorted({r["sport"] for r in rows}):
                    sc = clusters([r for r in rows if r["sport"] == sp and r["game"] in test_games], pick_rule, 0)
                    ci = mean_ci(sc, rng, boot) if games_of(sc) >= HIDE_N else None
                    sports_pos += 1 if ci and ci[0] > 0 and ci[2] is not None and ci[2] > 0 else 0
            weeks = {}
            for c in te[pick]:
                weeks.setdefault(week_of(c[4]), []).append(c)
            wk = [mean_ci(v, rng, 0) for v in weeks.values() if games_of(v) >= 10]
            weeks_pos = sum(1 for x in wk if x and x[0] > 0)
            oos["stable"] = {"sports_positive": sports_pos, "weeks_scored": len(wk), "weeks_positive": weeks_pos}
            reasons += stat_reasons(oos["test"], lagged[60], sports_pos, len(wk), weeks_pos)
        else:
            reasons.append("test slice under %d games" % HIDE_N)
        oos["pass"] = not reasons
        oos["pass_reasons"] = reasons
        res.append({"key": list(key), "games": len(games), "entries": len(rows), "cells": cells, "oos": oos,
                    "hindsight": key[1] != "game"})
    return res


def permutation_null(entries, n, seed=SEED):
    """Chance baseline for the pass bar, on the leaf groups that are allowed to pass (one sport, winner markets, one entry
    time, one price bucket, >= MIN_PASS_GAMES games). For each group the per-day-block difference (rule minus hold) is
    kept but its SIGN is shuffled at random, n times, which makes every rule equal to hold on average. Each shuffle then
    runs the same pipeline: pick the best of the 5 rules on the first 70%, score the last 30%, and apply the pass bar
    (test edge >= 1c with range above 0, lag-60 edge the same, and >= 70% of >= 3 scored weeks positive). The range here
    is a normal approximation from the day-block spread, not the bootstrap, so it is approximate. Returns the share of
    these groups that pass by chance, and how often at least one does."""
    rng = random.Random(seed)
    groups = []
    for key in group_keys(entries):
        if key[0] == "ALL" or key[1] != "game" or key[3] == "all":
            continue
        rows = [r for r in entries if in_group(r, key)]
        if len({r["game"] for r in rows}) < MIN_PASS_GAMES:
            continue
        base = clusters(rows, None, 0)
        k = int(len(base) * 0.7)
        if games_of(base[k:]) < HIDE_N:
            continue
        D0 = [[c[1] - b[3] for c, b in zip(clusters(rows, r, 0), base)] for r in RULES]
        D60 = [[c[1] - b[3] for c, b in zip(clusters(rows, r, 60), base)] for r in RULES]
        wk = {}
        for i in range(k, len(base)):
            wk.setdefault(week_of(base[i][4]), []).append(i)
        scored = [v for v in wk.values() if sum(len(base[i][5]) for i in v) >= 10]
        groups.append({"S": [c[2] for c in base], "k": k, "D0": D0, "D60": D60, "weeks": scored})
    if not groups or n <= 0:
        return {"leaf_groups": len(groups), "shuffles": n, "chance_pass_share": None, "chance_any_pass": None}

    def tstat(D, S, eps, lo, hi):
        sS = sum(S[i] for i in range(lo, hi))
        if sS <= 0:
            return None
        e = sum(eps[i] * D[i] for i in range(lo, hi)) / sS
        se = math.sqrt(sum((eps[i] * D[i] - e * S[i]) ** 2 for i in range(lo, hi))) / sS
        return 100.0 * e, 100.0 * (e - 1.96 * se)

    total, any_pass = 0, 0
    for _ in range(n):
        got = 0
        for g in groups:
            m = len(g["S"])
            eps = [1 if rng.random() < 0.5 else -1 for _ in range(m)]
            best, bi = -1e18, 0
            for ri, D in enumerate(g["D0"]):
                t = tstat(D, g["S"], eps, 0, g["k"])
                if t is not None and t[0] > best:
                    best, bi = t[0], ri
            t0, t60 = tstat(g["D0"][bi], g["S"], eps, g["k"], m), tstat(g["D60"][bi], g["S"], eps, g["k"], m)
            if not (t0 and t60 and t0[0] >= 1.0 and t0[1] > 0 and t60[0] >= 1.0 and t60[1] > 0):
                continue
            pos = sum(1 for v in g["weeks"] if sum(eps[i] * g["D0"][bi][i] for i in v) > 0)
            if weeks_ok(len(g["weeks"]), pos):
                got += 1
        total += got
        any_pass += 1 if got else 0
    return {"leaf_groups": len(groups), "shuffles": n, "chance_pass_share": round(total / (n * len(groups)), 4),
            "chance_any_pass": round(any_pass / n, 4)}


def pctl(vals, q):
    if not vals:
        return None
    v = sorted(vals)
    return v[int(round(q * (len(v) - 1)))]


def measure_placeholders(series_by):
    """Measured stand-ins for SB_PRE_CLOSE / SB_PRE_VOL / SB_SPREAD / SB_LIVE_WIDEN from the winner markets' candles,
    plus the kickoff check (kick_check_share)."""
    out = {}
    for sport, lst in series_by.items():
        d1, dt_, vols, sp_pre, sp_live, kick_ok, kick_n = [], [], [], [], [], 0, 0
        for m, s in lst:
            kick = kick_of(m, sport)[0]

            def mid(t):
                j = s.idx(t)
                if j is None or not s.bid_fresh(j, t) or not s.ask_fresh(j, t):
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
            kc = kick_check(s, kick)
            if kc is not None:
                kick_n += 1
                kick_ok += 1 if kc else 0
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
        res["kick_check_share"] = round(kick_ok / kick_n, 3) if kick_n else None
        res["kick_check_games"] = kick_n
        out[sport] = res
    return out


# ------------------------------------------------------------------------------------------------------------ report
def dist(v):
    if not v:
        return None
    return {"n": len(v), "median": round(statistics.median(v), 2), "p10": round(pctl(v, .10), 2),
            "p90": round(pctl(v, .90), 2)}


def gates(gate):
    out = {}
    for sport, g in gate.items():
        games = len(g["games"])
        win = g["keys"]["game"]
        out[sport] = {
            "game_winner_games": games, "markets_chosen": g["chosen"], "markets_with_candles": g["with_candles"],
            "pct_with_candles": round(100.0 * g["with_candles"] / g["chosen"], 1) if g["chosen"] else None,
            "pct_games_with_spread_candles": round(100.0 * len(g["game_with_spread"] & g["games"]) / games, 1)
            if games else None,
            "span": [dt.datetime.fromtimestamp(g["lo"], dt.timezone.utc).strftime("%Y-%m-%d"),
                     dt.datetime.fromtimestamp(g["hi"], dt.timezone.utc).strftime("%Y-%m-%d")] if g["lo"] else None,
            "n_listed": g["n_listed"], "n_nonbinary": g["n_nonbinary"], "n_no_close": g["n_no_close"],
            "n_no_settle": g["n_no_settle"],
            "close_minus_occ_h": dist(g["d_occ"]), "close_minus_exp_h": dist(g["d_exp"]),
            "kick_source_markets": dict(g["kick_src"]),
            "pct_spread_keys_also_winner": round(100.0 * len(g["keys"]["spread"] & win) / len(g["keys"]["spread"]), 1)
            if g["keys"]["spread"] and win else None,
            "pct_total_keys_also_winner": round(100.0 * len(g["keys"]["total"] & win) / len(g["keys"]["total"]), 1)
            if g["keys"]["total"] and win else None,
        }
    return out


def fmt(cell):
    return "n/a" if not cell else f"{cell['edge_c']} [{cell['lo']}, {cell['hi']}]"


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
        print(f"     listed {g['n_listed']}; dropped: {g['n_nonbinary']} void/scalar (survivorship), {g['n_no_close']} with no"
              f" close time; {g['n_no_settle']} had no settlement value (taken from the yes/no result)")
        print(f"     close-minus-occurrence hours {g['close_minus_occ_h']}; close-minus-expected-expiry hours"
              f" {g['close_minus_exp_h']}")
        ks = g["kick_source_markets"]
        print(f"     kickoff taken from occurrence time in {ks['occ']} markets, from close minus a typical game length in"
              f" {ks['fallback']}")
        print(f"     game keys shared with winner markets: spread {g['pct_spread_keys_also_winner']}%, total"
              f" {g['pct_total_keys_also_winner']}%")
    print(f"  entries replayed: {len(entries)}; groups shown: {len(ev)} (groups under {HIDE_N} games hidden)")
    fired = sum(r["lag_fired"] for r in entries)
    if fired:
        parts = ", ".join("lag %d: %.1f%%" % (lag, 100.0 * sum(r["lag_diff"][lag] for r in entries) / fired)
                          for lag in LAGS[1:])
        print(f"  exits that hit a different candle than lag 0 (all rules, {fired} fired exits): {parts}")
        out["lag_changes_candle_pct"] = {str(lag): round(100.0 * sum(r["lag_diff"][lag] for r in entries) / fired, 2)
                                          for lag in LAGS[1:]}
    print("\nMEASURED REPLACEMENTS")
    for sp, m in out["placeholders"].items():
        print(f"  {sp}: {json.dumps(m)}")
        if m.get("kick_check_share") is not None:
            print(f"     kickoff check: in {100 * m['kick_check_share']:.0f}% of {m['kick_check_games']} games the 30 min after"
                  " the estimated kickoff trade more than the 30 min before AND that is the biggest half-hour step-up"
                  " within 3h either side (a low number means the kickoff estimate is off)")
    print("\nRESULTS: cents per $1 staked, EDGE = rule minus hold on the same entries, 95% range by (sport, day) block"
          " (bootstrap). Spread/total lines are SELECTED WITH HINDSIGHT (full-life volume) and can never pass.")
    for g in ev:
        k = g["key"]
        tag = "  [selected-with-hindsight]" if g["hindsight"] else ""
        hold = g["cells"]["hold"]
        print(f"- sport={k[0]} type={k[1]} entry={k[2]} price={k[3]}  games={g['games']}  hold net="
              f"{hold['net_c'] if hold else 'n/a'}{tag}")
        for n in out["variants"]:
            c = g["cells"][n]
            if c:
                print(f"    {('fair*' if n == 'fair' else n):6} net {c['net_c']:7.2f}  edge {c['edge_c']:6.2f}  [{c['lo']}, {c['hi']}]")
        o = g["oos"]
        if o.get("test") is not None:
            lag = (o.get("lag") or {}).get("60")
            print(f"    picked on first 70%: {o['picked']}; last 30% ({o['test_games']} games) edge {fmt(o['test'])};"
                  f" lag60 {fmt(lag)}; stable {o['stable']}; PASS={o['pass']}")
            if o.get("worse") is not None:
                print(f"    worse fill (in at the candle's ask high, out at its bid low): edge {fmt(o['worse'])}")
        if not o["pass"] and o["pass_reasons"]:
            print(f"    not a pass: {'; '.join(o['pass_reasons'])}")
    passes = [g for g in ev if g["oos"].get("pass")]
    print("\n  fair* = buy only when the ask is under the pre-game price taken just before the start. For T-24h and T-4h"
          " entries that price is not known at entry (an ORACLE), so fair* is an upper bound, never a tradable rule and"
          " never picked or passed.")
    print(f"\nPASS BAR (winner markets only; >= {MIN_PASS_GAMES} games; test edge >= 1c/$1 over hold, range above 0; 2+ sports"
          f" each with range above 0, or >= {round(PASS_WEEK_SHARE * 100)}% of >= {PASS_MIN_WEEKS} weeks positive; still >= 1c"
          f" with range above 0 at a 60 s lag): {len(passes)} of {sum(1 for g in ev if g['oos'].get('test') is not None)}"
          " scored groups pass. With this many groups some would pass by luck alone.")
    out["passes"] = len(passes)
    leaf_pass = sum(1 for g in ev if g["oos"]["pass"] and g["key"][0] != "ALL" and g["key"][1] == "game"
                    and g["key"][3] != "all")
    out["leaf_passes"] = leaf_pass
    if args.null:
        nl = permutation_null(entries, args.null)
        out["null"] = nl
        if nl["chance_pass_share"] is None:
            print(f"\nPERMUTATION NULL: {nl['leaf_groups']} eligible leaf groups, nothing to simulate")
        else:
            print(f"\nPERMUTATION NULL ({nl['shuffles']} shuffles of the rule-vs-hold sign by day block): of"
                  f" {nl['leaf_groups']} eligible leaf winner groups, {100 * nl['chance_pass_share']:.1f}% pass by chance"
                  f" (about {nl['chance_pass_share'] * nl['leaf_groups']:.1f} groups), and in {100 * nl['chance_any_pass']:.0f}%"
                  f" of shuffles at least one passes. Actual leaf passes: {leaf_pass}. (Range is a normal approximation;"
                  " the shuffle forces every rule to equal hold on average, so it measures luck from picking the best"
                  " of 5 rules, not whether fees make real edges negative.)")
    if args.kick_jitter_min:
        out["jitter"] = jitter_report(args, cache, ev)
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1))
    return 0


def jitter_report(args, cache, ev):
    """Rerun the whole evaluation with every estimated kickoff moved by +/- kick_jitter_min and say what flips."""
    base = {tuple(g["key"]): g for g in ev}
    base_pass = [k for k, g in base.items() if g["oos"].get("pass")]
    rep = {}
    print(f"\nKICKOFF JITTER (+/- {args.kick_jitter_min} min on every estimated kickoff; {len(base_pass)} groups pass at 0)")
    for sign in (-1, 1):
        shift = sign * args.kick_jitter_min * 60
        e2, _, _ = load_all(cache, args.sports, args.kinds, kick_shift=shift, keep_series=False)
        ev2 = {tuple(g["key"]): g for g in evaluate(e2, boot=args.boot)}
        lost = [k for k in base_pass if not (ev2.get(k) or {}).get("oos", {}).get("pass")]
        gained = [k for k, g in ev2.items() if g["oos"].get("pass") and k not in base_pass]
        lab = "%+d min" % (sign * args.kick_jitter_min)
        print(f"  {lab}: {len(base_pass) - len(lost)} of {len(base_pass)} base passes still pass; {len(lost)} flip to fail;"
              f" {len(gained)} fail-to-pass; {sum(1 for g in ev2.values() if g['oos'].get('pass'))} pass in total")
        for k in base_pass:
            g2 = ev2.get(k)
            st = "PASS" if g2 and g2["oos"]["pass"] else "FAIL (%s)" % ("; ".join(g2["oos"]["pass_reasons"]) if g2 else "hidden")
            print(f"     {'/'.join(k)}: {st}")
        rep[lab] = {"still_pass": len(base_pass) - len(lost), "flip_to_fail": len(lost), "fail_to_pass": len(gained)}
    return rep


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
            p.add_argument("--null", type=int, default=0, help="permutation-null shuffles for the leaf groups (0 = off)")
            p.add_argument("--kick-jitter-min", type=int, default=0,
                           help="rerun with every kickoff moved +/- this many minutes and say what flips (0 = off)")
    a = ap.parse_args(argv)
    return cmd_fetch(a) if a.cmd == "fetch" else cmd_report(a)


if __name__ == "__main__":
    sys.exit(main())
