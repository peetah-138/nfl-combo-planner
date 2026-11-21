/* ---- Buy straight (issue #113): one team, or a spread/total, bought on its own by Pete's tap. The sheet asks the Mac
   for a price (Kalshi's order book read right now, our fair chance, the edge, a suggested stake, the cap), which is good
   for 20 seconds (the draining bar). Buy sends that exact quote once; the Mac re-reads the book and refuses a higher price,
   so it never pays more than shown. Stakes over the quote's `arm` need a second tap. Nothing here buys by itself. */
const m2=x=>x==null?'—':'$'+(+x).toFixed(2);
function sbOpen(t,lg){if(!t)return;S.sb={t,lg:lg||'',stake:null,q:null,busy:true,err:null,back:S.gameOpen||null};modal(`<div class="sb" id="sbx">${sbSkel()}</div>`);sbQuote();}
function sbSkel(){return `<div class="psk"><i style="height:12px;width:30%"></i><i style="height:24px;width:70%"></i><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px"><i style="height:64px"></i><i style="height:64px"></i><i style="height:64px"></i></div><i style="height:34px"></i><i style="height:90px"></i><i style="height:46px"></i></div><div class="m" style="text-align:center;font-size:12.5px"><span class="spin"></span> Asking Kalshi for its price now…</div>`;}
async function sbQuote(stake){const s=S.sb;if(!s||s.sending)return;if(stake!=null)s.stake=stake;s.busy=true;s.err=null;s.fail=null;sbPaint();
 const r=await api('/app/api/act',{a:'singlequote',t:s.t,lg:s.lg,stake:s.stake}).catch(()=>({ok:false,msg:'Couldn\'t reach your Mac.'}));
 if(S.sb!==s)return;s.busy=false;
 if(!r||!r.ok){s.q=null;s.err=(r&&r.msg)||'No price came in.';hap('error');sbPaint();return;}
 r.at=Date.now()/1000;s.q=r;s.stake=r.stake;hap(r.blocked||!r.clears?'warning':'success');sbPaint();
 clearInterval(S.sbT);S.sbT=setInterval(sbTick,1000);}
function sbTick(){const s=S.sb,q=s&&s.q,box=$('#sbx');if(!q||!box||!$('#modal').classList.contains('on')){clearInterval(S.sbT);return;}
 const left=Math.max(0,Math.round(q.secs-(Date.now()/1000-q.at)));const e=box.querySelector('.sbs');if(e&&e.textContent!==String(left))e.textContent=left;
 if(left<=0&&!q.x&&!s.sending){q.x=1;clearInterval(S.sbT);sbPaint();}}
