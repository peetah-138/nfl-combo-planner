# CHECK: group=engine
# Pete's refined rule (money-h): holding a WINNER bet on a game must not hide or block a TOTAL-points buy on the same
# game, and a spread and a total never block each other; a winner still blocks a spread (nearly the same bet), the same
# market never doubles up and the other side of the same market stays blocked. Checked on the panel's own choice
# (choose_panel), the extras filter, the Mac's saved "games Pete holds" file (note_held / account_held) and what
# build_panel leaves out. Combos are unchanged on purpose (an open question for Pete).
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.HELD_FILE = os.path.join(E.HERE, "held_events.json")
ok = lambda n, c, *x: print(("PASS " if c else "FAIL ") + n + ("" if c or not x else " :: " + repr(x)))
now = time.time()
tag = time.strftime("%y%b%d", time.gmtime(now)).upper()
GW = f"KXNFLGAME-{tag}DALNYG"            # the game's winner event
GS = f"KXNFLSPREAD-{tag}DALNYG"
GT = f"KXNFLTOTAL-{tag}DALNYG"


def leg(tk, ev, p=0.40, fair=0.50):
    return {"ticker": tk, "event": ev, "pick": tk, "p": p, "fair": fair}


def single(tk, ev, kind="single"):
    c = E._cand(kind, "nfl", [leg(tk, ev)], 0.5, 0.25, "w", price=0.40)
    c["kick"] = c["last"] = now + 3600
    return c


win_dal, win_nyg = single(f"{GW}-DAL", GW), single(f"{GW}-NYG", GW)
spread_dal = single(f"{GS}-DAL3", GS, "line")
total_over, total_under = single(f"{GT}-47", GT, "line"), single(f"{GT}-48", GT, "line")

# ---- families
ok("a winner and a spread are one family, a total its own",
   E.bet_family(f"{GW}-DAL") == E.bet_family(f"{GS}-DAL3") == "side" and E.bet_family(f"{GT}-47") == "total")
ok("a straight bet has one (game, family); a combo has none", E._fams_of(win_dal) == [(GW, "side")]
   and E._fams_of(total_over) == [(GW, "total")] and E._fams_of(dict(win_dal, kind="combo")) == [])

# ---- the panel's own choice: one straight bet per game AND family
E.rank_dollars = lambda: True
E._sim_panel = lambda items, n=3000, seed=7: [1.0 + 0.1 * len(items)] * 10
E._qualifies = lambda c: True
E._size = lambda c, base: 5.0


def pick(*cs):
    got, _ = E.choose_panel([dict(c) for c in cs], 100.0, 300.0, size=10)
    return sorted(c["id"] for c in got)


both = pick(win_dal, total_over)
ok("panel: a winner and a total on one game can both go in", len(both) == 2)
ok("panel: a spread and a total on one game can both go in", len(pick(spread_dal, total_over)) == 2)
ok("panel: a winner and a spread on one game still can't (one family)", len(pick(win_dal, spread_dal)) == 1)
ok("panel: the other team to win still can't be added", len(pick(win_dal, win_nyg)) == 1)
ok("panel: two totals on one game still can't (the same market)", len(pick(total_over, total_under)) == 1)

# ---- the extras filter: a live panel winner leaves a total open, still hides a spread and the winner
real = {"items": [dict(win_dal, state="bought")]}
left = [c["id"] for c in E._extras_filter([dict(c) for c in (total_over, spread_dal, win_nyg, win_dal)], real)]
ok("extras: with a winner riding, the total stays offered", left == [total_over["id"]])
real2 = {"items": [dict(total_over, state="bought")]}
left2 = [c["id"] for c in E._extras_filter([dict(c) for c in (win_dal, spread_dal, total_under)], real2)]
ok("extras: with a total riding, the winner and spread stay offered, another total doesn't",
   sorted(left2) == sorted([win_dal["id"], spread_dal["id"]]))
cmb = dict(E._cand("combo", "nfl", [leg(f"{GW}-DAL", GW), leg("KXNFLGAME-%sMIABUF-MIA" % tag, "KXNFLGAME-%sMIABUF" % tag)],
                   0.25, 0.1, "w"), kick=now + 3600, last=now + 3600)
ok("extras: a combo on that game is still left out beside a held winner (unchanged, open question)",
   E._extras_filter([cmb], real) == [])

