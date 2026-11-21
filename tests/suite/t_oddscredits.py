# CHECK: group=engine
# Odds service credits: recorded from the headers of answers we already get (no extra calls), the burn rate, run-out
# and reset date for Settings › The Mac, the one low-credit alert, and low mode (which only changes which leagues'
# sportsbook lines the Mac reads; never a buy, a sale or a price rule). Everything is faked; nothing touches the network.
import os, sys, time, json, tempfile, importlib.util, traceback, datetime as dt
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db"))
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


E.REAL_CREDITS = E.ODDS_CREDITS


def fresh_file():
    E.ODDS_CREDITS = os.path.join(tempfile.mkdtemp(), "combo_odds_credits.json")


class Resp:
    def __init__(s, code=200, body=None, headers=None):
        s.status_code, s.ok, s.headers, s._b = code, code < 400, headers or {}, body if body is not None else []

    def json(s):
        return s._b


T0 = dt.datetime(2026, 11, 10, 12, tzinfo=dt.timezone.utc).timestamp()     # Nov 10: the free plan resets Dec 1


# ---------------------------------------------------------------- A: headers recorded, no extra calls
def sec_a():
    fresh_file()
    calls = []
    real = E.requests.get

    def fake(url, params=None, **kw):
        calls.append(url)
        return Resp(200, [], {"x-requests-remaining": "412", "x-requests-used": "88", "x-requests-last": "2"})
    E.requests.get = fake
    try:
        E.fetch_book_odds_one("SECRETKEY123", "https://api.the-odds-api.com/v4/sports/basketball_nba/odds")
    finally:
        E.requests.get = real
    s = json.load(open(E.ODDS_CREDITS))
    ok("A: one odds call = one request (the quota is read from its headers, never asked for)", len(calls) == 1)
    ok("A: remaining, used and last cost are recorded", (s["remaining"], s["used"], s["last"]) == (412, 88, 2))
    ok("A: the file name is git-ignored (combo_*.json) and holds no key",
       os.path.basename(E.ODDS_CREDITS).startswith("combo_") and os.path.basename(E.REAL_CREDITS).startswith("combo_")
       and "SECRETKEY123" not in open(E.ODDS_CREDITS).read())
    E.requests.get = lambda url, params=None, **kw: Resp(429, {"message": "quota"}, {"x-requests-remaining": "0", "x-requests-used": "500"})
    try:
        _, note = E.fetch_book_odds_one("k", "https://api.the-odds-api.com/v4/sports/basketball_nba/odds")
    finally:
        E.requests.get = real
    ok("A: an out-of-credits answer (429) is recorded too", json.load(open(E.ODDS_CREDITS))["remaining"] == 0 and "credits" in note)
    E.requests.get = lambda url, params=None, **kw: Resp(200, [], {})
    try:
        E.fetch_book_odds_one("k", "https://api.the-odds-api.com/v4/sports/basketball_nba/odds")
    finally:
        E.requests.get = real
    ok("A: an answer without the headers leaves the last numbers alone", json.load(open(E.ODDS_CREDITS))["remaining"] == 0)
    ok("A: odd header values never raise or get saved", E.odds_credits_note({"x-requests-remaining": "lots"}) is False
       and E.odds_credits_note({"x-requests-remaining": "-3"}) is False)
    src = open("wahome/engine.py").read()
    ok("A: the stale-line expiry stays 45 minutes", E.PRE_LINE_AGE == 45 * 60 and E.PRE_LINE_NEAR == 4 * 3600)
    ok("A: tennis's tournament list records the headers too", "odds_credits_note(r.headers)\n        return [x[\"key\"]" in src)


# ---------------------------------------------------------------- B: burn rate, run-out, reset date
def sec_b():
    fresh_file()
    ok("B: nothing recorded yet = nothing to show", E.odds_credits(T0) is None)
    E.odds_credits_note({"x-requests-remaining": "400", "x-requests-used": "100"}, now=T0 - 2 * 3600)
    c = E.odds_credits(T0)
    ok("B: with under 6 hours of history there's no pace yet (and no false alarm)", c["per_day"] is None and not c["low"])
    fresh_file()
    E.odds_credits_note({"x-requests-remaining": "400", "x-requests-used": "100"}, now=T0 - 2 * 86400)
    E.odds_credits_note({"x-requests-remaining": "350", "x-requests-used": "150"}, now=T0 - 86400)
    E.odds_credits_note({"x-requests-remaining": "300", "x-requests-used": "200", "x-requests-last": "2"}, now=T0)
    c = E.odds_credits(T0)
    ok("B: about 50 credits a day", abs(c["per_day"] - 50) < 0.01)
    ok("B: 300 left at 50 a day runs out in 6 days", abs(c["runs_out"] - (T0 + 6 * 86400)) < 60)
    reset = dt.datetime.fromtimestamp(c["reset"], dt.timezone.utc)
    ok("B: no reset seen yet: the 1st of next month, marked as an estimate", (reset.month, reset.day) == (12, 1) and c["reset_guess"])
    ok("B: running out (Nov 16) before the reset (Dec 1) = low, reason 'pace'", c["low"] and c["why"] == "pace")
    # the plan resets: credits jump back up, the pace starts over, the reset day comes from what we saw
    E.odds_credits_note({"x-requests-remaining": "500", "x-requests-used": "0"}, now=T0 + 3600)
    c = E.odds_credits(T0 + 7200)
    reset = dt.datetime.fromtimestamp(c["reset"], dt.timezone.utc)
    ok("B: a jump back up is a reset: next one a month after it, not an estimate",
       not c["reset_guess"] and (reset.month, reset.day) == (12, 10))
    ok("B: after a reset there's no pace until it builds again, and it isn't low", c["per_day"] is None and not c["low"])
    fresh_file()
    E.odds_credits_note({"x-requests-remaining": "30", "x-requests-used": "470"}, now=T0)
    c = E.odds_credits(T0)
    ok("B: 30 left is under the floor (40) whatever the pace", c["low"] and c["why"] == "floor")
    E.odds_credits_note({"x-requests-remaining": "0", "x-requests-used": "500"}, now=T0 + 60)
    ok("B: none left = reason 'out'", E.odds_credits(T0 + 120)["why"] == "out")
    s = json.load(open(E.ODDS_CREDITS))
    for i in range(900):
        E.odds_credits_note({"x-requests-remaining": "0"}, now=T0 + 200 + i)
    ok("B: the history stays small", len(json.load(open(E.ODDS_CREDITS))["pts"]) <= 400 and s)


