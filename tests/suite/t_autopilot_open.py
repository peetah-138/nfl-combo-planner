# CHECK: group=engine
# Autopilot's open-bet limit (#145): full auto's max open bets (Pete's number, default 15) moves one bet at a time between
# 8 and 20 through the shared registry: tighten fast, loosen slow, never loosen while the soft brake is cautious, no step on
# unreadable data, Undo/freeze/master switch work, and Pete's own edit replaces what was learned. Kalshi is fake.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.can_trade = lambda: True
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
NOW = time.time()
for _r in ("stake", "capuse"):   # step 7 has its own test (t_autopilot_stake): out of this older test's way
    E.AP_REG.pop(_r, None)
DAY = 86400
PL = {}
E._fa_rows = lambda now, days=None: [(k.split("|")[0], {"id": k.split("|")[1], "result": "x", "pl": v}) for k, v in PL.items()]


def reset():
    E.store_x("drop table if exists fa_slots", ())
    PL.clear()
    try:
        os.remove(E._fa_path())
    except OSError:
        pass
    E.FAL_RUN["at"] = 0.0
    E._fa_update(lambda s: s.update(on=True, gate="passed"))


def tick(at=NOW):
    E.FAL_RUN["at"] = 0.0
    return E.fal_tick(E.fa_state(), at, lambda *a: None)


def stepped(at=NOW):
    tick(at)
    return any(e.get('kind') == 'step' for e in lessons().get('log') or [])


def lessons():
    return E.fa_state().get("lessons") or {}


def limit():
    return E.ap_open_limit(E.fa_state())


def seed_taken(top, bad_at, n=240, t0=NOW - 5 * DAY):
    """n bought bets, opened with 0..top-1 already open; the ones bought as open number `bad_at` (0-based) lose."""
    E._fa_slot_table()
    for i in range(n):
        at = i % top
        k = f"2026-11-2{i % 5}|b{i}"
        E.store_x("insert into fa_slots values(?,?,?,?,?,?,?,?,?,?)", (k, t0 + i * 600, k.split("|")[0], "taken", at, 5.0, None, None, None, None))
        PL[k] = -4.0 if at == bad_at else 1.0


def seed_skips(open_at, n=60, pnl=3.0, t0=NOW - 20 * DAY):
    E._fa_slot_table()
    for i in range(n):
        E.store_x("insert into fa_slots values(?,?,?,?,?,?,?,?,?,?)",
                  (f"d|s{i}", t0 + i * 600, "d", "skip", open_at, 5.0, 9.0, "[]", "won", pnl))


# 1. nothing learned: Pete's number, any value
reset()
ok("start: Pete's number", limit() == 15)
E._fa_update(lambda s: s.update(max_open=25))
ok("Pete's own 25 is never clamped to 20", limit() == 25)
E._fa_update(lambda s: s.update(max_open=15))

# 2. tighten fast: the 15th open bet loses
reset(); seed_taken(15, 14)
ok("tighten: step taken", tick() and E.fa_state()["lessons"]["vals"].get("open_slots") == 14)
ok("tighten: limit is 14", limit() == 14)
ok("tighten: logged in plain words", any("open-bet limit" in e["text"] for e in lessons()["log"]))
ok("tighten: Pete's saved number is untouched", E.fa_state()["max_open"] == 15)
ok("one step a week", not stepped(NOW + DAY) or E.fa_state()["lessons"]["vals"]["open_slots"] == 14)

# 3. not enough evidence: no step
reset(); seed_taken(15, 14, n=10)
ok("thin evidence: no step", not stepped() and "open_slots" not in (lessons().get("vals") or {}))

# 4. loosen slow: sample twice as big and 14 days since the last move (Pete's 15 is the ceiling)
def learned(v, since=NOW - 30 * DAY):
    E._fa_update(lambda s: s.update(lessons={"vals": {"open_slots": v}, "since": {"open_slots": since}}))


reset(); learned(14); seed_skips(14, n=60)
ok("loosen: 14 -> 15, skips at 14 would have won", stepped() and limit() == 15)
reset(); learned(14, NOW - 2 * DAY); seed_skips(14, n=60)
ok("loosen: waits 14 days after the last move", not stepped() and limit() == 14)
reset(); learned(14); seed_skips(14, n=30)
ok("loosen: needs twice the sample", not stepped())
reset(); seed_skips(15, n=60)
ok("ceiling: Pete's 15 is never exceeded by learning", not stepped() and limit() == 15)
reset(); E._fa_update(lambda s: s.update(max_open=18)); learned(20) 
ok("a stale learned 20 above Pete's 18 is held to 18", limit() == 18)
E._fa_update(lambda s: s.update(max_open=15))

# 5. soft brake cautious: nothing loosens, tightening still allowed
reset(); seed_skips(15, n=60)
E._fa_update(lambda s: s.update(caution={"level": 1, "base_at": NOW, "since": NOW, "why": "x"}))
ok("cautious: no loosening", not stepped() and limit() == 15)
reset(); seed_taken(15, 14)
E._fa_update(lambda s: s.update(caution={"level": 1, "base_at": NOW, "since": NOW, "why": "x"}))
ok("cautious: tightening still fine", tick() and limit() == 14)

