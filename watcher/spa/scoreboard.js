// ---------------- RESULTS › the profit scoreboard (issue #138) and the smart-sell scorecard (issue #115)
/* Real dollars only: every finished bet from Kalshi's own fills and settlements, after Kalshi's fees. Open bets are a
   separate, labelled estimate and never part of the profit. Groups under 20 bets are shown but marked "too few to trust".
   Read-only: nothing here buys or sells. Range and breakdown are remembered per phone. */
try{S.pbr=['week','month','all'].includes(localStorage.getItem('cw_pbr'))?localStorage.getItem('cw_pbr'):'all';S.pbt=localStorage.getItem('cw_pbt')||'type'}catch(e){S.pbr='all';S.pbt='type'}
const PBT=[['type','Bet type'],['league','League'],['end','How it ended'],['source','Source'],['price','Price quality'],['stake','Stake']];
function pbSet(k,v){if(S[k]===v)return;S[k]=v;try{localStorage.setItem(k==='pbr'?'cw_pbr':'cw_pbt',v)}catch(e){}S.pbJust=k;
 const old=document.querySelector('.pb .pbb'),b=(S.res||{}).board,p=b&&b.periods&&(b.periods[S.pbr]||b.periods.all);
 if(k==='pbt'&&old&&p){const h=old.offsetHeight;old.outerHTML=pbBreak(p);const nw=document.querySelector('.pb .pbb');if(nw){nw.style.minHeight=h+'px';setTimeout(()=>{if(nw.isConnected)nw.style.minHeight='';},400);}}else renderResults();S.pbJust=null;
 if(!matchMedia('(prefers-reduced-motion: reduce)').matches)document.querySelectorAll('.pb .pbbody .anrow').forEach((r,i)=>{r.style.animation=`rise .34s var(--ease) ${Math.min(i,10)*28}ms both`;});}
