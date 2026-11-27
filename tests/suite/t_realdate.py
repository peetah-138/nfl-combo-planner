# CHECK: group=engine
# Issue #91: Results "Profit by day" AND "Profit by week" group each bet by when the money actually
# moved (cash-out / settlement), not the NFL game/slate date. Display-only: no bet, P/L, or buy/sell
# logic changes — only how a settled bet is DATED in Results.
import os, time, tempfile, importlib.util, datetime as dt
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)


def local_ts(y, m, d, hh=14):
    """A unix ts for local midday on a given date, so date.fromtimestamp lands on that day in any tz."""
    return time.mktime(dt.datetime(y, m, d, hh, 0, 0).timetuple())


# ---- sunday_of: the shared week rounding (Monday back, every other day forward to the coming Sunday) ----
ok("sunday_of: Sunday maps to itself", E.sunday_of(dt.date(2026, 11, 22)).isoformat() == "2026-11-22")
ok("sunday_of: a weekday maps to the coming Sunday", E.sunday_of(dt.date(2026, 11, 18)).isoformat() == "2026-11-22")
ok("sunday_of: Monday maps back to the prior Sunday", E.sunday_of(dt.date(2026, 11, 23)).isoformat() == "2026-11-22")
ok("sunday_of: week_of still uses it for weekly leagues",
   E.week_of("KXNFLGAME-26NOV18BUFKC").isoformat() == "2026-11-22")

# ---- realized_ts: precedence cash-out > settlement > Mac detection (st) > nothing (c) ----
ok("(c) realized_ts prefers the cash-out sell time", E.realized_ts({"cashed_at": 100, "settled_at": 200}, 300) == 100)
ok("(c) realized_ts falls to the settlement time", E.realized_ts({"settled_at": 200}, 300) == 200)
ok("(c) realized_ts falls to the Mac detection time", E.realized_ts({}, 300) == 300)
ok("(c) realized_ts is None when nothing is timestamped", E.realized_ts({}, None) is None)

# ---- (a) a bet CASHED early buckets by its cash-out date, not the game date ----
# Game is Sunday Nov 22 (the future NFL Sunday in issue #91); it was cashed out Wed Nov 18.
cashed = {"cashed_at": local_ts(2026, 11, 18), "week": "2026-11-22"}
day, week = E.realized_buckets(cashed, None)
ok("(a) a cashed-early bet's DAY is the cash-out date, not the game date", day == "2026-11-18")
# (b) and its WEEK is the realized week (the Sunday of the cash-out day), which here is still Nov 22.
ok("(b) its WEEK rounds from the realized date, not the game date", week == "2026-11-22")

# A cash-out in a different week lands in that week, not the game week.
early = {"cashed_at": local_ts(2026, 11, 10), "week": "2026-11-22"}
d2, w2 = E.realized_buckets(early, None)
ok("(a) a bet cashed a week before the game buckets in the earlier week",
   d2 == "2026-11-10" and w2 == E.sunday_of(dt.date(2026, 11, 10)).isoformat())

# ---- (b) won/lost use the settlement time; with none, the Mac detection time st ----
won = {"settled_at": local_ts(2026, 11, 22), "week": "2026-11-22"}
dw, ww = E.realized_buckets(won, local_ts(2026, 11, 25))  # st is later; settled_at wins
ok("(b) a won bet uses Kalshi's settlement time over st", dw == "2026-11-22")
only_st = {"week": "2026-11-22"}
ds, wsk = E.realized_buckets(only_st, local_ts(2026, 11, 23))  # no cashed_at/settled_at: use st (Mon -> prior Sun)
ok("(b) with no settlement time, the Mac detection time st dates it", ds == "2026-11-23" and wsk == "2026-11-22")

# ---- (c) last-resort fallback: an un-timestamped bet still lands on its game date ----
fb = {"week": "2026-11-22"}
df, wf = E.realized_buckets(fb, None)
ok("(c) an un-timestamped NFL bet falls back to the game week (already a Sunday)", df == "2026-11-22" and wf == "2026-11-22")
ok("(c) no week and no timestamp: empty, never a crash", E.realized_buckets({}, None) == ("", ""))
# A daily league's "week" is its game DAY (week_of returns the day for NBA/NHL/AHL/...). The fallback week
# must still round to a Sunday, so an un-timestamped daily-league bet shares a week bar with a timestamped one
# from the same week (Pete uses NBA/NHL daily).
dd, dw = E.realized_buckets({"week": "2026-11-18"}, None)   # an NBA bet whose game was Wed Nov 18
ok("(d) an un-timestamped daily-league bet's week rounds to a Sunday, not the game day", dw == "2026-11-22")
cd2, cw2 = E.realized_buckets({"cashed_at": local_ts(2026, 11, 20)}, None)  # a cashed NBA bet the same week
ok("(d) a cashed and an un-timestamped daily-league bet in one week share a week bar", cw2 == dw == "2026-11-22")

# ---- (d) day and week always come from ONE date in ONE timezone (can't diverge) ----
consistent = True
for days_off in range(-20, 21):
    ts = local_ts(2026, 11, 22) + days_off * 86400
    d, w = E.realized_buckets({"cashed_at": ts}, None)
    if E.sunday_of(dt.date.fromisoformat(d)).isoformat() != w:  # the week is exactly the Sunday of the day
        consistent = False
ok("(d) day and week are consistent: sunday_of(day) == week for every realized date", consistent)

