# CHECK: group=engine
# Guards batch 2 (#350, #400, #366, #367, #407). Guards, logging and warnings only; nothing here changes what is bought or sold.
#  #350  carry_quote never withdraws a price request that is not its own (Pete's open "Get price" on the same combo)
#  #400  Pete's own sale tap leaves a short marker; the automatic sellers skip that bet while it stands (one direction only:
#        the tap never reads or waits on it)
#  #366  Add anyway now carries the game's exposure at the tap; more riding than that greys the game again (never looser)
#  #367  greyed games and Add anyway taps are written to overlap_log (measurement only)
#  #407  the closed-bet detail is cached per ticker (source check: the function is inside the web app's server)
# Kalshi and the network are faked; nothing is sent.
import os, re, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl"); E.HEDGES = os.path.join(E.HERE, "hedges.json")
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
E.MANUAL_SELL = os.path.join(E.HERE, "combo_manual_sell.json")
E.MAIN_SAVED = os.path.join(E.HERE, "no_shared_settings.json")
ok = lambda n, c, *why: print(("PASS " if c else "FAIL ") + n + ("" if c or not why else f" {why}"))

# ---- #350: carry_quote and Pete's own price request
SENT = []
OPEN = {"rfqs": []}


def fake_send(method, path, body=None, params=None, **k):
    SENT.append((method, path))
    if method == "POST" and path.startswith("/multivariate_event_collections/"):
        return {"market_ticker": "KXMVE-TEST-1"}
    if method == "GET" and path == "/communications/rfqs":
        if OPEN.get("boom"):
            raise RuntimeError("unreadable")
        return OPEN
    if method == "POST" and path == "/communications/rfqs":
        return {"id": "mine1"}
    if method == "GET" and path == "/communications/quotes":
        return {"quotes": []}
    return {}


E.kalshi_send = fake_send
E.hold_refusal = lambda kind: (None, None)
E.find_collection = lambda legs: "COLL"
E.rfq_unsure = lambda *a, **k: False
E.time.sleep = lambda s: None
LEGS = [{"ticker": "KXNBAGAME-26NOV22AAABBB-AAA", "event": "KXNBAGAME-26NOV22AAABBB"}]

SENT.clear(); OPEN.clear(); OPEN["rfqs"] = []
E.carry_quote(LEGS, 5.0)
ok("#350 control: no open request, ours is created and deleted", ("POST", "/communications/rfqs") in SENT
   and any(m == "DELETE" for m, _ in SENT), SENT)
SENT.clear(); OPEN.clear(); OPEN["rfqs"] = [{"id": "petes", "market_ticker": "KXMVE-TEST-1"}]
r = E.carry_quote(LEGS, 5.0)
ok("#350 Pete's own open request on the combo: no quote, nothing created, nothing deleted",
   r is None and ("POST", "/communications/rfqs") not in SENT and not any(m == "DELETE" for m, _ in SENT), SENT)
SENT.clear(); OPEN.clear(); OPEN["boom"] = True
r = E.carry_quote(LEGS, 5.0)
ok("#350 open requests unreadable: treated as maybe one, so no request and no deletion",
   r is None and ("POST", "/communications/rfqs") not in SENT and not any(m == "DELETE" for m, _ in SENT), SENT)
OPEN.clear(); OPEN["rfqs"] = []

# ---- #400: the manual-sell marker
ok("#400 no marker: nothing is selling", not E.manual_selling("C1"))
with E.manual_sell_mark("C1"):
    ok("#400 inside Pete's tap the bet reads as selling, another does not", E.manual_selling("C1") and not E.manual_selling("C2"))
ok("#400 the marker is gone after the tap", not E.manual_selling("C1"))
try:
    with E.manual_sell_mark("C1"):
        raise ValueError("tap failed")
except ValueError:
    pass
ok("#400 a tap that fails still clears its marker", not E.manual_selling("C1"))
E.save_json(E.MANUAL_SELL, {"OLD": time.time() - 500})
ok("#400 a crashed tap's old marker counts for nothing", not E.manual_selling("OLD"))
with open(E.MANUAL_SELL, "w") as f:
    f.write("{not json")
