# CHECK: group=engine
# Autopilot's league / bet-type budget shares (#145 step 6): each league (and combo vs single) gets a MAX share of the day's
# spending cap, moved 5 pts a week through the shared registry from the practice panel's net dollars after fees and closing-line
# value. Floor 5% (a league keeps learning: its first bet of the day always passes and its evidence is never filtered), tighten
# fast and loosen slow, no loosening while the soft brake is cautious, the cap never exceeded and never added to, unreadable data
# = no change, never the same week as the combo bars. Kalshi is fake.
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
NBA, NHL = "KXNBAGAME-26NOV20LALBOS-LAL", "KXNHLGAME-26NOV20TORBOS-TOR"


def reset():
    E.store_x("drop table if exists panel", ())
    E.STORE["panel_ok"] = False
    E._panel_table()
    try:
        os.remove(E._fa_path())
    except OSError:
        pass
    E.FAL_RUN["at"] = 0.0
    E._fa_update(lambda s: s.update(on=True, gate="passed"))


def seed(days=20, nba_pls=(4, -7, -7, -7), clv=0.02, stake=7.0, nhl_pl=1.0):
    """Practice panel history. Per day: 1 NHL single ($2) first, then 4 NBA combos (`stake` each, results nba_pls in order). The
    day totals $30 at the default stake: exactly the live daily cap, so the replay and the live guard see the same day."""
    for d in range(1, days + 1):
        t0 = NOW - d * DAY
        items = [{"id": "h0", "kind": "single", "state": "paper", "legs": [{"ticker": NHL}], "stake": 2.0, "result": "won",
                  "pl": nhl_pl, "clv": 0.01, "at": t0}]
        items += [{"id": f"n{i}", "kind": "combo", "state": "paper", "legs": [{"ticker": NBA}], "stake": stake, "result": "won" if p > 0 else "lost",
                   "pl": p, "clv": clv, "at": t0 + 600 + i * 60} for i, p in enumerate(nba_pls)]
        E.store_x("insert into panel values(?,?,?,?,?)", (E._panel_day(t0), "paper", t0, "done", json.dumps({"at": t0, "items": items})))


def lessons():
    return E.fa_state().get("lessons") or {}


def vals():
    return dict(lessons().get("vals") or {})


def tick(at=NOW):
    E.FAL_RUN["at"] = 0.0
    return E.fal_tick(E.fa_state(), at, lambda *a: None)


def stepped(at=NOW):
    tick(at)
    return any(e.get("kind") == "step" for e in lessons().get("log") or [])


def learned(v, since=NOW - 30 * DAY, key="share:nba"):
    E._fa_update(lambda s: s.update(lessons={"vals": {key: v}, "since": {key: since}}))


def cautious(level=1):
    E._fa_update(lambda s: s.update(caution={"level": level, "base_at": NOW, "since": NOW, "why": "x"}))


# 1. registered, named, empty data = no change
reset()
ok("the share record is registered with a 5% floor, 5-pt step, 100% start", "share" in E.AP_REG and E.FAL["share"] == {"lo": 0.05, "hi": 1.0, "step": 0.05}
   and E.FAL_START["share"] == 1.0)
ok("empty data: no step, nothing saved", not stepped() and vals() == {})
ok("the shares are plain 'no learned share': the guard reads nothing", E.FaShareGuard(E.fa_state(), 30.0, "d", NOW).sh == {})

# 2. tighten fast: the NBA bets after its first lose money on paper
reset(); seed()
ok("tighten: the weekly look takes a step", stepped())
v = vals()
ok("tighten: a share below 100%, a 5-pt multiple, at most 15 pts in one week", len(v) == 1 and all(0.85 - 1e-9 <= x < 1.0 and abs(x * 20 - round(x * 20)) < 1e-6 for x in v.values()))
ok("tighten: logged in plain words with the dollars", any("budget share" in e["text"] and "more after fees" in e["text"] for e in lessons()["log"]))
ok("tighten: shows on the card as learned", any("budget share" in x["name"] for x in E.fal_view(E.fa_state())["learned"]))
n_steps = len([e for e in lessons()["log"] if e.get("kind") == "step"]); tick(NOW + DAY)
ok("one step a week", len([e for e in lessons()["log"] if e.get("kind") == "step"]) == n_steps and len(vals()) == 1)
ok("Pete's limits are untouched", E.fa_state()["cap"] == 30.0 and E.fa_state()["bank"] == 300.0 and E.fa_state()["day_loss"] == 20.0)

