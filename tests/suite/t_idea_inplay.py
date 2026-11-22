# CHECK: group=engine
# A single-game Buy idea's fresh price for a game UNDER WAY (GitHub #255, Pete's ruling: option 2). The fair chance comes
# only from live_side_fair (a live sportsbook line read in the last LIVE_LINE_AGE seconds, else the live model on a fresh
# score), never from the Build board's number (the pre-game price, or Kalshi's mid from when Build was built). With
# neither there is no fair price: no edge, no green Buy. Before the game nothing changes (the board's fair, exactly).
# Also: a finished game, a spread under way, Buy straight's live cautions (thin, nearly decided, far from the live
# chance), a combo idea with a game under way that the board only has pre-game for, and the web app's idea quote wired
# to it. Network = fakenet (the fake's first NBA game is under way, the second is final). Reads only: nothing is bought.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.set_league("nba")
E.hub_conf = lambda: None
import fakenet
fakenet.install(port=1)
G = fakenet.GAMES["KXNBAGAME"]
G[1], G[2] = G[2], G[1]                 # as t_singlebuy: Denver-LA third (not started), the second game final
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
mk = {m["ticker"]: m for m in fakenet.markets()}
EV = fakenet.event_ticker("KXNBAGAME", "DEN", "LAL")          # not started
T = EV + "-DEN"
LIVE_EV = fakenet.event_ticker("KXNBAGAME", "BOS", "NYK")     # under way
LT = LIVE_EV + "-BOS"
now = time.time()
BOOK = {"ask": 0.55, "bid": 0.53, "spread": 0.02, "ask_size": 500}
pre_side = {"ticker": T, "pick": "Denver Nuggets", "event": EV, "exp": mk[T]["expected_expiration_time"], "fair": 0.80,
            "src": "pinnacle"}
live_side = {"ticker": LT, "pick": "Boston Celtics", "event": LIVE_EV, "exp": mk[LT]["expected_expiration_time"],
             "fair": 0.80, "src": "pinnacle"}
ok("the fake's first game is under way, the Denver game isn't", E.started(live_side) and not E.started(pre_side))

# ---- before the game: unchanged (the board's own fair, to the digit)
f = E.idea_single_fair(T, pre_side, 0.71, BOOK)
ok(f"pregame: the board's fair exactly (0.80), labelled sportsbooks, not live ({f})",
   f["fair"] == 0.80 and f["src"] == "sportsbooks" and not f["live"] and not f["warn"] and not f["over"])
f = E.idea_single_fair(T, None, 0.71, BOOK)
ok(f"pregame with no board side: the idea's own chance as before (0.71, {f['src']})", f["fair"] == 0.71 and not f["live"])
f = E.idea_single_fair(T, dict(pre_side, src=None, fair=0.6), None, BOOK)
ok("pregame with Kalshi's own chance on the board: said so", f["fair"] == 0.6 and f["src"] == "Kalshi's price")

# ---- under way with a fresh live sportsbook line: that line, said so
fresh = dict(live_side, fair=0.66, line_live=True, line_at=now - 30)
f = E.idea_single_fair(LT, fresh, 0.80, BOOK)
ok(f"under way, live line 30 s old: its 66%, 'live line' ({f['fair']}, {f['src']})",
   f["live"] and f["fair"] == 0.66 and f["src"] == "live line" and f["how"] == "live sportsbook line")
ok("under way: the first caution says it is live and names the source", f["warn"] and f["warn"][0]["k"] == "live"
   and "live line" in f["warn"][0]["t"])

# ---- a live line older than LIVE_LINE_AGE is never used: the live model on the score instead
stale = dict(fresh, line_at=now - E.LIVE_LINE_AGE - 60, pre=0.62)
f = E.idea_single_fair(LT, stale, 0.80, BOOK)
ok(f"under way, live line {E.LIVE_LINE_AGE + 60} s old: rejected, the live model ({f['fair']}, {f['src']})",
   f["live"] and f["src"] == "live model" and f["fair"] is not None and f["fair"] not in (0.66, 0.80))

