# CHECK: group=page
"""Pete sets his own bet amount (issue #145), end to end through the real web app. Server side (POSTs to the real
/app/api/act, the engine's money calls faked so nothing can be ordered): a combo price with a bad amount (NaN, negative,
text, over $100) is refused before Kalshi is asked; a good one is asked for exactly that amount and comes back with the
recommended size, the expected profit and the limits; a Live single idea is priced at Pete's amount (contracts rounded
down) and its Buy may only send the size and price the Mac itself quoted (a page that changes them, or buys without a
price, is refused and nothing is sent). On the page (390 phone and desktop): the idea's amount row shows the recommended
size, a tap on + re-prices at the new amount and Buy sends that size once; a panel bet's amount sheet changes the card,
the Approve total and sends the amount with Approve; no sideways scroll; no JS errors. Prints PROBLEMS on any failure."""
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
AA = {}
OFFERS, BUYS = [], []


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
    # (#286) a pregame idea now needs a fresh sportsbook-backed price from the board; this page test is about the amount row,
    # so the board price is stubbed (the rules themselves are tested in t_idea_inplay / t_rank_e144)
    A.idea_single_fair = lambda tk, side=None, pfair=None, book=None, **k: {
        "fair": .45, "src": "sportsbooks + your record", "how": "sportsbooks + your record", "live": False,
        "nofair": None, "warn": [], "over": False}

    def offer(i, amount=None, check_cap=True):        # Kalshi's combo price, faked: records the amount asked for
        OFFERS.append(amount)
        st = amount or 5.0
        return {"pays": st * 3.1, "price": 1 / 3.1, "min": st * 2.8, "ok": True, "stake": st, "pct": 1.02, "bar": 95}
    A.get_offer = offer
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

# ---- server: combo price
COMBO = {"legs": [{"ticker": TK, "event": TK.rsplit("-", 1)[0], "pick": "Boston Celtics", "fair": .45}], "fair": 11.0, "min": 1, "kind": "value"}
def setc():
    A.CTX.update(combos=[COMBO], stake=5.0)
for badv in ("nan", -4, "abc", 500, "Infinity", [3]):
    setc(); n0 = len(OFFERS)
    r = post({"a": "quote", "i": 1, "stake": badv})
    if r.get("ok") or not r.get("bad_stake") or len(OFFERS) != n0: bad(f"combo price with amount {badv!r} must be refused before Kalshi is asked: {r}")
setc(); r = post({"a": "quote", "i": 1, "stake": "7.509"})
if not r.get("ok") or OFFERS[-1] != 7.5 or r.get("stake") != 7.5: bad(f"combo price at $7.509 should ask Kalshi for exactly $7.50: {r} {OFFERS[-3:]}")
if r.get("ev") is None or r.get("rec") is None or r.get("max") is None or r.get("own") is not True: bad(f"the price should carry rec, ev, max and own: {r}")
if abs(r["ev"] - round(7.5 * 3.1 * 5.0 / 11.0 - 7.5, 2)) > 0.011: bad(f"expected profit should be pays x chance - stake: {r['ev']}")
real_cal = A.calib_fair                            # (#361) the profit on the chance corrected by his record is sent beside the books' one
A.calib_fair = lambda code, f, t=None, table="closes": f * 0.9
setc(); r = post({"a": "quote", "i": 1, "stake": 7.5})
if r.get("ev_cal") != round(7.5 * (1.02 * 0.9 - 1), 2): bad(f"ev_cal should be stake x (pct x calibrated/shown - 1) = {round(7.5 * (1.02 * 0.9 - 1), 2)}: {r.get('ev_cal')}")
if abs(r["ev"] - round(7.5 * 3.1 * 5.0 / 11.0 - 7.5, 2)) > 0.011: bad(f"the books' ev (it decides rec / small) must not change: {r['ev']}")
A.calib_fair = lambda code, f, t=None, table="closes": 1 / 0
setc(); r = post({"a": "quote", "i": 1, "stake": 7.5})
if not r.get("ok") or r.get("ev_cal") is not None or r.get("ev") is None: bad(f"a chance that can't be corrected: ev_cal None, the price still comes back: {r}")
A.calib_fair = real_cal
setc(); r = post({"a": "quote", "i": 1})
if not r.get("ok") or r.get("own") is not False: bad(f"no amount = the recommended size, as before: {r}")