# 3. thin evidence
reset(); seed(days=5)
ok("thin evidence: no step", not stepped() and vals() == {})

# 4. winners are not tightened
reset(); seed(nba_pls=(4, 4, 4, 4))
ok("a league that keeps winning is not tightened", not stepped() and vals() == {})

# 5. loosen slow, with closing-line value
reset(); seed(nba_pls=(4, 4, 4, 4)); learned(0.65)
ok("loosen: blocked bets would have won and CLV is positive: exactly ONE 5-pt step back up", stepped() and abs(vals().get("share:nba", 1.0) - 0.7) < 1e-9)
reset(); seed(nba_pls=(4, 4, 4, 4)); learned(0.65, since=NOW - 2 * DAY)
ok("loosen waits 14 days after the last move", not stepped() and vals() == {"share:nba": 0.65})
reset(); seed(days=12, nba_pls=(4, 4, 4, 4)); learned(0.65)
ok("loosen needs twice the sample", not stepped() and vals() == {"share:nba": 0.65})
reset(); seed(nba_pls=(4, 4, 4, 4), clv=-0.03); learned(0.65)
ok("loosen refused on negative closing-line value", not stepped() and vals() == {"share:nba": 0.65})
reset(); seed(nba_pls=(4, 4, 4, 4), clv=None); learned(0.65)
ok("loosen refused when closing-line value is unreadable", not stepped() and vals() == {"share:nba": 0.65})

# 6. soft brake cautious: no loosening, tightening still fine
reset(); seed(nba_pls=(4, 4, 4, 4)); learned(0.65); cautious()
ok("cautious: no loosening", not stepped() and vals() == {"share:nba": 0.65})
reset(); seed(); cautious()
ok("cautious: tightening still allowed", stepped() and vals().get("share:nba", 1.0) < 1.0)
reset(); seed(nba_pls=(4, 4, 4, 4)); learned(0.65); E._fa_update(lambda s: s.update(caution={"level": "x"}))
ok("an unreadable caution level fails closed (no loosening)", not stepped())

# 7. the floor and the feedback loop: a league held at 5% still has its evidence and can step back up
reset(); seed(); learned(0.05)
st_=stepped(); ok("floor: never below 5%", vals().get("share:nba") == 0.05)
reset(); seed(nba_pls=(4, 4, 4, 4), stake=1.0); learned(0.05)
ok("feedback loop: at the floor the paper evidence still arrives and the share steps back up, one step", stepped() and abs(vals().get("share:nba", 1.0) - 0.10) < 1e-9)
by, _ = E._share_load(NOW)
ok("the evidence is not filtered by the shares (all 4 NBA bets a day are there)", len(by["share:nba"]) == 80 and len(by["share:@combo"]) == 80 and len(by["share:@single"]) == 20)

# 8. never the same week as the combo bars
reset(); seed()
E._fa_update(lambda s: s.update(lessons={"steps": {"bar": NOW - 2 * DAY}}))
ok("a combo-bar step this week holds the share", not stepped() and "share:nba" not in vals())
reset(); seed()
E._fa_update(lambda s: s.update(lessons={"steps": {"share": NOW - 2 * DAY}}))
plan = E._fal_plan(E.fa_state(), NOW)
ok("and a share step this week holds the bars", plan["status"]["share"]["note"].startswith("one step a week"))
reset(); seed()
E._fa_update(lambda s: s.update(lessons={"steps": {"bar": NOW - 2 * DAY}}))
plan = E._fal_plan(E.fa_state(), NOW)
ok("the plan says why it waits", "never move in the same week" in plan["status"]["share"]["note"])