const pbRoi=x=>x==null?'<span class="m">—</span>':`<b class="${x>=0?'up':'down'}">${x>=0?'+':'−'}${Math.abs(x*100).toFixed(Math.abs(x)<.1?1:0)}%</b>`;
const pbFew=r=>r&&r.few?' <span class="few">too few to trust</span>':'';
const pbDay=d=>d?new Date(d+'T12:00:00').toLocaleDateString([], {weekday:'short',month:'short',day:'numeric'}):'';
const pbHold=h=>h==null?'—':h<1?Math.max(1,Math.round(h*60))+' min':h<48?(h<10?h.toFixed(1):Math.round(h))+' h':Math.round(h/24)+' days';
function pbSkel(){return `<div class="card pb" aria-busy="true"><div class="pbh"><h2>💵 Profit scoreboard</h2></div><div class="ansk" aria-label="Loading"><i style="height:44px;width:46%;border-radius:10px"></i><i style="width:70%"></i><i style="height:84px;border-radius:12px"></i><i style="width:88%"></i><i style="width:64%"></i></div></div>`;}
function pbBlock(b,an){if(b===undefined)return pbSkel();
 if(b===null)return `<div class="card pb"><div class="pbh"><h2>💵 Profit scoreboard</h2></div><div class="m" style="padding:4px 0 2px">The Mac couldn't read your betting record just now. It tries again on the next refresh.</div></div>`;
 if(!b.n)return `<div class="card pb empty" data-ic="💵"><b>Your profit scoreboard</b>Real profit in dollars, after Kalshi's fees, fills in here as your bets settle or sell: by week and month, by bet type and league, and what selling early did against holding.<br><button class="btn acc" onclick="go('build')">See today's bets</button></div>`;
 const P=b.periods||{},r=S.pbr,p=P[r]||P.all||{};const lab={week:'this week',month:'this month',all:'all time'}[r];
 const sw=`<div class="seg pbr" role="tablist" aria-label="Period">${[['week','Week'],['month','Month'],['all','All time']].map(([k,l])=>`<button role="tab" aria-selected="${r===k}" class="${r===k?'on':''}" onclick="pbSet('pbr','${k}')">${l}</button>`).join('')}</div>`;
 const pl=p.pl||0,sign=pl>=0?'+':'−';
 const big=`<div class="pbbig"><b class="${pl>=0?'up':'down'}" data-num="pb:pl" data-v="${Math.abs(pl).toFixed(2)}" data-pre="${sign}">${smoney(pl)}</b>
  <span class="pill ${p.roi==null?'':p.roi>=0?'up':'down'}" ${p.roi==null?'':`data-num="pb:roi" data-v="${p.roi}" data-f="spct"`}>${p.roi==null?'—':(p.roi>=0?'+':'−')+Math.abs(Math.round(p.roi*100))+'%'}</span><span class="m pbroi">return on ${money(p.staked||0)} staked</span></div>
  <div class="m pbsub" aria-live="polite">${p.n?`${p.n} finished bet${p.n===1?'':'s'} ${lab} · settled or sold, after ${money(p.fees||0)} of Kalshi fees${pbFew(p)}`:`Nothing finished ${lab} yet.`}</div>`;
 const day=(x,cls)=>x?`<b class="${cls}">${smoney(x.pl)}</b><small>${esc(pbDay(x.day))}</small>`:'<b class="m">—</b>';
 const kp=`<div class="pbk"><div><span>Days up · down</span><b><span class="up">${p.up||0}</span> <span class="m">·</span> <span class="down">${p.down||0}</span></b><small>of ${p.days||0} with results</small></div>
  <div><span>Best day</span>${day(p.best,'up')}</div><div><span>Worst day</span>${day(p.worst,p.worst&&p.worst.pl<0?'down':'up')}</div>
  <div><span>Made money</span><b>${p.n?Math.round(p.won/p.n*100)+'%':'—'}</b><small>${p.won||0} of ${p.n||0} bets</small></div></div>`;
 const o=b.open;const open=o?`<div class="pbopen"><span>Open bets, not counted above</span><b>≈ ${money(o.worth)}</b><small>if sold now (an estimate) · ${money(o.staked)} in</small></div>`:'';
 const sc=b.scorecard||{},st=sc.total||{},vh=p.vs_hold||{};const sb=(an&&an.smart_buy&&Array.isArray(an.smart_buy.gate))?an.smart_buy.gate:null;
 const sbSaved=sb?sb.reduce((s,g)=>s+(+g.saved||0),0):null,sbSkip=sb?sb.reduce((s,g)=>s+(+g.skipped||0),0):0;
 const smart=`<div class="pbsm"><div><span>🤖 Smart Sell vs holding, all time</span>${st.done?`<b class="${st.gain>=0?'up':'down'}">${smoney(st.gain)}</b><small>over ${st.done} automatic sale${st.done===1?'':'s'} whose games are over${st.n>st.done?` · ${st.n-st.done} still being followed`:''}${pbFew(st)}</small>`:`<b class="m">—</b><small>${st.n?`${st.n} sale${st.n===1?'':'s'} waiting for their games to finish`:'No automatic sales yet'}</small>`}</div>
  <div><span>🧠 Smart Buy skips (paper)</span>${sb&&sbSkip?`<b class="${sbSaved>=0?'up':'down'}">${sbSaved>=0?'would have saved ':'would have cost '}${money(Math.abs(sbSaved))}</b><small>${sbSkip} bet${sbSkip===1?'':'s'} skipped, scored on paper at $5 each, not real dollars${sbSkip<20?' <span class="few">too few to trust</span>':''}</small>`:`<b class="m">—</b><small>${an&&an.smart_buy&&an.smart_buy.on===false?'Switched off in Settings':'Nothing skipped yet'}</small>`}</div>
  ${vh.n?`<div><span>Every sale vs holding, ${esc(lab)}</span><b class="${vh.gain>=0?'up':'down'}">${smoney(vh.gain)}</b><small>${vh.n} sold bet${vh.n===1?'':'s'}, yours and smart sell's, after the fee</small></div>`:''}</div>`;
 return `<div class="card pb"><div class="pbh"><h2>💵 Profit scoreboard</h2>${sw}</div>${big}${kp}${pbCurve(b.curve||[])}${open}${smart}${pbBreak(p)}</div>`;}
/* The running total of realized profit, day by day: drag a finger across it for that day's total (a tick per day). */
function pbCurve(c){if(!c||c.length<2)return '';const n=c.length,W=340,H=86,vs=c.map(x=>x[1]),lo=Math.min(0,...vs),hi=Math.max(0,...vs),sp=Math.max(1e-6,hi-lo);
 const X=i=>i/(n-1)*W,Y=v=>6+(H-12)*(1-(v-lo)/sp),last=vs[n-1],col=last>=0?'var(--yes)':'var(--no)';
 const path=c.map((x,i)=>`${i?'L':'M'}${X(i).toFixed(1)} ${Y(x[1]).toFixed(1)}`).join('');
 S.scr=S.scr||{};S.scr.pbc={n,at:f=>Math.min(n-1,Math.round(f*(n-1))),x:i=>X(i)/W*100,y:i=>Y(vs[i])/H*100,lab:i=>`${pbDay(c[i][0])} · ${smoney(vs[i])}`};
 return `<div class="pbc"><div class="m pbcl"><span>Running total, all time</span><span>${esc(pbDay(c[0][0]))} – ${esc(pbDay(c[n-1][0]))}</span></div>
  <div class="scrub" data-scrub="pbc" aria-label="Running total of realized profit"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><line x1="0" x2="${W}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--line)" stroke-dasharray="3 4" vector-effect="non-scaling-stroke"/>
  <path d="${path} L${W} ${H} L0 ${H}Z" fill="${col}" opacity=".10"/><path class="pbline${S.pbDrawn?'':' draw'}" d="${path}" fill="none" stroke="${col}" stroke-width="2.2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>
  <i class="scrl"></i><i class="scrd"></i><span class="sread"></span></div></div>`+(S.pbDrawn=true,'');}
