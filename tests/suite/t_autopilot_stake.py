# CHECK: group=engine
# Autopilot's bet size and cap use (#145 step 7): full auto moves its bet size (a multiple of today's, 50% to 150%, a step is 5% of
# the current size) and the share of Pete's daily cap it uses (50% to 100%, 5 points) weekly through the shared registry. TIGHTEN
# FAST, LOOSEN SLOW: loosening needs a profitable last 30 days of REAL full-auto bets, a soft brake quiet for 14 days, the shared
# gate (70/30, bootstrap, minimum sample) and 14 days since the last move; any brake week or a losing month tightens one step at
# once. Never the same week as the bars or shares, at most 2 settings a week, Pete's $300 / $30 / $20 never exceeded. Kalshi is fake.
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
E.kalshi_send = lambda *a, **k: {}
E.book_depth = lambda t, max_age=60: {"ask": 0.50, "bid": 0.49}
E.buy_single = lambda t, n, px: (n, None)
E.can_trade = lambda: True
E._held_all = lambda: []
E.panel_record = lambda: {"paper": {"ready": True, "bets": 60, "pl": 40.0, "days": 20, "days_up": 14, "clv": 0.01}, "real": {}}
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n + ("" if c else "   [vals=%s]" % vals()))
NOW = time.time()
DAY = 86400
NBA = "KXNBAGAME-26NOV20LALBOS-LAL"


def reset(quiet=True):
    E.store_x("drop table if exists panel", ())
    E.STORE["panel_ok"] = False
    E._panel_table()
    try:
        os.remove(E._fa_path())
    except OSError:
        pass
    E.FAL_RUN["at"] = 0.0
    E._fa_update(lambda s: s.update(on=True, gate="passed", lessons={"cq": {"first": NOW - 40 * DAY, "last": 0}} if quiet else {}))


def seed(days=25, pls=(4, 3, -2, 4), stake=5.0, mult=None):
    """Full auto's own settled REAL bets: `pls` each day, bought at 10:00 plus a minute each."""
    bets, sizes = {}, {}
    for d in range(1, days + 1):
        t0 = NOW - d * DAY
        items = []
        for i, p in enumerate(pls):
            cid = f"r{d}_{i}"
            items.append({"id": cid, "kind": "single", "state": "won" if p > 0 else "lost", "result": "won" if p > 0 else "lost", "pl": p,
                          "stake": stake, "bought_at": t0 + 600 + i * 60, "legs": [{"ticker": NBA}]})
            bets[f"{E._panel_day(t0)}|{cid}"] = {"at": t0}
            if mult:
                sizes[f"{E._panel_day(t0)}|{cid}"] = mult
        E.store_x("insert or replace into panel values(?,?,?,?,?)", (E._panel_day(t0), "real", t0, "done", json.dumps({"at": t0, "items": items})))
    E._fa_update(lambda s: (s["bets"].update(bets), s.update(sizes=sizes) if sizes else None))


def seed_paper(days=20, pl=2.0, n=6, stake=5.0, clv=0.02):
    """Practice panel history: `n` bets of `stake` a day, all won, totalling exactly the $30 live cap (what the cap-use judge replays)."""
    for d in range(1, days + 1):
        t0 = NOW - d * DAY
        items = [{"id": f"p{i}", "kind": "combo", "state": "paper", "legs": [{"ticker": NBA}], "stake": stake, "result": "won", "pl": pl,
                  "clv": clv, "at": t0 + 600 + i * 60} for i in range(n)]
        E.store_x("insert into panel values(?,?,?,?,?)", (E._panel_day(t0), "paper", t0, "done", json.dumps({"at": t0, "items": items})))


def lessons():
    return E.fa_state().get("lessons") or {}


def vals():
    return dict(lessons().get("vals") or {})


def tick(at=NOW):
    E.FAL_RUN["at"] = 0.0
    return E.fal_tick(E.fa_state(), at, lambda *a: None)


def steps_of(*recs):
    return [e for e in lessons().get("log") or [] if e.get("kind") == "step" and e.get("rec", e.get("key", "")) in recs]


def has(key):
    return key in vals()


def learned(key, v, since=NOW - 30 * DAY):
    E._fa_update(lambda s: s["lessons"].update(vals={**s["lessons"].get("vals", {}), key: v}, since={**s["lessons"].get("since", {}), key: since}))


def cautious(level=1):
    E._fa_update(lambda s: s.update(caution={"level": level, "base_at": NOW, "since": NOW, "why": "x"}))


# 1. registered with the right bounds and steps; empty data = no change
reset(False)
ok("stake and capuse are registered with their ranges", list(E.AP_REG) == ["bar", "sbev", "game", "open", "share", "stake", "capuse"]
   and E.FAL["stake"] == {"lo": 0.5, "hi": 1.5, "step": 0.05} and E.FAL["capuse"] == {"lo": 0.5, "hi": 1.0, "step": 0.05})
ok("both start at today's behaviour", E.FAL_START["stake"] == 1.0 and E.FAL_START["capuse"] == 1.0)
tick()
ok("empty data: nothing changes, nothing saved", vals() == {} and not [e for e in lessons().get("log") or [] if e.get("kind") == "step"])
ok("with nothing learned the live readers return today's size", E.ap_stake_mult(E.fa_state()) == 1.0 and E.ap_cap_use(E.fa_state()) == 1.0)

