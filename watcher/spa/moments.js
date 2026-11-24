// ---------------- the Sold moment, wins and the big hit
/* Cashing out gets the same drawn-check sheet as buying: what came back, the profit and a ticket stub. A loss gets a
   calm grey version (no alarm), like Kalshi's "Position closed" card. Shown for your own taps and, while the page is
   open, for sales smart sell or auto cash-out made by themselves. */
function soldSheet(o){const back=+o.back||0,cost=+o.cost||0,pl=back-cost,up=pl>=-0.004;hap(up?'success':'light');
 const id='sold:'+Date.now();S.nums[id]=0;
 modal(`<div class="okcard sold ${up?'':'okloss'}"><svg viewBox="0 0 84 84"><circle cx="42" cy="42" r="38"/>${up?'<path d="M27 43 L37 53 L58 32"/>':'<path d="M28 42 L56 42"/>'}</svg>
  <div class="stamp">${o.auto?'SOLD BY SMART SELL':'POSITION CLOSED'}</div><h3>${up?'Sold':'Closed'} · ${esc(o.label||'')}</h3>
  <div class="amt" data-num="${id}" data-v="${back.toFixed(2)}">${money(back)}</div>
  <div class="plp">${pl>=0?'+':'−'}${money(Math.abs(pl))} ${pl>=0?'profit':'loss'}${cost?` · ${pl>=0?'+':'−'}${Math.abs(Math.round(pl/cost*100))}%`:''}</div>
  <div class="tkt"><div>You paid<b>${money(cost)}</b></div><div>Got back<b>${money(back)}</b></div></div>
  <p>${up?(o.auto?'Smart sell took the offer because it beat holding.':'Locked in. The money is back in your balance.'):(o.auto?'Smart sell cut this one before it slid further.':'Some of it came back. On to the next one.')}</p>
  <div class="row" style="justify-content:center"><button class="btn acc" onclick="closeModal()">Done</button></div></div>`);
 rollNums($('#sheet'));clearTimeout(S.okT);S.okT=setTimeout(()=>{if($('#sheet .okcard.sold'))closeModal();},7000);}
function bigWin(c){const pays=+c.pays||0,cost=+c.cost||0,reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
 document.querySelectorAll('.bigwin').forEach(e=>e.remove());const box=document.createElement('div');box.className='bigwin';
 box.innerHTML=`<i class="ring2"></i><i class="ring2 b"></i><div class="bw"><div class="ey">Big hit</div><div class="amt">${money(reduce?pays:0)}</div><div class="lb">${esc(c.label||'')}</div>
  <div class="mx">+${money(pays-cost)}${cost?` · ${(pays/cost).toFixed(1)}× your money`:''}</div><br><button class="btn acc">Nice</button></div>`;
 const close=()=>{box.classList.add('out');setTimeout(()=>box.remove(),380);};box.addEventListener('click',close);document.body.appendChild(box);
 hap('success');setTimeout(()=>hap('success'),650);if(!reduce){celebrate();setTimeout(celebrate,700);
  const a=box.querySelector('.amt'),t0=performance.now();const step=t=>{const k=Math.min(1,(t-t0)/1400),e=1-Math.pow(1-k,4);a.textContent=money(pays*e);if(k<1)requestAnimationFrame(step);};requestAnimationFrame(step);}
 setTimeout(()=>{if(box.isConnected)close();},9000);}
function isBig(c){const p=(+c.pays||0)-(+c.cost||0);return p>=50||(p>=15&&c.cost>0&&c.pays/c.cost>=5);}
function winMoment(c){S.momSeen=S.momSeen||{};if(S.momSeen['w:'+c.t])return;S.momSeen['w:'+c.t]=1;
 if(isBig(c))bigWin(c);else{celebrate();toast(`${c.label} won · +${money((c.pays||0)-(c.cost||0))}`,5000,'good');}}
/* What changed between two loads of Live while the page was open: a combo that won, one that was cashed out, and
   any sale smart sell made by itself (singles included, from its log). */
