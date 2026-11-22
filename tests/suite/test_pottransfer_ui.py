# CHECK: group=page
# Moving cash between Kalshi's pots, on the page (issue #144), at phone size: Settings › Money › Kalshi balance by pot
# names the pots and has "Move money between pots"; the tool's Review opens a confirm sheet with both pots before and
# after and the plain words; Move needs a second tap ("Tap again"), sends one move with the sheet's own id, then the
# result moment. An open "check" move shows with Clear. The Buy straight sheet, refused for its pot, offers "Move $X
# from <pot> to <pot>", which opens the same confirm sheet. The engine's move is stubbed: nothing reaches Kalshi.
import sys, os, time, threading
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
ENG, SENT, CLEARED = {}, [], []
POTS = {"total": 69.49, "by": [[0, 0.0], [1, 63.86], [3, 5.63]], "at": int(time.time())}


def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    A.resting_sells = lambda: {}
    A.kalshi_pots = lambda: POTS
    A.pot_moves = lambda refresh=False: [{"cid": "c-old", "ts": int(time.time()) - 300, "from": 1, "to": 3, "from_name": "Combos pot",
                            "to_name": "Tennis, Baseball, Basketball pot", "amount": 4.0, "status": "check",
                            "why": "Timeout", "open": not CLEARED}]
    A.pot_clear = lambda cid: (CLEARED.append(cid), True)[1]

    def move(f, t, amount, cid=None, paused=False):
        SENT.append((f, t, amount, cid, paused))
        return {"ok": True, "status": "complete", "msg": "Moved $5.00 from Combos pot to Tennis, Baseball, Basketball pot.",
                "pots": {"by": [[0, 0.0], [1, 58.86], [3, 10.63]], "total": 69.49}, "amount": float(amount)}
    A.pot_transfer = move
    ENG["A"] = A
    return A


W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); time.sleep(3)
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright
problems = []
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/app"); time.sleep(3)
    pg.evaluate("go('settings')")
    pg.wait_for_function("[...document.querySelectorAll('button')].some(b=>b.innerText.includes('Move money between pots'))",
                         timeout=20000)
    row = pg.evaluate("[...document.querySelectorAll('.srow')].map(r=>r.innerText).find(t=>t.includes('Kalshi balance by pot'))||''")
    for w in ("Combos pot", "Index 1", "$63.86", "Tennis, Baseball, Basketball pot", "$5.63", "Total", "$69.49",
              "Money only moves when you tap and confirm", "No clear answer: check Kalshi"):
        if w not in row:
            problems.append(f"the pots row is missing {w!r}: {row!r}")
    if pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1"):
        problems.append("sideways scroll on Settings at phone size")
    # the move tool -> Review -> confirm sheet
    pg.locator("button", has_text="Move money between pots").first.click()
    pg.wait_for_selector("#potx #pota", timeout=5000)
    if pg.evaluate("$('#potf').value") != "1" or pg.evaluate("$('#pott').value") != "0":
        problems.append("the tool doesn't default to the largest pot -> the smallest")
    pg.select_option("#pott", "3")
    pg.locator("#potx .chip", has_text="$5").first.click()
    pg.locator("#potx button", has_text="Review the move").click()
    pg.wait_for_selector("#potc", timeout=8000)
    sheet = pg.evaluate("$('#potc').innerText")
    for w in ("Move $5.00 to Tennis, Baseball, Basketball pot?", "$63.86", "$58.86", "$5.63", "$10.63",
              "Both pots are your own Kalshi money; this moves cash between them"):
        if w not in sheet:
            problems.append(f"the confirm sheet is missing {w!r}: {sheet!r}")
    go = pg.locator("#potgo")
    go.click()
    time.sleep(0.3)
    if "Tap again" not in go.inner_text() or SENT:
        problems.append(f"the first tap moved money or didn't arm: {go.inner_text()!r} {SENT}")
    go.click()
    pg.wait_for_selector("#sheet .okcard", timeout=10000)
    ok_text = pg.evaluate("$('#sheet .okcard').innerText")
    if "Moved" not in ok_text or "$5.00" not in ok_text:
        problems.append(f"no result moment: {ok_text!r}")
    if len(SENT) != 1 or SENT[0][:3] != (1, 3, "5.00") or not SENT[0][3] or SENT[0][4]:
        problems.append(f"not exactly one move, with an id, unpaused: {SENT}")
    # Clear an open 'check' move
    pg.evaluate("closeModal()"); time.sleep(0.5)
    pg.evaluate("load('settings',true)")
    pg.wait_for_selector("[data-pm] button", timeout=10000)
    pg.locator("[data-pm] button", has_text="Clear").first.click()
    t0 = time.time()
    while not CLEARED and time.time() - t0 < 8:
        time.sleep(0.2)
    if CLEARED != ["c-old"]:
        problems.append(f"Clear didn't clear the open move: {CLEARED}")
    # the Buy straight sheet refused for its pot offers the move
    pg.evaluate("""(()=>{S.sb={t:'KXNBASPREAD-X',lg:'nba',stake:5,busy:false,err:null,back:null,fail:"Kalshi didn't take the order: the money available for this market isn't enough",
      pot:{ok:true,from:1,to:3,from_name:'Combos pot',to_name:'Tennis, Baseball, Basketball pot',amount:5,before:[63.86,5.63],after:[58.86,10.63],short:4.27,need:9.9},
      q:{t:'KXNBASPREAD-X',pick:'Denver -5',sport:'nba',ask:.17,gap:.01,depth:500,fair:.2,edge:.02,stake:5,sug:5,max:100,n:55,cost:9.9,pays:55,profit:45,presets:[3,5,10],secs:20,at:Date.now()/1000,used:1,warn:[]}};
      modal('<div class="sb" id="sbx"></div>');sbPaint();})()""")
    pg.wait_for_selector("#sbpot", timeout=5000)
    label = pg.locator("#sbpot").inner_text()
    if label != "Move $5.00 from Combos pot to Tennis, Baseball, Basketball pot":
        problems.append(f"the buy sheet's move button reads {label!r}")
    pg.locator("#sbpot").click()
    pg.wait_for_selector("#potc", timeout=5000)
    if "was $4.27 short" not in pg.evaluate("$('#potc').innerText"):
        problems.append("the confirm sheet from a refused buy doesn't say how short the pot was")
    if pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1"):
        problems.append("sideways scroll on the confirm sheet")
    print("checks: pots row, tool defaults, review, confirm numbers and words, arm, one move, result, clear, buy sheet button")
    print("JS errors:", errs[:3])
    if errs:
        problems.append(f"JS errors: {errs[:3]}")
    print("PROBLEMS:" if problems else "no problems", problems)
    br.close()
