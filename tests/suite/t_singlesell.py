# CHECK: group=engine
# Sell a single bet by Pete's tap (issue #238): Live's single cards get "Get new price" and "Sell". The quote reads
# Kalshi's order book now (never a cached copy) and is good for 20 s; the sale re-reads the book, refuses a lower bid,
# and sends one fill-now-or-cancel, reduce-only sale at the quoted price, once per quote. Pause does not block it
# (Pete's own tap, #245), but every buy and every automatic sale still stop under Pause; an unclear
# answer is "check", the market is blocked and nothing is resent (rule 8); a thin market warns and needs Sell anyway.
# Also: a total's "On track" line follows the pace, not the running total (an Over is always under the line mid-game).
# Real signing code with a throwaway key; the network is fakenet (V2 order desk), so nothing can reach Kalshi.
import os, re, time, tempfile, importlib.util
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.ORDER_LEDGER = os.path.join(E.HERE, "orders.json")
E.set_league("nba")
E.CFG["kalshi_key_id"] = "fake-key-id"
E.hub_conf = lambda: None
E.haptic = lambda *a: None
import requests
import fakenet
fakenet.install(port=1)
D = fakenet.ORDERS
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
E.can_trade = lambda: True
T = "KXNCAAMBTOTAL-26NOV21DUKEUNC-157"
HELD = {"x": {"t": T, "ticker": T, "label": "Over 157.5 points", "kind": "total", "sport": "ncaamb", "side": "yes",
              "n": 16.0, "cost": 9.60, "pays": 16.0, "chance": 0.97, "state": "live", "res": None,
              "game": "Duke at North Carolina: Total Points"}}
E.open_singles = lambda max_age=30: [dict(HELD["x"])] if HELD["x"] else []
E.resting_single_sells = lambda: set()
READS = []
LOG = []


def book(bid, ask, bid_size=500, ask_size=500):
    def f(tk, max_age=60):
        READS.append(max_age)
        return {"bid": bid, "ask": ask, "spread": round(ask - bid, 4) if bid is not None and ask is not None else None,
                "ask_size": ask_size, "bid_size": bid_size, "thin": False}
    E.book_depth = f


def reset():
    D.update(mode="v2", sent=[], next=None, fill=None, headers={})
    E._ORDER_SHARED.recent.clear()
    E._ORDER_SHARED.unsure.clear()
    E.save_json(E.ORDER_LEDGER, {})
    READS.clear()
    HELD["x"]["side"], HELD["x"]["n"] = "yes", 16.0
    book(0.94, 0.96)


def sell(q, **k):
    return E.single_sell(q["q"], q["t"], log=LOG.append, **k)


# ---- (1) the quote: a fresh book, what comes back after the fee
reset()
q = E.single_sell_quote(T)
fee = E.single_fee(0.94, 16)
ok(f"quote reads the book fresh (max_age=0): bid 94c, gap 2c ({READS})", q["ok"] and READS == [0]
   and abs(q["bid"] - 0.94) < 1e-9 and abs(q["gap"] - 0.02) < 1e-9)
ok(f"16 contracts, back = 16 x (94c - fee) = {q['got']}, profit vs $9.60 paid", q["n"] == 16
   and q["got"] == round(16 * (0.94 - fee), 2) and q["profit"] == round(q["got"] - 9.60, 2) and q["cost"] == 9.60)
ok("worth now = held x bid (Live's own rule), clears (green Sell), no warnings, 16-hex id, 20 s",
   q["worth"] == round(16 * 0.94, 2) and q["clears"] and not q["warn"] and len(q["q"]) == 16 and q["secs"] == 20)
ok("nothing was sent by a quote", not D["sent"])
HELD["x"]["side"] = "no"
book(0.03, 0.05)
qn = E.single_sell_quote(T)
ok(f"a NO bet sells at NO's bid = 1 - YES's ask (95c) ({qn.get('bid')})", qn["ok"] and abs(qn["bid"] - 0.95) < 1e-9
   and abs(qn["ask"] - 0.97) < 1e-9)
reset()
book(0.94, 0.96, bid_size=10)
qd = E.single_sell_quote(T)
ok("only 10 wanted at the bid: sells 10, says so", qd["n"] == 10 and any(w["k"] == "depth" for w in qd["warn"]))
HELD["x"] = None
ok("a bet you no longer hold: no quote", not E.single_sell_quote(T)["ok"])
HELD["x"] = {"t": T, "ticker": T, "label": "Over 157.5 points", "kind": "total", "sport": "ncaamb", "side": "yes",
             "n": 16.0, "cost": 9.60, "pays": 16.0, "chance": 0.97, "state": "live", "res": None, "game": "x"}