# 2. step sizes and bounds, exact
mv = dict(E._fal_moves("stake", 1.0, [], None))
ok("stake: one step is 5% of the current size, both ways", mv == {"tighter": 0.95, "looser": 1.05})
mv = dict(E._fal_moves("stake", 0.95, [], None))
ok("stake: the step is 5% of the CURRENT size (0.95 -> 0.9025 / 0.9975)", mv == {"tighter": 0.9025, "looser": 0.9975})
ok("stake: never below 50%", "tighter" not in dict(E._fal_moves("stake", 0.5, [], None)) and dict(E._fal_moves("stake", 0.51, [], None))["tighter"] == 0.5)
ok("stake: never above 150%", "looser" not in dict(E._fal_moves("stake", 1.5, [], None)) and dict(E._fal_moves("stake", 1.45, [], None))["looser"] == 1.5)
mv = dict(E._fal_moves("capuse", 1.0, [], None))
ok("cap use: 5 points, never above 100%", mv == {"tighter": 0.95} )
mv = dict(E._fal_moves("capuse", 0.5, [], None))
ok("cap use: never below 50%, loosens back 5 points", mv == {"looser": 0.55})
ok("the fence clamps both, and rejects junk", E.ap_clamp("stake", 9) == 1.5 and E.ap_clamp("stake", 0.1) == 0.5 and E.ap_clamp("capuse", 2) == 1.0
   and E.ap_clamp("capuse", 0.2) == 0.5 and E.ap_clamp("stake", float("nan")) is None and E.ap_clamp("capuse", True) is None)

# 3. loosen slow: a profitable month, quiet brake, enough sample -> exactly ONE step
reset(); seed(); learned("stake_mult", 0.9)
tick()
ok("loosen: a profitable quiet month raises the size by exactly one step (0.9 -> 0.945)", vals().get("stake_mult") == 0.945)
ok("loosen: it is logged in plain words with dollars", any("bet size" in e["text"] and "$" in e["text"] for e in lessons()["log"]))
ok("loosen: Pete's limits are untouched", E.fa_state()["cap"] == 30.0 and E.fa_state()["bank"] == 300.0 and E.fa_state()["day_loss"] == 20.0)
tick(NOW + DAY)
ok("one step a week", vals().get("stake_mult") == 0.945)
reset(); seed(); learned("stake_mult", 1.0)
tick()
ok("loosen past today's size is allowed on evidence (1.0 -> 1.05)", vals().get("stake_mult") == 1.05)
reset(); seed(); learned("stake_mult", 1.5)
tick()
ok("at the 150% ceiling nothing more happens", vals().get("stake_mult") == 1.5)
reset(); seed(); seed_paper(); learned("cap_use", 0.8); E._fa_update(lambda s: s["lessons"].update(steps={"stake": NOW - 20 * DAY, "capuse": NOW - 30 * DAY}))
tick()
ok("cap use loosens exactly 5 points (0.8 -> 0.85) on the practice-panel evidence", vals().get("cap_use") == 0.85)
ok("cap use loosening is logged in plain words", any("cap" in e["text"].lower() and e.get("kind") == "step" for e in lessons()["log"]))
reset(); learned("cap_use", 0.8)
tick()
ok("cap use with no practice-panel evidence stays at 0.8", vals().get("cap_use") == 0.8)

# 4. loosening gates
reset(); seed(); learned("stake_mult", 0.9, since=NOW - 3 * DAY)
tick()
ok("loosen waits 14 days after the last move", vals().get("stake_mult") == 0.9)
reset(); seed(days=15); learned("stake_mult", 0.9)
tick()
ok("loosen needs twice the minimum sample", vals().get("stake_mult") == 0.9)
reset(); seed(pls=(2, -3, -3, 3)); learned("stake_mult", 0.9)
tick()
ok("loosen refused when the last 30 days lost money: tightens, never loosens (0.9 -> 0.855)", vals().get("stake_mult") == 0.855)
reset(quiet=False); seed(); learned("stake_mult", 0.9)
tick()
ok("loosen refused when full auto has not been watched for 14 days (never quiet)", vals().get("stake_mult") == 0.9)
reset(); seed(); learned("stake_mult", 0.9); cautious(1)
tick()
ok("brake gating: cautious now = no loosening, only a tightening (0.9 -> 0.855)", vals().get("stake_mult") == 0.855)
reset(); seed(); learned("stake_mult", 0.9); E._fa_update(lambda s: s.update(caution={"level": 0, "base_at": 0, "since": NOW - 5 * DAY, "why": "x"}))
tick()
ok("brake gating: a cautious episode 5 days ago = no loosening, only a tightening (0.9 -> 0.855)", vals().get("stake_mult") == 0.855)
reset(); seed(); learned("stake_mult", 0.9); E._fa_update(lambda s: s.update(caution={"level": "x"}))
tick()
ok("brake gating: an unreadable caution level fails closed (no loosening; tightens 0.9 -> 0.855)", vals().get("stake_mult") == 0.855)
reset(); seed(); learned("stake_mult", 0.9); E._fa_update(lambda s: s.update(history=[{"at": NOW - 6 * DAY, "ev": "brake"}]))
tick()
ok("brake gating: a day-brake note inside 14 days = no loosening, only a tightening (0.9 -> 0.855)", vals().get("stake_mult") == 0.855)
reset(); seed(); learned("stake_mult", 0.9); E._fa_update(lambda s: s.update(history=[{"at": NOW - 20 * DAY, "ev": "brake"}] + [{"at": NOW - 19 * DAY, "ev": "x"}] * 19))
tick()
ok("an old brake (20 days ago) does not block loosening", vals().get("stake_mult") == 0.945)

