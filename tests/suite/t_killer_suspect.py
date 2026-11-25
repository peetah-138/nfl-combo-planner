# CHECK: group=engine
# The killer combo path honours get_offer's own verdict (issue #398). shadow_pass used to buy a killer combo on pct alone,
# so a quote get_offer held back as "suspect" (over COMBO_SUSPECT of fair: a wrong chance far more often than a gift)
# still reached killer_act. Now ok=False is final: the deal is skipped with a logged reason. An ok quote is unchanged.
# Strictly fewer buys. Fakes only: no network, no orders, a temp history.
import os, tempfile, importlib.util, traceback
os.environ["COMBOWATCH_HOME"] = os.path.abspath("wahome")
spec = importlib.util.spec_from_file_location("E", "wahome/engine.py"); E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
E.store_open(os.path.join(tempfile.mkdtemp(), "h.db")); E.HERE = tempfile.mkdtemp()
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)


def safe(name, fn):
    try:
        fn()
    except Exception:
        print("FAIL " + name + " raised: " + traceback.format_exc().strip().splitlines()[-1])


LEGS = [{"ticker": "KXNBAGAME-26NOV23AAABBB-A", "pick": "A", "fair": .6, "p": .6, "ask": .55},
        {"ticker": "KXNBAGAME-26NOV23CCCDDD-C", "pick": "C", "fair": .6, "p": .6, "ask": .55}]
STATE = {"quotes": [], "bets": [], "quotes_per_day": 50, "per_pass": 5, "per_day": 50, "bank": 100, "min_pct": 100,
         "max_open": 5, "reask": {}, "reasked": [], "seen": {}}
RESULT = {}
CALLS = {"check": 0, "act": 0}


def run(r):
    CALLS.update(check=0, act=0)
    RESULT["r"] = r
    logs = []
    E.shadow_pass({}, log=lambda *a: logs.append(" ".join(str(x) for x in a)))
    return logs


def sec():
    E.shadow_state = lambda: dict(STATE, quotes=[], bets=[], reask={}, reasked=[], seen={})
    E.shadow_settle = lambda st: 0
    E.save_json = lambda *a, **k: None
    E.load_book_state = lambda snap: None
    E.shadow_candidates_with = lambda book: [{"legs": LEGS, "same_game": False}]
    E.get_offer = lambda i, check_cap=False: dict(RESULT["r"])
    E.notify_bar = lambda legs: 99.0
    E.CFG.update(killer_mode="on", stake=5)

    def chk(legs, snap):
        CALLS["check"] += 1
        return True, []
    E.killer_check = chk
    E.killer_act = lambda *a, **k: CALLS.__setitem__("act", CALLS["act"] + 1)
    sus = {"ok": False, "why": "suspect", "pct": 1.40, "stake": 5.0, "pays": 20.0}
    logs = run(sus)
    ok("a suspect quote (140% of fair, ok False) is never a killer buy", CALLS["act"] == 0 and CALLS["check"] == 0)
    ok("... and the reason is logged", any("held back" in x and "suspect" in x and "140%" in x for x in logs))
    logs = run({"ok": False, "why": "under", "pct": 1.20, "stake": 5.0, "pays": 20.0})
    ok("an under-bar quote above the killer line is not bought either", CALLS["act"] == 0)
    ok("... and logs why", any("held back" in x and "under" in x for x in logs))
    run({"ok": False, "pct": 1.20, "stake": 5.0, "pays": 20.0})
    ok("no verdict text still fails closed", CALLS["act"] == 0)
    run({"ok": True, "pct": 1.20, "stake": 5.0, "pays": 20.0})
    ok("an ok quote still reaches killer_check and killer_act", CALLS["check"] == 1 and CALLS["act"] == 1)
    run({"ok": True, "pct": 1.05, "stake": 5.0, "pays": 20.0})
    ok("below the killer line nothing changes (no killer check)", CALLS["check"] == 0 and CALLS["act"] == 0)
    E.CFG["killer_mode"] = "watch"
    run(sus)
    ok("watch mode also drops a suspect quote", CALLS["act"] == 0 and CALLS["check"] == 0)
    E.CFG["killer_mode"] = "off"
    logs = run(sus)
    ok("off mode: no killer logging at all", not any("held back" in x for x in logs))


safe("killer suspect", sec)
