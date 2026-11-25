# CHECK: group=engine
# Issue #228, PR1: the knob registry (KNOBS) lists every number smart sell, the loss guards, auto-hedge and Smart Buy
# decide with, read-only. Checks: every entry is complete and inside its own bounds; for every knob the value the live
# code reads today (its `src`) equals the registry's start, and the rules without a number still hold (probed), so the
# two can't drift apart; the numbers that used to be written inline are gone from the live functions (named now, same
# values); knob_view gives, per league, exactly what smart_params / stoploss_params / sb_dial give the live code, and
# never raises or writes anything; no live decision reads the registry.
import os, time, tempfile, importlib.util, json, inspect, re
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.SB_DIAL_FILE = os.path.join(E.HERE, "sb.json"); E.SB_GATE["dial"] = None
E.DISCOUNT_FILE = os.path.join(E.HERE, "disc.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
E.CFG["knobs_live"] = False; E.KNOB_SWITCH["on"] = None   # PR1's view with self-tuning off; section 7 turns it on
now = time.time()

# ---- 1. every entry complete and consistent
names = [k["name"] for k in E.KNOBS]
ok("knob names are unique", len(names) == len(set(names)) and set(names) == set(E.KNOB_BY))
bad = []
for k in E.KNOBS:
    for f in ("name", "group", "cls", "label", "owner", "start", "unit"):
        if f not in k:
            bad.append((k["name"], "missing " + f))
    if k["cls"] not in ("tunable", "setting", "evidence", "invariant"):
        bad.append((k["name"], "cls"))
    if k["unit"] not in E.KNOB_UNITS:
        bad.append((k["name"], "unit"))
    if k["cls"] in ("tunable", "setting"):
        for f in ("min", "max", "step", "stricter", "borrow", "learned", "metric", "judge", "what"):
            if f not in k:
                bad.append((k["name"], "missing " + f))
        if k.get("stricter") not in ("up", "down", None) or k.get("borrow") not in ("own", "chain", "chain-stricter", "none"):
            bad.append((k["name"], "stricter/borrow"))
        if k["unit"] != "rule":
            lo, hi, st = k["min"], k["max"], k["step"]
            starts = [] if k["start"] is None else list(k["start"].values()) if isinstance(k["start"], dict) else [k["start"]]
            if lo is None or st is None or st <= 0 or (hi is not None and lo >= hi):
                bad.append((k["name"], "bounds"))
            elif not all(lo <= x and (hi is None or x <= hi) for x in starts):
                bad.append((k["name"], "start outside its bounds"))
            if k["start"] is None and not (k.get("on_value") is not None and lo <= k["on_value"] <= hi):
                bad.append((k["name"], "a knob that starts off says its first value"))
        if k.get("step_kind") not in ("add", "mult"):
            bad.append((k["name"], "step_kind"))
        if k["group"] not in {g for g, _ in E.KNOB_GROUPS}:
            bad.append((k["name"], "group"))
    else:
        if not k.get("why"):
            bad.append((k["name"], "an untunable knob says why"))
ok("every knob is complete, its start inside its bounds" + (f" {bad}" if bad else ""), not bad)
inv = {k["name"] for k in E.KNOBS if k["cls"] == "invariant"}
ok("the invariants Pete named are listed and untunable",
   {"pause", "can_trade", "rule8", "cap_read_age", "sl_feed_age", "in_play", "live_line_age", "fresh_quote",
    "secrets", "your_switches", "offer_life", "accept_wait", "cash_retries"} <= inv)
ok("a hedge can never be tuned into locking in a loss (min 1x cost); the loss cut's first value is the tuner's",
   E.KNOB_BY["hedge_lock_cost"]["min"] == 1.0 and E.KNOB_BY["smart_loss"]["on_value"] == 0.15
   and E.KNOB_BY["smart_lam"]["step_kind"] == "mult")
ok("the break guard is tunable (Pete: conditional break_ok, #228 PR5), not an invariant, and starts off",
   E.KNOB_BY["brk_on"]["cls"] == "tunable" and E.KNOB_BY["brk_on"]["start"] == 0 and E.KNOB_BY["brk_on"]["borrow"] == "own"
   and E.KNOB_BY["brk_move"]["start"] == 0.08 and "break_guard" not in E.KNOB_BY)
ok("Pete's caps: hedge_cap may rise to $150, auto_cap has no ceiling",
   E.KNOB_BY["hedge_cap"]["max"] == 150 and E.KNOB_BY["auto_cap"]["max"] is None
   and E.KNOB_BY["hedge_cap"]["cls"] == E.KNOB_BY["auto_cap"]["cls"] == "setting")
ok("the loss cut is never borrowed; the loss guards and Smart Buy borrow only stricter",
   E.KNOB_BY["smart_loss"]["borrow"] == "own" and E.KNOB_BY["sl_prog"]["borrow"] == "chain-stricter"
   and E.KNOB_BY["sl_drop"]["borrow"] == "chain-stricter" and E.KNOB_BY["sb_dial"]["borrow"] == "chain-stricter")
ok("PR2's evidence bar and brake are written down (Pete, 2026-11-21)",
   E.KNOB_EVIDENCE == {"band_n": 10, "gain": 0.02, "se": 2.0, "new": 20, "holdout": 0.30}
   and E.KNOB_BRAKE == {"losses": 4, "month_share": 0.05, "days": 14})

# ---- 2. drift: the live code's value == the registry's start
drift = [(k["name"], E.knob_live(k["name"]), k["start"]) for k in E.KNOBS
         if k.get("src") and E.knob_live(k["name"]) != k["start"]]
ok("every knob's live value equals its registry start" + (f" {drift}" if drift else ""), not drift)
ok("the knobs without a number are the rules and the Smart Buy dial's start",
   {k["name"] for k in E.KNOBS if not k.get("src")} == {"sl_auto", "brk_on", "sb_dial", "pause", "can_trade", "rule8",
                                                         "in_play", "fresh_quote", "secrets", "below_cost",
                                                         "your_switches"})
ok("below-cost guard (start: on): automatic sales still skip an offer under what was paid",
   'why="below what you paid"' in open("wahome/engine.py", encoding="utf-8").read())
# the settings' fallbacks in the live code are the shipped defaults too
ok("auto_cap: an unreadable value falls back to the start (5)", E.auto_cap_limit("junk") == E.KNOB_BY["auto_cap"]["start"])
eng_src = open("wahome/engine.py", encoding="utf-8").read()
falls = {k: set(re.findall(r"CFG\.get\([\"']%s[\"'], (\d+)\)" % k, eng_src)) for k in ("hedge_cap", "auto_cap")}
ok("the settings' fallbacks in the live code are their starts ($100 hedge cap, 5 sales)",
   falls == {"hedge_cap": {"100"}, "auto_cap": {"5"}} and E.KNOB_BY["hedge_cap"]["start"] == 100
   and "hedge_cap" in inspect.getsource(E.hedge_fresh))
# probes for the rules
E.leg_score = lambda l: {"state": "in", "frac": 0.3, "detail": "Half", "brk": True}
E.SCORES_BY["nba"] = {"at": now, "by": {}}
T = "KXNBAGAME-26NOV19LALBOS-LAL"
ok("break guard (start: on): no loss sale at halftime",
   E.stop_loss_leg(T, "yes", 0.7, 0.2, {"prog": 0.5, "drop": 0.2}, now) == (False, "halftime or a break"))
h = {"need": [(("yes", T), "x")], "cost": 5.0}
ok("break guard (start: on): no hedge at halftime",
   E.hedge_guard("C1", h, {"locked": 9.0}, now)[1] == "halftime or a break")
E.leg_score = lambda l: {"state": "post", "frac": 0.0, "detail": "Final", "brk": False}
ok("in play (invariant): no loss guard on a finished game", E.fresh_live_score(T, "yes", now)[1] == "game not under way")
E.leg_score = lambda l: {"state": "in", "frac": 0.3, "detail": "Q3 4:00", "brk": False}
E.SCORES_BY["nba"]["at"] = now - E.SL_FEED_AGE - 1
ok("fresh score (invariant): a score older than its limit is stale", E.fresh_live_score(T, "yes", now)[1] == "score feed stale")
ok("Smart Buy's dial starts at level 0 (skips nothing) with no results", E.sb_dial([T], now)["level"] == E.KNOB_BY["sb_dial"]["start"])
ok("the Pi's role and the unknown-outcome checks still exist",
   all(callable(getattr(E, f, None)) for f in ("can_trade", "hedge_unsure", "rfq_unsure", "order_unsure", "cap_bets")))

# ---- 3. the numbers once written inline are named (same values) in the live functions
def has_lit(fn, pats):
    s = inspect.getsource(fn)
    s = "\n".join(l.split("#")[0] for l in s.split("\n") if not l.strip().startswith(("\"", "'")))
    body = s.split('"""')[-1] if s.count('"""') >= 2 else s
    return [p for p in pats if re.search(p, body)]
lit = {"exit_policy": has_lit(E.exit_policy, [r"q >= 0\.5", r"/ 0\.95", r"/ 0\.9\b", r"0\.02 \* cost", r"1\.5 \* cost", r"1\.1 \* cost"]),
       "swing_lambda": has_lit(E.swing_lambda, [r"0\.35", r"\* 1\.3"]),
       "_replay": has_lit(E._replay, [r"0\.35"]),
       "simulate_exit": has_lit(E.simulate_exit, [r"0\.35 \*", r"\*= 1\.3", r"p_exit\"\] >= 0\.5"]),
       "hedge_beats": has_lit(E.hedge_beats, [r"0\.95", r"\+ 0\.5"]),
       "stop_loss_leg": has_lit(E.stop_loss_leg, [r">= 0\.5"]),
       "_sl_held": has_lit(E._sl_held, [r"< 0\.5"]),
       "kalshi_discount": has_lit(E.kalshi_discount, [r"0\.82", r"0\.88"]),
       "model_cushion": has_lit(E.model_cushion, [r"0\.15", r"0\.02"]),
       "smart_sell_singles": has_lit(E.smart_sell_singles, [r"> 180\b"])}
ok("no live function still writes a registry number inline" + (f" {lit}" if any(lit.values()) else ""), not any(lit.values()))

# ---- 4. no live decision reads the registry (PR1 describes it; PR2's stepper only proposes, in shadow)
eng = open("wahome/engine.py", encoding="utf-8").read()
start, end = eng.index("KNOB_UNITS = ("), eng.index("\ndef prune_drafts(")     # the registry and its shadow stepper
outside = eng[:start] + eng[end:]
uses = sorted({m.group(0) for m in re.finditer(r"\b(KNOBS|KNOB_[A-Z_]+|_?knob_\w+|knob(?=\())", outside)})
LIVE_OK = ["knob_auto_slip", "knob_exit_prm", "knob_shadow", "knob_shadow_view", "knob_smart_params", "knob_switch_on",
           "knob_view",
           # #228 PR5/PR6: the loss guards, the stop-loss's own switch, the hedge's numbers and cap (behind the switch),
           # and break_ok's watch-only episodes
           "KNOB_HAIRCUT", "KNOB_LIVE", "KNOB_PRM_ERR", "_knob_bet_chain", "_knob_err", "_knob_nums", "_knob_sale_league",
           "_knob_valid", "knob", "knob_cap", "knob_live_value", "knob_state_cached"]
LIVE_OK = sorted(LIVE_OK)
ok("outside the registry only analytics and, from PR3, smart sell's exit numbers (behind the switch) read it"
   + (f" {uses}" if uses != LIVE_OK else ""), uses == LIVE_OK)
_callers = {n: [f for f in ("take_profit_reason", "single_sell_reason", "exit_settings", "smart_params", "smart_tune")
                if n in inspect.getsource(getattr(E, f))] for n in ("knob_exit_prm", "knob_smart_params", "knob_switch_on")}
ok("#228 PR4: smart sell's own slip (auto_slip) is read only by auto_sell_now, for a combo's automatic sale",
   (lambda a: "knob_auto_slip(" in a and "CASH_SLIP" not in a.replace("AUTO_CASH_SLIP", ""))(
       eng_src[eng_src.index("\ndef auto_sell_now("):eng_src.index("\ndef ", eng_src.index("\ndef auto_sell_now(") + 5)])
   and "CASH_SLIP * agreed" in inspect.getsource(E.flex_fallback_bar) and "flex_fallback_bar(" in inspect.getsource(E._accept_with_retries))
ok("...and your own Cash out retries keep CASH_SLIP, listed as never moving by itself",
   E.KNOB_BY["cash_slip"]["cls"] == "invariant" and E.KNOB_BY["auto_slip"]["cls"] == "tunable"
   and E.AUTO_CASH_SLIP == E.CASH_SLIP == 0.97 and not E.KNOB_BY["auto_slip"].get("shared_with"))
ok("...and exactly where: the two sellers and Smart Buy's exit settings take the exit numbers, smart_params the "
   "floor/risk/loss, smart_tune only asks the switch", _callers == {
       "knob_exit_prm": ["take_profit_reason", "single_sell_reason", "exit_settings"],
       "knob_smart_params": ["smart_params"], "knob_switch_on": ["smart_params", "smart_tune"]})
wsrc_ = open("wtest/combo_watcher.py", encoding="utf-8").read() if os.path.exists("wtest/combo_watcher.py") else None
if wsrc_ is not None:
    code_ = "\n".join(l.split("#")[0] for l in wsrc_.split("\n"))          # code only, not comments
    wu = sorted({m.group(0) for m in re.finditer(r"\b(KNOBS|KNOB_[A-Z_]+|_?knob_\w+|knob(?=\())", code_)})
    ok("the watcher only runs the shadow pass (knob_pass)" + (f" {wu}" if wu != ["knob_pass"] else ""), wu == ["knob_pass"])

# ---- 5. knob_view mirrors the live resolvers league by league
TICK = {"nba": "KXNBAGAME-26NOV19LALBOS-LAL", "nhl": "KXNHLGAME-26NOV19PHIBOS-PHI", "epl": "KXEPLGAME-26NOV22ARSCHE-ARS",
        "laliga": "KXLALIGAGAME-26NOV22RMABAR-RMA", "nfl": "KXNFLGAME-26NOV22KCBUF-KC", "ncaamb": "KXNCAAMBGAME-26NOV21DUKUNC-DUK"}
MIX = ["KXNBAGAME-26NOV19LALBOS-LAL", "KXNHLGAME-26NOV19PHIBOS-PHI"]
table = {"_at": now,
         "nba": {"n": 45, "floor": 1.7, "lam": 1.15, "loss": 0.2, "sl_n": 60, "sl_prog": 0.4, "sl_drop": 0.15},   # own, looser loss guards
         "soccer": {"n": 80, "floor": 1.3, "lam": 0.85, "loss": 0.25, "sl_n": 55, "sl_prog": 0.4, "sl_drop": 0.3},  # epl borrows this
         "epl": {"n": 4, "floor": 2.0, "lam": 2.0, "loss": 0.3},                                                    # too few: unused
         "all": {"n": 300, "floor": 1.4, "lam": 1.0, "loss": None, "sl_n": 70, "sl_prog": 0.6, "sl_drop": 0.1},
         "nhl": {"n": 10, "floor": 1.9}, "nfl": {"n": 31, "floor": 1.6, "lam": 1.0, "loss": None},
         "mix": {"n": 33, "floor": 1.8, "lam": 1.3, "loss": None}}
json.dump(table, open(E.SMART_FILE, "w")); E.SMART_CACHE["at"] = 0
dial = {"all": {"n": 40, "level": 2}, "nba": {"n": 35, "level": 4}, "soccer": {"n": 31, "level": 3}, "nhl": {"n": 5, "level": 6},
        "laliga": {"n": 3, "level": 7}, "ncaamb": {"n": 30, "level": 1}}
json.dump(dial, open(E.SB_DIAL_FILE, "w")); E.SB_GATE["dial"] = None
mt = (os.path.getmtime(E.SMART_FILE), os.path.getmtime(E.SB_DIAL_FILE))
v = E.knob_view(now)
by = {k["name"]: k for k in v.get("knobs", [])}
keys = [l["key"] for l in v.get("leagues", [])]
ok("knob_view lists every knob and every league it has numbers for",
   len(by) == len(E.KNOBS) and keys[0] == "all" and {"nba", "nhl", "epl", "soccer"} <= set(keys))
mism = []
for lg, t in TICK.items():
    if lg not in keys:
        continue
    sp, sl, sb = E.smart_params([t]), E.stoploss_params([t]), E.sb_dial([t], now)
    got = {n: by[n]["values"][lg]["v"] for n in ("smart_floor", "smart_lam", "smart_loss", "sl_prog", "sl_drop", "sb_dial")}
    want = {"smart_floor": sp["floor"], "smart_lam": sp["lam"], "smart_loss": sp["loss"], "sl_prog": sl["prog"],
            "sl_drop": sl["drop"], "sb_dial": sb["level"]}
    if got != want:
        mism.append((lg, got, want))
if "mix" in keys:
    sp, sl, sb = E.smart_params(MIX), E.stoploss_params(MIX), E.sb_dial(MIX, now)
    got = {n: by[n]["values"]["mix"]["v"] for n in ("smart_floor", "smart_lam", "smart_loss", "sl_prog", "sl_drop", "sb_dial")}
    if got != {"smart_floor": sp["floor"], "smart_lam": sp["lam"], "smart_loss": sp["loss"], "sl_prog": sl["prog"],
               "sl_drop": sl["drop"], "sb_dial": sb["level"]}:
        mism.append(("mix", got))
ok("per league (and Mix), knob_view's values are exactly what the live code uses" + (f" {mism}" if mism else ""),
   not mism and {"laliga", "nfl", "ncaamb", "mix"} <= set(keys))
ok("Smart Buy's dial: laliga and epl borrow soccer's level 3, ncaamb has its own 1",
   by["sb_dial"]["values"]["laliga"]["v"] == 3 and by["sb_dial"]["values"]["laliga"]["from"] == "borrowed from Soccer"
   and by["sb_dial"]["values"]["epl"]["v"] == 3 and by["sb_dial"]["values"]["ncaamb"]["v"] == 1)
ok("epl: borrows soccer's floor, never its loss cut; the loss guards borrowed only stricter",
   by["smart_floor"]["values"]["epl"]["v"] == 1.3 and by["smart_loss"]["values"]["epl"]["v"] is None
   and by["smart_floor"]["values"]["epl"]["from"] == "borrowed from Soccer"
   and by["sl_prog"]["values"]["epl"]["v"] == 0.5 and by["sl_drop"]["values"]["epl"]["v"] == 0.3)
ok("nba: its own record, in plain words", by["smart_floor"]["values"]["nba"]["from"] == "own (45 results)"
   and by["smart_floor"]["values"]["nba"]["say"] == "1.7× what you paid" and by["sl_prog"]["values"]["nba"]["v"] == 0.4)
ok("nhl: too few results of its own, borrows everyone's (dial never under its start)",
   by["smart_floor"]["values"]["nhl"]["v"] == 1.4 and by["sb_dial"]["values"]["nhl"]["v"] == 2
   and by["sb_dial"]["values"]["nhl"]["from"] == "borrowed from Everything")
ok("Kalshi's offer before quotes: the starting point until 5 quotes, then the learned median",
   by["disc_pre"]["value"]["v"] == 0.88 and by["disc_pre"]["value"]["from"].startswith("starting point"))
json.dump({"pre": [0.9, 0.91, 0.92, 0.93, 0.94], "live": []}, open(E.DISCOUNT_FILE, "w"))
_dv = {k["name"]: k for k in E.knob_view(now)["knobs"]}
ok("...and once 5 are seen, the learned number the live code uses", _dv["disc_pre"]["value"]["v"] == E.kalshi_discount(False) == 0.92
   and _dv["disc_pre"]["value"]["from"] == "learned from your last 5 quotes")
os.remove(E.DISCOUNT_FILE)
ok("a fixed knob shows one value, 'fixed for now'", by["exit_q_min"].get("value") == {"v": 0.5, "say": "50%", "from": "fixed for now"}
   and "values" not in by["exit_q_min"])
E.CFG["auto_cap"] = E.AUTO_CAP_UNLIMITED
E.CFG["hedge_cap"] = 80
v2 = E.knob_view(now)
b2 = {k["name"]: k for k in v2["knobs"]}
ok("settings show Pete's own values (Unlimited = no limit)", b2["auto_cap"]["value"]["say"] == "no limit"
   and b2["hedge_cap"]["value"] == {"v": 80.0, "say": "$80", "from": "your setting"}
   and b2["hedge_cap"]["max_say"] == "$150" and b2["auto_cap"]["max_say"] == "no limit")
E.CFG["auto_cap"], E.CFG["hedge_cap"] = 5, 100
ok("invariants say why, and never move", all(b2[n]["why"] and b2[n]["value"]["from"] == "never moves" for n in inv))
ok("the evidence bar is shown with the stepper's numbers", v2.get("evidence") == E.KNOB_EVIDENCE and v2.get("brake") == E.KNOB_BRAKE)
ok("reading the registry writes nothing", mt == (os.path.getmtime(E.SMART_FILE), os.path.getmtime(E.SB_DIAL_FILE)))
json.dumps(v2)
ok("it is plain JSON for the page", True)
ok("plain words for each unit", (E.knob_say("share", 0.5), E.knob_say("pts", 0.2), E.knob_say("cents", 0.06),
                                 E.knob_say("secs", 180), E.knob_say("usd", 0.25), E.knob_say("x", 1.25),
                                 E.knob_say("share", None), E.knob_say("rule", True))
   == ("50%", "20 points", "6¢", "3 min", "$0.25", "1.25× what you paid", "off", "on"))

# ---- 6. never raises
open(E.SMART_FILE, "w").write('{"nba": "garbage", "nhl": [1, 2]}'); E.SMART_CACHE["at"] = 0
try:
    r = E.knob_view(now)
    ok("a damaged league entry hides only that league", isinstance(r, dict) and bool(r.get("knobs"))
   and "nba" not in [l["key"] for l in r["leagues"]])
except Exception as err:
    ok("a damaged settings file never raises: " + repr(err), False)
_real_smart_table = E.smart_table
E.smart_table = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
ok("an error inside gives an empty view, never an exception", E.knob_view(now) == {})

# ---- 7. with self-tuning on (#228 PR3), knob_view still shows exactly what the live code uses, per league
E.smart_table = _real_smart_table
E.CFG["knobs_live"] = True; E.KNOB_SWITCH["on"] = None
json.dump(table, open(E.SMART_FILE, "w")); E.SMART_CACHE["at"] = 0; E.SB_GATE["dial"] = None
E.KNOBS_FILE = os.path.join(E.HERE, "knobs.json"); E.KNOB_STATE_CACHE["d"] = None
v3 = E.knob_view(now)
b3 = {k["name"]: k for k in v3.get("knobs", [])}
mism = []
for lg, t in TICK.items():
    if lg not in [l["key"] for l in v3.get("leagues", [])]:
        continue
    sp = E.smart_params([t])
    got = {n: b3[n]["values"][lg]["v"] for n in ("smart_floor", "smart_lam", "smart_loss")}
    if got != {"smart_floor": sp["floor"], "smart_lam": sp["lam"], "smart_loss": sp["loss"]}:
        mism.append((lg, got, sp))
ok("switch on: per league, knob_view's floor/risk/loss are what smart_params gives" + (f" {mism}" if mism else ""), not mism)
ok("switch on: epl borrows soccer's numbers only stricter (#259): floor 1.5 not 1.3, risk weight 0.85, no loss cut",
   b3["smart_floor"]["values"]["epl"]["v"] == 1.5 and b3["smart_lam"]["values"]["epl"]["v"] == 0.85
   and b3["smart_loss"]["values"]["epl"]["v"] is None and E.smart_params([TICK["epl"]])["floor"] == 1.5)
ok("switch on: the exit numbers show per league (all at their start with nothing learned)",
   b3["exit_q_min"].get("values", {}).get("nba", {}).get("v") == 0.5 and b3["trail_drop"]["values"]["all"]["v"] == 0.2)
