# CHECK: group=engine
import os, time, tempfile, importlib.util, json
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.SMART_FILE = os.path.join(E.HERE, "smart.json"); E.SMART_CACHE["at"] = 0
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
E.CFG["knobs_live"] = False; E.KNOB_SWITCH["on"] = None   # the weekly tuner as it runs with self-tuning off (#228 PR3)
now = time.time()
E.CFG.update(smart_sell=True, ride=2, take_profit=0, lock_trail=True)

ok("leagues: soccer by league, AHL apart from the NHL, college apart from the pros",
   E.league_key("KXEPLGAME-26NOV22ARSCHE-ARS") == "epl" and E.league_key("KXAHLGAME-26NOV191900HERCHA-HER") == "ahl"
   and E.league_key("KXNHLGAME-26NOV18SJSVGK-SJS") == "nhl" and E.league_key("KXNCAAMBGAME-26NOV18KANDUKE-KAN") == "ncaamb"
   and E.league_key("KXNBAGAME-26NOV18LALBOS-LAL") == "nba")
ok("a combo across leagues is 'mixed'", E.bet_key(["KXNBAGAME-1-A", "KXNHLGAME-1-B"]) == "mix")
ok("no data yet: the starting point (1.5x floor, no loss cutting)", E.smart_params(["KXNBAGAME-1-A"]) == {**E.SMART_DEFAULT, "key": None})
E.save_json(E.SMART_FILE, {"soccer": {"floor": 1.7, "lam": 1.0, "loss": None, "n": 40}, "epl": {"floor": 1.3, "n": 5}}); E.SMART_CACHE["at"] = 0
ok("a league short on data borrows its sport's settings", E.smart_params(["KXEPLGAME-26NOV22ARSCHE-ARS"])["floor"] == 1.7)
E.save_json(E.SMART_FILE, {}); E.SMART_CACHE["at"] = 0
E.CFG["ride"] = 0; a = E.ride_lam(); E.CFG["ride"] = 3; b = E.ride_lam(); E.CFG["ride"] = 4; c = E.ride_lam(); E.CFG["ride"] = 2
ok("Let it ride sets the boldness: Cautious sells sooner, Bold later, Ride it out switches smart sell off", a > 1 and b < 1 and c is None)

# 40 NBA singles that ran up to 78c then lost: a 1.4x floor would have banked them
def add_item(mode, i, code, path, won, scores=None):
    t = f"KX{code.upper()}GAME-26NOV{10 + i % 9:02d}T{i:03d}-AAA"
    kick = now - 86400 * 3 - i * 600
    for k, ch in enumerate(path):
        E.store_x("insert into ticks values(?,?,?,?,?)", (kick + 60 * (k + 1), t, ch, "sim", scores[k] if scores else "active"))
    return {"id": f"{mode}:{t}", "kind": "single", "code": code, "legs": [{"ticker": t, "p": .5, "pick": t}], "stake": 5.0,
            "price": .5, "paid": .5, "kick": kick, "state": "paper", "result": "won" if won else "lost",
            "pl": round(5 / (.5 + E.single_fee(.5)) - 5, 2) if won else -5.0}
items = [add_item("paper", i, "nba", [.52, .6, .7, .78, .6, .4, .2, 0.0], False) for i in range(40)]
# 40 NHL singles that slid all game, late in the game and for minutes on end (the loss cut's guards would let it cut)
NHL_SC = ["", "AAA 0–1 BBB P2 10:00", "AAA 0–2 BBB P2 2:00", "AAA 0–3 BBB P3 15:00", "AAA 0–3 BBB P3 14:00",
          "AAA 0–3 BBB P3 13:00", "AAA 0–3 BBB P3 12:00", "AAA 0–3 BBB P3 11:00", "AAA 0–4 BBB Final"]
items += [add_item("paper", 100 + i, "nhl", [.5, .4, .25, .12, .1, .08, .07, .06, 0.0], False, NHL_SC) for i in range(40)]
E._panel_table()
E.store_x("insert or replace into panel values(?,?,?,?,?)", ("2026-11-15", "paper", now - 86400 * 3, "paper", json.dumps({"at": now - 86400 * 3, "items": items})))
moved = E.smart_tune(force=True)
d = E.load_json(E.SMART_FILE, {})
ok("NBA: run-ups that fell back teach it to take profits a bit earlier", d["nba"]["floor"] == 1.4 and any("NBA" in m and "1.5× → 1.4×" in m for m in moved))
ok("NHL: bets that kept sliding teach it to cut losses there", d["nhl"]["loss"] == 0.15 and any("cut a loss" in m for m in moved))
ok("one small step, and only what made a difference (risk weight left alone)", d["nba"]["floor"] == 1.4 and d["nba"]["lam"] == 1.0)
ok("the reason is written down for Results", "returned" in d["nba"]["why"] and d["nba"]["n"] == 40)
ok("not again until next week", E.smart_tune() == [])
E.SMART_CACHE["at"] = 0
x = {"t": items[0]["legs"][0]["ticker"], "kind": "win", "sport": "nba", "side": "yes", "n": 9.6, "cost": 5.0, "chance": .78, "state": "live"}
why, fl = E.single_sell_reason(x, .76, .78, track=False)
ok("live: an NBA single at 76c now sells (learned 1.4x floor)", why == "smart" and abs(fl - 7.0) < .01)
y = {"t": items[45]["legs"][0]["ticker"], "kind": "win", "sport": "nhl", "side": "yes", "n": 9.6, "cost": 5.0, "chance": .12, "state": "live"}
why, fl = E.single_sell_reason(y, .11, .13, track=False)
ok("live: an NHL single under 15% is not cut until the loss guards have held (issue #27)", why is None)
why, fl = E.single_sell_reason(y, .11, .13, track=False, cut_ok=True)
ok("live: ...and once they have, it is cut (learned)", why == "cut loss")
z = dict(y, t="KXNBAGAME-26NOV18ZZZYYY-ZZZ")
why, fl = E.single_sell_reason(z, .11, .13, track=False, cut_ok=True)
ok("...but not in the NBA, whose record never showed it paying", why is None)
E.CFG["ride"] = 4
why, fl = E.single_sell_reason(x, .76, .78, track=False)
ok("Ride it out: smart sell stands down", why is None)
E.CFG["ride"] = 2
s = {r["key"]: r for r in E.smart_summary()}
ok("Results lists each league's settings", s["nba"]["floor"] == 1.4 and s["nhl"]["loss"] == 0.15 and s["nba"]["own"])