# 9. fail closed on unreadable data
reset(); seed()
real = E.store_rows_strict
E.store_rows_strict = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
ok("unreadable data: no step", not stepped() and "share:nba" not in vals())
E.store_rows_strict = real
reset(); seed()
E._fa_update(lambda s: s.update(lessons={"vals": {"share:nba": 7}}))
ok("a saved share outside 5-100% is unreadable", E._fal_vals(E.fa_state())[0] is None and not stepped())
reset(); seed(); learned(0.65)
E.store_x("update panel set body='{bad'")
ok("a corrupt panel row: no step", not stepped() and vals() == {"share:nba": 0.65})

# 10. master switch, freeze, undo
reset(); seed(); E._fa_update(lambda s: s.update(fa_lessons=False))
ok("master switch off: no step", not stepped() and vals() == {})
reset(); seed(); E.ap_freeze("share", True)
ok("frozen (the whole record): no step", not stepped() and vals() == {})
reset(); seed(); E.ap_freeze("share:nba", True)
ok("frozen (one league): that league is left alone", "share:nba" not in vals() and not any("NBA" in e["text"] for e in lessons().get("log") or []))
reset(); seed(); tick(); k = next(iter(vals()))
res = E.ap_undo(NOW + 1)
ok("undo puts it back and holds it", res[0] and k not in vals() and lessons()["holds"][k] > NOW)
ok("the undone share is held (nothing loosens it) and a second undo does nothing", E.ap_undo(NOW + 2)[0] is False)

# 11. a revert after a losing week puts it back
reset(); seed(); tick(); k = next(iter(vals())); v_before = vals()[k]
n_old = len([e for e in lessons()["log"] if e.get("kind") == "revert"])
for d in range(1, 6):   # newer bets the share would have blocked WON: the step cost money
    tt = NOW + d * DAY
    items = [{"id": f"w{i}", "kind": "combo", "state": "paper", "legs": [{"ticker": NBA}], "stake": 7.0, "result": "won", "pl": 4.0, "clv": 0.02,
              "at": tt + 600 + i * 60} for i in range(4)]
    E.store_x("insert or replace into panel values(?,?,?,?,?)", (E._panel_day(tt), "paper", tt + 600, "done", json.dumps({"at": tt, "items": items})))
tick(NOW + 8 * DAY)
ok("a losing step is reverted a week later, in plain words", len([e for e in lessons()["log"] if e.get("kind") == "revert"]) == n_old + 1 and k not in vals())
ok("the revert is logged with the old value and the dollars", any(e.get("kind") == "revert" and "back" in e["text"] and "lost" in e["text"] for e in lessons()["log"]))

# 12. the buy pass: shares skip, never add; the cap is never exceeded; the floor keeps the first bet
def mk(t, ev, f, p, k, lg="nba"):
    l = {"ticker": t, "event": ev, "pick": t, "p": p, "fair": f}; E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(k))
    return E._cand("single", lg, [l], f, (f - p - E.single_fee(p)) / (p + E.single_fee(p)), "w", price=p)


def fresh(nn=6, nh=0):
    E._panel_table()
    E.store_x("delete from panel", ())
    cs = [mk(f"KXNBAGAME-26NOV27G{i}-A", f"KXNBAGAME-G{i}", .60 + i / 100, .50, NOW + 9000) for i in range(nn)]
    pool = {"nba": (time.time(), cs)}
    if nh:
        pool["nhl"] = (time.time(), [mk(f"KXNHLGAME-26NOV27H{i}-A", f"KXNHLGAME-H{i}", .60 + i / 100, .50, NOW + 9000, "nhl") for i in range(nh)])
    E.PANEL_POOL = pool
    E.panel_pass()
    return E.panel_get("real")