# 5. tighten fast: a brake week or a net-negative month, one step, no bootstrap
reset(); seed(); learned("stake_mult", 1.0); E._fa_update(lambda s: s.update(history=[{"at": NOW - 2 * DAY, "ev": "brake"}]))
tick()
ok("a brake in the last week tightens one step at once (1.0 -> 0.95)", vals().get("stake_mult") == 0.95)
ok("and says why in plain words", any("soft brake" in e["text"] for e in lessons()["log"]))
reset(); seed(pls=(2, -4, -4, 1)); learned("stake_mult", 1.0)
tick()
ok("a net-negative month tightens one step (1.0 -> 0.95)", vals().get("stake_mult") == 0.95)
reset(); seed(pls=(2, -4, -4, 1)); learned("stake_mult", 0.5)
tick()
ok("tightening stops at the 50% floor", vals().get("stake_mult") == 0.5)
reset(); seed(days=1, pls=(-3, -3))
tick()
ok("too few bets: no tightening on thin data", vals() == {})
reset(); seed(pls=(2, -4, -4, 1)); tick(); tick(NOW + DAY); tick(NOW + 2 * DAY)
ok("one step a week even when tightening (one step after three looks)", len([e for e in lessons()["log"] if e.get("kind") == "step"]) == 1 and len(vals()) == 1)

# 6. same-week exclusion and the cap of two settings a week
reset(); seed(pls=(2, -4, -4, 1)); E._fa_update(lambda s: s["lessons"].update(steps={"bar": NOW - 2 * DAY}))
tick()
ok("a bar step this week holds bet size and cap use", "stake_mult" not in vals() and "cap_use" not in vals())
reset(); seed(pls=(2, -4, -4, 1)); E._fa_update(lambda s: s["lessons"].update(steps={"share": NOW - 2 * DAY}))
tick()
ok("a share step this week holds bet size and cap use", "stake_mult" not in vals() and "cap_use" not in vals())
reset(); seed(pls=(2, -4, -4, 1)); E._fa_update(lambda s: s["lessons"].update(steps={"stake": NOW - 2 * DAY}))
tick()
ok("a bet-size step this week holds cap use", "cap_use" not in vals())
reset(); seed(pls=(2, -4, -4, 1)); E._fa_update(lambda s: s["lessons"].update(steps={"capuse": NOW - 2 * DAY}))
tick()
ok("a cap-use step this week holds bet size", "stake_mult" not in vals())
plan = E._fal_plan(E.fa_state(), NOW)
ok("the plan says why it waits", "same week" in plan["status"]["stake"]["note"])
reset(); seed(pls=(2, -4, -4, 1))
plan = E._fal_plan(E.fa_state(), NOW)
acts = [a["rec"] for a in plan["actions"] if a["do"] == "step"]
ok("never stake and cap use together in one plan, and at most two settings", not ({"stake", "capuse"} <= set(acts)) and len(acts) <= E.AP_WEEK_MAX)
# the weekly limit, behaviourally: a third loosening in one week is refused, a tightening still goes ahead
reset(); seed(); learned("stake_mult", 0.9); E._fa_update(lambda s: s["lessons"].update(steps={"open": NOW - DAY, "game": NOW - DAY}))
tick()
ok("third loosening in a week refused: two other settings moved, a profitable quiet month does not raise bet size", vals().get("stake_mult") == 0.9)
reset(); seed(pls=(2, -4, -4, 1)); learned("stake_mult", 1.0); E._fa_update(lambda s: s["lessons"].update(steps={"open": NOW - DAY, "game": NOW - DAY}))
tick()
ok("with the same two moves this week, a tightening is still allowed (1.0 -> 0.95)", vals().get("stake_mult") == 0.95)
# tightening is never held by the two-a-week limit; a loosening is
reset(); seed(pls=(2, -4, -4, 1)); E._fa_update(lambda s: s["lessons"].update(steps={"open": NOW - DAY, "game": NOW - DAY}))
tick()
ok("two other settings moved this week: a losing month still tightens bet size (1.0 -> 0.95)", vals().get("stake_mult") == 0.95)
reset(); seed(); learned("stake_mult", 0.9); E._fa_update(lambda s: s["lessons"].update(steps={"open": NOW - DAY, "game": NOW - DAY}))
tick()
ok("two other settings moved this week: a loosening of bet size waits (stays 0.9)", vals().get("stake_mult") == 0.9)
reset(); seed(); learned("stake_mult", 0.9); E._fa_update(lambda s: s["lessons"].update(steps={"open": NOW - DAY}))
tick()
ok("only one other setting moved this week: the loosening goes through (0.9 -> 0.945)", vals().get("stake_mult") == 0.945)
reset(); seed(); learned("stake_mult", 0.9); E._fa_update(lambda s: s["lessons"].update(steps={"open": NOW - DAY, "game": NOW - DAY}))
plan = E._fal_plan(E.fa_state(), NOW)
ok("the plan says why a loosening waits", "two settings already changed" in plan["status"]["stake"]["note"])
# a brake week tightens stake even with two others already moved
reset(); seed(); learned("stake_mult", 1.0); E._fa_update(lambda s: (s["lessons"].update(steps={"open": NOW - DAY, "game": NOW - DAY}), s.update(history=[{"at": NOW - 2 * DAY, "ev": "brake"}])))
tick()
ok("a brake week tightens bet size even with two others already moved", vals().get("stake_mult") == 0.95)
# fair rotation: two loosenings compete for one slot; the one stepped longest ago wins
reset(); seed(); seed_paper(); learned("stake_mult", 0.9); learned("cap_use", 0.8)
E._fa_update(lambda s: s["lessons"].update(steps={"open": NOW - DAY, "stake": NOW - 20 * DAY, "capuse": NOW - 30 * DAY}))
tick()
ok("rotation: bet size and cap use never move together", not ("stake_mult" in vals() and vals().get("stake_mult") != 0.9 and vals().get("cap_use") != 0.8))
ok("rotation: the setting stepped longest ago (cap use) takes the one free slot", vals().get("cap_use") == 0.85 and vals().get("stake_mult") == 0.9)
reset(); seed(); seed_paper(); learned("stake_mult", 0.9); learned("cap_use", 0.8)
E._fa_update(lambda s: s["lessons"].update(steps={"open": NOW - DAY, "stake": NOW - 30 * DAY, "capuse": NOW - 20 * DAY}))
tick()
ok("rotation: and the other way round (bet size is longer waiting, so it goes)", vals().get("stake_mult") == 0.945 and vals().get("cap_use") == 0.8)

