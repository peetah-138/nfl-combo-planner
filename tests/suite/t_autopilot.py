# CHECK: group=engine
# Autopilot registry (#144 step 1): one shared evidence gate, Undo last change (restores the value, holds that setting two
# weeks), a freeze per setting, the Lessons switch kept as the master Autopilot switch (same stored key), a brake hook that
# stops all loosening, no step on any error (logged "no change, not enough evidence"), and every value fenced inside its
# bounds. The step sizes and evidence rules are #602's and are covered by t_fa_lessons.py. Kalshi is fake.
import os, time, tempfile, json, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.injury_note = lambda code, *teams, hours=48: ([], False)
import datetime as _dt; _u = _dt.datetime.now(_dt.timezone.utc); E.PACIFIC = _dt.timezone(_dt.timedelta(hours=round(12 - _u.hour - _u.minute / 60)))
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.REBUILD_FLAG = os.path.join(E.HERE, "panel_rebuild.flag"); E.REBUILD_STATE = os.path.join(E.HERE, "combo_rebuild.json")
E.BUY_FLAG = os.path.join(E.HERE, "panel_buy.flag")
E.fetch_account = lambda **k: ([], 300.0, None)
E.account_events = lambda *a, **k: set()
SENT = []
E.kalshi_send = lambda *a, **k: (SENT.append((a, k)) or {})
E.book_depth = lambda t, max_age=60: {"ask": 0.50, "bid": 0.49}
BOUGHT = []
E.buy_single = lambda t, n, px: (BOUGHT.append((t, n, px)) or (n, None))
E.can_trade = lambda: True
E._held_all = lambda: []
E.panel_record = lambda: {"paper": {"ready": True, "bets": 60, "pl": 40.0, "days": 20, "days_up": 14, "clv": 0.01}, "real": {}}
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
NOW = time.time()
DAY = 86400


def reset(on=True, lessons=True):
    for t in ("league_shadow_q", "sb_paper", "expo_pos"):
        E.store_x(f"drop table if exists {t}", ())
    E.EXPO_STATE["db"] = None
    E._league_shadow_q_table(); E._sb_paper_table(); E._expo_tables()
    try:
        os.remove(E._fa_path())
    except OSError:
        pass
    E.FAL_RUN["at"] = 0.0
    E.TRADING_PAUSED = None
    BOUGHT.clear(); SENT.clear()
    if on:
        E._fa_update(lambda s: s.update(on=True, gate="passed", **({} if lessons else {"fa_lessons": False})))


def tick(at):
    E.FAL_RUN["at"] = 0.0
    return E.fal_tick(E.fa_state(), at, lambda *a: None)


def lessons():
    return E.fa_state().get("lessons") or {}


def vals():
    return lessons().get("vals") or {}


def seed_bar(n=80, t0=NOW - 4 * DAY, win_in_band=False):
    """n quotes in nba: half just above the 95% cut-off (the band a +0.5 step would stop), losing; half far above, winning."""
    for i in range(n):
        band = i % 2 == 0
        E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (1000 + i, t0 + i * 3600, "nba", "nba", 2, 0.951 if band else 0.99, 5.0, 5.5, 95.0, 95.0, 1, 1,
                   "lost" if band else "won", -4.0 if band else 0.5))


def seed_sb(n=70, t0=NOW - 4 * DAY):
    for i in range(n):
        low = i % 2 == 0
        E.store_x("insert into sb_paper values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (f"b{i}", t0 + i * 3600, "2026-11-20", "nba", "nba", "combo", "panel", "cand", "stake", 5.0, 0.5,
                   -0.5 if low else 0.3, 9.0, 3.0, 0.0, -5.0 if low else 1.0, None, NOW, f"g{i}"))


def seed_expo(games=20, t0=NOW - 4 * DAY):
    k = 0
    for g in range(games):                              # three $28.50 bets stack on each game: the third passes 30% but not 27.5%
        for j in range(3):
            net = -28.5 if j == 2 else 5.0
            E.store_x("insert into expo_pos values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (f"p{k}", t0 + k * 3600, "2026-11-20", "nba", "combo", 28.5, 300.0, json.dumps({f"G{g}": ["yes"]}),
                       json.dumps({f"G{g}": 28.5}), 0, "", net, t0 + k * 3600 + 1, 1, 1))
            k += 1




def step_bar():
    reset()
    seed_bar()
    tick(NOW)


# ---- the registry and the shared gate
ok("registry lists the seven lessons settings", list(E.AP_REG) == ["bar", "sbev", "game", "open", "share", "stake", "capuse"])
ok("registry bounds and steps are #602's", E.AP_REG["bar"]["bounds"] == {"lo": 0.0, "hi": 5.0, "step": 0.5}
   and E.AP_REG["game"]["bounds"]["step"] == 0.025 and E.AP_REG["sbev"]["bounds"]["hi"] == 4)