def run_pass(share, cap=100.0, nn=6, nh=0):
    reset()
    BOUGHT.clear()
    p = fresh(nn, nh)
    E.fa_set(True, limits={"cap": cap, "max_open": 30})
    if share is not None:
        E._fa_update(lambda s: s.update(lessons={"vals": share}))
    res = E.full_auto_pass(now=time.time())
    live = [c for c in E.panel_get("real")["items"] if c.get("state") == "scheduled"]
    return p, res, live


p, res, live_all = run_pass(None)
n_all, spend_all = len(live_all), sum(c["stake"] for c in live_all)
ok("baseline: no shares, it approves the draft", res and n_all >= 3)
p, res, live = run_pass({"share:nba": 0.1}, cap=100.0)
spend = sum(c["stake"] for c in live)
ok("a 10% NBA share holds NBA to one bet at most plus what fits under 10 dollars", len(live) < n_all and spend <= 10 + max(c["stake"] for c in p["items"]) + 0.01)
ok("the first bet of the day always passes (the floor keeps a league learning)", len(live) >= 1)
ok("shares only skip: spend is never more than with no share, and never above the cap", spend <= spend_all + 0.01 and spend <= 100 + 0.01)
p, res, live = run_pass({"share:nba": 0.05}, cap=100.0)
ok("a 5% share still lets the first NBA bet through", len(live) == 1)
p, res, live = run_pass({"share:nba": 0.05}, cap=12.0)
ok("the daily cap still binds under shares", sum(c["stake"] for c in live) <= 12.0 + 0.01)
p, res, live = run_pass({"share:@single": 0.1}, cap=100.0)
ok("a bet-type share applies too (every draft bet here is a single)", 1 <= len(live) < n_all)
p, res, live = run_pass({"share:nba": 0.1, "share:@single": 0.9}, cap=100.0, nn=3, nh=3)
nhl = [c for c in live if "NHL" in c["legs"][0]["ticker"].upper()]
ok("another league is not held by the NBA share", len(nhl) >= 1)
E._fa_update(lambda s: s.update(fa_lessons=False))
p2 = fresh(6)
res = E.full_auto_pass(now=time.time())
live2 = [c for c in E.panel_get("real")["items"] if c.get("state") == "scheduled"]
ok("Autopilot off: shares are ignored entirely", res and len(live2) >= n_all - 1)

# 13. a malformed saved share stops the pass (as every learned number does), and the pass never raises
reset(); fresh(4); E.fa_set(True, limits={"cap": 100, "max_open": 30})
E._fa_update(lambda s: s.update(lessons={"vals": {"share:nba": 5}}))
ok("a malformed share approves nothing", E.full_auto_pass(now=time.time()) is None)
reset(); fresh(4); E.fa_set(True, limits={"cap": 100, "max_open": 30})
E._fa_update(lambda s: s.update(lessons={"vals": {"share:nba": 0.5}}))
orig = E.store_rows_strict
E.store_rows_strict = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
r13 = E.full_auto_pass(now=time.time())
E.store_rows_strict = orig
ok("unreadable bets with a share set: approves nothing, does not raise (fail closed)", r13 is None and not [c for c in E.panel_get("real")["items"] if c.get("state") == "scheduled"])

# 13b. the guard itself: unreadable today's bets raise (the pass catches it and approves nothing); settled-today bets count
reset(); E._fa_update(lambda s: s.update(lessons={"vals": {"share:nba": 0.2}}))
E.store_rows_strict = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
try:
    E.FaShareGuard(E.fa_state(), 30.0, E._panel_day(NOW), NOW); raised = False
except RuntimeError:
    raised = True