# ---- the live model on a fresh score (board fair = pre-game 80%: never used)
f = E.idea_single_fair(LT, dict(live_side, pre=0.62), 0.80, BOOK)
ok(f"under way, no live line: the live model from the closing line, never the board's 80% ({f['fair']})",
   f["live"] and f["src"] == "live model" and f["fair"] is not None and f["fair"] != 0.80)
same = E.live_side_fair(dict(live_side, ticker=LT, pre=0.62))[0]
ok(f"... exactly what Buy straight's live_side_fair gives ({same})", f["fair"] == round(same, 4))

# ---- neither: no fair price at all
E.CLOSING = os.path.join(E.HERE, "none.json")
f = E.idea_single_fair(LT, live_side, 0.80, BOOK)
ok(f"under way, no live line and no closing line: no fair price, 'none' ({f['nofair']})",
   f["live"] and f["fair"] is None and f["src"] == "none" and f["nofair"] and f["how"] is None)
ok("... the caution says Kalshi's price alone", "Kalshi's price alone" in f["warn"][0]["t"])
saved = E.score_age
E.score_age = lambda sport, now=None: E.LIVE_SCORE_AGE + 5
f = E.idea_single_fair(LT, dict(live_side, pre=0.62), 0.80, BOOK)
ok(f"under way, score feed stale: no fair price, never the board's ({f['nofair']})", f["fair"] is None and f["live"])
E.score_age = saved
f = E.idea_single_fair(LT, None, 0.80, BOOK, row_live=True)
ok("under way with no board side at all: never the idea's pre-game 80%", f["live"] and f["fair"] is None)
f = E.idea_single_fair(T, pre_side, 0.71, BOOK, kick=now - 60)
ok("the idea's own start time has passed: treated as under way (never the board's pregame 80%)",
   f["live"] and f["fair"] != 0.80)

# ---- a spread under way: no live fair price
sp = fakenet.event_ticker("KXNBASPREAD", "BOS", "NYK") + "-BOS5"
f = E.idea_single_fair(sp, {"ticker": sp, "kind": "spread", "fair": 0.6, "event": LIVE_EV}, 0.6, BOOK, row_live=True)
ok(f"a spread under way: no fair price ({f['nofair']})", f["live"] and f["fair"] is None and "spreads" in f["nofair"])

# ---- a finished game: over (the web app answers 'gone', no quote)
FIN_EV = fakenet.event_ticker("KXNBAGAME", G[1][0], G[1][2])
FT = FIN_EV + "-" + G[1][0]
f = E.idea_single_fair(FT, {"ticker": FT, "event": FIN_EV, "fair": 0.7, "src": "pinnacle"}, 0.7, BOOK, row_live=True)
ok(f"a finished game: over, no fair price ({f})", f["over"] and f["fair"] is None)

# ---- Buy straight's live cautions
f = E.idea_single_fair(LT, fresh, 0.8, {"ask": 0.55, "bid": 0.45})
ok("under way, 10c gap: thin, with a caution", f["thin"] and any(w["k"] == "thin" for w in f["warn"]))
f = E.idea_single_fair(LT, fresh, 0.8, {"ask": 0.55, "bid": None})
ok("under way, nobody bidding: thin", f["thin"])
f = E.idea_single_fair(LT, fresh, 0.8, {"ask": 0.40, "bid": 0.38})
ok("under way, live chance 66% vs Kalshi's 39% mid: 'far apart' caution", any(w["k"] == "disagree" for w in f["warn"]))
f = E.idea_single_fair(LT, dict(fresh, fair=0.97), 0.8, {"ask": 0.96, "bid": 0.95})
ok("under way at 97%: 'nearly decided' caution", any(w["k"] == "decided" for w in f["warn"]) and not f["thin"])
f = E.idea_single_fair(T, pre_side, 0.71, {"ask": 0.55, "bid": 0.30})
ok("pregame, wide gap: unchanged (no new cautions before the game)", not f["warn"] and not f["thin"])