# ---- the games Pete holds himself (the saved file the panel reads)
E.note_held({GW}, fams={GW + "|side"}, combo_events=set())
g, f = E.account_held()
ok("held file: a winner he holds blocks the side family only", g == set() and f == {(GW, "side")})
ok("held file: a combo he holds blocks the whole game", (E.note_held({GW}, fams=set(), combo_events={GW}), E.account_held())[1][0] == {GW})
E.save_json(E.HELD_FILE, {"at": now, "events": [GW]})      # an older file: everything blocks, as before
ok("held file: an older file without families blocks the whole game", E.account_held() == ({GW}, set()))
E.save_json(E.HELD_FILE, {"at": now - 7200, "events": [GW]})
ok("held file: a stale read blocks nothing, as before", E.account_held() == (set(), set()))

# ---- build_panel leaves out what he holds, but only the same family
E.note_held({GW}, fams={GW + "|side"}, combo_events=set())
E.account_held_orig = E.account_held
games, held_f = E.account_held()[0], E.account_held()[1]
ok("busy check: his winner hides the other team and a spread, not a total",
   E._busy_hit(win_nyg, games, held_f) and E._busy_hit(spread_dal, games, held_f) and not E._busy_hit(total_over, games, held_f))
ok("busy check: his total hides another total, not a winner or spread",
   E._busy_hit(total_under, set(), {(GW, "total")}) and not E._busy_hit(win_dal, set(), {(GW, "total")})
   and not E._busy_hit(spread_dal, set(), {(GW, "total")}))
E.PANEL_POOL.clear()
E.PANEL_POOL["nfl"] = (now, [dict(c, pct=9.9, prio=0.0) for c in (win_dal, total_over)])
E.sizing_base = lambda *a, **k: (300.0, None)
E.spent_earlier_today = lambda now=None: 0.0
E.day_items = lambda day, prefix="real": []
E.low_credit_filter = lambda items, now=None: (items, [])
E.smart_buy_filter = lambda items, now=None: (items, [])
E.sport_pay_index = lambda: {}
p = E.build_panel(codes=["nfl"])
ids = [c["id"] for c in p["items"]]
ok("build_panel: his held winner hides the winner pick, the total pick stays", total_over["id"] in ids and win_dal["id"] not in ids)

# ---- never both sides of one market: buy_single refuses when the account holds / has an order out on the other side
POS, ORDERS, SENT = [], [], []
E._positions_strict = lambda: list(POS)
E.order_blocks = lambda: []
E.hold_refusal = lambda *a, **k: (None, "")
E.RECENT_BUYS.clear()


def fake_send(method, path, body=None, params=None):
    if method == "GET":
        return {"orders": list(ORDERS)}
    SENT.append(body)
    return {"order": {"fill_count": body["count"], "status": "executed"}}


E.kalshi_send = fake_send


def pos(t, n):
    return {"ticker": t, "position_fp": str(n)}


def tries(t, recent=False):
    SENT.clear()
    if not recent:
        E.RECENT_BUYS.clear()                            # a fill sets it; each case starts clean
    got = E.buy_single(t, 3, 0.40)
    return got, bool(SENT)


POS[:] = [pos(f"{GW}-DAL", 5)]
(got, err), sent = tries(f"{GW}-NYG")
ok("holding DAL to win: buying NYG to win is refused, named by team, nothing sent", got == 0 and not sent
   and "already hold DAL to win" in err and "NYG to win was not bought" in err)
