# Money-safety hardening (issue #143). Each check below failed on the code before this change:
#  1 the Pi (backup role) can never place an order, and a synced Auto cash-out = on can't switch it back on;
#  2 a combo accept that went out but whose status poll failed (429/5xx/timeout) is "check", never "refused";
#  3 a 5xx/timeout on the accept itself, or no confirmation within the wait, is "check" too (web app and panel),
#    recorded in the order ledger, and the same combo is never re-quoted or re-bought until cleared; a clear 4xx is
#    still a plain refusal;
#  4 a cash-out accept with an unknown outcome stops (no second accept) and is marked "check";
#  5 killer deals: an unreadable history = skip (never "0 bought today"), the record is written before the order;
#  6 the hub's proxy waits long enough for an order tap and answers a timeout with JSON "may or may not", updates wait
#    for a tap mid-order;
#  7 the order ledger and combo_hedges.json are safe across processes (file lock), a failed write is loud and still
#    blocks a resend in that process;
#  8 Pause covers combo buys (engine and web app) and killer deals read it live;
#  9 an unreadable balance never sizes or approves a panel on the bankroll setting.
# Fake Kalshi (scripted answers / fakenet's order desk); nothing can reach Kalshi or move money.
import os, re, sys, json, time, tempfile, threading, subprocess, importlib.util, hmac, hashlib
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
os.environ.pop("COMBO_ROLE", None)
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.HEDGES = os.path.join(E.HERE, "hedges.json"); E.SELL_LOG = os.path.join(E.HERE, "sells.jsonl")
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
E.SAVED = E.MAIN_SAVED = os.path.join(E.HERE, "settings.json")
E.SIZING_FILE = os.path.join(E.HERE, "sizing.json")
E.HISTORY = os.path.join(E.HERE, "history.json")
E.CFG["kalshi_key_id"] = "fake-key-id"
E.hub_conf = lambda: None
E.haptic = lambda *a: None
E.loading = lambda *a, **k: None
import requests
import fakenet
fakenet.install(port=1)
D = fakenet.ORDERS
ok = lambda n, c, *x: print(("PASS " if c else "FAIL ") + n + ("" if c or not x else f"  {x}"))
T = "KXNBAGAME-26NOV19NYKMIN-NYK"
SRC = open("wahome/engine.py").read()
WSRC = open("wtest/combo_watcher.py").read()


def before(text, a, b):
    """a appears in text, before b."""
    i, j = text.find(a), text.find(b)
    return 0 <= i < j


def attempt(f, *a, **k):
    try:
        return f(*a, **k), None
    except Exception as err:
        return None, err


def ledger_reset():
    E.save_json(E.ORDER_LEDGER, {})
    getattr(E._ORDER_SHARED, "unsure", {}).clear()
    E._ORDER_SHARED.recent.clear()


def unsure(t, kind="buy"):
    f = getattr(E, "rfq_unsure", None)
    return bool(f and f(t, kind))


# ================================================================ (1) the Pi never trades
D.update(mode="v2", sent=[], next=None, fill=None, headers={})
ok("a normal device can trade (the check below means something)", E.can_trade())
E.ROLE_BACKUP = True
ok("backup role: can_trade() is False", not E.can_trade())
body = {"ticker": T, "action": "buy", "side": "yes", "count": 2, "yes_price": 40, "time_in_force": "immediate_or_cancel",
        "client_order_id": "pi-1"}
_, err = attempt(E.kalshi_send, "POST", "/portfolio/events/orders", body)
_, err2 = attempt(E.kalshi_send, "PUT", "/communications/rfqs/r1/quotes/q1/accept", {"accepted_side": "yes"})
ok("backup role: an order and a combo accept are refused before anything is sent",
   err is not None and err2 is not None and not D["sent"], (err, err2, D["sent"]))
r, err = attempt(E.accept_once, {"rfq": "r1", "quote": "q1"}, T)
ok("backup role: a cash-out accept is refused before sending ('failed', not marked unknown)", r == "failed", (r, err))
E.ROLE_BACKUP = False

