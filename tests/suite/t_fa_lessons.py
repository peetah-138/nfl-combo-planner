# CHECK: group=engine
# Full-auto lessons (#144): a paper or shadow record that has enough data and passes its bar moves ONE small step of a
# full-auto-only number. Checked here: everything is inert while full auto is off (or the Lessons switch is off); an
# unreadable table, a small sample or a malformed saved value takes no step (and a malformed value approves nothing);
# the fixed bounds hold in both directions; a step is re-scored a week later and reverted when it lost money, kept when
# it did not; one step per record per week; the daily cap / bankroll / streak and loss limits are never changed; and the
# manual panel, the live cut-off and every non-auto path are exactly as before. Kalshi is fake, nothing is ever sent.
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


# ---- off by default: nothing is read, written or filtered
reset(on=False)
seed_bar()
ok("full auto off: the tick does nothing and writes nothing", tick(NOW) is False and "lessons" not in E.fa_state() and not os.path.exists(E._fa_path()))
ok("full auto off: lessons are not in effect", not E.fal_on(E.fa_state()))
E._fa_update(lambda s: s.update(lessons={"vals": {"bar:nba": 2.0}}))
E._fa_update(lambda s: s.update(on=False))
cs = [{"id": "a", "kind": "single", "stake": 5, "legs": [{"ticker": "KXNBAGAME-G1-T1", "event": "KXNBAGAME-G1"}]}]
ok("full auto off: nothing is filtered even with saved values", E.full_auto_pass(now=NOW) is None)

# ---- on with lessons: one small step from the league shadow, in plain English
reset()
seed_bar()
ok("a clear lesson takes one step", tick(NOW) is True and vals() == {"bar:nba": 0.5})
line = (lessons().get("log") or [{}])[-1].get("text", "")
ok("the step is logged in plain English with before, after and the evidence", line.startswith("Raised the NBA combo bar a little: on ")
   and "past bets this would have made $" in line and line.endswith("more after fees.") and "->" not in line
   and lessons()["log"][-1]["ev"]["lb"] > 0)
ok("the view shows it", E.full_auto_view()["lessons"]["log"][0] == line and E.full_auto_view()["lessons"]["learned"][0]["text"] == "+0.5 points")
ok("one step a week per record: nothing more a day later", tick(NOW + DAY) is True and vals() == {"bar:nba": 0.5})
before = {k: E.fa_state()[k] for k in E.FA_LIMITS}
ok("the daily cap, bankroll, streak and loss limits are untouched", all(E.fa_state()[k] == before[k] == E.FA[k] for k in E.FA_LIMITS))
ok("the other records took no step (no data)", set(vals()) == {"bar:nba"})

# ---- revert: the following week's results are worse
E.store_x("delete from league_shadow_q where ts > ?", (NOW,))
at = lessons()["last"]["bar"]["at"]
for i in range(6):                                      # bets in the band the step stopped, which would have WON
    E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (5000 + i, at + 3600 * (i + 1), "nba", "nba", 2, 0.951, 5.0, 5.5, 95.0, 95.0, 1, 1, "won", 3.0))
tick(NOW + 8 * DAY)
ok("a step that lost money the week after is reverted", vals() == {} and lessons()["last"]["bar"].get("reverted") is True)
ok("the revert is logged", lessons()["log"][-1]["text"].startswith("Put the NBA combo bar back where it was: the ") and "lost $" in lessons()["log"][-1]["text"])
ok("after a revert only newer bets count: no step the next day", tick(NOW + 9 * DAY) is True and vals() == {})

# ---- kept: the step held up
reset()
seed_bar()
tick(NOW)
at = lessons()["last"]["bar"]["at"]
for i in range(6):
    E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (6000 + i, at + 3600 * (i + 1), "nba", "nba", 2, 0.951, 5.0, 5.5, 95.0, 95.0, 1, 1, "lost", -4.0))
tick(NOW + 8 * DAY)
ok("a step that held up is kept", vals() == {"bar:nba": 0.5} and lessons()["last"]["bar"]["judged"] is True
   and lessons()["log"][-1]["text"].startswith("Kept the NBA combo bar change"))

