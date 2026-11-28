# CHECK: group=engine
"""Motion M3 (watcher/spa/motion3.js): exact-value tests of the pure logic behind the Games tab, game sheet and Results motion:
the animate-or-snap gate, score and win-chance moves between two consecutive real pictures, who won a finished card, bar slides,
entrance stagger, result tone and the P/L count-up text. Runs motion3.js under node. Display only: no money path is touched."""
import os, json, subprocess
HERE = os.path.abspath("wtest")
ok = lambda n, c, info=None: print(("PASS " if c else "FAIL ") + n + ("" if c or info is None else f"  ({info})"))
JS = os.path.join(HERE, "spa", "motion3.js")
prog = r"""
const M=require(process.argv[1]),o={};
o.gate=[M.gate({}),M.gate({reduce:1}),M.gate({hidden:1}),M.gate({live:1,stale:1}),M.gate({stale:1}),M.gate({live:1})];
o.sm=[M.scoreMove([10,7],[17,7]),M.scoreMove([10,7],[10,7]),M.scoreMove([10,7],[9,7]),M.scoreMove(null,[1,1]),M.scoreMove([3,3],[3,6]),M.scoreMove([3,'x'],[4,4])];
o.cm=[M.chanceMove(.5,.58),M.chanceMove(.5,.62),M.chanceMove(.5,.52),M.chanceMove(.6,.45),M.chanceMove(null,.5)];
o.ft=[M.finalTone({phase:'over',sc:{me:21,opp:14}}),M.finalTone({phase:'over',sc:{me:14,opp:21}}),M.finalTone({phase:'over',sc:{me:7,opp:7}}),
 M.finalTone({phase:'over',kind:'spread',sc:{me:21,opp:14}}),M.finalTone({phase:'live',sc:{me:21,opp:14}}),M.finalTone({phase:'over'})];
const live=(t,me,opp,ch)=>({ticker:t,state:'live',phase:'q2',sc:{me,opp},chance:ch});
const A=M.snapGames([live('a',10,7,.5),live('b',3,3,.4)]);
const B=M.snapGames([live('a',17,7,.62),{ticker:'b',state:'live',phase:'over',sc:{me:3,opp:6},chance:0}]);
const c1={now:10000,prevAt:0,prevStale:false,reduce:false,hidden:false,stale:false};
o.d=M.diffGames(A,B,c1);
o.dreduce=M.diffGames(A,B,{...c1,reduce:true});
o.dhidden=M.diffGames(A,B,{...c1,hidden:true});
o.dstale=M.diffGames(A,B,{...c1,stale:true});
o.dprev=M.diffGames(A,B,{...c1,prevStale:true});
o.dgap=M.diffGames(A,B,{...c1,now:M.GAP_MS+1});
o.dedge=Object.keys(M.diffGames(A,B,{...c1,now:M.GAP_MS}));
o.dfirst=M.diffGames(null,B,c1);
o.dnew=M.diffGames({},B,c1);
o.bs=[M.barScale(.5),M.barScale(0),M.barScale(null),M.barScale(1.5)];
o.bf=[M.barFrom(.5,.6,true),M.barFrom(.5,.501,true),M.barFrom(.5,.6,false),M.barFrom(null,.6,true)];
o.sd=[M.stagDelay(0),M.stagDelay(5),M.stagDelay(6),M.stagDelay(-1)];
o.rt=[M.resultTone(12.5),M.resultTone(-3),M.resultTone(0),M.resultTone(null)];
o.ct=[M.countText('+$1,234.50',.4),M.countText('−$12',.5),M.countText('none',.5),M.countText('+$1,234.50',1),M.countText('$9',0)];
o.dt=[M.deltaText(7),M.deltaText(-5),M.deltaText(0)];
o.eo=[M.easeOut(0),M.easeOut(1),M.easeOut(2)];
console.log(JSON.stringify(o));
"""
r = subprocess.run(["node", "-e", prog, JS], capture_output=True, text=True)
ok("motion3.js loads under node and runs", r.returncode == 0, r.stderr[-300:])
o = json.loads(r.stdout) if r.returncode == 0 else {}
ok("gate: reduced motion or hidden never; stale blocks only live-data motion", o.get("gate") == [True, False, False, False, True, True], o.get("gate"))
ok("score move: points gained per side; no change, a correction down or bad data is nothing",
   o.get("sm") == [{"me": 7, "opp": 0}, None, None, None, {"me": 0, "opp": 3}, None], o.get("sm"))