sys.argv = ["combo_watcher.py"]
wspec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py"); W = importlib.util.module_from_spec(wspec); wspec.loader.exec_module(W)
W.CONF = os.path.join(E.HERE, "watcher.json")
W.push = lambda *a, **k: None
conf = {"role": "backup", "topic": "t", "secret": "s"}
W.DEP["conf"] = conf
sent_body = json.dumps({"at": int(time.time()), "cfg": {"auto_sell": True, "auto_hedge": True, "killer_mode": "on",
                                                         "maker_mode": "on"}}, separators=(",", ":"))
msg = json.dumps({"body": sent_body, "sig": hmac.new(b"s", sent_body.encode(), hashlib.sha256).hexdigest()})


class _R:
    ok, status_code = True, 200
    text = json.dumps({"event": "message", "message": msg}) + "\n"


W.requests = type(sys)("fake_requests")
W.requests.get = lambda *a, **k: _R()
W.requests.RequestException = requests.RequestException
E.CFG.update(auto_sell=False, auto_hedge=False, killer_mode="watch", maker_mode="watch")
W.fetch_settings(conf, E)
ok("backup role: the phone's synced Auto cash-out / auto-hedge / killer / standing orders = on never take effect",
   E.CFG["auto_sell"] is False and not E.CFG.get("auto_hedge") and E.CFG["killer_mode"] == "off"
   and E.CFG["maker_mode"] == "off", {k: E.CFG.get(k) for k in ("auto_sell", "auto_hedge", "killer_mode", "maker_mode")})
ok("backup role: after the settings copy the engine still refuses to trade", not E.can_trade())
i = WSRC.index("def main():")
m = WSRC[i:]
ok("main loop: the Pi's trading is forced off before live_check / auto-sell run",
   before(m[m.find("while True:\n        t0"):], "backup_safe(conf, E)", "E.live_check(None)")
   and "not backup_safe(conf, E)" in m)
ok("main loop: the role is set before the engine loads (every engine copy in the process is a backup)",
   before(m, 'os.environ["COMBO_ROLE"] = "backup"', "E = load_engine()"))
ok("the settings listener thread re-applies the backup rule after every message",
   "backup_safe(conf, E)" in WSRC[WSRC.index("def listen_for_settings"):WSRC.index("def pause(")])
E.ROLE_BACKUP = False
os.environ.pop("COMBO_ROLE", None)
conf["role"] = "main"
E.CFG.update(auto_sell=False, auto_hedge=False, killer_mode="watch", maker_mode="watch")
ok("off the Pi again: trading allowed (the test is isolated)", E.can_trade())

# ================================================================ (2) (3) combo buys: once the accept is out, unclear = check
SCRIPT = {}
CALLS = []


def fake_send(method, path, body=None, params=None):
    CALLS.append((method, path))
    if getattr(E, "role_backup", lambda: False)() and method != "GET":
        raise E.KalshiRefused("backup", 403, "app_backup")
    f = SCRIPT.get((method, "accept" if path.endswith("/accept") else "status" if "/quotes/" in path else path))
    if callable(f):
        return f()
    return f if f is not None else {}


real_send = E.kalshi_send
E.kalshi_send = fake_send
E.ACCEPT_WAIT = 2
MK = "KXMVENBA-26NOV19-ABC123"
LEGS = ["KXNBAGAME-26NOV19NYKMIN-NYK", "KXNBAGAME-26NOV19BOSLAL-BOS"]


def offer():
    E.CTX["offers"] = {1: {"rfq": "rfq1", "quote": "q1", "pays": 20.0, "market": MK, "price": 0.25, "stake": 5.0,
                           "p": 0.2, "legs": list(LEGS)}}


def run_accept(put, status):
    ledger_reset(); CALLS.clear()
    SCRIPT.clear(); SCRIPT[("PUT", "accept")] = put; SCRIPT[("GET", "status")] = status
    offer()
    return attempt(E.accept_offer, 1, skip_cap=True)


def boom(e):
    def f():
        raise e
    return f


r, err = run_accept({}, boom(RuntimeError("Kalshi is busy right now; try again in a minute (429)")))
ok("accept went out, status poll answers 429: 'check' (never 'refused' / 'try again'), recorded in the ledger",
   err is None and r and r.get("check") and unsure(MK), (r, err))
