// ---------------- settings
const UNITS={panel_budget:['$',''],take_profit:['','% of payout'],stake:['$',''],budget:['$',''],accept_pct:['','%'],live_min:['','%'],max_share:['','%'],bankroll:['$',''],refresh_secs:['','s'],cash_every:['',' min'],auto_cap:['',''],hedge_cap:['$',''],ideas_shown:['',''],overlap_n:['',' bets'],overlap_pct:['','% of panel money']};
const RANGES={panel_budget:[10,200,5],take_profit:[0,95,5],stake:[1,20,1],budget:[10,200,10],accept_pct:[50,100,5],live_min:[10,50,5],max_share:[20,100,10],bankroll:[100,5000,100],refresh_secs:[10,120,5],cash_every:[1,10,1],auto_cap:[1,11,1],hedge_cap:[25,500,25],ideas_shown:[1,10,1],overlap_n:[1,5,1],overlap_pct:[2,25,1]};
/* Auto cash-outs a day: the slider's top stop (11) is "Unlimited", stored as AUTO_CAP_UNL (issue #217; an older
   process reads 1000 as a cap it never reaches). Anything over 10 shows and saves as Unlimited. */
const AUTO_CAP_MAX=10,AUTO_CAP_UNL=1000;
function rngPos(k,v){return k==='auto_cap'&&+v>AUTO_CAP_MAX?AUTO_CAP_MAX+1:v;}
function rngVal(k,v){return k==='auto_cap'&&+v>AUTO_CAP_MAX?AUTO_CAP_UNL:+v;}
function fmtv(k,v){if(k==='take_profit'&&+v===0)return 'Off';if(k==='auto_cap'&&+v>AUTO_CAP_MAX)return 'Unlimited';const u=UNITS[k]||['',''];return u[0]+(+v).toLocaleString()+u[1];}
function rng(k,label,sub,dis){const v=rngPos(k,S.set.values[k]),[lo,hi,st]=RANGES[k];const p=Math.round((Math.min(Math.max(v,lo),hi)-lo)/(hi-lo)*100);
 return `<div class="srow ${dis?'dim':''}"><div class="l"><b>${label}</b>${sub?`<small>${sub}</small>`:''}</div><div class="rng"><input type="range" min="${lo}" max="${hi}" step="${st}" value="${v}" style="--p:${p}%"
  oninput="this.style.setProperty('--p',Math.round((this.value-${lo})/${hi-lo}*100)+'%');const o=this.nextElementSibling;o.textContent=fmtv('${k}',this.value);o.classList.remove('bump');void o.offsetWidth;o.classList.add('bump')" onchange="setv('${k}',rngVal('${k}',this.value))"><output>${fmtv(k,v)}</output></div></div>`;}
function tgl(k,label,sub,dis){return `<label class="srow ${dis?'dim':''}"><div class="l"><b>${label}</b>${sub?`<small>${sub}</small>`:''}</div><input type="checkbox" switch class="tg" ${S.set.values[k]?'checked':''} onchange="setv('${k}',this.checked)"></label>`;}
/* Settings › Cash out › Selling at a loss (#228 PR5): three choices instead of the old on/off override. An older saved
   value (only stop_loss) reads as Allow when it was on, else Let it tune itself, as the engine's sl_mode does. */
const SLM=[['never','Never sell at a loss','Nothing sells for less than you paid by itself, the learned loss cut included: a bet that keeps sliding rides to the end. Your own Cash out taps still work.'],
 ['tune','Let it tune itself','Off in each league until its own results show that selling a combo that turned against you late in a game beats holding it. Results › Selling shows where it is on. (The learned loss cut works as usual.)'],
 ['allow','Allow (guarded)','Auto cash-out may sell a combo for less than you paid, but only late in a game, when a pick has fallen well below its chance before the game and stayed there for a few minutes.']];
function slMode(){const v=S.set.values;return ['never','tune','allow'].includes(v.stop_loss_mode)?v.stop_loss_mode:(v.stop_loss===true?'allow':'tune');}
function slRow(dis){const m=slMode(),cur=SLM.find(x=>x[0]===m);
 return `<div class="srow ${dis?'dim':''}" id="slrow"><div class="l"><b>Selling at a loss</b><small>${esc(cur[2])}${m==='never'?'':' Never at halftime or a break, early in a game, or when the live score is missing or out of date.'}</small></div><div class="seg slseg">${SLM.map(x=>`<button class="${x[0]===m?'on':''}" data-slm="${x[0]}" onclick="setv('stop_loss_mode','${x[0]}');S.set.values.stop_loss=${x[0]==='allow'};renderSettings()">${esc(x[1])}</button>`).join('')}</div></div>`;}
