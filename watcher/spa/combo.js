// ---------------- combo detail
async function openCombo(t){S.gameOpen=null;S.ideaOpen=null;S.comboOpen=t;pushOpen('Combo');
 const [r]=await Promise.all([api('/app/api/combo?t='+encodeURIComponent(t)).catch(()=>null),pushWait()]);if(S.comboOpen!==t)return;const c=r&&r.combo;
 if(!c){closedFill(t,'Combo');return;}
 const h=r.history||{offers:[],ticks:{}};const [vc,vt]=verdictOf(c);
 pushFill(`<div class="dhead"><div><div class="m" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase">${(c.sports||[]).map(s=>SPN[s]||s).join(' · ')}</div><h3 style="font-size:22px">${esc(c.label)}</h3><div class="m">${esc(nextLine(c))}</div></div>
  <div style="display:flex;gap:8px;align-items:center"><span class="verdict ${vc}">${vt}</span></div></div>
  <div class="dkpis"><div><span>Paid</span><b>${money(c.cost)}</b></div><div><span>Pays</span><b>${money(c.pays)}</b></div><div><span>Chance</span><b>${c.group==='pending'?`<span data-num="dp:${c.t}" data-v="${c.p}" data-f="pct">${pct(c.p)}</span>`:'—'}</b></div><div><span>${c.offer_real?'Offer':'Likely offer'}</span><b>${c.offer!=null?`<span data-num="do:${c.t}" data-v="${c.offer}" data-pre="${c.offer_real?'':'≈ '}">${(c.offer_real?'':'≈ ')+money(c.offer)}</span>`:'—'}</b></div></div>
  ${whyShown(c)?`<p style="margin:-4px 0 14px">${esc(whyShown(c))}</p>`:''}
  <div class="chartbox">${valueChart(h.offers,c.cost,c.pays)}</div>
  <h2 style="margin:4px 0 6px">Picks <span class="n">${c.legs.length}</span></h2><div class="dlegs">${c.legs.map(l=>{const tk=(h.ticks||{})[l.ticker]||[];const pts=tk.filter(x=>x.chance!=null).map(x=>[x.ts,x.chance]);
   return `<div class="lg"><div><b>${ICON[l.sport]||''} ${esc(betPlain(l))}</b><div class="m" style="font-size:12.5px">${l.matchup?betWhere(l)+' · ':l.opp?'vs '+esc(l.opp)+' · ':''}${esc(l.score||(!l.res&&l.note)||l.starts||(l.res==='yes'?'won':l.res==='no'?'lost':''))}</div></div>
    ${l.res?`<span class="m" style="text-align:center">${l.res==='yes'?'✓ won':'✕ lost'}</span>`:spark(pts,120,28)}<b style="text-align:right">${l.res?'':pct(l.live!=null?l.live:l.chance)}</b></div>`;}).join('')}</div>
  ${c.group==='pending'?`<div class="row" style="margin-top:16px;flex-wrap:wrap">${c.hedge&&!c.hedge.done?`<button class="btn" data-t="${esc(c.t)}" onclick="var t=this.dataset.t;closeModal();hedge(t)">Hedge · ${money(c.hedge.cost)}</button>`:''}
   <button class="btn" data-t="${esc(c.t)}" onclick="var t=this.dataset.t;closeModal();ask(t)">${c.offer_real?'New offer':'Get cash-out offer'}</button>${c.offer_real?`<button class="btn yes" data-t="${esc(c.t)}" onclick="var t=this.dataset.t;closeModal();sell(t)">Cash out ${money(c.offer)}</button>`:''}</div>`:''}`,c.label);}

