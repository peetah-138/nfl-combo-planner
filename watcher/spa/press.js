/* Button feedback (visual only; Pete runs with haptics off, so the screen has to say what is happening).
   Every button that moves money or state goes through the same four looks:
     1. pressed   instant, pure CSS (:active, and .prs from common.js's press feedback): darker, a touch smaller
     2. pending   fbPend(): spinner + "Buying…", disabled, aria-busy, width locked so nothing around it jumps (#456)
     3. result    fbEnd(): green check + the amount, or red "Didn't go through" (the reason sits right under it),
                  or amber "Checking with Kalshi…" when the answer is unknown
     4. never a silent revert: a pending button always ends in one of the three results above.
   NOTHING here sends, retries or changes an order. The helpers only paint; every request still goes through the
   caller's own guard (S.buying, S.ibuy, s.sending, S.pSend...) and its own body. An unknown outcome (a lost reply, a
   timeout, a "may or may not" message) is never shown as success and never offers a retry (rule 8). */
function fbSay(m){let e=document.getElementById('fbsr');if(!e){e=document.createElement('div');e.id='fbsr';e.className='sr';e.setAttribute('role','status');e.setAttribute('aria-live','polite');document.body.appendChild(e);}
 e.textContent='';setTimeout(()=>{e.textContent=String(m||'');},30);}
/* pending: returns false (and does nothing) if the button is already pending or gone, so a second tap is a no-op */
function fbPend(b,label,say){if(!b||!b.isConnected||b.getAttribute('aria-busy')==='true')return false;
 if(b._fbOld==null)b._fbOld=b.innerHTML;const w=b.offsetWidth;if(w&&b._fbW==null){b._fbW=b.style.minWidth||'';b.style.minWidth=w+'px';}
 b.classList.remove('fb-ok','fb-bad','fb-chk','st-ok','st-bad');b.classList.add('fb-pend');b.disabled=true;b.setAttribute('aria-busy','true');b.setAttribute('aria-disabled','true');
 b.innerHTML='<span class="spin" aria-hidden="true"></span> <span>'+esc(label)+'</span>';fbSay(say||String(label).replace(/….*$/,'')+'. Waiting for Kalshi.');return true;}
/* result. kind: 'ok' (green check), 'bad' (red cross, button comes back as the retry after `ms`), 'chk' (amber, unknown:
   stays disabled for good: nothing may be sent again until Pete has looked at Live / Kalshi). */
function fbEnd(b,kind,label,ms){if(!b||!b.isConnected)return;const old=b._fbOld;
 b.classList.remove('fb-pend','fb-ok','fb-bad','fb-chk');b.removeAttribute('aria-busy');b.classList.add('fb-'+kind);
 b.innerHTML='<i aria-hidden="true">'+(kind==='ok'?'✓':kind==='bad'?'✕':'…')+'</i> <span>'+esc(label)+'</span>';
 b.disabled=kind!=='bad';b.setAttribute('aria-disabled',kind!=='bad'?'true':'false');b.dataset.fb=kind;fbSay(label);
 hap(kind==='ok'?'success':kind==='bad'?'error':'warning');
 if(kind==='bad'){clearTimeout(b._fbT);b._fbT=setTimeout(()=>fbIdle(b),ms||8000);}}
function fbIdle(b){if(!b||!b.isConnected)return;b.classList.remove('fb-pend','fb-ok','fb-bad','fb-chk');b.removeAttribute('aria-busy');b.removeAttribute('aria-disabled');b.disabled=false;delete b.dataset.fb;
 if(b._fbOld!=null){b.innerHTML=b._fbOld;b._fbOld=null;}if(b._fbW!=null){b.style.minWidth=b._fbW;b._fbW=null;}}
/* what a Mac answer to Cash out / Place hedge means. The Mac says ok:true for anything that did not error, including
   "The hedge wasn't placed" and "may or may not have gone through", so the words decide: only a message that starts with
   the green check is a success; a warning or a lost reply is "unknown"; anything else is a refusal. */