ok("...the words say Kalshi may have taken it and there's no retry",
   bool(r) and "may have taken it" in (r.get("error") or "") and "No retry" in (r.get("error") or ""), r)
r, err = run_accept({}, boom(requests.Timeout("read timed out")))
ok("status poll times out: 'check'", err is None and r and r.get("check") and unsure(MK), (r, err))
r, err = run_accept({}, lambda: "not json at all")
ok("status poll unreadable: 'check'", err is None and r and r.get("check") and unsure(MK), (r, err))
r, err = run_accept(boom(RuntimeError("Kalshi said: internal (503)")), {"quote": {"status": "executed"}})
ok("accept PUT answers 503: 'check' (not 'probably expired, get a fresh offer')",
   err is None and r and r.get("check") and unsure(MK) and "expired" not in (r.get("error") or ""), (r, err))
r, err = run_accept(boom(requests.Timeout("read timed out")), {})
ok("accept PUT times out: 'check'", err is None and r and r.get("check") and unsure(MK), (r, err))
r, err = run_accept(boom(RuntimeError("Lost contact with your Mac during this trade, so it may or may not have gone "
                                      "through. Check Kalshi before trying again.")), {})
ok("accept through the Mac, Mac lost mid-trade: 'check'", err is None and r and r.get("check") and unsure(MK), (r, err))
r, err = run_accept({}, {"quote": {"status": "accepted"}})
ok("no confirmation within the wait ('Still waiting on Kalshi'): 'check'",
   err is None and r and r.get("check") and unsure(MK), (r, err))
r, err = run_accept(boom(RuntimeError("Kalshi wouldn't take the order as sent (400)")), {})
ok("a clear 4xx before Kalshi took the accept: a plain refusal, nothing marked",
   err is None and r and r.get("error") and not r.get("check") and not unsure(MK), (r, err))
r, err = run_accept({}, {"quote": {"status": "executed"}})
ok("executed: bought, nothing marked", err is None and r and r.get("done") and not unsure(MK), (r, err))
r, err = run_accept({}, {"quote": {"status": "cancelled"}})
ok("the seller backed out (cancelled): a plain 'nothing was bought', nothing marked",
   err is None and r and "nothing was bought" in r.get("error", "") and not unsure(MK), (r, err))

# a combo marked check is never quoted or accepted again
r, err = run_accept(boom(requests.Timeout("x")), {})
E.CTX["combos"] = [{"kind": "own", "legs": [{"ticker": t, "event": t.rsplit("-", 1)[0], "fair": 0.5, "p": 0.5}
                                            for t in LEGS], "fair": 20.0, "min": 19.0, "kalshi": 20.0}]
E.CTX["stake"] = 5.0
E.CFG["budget"] = 1000
CALLS.clear()
q, err = attempt(E.get_offer, 1, 5, check_cap=False)
ok("the same combo isn't re-quoted (no fresh RFQ) while it's marked check",
   err is None and q and q.get("check") and not any(m == "POST" for m, _ in CALLS), (q, err, CALLS))
offer(); CALLS.clear()
r, err = attempt(E.accept_offer, 1, skip_cap=True)
ok("...nor accepted again from an old offer", err is None and r and r.get("check") and
   not any(p.endswith("/accept") for _, p in CALLS), (r, CALLS))
key = E.rfq_key(MK, "buy") if hasattr(E, "rfq_key") else ""
blocks = E.order_blocks()
ok("Settings › Money lists it as a combo buy block, and Clear lifts it",
   any(b["key"] == key and b["side"] == "combo buy" for b in blocks) and E.clear_order_block(key) and not unsure(MK), blocks)

# Pause stops a combo buy before anything is sent
ledger_reset(); offer(); CALLS.clear()
E.TRADING_PAUSED = lambda: True
r, err = attempt(E.accept_offer, 1, skip_cap=True)
noput = lambda: not any(p_.endswith("/accept") for _, p_ in CALLS)
ok("Pause: a combo accept is refused, no accept sent, and its quote request is cancelled",
   err is None and r and r.get("error") and r.get("paused") and noput() and ("DELETE", "/communications/rfqs/rfq1") in CALLS,
   (r, CALLS))