(got, err), sent = tries(f"{GT}-47")
ok("holding DAL to win: a total on the same game is still bought", got == 3 and sent and err is None)
(got, err), sent = tries(f"{GW}-DAL")
ok("holding DAL to win: the same side again is not this guard's business (unchanged)", got == 3 and sent)
(got, err), sent = tries(f"{GS}-NYG3")
ok("holding DAL to win: the other team's spread is refused too (one family)", got == 0 and not sent and "NYG to cover" in err)
POS[:] = [pos(f"{GW}-DAL", -5)]
(got, err), sent = tries(f"{GW}-DAL")
ok("holding NO on DAL (the other side of the same market): buying DAL YES is refused", got == 0 and not sent and "DAL not to win" in err)
POS[:] = [pos(f"{GT}-47", 4)]
(got, err), sent = tries(f"{GT}-47")
ok("holding the over: the same total again is untouched", got == 3 and sent)
POS[:] = [pos(f"{GT}-47", -4)]
(got, err), sent = tries(f"{GT}-47")
ok("holding the under (NO on the over): buying the over is refused", got == 0 and not sent and "the under" in err)
POS[:] = [pos(f"{GT}-47", 4)]
(got, err), sent = tries(f"{GT}-48")
ok("holding over 47 and buying over 48 is the same side (a total beside a total, not opposed)", got == 3 and sent)
POS[:] = [pos(f"{GS}-DAL3", 4)]
(got, err), sent = tries(f"{GT}-47")
ok("holding a spread: a total stays open", got == 3 and sent)
POS[:] = []
ORDERS[:] = [{"ticker": f"{GW}-DAL", "action": "buy", "side": "yes", "status": "resting"}]
(got, err), sent = tries(f"{GW}-NYG")
ok("an order waiting for DAL: NYG is refused", got == 0 and not sent and "order out for DAL to win" in err)
ORDERS[:] = [{"ticker": f"{GW}-DAL", "action": "sell", "side": "yes", "status": "resting"}]
(got, err), sent = tries(f"{GW}-NYG")
ok("a waiting SELL is not a holding", got == 3 and sent)
ORDERS[:] = []
E.order_blocks = lambda: [{"ticker": f"{GW}-DAL", "side": "YES", "key": "k", "sell": False, "until": 0, "why": ""}]
(got, err), sent = tries(f"{GW}-NYG")
ok("an order with no clear answer on DAL: NYG is refused", got == 0 and not sent and "no clear answer" in err)
E.order_blocks = lambda: []
E.RECENT_BUYS[f"{GW}-DAL"] = time.time()
(got, err), sent = tries(f"{GW}-NYG", recent=True)
ok("a DAL buy in the last minutes (position not shown yet): NYG is refused", got == 0 and not sent)
E.RECENT_BUYS.clear()
(got, err), sent = tries(f"{GW}-NYG")
ok("nothing held: the buy goes", got == 3 and sent)
E.RECENT_BUYS.clear()
E._positions_strict = lambda: (_ for _ in ()).throw(RuntimeError("down"))
(got, err), sent = tries(f"{GW}-NYG")
ok("positions can't be read: fails closed, nothing sent", got == 0 and not sent and "Couldn't check" in err)
E._positions_strict = lambda: list(POS)
E.kalshi_send = lambda m, p, b=None, params=None: (_ for _ in ()).throw(RuntimeError("down")) if m == "GET" else fake_send(m, p, b, params)
(got, err), sent = tries(f"{GW}-NYG")
ok("waiting orders can't be read: fails closed, nothing sent", got == 0 and not sent and "Couldn't check" in err)

# ======== round 2 (Pete): a combo with a leg against a single he holds is hidden and never bought =======
MIA = "KXNFLGAME-%sMIABUF" % tag
CHI = f"KXNFLGAME-{tag}CHIDET"


def cmb2(*legs, kind="combo"):
    return dict(E._cand(kind, "nfl", [leg(t, t.rsplit("-", 1)[0]) for t in legs], 0.25, 0.1, "w"), kick=now + 3600, last=now + 3600)


E.kalshi_send = fake_send
E._positions_strict = lambda: list(POS)
E.order_blocks = lambda: []
E.RECENT_BUYS.clear()
E.LIST_HELD.update(at=0.0, held=None)
POS[:] = [pos(f"{CHI}-CHI", 5)]                          # he holds Chicago to win
det_c, chi_c = cmb2(f"{CHI}-DET", f"{MIA}-MIA"), cmb2(f"{CHI}-CHI", f"{MIA}-MIA")
why = E.combo_contradiction([{"ticker": f"{CHI}-DET", "side": "yes"}, {"ticker": f"{MIA}-MIA"}])
ok("combo with Detroit to win while holding Chicago to win: refused, naming both teams",
   why and "CHI to win" in why and "DET to win" in why, why)
ok("combo with Chicago to win (same side) is fine", E.combo_contradiction([f"{CHI}-CHI", f"{MIA}-MIA"]) is None)
ok("combo with a total on that game is fine (a winner never blocks a total)", E.combo_contradiction([f"KXNFLTOTAL-{tag}CHIDET-47", f"{MIA}-MIA"]) is None)
ok("combo with Detroit's spread while holding Chicago to win: refused", E.combo_contradiction([f"KXNFLSPREAD-{tag}CHIDET-DET3"]) is not None)
ok("combo with NO on Chicago (a leg 'no' side): refused", E.combo_contradiction([{"ticker": f"{CHI}-CHI", "side": "no"}]) is not None)

