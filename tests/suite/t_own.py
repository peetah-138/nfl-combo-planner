import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.HELD_FILE = os.path.join(E.HERE, "held.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)

# --- which bets the app bought ---
E.seed_origins(["KXMVEOLD-1", "KXNBAGAME-26NOV18LALBOS-LAL"])
ok("bets held before tracking count as the app's", not E.is_own("KXMVEOLD-1") and not E.is_own("KXNBAGAME-26NOV18LALBOS-LAL"))
E.note_app_order("POST", "/portfolio/orders", {"ticker": "KXNFLSPREAD-26NOV22BUFKC-KC7", "action": "buy", "side": "yes"})
E.note_app_order("POST", "/communications/rfqs", {"market_ticker": "KXMVEAPP-2"})
E.note_app_order("POST", "/portfolio/orders", {"ticker": "KXNHLGAME-26NOV18SJSVGK-SJS", "action": "sell", "side": "yes"})
ok("app buys and combo requests are the app's", not E.is_own("KXNFLSPREAD-26NOV22BUFKC-KC7") and not E.is_own("KXMVEAPP-2"))
ok("a sell doesn't make a bet the app's", E.is_own("KXNHLGAME-26NOV18SJSVGK-SJS"))
ok("a new bet placed on Kalshi is yours", E.is_own("KXMVEMINE-3"))
ok("seeding happens only once", (E.seed_origins(["KXMVEMINE-3"]) or True) and E.is_own("KXMVEMINE-3"))
E.SELF_SELL = os.path.join(E.HERE, "selfsell.json")
ok("smart sell watches every bet by default, yours too", not E.hands_off("KXMVEMINE-3") and not E.hands_off("KXMVEAPP-2"))
E.set_self_sell("KXMVEMINE-3", True)
ok("...except one you set to I'll sell it", E.hands_off("KXMVEMINE-3") and not E.hands_off("KXMVEAPP-2"))

# --- auto cash-out skips your own combos ---
asked = []
E.CFG["auto_sell"] = True; E.can_trade = lambda: True
E.MINE["hold"] = {t: {"label": t, "p": .6, "pays": 20, "cost": 5, "hold": 12, "won_some": True, "legs_left": []}
                  for t in ("KXMVEMINE-3", "KXMVEAPP-2")}
E.MINE["cash"] = {}
E.take_profit_reason = lambda t, h, cut_ok=False: ("take profit", 6.0)
E.get_cash_offer = lambda t, f: asked.append(t) or {"offer": 0}
E.fetch_account = lambda **k: ([], 300.0, None)
E.auto_sell_now({"acts": {"KXMVEMINE-3": 1.0, "KXMVEAPP-2": 0}})
ok("auto cash-out never looks at a combo set to I'll sell it", "KXMVEMINE-3" not in asked and "KXMVEAPP-2" in asked)

# --- singles and spreads on Live ---
now = time.time()
E.ACCT_POS.update(at=now, items=[
    {"ticker": "KXNFLSPREAD-26NOV22BUFKC-KC7", "position_fp": "10", "market_exposure_dollars": "5.20"},
    {"ticker": "KXNFLTOTAL-26NOV22BUFKC-45", "position_fp": "-4", "market_exposure_dollars": "2.10"},
    {"ticker": "KXNHLGAME-26NOV18SJSVGK-SJS", "position_fp": "6", "market_exposure_dollars": "3.00"},
    {"ticker": "KXMVEAPP-2", "position_fp": "30", "market_exposure_dollars": "3.00"},
    {"ticker": "KXNBAGAME-26NOV18LALBOS-LAL", "position_fp": "0", "market_exposure_dollars": "0"}])
MK = {"KXNFLSPREAD-26NOV22BUFKC-KC7": {"ticker": "KXNFLSPREAD-26NOV22BUFKC-KC7", "event_ticker": "KXNFLSPREAD-26NOV22BUFKC",
          "title": "Buffalo at Kansas City: Spread", "yes_sub_title": "Kansas City wins by over 6.5 points", "status": "active",
          "yes_bid_dollars": "0.70", "yes_ask_dollars": "0.74", "no_bid_dollars": "0.26"},
      "KXNFLTOTAL-26NOV22BUFKC-45": {"ticker": "KXNFLTOTAL-26NOV22BUFKC-45", "event_ticker": "KXNFLTOTAL-26NOV22BUFKC",
          "title": "Buffalo at Kansas City: Total Points", "yes_sub_title": "Over 45.5 points scored", "status": "active",
          "yes_bid_dollars": "0.60", "yes_ask_dollars": "0.64", "no_bid_dollars": "0.36"},
      "KXNHLGAME-26NOV18SJSVGK-SJS": {"ticker": "KXNHLGAME-26NOV18SJSVGK-SJS", "event_ticker": "KXNHLGAME-26NOV18SJSVGK",
          "title": "San Jose vs Vegas Winner?", "yes_sub_title": "San Jose", "status": "active",
          "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.44", "no_bid_dollars": "0.56"}}
class R:
    def __init__(s, d): s.d = d; s.ok = True
    def raise_for_status(s): pass
    def json(s): return s.d
asked_mk = []
def fake_get(url, params=None, timeout=None):
    asked_mk.append(params)
    return R({"markets": [MK[t] for t in (params or {}).get("tickers", "").split(",") if t in MK]})
E.requests.get = fake_get
E.fetch_scores = lambda **k: {}
def fake_score(l):
    t = l["ticker"]
    if t.startswith("KXNFLGAME-26NOV22BUFKC-KC"):
        return {"state": "in", "me": 24, "opp": 14, "abbr": "KC", "opp_abbr": "BUF", "detail": "Q3 4:12", "ball": False, "frac": 0.32}
    if t.startswith("KXNHLGAME"):
        return {"state": "pre", "me": 0, "opp": 0, "abbr": "SJ", "opp_abbr": "VGK", "detail": "", "ball": False}
    return None
E.leg_score = fake_score
E.SINGLES["at"] = 0
ss = {x["t"]: x for x in E.open_singles()}
ok("combos and closed positions stay out of singles", set(ss) == {"KXNFLSPREAD-26NOV22BUFKC-KC7", "KXNFLTOTAL-26NOV22BUFKC-45", "KXNHLGAME-26NOV18SJSVGK-SJS"})
sp = ss["KXNFLSPREAD-26NOV22BUFKC-KC7"]
ok("spread: what you need, live, covering", sp["kind"] == "spread" and sp["state"] == "live" and sp["how"].startswith("Covering now · +10") and "6.5" in sp["how"])
ok("spread: worth now is what it would sell for", sp["worth"] == 7.0 and sp["pays"] == 10 and sp["cost"] == 5.2)
to = ss["KXNFLTOTAL-26NOV22BUFKC-45"]
ok(f"NO on a total reads as the under: 38 with 68% played is on pace for 56, over 45.5, so not on track (#238: the pace, not the running total) ({to['how']})", to["side"] == "no" and to["kind"] == "total" and to["how"].startswith("Not on track · 38 so far, on pace for 56") and abs(to["chance"] - .38) < .001)
hk = ss["KXNHLGAME-26NOV18SJSVGK-SJS"]
ok("moneyline single shows team to win, before the game", hk["label"] == "San Jose to win" and hk["state"] == "pre" and hk["how"] == "")
ok("singles show the origin tag", hk["t"] and (E.is_own(hk["t"])) and not E.is_own(sp["t"]))
n0 = len(asked_mk); E.open_singles(); ok("cached for half a minute", len(asked_mk) == n0)

# --- the opponent on a single (GitHub #95): from the score, name first then code; nothing when there is no score
ok("spread single: the opponent comes from the score's short code", sp["opp"] == "BUF")
ok("NHL single (before the game): the opponent still comes from the score, unchanged", hk["opp"] == "VGK")
E.ACCT_POS["items"] = E.ACCT_POS["items"] + [{"ticker": "KXNBAGAME-26NOV19BOSNYK-BOS", "position_fp": "5", "market_exposure_dollars": "2.50"}]
MK["KXNBAGAME-26NOV19BOSNYK-BOS"] = {"ticker": "KXNBAGAME-26NOV19BOSNYK-BOS", "event_ticker": "KXNBAGAME-26NOV19BOSNYK",
          "title": "Boston at New York Winner?", "yes_sub_title": "Boston", "status": "active",
          "yes_bid_dollars": "0.50", "yes_ask_dollars": "0.54", "no_bid_dollars": "0.46"}
E.SINGLES["at"] = 0
ss2 = {x["t"]: x for x in E.open_singles()}
nb = ss2.get("KXNBAGAME-26NOV19BOSNYK-BOS")
ok("a held NBA single with no score at all (not a Kalshi-live sport): opp is empty, src empty", nb is not None and nb["opp"] == "" and nb["src"] == "" and nb["sc"] is None)
ok("adding it changed nothing about the others' opponents", ss2["KXNFLSPREAD-26NOV22BUFKC-KC7"]["opp"] == "BUF" and ss2["KXNHLGAME-26NOV18SJSVGK-SJS"]["opp"] == "VGK")

# --- the panel steers clear of games you bet yourself ---
E.note_held({E.game_event(hk["event"])})
ok("games you bet yourself are kept from the panel", "KXNHLGAME-26NOV18SJSVGK" in E.account_events())
E.save_json(E.HELD_FILE, {"at": now - 4000, "events": ["X"]})
ok("old notes about your bets are ignored", E.account_events() == set())
