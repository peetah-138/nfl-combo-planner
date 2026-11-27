# CHECK: group=engine
# Autopilot (#145): the exit knobs share the Autopilot card. A live knob step shows in the same log in plain words (from/to,
# why, dollars after fees); Undo takes the newest one back (restoring exactly what was there, holding it two weeks, never
# loosening while the brake is cautious, never when the knob has moved on); a freeze ("knobs" or one knob) and the master
# switch pause the live steps; an unreadable control file pauses them too; with nothing frozen the stepper moves exactly as
# before (when and how much are untouched); a week on, a step is judged again on full-auto bets (display only), and with no
# full-auto bets the all-bets evidence stands. Kalshi is fake.
import os, time, tempfile, json, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.CFG["loss_cut_default"] = False
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SB_DIAL_FILE = os.path.join(E.HERE, "sb.json"); E.SB_GATE["dial"] = None
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json"); E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.KNOBS_FILE = os.path.join(E.HERE, "knobs.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()
DAY = 86400
NBA = "KXNBAGAME-X1-LAL"


def switch(on):
    E.CFG["knobs_live"] = on
    E.save_json(E.MAIN_SAVED, {"knobs_live": on})
    E.KNOB_SWITCH["on"] = None
    E.KNOB_STATE_CACHE["d"] = None


def fresh(fa=None):
    """A clean knob record and full-auto file; fa = what to put in the full-auto file (None = no file)."""
    for f in (E.KNOBS_FILE, E._fa_path()):
        try:
            os.remove(f)
        except OSError:
            pass
    E.KNOB_STATE_CACHE["d"] = None
    if fa is not None:
        E._fa_update(lambda s: s.update(fa))
    json.dump({"nba": {"n": 45, "floor": 1.7, "lam": 1.0, "loss": None}, "_at": now}, open(E.SMART_FILE, "w"))
    E.SMART_CACHE["at"] = 0


def tune(at=now):
    E.KNOB_STATE_CACHE["d"] = None
    return E.knob_tune(at, force=True)


def nba():
    return E.knob_state()["groups"]["nba"]


def last(name):
    return {r["knob"]: r["status"] for r in nba()["last"]}.get(name)


def fa_set(**kw):
    E._fa_update(lambda s: s.update(kw))


def lessons():
    return E.fa_state().get("lessons") or {}


switch(True)
bets = [({"id": i, "stake": 5.0, "kick": now - 50 * DAY + i * DAY * 0.75, "pl": -5.0, "kind": "single",
          "legs": [{"ticker": "KXNBAGAME-X%d-LAL" % i}]}, [], []) for i in range(60)]
ROWS = {"replay": {"nba": bets, "all": bets}, "sl": {"nba": bets[:55]}, "sb": {}}
E._knob_rows = lambda now, deadline=None: ROWS
JUDGE = {"mode": "up"}


def judge(jd, rows, cur_, name, to, cache=None, **kw):
    base = [((x[0] if isinstance(x, tuple) else x).get("kick"), 0.0, 5.0) for x in rows]
    m = JUDGE["mode"]
    if name == "smart_floor" and ((m == "up" and to == 1.8) or (m == "down" and to == 1.6)):
        return [(k, (0.9 if i % 4 == 0 else 0.0), s) for i, (k, _, s) in enumerate(base)]
    return base


E.knob_judge = judge
REAL_TICKERS = E._ap_fa_tickers
E._ap_fa_tickers = lambda now: set()                 # no full-auto bets, until a test says otherwise

# ---- 1. a live step shows in the Autopilot log, in plain words
fresh()
smart_bytes = open(E.SMART_FILE, "rb").read()
cfg_before = json.dumps(E.CFG, sort_keys=True, default=str)
tune()
ok("with nothing frozen the stepper moves exactly as it did: the floor 1.7 → 1.8, once, by its own record",
   nba()["lv"] == {"smart_floor": 1.8} and last("smart_floor") == "stepped" and nba()["lstep_at"] == now
   and E.smart_params([NBA])["floor"] == 1.8)
