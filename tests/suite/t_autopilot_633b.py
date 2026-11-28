# CHECK: group=engine
# #633 (money half) + #592: autopilot follow-ups. (1) the legacy stop-loss mover _sl_tune is tighten-only; (2) open-slot evidence
# is sized exactly as the live buy pass sizes bets (autopilot multiple, loss room); (3) share evidence is judged against the
# live (reduced) cap; (4) the soft brake's tightening is not held a week behind a share/bar step. Kalshi is fake.
import os, time, tempfile, json, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.injury_note = lambda code, *teams, hours=48: ([], False)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.can_trade = lambda: True
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
NOW = time.time()
DAY = 86400
NBA = "KXNBAGAME-26NOV20LALBOS-LAL"

# 1. _sl_tune never loosens (#592)
rows = [({"stake": 10.0, "pl": 0.0}, None) for _ in range(E.SL_MIN_N)]
real_replay = E._sl_replay
try:
    E._sl_replay = lambda c, path, prog, drop, *a, **k: -(prog + drop) * 10      # lower settings do better: a loosening would win
    e = {"sl_prog": 0.5, "sl_drop": 0.2}
    why = E._sl_tune(e, rows)
    ok("loosening would win: nothing moves (0.50 / 0.20 stay)", why == "" and e["sl_prog"] == 0.5 and e["sl_drop"] == 0.2)
    E._sl_replay = lambda c, path, prog, drop, *a, **k: (prog + drop) * 10       # higher settings do better: a tightening is allowed
    e = {"sl_prog": 0.5, "sl_drop": 0.2}
    why = E._sl_tune(e, rows)
    ok("tightening wins: one step up on both (0.55 / 0.25)", e["sl_prog"] == 0.55 and e["sl_drop"] == 0.25 and "waits until 55%" in why)
    e = {"sl_prog": 0.95, "sl_drop": 0.5}                                        # outside the bounds: never pulled DOWN to them
    E._sl_tune(e, rows)
    ok("a value above its bound is never pulled down", e["sl_prog"] == 0.95 and e["sl_drop"] == 0.5)
    e = {"sl_prog": 0.9, "sl_drop": 0.2}
    E._sl_tune(e, rows)
    ok("at the top bound one stays, the other still tightens (0.90 / 0.25)", e["sl_prog"] == 0.9 and e["sl_drop"] == 0.25)
finally:
    E._sl_replay = real_replay

# 2. open-slot evidence is sized like the live pass
E._fa_slot_table()
c1 = {"id": "c1", "kind": "combo", "stake": 10.0, "pays": 20.0, "legs": [{"ticker": "T1"}]}


def skip_stakes():
    return [r["stake"] for r in E.store_rows("select stake from fa_slots where kind='skip' order by open_at", ())]


E.store_x("delete from fa_slots", ())
E.fa_slot_skips([c1], 0, {"room": 100.0, "free": 100.0}, 15, {"at": NOW}, NOW, mult=1.2, loss_room=100.0, panel_room=100.0)
ok("autopilot multiple 1.2: the turned-away $10 bet is evidenced at $12", skip_stakes() == [12.0])
E.store_x("delete from fa_slots", ())
E.fa_slot_skips([c1], 0, {"room": 100.0, "free": 100.0}, 15, {"at": NOW}, NOW, mult=0.5, loss_room=100.0, panel_room=100.0)
ok("autopilot multiple 0.5: evidenced at $5", skip_stakes() == [5.0])
E.store_x("delete from fa_slots", ())
E.fa_slot_skips([c1], 0, {"room": 100.0, "free": 100.0}, 15, {"at": NOW}, NOW, mult=1.2, loss_room=3.0, panel_room=100.0)
ok("loss room $3: evidenced at $3, as the live pass would trim it", skip_stakes() == [3.0])
E.store_x("delete from fa_slots", ())
E.fa_slot_skips([c1], 0, {"room": 100.0, "free": 100.0}, 15, {"at": NOW}, NOW, mult=1.0, loss_room=1.99, panel_room=100.0)
ok("loss room under $2: not evidenced (live would leave it out)", skip_stakes() == [])
E.store_x("delete from fa_slots", ())
E.fa_slot_skips([c1], 0, {"room": 100.0, "free": 100.0}, 15, {"at": NOW}, NOW)
ok("old call without the new numbers is unchanged ($10)", skip_stakes() == [10.0])

