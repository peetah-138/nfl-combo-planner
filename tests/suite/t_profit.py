# CHECK: group=engine
# Profit leaks from the audit (issue #142): each check fails on the code before the fix.
#  A  the panel ranks by expected dollars, the chance the day ends ahead kept as a floor (switch: old rule)
#  B  stale sharp lines: expired on an empty refresh, give way to fresh free lines, never price a game starting soon
#  C  the green Buy and buy-idea alerts need the league's cut-off (alerts: 100% of calibrated fair too)
#  D  closing prices: the mid is stored and used to learn cut-offs and CLV; re-quotes count once; symmetric rule
#  E  no panel bet on a big gap right after fresh injury news
#  F  Kalshi's fee rounded up to the cent per order; a swapped-in bet sized for itself
import os, sys, time, json, types, tempfile, inspect, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.CUTOFF_FILE = os.path.join(E.HERE, "cut.json")
E.MAIN_SAVED = os.path.join(E.HERE, "no_shared_settings.json")      # switches come from CFG here
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def section(name, fn):
    """A section that raises (old code: a missing function) is a FAIL, never a silent stop."""
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def leg(t, ev, pick, p, fair, **x):
    return dict({"ticker": t, "event": ev, "pick": pick, "p": p, "fair": fair}, **x)


def mk(kind, code, legs, chance, ret, kick, **x):
    for l in legs:
        E.KICKOFF[l["event"]] = iso(kick)
    return E._cand(kind, code, legs, chance, ret, "why", **x)


def single(i, p, fair, kick=None):
    x = leg(f"KXNBAGAME-26NOV21G{i:02d}-A", f"KXNBAGAME-26NOV21G{i:02d}", f"Team{i}", p, fair, vs=f"Opp{i}")
    edge = fair - p - E.single_fee(p)
    return mk("single", "nba", [x], fair, edge / (p + E.single_fee(p)), kick or now + 3 * 3600 + i * 60, price=p)


# ---------------------------------------------------------------- A: rank by dollars
def sec_a():
    # a fake slate: six heavy favorites with a thin edge, and six coin-flip teams priced well under their chance
    favs = [single(i, 0.84, 0.88) for i in range(6)]
    value = [single(10 + i, 0.45, 0.55) for i in range(6)]
    cands = favs + value
    E.CFG["panel_rank_dollars"] = False
    old_p, old_st = E.choose_panel(cands, 40, 300, size=8)
    E.CFG["panel_rank_dollars"] = True
    new_p, new_st = E.choose_panel(cands, 40, 300, size=8)
    print(f"  fake slate, old rule: {len(old_p)} bets, ${old_st['stake']}, chance ahead {old_st['p_ahead']:.0%}, "
          f"expects ${old_st['ev']:.2f}; by dollars: {len(new_p)} bets, ${new_st['stake']}, chance ahead "
          f"{new_st['p_ahead']:.0%}, expects ${new_st['ev']:.2f}")
    ok("A: ranking by dollars expects clearly more profit on the fake slate than the old rule",
       new_st["ev"] >= old_st["ev"] * 1.2 and new_st["ev"] - old_st["ev"] >= 0.5)
    ok("A: ...while the chance the day finishes ahead stays over the floor (55%, near the best)",
       new_st["p_ahead"] >= E.PANEL_AHEAD_FLOOR - 0.02)
    ok("A: ...and it carries more of the bets with the big edge", sum(c["id"] in {v["id"] for v in value} for c in new_p)
       > sum(c["id"] in {v["id"] for v in value} for c in old_p))
    ok("A: the panel says how it ranked", new_st.get("rank") == "dollars" and old_st.get("rank") == "chance")
    # switch off = exactly the old function (kept verbatim below, from before the change)
    ns = dict(vars(E))
    exec(OLD_CHOOSE, ns)
    ref_p, ref_st = ns["choose_panel"](cands, 40, 300, size=8)
    ok("A: with the switch off the panel is exactly what the old code picked",
       [c["id"] for c in ref_p] == [c["id"] for c in old_p] and ref_st["ev"] == old_st["ev"])
    # the rules still hold when ranking by dollars: one straight bet per game, per-game cap, spreads/totals share
    two = [single(30, 0.45, 0.55), dict(single(30, 0.45, 0.55), id="single:other")]
    p2, _ = E.choose_panel(two + favs[:3], 40, 300, size=8)
    ok("A: one straight bet per game still holds", sum(1 for c in p2 if c["legs"][0]["event"].endswith("G30")) == 1)
    p3, st3 = E.choose_panel(cands, 6, 300, size=8)
    ok("A: the budget still holds", st3["stake"] <= 6.01)
    # a slate of long shots only (no panel reaches 55%): it still picks, within 5 points of the best chance
    shots = [mk("combo", "nba", [leg(f"KXNBAGAME-26NOV21L{i}{j}-A", f"KXNBAGAME-26NOV21L{i}{j}", "X", .3, .33) for j in range(2)],
                .33 ** 2, 0.08, now + 3 * 3600, pct=1.08, fair_mult=round(1 / .33 ** 2, 3)) for i in range(5)]
    E.save_json(E.CUTOFF_FILE, {})
    p4, st4 = E.choose_panel(shots, 40, 300, size=6)
    ok("A: a long-shot-only slate still gets a panel", len(p4) >= 1)


