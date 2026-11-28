# CHECK: group=engine
"""Live motion (package M2, watcher/spa/live.js): exact-value tests of the pure logic behind the Live tab's motion: the leg-hit and
combo win/loss diff between two consecutive real snapshots, the animate-or-snap gate (reduced motion, hidden tab, stale feed, gap),
and which combos get the hot sheen. Runs live.js under node. Display only: nothing here touches a money path."""
import os, json, subprocess
HERE = os.path.abspath("wtest")
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))
JS = os.path.join(HERE, "spa", "live.js")
prog = r"""
globalThis.S={};const L=require(process.argv[1]),o={};
const mk=(grp,res)=>L.lvSnap([{t:'A',group:grp,legs:[{ticker:'x',res:res[0]},{ticker:'y',res:res[1]}]},{t:'B',group:'pending',legs:[{ticker:'z',res:''}]}]);
const a=mk('pending',['','']),b=mk('pending',['yes','']),c=mk('won',['yes','yes']),d=mk('lost',['no','']);
const ok1={now:10000,prevAt:0,prevStale:false,reduce:false,hidden:false,stale:false};
o.snap=a;
o.hit=L.lvDiff(a,b,ok1);
o.won=L.lvDiff(b,c,ok1);
o.lost=L.lvDiff(a,d,ok1);
o.same=L.lvDiff(b,b,ok1);
o.first=L.lvDiff(null,b,ok1);
o.reduce=L.lvDiff(a,b,{...ok1,reduce:true});
o.hidden=L.lvDiff(a,b,{...ok1,hidden:true});
o.stale=L.lvDiff(a,b,{...ok1,stale:true});
o.prevStale=L.lvDiff(a,b,{...ok1,prevStale:true});
o.gap=L.lvDiff(a,b,{...ok1,now:L.LV_GAP_MS+1});
o.edge=L.lvDiff(a,b,{...ok1,now:L.LV_GAP_MS});
o.newcombo=L.lvDiff(a,L.lvSnap([{t:'Z',group:'won',legs:[{ticker:'q',res:'yes'}]}]),ok1);
o.gate=[L.lvGate({}),L.lvGate({reduce:1}),L.lvGate({hidden:1}),L.lvGate({stale:1})];
const cs=[{t:'p',group:'pending',offer_real:true,pays:10,offer:8},{t:'q',group:'pending',offer_real:true,pays:10,offer:7.9},{t:'m',group:'pending',moment:true,offer:1,pays:50},
 {t:'e',group:'pending',offer_real:false,pays:10,offer:9.5},{t:'w',group:'won',offer_real:true,pays:10,offer:10},{t:'r',group:'pending',offer_real:true,pays:20,offer:19}];
o.hot=cs.map(x=>L.lvHot(x));
o.pick=L.lvHotPick(cs);
console.log(JSON.stringify(o));
"""
r = subprocess.run(["node", "-e", prog, JS], capture_output=True, text=True)
ok("live.js loads under node and runs", r.returncode == 0, r.stderr[-300:])
o = json.loads(r.stdout) if r.returncode == 0 else {}
E = lambda **k: dict({"hits": [], "misses": [], "won": [], "lost": []}, **k)
ok("snapshot keys legs by combo and ticker", o.get("snap", {}).get("legs") == {"A|x": "", "A|y": "", "B|z": ""} and o["snap"]["grp"] == {"A": "pending", "B": "pending"}, o.get("snap"))
ok("a leg that turns yes is a hit", o.get("hit") == E(hits=["A|x"]), o.get("hit"))
ok("a combo pending to won: win moment plus its other leg hit", o.get("won") == E(hits=["A|y"], won=["A"]), o.get("won"))
ok("a combo pending to lost: loss and the missed leg only, no hit", o.get("lost") == E(misses=["A|x"], lost=["A"]), o.get("lost"))
ok("same picture again: nothing", o.get("same") == E(), o.get("same"))
ok("first paint (no earlier picture): nothing", o.get("first") == E(), o.get("first"))
ok("reduced motion: nothing", o.get("reduce") == E(), o.get("reduce"))
ok("hidden tab: nothing", o.get("hidden") == E(), o.get("hidden"))
ok("stale feed: nothing", o.get("stale") == E(), o.get("stale"))
ok("earlier picture was stale: nothing (snap, no replay of missed moments)", o.get("prevStale") == E(), o.get("prevStale"))
ok("gap over 90 s: nothing; exactly 90 s still counts", o.get("gap") == E() and o.get("edge") == E(hits=["A|x"]), (o.get("gap"), o.get("edge")))
ok("a combo that first appears already won is not celebrated", o.get("newcombo") == E(), o.get("newcombo"))
ok("gate", o.get("gate") == [True, False, False, False], o.get("gate"))
ok("hot: real offer at 80%+ of payout, or a flagged moment; estimates and settled never", o.get("hot") == [True, False, True, False, False, True], o.get("hot"))
ok("hot sheen: at most two, closest to paying first", o.get("pick") == ["r", "p"], o.get("pick"))
src = open(JS).read()
ok("motion block is guarded (errors swallowed) at the one call site", "try{lvFx();}catch(e){}" in src)
css = open(os.path.join(HERE, "spa", "live.css")).read()
ok("reduced-motion rule and the fresh-only live dot exist in live.css", "prefers-reduced-motion:reduce" in css and "main.lvfresh .livedot::after" in css and "main.lvstale" in css)