ok("#400 an unreadable marker file never blocks or raises (reads as not selling)", not E.manual_selling("C1"))
with E.manual_sell_mark("C1"):
    pass
ok("#400 the tap's marker never raises even over a broken file", True)
E.save_json(E.MANUAL_SELL, {})
real_save = E.save_json
E.save_json = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
try:
    with E.manual_sell_mark("C1"):
        went = True
except Exception:
    went = False
E.save_json = real_save
ok("#400 if the marker can't be written, Pete's tap goes ahead anyway (never held up)", went)

# the automatic combo seller skips a bet Pete's tap is selling, and still sells it when no tap is
E.can_trade = lambda: True
E.haptic = E.loading = lambda *a: None
E.resting_sells = lambda: {}
E.drop_cash = lambda t: E.MINE["cash"].pop(t, None)
E._cash_pause = lambda s: None
ACC = []
E.accept_once = lambda o, t=None: (ACC.append(t), "executed")[1]
E.TRADING_PAUSED = lambda: False
E.CFG.update(auto_sell=True, auto_hedge=False, smart_sell=True, auto_cap=9)
E.take_profit_reason = lambda t, h, cut_ok=False: ("smart", 12.0)
E.get_cash_offer = lambda t, f=1.0: {"offer": 13.0, "frac": 1.0, "rfq": "x", "quote": "q", "contracts": 20, "at": time.time()}
E.smart_sell_singles = lambda: []
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20}], 300.0, None)
HOLD = {"label": "Combo 5", "cost": 8.0, "p": 0.7, "pays": 20, "left": 1, "legs_left": [(0.7, True, 0)], "won_some": True}
E.fresh_offer = lambda t: dict(E.get_cash_offer(t))
E.wait_threshold = lambda t: 10.0
E.combo_wait_why = lambda *a, **k: None


def auto_round():
    ACC.clear()
    E.MINE["hold"] = {"C1": dict(HOLD)}
    E.MINE["cash"] = {"C1": dict(E.get_cash_offer("C1"))}
    E.MINE["busy"] = False; E.MINE["selling"] = set(); E.COMBO_WAIT.clear()
    return E.auto_sell_now({"acts": {"C1": 1.0}})


r0 = auto_round()
print("DEBUG", r0, ACC)
ok("#400 control: with no tap running the automatic round sells it (the test can fail)", ACC == ["C1"], ACC)
with E.manual_sell_mark("C1"):
    out = auto_round()
ok("#400 while Pete's tap is selling it, the automatic round sends nothing", not ACC, (ACC, out))
ok("#400 the skip is logged (once), so it can be seen", "your own Cash out tap" in open(E.SELL_LOG).read())
auto_round()
ok("#400 after the tap, the next round sells it as before", ACC == ["C1"], ACC)

# the take-profit pass leaves it alone too
E.AUTOSELL = True
E.CFG.update(tp_auto=True, tp_follow=True)
PLACED = []
E.place_take_profit = lambda t, pays, cost, p=None: (PLACED.append(t), "🎯 placed")[1]
E.combo_chance_now = lambda a: 0.8
E.MINE["hold"] = {}; E.MINE["busy"] = False; E.MINE["selling"] = set()
E.fetch_account = lambda **k: ([{"ticker": "C1", "status": "pending", "pays": 20, "cost": 8.0}], 300.0, None)
E.hands_off = lambda t: False
E.autosell_pass()
ok("#400 control: the take-profit pass places its sell when no tap runs", PLACED == ["C1"], PLACED)
PLACED.clear()
with E.manual_sell_mark("C1"):
    E.autosell_pass()
ok("#400 the take-profit pass skips a bet Pete's tap is selling", not PLACED, PLACED)

# Pete's tap never reads the marker: the web app's tap sites only write it
W = open("wtest/combo_watcher.py", encoding="utf-8").read()
ok("#400 the web app only wraps its taps in the marker (never checks it)", "manual_selling" not in W and W.count("manual_sell_mark") == 2)
P = open("wahome/engine.py", encoding="utf-8").read()
i = P.index("def single_sell(")
j = P.index("\ndef ", i + 10)
ok("#400 single_sell and accept_cash (Pete's own paths) never read the marker",
   "manual_selling" not in P[i:j] and "manual_selling" not in P[P.index("def accept_cash("):P.index("def accept_cash(") + 6000])

