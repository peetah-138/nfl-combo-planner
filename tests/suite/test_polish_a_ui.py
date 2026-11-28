# CHECK: group=page secs=40
"""Live / Your Combos polish (package A), display only. One money rule on the Live tab (cents everywhere, same decimals
in a row), the "Auto cash-out is off in Settings" text shown ONCE as a calm note instead of on every card, worth-now
first on a card, 44px taps, and a card-shaped skeleton. Each fragment is rendered by the real SPA function and the
exact text is compared. Money logic is untouched: only what is drawn changes. Fakes only; nothing reaches Kalshi."""
import sys, os, re, json, threading, time
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
from playwright.sync_api import sync_playwright

fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def eq(name, got, want):
    check(f"{name}: {got!r}" + ("" if got == want else f" (wanted {want!r})"), got == want)


def combo(**kw):
    c = {"t": "KXT-1", "group": "pending", "label": "Celtics + Nuggets", "cost": 5, "pays": 41.2, "p": .24, "legs": [], "sports": ["nba"],
         "offer": 8.82, "offer_real": False, "offer_live": None, "hold_value": 7, "sort": 1, "live": False, "preview": "Started 1h ago",
         "smart_profit": "Take profit: off (Auto cash-out is off in Settings)", "loss_chip": "Loss cut: off (Auto cash-out is off in Settings)",
         "smart_txt": "", "verdict": "hold"}
    c.update(kw)
    return c


