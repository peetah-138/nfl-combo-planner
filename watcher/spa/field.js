/* Field motion (package M1). Display only: it reads what the game page already drew and adds motion on top. It never changes
   what a number says, never touches a fetch, a bet or a price, and an error in here is swallowed (the page stays as drawn).
   Hooks: loaded after game_tabs.js, it wraps gameAfterPaint (every game-sheet paint) and pbpRefresh/pbpFx (replay stepping), so
   game.js and game_tabs.js are untouched. Everything animates transform / opacity (translate, scale, rotate properties too).
   Rules: events fire only between two real consecutive snapshots (never after a gap, never while the feed is stale or the page is
   hidden); prefers-reduced-motion = the final state only; loops pause when the strip is offscreen or the tab is hidden.
   Pure logic (positions, event classification, the animate-or-snap decision) is at the top and unit-tested from Node. */
const Field=(()=>{
const GAP_MS=90000;            // a longer silence between two snapshots is a gap: snap to the new picture, replay nothing
const STALE_S=60;              // the same threshold the page uses for its ".old" freshness text
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const num=v=>(v==null||v===''||isNaN(+v))?null:+v;

/* ---- pure logic ------------------------------------------------------------------------------------------------------------ */
// % across the grass (0 = left goal line, 100 = right goal line) of a spot `ytz` yards from the end zone the offence attacks.
// Home attacks left (so its yards-to-go IS the distance from the left line); away attacks right.
function losPct(homeHas,ytz){const y=num(ytz);if(y==null)return null;return clamp(homeHas?y:100-y,0,100);}
// The first-down line: `dist` yards further toward the attacked end zone, or null when the feed gave no distance.
function fdPct(homeHas,los,dist){const d=num(dist);if(los==null||d==null)return null;return clamp(homeHas?los-d:los+d,0,100);}
function pctPx(pct,width){return +(pct/100*width).toFixed(2);}
function sideOf(d,abbr){const b=(d||{}).board||{},a=String(abbr||'').toUpperCase();if(!a)return null;
 if((b.home||{}).abbr&&b.home.abbr.toUpperCase()===a)return 'home';if((b.away||{}).abbr&&b.away.abbr.toUpperCase()===a)return 'away';return null;}
// Same answer as the page's possTeam(): the drive's team first, then the scoreboard's possession team; '' when unknown.
function possAbbr(d){const sit=(d||{}).situation||{},dr=(d||{}).drive||{};
 for(const c of [dr.teamAbbr,sit.possAbbr]){const a=String(c||'').toUpperCase();if(a&&sideOf(d,a))return a;}return '';}
// One normalised picture of the strip from a game-detail block (the same one fieldStrip draws), or null when no ball spot.
function snap(d){if(!d)return null;const b=d.board||{},sit=d.situation||{},dr=d.drive||{};
 let ytz=num(dr.ballYardsToEndzone);if(ytz==null&&num(sit.yardLine)!=null)ytz=100-sit.yardLine;if(ytz==null)return null;
 const poss=possAbbr(d),homeHas=!!poss&&sideOf(d,poss)==='home';const los=losPct(homeHas,ytz);
 return {poss,homeHas,los,fd:fdPct(homeHas,los,sit.distance),rz:!!sit.isRedZone,down:num(sit.down),
  home:num((b.home||{}).score),away:num((b.away||{}).score),
  type:String(sit.lastPlayType||''),text:String(sit.lastPlayText||''),live:b.state==='in',replay:!!sit.replay};}
const TURN=/intercept|fumble|on downs|turnover/i;
// What changed between two consecutive real snapshots, in the order it should be shown: a score beats a turnover beats a
// possession change beats a first down beats the red zone. [] when nothing happened (a plain gain is a glide, not an event).
function classify(a,b){if(!a||!b)return [];const ev=[];
 const dh=(a.home!=null&&b.home!=null)?b.home-a.home:0,da=(a.away!=null&&b.away!=null)?b.away-a.away:0;
 const side=dh>=da?'home':'away',pts=Math.max(dh,da);let scored=false;
 if(pts>=6){ev.push({k:'td',side});scored=true;}
 else if(pts===3){ev.push({k:'fg',side});scored=true;}
 else if(pts===2&&/safety/i.test(b.type+' '+b.text)){ev.push({k:'safety',side});scored=true;}
 if(!scored&&a.poss&&b.poss&&a.poss!==b.poss)ev.push({k:TURN.test(b.type+' '+b.text)?'turnover':'possession',team:b.poss});
 if(a.poss&&a.poss===b.poss&&b.down===1&&a.down!=null&&a.down>1&&b.los!=null&&a.los!=null){
  const dir=b.homeHas?-1:1;if((b.los-a.los)*dir>0)ev.push({k:'firstdown',team:b.poss});}
 if(!a.rz&&b.rz&&!scored)ev.push({k:'redzone'});
 return ev;}
// The drive trail: it starts where this possession was first seen and grows to the ball. A new possession restarts it.
function driveTrail(prev,s){if(!s)return null;const start=(prev&&prev.poss===s.poss&&prev.start!=null)?prev.start:s.los;
 return {start,los:s.los,left:Math.min(start,s.los),width:+Math.abs(s.los-start).toFixed(2),fromLeft:start<=s.los};}
// How the ball should travel: nothing under half a yard, a pass-like hop from 15 yards, a plain slide otherwise.
function glideKind(from,to){if(from==null||to==null)return 'none';const m=Math.abs(to-from);return m<.5?'none':m>=15?'hop':'slide';}
// Should motion run at all? Reduced motion and a hidden page never; a live feed only while fresh; a replay step is calm and fine.
function gate(o){if(o.reduce||o.hidden)return false;return o.replay?true:!o.stale;}
// The whole decision for one new snapshot: events to show (only when everything is real, fresh and consecutive) and the ball glide.
function plan(prev,next,c){const out={events:[],glide:null};if(!next)return out;
 const consecutive=!!prev&&c.prevMode===c.mode&&c.prevAt!=null&&(c.now-c.prevAt)<=GAP_MS&&!c.prevStale;
 if(c.ok&&prev&&prev.los!=null&&next.los!=null){const k=glideKind(prev.los,next.los);if(k!=='none'&&(c.mode!=='live'||consecutive))out.glide={from:prev.los,to:next.los,kind:k};}
 if(c.ok&&consecutive&&c.mode==='live')out.events=classify(prev,next);
 return out;}

/* ---- the DOM side ----------------------------------------------------------------------------------------------------------- */
const D4=520,ST=80;      // field move time (the planned --d-4); the stagger between ball, first-down line and chips
const R={};              // per game: {snap,mode,at,stale,start,fx,pids}
let io=null,lastDelay=0;
const reduceMQ=()=>typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;
function isStale(){try{const b=typeof frBuilt==='function'?frBuilt('G'):null;
 return b==null||b>STALE_S||(typeof netIsDown==='function'&&netIsDown())||(typeof S!=='undefined'&&S.live_ok===false&&!!S.esEver);}catch(e){return true;}}
const col=(c,fb)=>typeof fcolor==='function'?fcolor(c,fb):fb;
const strip=()=>document.querySelector('#sheet .fstrip');
const el=(tag,cls,css)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(css)e.style.cssText=css;return e;};
function anim(e,frames,o){if(!e||!e.animate)return null;try{return e.animate(frames,Object.assign({fill:'backwards',easing:'cubic-bezier(.2,.8,.2,1)'},o));}catch(x){return null;}}
function gone(e,ms){setTimeout(()=>{if(e&&e.parentNode)e.parentNode.removeChild(e);},ms);}

function glideBall(st,g,W,delay){const px=pctPx(g.from-g.to,W),ball=st.querySelector('.fball'),dir=st.querySelector('.fdir');
 const frames=g.kind==='hop'?[{translate:px+'px 0',offset:0},{translate:(px/2)+'px -9px',offset:.5},{translate:'0 0',offset:1}]:[{translate:px+'px 0'},{translate:'0 0'}];
 anim(ball,frames,{duration:D4,delay});anim(dir,[{translate:px+'px 0'},{translate:'0 0'}],{duration:D4,delay});}
function drawTrail(st,tr,s,prevTr,animate,d){const grass=st.querySelector('.grass');if(!grass||!tr||tr.width<.5)return;
 const home=((d.board||{}).home)||{},away=((d.board||{}).away)||{},c=s.poss?col(s.homeHas?home.color:away.color,'#ffffff'):'#ffffff';
 const t=el('i','fxtrl'+(tr.fromLeft?'':' r'),`left:${tr.left}%;width:${tr.width}%;--c:${c}`);grass.insertBefore(t,grass.firstChild);
 if(animate){const was=prevTr&&prevTr.start===tr.start?prevTr.width:0;anim(t,[{scale:(was/tr.width)+' 1'},{scale:'1 1'}],{duration:D4,delay:ST});}}

function banner(st,kind,txt,color,elapsed){const fld=st.querySelector('.fld');if(!fld)return;
 const b=el('span','fxban '+kind,color?`--c:${color}`:'');b.textContent=txt;if(elapsed)b.style.animationDelay=(-elapsed)+'ms';fld.appendChild(b);gone(b,2200);}
function wash(st,color,delay){const fld=st.querySelector('.fld');if(!fld)return;const w=el('i','fxwash',`--c:${color}`);if(delay)w.style.animationDelay=delay+'ms';fld.appendChild(w);gone(w,1800);}
function crowd(st,color){const fld=st.querySelector('.fld');if(!fld)return;const c=el('span','fxcrowd',`--c:${color}`);
 for(let i=0;i<14;i++){const d=el('i','',`left:${(i*7.2+3).toFixed(1)}%;animation-delay:${(i*37)%320}ms`);c.appendChild(d);}fld.appendChild(c);gone(c,1800);}
function sweep(st,color){const fld=st.querySelector('.fld');if(!fld)return;const w=el('i','fxsweep',`--c:${color}`);fld.appendChild(w);gone(w,1100);}
// The ball (a ghost copy) flies from the line of scrimmage into the end zone; a field goal adds the uprights it goes through.
function flight(st,s,prev,sideScored,kind,W){const grass=st.querySelector('.grass'),ball=st.querySelector('.fball');if(!grass||!ball||prev.los==null)return;
 const goal=sideScored==='home'?0:100,dx=pctPx(prev.los-goal,W),g=ball.cloneNode(true);g.classList.add('fxg');g.style.left=goal+'%';g.removeAttribute('style');g.style.left=goal+'%';
 grass.appendChild(g);const fg=kind==='fg';
 anim(g,[{translate:(-pctPx(goal-prev.los,W))+'px 0',opacity:1,offset:0},{translate:(-pctPx(goal-prev.los,W)/2)+'px '+(fg?-16:-11)+'px',opacity:1,offset:.5},{translate:'0 0',opacity:1,offset:.85},{translate:'0 0',opacity:0,offset:1}],{duration:fg?900:760,delay:ST,fill:'both'});
 if(fg){const up=el('i','fxup',goal===0?'left:0':'right:0');grass.appendChild(up);gone(up,1700);}
 void dx;gone(g,1700);}
function ezPulse(st,sideScored,color){const ez=st.querySelector(sideScored==='home'?'.ez.l':'.ez.r');if(!ez)return;const p=el('i','fxezp',`--c:${color}`);ez.appendChild(p);gone(p,1500);}

function runEvents(st,ev,s,prev,d,W){const home=(d.board||{}).home||{},away=(d.board||{}).away||{};
 const hc=col(home.color,'#444'),ac=col(away.color,'#444'),teamCol=a=>sideOf(d,a)==='home'?hc:ac,sideCol=x=>x==='home'?hc:ac,sideAbbr=x=>x==='home'?home.abbr:away.abbr;
 let shown=false;const f=R.cur;
 const say=(kind,txt,color,ms)=>{if(shown)return;shown=true;banner(st,kind,txt,color);if(f)f.fx={kind,txt,color,t0:Date.now(),ms};};
 ev.forEach(e=>{
  if(e.k==='td'){say('td',(sideAbbr(e.side)||'')+' TOUCHDOWN',sideCol(e.side),1800);wash(st,sideCol(e.side),0);ezPulse(st,e.side,sideCol(e.side));flight(st,s,prev,e.side,'td',W);crowd(st,sideCol(e.side));}
  else if(e.k==='fg'){say('fg',(sideAbbr(e.side)||'')+' FIELD GOAL',sideCol(e.side),1800);wash(st,sideCol(e.side),0);flight(st,s,prev,e.side,'fg',W);crowd(st,sideCol(e.side));}
  else if(e.k==='safety'){say('fg',(sideAbbr(e.side)||'')+' SAFETY',sideCol(e.side),1800);ezPulse(st,e.side==='home'?'away':'home',sideCol(e.side));}
  else if(e.k==='turnover'){say('to','TURNOVER',teamCol(e.team),1800);sweep(st,teamCol(e.team));crowd(st,teamCol(e.team));const b=st.querySelector('.fball');if(b)b.classList.add('fxturn');}
  else if(e.k==='possession'){say('sm',e.team+' BALL',teamCol(e.team),1500);sweep(st,teamCol(e.team));}
  else if(e.k==='firstdown'){say('sm','1ST DOWN','#f5d020',1400);const l=st.querySelector('.fdline');if(l){
    if(prev.fd!=null&&s.fd!=null&&prev.fd!==s.fd)anim(l,[{translate:pctPx(prev.fd-s.fd,W)+'px 0'},{translate:'0 0'}],{duration:D4,delay:ST});
    l.classList.add('fxlock');}}
  else if(e.k==='redzone'){const z=st.querySelector('.frz');if(z)z.classList.add('fxrz');const c=st.querySelector('.rzt:not(.rpl)');if(c)c.classList.add('fxpop');}
 });}

// A banner still running when the strip is redrawn is redrawn too, from where it was, so a repaint never cuts it short.
function resume(st,f){if(!f||!f.fx)return;const el=Date.now()-f.fx.t0;if(el>=f.fx.ms){f.fx=null;return;}banner(st,f.fx.kind,f.fx.txt,f.fx.color,el);}

function rows(r,key,f,ok){const pan=document.querySelector('#sheet .gpanel[data-tab="pbp"]');if(!pan)return;
 const ids=Array.from(pan.querySelectorAll('.pp[data-pid]'));if(!ids.length)return;
 const seen=f.pids,now=new Set(ids.map(x=>x.dataset.pid));f.pids=now;
 if(!seen||!ok)return;let i=0;
 ids.forEach(x=>{if(seen.has(x.dataset.pid))return;const n=i++;if(n>=6)return;
  anim(x,[{translate:'0 -10px',opacity:0},{translate:'0 0',opacity:1}],{duration:260,delay:n*30});
  if(x.classList.contains('sc')){const rl=el('i','fxrail');x.appendChild(rl);gone(rl,1600);}});}

function watch(st){if(typeof IntersectionObserver==='undefined')return;if(io)io.disconnect();
 io=new IntersectionObserver(es=>{es.forEach(e=>e.target.classList.toggle('fxpaused',!e.isIntersecting||document.hidden));},{threshold:0});io.observe(st);}

// Live state of the strip: the pulsing dot and the arrow nudge run only while the game is live AND the feed is fresh.
function liveState(){const st=strip();if(!st)return;const f=R.cur;if(!f||!f.snap)return;
 const live=f.mode==='live'&&f.snap.live,run=live&&!isStale()&&!reduceMQ()&&!document.hidden;
 st.classList.toggle('fxlive',run);st.classList.toggle('fxstale',live&&!run);st.classList.toggle('fxpaused',document.hidden||st.classList.contains('fxpaused')&&!run&&false);
 const dot=st.querySelector('.fxdot');if(dot)dot.title=run?'Live, feed fresh':live?'Feed is not fresh, so nothing here is moving':'';}

function update(r){const st=strip();if(!st||!r)return;const t=(typeof S!=='undefined'&&S.gameOpen)||'';
 const d=typeof gameStepDetail==='function'?gameStepDetail(r):r.detail;if(!d)return;
 const s=snap(d);st.classList.add('fx');const replay=!!(s&&s.replay)||(typeof S!=='undefined'&&S.pbpStep!=null);
 const mode=replay?'replay':'live',f=R[t]||(R[t]={snap:null,mode:null,at:null,stale:false,start:null,fx:null,pids:null});R.cur=f;
 const reduce=reduceMQ(),stale=isStale(),ok=gate({reduce,hidden:document.hidden,stale,replay});
 const grass=st.querySelector('.grass'),W=grass?grass.getBoundingClientRect().width:0;
 // the dot for a live game, always drawn (static) so the strip never shifts; liveState() decides whether it pulses
 const fld=st.querySelector('.fld');if(fld&&s&&mode==='live'&&s.live)fld.appendChild(el('i','fxdot'));
 if(s){st.style.setProperty('--fxdir',s.homeHas?-1:1);
  const prevSnap=f.snap&&f.mode===mode?f.snap:(f.snap||null);
  const pl=plan(prevSnap,s,{now:Date.now(),prevAt:f.at,prevStale:f.stale,prevMode:f.mode,mode,ok:ok&&W>0});
  const tr=driveTrail(f.snap&&f.mode===mode?{poss:f.snap.poss,start:f.start}:null,s);
  const prevTr=f.snap&&f.mode===mode&&f.start!=null?{start:f.start,width:Math.abs(f.snap.los-f.start)}:null;
  drawTrail(st,tr,s,prevTr,!!pl.glide,d);
  if(pl.glide)glideBall(st,pl.glide,W,lastDelay);
  if(pl.events.length)runEvents(st,pl.events,s,f.snap,d,W);else if(ok)resume(st,f);
  if(ok&&f.snap&&f.mode===mode){const dd=st.querySelector('.situ .dd'),p0=f.sit;if(dd&&p0&&p0!==dd.textContent)anim(dd,[{opacity:.35},{opacity:1}],{duration:200,easing:'ease-out'});}
  f.sit=(st.querySelector('.situ .dd')||{}).textContent||'';
  f.start=tr?tr.start:null;f.snap=s;
 }else{f.snap=null;f.start=null;}
 f.mode=mode;f.at=Date.now();f.stale=!replay&&stale;lastDelay=0;
 if(mode==='live')rows(r,t,f,ok&&!stale);
 watch(st);liveState();}

function install(){if(typeof document==='undefined')return;
 if(typeof gameAfterPaint==='function'){const o=gameAfterPaint;gameAfterPaint=function(r){o(r);try{update(r);}catch(e){}};}
 if(typeof pbpFx==='function'){const o=pbpFx;pbpFx=function(p){const v=o(p);lastDelay=v||0;return v;};}
 if(typeof pbpRefresh==='function'){const o=pbpRefresh;pbpRefresh=function(mode){lastDelay=0;o(mode);if(mode){try{update(S.gameR);}catch(e){}}};}
 document.addEventListener('visibilitychange',()=>{try{liveState();const s=strip();if(s)s.classList.toggle('fxpaused',document.hidden);}catch(e){}});
 setInterval(()=>{try{liveState();}catch(e){}},2000);}
install();

return {losPct,fdPct,pctPx,snap,classify,driveTrail,glideKind,gate,plan,GAP_MS,STALE_S,update};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=Field;
