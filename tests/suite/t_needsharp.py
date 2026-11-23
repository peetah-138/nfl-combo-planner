# CHECK: group=engine
# Killer deals and standing orders need an odds-service line (Pete, 2026-11-23, issue #344). Free lines (ESPN's posted
# moneyline, Polymarket) alone never trigger a killer deal or rest a standing order; a price an odds-service line backs
# is treated exactly as before. Stricter only: nothing new is ever bought or posted. Everything is faked, no network.
import os, re, time, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
NOW = time.time()
SRC = open("wahome/engine.py").read()
SENT = []                                                   # every Kalshi write any path tried


def fake_send(method, path, body=None, **k):
    SENT.append((method, path))
    return {"order": {"order_id": "o1", "status": "resting"}}


E.kalshi_send = fake_send
E._maker_status = lambda oid: ("resting", 0)
E.injury_note = lambda code, *teams, hours=48: ([], False)
E.started = lambda x: False
E.steady = lambda t, f, mins=None: True
E.book_depth = lambda t, max_age=None: {"thin": False, "ask": 0.5, "ask_size": 100}
E.trading_paused = lambda: False
E.role_backup = lambda: False
E.can_trade = lambda: True
E.week_spend = lambda *a, **k: 0.0
E.maker_fair = lambda x: x["fair"]
POSTS = []
E._maker_post = lambda t, n, price, exp: POSTS.append((t, n, price)) or "oid-1"

FREE = {"parts": {"Hawks": {"sportsbook": 0.55, "polymarket": 0.56}}}
SHARP = {"parts": {"Hawks": {"sportsbook": 0.55, "polymarket": 0.56, "pinnacle": 0.555}}}
STALE = {"parts": {"Hawks": {"sportsbook": 0.55, "pinnacle": 0.555}}, "sharp_stale": ["Hawks"]}
FAR = {"parts": {"Hawks": {"sportsbook": 0.55, "polymarket": 0.56, "odds service": 0.62}}}


def section(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


def sec_a():
    ok("A: free lines alone (two agreeing) used to be enough for the two-source rule", E.sources_agree(FREE, "Hawks", 0.55)[0])
    ok("A: ...but they don't back the price", E.sharp_backed(FREE, "Hawks", 0.55) is False)
    ok("A: an odds-service line within 2 points does", E.sharp_backed(SHARP, "Hawks", 0.55) is True)
    ok("A: the 'odds service' name counts the same as Pinnacle",
       E.sharp_backed({"parts": {"Hawks": {"odds service": 0.55}}}, "Hawks", 0.55) is True)
    ok("A: matched by the team's last word, as sources_agree is", E.sharp_backed(SHARP, "Atlanta Hawks", 0.55) is True)
    ok("A: a sharp line too old for this game (merge_books gave way to a free one) doesn't", not E.sharp_backed(STALE, "Hawks", 0.55))
    ok("A: a sharp line far from the fair chance doesn't", not E.sharp_backed(FAR, "Hawks", 0.55))
    ok("A: no snapshot / no parts / unknown team / junk = not backed (fails closed)",
       not any(E.sharp_backed(s, "Hawks", 0.55) for s in (None, {}, {"parts": {}}, {"parts": {"Hawks": None}},
                                                          {"parts": {"Bulls": {"pinnacle": 0.55}}},
                                                          {"parts": {"Hawks": {"pinnacle": "0.55"}}}, "junk")))
    ok("A: sources_agree itself is unchanged on the same inputs",
       E.sources_agree(SHARP, "Hawks", 0.55) == (True, 3) and E.sources_agree(FAR, "Hawks", 0.55) == (True, 3)
       and E.sources_agree({}, "Hawks", 0.55) == (False, 0))


def sec_b():
    sharp = {"games": {"Hawks": [{"fair": [0.6, "Pinnacle"], "start": "2026-11-23T20:00:00Z", "at": NOW - 7200}]},
             "fair": {"Hawks": [0.6, "Pinnacle"]}, "opp": {}, "kick": {}, "note": ""}
    free = {"games": {"Hawks": [{"fair": [0.55, "ESPN"], "start": "2026-11-23T20:00:00Z", "at": NOW - 60}]},
            "fair": {"Hawks": [0.55, "ESPN"]}, "opp": {}, "kick": {}, "note": "ESPN",
            "parts": {"Hawks": {"sportsbook": 0.55}}}
    kick = NOW + 3600
    for g in (sharp, free):
        g["games"]["Hawks"][0]["start"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(kick))
    out = E.merge_books(sharp, free, NOW)
    ok("B: merge_books names a team whose sharp line was too old (fair from the free line)",
       out["sharp_stale"] == ["Hawks"] and out["fair"]["Hawks"][0] == 0.55)
    ok("B: ...so that stale sharp line can't back a killer deal or standing order",
       not E.sharp_backed(out, "Hawks", 0.55))
    sharp["games"]["Hawks"][0]["at"] = NOW - 60
    out = E.merge_books(sharp, free, NOW)
    ok("B: a fresh sharp line: nothing stale, and it backs its own price",
       out["sharp_stale"] == [] and E.sharp_backed(out, "Hawks", 0.6))


def leg(pick="Hawks", fair=0.55):
    return {"pick": pick, "ticker": "KXNBAGAME-26NOV23ATLBOS-ATL", "event": "KXNBAGAME-26NOV23ATLBOS", "fair": fair, "p": 0.45}


def sec_c():
    good, why = E.killer_check([leg()], FREE)
    ok("C: killer deal on free lines only: held back", good is False)
    ok("C: ...with a plain reason", why == [f"Hawks: {E.NEED_SHARP_WHY}"])
    good, why = E.killer_check([leg()], SHARP)
    ok("C: killer deal an odds-service line backs: passes as before", good is True and why == [])
    good, why = E.killer_check([leg()], STALE)
    ok("C: a stale sharp line: held back", good is False and any(E.NEED_SHARP_WHY in w for w in why))
    good, why = E.killer_check([leg(), leg("Bulls")], {"parts": dict(SHARP["parts"], Bulls={"sportsbook": 0.55, "polymarket": 0.55})})
    ok("C: a combo with one free-only leg: held back, naming that leg", good is False and why == [f"Bulls: {E.NEED_SHARP_WHY}"])
    real = E.book_depth
    E.book_depth = lambda t, max_age=None: {"thin": True}
    good, why = E.killer_check([leg()], SHARP)
    E.book_depth = real
    ok("C: sharp-backed, other reasons unchanged (thin book still holds it back, same words)",
       good is False and why == ["Hawks: thin order book"])
    # every place that can buy a killer deal sits behind killer_check
    calls = [m.start() for m in re.finditer(r"killer_act\(\"", SRC)]
    ok("C: every killer_act buy is guarded by killer_check just before it",
       calls and all("killer_check(" in SRC[max(0, i - 900):i] for i in calls))


def games(kick):
    st = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(kick))
    E.KICKOFF["KXNBAGAME-26NOV23ATLBOS"] = st
    return {"KXNBAGAME-26NOV23ATLBOS": [
        {"ticker": "KXNBAGAME-26NOV23ATLBOS-ATL", "event": "KXNBAGAME-26NOV23ATLBOS", "pick": "Hawks", "p": 0.55,
         "fair": 0.555, "src": "Pinnacle", "start": st, "edge": 0.0}]}