function pbBreak(p){const t=S.pbt,by=p.by||{},say=p.say||{};
 const tabs=`<div class="seg ant pbt" role="tablist" aria-label="Breakdown">${PBT.map(([k,l])=>`<button role="tab" aria-selected="${t===k}" class="${t===k?'on':''}" onclick="pbSet('pbt','${k}')">${l}</button>`).join('')}</div>`;
 const tb=(head,rows,empty)=>`<div class="antbl"><div class="anrow h">${head.map(h=>`<div>${h}</div>`).join('')}</div>${rows.map(cs=>`<div class="anrow">${cs.map((c,i)=>`<div data-l="${i?esc(head[i]):''}">${c}</div>`).join('')}</div>`).join('')||`<div class="m" style="padding:10px 0">${empty||'Nothing finished in this period yet.'}</div>`}</div>`;
 const grp=(k,first,extra)=>{const rs=by[k]||[];return tb([first,'Bets','Profit','Return','Made money','Avg hold'].concat(extra?extra.h:[]),
  rs.map(x=>[`<b>${esc(x.name)}</b>${pbFew(x)}`,x.n,`<b class="${x.pl>=0?'up':'down'}">${smoney(x.pl)}</b>`,pbRoi(x.roi),Math.round(x.won*100)+'%',pbHold(x.hold)].concat(extra?extra.c(x):[])))
  +(say[k]?`<p class="pbsay">${esc(say[k])}</p>`:'');};
 let body='',ex='';
 if(t==='type'){ex='Every finished bet with real money, by kind. Paper is the paper panel over the same period, for comparison (the combo lab is left out: it tests prices under the cut-off).';
  const hasP=(by.type||[]).some(x=>x.paper_n);if(!hasP)ex='Every finished bet with real money, by kind.';
  body=grp('type','Bet type',hasP?{h:['Paper'],c:x=>[x.paper_n?`${pbRoi(x.paper_roi)} <span class="m">(${x.paper_n})</span>`:'<span class="m">—</span>']}:null);}
 else if(t==='league'){ex='The same bets by league. A combo across leagues counts as Mixed.';body=grp('league','League');}
 else if(t==='end'){ex='How each bet finished. For sold bets, "vs holding" is what selling made compared with riding it to the end, once the games are over.';
  const hd=p.held,hs=hd?`<p class="pbheld">${esc(hd.line)}${hd.few?' <span class="few">small sample</span>':''}</p>`:'',hh=hd&&hd.hist?`<p class="pbheld pbhi"><b>Could have been sold higher</b> ${esc(hd.hist.line)}${hd.hist.few?' <span class="few">small sample</span>':''}</p>`:'';
  body=hs+grp('end','How it ended',{h:['vs holding'],c:x=>[x.vs_n?`<b class="${x.vs>=0?'up':'down'}">${smoney(x.vs)}</b> <span class="m">(${x.vs_n})</span>`:'<span class="m">—</span>']})+hh;}
 else if(t==='source'){ex='Where each bet came from. Build and Live ideas are counted together for now.';body=grp('source','Source');}
 else if(t==='stake'){ex='By how much was staked on the bet, fees included.';body=grp('stake','Stake');}
 else{const q=p.quality||{},rq=q.real||{},pq=q.paper||{};ex='From the panel\'s own record: what it expected each bet to return, against what it did. The paper panel is shown apart, since it tests the same prices.';
  const clv=(x,n)=>x==null?'<span class="m">—</span>':`${pbRoi(x)} <span class="m">(${n})</span>`;
  body=`<div class="pbclv"><div><span>Prices vs the close, your panel</span>${clv(rq.clv,rq.clv_n)}</div><div><span>Prices vs the close, paper</span>${clv(pq.clv,pq.clv_n)}</div></div><div class="m" style="font-size:12px;margin:2px 0 10px">Above 0% means the market moved your way after you bought: the earliest honest sign of an edge.</div>`
   +['real','paper'].map(m=>{const x=q[m]||{};return `<h3 class="pbq">${m==='real'?'Your panel':'Paper panel'}: expected vs actual return</h3>`
    +tb(['Expected edge','Bets','Expected','Actual'],(x.edge||[]).map(e=>[`<b>${esc(e.name)}</b>${pbFew(e)}`,e.n,pbRoi(e.pred),pbRoi(e.roi)]),'No settled panel bets in this period.')
    +`<h3 class="pbq">${m==='real'?'Your panel':'Paper'}: chance it wins, predicted vs how often it won</h3>`
    +tb(['League','Bets','Predicted','Won'],(x.cal||[]).map(e=>[`<b>${esc(e.name)}</b>${pbFew(e)}`,e.n,pct(e.pred),pct(e.hit)]),'No settled panel bets in this period.')
    +`<h3 class="pbq">${m==='real'?'Your panel':'Paper'}: when it was bought</h3>`
    +tb(['Bought','Bets','Profit','Return'],(x.timing||[]).map(e=>[`<b>${esc(e.name)}</b>${pbFew(e)}`,e.n,`<b class="${e.pl>=0?'up':'down'}">${smoney(e.pl)}</b>`,pbRoi(e.roi)]),'No settled panel bets in this period.');}).join('');}
 return `<div class="pbb"><h3 style="margin:18px 0 8px;font-size:15px">What's making money</h3>${tabs}<div class="pbbody ${S.pbJust==='pbt'?'antab':''}"><div class="m" style="font-size:12.5px;margin:4px 0 10px;line-height:1.45">${ex}</div>${body}</div></div>`;}
