# CHECK: group=engine
# Autopilot "Drift since start" and "Back to start" (#145, plan section 5): every setting autopilot moved shows start -> now in one
# plain line; a reset puts one setting (or all) back to its start, holds it two weeks like Undo and is logged; it never loosens
# while the soft brake is cautious (or, for bet size and cap use, before a quiet fortnight), never touches Pete's own limits,
# leaves frozen settings alone under Reset all, works with Autopilot off, and changes nothing on unreadable state.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.KNOBS_FILE = os.path.join(E.HERE, "knobs.json"); E.KNOB_STATE_CACHE["d"] = None
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
NOW = time.time()
DAY = 86400
LIMITS = ("cap", "max_open", "streak", "day_loss")


def fresh(vals=None, **top):
    for f in (E._fa_path(), E.KNOBS_FILE):
        try:
            os.remove(f)
        except OSError:
            pass
    E.KNOB_STATE_CACHE["d"] = None
    base = {"on": True, "gate": "passed", "lessons": {"vals": dict(vals or {}), "cq": {"first": round(NOW - 40 * DAY), "last": 0}}}
    base.update(top)
    E._fa_update(lambda s: s.update(base))


def L():
    return E.fa_state().get("lessons") or {}


def lines():
    return [x["line"] for x in E.ap_drift_view(E.fa_state(), NOW)["items"]]


ALL = {"bar:nba": 1.5, "sbev:nba": 2, "game_share": 0.2, "share:nba": 0.8, "stake_mult": 0.9, "cap_use": 0.8}
fresh(ALL)
ok("the drift lines are exact and plain",
   lines() == ["Per-game limit: 30% of bankroll → 20% of bankroll, tighter",
               "Share of the day's cap: 100% → 80%, tighter".replace("Share of the day's cap", "NBA budget share"),
               "Bet size: 100% → 90%, tighter",
               "Share of the daily cap it uses: 100% → 80%, tighter",
               "NBA combo bar: +0 points → +1.5 points, tighter",
               "NBA Smart Buy bar: no extra bar → $-0.10 expected on $5, tighter"] or print(lines()))
v = E.full_auto_view()["lessons"]
ok("the card carries the drift, grouped, with every item resettable and nothing looser", v["drift"]["err"] is None
   and [x["group"] for x in v["drift"]["items"]] == ["spend"] * 4 + ["picky"] * 2 and v["drift"]["all_n"] == 6)
fresh({})
ok("nothing moved: no drift", E.ap_drift_view(E.fa_state(), NOW)["items"] == [])

# a single reset (calm brake, quiet fortnight): restores the start, holds two weeks, logs, outer limits untouched
fresh(ALL)
before = {k: E.fa_state()[k] for k in LIMITS}
okc, msg = E.ap_reset("bar:nba", NOW)
ok("reset one: done, says what moved", okc is True and "NBA combo bar" in msg and "+1.5 points" in msg and "+0 points" in msg and "2 weeks" in msg)
ok("...the saved value is gone (= start), the others are untouched", "bar:nba" not in L()["vals"] and L()["vals"]["stake_mult"] == 0.9
   and len(L()["vals"]) == 5)
ok("...it is held for 14 days and bets before now do not count toward its next step",
   abs(L()["holds"]["bar:nba"] - (round(NOW) + 14 * DAY)) <= 1 and L()["since"]["bar:nba"] == round(NOW))
ok("...it is logged", L()["log"][-1]["kind"] == "reset" and L()["log"][-1]["key"] == "bar:nba" and "put NBA combo bar back to its start" in L()["log"][-1]["text"])
ok("...Pete's own limits never moved", {k: E.fa_state()[k] for k in LIMITS} == before)
okc, msg = E.ap_reset("bar:nba", NOW)
ok("resetting what is already at start does nothing", okc is False and "already at its start" in msg)

# the held setting cannot be loosened again by autopilot (a hold blocks loosening only)
ok("the hold is the shared one", E._ap_held(L(), "bar:nba", NOW + DAY) and not E._ap_held(L(), "bar:nba", NOW + 15 * DAY))

# cautious soft brake: a reset that would loosen is refused, the setting stays put, the card says why
fresh(ALL, caution={"level": 1, "base_at": 0, "since": round(NOW - 1000), "why": "x"})
okc, msg = E.ap_reset("bar:nba", NOW)
ok("cautious: no loosening, nothing saved", okc is False and L()["vals"] == ALL and "careful" in msg and "stays at +1.5 points" in msg
   and "holds" not in L() or L().get("holds") == {})
d = E.ap_drift_view(E.fa_state(), NOW)
ok("cautious: the card says why in words and offers no Reset all", d["cautious"] is True and d["can_reset"] is False
   and all(x["reset_ok"] is False and "careful" in x["why_not"] for x in d["items"]))
