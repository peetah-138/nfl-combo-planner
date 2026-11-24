# CHECK: group=engine
# Killer deals respect the overlap guard (issue #365, Pete 2026-11-23 "fix the 2 killer paths"). The Mac's automatic
# killer combo and killer single SKIP (never buy) a deal touching a game that already has overlap_n open bets (2) or
# overlap_pct (8%) of the sizing base at risk, with the same Settings › Money switch as the pick lists. It counts every
# open bet on the game (combos, singles, today's panel, standing orders) and the killer's own buys, each real bet once.
# Unlike the pick lists it fails closed: anything unreadable skips the deal. The switch off = today's behaviour, nothing
# read. Hedges, standing orders and the panel are untouched. Fakes only: no network, no orders, a temp history.
import os, json, time, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.MAIN_SAVED = os.path.join(E.HERE, "no_shared_settings.json")      # switches come from CFG here
E.SIZING_FILE = os.path.join(E.HERE, "sizing.json")
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
SRC = open("wahome/engine.py").read()


def safe(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


E.store_x("create table if not exists killer(ts real, kind text, legs text, picks text, mode text, status text, "
          "stake real, pays real, pct real, why text, outcome text)")
E.store_x("create table if not exists maker(ts real, ticker text, pick text, mode text, price real, n int, fair real, "
          "status text, order_id text, filled real, outcome text, updated real, kick real, why text)")
E.trading_paused = lambda: False
E.can_trade = lambda: True
E.week_spend = lambda: 0.0
E.KILLER.update(per_day=50, day_dollars=1000)       # the day caps have their own tests; here only the game guard
E.CFG.update(killer_mode="on", budget=1000, overlap_guard=True, overlap_n=2, overlap_pct=8)

G1, G2, G3, G4 = ("KXNBAGAME-26NOV23AAABBB", "KXNBAGAME-26NOV23CCCDDD", "KXNBAGAME-26NOV23EEEFFF",
                  "KXNBAGAME-26NOV23GGGHHH")
READS = {"bets": 0, "pos": 0}
ACCT = {"bets": [], "pos": [], "bets_err": None, "pos_err": None}


def fake_cap_bets(now=None):
    READS["bets"] += 1
    if ACCT["bets_err"]:
        raise ACCT["bets_err"]
    return list(ACCT["bets"])


def fake_positions():
    READS["pos"] += 1
    if ACCT["pos_err"]:
        raise ACCT["pos_err"]
    return list(ACCT["pos"])


REAL_POSITIONS = E._positions_strict
E.cap_bets = fake_cap_bets
E._positions_strict = fake_positions


def reset(bets=(), pos=(), balance=500.0):
    ACCT.update(bets=list(bets), pos=list(pos), bets_err=None, pos_err=None)
    READS.update(bets=0, pos=0)
    E.ACCT_CACHE.update(at=now, value=(list(bets), balance, "test"))
    E._panel_table()
    for t in ("killer", "maker", "panel"):
        try:
            E.store_x(f"delete from {t}")
        except Exception:
            pass


def combo(tickers, cost):
    return {"status": "pending", "cost": cost, "legs": [{"ticker": t, "event": t.rsplit("-", 1)[0]} for t in tickers]}


def pos(t, cost):
    return {"ticker": t, "position_fp": "3.00", "market_exposure_dollars": f"{cost:.2f}"}


BUYS = []


def act(kind, tickers, stake=5.0):
    legs = [{"ticker": t, "pick": t.rsplit("-", 1)[1]} for t in tickers]
    st = E.killer_act(kind, legs, stake, stake * 2, 1.3, lambda: (BUYS.append(tickers) or (True, "bought")),
                      None, lambda *a: None)
    row = E.store_rows("select status, why from killer order by rowid desc limit 1")
    return st, (dict(row[0]) if row else {})


def t_combo_threshold():
    BUYS.clear()
    reset(bets=[combo([G1 + "-AAA", G2 + "-CCC"], 4.0)], pos=[pos(G1 + "-BBB", 3.0)])
    st, row = act("combo", [G4 + "-GGG", G1 + "-AAA"])
    ok(f"killer combo: a game with 2 open bets (a combo + a single) is skipped, never bought ({st}, {row})",
       st == "skipped" and not BUYS and row.get("status") == "skipped")
    ok(f"...with a plain reason naming the bets and the money ({row.get('why')})",
       "you already have 2 open bets" in (row.get("why") or "") and "$7" in (row.get("why") or ""))
    reset(bets=[combo([G1 + "-AAA", G2 + "-CCC"], 4.0)])
    st, _ = act("combo", [G4 + "-GGG", G1 + "-AAA", G3 + "-EEE"])
    ok(f"killer combo: one open bet on the game (under the line) still buys ({st})", st == "bought" and BUYS)


def t_pct_threshold():
    BUYS.clear()
    reset(pos=[pos(G2 + "-CCC", 1.0)])
    base = E._overlap_base()
    reset(pos=[pos(G2 + "-CCC", round(base * 0.08 + 0.5, 2))])
    st, row = act("single", [G2 + "-DDD"])
    ok(f"killer single: one bet but 8%+ of the base at risk on the game is skipped ({st}, {row.get('why')})",
       st == "skipped" and not BUYS and "at risk" in (row.get("why") or ""))


def t_single_pass():
    """The real killer-single path: single_pass → killer_check → killer_act, on a game at the line."""
    ev = G3
    x = {"ticker": ev + "-EEE", "event": ev, "pick": "EEE", "p": 0.40, "fair": 0.56, "edge": 0.14,
         "src": "pinnacle", "opp": "FFF"}
    singles = []
    saved = {k: getattr(E, k) for k in ("load_book_state", "week_games", "fetch_markets", "attach_fair", "maker_pass",
                                        "single_candidates", "book_depth", "injury_note", "game_context", "edge_stake",
                                        "store_suggestion", "_alert", "screen_live", "started", "killer_check",
                                        "fair_ok", "_killer_single")}
    try:
        for k, v in dict(load_book_state=lambda snap: {}, week_games=lambda m: ({ev: [x]}, {}, {}),
                         fetch_markets=lambda: [], attach_fair=lambda g, b: (1, {}), maker_pass=lambda *a, **k: [],
                         single_candidates=lambda games, live_ok: [dict(x)],
                         book_depth=lambda t, max_age=60: {"thin": False, "ask": 0.40, "ask_size": 500},
                         injury_note=lambda *a: ([], False), game_context=lambda *a: [], edge_stake=lambda *a: 5.0,
                         store_suggestion=lambda c, r, pct: 1, _alert=lambda *a, **k: None,
                         screen_live=lambda games, bf: ([], []), started=lambda l: False,
                         killer_check=lambda legs, snap, live_ok=(): (True, []), fair_ok=lambda x, ask: True,
                         _killer_single=lambda t, n, p: (singles.append(t) or (True, "bought"))).items():
            setattr(E, k, v)
        reset(bets=[combo([G3 + "-FFF", G1 + "-AAA"], 4.0), combo([G3 + "-EEE", G2 + "-CCC"], 3.0)])
        E.single_pass(None, alert=None, log=lambda *a: None)
        row = E.store_rows("select kind, status, why from killer order by rowid desc limit 1")
        ok(f"killer single (single_pass): a game with 2 open combos on it is skipped, nothing bought "
           f"({row and dict(row[0])})", not singles and row and row[0]["kind"] == "single"
           and row[0]["status"] == "skipped" and "2 open bets" in row[0]["why"])
        reset()
        E.single_pass(None, alert=None, log=lambda *a: None)
        ok(f"killer single (single_pass): the same deal on a clear game is bought ({singles})", singles == [ev + "-EEE"])
    finally:
        for k, v in saved.items():
            setattr(E, k, v)


def t_switch_off():
    BUYS.clear()
    E.CFG["overlap_guard"] = False
    try:
        reset(bets=[combo([G1 + "-AAA", G2 + "-CCC"], 4.0)], pos=[pos(G1 + "-BBB", 3.0)])
        ACCT["bets_err"] = E.CapUnknown("down")
        ACCT["pos_err"] = RuntimeError("down")
        ok("switch off: killer_overlap clears every deal", E.killer_overlap([{"ticker": G1 + "-AAA"}]) is None)
        st, _ = act("combo", [G1 + "-AAA", G4 + "-GGG"])
        ok(f"switch off: a killer combo on a game at the line buys as before, with nothing extra read "
           f"({st}, reads {READS})", st == "bought" and BUYS and READS == {"bets": 0, "pos": 0})
    finally:
        E.CFG["overlap_guard"] = True


def t_unreadable():
    real = E.store_rows_strict

    def maker_locked(q, args=()):                   # only the guard reads standing orders strictly
        if "from maker" in q:
            raise RuntimeError("database is locked")
        return real(q, args)
    for name, setup in (("Kalshi's combos can't be read", lambda: ACCT.update(bets_err=E.CapUnknown("no read"))),
                        ("the positions can't be read", lambda: ACCT.update(pos_err=RuntimeError("429"))),
                        ("no balance for the base", lambda: E.ACCT_CACHE.update(value=([], None, "test"))),
                        ("the standing orders can't be read", lambda: setattr(E, "store_rows_strict", maker_locked))):
        BUYS.clear()
        reset()
        setup()
        try:
            st, row = act("single", [G4 + "-HHH"], stake=4.0 + len(name) / 100)
        finally:
            E.store_rows_strict = real
        ok(f"unreadable ({name}): skipped, never bought ({st}, {row.get('why')})",
           st == "skipped" and not BUYS and "couldn't check your open bets" in (row.get("why") or ""))


def t_unread_retry():
    """A deal skipped only because the bets couldn't be read is looked at again after a couple of minutes (a 429
    mustn't cost it for 6 hours); a real 'at the line' skip keeps the 6-hour rule."""
    BUYS.clear()
    reset()
    ACCT["pos_err"] = RuntimeError("429")
    a, _ = act("single", [G3 + "-EEE"])
    ACCT["pos_err"] = None
    b, _ = act("single", [G3 + "-EEE"])
    E.store_x("update killer set ts = ts - ?", (E.KILLER_UNREAD_RETRY + 5,))
    c, _ = act("single", [G3 + "-EEE"])
    ok(f"unreadable skip: not retried at once, retried (and bought) after {E.KILLER_UNREAD_RETRY}s ({a}, {b}, {c})",
       (a, b, c) == ("skipped", None, "bought") and len(BUYS) == 1)
    BUYS.clear()
    reset(pos=[pos(G2 + "-CCC", 1.0), pos(G2 + "-DDD", 1.0)])
    a, _ = act("single", [G2 + "-DDD"])
    E.store_x("update killer set ts = ts - ?", (E.KILLER_UNREAD_RETRY + 5,))
    ACCT["pos"] = []                                # the game is clear now, but a real skip still waits 6 hours
    b, _ = act("single", [G2 + "-DDD"])
    ok(f"a real 'at the line' skip keeps the 6-hour rule ({a}, {b})", (a, b) == ("skipped", None) and not BUYS)


def t_hub_positions():
    """A Mac reading Kalshi through the hub (no local key) still reads positions, so killer isn't blocked for good."""
    keep = {k: getattr(E, k) for k in ("hub_up", "account_pages", "KEYFILE")}
    asked = []
    try:
        E.hub_up = lambda: True
        E.KEYFILE = os.path.join(E.HERE, "no_key.pem")
        E.account_pages = lambda key, key_id, path, field, params=None: asked.append((key, path)) or [pos(G1 + "-AAA", 2)]
        got = REAL_POSITIONS()
        ok(f"positions through the hub with no local key ({asked})", got and asked == [(None, "/portfolio/positions")])
        E.hub_up = lambda: False
        try:
            REAL_POSITIONS()
            raised = False
        except RuntimeError:
            raised = True
        ok("no hub and no key: the positions read raises (so the deal is skipped)", raised)
    finally:
        for k, v in keep.items():
            setattr(E, k, v)


def t_self_stack():
    BUYS.clear()
    reset()
    a, _ = act("single", [G4 + "-GGG"])
    b, _ = act("single", [G4 + "-HHH"])
    c, row = act("combo", [G4 + "-GGG", G2 + "-CCC"])
    ok(f"self-stacking: from zero, two killer buys on one game go through, the third is skipped ({a}, {b}, {c})",
       (a, b, c) == ("bought", "bought", "skipped") and len(BUYS) == 2 and "2 open bets" in (row.get("why") or ""))
    E.store_x("update killer set status='buying' where status='bought'")
    ok("self-stacking: a killer buy still 'buying' (or 'check') counts too",
       E.killer_overlap([{"ticker": G4 + "-GGG"}]) and "2 open bets" in E.killer_overlap([{"ticker": G4 + "-GGG"}]))
    BUYS.clear()
    reset(pos=[pos(G4 + "-GGG", 5.0)])
    E.store_x("insert into killer(ts, kind, legs, picks, mode, status, stake, pays, pct, why) values(?,?,?,?,?,?,?,?,?,?)",
              (now - 60, "single", json.dumps([G4 + "-GGG"]), "GGG", "on", "bought", 5.0, 10.0, 1.3, ""))
    ex = E.killer_exposure()
    ok(f"one bet the account shows and killer's own row for it count once, not twice ({ex.get(G4)})",
       ex.get(G4, {}).get("n") == 1)
    st, _ = act("single", [G4 + "-HHH"])
    ok(f"...so a second deal on that game still buys ({st})", st == "bought")
    reset()
    E.store_x("insert into killer(ts, kind, legs, picks, mode, status, stake, pays, pct, why, outcome) "
              "values(?,?,?,?,?,?,?,?,?,?,?)", (now - 60, "single", json.dumps([G4 + "-GGG"]), "GGG", "on", "bought",
                                                5.0, 10.0, 1.3, "", "won"))
    E.store_x("insert into killer(ts, kind, legs, picks, mode, status, stake, pays, pct, why) values(?,?,?,?,?,?,?,?,?,?)",
              (now - 60, "single", json.dumps([G4 + "-HHH"]), "HHH", "watch", "watched", 5.0, 10.0, 1.3, ""))
    ok("settled killer buys and watch-only rows don't count", not E.killer_exposure().get(G4))


def t_panel_and_orders():
    reset()
    E.store_x("insert into maker(ts, ticker, pick, mode, price, n, fair, status) values(?,?,?,?,?,?,?,?)",
              (now, G2 + "-CCC", "CCC", "on", 0.4, 10, 0.5, "posted"))
    E.store_x("insert into maker(ts, ticker, pick, mode, price, n, fair, status) values(?,?,?,?,?,?,?,?)",
              (now, G2 + "-DDD", "DDD", "watch", 0.4, 10, 0.5, "watching"))
    E._panel_table()
    body = {"items": [{"state": "bought", "stake": 5.0, "legs": [{"ticker": G2 + "-DDD", "event": G2}]},
                      {"state": "skipped", "stake": 5.0, "legs": [{"ticker": G2 + "-CCC", "event": G2}]}]}
    E.store_x("insert into panel(day, mode, ts, status, body) values(?,?,?,?,?)",
              (E._panel_day(), "real", now, "ok", json.dumps(body)))
    ex = E.killer_exposure()
    ok(f"a posted standing order and today's bought panel bet each count; watch orders and skipped panel bets don't "
       f"({ex.get(G2)})", ex.get(G2) == {"n": 2, "risk": 9.0})
    BUYS.clear()
    st, row = act("single", [G2 + "-CCC"], stake=3.0)
    ok(f"...so a killer single on that game is skipped ({st}, {row.get('why')})", st == "skipped" and not BUYS)


def t_untouched():
    """Only killer_act asks; the hedge, standing orders, the panel's auto-buy and watch mode never do."""
    calls = [i for i in range(len(SRC)) if SRC.startswith("killer_overlap(", i) and not SRC.startswith("def ", i - 4)]
    owners = {SRC.rfind("\ndef ", 0, i) for i in calls}
    names = sorted(SRC[o + 5:SRC.index("(", o + 5)] for o in owners)
    ok(f"killer_overlap is called only from killer_act ({names})", names == ["killer_act"])
    for fn in ("hedge_for", "place_hedge", "maker_pass", "panel_exec", "_buy_panel_bet", "_killer_combo", "_killer_single"):
        i = SRC.find(f"\ndef {fn}(")
        body = SRC[i:SRC.index("\ndef ", i + 10)] if i >= 0 else ""
        ok(f"{fn} doesn't use the killer guard", i < 0 or ("killer_overlap" not in body and "killer_exposure" not in body))
    BUYS.clear()
    reset(bets=[combo([G1 + "-AAA", G2 + "-CCC"], 4.0)], pos=[pos(G1 + "-BBB", 3.0)])
    E.CFG["killer_mode"] = "watch"
    try:
        st, _ = act("combo", [G1 + "-AAA", G3 + "-FFF"])
    finally:
        E.CFG["killer_mode"] = "on"
    ok(f"watch mode records the deal as before and reads nothing ({st}, {READS})",
       st == "watched" and not BUYS and READS == {"bets": 0, "pos": 0})


def t_hedge():
    """A game at the line still gets its hedge: the hedge decision never looks at the guard."""
    seen = []
    keep = E.killer_overlap
    E.killer_overlap = lambda legs: seen.append(legs) or "you already have 9 open bets on this game"
    try:
        reset(bets=[combo([G1 + "-AAA", G2 + "-CCC"], 4.0)], pos=[pos(G1 + "-BBB", 3.0)])
        try:
            E.hedge_for(G1 + "-AAA", 0.4)
        except Exception:
            pass                                   # no market here; what matters is that it never asks the guard
    finally:
        E.killer_overlap = keep
    ok("hedge_for on a game at the line never consults the guard (hedges stay allowed)", seen == [])


for n, f in (("combo threshold", t_combo_threshold), ("pct threshold", t_pct_threshold),
             ("single_pass", t_single_pass), ("switch off", t_switch_off), ("unreadable", t_unreadable),
             ("unread retry", t_unread_retry), ("hub positions", t_hub_positions),
             ("self stack", t_self_stack), ("panel and orders", t_panel_and_orders), ("untouched", t_untouched),
             ("hedge", t_hedge)):
    safe(n, f)
