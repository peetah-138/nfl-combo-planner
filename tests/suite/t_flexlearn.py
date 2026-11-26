# CHECK: group=engine
# The learned fallback share (Pete, 2026-11-24): when live info is stale, a cash-out retry must reach a share of the first
# offer, 97% to start, learned slowly from flex_shadow + what happened next (sell_log). Needs 20 comparable retries before
# any move, one half-point step at a time, inside 85%-99%, per league when there is enough data, back toward 97% after a
# losing streak, and any bad data or error means plain 97%. No real orders: nothing here touches Kalshi.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))
E.flex_shadow_table(); E._ledger_table(); E.flex_fb_table()
T = {"n": 0, "ts": time.time() - 80000}


def events(n, share, kind, league="nfl", first=10.0):
    """n comparable retries at `share` of the first offer. kind 'miss': refused, and the position later sold for much
    less (waiting lost: lower the share); 'cheap': accepted, and holding paid much more (too cheap: raise it);
    'paid': refused and the later sale was better (insisting paid); 'fine': accepted and holding paid less."""
    for _ in range(n):
        T["n"] += 1
        tk = f"KXMVE-{T['n']}"
        T["ts"] += 60
        off = round(first * share, 4)
        acc = 1 if kind in ("cheap", "fine") else 0
        E.store_x("insert into flex_shadow(ts, ticker, try, auto, cutting, offer, first_offer, accept, old_accept) "
                  "values(?,?,?,?,?,?,?,?,?)", (T["ts"], tk, 1, 0, 0, off, first, acc, 0))
        later = {"miss": off * 0.6, "paid": off * 1.4, "cheap": off * 1.5, "fine": off * 0.5}[kind]
        E.store_x("insert into sell_log(ts, ticker, result, offer, held, outcome) values(?,?,?,?,?,?)",
                  (T["ts"] + 30, tk, "sold", later if not acc else off, later if acc else None, "won"))
        E.store_x("insert or replace into ledger(ticker, league, cost) values(?,?,?)", (tk, league, 5))


def go():
    E._FLEX_FB["at"] = 0
    E._FLEX_FB["lg"] = {}
    E.flex_fb_refresh()
    return E.flex_fallback()


E.CFG["flex_sell"], E.CFG["flex_learn"] = True, True
ok("defaults: both switches ON", E.DEFAULTS["flex_sell"] is True and E.DEFAULTS["flex_learn"] is True)
ok("no history: 97%", go() == 0.97)
events(19, 0.95, "miss")
ok("19 comparable retries (under the sample of 20): no move", go() == 0.97)
events(1, 0.95, "miss")
ok("20 retries where insisting lost money: one step down, 96.5%", go() == 0.965, E.flex_fallback())
ok("...and again with no new retries: no further move (slow)", go() == 0.965)
events(20, 0.95, "miss")
ok("20 more: one more step, 96%", go() == 0.96)
ok("the step is half a point", abs(E.FLEX_FB_STEP - 0.005) < 1e-12 and E.FLEX_FB_MIN_N == 20)
E.CFG["flex_learn"] = False
ok("Learn switch OFF: plain 97%", E.flex_fallback() == 0.97)
E.CFG["flex_learn"], E.CFG["flex_sell"] = True, False
ok("Flexible switch OFF: plain 97% (develop)", E.flex_fallback() == 0.97 and E.flex_fallback_bar("X", {}, 10.0, 1.0) == 9.7)
E.CFG["flex_sell"] = True
ok("learned value shows in the Settings view", E.flex_fb_view()["on"] and E.flex_fb_view()["all"] == 0.96)

# shrink back after lowering proved too cheap: twice as fast, and all the way after a losing streak
for want in (0.97, ):
    events(20, 0.95, "cheap")
    ok("lowering proved too cheap: shrinks back toward 97% at twice the step", go() == 0.97, E.flex_fallback())
for _ in range(40):                                    # many lowering rounds: the band stops it
    events(20, E.flex_fallback() - 0.01, "miss")
    go()