# ---- #366 / #367: Add anyway carries the exposure; more riding greys it again; everything is logged
G1 = "KXNBAGAME-26NOV22AAABBB"
G2 = "KXNBAGAME-26NOV22CCCDDD"
E.overlap_settings = lambda: (True, 2, 8.0)
al = E.overlap_allow([f"{G1}~2~10.00", G2, "bad~x~y", f"{G1.replace('AAA', 'ZZZ')}~-1~5", f"{G2.replace('CCC', 'EEE')}~2~nan"])
ok("#366 allow parses KEY~n~risk, a plain key, and drops malformed or negative or nan exposure (stays greyed)",
   al == {G1, G2} and al.at == {G1: (2, 10.0)}, (set(al), al.at))
ok("#366 the old plain-list form still works", E.overlap_allow([G1]) == {G1} and E.overlap_allow(G1 + "," + G2) == {G1, G2})
ok("#366 nothing but text or a list is ignored, as before", E.overlap_allow(5) == set())
EXP = {G1: {"n": 2, "risk": 10.0}, G2: {"n": 2, "risk": 10.0}}
ok("#366 control: no allow, both greyed", set(E.overlap_games(base=100.0, exposure=EXP)) == {G1, G2})
ok("#366 allowed at the tap's exposure: let through (as before)", set(E.overlap_games(allow=E.overlap_allow([f"{G1}~2~10"]), base=100.0, exposure=EXP)) == {G2})
ok("#366 a plain allowed key (older page) is let through as before", set(E.overlap_games(allow=E.overlap_allow([G1]), base=100.0, exposure=EXP)) == {G2})
EXP2 = {G1: {"n": 3, "risk": 10.0}, G2: {"n": 2, "risk": 10.0}}
ok("#366 one more open bet after the tap: greyed again", set(E.overlap_games(allow=E.overlap_allow([f"{G1}~2~10"]), base=100.0, exposure=EXP2)) == {G1, G2})
EXP3 = {G1: {"n": 2, "risk": 14.0}, G2: {"n": 2, "risk": 10.0}}
ok("#366 more dollars at risk after the tap: greyed again", G1 in E.overlap_games(allow=E.overlap_allow([f"{G1}~2~10"]), base=100.0, exposure=EXP3))
EXP4 = {G1: {"n": 1, "risk": 4.0}}
ok("#366 exposure that fell is never greyed by the allow (the game is under the line)", E.overlap_games(allow=E.overlap_allow([f"{G1}~2~10"]), base=100.0, exposure=EXP4) == {})
al2 = E.overlap_allow([f"{G1}~3~30", f"{G1}~2~10"])
ok("#366 the same game sent twice keeps the stricter (lower) exposure", al2.at == {G1: (2, 10.0)}, al2.at)
ok("#366 the guard off means no guard, as before", (setattr(E, "overlap_settings", lambda: (False, 2, 8.0)) or E.overlap_games(base=100.0, exposure=EXP)) == {})
E.overlap_settings = lambda: (True, 2, 8.0)

rows = lambda sql="select kind, game, n, risk from overlap_log order by rowid": E.store_rows(sql)
E.store_x("drop table if exists overlap_log"); E._OV_SEEN.clear()
E.overlap_games(base=100.0, exposure=EXP)
E.overlap_games(base=100.0, exposure=EXP)
r = rows()
ok("#367 greyed games are logged once per exposure (a refresh does not repeat the row)", len(r) == 2 and {x["kind"] for x in r} == {"grey"}, r)
E.overlap_games(base=100.0, exposure=EXP2)
ok("#367 a changed exposure logs again", len(rows()) == 3)
E.overlap_games(allow=E.overlap_allow([f"{G1}~3~10"]), base=100.0, exposure=EXP2)
r = rows("select kind, game from overlap_log where kind='add'")
ok("#367 an Add anyway tap on a game that is over the line is logged as 'add'", len(r) == 1 and r[0]["game"] == G1, r)
E.STORE["db"], keep = None, E.STORE["db"]
try:
    E.overlap_games(base=100.0, exposure={G2: {"n": 9, "risk": 1.0}})
    fine = True
