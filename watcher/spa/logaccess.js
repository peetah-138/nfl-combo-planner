/* Settings › This Mac › "Let the dev Mac read logs" (issue #377, docs/LOG_ACCESS.md). Only on the Mac itself.
   Turning it on makes a new read-only code, shown once here; the Mac keeps only a fingerprint of it. Turning it off
   (or making a new code) stops the old one at once. The dev Mac can read the activity log and the saved data this Mac collects, with passwords
   and keys hidden: no buying, selling, settings or keys. */
function logRow(mac){const l=mac.logs||{};const ago=t=>{const s=Math.max(0,Math.round(Date.now()/1000-t));return s<90?'just now':s<5400?Math.round(s/60)+' min ago':s<172800?Math.round(s/3600)+' hr ago':Math.round(s/86400)+' days ago';};
 const sub=l.on?`On${l.read?' · last read '+ago(l.read):' · not read yet'}. The dev Mac can read this Mac's activity log and the data it saves, with passwords and keys hidden. It can't buy, sell or change anything.`
  :'Off. When on, the dev Mac can read this Mac\'s activity log and the data it saves, over Tailscale, with passwords and keys hidden. It can\'t buy, sell or change anything.';
 return `<label class="srow" id="logrow"><div class="l"><b>Let the dev Mac read logs</b><small>${sub}</small></div><input type="checkbox" switch class="tg" aria-label="Let the dev Mac read logs" ${l.on?'checked':''} onchange="logAccess(this.checked,this)"></label>${l.on?`<div class="srow"><div class="l"><small>Lost the code, or want to cut off the old one?</small></div><button class="btn" onclick="logAccess(true,this,1)">New code</button></div>`:''}`;}
async function logAccess(on,el,again){
 if(!on&&!confirm('Stop the dev Mac reading logs? Its code stops working now.')){el.checked=true;return;}
 if(again&&!confirm('Make a new code? The old one stops working now.'))return;
 let r;el.disabled=true;                     /* no double tap: two quick taps would make two codes */
 try{r=await api('/app/mac',{a:'logaccess',on});}catch(e){toast('Couldn\'t change it. Try again.');load('settings');return;}finally{el.disabled=false;}
 if(!r||!r.ok){toast((r&&r.msg)||'Couldn\'t change it. Try again.');load('settings');return;}
 if(!on){toast(r.msg);load('settings');return;}
 modal(`<h3>Code for the dev Mac</h3><p>Copy this now: it is shown only once. Give it to Claude on the dev Mac and Claude will set it up. It only lets the dev Mac read the activity log and saved data.</p>
 <div class="code" id="lc">${esc(r.token||'')}</div>${r.url?`<p class="m" style="font-size:12.5px">Address (give Claude this too):</p><div class="code" id="lu">${esc(r.url)}</div>`:'<p class="m" style="font-size:12.5px">Tailscale isn\'t signed in on this Mac, so the dev Mac can\'t reach it yet.</p>'}
 <div class="row" style="margin-top:12px"><button class="btn" onclick="logDone()">Done</button>${r.url?`<button class="btn" onclick="logCopy('#lu','Address')">Copy address</button>`:''}<button class="btn acc" onclick="logCopy('#lc','Code')">Copy code</button></div>`);}
function logCopy(sel,what){navigator.clipboard.writeText($(sel).textContent).then(()=>toast(what+' copied'),()=>toast('Couldn\'t copy: tap the '+what.toLowerCase()+' and copy it by hand'));}
function logDone(){const c=$('#lc');if(c)c.textContent='';closeModal();load('settings');}   /* the code doesn't linger in the page */