# ---- server: a Live single idea at Pete's amount, and its Buy only as the Mac quoted it
r = post({"a": "singlebuy", "id": SID, "n": 3, "price": 0.32})
if r.get("ok") or BUYS: bad(f"Buy with no price from the Mac must be refused, nothing sent: {r}")
r = post({"a": "idea", "id": SID, "stake": "nan"})
if r.get("ok") or not r.get("bad_stake"): bad(f"an idea priced at NaN must be refused: {r}")
r = post({"a": "idea", "id": SID, "stake": 12})
per = 0.32 + A.single_fee(0.32)
if not r.get("ok") or r.get("n") != int(12 / per + 1e-9) or r.get("stake") > 12 or r.get("own") is not True:
    bad(f"the idea at $12 should be {int(12 / per)} contracts at 32c (rounded down): {r}")
q = r
r = post({"a": "singlebuy", "id": SID, "n": q.get("n", 0) + 50, "price": 0.32})
if r.get("ok") or BUYS: bad(f"a page that changes the size must be refused, nothing sent: {r} {BUYS}")
r = post({"a": "singlebuy", "id": SID, "n": q.get("n"), "price": 0.30})
if r.get("ok") or BUYS: bad(f"a page that changes the price must be refused, nothing sent: {r} {BUYS}")
r = post({"a": "singlebuy", "id": SID, "n": q.get("n"), "price": 0.32})
if not r.get("ok") or BUYS[-1:] != [(TK, q.get("n"), 0.32)]: bad(f"Buy at the Mac's own quote should send exactly that size once: {r} {BUYS}")