function liveMoments(prev,d){if(!d||d.error)return;S.momSeen=S.momSeen||{};const was={};((prev&&prev.combos)||[]).forEach(c=>was[c.t]=c.group);
 if(prev&&!prev.error)(d.combos||[]).forEach(c=>{if(was[c.t]!=='pending')return;
  if(c.group==='won')winMoment(c);
  else if(c.group==='cashed'&&!S.momSeen['s:'+c.t]){S.momSeen['s:'+c.t]=1;const auto=(d.sales||[]).some(x=>x.ticker===c.t);soldShow({label:c.label,back:c.back,cost:c.cost,auto});}});
 (d.sales||[]).forEach(x=>{if((x.at||0)<S.t0||S.momSeen['s:'+x.ticker])return;S.momSeen['s:'+x.ticker]=1;soldShow({label:x.combo,back:x.offer,cost:x.cost,auto:true});soldReload();});}
/* Issue #242: a sale the Mac made shows its Sold moment at once; the list behind it is read again a few seconds
   later (even under the Sold sheet), so the sold bet leaves Live without waiting for the next refresh. */
function soldReload(){clearTimeout(S.soldT);S.soldT=setTimeout(()=>{if(S.view==='live'&&!S.scrub){S.lastLoad=Date.now();load('live');}},3000);}
/* Issue #242: every Mac tick carries when money last moved (a sale, hedge, fill or settlement). When it moves, the
   screen on show is read again now: Live/Games, and Results (which otherwise only loads when you open it). A finger
   on a chart or an open sheet waits for the next tick. */
function moneyTick(m){if(!(m>0))return;if(S.money==null){S.money=m;return;}if(m<=S.money)return;
 if(S.scrub||$('#modal').classList.contains('on'))return;
 S.money=m;if(['live','games'].includes(S.view)){S.lastLoad=Date.now();load(S.view);}else if(S.view==='results')load('results');}
function soldShow(o){if($('#modal').classList.contains('on')){const pl=(+o.back||0)-(+o.cost||0);toast(`Sold ${o.label} for ${money(o.back)} (${pl>=0?'+':'−'}${money(Math.abs(pl))})`,6000,pl>=0?'good':null);return;}soldSheet(o);}
S.t0=Date.now()/1000;
// ---------------- live events from the Mac
async function loadRecap(){const h=new Date().getHours();const day=new Date().toDateString();
 let seen='';try{seen=localStorage.getItem('cw_recap')||''}catch(e){}
 if(h<5||h>=14||seen===day){S.recap=null;return;}S.recap=await api('/app/api/recap').catch(()=>null);if(S.view==='live')renderLive();}
function recapCard(){const r=S.recap;if(!r||!r.bets||!r.bets.length)return '';
 return `<div class="card recap"><div class="rh"><div><div class="m" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase">Yesterday</div>
  <b style="font-size:26px" class="${r.pl>=0?'up':'down'}" data-num="rc:pl" data-v="${Math.abs(r.pl||0).toFixed(2)}" data-pre="${(r.pl||0)>=0?'+':'−'}">${smoney(r.pl)}</b> <span class="m">${r.won} up · ${r.lost} down</span></div>
  <button class="x" onclick="try{localStorage.setItem('cw_recap',new Date().toDateString())}catch(e){};S.recap=null;renderLive()">✕</button></div>
  ${r.best&&r.best.pl>0?`<div class="mini">Best<b class="up">${esc(r.best.what)} ${smoney(r.best.pl)}</b></div>`:''}${r.worst&&r.worst.pl<0?`<div class="mini">Worst<b class="down">${esc(r.worst.what)} ${smoney(r.worst.pl)}</b></div>`:''}
  ${r.note?`<div class="m" style="font-size:12.5px;margin-top:6px">${esc(r.note)}</div>`:''}${streakNote(r)}</div>`;}
/* The streak note in the morning recap: days in a row the panel finished up, a flame and a dot per day (up to a week).
   One good day says what starts a streak; a down day says nothing (no guilt trip). */