function seg(k,label,sub,names){const v=S.set.values[k];return `<div class="srow"><div class="l"><b>${label}</b>${sub?`<small>${sub}</small>`:''}</div><div class="seg">${names.map((n,i)=>`<button class="${v===i?'on':''}" onclick="setv('${k}',${i});renderSettings()">${esc(n)}</button>`).join('')}</div></div>`;}
/* Let it ride as a slider with five detents: each step ticks the phone, the name pops, the dots under it fill. */
function rideRow(names){names=names||[];const n=Math.max(2,names.length),v=Math.max(0,Math.min(n-1,+S.set.values.ride||0));
 return `<div class="srow"><div class="l"><b>Let it ride</b><small>How long to hold before cashing out. Cautious sells sooner, Bold later, Ride it out turns smart sell off.</small></div>
  <div class="rng rdet"><input type="range" id="ride" aria-label="Let it ride" min="0" max="${n-1}" step="1" value="${v}" style="--p:${Math.round(v/(n-1)*100)}%" oninput="rideIn(this)" onchange="setv('ride',+this.value);renderSettings()"><output>${esc(names[v]||'')}</output>
  <div class="tks">${names.map((_,i)=>`<i class="${i<=v?'on':''} ${i===v?'at':''}"></i>`).join('')}</div></div></div>`;}
function rideIn(el){const names=(S.set&&S.set.ride)||[],n=Math.max(2,names.length),v=+el.value;el.style.setProperty('--p',Math.round(v/(n-1)*100)+'%');
 const o=el.parentNode.querySelector('output');if(o){o.textContent=names[v]||'';o.classList.remove('bump');void o.offsetWidth;o.classList.add('bump');}
 el.parentNode.querySelectorAll('.tks i').forEach((t,i)=>{t.classList.toggle('on',i<=v);t.classList.toggle('at',i===v);});}
function stp(k,lo,hi){const v=S.set.values[k];return `<div class="stp"><button onclick="bump('${k}',-1,${lo},${hi})">−</button><span>${v}</span><button onclick="bump('${k}',1,${lo},${hi})">＋</button></div>`;}
function bump(k,d,lo,hi){const v=Math.min(hi,Math.max(lo,(S.set.values[k]||0)+d));if(v===S.set.values[k])return;setv(k,v);
 const t=k.split('_')[0];const mn=t+'_min',mx=t+'_max';if(S.set.values[mn]>S.set.values[mx]){const o=k===mn?mx:mn;setv(o,S.set.values[k]);}renderSettings();}
/* #281 (scrolling first, as #151): the section headers (.sfold) and the Mac line (.smac) are full-width buttons, and with most
   sections folded they are a stack covering ~2/3 of a phone screen. Each carried a see-through iOS switch (method N), and a
   switch under the finger can stop iOS scrolling, so swiping the folded page mostly didn't scroll. They get no switch
   (data-hsw="0"): no iOS tick on them, but their press feedback and tap stay; the small controls keep theirs. */
function scard(id,ic,title,sub,inner){const o=sOpen(id);   // every section folds (GitHub #212): the header is the toggle, the body is a .fold
 return `<section class="scard ${o?'':'shut'}" id="s-${id}" data-sid="${id}"><header><h3><button type="button" class="sfold" data-hsw="0" aria-expanded="${o}" aria-controls="sb-${id}" onclick="sTog('${id}')"><span class="ic">${ic}</span><span class="st">${title}</span><span class="sbadge"></span><span class="chev">▾</span></button></h3>${sub?`<p>${sub}</p>`:''}</header><div class="fold ${o?'':'shut'}" id="sb-${id}" data-fk="set_${id}"><div class="fin">${inner}</div></div></section>`;}
/* ---- Settings: folds, jump chips, search and the Mac line (GitHub #212). Display only: no setting, switch, slider, save or
   Mac action changes. Every section folds with a chevron (remembered per phone as cw_fold_set_<id>; Money and The Mac start
   open, the rest folded). A folded body is still in the page (hidden, so nothing re-draws) and opens with the same height
   animation as Live's sections. The chips jump to a section and open it. Search filters rows by name and description across
   every section and opens them while it is on (the saved folds come back when it's cleared). */
const SFOLD_OPEN={money:1,mac:1};
function sOpen(id){let v=null;try{v=localStorage.getItem('cw_fold_set_'+id);}catch(e){}return v===null?!!SFOLD_OPEN[id]:v==='1';}
function sShow(id,o){try{localStorage.setItem('cw_fold_set_'+id,o?'1':'0');}catch(e){}
 const c=document.getElementById('s-'+id);if(!c)return;c.classList.toggle('shut',!o);const f=c.querySelector('.fold');if(f)f.classList.toggle('shut',!o);
 const b=c.querySelector('.sfold');if(b)b.setAttribute('aria-expanded',S.sq?'true':String(o));}
function sTog(id){hap('selection');sShow(id,!sOpen(id));}
function sJump(id){if(S.sq)sFind('');const c=document.getElementById('s-'+id);if(!c)return;if(!sOpen(id))sShow(id,true);
 const red=window.matchMedia&&matchMedia('(prefers-reduced-motion:reduce)').matches;
 c.scrollIntoView({behavior:red?'auto':'smooth',block:'start'});const b=c.querySelector('.sfold');if(b)try{b.focus({preventScroll:true});}catch(e){}}