h = nba()["hist"][-1]
ok("the history entry keeps the evidence in dollars after fees, and that the group had no value of its own",
   h["live"] and h["from"] == 1.7 and h["to"] == 1.8 and h["gain"] > 0 and h["n"] == 60 and h["prev_own"] is False)
ok("smart_tune's file and the settings are untouched", open(E.SMART_FILE, "rb").read() == smart_bytes
   and json.dumps(E.CFG, sort_keys=True, default=str) == cfg_before)
v = E.fal_view(E.fa_state())
top = v["log"][0]
ok("the card's log shows it: league, name, from → to, why, dollars after fees",
   "NBA Profit floor" in top and "1.7× what you paid → 1.8× what you paid" in top and "Why:" in top
   and "after fees" in top and "+$" in top)
ok("...and says it was judged on all bets while there are no full-auto bets to check it on", "Judged on all bets" in top)
ok("Undo names it", v["undo"] == "NBA Profit floor: 1.8× what you paid back to 1.7× what you paid")
kr = [r for r in v["recs"] if r["rec"] == "knobs"]
ok("the knobs have a record row of their own (the card's Freeze button works on it)", len(kr) == 1 and kr[0]["state"] == "on")

# ---- 2. Undo
ok("Undo works with Autopilot's switch on or off", E.fa_state().get("fa_lessons") is not False)
fa_set(brake={"kind": "streak", "at": now})
okc, msg = E.ap_undo(now)
ok("while the brake is cautious Undo can't loosen (this undo puts the floor back to the looser 1.7)",
   okc is False and "brake" in msg and nba()["lv"] == {"smart_floor": 1.8})
fa_set(brake=None)
okc, msg = E.ap_undo(now + 10)
ok("Undo puts the group back to having no value of its own (the floor 1.7 again), says so, and holds 2 weeks",
   okc and "you undid NBA Profit floor" in msg and "smart_floor" not in (nba().get("lv") or {})
   and E.smart_params([NBA])["floor"] == 1.7 and nba()["hist"][-1].get("undone") is True
   and abs(lessons()["holds"]["knob:nba:smart_floor"] - (now + 10 + E.AP_HOLD)) < 2)
ok("the undo is in the log, the card shows the hold, the entry says you undid it, and there is nothing left to undo",
   E.fal_view(E.fa_state())["log"][0].startswith("Autopilot: you undid NBA Profit floor")
   and any("You undid this." in x for x in E.fal_view(E.fa_state())["log"])
   and any(x["name"] == "NBA Profit floor" for x in E.fal_view(E.fa_state())["holds"])
   and E.fal_view(E.fa_state())["undo"] is None and E.ap_undo(now + 20)[0] is False)
tune(now + 30)
ok("after an Undo the next step waits for new bets after it (the stepper's own rule, as for any step)",
   last("smart_floor") != "stepped" and "smart_floor" not in (nba().get("lv") or {}))

# a step that moved on is not undone; the newer of knob step and setting change is "the last change"
fresh()
tune()
lv = E.knob_state()
lv["groups"]["nba"]["lv"]["smart_floor"] = 1.9
E.save_json(E.KNOBS_FILE, lv); E.KNOB_STATE_CACHE["d"] = None
okc, msg = E.ap_undo(now)
ok("a knob that has since moved is never undone", okc is False and "no longer where autopilot left it" in msg
   and nba()["lv"]["smart_floor"] == 1.9 and E.fal_view(E.fa_state())["undo"] is None)
fresh()
fa_set(lessons={"change": {"rec": "bar", "key": "bar:nba", "from": 0.0, "to": 0.5, "at": now - 1000, "kind": "step"}})
tune()
okc, msg = E.ap_undo(now + 1)
ok("a knob step newer than the last setting change is the one Undo takes (the older change stays)",
   okc and "NBA Profit floor" in msg and lessons()["change"].get("undone") is not True)