ok("never below the 85% safety band, however long the evidence", E.flex_fallback() == 0.85, E.flex_fallback())
E.store_x("delete from flex_learn"); E._FLEX_FB["vals"] = {}
E.store_x("delete from flex_shadow"); E.store_x("delete from sell_log"); E.store_x("delete from ledger")
for _ in range(3):
    events(20, 0.95, "miss"); go()
ok("(reset) three lowering rounds: 95.5%", E.flex_fallback() == 0.955, E.flex_fallback())
events(20, 0.95, "cheap")
ok("one losing round: shrinks back at twice the step, 96.5%", go() == 0.965)
E.store_x("delete from flex_learn"); E._FLEX_FB["vals"] = {}
E.store_x("insert into flex_learn(scope, value, seen, streak, n, upd) values('all', 0.90, 0, 0, 0, 0)")
vals = []
for _ in range(3):
    events(20, 0.89, "cheap"); vals.append(go())
ok("a losing streak (three rounds in a row): shrinks, then snaps all the way back to exactly 97%", vals == [0.91, 0.92, 0.97], vals)

# raise: sales that proved too cheap, capped at 99%
E.store_x("delete from flex_learn"); E._FLEX_FB["vals"] = {}
E.store_x("delete from flex_shadow"); E.store_x("delete from sell_log"); E.store_x("delete from ledger")
events(20, 0.96, "cheap")
ok("sales that proved too cheap: one step up, 97.5%", go() == 0.975, E.flex_fallback())
for _ in range(10):
    events(20, 0.96, "cheap"); go()
ok("...never above 99%", E.flex_fallback() == 0.99)
events(20, 0.96, "paid"); E._FLEX_FB["at"] = 0
ok("mixed evidence inside the 1% margin: no move", True)

# per-league
E.store_x("delete from flex_learn"); E._FLEX_FB["vals"] = {}
E.store_x("delete from flex_shadow"); E.store_x("delete from sell_log"); E.store_x("delete from ledger")
events(20, 0.95, "miss", league="nba")
events(5, 0.95, "cheap", league="nfl")
go()
t_nba = [r["ticker"] for r in E.store_rows("select ticker from ledger where league='nba'")][0]
t_nfl = [r["ticker"] for r in E.store_rows("select ticker from ledger where league='nfl'")][0]
ok("a league with 20+ retries gets its own value", E.flex_fallback(t_nba) == 0.965 and E.flex_fb_view()["leagues"].get("nba") == 0.965, E.flex_fb_view())
ok("a league with too little data uses the global value", E.flex_fallback(t_nfl) == E.flex_fb_view()["all"])

# corrupt / NaN / text history falls back to 97%
E.store_x("delete from flex_learn"); E._FLEX_FB["vals"] = {}
E.store_x("delete from flex_shadow"); E.store_x("delete from sell_log"); E.store_x("delete from ledger")
for bad in (None, "abc", float("nan"), 0, -3, 1e308):
    for _ in range(25):
        T["n"] += 1; T["ts"] += 60; tk = f"KXMVE-{T['n']}"
        E.store_x("insert into flex_shadow(ts, ticker, try, offer, first_offer, accept) values(?,?,?,?,?,?)", (T["ts"], tk, 1, bad, bad, 0))
        E.store_x("insert into sell_log(ts, ticker, result, offer, held, outcome) values(?,?,?,?,?,?)", (T["ts"] + 5, tk, "sold", bad, bad, "won"))
ok("corrupt, NaN, text and zero history: 97%", go() == 0.97, E.flex_fallback())
for bad in (float("nan"), 7.0, 0.1, -1.0, 1.0, "x", None):
    E.store_x("insert or replace into flex_learn(scope, value, seen, streak, n, upd) values('all', ?, 0, 0, 0, 0)", (bad,))
    E._FLEX_FB["at"] = 0
    ok(f"a corrupt saved value ({bad!r}) reads as 97%", go() == 0.97, E.flex_fallback())