E.store_rows_strict = orig
ok("FaShareGuard raises when today's bets can't be read", raised)
day0 = E._panel_day(NOW)
nba_c = {"id": "x1", "kind": "single", "state": "won", "result": "won", "bought_at": NOW - 3600, "legs": [{"ticker": NBA}], "stake": 10.0}
E.store_x("insert into panel values(?,?,?,?,?)", (day0, "real", NOW, "done", json.dumps({"at": NOW, "items": [nba_c]})))
E._fa_update(lambda s: s.update(bets={f"{day0}|x1": {"at": NOW}}))
g = E.FaShareGuard(E.fa_state(), 30.0, day0, NOW)
cand = {"id": "x2", "kind": "single", "legs": [{"ticker": NBA}], "stake": 3.0}
ok("a bet already SETTLED today still counts toward the league's share", g.spent["share:nba"] == 10.0 and not g.allows(cand, 3.0))
ok("another league is untouched by it", g.allows({"id": "x3", "kind": "single", "legs": [{"ticker": NHL}], "stake": 3.0}, 3.0))
nba_c.pop("bought_at")
E.store_x("update panel set body=? where mode='real'", (json.dumps({"at": NOW, "items": [dict(nba_c, state="cancelled", result=None)]}),))
ok("a cancelled never-bought bet does not count", E.FaShareGuard(E.fa_state(), 30.0, day0, NOW).spent["share:nba"] == 0)

# 13c. the #614 open-bet limit still moves (the share branch must not replace it)
ob = E.FAL["open"]
mid = (ob["lo"] + ob["hi"]) // 2
mv = dict(E._fal_moves("open", mid))
ok("open limit: tighter is one step down, looser one step up", mv.get("tighter") == mid - ob["step"] and mv.get("looser") == mid + ob["step"])
ok("open limit: no step past either end", "tighter" not in dict(E._fal_moves("open", ob["lo"])) and "looser" not in dict(E._fal_moves("open", ob["hi"])))
ok("open limit: Pete's number outside the range is left alone", E._fal_moves("open", ob["hi"] + 100) == [])

# 15. the replay judges the same rule as the live guard: a share of the DAILY CAP, not of the practice panel's bigger day
reset()
t0 = NOW - DAY
big = [{"id": f"b{i}", "kind": "combo", "state": "paper", "legs": [{"ticker": NBA}], "stake": 5.0, "result": "lost", "pl": -5.0, "clv": 0.0,
        "at": t0 + i * 60} for i in range(20)]          # a $100 practice day against a $30 cap
E.store_x("insert into panel values(?,?,?,?,?)", (E._panel_day(t0), "paper", t0, "done", json.dumps({"at": t0, "items": big})))
by, passes = E._share_load(NOW)
rs = by["share:nba"]
ok("the replay keeps only what the live daily cap ($30) would have allowed", len(rs) == 6 and all(r["base"] == 30.0 for r in rs))
ok("a 20% share replays as $6 (first bet only), not $20 of the $100 day", sum(passes(rs, 0.2)) == 1)
E._fa_update(lambda s: s.update(lessons={"vals": {"share:nba": 0.2}}))
g = E.FaShareGuard(E.fa_state(), 30.0, E._panel_day(NOW), NOW)
cb = {"id": "z", "kind": "combo", "legs": [{"ticker": NBA}], "stake": 5.0}
g.take(cb, 5.0)
ok("the live guard blocks the second $5 at 20% of $30, the same as the replay", not g.allows(cb, 5.0))

# 16. step sizes: tighten at most 15 pts in a week, loosen exactly one 5-pt step, never below the 5% floor
rs_ = [{"day": "d", "s": 5.0, "base": 30.0}] * 6
ok("loosen is exactly one 5-pt step", E._share_step(rs_, E._share_passes, 0.3, "looser") == 0.35 and E._share_step(rs_, E._share_passes, 0.95, "looser") == 1.0)
t = E._share_step(rs_, E._share_passes, 1.0, "tighter")
ok("tighten is never more than 15 pts (here no bet changes within 15 pts, so none)", t is None or t >= 0.85 - 1e-9)
ok("tighten at the floor stays put", E._share_step(rs_, E._share_passes, 0.05, "tighter") is None)
ok("tighten can't pass the floor", E._share_step(rs_, E._share_passes, 0.10, "tighter") in (None, 0.05))