# ---- the page
P = json.load(open("panel_fixture2.json"))
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, tag in ((390, 844, "phone390"), (1400, 900, "desktop")):
        pg = br.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=2, has_touch=vw < 500)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        SENT = []
        def act(route):
            try: b = json.loads(route.request.post_data or "{}")
            except ValueError: b = {}
            SENT.append(b)
            if b.get("a") in ("panel_approve", "panel_whatif"):
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps({"ok": True, "msg": "Approved.", "p_ahead": .61, "ev": 2.5, "stake": 14, "worst": -9, "best": 20}))
            else:
                route.continue_()
        pg.route("**/app/api/act", act)
        pg.goto(B + "/app"); pg.wait_for_function("typeof go==='function'", timeout=20000); time.sleep(1.5)
        if tag != "phone390":                         # a bought idea never comes back: a fresh one on another game
            TK = f"KXNBAGAME-{tk}DENLAL-DEN"
            A.KICKOFF[TK.rsplit("-", 1)[0]] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)).isoformat()
            A.PICK_NAME[TK] = "Denver Nuggets"
            SID = A.store_suggestion({"legs": [{"ticker": TK, "event": TK.rsplit("-", 1)[0], "pick": "Denver Nuggets", "p": .30,
                                                "fair": .45}], "fair": 25.0}, {"pays": 20.0, "stake": 6.0}, 1.4)
        pg.evaluate("go('live')")
        if not wait(pg, f"!!document.querySelector('[data-ib=\"{SID}\"]')", 20): bad(f"{tag}: the idea card should show"); continue
        BUYS.clear()
        pg.locator(f"#ib-{SID}").click()
        if not wait(pg, f"!!document.querySelector('.stk[data-sk=\"id:{SID}\"]')", 15): bad(f"{tag}: a fresh price should show the amount row")
        else:
            txt = pg.locator(f".stk[data-sk='id:{SID}']").inner_text()
            for w in ("Your bet", "Recommended", "Expected profit"):
                if w not in txt: bad(f"{tag}: the amount row should say '{w}': {txt}")
            rec = pg.evaluate(f"S.ideaq['{SID}'].rec")
            n0 = len(SENT)
            pg.locator(f".stk[data-sk='id:{SID}'] .stkb[aria-label='One dollar more']").click()
            if not wait(pg, f"S.ideaq['{SID}']&&S.stk['id:{SID}']=={rec}+1", 10): bad(f"{tag}: + should re-price at the recommended amount + $1 ({rec})")
            if not any(b.get("a") == "idea" and b.get("stake") == rec + 1 for b in SENT[n0:]): bad(f"{tag}: the new price should be asked at ${rec + 1}: {SENT[n0:]}")
            if "your amount" not in pg.locator(f".stk[data-sk='id:{SID}']").inner_text(): bad(f"{tag}: the row should say it's his own amount now")
            if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{tag}: sideways scroll with the amount row")
            if SHOTS: pg.locator(f"#idea-{SID}").screenshot(path=os.path.join(SHOTS, f"idea_{tag}.png"))
            n = pg.evaluate(f"S.ideaq['{SID}'].n")
            pg.locator(f"#idea-{SID} .btn.yes").click()
            for _ in range(50):
                if BUYS: break
                time.sleep(.1)
            if BUYS[-1:] != [(TK, n, 0.32)] or len(BUYS) != 1: bad(f"{tag}: one Buy tap should send the size on screen ({n}) once: {BUYS}")
        # the panel: a bet's amount before Approve
        pg.evaluate("go('build')"); time.sleep(2)
        pg.evaluate("window.load=async()=>{};const P=" + json.dumps(P) + ";P.panel.at=Date.now()/1000;P.panel.items.forEach(c=>c.kick=Date.now()/1000+7200);P.view='all';P.approved_other=false;S.panel=P;S.pview='all';S.stk={};renderBuild()")
        if not wait(pg, "!!document.querySelector('.pstb')", 8): bad(f"{tag}: draft panel bets should have an amount button"); pg.close(); continue
        first = pg.evaluate("S.panel.panel.items[0].id")
        pg.locator(".pstb").first.click()
        if not wait(pg, f"!!document.querySelector('#sheet .stk[data-sk=\"pn:{first}\"]')", 5): bad(f"{tag}: the amount sheet should open")
        else:
            pg.locator("#sheet .stk .chip", has_text="$10").first.click()
            if not wait(pg, f"S.stk['pn:{first}']===10", 3): bad(f"{tag}: the $10 preset should set the amount")
            if "more risk" not in pg.locator("#sheet").inner_text(): bad(f"{tag}: 3x the recommended size should say it's more risk")
            if SHOTS: time.sleep(.6); pg.screenshot(path=os.path.join(SHOTS, f"panel_sheet_{tag}.png"))
            pg.locator("#sheet .btn.pri").click(); time.sleep(.6)
            card = pg.locator(f".pitem[data-pid='{first}']").inner_text()
            if "$10" not in card or "yours" not in card: bad(f"{tag}: the card should show his $10: {card}")
            if SHOTS: pg.locator(".card.panel").first.screenshot(path=os.path.join(SHOTS, f"panel_{tag}.png"))
            tot = pg.evaluate("[...document.querySelectorAll('.panel .btn')].map(b=>b.innerText).join('|')")
            want = sum(c["stake"] for c in P["panel"]["items"][1:]) + 10
            if f"${round(want)}" not in tot and f"${want:.2f}".replace('.00', '') not in tot: bad(f"{tag}: the Approve total should count his amount (${want}): {tot}")
            if not wait(pg, "!!S.pWhat", 4): bad(f"{tag}: the chance-up ring should be re-worked at his amount")
            btn = pg.locator(".panel .btn.acc", has_text="Approve").first
            btn.click()
            if not wait(pg, "!!document.querySelector('.panel .btn.arm')", 3): bad(f"{tag}: the first Approve tap should arm the button")
            pg.locator(".panel .btn.arm").first.click()
            sent = lambda: any(b.get("a") == "panel_approve" and (b.get("stakes") or {}).get(first) == 10 for b in SENT)
            for _ in range(50):
                if sent(): break
                time.sleep(.1)
            if not sent(): bad(f"{tag}: Approve should send his amount: {[b for b in SENT if b.get('a') == 'panel_approve']}")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): bad(f"{tag}: sideways scroll on Build")
        if errs: bad(f"{tag}: JS errors: {errs[:3]}")
        pg.close()
    br.close()
print("PROBLEMS:", problems) if problems else print("ALL GOOD")
