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

# ---- Issue #271: no stamp from an incomplete account read; failed cash-outs repeated every pass stamp rarely; the hub's
# forced fresh read has a floor. None of this changes what is bought or sold, or how a balance is used.
E.MONEY_FP.update(v=None, pb=None, inc=0)
E.money_note(bets, pos, 100.0)                       # complete read: remembered
os.utime(E.MONEY_FLAG, (1, 1)) if os.path.exists(E.MONEY_FLAG) else None
logged = []
E.console_note = lambda m: logged.append(m)
E.money_note([], pos, 100.0, 1)                      # a combo dropped out because its legs weren't read
ok("an incomplete read (a combo dropped out) does not stamp", E.money_seen() <= 1)
ok("...and says why, once", len(logged) == 1 and "skipped" in logged[0])
E.money_note([], pos, 100.0, 1)
ok("the same reason is not repeated every pass", len(logged) == 1)
E.money_note([dict(b) for b in bets], [dict(p) for p in pos], 100.0)
ok("the combo coming back (complete read, nothing changed) does not stamp either", E.money_seen() <= 1)
E.money_note([], pos, 100.0, 1)
E.money_note([], [], 100.0, 1)
ok("an incomplete read still stamps when a position really changed", E.money_seen() > time.time() - 60)
os.utime(E.MONEY_FLAG, (1, 1))
E.money_note([], [], 120.0, 1)
ok("an incomplete read still stamps when the balance really changed", E.money_seen() > time.time() - 60)
E.MONEY_FP.update(v=None, pb=None, inc=0)
E.money_note(bets, pos, 100.0); os.utime(E.MONEY_FLAG, (1, 1))
E.money_note([dict(bets[0], status="cashed", back=9.1)], pos, 100.0)
ok("a complete read with a changed combo still stamps", E.money_seen() > time.time() - 60)

E.MONEY_FAIL_AT.clear()
for res in ("failed", "hedge failed"):
    os.utime(E.MONEY_FLAG, (1, 1))
    E.log_decision({"result": res, "combo": "X", "ticker": "KXMVE-F" + res[:2], "offer": 9.1, "cost": 5.0})
    ok(f"the first '{res}' stamps", E.money_seen() > time.time() - 60)
    os.utime(E.MONEY_FLAG, (1, 1))
    E.log_decision({"result": res, "combo": "X", "ticker": "KXMVE-F" + res[:2], "offer": 9.1, "cost": 5.0})
    ok(f"the same '{res}' on the same bet next pass does not stamp again", E.money_seen() <= 1)
os.utime(E.MONEY_FLAG, (1, 1))
E.log_decision({"result": "failed", "combo": "X", "ticker": "KXMVE-OTHER", "offer": 9.1, "cost": 5.0})
ok("a failure on a different bet stamps", E.money_seen() > time.time() - 60)
E.MONEY_FAIL_AT[("KXMVE-F" + "fa", "failed")] = time.time() - E.MONEY_FAIL_GAP - 1
os.utime(E.MONEY_FLAG, (1, 1))
E.log_decision({"result": "failed", "combo": "X", "ticker": "KXMVE-Ffa", "offer": 9.1, "cost": 5.0})
ok("the same failure after the gap stamps again", E.money_seen() > time.time() - 60)
for res in ("sold", "hedged", "check", "hedge check"):
    for _ in range(2):
        os.utime(E.MONEY_FLAG, (1, 1))
        E.log_decision({"result": res, "combo": "X", "ticker": "KXMVE-REP", "offer": 9.1, "cost": 5.0})
        ok(f"'{res}' always stamps, repeated or not", E.money_seen() > time.time() - 60)

# the hub's forced fresh read: a floor, flagged when held back, and the web copy never keeps a held-back copy
wsrc = open("wtest/combo_watcher.py", encoding="utf-8").read()
hub = wsrc.split('if op == "account":')[1].split('if op == "pots":')[0]
ok("hub floor: forces max_age=0 only when the cached copy is old enough", "HUB_FRESH_FLOOR" in hub and "max_age=15 if held or not moved else 0" in hub)
ok("hub floor: a held-back copy is flagged and the reason logged", '"held_back"' in hub and "held back" in hub)
ok("hub floor is 3 seconds", E.HUB_FRESH_FLOOR == 3)
E.ACCT_CACHE.update(at=0, value=None)
E.hub_up = lambda: True
E.hub_call = lambda op, timeout=0: {"value": [[], 7.0, "n"], "held_back": True}
E.fetch_account(max_age=15, every_league=True)
ok("a held-back hub copy is used but not kept as fresh (the next call asks again)", E.ACCT_CACHE["at"] == 0 and E.ACCT_CACHE["value"])
E.hub_call = lambda op, timeout=0: {"value": [[], 8.0, "n"]}
E.fetch_account(max_age=15, every_league=True)
ok("a normal hub copy is cached as before", E.ACCT_CACHE["at"] > time.time() - 60 and E.ACCT_CACHE["value"][1] == 8.0)
E.hub_up = lambda: False

# #457: failures with neither a ticker nor a combo must not hide each other's stamp
E.MONEY_FAIL_AT.clear()
os.utime(E.MONEY_FLAG, (1, 1))
E.log_decision({"result": "failed", "offer": 9.1, "cost": 5.0})
ok("a failure with no ticker or combo stamps", E.money_seen() > time.time() - 60)
os.utime(E.MONEY_FLAG, (1, 1))
E.log_decision({"result": "failed", "offer": 7.7, "cost": 4.0})
ok("a different no-id failure is not hidden by the first", E.money_seen() > time.time() - 60)
os.utime(E.MONEY_FLAG, (1, 1))
E.log_decision({"result": "failed", "offer": 7.7, "cost": 4.0})
ok("the same no-id failure repeating still does not re-stamp", E.money_seen() <= 1)