function sbKind(q){return q.kind==='spread'?'📏 Spread':q.kind==='total'?'➕ Total':'🎯 Single game';}
function sbPaint(){const s=S.sb,box=$('#sbx');if(!s||!box)return;
 if(!s.q){box.innerHTML=s.busy?sbSkel():`<div class="sbk">Buy straight</div><h3>No price right now</h3><div class="sbw sbx"><i>✕</i><span>${esc(s.err||'No price came in.')}</span></div>
  <div class="sbgo"><button class="btn ghost" onclick="sbClose()">Close</button><button class="btn acc pri" onclick="sbQuote()">Try again</button></div>`;return;}
 const q=s.q,dead=q.x||Date.now()/1000-q.at>=q.secs,left=Math.max(0,Math.round(q.secs-(Date.now()/1000-q.at)));
 const ret=q.ret,ok=q.clears&&!q.blocked;
 const chips=(q.presets||[3,5,10]).map(v=>`<button class="chip ${Math.abs(q.stake-v)<.005?'on':''}" onclick="sbQuote(${v})">$${v}</button>`).join('');
 const custom=(q.presets||[]).every(v=>Math.abs(q.stake-v)>=.005);
 box.innerHTML=`<div class="sbk">${ICON[q.sport]||''} ${sbKind(q)}${q.live?' <span class="tag" style="background:var(--livebg);color:var(--live)">LIVE</span>':''}</div>
  <h3>${esc(q.pick)}</h3>${q.opp||q.game?`<div class="m" style="font-size:13px">${q.opp?'vs '+esc(q.opp):esc(q.game)}</div>`:''}
  <div class="sbn"><div><span>Kalshi now</span><b data-num="sb:ask" data-v="${q.ask}" data-f="cent">${Math.round(q.ask*100)}¢</b><small>${q.gap!=null?Math.round(q.gap*100)+'¢ gap':'no bids'} · ${q.depth>=1000?Math.round(q.depth/1000)+'k':Math.floor(q.depth)} for sale</small></div>
   <div><span>Our chance</span><b>${q.fair!=null?pct(q.fair):'—'}</b><small>${q.fair!=null?esc(q.how||''):'no fair price'}</small></div>
   <div><span>Edge</span><b class="${ret==null?'':ret>=0?'up':'down'}">${ret==null?'—':(ret>=0?'+':'−')+Math.abs(Math.round(ret*100))+'%'}</b><small>${ret==null?'Kalshi\'s price only':'expected · '+(q.edge>=0?'+':'−')+Math.abs(q.edge*100).toFixed(1)+'¢ a contract'}</small></div></div>
  <div class="sbk" style="margin-top:2px">Stake</div>
  <div class="sbst">${chips}<input id="sbin" type="number" inputmode="decimal" min="1" max="${q.max}" step="1" placeholder="Custom" value="${custom?q.stake:''}" onkeydown="if(event.key==='Enter'){this.blur()}" onchange="sbCustom(this)" aria-label="Custom stake in dollars">
   ${Math.abs(q.sug-q.stake)>=.005?`<button class="chip" onclick="sbQuote(${q.sug})">Suggested $${(+q.sug).toFixed(2).replace(/\.00$/,'')}</button>`:'<span class="m" style="font-size:12px">suggested size</span>'}</div>
  <div class="sum">Contracts<b>${q.n} at ${Math.round(q.ask*100)}¢</b></div><div class="sum">You pay (with Kalshi's fee)<b>${m2(q.cost)}</b></div>
  <div class="sum">Pays if it wins<b class="up">${m2(q.pays)} <span class="m" style="font-weight:600">(${smoney(q.profit)})</span></b></div>
  ${q.room!=null?`<div class="sum">Room under your cap<b>${m2(q.room)} of ${m2(q.budget)}</b></div>`:''}
  ${(q.warn||[]).map(w=>`<div class="sbw" data-w="${esc(w.k)}"><i>⚠️</i><span>${esc(w.t)}</span></div>`).join('')}
  ${q.blocked?`<div class="sbw sbx" data-w="blocked"><i>✕</i><span>${esc(q.blocked)}</span></div>`:''}
  ${s.fail?`<div class="sbw sbx" data-w="failed"><i>✕</i><span>${esc(s.fail)}</span></div>`:''}
  <div class="sbgo"><button class="btn ghost" onclick="sbClose()">Cancel</button>${dead||s.fail||q.used?`<button class="btn acc pri" id="sbbuy" onclick="sbQuote()">Get a fresh price</button>`:
   q.blocked?`<button class="btn pri" id="sbbuy" disabled>Can't buy this now</button>`:
   `<button class="btn qb pri ${ok?'yes':'warn'}" id="sbbuy" onclick="sbBuy(this)">${qBar(q)}${ok?'Buy':'Buy anyway'} ${m2(q.cost)} → ${m2(q.pays)}</button>`}</div>
  <div class="sbleft">${dead||s.fail||q.used?'Prices move. Get a fresh one to buy.':`Price good for <span class="sbs">${left}</span>s · fills now at ${Math.round(q.ask*100)}¢ or better, or not at all`}</div>`;
 rollNums(box);}
function sbCustom(el){const v=parseFloat(el.value);if(!(v>0)){toast('Type a stake in dollars.');return;}const s=S.sb;const mx=(s&&s.q&&s.q.max)||100;
 if(v>mx){toast(`One straight bet is at most $${mx}.`,4000,'bad');el.value=mx;}sbQuote(Math.min(v,mx));}
async function sbBuy(b){const s=S.sb,q=s&&s.q;if(!q||s.sending||b.disabled)return;
 if(q.x||Date.now()/1000-q.at>=q.secs){sbQuote();return;}
 if(q.cost>q.arm&&b.dataset.sure!=='1'){b.dataset.sure='1';b.classList.add('arm');b.textContent=`Tap again to buy ${m2(q.cost)}`;hap('warning');
  setTimeout(()=>{if(b.isConnected&&b.dataset.sure==='1'&&!s.sending){b.dataset.sure='';sbPaint();}},4000);return;}
 s.sending=true;b.disabled=true;b.classList.remove('arm');b.innerHTML='<span class="spin"></span> Buying… confirming with Kalshi';
 let r;try{r=await api('/app/api/act',{a:'singlebuy',t:q.t,q:q.q,anyway:!(q.clears&&!q.blocked)});}
 catch(e){r={ok:false,check:true,msg:'Lost contact with your Mac while buying, so this may or may not have gone through. Check Live in a minute before trying again.'};}
 s.sending=false;q.used=1;clearInterval(S.sbT);if(r.ok&&S.view==='live')load('live',true).catch(()=>{});
 /* the answer is always shown, even if the sheet was closed or another one opened meanwhile (a Bought or a Check Kalshi
    must never go unseen): on this sheet, else as a sheet of its own, else (another sheet is up) as a long toast */
 const here=S.sb===s&&!!$('#sbx')&&$('#modal').classList.contains('on'),free=here||!$('#modal').classList.contains('on');
 if(r.ok||r.check){if(S.sb===s)S.sb=null;const sub=r.ok?`${q.pick}. ${r.msg} It shows on Live under Single bets & spreads within a minute; smart sell watches it from there.`:r.msg;
  if(free){if(r.ok)okSheet('Bought',`${m2(r.pays)} if it wins`,sub);else okSheet('Check Kalshi',null,sub,true);}
  else{hap(r.ok?'success':'error');toast((r.ok?'Bought: ':'Check Kalshi: ')+sub,9000,r.ok?'good':'bad');}return;}
 const why=r.msg||'It didn\'t go through. Nothing was bought.';
 if(here){s.fail=why;hap('error');sbPaint();}else{hap('error');toast(why,7000,'bad');}}
function sbClose(){closeModal();S.sb=null;}
function lineFromBoard(t){sbOpen(t,S.lg);}
