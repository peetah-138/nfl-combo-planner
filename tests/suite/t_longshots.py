# CHECK: group=engine
# Long shots on Build (issue #341): 6-8 pick full-slate combos, each pick 65-80% before its game on the market-anchored
# chance (Kalshi's mid, moved by the books only as far as they've earned; free lines never overrule the mid), never both
# sides of a game, a 7%+ chance to hit, combos sharing at most half their picks, Kalshi's quote at least the fair value
# after the fee (no quote = not shown), Pete's hold-to-win test (positive expected dollars held to the end, not smart_buy_ok), quarter Kelly capped at $5, pregame only, and
# fail closed on Pause / no trading / Kalshi refusing / an unknown-outcome block. Plus get_offer's green Buy for a long
# shot. Recommend-only: nothing here buys. Fakes only: no network, temp files, a temp history.
import os, time, tempfile, importlib.util, traceback, itertools
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
E.leg_score = lambda l: None


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)


def safe(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


class NoNet:
    RequestException = E.requests.RequestException

    def __getattr__(self, name):
        def call(*a, **k):
            raise E.requests.RequestException("no network in this test")
        return call


E.requests = NoNet()
now = time.time()
SENT = []
E.kalshi_send = lambda *a, **k: SENT.append(a) or (_ for _ in ()).throw(AssertionError("no Kalshi call in this test"))
E.started = lambda x: bool(x.get("_started"))
E.can_trade = lambda: True
E.role_backup = lambda: False
E.hold_refusal = lambda *a, **k: (None, "")
E.rfq_unsure = lambda *a, **k: False
E.calib_fair = lambda code, f, t=None, table="closes": f
E.mkt_weight = lambda *a: 0.0
E._manual_base = lambda: 1000.0
E.line_stale = lambda at, kick, now=None: False
E.TRADING_PAUSED = None


def game(i, fav, gap=0.02, started=False, sharp=True, book=None, kick_h=5):
    kick_h = -0.5 if started else kick_h                 # under way: its start time has passed
    ev = f"KXNFLGAME-26NOV29T{i:02d}U{i:02d}"
    E.KICKOFF[ev] = E.dt.datetime.fromtimestamp(now + kick_h * 3600, E.dt.timezone.utc).isoformat()
    mk = lambda tag, mid, b: {"ticker": f"{ev}-{tag}", "event": ev, "pick": f"Team {tag}", "p": round(mid + gap / 2, 4),  # noqa: E731
                              "bid": round(mid - gap / 2, 4), "fair": b, "src": "pinnacle" if b else None,
                              "sharp_line": sharp, "_started": started}
    return ev, [mk(f"T{i:02d}", fav, book if book is not None else fav), mk(f"U{i:02d}", 1 - fav, 1 - (book if book is not None else fav))]


def slate(favs, **kw):
    return dict(game(i, f, **kw) for i, f in enumerate(favs))




def quoter(px=0.90):
    """A fake combo maker: its YES price is `px` x the legs' chance (0.90 = it pays 1/0.9 of fair before the fee)."""
    calls = []

    def q(legs, stake):
        calls.append([l["ticker"] for l in legs])
        chance = E.math.prod(l["fair"] for l in legs)
        return chance * px
    q.calls = calls
    return q


def t_legs():
    g = slate([0.72, 0.75, 0.78, 0.70, 0.68, 0.74, 0.76, 0.55, 0.90, 0.60])
    pool, why = E.longshot_pool(g, now)
    ok("pool: one leg per game, only 65-80% picks (no coin flips, no big favourites, never under 50%)",
       len(pool) == 7 and len({l["event"] for l in pool}) == len(pool) and all(0.65 <= l["fair"] <= 0.80 for l in pool))
    ok("pool: the 55% / 90% / 60% games are left out by the range", why.get("range", 0) >= 3)
    g2 = slate([0.72, 0.75], started=True)
    ok("pool: games under way are never long-shot legs (pregame only)", E.longshot_pool(g2, now)[0] == [])
    g3 = slate([0.72], kick_h=0.2)
    ok("pool: a game starting within 20 minutes is out", E.longshot_pool(g3, now)[0] == [])
    g4 = slate([0.72], gap=0.12)
    ok("pool: no readable mid (gap over 10c) = out, fail closed", E.longshot_pool(g4, now)[0] == [])
    # the chance: Kalshi's mid; free lines that disagree never overrule it; a sharp line only by the earned weight
    ev, sd = game(30, 0.70, sharp=False, book=0.78)
    f, how = E.longshot_leg_fair(sd[0], now)
    ok("chance: a free-line-only fair that disagrees with the mid is ignored (the mid is used)", abs(f - 0.70) < 1e-9 and how == "mid")
    ev, sd = game(31, 0.70, sharp=True, book=0.78)
    ok("chance: with no earned weight the sharp book doesn't move the mid either", abs(E.longshot_leg_fair(sd[0], now)[0] - 0.70) < 1e-9)
    E.mkt_weight = lambda *a: 0.5
    f, how = E.longshot_leg_fair(sd[0], now)
    ok("chance: with an earned weight it blends mid and books (0.70 + 0.5 x 0.08 = 0.74)", abs(f - 0.74) < 1e-9 and how == "blend")
    E.mkt_weight = lambda *a: 0.0
    live = dict(sd[0], live=True, _started=False)
    ok("chance: a live-priced side is never a long-shot leg", E.longshot_leg_fair(live, now)[0] is None)


def t_combos():
    g = slate([0.72, 0.75, 0.78, 0.70, 0.68, 0.74, 0.76, 0.73, 0.71, 0.77, 0.69, 0.79])
    pool, _ = E.longshot_pool(g, now)
    cs = E.longshot_combos(pool, k=6)
    ok("combos: some candidates", len(cs) >= 2)
    ok("combos: 6 to 8 legs, never more than 8", all(6 <= len(c) <= 8 for c in cs))
    ok("combos: every one at least a 7% chance to hit", all(E.math.prod(l["fair"] for l in c) >= 0.07 for c in cs))
    ok("combos: never both sides of one game", all(len({l["event"] for l in c}) == len(c) for c in cs))
    ok("combos: each leg within 65-80%", all(0.65 <= l["fair"] <= 0.80 for c in cs for l in c))
    ok("combos: any two share at most half their picks",
       all(len({l["ticker"] for l in a} & {l["ticker"] for l in b}) * 2 <= min(len(a), len(b)) for a, b in itertools.combinations(cs, 2)))
    lows = slate([0.66] * 10)
    ok("combos: 0.66^7 = 5.5% is under the 7% floor, so only 6-pick combos (8.3%) are built",
       all(len(c) == 6 for c in E.longshot_combos(E.longshot_pool(lows, now)[0])))


def t_build():
    g = slate([0.72, 0.75, 0.78, 0.70, 0.68, 0.74, 0.76, 0.73, 0.71, 0.77])
    q = quoter(0.90)                                    # pays 1/0.90 of fair before the fee: clears after it
    recs, info = E.longshot_build(g, now=now, quote=q, paused=False)
    ok(f"build: 2-3 recommendations ({len(recs)}), ranked by expected dollars", 1 <= len(recs) <= 3
       and [r["exp"] for r in recs] == sorted([r["exp"] for r in recs], reverse=True))
    ok("build: each at least 100% of fair after the fee", all(r["pct"] >= 1.0 for r in recs))
    ok("build: stake is quarter Kelly capped at $5", all(1 <= r["stake"] <= 5.0 for r in recs))
    ok("build: card numbers (hit %, expected $ after the fee, stake, payout, fee)", all(
        {"chance", "exp", "route", "fee", "stake", "pays", "legs"} <= set(r) and r["exp"] > 0 for r in recs))
    ok("build: expected dollars = chance x contracts - cost (the order's fee rounded up)", all(
        abs(r["exp"] - round(r["chance"] * r["pays"] - r["stake"], 2)) <= 0.011 for r in recs))
    ok("build: no Kalshi order or request sent (the quote is the fake maker's)", SENT == [])
    recs, info = E.longshot_build(g, now=now, quote=quoter(1.0), paused=False)
    ok("build: a quote exactly at fair before the fee is under fair after it: not shown", recs == [] and info["skipped"].get("price"))
    recs, info = E.longshot_build(g, now=now, quote=lambda legs, st: None, paused=False)
    ok("build: no quote = not shown (fail closed) and says why", recs == [] and info["skipped"].get("quote") and info["why"])

    def boom(legs, st):
        raise RuntimeError("Kalshi doesn't offer this exact combo")
    recs, info = E.longshot_build(g, now=now, quote=boom, paused=False)
    ok("build: a quote that errors = not shown", recs == [] and info["skipped"].get("quote"))
    E._sb_sim = lambda c, now: (_ for _ in ()).throw(AssertionError("long shots don't use the exit simulator"))
    q = quoter(0.80)
    recs, info = E.longshot_build(g, now=now, quote=q, paused=False)
    ok("build: judged on holding to the end, not smart_buy_ok (the exit simulator is never asked)", len(recs) >= 1
       and all(r["route"] == "hold" for r in recs))
    q = quoter(0.80)
    wide = slate([0.72, 0.75, 0.78, 0.70, 0.68, 0.74, 0.76, 0.73, 0.71, 0.77], gap=0.08)
    recs, info = E.longshot_build(wide, now=now, quote=q, paused=False)
    ok("build: picks whose asks are far over the chance aren't even quoted (a maker would have to pay 11%+ over them)",
       recs == [] and q.calls == [])
    for name, kw, patch in (("paused", {"paused": True}, None), ("no trading", {"paused": False}, ("can_trade", lambda: False)),
                            ("Kalshi refusing", {"paused": False}, ("hold_refusal", lambda *a, **k: ({"x": 1}, "no"))),
                            ("the Pi", {"paused": False}, ("role_backup", lambda: True))):
        old = getattr(E, patch[0]) if patch else None
        if patch:
            setattr(E, patch[0], patch[1])
        q = quoter(0.8)
        recs, info = E.longshot_build(g, now=now, quote=q, **kw)
        ok(f"build: {name} = nothing shown, Kalshi not asked", recs == [] and q.calls == [] and info["why"])
        if patch:
            setattr(E, patch[0], old)
    E.rfq_unsure = lambda *a, **k: True
    q = quoter(0.8)
    recs, info = E.longshot_build(g, now=now, quote=q, paused=False)
    ok("build: an unknown-outcome block on the picks = skipped, never re-quoted (rule 8)", recs == [] and q.calls == [])
    E.rfq_unsure = lambda *a, **k: False
    first = E.longshot_combos(E.longshot_pool(g, now)[0])[0]
    q = quoter(0.8)
    E.longshot_build(g, now=now, quote=q, paused=False, skip={frozenset(l["ticker"] for l in first)})
    ok("build: a combo with a live quote on screen is never re-quoted underneath Pete", [l["ticker"] for l in first] not in q.calls)
    calls = []
    q = quoter(0.8)
    E.longshot_build(g, now=now, quote=q, paused=False, skip=lambda: calls.append(1) or set())
    ok("build: the on-screen offers are re-read before every quote (a callable skip)", len(calls) >= len(q.calls) >= 1)
    w = open("wtest/combo_watcher.py").read() if os.path.exists("wtest/combo_watcher.py") else ""
    ok("watcher: Buy refuses an offer for other picks than the ones shown (rule 7)",
       not w or ("expect_legs=shown" in w and "different combo" in open("wahome/engine.py").read()))
    ok("watcher: long shots are never worked out for a warm-up (only a Build Pete opened)", not w or "if not warming:" in w)
    ok("watcher: the act re-prices each pick fresh before quoting", not w or "A.longshot_leg_fair(x)" in w)
    g2 = slate([0.72, 0.75, 0.78, 0.70, 0.68, 0.74, 0.76, 0.73], started=True)
    recs, info = E.longshot_build(g2, now=now, quote=quoter(0.8), paused=False)
    ok("build: games under way are left out (in-play excluded)", recs == [] and info["why"])
    rows = E.store_rows("select * from longshot_log")
    ok("build: every quoted candidate is logged (measured)", len(rows) > 0)


def t_hold():
    h = E.longshot_hold(0.10, 0.08, 5.0)
    ok(f"hold: 10% to hit at 8c is a long shot worth holding ({h})", h and h["exp"] > 0 and h["cost"] <= 5.0 and h["pct"] >= 1.0)
    ok("hold: the fee is charged (never zero) and rounded up per order", h and h["fee"] >= 0.01 and abs(h["fee"] * 100 - round(h["fee"] * 100)) < 1e-6)
    ok("hold: under the 7% floor = no", E.longshot_hold(0.065, 0.05, 5.0) is None)
    ok("hold: exactly fair before the fee = no (under fair after it)", E.longshot_hold(0.10, 0.10, 5.0) is None)
    ok("hold: bad numbers fail closed", E.longshot_hold(0.10, None, 5.0) is None and E.longshot_hold(0.10, 0.0, 5.0) is None
       and E.longshot_hold(0.10, 0.08, 0.0) is None)
    E.LONGSHOT["fee_rate"] = 0.30
    ok("hold: a higher fee rate (once confirmed) is respected", E.longshot_hold(0.10, 0.093, 5.0) is None)
    E.LONGSHOT["fee_rate"] = None


def t_offer():
    """get_offer's green Buy for a long shot: the quote after the fee must pay at least its fair value."""
    E.CTX.clear()
    legs = [{"ticker": f"KXNFLGAME-X{i}-A", "event": f"KXNFLGAME-X{i}", "fair": 0.72, "p": 0.73} for i in range(7)]
    chance = 0.72 ** 7
    E.CTX.update(stake=5.0, offers={}, combos=[{"kind": "longshot", "legs": legs, "fair": 5.0 / chance, "min": 5.0 / chance * 0.95}])
    E.CFG.update(budget=500.0, accept_pct=95)
    calls = []

    def send(method, path, body=None, params=None):
        calls.append((method, path))
        if path.startswith("/multivariate_event_collections/"):
            return {"market_ticker": "KXMVE-1"}
        if path == "/communications/rfqs" and method == "POST":
            return {"id": "r1"}
        if path == "/communications/quotes":
            return {"quotes": [{"status": "open", "no_bid_dollars": f"{1 - PRICE[0]:.4f}", "id": "q1"}]}
        return {}
    E.kalshi_send = send
    E.find_collection = lambda legs: "COLL"
    E.clear_my_rfqs = lambda m: None
    E.week_spend = lambda: 0.0
    E.time.sleep = lambda s: None
    E.store_quote = lambda *a, **k: None
    E.carry_note = lambda *a, **k: None
    PRICE = [chance * 0.99]                               # pays ~101% of fair before the fee, under it after
    r = E.get_offer(1, 5.0, check_cap=False)
    ok(f"offer: 101% of fair before the fee is NOT a green Buy for a long shot (ok={r.get('ok')})", r.get("ok") is False)
    PRICE[0] = chance * 0.90
    r = E.get_offer(1, 5.0, check_cap=False)
    ok(f"offer: comfortably over fair after the fee is a green Buy (ok={r.get('ok')})", r.get("ok") is True)
    ok("offer: no accept was sent by a price request", not any("/accept" in p for _, p in calls))


for n, fn in (("legs", t_legs), ("combos", t_combos), ("build", t_build), ("hold", t_hold), ("offer", t_offer)):
    safe(n, fn)