# a group that had its own value gets exactly that value back
fresh()
E.save_json(E.KNOBS_FILE, {"groups": {"nba": {"lv": {"smart_floor": 1.7}, "lat": {"smart_floor": now - 90 * DAY}, "v": {}}}, "brake": {}, "settings": {}})
E.KNOB_STATE_CACHE["d"] = None
E.SMART_CACHE["at"] = 0
tune()
ok("a group with its own value before: the step is recorded as such", nba()["hist"][-1]["prev_own"] is True and nba()["lv"]["smart_floor"] == 1.8)
okc, msg = E.ap_undo(now + 5)
ok("...and Undo restores that value, not 'none'", okc and nba()["lv"]["smart_floor"] == 1.7 and nba()["v"]["smart_floor"] == 1.7)

# an old history entry (before this PR) is shown but cannot be undone
fresh()
E.save_json(E.KNOBS_FILE, {"groups": {"nba": {"lv": {"smart_floor": 1.8}, "lat": {}, "hist": [
    {"at": int(now - DAY), "knob": "smart_floor", "from": 1.7, "to": 1.8, "live": True,
     "why": "Profit floor: 1.7× what you paid → 1.8× what you paid. 15 of 60 recent bets would have ended differently, +$3.60 in all."}]}},
    "brake": {}, "settings": {}})
E.KNOB_STATE_CACHE["d"] = None
v = E.fal_view(E.fa_state())
ok("an older entry shows with its own why, but is not undoable (no record of what was there before)",
   any("NBA Profit floor" in x and "+$3.60" in x for x in v["log"]) and v["undo"] is None and E.ap_undo(now)[0] is False)

# ---- 3. freeze, the master switch, a hold, unreadable controls
fresh()
okf, msg = E.ap_freeze("knob:smart_floor", True)
ok("freeze one knob (or all: 'knobs'); a made-up key is refused", okf and "frozen" in msg and "Profit floor" in msg
   and E.ap_freeze("knobs", False)[0] and E.ap_freeze("knob:nope", True)[0] is False
   and E.ap_freeze("knob:nba:smart_floor", True)[0] is False and E.ap_freeze("bar", False)[0])
tune()
ok("a frozen knob takes no step", last("smart_floor") == "frozen" and "smart_floor" not in (nba().get("lv") or {})
   and E.smart_params([NBA])["floor"] == 1.7)
E.ap_freeze("knob:smart_floor", False)
E.ap_freeze("knobs", True)
tune(now + 1)
ok("freezing the whole record stops every live exit knob (the other qualifying one too)",
   last("smart_floor") == "frozen" and last("trail_drop") == "frozen" and not (nba().get("lv") or {}))
E.ap_freeze("knobs", False)
tune(now + 2)
ok("unfrozen, the stepper moves again", last("smart_floor") == "stepped")

fresh(dict(fa_lessons=False))
tune()
ok("the master Autopilot switch off pauses the live steps", last("smart_floor") == "paused" and not (nba().get("lv") or {}))
fa_set(fa_lessons=True)
tune(now + 1)
ok("...and on again they step", last("smart_floor") == "stepped")
fresh(dict(on=False))
tune()
ok("full auto itself being off doesn't stop them (they serve manual smart sell too)", last("smart_floor") == "stepped")

JUDGE["mode"] = "down"
fresh()
ok("the step that lowers the floor is a loosening one", E.knob_loosens("smart_floor", 1.7, 1.6) is True)
tune()
ok("with no hold a loosening step the evidence supports goes through", nba()["lv"] == {"smart_floor": 1.6})
fresh(dict(lessons={"holds": {"knob:nba:smart_floor": round(now + DAY)}}))
tune()
ok("a hold (after Undo) stops a loosening step", last("smart_floor") == "held" and not (nba().get("lv") or {}))
fresh(dict(lessons={"holds": {"knob:nba:smart_floor": round(now - DAY)}}))
tune()
ok("...only until it ends", nba()["lv"] == {"smart_floor": 1.6})
fresh(dict(lessons={"holds": {"knob:nba:smart_floor": "garbage"}}))
tune()
ok("a malformed hold counts as held", last("smart_floor") == "held" and not (nba().get("lv") or {}))
JUDGE["mode"] = "up"

