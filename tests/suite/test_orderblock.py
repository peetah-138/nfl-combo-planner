# Settings › Money › "Clear order block" (issue #81): after an order with an unknown outcome the app sends no order on
# that market and side for 2 hours. Pete can lift it with one tap (and a confirm) once he has checked Kalshi; the row
# says which market and side and when the block ends, and clearing is logged. No real orders: nothing is sent here.
import sys, os, time, threading, json
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
ENG = {}
TK = "KXNBAGAME-26NOV19NYKMIN-NYK"


def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    A.resting_sells = lambda: {}
    A.kalshi_pots = lambda: {"total": 69.49, "by": [[0, 4.1], [1, 65.39]], "at": int(time.time())}
    A.save_json(A.ORDER_LEDGER, {f"{TK}|bid|o": {"ts": time.time() - 600, "coid": "c1", "why": "Timeout"}})
    ENG["A"] = A
    return A


W.load_engine = load
LOGS = []
real_log = W.log
W.log = lambda *a: (LOGS.append(" ".join(str(x) for x in a)), real_log(*a))
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()   # waits for the port (was a fixed 3 s)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
problems = []
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    asked = []
    pg.on("dialog", lambda d: (asked.append(d.message), d.accept()))
    pg.goto(B + "/app"); time.sleep(3)
    pg.evaluate("go('settings')")
    pg.wait_for_function("S.set && S.set.blocks !== undefined", timeout=20000)
    blocks = pg.evaluate("S.set.blocks")
    if not (blocks and blocks[0]["ticker"] == TK and blocks[0]["side"] == "YES" and
            abs(blocks[0]["until"] - (time.time() - 600 + 7200)) < 30):
        problems.append(f"settings did not list the block with its 2-hour end: {blocks}")
    pg.wait_for_function("[...document.querySelectorAll('button')].some(b=>b.innerText.includes('Clear order block'))",
                         timeout=10000)
    row = pg.evaluate("[...document.querySelectorAll('.srow')].map(r=>r.innerText).find(t=>t.includes('Order block'))||''")
    if TK not in row or "YES" not in row or "until" not in row:
        problems.append(f"the row doesn't say which market, side and until when: {row!r}")
    pot = pg.evaluate("[...document.querySelectorAll('.srow')].map(r=>r.innerText).find(t=>t.includes('Kalshi balance by pot'))||''")
    if not all(w in pot for w in ("Index 0", "$4.10", "Index 1", "$65.39", "Total", "$69.49", "Kalshi's own app shows one total")):
        problems.append(f"Settings › Money doesn't show the balance by pot: {pot!r}")
    btn = pg.locator("button", has_text="Clear order block").first
    btn.scroll_into_view_if_needed(); btn.click()
    pg.wait_for_function("!(S.set.blocks||[]).length || [...document.querySelectorAll('button')].every(b=>!b.innerText.includes('Clear order block'))",
                         timeout=15000)
    if not asked or "checking Kalshi" not in asked[0]:
        problems.append(f"no confirm before clearing: {asked}")
    left = ENG["A"].load_json(ENG["A"].ORDER_LEDGER, {})
    if left:
        problems.append(f"the block is still in the ledger: {left}")
    if not any("order block cleared" in x for x in LOGS):
        problems.append("clearing wasn't logged")
    r = __import__("requests").post(B + "/app/api/act", json={"a": "clear_block", "key": "nope|bid|o"}, headers={"X-CW": "x"})
    if r.ok and r.json().get("ok"):
        problems.append("clearing a block that isn't there said ok")
    print("checks: balance by pot, block listed, row words, confirm, cleared, logged, missing key refused")
    print("JS errors:", errs[:3])
    print("PROBLEMS:" if problems else "no problems", problems)
    br.close()
