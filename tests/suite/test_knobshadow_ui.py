# CHECK: group=page secs=25
# Issue #228, PR2/PR3: Results › What's working › Selling shows "What self-tuning would change" (self-tuning off: a test
# run, nothing changes) or, with Settings › Money › 'Let smart sell tune its own numbers' on (PR3), "What self-tuning
# changed": each change (what, from, to, when, why), a live brake, the knobs still in test. Off: folded by default (44pt header with a count), opened it says nothing changes yet, the bar in plain words, league
# chips, per league the step it would take, the others that clear the bar, the ones the newest bets held back, where
# the test has a number now, and a brake (test) banner; an empty league says nothing would change yet; a first run not
# yet made says so. No setting control. Real knob_shadow_view output from the engine under test, at phone (dark and
# light) and desktop sizes; no JS errors, no sideways scroll; the header keeps a focus ring.
import sys, os, time, threading, json, tempfile
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
real_load = W.load_engine
ENG = {}
def load():
    A = real_load(); ENG["A"] = A
    return A
W.load_engine = load
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
t0 = time.time()
while "A" not in ENG and time.time() - t0 < 30:
    time.sleep(.1)
A = ENG["A"]
A.CFG["knobs_live"] = False; A.KNOB_SWITCH["on"] = None; A.KNOB_SWITCH["at"] = 1e18   # the test-run card first
tmp = tempfile.mkdtemp()
A.KNOBS_FILE = os.path.join(tmp, "knobs.json")
now = time.time()
EMPTY = A.knob_shadow_view(now)                      # no run yet
step_say = ("Profit floor: 1.5× what you paid → 1.6× what you paid. 14 of 84 recent bets would have ended differently, "
            "+$3.20 in all (+2.4% of what was staked, 2.6 standard errors from luck); the newest 30% agree (+$1.10).")
json.dump({"_at": now - 3600, "_next": now + 6 * 86400, "run": {"done": True},
           "groups": {"all": {"v": {"smart_floor": 1.5}, "last": [{"knob": "smart_floor", "status": "below", "say": "x"}]},
                      "nba": {"v": {"smart_floor": 1.6, "smart_lam": 1.0},
                              "last": [{"knob": "smart_floor", "status": "would step", "say": step_say, "gain": 3.2},
                                       {"knob": "smart_lam", "status": "qualifies", "say": "Risk weight: 1× → 0.85×. Also good."},
                                       {"knob": "smart_loss", "status": "vetoed", "say": "Cut a loss under: off → 15%. But the newest 30% disagree."},
                                       {"knob": "sl_prog", "status": "thin", "say": "Not before this much of the game: needs 50 results of its own (has 20)"}]},
                      "nhl": {"v": {}, "last": []}},
           "brake": {"nhl": {"at": now - 60, "until": now + 14 * 86400, "why": "the last 4 sales the app made on its own all lost money ($12.40)"}},
           "settings": {}}, open(A.KNOBS_FILE, "w"))
KS = A.knob_shadow_view(now)
assert KS.get("leagues"), KS
assert KS["mode"] == "shadow", KS["mode"]
A.CFG["knobs_live"] = True; A.KNOB_SWITCH["on"] = True                                     # PR3: live
chg_why = ("Profit floor: 1.5× what you paid → 1.6× what you paid. 14 of 84 recent bets would have ended differently, "
           "+$3.20 in all (+2.4% of what was staked, 2.6 standard errors from luck); the newest 30% agree (+$1.10).")
json.dump({"_at": now - 3600, "_next": now + 6 * 86400, "run": {"done": True, "mode": "live"},
           "groups": {"all": {"v": {}, "last": []},
                      "nba": {"v": {"smart_floor": 1.6}, "lv": {"smart_floor": 1.6}, "lat": {"smart_floor": now - 3600},
                              "hist": [{"at": int(now - 3600), "knob": "smart_floor", "from": 1.5, "to": 1.6, "live": True,
                                        "why": chg_why}],
                              "last": [{"knob": "smart_floor", "status": "stepped", "say": chg_why, "gain": 3.2},
                                       {"knob": "sl_prog", "status": "would step", "say": "Not before this much of the game: 50% → 55%. A test."}]},
                      "nhl": {"v": {}, "lv": {}, "last": [],
                              "hist": [{"at": int(now - 60), "knob": "*", "brake": True, "live": True,
                                        "why": "the last 4 sales the app made on its own all got less than holding was worth at the time they sold ($9.10 less)"}]}},
           "brake": {"nhl": {"at": now - 60, "until": now + 14 * 86400, "mode": "live",
                             "why": "the last 4 sales the app made on its own all got less than holding was worth at the time they sold ($9.10 less)"}},
           "settings": {}}, open(A.KNOBS_FILE, "w"))