def reset():
    E.store_x("delete from maker")
    POSTS.clear()
    SENT.clear()
    E._CAP_LOGGED.pop("maker_sharp", None)


def sec_d():
    E.CFG["maker_mode"] = "on"
    E.CFG["budget"] = 500
    E.LEAGUE["code"] = "nba"
    g = games(NOW + 6 * 3600)
    for name, snap in (("free lines only", FREE), ("a stale sharp line", STALE), ("no snapshot", {})):
        reset()
        logs = []
        E.maker_pass(g, snap, log=lambda *a: logs.append(" ".join(map(str, a))))
        rows = E.store_rows("select * from maker")
        ok(f"D: standing orders, {name}: nothing posted, no row, no Kalshi write", not POSTS and not rows and not SENT)
        if snap:
            ok(f"D: ...and a plain reason in the log ({name})", any(E.NEED_SHARP_WHY in x for x in logs))
    reset()
    logs = []
    E.maker_pass(g, FREE, log=lambda *a: logs.append(a))
    E.maker_pass(g, FREE, log=lambda *a: logs.append(a))
    ok("D: the reason is said once, not every pass", sum(1 for a in logs if E.NEED_SHARP_WHY in " ".join(map(str, a))) == 1)
    reset()
    did = E.maker_pass(g, SHARP, log=lambda *a: None)
    rows = E.store_rows("select * from maker")
    ok("D: an odds-service line backs it: posted exactly as before (one order, its usual size and price)",
       len(POSTS) == 1 and len(rows) == 1 and rows[0]["status"] == "posted" and did and did[0].startswith("posted Hawks"))
    price = POSTS[0][2]
    ok("D: ...priced by the unchanged rule", abs(price - E.math.floor((0.555 - E.MAKER["discount"] - E.maker_fee(0.555)) * 100) / 100) < 1e-9)
    # a resting order whose backing went away is cancelled (a cancel, never a new order)
    POSTS.clear()
    SENT.clear()
    E.maker_pass(g, FREE, log=lambda *a: None)
    rows = E.store_rows("select * from maker")
    ok("D: a resting order left with free lines only is cancelled", rows[0]["status"] == "cancelled" and "odds-service" in (rows[0]["why"] or ""))
    ok("D: ...by a cancel only: nothing new posted or sent but the DELETE",
       not POSTS and SENT and all(m == "DELETE" for m, _ in SENT))
    reset()
    E.CFG["maker_mode"] = "watch"
    E.maker_pass(g, FREE, log=lambda *a: None)
    ok("D: watch mode on free lines: not even a paper order", not E.store_rows("select * from maker"))
    E.maker_pass(g, SHARP, log=lambda *a: None)
    ok("D: watch mode, sharp-backed: the paper order as before", len(E.store_rows("select * from maker where status='watching'")) == 1
       and not POSTS)
    E.CFG["maker_mode"] = "watch"


for n, f in (("A", sec_a), ("B", sec_b), ("C", sec_c), ("D", sec_d)):
    section(n, f)
