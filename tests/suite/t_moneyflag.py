# CHECK: group=engine
# Issue #242: the "money moved" stamp that makes open screens refresh after a sale, hedge, fill or settlement.
# Display only: the stamp is a file's time; nothing that buys, sells or sizes reads it. Covers: no stamp on a
# process's first account read, a stamp when a combo's status/money, a position or the balance changes, none when
# nothing changed, a stamp for every sale-type sell-log line and none for a skip, never raising on odd input or an
# unwritable folder, and that the file is git-ignored.
import os, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
E.HERE = tempfile.mkdtemp()
E.MONEY_FLAG = os.path.join(E.HERE, "combo_money.json")
E.SELL_LOG = os.path.join(E.HERE, "combo_sells.jsonl")
E.sale_store = lambda rec: None
ok("no stamp yet reads as 0", E.money_seen() == 0.0)
bets = [{"ticker": "KXMVE-1", "status": "pending", "back": 0, "cost": 5.0, "pays": 41.2}]
pos = [{"ticker": "KXNBAGAME-26NOV21BOSNYK-BOS", "position_fp": "10.00"}]
E.money_note(bets, pos, 100.0)
ok("first read of a process only remembers", E.money_seen() == 0.0)
E.money_note([dict(b) for b in bets], [dict(p) for p in pos], 100.0)
ok("same account again: no stamp", E.money_seen() == 0.0)
def moved(b, p, bal):
    os.utime(E.MONEY_FLAG, (1, 1)) if os.path.exists(E.MONEY_FLAG) else None
    before = E.money_seen()
    E.money_note(b, p, bal)
    return E.money_seen() > before
ok("a combo cashed out stamps", moved([dict(bets[0], status="cashed", back=9.1)], pos, 100.0))
ok("a position sold stamps", moved([dict(bets[0], status="cashed", back=9.1)], [], 100.0))
ok("the balance changing stamps", moved([dict(bets[0], status="cashed", back=9.1)], [], 109.1))
ok("nothing changed: no stamp", not moved([dict(bets[0], status="cashed", back=9.1)], [], 109.1))
ok("a new fill stamps", moved([dict(bets[0], status="cashed", back=9.1), {"ticker": "KXMVE-2", "status": "pending"}], [], 104.1))
try:
    E.money_note(None, [None, 3, {"x": 1}], object()); E.money_note([{"ticker": object()}], "bad", None); raised = False
except Exception:
    raised = True
ok("odd input never raises", not raised)
os.utime(E.MONEY_FLAG, (1, 1))
E.log_decision({"result": "skipped", "combo": "X", "why": "holding is worth more"})
ok("a skip line does not stamp", E.money_seen() == 1)
for res in E.SALE_RESULTS:
    os.utime(E.MONEY_FLAG, (1, 1))
    E.log_decision({"result": res, "combo": "X", "ticker": "KXMVE-1", "offer": 9.1, "cost": 5.0})
    ok(f"a '{res}' line stamps at once", E.money_seen() > time.time() - 60)
E.MONEY_FLAG = os.path.join(E.HERE, "no", "such", "dir", "combo_money.json")
try:
    E.money_mark(); raised = False
except Exception:
    raised = True
ok("an unwritable stamp never raises", not raised and E.money_seen() == 0.0)
E.MONEY_FLAG = os.path.join(E.HERE, "combo_money.json")
src = open("wahome/engine.py", encoding="utf-8").read()
body = src.split("def money_note(")[1].split("\ndef ")[0] + src.split("def money_mark(")[1].split("\ndef ")[0]
ok("the stamp code places no order", not any(w in body for w in ("kalshi_send", "accept_offer", "buy(", "sell(", "requests.")))
ok("the stamp file matches the git-ignored combo_*.json pattern", __import__("fnmatch").fnmatch(os.path.basename(E.MONEY_FLAG), "combo_*.json"))