for label, junk in (("the file isn't a dict", "[1, 2]"), ("lessons isn't a dict", '{"on": true, "lessons": "x"}'),
                    ("frozen isn't a dict", '{"lessons": {"frozen": ["knobs"]}}')):
    fresh()
    open(E._fa_path(), "w").write(junk)
    tune()
    ok(f"fail closed: {label} = the live steps pause", last("smart_floor") == "paused" and not (nba().get("lv") or {}))
fresh()
ok("a missing control file is a normal start (not paused)", E.ap_knob_ctl(now)["paused"] is False)
tune()
ok("...and steps", last("smart_floor") == "stepped")

# ---- 4. a week on: judged again on full-auto bets (display only)
later = [({"id": 100 + i, "stake": 5.0, "kick": now + 60 + i * 3600, "pl": -5.0, "kind": "single",
           "legs": [{"ticker": "KXNBAGAME-Y%d-LAL" % i}]}, [], []) for i in range(40)]
fresh()
tune()
ROWS["replay"]["nba"] = bets + later
E._ap_fa_tickers = lambda now: set()
tune(now + 8 * DAY)
ok("no full-auto bets: no review, the all-bets evidence stands, and the step itself is untouched",
   "fa" not in nba()["hist"][0] and nba()["lv"] == {"smart_floor": 1.8}
   and "Judged on all bets" in E.fal_view(E.fa_state())["log"][0])
E._ap_fa_tickers = lambda now: None
tune(now + 9 * DAY)
ok("unreadable full-auto bets: no review either", "fa" not in nba()["hist"][0])
E._ap_fa_tickers = lambda now: {"KXNBAGAME-Y%d-LAL" % i for i in range(3)}
tune(now + 10 * DAY)
ok("fewer than 5 full-auto bets since: no review", "fa" not in nba()["hist"][0])
E._ap_fa_tickers = lambda now: {"KXNBAGAME-Y%d-LAL" % i for i in range(40)}
before = json.dumps({k: nba()[k] for k in ("lv", "lstep_at")})
tune(now + 11 * DAY)
fa = nba()["hist"][0].get("fa")
ok("full-auto bets since the step: it is judged on them, the same replay, +$9.00 on 40 bets",
   fa and fa["n"] == 40 and fa["net"] == 9.0)
ok("...which moves nothing (display only)", json.dumps({k: nba()[k] for k in ("lv", "lstep_at")}) == before)
ok("...and the card says so", "On 40 full-auto bets since: +$9.00 after fees." in E.fal_view(E.fa_state())["log"][0])

# which bets count as full auto: the ones it placed and what was swapped in for them, by their panel ticker
real_rows = E._fa_rows
E._fa_rows = lambda now: [("d", {"id": 1, "kind": "single", "legs": [{"ticker": "A"}]}),
                          ("d", {"id": 2, "kind": "single", "legs": [{"ticker": "B"}], "swap_of": 1}),
                          ("d", {"id": 3, "kind": "single", "legs": [{"ticker": "C"}]}),
                          ("d", {"id": 4, "kind": "combo", "market": "M", "legs": [{"ticker": "Z"}], "swap_of": 2})]
fresh(dict(bets={"d|1": {}}))
E._ap_fa_tickers = REAL_TICKERS
ok("full-auto bets = Pete's list plus swap chains (C is a manual bet)", E._ap_fa_tickers(now) == {"A", "B", "M"})


def boom(now):
    raise OSError("x")


E._fa_rows = boom
ok("unreadable panel rows = None, never a guess", E._ap_fa_tickers(now) is None)
E._fa_rows = real_rows
ok("the knob names in freeze/hold keys read in plain words", E.ap_knob_name("knobs") == "smart sell's numbers"
   and E.ap_knob_name("knob:nba:smart_floor") == "NBA Profit floor" and E.ap_knob_name("bar:nba") is None)