OLD_CHOOSE = '''
def choose_panel(cands, budget, base, size=None):
    size = size or PANEL["size"]
    picked, spent, per_game = [], 0.0, defaultdict(int)
    solo = set()
    pool = [dict(c, stake=_size(c, base)) for c in cands if _qualifies(c)]
    while len(picked) < size and pool:
        best = None
        for c in pool:
            evs = _events_of(c)
            if any(per_game[e] >= PANEL["per_game"] for e in evs):
                continue
            if c["kind"] != "combo" and evs[0] in solo:
                continue
            if c["kind"] == "line" and sum(1 for x in picked if x["kind"] == "line") >= max(2, int(size * PANEL["line_share"])):
                continue
            if spent + c["stake"] > budget + 0.01:
                continue
            tot = _sim_panel(picked + [c], n=1500)
            pr = sum(1 for t in tot if t > 0) / len(tot)
            ev = sum(tot) / len(tot)
            score = pr + 0.05 * ev / max(budget, 1) + c.get("prio", 0)
            if best is None or score > best[0]:
                best = (score, c, pr, ev)
        if not best:
            break
        _, c, pr, ev = best
        picked.append(c)
        spent += c["stake"]
        pool = [x for x in pool if x["id"] != c["id"]]
        for e in _events_of(c):
            per_game[e] += 1
            if c["kind"] != "combo":
                solo.add(e)
    floor_n = min(len(picked), 3)
    stats = {}
    for k in range(floor_n, len(picked) + 1):
        tot = _sim_panel(picked[:k], n=2000)
        stats[k] = (sum(1 for t in tot if t > 0) / len(tot), sum(tot) / len(tot))
    if stats:
        top = max(v[0] for v in stats.values())
        ok_k = [k for k, v in stats.items() if v[0] >= top - 0.05]
        picked = picked[:max(ok_k, key=lambda k: stats[k][1])]
    spent = sum(c["stake"] for c in picked)
    tot = _sim_panel(picked) if picked else [0]
    return picked, {"p_ahead": round(sum(1 for t in tot if t > 0) / len(tot), 3), "ev": round(sum(tot) / len(tot), 2),
                    "stake": round(spent, 2), "worst": round(min(tot), 2), "best": round(max(tot), 2)}
'''


# ---------------------------------------------------------------- B: stale sharp lines
def snap(team, opp, fair, src, at, start):
    s = E.empty_snapshot("n")
    for me, other, f in ((team, opp, fair), (opp, team, 1 - fair)):
        s["fair"][me] = [f, src]
        s["games"][me] = [{"fair": [f, src], "start": iso(start), "day": None, "opp": other, "at": at}]
        s["opp"][me] = other
        s["kick"][me] = iso(start)
    return s


