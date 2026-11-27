# CHECK: group=engine
# money-h-144: three stricter-only changes. (1) #286 the pregame single Buy idea's fair chance follows Buy straight's
# rules: a board side only with a sportsbook behind it, read within SINGLE_FAIR_AGE, a winner's chance calibrated; the
# idea's own stored chance only while fresh; otherwise no fair price (no edge, never green). (2) #482 the old total
# curve never gives a higher chance than the same curve at the league's fitted width. (3) #374 the killer's skipped
# deals are scored (measurement only). Fakes only: nothing is bought.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.set_league("nba")
E.hub_conf = lambda: None
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
T = "KXNBAGAME-26DEC25DENLAL-DEN"
BOOK = {"ask": 0.55, "bid": 0.53, "spread": 0.02, "ask_size": 500}
E.started = lambda s: False
E._game_over = lambda t: False
side = {"ticker": T, "event": "KXNBAGAME-26DEC25DENLAL", "fair": 0.70, "src": "pinnacle", "fair_at": now - 60}

# ---- (1) #286 pregame idea fair chance
f = E.idea_single_fair(T, side, 0.62, BOOK, now=now)
ok(f"fresh board side with a sportsbook: used ({f['fair']}), not the idea's own 0.62", f["fair"] is not None and not f["nofair"]
   and abs(f["fair"] - 0.70) < 0.2 and f["src"] == "sportsbooks")
E_cal = E.calib_fair
E.calib_fair = lambda code, fair, ticker=None, table="closes": round(fair - 0.05, 4)
f = E.idea_single_fair(T, side, 0.62, BOOK, now=now)
ok(f"a winner's chance goes through calib_fair, as on Buy straight ({f['fair']})", f["fair"] == 0.65)
E.calib_fair = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
f = E.idea_single_fair(T, side, 0.62, BOOK, now=now)
ok("a calibration hiccup: no fair price, never the raw one", f["fair"] is None and f["nofair"])
E.calib_fair = E_cal
f = E.idea_single_fair(T, dict(side, fair_at=now - E.SINGLE_FAIR_AGE - 60), 0.62, BOOK, now=now)
ok("a board price older than 12 minutes: no fair price, and it does NOT fall back to the idea's own", f["fair"] is None
   and "minutes old" in f["nofair"] and f["warn"] and f["warn"][0]["k"] == "nofair")
f = E.idea_single_fair(T, {k: v for k, v in side.items() if k != "fair_at"}, 0.62, BOOK, now=now)
ok("a board price of unknown age: no fair price (fails closed)", f["fair"] is None and "unknown age" in f["nofair"])
f = E.idea_single_fair(T, dict(side, src=""), 0.62, BOOK, now=now)
ok("a board side holding Kalshi's own price (no sportsbook): circular, no fair price", f["fair"] is None and "Kalshi's own" in f["nofair"])
f = E.idea_single_fair(T, None, 0.62, BOOK, now=now, pfair_at=now - 3600)
ok("no board side and the idea's chance an hour old: no fair price", f["fair"] is None and f["nofair"])
f = E.idea_single_fair(T, None, 0.62, BOOK, now=now)
ok("no board side and no age for the idea's chance: no fair price", f["fair"] is None)
f = E.idea_single_fair(T, None, 0.62, BOOK, now=now, pfair_at=now - 120)
ok("no board side, the idea's chance 2 minutes old: still used", f["fair"] == 0.62 and f["src"] == "from when it was found")
sp = "KXNBASPREAD-26DEC25DENLAL-DEN5"
f = E.idea_single_fair(sp, {"ticker": sp, "kind": "spread", "fair": 0.55, "src": "model", "fair_at": now - 10}, None, BOOK, now=now)
ok("a spread with a fresh model side: used, not calibrated as a winner", f["fair"] == 0.55 and f["src"] == "line model")
f = E.idea_single_fair(sp, {"ticker": sp, "kind": "spread", "fair": 0.55, "src": "model", "fair_at": now - 3600}, 0.55, BOOK, now=now)
ok("a spread with a stale side: no fair price", f["fair"] is None)
W = open("wtest/combo_watcher.py", encoding="utf-8").read()
blk = W[W.index('if a == "idea":'):W.index('if a == "singlequote":')]
ok("the idea quote passes when the idea's own chance was found", 'pfair_at=row.get("ts")' in blk)
ok("a pregame idea with no fair price still quotes Kalshi's price (not 'gone') and is never green",
   'not fi["live"] and not fi["nofair"]' in blk and "clears = fair is not None and edge" in blk)

