# CHECK: group=page
"""The combo Buy act end to end through the real /app/api/act (issue #203): an idea Buy carries its quoted legs and still
works; other legs or a changed combo are refused with nothing sent; a card with no legs sent is held to offer = card;
Build cards and long shots unchanged. Kalshi is faked; nothing can be ordered."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
AA = {}
OFFERS, BUYS, ACCEPTS = [], [], []


def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    A.open_singles = lambda: []
    A.can_trade = lambda: True
    A.book_depth = lambda t, max_age=60: {"bid": .31, "ask": .32, "spread": .01, "ask_size": 240, "thin": False}
    A.single_cap_block = lambda t, cost, now=None: (None, 10.0, 100.0)
    A.week_spend = lambda: 10.0

    def offer(i, amount=None, check_cap=True):        # like the real one: stores the offer with the combo's legs
        OFFERS.append(amount); st = amount or 5.0
        A.CTX["offers"][i] = {"rfq": "r%d" % i, "quote": "q%d" % i, "pays": st * 3.1, "market": "M%d" % i, "price": 1 / 3.1,
                              "stake": st, "p": .3, "legs": [l["ticker"] for l in A.CTX["combos"][i - 1]["legs"]]}
        return {"pays": st * 3.1, "price": 1 / 3.1, "min": st * 2.8, "ok": True, "stake": st, "pct": 1.02, "bar": 95}
    A.get_offer = offer
    def ksend(m, path, body=None, *a, **k):
        if path.endswith("/accept"): ACCEPTS.append(path); return {}
        if "/quotes/" in path and m == "GET": return {"quote": {"status": "executed"}}
        return {}
    A.kalshi_send = ksend
    A.ACCEPT_WAIT = 3
    A.CFG["budget"] = 10000
    A.hold_refusal = lambda *a, **k: (False, "")
    A.trading_paused = lambda: False
    A.rfq_unsure = lambda *a, **k: False
    A.mark_rfq_unsure = lambda *a, **k: None
    A.idea_single_buy = lambda t, n, price, paused=False, log=print, key=None: (BUYS.append((t, n, price)) or
                                                                               {"ok": True, "pays": n, "msg": f"Bought {n}."})
    AA["A"] = A
    return A


W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
SHOTS = os.environ.get("SHOTS") or ""
problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=10):
    for _ in range(int(secs / .1)):
        try:
            if pg.evaluate(js): return True
        except Exception:
            pass
        time.sleep(.1)
    return False
post = lambda body: requests.post(B + "/app/api/act", json=body, headers={"X-CW": "x"}, timeout=120).json()

A = AA["A"]
if not A.STORE.get("db"):
    A.store_open()
A.LEAGUE["code"] = "nba"
TK = f"KXNBAGAME-{tk}BOSNYK-BOS"
A.KICKOFF[TK.rsplit("-", 1)[0]] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)).isoformat()
A.PICK_NAME[TK] = "Boston Celtics"
A.store_x("delete from suggestions")
try: os.remove(A.IDEA_DISMISS)
except OSError: pass
SID = A.store_suggestion({"legs": [{"ticker": TK, "event": TK.rsplit("-", 1)[0], "pick": "Boston Celtics", "p": .30, "fair": .45}],
                          "fair": 25.0}, {"pays": 20.0, "stake": 6.0}, 1.4)


A = AA["A"]
if not A.STORE.get("db"):
    A.store_open()
A.LEAGUE["code"] = "nba"
T1, T2, T3 = "KXNBAGAME-26NOVAAABBB-AAA", "KXNBAGAME-26NOVCCCDDD-CCC", "KXNBAGAME-26NOVEEEFFF-EEE"
L = lambda *ts: [{"ticker": t, "event": t.rsplit("-", 1)[0], "pick": t, "fair": .5} for t in ts]
A.store_x("delete from suggestions")
SID = A.store_suggestion({"legs": L(T1, T2), "fair": 11.0}, {"pays": 20.0, "stake": 6.0}, 1.4)
A.CTX.update(combos=[], stake=5.0, offers={})
def own(lst):                                   # the idea act builds its own-combo card; the games board isn't under test
    A.CTX["combos"].append({"legs": L(*lst), "fair": 11.0, "min": 1, "kind": "own"}); return len(A.CTX["combos"]), ""
A.add_own_combo = lambda tickers: own(tickers)
def acc(): n = len(ACCEPTS); return n
def buy(**kw): return post(dict({"a": "buy"}, **kw))

# ---- the idea Buy: the act's price carries the legs, the page sends them back, the Buy goes through
q = post({"a": "idea", "id": SID})
if not q.get("ok") or sorted(q.get("legs") or []) != sorted([T1, T2]): bad(f"the idea price must name its legs: {q}")
n0 = len(ACCEPTS); r = buy(i=q["i"], legs=q["legs"])
if not r.get("ok") or len(ACCEPTS) != n0 + 1: bad(f"idea Buy with its own legs must go through: {r}")
# the idea Buy of an older page (no legs at all) still works when the offer matches the card (never refused for missing legs)
q = post({"a": "idea", "id": SID}); n0 = len(ACCEPTS); r = buy(i=q["i"])
if not r.get("ok") or len(ACCEPTS) != n0 + 1: bad(f"idea Buy with no legs but offer = card must still go through: {r}")
# a page showing other legs than the offer: refused, nothing sent
q = post({"a": "idea", "id": SID}); n0 = len(ACCEPTS); r = buy(i=q["i"], legs=[T1, T3])
if r.get("ok") or len(ACCEPTS) != n0: bad(f"idea Buy with other legs must be refused, nothing sent: {r}")
# a combo changed on the Mac without its offer being dropped: refused with or without legs
for sent in (q["legs"], None, [T1, T3]):
    q = post({"a": "idea", "id": SID}); n0 = len(ACCEPTS)
    A.CTX["combos"][q["i"] - 1]["legs"] = L(T1, T3)
    r = buy(i=q["i"], **({"legs": sent} if sent else {}))
    if r.get("ok") or len(ACCEPTS) != n0: bad(f"flip on the Mac without popping the offer must refuse (page legs {sent}): {r}")

# ---- a Build card (quote then Buy with the card's legs) and a long shot's Buy use the same act and are unchanged
A.CTX.update(combos=[{"legs": L(T1, T2), "fair": 11.0, "min": 1, "kind": "value"},
                     {"legs": L(T2, T3), "fair": 11.0, "min": 1, "kind": "longshot", "ls_stake": 2.0}], stake=5.0, offers={})
for i, lg in ((1, [T2, T1]), (2, [T2, T3])):
    r = post({"a": "quote", "i": i, "legs": lg}); n0 = len(ACCEPTS)
    if not r.get("ok") and i == 1: bad(f"Build quote failed: {r}")
    if i not in A.CTX["offers"]: continue
    r = buy(i=i, legs=lg)
    if not r.get("ok") or len(ACCEPTS) != n0 + 1: bad(f"card {i} Buy with its legs must go through: {r}")
r = post({"a": "quote", "i": 1, "legs": [T1, T2]}); n0 = len(ACCEPTS); r = buy(i=1, legs=[T2, T3])
if r.get("ok") or len(ACCEPTS) != n0: bad(f"Build Buy with other legs must be refused: {r}")
# the page's own code sends the legs for an idea
ideas = open("wtest/spa/ideas.js").read()
if "legs:q.legs&&q.legs.length?q.legs:undefined" not in ideas or "legs:r.legs" not in ideas: bad("ideas.js must keep the quoted legs and send them with Buy")

print("PROBLEMS:", problems) if problems else print("ALL GOOD")