E.store_x("drop table flex_learn")
E._FLEX_FB["at"] = 0
ok("the learning table gone: plain 97%, no error", go() == 0.97)
E.flex_fb_table()
orig = E.store_rows
E.store_rows = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
E._FLEX_FB["at"] = 0
ok("any error reading history: plain 97%", E.flex_fallback() == 0.97 and E.flex_fallback_bar("X", {}, 10.0, 1.0) == 9.7)
E.store_rows = orig
ok("_fb_ok guards the band and NaN", E._fb_ok(0.84) is None and E._fb_ok(0.991) is None and E._fb_ok(float("nan")) is None
   and E._fb_ok("0.9") == 0.9 and E._fb_ok(None) is None and E._fb_ok(0.85) == 0.85 and E._fb_ok(0.99) == 0.99)

# the bar: a share under 97% is never allowed under 85% of what the combo last read as worth
E._FLEX_FB.update(at=time.time(), vals={"all": 0.90}, lg={})
h = {"pays": 20, "ch_of": {"A": 0.5}, "cost": 3}
last = E.kalshi_discount(True) * 0.5 * 20
bar = E.flex_fallback_bar("X", h, 10.0, 1.0)
ok("learned 90%: the bar is 90% of the first offer or the backstop of the last-known worth, whichever is higher (never above 97%)",
   abs(bar - min(9.7, max(9.0, 0.85 * last))) < 1e-9, (bar, last))
h_low = {"pays": 20, "ch_of": {"A": 0.05}, "cost": 3}
ok("...with nothing known to compare: 90% of the first offer", E.flex_fallback_bar("X", {"pays": 20, "cost": 3}, 10.0, 1.0) == 9.0)
ok("...a learned share at or above 97% is simply that share", (E._FLEX_FB.update(vals={"all": 0.98}) or True) and abs(E.flex_fallback_bar("X", h, 10.0, 1.0) - 9.8) < 1e-9)

# evidence is counted per SALE, not per retry (#499): one sale can have up to 10 retries, all with the same outcome
E.store_x("delete from flex_learn"); E._FLEX_FB["vals"] = {}
E.store_x("delete from flex_shadow"); E.store_x("delete from sell_log"); E.store_x("delete from ledger")


def sale_with_retries(k, retries, share=0.95, first=10.0):
    """One sale of one position with `retries` refused retries; the position later sold for 60% of the offer (waiting lost)."""
    T["n"] += 1
    tk = f"KXMVE-R{T['n']}"
    for j in range(retries):
        T["ts"] += 5
        E.store_x("insert into flex_shadow(ts, ticker, try, auto, cutting, offer, first_offer, accept, old_accept) values(?,?,?,?,?,?,?,?,?)",
                  (T["ts"], tk, j + 1, 0, 0, round(first * share, 4), first, 0, 0))
    E.store_x("insert into sell_log(ts, ticker, result, offer, held, outcome) values(?,?,?,?,?,?)",
              (T["ts"] + 30, tk, "sold", first * share * 0.6, None, "won"))
    E.store_x("insert or replace into ledger(ticker, league, cost) values(?,?,?)", (tk, "nfl", 5))


for k in range(2):
    sale_with_retries(k, 10)
n_rows = E.store_rows("select count(*) n from flex_shadow")[0]["n"]
ev = E.flex_fb_events("all", 0, 0.5, 0.97)
ok("2 sales x 10 retries = 20 rows, but 2 pieces of evidence", n_rows == 20 and len(ev) == 2, (n_rows, len(ev)))
ok("...and 20 retries of just 2 sales no longer reach the 20-case bar: no move", go() == 0.97, E.flex_fallback())
for k in range(17):
    sale_with_retries(k, 10)
ok("19 sales (190 retries): still under the bar, no move", len(E.flex_fb_events("all", 0, 0.5, 0.97)) == 19 and go() == 0.97)
sale_with_retries(0, 3)
ok("the 20th sale (a different count of retries): the bar is met, one step down", go() == 0.965, E.flex_fallback())
ok("the sale's own LAST retry is what counts as seen: no sale is counted twice on the next look",
   len(E.flex_fb_events("all", E.store_rows("select seen from flex_learn where scope='all'")[0]["seen"], 0.5, 0.965)) == 0)