for _r in ("stake", "capuse"):   # step 7 has its own test (t_autopilot_stake)
    E.AP_REG.pop(_r, None)
reset(); seed_bar()
by, passes = E._fal_load("bar", NOW)
okg, ev, lb = E.ap_gate("bar", "bar:nba", by["bar:nba"], passes, 0.0, 0.5, 0)
ok("the shared gate passes a clear lesson and agrees with the old name", okg and lb > 0 and E._fal_judge("bar", "bar:nba", by["bar:nba"], passes, 0.0, 0.5, 0)[0])
ok("the gate refuses a thin sample", not E.ap_gate("bar", "bar:nba", by["bar:nba"][:10], passes, 0.0, 0.5, 0)[0])
ok("the gate refuses a move that loses money", not E.ap_gate("bar", "bar:nba", by["bar:nba"], passes, 0.5, 0.0, 0)[0])

# ---- switch back-compat: the stored key is still fa_lessons, the label is Autopilot
reset()
E._fa_update(lambda s: s.update(fa_lessons=False))
ok("a stored fa_lessons=False still turns Autopilot off", not E.fal_on(E.fa_state()) and E.full_auto_view()["lessons"]["switch"] is False)
okS, msg = E.fa_lessons_set(True)
ok("the switch says Autopilot and keeps the key", okS and msg.startswith("Autopilot is ON") and E.fa_state()["fa_lessons"] is True)
reset()
ok("no stored key = on, as before", E.fal_on(E.fa_state()))

# ---- a step, then Undo
step_bar()
ok("a clear lesson steps", vals() == {"bar:nba": 0.5})
ok("the view offers the undo", "NBA combo bar" in (E.full_auto_view()["lessons"]["undo"] or ""))
okU, msgU = E.ap_undo(NOW + 3600)
ok("undo restores the previous value", okU and vals() == {} and "you undid" in msgU)
ok("undo is logged on the card", "you undid" in E.full_auto_view()["lessons"]["log"][0] and "2 weeks" in msgU)
ok("a second undo does nothing", E.ap_undo(NOW + 3700)[0] is False and vals() == {})
ok("the view no longer offers undo; the setting is held", E.full_auto_view()["lessons"]["undo"] is None and E.full_auto_view()["lessons"]["holds"])
tick(NOW + 8 * DAY)
ok("the undone setting is held: no step a week later", vals() == {})
tick(NOW + 13 * DAY)
ok("still held on day 13", vals() == {})
E.store_x("delete from league_shadow_q", ()); seed_bar(t0=NOW + 2 * DAY)     # fresh bets after the undo
tick(NOW + 16 * DAY)
ok("after two weeks the hold ends and evidence can step it again", vals() == {"bar:nba": 0.5})

# undo is not fooled by a value that moved since
step_bar()
E._fa_update(lambda s: s["lessons"]["vals"].update({"bar:nba": 1.0}))
ok("undo refuses when the value is no longer where autopilot left it", E.ap_undo(NOW + 10)[0] is False and vals() == {"bar:nba": 1.0})
reset()
ok("undo with nothing changed says so", E.ap_undo(NOW)[0] is False)
# undo also covers an automatic revert, and works with Autopilot off
step_bar()
at = lessons()["last"]["bar"]["at"]
for i in range(6):
    E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (7000 + i, at + 3600 * (i + 1), "nba", "nba", 2, 0.951, 5.0, 5.5, 95.0, 95.0, 1, 1, "won", 3.0))
tick(NOW + 8 * DAY)
ok("setup: the step was auto-reverted", vals() == {} and lessons()["change"]["kind"] == "revert")
E._fa_update(lambda s: s.update(fa_lessons=False))
okU, _ = E.ap_undo(NOW + 8 * DAY + 5)
ok("undo of a revert restores the stepped value even with Autopilot off, and holds it", okU and vals() == {"bar:nba": 0.5})

# ---- freeze
reset(); seed_bar()
okF, msgF = E.ap_freeze("bar:nba", True)
ok("freeze one setting", okF and "frozen" in msgF and "bar:nba" in E.full_auto_view()["lessons"]["frozen"])
tick(NOW)
ok("a frozen setting takes no step", vals() == {})
tick(NOW + DAY)
E.ap_freeze("bar:nba", False)
tick(NOW + 2 * DAY)
ok("unfrozen, it can step", vals() == {"bar:nba": 0.5})
reset(); seed_bar()
E.ap_freeze("bar", True)
tick(NOW)
ok("freezing the whole record also holds it", vals() == {})
ok("freeze refuses an unknown key", E.ap_freeze("nonsense", True)[0] is False and E.ap_freeze("bar:", True)[0] is False)
# a frozen setting is not auto-reverted either
step_bar()
at = lessons()["last"]["bar"]["at"]
for i in range(6):
    E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (8000 + i, at + 3600 * (i + 1), "nba", "nba", 2, 0.951, 5.0, 5.5, 95.0, 95.0, 1, 1, "won", 3.0))
