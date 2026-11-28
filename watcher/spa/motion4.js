/* Motion package M4: celebrations, pull-to-refresh honesty, the boot splash. Display only: nothing here reads or changes a
   price, bet, cap, Pause or rule; it fetches nothing. Transform/opacity only (CSS in motion4.css). A win gets the
   party, a loss stays sober (no confetti, no shake), and no motion implies fresh data while the feed is stale.
   The pure parts (confetti plan, tones, gates, splash timing) are exact-value tested by t_motion_m4.py under node. */
const Motion4=(()=>{
const PALETTE=['#3ecf8e','#ffd166','#4f8cff','#ff6b9a','#b48cff','#7ee0b5'];
const MAX_PIECES=40,MAX_TOTAL=64;                       // one burst holds at most 40; all layers on screen at most 64
// A small seeded random source so a burst is repeatable (and testable); the live caller seeds it with the clock.
function rng(seed){let a=(seed>>>0)||1;return()=>{a=(a+0x6D2B79F5)>>>0;let t=a;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return((t^(t>>>14))>>>0)/4294967296;};}
const r1=x=>Math.round(x*10)/10;
// The pieces of one confetti burst. x is the start column in vw, dx the sideways drift in px, rot the spin in degrees,
// delay/dur in seconds, shape 0 strip, 1 dot, 2 chip. Never more than MAX_PIECES.
function confettiPlan(n,seed,palette){const N=Math.max(0,Math.min(MAX_PIECES,Math.floor(+n||0))),R=rng(seed),P=(palette&&palette.length)?palette:PALETTE,out=[];
 for(let i=0;i<N;i++){out.push({x:r1(R()*100),dx:Math.round((R()-.5)*180),rot:Math.round(180+R()*540),delay:r1(R()*35)/100,dur:r1(160+R()*110)/100,
  w:6+Math.floor(R()*5),h:8+Math.floor(R()*7),color:P[i%P.length],shape:i%3});}
 return out;}
// How a closed bet feels: only a real profit celebrates; flat is a plain check; a loss is sober.
function soldTone(back,cost){const pl=(+back||0)-(+cost||0);return pl>0.004?'win':pl>=-0.004?'flat':'loss';}
// How many confetti pieces a moment gets: the big hit two bursts, a won combo one, a sold-at-a-profit a small one, a loss none.
function burstCounts(kind){return kind==='big'?[40,24]:kind==='win'?[32]:kind==='sold'?[18]:[];}
// Motion that is only decoration needs a visible page and no reduced-motion setting; motion that implies live data also
// needs a fresh feed.
function motionOk(o){o=o||{};if(o.reduce||o.hidden)return false;return o.live?!o.stale:true;}
// The pull-to-refresh check only means "fresh" when the load really worked; offline it ends on a calm grey dash.
function ptrEnd(o){o=o||{};return o.down?'stale':'fresh';}
// The splash: shown only on a cold start, held at least MIN ms so it reads as a mark and not a flicker, gone at MAX at the
// latest, never when reduced motion is on.
const SPLASH_MIN=450,SPLASH_MAX=1500;
function splashHide(elapsed,ready,reduce){if(reduce)return true;if(elapsed>=SPLASH_MAX)return true;return !!ready&&elapsed>=SPLASH_MIN;}
function splashDelay(elapsed,ready){return ready?Math.max(0,SPLASH_MIN-elapsed):Math.max(0,SPLASH_MAX-elapsed);}

const DOC=typeof document!=='undefined'&&document,reduce=()=>{try{return matchMedia('(prefers-reduced-motion: reduce)').matches;}catch(e){return false;}};
const down=()=>{try{return typeof netIsDown==='function'&&netIsDown();}catch(e){return false;}};
// Confetti: a burst per call, 64 pieces on screen at most, pieces fall on transform only, removed when done.
function confetti(n,opts){if(!DOC||!motionOk({reduce:reduce(),hidden:document.hidden}))return;
 const room=MAX_TOTAL-document.querySelectorAll('.confetti.v2 i').length;n=Math.min(n,room);if(n<=0)return;
 const box=document.createElement('div');box.className='confetti v2';
 confettiPlan(n,(opts&&opts.seed)||Date.now(),opts&&opts.palette).forEach(p=>{const s=document.createElement('i');
  s.className='cf'+p.shape;s.style.cssText=`left:${p.x}vw;width:${p.w}px;height:${p.shape===1?p.w:p.h}px;background:${p.color};--dx:${p.dx}px;--rot:${p.rot}deg;animation-delay:${p.delay}s;animation-duration:${p.dur}s`;box.appendChild(s);});
 document.body.appendChild(box);setTimeout(()=>box.remove(),3200);}
// Sparks from a point (the check, the payout): transform/opacity only, cleaned up after.
function sparks(host,n){if(!DOC||!host||!motionOk({reduce:reduce(),hidden:document.hidden}))return;
 const R=rng(Date.now()),box=document.createElement('span');box.className='m4sp';
 for(let i=0;i<n;i++){const a=(i/n)*Math.PI*2+R()*.4,d=46+R()*34,s=document.createElement('i');s.style.cssText=`--sx:${Math.round(Math.cos(a)*d)}px;--sy:${Math.round(Math.sin(a)*d)}px;animation-delay:${Math.round(R()*90)}ms;background:${PALETTE[i%PALETTE.length]}`;box.appendChild(s);}
 host.appendChild(box);setTimeout(()=>box.remove(),1400);}
// Boot splash: the cover is pure CSS on <body> so it paints on the very first frame; this only says when to lift it.
let t0=0,lifted=false,dueT=null;
function lift(){if(lifted||!DOC)return;lifted=true;const h=document.documentElement;h.classList.add('m4go');setTimeout(()=>h.classList.add('m4gone'),520);}
function ready(){if(!DOC||lifted)return;const el=(typeof performance!=='undefined'?performance.now():0)-t0;
 if(splashHide(el,true,reduce()))lift();else{clearTimeout(dueT);dueT=setTimeout(lift,splashDelay(el,true));}}
function boot(){if(!DOC)return;t0=0;if(reduce()){lift();return;}dueT=setTimeout(lift,splashDelay(0,false));}
// Pull to refresh: the ring and spin are real (they follow the finger and a real fetch). When it ends while the Mac link
// is down, the check becomes a grey dash so it never claims fresh data.
function watchPtr(){if(!DOC||typeof MutationObserver==='undefined')return;let seen=null;
 const hook=el=>{if(seen===el)return;seen=el;new MutationObserver(()=>{const d=el.classList.contains('done');
  if(d&&ptrEnd({down:down()})==='stale')el.classList.add('stale');else if(!d)el.classList.remove('stale');}).observe(el,{attributes:true,attributeFilter:['class']});};
 const f=document.getElementById('ptr');if(f)hook(f);
 new MutationObserver(()=>{const e=document.getElementById('ptr');if(e)hook(e);}).observe(document.body,{childList:true});}
function install(){if(!DOC)return;boot();watchPtr();
 document.addEventListener('visibilitychange',()=>document.documentElement.classList.toggle('m4hide',document.hidden));}
try{install();}catch(e){}
return {confettiPlan,soldTone,burstCounts,motionOk,ptrEnd,splashHide,splashDelay,rng,confetti,sparks,ready,MAX_PIECES,MAX_TOTAL,PALETTE,SPLASH_MIN,SPLASH_MAX};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=Motion4;
