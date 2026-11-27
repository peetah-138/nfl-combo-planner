/* A newer version is running on the Mac (GitHub #150). The Home Screen app can keep an old page after an update, so the
   page compares the version the Mac says it is running (every live/games/game answer carries it, `fresh.ver`, and any view
   asks /app/api/ver on the Mac's tick, every 12 s and when the app comes back) with the one baked into the page when it
   loaded (PAGE_VER). Different + idle = reload by itself (quiet fade, "Updated to" toast after); busy = a small "New version
   ready: tap to refresh" pill. Never reloads in the middle of a quote, buy or sell. Display only: nothing here moves money. */
const VER_IDLE_MS=1500,VER_TICK_MS=1000,VER_HOLD_MS=15000;
function verOk(v){return typeof v==='string'&&/^\d[\w.\-]*$/.test(v);}
function verDiffers(){return verOk(PAGE_VER)&&verOk(S.srvVer)&&S.srvVer!==PAGE_VER;}
function verSeen(v){if(!verOk(v))return;S.srvVer=v;if(verDiffers()){verTickOn();verCheck();}else verPill(false);}
/* Read-only version source (same sign-in as every answer; no money, no app lock). */
function verPoll(){const n=Date.now();if(S.verPolling||n-(S.verPollAt||0)<4000)return;S.verPollAt=n;S.verPolling=true;
 api('/app/api/ver').then(r=>{if(r&&r.ver)verSeen(r.ver);}).catch(()=>{}).finally(()=>{S.verPolling=false;});}
setInterval(()=>{if(!document.hidden)verPoll();},12000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)verPoll();});
let verFingers=0,verLastAct=Date.now();
const verAct=()=>{verLastAct=Date.now();};
addEventListener('pointerdown',()=>{verFingers++;verAct();},{capture:true,passive:true});
['pointerup','pointercancel'].forEach(t=>addEventListener(t,()=>{verFingers=Math.max(0,verFingers-1);verAct();},{capture:true,passive:true}));
addEventListener('touchstart',e=>{verFingers=Math.max(verFingers,e.touches.length);verAct();},{capture:true,passive:true});
addEventListener('touchmove',verAct,{capture:true,passive:true});
addEventListener('touchend',e=>{verFingers=e.touches.length;verAct();},{capture:true,passive:true});
addEventListener('touchcancel',()=>{verFingers=0;verAct();},{capture:true,passive:true});
['scroll','wheel','keydown'].forEach(t=>addEventListener(t,verAct,{capture:true,passive:true}));
function verBusy(){   // anything that must not be pulled out from under the person
 try{
  const now=Date.now();
  if(verFingers>0||S.scrub)return true;
  const m=$('#modal');if(m&&m.classList.contains('on'))return true;
  if(S.gameOpen||S.comboOpen||S.ideaOpen)return true;
  if(S.buying||S.pSend||(S.potq&&S.potq.sending))return true;
  if((S.inflight||0)>0)return true;                         // any tap's request still on its way
  if((S.verHold||0)>now)return true;                        // a buy/approve/hedge/pot result landed: let the message be read
  if(Object.values(S.busy||{}).some(Boolean))return true;
  const young=o=>Object.values(o||{}).some(e=>e&&(+e.t||0)>now-60000);   // older entries are leftovers of a rebuilt card
  if(young(S.qpend)||young(S.bpend))return true;
  if(Object.values(S.fpend||{}).some(Boolean))return true;
  const sec=now/1000;       // a price on screen that can still be bought
  if(Object.values(S.quotes||{}).some(q=>q&&!q.x&&sec-q.at<25)||(S.custom&&S.custom.offer&&!S.custom.offer.x&&sec-S.custom.offer.at<25))return true;
  if(Object.values(S.ideaq||{}).some(q=>q&&sec-q.at<25))return true;
  const t=$('#toast');if(t&&t.classList.contains('on')&&(t.classList.contains('bad')||/check/i.test(t.textContent||'')))return true;   // a refusal or "check" message is being read
  const a=document.activeElement;if(a&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)&&a.type!=='checkbox')return true;
  if(document.querySelector('[data-sure="1"],[data-sure="sent"]'))return true;   // an Approve/Add that is armed or on its way
 }catch(e){return true;}   // can't tell = not idle
 return false;}
