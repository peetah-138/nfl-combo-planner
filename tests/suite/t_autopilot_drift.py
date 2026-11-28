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
   lines() == ["Per-game limit: from 30% of bankroll to 20% of bankroll, tighter",
               "Share of the day's cap: from 100% to 80%, tighter".replace("Share of the day's cap", "NBA budget share"),
               "Bet size: from 100% to 90%, tighter",
               "Share of the daily cap it uses: from 100% to 80%, tighter",
               "NBA combo bar: from +0 points to +1.5 points, tighter",
               "NBA Smart Buy bar: from no extra bar to $-0.10 expected on $5, tighter"] or print(lines()))
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
ok("open-bet drift is measured from Pete's own number", lines() == ["Open-bet limit: from 14 open bets to 10 open bets, tighter"])
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
ok("knob reset: its own value is pinned to the start, held two weeks, logged",
   okc is True and kst["lv"]["smart_floor"] == k["start"] and kst["v"]["smart_floor"] == k["start"] and kst["hist"][-1].get("reset") is True
   and L()["holds"]["knob:nba:smart_floor"] >= round(NOW + 13 * DAY) and L()["log"][-1]["key"] == "knobs")
# a FILLED smart.json: smart_tune's own number must not show through after a reset (it may be looser than the start)
fld = E.KNOB_SMART_FIELD["smart_floor"]
E.SMART_FILE = os.path.join(E.HERE, "combo_smart.json")
E.save_json(E.SMART_FILE, {"nba": {"n": E.SMART_MIN_N + 5, "at": NOW - 3600, fld: k["start"] - 0.3}})
fresh(ALL)
knobfile()
okc, msg = E.ap_reset("knob:nba:smart_floor", NOW)
has, val = E._knob_own_live("smart_floor", "nba", E.knob_state(), E.load_json(E.SMART_FILE, {}))
ok("knob reset with a filled smart.json: the effective floor is exactly the start, not smart_tune's",
   okc is True and has and val == k["start"] and E.knob_state()["groups"]["nba"]["lv"]["smart_floor"] == k["start"])
os.remove(E.SMART_FILE)
# the value IN FORCE (smart_tune's newer number can win over a stale `lv`) is what the card shows and what the gate judges
SMARTF = {"smart_floor": ("floor", "n", "at"), "smart_lam": ("lam", "n", "at"), "sl_prog": ("prog", "sl_n", "sl_at"), "sl_drop": ("drop", "sl_n", "sl_at")}
def smart_row(name, val):
    f, nk, ak = SMARTF[name]
    row = {nk: 500, ak: int(NOW - 3600), f: val}
    if name in ("sl_prog", "sl_drop"):
        row.update(sl_prog=E.SL_DEFAULT["prog"], sl_drop=E.SL_DEFAULT["drop"]); row["sl_" + f] = val
    return {"nba": row}
def pick(name):
    kk = E.KNOB_BY[name]; st0 = kk["start"]
    cs = [round(st0 * f, 4) for f in (0.5, 0.7, 0.9, 1.1, 1.3, 1.6) if E._knob_valid(name, round(st0 * f, 4)) and round(st0 * f, 4) != st0]
    tight = [c for c in cs if not E.knob_loosens(name, st0, c)]; loose = [c for c in cs if E.knob_loosens(name, st0, c)]
    return tight[0], loose[0]
for name in SMARTF:
    kk = E.KNOB_BY[name]; tight, loose = pick(name)
    for stale, inforce in ((tight, loose), (loose, tight)):
        E.save_json(E.SMART_FILE, smart_row(name, inforce))
        fresh(ALL, caution={"level": 1})
        E.save_json(E.KNOBS_FILE, {"groups": {"nba": {"v": {name: stale}, "lv": {name: stale}, "lat": {name: NOW - DAY}}}}); E.KNOB_STATE_CACHE["d"] = None
        it = [x for x in E.ap_drift_view(E.fa_state(), NOW)["items"] if x["key"] == f"knob:nba:{name}"]
        okc, msg = E.ap_reset(f"knob:nba:{name}", NOW)
        tag = f"{name}, stale {'tighter' if stale == tight else 'looser'} number, smart_tune's newer one {'looser' if inforce == loose else 'tighter'}"
        ok(tag + ": the card shows the in-force number",
           len(it) == 1 and it[0]["cur"] == inforce and E.knob_say(kk["unit"], inforce) in it[0]["line"] and it[0]["dir"] == ("looser" if inforce == loose else "tighter"))
        would_loosen = E.knob_loosens(name, inforce, kk["start"])
        ok(tag + ": at caution 1 a loosening reset is refused, a tightening one goes through", okc is (not would_loosen))
        if would_loosen:
            ok(tag + ": ...and nothing was written", E.knob_state()["groups"]["nba"]["lv"][name] == stale)
        else:
            ok(tag + ": ...the floor in force is exactly the start",
               E._knob_own_live(name, "nba", E.knob_state(), E.load_json(E.SMART_FILE, {})) == (True, kk["start"]))