# 6. bounds
reset(); E._fa_update(lambda s: s.update(lessons={"vals": {"open_slots": 8}})); seed_taken(8, 7)
ok("floor 8: no step below", not stepped() and limit() == 8)
reset(); E._fa_update(lambda s: s.update(max_open=20, lessons={"vals": {"open_slots": 20}})); seed_skips(20, n=80)
ok("ceiling 20: no step above", not stepped() and limit() == 20)
E._fa_update(lambda s: s.update(max_open=15))
E._fa_update(lambda s: s.update(lessons={"vals": {"open_slots": 99}}))
ok("a saved value outside 8-20 is unreadable: falls back to Pete's number and approves nothing", limit() == 15 and E._fal_vals(E.fa_state())[0] is None)

# 7. fail closed on unreadable data
reset(); seed_taken(15, 14)
real = E.store_rows_strict
E.store_rows_strict = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
ok("unreadable data: no step", not stepped() or "open_slots" not in (lessons().get("vals") or {}))
E.store_rows_strict = real

# 8. master switch off, freeze, undo
reset(); seed_taken(15, 14); E._fa_update(lambda s: s.update(fa_lessons=False))
ok("master switch off: Pete's number, no step", not stepped() and limit() == 15)
reset(); seed_taken(15, 14); E.ap_freeze("open_slots", True)
ok("frozen: no step", not stepped() and limit() == 15)
reset(); seed_taken(15, 14); tick()
res = E.ap_undo(NOW + 1)
ok("undo puts it back", limit() == 15 and res)

# 9. Pete's own edit clears the override
reset(); seed_taken(15, 14); tick()
E.fa_set(True, limits={"max_open": 12}, explicit_on=True)
ok("Pete's edit wins", limit() == 12 and "open_slots" not in (lessons().get("vals") or {}))
reset(); seed_taken(15, 14); tick(); since0 = lessons()["since"]["open_slots"]
E.fa_set(True, limits={"max_open": 15, "cap": 25}, explicit_on=True)
ok("saving the cap alone keeps the learned limit and its clock", limit() == 14 and lessons()["since"]["open_slots"] == since0
   and E.fa_state()["cap"] == 25)

# 10. the other limits never move; effective limit only changes the slot count
reset(); E._fa_update(lambda s: s.update(lessons={"vals": {"open_slots": 12}}))
v = E.fa_check(E.fa_state(), now=NOW)
ok("slots follow the learned number", v["max_open"] == 12 and v["slots"] == 12 - v["open"])
ok("cap, bankroll, loss limit are Pete's", v["bank"] == E.fa_state()["bank"])

# 11. skip logging only counts bets that fit everything but a slot
reset()
E._fa_slot_table()
real_c = {"id": "c1", "kind": "combo", "stake": 5.0, "pays": 9.0, "legs": [{"ticker": "T1"}]}
E.fa_slot_skips([real_c], 0, {"room": 30.0, "free": 100.0}, 15, {"at": NOW}, NOW)
E.fa_slot_skips([dict(real_c, id="c2")], 0, {"room": 1.0, "free": 100.0}, 15, {"at": NOW}, NOW)
n = E.store_rows("select count(*) n from fa_slots where kind='skip'", ())[0]["n"]
ok("a skip needs the room and the bankroll", n == 1)

# 12. several skips in one pass: each is replayed as if the ones before it had been bought
reset()
E._fa_slot_table()
cs = [dict(real_c, id=f"m{i}", legs=[{"ticker": f"T{i}"}]) for i in range(6)]
E.fa_slot_skips(cs, 0, {"room": 12.0, "free": 100.0}, 15, {"at": NOW}, NOW)
rows = E.store_rows("select open_at from fa_slots where kind='skip' order by open_at", ())
ok("6 skips with room for 2: only 2 logged, open counts 15 and 16", [r["open_at"] for r in rows] == [15, 16])

# 13. a pass that buys one and turns away the rest: skips are replayed from the room left AFTER the buy
reset()
E._fa_slot_table()
_saved = (E.fa_check, E.panel_get, E._fa_candidates, E.panel_approve, E.fa_slot_taken)
mix = [dict(real_c, id=f"x{i}", legs=[{"ticker": f"X{i}"}]) for i in range(3)]
E.fa_check = lambda *a, **k: {"brake": None, "caution": {"changed": False, "level": 0, "events": []}, "blockers": [],
                              "room": 12.0, "slots": 1, "free": 100.0, "open": 15, "cap": 30.0}
E.panel_get = lambda *a, **k: {"at": NOW, "status": "draft"}
E._fa_candidates = lambda *a, **k: list(mix)
E.panel_approve = lambda *a, **k: (True, "ok")
E.fa_slot_taken = lambda *a, **k: None
try:
    E._full_auto_pass(now=NOW, log=lambda *a: None)
finally:
    E.fa_check, E.panel_get, E._fa_candidates, E.panel_approve, E.fa_slot_taken = _saved
rows = E.store_rows("select open_at from fa_slots where kind='skip' order by open_at", ())
ok("1 bought, room 12 -> 7 left: only 1 of the 2 turned-away bets is logged, open count 16", [r["open_at"] for r in rows] == [16])