// ---------------- a bet that has closed (sold, settled or expired): read-only detail from what the Mac stored
function closedWhen(a){return esc(a.when||'')}
async function openClosed(t){S.gameOpen=null;S.ideaOpen=null;S.comboOpen=t;pushOpen('Bet');await pushWait();if(S.comboOpen!==t)return;await closedFill(t,'Bet');}
async function closedFill(t,title){const r=await api('/app/api/closed?t='+encodeURIComponent(t)).catch(()=>null);if(S.comboOpen!==t)return;
 /* (#406) no answer at all (the phone couldn't reach the Mac, or it sent something unreadable) is not "no record": say so and offer a retry */
 if(!r||typeof r!=='object'||r.found===undefined){pushFill(`<h3>Couldn't load that bet</h3><p>Your phone couldn't reach the Mac just now. The bet is fine; this is only the page.</p><div class="row"><button type="button" class="btn acc" data-t="${esc(t)}" data-title="${esc(title)}" onclick="this.disabled=true;this.textContent='Trying…';closedFill(this.dataset.t,this.dataset.title)">Try again</button></div>`,title);return;}
 if(!r.found){pushFill('<h3>We can\'t find that bet</h3><p>It isn\'t live and the Mac has no record of it.</p>',title);return;}
 const pl=r.pl,win=pl!=null&&pl>0,tag=pl==null?'':win?'good':pl<0?'bad':'';
 const picks=(r.picks||[]).map(p=>`<div class="lg"><div><b>${esc(p.name||'')}</b></div><span class="mark ${p.res==='yes'?'yes':p.res==='no'?'no':''}">${p.res==='yes'?'won':p.res==='no'?'lost':''}</span></div>`).join('');
 const at=(r.attempts||[]).map(a=>`<div class="srow"><div class="l"><b>${esc(a.when||'')} · ${esc(a.result||'')}${a.why?' · '+esc(a.why):''}</b>${a.note?`<small>${esc(a.note)}</small>`:''}${(a.tries||[]).map((x,i)=>`<small>Try ${i+1}: ${x.offer!=null?money(x.offer):''} ${esc(x.quote||'')}${x.error?' ('+esc(x.error)+')':''}</small>`).join('')}</div></div>`).join('');
 const lg=(r.sports||[]).map(x=>SPN[x]||x.toUpperCase()).join(' · ')||'Closed bet',big=esc(r.label||(r.kind==='combo'?'Combo':'Single bet')),pc=r.pl_pct;
 pushFill(`<div class="ccard ${tag}"><div class="cc-lg">${(r.sports||[]).map(x=>ICON[x]||'').join('')} ${esc(lg)}</div>
  ${r.game?`<div class="cc-gm">${esc(r.game)}</div>`:''}
  <div class="cc-bet"><b>${big}</b>${r.chance!=null?`<span>${pct(r.chance)} chance</span>`:''}</div>
  <div class="cc-nums"><div><span>Cost</span><b>${r.cost!=null?money(r.cost):'?'}</b></div><div class="${tag}"><span>${r.status==='cashed'?'Sold for':'Paid out'}</span><b>${r.back!=null?money(r.back):'?'}</b></div></div>
  <div class="cc-pl"><span>Profit</span><b class="${tag}">${pl==null?'unknown':(pl<0?'-':pl>0?'+':'')+money(Math.abs(pl))+(pc!=null?` (${pc>=0?'+':'-'}${Math.abs(pc).toFixed(2)}%)`:'')}</b></div>
  <div class="cc-ft"><span>${esc(r.closed||'')}</span><span class="cc-stamp">${esc(r.stamp||'CLOSED')}</span></div></div>
  <p style="margin:10px 0 14px">${esc(r.why||'')}</p>
  ${r.chart&&(r.chart.offers||[]).length>1?`<div class="chartbox">${valueChart(r.chart.offers,r.cost,r.pays)}</div>`:''}
  ${picks?`<h2 style="margin:4px 0 6px">Picks <span class="n">${(r.picks||[]).length}</span></h2><div class="dlegs">${picks}</div>`:''}
  ${at?`<h2 style="margin:14px 0 6px">What the auto-sell did <span class="n">${(r.attempts||[]).length}</span></h2>${at}`:''}`,title);}
