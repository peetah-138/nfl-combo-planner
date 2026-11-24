# CHECK: group=engine
import os, time, tempfile, importlib.util, json
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp(); E.SELL_LOG = os.path.join(E.HERE, "sell.log")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()

def quote(pct, hours=3, legs=None, ts=None, stake=10, chance=0.25, outcome=None):
    legs = legs or [[f"KXNBAGAME-26NOV18A{pct:.3f}-X", .5, .52], [f"KXNBAGAME-26NOV18B{pct:.3f}-Y", .5, .5]]
    fair = stake / chance
    E.store_x("insert into quotes(ts, source, sport, n, legs, stake, pays, fair, kalshi, pct, hours, outcome) values(?,?,?,?,?,?,?,?,?,?,?,?)",
              (ts or now - 60, "shadow", "nba", len(legs), json.dumps(legs), stake, fair * pct, fair, fair * .9, pct, hours, outcome))

for pct in (0.81, 0.82, 0.83, 0.84, 0.86, 0.91, 0.97, 1.03, 0.75):
    quote(pct)
quote(0.88, hours=0.1)                        # starts in 6 minutes: too late
quote(0.89, legs=[["KXNBAGAME-26NOV18A0.860-X", .5, .52], ["KXNBAGAME-26NOV18B0.860-Y", .5, .5]])   # same combo as 0.86
n = E.lab_pass(now)
lab = E.panel_get("lab")
bands = {}
for c in lab["items"]:
    bands[c["band"]] = bands.get(c["band"], 0) + 1
ok("lab paper-buys combos in every band from 80%", set(bands) == {"80–85%", "85–90%", "90–95%", "95–100%", "100%+"})
ok("at most 3 a band a day", bands["80–85%"] == 3)
ok("never one whose game is about to start, never the same combo twice, nothing under 80%",
   bands["85–90%"] == 1 and not any(abs(c["pct"] - .75) < .001 for c in lab["items"]))
ok("lab bets are $5 paper bets at the quoted payout", all(c["stake"] == 5 and c["state"] == "paper" for c in lab["items"]))
ok("running again adds nothing new", E.lab_pass(now) == 0)

# game prices are recorded for open bets
c = next(x for x in lab["items"] if x["band"] == "95–100%")
t1, t2 = c["legs"][0]["ticker"], c["legs"][1]["ticker"]
body = E.panel_get("lab"); [x.update(kick=now - 600) for x in body["items"] if x["id"] == c["id"]]
E.store_x("update panel set body=? where mode='lab'", (json.dumps(body),))
class R:
    def __init__(s, d): s.d = d; s.ok = True
    def raise_for_status(s): pass
    def json(s): return s.d
asked = []
def fake_get(url, params=None, timeout=None):
    ts = (params or {}).get("tickers", "").split(",")
    asked.append(ts)
    return R({"markets": [{"ticker": t, "yes_bid_dollars": "0.60", "yes_ask_dollars": "0.62", "status": "active"} for t in ts]})
E.requests.get = fake_get
saved = E.lab_ticks(now)
ok("in-game prices recorded only for bets whose games are on", saved == 2 and set(asked[0]) == {t1, t2})

# smart-sell replay on a recorded path: both legs climb, so smart sell would have taken it
E.store_x("delete from ticks")
for i, (a, b) in enumerate([(.55, .55), (.75, .7), (.92, .9), (.97, .95)]):
    E.store_x("insert into ticks values(?,?,?,?,?)", (now - 500 + i * 60, t1, a, "sim", "active"))
    E.store_x("insert into ticks values(?,?,?,?,?)", (now - 500 + i * 60, t2, b, "sim", "active"))
c2 = dict(c, kick=now - 600)
sim = E.sim_exit(c2)
ok("replay: smart sell would have locked in a profit as both picks came good", sim and sim[1] == "smart" and sim[0] > 0)
E.store_x("delete from ticks")
for i, (a, b) in enumerate([(.5, .5), (.45, .4), (.3, .35), (.0, .2)]):
    E.store_x("insert into ticks values(?,?,?,?,?)", (now - 500 + i * 60, t1, a, "sim", "active"))
    E.store_x("insert into ticks values(?,?,?,?,?)", (now - 500 + i * 60, t2, b, "sim", "active"))
ok("replay: a combo that never got going just rides", E.sim_exit(c2) is None)
ok("replay needs a recorded path", E.sim_exit(dict(c2, legs=[{"ticker": "NOPE", "p": .5}])) is None)

# settling the lab records the result and the smart-sell replay
E.store_x("delete from ticks")
for i, (a, b) in enumerate([(.55, .55), (.75, .7), (.92, .9), (1, 1)]):
    E.store_x("insert into ticks values(?,?,?,?,?)", (now - 500 + i * 60, t1, a, "sim", "active"))
    E.store_x("insert into ticks values(?,?,?,?,?)", (now - 500 + i * 60, t2, b, "sim", "active"))
E.fetch_results = lambda ts: {t: "yes" for t in ts}
E.panel_settle()
done = next(x for x in E.panel_get("lab")["items"] if x["id"] == c["id"])
ok("lab bets settle with their result and the smart-sell replay", done.get("result") == "won" and done.get("sim_pl") is not None
   and done["pl"] == round(done["pays"] - 5, 2))

# analytics
for i in range(40):
    quote(0.9, ts=now - 86400 * 2 - i, outcome="won" if i % 3 == 0 else "lost")
E.store_x("insert into bets(combo, first_seen, cost, pays, legs, sports, status, back, settled) values(?,?,?,?,?,?,?,?,?)",
          ("C1", now - 9000, 5, 20, "[]", "nba", "cashed", 8, now - 3000))
E.store_x("insert into bets(combo, first_seen, cost, pays, legs, sports, status, back, settled) values(?,?,?,?,?,?,?,?,?)",
          ("C2", now - 9000, 5, 20, "[]", "nba", "lost", 0, now - 3000))
with open(E.SELL_LOG, "w") as f:
    f.write(json.dumps({"at": int(now), "result": "sold", "why": "smart"}) + "\n")
a = E.analytics(max_age=0)
lv = {r["band"]: r for r in a["levels"]}
ok("levels: every quoted combo counted by band, with hit rate vs expected", lv["90–95%"]["n"] == 40 and abs(lv["90–95%"]["hit"] - 14 / 40) < .001
   and abs(lv["90–95%"]["exp"] - .25) < .001)
ok("levels: riding-to-the-end return computed", lv["90–95%"]["ride"] is not None)
ok("levels: the lab's own results sit next to them", lv["95–100%"]["lab_n"] == 1 and lv["95–100%"]["lab_smart"] is not None)
ok("bet types include the paper lab", any(t["what"] == "Combos" and t["mode"] == "paper" for t in a["types"]))
ok("sports breakdown", any(t["what"] in ("NBA", "Nba") for t in a["sports"]))
ex = {e["what"]: e for e in a["exits"]}
ok("selling: ridden vs cashed, and what auto-sell did", ex["Cashed out early"]["pl"] == 3 and ex["Rode to the end"]["pl"] == -5 and a["auto"] == {"smart": 1})
ok("plain-English notes", any("90–95% of fair have done best" in n for n in a["notes"]) and any("No real panel bets" in n for n in a["notes"]))
ok("cached so Results stays quick", E.analytics() is a)