E.ap_freeze("bar:nba", True)
tick(NOW + 8 * DAY)
ok("a frozen setting's pending step is still judged and reverted when it lost", vals() == {})

# ---- brake hook: no loosening anywhere while cautious; tightening still allowed
ok("the hook is calm with no brake", E.ap_brake_cautious({}) is False)
ok("the hook is cautious when the brake is tripped", E.ap_brake_cautious({"brake": {"kind": "streak"}}) is True)
step_bar()
at = lessons()["last"]["bar"]["at"]
E.store_x("delete from league_shadow_q where ts > ?", (NOW,))
for i in range(6):
    E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (9000 + i, at + 3600 * (i + 1), "nba", "nba", 2, 0.951, 5.0, 5.5, 95.0, 95.0, 1, 1, "won", 3.0))
E._fa_update(lambda s: s.update(brake={"kind": "streak", "why": "test"}))
tick(NOW + 8 * DAY)
ok("while the brake is cautious even a losing step is not walked back (no loosening)", vals() == {"bar:nba": 0.5})
E._fa_update(lambda s: s.update(brake=None))
tick(NOW + 9 * DAY)
ok("once the brake clears the revert happens", vals() == {})
reset(); seed_bar()
E._fa_update(lambda s: s.update(brake={"kind": "day", "day": "x", "why": "test"}))
tick(NOW)
ok("tightening is still allowed while cautious", vals() == {"bar:nba": 0.5})
# a tightened value that wants to loosen (evidence says the bar is too tight) waits while cautious
reset(); seed_bar()
E._fa_update(lambda s: s.update(lessons={"vals": {"bar:nba": 2.0}}))
E.store_x("delete from league_shadow_q", ())
for i in range(80):                                      # the band the +2 bar blocks wins: looser would pay
    E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (2000 + i, NOW - 4 * DAY + i * 3600, "nba", "nba", 2, 0.968 if i % 2 == 0 else 0.99, 5.0, 5.5, 95.0, 95.0, 1, 1, "won", 4.0 if i % 2 == 0 else 0.5))
E._fa_update(lambda s: s.update(brake={"kind": "streak", "why": "test"}))
tick(NOW)
ok("cautious brake: no loosening step", vals() == {"bar:nba": 2.0})
E._fa_update(lambda s: s.update(brake=None))
tick(NOW + DAY)
ok("brake clear: the same evidence loosens by one step", vals() == {"bar:nba": 1.5})

# ---- errors: no step, logged plainly
reset(); seed_bar()
real = E._fal_load
def boom(rec, now):
    raise RuntimeError("disk")
E.AP_REG["bar"]["load"] = boom
tick(NOW)
ok("an unreadable record takes no step", vals() == {})
ok("and says so on the card", any("no change, not enough evidence" in (e.get("text") or "") for e in lessons().get("log", [])))
n = len(lessons()["log"]); tick(NOW + 3600)
ok("that line is not repeated every look", len(lessons()["log"]) == n)
E.AP_REG["bar"]["load"] = lambda rec, now: E._fal_load(rec, now)
real_plan = E._fal_plan
E._fal_plan = lambda st, now: (_ for _ in ()).throw(RuntimeError("x"))
ok("an error in the whole look is swallowed, no step", tick(NOW + 2 * DAY) is False and vals() == {})
E._fal_plan = real_plan
reset(); seed_bar()
E._fa_update(lambda s: s.update(lessons={"vals": {"bar:nba": "x"}}))
tick(NOW)
ok("a malformed saved value takes no step", E.fa_state()["lessons"]["vals"] == {"bar:nba": "x"})

# ---- clamping
ok("clamp holds a bar inside 0 to 5", E.ap_clamp("bar", 9) == 5.0 and E.ap_clamp("bar", -1) == 0.0)
ok("clamp holds a game share inside 10% to 30%", E.ap_clamp("game", 0.9) == 0.30 and E.ap_clamp("game", 0.01) == 0.10)
ok("clamp refuses junk", E.ap_clamp("bar", float("nan")) is None and E.ap_clamp("bar", "1") is None and E.ap_clamp("sbev", True) is None)
ok("clamp keeps Smart Buy a whole level", E.ap_clamp("sbev", 2.4) == 2 and E.ap_clamp("sbev", 7) == 4)
reset(); seed_bar()
plan = E._fal_plan(E.fa_state(), NOW)
plan["actions"][0]["to"] = 9.0                           # a plan that tries to leap past the fence
E._fa_update(lambda s: E._fal_apply(s, plan, NOW))
ok("a plan outside the bounds is not applied", vals() == {})
ok("limits are never touched", all(E.fa_state()[k] == E.FA[k] for k in E.FA_LIMITS))