# 17. a share-held bet is not 'no slot' evidence for the #614 open-bet limit
def slots_run(share):
    reset(); E.store_x("delete from fa_slots", ()); E.FA_SLOT_RUN["at"] = 0.0
    if share:
        E._fa_update(lambda s: s.update(lessons={"vals": {"share:nba": 0.05}}))
    cs = [{"id": f"s{i}", "kind": "combo", "stake": 5.0, "pays": 9.0, "legs": [{"ticker": NBA.replace("LALBOS", f"LAL{i}BOS")}]} for i in range(3)]
    saved = (E.fa_check, E.panel_get, E._fa_candidates)
    E.fa_check = lambda *a, **k: {"brake": None, "caution": {"changed": False, "level": 0, "events": []}, "blockers": ["x"], "slots_only": True,
                                  "room": 30.0, "slots": 0, "free": 100.0, "open": 15, "cap": 30.0}
    E.panel_get = lambda *a, **k: {"at": NOW, "status": "draft"}
    E._fa_candidates = lambda *a, **k: list(cs)
    try:
        E._full_auto_pass(now=NOW, log=lambda *a: None)
    finally:
        E.fa_check, E.panel_get, E._fa_candidates = saved
    return E.store_rows("select open_at from fa_slots where kind='skip'", ())


E._fa_slot_table()
ok("control: with no share every turned-away bet is logged as an open-slot skip", len(slots_run(False)) == 3)
ok("with a 5% share only the bet the share lets through is logged", len(slots_run(True)) == 1)

# 18. swapped-in bets count toward the share like fa_check counts them
reset(); E._fa_update(lambda s: s.update(lessons={"vals": {"share:nba": 0.2}}))
day0 = E._panel_day(NOW)
orig_b = {"id": "o1", "kind": "combo", "state": "swapped", "bought_at": NOW - 900, "legs": [{"ticker": NBA}], "stake": 10.0}
swap_b = {"id": "o2", "kind": "combo", "state": "bought", "bought_at": NOW - 600, "swap_of": "o1", "legs": [{"ticker": NBA}], "stake": 10.0}
E.store_x("insert into panel values(?,?,?,?,?)", (day0, "real", NOW, "done", json.dumps({"at": NOW, "items": [orig_b, swap_b]})))
E._fa_update(lambda s: s.update(bets={f"{day0}|o1": {"at": NOW}}))
ok("a bet swapped in for one of ours (new id) counts toward the share", E.FaShareGuard(E.fa_state(), 30.0, day0, NOW).spent["share:nba"] == 20.0)

# 19. the bar side of 'never the same week': a bar step is refused when a share stepped this week
reset(); bk = E._fal_key("bar", "nba")
act = {"do": "step", "rec": "bar", "key": bk, "from": 0.0, "to": E.FAL["bar"]["step"], "dir": "tighter", "lb": 1.0, "borrow": False, "stale": False,
       "ev": {"band": 30, "gain": 5.0, "hold_n": 5, "hold": 1.0}}
E._fa_update(lambda s: E._fal_apply(s, {"actions": [dict(act)], "status": {}}, NOW))
ok("control: a bar step applies when no share stepped this week", bk in vals() or "bar" in str(lessons().get("vals")))
reset()
E._fa_update(lambda s: s.update(lessons={"steps": {"share": NOW - 2 * DAY}}))
E._fa_update(lambda s: E._fal_apply(s, {"actions": [dict(act)], "status": {}}, NOW))
ok("a bar step is refused in the week after a share step", not any(str(k).startswith("bar") for k in (lessons().get("vals") or {}).get("bar", {}) or {}) and bk not in (lessons().get("vals") or {})
   and "bar" not in (lessons().get("steps") or {}))

# 14. the card
reset(); seed(); tick()
view = E.fal_view(E.fa_state())
ok("the card lists the record, its log, Undo and Freeze", any(r["rec"] == "share" for r in view["recs"]) and view["undo"] and "budget share" in view["undo"])