# 3. share evidence uses the live (reduced) cap
def reset():
    E.store_x("drop table if exists panel", ())
    E.STORE["panel_ok"] = False
    E._panel_table()
    try:
        os.remove(E._fa_path())
    except OSError:
        pass
    E.FAL_RUN["at"] = 0.0
    E._fa_update(lambda s: s.update(on=True, gate="passed", cap=30.0))


def seed_paper(days=3):
    for d in range(1, days + 1):
        t0 = NOW - d * DAY
        items = [{"id": f"p{i}", "kind": "combo", "state": "paper", "legs": [{"ticker": NBA}], "stake": 7.0, "result": "won", "pl": 1.0,
                  "clv": 0.01, "at": t0 + 600 + i * 60} for i in range(4)]
        E.store_x("insert into panel values(?,?,?,?,?)", (E._panel_day(t0), "paper", t0, "done", json.dumps({"at": t0, "items": items})))


reset(); seed_paper()
by, _ = E._share_load(NOW)
ok("normal brake: base is the plain $30 cap and 4 $7 bets fit $30", {r["base"] for r in by["share:nba"]} == {30.0} and len(by["share:nba"]) == 12)
reset(); seed_paper(); E._fa_update(lambda s: s.update(caution={"level": 1, "base_at": NOW, "since": NOW, "why": "x"}))
by, _ = E._share_load(NOW)
ok("cautious level 1: base is $15 and only 2 $7 bets fit a day", {r["base"] for r in by["share:nba"]} == {15.0} and len(by["share:nba"]) == 6)
reset(); seed_paper(); E._fa_update(lambda s: s.update(caution={"level": "x"}))
by, _ = E._share_load(NOW)
ok("unreadable brake level: the smallest cap ($7.50), never the plain one", {r["base"] for r in by["share:nba"]} == {7.5})

# 4. the soft brake's tightening is not held a week behind a bar/share step; a losing-month tightening still is
def seed_real(days=20, pls=(2, -4, -4, 1)):
    for d in range(1, days + 1):
        t0 = NOW - d * DAY
        items = [{"id": f"r{i}", "kind": "combo", "state": "paper", "legs": [{"ticker": NBA}], "stake": 7.0,
                  "result": "won" if p > 0 else "lost", "pl": p, "clv": 0.01, "at": t0 + 600 + i * 60} for i, p in enumerate(pls)]
        E.store_x("insert into panel values(?,?,?,?,?)", (E._panel_day(t0), "paper", t0, "done", json.dumps({"at": t0, "items": items})))


E._fa_rows = lambda now, days=None: []
def vals():
    return dict((E.fa_state().get("lessons") or {}).get("vals") or {})


def tick():
    E.FAL_RUN["at"] = 0.0
    return E.fal_tick(E.fa_state(), NOW, lambda *a: None)


def prep(brake):
    reset(); seed_real()
    E._fa_update(lambda s: s.setdefault("lessons", {}).update(vals={"stake_mult": 1.0}, since={"stake_mult": NOW - 30 * DAY},
                                                              steps={"bar": NOW - 2 * DAY}))
    if brake:
        E._fa_update(lambda s: s.update(history=[{"at": NOW - 2 * DAY, "ev": "brake"}]))


prep(True); tick()
ok("brake week + a bar step 2 days ago: bet size still tightens (1.0 -> 0.95)", vals().get("stake_mult") == 0.95)
plan_acts = None
prep(False); tick()
ok("no brake: a bar step this week still holds bet size (stays 1.0)", vals().get("stake_mult") == 1.0)
