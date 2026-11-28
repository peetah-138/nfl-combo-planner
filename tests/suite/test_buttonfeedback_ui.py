# CHECK: group=page secs=90
"""Button feedback (press.js): every button that moves money or state shows the same sequence on screen, because Pete runs
with haptics off: pressed (instant), pending (spinner + "Selling…", disabled, aria-busy, width locked), then a result:
green check, red "Didn't go through" with the reason, or amber "Check Kalshi" when the answer is unknown. Never "Sold" or
"Bought" for an unknown or unconfirmed answer, and never a second request for a second tap. Requests are held at the page's
own request layer and answered by this test (nothing is priced, bought or sold). Phone dark + light. Saves screenshots
(SHOTS dir, if set). Prints PROBLEMS on any failure."""
import sys, os, time, threading, json, re
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
def load():
    A = real_load()
    A.fetch_account = lambda max_age=60, every_league=False: ([], 211.03, "test")
    A.fetch_results = lambda t: {}
    A.resting_sells = lambda: {}
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
SHOTS = os.environ.get("SHOTS") or ""
from playwright.sync_api import sync_playwright
problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=8):
    for _ in range(int(secs / .1)):
        try:
            if pg.evaluate(js): return True
        except Exception:
            pass
        time.sleep(.1)
    return False
def shot(pg, name):
    if SHOTS: pg.screenshot(path=os.path.join(SHOTS, name))

WATCH = ("go", "hedgego", "singlebuy", "singlesell", "pot_move", "panel_restart", "panel_cancel", "ask", "buy")
HELD, SENT = [], []
def act(route):
    try: body = json.loads(route.request.post_data or "{}")
    except ValueError: body = {}
    if body.get("a") in WATCH:
        SENT.append(body); HELD.append(route); return        # held until this test answers it
    route.continue_()
def answer(obj=None, abort=False):
    if not wait_held(): bad("a request should have been sent"); return
    r = HELD.pop(0)
    if abort: r.abort()
    else: r.fulfill(status=200, content_type="application/json", body=json.dumps(obj))
PG = [None]
def nap(ms): PG[0].wait_for_timeout(ms)      # sync Playwright only runs route handlers while a Playwright call is in flight
def wait_held(n=1):
    for _ in range(100):
        if len(HELD) >= n: return True
        nap(100)
    return False
def hold_still(pg, n):
    """a second tap (or a third) while one is pending must send nothing more"""
    nap(500)
    if len(SENT) != n: bad(f"a tap while pending sent another request: {len(SENT)} sent, want {n}: {SENT}")
def ev(pg, js): return pg.evaluate(js)
def SHEETTAIL(): return PG[0].evaluate("document.querySelector('#sheet').outerHTML").split('class="row"')[-1]
def SR(): return PG[0].evaluate("document.getElementById('fbsr').textContent")
def modal_txt(pg): return ev(pg, "document.querySelector('#modal.on')?document.querySelector('#sheet').innerText:''")
def state(pg, sel):
    return ev(pg, f"""(()=>{{const b=document.querySelector({json.dumps(sel)});if(!b)return null;return {{txt:b.innerText.trim(),cls:b.className,dis:b.disabled,busy:b.getAttribute('aria-busy'),w:b.style.minWidth,ow:b.offsetWidth}};}})()""")

LIVE = "S.live={combos:[{t:'T1',label:'Test combo',offer:12.5,cost:10,p:.5,pays:20,group:'pending',offer_real:true,legs:[],sports:['nfl'],hedge:{name:'Colts',cost:3,locked:10,done:false}}],singles:[]};"
def reset(pg):
    SENT.clear(); HELD.clear()
    ev(pg, "closeModal();S.buying=false;S.pSend=false;S.sb=null;S.ss=null;S.potq=null;document.querySelectorAll('.fbfix,.fbnote').forEach(e=>e.remove());1")
    nap(300)