# ---- review fixes: soft brake (caution level), hold only blocks loosening, undo never loosens, frozen reverts, bad holds
ok("hook: a soft-brake caution level above 0 is cautious", E.ap_brake_cautious({"caution": {"level": 1}}) is True)
ok("hook: level 0 or no caution is calm", E.ap_brake_cautious({"caution": {"level": 0}}) is False and E.ap_brake_cautious({}) is False)
ok("hook fails closed on unreadable state", E.ap_brake_cautious({"caution": "x"}) is True and E.ap_brake_cautious({"caution": {"level": "hi"}}) is True
   and E.ap_brake_cautious(None) is True and E.ap_brake_cautious({"caution": {"level": float("nan")}}) is True)


def seed_loosen():
    reset(); seed_bar()
    E._fa_update(lambda s: s.update(lessons={"vals": {"bar:nba": 2.0}}))
    E.store_x("delete from league_shadow_q", ())
    for i in range(80):
        E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (2000 + i, NOW - 4 * DAY + i * 3600, "nba", "nba", 2, 0.968 if i % 2 == 0 else 0.99, 5.0, 5.5, 95.0, 95.0, 1, 1, "won", 4.0 if i % 2 == 0 else 0.5))


seed_loosen()
E._fa_update(lambda s: s.update(caution={"level": 1}))
tick(NOW)
ok("soft-brake caution blocks loosening", vals() == {"bar:nba": 2.0})
E._fa_update(lambda s: s.update(caution={"level": 0}))
tick(NOW + DAY)
ok("caution at 0: it loosens", vals() == {"bar:nba": 1.5})

# a hold blocks only loosening
seed_loosen()
E._fa_update(lambda s: s["lessons"].update(holds={"bar:nba": NOW + 5 * DAY}))
tick(NOW)
ok("a hold blocks loosening", vals() == {"bar:nba": 2.0})
tick(NOW + 6 * DAY)
ok("the hold over, it loosens", vals() == {"bar:nba": 1.5})
reset(); seed_bar()
E._fa_update(lambda s: s.update(lessons={"holds": {"bar:nba": NOW + 5 * DAY}}))
tick(NOW)
ok("a hold does not block tightening", vals() == {"bar:nba": 0.5})

# undo never loosens while cautious
step_bar()
E._fa_update(lambda s: s.update(caution={"level": 2}))
okU, msgU = E.ap_undo(NOW + 10)
ok("undo refuses a loosening undo while cautious", okU is False and vals() == {"bar:nba": 0.5} and "brake" in msgU)
E._fa_update(lambda s: s.update(caution={"level": 0}))
ok("undo works once calm", E.ap_undo(NOW + 20)[0] is True and vals() == {})

# undoing a revert never restores a looser value the evidence rejected
seed_loosen()
tick(NOW)
ok("setup: loosened 2.0 -> 1.5", vals() == {"bar:nba": 1.5})
at = lessons()["last"]["bar"]["at"]
for i in range(6):
    E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (9500 + i, at + 3600 * (i + 1), "nba", "nba", 2, 0.968, 5.0, 5.5, 95.0, 95.0, 1, 1, "lost", -4.0))
tick(NOW + 8 * DAY)
ok("setup: the losing looser step reverted to 2.0", vals() == {"bar:nba": 2.0} and lessons()["change"]["kind"] == "revert")
okU, msgU = E.ap_undo(NOW + 8 * DAY + 5)
ok("undo refuses to restore the looser value the evidence rejected", okU is False and vals() == {"bar:nba": 2.0} and "rejected" in msgU)

# a frozen looser step still reverts (tightening)
seed_loosen()
tick(NOW)
at = lessons()["last"]["bar"]["at"]
for i in range(6):
    E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (9600 + i, at + 3600 * (i + 1), "nba", "nba", 2, 0.968, 5.0, 5.5, 95.0, 95.0, 1, 1, "lost", -4.0))
E.ap_freeze("bar", True)
tick(NOW + 8 * DAY)
ok("a frozen losing looser step still reverts", vals() == {"bar:nba": 2.0})

# a malformed hold doesn't break the card
step_bar()
E._fa_update(lambda s: s["lessons"].update(holds={"bar:nba": "soon", "sbev:nba": None}))
v = E.full_auto_view()["lessons"]
ok("a malformed hold is no hold and the card still renders", v.get("err") is None and v["holds"] == [] and v["switch"] is True)