okc, msg = E.ap_reset("all", NOW)
ok("cautious: Reset all changes nothing", okc is False and L()["vals"] == ALL)
# ... but a setting that is LOOSER than start may always be brought back in toward start
fresh({"stake_mult": 1.2, "bar:nba": 1.0}, caution={"level": 2, "base_at": 0, "since": round(NOW - 1000), "why": "x"})
okc, msg = E.ap_reset("stake_mult", NOW)
ok("cautious: tightening back to start is allowed", okc is True and "stake_mult" not in L()["vals"] and L()["vals"] == {"bar:nba": 1.0})
okc, msg = E.ap_reset("all", NOW)
ok("cautious: Reset all does the safe ones only (here none left)", okc is False and L()["vals"] == {"bar:nba": 1.0})

# bet size and cap use also need a quiet fortnight
fresh(ALL)
E._fa_update(lambda s: s["lessons"].update(cq={"first": round(NOW - 3 * DAY), "last": 0}))
okc, msg = E.ap_reset("stake_mult", NOW)
ok("not quiet yet: bet size stays and says why", okc is False and L()["vals"]["stake_mult"] == 0.9 and "two weeks" in msg)
okc, msg = E.ap_reset("all", NOW)
ok("not quiet yet: Reset all moves the others, keeps bet size and cap use",
   okc is True and set(L()["vals"]) == {"stake_mult", "cap_use"} and "Bet size stays at 90%" in msg and "cap it uses stays at 80%" in msg)

# a recent brake in the history is also not quiet
fresh(ALL)
E._fa_update(lambda s: s.update(history=[{"at": round(NOW - 2 * DAY), "ev": "brake"}]))
okc, msg = E.ap_reset("cap_use", NOW)
ok("a brake two days ago: cap use stays", okc is False and L()["vals"]["cap_use"] == 0.8)

# Reset all with a frozen setting
fresh(ALL)
E.ap_freeze("bar", True)
E.ap_freeze("stake_mult", True)
okc, msg = E.ap_reset("all", NOW)
ok("Reset all leaves frozen settings alone and names them", okc is True and set(L()["vals"]) == {"bar:nba", "stake_mult"}
   and "froze" in msg and "NBA combo bar" in msg and "Bet size" in msg and L()["frozen"] == {"bar": True, "stake_mult": True})
okc, msg = E.ap_reset("bar:nba", NOW)
ok("a tap on one frozen setting is Pete's own call: it resets and stays frozen", okc is True and "bar:nba" not in L()["vals"] and L()["frozen"]["bar"] is True)
v = E.ap_drift_view(E.fa_state(), NOW)
ok("the card marks the frozen one and Reset all counts only what would move", [x["frozen"] for x in v["items"]] == [True] and v["all_n"] == 0)
fresh(ALL)
for k in ("bar", "sbev", "game", "share", "stake_mult", "cap_use"):
    E.ap_freeze(k, True)
okc, msg = E.ap_reset("all", NOW)
ok("everything frozen: nothing changes", okc is False and L()["vals"] == ALL and "froze" in msg)

# master switch off (fa_lessons False) and full auto off: resets still work, with the same gates
fresh(ALL, fa_lessons=False)
okc, msg = E.ap_reset("all", NOW)
ok("master off: Reset all works", okc is True and L()["vals"] == {} and E.fa_state()["fa_lessons"] is False)
fresh(ALL, fa_lessons=False, caution={"level": 1})
ok("master off while cautious: still refused", E.ap_reset("bar:nba", NOW)[0] is False and L()["vals"] == ALL)

# Undo cannot re-apply over a reset
fresh({"bar:nba": 0.5}, lessons={"vals": {"bar:nba": 0.5}, "cq": {"first": round(NOW - 40 * DAY), "last": 0},
                                  "change": {"rec": "bar", "key": "bar:nba", "from": 0.0, "to": 0.5, "at": round(NOW - 100), "kind": "step"}})
E.ap_reset("bar:nba", NOW)
okc, msg = E.ap_undo(NOW)
ok("Undo after a reset does nothing", okc is False and "bar:nba" not in L()["vals"])

# unreadable state fails closed and never writes over it
for name, raw in (("garbage file", b"{not json"), ("lessons not a record", b'{"on": true, "lessons": 5}'),
                  ("caution damaged", b'{"on": true, "lessons": {"vals": {"bar:nba": 1.5}}, "caution": "x"}'),
                  ("brake damaged", b'{"on": true, "lessons": {"vals": {"bar:nba": 1.5}}, "brake": []}'),
                  ("bad value", b'{"on": true, "lessons": {"vals": {"bar:nba": "high"}}}'),
                  ("unknown key", b'{"on": true, "lessons": {"vals": {"zzz": 1}}}')):
    fresh({})
    open(E._fa_path(), "wb").write(raw)
    okc, msg = E.ap_reset("all", NOW)
    okc2, _ = E.ap_reset("bar:nba", NOW)
    view = E.ap_drift_view(E.fa_state(), NOW)
    ok(f"unreadable ({name}): refused, file byte-for-byte unchanged, no buttons", okc is False and okc2 is False
       and open(E._fa_path(), "rb").read() == raw and view["can_reset"] is False)