os.remove(E.SMART_FILE)
# an unreadable smart.json: refused, nothing changed
fresh(ALL, caution={"level": 1}); knobfile()
open(E.SMART_FILE, "w").write("{broken")
okc, msg = E.ap_reset("knob:nba:smart_floor", NOW)
ok("unreadable smart.json: refused", okc is False and E.knob_state()["groups"]["nba"]["lv"]["smart_floor"] == cur)
os.remove(E.SMART_FILE)
# a damaged frozen list is not silently cleared
fresh(ALL)
E._fa_update(lambda s: s["lessons"].__setitem__("frozen", ["bar:nba"]))
okc, msg = E.ap_reset("all", NOW)
ok("damaged frozen list: nothing changed", okc is False and L()["vals"] == ALL and L()["frozen"] == ["bar:nba"])
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
   "Autopilot, month in review: 6 settings are away from where you started. Per-game limit: from 30% of bankroll to 20% of bankroll, tighter;")
   and n1[0]["text"].endswith("Tap Back to start on the card to put one or all of them back."))
run(NOW + 40 * DAY)
ok("...and another a month later", len([x for x in L()["log"] if x["kind"] == "drift"]) == 2)

# ---- #665 hardening (tighten-only) and #664 wording
print("# --- #665")
loose = pick("smart_floor")[1]
def knobfile2(val, brake=None):
    d = {"groups": {"nba": {"v": {"smart_floor": val}, "lv": {"smart_floor": val}, "lat": {"smart_floor": NOW - DAY}, "hist": [
        {"at": int(NOW - DAY), "knob": "smart_floor", "from": k["start"], "to": val, "live": True, "prev_own": False}]}}}
    if brake:
        d["brake"] = {"nba": {"at": NOW - 100, "until": NOW + DAY, "why": "x", "mode": "live"}}
    E.save_json(E.KNOBS_FILE, d); E.KNOB_STATE_CACHE["d"] = None
KB_WHY = "Smart sell's own brake is on for a league, so nothing is loosened right now. Try again once it has ended."
# the exit number is looser than its start (a reset would tighten it): allowed under smart sell's brake
tight_v = pick("smart_floor")[0]
fresh(ALL); knobfile2(loose, brake=True)
it = [x for x in E.ap_drift_view(E.fa_state(), NOW)["items"] if x["rec"] == "knob"]
ok("exit knob already looser than start: the reset (a tightening) is still allowed under the knob brake",
   len(it) == 1 and it[0]["loosens"] is False and it[0]["reset_ok"] is True)
fresh(ALL); knobfile2(tight_v, brake=True)
it = [x for x in E.ap_drift_view(E.fa_state(), NOW)["items"] if x["rec"] == "knob"]
ok("exit knob tighter than start: a reset would loosen, so the knob brake refuses it, with the exact reason",
   len(it) == 1 and it[0]["loosens"] is True and it[0]["reset_ok"] is False and it[0]["why_not"] == KB_WHY)
okc, msg = E.ap_reset("knob:nba:smart_floor", NOW)
ok("...ap_reset changes nothing and says why", okc is False and KB_WHY in msg and E.knob_state()["groups"]["nba"]["lv"]["smart_floor"] == tight_v
   and "holds" not in L() or L().get("holds") == {})
okc, msg = E.ap_reset("all", NOW)
ok("...Reset all leaves the loosening knob alone", E.knob_state()["groups"]["nba"]["lv"]["smart_floor"] == tight_v)
fresh(ALL); knobfile2(tight_v)
okc, msg = E.ap_reset("knob:nba:smart_floor", NOW)
ok("same loosening reset with no knob brake: allowed (control)", okc is True and E.knob_state()["groups"]["nba"]["lv"]["smart_floor"] == k["start"])
# the brake begins between the look and the write: the knob file's own check refuses
fresh(ALL); knobfile2(tight_v)
orig_items = E.ap_drift_items
def late_brake(st, now=None, kst=None):
    r = orig_items(st, now, kst); knobfile2(tight_v, brake=True); return r
E.ap_drift_items = late_brake
okc, msg = E.ap_reset("knob:nba:smart_floor", NOW)
E.ap_drift_items = orig_items
ok("a knob brake that starts after the look still stops the loosening", okc is False and KB_WHY in msg
   and E.knob_state()["groups"]["nba"]["lv"]["smart_floor"] == tight_v)
# an unreadable knob brake state counts as braked (fail closed)
fresh(ALL)
ok("unreadable knob state counts as braked", E._ap_knob_braked(None, NOW) is False and E._ap_knob_braked({"brake": 5}, NOW) is True)
# note(): the saved file is re-read before the hold is written; unreadable = no hold, said in words
fresh(ALL); knobfile2(tight_v)
orig_raw, orig_ks, flag = E._ap_raw_fa, E._knob_save, {"saved": False}
def ks(fn):
    r = orig_ks(fn); flag["saved"] = True; return r
E._knob_save = ks
E._ap_raw_fa = lambda: ((None, "the saved full-auto file can't be read") if flag["saved"] else orig_raw())
okc, msg = E.ap_reset("knob:nba:smart_floor", NOW)
E._ap_raw_fa, E._knob_save = orig_raw, orig_ks
ok("hold unreadable after the knob write: no hold or log line written, and the card message says so",
   "knob:nba:smart_floor" not in (L().get("holds") or {}) and not [x for x in L().get("log", []) if x.get("key") == "knobs"]
   and "The 2-week hold and log line for the exit numbers couldn't be saved just now." in msg)
# a damaged caution level is cautious (refuses loosening) from the saved file too
fresh(ALL, caution={"level": "x"})
okc, msg = E.ap_reset("bar:nba", NOW)
ok("damaged caution level: loosening refused", okc is False and L()["vals"] == ALL)