A.SMART_CACHE.update(at=time.time() + 1e6, d={})
KS_LIVE = A.knob_shadow_view(now)
assert KS_LIVE["mode"] == "live" and KS_LIVE["leagues"], KS_LIVE
AN = {"at": time.time() - 60, "levels": [], "types": [], "sports": [], "live": [], "exits": [], "auto": {}, "cut_held": {},
      "hedge_held": {}, "tuning": [], "notes": [], "knobs": A.knob_view(), "knob_shadow": KS}
from playwright.sync_api import sync_playwright
def wait(pg, js, secs=30):
    t = time.time()
    while time.time() - t < secs:
        try:
            if pg.evaluate(js): return True
        except Exception: pass
        time.sleep(.1)
    return False
P = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, scheme, tag in ((390, 844, "dark", "phone"), (390, 844, "light", "phone-light"), (1440, 900, "dark", "desktop")):
        pg = br.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=2, color_scheme=scheme)
        pg.add_init_script(__import__("upwait").COUNT_FETCHES)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/app/api/analytics", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(AN)))
        pg.goto(B + "/app"); pg.wait_for_function("typeof window.load==='function'&&typeof S==='object'", timeout=30000)
        pg.evaluate("go('results')"); wait(pg, "!!document.querySelector('.an .ant')", 40)
        pg.locator(".ant button", has_text="Selling").click()
        if not wait(pg, "!!document.querySelector('.an .ksp .ksh')", 10):
            P.append(tag + ": no self-tuning card in Results › Selling"); pg.close(); continue
        hd = pg.locator(".an .ksp .ksh")
        bb = hd.bounding_box()
        if hd.get_attribute("aria-expanded") != "false" or pg.locator(".an .ksp .ksr").count():
            P.append(tag + ": the self-tuning card isn't folded by default")
        if bb["height"] < 44: P.append(tag + ": its header is under 44pt: %r" % bb)
        if "1 would change" not in hd.inner_text() or "brake" not in hd.inner_text():
            P.append(tag + ": header has no count: " + hd.inner_text())
        if "all:unset" in (hd.get_attribute("style") or "").replace(" ", ""):
            P.append(tag + ": the header resets all its styles (no focus ring)")
        hd.click(); wait(pg, "!!document.querySelector('.an .ksp .kslg')", 5)
        txt = pg.locator(".an .ksp").inner_text()
        for want in ("nothing changes yet", "judged against luck", "Tested so far", "Profit floor"):
            if want not in txt: P.append(tag + ": missing %r" % want)
        pg.locator(".an .ksp .kslg button", has_text="NBA").click()
        wait(pg, "!!document.querySelector('.an .ksp .kss')", 5)
        txt = pg.locator(".an .ksp").inner_text()
        for want in ("Would change", "1.6× what you paid", "the newest 30% agree", "Waiting its turn", "Risk weight",
                     "Held back: the newest bets disagree", "Where the test has it now", "Needs more results first"):
            if want not in txt: P.append(tag + ": NBA missing %r" % want)
        pg.locator(".an .ksp .kslg button", has_text="NHL").click()
        wait(pg, "!!document.querySelector('.an .ksp .ksbrk')", 5)
        if "would stay at its starting numbers" not in pg.locator(".an .ksp").inner_text() or \
                "keeping any number it had made stricter" not in pg.locator(".an .ksp").inner_text():   # #284: never looser
            P.append(tag + ": NHL's brake (test) banner not shown")
        pg.locator(".an .ksp .kslg button", has_text="Everything").click()
        wait(pg, "!!document.querySelector('.an .ksp .ksempty')", 5)
        if "Nothing would change in Everything yet" not in pg.locator(".an .ksp").inner_text():
            P.append(tag + ": an empty league should say nothing would change yet")
        if pg.locator(".an .ksp input, .an .ksp select, .an .ksp textarea").count():
            P.append(tag + ": the card has a setting control (it must be read-only)")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): P.append(tag + ": Results scrolls sideways")
        pg.locator(".an .ksp .kslg button", has_text="NBA").click(); wait(pg, "!!document.querySelector('.an .ksp .kss')", 5)
        over = pg.evaluate("[...document.querySelectorAll('.an .ksp .ksr')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).length")
        if over: P.append(tag + ": %d rows run past the screen" % over)
        pg.locator(".an .ksp").screenshot(path=os.path.join(os.environ.get("SHOT_DIR", "."), "knobshadow_%s.png" % tag))
        # no run yet: a first-run note, never an error; a broken answer draws nothing
        html0 = pg.evaluate("v=>{const o=S.ksOpen;S.ksOpen=true;const h=knobShadow(v);S.ksOpen=o;return h}", EMPTY)
        if "first test run happens within a week" not in html0: P.append(tag + ": no first-run note: " + html0[:200])
        if pg.evaluate("knobShadow({})+knobShadow(null)") != "": P.append(tag + ": an empty answer should draw nothing")
        pre = {"mode": "live", "at": None, "leagues": [{"key": "nhl", "name": "NHL", "brake": {"why": "x", "until": now + 86400,
               "until_say": "Dec 6"}, "steps": [], "changes": [], "moved": []}]}
        html1 = pg.evaluate("v=>{const o=S.ksOpen;S.ksOpen=true;const h=knobShadow(v);S.ksOpen=o;return h}", pre)
        if "ksbrk" not in html1 or "first run happens" in html1:   # PR4: a brake before any run is shown
            P.append(tag + ": a brake before the first run is hidden: " + html1[:200])
        # PR3: self-tuning on: what it changed, a live brake, the knobs still in test
        pg.evaluate("v=>{S.ksOpen=false;S.ksLg=null;document.querySelector('.an .ksp').outerHTML=knobShadow(v)}", KS_LIVE)
        hd2 = pg.locator(".an .ksp .ksh")
        if "What self-tuning changed" not in hd2.inner_text() or "1 change" not in hd2.inner_text() or "brake" not in hd2.inner_text():
            P.append(tag + ": live header wrong: " + hd2.inner_text())
        pg.evaluate("v=>{S.ksOpen=true;S.ksLg='nba';document.querySelector('.an .ksp').outerHTML=knobShadow(v)}", KS_LIVE)
        txt = pg.locator(".an .ksp").inner_text()
        for want in ("Self-tuning is on", "Changed", "Profit floor: 1.5× what you paid → 1.6× what you paid",
                     "the newest 30% agree", "Still a test, nothing changes", "Where it stands now", "Tuning itself: %d of its selling, loss and hedge numbers" % sum(1 for n in A.KNOB_LIVE if n in A.KNOB_JUDGED)):
            if want not in txt: P.append(tag + ": live NBA missing %r" % want)
        if "nothing changes yet" in txt: P.append(tag + ": live card still says nothing changes")
        if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): P.append(tag + ": the live card scrolls sideways")
        over = pg.evaluate("[...document.querySelectorAll('.an .ksp .ksr')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).length")
        if over: P.append(tag + ": %d live rows run past the screen" % over)
        pg.locator(".an .ksp").screenshot(path=os.path.join(os.environ.get("SHOT_DIR", "."), "knoblive_%s.png" % tag))
        pg.evaluate("v=>{S.ksOpen=true;S.ksLg='nhl';document.querySelector('.an .ksp').outerHTML=knobShadow(v)}", KS_LIVE)
        txt = pg.locator(".an .ksp").inner_text()
        if "is back on its starting numbers until" not in txt or "Brake: back to the starting numbers" not in txt \
                or "keeping any number it had made stricter" not in txt or "worth at the time" not in txt:
            P.append(tag + ": NHL's live brake not shown: " + txt[:300])
        if pg.locator(".an .ksp input, .an .ksp select, .an .ksp textarea").count():
            P.append(tag + ": the live card has a setting control (it must be read-only)")
        if errs: P.append(tag + ": JS errors %r" % errs[:3])
        pg.close()
    br.close()
print("PROBLEMS: " + " | ".join(P) if P else "knob shadow ui ok")
