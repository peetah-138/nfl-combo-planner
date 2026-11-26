# CHECK: group=engine
# Money batch G. #177: a Buy-idea push (combo and single) goes out only if the Live page's Smart Buy gate would show the
# idea (skip-only, fails closed). #451: a lost or unclear reply hides a Buy idea only while the order might still be live
# (IDEA_UNSURE_SECS, and only when the Mac can see what you hold); a definite buy still hides it for days.
# Fakes only: no network, no orders, temp files and history.
import os, time, tempfile, importlib.util, json, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.injury_note = lambda code, *teams, hours=48: ([], False)
E.game_context = lambda code, *teams: []
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.IDEA_DISMISS = os.path.join(E.HERE, "combo_idea_dismiss.json")
E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.SB_DIAL_FILE = os.path.join(E.HERE, "sb.json")
E.leg_score = lambda l: None
E.LEAGUE["code"] = "nba"
import datetime as dt
iso = lambda secs: (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=secs)).isoformat()
D = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=5)).strftime("%y%b%d").upper()
now = time.time()


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)


def safe(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def single(tag, pct=1.10):
    ev = f"KXNBAGAME-{D}{tag}"
    tk = f"{ev}-{tag[:3]}"
    E.KICKOFF[ev] = iso(7200)
    E.PICK_NAME[tk] = tag
    return tk, E.store_suggestion({"legs": [{"ticker": tk, "event": ev, "pick": tag, "p": .3, "fair": .4}], "fair": 25.0},
                                  {"pays": 20.0, "stake": 6.0}, pct)


def combo(a, b, pct):
    legs = []
    for tag in (a, b):
        ev = f"KXNBAGAME-{D}{tag}"
        E.KICKOFF[ev] = iso(7200)
        legs.append({"ticker": f"{ev}-{tag[:3]}", "event": ev, "pick": tag, "p": .5, "fair": .6})
    return [l["ticker"] for l in legs], E.store_suggestion({"legs": legs, "fair": 30.0}, {"pays": 40.0, "stake": 5.0}, pct)


def t_push_gate():
    E.save_json(E.MAIN_SAVED, {"smart_buy_gate": True})
    E._exit_shadow_table()
    E.SB_GATE.update(dial=None, dial_at=0)
    legs, sid = combo("PPPAAA", "PPPBBB", 0.97)          # under fair: the page shows it only once smart sell likely profits
    ok("push: an under-fair combo idea the shadow hasn't cleared gets no push (the page hides it)", E.idea_push_ok(sid) is False)
    E.store_x("insert into exit_shadow(ts, cand, source, tickers, ev, new) values(?,?,?,?,?,?)",
              (time.time(), f"idea:idea:{sid}", "idea", json.dumps(legs), 0.5, 1))
    ok("push: ...and gets one once the shadow found a profitable exit (the page shows it)", E.idea_push_ok(sid) is True)
    ok("push: no stored idea, no push (fails closed)", E.idea_push_ok(None) is False and E.idea_push_ok("nope") is False)
    t, sid2 = single("QQQAAA")
    E.save_json(E.SB_DIAL_FILE, {"nba": {"n": 40, "level": 4, "own": True}})   # bar +$0.10 on $5
    E.SB_GATE.update(dial=None, dial_at=0)
    E.store_x("insert into exit_shadow(ts, cand, source, tickers, ev, new) values(?,?,?,?,?,?)",
              (time.time(), f"idea:idea:{sid2}", "idea", json.dumps([t]), -0.5, 0))
    ok("push: a pregame single the dial skips (expects to lose) gets no push", E.idea_push_ok(sid2) is False)
    ok("push: ...and the page hides the same idea", not any(r["picks"] == "QQQAAA" for r in E.live_ideas()))
    E.save_json(E.MAIN_SAVED, {"smart_buy_gate": False})
    ok("push: with Smart Buy off a pregame idea is pushed as before (the gate is off)", E.idea_push_ok(sid2) is True)
    E.save_json(E.SB_DIAL_FILE, {})
    E.SB_GATE.update(dial=None, dial_at=0)


def t_single_pass_push():
    """The single-idea path asks the same gate before it pushes."""
    E.save_json(E.MAIN_SAVED, {"smart_buy_gate": True})
    E.save_json(E.SB_DIAL_FILE, {"nba": {"n": 40, "level": 4, "own": True}})
    E.SB_GATE.update(dial=None, dial_at=0)
    ev = f"KXNBAGAME-{D}ZZZYYY"
    tk = ev + "-ZZZ"
    E.KICKOFF[ev] = iso(7200)
    x = {"ticker": tk, "event": ev, "pick": "ZZZ", "p": 0.26, "fair": 0.40, "edge": 0.129, "src": "pinnacle", "opp": "YYY"}
    real_store = E.store_suggestion
    alerts = []
    for k, v in dict(load_book_state=lambda snap: {}, week_games=lambda m: ({ev: [x]}, {}, {}), fetch_markets=lambda: [],
                     attach_fair=lambda g, b: (1, {}), maker_pass=lambda *a, **k: [],
                     single_candidates=lambda games, live_ok: [dict(x)],
                     book_depth=lambda t, max_age=60: {"thin": False, "ask": 0.26, "ask_size": 500},
                     edge_stake=lambda *a: 5.0,
                     _alert=lambda alert, msg, *a: alerts.append(msg)).items():
        setattr(E, k, v)
    E.CFG.update(include_live=True, killer_mode="off")
    E.started = lambda l: False
    E.screen_live = lambda games, bf: ([], [])
    E._exit_shadow_table()

    def store(c, r, pct):
        sid = real_store(c, r, pct)
        E.store_x("insert into exit_shadow(ts, cand, source, tickers, ev, new) values(?,?,?,?,?,?)",
                  (time.time(), f"idea:idea:{sid}", "idea", json.dumps([tk]), -0.5, 0))   # the dial's bar is not met
        return sid
    E.store_suggestion = store
    E.single_pass(None, alert="topic", log=lambda *a: None)
    ok("single push: an idea the Smart Buy gate skips sends no push (the card is still stored)",
       alerts == [] and len(E.store_rows("select id from suggestions where legs=?", (json.dumps([tk]),))) == 1)
    E.store_suggestion = real_store
    E.store_x("delete from suggestions where legs=?", (json.dumps([tk]),))
    E.save_json(E.SB_DIAL_FILE, {})
    E.SB_GATE.update(dial=None, dial_at=0)
    E.single_pass(None, alert="topic", log=lambda *a: None)
    ok("single push: control, with nothing to skip it the push still goes out", len(alerts) == 1)


def t_unsure():
    E.save_json(E.SB_DIAL_FILE, {})
    E.SB_GATE.update(dial=None, dial_at=0)
    E.save_json(E.IDEA_DISMISS, {})
    E.MINE.pop("view", None); E.MINE.pop("view_at", None)
    shown = lambda tag, at=None: tag in [r["picks"] for r in E.live_ideas(now=at)]
    old = time.time() - E.IDEA_UNSURE_SECS - 60               # an unclear answer, longer ago than the order can be live
    tA, _ = single("RRRAAA")
    E.idea_mark_bought([tA], now=old, unsure=True)
    ok("unsure: no view of your positions, so it stays hidden (fail closed)", not shown("RRRAAA"))
    E.MINE["view"] = {"singles": [], "singles_ok": True, "combos": []}; E.MINE["view_at"] = old - 5
    ok("unsure: a read of your positions built before the unclear order can't clear it (could be stale)", not shown("RRRAAA"))
    E.MINE["view_at"] = time.time() - E.IDEA_VIEW_FRESH_SECS - 30
    ok("unsure: ...nor can an old read", not shown("RRRAAA"))
    E.MINE["view_at"] = time.time()
    ok("unsure: past the window and a fresh read shows nothing held, the idea is back", shown("RRRAAA"))
    E.MINE["view"] = {"singles": [{"t": tA}], "singles_ok": True, "combos": []}
    ok("unsure: ...but not if you hold it now (it did fill)", not shown("RRRAAA"))
    E.MINE["view"] = {"error": "boom"}
    ok("unsure: ...nor when the account read failed", not shown("RRRAAA"))
    E.MINE["view"] = {"singles": [], "singles_ok": False, "combos": []}; E.MINE["view_at"] = time.time()
    ok("unsure: ...nor when the singles read failed (empty list is not 'holds nothing')", not shown("RRRAAA"))
    E.MINE["view"] = {"singles": [], "combos": []}; E.MINE["view_at"] = time.time()
    ok("unsure: ...nor when the view has no singles_ok flag (fail closed)", not shown("RRRAAA"))
    _os = E.open_singles
    def _boom(*a, **k): raise RuntimeError("singles read down")
    E.open_singles = _boom
    try:
        v = E.live_view([], [], None, 0.0, 0.0)
    except Exception as err:
        v = None; print("live_view raised", err)
    finally:
        E.open_singles = _os
    ok("unsure: live_view flags a raising singles read", bool(v) and v.get("singles_ok") is False)
    E.MINE["view"] = {"singles": [], "singles_ok": True, "combos": []}; E.MINE["view_at"] = time.time()
    E.MINE["view"] = {"singles": [], "singles_ok": True, "combos": []}; E.MINE["view_at"] = time.time()
    tB, _ = single("SSSAAA")
    E.idea_mark_bought([tB], unsure=True)
    ok("unsure: still inside the window it stays hidden", not shown("SSSAAA"))
    tC, _ = single("TTTAAA")
    E.idea_mark_bought([tC], now=old)                          # a definite buy
    ok("unsure: a definite buy stays hidden for days as before", not shown("TTTAAA"))
    E.idea_mark_bought([tC], now=old, unsure=True)
    ok("unsure: ...and an unclear mark never softens a definite one", not shown("TTTAAA"))
    tD, _ = single("UUUAAA")
    E.idea_mark_bought([tD], now=old, unsure=True)
    E.idea_mark_bought([tD], now=old)                          # then the Mac saw it fill
    ok("unsure: a later definite buy overrides the unclear mark", not shown("UUUAAA"))
    tE, sE = single("VVVAAA")
    E.idea_dismiss([E.idea_id([tE])], bought="unsure", now=old)   # the phone's follow-up after a lost reply
    ok("unsure: the phone's 'lost reply' follow-up is the same soft hide", shown("VVVAAA"))
    tF, _ = single("WWWAAA")
    E.idea_dismiss([E.idea_id([tF])], bought=True, now=old)
    ok("unsure: the phone's 'bought' follow-up stays a hard hide", not shown("WWWAAA"))
    E.save_json(E.IDEA_DISMISS, {})


for n, fn in (("push gate", t_push_gate), ("single pass push", t_single_pass_push), ("unsure", t_unsure)):
    safe(n, fn)
