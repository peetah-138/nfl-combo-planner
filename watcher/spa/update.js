/* A newer version is running on the Mac (GitHub #150). The Home Screen app can keep an old page after an update, so the
   page compares the version the Mac says it is running (every live/games/game answer carries it, `fresh.ver`) with the
   one baked into the page when it loaded (PAGE_VER). When they differ: idle = reload by itself (quiet fade, "Updated to"
   toast after); busy = a small "New version ready: tap to refresh" pill. Never reloads in the middle of a quote, buy or
   sell, a sheet, a finger on the screen, a scrub or a field being typed in. Display only: nothing here moves money. */
const VER_IDLE_MS=1500,VER_TICK_MS=1000;
function verOk(v){return typeof v==='string'&&/^\d[\w.\-]*$/.test(v);}
function verDiffers(){return verOk(PAGE_VER)&&verOk(S.srvVer)&&S.srvVer!==PAGE_VER;}
function verSeen(v){if(!verOk(v))return;S.srvVer=v;if(verDiffers()){verTickOn();verCheck();}else verPill(false);}
let verFingers=0;
addEventListener('pointerdown',()=>{verFingers++;},{capture:true,passive:true});
['pointerup','pointercancel'].forEach(t=>addEventListener(t,()=>{verFingers=Math.max(0,verFingers-1);},{capture:true,passive:true}));
addEventListener('touchstart',e=>{verFingers=Math.max(verFingers,e.touches.length);},{capture:true,passive:true});
addEventListener('touchend',e=>{verFingers=e.touches.length;},{capture:true,passive:true});
addEventListener('touchcancel',()=>{verFingers=0;},{capture:true,passive:true});
function verBusy(){   // anything that must not be pulled out from under the person
 try{
  if(verFingers>0||S.scrub)return true;
  const m=$('#modal');if(m&&m.classList.contains('on'))return true;
  if(S.gameOpen||S.comboOpen||S.ideaOpen)return true;
  if(S.buying||S.pSend||(S.potq&&S.potq.sending))return true;
  if(Object.values(S.busy||{}).some(Boolean))return true;
  if(Object.keys(S.qpend||{}).length||Object.keys(S.bpend||{}).length)return true;
  if(Object.values(S.fpend||{}).some(Boolean))return true;
  const now=Date.now()/1000;   // a price on screen that can still be bought
  if(Object.values(S.quotes||{}).some(q=>q&&!q.x&&now-q.at<25)||(S.custom&&S.custom.offer&&!S.custom.offer.x&&now-S.custom.offer.at<25))return true;
  const a=document.activeElement;if(a&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)&&a.type!=='checkbox')return true;
  if(document.querySelector('[data-sure="1"],[data-sure="sent"]'))return true;   // an Approve/Add that is armed or on its way
 }catch(e){return true;}   // can't tell = not idle
 return false;}
function verPill(on){let el=document.getElementById('verpill');
 if(!on){if(el){el.classList.remove('on');}return;}
 if(!el){el=document.createElement('button');el.id='verpill';el.className='verpill';el.type='button';el.setAttribute('role','status');el.onclick=verTap;
  el.innerHTML='<i></i><span>New version ready: tap to refresh</span>';document.body.appendChild(el);void el.offsetWidth;}
 el.classList.add('on');}
function verTap(){hap('light');verReload(true);}   // the tick comes from the real tap (iOS 27 ignores one fired after an await or a timer)
function verReload(forced){const v=S.srvVer||'';
 try{localStorage.setItem('cw_upd',JSON.stringify({v,at:Date.now()}));sessionStorage.setItem('cw_vrl',JSON.stringify({v,at:Date.now()}));}catch(e){}
 const quiet=!matchMedia('(prefers-reduced-motion:reduce)').matches;
 if(quiet)document.body.classList.add('verfade');
 setTimeout(()=>location.reload(),quiet?260:0);}
function verLooped(){try{const o=JSON.parse(sessionStorage.getItem('cw_vrl')||'null');return !!(o&&o.v===S.srvVer&&Date.now()-o.at<300000);}catch(e){return false;}}
function verCheck(){if(!verDiffers())return;
 if(verBusy()){S.verIdleAt=0;verPill(true);return;}
 if(!S.verIdleAt)S.verIdleAt=Date.now();
 if(Date.now()-S.verIdleAt<VER_IDLE_MS){return;}   // quiet for a moment first, so a tap that is just starting isn't caught
 if(verLooped()){verPill(true);return;}            // we already reloaded for this version and still differ: no loop, the pill stays
 if(S.verGo)return;S.verGo=true;verReload(false);}
function verTickOn(){if(S.verT)return;S.verT=setInterval(()=>{if(!verDiffers()){clearInterval(S.verT);S.verT=0;S.verIdleAt=0;verPill(false);return;}verCheck();},VER_TICK_MS);}
/* After a reload for an update: say so once. */
function verWelcome(){try{const o=JSON.parse(localStorage.getItem('cw_upd')||'null');localStorage.removeItem('cw_upd');
 if(o&&verOk(o.v)&&o.v===PAGE_VER&&Date.now()-o.at<120000)setTimeout(()=>toast('Updated to '+o.v,4000,'good'),600);}catch(e){}}
function verRow(v){const run=verOk(v)?v:(verOk(S.srvVer)?S.srvVer:'');if(!run)return '';
 const pg=!verOk(PAGE_VER)||PAGE_VER===run?'page: same':'page: '+esc(PAGE_VER)+' · <span class="down">reload to update</span>';
 return `<div class="srow" id="verrow"><div class="l"><b>App version</b><small>${esc(run)} (${pg})</small></div></div>`;}
verWelcome();
