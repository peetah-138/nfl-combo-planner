# CHECK: group=engine
# #478: league shadow housekeeping (paper only). lgsh_rows honours its `now` for the 60-day window; a cut-off entry with
# no quotes (n=0) but a recorded move still weighs in the shadow blend (as _cut_own treats it); a real panel buy that is
# also in the bets table is counted once in the shadow's settled-bet record. smart_tune's list (_tune_items default) is
# unchanged, and the shadow still writes no setting.
import os, time, json, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
H = tempfile.mkdtemp()
E.store_open(os.path.join(H, "h.db")); E.HERE = H
E.CUTOFF_FILE = os.path.join(H, "cut.json")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
now = time.time()

# ---- n=0 borrowed entry
ok("n: a plain entry weighs its own count", E._lgsh_n({"level": 95, "n": 12}) == 12)
ok("n: no entry is 0", E._lgsh_n(None) == 0 and E._lgsh_n({}) == 0)
ok("n: n=0 with a recorded move counts as one quote", E._lgsh_n({"level": 93, "n": 0, "why": "borrowed"}) == 1)
ok("n: n=0 with no move stays 0", E._lgsh_n({"level": 95, "n": 0}) == 0)
json.dump({"all:2": {"level": 97.0, "n": 200}, "soccer:2": {"level": 96.0, "n": 100},
           "epl:2": {"level": 90.0, "n": 0, "why": "borrowed", "borrowed": True}}, open(E.CUTOFF_FILE, "w"))
r = {(x["league"], x["metric"], x["key"]): x for x in E.lgsh_rows(now)}[("epl", "cutoff", "2")]
base, _ = E.lgsh_blend(95.0, [("all", 97.0, 200), ("sport", 96.0, 100)], E.LGSH["k_cut"])
ok("cutoff: the n=0 moved entry now pulls the shadow a little (not ignored)", r["shadow"] < round(min(max(base, 85.0), 110.0), 2)
   and r["n_own"] == 0)

# ---- now is honoured by the settled-bet window
E._panel_table()
def panel(mode, ts, items):
    E.store_x("insert or replace into panel values(?,?,?,?,?)", ("2026-01-01", mode, ts, "closed", json.dumps({"items": items})))
def item(i, mkt):
    return {"id": i, "kind": "combo", "market": mkt, "stake": 10, "pays": 25, "kick": now - 100, "result": "won", "pl": 15,
            "legs": [{"ticker": "KXEPLGAME-G%s-A" % i}]}
panel("real", now - 100, [item("1", "KXMVE-SHARED"), item("2", "KXMVE-ONLY-PANEL")])
panel("paper", now - 100, [item("3", "KXMVE-PAPER")])
for combo in ("KXMVE-SHARED", "KXMVE-ONLY-BETS", "KXMVE-PAPER"):
    E.store_x("insert or replace into bets(combo, cost, pays, legs, status, first_seen, settled) values(?,?,?,?,?,?,?)",
              (combo, 10, 25, json.dumps(["KXEPLGAME-GB-A"]), "won", now - 200, now - 50))
ids = lambda **kw: sorted(str(c["id"]) for c in E._tune_items(60, **kw))
ok("default list is unchanged: nothing is deduped (smart_tune keeps its evidence)", len(E._tune_items(60)) == 6)
d = E._tune_items(60, dedupe=True)
ok("dedupe: the real panel buy that is also a bet is counted once", len(d) == 5 and sum(1 for c in d if c["id"] == "KXMVE-SHARED") == 0)
ok("dedupe: a paper panel bet and a bet on the same market are both kept (paper is not a real buy)",
   any(c["id"] == "KXMVE-PAPER" for c in d) and any(c["id"] == "3" for c in d))
ok("now: a clock 90 days on sees an empty 60-day window", E._tune_items(60, now + 90 * 86400) == [])
ok("now: a clock in the window sees them", len(E._tune_items(60, now + 10 * 86400)) == 6)
ok("lgsh_rows takes its window from `now`", any(x["metric"] == "record" for x in E.lgsh_rows(now)) and not any(x["metric"] == "record" for x in E.lgsh_rows(now + 90 * 86400)))
ok("shadow still writes no cut-off file", json.load(open(E.CUTOFF_FILE))["epl:2"]["level"] == 90.0)
