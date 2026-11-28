/* Motion package M3: Games tab, game sheet and Results. Display only: nothing here reads or changes a price, bet, cap, Pause or
   rule, and it fetches nothing. It reads what the page already drew (and the data behind it) and adds motion on top; an error in
   here is swallowed and the page stays as drawn. Hooks: loaded after game_tabs.js, it wraps renderGames, renderResults and
   paintGame, so games.js, game.js, results.js and common.js keep their own logic. Only transform and opacity animate (CSS in
   motion3.css, WAAPI here), on the --dur-* tokens. Rules: a moment fires only between two real consecutive snapshots (never
   after a gap over 90 s, after a stale one, while the tab is hidden, or with reduced motion); wins are celebrated, losses are
   sober (a slow dim, no colour alarm); numbers are always final in the DOM. The pure parts (diffs, tones, count text, stagger)
   are exact-value tested by t_motion_m3.py under node. */
const Motion3=(()=>{
const GAP_MS=90000;             // a longer silence between two snapshots is a gap: snap, replay nothing
const STALE_S=60;               // same threshold as the page's ".old" freshness text
const SHOW_PTS=3,BIG_PTS=10;    // a win-chance move shows a "+N" chip from 3 points, and a glow from 10
const MAX_STAG=6,STAG_MS=30;    // list entrances: the first six, 30 ms apart
const COUNT_MS={win:800,flat:520,loss:520};
const num=v=>(v==null||v===''||isNaN(+v))?null:+v;

/* ---- pure logic ------------------------------------------------------------------------------------------------------------ */
// Decorative motion needs a visible page and no reduced-motion setting; motion that implies live data also needs a fresh feed.
function gate(c){c=c||{};if(c.reduce||c.hidden)return false;return c.live?!c.stale:true;}
// Points scored between two snapshots, per side. null when nothing went up (a correction downward just snaps).
function scoreMove(prev,next){if(!prev||!next)return null;const pm=num(prev[0]),po=num(prev[1]),nm=num(next[0]),no=num(next[1]);
 if(pm==null||po==null||nm==null||no==null)return null;const me=nm-pm,opp=no-po;if(me<0||opp<0||(me===0&&opp===0))return null;
 return {me,opp};}
// How the win chance moved, in whole points (the two are 0..1 chances). show from 3 points, big from 10.
function chanceMove(prev,next){const a=num(prev),b=num(next);if(a==null||b==null)return null;const d=Math.round((b-a)*100);
 return {d,dir:d>0?'up':d<0?'down':'flat',show:Math.abs(d)>=SHOW_PTS,big:Math.abs(d)>=BIG_PTS};}
// Who won a finished game card: only plain "to win" cards (a spread or total card cannot be told from the score), never a tie.
function finalTone(g){if(!g||g.phase!=='over'||g.kind==='spread'||g.kind==='total')return '';const sc=g.sc;if(!sc)return '';
 const me=num(sc.me),opp=num(sc.opp);if(me==null||opp==null||me===opp)return '';return me>opp?'win':'loss';}
const isLive=g=>!!g&&g.state==='live'&&!['probably_over','waiting','over'].includes(g.phase);
// One small picture of every game card: score, chance, live, over. Keyed like the cards are.
function snapGames(list){const o={};(list||[]).forEach(g=>{const k=g.ticker||g.name;if(!k)return;const sc=g.sc;
 o[k]={sc:sc&&num(sc.me)!=null&&num(sc.opp)!=null?[+sc.me,+sc.opp]:null,ch:num(g.chance),live:isLive(g),over:g.phase==='over',tone:finalTone(g)};});return o;}
// What just changed between two consecutive real pictures: scores that went up, win-chance moves, games that just finished.
function diffGames(prev,next,c){const o={};c=c||{};
 if(!prev||!next||!gate({reduce:c.reduce,hidden:c.hidden,stale:c.stale,live:true})||c.prevStale||c.prevAt==null||(c.now-c.prevAt)>GAP_MS||c.now<c.prevAt)return o;
 for(const k of Object.keys(next)){const a=prev[k],b=next[k];if(!a)continue;const e={};
  if(a.live&&b.live){const s=scoreMove(a.sc,b.sc);if(s)e.score=s;const m=chanceMove(a.ch,b.ch);if(m&&m.show)e.chance=m;}
  if(a.live&&b.over&&!a.over&&b.tone)e.final=b.tone;
  if(Object.keys(e).length)o[k]=e;}
 return o;}
// The chance bar is a scaleX: 2% minimum so a tiny chance still shows, 100% max.
function barScale(ch){const v=num(ch);return v==null?0:Math.max(2,Math.min(100,v*100))/100;}
// Where the bar slides from: the old scale, only when it really moved and motion is on; otherwise null (just show the new one).
function barFrom(old,next,ok){if(!ok||old==null||next==null)return null;return Math.abs(old-next)>0.004?old:null;}
// Entrance stagger: index -> delay in ms, or null past the sixth (those just appear).
function stagDelay(i){return i>=0&&i<MAX_STAG?i*STAG_MS:null;}
// How a result feels: only a real profit celebrates; flat is plain; a loss is sober.
function resultTone(pl){const v=num(pl);if(v==null)return 'flat';return v>0.004?'win':v<-0.004?'loss':'flat';}
// "+$1,234.50" at 40% -> "+$493.80": the first number in the text counts up, the rest of the text stays; the decimals stay too.
function countText(t,f){t=String(t);const m=/(\d[\d,]*)(\.(\d+))?/.exec(t);if(!m)return t;const dec=m[3]?m[3].length:0;
 const end=+(m[1].replace(/,/g,'')+(m[3]?'.'+m[3]:''));const v=end*Math.max(0,Math.min(1,f));
 return t.slice(0,m.index)+v.toLocaleString('en-US',{minimumFractionDigits:dec,maximumFractionDigits:dec})+t.slice(m.index+m[0].length);}
const easeOut=t=>1-Math.pow(1-Math.max(0,Math.min(1,t)),3);   // numbers never overshoot
// A short signed chip text: "+7" in your favour, "−5" against, using the proper minus sign.
const deltaText=d=>(d>0?'+':d<0?'−':'')+Math.abs(d);

/* ---- page side ------------------------------------------------------------------------------------------------------------- */
const reduceNow=()=>typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;
function stale(key){try{const b=typeof frBuilt==='function'?frBuilt(key):null;
 if(b==null||b>STALE_S)return true;if(typeof netIsDown==='function'&&netIsDown())return true;
 if(typeof S!=='undefined'&&S.live_ok===false&&!!S.esEver)return true;
 const sc=typeof frScores==='function'?frScores(key):null;return !!(sc!=null&&sc>90&&typeof frLive==='function'&&frLive(key));}catch(e){return true;}}
const st=()=>{S.m3=S.m3||{bars:{},sp:{}};return S.m3;};
function flag(m,key){try{const s=stale(key);m.classList.toggle('m3stale',s);m.classList.toggle('m3fresh',!s&&!document.hidden);m.classList.toggle('m3hid',!!document.hidden);}catch(e){}}
function cardsByKey(m){const o={};m.querySelectorAll('.gc[data-gk]').forEach(c=>{o[c.dataset.gk]=c;});return o;}
const EASE='cubic-bezier(.2,.8,.2,1)',POP='cubic-bezier(.2,.9,.25,1.12)';
function anim(el,frames,opt){try{return el.animate?el.animate(frames,opt):null;}catch(e){return null;}}
// The number flips: the old digits rise out, the new ones rise in from below. The text is already final in the DOM.
function flip(el,oldText){if(!el||oldText==null)return;el.style.position=el.style.position||'relative';
 const g=document.createElement('i');g.className='m3g';g.setAttribute('aria-hidden','true');g.textContent=oldText;el.appendChild(g);
 const a=anim(g,[{transform:'none',opacity:1},{transform:'translateY(-70%)',opacity:0}],{duration:260,easing:EASE,fill:'forwards'});
 if(a)a.onfinish=()=>g.remove();else g.remove();setTimeout(()=>{if(g.isConnected)g.remove();},700);
 anim(el.querySelector?el:el,[{transform:'translateY(60%)',opacity:0},{transform:'none',opacity:1}],{duration:320,easing:POP});}
// A small chip that rises off a number and fades: "+7" (green) in your favour, grey otherwise (a loss is never a colour alarm).
function chip(host,text,good){if(!host)return;const c=document.createElement('i');c.className='m3d '+(good?'good':'calm');c.textContent=text;c.setAttribute('aria-hidden','true');
 host.appendChild(c);const a=anim(c,[{transform:'translateY(4px) scale(.9)',opacity:0},{transform:'translateY(-6px) scale(1)',opacity:1,offset:.2},{transform:'translateY(-22px) scale(1)',opacity:0}],{duration:1200,easing:EASE,fill:'forwards'});
 if(a)a.onfinish=()=>c.remove();setTimeout(()=>{if(c.isConnected)c.remove();},1600);}
function sweep(bar,cls){if(!bar)return;bar.classList.remove('m3up','m3dn');void bar.offsetWidth;bar.classList.add(cls);setTimeout(()=>bar.classList.remove(cls),1400);}
function once(el,cls,ms){if(!el)return;el.classList.remove(cls);void el.offsetWidth;el.classList.add(cls);setTimeout(()=>el.classList.remove(cls),ms||2200);}

// Count a text up to its final value (visual only; the DOM text is final before and after).
function countUp(el,tone){if(!el||el.children.length||!/\d/.test(el.textContent))return;const fin=el.textContent,dur=COUNT_MS[tone]||COUNT_MS.flat;let t0=null;
 const step=t=>{if(!el.isConnected)return;if(t0==null)t0=t;const k=(t-t0)/dur;if(k>=1){el.textContent=fin;return;}el.textContent=countText(fin,easeOut(k));requestAnimationFrame(step);};
 el.textContent=countText(fin,0);requestAnimationFrame(step);}

// Skeleton to content: the old skeleton is kept as an overlay and fades out while the real content fades in under it.
function ghostOf(m){if(reduceNow()||document.hidden)return null;if(!m.querySelector('[aria-busy="true"],.skel,.hsk,.ansk'))return null;
 const g=document.createElement('div');g.className='m3ghost';g.setAttribute('aria-hidden','true');g.innerHTML=m.innerHTML;return g;}
function place(m,g){if(!g)return;const cs=getComputedStyle(m);g.style.left=cs.paddingLeft;g.style.right=cs.paddingRight;g.style.top=cs.paddingTop;
 m.classList.add('m3x');m.appendChild(g);const a=anim(g,[{opacity:1},{opacity:0}],{duration:240,easing:EASE,fill:'forwards'});
 const done=()=>{g.remove();m.classList.remove('m3x');};if(a)a.onfinish=done;setTimeout(done,700);}
function before(m){const first=!!(typeof S!=='undefined'&&S.entered);return {first,ghost:m?ghostOf(m):null,hadSkel:!!(m&&m.querySelector('[aria-busy="true"],.skel,.hsk,.ansk'))};}

function staggerIn(m,els){const n=[];let i=0;els.forEach(e=>{const d=stagDelay(i);if(d==null)return;i++;e.classList.add('m3in');e.style.setProperty('--m3i',String(d)+'ms');n.push(e);});
 if(n.length){m.classList.add('m3st');setTimeout(()=>m.classList.remove('m3st'),900);}}

function afterGames(pre){const m=document.getElementById('main'),d=S.games;if(!m||!d||!m.querySelector('.gc'))return;
 const s=st(),reduce=reduceNow(),hidden=document.hidden,isStale=stale('N');flag(m,'N');
 const by=cardsByKey(m),games=d.games||[];
 // who won a finished card stays visible (a calm tint for a win, a dim for a loss): drawn from the data, so it survives every repaint
 games.forEach(g=>{const c=by[g.ticker||g.name];if(!c||!c.classList.contains('done'))return;const t=finalTone(g);if(t)c.classList.add(t==='win'?'m3won':'m3lost');});
 const now=Date.now(),snap=snapGames(games),prev=s.gp;
 const ev=diffGames(prev&&prev.snap,snap,{now,prevAt:prev&&prev.at,prevStale:prev&&prev.stale,reduce,hidden,stale:isStale});
 s.gp={snap,at:now,stale:isStale};
 for(const k of Object.keys(ev)){const c=by[k],e=ev[k];if(!c)continue;
  if(e.score){const me=c.querySelector('.gtr.me .pts'),opp=c.querySelector('.gtr.them .pts'),p=prev.snap[k].sc;
   if(e.score.me&&me){flip(me,String(p[0]));chip(me.parentNode,deltaText(e.score.me),true);}
   if(e.score.opp&&opp){flip(opp,String(p[1]));chip(opp.parentNode,deltaText(e.score.opp),false);}}
  if(e.chance){const b=c.querySelector('.gl .ch b'),bar=c.querySelector('.gbar i');if(b)chip(b.parentNode,deltaText(e.chance.d)+' pts',e.chance.dir==='up');
   if(e.chance.big&&bar)sweep(bar,e.chance.dir==='up'?'m3up':'m3dn');}
  if(e.final==='win')once(c,'m3win',2400);else if(e.final==='loss')once(c,'m3loss',1200);}
 // the win-chance bars ease from where they were (a bar is a scaleX, so only transform animates)
 const ok=!reduce&&!pre.first&&!pre.hadSkel;
 m.querySelectorAll('.gbar i[data-m3b]').forEach(el=>{const k=el.dataset.m3b,v=parseFloat(el.dataset.v),was=s.bars[k];s.bars[k]=v;
  const f=barFrom(was,v,ok);if(f==null)return;el.style.transition='none';el.style.transform='scaleX('+f+')';void el.offsetWidth;el.style.transition='';el.style.transform='scaleX('+v+')';});
 if((pre.first||pre.hadSkel)&&!reduce&&!hidden)staggerIn(m,[].slice.call(m.querySelectorAll('.gc')));
 place(m,pre.ghost);}

function afterResults(pre){const m=document.getElementById('main'),d=S.res;if(!m||!d||m.querySelector('[aria-busy="true"]')||!m.querySelector('.kpis,.pb,.plc,.hn'))return;
 const reduce=reduceNow(),hidden=document.hidden;
 if((pre.first||pre.hadSkel)&&!reduce&&!hidden){
  const tone=resultTone(d.pl);
  m.querySelectorAll('.kpis.rk .kpi b,.pbbig>b,.pbk b,.pbclv b').forEach(el=>countUp(el,el.closest('.kpi.rkh,.pbbig')?tone:'flat'));
  const hero=m.querySelector('.kpi.rkh'),pbb=m.querySelector('.pbbig>b');
  if(tone==='win'){if(hero)setTimeout(()=>once(hero,'m3pl',2400),COUNT_MS.win-200);if(pbb&&pbb.classList.contains('up'))setTimeout(()=>once(pbb,'m3pl',2400),COUNT_MS.win-200);}
  // the profit bars grow from their baseline, 30 ms apart; a win bar grows up, a loss bar grows down
  m.querySelectorAll('.plc rect.brc').forEach((r,i)=>{const dl=stagDelay(i);r.style.setProperty('--m3i',(dl==null?MAX_STAG*STAG_MS:dl)+'ms');r.classList.add('m3bar');r.style.transformOrigin=r.getAttribute('fill')==='var(--no)'?'50% 0':'50% 100%';});
  // history rows settle in 30 ms apart; a winning result number gets a thin green underline sweep, a loss just fades
  const rows=[].slice.call(m.querySelectorAll('.hn.rs'));rows.forEach(r=>{const b=r.querySelector('.res b');if(b)r.classList.add(b.classList.contains('up')?'m3w':'m3l');});
  staggerIn(m,rows);
  const grow=[].slice.call(m.querySelectorAll('.bars2 .tr2 i'));grow.forEach((e,i)=>{const dl=stagDelay(i);e.style.animationDelay=(dl==null?0:dl)+'ms';});}
 place(m,pre.ghost);}

// The game sheet: the scoreboard digits flip, a "+7" rises off the score, the win-chance number gets its move chip.
function afterSheet(r){const l=r&&r.leg,t=S.gameOpen,sh=document.getElementById('sheet');if(!l||!t||!sh)return;
 const s=st(),reduce=reduceNow(),hidden=document.hidden,isStale=stale('G'),sc=l.sc,ch=l.live!=null?l.live:l.chance;
 const live=l.state==='live'||l.on,now=Date.now();
 const cur={sc:sc&&num(sc.me)!=null&&num(sc.opp)!=null?[+sc.me,+sc.opp]:null,ch:num(ch),live:!!live&&!['probably_over','waiting','over'].includes(l.phase)};
 const prev=s.sp[t];s.sp[t]={snap:cur,at:now,stale:isStale};
 const first=!prev;
 if(first&&!reduce&&!hidden){const k=[].slice.call(sh.querySelectorAll('.dkpis>div'));staggerIn(sh,k);const cb=sh.querySelector('.chartbox');if(cb)once(cb,'m3chart',900);}
 if(!prev||!gate({reduce,hidden,stale:isStale,live:true})||prev.stale||(now-prev.at)>GAP_MS||now<prev.at||!prev.snap.live||!cur.live)return;
 const mv=scoreMove(prev.snap.sc,cur.sc);
 if(mv){const bs=sh.querySelectorAll('.board2 .tm2 b');
  if(mv.me&&bs[0]){flip(bs[0],String(prev.snap.sc[0]));chip(bs[0].parentNode,deltaText(mv.me),true);}
  if(mv.opp&&bs[1]){flip(bs[1],String(prev.snap.sc[1]));chip(bs[1].parentNode,deltaText(mv.opp),false);}}
 const cm=chanceMove(prev.snap.ch,cur.ch);
 if(cm&&cm.show){const b=sh.querySelector('.dkpis b[data-num^="gc:"]');if(b){chip(b.parentNode,deltaText(cm.d)+' pts',cm.dir==='up');if(cm.big)once(b,cm.dir==='up'?'m3big':'m3bigd',1400);}}}

function install(){
 if(typeof renderGames==='function'){const o=renderGames;renderGames=function(){let pre=null;try{pre=before(document.getElementById('main'));}catch(e){}
  const r=o.apply(this,arguments);if(pre){try{afterGames(pre);}catch(e){}}return r;};}
 if(typeof renderResults==='function'){const o=renderResults;renderResults=function(){let pre=null;try{pre=before(document.getElementById('main'));}catch(e){}
  const r=o.apply(this,arguments);if(pre){try{afterResults(pre);}catch(e){}}return r;};}
 if(typeof paintGame==='function'){const o=paintGame;paintGame=function(r){const x=o.apply(this,arguments);try{afterSheet(r);}catch(e){}return x;};}
 document.addEventListener('visibilitychange',()=>{try{const m=document.getElementById('main');if(m)flag(m,'N');}catch(e){}});
 setInterval(()=>{try{const m=document.getElementById('main');if(m&&S.view==='games')flag(m,'N');}catch(e){}},5000);}
try{if(typeof document!=='undefined'&&typeof renderGames==='function')install();}catch(e){}
return {gate,scoreMove,chanceMove,finalTone,snapGames,diffGames,barScale,barFrom,stagDelay,resultTone,countText,easeOut,deltaText,GAP_MS,STALE_S,SHOW_PTS,BIG_PTS,MAX_STAG,STAG_MS,COUNT_MS};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=Motion3;