# 7. a revert after a losing week puts it back; a tightening is never reverted
reset(); seed(); learned("stake_mult", 0.9); tick(); v1 = vals().get("stake_mult")
ok("setup: it loosened", v1 == 0.945)
for d in range(1, 6):   # the week after: real bets at the larger size LOST
    tt = NOW + d * DAY
    items = [{"id": f"L{d}_{i}", "kind": "single", "state": "lost", "result": "lost", "pl": -5.0, "stake": 5.0, "bought_at": tt + 600 + i * 60,
              "legs": [{"ticker": NBA}]} for i in range(4)]
    E.store_x("insert or replace into panel values(?,?,?,?,?)", (E._panel_day(tt), "real#L", tt, "done", json.dumps({"at": tt, "items": items})))
    E._fa_update(lambda s, tt=tt, d=d: s["bets"].update({f"{E._panel_day(tt)}|L{d}_{i}": {"at": tt} for i in range(4)}))
tick(NOW + 8 * DAY)
ok("a losing loosened step is reverted a week later to EXACTLY the old value", vals().get("stake_mult", 0.9) == 0.9)
ok("and the revert is logged in plain words with the dollars", any(e.get("kind") == "revert" and "back" in e["text"] for e in lessons()["log"]))
reset(); seed(pls=(2, -4, -4, 1)); learned("stake_mult", 1.0); tick(); t1 = vals().get("stake_mult")
tick(NOW + 8 * DAY)
ok("a tightening is never auto-reverted (it stays at 0.95)", t1 == 0.95 and vals().get("stake_mult") == 0.95
   and not [e for e in lessons()["log"] if e.get("kind") == "revert"])

# 8. unreadable data = no change
reset(); seed(); learned("stake_mult", 0.9)
real = E.store_rows_strict
E.store_rows_strict = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
tick()
E.store_rows_strict = real
ok("unreadable bets: no step in either direction", vals().get("stake_mult") == 0.9)
reset(); seed(pls=(2, -4, -4, 1)); learned("stake_mult", 1.0)
E.store_rows_strict = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
tick()
E.store_rows_strict = real
ok("unreadable bets: no tightening either (fail closed means no change)", vals().get("stake_mult") == 1.0)
reset(); seed(); learned("stake_mult", 0.9); E._fa_update(lambda s: s.update(sizes={f"{E._panel_day(NOW - DAY)}|r1_0": "big"}))
tick()
ok("an unreadable recorded size: no change", vals().get("stake_mult") == 0.9)
reset(); seed(); E._fa_update(lambda s: s["lessons"].update(vals={"stake_mult": 7}))
ok("a saved size outside 50-150% is unreadable", E._fal_vals(E.fa_state())[0] is None)
ok("an unreadable saved size never buys bigger: the live multiple is the smallest", E.ap_stake_mult(E.fa_state()) == 0.5)
E._fa_update(lambda s: s["lessons"].update(vals={"cap_use": 3}))
ok("an unreadable saved cap use never raises the cap: the smallest share", E.ap_cap_use(E.fa_state()) == 0.5)

# 9. master switch, freeze, undo, hold
reset(); seed(pls=(2, -4, -4, 1)); E._fa_update(lambda s: s.update(fa_lessons=False)); tick()
ok("master switch off: no step", vals() == {})
ok("master switch off: the live readers return today's numbers", E.ap_stake_mult(E.fa_state()) == 1.0 and E.ap_cap_use(E.fa_state()) == 1.0)
reset(); seed(pls=(2, -4, -4, 1)); E.ap_freeze("stake", True); tick()
ok("frozen: no bet-size step", "stake_mult" not in vals())
reset(); seed(pls=(2, -4, -4, 1)); tick(); k = [x for x in ("stake_mult", "cap_use") if x in vals()]
res = E.ap_undo(NOW + 1)
ok("undo puts it back and holds it two weeks", k and res[0] and not [x for x in k if x in vals()] and all(lessons()["holds"][x] > NOW for x in k))
learned("stake_mult", 0.9)
reset(); seed(); learned("stake_mult", 0.9); E._fa_update(lambda s: s["lessons"].update(holds={"stake_mult": NOW + 5 * DAY}))
tick()
ok("a held setting does not loosen", vals().get("stake_mult") == 0.9)

