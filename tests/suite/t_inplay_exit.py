# CHECK: group=engine
# In-play audit (issue #341, Pete): a bet on a game under way is judged on its chance of a profitable exit from the live
# state (Smart Buy's exit simulator, smart_buy_ok), never on a pregame-style edge; a big 'edge' on a trailing team must
# not pass. Stricter only: the panel's live bets (whatever the switch or dial, and again after the buy-time live
# recheck), Buy straight's and Live ideas' green Buy, Live's in-play ideas, Build's spreads/totals and suggested combos,
# Best bets, and the Mac's buy-idea alerts. Fakes only: no network, temp files, a temp history.
import os, time, tempfile, importlib.util, inspect, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.leg_score = lambda l: None
E.comeback_judge = (lambda c, now=None, sim=None: (lambda o: {"ok": o, "old": o, "new": o, "pregame": True,   # (#348)
                    "why": None if o else E.IN_PLAY_WHY})(E.smart_buy_ok(sim if sim is not None else E._sb_sim(c, now))))
now = time.time()


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)


def safe(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


PASS_SIM = {"route": "sell", "ev": 1.0, "p_exit": 0.6, "win": 0.5}
FAIL_SIM = {"route": "none", "ev": -0.6, "p_exit": 0.05, "win": 0.12}   # a trailing team: 'edge' but no way out


def t_live_exit_ok():
    E._sb_sim = lambda c, now: dict(PASS_SIM)
    ok("live_exit_ok: a likely profitable exit passes", E.live_exit_ok("KXNBAGAME-X-A", "KXNBAGAME-X", 0.4, 0.3))
    E._sb_sim = lambda c, now: dict(FAIL_SIM)
    ok("live_exit_ok: a trailing team with a big 'edge' but no likely exit fails", not E.live_exit_ok("KXNBAGAME-X-A", "KXNBAGAME-X", 0.3, 0.12))
    ok("live_exit_ok: no live fair = fails closed", not E.live_exit_ok("KXNBAGAME-X-A", "KXNBAGAME-X", None, 0.3))
    E._sb_sim = lambda c, now: (_ for _ in ()).throw(ValueError("x"))
    ok("live_exit_ok: an error fails closed", not E.live_exit_ok("KXNBAGAME-X-A", "KXNBAGAME-X", 0.4, 0.3))


def t_panel_gate():
    c = {"kind": "single", "live": True, "id": "single:X", "legs": [{"ticker": "KXNBAGAME-X-A", "fair": 0.3, "p": 0.12}]}
    E._sb_sim = lambda c, now: dict(FAIL_SIM)
    keep, why = E.smart_buy_gate(c, now, on=False)
    ok("panel: a live bet with no likely exit is skipped even with Smart Buy switched off", keep is False and why == E.IN_PLAY_WHY)
    E.sb_dial = lambda tks, now=None: {"level": 0, "key": "nba"}
    keep, _ = E.smart_buy_gate(c, now, on=True)
    ok("panel: ...and while the league's dial is at 0 (learning)", keep is False)
    E._sb_sim = lambda c, now: None
    ok("panel: a live bet the simulator can't model is skipped (fail closed)", E.smart_buy_gate(c, now, on=True)[0] is False)
    E._sb_sim = lambda c, now: dict(PASS_SIM)
    ok("panel: a live bet with a likely profitable exit goes through as before", E.smart_buy_gate(c, now, on=True)[0] is True)
    pre = dict(c, live=False)
    E._sb_sim = lambda c, now: dict(FAIL_SIM)
    ok("panel: pregame bets are untouched at dial 0 (as before)", E.smart_buy_gate(pre, now, on=True)[0] is True)
    kept, sk = E.smart_buy_filter([c, pre], now)
    ok("panel: smart_buy_filter drops only the live one, same dicts", kept == [pre] and len(sk) == 1)
    src = inspect.getsource(E._buy_panel_bet)
    ok("panel: the buy-time live recheck runs the exit gate again before any order",
       src.index("live_recheck") < src.index("inplay_exit_ok(c, sim=_sb_sim(c, None)") < src.index("book_depth"))


def t_ideas_gate():
    E.smart_buy_on = lambda: True
    E.sb_dial = lambda tks, now=None: {"level": 0, "key": "nba"}
    live = {"id": 7, "idea_id": "a", "legs": ["KXNBAGAME-X-A"], "pct": 1.4, "live": True, "picks": "A"}
    pre = {"id": 8, "idea_id": "b", "legs": ["KXNBAGAME-Y-A"], "pct": 1.1, "picks": "B"}
    kept, sk = E.smart_buy_ideas_gate([live, pre], now)
    ok("ideas: an in-play idea the shadow hasn't found a likely exit for is left out, with the plain reason",
       kept == [pre] and sk and sk[0]["why"] == E.IN_PLAY_WHY)
    legs_live = dict(pre, legs_info=[{"live": True}])
    ok("ideas: a leg marked live counts as in play", E._idea_in_play(legs_live) and not E._idea_in_play(pre))
    E._exit_shadow_table()
    E.store_x("insert into exit_shadow(ts, cand, source, tickers, ev, new) values(?,?,?,?,?,?)",
              (now, E._sb_idea_cand(live), "idea", E.json.dumps(live["legs"]), 1.0, 1))
    E._cb_table()                                      # (#348) and the comeback model agreed on the same quote
    E.store_x("insert into comeback_shadow(ts, cand, source, ok) values(?,?,?,?)", (now, E._sb_idea_cand(live), "idea", 1))
    kept, sk = E.smart_buy_ideas_gate([live, pre], now)
    ok("ideas: once the shadow found smart_buy_ok on its own quote it is shown", live in kept)


def t_lines_and_combos():
    x = {"ticker": "KXNBASPREAD-X-A3", "event": "KXNBASPREAD-X", "fair": 0.6, "p": 0.4, "kick": now - 600}
    r, why = E._line_rec_one("nba", x, 1000.0, now, [(0.4, 100)])
    ok("lines: a spread/total whose game has started is never recommended (pregame line)", r is None and why == "started")
    E.started = lambda l: bool(l.get("_started"))
    ok("combos: idea_combo_live_gap names the started pick", E.idea_combo_live_gap([{"pick": "A", "_started": True}, {"pick": "B"}]) == ["A"])
    for fn in ("shadow_pass", "best_bets_feed"):
        ok(f"source: {fn} leaves out combos with a pick under way", "idea_combo_live_gap(" in inspect.getsource(getattr(E, fn)))
    ok("source: single_pass skips games under way before any idea or alert", "in live_ok or started(x):" in inspect.getsource(E.single_pass))
    ok("source: Buy straight's green Buy for a live game needs live_exit_ok", "live_exit_ok(" in inspect.getsource(E.single_buy_quote))
    w = open("wtest/combo_watcher.py").read() if os.path.exists("wtest/combo_watcher.py") else ""
    if w:
        ok("source: the Live single idea's green Buy for a live game needs live_exit_ok", "A.live_exit_ok(" in w)
        ok("source: Build's suggested combos skip started games the live checks didn't pass",
           "pre = {e: sd for e, sd in games.items() if e in live_ok or not any(A.started(x) for x in sd)}" in w)


def t_offer():
    """get_offer: a Build combo (not the panel's) with a pick under way never gets the green Buy."""
    E.started = lambda l: bool(l.get("_started"))
    legs = [{"ticker": "KXNBAGAME-X1-A", "event": "KXNBAGAME-X1", "fair": 0.6, "p": 0.3, "pick": "A", "_started": True},
            {"ticker": "KXNBAGAME-X2-A", "event": "KXNBAGAME-X2", "fair": 0.6, "p": 0.55, "pick": "B"}]
    E.CTX.clear()
    E.CTX.update(stake=5.0, offers={}, combos=[{"kind": "own", "legs": legs, "fair": 5 / 0.36, "min": 5 / 0.36 * 0.95}])
    E.CFG.update(budget=500.0, accept_pct=95)
    E.kalshi_send = lambda m, p, body=None, params=None: ({"market_ticker": "M"} if p.startswith("/multivariate") else
                                                         {"id": "r"} if p == "/communications/rfqs" else
                                                         {"quotes": [{"status": "open", "no_bid_dollars": "0.8", "id": "q"}]}
                                                         if p == "/communications/quotes" else {})
    E.find_collection = lambda legs: "C"
    E.clear_my_rfqs = lambda m: None
    E.rfq_unsure = lambda *a, **k: False
    E.hold_refusal = lambda *a, **k: (None, "")
    E.time.sleep = lambda s: None
    E.store_quote = E.carry_note = E.note_quote_time = E.note_buy_ratio = lambda *a, **k: None
    r = E.get_offer(1, 5.0, check_cap=False)
    ok(f"offer: a combo priced far over fair with a started pick is NOT green ({r.get('ok')}, pct {r.get('pct')})", r.get("ok") is False)
    legs[0]["_started"] = False
    r = E.get_offer(1, 5.0, check_cap=False)
    ok("offer: the same combo before the start is green as before", r.get("ok") is True)


for n, fn in (("live_exit_ok", t_live_exit_ok), ("panel", t_panel_gate), ("ideas", t_ideas_gate),
              ("lines", t_lines_and_combos), ("offer", t_offer)):
    safe(n, fn)


def t_single_alert():
    """Pete's real push (2026-11-23): 'Single: Indiana St. (game in progress) at 26c on Kalshi; the sharp books say 40%.
    About 12.9c a contract in your favour after the fee.' A game under way never becomes a single idea or a push, whether
    the start time is known (started) or only the live screen knows it's under way; the same pick before its start still
    does (the control)."""
    ev = "KXNCAAMBGAME-26NOV23INSTEVAN"
    x = {"ticker": ev + "-INST", "event": ev, "pick": "Indiana St.", "p": 0.26, "fair": 0.40, "edge": 0.129,
         "src": "pinnacle", "opp": "Evansville"}
    alerts, ideas = [], []
    for k, v in dict(load_book_state=lambda snap: {}, week_games=lambda m: ({ev: [x]}, {}, {}), fetch_markets=lambda: [],
                     attach_fair=lambda g, b: (1, {}), maker_pass=lambda *a, **k: [],
                     single_candidates=lambda games, live_ok: [dict(x)],
                     book_depth=lambda t, max_age=60: {"thin": False, "ask": 0.26, "ask_size": 500},
                     injury_note=lambda *a: ([], False), game_context=lambda *a: [], edge_stake=lambda *a: 5.0,
                     store_suggestion=lambda c, r, pct: ideas.append(c) or 1,
                     _alert=lambda alert, msg, *a: alerts.append(msg)).items():
        setattr(E, k, v)
    E.CFG.update(include_live=True, killer_mode="off")
    E.started = lambda l: True
    E.screen_live = lambda games, bf: ([], [ev])
    E.single_pass(None, alert="topic", log=lambda *a: None)
    ok("single idea: a game in progress gets no push and no idea card", alerts == [] and ideas == [])
    E.started = lambda l: False                         # start time unknown, but the live screen says it's under way
    E.single_pass(None, alert="topic", log=lambda *a: None)
    ok("single idea: ...nor when only the live screen knows it's under way", alerts == [] and ideas == [])
    E.screen_live = lambda games, bf: ([], [])
    E.single_pass(None, alert="topic", log=lambda *a: None)
    ok("single idea: the same pick before its start is still offered (control), never saying 'in progress'",
       len(alerts) == 1 and "in progress" not in alerts[0] and len(ideas) == 1)


safe("single alert", t_single_alert)