E.TRADING_PAUSED = lambda: (_ for _ in ()).throw(OSError("conf unreadable"))
offer(); CALLS.clear()
r, err = attempt(E.accept_offer, 1, skip_cap=True)
ok("Pause unreadable counts as paused", err is None and r and r.get("error") and noput(), (r, CALLS))
E.TRADING_PAUSED = None

# the panel: an unknown combo accept is "check" (never "failed"/"skipped", never retried)
ledger_reset()
orig = {k: getattr(E, k) for k in ("get_offer", "_panel_combo", "combo_cutoff", "_with_ctx")}


def panel_quote(i, stake, check_cap=True):
    offer()
    return {"ok": True, "pays": 20.0, "pct": 1.0, "stake": stake}


E.get_offer = panel_quote
E._panel_combo = lambda c, cut: None
E.combo_cutoff = lambda *a, **k: 0.95
E._with_ctx = lambda f: f()
pc = {"kind": "combo", "code": "nba", "stake": 5.0, "legs": [{"ticker": t, "event": t.rsplit("-", 1)[0], "fair": 0.5, "p": 0.5}
                                                             for t in LEGS]}
for name, put, st in (("accept 5xx", boom(RuntimeError("x (502)")), {}), ("accept timeout", boom(requests.Timeout("x")), {}),
                      ("poll 429", {}, boom(RuntimeError("busy (429)"))), ("no confirmation", {}, {"quote": {"status": "accepted"}})):
    ledger_reset(); SCRIPT.clear(); SCRIPT[("PUT", "accept")] = put; SCRIPT[("GET", "status")] = st
    got, err = attempt(E._buy_panel_bet, dict(pc))
    ok(f"panel combo, {name}: ok None = 'check' (never failed/skipped)", err is None and got and got[0] is None, (got, err))
E.TRADING_PAUSED = lambda: True
ledger_reset(); SCRIPT.clear(); CALLS.clear()
got, err = attempt(E._buy_panel_bet, dict(pc))
ok("panel combo, Pause comes on mid-pass: nothing sent, flagged paused (the bet goes back to waiting)",
   err is None and got and got[0] is False and got[2].get("paused") and noput(), (got, err))
E.TRADING_PAUSED = None
i = SRC.index("def panel_exec")
ok("...panel_exec puts a paused bet back to 'scheduled' (hold paused), not 'failed'",
   'if ok is False and d.get("paused"):' in SRC[i:i + 12000] and '"state": "scheduled", "hold": "paused"' in SRC[i:i + 12000])
ledger_reset(); SCRIPT.clear(); SCRIPT[("PUT", "accept")] = boom(RuntimeError("expired (400)"))
got, err = attempt(E._buy_panel_bet, dict(pc))
ok("panel combo, a clear 4xx: a refusal (ok False)", err is None and got and got[0] is False, (got, err))
for k, v in orig.items():
    setattr(E, k, v)

# killer combos: an unknown accept is "check"
ledger_reset(); SCRIPT.clear(); SCRIPT[("PUT", "accept")] = boom(requests.Timeout("x"))
offer()
got, err = attempt(E._killer_combo, 1)
ok("killer combo, accept times out: None = 'check'", err is None and got and got[0] is None, (got, err))

# ================================================================ (4) cash-out accepts: unknown = stop, check, no second accept
ledger_reset()
H = "KXMVENBA-26NOV19-HELD1"
E.MINE.setdefault("hold", {})[H] = {"label": "Knicks + Celtics", "pays": 10.0, "cost": 5.0, "p": 0.7}
E.MINE.setdefault("cash", {})
E.MINE["tp"] = {}
E.resting_sells = lambda: {}
FRESH = []
E.get_cash_offer = lambda t, frac=1.0: (FRESH.append(t) or {"rfq": "r2", "quote": "q2", "offer": 7.0, "frac": 1.0,
                                                             "at": time.time(), "contracts": 10.0})


def cash(put, status):
    SCRIPT.clear(); SCRIPT[("PUT", "accept")] = put; SCRIPT[("GET", "status")] = status
    E.MINE["cash"][H] = {"rfq": "r1", "quote": "q1", "offer": 7.0, "frac": 1.0, "at": time.time(), "contracts": 10.0}
    CALLS.clear(); FRESH.clear()
    return attempt(E.accept_cash, H)