function streakNote(r){const s=+r.streak||0;if(s<1)return '';
 if(s===1)return `<div class="streak"><span class="fl">🔥</span><span><b>1 day up.</b> Another good day today starts a streak.</span></div>`;
 return `<div class="streak hot"><span class="fl">🔥</span><span><b>${s} days up</b> in a row${s>=7?'. A whole week.':s>=3?'. Keep it going.':''}</span><span class="dots">${Array.from({length:Math.min(s,7)},(_,i)=>`<i style="--i:${i}"></i>`).join('')}</span></div>`;}
function okSheet(title,amt,sub,bad){hap(bad?'error':'success');modal(`<div class="okcard ${bad?'bad':''}"><svg viewBox="0 0 84 84"><circle cx="42" cy="42" r="38"/>${bad?'<path d="M30 30 L54 54 M54 30 L30 54"/>':'<path d="M27 43 L37 53 L58 32"/>'}</svg>
 <h3>${esc(title)}</h3>${amt!=null?`<div class="amt">${esc(amt)}</div>`:''}<p>${esc(sub||'')}</p><div class="row" style="justify-content:center"><button class="btn acc" onclick="closeModal()">Done</button></div></div>`);
 clearTimeout(S.okT);S.okT=setTimeout(()=>{if($('#sheet .okcard'))closeModal();},5200);}
function celebrate(){hap('success');const box=document.createElement('div');box.className='confetti';const cols=['#4f8cff','#3ecf8e','#ffb020','#ff6b9a','#b48cff'];
 for(let i=0;i<70;i++){const s=document.createElement('i');s.style.left=Math.random()*100+'vw';s.style.background=cols[i%cols.length];s.style.animationDelay=Math.random()*.4+'s';s.style.transform=`rotate(${Math.random()*360}deg)`;box.appendChild(s);}
 document.body.appendChild(box);setTimeout(()=>box.remove(),2600);}
function connect(){if(!window.EventSource)return;try{const es=new EventSource('/app/events');S.es=es;
 es.onopen=()=>{S.live_ok=true;S.esEver=true;stat();};
 es.onerror=()=>{S.live_ok=false;stat();};
 es.onmessage=e=>{let ev;try{ev=JSON.parse(e.data)}catch(x){return}
  if(ev.kind==='tick'){moneyTick(ev.money);if(typeof verPoll==='function')verPoll();if(S.gameOpen&&$('#modal').classList.contains('on')){if(Date.now()-(S.gameAt||0)>4000)drawGame();return;}if(['live','games'].includes(S.view)&&Date.now()-(S.lastLoad||0)>4000&&!$('#modal').classList.contains('on')){S.lastLoad=Date.now();load(S.view);}return;}
  S.events=(S.events||[]).concat([ev]).slice(-30);
  if(ev.kind==='settled'&&/ won$/.test(ev.text||'')){const c=((S.live&&S.live.combos)||[]).find(x=>x.t===ev.combo);if(c)winMoment(c);else celebrate();}
  if(['score','advice','alert','settled','idea'].includes(ev.kind)){const k=ev.kind+'|'+ev.text;S.seen=S.seen||{};if(Date.now()-(S.seen[k]||0)>90000){S.seen[k]=Date.now();toast(ev.text,ev.kind==='score'?6000:ev.kind==='advice'?7000:4500,ev.kind==='score'?(ev.good?'good':'bad'):null,ev.kind==='advice'&&comboOk(ev.combo)?()=>openCombo(ev.combo):null);}}
  if(S.gameOpen&&ev.ticker===S.gameOpen)drawGame();
  if(S.view==='live'||S.view==='games'){S.lastLoad=Date.now();load(S.view,ev.kind==='advice'||ev.kind==='settled'||ev.kind==='idea');}};
 }catch(x){}}
function stat(){netBanner();const el=$('#st');if(!el)return;el.innerHTML=`<span class="dot ${S.live_ok===false?'off':''}"></span>${S.live_ok===false?'Reconnecting…':'Mac · live'}`;}