# 10. live: sizing with the soft brake, the cap, the bankroll and the loss limit
reset()
c = E.fa_check(E.fa_state(), now=NOW)
ok("no autopilot: the cap is Pete's", c["cap"] == 30.0 and c["cap_use"] == 1.0 and c["stake_mult"] == 1.0)
reset(); learned("cap_use", 0.6)
c = E.fa_check(E.fa_state(), now=NOW)
ok("cap use 60%: the day's cap is 60% of Pete's $30", c["cap"] == 18.0 and c["room"] == 18.0)
cautious(1)
c = E.fa_check(E.fa_state(), now=NOW)
ok("cap use stacks on the brake's own cut (50% of 18 = 9)", c["cap"] == 9.0 and c["room"] == 9.0)
ok("sizing: 1.0 = the brake's own size", E._fa_sized(10.0, 1.0, 1.0) == E._fa_scaled(10.0, 1.0) == 10.0)
ok("sizing: 0.9 shrinks a $10 bet to $9", E._fa_sized(10.0, 1.0, 0.9) == 9.0)
ok("sizing: never below $2", E._fa_sized(2.0, 1.0, 0.5) == 2.0)
ok("sizing: 1.2 enlarges a $10 bet to $12 within the room", E._fa_sized(10.0, 1.0, 1.2, 100, 100, 100, 100) == 12.0)
ok("sizing: never past the cap room left", E._fa_sized(10.0, 1.0, 1.5, 11.0, 100, 100, 100) == 11.0)
ok("sizing: never past the free bankroll", E._fa_sized(10.0, 1.0, 1.5, 100, 10.5, 100, 100) == 10.5)
ok("sizing: never past what is left before the loss limit", E._fa_sized(10.0, 1.0, 1.5, 100, 100, 12.25, 100) == 12.25)
ok("sizing: never past the panel budget", E._fa_sized(10.0, 1.0, 1.5, 100, 100, 100, 13.0) == 13.0)
ok("sizing: never past 150% of the panel's size even when asked for more", E._fa_sized(10.0, 1.0, 9.0, 100, 100, 100, 100) == 15.0)
ok("sizing: never below the plain size (room too small to enlarge keeps the bet)", E._fa_sized(10.0, 1.0, 1.5, 5.0, 5.0, 5.0, 5.0) == 10.0)
ok("sizing with the brake: 0.5 brake x 1.2 = the brake's own $5 (a multiple never undoes the cut)", E._fa_sized(10.0, 0.5, 1.2, 100, 100, 100, 100) == 5.0)
ok("while cautious the live multiple is capped at 1.0", (learned("stake_mult", 1.3), E.ap_stake_mult(E.fa_state(), 1))[1] == 1.0
   and E.ap_stake_mult(E.fa_state(), 0) == 1.3)
ok("below 1 it stays below 1 while cautious", (learned("stake_mult", 0.7), E.ap_stake_mult(E.fa_state(), 2))[1] == 0.7)

# 11. the buy pass: a bigger size never breaks the cap, the bankroll or the panel budget
def mk(t, ev, f, p, k, lg="nba"):
    l = {"ticker": t, "event": ev, "pick": t, "p": p, "fair": f}; E.KICKOFF[ev] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(k))
    return E._cand("single", lg, [l], f, (f - p - E.single_fee(p)) / (p + E.single_fee(p)), "w", price=p)


def run_pass(vals_, cap=30.0, bank=300.0, nn=6):
    reset()
    E.store_x("delete from panel", ())
    E.PANEL_POOL = {"nba": (time.time(), [mk(f"KXNBAGAME-26NOV27G{i}-A", f"KXNBAGAME-G{i}", .60 + i / 100, .50, NOW + 9000) for i in range(nn)])}
    E.panel_pass()
    E.fa_set(True, limits={"cap": cap, "bank": bank, "max_open": 30})
    if vals_:
        E._fa_update(lambda s: s["lessons"].update(vals=vals_))
    res = E.full_auto_pass(now=time.time())
    return res, [c for c in E.panel_get("real")["items"] if c.get("state") == "scheduled"]


# several small bets at 150%: together they never pass the $20 loss room (it shrinks bet by bet, like the cap and the bankroll)
def small_pass(vals_, n=3, stake=5.0):
    reset()
    E.store_x("delete from panel", ())
    E.PANEL_POOL = {"nba": (time.time(), [mk(f"KXNBAGAME-26NOV27G{i}-A", f"KXNBAGAME-G{i}", .60 + i / 100, .50, NOW + 9000) for i in range(n)])}
    E.panel_pass()
    real = E.panel_get("real")
    def put(old, st):
        old["items"] = old["items"][:n]
        for c in old["items"]:
            c["stake"] = stake                            # equal $5 bets: $15 together, inside the $20 loss room
        return old, "draft"
    E.panel_tx(E._panel_day(real["at"]), "real", put)
    E.fa_set(True, limits={"cap": 100.0, "bank": 300.0, "max_open": 30})
    if vals_:
        E._fa_update(lambda s: s["lessons"].update(vals=vals_))
    E.full_auto_pass(now=time.time())
    return [c["stake"] for c in E.panel_get("real")["items"] if c.get("state") == "scheduled"]
