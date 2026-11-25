function fidRow(){const f=S.fid||{};const here=(f.keys||[]).filter(k=>k.rp===location.hostname);
 if(LOCAL&&!/\.ts\.net$/.test(location.hostname))return (f.keys||[]).length?`<div class="srow"><div class="l"><b>Face ID sign-in</b><small>${f.keys.map(k=>esc(k.name)).join(', ')}</small></div><button class="btn ghost" onclick="fidRemoveAll()">Remove all</button></div>`:'';
 if(location.protocol!=='https:'||!window.PublicKeyCredential)return `<div class="srow"><div class="l"><b>Face ID sign-in</b><small>${(S.pk||{}).https?`Works on the secure address. Open <a href="${esc(S.pk.https)}">${esc(S.pk.https.replace('https://',''))}</a> and turn it on there.`:'Needs the Mac\'s secure address first (Settings › This Mac on the Mac).'}</small></div></div>`;
 return `<div class="srow"><div class="l"><b>Face ID sign-in</b><small>${here.length?`On for ${here.map(k=>esc(k.name)).join(', ')}. Unlock Combo Hub with your face instead of the passcode.`:((f.keys||[]).length?`Face ID was set up for another address (${esc((f.keys[0]||{}).rp||'')}). Turn it on again here to use it on this one.`:'Unlock Combo Hub with Face ID instead of typing the passcode.')}</small></div>
  ${here.length?`<button class="btn ghost" onclick="fidRemoveAll()">Turn off</button>`:`<button class="btn acc" onclick="fidOn(this)">Turn on</button>`}</div>`;}
const fb64=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-s.length%4)%4)),c=>c.charCodeAt(0));
const fe64=a=>btoa(String.fromCharCode(...new Uint8Array(a))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
async function fidOn(btn){hap();try{if(btn)btn.innerHTML='<span class="spin"></span>';
  const o=await api('/auth/reg-begin',{});const name=/iPhone/.test(navigator.userAgent)?'iPhone':/iPad/.test(navigator.userAgent)?'iPad':/Mac/.test(navigator.userAgent)?'Mac':'This device';
  const c=await navigator.credentials.create({publicKey:{challenge:fb64(o.challenge),rp:{id:o.rp,name:'Combo Hub'},user:{id:fb64(o.user),name:'Combo Hub',displayName:'Combo Hub'},
   pubKeyCredParams:[{type:'public-key',alg:-7}],authenticatorSelection:{authenticatorAttachment:'platform',residentKey:'preferred',userVerification:'required'},
   excludeCredentials:o.exclude.map(id=>({type:'public-key',id:fb64(id)})),attestation:'none',timeout:60000}});
  const r=await api('/auth/reg-finish',{clientDataJSON:fe64(c.response.clientDataJSON),attestationObject:fe64(c.response.attestationObject),name});
  hap(r.ok?'success':'error');toast(r.ok?'Face ID is on. Next time, just look at your phone to unlock.':(r.msg||'Couldn\'t turn it on.'),5000,r.ok?'good':'bad');
 }catch(e){toast(e&&e.name==='NotAllowedError'?'Cancelled.':e&&e.name==='InvalidStateError'?'Face ID is already on for this device.':'Couldn\'t turn it on: '+(e&&e.message||e),5000);}
 await fidLoad();if(S.view==='settings')renderSettings();}
async function fidLoad(){S.fid=await api('/auth/list',{}).catch(()=>({keys:[]}));}
async function fidRemoveAll(){const here=(S.fid.keys||[]).filter(k=>LOCAL&&!/\.ts\.net$/.test(location.hostname)||k.rp===location.hostname);
 for(const k of here)await api('/auth/remove',{id:k.id});toast('Face ID sign-in turned off.');await fidLoad();renderSettings();}
function pushRow(){const pk=S.pk||{};const can='serviceWorker' in navigator&&'PushManager' in window;
 if(location.protocol!=='https:'&&location.hostname!=='localhost')return `<div class="srow"><div class="l"><b>Notifications on this device</b><small>${pk.https?`Needs the secure address. Open <a href="${esc(pk.https)}">${esc(pk.https.replace('https://',''))}</a>, add that to your Home Screen, and turn them on there.`:'Needs the Mac\'s secure address first (Settings › This Mac on the Mac).'}</small></div></div>`;
 if(!can)return `<div class="srow"><div class="l"><b>Notifications on this device</b><small>On iPhone: open Combo Hub from its Home Screen icon (Share › Add to Home Screen), then turn them on here.</small></div></div>`;
 return `<div class="srow"><div class="l"><b>Notifications on this device</b><small>${S.pushOn?'On. Alerts from the Mac open the right screen when tapped.':'Get the Mac\'s alerts here, straight from Combo Hub.'}${pk.n?` · ${pk.n} device${pk.n>1?'s':''} signed up`:''}</small></div>
  ${S.pushOn?`<button class="btn" onclick="pushTest(this)">Send test</button><button class="btn ghost" onclick="pushOff()">Turn off</button>`:`<button class="btn acc" onclick="pushOn(this)">Turn on</button>`}</div>`;}
function urlB64(s){const p='='.repeat((4-s.length%4)%4);const b=atob((s+p).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from([...b].map(c=>c.charCodeAt(0)));}
async function pushOn(btn){try{const perm=await Notification.requestPermission();
  if(perm!=='granted'){toast('Notifications are blocked. Allow them in Settings › Notifications › Combo Hub.',6000);return;}
  if(btn)btn.innerHTML='<span class="spin"></span>';
  const k=await api('/app/push',{a:'key'});if(!k.ok){toast('The Mac is still updating. Try again in a few minutes.');return;}
  const reg=await navigator.serviceWorker.register('/sw.js');await navigator.serviceWorker.ready;
  const sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:urlB64(k.key)});
  await api('/app/push',{a:'sub',sub:sub.toJSON(),label:/iPhone/.test(navigator.userAgent)?'iPhone':'Browser'});
  const t=await api('/app/push',{a:'test'});S.pushOn=true;toast(t.sent?'Notifications are on. A test is on its way.':'Signed up. The test didn\'t go through yet.',5000);load('settings');
 }catch(e){toast('Couldn\'t turn them on: '+(e&&e.message||e),6000);load('settings');}}