# ---------------------------------------------------------------- C: one alert per low state; low mode doesn't flap
def sec_c():
    fresh_file()
    E.odds_credits_note({"x-requests-remaining": "30", "x-requests-used": "470"}, now=T0)
    saving, c = E.odds_saving(T0)
    k1 = E.odds_low_alert(c)
    ok("C: low turns saving on, with a plain message", saving and k1 and "running low" in k1[1] and "reset Dec 1 (estimate)" in k1[1])
    E.odds_mark(alerted=k1[0])
    ok("C: the same low state on the next check gives the same key (so it's sent once)",
       E.odds_low_alert(E.odds_saving(T0 + 60)[1])[0] == k1[0] and E.odds_credits(T0)["alerted"] == k1[0])
    E.odds_credits_note({"x-requests-remaining": "45", "x-requests-used": "470"}, now=T0 + 600)   # a little more, not a reset
    saving, c = E.odds_saving(T0 + 700)
    ok("C: just over the floor again: saving stays on (no flapping)", saving and not c["low"])
    E.odds_credits_note({"x-requests-remaining": "0", "x-requests-used": "500"}, now=T0 + 900)
    k2 = E.odds_low_alert(E.odds_saving(T0 + 901)[1])
    ok("C: running out completely is a new state: its own alert", k2[0] != k1[0] and "used up" in k2[1])
    E.odds_credits_note({"x-requests-remaining": "500", "x-requests-used": "0"}, now=T0 + 86400)
    saving, c = E.odds_saving(T0 + 86400 + 60)
    ok("C: after the reset saving turns off and there's no alert", not saving and E.odds_low_alert(c) is None)


# ---------------------------------------------------------------- D: which leagues are worth a call in low mode
def sec_d():
    now = T0
    E.PANEL_POOL.clear()
    ok("D: nothing that matters = not worth a call", not E.odds_worth_reading("nba", E.odds_interest([], now), now))
    E.PANEL_POOL["nba"] = (now - 60, [{"kick": now + 2 * 3600}])
    ok("D: an edge candidate starting in 2 hours = worth it", E.odds_worth_reading("nba", E.odds_interest([], now), now))
    ok("D: ...only for its own league", not E.odds_worth_reading("nhl", E.odds_interest([], now), now))
    ok("D: ...and the Mix (it reads the NBA too)", E.odds_worth_reading("mix", E.odds_interest([], now), now))
    E.PANEL_POOL["nba"] = (now - 60, [{"kick": now + 9 * 3600}])
    ok("D: a candidate 9 hours away waits (far-off game)", not E.odds_worth_reading("nba", E.odds_interest([], now), now))
    E.PANEL_POOL["nba"] = (now - 3 * 3600, [{"kick": now + 3600}])
    ok("D: an old candidate (pool past its age) doesn't count", not E.odds_worth_reading("nba", E.odds_interest([], now), now))
    E.PANEL_POOL["nba"] = (now - 60, [{"kick": None}])
    ok("D: a candidate with no start time doesn't count", not E.odds_worth_reading("nba", E.odds_interest([], now), now))
    E.PANEL_POOL.clear()
    held = [("KXNHLGAME-26NOV10BOSNYR-BOS", now - 3600)]
    ok("D: a held bet whose game is under way = worth it", E.odds_worth_reading("nhl", E.odds_interest(held, now), now))
    held = [("KXNHLSPREAD-26NOV10BOSNYR-BOS2", now + 3600)]
    ok("D: a held spread counts for its game's league", E.odds_worth_reading("nhl", E.odds_interest(held, now), now))
    held = [("KXEPLGAME-26NOV10ARSCHE-ARS", None)]
    ok("D: a held bet with an unknown start counts (we'd rather read than guess)",
       E.odds_worth_reading("soccer", E.odds_interest(held, now), now) and not E.odds_worth_reading("nfl", E.odds_interest(held, now), now))
    ok("D: NCAA men's and women's basketball stay apart",
       E._codes_of_ticker("KXNCAAWBGAME-26NOV10AB-A") == ["ncaawb"])
    E.MINE["hold"] = {"KXMVE-1": {"need": [(("yes", "KXNBAGAME-26NOV10BOSNYK-BOS"), "Boston")]}}
    E.ACCT_POS.update(at=time.time(), items=[{"ticker": "KXNHLGAME-26NOV10BOSNYR-BOS", "position_fp": "3"},
                                             {"ticker": "KXNHLGAME-26NOV10X-Y", "position_fp": "0"}])
    got = [t for t, _ in E.held_for_credits()]
    ok("D: held bets come from live combos' picks and open single positions (no fetch)",
       got == ["KXNBAGAME-26NOV10BOSNYK-BOS", "KXNHLGAME-26NOV10BOSNYR-BOS"])
    E.MINE["hold"] = {"bad": {"need": [None, 3]}}
    ok("D: odd held data never raises", isinstance(E.held_for_credits(), list))
    E.MINE["hold"] = {}
    E.ACCT_POS.update(items=[])