reset()
book(None, 0.96)
ok("nobody bidding: no price, nothing to sell at", not E.single_sell_quote(T)["ok"])
reset()
E.book_depth = lambda tk, max_age=60: None
ok("an unreadable book: no quote (never a cached or guessed price)", not E.single_sell_quote(T)["ok"])

# ---- (2) the sale: one reduce-only IOC order at the quoted bid, once
reset()
q = E.single_sell_quote(T)
r = sell(q)
m, p, body, _ = D["sent"][-1]
ok(f"sell: one V2 order, ask (sell YES) '0.9400' x '16.00', IOC, reduce-only, the quote's client id ({r.get('msg')})",
   r["ok"] and r["sold"] == 16 and len(D["sent"]) == 1 and p.endswith("/portfolio/events/orders")
   and body["side"] == "ask" and body["price"] == "0.9400" and body["count"] == "16.00"
   and body["time_in_force"] == "immediate_or_cancel" and body.get("reduce_only") is True
   and body["client_order_id"] == "cw-ss-" + q["q"])
ok("the answer has what came back and what those contracts cost (for the Sold sheet)",
   r["got"] == q["got"] and r["cost"] == 9.60 and r["msg"].startswith("✅"))
r2 = sell(q)
ok("the same quote tapped again: refused, still one order", not r2["ok"] and "already used" in r2["msg"] and len(D["sent"]) == 1)
reset()
q = E.single_sell_quote(T)
ok("a sell quote can never buy (Buy straight refuses it)", not E.single_buy(q["q"], T)["ok"] and not D["sent"])
HELD["x"]["side"] = "no"
book(0.03, 0.05)
q = E.single_sell_quote(T)
r = sell(q)
body = D["sent"][-1][2]
ok("a NO bet's sale goes on the YES book as a bid at 1 - 95c = '0.0500'", r["ok"] and body["side"] == "bid"
   and body["price"] == "0.0500" and body.get("reduce_only") is True)

# ---- (3) Pause does NOT block Pete's own sale (Pete's decision on #245); every other guard still holds
reset()
qp = E.single_sell_quote(T, paused=True)
ok("Pause on: a quote still comes, from a fresh book, with the calm note",
   qp["ok"] and qp.get("paused") is True and READS == [0] and qp["clears"]
   and qp.get("paused_note") == "Pause is on. This is your own sale, so it still works.")
ok("Pause off: no note", E.single_sell_quote(T).get("paused") is False and not E.single_sell_quote(T).get("paused_note"))
LOG.clear()
r = sell(qp, paused=True)
m, p, body, _ = D["sent"][-1]
ok(f"Pause on: the sale goes through, one IOC reduce-only order at the quoted bid ({r.get('msg')})",
   r["ok"] and len(D["sent"]) == 1 and body["side"] == "ask" and body["price"] == "0.9400"
   and body["time_in_force"] == "immediate_or_cancel" and body.get("reduce_only") is True
   and body["client_order_id"] == "cw-ss-" + qp["q"])
ok("...and the log says it was Pete's own tap while paused", any("while Pause is on" in x for x in LOG))
ok("Pause on: the same quote again is still refused (one order per quote)", not sell(qp, paused=True)["ok"]
   and len(D["sent"]) == 1)
reset()
q = E.single_sell_quote(T, paused=True)
_flip, _bd = {"p": False}, E.book_depth
def _bd_pause(tk, max_age=60):                      # Pause comes on while the book is re-read
    _flip["p"] = True
    return _bd(tk, max_age=max_age)
E.book_depth = _bd_pause
r = sell(q, paused=lambda: _flip["p"])
E.book_depth = _bd
ok("Pause turned on during the book re-read: still sells (one order)", r["ok"] and len(D["sent"]) == 1)
reset()
q = E.single_sell_quote(T, paused=lambda: 1 / 0)
ok("a Pause that can't be read: the note shows (counts as paused), the sale still works",
   q["ok"] and q["paused"] and sell(q, paused=lambda: 1 / 0)["ok"] and len(D["sent"]) == 1)
reset()
E.can_trade = lambda: False
ok("Pause on + no trading access (the Pi): no quote, nothing read", not E.single_sell_quote(T, paused=True)["ok"]
   and not READS)
