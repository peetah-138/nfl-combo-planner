# CHECK: group=engine
# Moving cash between Kalshi's pots (issue #144). Kalshi keeps API cash in a pot per exchange shard and an API order can
# only use its market's pot. Pete's single-game buy was refused with $69.49 in all but $5.63 in that pot. This checks
# the manual move (only on Pete's confirmed tap) on the fake Kalshi: the request's units (centicents), the shortfall
# math, a happy path, a short source, Kalshi's 4xx (nothing moved), an unknown outcome (check, never resent, blocks
# further moves until cleared), a double tap (one move), Pause, the hub path, and that nothing else can send a move.
# Throwaway key; fake network only.
import os, tempfile, importlib.util, uuid
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")


def engine(name):
    spec = importlib.util.spec_from_file_location(name, "wahome/engine.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


E = engine("E")
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
E.POT_LEDGER = os.path.join(E.HERE, "pots.json")
E.CFG["kalshi_key_id"] = "fake-key-id"
E.hub_conf = lambda: None
E.hub_up = lambda: False
import fakenet
fakenet.install(port=1)
D, T = fakenet.ORDERS, fakenet.TRANSFERS
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
LOGS = []
E.print = lambda *a, **k: LOGS.append(" ".join(str(x) for x in a))
TK = "KXNBASPREAD-26NOV21DENLAL-DEN5"
NOSLEEP = lambda s: None


def pots(total, *by):
    return {"balance": int(round(total * 100)), "balance_dollars": f"{total:.4f}", "portfolio_value": 0, "updated_ts": 1,
            "balance_breakdown": [{"exchange_index": i, "balance": f"{v:.4f}"} for i, v in by]}


def reset(**k):
    D.update(mode="v2", sent=[], next=None, fill=None, headers={}, balance=pots(69.49, (0, 0.0), (1, 63.86), (3, 5.63)),
             shards={TK: 3})
    T.update(on=True, sent=[], next=None, status="complete", ids={}, active=True, moved={})
    T.update(k)
    E._POT_SHARED.recent.clear()
    E._POT_SHARED.unsure.clear()
    E._POT_SHARED.names["at"] = 0
    E.save_json(E.POT_LEDGER, {})
    E.note_pots(D["balance"])


def by_now():
    return {r["exchange_index"]: round(float(r["balance"]), 2) for r in D["balance"]["balance_breakdown"]}


def move(f, t, amt, **k):
    return E.pot_transfer(f, t, amt, sleep=NOSLEEP, **k)


# ---- names: from Kalshi's public exchange status, the docs' table as a fallback
reset()
n = E.pot_names()
ok(f"pots named from Kalshi's exchange status ({n})",
   n[0] == "Main pot (most markets)" and n[1] == "Combos pot" and n[3] == "Tennis, Baseball, Basketball pot")

# ---- (1) the quote and the shortfall math
q = E.pot_transfer_quote(1, 3, "10.00")
ok(f"quote: before and after for both pots ({q})",
   q["ok"] and q["before"] == [63.86, 5.63] and q["after"] == [53.86, 15.63] and q["amount"] == 10.0)
ok("quote refuses: same pot, zero, fractions of a cent, over $200, more than the pot has",
   not E.pot_transfer_quote(1, 1, "5")["ok"] and not E.pot_transfer_quote(1, 3, "0")["ok"]
   and not E.pot_transfer_quote(1, 3, "1.005")["ok"] and not E.pot_transfer_quote(1, 3, "200.01")["ok"]
   and not E.pot_transfer_quote(3, 1, "6.00")["ok"] and E.pot_transfer_quote(1, 3, "200")["ok"] is False)
s = E.pot_shortfall(TK, 9.90)
ok(f"Pete's case: $9.90 needed, $5.63 in the pot -> short $4.27, +$0.50 -> $5 from the combos pot ({s})",
   s["ok"] and s["to"] == 3 and s["from"] == 1 and s["amount"] == 5.0 and s["short"] == 4.27)
s = E.pot_shortfall(TK, 6.10, pots={"by": [[0, 0.0], [1, 63.86], [3, 5.63]]})
ok(f"short by $0.47: buffer makes $0.97, rounded up to $1 ({s.get('amount')})", s["ok"] and s["amount"] == 1.0)
s = E.pot_shortfall(TK, 9.90, pots={"by": [[0, 2.0], [1, 4.5], [3, 5.63]]})
ok(f"the largest other pot can't cover the buffer but covers the gap: all it has ({s.get('amount')})",
   s["ok"] and s["from"] == 1 and s["amount"] == 4.5)
s = E.pot_shortfall(TK, 20.0, pots={"by": [[1, 4.0], [3, 5.63]]})
ok(f"no pot covers the gap: says so, nothing offered ({s['msg']})", not s["ok"] and "short" in s["msg"])
ok("the pot already has enough: nothing offered", not E.pot_shortfall(TK, 5.0)["ok"])
s = E.pot_shortfall("KXUNKNOWN-1", 9.9)
ok("the market's pot unknown: says so, lets Pete pick", not s["ok"] and s.get("unknown"))

# ---- (2) happy path: the request's exact fields and units, the new pots, a ledger line, logged
reset()
cid = str(uuid.uuid4())
r = move(1, 3, "5.00", cid=cid)
b = T["sent"][-1]
ok(f"Kalshi's request: event_contract both ends, shards 1 -> 3, $5 = 50000 centicents, our UUID ({b})",
   b == {"client_transfer_id": cid, "source": "event_contract", "destination": "event_contract", "amount": 50000,
         "source_exchange_shard": 1, "destination_exchange_shard": 3})
ok(f"moved: complete, the new pots read back ({r.get('pots')})",
   r["ok"] and r["status"] == "complete" and [3, 10.63] in r["pots"]["by"] and [1, 58.86] in r["pots"]["by"])
led = E.pot_moves()
ok(f"ledger: the move, its pots, amount, status and client id ({led[0]})",
   led[0]["cid"] == cid and led[0]["status"] == "complete" and led[0]["amount"] == 5.0 and not led[0]["open"])
ok("logged with the client id and no key", any("pot move: complete $5.00 index 1 -> 3" in x for x in LOGS)
   and not any("fake-key-id" in x for x in LOGS))
reset(status="pending")
r = move(1, 3, "2.00")
ok(f"Kalshi still processing after the time box: says so, kept as pending ({r['msg']})",
   r["ok"] and r["status"] == "pending" and E.pot_moves()[0]["open"])
r2 = move(1, 3, "3.00")
ok("a pending move holds the next one until it lands", not r2["ok"] and r2.get("blocked") and len(T["sent"]) == 1)
T["status"] = "complete"
r3 = move(1, 3, "3.00")
ok("once Kalshi says complete, the next move goes", r3["ok"] and len(T["sent"]) == 2)

# ---- (3) refusals that send nothing
reset()
r = move(3, 1, "6.00")
ok(f"the source pot short on a fresh read: refused, nothing sent ({r['msg']})", not r["ok"] and not T["sent"])
r = move(1, 3, "5.00", paused=True)
ok("Pause: refused with the Pause words, nothing sent", not r["ok"] and r.get("paused") and "Paused" in r["msg"]
   and not T["sent"])
E.TRADING_PAUSED = lambda: True
r = move(1, 3, "5.00")
E.TRADING_PAUSED = lambda: 1 / 0
r2 = move(1, 3, "5.00")
E.TRADING_PAUSED = None
ok("Pause as the watcher holds it (read fresh; a failed read counts as paused): refused, nothing sent",
   r.get("paused") and r2.get("paused") and not T["sent"])
E.ROLE_BACKUP = True
r = move(1, 3, "5.00")
E.ROLE_BACKUP = False
ok("the Pi (alerts-only backup) never moves money", not r["ok"] and "backup" in r["msg"] and not T["sent"])
reset(active=False)
r = move(1, 3, "5.00")
ok("Kalshi has paused moves between pots: refused, nothing sent", not r["ok"] and not T["sent"])
reset()
D["balance"] = fakenet.R({"error": "down"}, 503)
r = move(1, 3, "5.00")
ok("the balance can't be read: refused (never a guess), nothing sent", not r["ok"] and not T["sent"])
reset()
key = E.KEYFILE
E.KEYFILE = os.path.join(E.HERE, "nope.pem")
r = move(1, 3, "5.00")
E.KEYFILE = key
ok("no trading key: refused, nothing sent", not r["ok"] and not T["sent"])

# ---- (4) Kalshi's definite refusal: nothing moved, its words, a fresh tap may try again
reset(next=(400, "invalid_parameters"))
r = move(1, 3, "5.00")
ok(f"a 400: nothing moved, Kalshi's words, recorded refused, not a block ({r['msg']})",
   not r["ok"] and not r.get("check") and "Nothing was moved" in r["msg"] and by_now()[3] == 5.63
   and E.pot_moves()[0]["status"] == "refused" and not E.pot_moves()[0]["open"])
r = move(1, 3, "5.00")
ok("after a refusal a fresh tap goes through", r["ok"] and by_now()[3] == 10.63)
reset(next=(403, "permission_denied"))
r = move(1, 3, "5.00")
ok("a 403: nothing moved, no check", not r["ok"] and not r.get("check"))
reset(next=429)
r = move(1, 3, "5.00")
ok("a 429: Kalshi busy, nothing moved, no check", not r["ok"] and not r.get("check") and "busy" in r["msg"])

# ---- (5) an unknown outcome: check, never resent, blocks further moves until Pete clears it
import requests
for what, nxt in (("a timeout", requests.Timeout("slow")), ("a 500", 500), ("a 409 (already taken)", 409),
                  ("an unreadable answer", fakenet.R({"oops": 1}))):
    reset(next=nxt)
    cid = str(uuid.uuid4())
    r = move(1, 3, "5.00", cid=cid)
    ok(f"{what}: check, not ok ({r['msg'][:60]})", not r["ok"] and r.get("check") and E.pot_moves()[0]["status"] == "check")
n0 = len(T["sent"])
r = move(1, 3, "5.00", cid=cid)
ok("the same move again (same id): the first answer, not resent", r.get("repeat") and r.get("check") and len(T["sent"]) == n0)
r = move(1, 3, "4.00")
ok("a different move while one is 'check': blocked, nothing sent", not r["ok"] and r.get("blocked") and len(T["sent"]) == n0)
ok("Settings shows it open with its why", E.pot_moves()[0]["open"] and E.pot_moves()[0]["why"])
ok("clearing it: logged, not resent", E.pot_clear(cid) and any("pot move cleared by you" in x for x in LOGS)
   and len(T["sent"]) == n0 and not E.pot_clear(cid))
r = move(1, 3, "4.00")
ok("after clearing, a new move goes", r["ok"] and len(T["sent"]) == n0 + 1)
reset(next=500)
real_save = E.save_json
cid = str(uuid.uuid4())


def flaky(path, data, strict=False):          # the write-ahead works, then the disk fails
    if path == E.POT_LEDGER and any(m.get("status") == "check" for m in data.get("moves", [])):
        raise OSError("disk full")
    return real_save(path, data, strict)


E.save_json = flaky
r = move(1, 3, "5.00", cid=cid)
E.save_json = real_save
r2 = move(1, 3, "4.00")
ok("a 'check' that can't be written to disk is kept in memory: still check, still blocks the next move",
   r.get("check") and r2.get("blocked") and len(T["sent"]) == 1 and any("MONEY STATE NOT SAVED: pot move" in x for x in LOGS))
E._POT_SHARED.unsure.clear()
reset()
E.save_json = lambda path, data, strict=False: (_ for _ in ()).throw(OSError("disk full")) if path == E.POT_LEDGER \
    else real_save(path, data, strict)
r = move(1, 3, "5.00")
E.save_json = real_save
ok("the write-ahead record can't be saved: nothing is sent", not r["ok"] and not T["sent"])
reset()
E.save_json(E.POT_LEDGER, {"moves": [{"cid": "c-crash", "ts": 1, "from": 1, "to": 3, "amount": 5, "status": "sending"}]})
r = move(1, 3, "5.00")
ok("a move left 'sending' (the Mac stopped mid-send) counts as unknown: blocks", not r["ok"] and r.get("blocked")
   and not T["sent"])

reset(next=fakenet.R([]))
r = move(1, 3, "5.00")
ok("a 200 whose body isn't an object (a list): check, never 'nothing moved'", not r["ok"] and r.get("check"))
reset(next=fakenet.R("ok"))
r = move(1, 3, "5.00")
ok("a 200 whose body is a string: check", not r["ok"] and r.get("check"))

# ---- (5b) the time box, Settings' refresh of a pending move, the $200 cap, string-keyed pots
reset()
E.POT_DEADLINE, keep = 5, E.POT_DEADLINE
r = move(1, 3, "5.00")
E.POT_DEADLINE = keep
ok(f"no time left to send and hear back inside the time box: refused, nothing sent ({r['msg']})",
   not r["ok"] and not r.get("check") and not T["sent"])
ok("the whole move fits inside the tap lock's 20 s wait and the hub proxy's 40 s",
   E.POT_DEADLINE < 20 and E.POT_DEADLINE + 10 < 40)
reset(status="pending")
move(1, 3, "2.00")
T["status"] = "complete"
ok("Settings' refresh asks Kalshi about a pending move and shows it landed",
   E.pot_moves()[0]["status"] == "pending" and E.pot_moves(refresh=True)[0]["status"] == "complete")
s = E.pot_shortfall(TK, 260, pots={"by": [[0, 900.0], [3, 20.0]]})
ok(f"short by more than one move carries: says the $200 cap, not 'no pot has it' ({s['msg']})",
   not s["ok"] and "$200.00" in s["msg"] and "No other pot" not in s["msg"])
ok("pots given with string keys still match", E.pot_transfer_quote(0, 3, "5", {"0": 50, "3": 0})["ok"])

# ---- (6) double taps: one move
reset()
cid = str(uuid.uuid4())
r1, r2 = move(1, 3, "5.00", cid=cid), move(1, 3, "5.00", cid=cid)
ok("the same sheet tapped twice: one move, the second gets the first answer",
   r1["ok"] and r2["ok"] and r2.get("repeat") and len(T["sent"]) == 1 and by_now()[3] == 10.63)
r3 = move(1, 3, "5.00")
ok("the same move from a new sheet within 10 s: not sent twice", not r3["ok"] and len(T["sent"]) == 1)
ok("a bad id is refused, nothing sent", not move(1, 3, "1.00", cid="not-a-uuid")["ok"] and len(T["sent"]) == 1)

# ---- (7) the real path: the webapp's copy relays to the Mac's copy (hub op pot_move), nothing else can move cash
A = engine("A")
A.hub_up = lambda: True
A.POT_LEDGER = E.POT_LEDGER
src = open("wtest/combo_watcher.py").read()
ok("the hub's pot_move op hands the move to the Mac's engine with the Pause switch",
   'if op == "pot_move":' in src and "E.pot_transfer(" in src and 'paused = True' in src)


def hub_call(op, timeout=0, **req):
    if op == "pot_move":
        return E.pot_transfer(req.get("frm"), req.get("to"), req.get("amount"), cid=req.get("cid"),
                              paused=bool(req.get("paused")), sleep=NOSLEEP)
    if op == "pot_clear":
        return {"ok": E.pot_clear(req.get("cid"))}
    if op == "pots":
        return {"pots": E.kalshi_pots()}
    return None


A.hub_call = hub_call
reset()
r = A.pot_transfer(1, 3, "5.00", cid=str(uuid.uuid4()))
ok("through the Mac: moved", r["ok"] and by_now()[3] == 10.63)
r = A.pot_transfer(1, 3, "1.00", paused=True)
ok("through the Mac, paused: refused", not r["ok"] and r.get("paused"))
A.hub_call = lambda op, timeout=0, **k: None
r = A.pot_transfer(1, 3, "1.00")
ok("lost the Mac mid-move: check (never 'nothing moved')", not r["ok"] and r.get("check"))
i = src.index('if op == "kalshi":')
seg = src[i:i + 600]
ok("the hub's generic Kalshi relay refuses transfers and target balance allocation (moves go through pot_move only)",
   "hub_refusal(method, path)" in seg and "transfer|balance_allocation|subaccount" in src[src.index("def hub_refusal"):][:900])
esrc = open("wahome/engine.py").read()
ok("the app never sets Kalshi's automatic rebalancing (target_balance_allocation is never called)",
   "/portfolio/target_balance_allocation" not in esrc)
ok("no code path moves cash on its own: pot_transfer is called only from the hub op and the tap",
   esrc.count("pot_transfer(") == esrc.count("def pot_transfer(") + 0 and src.count("pot_transfer(") == 2)
j = src.index('if a == "pot_move":')
ok("the tap runs under the web app's tap lock (inside act_lock, like orders)",
   src.rfind("with act_lock():", 0, j) > src.rfind("def _api_act", 0, j))

# ---- a move kept in memory (its note couldn't be written) steps aside once the file has it
reset()
E._POT_SHARED.unsure["mem-cid"] = {"cid": "mem-cid", "status": "pending", "amount": 1.0}
saved = E._pot_save([{"cid": "mem-cid", "status": "complete", "amount": 1.0}])
ok("a saved move drops its memory copy (it can't override the file or block later saves)",
   saved and "mem-cid" not in E._POT_SHARED.unsure and E._pot_ledger()[0]["status"] == "complete")