def sec_b():
    t = time.time()
    soon, later = t + 2 * 3600, t + 10 * 3600
    old_sharp = snap("Boston Celtics", "Miami Heat", 0.70, "Pinnacle", t - 60 * 60, soon)
    fresh_free = snap("Boston Celtics", "Miami Heat", 0.58, "ESPN BET + Polymarket", t - 60, soon)
    m = E.merge_books(old_sharp, fresh_free)
    ok("B: a sharp line an hour old (it missed its 40-min refresh), game in 2 h, gives way to a fresh free line",
       m["fair"]["Boston Celtics"][0] == 0.58 and m["games"]["Boston Celtics"][0]["fair"][0] == 0.58)
    m = E.merge_books(snap("Boston Celtics", "Miami Heat", 0.70, "Pinnacle", t - 5 * 60, soon), fresh_free)
    ok("B: a fresh sharp line still wins", m["fair"]["Boston Celtics"][0] == 0.70)
    m = E.merge_books(snap("Boston Celtics", "Miami Heat", 0.70, "Pinnacle", t - 3 * 3600, later),
                      snap("Boston Celtics", "Miami Heat", 0.58, "ESPN", t - 60, later))
    ok("B: far from the game (10 h) an older sharp line still wins", m["fair"]["Boston Celtics"][0] == 0.70)
    ok("B: line_stale: old near a game, unknown time near a game, fine far away",
       E.line_stale(t - 60 * 60, soon, t) and not E.line_stale(t - 30 * 60, soon, t) and E.line_stale(None, soon, t) and not E.line_stale(t - 5 * 3600, later, t)
       and not E.line_stale(t - 60, soon, t))
    # the panel: a game starting soon whose line is too old is priced on Kalshi alone (no single, combo or close)
    ev1, ev2 = "KXNBAGAME-26NOV21BOSMIA", "KXNBAGAME-26NOV21LALGSW"
    E.KICKOFF[ev1] = iso(soon)
    E.KICKOFF[ev2] = iso(soon)
    games = {ev1: [leg(ev1 + "-BOS", ev1, "Boston", .55, .70, src="Pinnacle", line_at=t - 60 * 60, edge=.15),
                   leg(ev1 + "-MIA", ev1, "Miami", .47, .30, src="Pinnacle", line_at=t - 60 * 60, edge=-.17)],
             ev2: [leg(ev2 + "-LAL", ev2, "LA", .50, .58, src="Pinnacle", line_at=t - 2 * 60, edge=.08),
                   leg(ev2 + "-GSW", ev2, "GS", .52, .42, src="Pinnacle", line_at=t - 2 * 60, edge=-.1)]}
    n = E.drop_stale_lines(games, t)
    ok("B: panel_collect drops a stale line for a game starting soon", n == 1 and games[ev1][0]["src"] is None
       and abs(games[ev1][0]["fair"] - .55 / 1.02) < 1e-6 and not E.single_candidates({ev1: games[ev1]}))
    ok("B: ...and keeps a fresh one", games[ev2][0]["src"] == "Pinnacle" and games[ev2][0]["fair"] == .58)
    ok("B: panel_collect runs that check before anything is priced or recorded",
       "drop_stale_lines(games)" in inspect.getsource(E.panel_collect)
       and inspect.getsource(E.panel_collect).index("drop_stale_lines(games)") < inspect.getsource(E.panel_collect).index("record_closes("))
    ok("B: free lines carry when they were read", '"at": fetched' in inspect.getsource(E.free_snapshot))
    # the Mac's shared odds cache: an empty refresh expires the old sharp snapshot (and doesn't re-ask every call)
    sys.argv = ["x"]
    os.environ["COMBOWATCH_HOME"] = tempfile.mkdtemp()
    wspec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
    W = importlib.util.module_from_spec(wspec); wspec.loader.exec_module(W)
    asked = []
    fake = types.SimpleNamespace(set_league=lambda lg: None, league_codes=lambda: ["nba"],
                                 free_snapshot=lambda codes: snap("Boston Celtics", "Miami Heat", 0.58, "ESPN", time.time(), soon),
                                 sharp_snapshot=lambda key: asked.append(key) or E.empty_snapshot("out of credits"),
                                 merge_books=E.merge_books, empty_snapshot=E.empty_snapshot)
    o = W.HubOdds()
    o.H = fake
    o.sharp["nba"] = (time.time() - 3 * 3600, snap("Boston Celtics", "Miami Heat", 0.70, "Pinnacle", time.time() - 3 * 3600, later))
    got = o.get("nba", "key")
    ok("B: an empty answer from the odds service drops the old sharp snapshot (free lines only)",
       got["fair"]["Boston Celtics"][0] == 0.58 and "nba" not in o.sharp and len(asked) == 1)
    o.get("nba", "key")
    ok("B: ...and the odds service isn't asked again on the next call (credits)", len(asked) == 1)
    ok("B: the near-game refresh also counts the sharp lines' own start times (leagues with no free lines)",
       abs((W.HubOdds.soonest(E.empty_snapshot(), snap("A", "B", .5, "Pinnacle", t, soon)) or 0) - soon) < 2)