# ---- (2) #482 old total curve: never a higher chance than at the fitted width
for code in ("ncaamb", "nba", "ncaaf", "ncaawb", "nfl"):
    for total, line in ((172.5, 163.5), (172.5, 181.5), (220.0, 210.5), (47.5, 44.5), (47.5, 52.5)):
        g = {"total": total}
        old = E._phi((total - line) / E.TOTAL_SD[code])
        got = E.line_fair(code, "total", line, True, g)
        fit = E._fitted_total_sd(code, total)
        ok(f"{code} total {total} strike {line}: {got:.4f} <= old curve {old:.4f}", got <= old + 1e-12)
        if fit and fit > E.TOTAL_SD[code] and line < total:
            ok(f"{code} {total}/{line}: strictly lower on a strike under the book total", got < old)
        if fit and fit > E.TOTAL_SD[code] and line > total:
            ok(f"{code} {total}/{line}: unchanged on a strike above (never raised)", abs(got - old) < 1e-12)
ok("the fitted width for men's college basketball is about 16.5 (wider than 14)", 16 < E._fitted_total_sd("ncaamb", 170) < 17.5)
ok("a league with no fitted width (euroleague) keeps the old curve exactly",
   E._fitted_total_sd("euroleague", 160) is None and E.line_fair("euroleague", "total", 150.5, True, {"total": 160})
   == E._phi((160 - 150.5) / E.TOTAL_SD["euroleague"]))
ok("hockey totals (Poisson) are untouched", E.line_fair("nhl", "total", 5.5, True, {"total": 6.0}) ==
   1 - E._poisson_cdf(5, 6.0))
ok("a total of None is still no fair price", E.line_fair("ncaamb", "total", 150.5, True, {"total": None}) is None)

# ---- (3) #374 killer skipped deals scored
E.store_x("create table if not exists killer(ts real, kind text, legs text, picks text, mode text, status text, "
          "stake real, pays real, pct real, why text, outcome text)")
def row(status, why, outcome, mode="on", stake=10.0, pays=40.0):
    E.store_x("insert into killer(ts, kind, legs, picks, mode, status, stake, pays, pct, why, outcome) values(?,?,?,?,?,?,?,?,?,?,?)",
              (now, "combo", "[]", "x", mode, status, stake, pays, 0.8, why, outcome))
row("skipped", "you already have 2 open bets ($20.00 at risk) on this game (X)", "won")
row("skipped", "you already have 2 open bets ($20.00 at risk) on this game (X)", "lost")
row("skipped", E.KILLER_OVERLAP_UNREAD, None)
row("skipped", "over your spending cap", "won")
row("bought", "", "won")
row("skipped", "you already have 3 open bets on this game", "won", mode="watch")
s = E.killer_skipped_summary()
ok(f"skipped deals: counted by reason ({s})", s["n"] == 4 and s["overlap_n"] == 3 and s["settled"] == 3 and s["overlap_settled"] == 2)
ok("what the skips would have made: +$30 won, -$10 lost; the overlap ones net +$20, all of them +$50",
   s["pl"] == 50.0 and s["overlap_pl"] == 20.0)
ok("killer_summary carries it and still has its old keys", "skipped" in E.killer_summary() and "settled" in E.killer_summary())
E.store_x("drop table killer")
ok("an unreadable history: an empty summary, never a crash", E.killer_skipped_summary()["n"] == 0)
