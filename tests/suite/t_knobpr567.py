# CHECK: group=engine
# Issue #228 PR5-PR7 (and #306). Checks: the exit knobs Pete tightened (#306) can't go below their start; with
# 'Let smart sell tune its own numbers' OFF the loss guards, the confirmation counts and the hedge numbers are exactly
# the old ones on random states (old stoploss_params copied verbatim below), and ON with nothing learned too; the
# stop-loss's own switch (sl_auto) is only ever a league's own and off while braked; borrowed loss-guard values are
# only stricter; break_ok never acts live (episodes are only recorded), its rule needs two reads a minute apart and news
# halves the move; the hedge cap is never raised past $150 and a brake gives it back; the new judges (stop-loss switch,
# break episodes, hedge decisions, Smart Buy's smallest expected profit) give the right sign, and only the loss guards
# and hedge numbers may step live (the break rule and Smart Buy stay watch-only).
import os, time, tempfile, importlib.util, json, random
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
E.KNOBS_FILE = os.path.join(E.HERE, "knobs.json"); E.MAIN_SAVED = os.path.join(E.HERE, "main.json")
E.SB_DIAL_FILE = os.path.join(E.HERE, "sb.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()


def old_stoploss_params(tickers):                      # verbatim from before this PR
    d = E.smart_table()
    k = E.bet_key(tickers)
    sport = E.ticker_sport(next(iter(tickers), "") or "") if k != "mix" else None
    for key in (k, sport, "all"):
        e = d.get(key) if key else None
        if e and e.get("sl_n", 0) >= E.SL_MIN_N and e.get("sl_prog") is not None:
            out = {"prog": float(e["sl_prog"]), "drop": float(e.get("sl_drop", E.SL_DEFAULT["drop"])), "key": key}
            if key != k:
                out.update(prog=max(out["prog"], E.SL_DEFAULT["prog"]), drop=max(out["drop"], E.SL_DEFAULT["drop"]))
            return out
    return dict(E.SL_DEFAULT, key=None)


def old_hedge_beats(hg, whole):
    if E.CFG.get("prefer_hedge", True):
        return hg["locked"] >= whole * E.HEDGE_LOCK_SHARE
    return hg["locked"] >= whole + E.HEDGE_LOCK_EXTRA


def switch(on):
    E.KNOB_SWITCH.update(at=1e18, on=on)
    E.KNOB_STATE_CACHE["d"] = None


def put_knobs(st):
    json.dump(st, open(E.KNOBS_FILE, "w"))
    E.KNOB_STATE_CACHE["d"] = None


def put_smart(d):
    json.dump(d, open(E.SMART_FILE, "w"))
    E.SMART_CACHE["at"] = 0


# ---- #306: own records may no longer loosen these below their start
K = E.KNOB_BY
ok("#306: cut_accept, exit_q_min, exit_est_smart and exit_est_tp can't go below their start",
   all(K[n]["min"] == K[n]["start"] for n in ("cut_accept", "exit_q_min", "exit_est_smart", "exit_est_tp")))
ok("#306: a step from the start only goes stricter",
   all(all(x > K[n]["start"] for x in E.knob_candidates(n, K[n]["start"])) for n in ("cut_accept", "exit_q_min", "exit_est_smart", "exit_est_tp")))
switch(True)
put_knobs({"groups": {"nba": {"lv": {"exit_q_min": 0.4, "cut_accept": 0.0, "exit_est_smart": 0.9, "exit_est_tp": 0.85},
                              "lat": {}}}})
NBA = "KXNBAGAME-26NOV21BOSNYK-BOS"
ok("#306: a value recorded below the start before this change is ignored (the start is used)", E.knob_exit_prm([NBA]) == {})
put_knobs({"groups": {"nba": {"lv": {"exit_q_min": 0.6}, "lat": {}}}})
ok("#306: ...a stricter one still counts", E.knob_exit_prm([NBA]) == {"q_min": 0.6})

# ---- random states: switch off = exactly the old numbers; on with nothing learned = the same
rng = random.Random(567)
TK = ["KXNBAGAME-26NOV21BOSNYK-BOS", "KXNHLGAME-26NOV21PHIBOS-PHI", "KXNFLGAME-26NOV22KCBUF-KC",
      "KXEPLGAME-26NOV22ARSCHE-ARS", "KXAHLGAME-26NOV191900HERCHA-HER", "KXLALIGAGAME-26NOV22RMABAR-RMA"]
LG = ("nba", "nhl", "nfl", "epl", "laliga", "soccer", "ahl", "all")
same_off = same_on = True
for i in range(400):
    sm = {}
    for k in LG:
        if rng.random() < 0.5:
            sm[k] = {"sl_n": rng.choice([10, 49, 50, 80]), "sl_prog": rng.choice([0.35, 0.45, 0.5, 0.7, 0.9]),
                     "sl_drop": rng.choice([0.1, 0.2, 0.3, 0.45]), "sl_at": now - rng.choice([0, 86400 * 9])}
    put_smart(sm)
    kn = {"groups": {k: {"lv": {n: rng.choice([K[n]["min"], K[n]["max"]]) for n in
                                ("sl_prog", "sl_drop", "sl_checks", "sl_span", "sl_gap", "hedge_lock_share",
                                 "hedge_lock_cost", "hedge_checks", "sl_auto") if rng.random() < 0.5},
                         "lat": {}} for k in LG if rng.random() < 0.5},
          "settings": {"hedge_cap": {"system": rng.choice([None, 120, 140, 400])}}}
    put_knobs(kn)
    tks = rng.sample(TK, rng.choice([1, 1, 2]))
    hg = {"locked": rng.uniform(5, 30), "cost": rng.uniform(1, 200)}
    whole = rng.uniform(5, 30)
    E.CFG.update(prefer_hedge=rng.random() < 0.7, hedge_cap=rng.choice([25, 100, 160]),
                 stop_loss=rng.random() < 0.5, stop_loss_mode=None)
    switch(False)
    a = (E.stoploss_params(tks), E.sl_confirm_params(tks), E.hedge_confirm_params(tks), E.hedge_beats(hg, whole, tks),
         E.hedge_lock_cost(tks), E.hedge_cap_now(), E.sl_allowed(tks))
    b = (old_stoploss_params(tks), (E.SL_CHECKS, E.SL_SPAN, E.SL_GAP), (3, 180, 300), old_hedge_beats(hg, whole),
         1.0, float(E.CFG["hedge_cap"]), bool(E.CFG["stop_loss"]))
    if a != b:
        same_off = False
        print("off:", a, b)
        break
    put_knobs({})
    switch(True)
    c = (E.stoploss_params(tks), E.sl_confirm_params(tks), E.hedge_confirm_params(tks), E.hedge_beats(hg, whole, tks),
         E.hedge_lock_cost(tks), E.hedge_cap_now(), E.sl_allowed(tks))
    if (c[0]["prog"], c[0]["drop"]) != (b[0]["prog"], b[0]["drop"]) or c[1:] != b[1:]:
        same_on = False
        print("on:", c, b)
        break
ok("switch OFF: loss guards, confirmation counts, hedge numbers and the stop-loss exactly as before (400 random states)", same_off)
ok("switch ON, nothing learned by self-tuning: the same numbers (smart_tune's own record included)", same_on)

# ---- borrowed values only stricter; sl_auto only a league's own
put_smart({})
switch(True)
put_knobs({"groups": {"nba": {"lv": {"sl_prog": 0.4}, "lat": {}}}})
ok("a league's own looser loss-guard value counts (on the evidence bar)", E.stoploss_params([NBA])["prog"] == 0.4)
put_knobs({"groups": {"all": {"lv": {"sl_prog": 0.4, "sl_drop": 0.35, "sl_checks": 2, "sl_gap": 120}, "lat": {}}}})
p = E.stoploss_params([NBA])
ok("borrowed: a looser value is not taken, a stricter one is", p["prog"] == 0.5 and p["drop"] == 0.35
   and E.sl_confirm_params([NBA]) == (3, 180, 120))
put_knobs({"groups": {"nba": {"lv": {"sl_prog": 0.4, "sl_checks": 2}, "lat": {}}},
           "brake": {"nba": {"at": now, "until": now + 86400, "mode": "live"}}})
ok("braked: back at the start, never looser", E.stoploss_params([NBA])["prog"] == 0.5 and E.sl_confirm_params([NBA]) == (3, 180, 300))
E.CFG.update(stop_loss=False, stop_loss_mode="tune")
put_knobs({"groups": {"basketball": {"lv": {"sl_auto": 1}, "lat": {}}, "all": {"lv": {"sl_auto": 1}, "lat": {}}}})
ok("the stop-loss's own switch is never borrowed", E.sl_allowed([NBA]) is False and E.knob_stricter("sl_auto", 1) == 0)
put_knobs({"groups": {"nba": {"lv": {"sl_auto": 1}, "lat": {}}}})
ok("...a league's own record turns it on", E.sl_allowed([NBA]) is True)
switch(False)
ok("...but only while self-tuning is on", E.sl_allowed([NBA]) is False)
switch(True)
E.CFG["stop_loss_mode"] = "never"
ok("a saved 'never' (retired) acts as 'tune': this league's own record decides, and it is never Allow",
   E.sl_mode() == "tune" and E.sl_allowed([NBA]) is True and E.sl_allowed(["KXNHLGAME-26NOV19BOSNYR-BOS"]) is False)
E.CFG["stop_loss_mode"] = "allow"
ok("Allow (guarded): on (every guard still has to hold)", E.sl_allowed([NBA]) is True)
E.CFG.update(stop_loss_mode=None, stop_loss=False)
ok("hedge confirmation is its own (split from the loss guards)",
   all(K[n].get("shared_with") is None for n in ("sl_checks", "sl_span", "sl_gap"))
   and {"hedge_checks", "hedge_span", "hedge_cgap"} <= set(K))
put_knobs({"groups": {"nba": {"lv": {"sl_checks": 5}, "lat": {}}}})
ok("...moving the loss sale's count leaves the hedge's alone", E.sl_confirm_params([NBA])[0] == 5 and E.hedge_confirm_params([NBA])[0] == 3)
put_knobs({"groups": {"nba": {"lv": {"hedge_lock_cost": 0.8}, "lat": {}}}})
ok("a hedge never locks in a loss (the least lock-in can't go under 1x)", E.hedge_lock_cost([NBA]) == 1.0 and K["hedge_lock_cost"]["min"] == 1.0)

# ---- the hedge cap: raised only up to $150, given back by a brake
E.CFG["hedge_cap"] = 100
put_knobs({"settings": {"hedge_cap": {"system": 400}}})
ok("a system raise never goes past $150", E.hedge_cap_now() == 150)
put_knobs({"settings": {"hedge_cap": {"system": 140}}, "brake": {"nfl": {"until": now + 60}}})
ok("a brake anywhere gives your own value back", E.hedge_cap_now() == 100)
switch(False)
put_knobs({"settings": {"hedge_cap": {"system": 140}}})
ok("self-tuning off: your own value", E.hedge_cap_now() == 100)
switch(True)
rows = [{"kick": now - 86400 * 20 + i * 3600, "whole": 20.0, "locked": 30.0, "hcost": 105.0, "cost": 20.0, "cap": 100.0,
         "prefer": True, "ok": True} for i in range(60)]
for cap0, want in ((100, 110), (145, 150), (150, None)):
    st = {"groups": {}, "brake": {}, "settings": {"hedge_cap": {"system": cap0 if cap0 > 100 else None}}}
    r = E.knob_cap_step([dict(x, hcost=cap0 + 5 if cap0 < 150 else 155) for x in rows], st, True, now)
    if (r or {}).get("to") != want:
        print("cap step", cap0, r)
        want = "bad"
        break
ok("the cap steps $10 at a time on evidence, never above $150", want != "bad")
ok("...and not without enough recorded decisions", E.knob_cap_step(rows[:10], {"groups": {}, "brake": {}, "settings": {}}, True, now) is None)

# ---- the hedge judge's sign
r = {"whole": 20.0, "locked": 19.5, "hcost": 30.0, "cost": 10.0, "cap": 100.0, "prefer": True, "ok": True}
ok("hedge judge: lowering the share to hedge a 97.5% lock-in counts what it locked in",
   abs(E._knob_res_hedge(r, {"hedge_lock_share": 0.95}) - 19.5 * E.KNOB_HAIRCUT["hedge"]) < 1e-9 and E._knob_res_hedge(r, {"hedge_lock_share": 0.99}) == 20.0)
ok("...never where the game wasn't in play on a fresh score, or over the cap",
   E._knob_res_hedge(dict(r, ok=False), {"hedge_lock_share": 0.9}) == 20.0
   and E._knob_res_hedge(r, {"hedge_lock_share": 0.9, "hedge_cap": 25}) == 20.0)

# ---- break_ok: never live in this build; episodes recorded; its rule
T1 = "KXNBAGAME-26NOV21BOSNYK-BOS"
put_knobs({"groups": {"nba": {"lv": {"brk_on": 1, "brk_move": 0.04}, "v": {"brk_on": 1, "brk_move": 0.04}, "lat": {}}}})
brk_sc = {"state": "in", "detail": "Half", "frac": 0.5}
E.PRICE_SEEN[T1] = (time.time(), 0.30, 0.34, 10)
_g = E.guards_on; E.guards_on = lambda: False                 # the learned guards off = develop (t_learnedguards.py has them on)
ok("break_ok never acts live (BRK_LIVE off, brk_on not a live knob), whatever is recorded",
   E.BRK_LIVE is False and "brk_on" not in E.KNOB_LIVE and "brk_move" not in E.KNOB_LIVE
   and E.break_ok(T1, "yes", brk_sc, time.time()) is False)
E.SCORES_BY["nba"] = {"at": time.time(), "by": {}}
E.leg_score = lambda l: brk_sc
ok("a loss sale still waits out the break", E.stop_loss_leg(T1, "yes", 0.7, 0.2, {"prog": 0.4, "drop": 0.2})
   == (False, "halftime or a break"))
ok("brk_fires: two reads a minute apart that moved enough",
   E.brk_fires([(0, 0.3, 0.3), (30, 0.2, 0.2), (95, 0.2, 0.2)], 0.3, 0.08) == 2
   and E.brk_fires([(0, 0.3, 0.3), (30, 0.2, 0.2), (50, 0.2, 0.2)], 0.3, 0.08) is None
   and E.brk_fires([(0, 0.3, 0.3), (30, 0.25, 0.25), (95, 0.25, 0.25)], 0.3, 0.08) is None
   and E.brk_fires([(0, 0.3, 0.3), (30, 0.25, 0.25), (95, 0.25, 0.25)], 0.3, 0.08, news=True) == 2)
E.BRK_EP.clear()
t0 = time.time()
for k, (bid, ask) in enumerate(((0.30, 0.34), (0.20, 0.24), (0.19, 0.23), (0.19, 0.23))):
    E.PRICE_SEEN[T1] = (t0 + 30 * k, bid, ask, 5)
    E.break_watch(T1, "yes", brk_sc, t0 + 30 * k)
E.PRICE_SEEN[T1] = (t0 + 200, 0.15, 0.19, 5)
E.break_watch(T1, "yes", {"state": "in", "detail": "Q3 11:40", "frac": 0.48}, t0 + 200)
row = (E.store_rows("select * from break_ep") or [{}])[0]
ok("a break episode is recorded with its reads, the price after, and when it would have acted (watch-only)",
   row.get("ticker") == T1 and len(json.loads(row["reads"])) == 4 and row["after_bid"] == 0.15
   and row["would"] is not None and row["league"] == "nba")
ok("a thin or old book is never read as a move", E._brk_book(T1, "yes", t0 + 200 + E.BRK_FRESH + 1) is None)
E.GUARD_SWITCH.update(at=time.monotonic(), on=False)         # the learned guards off: develop's gross result
ok("break judge: acting at the break vs just after it, per contract",
   abs(E._knob_res_brk({"reads": [(0, 0.3, 0.32), (30, 0.2, 0.22), (95, 0.2, 0.22)], "after": 0.15, "news": False},
                       {"brk_on": 1, "brk_move": 0.08}) - 0.05) < 1e-9
   and E._knob_res_brk({"reads": [(0, 0.3, 0.32)], "after": 0.15}, {"brk_on": 0, "brk_move": 0.08}) == 0.0)
E.GUARD_SWITCH.update(at=0.0, on=None)                       # back to reading the real switch

# ---- the stop-loss switch's judge and Smart Buy's watch-only bar
c = {"stake": 10.0, "pl": -10.0, "pays": 20.0, "legs": [{"ticker": T1, "p": 0.6}]}
slp = [(now + 100 * k, {T1: (ch, "AAA 40–50 BBB " + sc)}) for k, (ch, sc) in enumerate(
    [(0.3, "Q3 6:00"), (0.3, "Q3 5:00"), (0.3, "Q3 4:00"), (0.3, "Q3 3:00"), (0.1, "Q4 5:00"), (0.0, "Final")])]
cur = {"sl_prog": 0.5, "sl_drop": 0.2, "sl_auto": 0, "sl_checks": 3, "sl_span": 180, "sl_gap": 300}
ds = E.knob_judge("sl", [(c, None, slp)], cur, "sl_auto", 1)
sold_ = E._sl_replay(c, slp, 0.5, 0.2, hair=True)
ok("stop-loss switch judge: turning it on = what selling at a loss got (on a 3% worse price) vs holding",
   sold_ is not None and abs(ds[0][1] - (sold_ - c["pl"])) < 1e-6 and sold_ < E._sl_replay(c, slp, 0.5, 0.2))
sbr = [{"ev": 0.3, "out": -2.0, "kick": 1}, {"ev": 0.2, "out": 1.0, "kick": 2}]
ds = E.knob_judge("sbev", sbr, {"sb_ev_min": 0.25}, "sb_ev_min", 0.35)
ok("Smart Buy's smallest expected profit is judged (a bet the higher bar drops loses its result)",
   ds[0][1] == 2.0 and ds[1][1] == 0.0 and "sb_ev_min" not in E.KNOB_LIVE)
ok("the loss guards may step live; the break rule, the hedge lock-in numbers and Smart Buy only in shadow",
   {"sl_prog", "sl_drop", "sl_auto", "sl_checks", "sl_span", "sl_gap"} <= set(E.KNOB_LIVE)
   and not {"brk_on", "brk_move", "sb_ev_min", "sb_dial"} & set(E.KNOB_LIVE)
   and all(E.KNOB_JUDGED.get(n) for n in ("sl_auto", "brk_on", "brk_move", "hedge_lock_share", "sb_ev_min")))
ok("invariants stay untouched (never judged, never live)",
   all(K[n]["cls"] == "invariant" and n not in E.KNOB_JUDGED and n not in E.KNOB_LIVE
       for n in ("pause", "can_trade", "rule8", "cap_read_age", "in_play", "fresh_quote", "secrets")))
ok("the confirmation counts can't be loosened below 3 checks over 3 minutes",
   all(K[n]["min"] == K[n]["start"] for n in ("sl_checks", "sl_span", "hedge_checks", "hedge_span")))
ok("turning the stop-loss on by itself needs 3 standard errors (a stricter bar)",
   "sl_auto" in E.KNOB_STRICT_BAR and E.KNOB_EVIDENCE_STRICT["se"] == 3.0)

# ---- settings sync: a stale old switch never loosens 'Selling at a loss' (code review of #228 PR5)
def sync(cur, inc):
    c = dict(cur); E.sl_sync(c, inc); return c
ok("a valid choice wins and keeps the old switch in step; the retired 'never' is saved as 'tune'",
   sync({"stop_loss": False, "stop_loss_mode": "tune"}, {"stop_loss_mode": "allow", "stop_loss": False})
   == {"stop_loss": True, "stop_loss_mode": "allow"}
   and sync({"stop_loss": True, "stop_loss_mode": "allow"}, {"stop_loss_mode": "never", "stop_loss": True})
   == {"stop_loss": False, "stop_loss_mode": "tune"})
ok("a phone with no control (None) and a stale 'on' can't undo Let it tune itself, even from a stored 'never'",
   sync({"stop_loss": False, "stop_loss_mode": "never"}, {"stop_loss_mode": None, "stop_loss": True})["stop_loss_mode"] != "allow"
   and sync({"stop_loss": False, "stop_loss_mode": "tune"}, {"stop_loss": True})["stop_loss_mode"] == "tune")
ok("an old page's 'off' turns Allow into Let it tune itself, never looser",
   sync({"stop_loss": True, "stop_loss_mode": "allow"}, {"stop_loss": False}) == {"stop_loss": False, "stop_loss_mode": "tune"}
   and sync({"stop_loss": True, "stop_loss_mode": None}, {"stop_loss": False})["stop_loss_mode"] == "tune"
   and sync({"stop_loss": False, "stop_loss_mode": "never"}, {"stop_loss": False})["stop_loss_mode"] == "tune")
W_ = open("wtest/combo_watcher.py").read()
ok("the watcher applies phone settings through sl_sync (never the raw value)", "E.sl_sync(E.CFG" in W_
   and 'k not in ("stop_loss", "stop_loss_mode")' in W_ and "A.sl_sync(A.CFG" in W_)
ok("the hedge lock-in numbers and the cap raise stay watch-only until judged on real results",
   not {"hedge_lock_share", "hedge_lock_cost"} & set(E.KNOB_LIVE) and E.HEDGE_RAISE_LIVE is False)

# ---- a saved 'never' (retired) reads as 'tune': a single's learned loss cut works as under 'tune' (its own guards)
E.CFG.update(stop_loss_mode="never", smart_sell=True, auto_sell=True)
E.SINGLES.update(at=time.time(), items=[{"t": T1, "side": "yes", "state": "live", "n": 10, "cost": 6.0, "label": "BOS",
                                          "kind": "win", "chance": 0.2, "sport": "nba"}],
                 mk={T1: {"yes_bid_dollars": "0.30", "yes_ask_dollars": "0.32"}})
SOLD = []
E.single_sell_reason = lambda x, bid, ask, track=True, cut_ok=False: ("cut loss", 0.1)
E.sell_single_now = lambda *a: (SOLD.append(a), (10, None))[1]
E.resting_single_sells = lambda: set(); E.order_unsure = lambda t: False; E.hands_off = lambda t: False
E.sell_held = lambda out: False; E.auto_cap_reached = lambda: False; E.log_decision = lambda r: None
E.smart_sell_singles()
ok("a saved 'never' no longer blocks a single's learned loss cut (the cut's own guards decide)", len(SOLD) == 1)
E.CFG["stop_loss_mode"] = "allow"
E.smart_sell_singles()
ok("...and with Allow the same cut goes through", len(SOLD) == 2)
E.CFG["stop_loss_mode"] = None