# ---- fail closed
reset()
seed_bar(n=20)
ok("too small a sample takes no step", tick(NOW) is True and vals() == {} and lessons()["status"]["bar"]["pass"] is False)
reset()
seed_bar()
E.store_x("drop table league_shadow_q", ()); E.store_x("create table league_shadow_q(qid integer primary key, junk text)", ())
tick(NOW)
ok("an unreadable table takes no step and says so", vals() == {} and "couldn't read" in lessons()["status"]["bar"]["note"])
reset()
seed_bar()
real = E.store_rows_strict
E.store_rows_strict = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
tick(NOW)
E.store_rows_strict = real
ok("any error takes no step", vals() == {})
reset()
seed_bar()
E.STORE_DB = E.STORE.get("db"); E.STORE["db"] = None
tick(NOW)
E.STORE["db"] = E.STORE_DB
ok("no database takes no step", vals() == {})
for bad in ({"bar:nba": "x"}, {"bar:nba": 9.0}, {"bar:nba": True}, {"bar:nba": float("nan")}, {"sbev:nba": 1.5}, {"nope:x": 1}, {"game_share": 0.9}):
    reset()
    E._fa_update(lambda s: s.update(lessons={"vals": bad}))
    ok(f"a malformed learned value is a blocker: {bad}", E.fa_state()["lessons"]["vals"].keys() == bad.keys() and E._fal_vals(E.fa_state())[0] is None
       and any("learned numbers" in b for b in E.full_auto_view()["blockers"]))
reset()
E._fa_update(lambda s: s.update(lessons=["bad"]))
ok("a lessons entry that isn't a dict is a blocker too", E._fal_vals(E.fa_state())[0] is None)

# ---- the pass: skip-only, identity at the start values, fail closed
def fresh(n=4):
    E._panel_table(); E.store_x("delete from panel", ())
    cs = []
    for i in range(n):
        ev = f"KXNBAGAME-G{i}"; E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW + 9000))
        l = {"ticker": f"{ev}-T{i}", "event": ev, "pick": f"T{i}", "p": .50, "fair": .60 + i / 100}
        cs.append(E._cand("single", "nba", [l], l["fair"], (l["fair"] - .5 - E.single_fee(.5)) / (.5 + E.single_fee(.5)), "w", price=.5))
    E.PANEL_POOL = {"nba": (time.time(), cs)}
    E.panel_pass()
    return E.panel_get("real")


reset()
p = fresh()
ok("league key of the test bets is nba", E.bet_key([l["ticker"] for l in p["items"][0]["legs"]]) == "nba")
kept, held = E.fal_filter(p["items"], E.fa_state(), NOW)
ok("start values: the filter is the identity", kept == p["items"] and held == [])
E._fa_update(lambda s: s.update(lessons={"vals": {"sbev:nba": 2}}))
E._sb_sim = lambda c, now: {"ev": -1.0}
kept, held = E.fal_filter(p["items"], E.fa_state(), NOW)
ok("a learned Smart Buy bar leaves out bets that fall under it", kept == [] and len(held) == len(p["items"]))
E._sb_sim = lambda c, now: {"ev": 0.5}
kept, held = E.fal_filter(p["items"], E.fa_state(), NOW)
ok("...and keeps bets that clear it, same order and stakes", kept == p["items"])
E._sb_sim = lambda c, now: None
kept, held = E.fal_filter(p["items"], E.fa_state(), NOW)
ok("a bet that can't be simulated is left out (fail closed)", kept == [])
E._sb_sim = lambda c, now: {"ev": -1.0}
E.fa_set(True, limits={"cap": 100, "max_open": 30})
res = E.full_auto_pass(now=NOW)
ok("full auto approves nothing the learned bar leaves out", res is None and E.panel_get("real")["status"] == "draft")
E._sb_sim = lambda c, now: {"ev": 0.5}
res = E.full_auto_pass(now=NOW)
ok("...and approves them when they clear it, through panel_approve", res and res["ok"] and E.panel_get("real")["status"] == "approved")
E.panel_exec()
ok("only approved bets were bought", len(BOUGHT) == len(res["ids"]) and BOUGHT)