const VER_DOT_MS=20000;
function verPill(on){let el=document.getElementById('verpill');
 if(!on){if(el)el.classList.remove('on');clearTimeout(S.verDotT);S.verDotT=0;return;}
 if(S.verHideV===S.srvVer)return;   // the x was tapped for this version: stay quiet (the Settings row still says so)
 if(!el){el=document.createElement('button');el.id='verpill';el.className='verpill';el.type='button';el.setAttribute('aria-label','New version ready. Tap to refresh.');el.onclick=verTap;
  el.innerHTML='<i></i><span>New version ready: tap to refresh</span><span class="vx" role="button" aria-label="Dismiss" onclick="verHide(event)">×</span>';document.body.appendChild(el);void el.offsetWidth;}
 el.classList.add('on');
 if(!S.verDotT&&!el.classList.contains('dot'))S.verDotT=setTimeout(()=>{el.classList.add('dot');},VER_DOT_MS);}
function verHide(e){if(e){e.stopPropagation();e.preventDefault();}hap('light');S.verHideV=S.srvVer;verPill(false);}
function verTap(){hap('light');verReload();}   // the tick comes from the real tap (iOS 27 ignores one fired after an await or a timer)
/* The "already reloaded for this version" note lives in sessionStorage AND localStorage; read back to be sure it stuck. */
function verMark(v){const o=JSON.stringify({v,at:Date.now()});let n=0;
 try{sessionStorage.setItem('cw_vrl',o);if(sessionStorage.getItem('cw_vrl')===o)n++;}catch(e){}
 try{localStorage.setItem('cw_vrl',o);if(localStorage.getItem('cw_vrl')===o)n++;}catch(e){}
 return n>0;}
/* Can this browser remember? If neither store takes a write, an automatic reload could loop: the pill only. */
function verCanMark(){let n=0;for(const st of ['sessionStorage','localStorage']){try{const k=window[st];k.setItem('cw_vrt','1');if(k.getItem('cw_vrt')==='1')n++;k.removeItem('cw_vrt');}catch(e){}}return n>0;}
function verLooped(){const hit=k=>{try{const o=JSON.parse(localStorage.getItem(k)||'null');return !!(o&&o.v===S.srvVer&&Date.now()-o.at<300000);}catch(e){return false;}};
 try{const o=JSON.parse(sessionStorage.getItem('cw_vrl')||'null');if(o&&o.v===S.srvVer&&Date.now()-o.at<300000)return true;}catch(e){}
 return hit('cw_vrl');}
function verReload(){const v=S.srvVer||'';verMark(v);
 try{localStorage.setItem('cw_upd',JSON.stringify({v,at:Date.now()}));}catch(e){}
 const quiet=!matchMedia('(prefers-reduced-motion:reduce)').matches;
 if(quiet)document.body.classList.add('verfade');
 setTimeout(()=>location.reload(),quiet?260:0);}
function verCheck(){if(!verDiffers())return;
 if(verBusy()){S.verIdleAt=0;verPill(true);return;}
 if(!S.verIdleAt)S.verIdleAt=Date.now();
 if(Date.now()-S.verIdleAt<VER_IDLE_MS||Date.now()-verLastAct<VER_IDLE_MS)return;   // quiet for a moment since the last touch, scroll or key
 if(verLooped()||!verCanMark()){verPill(true);return;}   // reloaded already, or can't remember we did: no loop, the pill stays
 if(S.verGo)return;S.verGo=true;verReload();}
function verTickOn(){if(S.verT)return;S.verT=setInterval(()=>{if(!verDiffers()){clearInterval(S.verT);S.verT=0;S.verIdleAt=0;verPill(false);return;}verCheck();},VER_TICK_MS);}
/* After a reload for an update: say so once. */
function verWelcome(){try{const o=JSON.parse(localStorage.getItem('cw_upd')||'null');localStorage.removeItem('cw_upd');
 if(o&&verOk(o.v)&&o.v===PAGE_VER&&Date.now()-o.at<120000)setTimeout(()=>toast('Updated to '+o.v,4000,'good'),600);}catch(e){}}
function verRow(v){const run=verOk(v)?v:(verOk(S.srvVer)?S.srvVer:'');if(!run)return '';
 const stale=verOk(PAGE_VER)&&PAGE_VER!==run;
 return `<div class="srow" id="verrow"><div class="l"><b>${stale?'A newer version is ready':'Up to date'}</b><small>App version ${esc(run)}${stale?' · this page is on '+esc(PAGE_VER):''}</small></div>${stale?'<button class="btn ghost" onclick="verTap()">Reload</button>':''}</div>`;}
function verFadeIn(){try{const o=JSON.parse(localStorage.getItem('cw_upd')||'null');
 if(o&&verOk(o.v)&&o.v===PAGE_VER&&Date.now()-o.at<120000&&!matchMedia('(prefers-reduced-motion:reduce)').matches)document.body.classList.add('verin');}catch(e){}}
verFadeIn();verWelcome();