m, err = cash(boom(requests.Timeout("x")), {})
puts = sum(1 for mt, p in CALLS if p.endswith("/accept"))
ok("cash-out accept times out: one accept only (no fresh offer, no second accept), marked check",
   err is None and puts == 1 and not FRESH and unsure(H, "sell"), (m, err, puts, FRESH))
ok("...and the words say check Kalshi, no retry", bool(m) and m.startswith("⚠️") and "No retry" in m, m)
m, err = cash({}, {})
ok("a combo marked check: Cash out does nothing at all until it's cleared",
   err is None and not any(p.endswith("/accept") for _, p in CALLS) and m.startswith("⚠️"), (m, CALLS))
ledger_reset()
m, err = cash(boom(RuntimeError("Kalshi said: bad gateway (502)")), {})
ok("cash-out accept answers 502: stop, check", err is None and sum(1 for _, p in CALLS if p.endswith("/accept")) == 1
   and unsure(H, "sell"), (m, CALLS))
ledger_reset()
m, err = cash({}, {"quote": {"status": "accepted"}})
ok("cash-out never confirmed: stop, check", err is None and sum(1 for _, p in CALLS if p.endswith("/accept")) == 1
   and unsure(H, "sell") and not FRESH, (m, CALLS))
ledger_reset()
SEQ = [boom(RuntimeError("Kalshi said: quote expired (400)")), {}]
SCRIPT.clear()
E.MINE["cash"][H] = {"rfq": "r1", "quote": "q1", "offer": 7.0, "frac": 1.0, "at": time.time(), "contracts": 10.0}
SCRIPT[("PUT", "accept")] = lambda: (SEQ.pop(0)() if callable(SEQ[0]) else SEQ.pop(0))
SCRIPT[("GET", "status")] = {"quote": {"status": "executed"}}
CALLS.clear(); FRESH.clear()
m, err = attempt(E.accept_cash, H)
ok("a definite refusal (quote expired, 400) still gets a fresh offer, and that one sells",
   err is None and m and m.startswith("✅") and len(FRESH) == 1 and not unsure(H, "sell"), (m, err, FRESH))
i = SRC.index("def auto_sell_now")
ok("auto cash-out leaves a combo with an unknown cash-out alone (like hedge_unsure)",
   'rfq_unsure(t, "sell")' in SRC[i:SRC.index("\ndef ", i + 10)])
E.kalshi_send = real_send

# ================================================================ (5) killer deals: fail closed
import sqlite3
E.CFG["killer_mode"] = "on"
E.week_spend = lambda: 0
BUYS = []
LEGK = [{"ticker": "KXNBAGAME-26NOV19AAABBB-AAA", "pick": "AAA", "fair": 0.6}]


class LockedDB:
    def __init__(self, real, fail=("select", "insert", "update")):
        self.real, self.fail = real, fail

    def execute(self, sql, args=()):
        if sql.strip().split()[0].lower() in self.fail:
            raise sqlite3.OperationalError("database is locked")
        return self.real.execute(sql, args)


real_db = E.STORE["db"]
E.STORE["db"] = LockedDB(real_db)
st, err = attempt(E.killer_act, "single", LEGK, 5.0, 10.0, 1.3, lambda: (BUYS.append(1) or (True, "bought")), None, lambda *a: None)
ok("killer: history locked ('database is locked') = skip, never '0 bought today'", err is None and not BUYS, (st, err))
E.STORE["db"] = LockedDB(real_db, fail=("insert",))
st, err = attempt(E.killer_act, "single", LEGK, 5.0, 10.0, 1.3, lambda: (BUYS.append(1) or (True, "bought")), None, lambda *a: None)
ok("killer: can't write its record before buying = skip", err is None and not BUYS, (st, err))
E.STORE["db"] = real_db
SEEN = []


def buy_checks_record():
    rows = E.store_rows("select status from killer where legs=?", (json.dumps([LEGK[0]["ticker"]]),))
    SEEN.append([r["status"] for r in rows])
    return True, "bought"