# idea lists / panel pool / extras / best bets: hidden, singles untouched, one read for the list
E.LIST_HELD.update(at=0.0, held=None)
got = E.hide_contradicting([det_c, chi_c, single(f"{CHI}-DET", CHI)], lambda c: c["legs"])
ok("lists: the Detroit combo is hidden, the Chicago combo and a single stay", [c["id"] for c in got] == [chi_c["id"], single(f"{CHI}-DET", CHI)["id"]])
E.LIST_HELD.update(at=0.0, held=None)
ok("extras: a combo against his holding is left out", [c["id"] for c in E._extras_filter([det_c, chi_c], {"items": []})] == [chi_c["id"]])
E.LIST_HELD.update(at=0.0, held=None)
E.PANEL_POOL.clear()
E.PANEL_POOL["nfl"] = (now, [dict(c, pct=9.9, prio=0.0) for c in (det_c, chi_c)])
E.account_held = lambda max_age=1800: (set(), set())
p = E.build_panel(codes=["nfl"])
ids = [c["id"] for c in p["items"]]
ok("build_panel: the Detroit combo is not offered", det_c["id"] not in ids)
E.LIST_HELD.update(at=0.0, held=None)
E._positions_strict = lambda: (_ for _ in ()).throw(RuntimeError("429"))
ok("lists fail closed: unreadable bets hide every combo (singles stay)",
   E.hide_contradicting([det_c, chi_c, single(f"{CHI}-DET", CHI)], lambda c: c["legs"])[0]["kind"] != "combo"
   and len(E.hide_contradicting([det_c, chi_c, single(f"{CHI}-DET", CHI)], lambda c: c["legs"])) == 1)
E._positions_strict = lambda: list(POS)

# live ideas (the Live page's Buy ideas)
E.LIST_HELD.update(at=0.0, held=None)
E.live_suggestions = lambda **k: [{"legs": [f"{CHI}-DET", f"{MIA}-MIA"], "live": 0, "legs_info": [], "pct": 1.1, "profit": 1.0, "ts": now},
                                  {"legs": [f"{CHI}-CHI", f"{MIA}-MIA"], "live": 0, "legs_info": [], "pct": 1.1, "profit": 1.0, "ts": now}]
E._idea_state = lambda now=None: {"bought": [], "items": {}}
E._held_idea_markets = lambda: (set(), set())
E.low_credit_ideas = lambda out, now=None: (out, 0)
E.smart_buy_ideas_gate = lambda out, now=None: (out, 0)
E._idea_below_bar = lambda r: False
E._idea_history = lambda keys, now: {}
ideas = E.live_ideas()
ok("live ideas: the Detroit combo idea is hidden, the Chicago one stays",
   [r["legs"][0] for r in ideas] == [f"{CHI}-CHI"], [r["legs"] for r in ideas])

# the buy path: accept_offer refuses before anything is accepted, and drops the quote request
SENT.clear()
CALLS = []
E.kalshi_send = lambda m, p, b=None, params=None: (CALLS.append((m, p)), fake_send(m, p, b, params))[1]
E.CTX["offers"] = {1: {"rfq": "R1", "quote": "Q1", "pays": 20.0, "market": "KXMVE-X", "price": 0.4, "stake": 8.0, "p": 0.3,
                       "legs": [f"{CHI}-DET", f"{MIA}-MIA"]}}
E.trading_paused = lambda: False
r = E.accept_offer(1, skip_cap=True)
ok("accept_offer: a combo with Detroit to win is refused, named, never accepted",
   r.get("error") and "CHI to win" in r["error"] and not any(m == "PUT" for m, _ in CALLS)
   and any(m == "DELETE" and "R1" in p for m, p in CALLS) and 1 not in E.CTX["offers"], r)
POS[:] = []
E.CTX["offers"] = {1: {"rfq": "R2", "quote": "Q2", "pays": 20.0, "market": "KXMVE-X", "price": 0.4, "stake": 8.0, "p": 0.3,
                       "legs": [f"{CHI}-DET", f"{MIA}-MIA"]}}
E.rfq_unsure = lambda *a, **k: False
E.ACCEPT_WAIT = 0
CALLS.clear()
E.accept_offer(1, skip_cap=True)
ok("accept_offer: nothing held, the accept goes out", any(m == "PUT" for m, _ in CALLS))
POS[:] = [pos(f"{CHI}-CHI", 5)]
E._positions_strict = lambda: (_ for _ in ()).throw(RuntimeError("down"))
E.CTX["offers"] = {1: {"rfq": "R3", "quote": "Q3", "pays": 20.0, "market": "KXMVE-X", "price": 0.4, "stake": 8.0, "p": 0.3,
                       "legs": [f"{CHI}-CHI", f"{MIA}-MIA"]}}