# ---------------------------------------------------------------- E: the Mac's HubOdds reads less, alerts once
def sec_e():
    sys.argv = ["combo_watcher.py", "--webapp"]
    spec2 = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
    W = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(W)
    pushed = []
    W.push = lambda conf, msg, **kw: pushed.append((msg, kw.get("title")))
    W.DEP["conf"] = {"topic": "t"}
    fresh_file()
    sharp = []
    soon = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    E.free_snapshot = lambda codes: {"fair": {}, "games": {}, "opp": {}, "kick": {"Team": soon}, "note": ""}
    E.sharp_snapshot = lambda key: (sharp.append(key), {"fair": {"Team": [0.6, "Pinnacle"]}, "games": {}, "opp": {}, "kick": {}, "note": "x"})[1]
    E.set_league = lambda code: None
    sent = []
    E.kalshi_send = lambda *a, **k: sent.append(a)
    o = W.HubOdds()
    o.H = E
    E.PANEL_POOL.clear()
    o.get("nba", "key")
    ok("E: plenty of credits (or none recorded): the Mac reads as before", len(sharp) == 1 and not pushed)
    E.odds_credits_note({"x-requests-remaining": "20", "x-requests-used": "480"})
    o.sharp.clear()
    snap = o.get("nba", "key")
    time.sleep(0.2)
    ok("E: low and nothing near that matters: no call", len(sharp) == 1)
    ok("E: ...the note says why", "Saving sportsbook credits" in snap["note"])
    o.sharp["nhl"] = (time.time() - 7 * 3600, {"fair": {"Old": [0.7, "Pinnacle"]}, "games": {}, "opp": {}, "kick": {}, "note": "x"})
    snap = o.get("nhl", "key")
    ok("E: an overdue sharp line skipped for credits is dropped, not kept for days",
       "nhl" not in o.sharp and "Old" not in snap.get("fair", {}) and len(sharp) == 1)
    ok("E: ...and one alert went out", len(pushed) == 1 and pushed[0][1] == "Odds credits")
    o.get("nhl", "key")
    o.get("nba", "key")
    time.sleep(0.2)
    ok("E: the same low state doesn't alert again", len(pushed) == 1)
    E.PANEL_POOL["nba"] = (time.time() - 60, [{"kick": time.time() + 3600}])
    o.get("nba", "key")
    ok("E: low, but an edge candidate starts within the hour: that league is read", len(sharp) == 2)
    o.get("nhl", "key")
    ok("E: ...and a league with nothing near still isn't", len(sharp) == 2)
    o.get("nba", "", )
    ok("E: no key: never calls (as before)", len(sharp) == 2)
    ok("E: nothing here ever places an order", not sent)
    E.odds_credits = lambda now=None: (_ for _ in ()).throw(ValueError("broken file"))
    ok("E: a broken credits file never stops lines being read", o.worth_credits(E, "nhl", time.time()) is True)
    # Settings › The Mac: numbers only, never the key
    E.odds_credits = odds_credits_real
    E.CFG["odds_key"] = "SECRETKEY123"
    info = W.odds_info(E)
    ok("E: The Mac card gets the numbers (remaining, pace, reset, saving)",
       info and info["remaining"] == 20 and "reset" in info and info["saving"] is True)
    ok("E: ...and never the key", "SECRETKEY123" not in json.dumps(info))
    E.CFG["odds_key"] = ""
    ok("E: no odds key: no credits row", W.odds_info(E) is None)
    fresh_file()
    E.CFG["odds_key"] = "k"
    ok("E: a key but nothing recorded yet: 'shows up after the next check'", W.odds_info(E) == {"none": True})
    E.CFG["odds_key"] = ""


odds_credits_real = E.odds_credits
for name, fn in (("A", sec_a), ("B", sec_b), ("C", sec_c), ("D", sec_d), ("E", sec_e)):
    section(name, fn)