const SITEM='.srow,.kv>div,.mixr,.sact';
function sFind(q){q=String(q==null?'':q);S.sq=q;const set=document.querySelector('.set');if(!set)return;
 const terms=q.toLowerCase().split(/\s+/).filter(Boolean),on=terms.length>0;set.classList.toggle('sq',on);
 const inp=$('#sq');if(inp&&inp.value!==q)inp.value=q;
 let any=false,n=0;
 set.querySelectorAll('.scard[data-sid]').forEach(c=>{const fin=c.querySelector('.fin'),b=c.querySelector('.sfold');
  const head=((c.querySelector('.st')||{}).textContent+' '+((c.querySelector('header p')||{}).textContent||'')).toLowerCase();
  const all=on&&terms.every(t=>head.includes(t));let hits=0;
  fin.querySelectorAll(SITEM).forEach(it=>{if(it._sq===undefined)it._sq=it.textContent.toLowerCase().replace(/\s+/g,' ');
   const ok=!on||all||terms.every(t=>it._sq.includes(t));it.classList.toggle('sq-no',!ok);if(ok)hits++;});
  fin.querySelectorAll('.kv,.mixl').forEach(k=>k.classList.toggle('sq-no',on&&!all&&!k.querySelector(SITEM+':not(.sq-no)')));
  [...fin.children].forEach(ch=>{if(!ch.matches(SITEM+',.kv,.mixl'))ch.classList.toggle('sq-no',on&&!all);});
  const vis=!on||all||hits>0;c.classList.toggle('sq-off',!vis);if(vis&&on){any=true;n+=hits;}
  if(b)b.setAttribute('aria-expanded',on?'true':String(sOpen(c.dataset.sid)));});
 const e=$('#sempty');if(e){e.hidden=!(on&&!any);const w=$('#semq');if(w)w.textContent=on?` “${q.trim()}”. Try another word.`:'';}
 const c=$('#scount');if(c)c.textContent=on?(any?`${n} setting${n===1?'':'s'} match`:'No settings match'):'';}
function sBadges(){const d=S.set;if(!d)return;
 document.querySelectorAll('.scard[data-sid]').forEach(c=>{const id=c.dataset.sid;let t='';
  if(id==='killer'||id==='maker'){const md=(d[id]||{}).mode;t=md==='on'?(id==='killer'?'Buying':'Placing orders'):md==='watch'?'Watching':'Off';}
  else if(id==='haptics'){const h=c.querySelector('#hapon');t=h?(h.checked?'On':'Off'):'';}
  else if(id==='mac'){t=S.mac&&S.mac.ok?String(S.mac.engine||S.mac.watcher||''):'';}
  else if(id==='keys'){t=d.keys&&d.keys.kalshi?'Kalshi connected':'Kalshi not connected';}
  else{const sw=c.querySelectorAll('input.tg:not([data-hapt])');if(sw.length)t=[...sw].filter(x=>x.checked).length+' of '+sw.length+' on';}
  const b=c.querySelector('.sbadge');if(b&&b.textContent!==t)b.textContent=t;});}
/* the Mac's version and whether it's current, right under the title; a tap jumps to Settings › The Mac */
function macLine(){const m=S.mac,nm=LOCAL?'This Mac':'The Mac';
 if(!m||!m.ok)return `<button type="button" class="smac" data-hsw="0" onclick="sJump('mac')"><span class="dot off"></span><span class="t"><b>${nm}</b> · status isn't available right now</span><span class="go">›</span></button>`;
 const v=esc(m.engine||m.watcher||'?');let st='running',up=true;
 if(!LOCAL&&m.latest){if(m.latest===m.engine)st='up to date';else{up=false;st='update available · '+esc(m.latest)+(m.waiting?' · waiting for approval':' · installing soon');}}
 return `<button type="button" class="smac" data-hsw="0" onclick="sJump('mac')"><span class="dot ${up?'':'upd'}"></span><span class="t"><b>${nm}</b> · version ${v} · <i class="${up?'ok':'upd'}">${st}</i></span><span class="go">›</span></button>`;}
function sAfter(m,hadF,a,b){sBadges();if(S.sq)sFind(S.sq);
 if(!m._sch){m._sch=1;m.addEventListener('change',e=>{if(e.target&&e.target.closest&&e.target.closest('.scard'))sBadges();});}
 if(hadF){const i=$('#sq');if(i){i.focus({preventScroll:true});try{i.setSelectionRange(a,b);}catch(e){}}}
 if(!window.__sRO){const t=$('.top');if(t){window.__sRO=1;const f=()=>{const h=Math.max(0,Math.round(t.getBoundingClientRect().bottom));if(h&&document.documentElement.style.getPropertyValue('--toph')!==h+'px')document.documentElement.style.setProperty('--toph',h+'px');};
  f();if(window.ResizeObserver)new ResizeObserver(f).observe(t);t.addEventListener('transitionend',f);addEventListener('scroll',f,{passive:true});addEventListener('resize',f);}}}