/* What's working › Selling: each automatic sale against what holding would have paid, per league and reason (#115). */
function scoreCard(sc){if(!sc||!sc.total)return '';const t=sc.total,m=sc.mine||{},rd=sc.rode||{};
 const WHY={smart:'Smart sell','lock in':'Locked in a run-up','take profit':'Take profit',checkpoint:'Checkpoint','cut loss':'Cut a loss',plan:'Cash-out plan'};
 const rows=(sc.rows||[]).map(x=>[`<b>${esc(x.name)}</b> <span class="m">${esc(WHY[x.why]||x.why)}</span>${x.few&&x.done?' <span class="few">too few to trust</span>':''}`,
  `${x.n}${x.n>x.done?` <span class="m">(${x.n-x.done} waiting)</span>`:''}`,x.done?money(x.sold):'—',x.done?money(x.held):'—',x.done?`<b class="${x.gain>=0?'up':'down'}">${smoney(x.gain)}</b>`:'—',x.done?`${x.early} · ${x.right}`:'—']);
 const head=['League and reason','Sales','Sold for','Holding paid','Selling gained','Too early · right'];
 return `<h3 class="sc-h" style="margin:18px 0 4px;font-size:15px">Smart sell's scorecard</h3><div class="m" style="font-size:12.5px;margin-bottom:6px">Every automatic sale, followed to the end of its games: what it sold for (Kalshi's own record, after the fee) against what holding would have paid. "Too early" means holding would have paid more.</div>
  ${t.done?`<div class="pbsc"><b class="${t.gain>=0?'up':'down'}">${smoney(t.gain)}</b><span>from selling instead of holding, over ${t.done} sale${t.done===1?'':'s'} · ${t.early} too early (${money(t.early_usd||0)} left on the table) · ${t.right} right${t.few?' · <span class="few">too few to trust</span>':''}</span></div>`:''}
  <div class="antbl"><div class="anrow h">${head.map(h=>`<div>${h}</div>`).join('')}</div>${rows.map(cs=>`<div class="anrow">${cs.map((c,i)=>`<div data-l="${i?esc(head[i]):''}">${c}</div>`).join('')}</div>`).join('')||`<div class="m" style="padding:10px 0">${sc.following?`${sc.following} sale${sc.following===1?' is':'s are'} waiting for their games to finish.`:'No automatic sales yet. Each one shows up here once its games are over.'}</div>`}</div>
  <div class="m sc-mine" style="margin-top:10px;font-size:13px">${m.done?`Sales you made yourself: <b class="${m.gain>=0?'up':'down'}">${smoney(m.gain)}</b> against holding, over ${m.done}${m.few?' (too few to trust)':''}.`:'No sales you made yourself have finished their games yet.'}</div>
  <div class="m sc-rode" style="margin-top:6px;font-size:13px">${rd.n?`Combos ridden to the end: the best real Kalshi offer seen added up to ${money(rd.best)}, against ${money(rd.final)} paid out on ${money(rd.cost)} staked; ${rd.above} of ${rd.n} had a real offer above what they cost${rd.few?' (too few to trust)':''}.`:'No ridden combo has a real Kalshi offer on record yet.'}</div>`;}