def fixture(pg, id_, label="Go"):
    ev(pg, f"(()=>{{const b=document.createElement('button');b.className='btn acc fbfix';b.id={json.dumps(id_)};b.textContent={json.dumps(label)};b.style.cssText='position:fixed;left:20px;top:300px;z-index:1';document.body.appendChild(b);return 1}})()")

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for tag, scheme, reduce in (("dark", "dark", "no-preference"), ("light", "light", "no-preference"), ("reduced", "dark", "reduce")):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, reduced_motion=reduce, has_touch=True, device_scale_factor=2)
        pg = ctx.new_page(); PG[0] = pg; errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
        pg.add_init_script("localStorage.clear();localStorage.setItem('cw_view','live')")
        pg.route("**/app/api/act", act)
        pg.goto(B + "/app")
        if not wait(pg, "typeof fbPend==='function'&&typeof S==='object'&&!!S.live", 15): bad(f"{tag}: the page or press.js didn't load"); ctx.close(); continue
        ev(pg, "S.autoLoad=false;clearInterval(S.qT);1")

        # ---- the helper itself: one pending at a time, width locked, aria, result kinds
        fixture(pg, "fx1", "Buy $5")
        w0 = state(pg, "#fx1")["ow"]
        if ev(pg, "fbPend(document.querySelector('#fx1'),'Buying… confirming with Kalshi')") is not True: bad(f"{tag}: fbPend should start")
        if ev(pg, "fbPend(document.querySelector('#fx1'),'Buying…')") is not False: bad(f"{tag}: a second fbPend on a pending button must be refused")
        s = state(pg, "#fx1")
        if not (s["dis"] and s["busy"] == "true" and "Buying…" in s["txt"] and "fb-pend" in s["cls"]): bad(f"{tag}: pending state wrong: {s}")
        if s["w"] != f"{w0}px" or s["ow"] < w0: bad(f"{tag}: the pending button must keep its width ({w0}px): {s}")
        if ev(pg, "document.querySelector('#fx1 .spin')") is None: bad(f"{tag}: pending needs a spinner")
        if reduce == "reduce" and ev(pg, "getComputedStyle(document.querySelector('#fx1 .spin')).animationName") != "none": bad(f"{tag}: the spinner must not animate under reduced motion")
        nap(200)
        if ev(pg, "document.getElementById('fbsr').textContent") != "Buying. Waiting for Kalshi.": bad(f"{tag}: pending should be announced: {SR()!r}")
        ev(pg, "fbEnd(document.querySelector('#fx1'),'ok','Bought · $13.00')")
        s = state(pg, "#fx1")
        if not (s["txt"].startswith("✓") and "Bought · $13.00" in s["txt"] and "fb-ok" in s["cls"] and s["busy"] is None): bad(f"{tag}: ok state wrong: {s}")
        ev(pg, "fbIdle(document.querySelector('#fx1'))")
        s = state(pg, "#fx1")
        if s["txt"] != "Buy $5" or s["dis"] or s["w"] != "" or s["busy"] is not None: bad(f"{tag}: idle should restore the button exactly: {s}")
        # the existing guard in front of buy(): while one buy is on its way a tap sends nothing
        ev(pg, "S.buying=true;buy(1,false,document.querySelector('#fx1'));1"); hold_still(pg, 0); ev(pg, "S.buying=false;1")
        reset(pg)

        # ---- Cash out
        def open_sell():
            ev(pg, LIVE + "sell('T1');1")
            return wait(pg, "!!document.querySelector('#sellgo')")
        if not open_sell(): bad(f"{tag}: the cash-out sheet didn't open"); ctx.close(); continue
        w0 = state(pg, "#sellgo")["ow"]; shot(pg, f"sell_1_idle_{tag}.png")
        pg.locator("#sellgo").hover(); nap(500)
        box = pg.locator("#sellgo").bounding_box()
        pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2); pg.mouse.down(); nap(150)
        if "prs" not in state(pg, "#sellgo")["cls"] and reduce != "reduce": bad(f"{tag}: the pressed state should show at once")
        shot(pg, f"sell_2_pressed_{tag}.png"); pg.mouse.up()
        nap(200)
        if not wait_held(1): bad(f"{tag}: tapping Cash out should send once: {SENT}")
        s = state(pg, "#sellgo")
        if not (s and s["dis"] and s["busy"] == "true" and "Selling…" in s["txt"] and s["w"] == f"{w0}px"): bad(f"{tag}: Cash out pending state wrong: {s}")
        shot(pg, f"sell_3_pending_{tag}.png")
        ev(pg, "doSell('T1');doSell('T1');1"); pg.locator("#sellgo").click(force=True, timeout=1500) if False else None
        hold_still(pg, 1)
        if SENT[0] != {"a": "go", "t": "T1"}: bad(f"{tag}: the cash-out request body changed: {SENT[0]}")
        answer({"ok": True, "msg": "✅ Cashed out Test combo for $12.50.", "offer": 12.5})
        if not wait(pg, "document.getElementById('fbsr').textContent.indexOf('Sold')===0", 6): bad(f"{tag}: a confirmed sale should say Sold: {SR()!r}")
        nap(600); shot(pg, f"sell_4_success_{tag}.png")
        if len(SENT) != 1: bad(f"{tag}: exactly one cash-out request, got {SENT}")
        reset(pg)
        # unknown answer from the Mac: never Sold, no retry
        for what, reply, abort in (("a may-or-may-not answer", {"ok": True, "msg": "⚠️ Test combo: Kalshi didn't answer clearly, so this cash-out may or may not have gone through. Check your Kalshi account."}, False),
                                   ("an ok with no check mark", {"ok": True, "msg": "Done."}, False), ("a lost reply", None, True)):
            open_sell(); ev(pg, "doSell('T1');1"); wait_held(1); answer(reply, abort)
            if not wait(pg, "/Check Kalshi/.test(document.querySelector('#sheet')?document.querySelector('#sheet').innerText:'')", 6): bad(f"{tag}: {what} should end on Check Kalshi: {modal_txt(pg)!r}")
            t = modal_txt(pg)
            if re.search(r"Sold|Cashed out for|Bought", t) or ev(pg, "!!document.querySelector('#sellgo')"): bad(f"{tag}: {what} must not look like a sale or offer a retry: {t!r}")
            shot(pg, f"sell_5_unknown_{tag}.png") if what.startswith("a may") else None
            if len(SENT) != 1: bad(f"{tag}: {what}: nothing may be sent again: {SENT}")
            reset(pg)
        # a plain refusal: red, the reason, and a way back that asks for a FRESH offer (never the old request)
        open_sell(); ev(pg, "doSell('T1');1"); wait_held(1)
        answer({"ok": True, "msg": "Test combo: that offer expired. Tap Get cash-out offer for a fresh one."})
        if not wait(pg, "!!document.querySelector('#sellgo.fb-bad')", 6): bad(f"{tag}: a refusal should turn the button red: {state(pg, '#sellgo')}")
        s = state(pg, "#sellgo"); note = ev(pg, "(document.querySelector('.fbnote')||{}).textContent||''")
        if "Didn't go through" not in s["txt"] or s["dis"] or "offer expired" not in note or ev(pg, "document.querySelector('.fbnote').getAttribute('role')") != "status": bad(f"{tag}: refusal wording: {s} {note!r} {SHEETTAIL()}")
        if re.search(r"Sold|Bought", modal_txt(pg)): bad(f"{tag}: a refusal must not say Sold")
        shot(pg, f"sell_6_failure_{tag}.png")
        pg.locator("#sellgo").click(); wait_held(1)
        if SENT[-1] != {"a": "ask", "t": "T1"} or len(SENT) != 2: bad(f"{tag}: retry should ask for a fresh offer, not replay the sale: {SENT}")
        answer({"ok": False, "msg": "No offer came in."}); reset(pg)

        # ---- Place hedge
        def open_hedge():
            ev(pg, LIVE + "hedge('T1');1")
            return wait(pg, "!!document.querySelector('#sheet button[onclick^=\"fbHedge\"]')")
        HB = "#sheet button[onclick^='fbHedge']"
        if not open_hedge(): bad(f"{tag}: the hedge sheet didn't open"); ctx.close(); continue
        shot(pg, f"hedge_1_idle_{tag}.png")
        pg.locator(HB).click(); wait_held(1); s = state(pg, HB)
        if not (s["dis"] and s["busy"] == "true" and "Placing hedge…" in s["txt"]): bad(f"{tag}: Place hedge pending state wrong: {s}")
        if not ev(pg, "!!document.querySelector('#modal.on')"): bad(f"{tag}: the hedge sheet must stay up while it is pending")
        shot(pg, f"hedge_2_pending_{tag}.png")
        ev(pg, f"fbHedge(document.querySelector({json.dumps(HB)}));1"); hold_still(pg, 1)
        if SENT[0] != {"a": "hedgego", "t": "T1"}: bad(f"{tag}: the hedge request body changed: {SENT[0]}")
        answer({"ok": True, "msg": "✅ Hedged Test combo: bought 3 Colts at 40¢."})
        if not wait(pg, "/Hedged/.test(document.querySelector('#sheet').innerText)&&!!document.querySelector('.okcard')", 6): bad(f"{tag}: a confirmed hedge should end on Hedged: {modal_txt(pg)!r}")
        shot(pg, f"hedge_3_success_{tag}.png"); reset(pg)
        open_hedge(); ev(pg, f"fbHedge(document.querySelector({json.dumps(HB)}));1"); wait_held(1)
        answer({"ok": True, "msg": "⚠️ An earlier hedge may or may not have gone through."})
        if not wait(pg, "/Check Kalshi/.test(document.querySelector('#sheet').innerText)", 6) or re.search(r"Hedged", modal_txt(pg)): bad(f"{tag}: an unknown hedge must say Check Kalshi, never Hedged: {modal_txt(pg)!r}")
        reset(pg)
        open_hedge(); ev(pg, f"fbHedge(document.querySelector({json.dumps(HB)}));1"); wait_held(1)
        answer({"ok": True, "msg": "The hedge wasn't placed. Kalshi isn't allowing orders for your account right now."})
        if not wait(pg, f"!!document.querySelector({json.dumps(HB + '.fb-bad')})", 6): bad(f"{tag}: a refused hedge should turn red: {state(pg, HB)}")
        if "isn't allowing orders" not in ev(pg, "(document.querySelector('.fbnote')||{}).textContent||''"): bad(f"{tag}: the refusal's reason should show")
        shot(pg, f"hedge_4_failure_{tag}.png")
        if len(SENT) != 1: bad(f"{tag}: nothing may be re-sent after a refusal: {SENT}")
        reset(pg)

        # ---- follow-ups: one request per ticker even across a closed/reopened sheet; refusal after the sheet closed; "That didn't work"
        TOAST = "(document.getElementById('toast')||{}).textContent||''"
        for kind, js_open, wait_sel, call in (("Cash out", "sell('T1')", "#sellgo", "doSell('T1')"), ("Place hedge", "hedge('T1')", HB, f"fbHedge(document.querySelector({json.dumps(HB)}))")):
            reset(pg); ev(pg, LIVE + "S.fbFly={};1"); ev(pg, js_open + ";1"); wait(pg, f"!!document.querySelector({json.dumps(wait_sel)})")
            ev(pg, call + ";1"); wait_held(1)
            if not ev(pg, "!!S.fbFly&&!!S.fbFly.T1"): bad(f"{tag}: {kind}: the in-flight flag should be set while pending")
            ev(pg, "closeModal();1"); nap(300); ev(pg, js_open + ";1"); nap(300)     # reopened from the Live card while pending
            if ev(pg, "!!document.querySelector('#modal.on')") or "still going through" not in ev(pg, TOAST): bad(f"{tag}: {kind}: reopening while pending must not open a second sheet: {ev(pg, TOAST)!r}")
            ev(pg, "fbSell('T1');1")
            hold_still(pg, 1)
            answer({"ok": True, "msg": "Test combo: that offer expired. Tap Get cash-out offer for a fresh one."}); nap(500)
            if ev(pg, "!!(S.fbFly&&S.fbFly.T1)"): bad(f"{tag}: {kind}: the flag must clear when the answer arrives")
            if "expired" not in ev(pg, TOAST) or "bad" not in ev(pg, "document.getElementById('toast').className"): bad(f"{tag}: {kind}: a refusal after the sheet closed should be a red toast: {ev(pg, TOAST)!r}")
            if len(SENT) != 1: bad(f"{tag}: {kind}: only one request: {SENT}")
            # a lost reply clears the flag too, and the sheet can be opened again
            reset(pg); ev(pg, "S.fbFly={};1"); ev(pg, js_open + ";1"); wait(pg, f"!!document.querySelector({json.dumps(wait_sel)})"); ev(pg, call + ";1"); wait_held(1); answer(None, abort=True)
            wait(pg, "/Check Kalshi/.test(document.querySelector('#sheet').innerText)", 6)
            if ev(pg, "!!(S.fbFly&&S.fbFly.T1)"): bad(f"{tag}: {kind}: the flag must clear on a failed request")
            reset(pg)
            # the sheet replaced by another one (button removed) while pending: still a toast, and unknown stays Check Kalshi
            ev(pg, js_open + ";1"); wait(pg, f"!!document.querySelector({json.dumps(wait_sel)})"); ev(pg, call + ";1"); wait_held(1)
            ev(pg, "modal('<h3>Other</h3>');1"); answer({"ok": True, "msg": "The hedge wasn't placed. Kalshi isn't allowing orders for your account right now."}); nap(500)
            if "isn't allowing orders" not in ev(pg, TOAST) or "bad" not in ev(pg, "document.getElementById('toast').className"): bad(f"{tag}: {kind}: refusal with the button gone should toast: {ev(pg, TOAST)!r}")
            reset(pg); ev(pg, js_open + ";1"); wait(pg, f"!!document.querySelector({json.dumps(wait_sel)})"); ev(pg, call + ";1"); wait_held(1)
            ev(pg, "modal('<h3>Other</h3>');1"); answer({"ok": True, "msg": "⚠️ may or may not have gone through."}); nap(500)
            if not re.search("Check Kalshi", modal_txt(pg)): bad(f"{tag}: {kind}: an unclear answer with the button gone must still show Check Kalshi: {modal_txt(pg)!r}")
            reset(pg)
        # what counts as a plain refusal: only the Mac's known refusal words. "That didn't work: <error>" and any other ok:false are unknown.
        for r, want in (({"ok": False, "msg": "That didn't work: TimeoutError: slow"}, "chk"), ({"ok": False, "msg": "Something odd."}, "chk"),
                        ({"ok": False, "msg": "Test combo: that offer expired."}, "bad"), ({"ok": True, "msg": "The hedge wasn't placed."}, "bad"),
                        ({"ok": False, "msg": "Kalshi didn't take it. Nothing was sold."}, "bad"), ({"ok": True, "msg": "✅ Cashed out."}, "ok")):
            got = ev(pg, f"fbKind({json.dumps(r)})")
            if got != want: bad(f"{tag}: fbKind({r}) = {got}, want {want}")
        ev(pg, LIVE + "sell('T1');1"); wait(pg, "!!document.querySelector('#sellgo')"); ev(pg, "doSell('T1');1"); wait_held(1)
        answer({"ok": False, "msg": "That didn't work: ValueError: boom"})
        if not wait(pg, "/Check Kalshi/.test(document.querySelector('#sheet').innerText)", 6) or ev(pg, "!!document.querySelector('.fb-bad')"): bad(f"{tag}: \"That didn't work\" must be Check Kalshi, not a red refusal: {modal_txt(pg)!r}")
        reset(pg)

        # ---- Buy straight: the sheet's own guard (s.sending) and the two-tap confirm
        QS = "{t:'KXT',q:'abc',pick:'Test',ask:.5,cost:5,pays:10,arm:25,clears:true,blocked:null,secs:20,at:Date.now()/1000,stake:5}"
        fixture(pg, "sbbuy", "Buy")
        ev(pg, f"S.sb={{q:{QS},sending:false,stake:5}};1")
        ev(pg, "sbBuy(document.getElementById('sbbuy'));sbBuy(document.getElementById('sbbuy'));1"); hold_still(pg, 1)
        if SENT[0] != {"a": "singlebuy", "t": "KXT", "q": "abc", "anyway": False, "cost": 5}: bad(f"{tag}: the Buy straight body changed: {SENT[0]}")
        s = state(pg, "#sbbuy")
        if not (s["dis"] and s["busy"] == "true" and "Buying…" in s["txt"]): bad(f"{tag}: Buy straight pending state wrong: {s}")
        answer(None, abort=True)
        if not wait(pg, "/Check Kalshi/.test(document.querySelector('#sheet').innerText)", 6) or re.search(r"Bought", modal_txt(pg)): bad(f"{tag}: a lost buy reply must say Check Kalshi, never Bought: {modal_txt(pg)!r}")
        reset(pg)
        # Sell straight: the first tap arms, the second sends, the third (pending) sends nothing
        fixture(pg, "sssell", "Sell")
        ev(pg, "S.sellq={};S.ss={q:{t:'KXS',q:'def',pick:'Test',px:.5,got:6,cost:5,clears:true,blocked:null,secs:20,at:Date.now()/1000},sending:false};1")
        ev(pg, "ssSell(document.getElementById('sssell'));1"); hold_still(pg, 0)
        ev(pg, "ssSell(document.getElementById('sssell'));ssSell(document.getElementById('sssell'));1"); hold_still(pg, 1)
        if SENT[0] != {"a": "singlesell", "t": "KXS", "q": "def", "anyway": False}: bad(f"{tag}: the Sell straight body changed: {SENT[0]}")
        if "Selling…" not in state(pg, "#sssell")["txt"]: bad(f"{tag}: Sell straight pending label: {state(pg, '#sssell')}")
        answer({"ok": False, "msg": "Kalshi didn't take it. Nothing was sold."}); nap(500); reset(pg)
        # Move money between pots
        fixture(pg, "potgo", "Move $5.00")
        ev(pg, "S.potq={q:{amount:5,from:1,to:2,to_name:'B',from_name:'A'},cid:'cid1',sending:false};1")
        ev(pg, "potGo(document.getElementById('potgo'));1"); hold_still(pg, 0)
        ev(pg, "potGo(document.getElementById('potgo'));potGo(document.getElementById('potgo'));1"); hold_still(pg, 1)
        if SENT[0] != {"a": "pot_move", "from": 1, "to": 2, "amount": "5.00", "cid": "cid1"}: bad(f"{tag}: the pot move body changed: {SENT[0]}")
        answer({"ok": False, "msg": "Kalshi refused the move."}); nap(500); reset(pg)
        # small state buttons: Restart / Stop the panel
        fixture(pg, "pr1", "Restart")
        ev(pg, "panelRestart(document.getElementById('pr1'));panelRestart(document.getElementById('pr1'));1"); hold_still(pg, 1)
        if SENT[0] != {"a": "panel_restart"} or "Restarting…" not in state(pg, "#pr1")["txt"]: bad(f"{tag}: Restart pending: {SENT} {state(pg, '#pr1')}")
        answer({"ok": False, "msg": "Couldn't restart."}); nap(500); reset(pg)
        fixture(pg, "pc1", "Stop")
        ev(pg, "panelCancel(document.getElementById('pc1'));1"); wait_held(1)
        ev(pg, "panelCancel(document.getElementById('pc1'));1"); hold_still(pg, 1)
        if SENT[0] != {"a": "panel_cancel"} or "Stopping…" not in state(pg, "#pc1")["txt"]: bad(f"{tag}: Stop pending: {SENT} {state(pg, '#pc1')}")
        answer({"ok": True, "msg": "Stopped."}); nap(500); reset(pg)
        # the pressed look is in the stylesheet, and the pending button is not dimmed
        css = ev(pg, "[...document.styleSheets].flatMap(s=>{try{return [...s.cssRules].map(r=>r.cssText)}catch(e){return []}}).join('\\n')")
        if ".btn:not(:disabled):active" not in css: bad(f"{tag}: the CSS-only pressed state is missing")
        print(tag, "errs:", errs)
        if errs: bad(f"{tag}: JS errors: {errs}")
        ctx.close()
    br.close()
if problems:
    print("PROBLEMS:", "; ".join(problems))
else:
    print("all good")
