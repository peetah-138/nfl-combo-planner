# CHECK: group=engine
# Overlap guard (issue #359): a game Pete already has enough on (2 open bets by default, or 8% of the panel's sizing
# base at risk) is held back from every pick list, with "Add anyway" on his own tap. Checks: one key per game for
# winners, spreads, totals and combo legs; a combo counts its full cost once per game it touches; today's panel counts
# unless the account already shows that bet; both thresholds at their edges; the switch off means no guard; the page's
# allow list; the quote line; a buy-straight price gets the line without changing whether it clears; the settings keys
# are shared. Display only: nothing here prices, buys or saves anything. The network is fakenet.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.MAIN_SAVED = os.path.join(E.HERE, "no_shared_settings.json")      # switches come from CFG here
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
E.SIZING_FILE = os.path.join(E.HERE, "sizing.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()

G1 = "KXNBAGAME-26NOV22AAABBB"            # a game
G2 = "KXNBAGAME-26NOV22CCCDDD"            # another
G3 = "KXNBAGAME-26NOV22EEEFFF"
SP1 = "KXNBASPREAD-26NOV22AAABBB"         # G1's spread event
TO1 = "KXNBATOTAL-26NOV22AAABBB"          # G1's total event

# ---- one key per game
ok("a spread ticker maps to its game", E.overlap_key("", SP1 + "-AAA3") == G1)
ok("a total event maps to its game", E.overlap_key(TO1) == G1)
ok("a game-winner ticker maps to its game", E.overlap_key("", G1 + "-AAA") == G1)
ok("nothing in, nothing out", E.overlap_key() == "")


def state(bets=(), singles=(), balance=500.0):
    E.ACCT_CACHE.update(at=now, value=(list(bets), balance, "test"))
    E.SINGLES.update(at=now if singles else 0, items=list(singles))
    E.ACCT_POS.update(at=0, items=[])


def combo(legs, cost, status="pending"):
    return {"status": status, "cost": cost, "legs": [{"ticker": t, "event": t.rsplit("-", 1)[0]} for t in legs]}


# ---- exposure: a combo counts its full cost once on every game it touches
state([combo([G1 + "-AAA", G2 + "-CCC"], 5.0), combo([G1 + "-BBB", SP1 + "-AAA3"], 4.0),   # 2nd: two legs on G1, counts once
       combo([G3 + "-EEE", G2 + "-DDD"], 3.0, status="won")],                             # settled: never counts
      singles=[{"t": TO1 + "-T220", "event": TO1, "cost": 2.5, "state": "open"},
               {"t": G3 + "-EEE", "event": G3, "cost": 9.0, "state": "over"}])               # finished: never counts
ex = E.game_exposure()
ok(f"G1: two combos and a total = 3 bets, $11.50 ({ex.get(G1)})", ex.get(G1) == {"n": 3, "risk": 11.5})
ok(f"G2: one combo, its full $5 ({ex.get(G2)})", ex.get(G2) == {"n": 1, "risk": 5.0})
ok(f"G3: only settled or finished bets: not counted ({ex.get(G3)})", G3 not in ex)

# ---- today's panel counts, unless the account already shows that bet
REAL_PG = E.panel_get
E.panel_get = lambda v: {"items": [
    {"state": "scheduled", "stake": 6.0, "legs": [{"ticker": G3 + "-EEE", "event": G3}]},                   # new: counts
    {"state": "bought", "stake": 5.0, "legs": [{"ticker": G1 + "-AAA", "event": G1}, {"ticker": G2 + "-CCC", "event": G2}]},  # the account has it
    {"state": "check", "stake": 2.0, "legs": [{"ticker": G2 + "-DDD", "event": G2}]},                       # unknown outcome: open
    {"state": "failed", "stake": 7.0, "legs": [{"ticker": G2 + "-CCC", "event": G2}]},                      # never bought
    {"state": "skipped", "stake": 7.0, "legs": [{"ticker": G3 + "-FFF", "event": G3}]}]}
ex = E.game_exposure()
ok(f"panel: a scheduled bet counts ({ex.get(G3)})", ex.get(G3) == {"n": 1, "risk": 6.0})
ok(f"panel: a bought combo the account shows counts once; a 'check' counts; failed doesn't ({ex.get(G2)})",
   ex.get(G2) == {"n": 2, "risk": 7.0})
ok(f"panel: G1 unchanged ({ex.get(G1)})", ex.get(G1) == {"n": 3, "risk": 11.5})
E.panel_get = REAL_PG

# ---- thresholds at their edges (defaults: 2 bets, 8% of base)
EXP = {G1: {"n": 1, "risk": 7.99}, G2: {"n": 2, "risk": 1.0}, G3: {"n": 1, "risk": 8.0}}
ov = E.overlap_games(base=100.0, exposure=EXP)
ok(f"1 bet under 8%: kept ({sorted(ov)})", G1 not in ov)
ok("2 bets: held back, by count", ov.get(G2, {}).get("why") == "n")
ok("exactly 8% of base at risk: held back, by risk", ov.get(G3, {}).get("why") == "risk")
ok("the note says how many bets and the money at risk",
   ov.get(G2, {}).get("text") == "You already have 2 open bets on this game ($1 at risk).")
E.ACCT_CACHE.update(value=None)
ov = E.overlap_games(exposure=EXP)
ok(f"no balance read: only the count rule ({sorted(ov)})", sorted(ov) == [G2])
ok("Add anyway: an allowed game is let through", E.overlap_games(allow={G2}, base=100.0, exposure=EXP).keys() == {G3})
ok("allow given as a spread event still lets its game through",
   G1 not in E.overlap_games(allow=E.overlap_allow(SP1), base=100.0, exposure={G1: {"n": 5, "risk": 50}}))

# ---- settings: the numbers and the switch
E.CFG["overlap_n"] = 3
ok("3 bets set: 2 bets kept", G2 not in E.overlap_games(base=100.0, exposure=EXP))
E.CFG["overlap_n"] = 2
E.CFG["overlap_pct"] = 10
ok("10% set: $8 of $100 kept", G3 not in E.overlap_games(base=100.0, exposure=EXP))
E.CFG["overlap_pct"] = 8
E.CFG["overlap_n"] = "junk"
ok("an unreadable number falls back to the default", E.overlap_settings()[1] == 2)
E.CFG["overlap_n"] = 2
E.CFG["overlap_guard"] = False
ok("switch off: no game held back", E.overlap_games(base=100.0, exposure=EXP) == {})
ok("switch off: no quote line", E.overlap_note([{"ticker": G2 + "-CCC"}]) is None)
E.CFG["overlap_guard"] = True
ok("on by default", E.CFG.get("overlap_guard") is True and E.overlap_settings()[0] is True)
ok("all three keys are shared with the web app's settings",
   {"overlap_guard", "overlap_n", "overlap_pct"} <= set(E.SHARED_KEYS))
REAL_GE = E.game_exposure
E.game_exposure = lambda: 1 / 0
ok("a failure means no guard, never a broken list", E.overlap_games() == {} and E.overlap_note([G1 + "-AAA"]) is None)
E.game_exposure = REAL_GE

# ---- the page's allow list
al = E.overlap_allow(G1 + "," + SP1 + ",<script>,," + "x" * 200)
ok(f"allow: game keys kept, junk dropped ({sorted(al)})", al == {G1})
ok("allow: at most 20 kept", len(E.overlap_allow([f"KXNBAGAME-26NOV22G{i:03d}" for i in range(40)])) == 20)
ok("allow: a list works too", E.overlap_allow([G2]) == {G2})
ok("allow: anything that isn't text or a list is ignored", E.overlap_allow(5) == set() and E.overlap_allow({"a": 1}) == set())

# ---- a buy clears the singles stamp (at=0) to force a re-read; the last items still count meanwhile
state([], singles=[{"t": G2 + "-CCC", "event": G2, "cost": 4.0, "state": "open"}])
E.SINGLES["at"] = 0
ok("singles stamp cleared: the open single still counts", E.game_exposure().get(G2, {}).get("n") == 1)

# ---- overlap_of and the quote line
ov = {G1: {"n": 2, "risk": 3.0, "why": "n", "text": "t"}}
ok("overlap_of: an event on the game", (E.overlap_of(ov, [SP1]) or {}).get("game") == G1)
ok("overlap_of: a ticker on the game", (E.overlap_of(ov, [], [G1 + "-BBB"]) or {}).get("n") == 2)
ok("overlap_of: another game is None", E.overlap_of(ov, [G2], [G2 + "-CCC"]) is None)
state([combo([G1 + "-AAA", G2 + "-CCC"], 5.0)])
ok("quote line: one bet on the game is enough for the note",
   E.overlap_note([{"ticker": G2 + "-DDD", "event": G2}]) == "You already have 1 open bet on this game ($5 at risk).")
ok("quote line: a bare ticker works", E.overlap_note([G1 + "-BBB"]) is not None)
ok("quote line: no bet on the game, no note", E.overlap_note([G3 + "-EEE"]) is None)

# ---- a buy-straight price: the note is added, whether it clears is unchanged
import fakenet
fakenet.install(port=1)
G = fakenet.GAMES["KXNBAGAME"]
G[1], G[2] = G[2], G[1]
E.set_league("nba")
E.CFG["kalshi_key_id"] = "fake-key-id"
E.CFG["budget"] = 100.0
E.CFG["bankroll"] = 400.0
E.hub_conf = lambda: None
E.can_trade = lambda: True
E.week_spend = lambda: 10.0
E.cap_combo_spend = lambda code, key, now=None: 10.0
EV = fakenet.event_ticker("KXNBAGAME", "DEN", "LAL")
T = EV + "-DEN"
mk = {m["ticker"]: m for m in fakenet.markets()}
X = {"ticker": T, "pick": "Denver Nuggets", "event": EV, "exp": mk[T]["expected_expiration_time"], "fair": 0.80,
     "src": "pinnacle", "opp": "Los Angeles Lakers", "fair_at": time.time()}
state([])
q0 = E.single_buy_quote(X, 10)
state([combo([EV + "-LAL", G2 + "-CCC"], 4.0)])
q1 = E.single_buy_quote(X, 10)
w0 = [w for w in q0.get("warn") or [] if w.get("k") == "overlap"]
w1 = [w for w in q1.get("warn") or [] if w.get("k") == "overlap"]
ok(f"buy straight: no bet on the game, no note ({q0.get('ok')}, {w0})", q0.get("ok") and not w0)
ok(f"buy straight: a bet on the game adds the note ({w1})", q1.get("ok") and len(w1) == 1 and "1 open bet" in w1[0]["t"])
ok("buy straight: the note never changes the price or whether it clears",
   all(q0.get(k) == q1.get(k) for k in ("ask", "clears", "stake", "edge", "n")))
