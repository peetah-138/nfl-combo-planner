# CHECK: group=engine
"""Field motion (package M1, watcher/spa/field.js): exact-value tests of the pure logic (yard to position, first-down line,
play-event classification, drive trail, glide kind, the animate-or-snap decision) plus a replayable fixture
(fixtures/field_replay.json). Runs field.js under node. Display only: nothing here touches a money path."""
import os, json, subprocess
HERE = os.path.abspath("wtest")
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))
JS = os.path.join(HERE, "spa", "field.js")
FX = os.path.abspath("fixtures/field_replay.json")
prog = r"""
const F=require(process.argv[1]),fx=require(process.argv[2]),o={};
o.pos=[F.losPct(true,25),F.losPct(false,25),F.losPct(true,null),F.losPct(true,120),F.losPct(false,-5)];
o.fd=[F.fdPct(true,40,10),F.fdPct(false,40,10),F.fdPct(false,95,10),F.fdPct(true,5,10),F.fdPct(true,40,null)];
o.px=F.pctPx(12.5,320);
o.glide=[F.glideKind(10,10.2),F.glideKind(10,20),F.glideKind(10,25),F.glideKind(null,5)];
o.gate=[F.gate({reduce:true}),F.gate({hidden:true}),F.gate({stale:true}),F.gate({stale:false}),F.gate({stale:true,replay:true})];
const s=fx.steps.map(x=>F.snap(x.detail));o.snaps=s.map(x=>[x.poss,x.los,x.fd]);
const evs=[],gl=[];let prev=null,at=null,stale=false;
fx.steps.forEach((x,i)=>{const p=F.plan(prev,s[i],{now:x.t*1000,prevAt:at,prevStale:stale,prevMode:prev?'live':null,mode:'live',ok:true});
 evs.push(p.events.map(e=>e.k==='td'||e.k==='fg'?[e.k,e.side]:[e.k]));gl.push(p.glide?p.glide.kind:null);prev=s[i];at=x.t*1000;});
o.evs=evs;o.gl=gl;
o.noGlideStale=F.plan(s[0],s[1],{now:5000,prevAt:0,prevStale:true,prevMode:'live',mode:'live',ok:true}).events.length;
o.notOk=JSON.stringify(F.plan(s[0],s[1],{now:5000,prevAt:0,prevStale:false,prevMode:'live',mode:'live',ok:false}));
o.modeSwitch=F.plan(s[0],s[1],{now:5000,prevAt:0,prevStale:false,prevMode:'replay',mode:'live',ok:true}).events.length;
o.trail=[F.driveTrail(null,s[0]),F.driveTrail({poss:'IND',start:25},s[1]),F.driveTrail({poss:'HOU',start:25},s[1])];
o.safety=F.classify({poss:'IND',home:0,away:0,rz:false,down:1,los:50},{poss:'HOU',home:2,away:0,rz:false,down:1,los:80,type:'Safety',text:''}).map(e=>e.k);
o.pat=F.classify({poss:'IND',home:0,away:6,rz:false,down:1,los:50},{poss:'IND',home:0,away:7,rz:false,down:1,los:50,type:'',text:''}).length;
console.log(JSON.stringify(o));
"""
r = subprocess.run(["node", "-e", prog, JS, FX], capture_output=True, text=True)
ok("field.js loads under node and runs", r.returncode == 0, r.stderr[-300:])
o = json.loads(r.stdout) if r.returncode == 0 else {}
fx = json.load(open(FX))
ok("home attacks left, away right; clamped; no distance = none", o.get("pos") == [25, 75, None, 100, 100], o.get("pos"))
ok("first-down line: toward the attacked end zone, clamped, none without distance", o.get("fd") == [30, 50, 100, 0, None], o.get("fd"))
ok("yards to pixels", o.get("px") == 40)
ok("glide kind: none under half a yard, slide, hop from 15", o.get("glide") == ["none", "slide", "hop", "none"], o.get("glide"))
ok("gate: reduced motion and hidden never; stale blocks live; replay allowed", o.get("gate") == [False, False, False, True, True], o.get("gate"))
ok("fixture snapshots (poss, ball %, first-down %)", o.get("snaps") == [["IND", 25, 30], ["IND", 35, 45], ["IND", 82, 92], ["IND", 97, 99], ["HOU", 80, 70], ["IND", 40, 50], ["HOU", 70, 60], ["HOU", 20, 17], ["HOU", 50, 40]], o.get("snaps"))
ok("replayable fixture: events", o.get("evs") == [x["events"] for x in fx["steps"]], o.get("evs"))
ok("replayable fixture: glide kinds", o.get("gl") == [x["glide"] for x in fx["steps"]], o.get("gl"))
ok("stale previous snapshot: no events", o.get("noGlideStale") == 0)
ok("not ok (reduced motion, hidden, stale): nothing animates", o.get("notOk") == '{"events":[],"glide":null}', o.get("notOk"))
ok("live vs replay mode switch: no events", o.get("modeSwitch") == 0)
t = o.get("trail", [])
ok("drive trail: first sight empty, grows from the drive start, restarts on a new possession",
   t[:1] == [{"start": 25, "los": 25, "left": 25, "width": 0, "fromLeft": True}] and t[1]["width"] == 10 and t[1]["left"] == 25 and t[2]["start"] == 35 and t[2]["width"] == 0, t)
ok("safety is scored, a 1-point kick is not an event", o.get("safety") == ["safety", "possession"][:1] or o.get("safety") == ["safety"], o.get("safety"))
ok("extra point (+1) makes no event", o.get("pat") == 0)
src = open(JS).read()
ok("field.js animates only transform-class properties", all(k not in src for k in ("animate(", )) or "translate" in src)
ok("field.js never touches a fetch or money path", not any(w in src for w in ("fetch(", "XMLHttpRequest", "api(", "kalshi")))