E.can_trade = lambda: True
q = E.single_sell_quote(T, paused=True)
E.can_trade = lambda: False
ok("Pause on + trading access lost after the quote: refused, nothing sent", not sell(q, paused=True)["ok"] and not D["sent"])
E.can_trade = lambda: True
reset()
book(0.80, 0.90)
q = E.single_sell_quote(T, paused=True)
ok("Pause on + thin market: still needs Sell anyway", not sell(q, paused=True)["ok"] and not D["sent"])
reset()
q = E.single_sell_quote(T, paused=True)
book(0.92, 0.95)
r = sell(q, paused=True)
ok("Pause on + the bid dropped: refused, nothing sent", not r["ok"] and r.get("moved") and not D["sent"])
reset()
q = E.single_sell_quote(T, paused=True)
D["next"] = requests.Timeout("slow")
r = sell(q, paused=True)
ok("Pause on + unclear answer: 'check', blocked, one order", r.get("check") and E.order_unsure(T) and len(D["sent"]) == 1)
q2 = E.single_sell_quote(T, paused=True)
ok("Pause on + the unknown-outcome block: blocked, never resent", q2["blocked"] and not sell(q2, paused=True, anyway=True)["ok"]
   and len(D["sent"]) == 1)
reset()
q = E.single_sell_quote(T, paused=True)
r = E.single_sell(q["q"], T, paused=True, now=time.time() + 25, log=LOG.append)
ok("Pause on + a quote over 20 s old: expired", not r["ok"] and r.get("expired") and not D["sent"])

# ---- (3b) everything else still stops under Pause: every buy and every automatic sale
reset()
ok("Buy straight: no quote while paused", not E.single_buy_quote({"t": T}, 5, paused=True)["ok"] and not D["sent"])
ok("Buy straight: the buy itself refuses while paused", not E.single_buy("0" * 16, T, paused=True)["ok"] and not D["sent"])
r = E.idea_single_buy(T, 3, 0.50, paused=True, log=LOG.append, key="i1")
ok("Live idea single buy: refused while paused, nothing sent", not r["ok"] and r["msg"] == E.PAUSE_MSG and not D["sent"])
E.CTX.setdefault("offers", {})[901] = {"rfq": "rfq-x", "pays": 10, "stake": 5}
E.TRADING_PAUSED = lambda: True
r = E.accept_offer(901)
E.TRADING_PAUSED = None
ok("combo buy (accept_offer): refused while paused, no accept sent",
   r.get("paused") and not any(x[0] == "PUT" for x in D["sent"]))
E.CFG["auto_sell"] = False                            # what Pause sets (watcher pause())
ok("auto cash-out / smart sell / auto-hedge: off while paused (auto_sell_now does nothing)",
   E.auto_sell_now({"acts": {"KXMVE-X": 1.0}}) == [] and not D["sent"])
PSRC = open("wtest/combo_watcher.py", encoding="utf-8").read()
pz = PSRC[PSRC.index("def pause(conf, E):"):PSRC.index("def pause(conf, E):") + 1200]
ok("Pause turns off auto cash-out (smart sell, hedge), killer deals and standing orders",
   'E.CFG["auto_sell"] = False' in pz and 'E.CFG["killer_mode"] = "watch"' in pz and 'E.CFG["maker_mode"] = "watch"' in pz)
ok("the panel's buys get Pause", 'H.panel_exec(log=log, paused=bool(conf.get("paused"))' in PSRC)
ok("the web app's combo quote/idea/Buy, Buy straight and idea buys still pass Pause",
   'if a in ("quote", "idea", "buy") and paused_now():' in PSRC
   and 'single_buy_quote(single_side(t, lg), d.get("stake"), paused=paused_now())' in PSRC
   and 'A.single_buy(str(d["q"]), t, anyway=bool(d.get("anyway")), paused=paused_now(), log=log)' in PSRC
   and "A.idea_single_buy(tk, n, price, paused=paused_now()" in PSRC)
reset()
E.can_trade = lambda: False
ok("no trading access: no quote", not E.single_sell_quote(T)["ok"])
E.can_trade = lambda: True

# ---- (4) unknown outcome: "check", the market blocked, never resent
reset()
q = E.single_sell_quote(T)
D["next"] = requests.Timeout("slow")
r = sell(q, anyway=True)
ok("timeout: 'check' (may or may not have sold), one order sent", not r["ok"] and r.get("check")
   and "may or may not" in r["msg"] and len(D["sent"]) == 1)
ok("the market is blocked (listed in Settings)", E.order_unsure(T) and any(b["ticker"] == T for b in E.order_blocks()))
r = sell(q, anyway=True)
ok("the unclear quote tapped again: refused, never resent", not r["ok"] and len(D["sent"]) == 1)
q2 = E.single_sell_quote(T)
ok("a new quote is blocked and can't sell", q2["ok"] and q2["blocked"] and not q2["clears"]
   and not sell(q2, anyway=True)["ok"] and len(D["sent"]) == 1)
reset()
q = E.single_sell_quote(T)
D["next"] = (503, "service_unavailable")
r = sell(q)
ok("503: 'check' too, blocked", r.get("check") and E.order_unsure(T) and len(D["sent"]) == 1)
reset()
q = E.single_sell_quote(T)
D["next"] = (400, "invalid_order")
r = sell(q)
ok(f"a definite refusal: plain words, not 'check', no block ({r['msg'][:60]})", not r["ok"] and not r.get("check")
   and not E.order_unsure(T))