sm0 = small_pass(None)
sm1 = small_pass({"stake_mult": 1.5})
ok(f"three $5 bets are bought at $5 each at today's size {sm0}", sm0 == [5.0] * 3)
ok(f"at 150% three small bets together never pass the $20 loss room {sm1}", len(sm1) >= 1 and sum(sm1) <= 18.01)
ok(f"at 150% the first two grow to $7.50 and the third gets only the $3 left of the $18 loss room {sm1}", sm1 == [7.5, 7.5, 3.0])
res, base = run_pass(None)
spend0 = sum(c["stake"] for c in base)
ok("baseline: the pass approves a draft within the $30 cap", res and 0 < spend0 <= 30.01)
res, big = run_pass({"stake_mult": 1.5})
spend1 = sum(c["stake"] for c in big)
ok("at 150% the day's spend never passes the $30 cap", res and spend1 <= 30.01)
ok("at 150% the first bet grows from $14.42 to $18.00 (the $18 loss room left, not a per-bet ceiling), never past 150% of it", big and big[0]["stake"] == 18.0 and big[0]["stake"] <= 1.5 * base[0]["stake"] + 0.01)
ok("at 150% the bet is recorded at its ACTUAL ratio (18.00 / 14.42 = 1.248, the loss room clamped it), not at 1.5", sorted(E.fa_state().get("sizes", {}).values()) == [round(18.0 / 14.42, 4)])
ok("one bet bought at $18 and the second ($13.33 normal) did not fit what was left", [c["stake"] for c in big] == [18.0])
res, small = run_pass({"stake_mult": 0.5})
ok("at 50% every bet is half size (7.21 from 14.42, never under $2) and the spend is lower", res and small[0]["stake"] == 7.21 and all(c["stake"] >= 2.0 for c in small))
res, cu = run_pass({"cap_use": 0.5}, cap=30.0)
ok("cap use 50% keeps the day's spend inside half of Pete's cap ($15), and still buys", 0 < sum(c["stake"] for c in cu) <= 15.01)
res, tight = run_pass({"stake_mult": 1.5}, cap=12.0)
ok("a bigger size never passes a tighter cap Pete set ($12)", sum(c["stake"] for c in tight) <= 12.01)
res, lowbank = run_pass({"stake_mult": 1.5}, bank=20.0)
ok("a bigger size never passes the bankroll ($20)", 0 < sum(c["stake"] for c in lowbank) <= 20.01)
E._fa_update(lambda s: s.update(fa_lessons=False))
E.store_x("delete from panel", ())
E.PANEL_POOL = {"nba": (time.time(), [mk(f"KXNBAGAME-26NOV27G{i}-A", f"KXNBAGAME-G{i}", .60 + i / 100, .50, NOW + 9000) for i in range(6)])}
E.panel_pass()
res = E.full_auto_pass(now=time.time())
off = [c for c in E.panel_get("real")["items"] if c.get("state") == "scheduled"]
ok("Autopilot off: sizes are exactly today's", res and abs(sum(c["stake"] for c in off) - spend0) < 0.01)

# 11b. the per-game limit is judged on the stake that would really be bought (the multiplied one), with exact numbers
reset()
GL = {"id": "g1", "kind": "single", "stake": 10.0, "legs": [{"ticker": NBA, "event": "KXNBAGAME-26NOV20LALBOS"}]}
GK = E.overlap_key("KXNBAGAME-26NOV20LALBOS", NBA)
E.killer_exposure = lambda now=None: {GK: {"n": 1, "risk": 20.0}}
def gl_pass(extra):
    reset(); E._fa_update(lambda s: s["lessons"].update(vals={"game_share": 0.10, **extra}))
    k, h = E.fal_filter([dict(GL)], E.fa_state(), NOW)
    return [c["id"] for c in k], [c["id"] for c in h]
ok("game limit 10% of $300 = $30: $20 open + a normal $10 bet lands exactly on $30 and is kept", gl_pass({}) == (["g1"], []))
ok("the same bet at 150% would really cost $15 ($35 on the game): held back", gl_pass({"stake_mult": 1.5}) == ([], ["g1"]))
ok("at 100% the learned multiple changes nothing", gl_pass({"stake_mult": 1.0}) == (["g1"], []))
ok("at 90% (smaller bets) the check never uses a smaller stake than the panel's own", gl_pass({"stake_mult": 0.9}) == (["g1"], []))
reset(); E._fa_update(lambda s: s["lessons"].update(vals={"game_share": 0.10, "stake_mult": 1.5})); cautious(1)
k, h = E.fal_filter([dict(GL)], E.fa_state(), NOW)
ok("recovery pass: SAVED brake level up, fresh level normal, multiple 1.5: judged at the full $15 ($20 + $15 = $35 > $30), held back, never kept at 1x",
   [c["id"] for c in k] == [] and [c["id"] for c in h] == ["g1"])
E.killer_exposure = lambda now=None: {GK: {"n": 1, "risk": 15.0}}
reset(); E._fa_update(lambda s: s["lessons"].update(vals={"game_share": 0.10, "stake_mult": 1.5})); cautious(1)
k, h = E.fal_filter([dict(GL)], E.fa_state(), NOW)
ok("recovery pass at exactly the limit: $15 open + $15 full-size = $30 is kept with the brake saved up", [c["id"] for c in k] == ["g1"] and not h)
E.killer_exposure = lambda now=None: {GK: {"n": 1, "risk": 15.01}}
k, h = E.fal_filter([dict(GL)], E.fa_state(), NOW)
ok("recovery pass one cent over: $15.01 + $15 = $30.01 is held back", not k and [c["id"] for c in h] == ["g1"])
E.killer_exposure = lambda now=None: {GK: {"n": 1, "risk": 14.0}}
reset(); E._fa_update(lambda s: s["lessons"].update(vals={"game_share": 0.10, "stake_mult": 1.5}))
two = [dict(GL, id="a"), dict(GL, id="b")]
k, h = E.fal_filter(two, E.fa_state(), NOW)
ok("running total uses the multiplied stake: $14 + $15 = $29 fits, the second ($44) is held", [c["id"] for c in k] == ["a"] and [c["id"] for c in h] == ["b"])

# 6b. rotation of the free slots for loosening is fair, tightening never starved
reset(); seed(pls=(2, -4, -4, 1)); E._fa_update(lambda s: s["lessons"].update(steps={"open": NOW - DAY, "game": NOW - DAY}))
plan = E._fal_plan(E.fa_state(), NOW)
ok("plan: tightening goes ahead past the weekly limit", [a["rec"] for a in plan["actions"] if a["do"] == "step"] == ["stake"])