with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/app"); pg.wait_for_function("typeof S==='object'&&typeof lm==='function'&&typeof autoNote==='function'", timeout=60000)
    ev = pg.evaluate

    # 1) the one money rule: exact strings
    for v, want in ((0, "$0.00"), (2, "$2.00"), (9.4, "$9.40"), (54, "$54.00"), (3.91, "$3.91"), (12.7, "$12.70"), (158.8, "$158.80"),
                    (1234.5, "$1,234.50"), (-0.37, "−$0.37"), (0.001, "$0.00"), (-0.001, "$0.00"), (None, "—"), ("x", "—")):
        eq(f"lm({v!r})", ev("v=>lm(v)", v), want)
    for v, want in ((9.4, "+$9.40"), (-0.37, "−$0.37"), (0, "$0.00"), (-12, "−$12.00"), (None, "—")):
        eq(f"lsm({v!r})", ev("v=>lsm(v)", v), want)
    eq("roller format 'lusd'", ev("()=>fmtNum(1.5,'lusd')"), "$1.50")
    eq("roller format 'labs'", ev("()=>fmtNum(-3.9,'labs')"), "$3.90")
    eq("the old formats still work (pct)", ev("()=>fmtNum(.5,'pct')"), "50%")
    eq("the old default format still works (money)", ev("()=>fmtNum(12.7)"), "$13")

    # 2) settled pill: same rule, true minus
    eq("won pill", ev("c=>plPill(c).replace(/<[^>]*>/g,'|')", combo(group="won", cost=5, pays=14.4)), "||+$9.40|Won||")
    eq("lost pill", ev("c=>plPill(c).replace(/<[^>]*>/g,'|')", combo(group="lost", cost=2.5)), "||−$2.50|Lost||")

    # 3) auto cash-out OFF: one note, no per-card jargon
    ev("()=>{S.live=S.live||{};S.live.auto_sell=false;}")
    note = ev("()=>autoNote(3)")
    eq("one calm note when auto cash-out is off", re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", note)).strip(),
       "Auto cash-out is off. Nothing sells on its own; offers below still update. Settings")
    eq("the note opens Settings", re.findall(r"onclick=\"([^\"]*)\"", note), ["go('settings')"])
    eq("no note when nothing is riding", ev("()=>autoNote(0)"), "")
    eq("smart-sell chip is hidden per card", ev("c=>ssChip(c)", combo()), "")
    eq("the two jargon lines are hidden per card", ev("c=>ssLines(c)", combo()), "")
    row = ev("c=>rowLive(c)", combo())
    check("a card never says 'off in Settings'", "off in Settings" not in row and "Smart sell" not in row)
    check("a card never repeats Take profit / Loss cut", "Take profit" not in row and "Loss cut" not in row)
    eq("an 'I'll sell it' bet still shows its chip", "I’ll sell it" in ev("c=>ssChip(c)", combo(self=True)) or "I'll sell it" in ev("c=>ssChip(c)", combo(self=True)), True)

    # 4) auto cash-out ON: nothing hidden, no note
    ev("()=>{S.live.auto_sell=true;}")
    eq("no note when auto cash-out is on", ev("()=>autoNote(3)"), "")
    check("smart-sell chip is back on", "Smart sell" in ev("c=>ssChip(c)", combo()))
    check("both lines are back on", "Take profit" in ev("c=>ssLines(c)", combo()) and "Loss cut" in ev("c=>ssLines(c)", combo()))

    # 5) a pending card: exact numbers and labels, worth-now cell, real vs estimated offer
    def cells(c):
        h = ev("c=>rowLive(c)", c)
        out = ev("""h=>{const d=document.createElement('div');d.innerHTML=h;
            return [...d.querySelectorAll('.numwrap>div')].map(x=>[x.dataset.l,x.textContent.replace(/\\s+/g,' ').trim()]);}""", h)
        return out
    got = cells(combo())
    eq("estimate card: labels", [g[0] for g in got], ["Paid", "Pays", "To hit", "Worth now"])
    eq("estimate card: paid", got[0][1], "$5.00")
    eq("estimate card: pays", got[1][1], "$41.20")
    eq("estimate card: to hit", got[2][1].split(" ")[0], "24%")
    check("estimate card: worth now leads with the estimate", got[3][1].startswith("≈ $8.82 estimate"))
    got = cells(combo(offer_real=True, offer=2.63, hold_value=2.1))
    eq("real offer card: label", got[3][0], "Offer now")
    check("real offer card: offer vs holding, same decimals", got[3][1].startswith("$2.63 vs $2.10 holding"))
    got = cells(combo(group="cashed", cost=5, pays=41.2, full=41.2, back=7.5))
    eq("cashed card: back", [got[3][0], got[3][1]], ["Cashed out", "$7.50 cashed out"])
    rl = ev("c=>rowLive(c)", combo(offer_real=True, offer=2.63))
    check("rolling offer cell uses the cents format", 'data-f="lusd"' in rl)
    ex = ev("c=>{S.open={};S.open[c.t]=1;return rowLive(c);}", combo(offer_real=True, offer=2.63, hold_value=2.1, legs=[]))
    check("expanded card: Cash out button reads cents", "Cash out $2.63" in ex and "$2.10" in ex)

    # 6) skeleton, not a spinner: the card-shaped block, the Ask button keeps its width
    sk = ev("()=>liveSkel()")
    eq("first paint: three card-shaped skeleton blocks", sk.count('class="skel lcsk"'), 3)
    S_ = ev("c=>{S.open={};S.open[c.t]=1;S.busy={};S.busy[c.t]=1;return rowLive(c);}", combo(offer_real=True, offer=2.63))
    check("asking shows a skeleton pill, no spinner", 'class="bsk"' in S_ and 'class="spin"' not in S_)
    ev("()=>{S.busy={};S.open={};}")

    # 7) real layout at 390px: 44px taps, one note, no sideways scroll, worth-now first, jargon gone
    ev("()=>{S.live=S.live||{};}")
    for scheme in ("light", "dark"):
        pg.emulate_media(color_scheme=scheme)
        pg.evaluate("""()=>{S.view='live';S.filter='all';S.live={auto_sell:false,staked:5,cash_now:8.82,riding:true,chance_one:.3,best:41.2,singles:[],
          combos:[%s,%s]};renderLive();}""" % (json.dumps(combo(t="KXT-1")), json.dumps(combo(t="KXT-2", label="Suns + Rublev"))))
        pg.wait_for_timeout(200)
        r = pg.evaluate("""()=>{const q=s=>[...document.querySelectorAll(s)];const h=e=>Math.round(e.getBoundingClientRect().height);
          const rows=q('#main .trow');const nums=rows[0].querySelector('.numwrap');const first=nums.children;const r4=first[3].getBoundingClientRect(),r1=first[0].getBoundingClientRect();
          return {notes:q('#main .anote').length,txt:(document.querySelector('#main').innerText.match(/off in Settings/g)||[]).length,
           taps:q('#main .anote .btn,#main .lsec .fbtn,#main .lchips .chip').map(h),rows:rows.length,
           worthFirst:r4.top<r1.top,over:document.documentElement.scrollWidth>innerWidth+1,big:parseFloat(getComputedStyle(first[3].querySelector('b')).fontSize)}}""")
        eq(f"{scheme}: exactly one note", r["notes"], 1)
        eq(f"{scheme}: 'off in Settings' appears nowhere on the page", r["txt"], 0)
        eq(f"{scheme}: two cards", r["rows"], 2)
        check(f"{scheme}: every tap target is at least 44px {r['taps']}", r["taps"] and min(r["taps"]) >= 44)
        check(f"{scheme}: worth now sits above what it paid", r["worthFirst"])
        check(f"{scheme}: worth-now number is the biggest on the card ({r['big']}px)", r["big"] >= 20)
        check(f"{scheme}: no sideways scroll", not r["over"])
    check("no page errors: " + "; ".join(errs[:3]), not errs)
    br.close()

print("ALL PASSED" if not fails else "FAILED: " + "; ".join(fails))
sys.exit(1 if fails else 0)