# ---------------------------------------------------------------- C: the green Buy and buy-idea alerts
def sec_c():
    E.save_json(E.CUTOFF_FILE, {})
    E.CFG["accept_pct"] = 90
    legs = [leg("KXNBAGAME-26NOV21AAA-A", "KXNBAGAME-26NOV21AAA", "A", .5, .6),
            leg("KXNBAGAME-26NOV21BBB-B", "KXNBAGAME-26NOV21BBB", "B", .5, .6)]
    ok("C: the green Buy's bar is the league's cut-off (95%) over the 90% setting", abs(E.green_bar(legs) - 0.95) < 1e-9)
    E.save_json(E.CUTOFF_FILE, {"nba:2": {"level": 99, "n": 40}})
    ok("C: ...and follows the league's learned cut-off", abs(E.green_bar(legs) - 0.99) < 1e-9)
    E.save_json(E.CUTOFF_FILE, {})
    E.CFG["idea_bar_strict"] = False
    ok("C: switch off: your setting alone, as before", abs(E.green_bar(legs) - 0.90) < 1e-9 and abs(E.notify_bar(legs) - 0.90) < 1e-9)
    E.CFG["idea_bar_strict"] = True
    # a quote at 92% of fair: green before, yellow ("Buy anyway") now; the panel's own quotes keep their cut-off
    clock = [time.time()]
    real_time, real_sleep = time.time, time.sleep
    calls = []

    def fake_send(method, path, body=None, params=None):
        calls.append((method, path))
        if path.startswith("/multivariate_event_collections/"):
            return {"market_ticker": "KXMVE-TEST"}
        if path == "/communications/rfqs" and method == "POST":
            return {"id": "rfq1"}
        if path == "/communications/quotes":
            return {"quotes": [{"status": "open", "no_bid_dollars": f"{1 - 5 / (5 / 0.36 * 0.92):.6f}", "id": "q1"}]}
        return {}
    saved = {k: getattr(E, k) for k in ("kalshi_send", "find_collection", "rfq_unsure", "clear_my_rfqs", "week_spend",
                                         "store_quote", "note_quote_time", "note_buy_ratio")}
    try:
        E.kalshi_send = fake_send
        E.find_collection = lambda legs: "COLL"
        E.rfq_unsure = lambda *a, **k: False
        E.clear_my_rfqs = lambda m: None
        E.week_spend = lambda: 0
        E.store_quote = E.note_quote_time = E.note_buy_ratio = lambda *a, **k: None
        time.time = lambda: clock[0]
        time.sleep = lambda s: clock.__setitem__(0, clock[0] + s)
        fair_pay = 5 / 0.36
        got = {}
        for kind in ("value", "panel"):
            E.CTX.clear()
            E.CTX.update(combos=[{"kind": kind, "legs": legs, "fair": fair_pay, "min": fair_pay * 0.90,
                                  "kalshi": 5 / 0.25}], stake=5, offers={})
            got[kind] = E.get_offer(1, check_cap=False)
        v, pn = got["value"], got["panel"]
        ok("C: a combo quoted at 92% of fair isn't a green Buy any more (under the 95% cut-off), and says so",
           v.get("ok") is False and abs((v.get("pct") or 0) - 0.92) < 0.01 and v.get("bar") == 95)
        ok("C: the panel's own quotes keep their own cut-off (unchanged)", pn.get("ok") is True and pn.get("bar") is None)
    finally:
        time.time, time.sleep = real_time, real_sleep
        for k, v in saved.items():
            setattr(E, k, v)
    # buy-idea alerts: 100% of the chance corrected by your own record, when that is higher
    E._close_table()
    for i in range(600):                  # NBA teams the books gave 65% won only 45% of the time
        E.store_x("insert or replace into closes values(?,?,?,?,?,?,?,?)",
                  (f"KXNBAGAME-26OCT{i % 28 + 1:02d}C{i:04d}-A", "nba", f"KXNBAGAME-26OCT{i % 28 + 1:02d}C{i:04d}", 0.65, 0.65,
                   now - 86400, now - 86400, "yes" if i % 100 < 45 else "no"))
    E.CALIB["at"] = 0
    fav = [leg("KXNBAGAME-26NOV21CCC-A", "KXNBAGAME-26NOV21CCC", "C", .6, .65),
           leg("KXNBAGAME-26NOV21DDD-B", "KXNBAGAME-26NOV21DDD", "D", .6, .65)]
    cal = [E.calib_fair("nba", .65, l["ticker"]) for l in fav]
    nb = E.notify_bar(fav)
    ok("C: a buy idea needs at least fair on your own record (here well over the 95% cut-off)",
       cal[0] < 0.6 and abs(nb - (.65 * .65) / (cal[0] * cal[1])) < 1e-6 and nb > 1.0)
    src = inspect.getsource(E.shadow_pass)
    ok("C: the Mac's buy-idea alerts use that bar", "notify_bar(c[\"legs\"])" in src and 'pct * 100 >= CFG["accept_pct"]' not in src)
    E.store_x("delete from closes")
    E.CALIB["at"] = 0