# 8b. an unreadable brake record means no step at all, and never the false 'soft brake' line
for label, mod in (("a history that is not a list", {"history": "junk"}),
                   ("a caution time that is not a number", {"caution": {"level": 0, "since": float("nan")}})):
    reset(); seed(); learned("stake_mult", 0.9); E._fa_update(lambda s, m=mod: s.update(m))
    tick()
    ok("unreadable brake record (" + label + "): no loosening", vals().get("stake_mult") == 0.9)
    reset(); seed(pls=(2, -4, -4, 1)); learned("stake_mult", 1.0); E._fa_update(lambda s, m=mod: s.update(m))
    tick()
    ok("unreadable brake record (" + label + "): no tightening either, and no 'soft brake stepped in' line",
       vals().get("stake_mult") == 1.0 and not any("soft brake" in e.get("text", "") for e in lessons().get("log") or []))
reset(); E._fa_update(lambda s: s.update(history="junk"))
ok("_ap_quiet on an unreadable record: not quiet, and no time made up", E._ap_quiet(E.fa_state(), NOW) == (False, None))

# 10b. the evidence divides by the bet's ACTUAL size ratio, not the multiple in force
reset(); seed(days=3, pls=(4,), mult=1.25); E._fa_update(lambda s: s.update(sizes={k: 1.25 for k in s["sizes"]} if s.get("sizes") else {}))
rows = E._ap_real_rows(E.fa_state(), NOW, 30)
ok("each real bet carries the ratio it was actually bought at (m = 1.25)", rows and all(r["m"] == 1.25 for r in rows))
ds = E._RiskScale().ds(rows[:1], 0.9, 0.945)[0]
ok("loosening 0.9 -> 0.945 on a $4 win bought at 1.25x: 4 * 0.045 / 1.25 = 0.144 dollars, extra stake 5 * 0.045 / 1.25 = 0.18", abs(ds[1] - 0.144) < 1e-9 and abs(ds[2] - 0.18) < 1e-9)

# 12. the card
reset(); learned("stake_mult", 1.1); learned("cap_use", 0.8)
v = E.fal_view(E.fa_state())
ok("the card lists both learned numbers in plain words", any("bet size" in x["name"].lower() for x in v["learned"]) and any("cap" in x["name"].lower() for x in v["learned"]))

# 13. (#632) Pete's $20 loss room stops buying at ANY size, and shrinks bet by bet inside one pass
def loss_pass(over, stakes, mult=None):
    """One pass with fa_check's loss numbers overridden (over = dict of fields, or a callable that breaks them); returns the bought stakes."""
    reset()
    E.store_x("delete from panel", ())
    n = len(stakes)
    E.PANEL_POOL = {"nba": (time.time(), [mk(f"KXNBAGAME-26NOV27H{i}-A", f"KXNBAGAME-H{i}", .60 + i / 100, .50, NOW + 9000) for i in range(n)])}
    E.panel_pass()
    real = E.panel_get("real")
    def put(old, st):
        old["items"] = old["items"][:n]
        for c, s in zip(old["items"], stakes):
            c["stake"] = s
        return old, "draft"
    E.panel_tx(E._panel_day(real["at"]), "real", put)
    E.fa_set(True, limits={"cap": 100.0, "bank": 300.0, "max_open": 30})
    if mult:
        E._fa_update(lambda s: s["lessons"].update(vals={"stake_mult": mult}))
    real_check = E.fa_check
    def fake(*a, **k):
        v = real_check(*a, **k)
        v.update(over)
        return v
    E.fa_check = fake
    try:
        E.full_auto_pass(now=time.time())
    finally:
        E.fa_check = real_check
    return sorted(c["stake"] for c in E.panel_get("real")["items"] if c.get("state") == "scheduled")
r3 = {"day_loss": 20.0, "loss_today": 0.0, "open_stake": 15.0}           # room = $3
r0 = {"day_loss": 20.0, "loss_today": 0.0, "open_stake": 18.0}           # room = $0
ok("loss room $3: a normal-size $10 bet is trimmed to exactly $3", loss_pass(r3, [10.0]) == [3.0])
ok("loss room $3 at 150%: a $10 bet is still trimmed to exactly $3, never $15", loss_pass(r3, [10.0], mult=1.5) == [3.0])
ok("loss room $0: a normal-size $10 bet is not bought", loss_pass(r0, [10.0]) == [])
ok("loss room $0 at 150%: nothing is bought", loss_pass(r0, [10.0, 5.0], mult=1.5) == [])
ok("loss room $1.99 (under the $2 minimum): nothing is bought", loss_pass({"day_loss": 20.0, "loss_today": 0.0, "open_stake": 16.01}, [10.0]) == [])
ok("room $18 (the $20 limit less the 10% cushion), three normal $10 bets: $10, $8 then nothing ($18 total, not $30)", loss_pass({"day_loss": 20.0, "loss_today": 0.0, "open_stake": 0.0}, [10.0, 10.0, 10.0]) == [8.0, 10.0])
ok("room $15, normal $10 bets: $10 then the last $5 (the room shrinks bet by bet)", loss_pass({"day_loss": 20.0, "loss_today": 0.0, "open_stake": 3.0}, [10.0, 10.0]) == [5.0, 10.0])
ok("room $14, normal $10 bets: $10 then $4", loss_pass({"day_loss": 20.0, "loss_today": 0.0, "open_stake": 4.0}, [10.0, 10.0]) == [4.0, 10.0])
ok("room $11, normal $10 bets: $10 then $1 is under the minimum, so only one bet", loss_pass({"day_loss": 20.0, "loss_today": 0.0, "open_stake": 7.0}, [10.0, 10.0]) == [10.0])
for nm, bad in (("a missing number", {"loss_today": None}), ("not a number", {"loss_today": float("nan")}), ("text", {"open_stake": "x"}),
                ("infinite", {"day_loss": float("inf")})):
    ok(f"unreadable loss data ({nm}): nothing is bought", loss_pass(dict(r3, **bad), [10.0]) == [])
