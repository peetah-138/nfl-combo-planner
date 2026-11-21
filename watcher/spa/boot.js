// ---------------- refresh loop
window.__inapp=function(){S.inapp=true;hswSync();if(S.view==='settings')renderSettings();};
function ideaFromHash(open){if(!location.hash.startsWith('#s='))return;S.hl=location.hash.slice(3);S.view='live';history.replaceState(null,'',location.pathname);if(open){chrome();load('live',true);}setTimeout(()=>{if(typeof ideaReveal==='function')ideaReveal(S.hl);const e=document.getElementById('idea-'+S.hl);if(e)e.scrollIntoView({behavior:'smooth',block:'center'});},open?1200:2500);}
ideaFromHash(false);
addEventListener('hashchange',()=>ideaFromHash(true));
chrome();render();load(S.view);connect();loadRecap();
setTimeout(async()=>{try{if(location.protocol!=='https:'||!window.PublicKeyCredential||S.inapp||localStorage.getItem('cw_fid_asked'))return;
 if(!(await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()))return;await fidLoad();
 if((S.fid.keys||[]).some(k=>k.rp===location.hostname))return;localStorage.setItem('cw_fid_asked','1');
 modal(`<h3>Unlock with Face ID?</h3><p>Skip the passcode next time. Your face never leaves your phone; the Mac only keeps a key that can't be used anywhere else.</p>
  <div class="row"><button class="btn" onclick="closeModal()">Not now</button><button class="btn acc" onclick="closeModal();fidOn()">Turn on Face ID</button></div>`);}catch(e){}},2500);
setInterval(()=>{if(document.hidden)return;if(S.live_ok&&Date.now()-(S.lastLoad||0)<30000)return;if(['live','games'].includes(S.view)&&!$('#modal').classList.contains('on')){S.lastLoad=Date.now();load(S.view);}},12000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&S.view==='live')load('live');});