# ---------------------------------------------------------------- D: closing prices and the cut-off learning
def quote(legs, pct, pays, ts=None):
    E.store_x("insert into quotes(ts, source, sport, n, legs, stake, pays, fair, kalshi, pct, hours) values(?,?,?,?,?,?,?,?,?,?,?)",
              (ts or now - 5 * 86400, "shadow", "nba", len(legs), json.dumps([[t, .5, .5] for t in legs]), 5.0,
               pays, 20.0, 19.0, pct, 3.0))


def sec_d():
    E._close_table()
    ev = "KXNBAGAME-26NOV21MID"
    E.KICKOFF[ev] = iso(now + 3600)
    E.record_closes({ev: [leg(ev + "-A", ev, "A", .60, .62, src="Pinnacle", bid=.56),
                          leg(ev + "-B", ev, "B", .44, .38, src="Pinnacle", bid=None)]}, "nba")
    E.store_x("update closes set kick=? where event=?", (now - 60, ev))
    ask, mid = E.close_prices([ev + "-A", ev + "-B"]), E.close_prices([ev + "-A", ev + "-B"], mid=True)
    ok("D: the closing ask stays in the old column; the mid is stored too", ask[ev + "-A"] == .60 and mid[ev + "-A"] == .58)
    ok("D: no bid = the ask alone", mid[ev + "-B"] == .44)
    ok("D: CLV is judged against the closing mid", "close_prices([l[\"ticker\"] for l in c[\"legs\"]], mid=True)"
       in inspect.getsource(E.panel_settle))
    E.store_x("delete from quotes")
    E.store_x("delete from closes")
    E.store_x("delete from close_mids")

    same = ["KXNBAGAME-26NOV21SAMA-A", "KXNBAGAME-26NOV21SAMB-B"]
    for i in range(30):                               # the same two games asked 30 times just under the bar, all won
        quote(same, 0.93, 40.0, ts=now - 5 * 86400 + i * 60)
    E.store_x("update quotes set outcome='won'")
    E.save_json(E.CUTOFF_FILE, {"nba:2": {"level": 95, "n": 40}})
    E.adjust_cutoffs(force=True)
    lvl = E.load_json(E.CUTOFF_FILE, {})["nba:2"]["level"]
    ok("D: 30 re-quotes of the same two games count once: the cut-off doesn't move on them", lvl == 95)
    # 30 different pairs just under the bar, worth 1-2% more than they cost: the old rule lowered (>= 1.0), the
    # symmetric one (3% either side) doesn't
    E.store_x("delete from quotes")
    for i in range(30):
        legs = [f"KXNBAGAME-26NOV{10 + i % 9:02d}U{i:03d}-A", f"KXNBAGAME-26NOV{10 + i % 9:02d}V{i:03d}-B"]
        quote(legs, 0.93, 25.5)                       # 1 in 5 won at 25.5 for 5: worth 102% of the cost
    for i, r in enumerate(E.store_rows("select rowid from quotes")):
        E.store_x("update quotes set outcome=? where rowid=?", ("won" if i % 5 == 0 else "lost", r["rowid"]))
    E.save_json(E.CUTOFF_FILE, {"nba:2": {"level": 95, "n": 40}})
    E.adjust_cutoffs(force=True)
    ok("D: worth 2% more than cost isn't enough to lower the bar (symmetric 3% rule)",
       E.load_json(E.CUTOFF_FILE, {})["nba:2"]["level"] == 95)
    # 30 pairs just over the bar, worth exactly their cost at the closing ask but 8% less at the closing mid: raised
    E.store_x("delete from quotes")
    for i in range(30):
        evs = [f"KXNBAGAME-26NOV{10 + i % 9:02d}W{i:03d}", f"KXNBAGAME-26NOV{10 + i % 9:02d}X{i:03d}"]
        for e in evs:
            E.store_x("insert or replace into closes values(?,?,?,?,?,?,?,null)", (e + "-A", "nba", e, .5, .5, now - 3600, now - 3700))
            E.store_x("insert or replace into close_mids values(?,?,?)", (e + "-A", .48, now - 3700))
        quote([e + "-A" for e in evs], 0.96, 20.0)
    E.save_json(E.CUTOFF_FILE, {"nba:2": {"level": 95, "n": 40}})
    E.adjust_cutoffs(force=True)
    lv = E.load_json(E.CUTOFF_FILE, {})["nba:2"]
    ok("D: worth at game time is read at the closing mid (worth 92%, not 100%): the bar goes up",
       lv["level"] == 97 and "92%" in lv["why"])
    E.store_x("delete from quotes")
    E.store_x("delete from closes")
    E.store_x("delete from close_mids")


