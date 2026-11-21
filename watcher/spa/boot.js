// ---------------- refresh loop
window.__inapp=function(){S.inapp=true;hswSync();if(S.view==='settings')renderSettings();};
function ideaFromHash(open){if(!location.hash.startsWith('#s='))return;S.hl=location.hash.slice(3);S.view='live';history.replaceState(null,'',location.pathname);if(open){chrome();load('live',true);}setTimeout(()=>{if(typeof ideaReveal==='function')ideaReveal(S.hl);const e=document.getElementById('idea-'+S.hl);if(e)e.scrollIntoView({behavior:'smooth',block:'center'});},open?1200:2500);}
/* A notification or toast about one combo opens that combo's page (#210): its link is '/#c=<ticker>'. The page
   opens Live, waits for the Live data, and pushes the combo only when it is one of yours; an unknown, old or
   malformed one just leaves you on Live. */
function comboOk(t){return typeof t==='string'&&/^[A-Za-z0-9._-]{3,120}$/.test(t);}
async function comboFromHash(open){if(!location.hash.startsWith('#c='))return;let t='';try{t=decodeURIComponent(location.hash.slice(3));}catch(e){}
 S.view='live';history.replaceState(null,'',location.pathname);if(open){chrome();render();}
 if(!comboOk(t)){if(open)load('live',true);return;}
 if(open)await load('live',true);
 for(let i=0;i<40&&!(S.live&&S.liveNet);i++)await new Promise(r=>setTimeout(r,250));   // first start: wait for Live's own load
 if(S.view==='live'&&((S.live&&S.live.combos)||[]).some(c=>c.t===t))openCombo(t);}
ideaFromHash(false);comboFromHash(false);
addEventListener('hashchange',()=>{ideaFromHash(true);comboFromHash(true);});
chrome();render();load(S.view);connect();loadRecap();
setTimeout(async()=>{try{if(location.protocol!=='https:'||!window.PublicKeyCredential||S.inapp||localStorage.getItem('cw_fid_asked'))return;
 if(!(await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()))return;await fidLoad();
 if((S.fid.keys||[]).some(k=>k.rp===location.hostname))return;localStorage.setItem('cw_fid_asked','1');
 modal(`<h3>Unlock with Face ID?</h3><p>Skip the passcode next time. Your face never leaves your phone; the Mac only keeps a key that can't be used anywhere else.</p>
  <div class="row"><button class="btn" onclick="closeModal()">Not now</button><button class="btn acc" onclick="closeModal();fidOn()">Turn on Face ID</button></div>`);}catch(e){}},2500);
setInterval(()=>{if(document.hidden)return;if(S.live_ok&&Date.now()-(S.lastLoad||0)<30000)return;if(['live','games'].includes(S.view)&&!$('#modal').classList.contains('on')){S.lastLoad=Date.now();load(S.view);}},12000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&S.view==='live')load('live');});