async function pushTest(b){btnBusy(b,'Sending…');const t=await api('/app/push',{a:'test'}).catch(()=>({}));btnState(b,!!t.sent,t.sent?'Sent':'Not sent');toast(t.sent?'Sent. It should arrive in a few seconds.':'Nothing sent. Try turning it off and on.');}
async function pushOff(){try{const reg=await navigator.serviceWorker.getRegistration();const sub=reg&&await reg.pushManager.getSubscription();if(sub){await api('/app/push',{a:'off',sub:sub.toJSON()});await sub.unsubscribe();}}catch(e){}S.pushOn=false;toast('Notifications off on this device.');load('settings');}
function httpsRow(mac){const h=mac.https||{};
 if(h.state==='on')return `<div class="srow"><div class="l"><b>Secure address</b><small><a href="${esc(h.url)}" target="_blank">${esc(h.url.replace('https://',''))}</a> · use this on your iPhone for notifications</small></div><button class="btn ghost" data-u="${esc(h.url)}" onclick="navigator.clipboard.writeText(this.dataset.u).then(()=>toast('Copied'))">Copy</button></div>`;
 if(h.state==='need-enable'&&h.link)return `<div class="srow"><div class="l"><b>Secure address: one step</b><small>HTTPS certificates are not enabled in Tailscale admin yet. Tap Allow https, approve in the Tailscale page, then tap Check (it also checks itself every few minutes).</small></div><a class="btn acc" href="${esc(h.link)}" target="_blank">Allow https</a><button class="btn" onclick="macDo('https',this)">Check</button></div>`;
 if(h.state==='need-enable')return `<div class="srow"><div class="l"><b>Secure address: one step</b><small>HTTPS certificates are not enabled in Tailscale admin. Open the page, sign in, scroll to <b>HTTPS Certificates</b>, tap <b>Enable HTTPS...</b> and confirm. Then tap Check (it also checks itself every few minutes).</small></div><a class="btn acc" href="${esc(h.admin||'https://login.tailscale.com/admin/dns')}" target="_blank">Open Tailscale admin</a><button class="btn" onclick="macDo('https',this)">Check</button></div>`;
 const why={'no-cli':'Tailscale\'s command line isn\'t available on this Mac. Install the Tailscale app, then Try again.',
  'no-status':'Couldn\'t read Tailscale\'s status. Open the Tailscale app on this Mac, then Try again.',
  'no-daemon':'Couldn\'t read Tailscale\'s status: the command line can\'t talk to the Tailscale app. Open Tailscale on this Mac, check it says Connected, then Try again.',
  'cli-broken':'Couldn\'t read Tailscale\'s status: its command line wouldn\'t start from the watcher. Install the command line from Tailscale\'s settings, then Try again.',
  'signed-out':'Tailscale says this Mac is signed out. Open Tailscale, sign in, then Try again.',
  'needs-approval':'This Mac waits for approval in Tailscale admin (login.tailscale.com/admin/machines). Approve it, then Try again.',
  'ts-off':'Tailscale is switched off on this Mac. Open Tailscale, turn it on, then Try again.',
  'starting':'Tailscale is still starting on this Mac. It checks again by itself in a few minutes.',
  'no-name':'Tailscale is running but gave this Mac no name. Turn MagicDNS on at login.tailscale.com/admin/dns, then Try again.',
  'issuing':'Tailscale is still making the certificate. This can take a few minutes; it keeps checking.'};
 if(h.detail&&['no-cli','no-status','no-daemon','cli-broken','signed-out','needs-approval','ts-off','starting'].includes(h.state))why[h.state]=esc(h.detail.slice(0,300));
 return `<div class="srow"><div class="l"><b>Secure address</b><small>${why[h.state]||(h.state?'Not on yet ('+esc(h.state)+')'+(h.detail?': '+esc(h.detail.slice(-140)):''):'Checking…')}</small></div><button class="btn" onclick="macDo('https',this)">Try again</button></div>`;}