ok("chance move: shown from 3 points, big from 10, signed",
   o.get("cm") == [{"d": 8, "dir": "up", "show": True, "big": False}, {"d": 12, "dir": "up", "show": True, "big": True},
                   {"d": 2, "dir": "up", "show": False, "big": False}, {"d": -15, "dir": "down", "show": True, "big": True}, None], o.get("cm"))
ok("final tone: win, loss; tie, spread, unfinished, no score are plain", o.get("ft") == ["win", "loss", "", "", "", ""], o.get("ft"))
ok("diff: score and chance move for a live game; a game that finishes with a loss reports the loss",
   o.get("d") == {"a": {"score": {"me": 7, "opp": 0}, "chance": {"d": 12, "dir": "up", "show": True, "big": True}}, "b": {"final": "loss"}}, o.get("d"))
ok("diff: reduced motion, hidden, stale, stale earlier picture, gap over 90 s: nothing",
   all(o.get(k) == {} for k in ("dreduce", "dhidden", "dstale", "dprev", "dgap")), [o.get(k) for k in ("dreduce", "dhidden", "dstale", "dprev", "dgap")])
ok("diff: exactly 90 s still counts; no earlier picture or a new game: nothing", o.get("dedge") == ["a", "b"] and o.get("dfirst") == {} and o.get("dnew") == {}, (o.get("dedge"), o.get("dfirst"), o.get("dnew")))
ok("bar scale: 2% minimum, 100% maximum, none is 0", o.get("bs") == [0.5, 0.02, 0, 1], o.get("bs"))
ok("bar slides only when it really moved and motion is on", o.get("bf") == [0.5, None, None, None], o.get("bf"))
ok("stagger: first six 30 ms apart, the rest none", o.get("sd") == [0, 150, None, None], o.get("sd"))
ok("result tone: profit celebrates, loss sober, flat or unknown plain", o.get("rt") == ["win", "loss", "flat", "flat"], o.get("rt"))
ok("count text: first number counts, decimals and commas and the rest stay",
   o.get("ct") == ["+$493.80", "−$6", "none", "+$1,234.50", "$0"], o.get("ct"))
ok("delta text uses a proper minus", o.get("dt") == ["+7", "−5", "0"], o.get("dt"))
ok("ease-out never overshoots", o.get("eo") == [0, 1, 1], o.get("eo"))
src = open(JS).read()
ok("each page hook is guarded (errors swallowed)", src.count("try{afterGames(pre);}catch(e){}") == 1 and src.count("try{afterResults(pre);}catch(e){}") == 1 and src.count("try{afterSheet(r);}catch(e){}") == 1)
ok("animates transform and opacity only (no width/height/left/top in keyframes)", "width:" not in src.split("function flip")[1].split("function sweep")[0])
css = open(os.path.join(HERE, "spa", "motion3.css")).read()
ok("css: reduced-motion rule and the stale/hidden hold exist", "prefers-reduced-motion:reduce" in css and "main.m3stale" in css and "main.m3hid" in css)
ok("the win-chance bar is a transform now, not a width", "transition:transform" in open(os.path.join(HERE, "spa", "games.css")).read() and "data-m3b" in open(os.path.join(HERE, "spa", "games.js")).read())
man = json.load(open(os.path.join(HERE, "spa", "MANIFEST.json")))
ok("manifest lists the new files", "motion3.js" in man["js"] and "motion3.css" in man["css"])