# ---- iso_unix: a Kalshi ISO time -> unix, bad input -> None ----
ok("iso_unix parses a Kalshi ISO time",
   abs(E.iso_unix("2026-11-18T14:00:00Z") - dt.datetime(2026, 11, 18, 14, 0, 0, tzinfo=dt.timezone.utc).timestamp()) < 1)
ok("iso_unix returns None for missing/garbage", E.iso_unix(None) is None and E.iso_unix("not-a-date") is None)

# ---- (e) _fetch_account captures the LAST sell fill as cashed_at, and a settlement time as settled_at ----
E.CFG = dict(E.CFG, kalshi_key_id="fake")
E.load_private_key = lambda pem: "key"
E.KEYFILE = os.path.join(E.HERE, "key.pem"); open(E.KEYFILE, "w").close()
E.account_get = lambda key, kid, path, params=None: {"balance": 30000}
E.all_positions = lambda key, kid, strict=False: []
LEG = {"ticker": "KXNFLGAME-26NOV22BUFKC-KC", "event": "KXNFLGAME-26NOV22BUFKC", "side": "yes"}
# Pre-seed the legs cache so combo_legs doesn't hit the network for our fake combos.
E.fetch_legs_parallel = lambda tickers, cache: cache.update({t: [dict(LEG)] for t in tickers if t not in cache})
E.combo_legs = lambda t, cache: cache.get(t)


def pages(key, kid, path, name, params=None):
    if name == "fills":
        # One combo cashed out over two sell fills; the LATER fill (Nov 18) is the realized moment.
        return [
            {"ticker": "KXMVE-CASH", "side": "yes", "action": "buy", "count": 10, "yes_price": "0.50",
             "created_time": "2026-11-10T12:00:00Z", "fee_cost": "0.00"},
            {"ticker": "KXMVE-CASH", "side": "yes", "action": "sell", "count": 4, "yes_price": "0.90",
             "created_time": "2026-11-17T09:00:00Z", "fee_cost": "0.00"},
            {"ticker": "KXMVE-CASH", "side": "yes", "action": "sell", "count": 6, "yes_price": "0.90",
             "created_time": "2026-11-18T15:30:00Z", "fee_cost": "0.00"},
            # A separate combo that settled won.
            {"ticker": "KXMVE-WON", "side": "yes", "action": "buy", "count": 5, "yes_price": "0.40",
             "created_time": "2026-11-10T12:00:00Z", "fee_cost": "0.00"},
        ]
    if name == "settlements":
        return [{"ticker": "KXMVE-WON", "revenue": "5.00", "yes_total_cost": "2.00", "no_total_cost": "0.00",
                 "yes_count": 5, "settled_time": "2026-11-22T20:00:00Z"}]
    return []


E.account_pages = pages
E.hub_up = lambda: False
E.ACCT_CACHE = {"at": 0, "value": None}
bets, bal, note = E._fetch_account()
by = {b["ticker"]: b for b in bets}
cash = by.get("KXMVE-CASH"); wonb = by.get("KXMVE-WON")
ok("(e) a cashed combo is captured with its last sell fill as cashed_at",
   cash is not None and cash["status"] == "cashed"
   and dt.datetime.fromtimestamp(cash["cashed_at"]).date() == dt.date(2026, 11, 18))
ok("(e) cashed_at is the LAST sell, not the first (Nov 18, not Nov 17)",
   cash and dt.datetime.fromtimestamp(cash["cashed_at"]).date() != dt.date(2026, 11, 17))
ok("(e) a won combo carries Kalshi's settlement time as settled_at",
   wonb is not None and wonb["status"] == "won" and wonb["settled_at"]
   and dt.datetime.fromtimestamp(wonb["settled_at"]).astimezone(dt.timezone.utc).date() == dt.date(2026, 11, 22))
ok("(e) a cashed combo carries no settled_at; a won combo carries no cashed_at",
   cash["settled_at"] is None and wonb["cashed_at"] is None)

# And the full chain: the cashed combo (game Nov 22) buckets by its Nov 18 cash-out, in both day and week.
cday, cweek = E.realized_buckets(cash, None)
ok("(a)(b) end to end: the cashed combo dates by Nov 18 cash-out, not the Nov 22 game",
   cday == "2026-11-18" and cweek == "2026-11-22")

# ---- issue #207: the date on Live's Settled cards (done_stamp = realized_ts, display only) ----
cache = {}
ok("(207) done_stamp prefers the cash-out time", E.done_stamp({"ticker": "A", "cashed_at": 100, "settled_at": 200}, cache) == 100.0)
ok("(207) done_stamp falls to Kalshi's settlement time", E.done_stamp({"ticker": "A", "settled_at": 200}, cache) == 200.0)
reads = []
_real_rows = E.store_rows
E.store_rows = lambda sql, args=(): (reads.append(sql) or [{"combo": "M1", "settled": 300}])
ok("(207) done_stamp falls to the Mac's own record (read once for many cards)",
   E.done_stamp({"ticker": "M1"}, cache) == 300.0 and E.done_stamp({"ticker": "M1"}, cache) == 300.0 and len(reads) == 1)
ok("(207) nothing timestamped = None, never a made-up date", E.done_stamp({"ticker": "ZZ", "week": "2026-11-22"}, cache) is None)
E.store_rows = lambda sql, args=(): (_ for _ in ()).throw(RuntimeError("db gone"))
ok("(207) an unreadable record never raises, it just shows no date", E.done_stamp({"ticker": "Q"}, {}) is None)
E.store_rows = _real_rows