reset()
q = E.single_sell_quote(T)
D["fill"] = 0
r = sell(q)
ok("nobody took it (IOC filled 0): says nothing was sold", not r["ok"] and "Nothing was sold" in r["msg"])

# ---- (5) a thin market warns and needs Sell anyway (never silently)
reset()
book(0.80, 0.90)
q = E.single_sell_quote(T)
ok("10c gap: a thin-market warning, not green", q["ok"] and q["thin"] and not q["clears"]
   and any(w["k"] == "thin" for w in q["warn"]))
r = sell(q)
ok("Sell (not anyway) on a thin market: refused, nothing sent", not r["ok"] and "Sell anyway" in r["msg"] and not D["sent"])
q = E.single_sell_quote(T)
r = sell(q, anyway=True)
ok("Sell anyway: one order", r["ok"] and len(D["sent"]) == 1)
reset()
book(0.80, None)
q = E.single_sell_quote(T)
ok("nobody selling (no ask): thin too", q["ok"] and q["thin"] and not q["clears"])

# ---- (6) a stale or moved book refuses
reset()
q = E.single_sell_quote(T)
book(0.92, 0.95)
r = sell(q)
ok("the bid dropped since the quote: refused, nothing sent", not r["ok"] and r.get("moved") and not D["sent"])
reset()
q = E.single_sell_quote(T)
E.book_depth = lambda tk, max_age=60: None
r = sell(q)
ok("the book can't be read at the sale: refused, nothing sent", not r["ok"] and not D["sent"])
reset()
q = E.single_sell_quote(T)
r = E.single_sell(q["q"], T, now=time.time() + 25, log=LOG.append)
ok("a quote over 20 s old: expired, nothing sent", not r["ok"] and r.get("expired") and not D["sent"])
ok("someone else's quote id: refused", not E.single_sell("0" * 16, T, log=LOG.append)["ok"] and not D["sent"])

# ---- (7) the web app's act: inside the app lock, Pause read fresh, a money tap for the proxy
WSRC = open("wtest/combo_watcher.py", encoding="utf-8").read()
i = WSRC.index('if a == "singlesell":')
ok("the act passes Pause as a callable read fresh (paused_now) and marks the tap busy", "paused=paused_now," in WSRC[i:i + 900]
   and "tap_mark()" in WSRC[i:i + 900] and WSRC.rindex("with act_lock():", 0, i) > WSRC.index("def _api_act"))
ok("both sell acts refuse on the Pi (backup_now, read fresh) before anything else",
   WSRC.count("if backup_now():") == 2 and WSRC.index("if backup_now():", WSRC.index('if a == "sellquote":')) < i + 300
   and "if backup_now():" in WSRC[i:i + 400])
ok("Sell anyway only on an explicit true", 'd.get("anyway") is True' in WSRC[i:i + 900])
ok("singlesell is a money tap for the proxy ('may or may not' on a timeout)",
   re.search(r'ORDER_ACTS = \([^)]*"singlesell"', WSRC) is not None)
ok("no automatic path calls the manual sale", WSRC.count("single_sell(") == 1)

# ---- (8) a total's line follows the pace (the screenshot: 'Not on track' at 97%)
sc = lambda me, opp, frac, st="in": {"me": me, "opp": opp, "frac": frac, "state": st}
h = E._single_how("total", "yes", 157.5, sc(70, 69, 0.2))
ok(f"Over 157.5 at 139 with 80% played: on pace for 174 = On track ({h})", h.startswith("On track") and "174" in h)
h = E._single_how("total", "yes", 157.5, sc(70, 69, 0.05))
ok(f"139 with 95% played: pace 146 = Not on track ({h})", h.startswith("Not on track"))
h = E._single_how("total", "yes", 157.5, sc(80, 80, 0.1))
ok(f"160 already: Over the line ({h})", h.startswith("Over the line"))
h = E._single_how("total", "no", 157.5, sc(80, 80, 0.1))
ok(f"an Under at 160: Not on track ({h})", h.startswith("Not on track"))
h = E._single_how("total", "no", 157.5, sc(50, 50, 0.3))
ok(f"an Under at 100 with 70% played (pace 143): On track ({h})", h.startswith("On track"))
h = E._single_how("total", "yes", 157.5, sc(10, 9, 0.9))
ok(f"too early for a pace: neutral words, no verdict ({h})", not h.startswith(("On track", "Not")))
h = E._single_how("total", "yes", 157.5, sc(75, 70, None, "post"))
ok(f"final under the line: Not on track ({h})", h.startswith("Not on track") and "final" in h)
