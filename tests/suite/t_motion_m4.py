# CHECK: group=engine
"""Motion package M4 (watcher/spa/motion4.js): exact-value tests of the pure logic: the seeded confetti plan and its caps,
which closes celebrate (profit) and which stay sober (flat, loss), the burst sizes per moment, the motion gate (reduced
motion, hidden page, stale feed), the pull-to-refresh ending (fresh check vs grey dash offline) and the splash timing.
Runs motion4.js under node. Display only: nothing here touches a money path."""
import os, json, subprocess
HERE = os.path.abspath("wtest")
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))
JS = os.path.join(HERE, "spa", "motion4.js")
prog = r"""
const M=require(process.argv[1]),o={};
const a=M.confettiPlan(40,1234),b=M.confettiPlan(40,1234),c=M.confettiPlan(40,99);
o.same=JSON.stringify(a)===JSON.stringify(b);o.diff=JSON.stringify(a)!==JSON.stringify(c);
o.lens=[M.confettiPlan(500,1).length,M.confettiPlan(0,1).length,M.confettiPlan(-3,1).length,M.confettiPlan('x',1).length,M.confettiPlan(7.9,1).length];
o.bounds=a.every(p=>p.x>=0&&p.x<=100&&p.delay>=0&&p.delay<=.36&&p.dur>=1.6&&p.dur<=2.7&&p.w>=6&&p.w<=10&&p.h>=8&&p.h<=14&&Math.abs(p.dx)<=90&&p.shape>=0&&p.shape<=2);
o.colors=a.slice(0,7).map(p=>p.color);o.custom=M.confettiPlan(2,5,['#111']).map(p=>p.color);
o.tone=[M.soldTone(12,10),M.soldTone(10,10),M.soldTone(10.003,10),M.soldTone(9.996,10),M.soldTone(4,10),M.soldTone(0,10),M.soldTone(null,null)];
o.burst=[M.burstCounts('big'),M.burstCounts('win'),M.burstCounts('sold'),M.burstCounts('loss'),M.burstCounts('x')];
o.gate=[M.motionOk(),M.motionOk({reduce:true}),M.motionOk({hidden:true}),M.motionOk({stale:true}),M.motionOk({live:true,stale:true}),M.motionOk({live:true,stale:false})];
o.ptr=[M.ptrEnd({down:true}),M.ptrEnd({down:false}),M.ptrEnd()];
o.splash=[M.splashHide(100,true,false),M.splashHide(450,true,false),M.splashHide(449,true,false),M.splashHide(1000,false,false),M.splashHide(1500,false,false),M.splashHide(0,false,true),
 M.splashDelay(100,true),M.splashDelay(600,true),M.splashDelay(0,false),M.splashDelay(2000,false)];
o.caps=[M.MAX_PIECES,M.MAX_TOTAL];
console.log(JSON.stringify(o));
"""
r = subprocess.run(["node", "-e", prog, JS], capture_output=True, text=True)
ok("motion4.js loads under node and runs", r.returncode == 0, r.stderr[-300:])
o = json.loads(r.stdout) if r.returncode == 0 else {}
ok("confetti plan is repeatable for a seed and differs for another", o.get("same") and o.get("diff"))
ok("confetti is capped at 40 per burst and never negative", o.get("lens") == [40, 0, 0, 0, 7], o.get("lens"))
ok("every piece stays inside its bounds", o.get("bounds"))
ok("palette cycles in order, and a custom palette is honoured", o.get("colors") == ["#3ecf8e", "#ffd166", "#4f8cff", "#ff6b9a", "#b48cff", "#7ee0b5", "#3ecf8e"] and o.get("custom") == ["#111", "#111"], o.get("colors"))
ok("only a real profit is a win; flat is flat; a loss is a loss", o.get("tone") == ["win", "flat", "flat", "flat", "loss", "loss", "flat"], o.get("tone"))
ok("burst sizes: big two bursts, win one, sold small, a loss none", o.get("burst") == [[40, 24], [32], [18], [], []], o.get("burst"))
ok("motion gate: reduced or hidden never; live motion needs a fresh feed", o.get("gate") == [True, False, False, True, False, True], o.get("gate"))
ok("pull-to-refresh ends on a check only when the link is up", o.get("ptr") == ["stale", "fresh", "fresh"], o.get("ptr"))
ok("splash: held 450 ms once ready, at most 1500 ms, never under reduced motion",
   o.get("splash") == [False, True, False, False, True, True, 350, 0, 1500, 0], o.get("splash"))
ok("one burst 40 plus a second 24 fits the 64 on-screen cap", o.get("caps") == [40, 64])
src = open(JS).read()
ok("motion4.js never touches a fetch or money path", not any(w in src for w in ("fetch(", "XMLHttpRequest", "api(", "kalshi")))
css = open(os.path.join(HERE, "spa", "motion4.css")).read()
import re
bad = [b for b in re.findall(r"@keyframes\s+\w+\{((?:[^{}]*\{[^{}]*\})+)\}", css) if re.search(r"(?<![-\w])(width|height|left|top|right|bottom|margin|padding)\s*:", b)]
ok("motion4.css keyframes animate no layout property", not bad and len(re.findall("@keyframes", css)) >= 8, bad)
ok("motion4.css respects reduced motion and pauses when hidden", "prefers-reduced-motion:reduce" in css and "animation-play-state:paused" in css)