const PEND={};let saveT=null;
function setv(k,v){hap('selection');S.set.values[k]=v;PEND[k]=v;saved('Saving…');clearTimeout(saveT);saveT=setTimeout(flush,450);
 if(['auto_sell','auto_hedge','include_live','auto_cash','size_auto'].includes(k))renderSettings();}
async function flush(){const vals=Object.assign({},PEND);for(const k in PEND)delete PEND[k];
 const r=await api('/app/api/settings',{lg:S.set.lg,values:vals}).catch(()=>({ok:false}));
 if(r.ok){S.build=null;saved('Saved','ok');if(r.synced===true)toast('Saved · the Mac watcher has it now.');else if(r.synced===false)toast('Saved here, but the Mac watcher didn\'t get it. Try again.');}
 else{saved('Not saved');toast(r.msg||'Couldn\'t save. Check the connection.');}}
function saved(t,c){const e=$('#saved');if(e){e.className='saved '+(c||'')+(c==='ok'?' bump':'');e.innerHTML=(t==='Saving…'?'<span class="spin"></span>':c==='ok'?'✓':'')+' '+t;}}
function sport(lg){S.slg=lg;S.set=null;renderSettings();load('settings');}
function settingsSkel(){const row='<div style="display:grid;grid-template-columns:1fr 46px;gap:14px;align-items:center"><div style="display:grid;gap:6px"><i style="height:13px;width:52%"></i><i style="height:10px;width:78%"></i></div><i style="height:26px;border-radius:99px"></i></div>';
 return `<div class="set"><div></div><div><div class="hsk" style="padding:2px 0 18px"><i style="height:24px;width:34%"></i><i style="height:12px;width:60%"></i></div><div class="setsk">${[3,4,2].map(n=>`<div><i style="height:15px;width:40%"></i>${row.repeat(n)}</div>`).join('')}</div></div></div>`;}
