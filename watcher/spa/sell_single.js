/* ---- Sell a single bet, spread or total by Pete's own tap (issue #238). Live's single cards (and the game page's
   "Your bets on this game") get "Get new price" (Kalshi's order book read now: the card's Worth now and what selling
   gets after the fee) and "Sell", which opens a sheet with a 20-second quote. The sale needs two taps (the first arms
   the button for 4 s); the Mac re-reads the book, refuses a lower bid, and sends one fill-now-or-cancel, reduce-only
   sale at the quoted price or better. Pause, the unknown-outcome block and rule 8 are checked on the Mac; an unclear
   answer is "Check Kalshi" and is never resent. Nothing here sells by itself. */
S.sellq=S.sellq||{};
function ssAge(at){const s=Math.max(0,Math.round(Date.now()/1000-at));return s<5?'just now':s<60?s+'s ago':Math.round(s/60)+' min ago';}
function ssActs(x){if(x.res||!(x.state==='live'||x.state==='pre'))return '';const p=S.sellq[x.t],busy=S.ssBusy&&S.ssBusy[x.t];
 const line=p?(p.ok?`Kalshi bid <b>${Math.round(p.bid*100)}¢</b> · sell now for <b>${m2(p.got)}</b> after the fee${p.thin?' · <span class="down">thin market</span>':''} · ${ssAge(p.at)}`:`<span class="down">${esc(p.msg||'No price right now.')}</span>`):'Sell any time: the price comes straight from Kalshi.';
 return `<div class="sacts" onclick="event.stopPropagation()"><span class="s">${line}</span>
  <button class="btn ghost sm" data-ssp="${esc(x.t)}" ${busy?'disabled':''} onclick="event.stopPropagation();ssPrice('${x.t}',this)">${busy?'<span class="spin"></span> Asking…':'Get new price'}</button>
  <button class="btn yes sm" data-sss="${esc(x.t)}" onclick="event.stopPropagation();ssOpen('${x.t}')">Sell${p&&p.ok?' '+m2(p.got):''}</button></div>`;}
function ssFind(t){const d=S.live||{};return (d.singles||[]).find(x=>x.t===t)||null;}
async function ssPrice(t,b){S.ssBusy=S.ssBusy||{};if(S.ssBusy[t])return;S.ssBusy[t]=1;if(b)btnBusy(b,'Asking…');
 const r=await api('/app/api/act',{a:'sellquote',t}).catch(()=>({ok:false,msg:'Couldn\'t reach your Mac.'}));delete S.ssBusy[t];
 r.at=Date.now()/1000;S.sellq[t]=r;const x=ssFind(t);
 if(r.ok&&x){x.worth=r.worth;}hap(r.ok?(r.thin?'warning':'success'):'error');if(!r.ok)toast(r.msg||'No price came in.',4500,'bad');
 if(S.view==='live')renderLive();else if(b&&b.isConnected)btnState(b,r.ok,r.ok?'✓ '+money(r.got):'✕ No price');return r;}
function ssOpen(t){if(!t)return;const p=S.sellq[t];S.ss={t,q:null,busy:true,err:null,fail:null};
 modal(`<div class="sb" id="ssx">${ssSkel()}</div>`);
 if(p&&p.ok&&!p.used&&Date.now()/1000-p.at<p.secs-8){S.ss.q=p;S.ss.busy=false;ssPaint();clearInterval(S.ssT);S.ssT=setInterval(ssTick,1000);return;}
 ssQuote();}
function ssSkel(){return `<div class="psk"><i style="height:12px;width:30%"></i><i style="height:24px;width:70%"></i><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px"><i style="height:64px"></i><i style="height:64px"></i><i style="height:64px"></i></div><i style="height:90px"></i><i style="height:46px"></i></div><div class="m" style="text-align:center;font-size:12.5px"><span class="spin"></span> Asking Kalshi what it pays now…</div>`;}
async function ssQuote(){const s=S.ss;if(!s||s.sending)return;s.busy=true;s.err=null;s.fail=null;ssPaint();
 const r=await api('/app/api/act',{a:'sellquote',t:s.t}).catch(()=>({ok:false,msg:'Couldn\'t reach your Mac.'}));
 if(S.ss!==s)return;s.busy=false;r.at=Date.now()/1000;S.sellq[s.t]=r;
 if(!r||!r.ok){s.q=null;s.err=(r&&r.msg)||'No price came in.';hap('error');ssPaint();return;}
 s.q=r;const x=ssFind(s.t);if(x)x.worth=r.worth;hap(r.blocked||!r.clears?'warning':'success');ssPaint();
 clearInterval(S.ssT);S.ssT=setInterval(ssTick,1000);}
function ssTick(){const s=S.ss,q=s&&s.q,box=$('#ssx');if(!q||!box||!$('#modal').classList.contains('on')){clearInterval(S.ssT);return;}
 const left=Math.max(0,Math.round(q.secs-(Date.now()/1000-q.at)));const e=box.querySelector('.sbs');if(e&&e.textContent!==String(left))e.textContent=left;
 if(left<=0&&!q.x&&!s.sending){q.x=1;clearInterval(S.ssT);ssPaint();}}
