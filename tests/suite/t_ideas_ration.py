# CHECK: group=engine
# Live "Buy ideas": ranked by expected dollars, rationed, dismissable (GitHub #141). Display and filtering only.
# Covers: the order (expected profit in dollars at the suggested stake, best first; ideas under the quality bar last),
# a stable idea_id/key that survives a re-offer, 'below the bar' marks, the 'Buy ideas shown' setting (default 3,
# clamped 1-10), a price older than two minutes marked stale, a pre-game idea whose game has started dropped, dismissals
# (persisted in a small file, applied to the next read, ignored for an id the Mac doesn't know, back when the edge
# improves 3+ points or the price drops 2+ cents, gone for the day, undone by Undo), bought ideas that never come back,
# and that the dismissal file matches the gitignored combo_*.json pattern. Nothing here prices or buys anything.
import os, time, tempfile, importlib.util, json, fnmatch
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.injury_note = lambda code, *teams, hours=48: ([], False)   # no injury news: never ESPN's real report (netguard)
E.game_context = lambda code, *teams: []   # no back-to-back/weather notes from ESPN's real scoreboard (netguard)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.IDEA_DISMISS = os.path.join(E.HERE, "combo_idea_dismiss.json")
E.MAIN_SAVED = os.path.join(E.HERE, "no_such_main_settings.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
import datetime as dt
iso = lambda secs: (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=secs)).isoformat()
D = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=5)).strftime("%y%b%d").upper()
E.LEAGUE["code"] = "nba"
E.CFG["accept_pct"] = 95
now = time.time()


def single(tag, stake, pays, pct, game="NBAGAME"):
    ev = f"KXNBAGAME-{D}{tag}"
    tk = f"{ev}-{tag[:3]}"
    E.KICKOFF[ev] = iso(7200)
    E.PICK_NAME[tk] = tag
    return tk, E.store_suggestion({"legs": [{"ticker": tk, "event": ev, "pick": tag, "p": .3, "fair": .4}], "fair": 25.0},
                                  {"pays": float(pays), "stake": stake}, pct)


def combo(a, b, stake, pays, pct):
    legs = []
    for tag in (a, b):
        ev = f"KXNBAGAME-{D}{tag}"
        E.KICKOFF[ev] = iso(7200)
        legs.append({"ticker": f"{ev}-{tag[:3]}", "event": ev, "pick": tag, "p": .5, "fair": .6})
    return [l["ticker"] for l in legs], E.store_suggestion({"legs": legs, "fair": 30.0}, {"pays": float(pays), "stake": stake}, pct)


tA, sA = single("AAAXXX", 6.0, 20, 1.10)      # +$0.60
tB, sB = single("BBBXXX", 3.0, 10, 1.30)      # +$0.90  (best: the biggest edge in dollars)
tC, sC = single("CCCXXX", 10.0, 30, 1.08)     # +$0.80
(c1, c2), sD = combo("DDDXXX", "FFFXXX", 5.0, 40, 0.97)   # -$0.15, a combo at 97% (clears the 95% bar)
tE, sE = single("EEEXXX", 4.0, 12, 0.98)      # -$0.08, no edge left after the fee: below the bar

info = {}
ideas = E.live_ideas(info=info)
names = [r["picks"] for r in ideas]
ok("ranked by expected dollars, best first; the one under the bar last",
   names == ["BBBXXX", "CCCXXX", "AAAXXX", "DDDXXX + FFFXXX", "EEEXXX"])
ok("every idea carries rank 1..n, a stable idea_id, a key and its expected dollars",
   [r["rank"] for r in ideas] == [1, 2, 3, 4, 5] and all(r["idea_id"].startswith("i") and len(r["idea_id"]) == 13 and r["key"] for r in ideas)
   and abs(ideas[0]["ep"] - 0.9) < .01 and abs(ideas[3]["ep"] - (-0.15)) < .01)
ok("below the bar is marked (a single with no edge) and a combo at 97% clears 95%",
   [r["below_bar"] for r in ideas] == [False, False, False, False, True])
E.CFG["accept_pct"] = 98
ok("a combo under the 'price you'll accept' setting is marked too", [r for r in E.live_ideas() if r["n"] == 2][0]["below_bar"])
E.CFG["accept_pct"] = 95
ok("the best one is never hidden by the ranking itself (nothing dismissed, nothing cut under the pool)", len(ideas) == 5 and info["hidden"] == 0)

# ---- a re-offer of the same market keeps its id and key, whatever the new row's own id is
sB2 = E.store_suggestion({"legs": [{"ticker": tB, "event": f"KXNBAGAME-{D}BBBXXX", "pick": "BBBXXX", "p": .3, "fair": .4}], "fair": 25.0},
                         {"pays": 10.0, "stake": 3.0}, 1.30)
again = {r["picks"]: r for r in E.live_ideas()}["BBBXXX"]
ok("a re-offered idea keeps the same idea_id and key", again["idea_id"] == ideas[0]["idea_id"] and again["key"] == ideas[0]["key"])
ok("the list still has one card per market", len(E.live_ideas()) == 5)