function renderSettings(){const m=$('#main');const d=S.set;if(!d){m.innerHTML=(S.lerr||{}).settings?`<div class="set"><div></div><div>${errCard('settings')}</div></div>`:settingsSkel();return;}
 const v=d.values,mode=d.mode,mac=S.mac;
 const cap=mode==='mix'?'Mix cap':mode==='day'?'Daily cap':'Weekly cap';
 /* The date range (#248) moved to Build, next to the games board; this is just a pointer so nobody hunts for it. */
 const days=`<div class="srow"><div class="l"><b>Which days to build over</b><small>This moved to the Build tab, at the top under the league chips.</small></div><button class="btn ghost" type="button" onclick="go('build')">Open Build</button></div>`;
 const tiers=(d.full?[['full','Full slate','Every game on the slate in one bet. You choose how many underdogs it picks.','upsets',0,8,'underdogs']]:[]).concat([['safer','Safer','Short combos, more likely to hit.',null,2,8,'games each'],['middle','Middle','The core of the mix.',null,2,12,'games each'],['moonshot','Moonshot','Long shots, big payouts.',null,2,16,'games each']]);
 const mix=`<div class="mixl">${tiers.map(([t,n,s,alt,lo,hi,unit])=>{const b=alt||t;
  return `<div class="mixr"><div><b>${n}</b><small>${s}</small></div><div class="mixs"><div><span>How many</span>${stp(t+'_count',0,10)}</div><div><span>${alt?'Underdogs':'Games each'}</span>${stp(b+'_min',alt?0:lo,hi)}<span>to</span>${stp(b+'_max',alt?0:lo,hi)}</div></div></div>`;}).join('')}</div>`;
 const secs=[['money','💵','Money','Money'],['mix','🧩','Combo mix','Mix'],['games','🗓️','Games & picks','Games'],['killer','🔥','Killer deals','Killer'],['maker','📌','Standing orders','Orders'],['cash','💸','Cash out & hedging','Cash out'],['alerts','🔔','Notifications','Alerts'],['haptics','📳','Haptics','Haptics'],['mac','💻',LOCAL?'This Mac':'The Mac',LOCAL?'This Mac':'The Mac'],['keys','🔑','Accounts & keys','Keys']].filter(x=>(x[0]!=='killer'||d.killer)&&(x[0]!=='maker'||d.maker));
 const ago=s=>s<3600?Math.round(s/60)+' min':s<86400?Math.round(s/3600)+' hr':Math.round(s/86400)+' days';
 const macCard=LOCAL&&mac&&mac.ok?`<div class="kv"><div><span>Watcher</span><b><span class="dot"></span>Running · ${ago(mac.up)}</b></div><div><span>Version</span><b>${esc(mac.engine||mac.watcher)}</b></div>
   <div><span>Tailscale</span><b>${mac.ts?esc(mac.ts):'<span class="down">Not signed in</span>'}</b></div><div><span>Role</span><b>${mac.role==='backup'?'Backup':'Main hub'}${mac.paused?' · auto cash-out paused':''}</b></div>
   <div><span>Combo Hub passcode</span><b>${esc(mac.pass)}</b></div><div><span>Updates</span><b>${mac.auto_update?'Automatic':'Phone-approved · '+esc(mac.approved||'—')}</b></div></div>
   <div class="sact"><button class="btn acc" onclick="macUpdate(this)">Update now</button><button class="btn" onclick="macCode()">Phone pairing code</button><button class="btn" onclick="macPass()">Change passcode</button><button class="btn" onclick="S.showlog=!S.showlog;renderSettings()">${S.showlog?'Hide':'Show'} activity</button><button class="btn ghost" onclick="macDo('advanced',this)">Kalshi key & removal…</button><button class="btn ghost" onclick="hap('light');location.reload()">Reload the page</button></div>
   <label class="srow"><div class="l"><b>Install updates automatically</b><small>${mac.auto_update?'New versions install within about 10 minutes, no tap needed.':'Waits until your phone runs the new version and approves it.'}</small></div><input type="checkbox" switch class="tg" ${mac.auto_update?'checked':''} onchange="api('/app/mac',{a:'autoupdate',on:this.checked}).then(r=>{toast(r.msg);load('settings')})"></label>
   <div class="srow"><div class="l"><b>Alerts</b><small>${mac.last_push&&mac.last_push.at?`Last sent ${ago2(mac.last_push.at)} ago${mac.last_push.ok===false?' · <span class="down">ntfy refused it ('+mac.last_push.code+')</span>':''}: ${esc(mac.last_push.title)}`:'None sent since the Mac last restarted.'}${mac.quiet?' · Quiet hours now (10 PM–7 AM): only urgent ones go out.':''}</small></div><button class="btn" onclick="macDo('testpush',this)">Send test</button></div>
   ${oddsRow(mac.odds)}${httpsRow(mac)}${logRow(mac)}${mac.history?`<div class="srow"><div class="l"><b>History on this Mac</b><small>${(mac.history.q||0).toLocaleString()} Kalshi quotes · ${(mac.history.t||0).toLocaleString()} live ticks · ${(mac.history.b||0).toLocaleString()} combos tracked</small></div></div>`:''}
   ${S.showlog?`<div class="logbox">${esc((mac.log||[]).join('\n'))}</div>`:''}`
  :!LOCAL&&mac&&mac.ok?`<div class="kv"><div><span>Watcher</span><b><span class="dot"></span>Running · ${ago(mac.up)}</b></div><div><span>Version</span><b>${esc(mac.engine||mac.watcher)}</b></div>
   <div><span>Newest</span><b style="display:block;word-break:normal">${mac.latest?(mac.latest===mac.engine?'<i style="font-style:normal;color:var(--yes)">Up to date</i>':esc(mac.latest)+(mac.waiting?' · waiting':' · installing soon')):'—'}${mac.checked?`<i class="m" style="display:block;font-style:normal;font-size:12px;font-weight:500;margin-top:2px">${Date.now()/1000-mac.checked<60?'checked just now':'checked '+ago(Math.round(Date.now()/1000-mac.checked))+' ago'}</i>`:''}</b></div><div><span>Role</span><b>${mac.role==='backup'?'Backup':'Main hub'}${mac.paused?' · paused':''}</b></div></div>
   ${oddsRow(mac.odds)}<div class="srow"><div class="l"><small>Updates install ${mac.auto_update?'automatically within about 10 minutes':'after your phone approves them'}. The pairing code and passcode are on the Mac itself.</small></div><div class="sact" style="margin:0"><button class="btn" onclick="macCheck(this)">Check for an update now</button><button class="btn ghost" onclick="hap('light');location.reload()">Reload the page</button></div></div>`
  :`<div class="srow"><div class="l"><b>${LOCAL?'Couldn\'t read the Mac\'s status':'Couldn\'t reach the Mac'}</b><small>${LOCAL?'Reload in a moment.':'It may be asleep or restarting. Pull to refresh in a minute.'}</small></div><button class="btn ghost" onclick="hap('light');location.reload()">Reload the page</button></div>`;
 const hadF=document.activeElement&&document.activeElement.id==='sq',selA=hadF?document.activeElement.selectionStart:0,selB=hadF?document.activeElement.selectionEnd:0;
 m.innerHTML=`<div class="set${S.sq?' sq':''}"><nav class="sidx" aria-label="Jump to a settings section">${secs.map(([id,ic,t,sh])=>`<button type="button" class="sj" aria-controls="s-${id}" onclick="sJump('${id}')"><span class="ji">${ic}</span><span class="jf">${t}</span><span class="js">${sh}</span></button>`).join('')}<div class="sv">Planner ${esc(d.version)}</div></nav><div>
 <div class="stop"><div class="shead"><div><h1>Settings</h1><p>Planner settings are per sport. Changes save as you go.</p></div><div class="saved" id="saved"></div></div>
 ${macLine()}
 <div class="ssearch"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M16 16l4.5 4.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><input id="sq" type="search" class="txt" placeholder="Search settings" aria-label="Search settings" value="${esc(S.sq||'')}" oninput="sFind(this.value)" onkeydown="if(event.key==='Enter')this.blur()" autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="search"><button type="button" class="sclr" aria-label="Clear search" onclick="sFind('');$('#sq').focus()">✕</button></div>
 <div class="sempty" id="sempty" hidden><b>No settings match</b><span id="semq"></span><button type="button" class="btn" onclick="sFind('')">Clear search</button></div><div class="sr" id="scount" role="status" aria-live="polite"></div></div>
 <div class="srest">
 <div class="chips" style="margin-bottom:18px" id="sleagues">${d.leagues.map(([k,n,ic])=>`<button class="chip ${k===d.lg?'on':''}" onclick="sport('${k}')">${ic} ${esc(n)}</button>`).join('')}</div>
 ${scard('money','💵','Money','What each combo costs and the price you\'ll accept from Kalshi.',
   rsRow()+rng('panel_budget',"Today's panel",'The most the daily panel spends in one day')+rng('ideas_shown','Buy ideas shown','On Live, the best few by expected profit in dollars show first; the rest fold under "N more ideas". Dismiss one and it stays hidden until its price or edge improves, or tomorrow.')+tgl('panel_live','Include games already under way','The panel may pick a game in progress when its live price beats its chance right now, worked out from a fresh score and clock (never the pre-game price), and checked again just before buying. Not EuroLeague, UFC or tennis: no live score we trust there.')+tgl('panel_rank_dollars','Pick the panel by expected dollars','On: the panel picks the bets expected to make the most money, while keeping the chance the day finishes ahead at 55% or more (and close to the best it can be). Off: the old way, the safest-looking day first.')+tgl('line_model','Smarter spread/total pricing','Auto: spreads and totals are priced from how each league\'s games really finish (key numbers like 3 and 7, no ties, goals), only in leagues where that has beaten the old model. Results › What\'s working shows which. Off: the old model everywhere.')+tgl('smart_buy_gate','Smart Buy','Skips bets that are unlikely to be profitable. Each league starts working once it has enough results, and keeps learning from every result.')+tgl('knobs_live','Let smart sell tune its own numbers','On: once a week, smart sell may nudge one of its selling numbers in a league, only when that clearly did better and the newest bets agree. If its automatic sales keep getting less than holding was expected to pay, that league goes back to the starting numbers for 14 days (keeping any number it had made stricter). Every change shows in Results › What\'s working › Selling. Off: smart sell works as before.')+cutCard(S.panelCuts)+blockRow(d.blocks)+potRow(d.pots,d.potnames,d.potmoves)+skimRow(S.skim)+rng('stake','Per combo')+rng('budget',cap,'The most the planner spends in one '+(mode==='day'?'day':mode==='mix'?'mix':'week (Tue to Mon)'))+rng('accept_pct','Cut-off for your own combos','Kalshi prices paying less than this share of fair get marked')+tgl('idea_bar_strict','Stricter green Buy','On: a combo only gets the green Buy when it also clears its league\'s panel cut-off, and the Mac only sends a buy idea when it pays at least fair on your own record. Off: this cut-off alone.')+tgl('size_auto','Bet more when the price is good','$3 near the cut-off, up to $10 well above fair')+overlapRows(v))}
 ${scard('mix','🧩','Combo mix','How many of each kind to build each day, and how big each one is.',mix)}
 ${scard('games','🗓️','Games & picks','Live games and how picks are spread. The days to build over are on Build.',days+tgl('include_live','Include games already in progress','With extra safety checks')+rng('live_min','Live picks need at least','Chance to win right now',!v.include_live)
   +rng('max_share','One pick in at most','Share of combos for any single team')+tgl('hedge_close','Split coin-flip games','Put both sides of close games across combos')+tgl('dogs_late','Underdogs late','Favourites in the early games')+tgl('skip_news','Skip games with breaking news','When Kalshi and the sportsbooks disagree a lot'))}
 ${d.killer?scard('killer','🔥','Killer deals','Rare deals so good the Mac may buy them on its own.',killerCard(d.killer)):''}
 ${d.maker?scard('maker','📌','Standing orders','Buy orders resting under fair, managed by the Mac.',makerCard(d.maker)):''}
 ${scard('cash','💸','Cash out & hedging','When to take money off the table. The Mac watches these all day.',
   rng('bankroll','Betting bankroll','Bigger sure amounts against this get favoured')+rideRow(d.ride)
   +tgl('auto_cash','Keep a cash-out offer ready','On every live combo')+rng('cash_every','Fresh offers every','',!v.auto_cash)+rng('refresh_secs','Live updates every')
   +tgl('auto_sell','Auto cash-out','The Mac sells by itself, logged and capped')
   +tgl('smart_sell','Smart profit-taking','Sells when locking in beats the risk of holding, by sport: a one-goal hockey lead is fragile, an early NBA lead isn\'t',!v.auto_sell)
   +rng('take_profit','Take profit at','Sell once Kalshi offers this much of the payout, if it\'s at least 25% more than you paid',!v.auto_sell)
   +tgl('lock_trail','Lock in a run-up','After the offer reaches 60% of the payout, sell if it drops 20% from its high, while still a profit',!v.auto_sell)
   +slRow(!v.auto_sell)
   +rng('auto_cap','Auto cash-outs a day, at most','',!v.auto_sell)
   +tgl('auto_hedge','Hedge instead when it locks in more','When a combo is down to its last game and a cash-out is due, buys the other side instead if that locks in more. It only does so while that game is in play on an up-to-date live score, never at halftime or a break, only if it locks in at least what you paid, only after that has held for 3+ minutes, and only after re-checking the price right before buying. Otherwise it waits or cashes out as usual.',!v.auto_sell)+tgl('prefer_hedge','Prefer hedging','Even at up to 5% less than the cash-out',!v.auto_sell)+rng('hedge_cap','Most to spend on one hedge','',!v.auto_sell))}
 ${scard('alerts','🔔','Notifications','From the Mac. Bundled to one every 30 minutes, quiet 10 PM–7 AM. Urgent ones come right away.',
   fidRow()+pushRow()+tgl('notify_value','Combos quoting at a fair price')+tgl('notify_price','A better price on a combo')+tgl('notify_cash','Cash-outs and hedges')+tgl('notify_news','Big line moves and news'))}
 ${hapCard()}
 ${scard('mac','💻',LOCAL?'This Mac':'The Mac',LOCAL?'The watcher and Combo Hub run here, and keep themselves up to date.':'',verRow(d.version)+macCard)}
 ${scard('keys','🔑','Accounts & keys','Keys never leave the device they\'re on.',`<div class="kv"><div><span>Kalshi</span><b style="display:flex;align-items:center;gap:7px;word-break:normal">${d.keys.kalshi?'<span class="dot" style="flex:none"></span><span>Connected through the Mac</span>':'<span class="down">Not connected</span>'}</b></div><div><span>Sportsbook odds</span><b>${d.keys.odds?'Key saved':'Free sources only'}</b></div></div>
   <div class="srow"><div class="l"><small>Change the Mac's Kalshi key under This Mac › Kalshi key. The phone's keys are in the planner on the iPhone.</small></div>${S.inapp?'<a class="btn ghost" href="combo://phone">Phone screens</a>':''}</div>`)}
 </div></div></div>`;sAfter(m,hadF,selA,selB);}