fit = E._fa_loss_fit
# (#646) a settled loss counts ONCE; the cushion is a named constant and never makes the room bigger than the exact-$20 value
lr = E._fa_loss_room
ok("#646 the cushion is a named 10% constant", E.FA_LOSS_MARGIN == 0.10)
ok("#646 example day: one settled $5 loss, nothing open: old room $10.00, exact $15.00, now $13.00", (20.0 + -5.0 - 5.0, 20.0 + -5.0 - 0.0, lr({"day_loss": 20.0, "loss_today": -5.0, "open_stake": 0.0})) == (10.0, 15.0, 13.0))
ok("#646 a settled loss is counted once: $5 loss + $4 still open = 18 - 5 - 4 = $9", lr({"day_loss": 20.0, "loss_today": -5.0, "open_stake": 4.0}) == 9.0)
ok("#646 never above the exact-$20 value (limit 20, 1.5 open, +3 won)", lr({"day_loss": 20.0, "loss_today": 3.0, "open_stake": 1.5}) == 19.5 and 19.5 <= 20.0 + 3.0 - 1.5)
ok("#646 old code blocked, new allows: settled $9.50 loss (old room $1.00, now $8.50) buys a $5 bet", loss_pass({"day_loss": 20.0, "loss_today": -9.5, "open_stake": 0.0}, [5.0]) == [5.0])
ok("#646 right at the limit still blocks: down $18, nothing open (room $0)", loss_pass({"day_loss": 20.0, "loss_today": -18.0, "open_stake": 0.0}, [5.0]) == [])
ok("#646 down $16.01 (room $1.99, under $2) still blocks", loss_pass({"day_loss": 20.0, "loss_today": -16.01, "open_stake": 0.0}, [5.0]) == [])
ok("#646 down $20 or more: room 0, never negative", lr({"day_loss": 20.0, "loss_today": -25.0, "open_stake": 0.0}) == 0.0)
ok("#646 a $10 bet with room $13 then $3 left: $10, $3 (room shrinks bet by bet, trimmed down)", loss_pass({"day_loss": 20.0, "loss_today": -5.0, "open_stake": 0.0}, [10.0, 10.0]) == [3.0, 10.0])
for nm, bad in (("missing open_stake", None), ("None", {"open_stake": None}), ("NaN", {"loss_today": float("nan")}), ("negative open", {"open_stake": -1.0})):
    v6 = {"day_loss": 20.0, "loss_today": 0.0, "open_stake": 0.0}
    if bad is None:
        del v6["open_stake"]
    else:
        v6.update(bad)
    try:
        lr(v6); bad6 = False
    except (KeyError, TypeError, ValueError):
        bad6 = True
    ok(f"#646 loss room fails closed on {nm}", bad6)
# (#646 follow-up) Pete's settled manual losses (and a settled bet with no readable P/L) shrink the room, never grow it
xl = E._fa_extra_loss
base = {"day_loss": 20.0, "loss_today": -5.0, "open_stake": 0.0}
ok("extra loss: no manual loss = identical to the #646 value ($13.00)", lr(base) == 13.0 and lr(dict(base, extra_loss=0.0)) == 13.0)
ok("extra loss: a $4 manual loss takes the room from $13.00 to $9.00", lr(dict(base, extra_loss=4.0)) == 9.0)
ok("extra loss: never below 0", lr(dict(base, extra_loss=99.0)) == 0.0)
ok("extra loss: never more than the #646 value", all(lr(dict(base, extra_loss=x)) <= lr(base) for x in (0.0, 0.01, 3.0, 50.0)))
ok("extra loss: a manual loss that leaves under $2 buys nothing", loss_pass(dict(base, extra_loss=11.5), [5.0]) == [])
for nm, bad in (("NaN", float("nan")), ("None", None), ("negative", -1.0), ("text", "x"), ("infinite", float("inf"))):
    try:
        lr(dict(base, extra_loss=bad)); b7 = False
    except (KeyError, TypeError, ValueError):
        b7 = True
    ok(f"extra loss: fails closed on {nm}", b7)
ok("extra loss helper: manual loss counts, manual win and full auto's own loss do not",
   xl([("d", {"stake": 5, "pl": -3.0, "result": "lost"}, False), ("d", {"stake": 5, "pl": 4.0, "result": "won"}, False),
       ("d", {"stake": 5, "pl": -2.0, "result": "lost"}, True)]) == 3.0)
ok("extra loss helper: a settled bet with no P/L counts as its whole stake (manual or full auto)",
   xl([("d", {"stake": 6, "result": "lost"}, False), ("d", {"stake": 2.5, "result": "lost", "pl": None}, True)]) == 8.5)
ok("extra loss helper: pl_real wins over pl; garbage numbers are safe; nothing = 0",
   xl([("d", {"stake": 5, "pl": 1.0, "pl_real": -2.0, "result": "lost"}, False)]) == 2.0 and xl([]) == 0.0
   and xl([("d", {"stake": "x", "pl": "y", "result": "lost"}, False)]) == 0.0
   and xl([("d", {"stake": 5, "pl": float("nan"), "result": "lost"}, True)]) == 5.0)
ok("_fa_loss_fit: fits unchanged, trims to the cent, 0 under $2 / empty / NaN", (fit(5.0, 8.0), fit(10.0, 3.456), fit(10.0, 1.99), fit(10.0, 0.0), fit(10.0, float("nan"))) == (5.0, 3.45, 0.0, 0.0, 0.0))
ok("money(): a loss reads -$3.50, a gain $3.50, big and zero unchanged", (E.money(-3.5), E.money(3.5), E.money(-12.4), E.money(12.4), E.money(0), E.money(-0.001)) == ("-$3.50", "$3.50", "-$12", "$12", "$0", "$0"))