# ---- the Buy ideas shown setting
ok("ideas shown: default 3", E.ideas_shown() == 3)
E.CFG["ideas_shown"] = 0
ok("ideas shown: clamped up to 1", E.ideas_shown() == 1)
E.CFG["ideas_shown"] = 99
ok("ideas shown: clamped down to 10", E.ideas_shown() == 10)
E.CFG["ideas_shown"] = "many"
ok("ideas shown: junk falls back to 3", E.ideas_shown() == 3)
E.CFG["ideas_shown"] = 5
ok("ideas shown: a good number is used", E.ideas_shown() == 5)
E.CFG["ideas_shown"] = 3
json.dump({"ideas_shown": 7}, open(E.MAIN_SAVED, "w"))
ok("ideas shown: the shared settings file wins (the web app and the Mac agree)", E.ideas_shown() == 7)
os.remove(E.MAIN_SAVED)

# ---- a price older than two minutes is stale (shown as refreshing), a fresh one is not
E.store_x("update suggestions set ts=? where id=?", (now - 400, sA))
st = {r["picks"]: r for r in E.live_ideas()}
ok("a price over two minutes old is marked stale, a fresh one is not", st["AAAXXX"]["stale"] and st["AAAXXX"]["age"] >= 399 and not st["BBBXXX"]["stale"])
E.store_x("update suggestions set ts=? where id=?", (now, sA))

# ---- a pre-game idea whose game has started is dropped (a live-priced idea is not)
E.store_x("insert into suggestions(id, ts, lg, legs, picks, n, pct, pays, stake, fair, kick, live, info) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
          ("started1", now, "nba", json.dumps(["KXNBAGAME-" + D + "GGGXXX-GGG"]), "GGGXXX", 1, 1.2, 10.0, 5.0, 20.0, None, 0,
           json.dumps([{"ticker": "KXNBAGAME-" + D + "GGGXXX-GGG", "kind": "win", "pick": "GGGXXX", "game": "", "plain": "GGGXXX to win", "kick": now - 600}])))
ok("a pre-game idea whose game has started is dropped", "GGGXXX" not in [r["picks"] for r in E.live_ideas()])
E.store_x("delete from suggestions where id='started1'")

# ---- dismiss: persisted, applied to the next read, ignored for an unknown id
top = E.live_ideas()[0]
r = E.idea_dismiss([top["idea_id"], "i000000000000", "nonsense"])
ok("dismissing hides the idea and reports how many it hid (an id it doesn't know is ignored)", r["n"] == 1 and r["ids"] == [top["idea_id"]])
after = E.live_ideas(info=info)
ok("a dismissed idea is gone from the next read and counted as waiting", top["picks"] not in [x["picks"] for x in after] and info["hidden"] == 1 and len(after) == 4)
saved = json.load(open(E.IDEA_DISMISS))
ok("it is saved in a small file (survives a reload, shared by every device)",
   top["key"] in saved["items"] and saved["day"] == time.strftime("%Y-%m-%d") and saved["items"][top["key"]]["price_c"] == top["price_c"])
ok("that file matches the gitignored combo_*.json pattern", fnmatch.fnmatch(os.path.basename(E.IDEA_DISMISS), "combo_*.json"))
ok("a fresh read of the file (as after a restart) still hides it", E._idea_state()["items"].get(top["key"]) is not None)

# ---- comes back only when the edge improves 3+ points or the price drops 2+ cents
E.store_suggestion({"legs": [{"ticker": tB, "event": f"KXNBAGAME-{D}BBBXXX", "pick": "BBBXXX", "p": .3, "fair": .4}], "fair": 25.0},
                   {"pays": 10.0, "stake": 3.0}, 1.31)                 # edge +1 point: still hidden
ok("a 1-point better edge doesn't bring it back", top["picks"] not in [x["picks"] for x in E.live_ideas()])
E.store_suggestion({"legs": [{"ticker": tB, "event": f"KXNBAGAME-{D}BBBXXX", "pick": "BBBXXX", "p": .3, "fair": .4}], "fair": 25.0},
                   {"pays": 10.0, "stake": 2.9}, 1.31)                 # price 29c vs 30c: 1 cent cheaper, still hidden
ok("a 1-cent cheaper price doesn't bring it back either", top["picks"] not in [x["picks"] for x in E.live_ideas()])
E.store_suggestion({"legs": [{"ticker": tB, "event": f"KXNBAGAME-{D}BBBXXX", "pick": "BBBXXX", "p": .3, "fair": .4}], "fair": 25.0},
                   {"pays": 10.0, "stake": 3.0}, 1.34)                 # edge +4 points