/* Settings › The Mac: the sportsbook odds service's credits, read from answers the Mac already got (no extra calls).
   A thin bar for what's left, the pace, the projected run-out and the reset (marked "about" when it's a guess). */
function oddsRow(o){if(!o)return '';const T='<b>Sportsbook odds credits</b>';
 if(o.none)return `<div class="srow" id="oddsrow"><div class="l">${T}<small>Shows up after the Mac's next sportsbook check.</small></div></div>`;
 const day=(t,u)=>t?new Date(t*1000).toLocaleDateString('en-US',u?{month:'short',day:'numeric',timeZone:'UTC'}:{month:'short',day:'numeric'}):'—';
 const rem=Math.max(0,Math.round(o.remaining||0)),plan=rem+Math.max(0,Math.round(o.used||0)),share=plan?rem/plan:0;
 const reset=(o.reset_guess?'resets about ':'resets ')+day(o.reset,1);
 const pace=o.per_day==null?'pace shows after a few hours':o.per_day<=0?'none used lately':`about ${(+o.per_day).toLocaleString('en-US',{maximumFractionDigits:1})} a day`
  +(o.runs_out?(o.runs_out<o.reset?` · <span class="down">runs out ${day(o.runs_out)}</span>`:` · lasts past the reset`):'');
 const low=o.why==='out'?'<span class="down">Used up. Chances use free lines until the reset.</span>':
  o.saving?'<span class="down">Running low, so the Mac saves them for games starting soon that you have bets or good prices on.</span>':'';
 const col=o.low||o.saving?'var(--no)':share<.25?'var(--live)':'var(--yes)';
 return `<div class="srow" id="oddsrow"><div class="l">${T}<small>${plan?`${rem.toLocaleString('en-US')} of ${plan.toLocaleString('en-US')} left`:`${rem.toLocaleString('en-US')} left`} · ${pace} · ${reset}${o.last!=null?` · last check cost ${Math.round(o.last)}`:''}</small>${low?`<small>${low}</small>`:''}</div>
  <div style="text-align:right;flex:none"><b data-num="oddsrem" data-v="${rem}" data-f="cint" aria-label="${rem} credits left">${rem.toLocaleString('en-US')}</b><div class="bar" role="img" aria-label="${Math.round(share*100)}% of the plan's credits left"><i data-bar="oddsrem" style="width:${Math.max(2,Math.round(share*100))}%;background:${col}"></i></div></div></div>`;}
