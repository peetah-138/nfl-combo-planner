# CHECK: group=engine
# Buy/recommend path follow-ups to issue #482 (CBB totals, items 5-7). Fakes only: no network, no orders.
#  6. a Kalshi event is priced from an ESPN game only when the event's own date is that game's day (no rematch mixups).
#  5. the Live card claims a pace only for a full-game total (not a first-half or team total).
#  7. line_pass (the alert path) runs the Build page's checks (_line_rec_one) and never offers more than they fill.
import os, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)

# ---- item 6: the date
chk = E._event_day_ok
ok("same day passes", chk("KXNCAAMBTOTAL-26NOV27DUKEUNC", "2026-11-27T23:00Z") is True)
ok("evening game after midnight UTC passes (ticker is the local day)", chk("KXNCAAMBTOTAL-26NOV27DUKEUNC", "2026-11-28T02:30Z") is True)
ok("a rematch two days later is refused", chk("KXNCAAMBTOTAL-26NOV29DUKEUNC", "2026-11-27T23:00Z") is False)
ok("a ticker dated after the ESPN day is refused", chk("KXNCAAMBTOTAL-26NOV28DUKEUNC", "2026-11-27T23:00Z") is False)
ok("a ticker dated 2 days before the ESPN day is refused", chk("KXNCAAMBTOTAL-26NOV25DUKEUNC", "2026-11-27T23:00Z") is False)
ok("unreadable start leaves the old match", chk("KXNCAAMBTOTAL-26NOV29DUKEUNC", None) is True)

E.espn_lines = lambda code: {frozenset({"duke blue devils", "unc tar heels"}): {
    "home": "UNC Tar Heels", "away": "Duke Blue Devils", "home_abbr": "UNC", "away_abbr": "DUKE",
    "spread_home": -3.5, "total": 150.5, "start": "2026-11-27T23:00:00Z"}}


def mk(ev, strike, p):
    return {"ticker": ev + "-" + str(int(strike)), "event_ticker": ev, "yes_sub_title": f"Over {strike} points scored",
            "floor_strike": strike, "last_price_dollars": str(p), "kind": "total"}
E.line_markets = lambda code: [mk("KXNCAAMBTOTAL-26NOV27DUKEUNC", 150.5, .50), mk("KXNCAAMBTOTAL-26NOV29DUKEUNC", 150.5, .50)]
E.price = lambda m: float(m["last_price_dollars"])
got = {x["event"] for x in E.line_candidates("ncaamb", everything=True)}
ok("priced: today's event only, not the same teams on the 29th", got == {"KXNCAAMBTOTAL-26NOV27DUKEUNC"})

# ---- item 5: which totals get a pace
for t, want in (("KXNCAAMBTOTAL-26NOV27DUKEUNC-150", True), ("KXNBATOTAL-26NOV27LALBOS-220", True),
                ("KXNCAAMB1HTOTAL-26NOV27DUKEUNC-70", False), ("KXNBATEAMTOTAL-26NOV27LALBOS-LAL110", False),
                ("KXEPLTOTAL-26NOV27ARSCHE-2", True), ("KXNCAAMBSPREAD-26NOV27DUKEUNC-DUKE3", False)):
    ok(f"_full_game_total({t}) is {want}", E._full_game_total(t) is want)

# ---- item 7: line_pass runs the Build page's checks
import datetime as dt
far = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)).isoformat()
tk = "KXNBASPREAD-26NOV27LLLMMM-LLL3"
cand = {"ticker": tk, "event": "KXNBASPREAD-26NOV27LLLMMM", "pick": "LLL -3.5", "p": 0.40, "fair": 0.50, "edge": 0.09,
        "kind": "spread", "book_line": -3.5, "start": far}
E.line_candidates = lambda code: [dict(cand)]
E.book_depth = lambda t, max_age=60: {"thin": False, "ask": 0.40, "ask_size": 500}
E.books_now = lambda ts, budget=None: {t: [] for t in ts}
E._manual_base = lambda: 0.0
E.edge_stake = lambda *a: 20.0                       # would be int(20 / 0.4x) = 47 contracts on its own
E.store_suggestion = lambda leg, buy, pct: (calls.append(buy), 1)[1]
E.store_x = lambda *a, **k: None
E.store_rows = lambda *a, **k: []
calls = []
E._line_rec_one = lambda code, x, base, now, asks: (None, "route")
ok("line_pass: a strike the Build page's checks refuse gets no idea", E.line_pass("nba") == [] and not calls)
E._line_rec_one = lambda code, x, base, now, asks: ({"n": 7}, None)
did = E.line_pass("nba")
ok("line_pass: a passing strike is offered", len(did) == 1)
ok("line_pass: ...for no more contracts than fill inside the edge (7, not 47)", calls and calls[0]["pays"] == 7.0)
def boom(*a): raise RuntimeError("book read failed")
E._line_rec_one = boom; calls.clear()
ok("line_pass: an error in the checks fails closed (no idea)", E.line_pass("nba") == [] and not calls)