function fbKind(r){if(!r)return 'chk';const m=String(r.msg||'');
 if(r.lost||r.check||/^⚠️|may or may not|no clear answer|^That didn't work/i.test(m))return 'chk';   // "That didn't work: <error>" can mean the outcome is unknown
 if(r.ok&&/^✅/.test(m))return 'ok';
 if(/offer expired|isn't live any more|wasn't placed|nothing was (bought|sold)|isn't allowing|no one was selling|didn't take/i.test(m))return 'bad';   // only the Mac's own plain refusals are red; any other ok:false falls through to Check Kalshi
 return 'chk';}   // ok without the check mark and not a known refusal: not confirmed, so never green
/* a plain-words line under a button (red for a refusal, amber for unknown); role=status so it is read out once */
function fbNote(b,msg,tone){document.querySelectorAll('.fbnote').forEach(e=>e.remove());if(!b||!b.isConnected)return;const d=document.createElement('div');d.className='fbnote'+(tone==='chk'?' chk':'');
 d.setAttribute('role','status');d.innerHTML='<i aria-hidden="true">'+(tone==='chk'?'…':'✕')+'</i><span>'+esc(msg)+'</span>';(b.parentNode||b).insertAdjacentElement('afterend',d);}
/* one money request per ticker at a time, even if the sheet is closed and reopened from the Live card while it is pending */
function fbFlying(t){return !!(S.fbFly&&S.fbFly[t]);}
function fbFly(t,on){S.fbFly=S.fbFly||{};if(on)S.fbFly[t]=1;else delete S.fbFly[t];}
function fbBusyToast(){toast('That one is still going through. Check Live in a moment.',4000);}
/* the button was on a sheet that has since closed: say a refusal in a toast instead of painting a dead button */
function fbRefused(b,msg){if(b&&b.isConnected&&!(b.closest('#modal')&&!b.closest('#modal.on')))return false;   // gone: removed, or its sheet was closed
 toast(msg,7000,'bad');return true;}
const FB_LOST='Couldn\'t reach your Mac, so this may or may not have gone through. Check Live before trying again.';
/* Cash out (the sheet from sell()): same request as before, {a:'go',t}; one tap at a time */
async function fbSell(t){if(fbFlying(t)){fbBusyToast();return;}const b=$('#sellgo');if(!b||!fbPend(b,'Selling… confirming with Kalshi'))return;hap();fbFly(t,1);
 const c=((S.live&&S.live.combos)||[]).find(x=>x.t===t)||{};let r;
 try{r=await api('/app/api/act',{a:'go',t});}catch(e){r={ok:false,lost:true,msg:FB_LOST.replace('gone through','sold')};}finally{fbFly(t,0);}
 const k=fbKind(r),msg=r&&r.msg||'';
 if(k==='ok'){fbEnd(b,'ok','Sold'+(r.offer!=null?' · '+money(r.offer):c.offer!=null?' · '+money(c.offer):''));closeModal();S.momSeen=S.momSeen||{};S.momSeen['s:'+t]=1;
  setTimeout(()=>soldSheet({label:momName(c),back:r.offer!=null?r.offer:c.offer,cost:c.cost}),360);}
 else if(k==='chk'){okSheet('Check Kalshi',null,(msg||FB_LOST).replace(/^⚠️\s*/,'')+(r.lost||r.check?'':' Check Live to see whether it sold.'),true);}
 else if(!fbRefused(b,msg||'Kalshi didn\'t take it, so nothing was sold.')){fbEnd(b,'bad','Didn\'t go through · tap for a new offer',20000);fbNote(b,msg||'Kalshi didn\'t take it, so nothing was sold.');
  /* the retry re-enters the normal flow: a fresh offer, never the old request */
  b.onclick=()=>{closeModal();ask(t);};b.dataset.t=t;b._fbOld='Get a new offer';}
 load('live',true);}
/* Place hedge: same request as before, {a:'hedgego',t}; the sheet stays up until the answer is in */
async function fbHedge(b){const t=b&&b.dataset.t;if(!t)return;if(fbFlying(t)){fbBusyToast();return;}if(!fbPend(b,'Placing hedge… confirming with Kalshi'))return;hap();fbFly(t,1);let r;
 try{r=await api('/app/api/act',{a:'hedgego',t});}catch(e){r={ok:false,lost:true,msg:FB_LOST.replace('gone through','been placed')};}finally{fbFly(t,0);}
 const k=fbKind(r),msg=r&&r.msg||'';
 if(k==='ok'){fbEnd(b,'ok','Hedged');okSheet('Hedged',null,msg.replace(/^✅\s*/,''));}
 else if(k==='chk'){okSheet('Check Kalshi',null,(msg||FB_LOST).replace(/^⚠️\s*/,'')+(r.lost||r.check?'':' Check Live to see whether it went through.'),true);}
 else if(!fbRefused(b,msg||'The hedge wasn\'t placed. Nothing was bought.')){fbEnd(b,'bad','Didn\'t go through · tap to look again',20000);fbNote(b,msg||'The hedge wasn\'t placed. Nothing was bought.');
  b.onclick=()=>{closeModal();hedge(t);};b._fbOld='Look at the hedge again';}
 load('live',true);}