function ssPaint(){const s=S.ss,box=$('#ssx');if(!s||!box)return;
 if(!s.q){box.innerHTML=s.busy?ssSkel():`<div class="sbk">Sell</div><h3>No price right now</h3><div class="sbw sbx"><i>✕</i><span>${esc(s.err||'No price came in.')}</span></div>
  <div class="sbgo"><button class="btn ghost" onclick="ssClose()">Close</button><button class="btn acc pri" onclick="ssQuote()">Try again</button></div>`;return;}
 const q=s.q,dead=q.x||Date.now()/1000-q.at>=q.secs,left=Math.max(0,Math.round(q.secs-(Date.now()/1000-q.at))),ok=q.clears&&!q.blocked;
 const pl=q.profit,plp=q.cost?Math.round(pl/q.cost*100):null;
 box.innerHTML=`<div class="sbk">${ICON[q.sport]||''} Sell · ${typeof sbKind==='function'?sbKind(q):''}${q.live?' <span class="tag" style="background:var(--livebg);color:var(--live)">LIVE</span>':''}</div>
  <h3>${esc(q.pick)}</h3>${q.game?`<div class="m" style="font-size:13px">${esc(q.game)}</div>`:''}
  <div class="sbn"><div><span>Kalshi bid</span><b data-num="ss:bid" data-v="${q.bid}" data-f="cent">${Math.round(q.bid*100)}¢</b><small>${q.gap!=null?Math.round(q.gap*100)+'¢ gap':'no sellers'} · ${q.depth>=1000?Math.round(q.depth/1000)+'k':Math.floor(q.depth||0)} wanted</small></div>
   <div><span>You'd get</span><b class="up" data-num="ss:got" data-v="${q.got}">${m2(q.got)}</b><small>after ${m2(q.fee)} fee</small></div>
   <div><span>${pl>=0?'Profit':'Loss'}</span><b class="${pl>=0?'up':'down'}">${smoney(pl)}</b><small>${plp!=null?(pl>=0?'+':'−')+Math.abs(plp)+'% on '+m2(q.cost):'vs what you paid'}</small></div></div>
  <div class="sum">Contracts<b>${q.n}${q.n<Math.floor(q.have)?' of '+Math.floor(q.have):''} at ${Math.round(q.px*100)}¢ or better</b></div>
  <div class="sum">You paid<b>${m2(q.cost)}</b></div>
  ${q.chance!=null?`<div class="sum">If you hold<b>${pct(q.chance)} chance of ${m2(q.pays)}</b></div>`:''}
  ${(q.warn||[]).map(w=>`<div class="sbw" data-w="${esc(w.k)}"><i>⚠️</i><span>${esc(w.t)}</span></div>`).join('')}
  ${q.blocked?`<div class="sbw sbx" data-w="blocked"><i>✕</i><span>${esc(q.blocked)}</span></div>`:''}
  ${s.fail?`<div class="sbw sbx" data-w="failed"><i>✕</i><span>${esc(s.fail)}</span></div>`:''}
  <div class="sbgo"><button class="btn ghost" onclick="ssClose()">Keep it</button>${dead||s.fail||q.used?`<button class="btn acc pri" id="sssell" onclick="ssQuote()">Get a fresh price</button>`:
   q.blocked?`<button class="btn pri" id="sssell" disabled>Can't sell this now</button>`:
   `<button class="btn qb pri ${ok?'yes':'warn'}" id="sssell" onclick="ssSell(this)">${qBar(q)}${ok?'Sell':'Sell anyway'} for ${m2(q.got)}</button>`}</div>
  <div class="sbleft">${dead||s.fail||q.used?'Prices move. Get a fresh one to sell.':`Price good for <span class="sbs">${left}</span>s · sells now at ${Math.round(q.px*100)}¢ or better, or not at all`}</div>`;
 rollNums(box);}
async function ssSell(b){const s=S.ss,q=s&&s.q;if(!q||s.sending||b.disabled)return;
 if(q.x||Date.now()/1000-q.at>=q.secs){ssQuote();return;}
 if(b.dataset.sure!=='1'){b.dataset.sure='1';b.classList.add('arm');b.textContent=`Tap again to sell for ${m2(q.got)}`;hap('warning');
  setTimeout(()=>{if(b.isConnected&&b.dataset.sure==='1'&&!s.sending){b.dataset.sure='';ssPaint();}},4000);return;}
 s.sending=true;b.disabled=true;b.classList.remove('arm');b.innerHTML='<span class="spin"></span> Selling… confirming with Kalshi';
 let r;try{r=await api('/app/api/act',{a:'singlesell',t:q.t,q:q.q,anyway:!ssOk(q)});}
 catch(e){r={ok:false,check:true,msg:'Lost contact with your Mac while selling, so this may or may not have gone through. Check Live in a minute before trying again.'};}
 s.sending=false;q.used=1;if(S.sellq[q.t]===q)delete S.sellq[q.t];clearInterval(S.ssT);
 if(r.ok||r.check)load('live',true).catch(()=>{});
 const here=S.ss===s&&!!$('#ssx')&&$('#modal').classList.contains('on'),free=here||!$('#modal').classList.contains('on');
 if(r.ok){if(S.ss===s)S.ss=null;if(free)soldSheet({back:r.got,cost:r.cost,label:q.pick});else{hap('success');toast('Sold: '+q.pick+'. '+(r.msg||'').replace(/^✅\s*/,''),9000,'good');}return;}
 if(r.check){if(S.ss===s)S.ss=null;if(free)okSheet('Check Kalshi',null,r.msg,true);else{hap('error');toast('Check Kalshi: '+r.msg,9000,'bad');}return;}
 const why=r.msg||'It didn\'t go through. Nothing was sold.';
 if(here){s.fail=why;hap('error');ssPaint();}else{hap('error');toast(why,7000,'bad');}}
function ssOk(q){return !!(q&&q.clears&&!q.blocked);}
function ssClose(){closeModal();S.ss=null;}