reset()
p = fresh()
E._fa_update(lambda s: s.update(lessons={"vals": {"game_share": 0.10}}))
bank = E.fa_state()["bank"]
l0 = p["items"][0]["legs"][0]
k0 = E.overlap_key(l0.get("event") or "", l0.get("ticker") or "")
E.killer_exposure = lambda now=None: {k0: {"n": 1, "risk": 0.10 * bank - 0.01}}
kept, held = E.fal_filter(p["items"], E.fa_state(), NOW)
ok("a learned per-game limit leaves out the bet that would push a game over it, keeps the rest",
   [h["id"] for h in held] == [p["items"][0]["id"]] and len(kept) == len(p["items"]) - 1)
E.killer_exposure = lambda now=None: (_ for _ in ()).throw(RuntimeError("unreadable"))
kept, held = E.fal_filter(p["items"], E.fa_state(), NOW)
ok("an unreadable exposure read leaves everything out (fail closed)", kept == [])

# ---- combo bar: combos only, skip-only; the live cut-off itself is untouched
reset()
E._fa_update(lambda s: s.update(lessons={"vals": {"bar:nba": 0.5}}))
legs = [{"ticker": "KXNBAGAME-G1-A", "event": "KXNBAGAME-G1"}, {"ticker": "KXNBAGAME-G2-B", "event": "KXNBAGAME-G2"}]
cut = E.combo_cutoff("nba", 2, legs)
mkc = lambda pct: {"id": f"c{pct}", "kind": "combo", "code": "nba", "pct": pct, "legs": legs, "stake": 5}
kept, held = E.fal_filter([mkc(cut + 0.001), mkc(cut + 0.01)], E.fa_state(), NOW)
ok("a learned combo bar needs the cut-off plus its extra points", [c["id"] for c in kept] == [f"c{cut + 0.01}"] and len(held) == 1)
ok("the live cut-off and the panel's own bar are unchanged", E.combo_cutoff("nba", 2, legs) == cut)
E._fa_update(lambda s: s.update(fa_lessons=False))
kept, held = E.fal_filter([mkc(cut + 0.001)], E.fa_state(), NOW)
ok("the master switch off: lessons are not in effect", not E.fal_on(E.fa_state()))

# ---- manual panel and non-auto paths unchanged
reset(on=False)
E._fa_update(lambda s: s.update(lessons={"vals": {"sbev:nba": 4, "game_share": 0.10, "bar:nba": 5.0}}))
E._sb_sim = lambda c, now: {"ev": -9.0}
p = fresh()
okm, msgm = E.panel_approve([c["id"] for c in p["items"]], "all", at=p.get("at"))
ok("the manual panel approves every bet as before, whatever is learned", okm and sum(1 for c in E.panel_get("real")["items"] if c["state"] == "scheduled") == len(p["items"]))
ok("manual approvals never touch the lessons file", E.fa_state().get("lessons", {}).get("vals") == {"sbev:nba": 4, "game_share": 0.10, "bar:nba": 5.0})

# ---- sbev and game steps, and the weekly rule across records
reset()
seed_sb()
ok("a Smart Buy paper book lesson steps the full-auto bar one level", tick(NOW) and vals() == {"sbev:nba": 1}
   and lessons()["log"][-1]["text"].startswith("Raised the NBA Smart Buy bar one level: on "))
reset()
seed_expo()
ok("an exposure lesson steps the per-game share one notch", tick(NOW) and vals() == {"game_share": 0.275}
   and lessons()["log"][-1]["text"].startswith("Lowered the per-game limit to 27.5% of the bankroll: on "))
reset()
seed_bar(); seed_sb(); seed_expo()
tick(NOW)
ok("each record may take one step in a week; (step 7) tightening is never held by the two-a-week cap", set(vals()) == {"bar:nba", "sbev:nba", "game_share"} and len(lessons()["log"]) == 3)
tick(NOW + 2 * DAY)
ok("a second look the same week adds nothing", len(lessons()["log"]) == 3)
reset()
seed_bar(); seed_sb(n=20)
tick(NOW)
ok("a record under its own minimum sample takes no step", set(vals()) == {"bar:nba"})

# ---- bounds
ok("bar: no tighter step past +5", [d for d, _ in E._fal_moves("bar", 5.0)] == ["looser"] and E._fal_moves("bar", 5.0)[0][1] == 4.5)
ok("bar: at the start there is no looser step", E._fal_moves("bar", 0.0) == [("tighter", 0.5)])
ok("Smart Buy bar: top level can't go tighter, level 1 loosens to none", [d for d, _ in E._fal_moves("sbev", 4)] == ["looser"] and E._fal_moves("sbev", 1)[-1] == ("looser", 0))
ok("game share: starts at 30%, tightens to 10% and no further, never looser than 30%",
   E._fal_moves("game", 0.30) == [("tighter", 0.275)] and [d for d, _ in E._fal_moves("game", 0.10)] == ["looser"] and E._fal_moves("game", 0.10)[0][1] == 0.125)
