# CHECK: group=engine
# Push gate: a Buy-idea push goes out only if the Live page would list that very idea now (same live_ideas filter), its
# game is 15+ minutes away, and the state to decide is there (fails closed); line_pass pushes a given idea once.
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


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)


def safe(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def single(tag, secs, pct=1.10):
    ev = f"KXNBAGAME-{D}{tag}"
    tk = f"{ev}-{tag[:3]}"
    E.KICKOFF[ev] = iso(secs)
    E.PICK_NAME[tk] = tag
    return tk, E.store_suggestion({"legs": [{"ticker": tk, "event": ev, "pick": tag, "p": .3, "fair": .4}], "fair": 25.0},
                                  {"pays": 20.0, "stake": 6.0}, pct)


def t_gate():
    E.save_json(E.MAIN_SAVED, {"smart_buy_gate": False})
    E.save_json(E.IDEA_DISMISS, {})
    E.MINE["view"] = {"singles": [], "singles_ok": True, "combos": []}; E.MINE["view_at"] = time.time()
    tk, sid = single("AAABBB", 7200)
    ok("gate: a visible idea 2h out is pushed", E.idea_push_ok(sid) is True)
    tk2, sid2 = single("CCCDDD", 600)
    ok("gate: a game 10 minutes away is not pushed (under the 15 minute lead)", E.idea_push_ok(sid2) is False)
    ok("gate: ...though the page's own 5 minute cut would still list it", any(r["id"] == sid2 for r in E.live_ideas()))
    tk3, sid3 = single("EEEFFF", 7200)
    E.save_json(E.IDEA_DISMISS, {"day": time.strftime("%Y-%m-%d"), "items": {E.idea_key([tk3]): {"at": time.time(), "edge": 9, "price_c": 1}}, "bought": {}, "unsure": {}})
    ok("gate: an idea the page filters out (dismissed) is not pushed", E.idea_push_ok(sid3) is False)
    E.save_json(E.IDEA_DISMISS, {})
    ok("gate: no id / unknown id is not pushed (fails closed)", E.idea_push_ok(None) is False and E.idea_push_ok("nope") is False)
    ok("gate: an older quote the page no longer lists is not pushed", E.idea_push_ok(sid) is True and
       E.idea_push_ok(E.store_suggestion({"legs": [{"ticker": tk, "event": f"KXNBAGAME-{D}AAABBB", "pick": "AAABBB", "p": .3, "fair": .4}],
                                          "fair": 25.0}, {"pays": 20.0, "stake": 6.0}, 1.10)) is True and E.idea_push_ok(sid) is False)
    E.store_x("update suggestions set kick=null where id=?", (sid2,))
    ok("gate: no kick time on file is not pushed (fails closed)", E.idea_push_ok(sid2) is False)


def t_shadow_missing():
    E.save_json(E.MAIN_SAVED, {"smart_buy_gate": True})
    E.save_json(E.SB_DIAL_FILE, {"nba": {"n": 40, "level": 1, "own": True}})   # dial active
    E.SB_GATE.update(dial=None, dial_at=0)
    E._exit_shadow_table()
    tk, sid = single("GGGHHH", 7200)
    ok("shadow: the page keeps an unsimulated idea...", any(r["id"] == sid for r in E.live_ideas()))
    ok("shadow: ...but no exit_shadow row yet means no push (fails closed)", E.idea_push_ok(sid) is False)
    E.store_x("insert into exit_shadow(ts, cand, source, tickers, ev, new) values(?,?,?,?,?,?)",
              (time.time(), f"idea:idea:{sid}", "idea", json.dumps([tk]), 0.5, 1))
    ok("shadow: ...and a pass once the verdict is written", E.idea_push_ok(sid) is True)
    E.save_json(E.SB_DIAL_FILE, {})
    E.SB_GATE.update(dial=None, dial_at=0)


def t_line_pass():
    E.save_json(E.MAIN_SAVED, {"smart_buy_gate": False})
    E.save_json(E.IDEA_DISMISS, {})
    alerts = []
    far, soon = iso(7200), iso(600)
    state = {"start": far}
    ev = f"KXNBASPREAD-{D}LLLMMM"
    tk = ev + "-LLL3"
    E.KICKOFF[ev] = far
    E.PICK_NAME[tk] = "LLL -3.5"

    def cands(code):
        return [{"ticker": tk, "event": ev, "pick": "LLL -3.5", "p": 0.40, "fair": 0.50, "edge": 0.09, "kind": "spread",
                 "book_line": -3.5, "start": state["start"]}]
    for k, v in dict(line_candidates=cands, book_depth=lambda t, max_age=60: {"thin": False, "ask": 0.40, "ask_size": 500},
                     edge_stake=lambda *a: 5.0, _alert=lambda alert, msg, *a: alerts.append(msg)).items():
        setattr(E, k, v)
    E.line_pass("nba", alert="topic", log=lambda *a: None)
    ok("line_pass: a visible idea 2h out is pushed once", len(alerts) == 1)
    E.store_x("update suggestions set ts=ts-7300")                  # 2h later, same price: stored again, no second push
    E.line_pass("nba", alert="topic", log=lambda *a: None)
    ok("line_pass: ...and not pushed again 2h later at the same price", len(alerts) == 1)
    E.store_x("delete from suggestions")
    state["start"] = soon
    E.KICKOFF[ev] = soon
    E.line_pass("nba", alert="topic", log=lambda *a: None)
    ok("line_pass: a game 10 minutes away gets no push (the card is still stored)",
       len(alerts) == 1 and len(E.store_rows("select id from suggestions")) == 1)
    state["start"] = far
    E.KICKOFF[ev] = far
    E.store_x("delete from suggestions")
    E.save_json(E.IDEA_DISMISS, {"day": time.strftime("%Y-%m-%d"), "items": {E.idea_key([tk]): {"at": time.time(), "edge": 9, "price_c": 1}}, "bought": {}, "unsure": {}})
    E.line_pass("nba", alert="topic", log=lambda *a: None)
    ok("line_pass: an idea the page hides gets no push", len(alerts) == 1)
    E.save_json(E.IDEA_DISMISS, {})


def t_held_push():
    sent = []
    E._alert = lambda alert, msg, *a: sent.append(msg)
    E.PUSH_WAIT.clear()
    E.save_json(E.MAIN_SAVED, {"smart_buy_gate": True})
    E.save_json(E.IDEA_DISMISS, {})
    E.save_json(E.SB_DIAL_FILE, {"nba": {"n": 40, "level": 1, "own": True}})
    E.SB_GATE.update(dial=None, dial_at=0)
    E._exit_shadow_table()
    E.store_x("delete from exit_shadow")

    def verdict(tk, sid):
        E.store_x("insert into exit_shadow(ts, cand, source, tickers, ev, new) values(?,?,?,?,?,?)",
                  (time.time(), f"idea:idea:{sid}", "idea", json.dumps([tk]), 0.5, 1))
    tk, sid = single("HHHIII", 7200)
    ok("held: stored before its verdict, not pushed yet", E.push_idea("topic", sid, "m1", "value", "/") is False and not sent)
    ok("held: ...flush before the verdict sends nothing and keeps it", E.flush_idea_pushes() == 0 and sid in E.PUSH_WAIT)
    verdict(tk, sid)
    ok("held: pushed once after the verdict", E.flush_idea_pushes() == 1 and sent == ["m1"] and sid not in E.PUSH_WAIT)
    ok("held: never pushed twice", E.flush_idea_pushes() == 0 and len(sent) == 1)
    tk2, sid2 = single("JJJKKK", 7200)
    E.push_idea("topic", sid2, "m2", "value", "/")
    E.save_json(E.IDEA_DISMISS, {"day": time.strftime("%Y-%m-%d"), "items": {E.idea_key([tk2]): {"at": time.time(), "edge": 9, "price_c": 1}}, "bought": {}, "unsure": {}})
    verdict(tk2, sid2)
    ok("held: dropped, not pushed, if the page hid it meanwhile", E.flush_idea_pushes() == 0 and "m2" not in sent and sid2 not in E.PUSH_WAIT)
    E.save_json(E.IDEA_DISMISS, {})
    tk3, sid3 = single("LLLNNN", 7200)
    E.push_idea("topic", sid3, "m3", "value", "/")
    E.store_x("update suggestions set kick=? where id=?", (time.time() + 600, sid3))
    verdict(tk3, sid3)
    ok("held: dropped if the game is under 15 minutes away", E.flush_idea_pushes() == 0 and "m3" not in sent and sid3 not in E.PUSH_WAIT)
    tk4, sid4 = single("OOOPPP", 7200)
    E.push_idea("topic", sid4, "m4", "value", "/")
    E.PUSH_WAIT[sid4] = (time.time() - 4000,) + E.PUSH_WAIT[sid4][1:]
    verdict(tk4, sid4)
    ok("held: dropped when it waited too long", E.flush_idea_pushes() == 0 and "m4" not in sent and sid4 not in E.PUSH_WAIT)
    tk5, sid5 = single("QQQRRR", 7200)
    E.push_idea("topic", sid5, "m5", "value", "/")
    verdict(tk5, sid5)
    real = E.live_ideas
    E.live_ideas = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    ok("held: an error fails closed (dropped, no push)", E.flush_idea_pushes() == 0 and "m5" not in sent and sid5 not in E.PUSH_WAIT)
    E.live_ideas = real
    E.save_json(E.SB_DIAL_FILE, {})
    E.SB_GATE.update(dial=None, dial_at=0)


def t_panel_collect_flush():
    """End to end: a push held for Smart Buy's verdict goes out when a real panel_collect pass ends (it calls
    flush_idea_pushes last), once, and only while the page still lists the idea and the game is 15+ minutes away."""
    sent = []
    E._alert = lambda alert, msg, *a: sent.append(msg)
    E.PUSH_WAIT.clear()
    E.save_json(E.MAIN_SAVED, {"smart_buy_gate": True})
    E.save_json(E.IDEA_DISMISS, {})
    E.save_json(E.SB_DIAL_FILE, {"nba": {"n": 40, "level": 1, "own": True}})
    E.SB_GATE.update(dial=None, dial_at=0)
    E._exit_shadow_table()
    E.store_x("delete from exit_shadow")
    E.MINE["view"] = {"singles": [], "singles_ok": True, "combos": []}; E.MINE["view_at"] = time.time()
    for k, v in dict(fetch_markets=lambda: [], week_games=lambda markets, loose=False, weeks=1: ({}, {}, None),
                     attach_fair=lambda games, book: (0, {}), load_book_state=lambda snap: {},
                     line_candidates=lambda code, everything=False: [], predict_quote=lambda c: None,
                     thin_legs=lambda legs: False).items():
        setattr(E, k, v)
    E.set_league("nba")
    tk, sid = single("SSSTTT", 7200)
    E.push_idea("topic", sid, "held1", "value", "/")
    E.panel_collect(E.empty_snapshot(), "nba", log=lambda *a: None)
    ok("panel_collect: a held push with no verdict yet is still held after the pass", not sent and sid in E.PUSH_WAIT)
    E.store_x("insert into exit_shadow(ts, cand, source, tickers, ev, new) values(?,?,?,?,?,?)",
              (time.time(), f"idea:idea:{sid}", "idea", json.dumps([tk]), 0.5, 1))
    E.panel_collect(E.empty_snapshot(), "nba", log=lambda *a: None)
    ok("panel_collect: ...and goes out, once, at the end of the next pass", sent == ["held1"] and sid not in E.PUSH_WAIT)
    E.panel_collect(E.empty_snapshot(), "nba", log=lambda *a: None)
    ok("panel_collect: ...and is never sent a second time", sent == ["held1"])
    E.save_json(E.SB_DIAL_FILE, {})
    E.SB_GATE.update(dial=None, dial_at=0)


for n, fn in (("gate", t_gate), ("shadow missing", t_shadow_missing), ("line pass", t_line_pass), ("held push", t_held_push),
              ("panel_collect flush", t_panel_collect_flush)):
    safe(n, fn)