st, err = attempt(E.killer_act, "single", LEGK, 5.0, 10.0, 1.3, buy_checks_record, None, lambda *a: None)
ok("killer: the dedupe record is written BEFORE the order goes out", err is None and SEEN and SEEN[0], (st, err, SEEN))
rows = E.store_rows("select status from killer where legs=?", (json.dumps([LEGK[0]["ticker"]]),))
ok("killer: ...and updated to 'bought' after (one row)", [r["status"] for r in rows] == ["bought"], rows)
BUYS.clear()
st, _ = attempt(E.killer_act, "single", LEGK, 5.0, 10.0, 1.3, lambda: (BUYS.append(1) or (True, "bought")), None, lambda *a: None)
ok("killer: the same deal again = nothing (one per deal)", not BUYS)
LEG2 = [{"ticker": "KXNBAGAME-26NOV19CCCDDD-CCC", "pick": "CCC", "fair": 0.6}]
E.TRADING_PAUSED = lambda: True
st, _ = attempt(E.killer_act, "single", LEG2, 5.0, 10.0, 1.3, lambda: (BUYS.append(1) or (True, "bought")), None, lambda *a: None)
ok("killer: Pause read live (the settings file still says 'on') = nothing bought", not BUYS and st == "paused", st)
E.TRADING_PAUSED = None
E.store_x("delete from killer", ())
E.store_x("insert into killer(ts, kind, legs, picks, mode, status, stake, pays, pct, why) values(?,?,?,?,?,?,?,?,?,?)",
          (time.time(), "single", "[]", "x", "on", "buying", 5.0, 10.0, 1.2, ""))
ok("killer: a deal left 'buying' (crash mid-order) counts toward today's cap", E.killer_today() == (1, 5.0))
E.store_x("update killer set ts=?", (time.time() - 600,))
msgs = getattr(E, "killer_sweep", lambda: [])()
rows = E.store_rows("select status from killer", ())
ok("killer: a deal stuck 'buying' becomes 'check', with an alert", rows and rows[0]["status"] == "check" and msgs
   and "may or may not" in msgs[0], (rows, msgs))
ok("...the watcher's history loop pushes that alert", "E.killer_sweep()" in WSRC)
E.store_x("delete from killer", ())
LEG3 = [{"ticker": "KXNBAGAME-26NOV19EEEFFF-EEE", "pick": "EEE", "fair": 0.6}]
E.TRADING_PAUSED = lambda: True
BUYS.clear()
st, _ = attempt(E.killer_act, "single", LEG3, 5.0, 10.0, 1.3, lambda: (BUYS.append(1) or (True, "bought")), None, lambda *a: None)
E.TRADING_PAUSED = None
st2, _ = attempt(E.killer_act, "single", LEG3, 5.0, 10.0, 1.3, lambda: (BUYS.append(1) or (True, "bought")), None, lambda *a: None)
ok("killer: a deal seen while paused can still be bought once Pete resumes", st == "paused" and BUYS == [1], (st, st2, BUYS))
E.CFG["killer_mode"] = "watch"
E.store_x("delete from killer", ())

# ================================================================ (6) the proxy and updates
import http.server, socket


class Slow(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        time.sleep(45)
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Slow)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()


class FakeHandler:
    def __init__(self):
        self.headers = {"Content-Type": "application/json"}
        self.client_address = ("127.0.0.1", 1)
        self.code, self.hdrs = None, {}
        import io
        self.wfile = io.BytesIO()

    def send_response(self, c):
        self.code = c

    def send_header(self, k, v):
        self.hdrs[k] = v

    def end_headers(self):
        pass


W.WEBAPP_PORT = srv.server_address[1]
W.PROXY_ACT_TIMEOUT = 1
W.log = lambda *a, **k: None
h = FakeHandler()
t0 = time.time()
W.webapp_proxy(h, "tok", "POST", "/app/api/act", b'{"a":"buy","i":1}')
try:
    out = json.loads(h.wfile.getvalue())
except ValueError:
    out = {}
ok("a tap the web app doesn't answer in time: JSON 504 'may or may not have gone through' (not the reload page)",
   h.code == 504 and "may or may not have gone through" in out.get("msg", "") and out.get("check") is True,
   (h.code, h.wfile.getvalue()[:120], round(time.time() - t0, 1)))
