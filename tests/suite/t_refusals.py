# CHECK: group=engine
# Kalshi refusals shown honestly (issue #134). When Kalshi turns an order down for the account or the region ("Nevada
# residents are not currently allowed to open positions in Sports markets..."), the app: shows Kalshi's whole message
# (never clipped), says it is Kalshi's rule and not "your API key needs write access", and stops sending the same
# refused request again and again (a hold that grows 30 min, 1 h, 2 h, 4 h), for the panel, Buy ideas, quotes and the
# automatic hedge. Sales have their own, shorter hold. After a hold, the next buy is the check; Kalshi taking it clears
# the note. An order with an UNKNOWN outcome is still "check" and is never retried, and nothing here changes a location
# or routes an order anywhere: it only reports and holds back. Fake Kalshi, throwaway key.
import os, tempfile, time, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")


def engine(name):
    spec = importlib.util.spec_from_file_location(name, "wahome/engine.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


E = engine("E")
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
E.RESTRICT_FILE = os.path.join(E.HERE, "combo_kalshi_block.json")
E.CFG["kalshi_key_id"] = "fake-key-id"
E.hub_conf = lambda: None
import fakenet
fakenet.install(port=1)
D = fakenet.ORDERS
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
BAY = "KXNCAAFSPREAD-26NOV21TTUBAY-BAY8"
LOGS = []
E.print = lambda *a, **k: LOGS.append(" ".join(str(x) for x in a))
NEV = ("Nevada residents are not currently allowed to open positions in Sports markets on Kalshi. This applies to your "
       "account because of the state you registered in. You can still close positions you already hold, and you can "
       "trade in other categories where they are available to you. See the Kalshi help center for details.")
BODY = {"error": {"code": "forbidden_for_region", "message": NEV, "details": ""}}
n, ask = 10, 0.30


def reset(**k):
    D.update(mode="v2", sent=[], next=None, fill=None, headers={}, balance=None, shards={BAY: 0})
    D.update(k)
    E._ORDER_SHARED.recent.clear()
    E.save_json(E.ORDER_LEDGER, {})
    E.save_json(E.RESTRICT_FILE, {})
    E.refusal_take()


def orders_sent():
    return [s for s in D["sent"] if s[0] == "POST" and "orders" in s[1]]


# ---- (1) the whole message, in Kalshi's words, never clipped, never "needs write access"
ok(f"the sample message is longer than the old 160-character clip ({len(NEV)})", len(NEV) > 300)
reset(next=fakenet.R(BODY, 403))
filled, err = E.buy_single(BAY, n, ask)
ok(f"a region refusal comes back with Kalshi's full message ({err})", filled == 0 and NEV in err)
ok("...and never blames the API key", "write (trading) access" not in err and "API key" not in err)
ok("nothing is marked 'check' (a definite refusal, nothing placed)", not E.order_unsure(BAY))
ref = E.refusal_take()
ok("the tap's refusal is kept for the page: full text, code, restricted", ref and ref["msg"] == NEV
   and ref["code"] == "forbidden_for_region" and ref["restricted"] is True and ref["status"] == 403)
ok("taking it empties it", E.refusal_take() is None)
info = E.restriction_info()
ok("the Mac notes it: buy restricted, holding, the full text, a count", info["buy"]["active"] and info["buy"]["holding"]
   and info["buy"]["msg"] == NEV and info["buy"]["count"] == 1 and not info["sell"]["active"])
ok("the hold is about 30 minutes", 25 * 60 < info["buy"]["hold_until"] - time.time() <= 30 * 60 + 5)
ok("the Mac's log line says what Kalshi said, once", any("refusing buy orders" in x and "Nevada" in x for x in LOGS))

# ---- (2) stops asking: no new request while the hold lasts
before = len(D["sent"])
filled, err = E.buy_single(BAY, n, ask)
ok(f"held: no request goes to Kalshi, the words say so ({err})", len(D["sent"]) == before and filled == 0
   and "nothing was sent" in err and NEV in err and "checks again after" in err)
ref = E.refusal_take()
ok("a held attempt is marked held for the page", ref and ref["held"] and ref["restricted"])
ok("quotes and accepts wait too (get_offer / accept_offer)", E.hold_refusal("buy")[0] is not None)
r = E.get_offer(1, 5, check_cap=False)
ok("get_offer answers with the hold, no RFQ sent", r.get("restricted") and "nothing was sent" in r.get("error", "")
   and len(D["sent"]) == before)
E.CTX.setdefault("offers", {})[1] = {"rfq": "r1", "stake": 5, "market": "M", "legs": []}
r = E.accept_offer(1, skip_cap=True)
ok("accept_offer answers with the hold too", r.get("restricted") and len(D["sent"]) == before)
E.CTX["offers"].pop(1, None)
msg = E.place_hedge("T", hg={"n": 5, "price": .4, "ticker": BAY, "name": "x", "fee": .01, "done": 0, "cost": 2}, auto=True)
ok("a hedge is a buy: auto-hedge places none while held", "wasn't placed" in msg and len(D["sent"]) == before)

# ---- (3) the ladder: 30 min, then 1 h, 2 h, 4 h; a success clears it
def expire():
    d = E.load_json(E.RESTRICT_FILE, {})
    d["buy"]["hold_until"] = time.time() - 1
    E.save_json(E.RESTRICT_FILE, d)


for streak, hours in ((2, 1), (3, 2), (4, 4), (5, 4)):
    expire()
    D["next"] = fakenet.R(BODY, 403)
    E.buy_single(BAY, n, ask)
    e = E.restriction_info()["buy"]
    ok(f"refused again after the hold (#{streak}): hold is {hours} h", e["count"] == streak
       and abs((e["hold_until"] - time.time()) - hours * 3600) < 10)
expire()
filled, err = E.buy_single(BAY, n, ask)
ok("after the hold, the next buy is let through (Kalshi takes it) and the note clears", filled == n and err is None
   and not E.restriction_info()["buy"]["active"])
ok("a later buy isn't held", E.hold_refusal("buy") == (None, ""))

# ---- (3b) Pete's own buy tap is never held: it goes through the usual guards and is the check; a new refusal renews the hold
reset(next=fakenet.R(BODY, 403))
E.buy_single(BAY, n, ask)                                   # an automatic attempt: refused, the hold starts
e0 = E.restriction_info()["buy"]
ok("setup: a hold is on", e0["holding"] and e0["count"] == 1)
before = len(D["sent"])
ok("automatic paths are still held", E.hold_refusal("buy")[0] is not None and E.buy_single(BAY, n, ask)[0] == 0
   and len(D["sent"]) == before)
with E.manual_tap():
    ok("a manual tap isn't held (hold_refusal)", E.hold_refusal("buy") == (None, ""))
    ok("...and sells keep their own rule", E.hold_refusal("sell") == (None, ""))
ok("the mark ends with the tap: automatic paths are held again", E.hold_refusal("buy")[0] is not None)
time.sleep(0.05)
d = E.load_json(E.RESTRICT_FILE, {})
d["buy"]["hold_until"] = time.time() + 600                  # 10 minutes of the hold left
E.save_json(E.RESTRICT_FILE, d)
D["next"] = fakenet.R(BODY, 403)
with E.manual_tap():
    filled, err = E.buy_single(BAY, n, ask)
ok(f"Buy straight during a hold: the request goes to Kalshi ({len(D['sent']) - before} sent)", len(D["sent"]) > before)
ok(f"Kalshi refused it again: Kalshi's words, filled nothing ({err})", filled == 0 and NEV in err
   and "nothing was sent" not in err)
e1 = E.restriction_info()["buy"]
ok("the refusal renews the hold (same level, from now), it does not escalate on a tap",
   e1["holding"] and e1["count"] == 2 and 25 * 60 < e1["hold_until"] - time.time() <= 30 * 60 + 5)
ref = E.refusal_take()
ok("the page gets the refusal, not a 'held' note", ref and ref["restricted"] and not ref.get("held"))
D["next"] = None
with E.manual_tap():
    filled, err = E.buy_single(BAY, n, ask)
ok("Kalshi takes the tap: bought, and the note clears", filled == n and err is None
   and not E.restriction_info()["buy"]["active"])
reset(next=fakenet.R(BODY, 403))
E.buy_single(BAY, n, ask)
E.CTX.setdefault("offers", {})[1] = {"rfq": "r1", "stake": 5, "market": "M", "legs": []}
before = len(D["sent"])
with E.manual_tap():
    try:
        r = E.accept_offer(1, skip_cap=True)
    except Exception:
        r = {}
ok("a manual accept isn't stopped by the hold", not r.get("restricted"))
E.CTX["offers"].pop(1, None)
with E.manual_tap():
    try:
        r = E.get_offer(1, 5, check_cap=False)
    except Exception:
        r = {}
ok("a manual quote isn't stopped by the hold", not r.get("restricted"))
before = len(D["sent"])
with E.manual_tap():
    msg = E.place_hedge("T", hg={"n": 5, "price": .4, "ticker": BAY, "name": "x", "fee": .01, "done": 0, "cost": 2}, auto=True)
ok("an automatic hedge stays held even inside a tap's mark", "wasn't placed" in msg and len(D["sent"]) == before)

# ---- (4) a refusal that is not about the region says Kalshi's own reason, not a guess about the key
reset(next=fakenet.R({"error": {"code": "forbidden", "message": "This market is closed to new orders."}}, 403))
filled, err = E.buy_single(BAY, n, ask)
ok(f"an ordinary 403: Kalshi's own words, no key blame ({err})", "This market is closed to new orders." in err
   and "write (trading) access" not in err and "API key" not in err)
ok("...and it is not a region hold", not E.restriction_info()["buy"]["active"] and E.hold_refusal("buy")[0] is None)
reset(next=fakenet.R({"error": {"code": "authentication_error", "message": "invalid signature"}}, 401))
filled, err = E.buy_single(BAY, n, ask)
ok(f"401: says Kalshi didn't accept the key, with its reason ({err})", "401" in err and "invalid signature" in err
   and "didn't accept the API key" in err)
reset(next=(403, "permission_denied"))
filled, err = E.buy_single(BAY, n, ask)
ok(f"only when Kalshi says permission_denied is the write-access hint shown ({err})", "write (trading) access" in err
   and "permission_denied" in err)
reset(next=fakenet.R({"message": "<html><body><h1>Forbidden</h1> blocked by gateway </body></html>"}, 403))
filled, err = E.buy_single(BAY, n, ask)
ok(f"a gateway page keeps its words, not its tags ({err})", "<" not in err and "blocked by gateway" in err)

# ---- (5) rule 8 is untouched: an unknown outcome is 'check' and never retried, and is never a region hold
reset(next=500)
try:
    E.buy_single(BAY, n, ask)
    raised = None
except Exception as e:
    raised = e
ok("a 500 is an unknown outcome: marked 'check' on the market", E.order_unsure(BAY) and not E.restriction_info()["buy"]["active"])
before = len(orders_sent())
filled, err = E.buy_single(BAY, n, ask)
ok(f"...and never retried ({err})", len(orders_sent()) == before and filled == 0)
reset(next=E.requests.exceptions.Timeout("timeout"))
try:
    E.buy_single(BAY, n, ask)
except Exception:
    pass
ok("a timeout is 'check' too, never a region hold", E.order_unsure(BAY) and not E.restriction_info()["buy"]["active"])

# ---- (6) sales have their own, shorter hold and never block a buy
reset(next=fakenet.R(BODY, 403))
sold, err = E.sell_single_now(BAY, "yes", 5, 0.40)
info = E.restriction_info()
ok(f"a refused sale is a sell restriction, not a buy one ({err})", sold == 0 and NEV in err and info["sell"]["active"]
   and not info["buy"]["active"])
ok("its hold is about 10 minutes", 8 * 60 < info["sell"]["hold_until"] - time.time() <= 10 * 60 + 5)
out = []
ok("automatic sales wait while held (and tell once a day)", E.sell_held(out) is True and len(out) == 1 and "Kalshi" in out[0]
   and E.sell_held(out) is True and len(out) == 1)
ok("a buy still goes through", E.hold_refusal("buy") == (None, ""))
before = len(D["sent"])
sold, err = E.sell_single_now(BAY, "yes", 5, 0.40)
ok("...but Pete's own sell tap still asks Kalshi (a sale is never trapped by the app)", len(D["sent"]) > before)

# ---- (7) a restriction we haven't heard of for a day is old news
reset(next=fakenet.R(BODY, 403)); E.buy_single(BAY, n, ask)
d = E.load_json(E.RESTRICT_FILE, {}); d["buy"]["at"] = time.time() - 25 * 3600; d["buy"]["hold_until"] = time.time() + 999
E.save_json(E.RESTRICT_FILE, d)
ok("a day-old note neither holds nor shows", not E.restriction_info()["buy"]["active"] and E.hold_refusal("buy")[0] is None)

# ---- (8) the panel: a refused bet waits (never 'failed', never 'check'), asks no more, tells once
import datetime as _dt
_u = _dt.datetime.now(_dt.timezone.utc); E.PACIFIC = _dt.timezone(_dt.timedelta(hours=round(12 - _u.hour - _u.minute / 60)))
E.SIZING_FILE = os.path.join(E.HERE, "s.json"); E.CUTOFF_FILE = os.path.join(E.HERE, "c.json")
E.REBUILD_FLAG = os.path.join(E.HERE, "panel_rebuild.flag"); E.REBUILD_STATE = os.path.join(E.HERE, "combo_rebuild.json")
E.BUY_FLAG = os.path.join(E.HERE, "panel_buy.flag")
E.fetch_account = lambda **k: ([], 300.0, None)
E.account_events = lambda *a, **k: set()
E.kalshi_send = lambda *a, **k: {}
E.book_depth = lambda t, max_age=60: {"ask": 0.50, "bid": 0.49}
SENT = []
mode = {"m": "refuse"}


def fake_buy(t, k, px):
    SENT.append(t)
    if mode["m"] == "refuse":
        E.note_refusal(403, "forbidden_for_region", NEV, "order")
        return 0, NEV
    if mode["m"] == "unknown":
        raise E.OrderUnknown("timeout")
    E.restriction_clear("buy", "order")                  # what a real accepted order does (checked above with buy_single)
    return k, None


E.buy_single = fake_buy
now = time.time()
l = {"ticker": "A1", "event": "KXNBAGAME-A", "pick": "A1", "p": .50, "fair": .60}
E.KICKOFF["KXNBAGAME-A"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 9 * 3600))
cand = E._cand("single", "nba", [l], .60, (.60 - .50 - E.single_fee(.50)) / (.50 + E.single_fee(.50)), "w", price=.50)
E.store_x("delete from panel", ())
E.PANEL_POOL.clear(); E.PANEL_POOL["nba"] = (time.time(), [cand])
reset()
p = E.build_panel(); E.panel_save_draft(p, "real")
E.panel_approve(None, "all", at=p["at"])
items = lambda: {c["id"]: c for c in E.panel_get("real")["items"]}
out = E.panel_exec()
it = list(items().values())[0]
ok(f"Kalshi refuses the panel bet: it goes back to waiting with the 'region' hold, not failed/check ({it['state']}, {it.get('hold')})",
   it["state"] == "scheduled" and it.get("hold") == "region" and len(SENT) == 1)