# ---------------------------------------------------------------- E: news guard
def sec_e():
    real = E.injury_note
    try:
        E.injury_note = lambda code, *teams, hours=48: ([], any(t and "Team40" in t for t in teams))
        big = single(40, 0.48, 0.58)                   # a 10-point gap with fresh news for its team
        small = single(41, 0.50, 0.55)                 # fresh news elsewhere, a small gap: fine
        quiet = single(42, 0.48, 0.58)                 # same gap, no news
        ok("E: the panel skips a big gap right after fresh injury news", not E._qualifies(big))
        ok("E: ...but not a big gap without news, or news without a big gap", E._qualifies(quiet) and E._qualifies(small))
        E.injury_note = lambda code, *teams, hours=48: (_ for _ in ()).throw(RuntimeError("feed down"))
        ok("E: an injury report that can't be read never blocks (as single ideas)", E._qualifies(big))
        E.injury_note = lambda code, *teams, hours=48: ([], any(t and "Team40" in t for t in teams))
        bought = []
        saved = (E.book_depth, E.buy_single)
        E.book_depth = lambda t, max_age=5: {"ask": 0.48, "bid": 0.47}
        E.buy_single = lambda t, n, ask: bought.append((t, n)) or (n, None)
        try:
            r = E._buy_panel_bet(dict(big, stake=5.0))
        finally:
            E.book_depth, E.buy_single = saved
        ok("E: the buy itself checks again: nothing bought, a plain reason", r[0] is False and "injury" in r[1] and not bought)
        ln = {"kind": "line", "code": "nfl", "legs": [{"ticker": "KXNFLSPREAD-X", "pick": "Bears win by 3.5+", "p": .40,
                                                     "fair": .52, "game": "Bears at Lions"}]}
        E.injury_note = lambda code, *teams, hours=48: ([], "Lions" in teams)
        ok("E: a spread is checked against both teams of its game", E.news_gap(ln) is not None)
        E.injury_note = lambda code, *teams, hours=48: ([], code == "nba")
        mix = dict(big, code="mix")
        ok("E: a Mix bet checks each pick's own league's injury report", not E._qualifies(mix))
    finally:
        E.injury_note = real


# ---------------------------------------------------------------- F: fee rounding, swapped-in stake
def sec_f():
    ok("F: Kalshi's fee is rounded up to the cent per order (1 contract at 50c pays 2c, not 1.75c)",
       E.single_fee(0.5, 1) == 0.02 and abs(E.single_fee(0.5) - 0.0175) < 1e-12 and abs(E.single_fee(0.5, 100) - 0.0175) < 1e-12)
    bought = []
    saved = (E.book_depth, E.buy_single)
    E.book_depth = lambda t, max_age=5: {"ask": 0.50, "bid": 0.49}
    E.buy_single = lambda t, n, ask: bought.append((t, n)) or (n, None)
    try:
        c = single(50, 0.50, 0.528)                  # clears the edge at 1.75c a contract, not at 2c
        r = E._buy_panel_bet(dict(c, stake=1.0))
    finally:
        E.book_depth, E.buy_single = saved
    ok("F: a one-contract panel buy counts the rounded fee: no edge left, nothing bought", r[0] is False and not bought)
    alt = single(51, 0.50, 0.55)
    ok("F: a swapped-in bet is sized for itself, never above the stake it replaces",
       E._swap_stake(alt, {"stake": 8.0}, {"base": 300}) == E._size(alt, 300) < 8.0
       and E._swap_stake(alt, {"stake": 2.0}, {"base": 300}) == 2.0 and E._swap_stake(alt, {"stake": 6.0}, {}) == 6.0)
    ok("F: panel_exec uses it", "_swap_stake(alt, c, p)" in inspect.getsource(E.panel_exec))


for name, fn in (("A", sec_a), ("B", sec_b), ("C", sec_c), ("D", sec_d), ("E", sec_e), ("F", sec_f)):
    section(name, fn)