# the act endpoint checks everything itself
fresh(ALL)
for name, d in (("no confirm", {"key": "bar:nba"}), ("confirm not true", {"key": "bar:nba", "confirm": "yes"}),
                ("no key", {"confirm": True}), ("key not text", {"key": 5, "confirm": True}),
                ("huge key", {"key": "bar:" + "x" * 500, "confirm": True}), ("not a record", None)):
    okc, msg = E.ap_reset_act(d)
    ok(f"act refuses: {name}", okc is False and L()["vals"] == ALL)
for key in ("bankroll", "cap", "day_loss", "max_open", "pause", "streak", "knob:nba", "knob:nba:nope", "knob::smart_floor", "bar", ""):
    okc, msg = E.ap_reset_act({"key": key, "confirm": True})
    ok(f"act refuses a key that is not one of autopilot's settings: {key!r}", okc is False and L()["vals"] == ALL
       and {k: E.fa_state()[k] for k in LIMITS} == before)
okc, msg = E.ap_reset_act({"key": "bar:nba", "confirm": True})
ok("act: a confirmed known key goes through", okc is True and "bar:nba" not in L()["vals"])

# the open-bet limit goes back to Pete's own number, not a fixed one
fresh({"open_slots": 10}, max_open=14)
ok("open-bet drift is measured from Pete's own number", lines() == ["Open-bet limit: 14 open bets → 10 open bets, tighter"])
okc, msg = E.ap_reset("open_slots", NOW)
ok("open-bet reset removes the saved value and leaves Pete's number", okc is True and "open_slots" not in L()["vals"] and E.fa_state()["max_open"] == 14)

# exit knobs (smart sell): a group's own value is taken away, back to the start; same gates
k = E.KNOB_BY["smart_floor"]
cur = k["start"] + 0.2
tighter = not E.knob_loosens("smart_floor", k["start"], cur)
def knobfile(extra=None):
    d = {"groups": {"nba": {"v": {"smart_floor": cur}, "lv": {"smart_floor": cur}, "lat": {"smart_floor": NOW - DAY}, "hist": [
        {"at": int(NOW - DAY), "knob": "smart_floor", "from": k["start"], "to": cur, "live": True, "prev_own": False}]}}}
    d.update(extra or {})
    E.save_json(E.KNOBS_FILE, d); E.KNOB_STATE_CACHE["d"] = None
fresh(ALL)
knobfile()
items = E.ap_drift_view(E.fa_state(), NOW)["items"]
kit = [x for x in items if x["rec"] == "knob"]
ok("a smart sell step shows up in its own group", len(kit) == 1 and kit[0]["key"] == "knob:nba:smart_floor" and kit[0]["group"] == "sell"
   and kit[0]["line"].startswith("NBA ") and E.knob_say(k["unit"], k["start"]) in kit[0]["line"] and kit[0]["dir"] == ("tighter" if tighter else "looser"))
okc, msg = E.ap_reset("knob:nba:smart_floor", NOW)
kst = E.knob_state()["groups"]["nba"]
ok("knob reset: its own value is gone, the start is in force, held two weeks, logged",
   okc is True and "smart_floor" not in kst["lv"] and kst["v"]["smart_floor"] == k["start"] and kst["hist"][-1].get("reset") is True
   and L()["holds"]["knob:nba:smart_floor"] >= round(NOW + 13 * DAY) and L()["log"][-1]["key"] == "knobs")
fresh(ALL, caution={"level": 1})
knobfile()
okc, msg = E.ap_reset("knob:nba:smart_floor", NOW)
ok("knob reset while cautious: " + ("allowed (tightening)" if not tighter else "refused (it would loosen)"),
   okc is (not tighter))
if tighter:
    ok("...the knob is exactly where it was", E.knob_state()["groups"]["nba"]["lv"]["smart_floor"] == cur)
fresh(ALL)
open(E.KNOBS_FILE, "w").write("{broken")
raw = open(E.KNOBS_FILE, "rb").read()
okc, msg = E.ap_reset("all", NOW)
ok("unreadable knob file: refused and left alone", okc is False and open(E.KNOBS_FILE, "rb").read() == raw and L()["vals"] == ALL)

# the monthly line: once per calendar month, in the log
def run(now):
    E._fa_update(lambda s: E._fal_apply(s, {"actions": [], "status": {}}, now))
fresh(ALL)
run(NOW)
n1 = [x for x in L()["log"] if x["kind"] == "drift"]
run(NOW + 3600)
n2 = [x for x in L()["log"] if x["kind"] == "drift"]
ok("one summary line in the month, exact", len(n1) == 1 and len(n2) == 1 and n1[0]["text"].startswith(
   "Autopilot, month in review: 6 settings are away from where you started. Per-game limit: 30% of bankroll → 20% of bankroll, tighter;")
   and n1[0]["text"].endswith("Tap Back to start on the card to put one or all of them back."))
run(NOW + 40 * DAY)
ok("...and another a month later", len([x for x in L()["log"] if x["kind"] == "drift"]) == 2)
