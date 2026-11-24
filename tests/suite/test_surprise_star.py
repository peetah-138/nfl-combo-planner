# CHECK: group=page secs=15
"""Surprise me: the All | ★ Only toggle (pure list helpers in build.js, run in the page at phone size)."""
import os, time, json
from playwright.sync_api import sync_playwright
import sys
exec(open("test_webapp_pw.py").read().split('sys.argv = ["combo_watcher.py", "--webapp"]')[0])
sys.argv = ["combo_watcher.py", "--webapp"]
import importlib.util, threading
spec = importlib.util.spec_from_file_location("W", "wtest/combo_watcher.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
threading.Thread(target=W.webapp_main, daemon=True).start(); __import__("upwait").wait_up()
B = "http://127.0.0.1:" + os.environ.get("CW_WEBAPP_PORT", "8766")
ok = lambda n, c: print(("PASS " if c else "FAIL ") + n)
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/app"); time.sleep(4)
    cs = [{"i": 1, "kind": "value"}, {"i": 2, "kind": "safer", "pred": {"p_clear": .9}}, {"i": 3, "kind": "value", "pred": {"p_clear": .1}}, {"i": 4, "kind": "mix"}]
    r = pg.evaluate("(cs)=>{S.sur='all';const a=surList(cs).map(c=>c.i);S.sur='star';const b=surList(cs).map(c=>c.i);return {a,b,t:surToggle(cs),e:surList([{i:9,kind:'mix'}]).length}}", cs)
    ok("All lists every combo, stars first", r["a"] == [3, 1, 2, 4] or r["a"][:2] in ([1, 3], [3, 1]) and len(r["a"]) == 4)
    ok("Only keeps just the stars", sorted(r["b"]) == [1, 3])
    ok("toggle shows the star count", "★ Only 2" in r["t"] and 'aria-pressed="true"' in r["t"])
    ok("no stars at all: empty list under Only", r["e"] == 0)
    r = pg.evaluate("()=>{setSur('star');const k=localStorage.getItem('cw_sur');setSur('all');return [k,localStorage.getItem('cw_sur'),S.sur]}")
    ok("choice is remembered", r == ["star", "all", "all"])
    ok("no JS errors", not errs)
    br.close()