s = socket.socket(); s.bind(("127.0.0.1", 0)); free = s.getsockname()[1]; s.close()
W.WEBAPP_PORT = free
h = FakeHandler()
W.webapp_proxy(h, "tok", "POST", "/app/api/act", b'{"a":"buy","i":1}')
try:
    out = json.loads(h.wfile.getvalue())
except ValueError:
    out = {}
ok("web app not running: JSON 503 'nothing was done'", h.code == 503 and "nothing was done" in out.get("msg", ""), out)
W.WEBAPP_PORT = srv.server_address[1]
h = FakeHandler()
W.webapp_proxy(h, "tok", "POST", "/app/api/act", b'{"a":"panel_approve"}')
try:
    out = json.loads(h.wfile.getvalue())
except ValueError:
    out = {}
ok("a slow non-order tap: no 'check Kalshi' words", h.code == 504 and out.get("check") is False and "Kalshi" not in
   out.get("msg", "x Kalshi"), out)
ok("the proxy waits long enough for a full order tap (lock 20 s + quotes + accept + 15 s confirm)",
   int((re.search(r"^PROXY_ACT_TIMEOUT = (\d+)", WSRC, re.M) or [0, 0])[1]) >= 120)
W.TAP_BUSY = os.path.join(E.HERE, "tap.json")
E.save_json(W.TAP_BUSY, {"at": time.time()})
busy = getattr(W, "tap_busy", lambda: False)
fresh = busy()
E.save_json(W.TAP_BUSY, {"at": time.time() - 3600})
ok("a tap mid-order is seen by the update loop (a stale mark isn't)", fresh and not busy())
i = WSRC.index("def update_loop")
u = WSRC[i:WSRC.index("\ndef ", i + 10)]
ok("updates wait while a tap is placing an order", before(u, "tap_busy()", "update_if_newer(E, conf)"))
i = WSRC.index("def orphan_check")
ok("the web app's shutdown waits (bounded) for the tap lock", "alock.acquire(timeout=" in WSRC[i:i + 500])
ok("combo buy, cash-out, hedge and single-buy taps mark themselves mid-order",
   WSRC.count("with tap_mark(") >= 3)
i = WSRC.index("A.idea_single_buy(")
ok("a Live buy idea's single-game buy marks itself mid-order too", "with tap_mark():" in WSRC[i - 200:i])

# ================================================================ (7) the ledger across processes
ledger_reset()
prog = r"""
import os, sys, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.ORDER_LEDGER, E.HEDGES = sys.argv[1], sys.argv[2]
tag = sys.argv[3]
for k in range(60):
    E._mark_unsure({"ticker": f"T{tag}{k}", "side": "bid", "reduce_only": False, "coid": f"c{k}"}, "test")
    if hasattr(E, "hedges_update"):
        E.hedges_update(f"H{tag}{k}", n=1.0)
    else:
        d = E.load_json(E.HEDGES, {}); d[f"H{tag}{k}"] = {"n": 1.0}; E.save_json(E.HEDGES, d)
"""
procs = [subprocess.Popen([sys.executable, "-c", prog, E.ORDER_LEDGER, E.HEDGES, tag]) for tag in "ab"]
for p_ in procs:
    p_.wait(120)
led = E.load_json(E.ORDER_LEDGER, {})
hed = E.load_json(E.HEDGES, {})
ok("two processes marking unknown orders at once: none lost (file lock)", len(led) == 120, len(led))
ok("two processes writing combo_hedges.json at once: none lost", len(hed) == 120, len(hed))
_, err = attempt(E.save_json, os.path.join(E.HERE, "missing-dir", "x.json"), {"a": 1}, strict=True)
ok("a money-state write that fails raises (not swallowed)", isinstance(err, OSError), err)
good = E.ORDER_LEDGER
E.ORDER_LEDGER = os.path.join(E.HERE, "missing-dir", "orders.json")
E._ORDER_SHARED.recent.clear()
attempt(E._mark_unsure, {"ticker": "TLOST", "side": "bid", "reduce_only": False, "coid": "z"}, "test")
ok("...and an unknown order whose mark couldn't be saved still blocks a resend in this process", E.order_unsure("TLOST"))
E.ORDER_LEDGER = good
E.HEDGES = os.path.join(E.HERE, "missing-dir", "hedges.json")
if hasattr(E, "hedges_update"):
    attempt(E.hedges_update, "HLOST", check=1)
