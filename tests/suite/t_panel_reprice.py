# CHECK: group=engine
# Issue #358: tapping a Skipped / Didn't buy card on today's panel asks where that exact bet would land now
# (panel_reprice). Read only: refused while paused, only a skipped/failed card on the stored real panel (rule 7: never
# another bet), a market with an unknown order outcome is never priced (rule 8), the combo's quote request is dropped and
# never accepted, a pick under way only on its live chance, judged on the panel's own buy-time bar, the panel never
# changes. Plus the web app's act (paused refusal, debounce, errors). Fakes only: no network, a temp history.
import os, json, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)


def safe(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


L1 = {"ticker": "KXNBAGAME-X1-A", "event": "KXNBAGAME-X1", "fair": 0.70, "p": 0.66, "pick": "Alpha"}
L2 = {"ticker": "KXNBAGAME-X2-B", "event": "KXNBAGAME-X2", "fair": 0.60, "p": 0.57, "pick": "Beta"}
PANEL = {"status": "approved", "items": [
    {"id": "combo:1", "kind": "combo", "state": "skipped", "legs": [L1, L2], "stake": 5.0, "fair_mult": 1 / 0.42,
     "code": "NN", "note": "no longer priced well enough, and nothing similar qualified"},
    {"id": "single:1", "kind": "single", "state": "failed", "legs": [L1], "stake": 5.0, "note": "no price on Kalshi"},
    {"id": "combo:2", "kind": "combo", "state": "bought", "legs": [L1, L2], "stake": 5.0, "fair_mult": 1 / 0.42}]}
SENT, PRICE, BOOK = [], [0.42 / 1.05], {}
E.panel_get = lambda mode="real", day=None: json.loads(json.dumps(PANEL))
E.panel_tx = lambda *a, **k: SENT.append(("panel_tx",))
E.hold_refusal = lambda *a, **k: (None, "")
E.order_unsure = lambda t: False
E.rfq_unsure = lambda *a, **k: False
E.started = lambda l: bool(l.get("_started"))
E.book_depth = lambda t, max_age=60: BOOK.get(t)
E.news_gap = lambda x, ask=None: None
E.combo_cutoff = lambda code, n, legs=None: 0.95
E.smart_buy_on = lambda: False
E.find_collection = lambda legs: "C"
E.clear_my_rfqs = lambda m: None
E.time.sleep = lambda s: None
E.store_quote = E.carry_note = E.note_quote_time = E.note_buy_ratio = lambda *a, **k: None


def send(m, p, body=None, params=None):
    SENT.append((m, p))
    if p.startswith("/multivariate"):
        return {"market_ticker": "M"}
    if p == "/communications/rfqs" and m == "POST":
        return {"id": "r9"}
    if p == "/communications/quotes":
        return {"quotes": [{"status": "open", "no_bid_dollars": f"{1 - PRICE[0]:.4f}", "id": "q"}]}
    return {}


E.kalshi_send = send


def t_refusals():
    r = E.panel_reprice("combo:1", paused=True)
    ok(f"paused: refused, nothing sent ({r.get('msg')[:30]})", r["ok"] is False and r.get("paused") and not SENT)
    r = E.panel_reprice("combo:9")
    ok("a bet not on today's panel: refused (rule 7: only the bet on screen)", r["ok"] is False and not SENT)
    r = E.panel_reprice("combo:2")
    ok("a bought bet: refused (only Skipped / Didn't buy)", r["ok"] is False and "Skipped" in r["msg"] and not SENT)
    E.order_unsure = lambda t: t == L1["ticker"]
    r = E.panel_reprice("combo:1")
    ok("an earlier order with no clear answer: never priced again (rule 8), says check", r["ok"] is False and r.get("check")
       and not SENT)
    E.order_unsure = lambda t: False
    E.hold_refusal = lambda *a, **k: (True, "Kalshi is refusing orders")
    ok("Kalshi refusing this account: refused", E.panel_reprice("combo:1")["ok"] is False and not SENT)
    E.hold_refusal = lambda *a, **k: (None, "")


def t_combo():
    SENT.clear()
    PRICE[0] = 0.42 / 1.05
    ctx_before = dict(E.CTX)
    r = E.panel_reprice("combo:1")
    ok(f"a combo at 105% of fair, bar 95%: would buy ({r.get('verdict')}, {r.get('pct')})",
       r["ok"] and r["would"] and abs(r["pct"] - 1.05) < 0.01 and r["bar"] == "95% of fair")
    ok("the quote request was dropped, never accepted", ("DELETE", "/communications/rfqs/r9") in SENT
       and not any("accept" in p for _, p in SENT))
    ok("the panel was not changed and the planner's context is back as it was",
       not any(x == ("panel_tx",) for x in SENT) and dict(E.CTX) == ctx_before)
    PRICE[0] = 0.42 / 0.90
    r = E.panel_reprice("combo:1")
    ok(f"at 90%: still wouldn't buy, in words ({r.get('why')})", r["ok"] and not r["would"] and "95%" in r["why"]
       and r["verdict"] == "Still wouldn't buy")
    PRICE[0] = 0.42 / 1.40
    r = E.panel_reprice("combo:1")
    ok(f"at 140%: too far over to trust, not a buy ({r.get('why')[:40]})", not r["would"] and "trust" in r["why"])


def t_live():
    SENT.clear()
    PANEL["items"][0]["legs"] = [dict(L1, _started=True), L2]
    r = E.panel_reprice("combo:1")
    ok(f"a pick under way with no live chance: no fair price, no quote asked for ({r.get('why')})",
       r["ok"] and not r["would"] and r["verdict"] == "No fair price right now" and r["live"]
       and not any(p == "/communications/rfqs" for _, p in SENT))
    BOOK[L1["ticker"]] = {"ask": 0.42, "bid": 0.40}
    E.live_side_fair = lambda x, now=None, refresh=True: (0.43, "line", None)
    E.inplay_exit_ok = lambda c, sim=None, now=None, source=None: (False, "a profitable exit doesn't look likely")
    E._sb_sim = lambda c, now: {}
    PRICE[0] = 0.43 * 0.60 / 1.05
    r = E.panel_reprice("combo:1")
    ok(f"under way, 105% of the LIVE fair but the in-play test says no: wouldn't buy ({r.get('why')})",
       r["ok"] and not r["would"] and "exit" in r["why"])
    E.inplay_exit_ok = lambda c, sim=None, now=None, source=None: (True, None)
    r = E.panel_reprice("combo:1")
    ok(f"...and with the in-play test passing: a good live price is allowed ({r.get('pct')})",
       r["would"] and abs(r["pct"] - 1.05) < 0.01 and "live chance" in r["why"])
    # the reason after "Kalshi pays $X for $Y." starts with a capital and ends in exactly one period,
    # whether the under-fair text is a lowercase fragment or already a full sentence
    sq, ip = E._sb_quote_under_fair, E._reprice_inplay
    try:
        for label, frag, want in (("fragment", "the game is under way and a sale doesn't look likely", "The game is under way and a sale doesn't look likely."),
                                  ("full sentence", "It is under the fair price.", "It is under the fair price.")):
            E._sb_quote_under_fair = lambda c, pct, f=frag: f
            r = E.panel_reprice("combo:1")
            ok(f"reprice reason, {label}: capital and one period ({r.get('why')})",
               r["ok"] and not r["would"] and r["why"].endswith(". " + want) and not r["why"].endswith(".."))
    finally:
        E._sb_quote_under_fair, E._reprice_inplay = sq, ip
    PANEL["items"][0]["legs"] = [L1, L2]


def t_single():
    SENT.clear()
    BOOK[L1["ticker"]] = {"ask": 0.60, "bid": 0.58}
    r = E.panel_reprice("single:1")
    fee = E.single_fee(0.60)
    ok(f"a single at 60c + fee against 70%: would buy ({r.get('why')})", r["ok"] and r["would"] and abs(r["fee"] - fee) < 1e-4)
    BOOK[L1["ticker"]] = {"ask": 0.69, "bid": 0.67}
    r = E.panel_reprice("single:1")
    ok(f"at 69c it isn't 2% better after the fee: still wouldn't buy ({r.get('why')})", r["ok"] and not r["would"])
    BOOK.pop(L1["ticker"])
    r = E.panel_reprice("single:1")
    ok("nobody selling: no price right now", r["ok"] and not r["would"] and r["verdict"] == "No price right now")
    ok("a single never sends anything to Kalshi's order or quote endpoints",
       not any(x[0] == "POST" for x in SENT))


def t_watcher():
    w = open("wtest/combo_watcher.py", encoding="utf-8").read()
    ok("the act is refused while paused", 'if a == "panel_reprice" and paused_now():' in w)
    blk = w[w.index('if a == "panel_reprice":'):w.index('if a == "panel_approve":')]
    ok("the act: one fresh price per card every few seconds, the id capped, errors in plain words",
       "REPRICE_SECS" in blk and '[:120]' in blk and "except Exception" in blk and "A.panel_reprice(pid, paused=paused_now())" in blk)
    ok("the act never buys", "accept" not in blk and "panel_approve" not in blk.split("if a ==")[1])
    src = open("wtest/spa/build.js", encoding="utf-8").read()
    ok("the card calls only panel_reprice", "a:'panel_reprice',id" in src and "function pReprice" in src)


for n, fn in (("refusals", t_refusals), ("combo", t_combo), ("live", t_live), ("single", t_single), ("watcher", t_watcher)):
    safe(n, fn)