async function macCheck(b){btnBusy(b,'Checking…');const was=S.mac&&S.mac.engine;
 const r=await api('/app/mac-check',{}).catch(()=>({ok:false}));toast(r.msg||'Couldn\'t reach the Mac.',6000);if(!r.ok){btnState(b,false,'Couldn\'t reach the Mac');return;}
 for(const w of [20,25,25,30]){await new Promise(z=>setTimeout(z,w*1000));const m=await api('/app/mac-info',{}).catch(()=>null);
  if(m&&m.ok){S.mac=m;if(S.view==='settings')renderSettings();if(m.engine!==was&&was){toast('The Mac is now on '+m.engine+'.',5000);return;}if(m.latest===m.engine&&m.checked*1000>Date.now()-60e3){toast('Already on the newest version.',4000);return;}}}}
async function httpsCheck(b){hap();if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Checking Tailscale…';}
 const was=JSON.stringify((S.mac||{}).https||{});const r=await api('/app/mac',{a:'https'}).catch(()=>({ok:false}));
 if(!r.ok){toast(r.msg||'Couldn\'t reach the Mac.',5000,'bad');load('settings');return;}
 for(let k=0;k<20;k++){await new Promise(z=>setTimeout(z,3000));const m=await api('/app/mac',{a:'status'}).catch(()=>null);
  if(m&&m.ok){const h=m.https||{};if(JSON.stringify(h)!==was||k===19){S.mac=m;renderSettings();
   toast(h.state==='on'?'Secure address is on.':h.state==='need-enable'?(h.link?'One step left: tap Allow https, approve in Tailscale, then Check.':'One step left: enable HTTPS Certificates in Tailscale admin, then Check.'):h.state==='no-cli'?'Tailscale isn\'t installed on this Mac.':h.state==='issuing'?'Almost there: Tailscale is making the certificate.':'Not on yet: '+(h.detail||h.state||'no answer from Tailscale'),7000,h.state==='on'?'good':h.state==='need-enable'?null:'bad');return;}}}
 load('settings');}