ok("a looser step never passes the start value", E._fal_moves("bar", 0.3) == [("tighter", 0.8), ("looser", 0.0)])

# ---- the switch
reset(on=False)
okS, _ = E.fa_lessons_set(False)
ok("the Lessons switch is its own tap and defaults on", okS and E.fa_state()["fa_lessons"] is False and E.full_auto_view()["lessons"]["switch"] is False)
E.fa_lessons_set(True)
ok("...and turns back on", E.full_auto_view()["lessons"]["switch"] is True and E.full_auto_view()["lessons"]["active"] is False)
ok("the card lists what is not wired yet, with a reason", all(x["why"] for x in E.full_auto_view()["lessons"]["not_wired"]) and len(E.full_auto_view()["lessons"]["not_wired"]) >= 8)

# ---- review tightening: NaN, thin sample, fa_set, a real off pass, the lock
def stepped():
    reset(); seed_bar(); tick(NOW); return lessons()["last"]["bar"]["at"]


at = stepped()
E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (7000, at + 3600, "nba", "nba", 2, 0.951, 5.0, 5.5, 95.0, 95.0, 1, 1, "won", 1.0))
_real_load = E._fal_load
def nan_load(rec, now):
    by, passes = _real_load(rec, now)
    for rows in by.values():
        for r in rows:
            if r["k"] > at:
                r["d"] = float("nan")
    return by, passes
E._fal_load = nan_load
tick(NOW + 8 * DAY)
E._fal_load = _real_load
ok("a NaN result is a revert, never kept", vals() == {} and lessons()["last"]["bar"].get("reverted") is True
   and "could not be read" in lessons()["log"][-1]["text"])
E.store_x("insert into league_shadow_q values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (7001, NOW, "nba", "nba", 2, 0.951, 5.0, 5.5, 95.0, 95.0, 1, 1, "won", float("nan")))
ok("a NaN stored in the database takes no step (reads as empty)", E.store_rows("select count(*) n from league_shadow_q where pnl is null")[0]["n"] >= 1)

at = stepped()
tick(NOW + 15 * DAY)
ok("too few bets after two weeks: the step is reverted, not silently kept",
   vals() == {} and lessons()["last"]["bar"].get("reverted") is True and "too few bets" in lessons()["log"][-1]["text"])

reset()
E._fa_update(lambda s: s.update(lessons={"vals": {"bar:nba": 1.0}, "log": [{"text": "x"}]}))
E.fa_set(True, limits={"cap": 12})
E.fa_set(False)
ok("fa_set keeps the learned values and log", E.fa_state()["lessons"]["vals"] == {"bar:nba": 1.0} and E.fa_state()["lessons"]["log"] == [{"text": "x"}])

reset(on=False)
p = fresh()
E._fa_update(lambda s: s.update(lessons={"vals": {"sbev:nba": 4}}))
E._sb_sim = lambda c, now: {"ev": -9.0}
real_tick, real_filter = E.fal_tick, E.fal_filter
calls = []
E.fal_filter = lambda *a, **k: calls.append(1) or ([], [])
E.fal_tick = lambda *a, **k: calls.append(2) or True
okp = E.full_auto_pass(now=NOW)
ok("full auto off: the real pass returns None, touches neither the tick nor the filter, approves nothing",
   okp is None and not calls and E.panel_get("real")["status"] == "draft" and not BOUGHT)
E.fal_tick, E.fal_filter = real_tick, real_filter

reset()
seed_bar()
held = []
real_load = E._fal_load
def slow_load(rec, now):
    got = E._FA_LOCK.acquire(blocking=False)
    held.append(got)
    if got:
        E._FA_LOCK.release()
    return real_load(rec, now)
E._fal_load = slow_load
E.fa_set(True, limits={"cap": 100, "max_open": 30})
E.full_auto_pass(now=NOW)
E._fal_load = real_load
ok("the weekly look reads tables without holding the full-auto lock", held and all(held))