except Exception:
    fine = False
E.STORE["db"] = keep
ok("#367 no database: the guard still answers (logging never breaks the list)", fine)

# ---- #407: the closed-bet detail is cached (the function lives inside the web app's server, so its text is run on its own)
m = re.search(r"( *)CLOSED_CACHE = \{\}.*?\n(?= *def api_closed_work)", W, re.S)
ok("#407 the cache block is in the web app", bool(m))
if m:
    import textwrap
    CALLS = []
    ns = {"time": time, "COMBO_TICKER": re.compile(r"^[A-Za-z0-9._-]{3,120}$"),
          "api_closed_work": lambda t: (CALLS.append(t), {"found": t != "NOPE-1", "t": t})[1]}
    exec(textwrap.dedent(m.group(0)), ns)
    c = ns["api_closed"]
    c("KXMVE-AAA-1"); c("KXMVE-AAA-1"); c("KXMVE-AAA-1")
    ok("#407 three requests for one closed bet do one lookup", CALLS == ["KXMVE-AAA-1"], CALLS)
    ok("#407 a bad ticker is answered before the cache and never looked up", c("../etc") == {"found": False} and c("") == {"found": False} and len(CALLS) == 1)
    c("NOPE-1")
    ok("#407 a bet that wasn't found is cached too (briefly)", c("NOPE-1")["found"] is False and CALLS.count("NOPE-1") == 1)
    ns["CLOSED_CACHE"]["KXMVE-AAA-1"] = (time.time() - 100, ns["CLOSED_CACHE"]["KXMVE-AAA-1"][1])
    c("KXMVE-AAA-1")
    ok("#407 an old answer is looked up again", CALLS.count("KXMVE-AAA-1") == 2)
    for i in range(200):
        c(f"KXMVE-BBB-{i}")
    ok("#407 the cache stays bounded", len(ns["CLOSED_CACHE"]) <= ns["CLOSED_CACHE_MAX"], len(ns["CLOSED_CACHE"]))

# ---- #244: a calm note when a manual sell brings less than holding is worth (a warning only)
X = {"t": "KXNBAGAME-26NOV22AAABBB-AAA", "chance": 0.90, "label": "AAA to win", "kind": "game"}
E.single_sell_reason = lambda x, bid, ask, track=True: (None, 0.0)
note = E._sell_under_hold(X, 0.80, 0.82, 8.0, 10, 10)
ok("#244 selling under the chance-based hold value shows a note with the gap", bool(note) and "$1 under" in note and "You can still sell" in note, note)
ok("#244 at or above what holding is worth: no note", E._sell_under_hold(X, 0.90, 0.92, 9.0, 10, 10) is None)
E.single_sell_reason = lambda x, bid, ask, track=True: ("smart sell would sell this", 0.0)
ok("#244 when smart sell would sell it anyway: no note", E._sell_under_hold(X, 0.80, 0.82, 8.0, 10, 10) is None)
E.single_sell_reason = lambda x, bid, ask, track=True: (None, 9.5)
ok("#244 with a smart sell hold value, that value is the yardstick (scaled to the contracts sold)",
   "1.5" in (E._sell_under_hold(X, 0.80, 0.82, 8.0, 10, 10) or ""))
ok("#244 nothing held or nothing sellable: no note, no error", E._sell_under_hold(X, 0.8, 0.82, 0, 0, 0) is None)
E.single_sell_reason = lambda *a, **k: 1 / 0
try:
    quote_ok = E._sell_under_hold(X, 0.8, 0.82, 8.0, 10, 10)
    raised = False
except Exception:
    raised = True
ok("#244 the note helper is only display: single_sell_quote wraps it (a failure there never blocks)",
   'under = _sell_under_hold(x, bid, ask, got, n, have)\n    except Exception:\n        under = None' in open("wahome/engine.py").read())