ok("a hedge 'check' mark that couldn't be saved still keeps auto cash-out off that combo", E.hedge_unsure("HLOST"))
E.HEDGES = os.path.join(E.HERE, "hedges.json")
ledger_reset()

# ================================================================ (8) Pause in the web app
i = WSRC.index("    def _api_act(d):")
act = WSRC[i:WSRC.index("\n    def ", i + 10)]
ok("web app: combo quote / buy idea / Buy refuse while paused",
   before(act, 'if a in ("quote", "idea", "buy") and paused_now():', 'if a == "quote":'))
ok("web app: the engine's own buy paths read the web app's Pause too", "A.TRADING_PAUSED = paused_now" in WSRC)
ok("web app: turning killer/standing orders on while paused doesn't take effect if the Mac didn't hear it",
   "if not synced and paused_now():" in WSRC)
ok("the shadow engine (killer, standing orders) reads Pause live", "self.H.TRADING_PAUSED = watcher_paused" in WSRC)
i = SRC.index("def maker_pass")
ok("standing orders: Pause read live turns 'on' into watch (real ones cancelled)",
   "trading_paused()" in SRC[i:i + 800])
ok("web app: an unclear combo Buy passes on 'check' (accept_offer's no-retry words)", '"check": bool(r.get("check"))' in act)

# ================================================================ (9) no balance, no real panel
E.fetch_account = lambda **k: (None, None, "Kalshi didn't answer")
E.ACCT_CACHE["at"] = 0
base, st = E.sizing_base()
ok("balance unreadable: no sizing base (not the $300 bankroll setting)", base is None, base)
E.PANEL_POOL.clear()
p = E.build_panel()
E.panel_save_draft(p, "real")
ok("...the draft says it was sized without the balance", p.get("base_guess") is True)
okk, why = E.panel_approve()
ok("...and it can't be approved", okk is False and "balance" in why, (okk, why))
E.fetch_account = lambda **k: ([], 250.0, None)
base, _ = E.sizing_base()
ok("balance readable again: sized from it", base is not None and abs(base - 250.0) < 1e-6, base)

# ================================================================ (10) release review fixes
W.RESTARTING = os.path.join(E.HERE, "restarting.json")
E.save_json(W.RESTARTING, {"at": time.time()})
fresh = W.restarting()
E.save_json(W.RESTARTING, {"at": time.time() - 3600})
ok("an installed update is seen by the web app (a stale mark isn't)", fresh and not W.restarting())
i = WSRC.index("def update_loop")
u = WSRC[i:WSRC.index("\ndef ", i + 10)]
ok("after installing, the watcher waits for quiet taps before it restarts",
   before(u, "restart_when_quiet()", 'UPDATED["now"] = True'))
i = WSRC.index("    def api_act(d):")
ok("the web app takes no new taps once an update is installed", "restarting()" in WSRC[i:i + 300])
ok("the proxy's 'check' words are only for taps that can move money (pot moves too, never price reads)",
   "pot_move" in W.ORDER_ACTS and not {"quote", "idea", "singlequote", "ask", "askhalf"} & set(W.ORDER_ACTS))
i = WSRC.index('if a == "buy":')
ok("an unexpected error on a combo Buy says 'may or may not', never 'nothing was bought'",
   "may or may not" in WSRC[i:i + 1400] and "nothing was bought. Try again" not in WSRC[i:i + 1400])
E.MINE["hold"] = {"CHK": {"label": "Combo X"}}
E._HEDGE_UNSURE_MEM["CHK"] = {"check": int(time.time())}
m = E.place_hedge("CHK", hg={"ticker": "KXNBAGAME-26NOV19NYKMIN-MIN", "name": "Wolves", "price": 0.3, "n": 20.0,
                             "fee": 0.3, "done": 0, "cost": 6.3, "locked": 13.7})
E._HEDGE_UNSURE_MEM.pop("CHK", None)
ok("a manual Hedge tap after an unclear (or unsaved) hedge buys nothing", m.startswith("⚠️") and "nothing was bought" in m)