/* Mac buttons: spin while working, then a check (or a cross) on the button itself before the card refreshes. */
async function macDo(a,b){if(a==='https')return httpsCheck(b);btnBusy(b);const r=await api('/app/mac',{a}).catch(()=>({ok:false}));
 toast(r.msg||(r.ok?'Done.':'That didn\'t work.'),5000);
 if(a==='update'&&r.ok){btnState(b,true,'Updating · back in about a minute',0);setTimeout(()=>location.reload(),70000);return;}
 btnState(b,!!r.ok,r.ok?(a==='testpush'?'Sent':'Done'):'Didn\'t work');setTimeout(()=>{if(S.view==='settings')load('settings');},1500);}
/* updating restarts the watcher, so it asks first */
function macUpdate(b){S.updBtn=b;modal(`<h3>Update the Mac now?</h3><p>It installs the newest version and restarts the watcher. Bets and settings stay as they are, and this page reloads by itself in about a minute.</p>
 <div class="row"><button class="btn" onclick="closeModal()">Not now</button><button class="btn acc" onclick="closeModal();macDo('update',S.updBtn)">Update now</button></div>`);}
async function macCode(){const r=await api('/app/mac',{a:'code'});modal(`<h3>Phone pairing code</h3><p>On the iPhone: planner › Settings › Watcher, paste this and Save. Only needed for a new phone or a reinstall.</p>
 <div class="code" id="pc">${esc(r.code||'')}</div><p class="m" style="font-size:12.5px">Hub: ${esc(r.hub||'Tailscale not signed in: the phone can only use the Mac at home.')}</p>
 <div class="row"><button class="btn" onclick="closeModal()">Close</button><button class="btn acc" onclick="navigator.clipboard.writeText($('#pc').textContent).then(()=>toast('Copied'))">Copy</button></div>`);}
function macPass(){modal(`<h3>Combo Hub passcode</h3><p>Needed on devices other than this Mac. Your phone's Open Combo Hub link signs in by itself.</p>
 <input class="txt" id="np" placeholder="At least 6 characters" autocomplete="new-password"><p class="m" id="perr" style="color:var(--no);min-height:18px"></p>
 <div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn acc" onclick="savePass()">Save passcode</button></div>`);setTimeout(()=>$('#np').focus(),50);}
async function savePass(){const r=await api('/app/mac',{a:'passcode',pass:$('#np').value});if(!r.ok){$('#perr').textContent=r.msg;return;}closeModal();toast(r.msg,5000);load('settings');}
/* Settings › Money: the overlap guard. On: a game you already have enough on (this many open bets, or this share of
   the panel's sizing base riding on it) is greyed in every pick list with an "Add anyway" only your own tap sends. */
function overlapRows(v){v=v||{};const off=!v.overlap_guard;
 return tgl('overlap_guard','Hold back games I already have bets on','On: Build, Best bets, Surprise me, Buy ideas and the panel\'s extras grey out a game you already have enough riding on, with Add anyway if you still want it. Buy prices also say when you already have a bet on that game.').replace("this.checked)","this.checked);renderSettings()")
  +(v.overlap_n!=null?rng('overlap_n','Held back from','Open bets on one game (combos, singles, spreads and totals each count once)',off):'')
  +(v.overlap_pct!=null?rng('overlap_pct','Or once this much is riding on it','Share of the money the panel sizes bets from (your Kalshi balance, less profit set aside) already at risk on one game',off):'');}