ok("one calm notification with Kalshi's words", len([x for x in out if "Kalshi" in x and "Nevada" in x]) == 1)
out = E.panel_exec(); out += E.panel_exec()
ok("the next passes send nothing and say nothing more", len(SENT) == 1 and not out)
expire()
mode["m"] = "ok"
E.panel_exec()
it = list(items().values())[0]
ok(f"after the hold Kalshi takes it: bought, the note clears ({it['state']}, {it.get('hold')}, {len(SENT)}, {it.get('note')})",
   it["state"] == "bought" and len(SENT) == 2 and not E.restriction_info()["buy"]["active"])
# unknown outcome: still check, never a region hold, never retried
E.store_x("delete from panel", ())
E.PANEL_POOL.clear(); E.PANEL_POOL["nba"] = (time.time(), [cand])
reset(); SENT.clear(); mode["m"] = "unknown"
p = E.build_panel(); E.panel_save_draft(p, "real"); E.panel_approve(None, "all", at=p["at"])
E.panel_exec(); E.panel_exec()
it = list(items().values())[0]
ok("an unknown outcome on the panel is still 'check' and tried once", it["state"] == "check" and len(SENT) == 1)
ok("Pause still wins over everything", E.panel_exec(paused=True) is not None and len(SENT) == 1)

# ---- (9) words
ok("kalshi_plain keeps a 500-character message whole", len(E.kalshi_plain(400, "x", "y" * 700)) > 500)
ok("a 4xx with a body that is not JSON still says something", E.body_words(fakenet.R(None, 403, raw=b"Forbidden"))[1] == "Forbidden")
ok("the Mac's state file holds no key or id", "fake-key-id" not in open(E.RESTRICT_FILE).read())
ok("the whole test ran to its end", True)