# ---- never raises
E_started = E.started
E.started = lambda s: (_ for _ in ()).throw(RuntimeError("x"))
f = E.idea_single_fair(T, pre_side, 0.71, BOOK)
ok("a start-time hiccup: still answers (before the game, as before)", f["fair"] == 0.80)
E.started = E_started
E_lsf = E.live_side_fair
E.live_side_fair = lambda *a, **k: (_ for _ in ()).throw(KeyError("x"))
f = E.idea_single_fair(LT, fresh, 0.8, BOOK)
ok("a live-score hiccup: no fair price, never the board's", f["live"] and f["fair"] is None and "couldn't" in f["nofair"])
E.live_side_fair = E_lsf

# ---- combos: a game under way that the board only has pre-game for
legs = [dict(pre_side), dict(live_side)]
ok("combo: a leg under way with the board's pre-game chance is named", E.idea_combo_live_gap(legs) == ["Boston Celtics"])
ok("combo: a leg under way the board priced live (screen_live: Kalshi's mid) is named too (no live_side_fair)",
   E.idea_combo_live_gap([dict(pre_side), dict(live_side, live=True)]) == ["Boston Celtics"])
ok("combo: nothing under way = nothing named", E.idea_combo_live_gap([dict(pre_side)]) == [])

# ---- the web app's idea quote uses it (the Build board's side is no longer the fair chance on its own)
W = open("wahome/combo_watcher.py", encoding="utf-8").read()
blk = W[W.index('if a == "idea":'):W.index('if a == "singlequote":')]
ok("the idea quote prices through idea_single_fair (live: live_side_fair only)", "A.idea_single_fair(tk, side" in blk
   and '(side or {}).get("fair") or row.get("pfair")' not in blk)
ok("the idea quote: no green Buy without a fair price, or under way when thin, nearly decided or far from Kalshi",
   'clears = fair is not None and edge >= A.SINGLE_MIN_EDGE * 0.6 and not (fi["live"] and doubt)' in blk
   and '("thin", "decided", "disagree")' in blk)
ok("the idea quote says where its fair chance came from", '"fair_src": fi["src"]' in blk and '"how": fi["how"]' in blk)
ok("the combo idea quote flags a game under way with only a pre-game chance", "A.idea_combo_live_gap(" in blk
   and "clears=False" in blk)
ok("the combo idea with no fair price is priced at the smallest usual stake, never sized on the pre-game edge",
   "combo_offer(k, own if small is None else small)" in blk and '"rec": small, "own": False' in blk)
ok("a live fair of exactly 0 is a fair price, not a crash (is not None, never truthiness)",
   "if fair else" not in blk.split('if row["n"] == 1')[1].split("if row[\"kick\"]")[0])
f = E.idea_single_fair(T, None, 0.71, BOOK)
ok(f"pregame with no board side: labelled honestly ({f['src']})", f["src"] == "from when it was found")

# ---- Build's live side (screen_live) holds Kalshi's mid with the odds' line_live/line_at still on it: never a "live line"
mid_side = dict(live_side, fair=0.71, line_live=True, line_at=time.time() - 20, live=True, pre=0.62)
f = E.idea_single_fair(LT, mid_side, 0.8, BOOK)
ok(f"a screen_live side's Kalshi mid is never taken as a live line (live model instead: {f['src']}, {f['fair']})",
   f["src"] == "live model" and f["fair"] != 0.71)
E.can_trade = lambda: True
E.book_depth = lambda tk, max_age=60: {"ask": 0.55, "bid": 0.53, "spread": 0.02, "ask_size": 500, "thin": False}
E.week_spend = lambda: 0.0
E.cap_combo_spend = lambda code, key, now=None: 0.0
E.CFG["kalshi_key_id"] = "fake-key-id"; E.CFG["budget"] = 100.0; E.CFG["bankroll"] = 400.0
bq = E.single_buy_quote(dict(mid_side, exp=mk[LT]["expected_expiration_time"]), 5)
ok(f"Buy straight: the same Kalshi mid is never a live line ({bq.get('how')})", bq.get("ok") and bq.get("how") == "live model")
bq = E.single_buy_quote(dict(live_side, fair=0.97, line_live=True, line_at=time.time() - 20), 5)
ok(f"Buy straight: a 97% live line = 'nearly decided', never green ({[w['k'] for w in bq.get('warn', [])]})",
   bq.get("ok") and any(w["k"] == "decided" for w in bq["warn"]) and not bq["clears"])