CALLS.clear()
E.unread_take()
r = E.accept_offer(1, skip_cap=True)
ok("accept_offer: bets unreadable fails closed, flagged as 'couldn't check'", "Couldn't check" in (r.get("error") or "")
   and not any(m == "PUT" for m, _ in CALLS) and E.unread_take())
E._positions_strict = lambda: list(POS)

# the panel's combo buy: no quote is even asked for
POS[:] = [pos(f"{CHI}-CHI", 5)]
E.get_offer = lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked Kalshi for a price"))
okb, note, d = E._buy_panel_bet(dict(det_c, stake=5.0, fair_mult=4.0, code="nfl"))
ok("panel combo buy: refused before any quote", okb is False and "CHI to win" in note)

# ======== standing orders (maker_mode 'on') ========
SENT.clear()
POS[:] = [pos(f"{GW}-DAL", 5)]
E.kalshi_send = fake_send
try:
    E._maker_post(f"{GW}-NYG", 3, 0.40, now + 3600); posted = True
except RuntimeError as err:
    posted = False
ok("maker 'on': a standing buy of the other side is refused, nothing posted", not posted and not SENT)
POS[:] = []
ok("maker 'on': nothing held, it posts", E._maker_post(f"{GW}-NYG", 3, 0.40, now + 3600) is None and len(SENT) == 1)
E._positions_strict = lambda: (_ for _ in ()).throw(RuntimeError("down"))
SENT.clear()
try:
    E._maker_post(f"{GW}-NYG", 3, 0.40, now + 3600); posted = True
except RuntimeError:
    posted = False
ok("maker 'on': unreadable bets fail closed", not posted and not SENT)
E._positions_strict = lambda: list(POS)

# ======== waiting orders: more than 200 are paged through, or it fails closed ========
POS[:] = []
PAGES = {None: {"orders": [], "cursor": "c2"},
         "c2": {"orders": [{"ticker": f"{GW}-DAL", "action": "buy", "side": "yes", "status": "resting"}], "cursor": ""}}


def paged(m, p, b=None, params=None):
    if m == "GET":
        return PAGES[(params or {}).get("cursor")]
    SENT.append(b)
    return {"order": {"fill_count": b["count"], "status": "executed"}}


E.kalshi_send = paged
(got, err), sent = tries(f"{GW}-NYG")
ok("waiting orders: an order on page 2 still blocks the other side", got == 0 and not sent and "order out for DAL" in err)
E.kalshi_send = lambda m, p, b=None, params=None: {"orders": [], "cursor": "more"} if m == "GET" else fake_send(m, p, b, params)
(got, err), sent = tries(f"{GW}-NYG")
ok("waiting orders: pages that never end fail closed", got == 0 and not sent and "Couldn't check" in err)

# ======== a panel bet refused for 'couldn't check' goes back to scheduled, not failed ========
import json
E.kalshi_send = fake_send
E.store_x("delete from panel")
E.PANEL_POOL.clear()
E.PANEL_POOL["nfl"] = (now, [dict(single(f"{GT}-47", GT), pct=9.9, prio=0.0)])
E.panel_pass(); E.panel_approve(None, "all")
pp = E.panel_get("real")
ok("panel: a bet is scheduled to start with", pp and pp["items"][0]["state"] == "scheduled")
E.book_depth = lambda t, max_age=5: {"ask": 0.40, "bid": 0.38}
E.news_gap = lambda *a, **k: None
E.can_trade = lambda *a, **k: True
E.base_unread = lambda: False
E.trading_paused = lambda: False
E._positions_strict = lambda: (_ for _ in ()).throw(RuntimeError("429 slow down"))
for c in pp["items"]:
    c.update(buy_at=now - 10)
E.store_x("update panel set body=? where mode='real'", (json.dumps(pp),))
E.panel_exec(paused=False)
it = E.panel_get("real")["items"][0]
ok("panel: refused for 'couldn't check' goes back to scheduled (not failed for good)",
   it["state"] == "scheduled" and it.get("hold") == "bets" and "Couldn't check" in it.get("note", ""), (it["state"], it.get("note")))
E._positions_strict = lambda: list(POS)
E.panel_exec(paused=False)
it = E.panel_get("real")["items"][0]
ok("panel: next pass, bets readable, it buys", it["state"] == "bought", (it["state"], it.get("note")))
