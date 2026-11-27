/* Settings › This Mac › "Let the dev Mac read logs" (issue #377, docs/LOG_ACCESS.md). Only on the Mac itself.
   Turning it on makes a new read-only code, shown once here; the Mac keeps only a fingerprint of it. Turning it off
   (or making a new code) stops the old one at once. The dev Mac can read the activity log and the saved data this Mac collects, with passwords
   and keys hidden: no buying, selling, settings or keys. */
function logRow(mac){const l=mac.logs||{};const ago=t=>{const s=Math.max(0,Math.round(Date.now()/1000-t));return s<90?'just now':s<5400?Math.round(s/60)+' min ago':s<172800?Math.round(s/3600)+' hr ago':Math.round(s/86400)+' days ago';};
 const sub=l.on?`On${l.read?' · last read '+ago(l.read):' · not read yet'}. The dev Mac can read this Mac's activity log and the data it saves, with passwords and keys hidden. It can't buy, sell or change anything.`
  :'Off. When on, the dev Mac can read this Mac\'s activity log and the data it saves, over Tailscale, with passwords and keys hidden. It can\'t buy, sell or change anything.';
 return `<label class="srow" id="logrow"><div class="l"><b>Let the dev Mac read logs</b><small>${sub}</small></div><input type="checkbox" switch class="tg" aria-label="Let the dev Mac read logs" ${l.on?'checked':''} onchange="logAccess(this.checked,this)"></label>${l.on?`<div class="srow"><div class="l"><small>Lost the code, or want to cut off the old one?</small></div><button class="btn" id="lanew" onclick="logAccess(true,this,1)">New code</button></div>`:''}`;}
/* (#378) the two "are you sure" questions are the app's own bottom sheet (modal), not the browser's confirm(). */
function logAccess(on,el,again){
 if(!on){el.checked=true;modal(`<h3>Stop the dev Mac reading logs?</h3><p>Its code stops working now. You can turn it back on any time and get a new code.</p><div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn acc" onclick="closeModal();logAccessRun(false,0)">Stop it</button></div>`);return;}
 if(again){modal(`<h3>Make a new code?</h3><p>The old code stops working now. You will see the new one once, so be ready to copy it.</p><div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn acc" onclick="closeModal();logAccessRun(true,1)">Make a new code</button></div>`);return;}
 logAccessRun(true,0);}
async function logAccessRun(on,again){const el=again?document.querySelector('#lanew'):document.querySelector('#logrow input');if(!el)return;
 let r;el.disabled=true;                     /* no double tap: two quick taps would make two codes */
 try{r=await api('/app/mac',{a:'logaccess',on});}catch(e){toast('Couldn\'t change it. Try again.');load('settings');return;}finally{el.disabled=false;}
 if(!r||!r.ok){toast((r&&r.msg)||'Couldn\'t change it. Try again.');load('settings');return;}
 if(!on){toast(r.msg);load('settings');return;}
 modal(`<h3>Code for the dev Mac</h3><p>Copy this now: it is shown only once. Give it to Claude on the dev Mac and Claude will set it up. It only lets the dev Mac read the activity log and saved data.</p>
 <div class="code" id="lc">${esc(r.token||'')}</div>${r.url?`<p class="m" style="font-size:12.5px">Address (give Claude this too):</p><div class="code" id="lu">${esc(r.url)}</div>`:'<p class="m" style="font-size:12.5px">Tailscale isn\'t signed in on this Mac, so the dev Mac can\'t reach it yet.</p>'}
 ${r.url?`<button class="btn acc" id="lsetup" style="width:100%;min-height:44px;margin-top:12px" onclick="logCopySetup()">Copy setup command</button><p class="m" style="font-size:12.5px">Or tap this, then paste it once on the dev Mac: it saves both for you. Don't paste it anywhere else.</p>`:''}
 <div class="row" style="margin-top:12px"><button class="btn" onclick="logDone()">Done</button>${r.url?`<button class="btn" onclick="logCopy('#lu','Address')">Copy address</button>`:''}<button class="btn${r.url?'':' acc'}" onclick="logCopy('#lc','Code')">Copy code</button></div>`);}
/* (#379) one Terminal line that stores the address and the code in the dev Mac's keychain (the names tools/read_prod_logs.py reads).
   It is built here from what is on screen and goes only to the clipboard: never logged, sent or kept. The leading space keeps it out of shell history where that is on. */
function logShq(v){return "'"+String(v).replace(/'/g,"'\\''")+"'";}
function logSetupCmd(url,code){const add=(svc,v)=>'security add-generic-password -U -a "$USER" -s '+svc+' -w '+logShq(v);
 return ' '+add('nfl-combo-logs-url',url)+' && '+add('nfl-combo-logs-token',code)+' && echo "Saved. Try: python3 tools/read_prod_logs.py --problems --since 1h"';}
function logCopySetup(){const u=$('#lu'),c=$('#lc');if(!u||!c)return;const cmd=logSetupCmd(u.textContent,c.textContent);
 navigator.clipboard.writeText(cmd).then(()=>toast('Setup command copied'),()=>toast('Couldn\'t copy: use Copy address and Copy code instead'));}
function logCopy(sel,what){navigator.clipboard.writeText($(sel).textContent).then(()=>toast(what+' copied'),()=>toast('Couldn\'t copy: tap the '+what.toLowerCase()+' and copy it by hand'));}
function logDone(){const c=$('#lc');if(c)c.textContent='';closeModal();load('settings');}   /* the code doesn't linger in the page */