ok("an edge 3+ points better brings it back", top["picks"] in [x["picks"] for x in E.live_ideas()])
ok("and the dismissal is cleared (it isn't hidden again if the edge slips)", top["key"] not in E._idea_state()["items"])
# a price drop of 2+ cents, on its own market
tH, sH = single("HHHXXX", 3.4, 10, 1.30)                              # 34c
E.idea_dismiss([E.idea_id([tH])])
ok("the new idea is hidden once dismissed", "HHHXXX" not in [x["picks"] for x in E.live_ideas()])
E.store_suggestion({"legs": [{"ticker": tH, "event": f"KXNBAGAME-{D}HHHXXX", "pick": "HHHXXX", "p": .3, "fair": .4}], "fair": 25.0},
                   {"pays": 10.0, "stake": 3.15}, 1.301)               # 31.5c: 2.5 cents cheaper, the same edge
ok("a price 2+ cents lower brings it back", "HHHXXX" in [x["picks"] for x in E.live_ideas()])
E.store_x("delete from suggestions where legs=?", (json.dumps([tH]),))
E.store_x("update suggestions set pct=pct")
E.idea_undismiss(everything=True)

# ---- tomorrow: 'Not now' means until tomorrow
E.idea_dismiss(everything=True)
ok("Clear all hides everything on the list", E.live_ideas() == [])
ok("a new day starts the dismissals over", len(E.live_ideas(now=time.time() + 86400)) == 5)

# ---- Undo
ids = [E.idea_id([tA]), E.idea_id([tC])]
u = E.idea_undismiss(ids)
ok("Undo brings those ideas back (and only those)", u["n"] == 2 and sorted(x["picks"] for x in E.live_ideas()) == ["AAAXXX", "CCCXXX"])
ok("show them again brings everything back", E.idea_undismiss(everything=True)["n"] == 3 and len(E.live_ideas()) == 5)

# ---- bought ideas never come back, even after a big improvement or the next day
bid = E.idea_id([tA])
E.idea_dismiss([bid], bought=True)
E.store_suggestion({"legs": [{"ticker": tA, "event": f"KXNBAGAME-{D}AAAXXX", "pick": "AAAXXX", "p": .2, "fair": .5}], "fair": 25.0},
                   {"pays": 20.0, "stake": 4.0}, 1.60)                 # a far better price
ok("a bought idea is gone, and a better price for the same market doesn't bring it back", "AAAXXX" not in [x["picks"] for x in E.live_ideas()])
ok("nor tomorrow", "AAAXXX" not in [x["picks"] for x in E.live_ideas(now=time.time() + 86400)])
ok("nor does Undo or 'show them again' bring a bought one back", E.idea_undismiss(everything=True) and "AAAXXX" not in [x["picks"] for x in E.live_ideas()])
ok("a bought idea is forgotten after a few days", E._idea_state(now=time.time() + 4 * 86400)["bought"] == {})

# ---- a broken file never breaks the list
open(E.IDEA_DISMISS, "w").write("{not json")
ok("a broken dismissal file reads as nothing dismissed", len(E.live_ideas()) >= 4)
open(E.IDEA_DISMISS, "w").write(json.dumps({"day": time.strftime("%Y-%m-%d"), "items": [1, 2], "bought": "x"}))
ok("a wrong-shaped dismissal file is ignored too", len(E.live_ideas()) >= 4)

# ---- review fixes: the newest quote is the one ranked and dated; an idea you already hold is dropped; Clear all clears the whole pool
os.remove(E.IDEA_DISMISS)
tN, sN = single("NNNXXX", 5.0, 20, 1.50)                                  # an old, rich quote...
E.store_x("update suggestions set ts=? where id=?", (now - 1800, sN))
single("NNNXXX", 5.0, 20, 1.04)                                            # ...then a newer, poorer one
nn = [r for r in E.live_ideas() if r["picks"] == "NNNXXX"][0]
ok("the newest quote of a market is the one ranked and dated (not its best of the hour)", abs(nn["edge"] - 0.04) < .001 and nn["age"] < 60 and not nn["stale"])
E.MINE["view"] = {"singles": [{"t": tC, "state": "pre"}], "combos": [{"group": "pending", "legs": [{"ticker": c2}, {"ticker": c1}]}]}
held = [r["picks"] for r in E.live_ideas()]
ok("an idea for a single you already hold is dropped", "CCCXXX" not in held and "BBBXXX" in held)
ok("so is a combo whose picks you already hold as a combo", not any(p.startswith("DDDXXX") for p in held))
E.MINE.pop("view")
ok("with nothing known to be held they all show again", "CCCXXX" in [r["picks"] for r in E.live_ideas()])
for i in range(20):
    single(f"Z{i:02d}XXX", 3.0, 10, 1.20 + i / 1000)
total = len(E.live_suggestions(limit=E.IDEA_POOL, newest=True))
ok("the page gets at most IDEA_KEEP ideas", len(E.live_ideas()) == E.IDEA_KEEP)
r = E.idea_dismiss(everything=True)
ok("Clear all clears the whole ranked pool, not just the top few", r["n"] == min(total, E.IDEA_POOL) and r["n"] > E.IDEA_KEEP and E.live_ideas() == [])
