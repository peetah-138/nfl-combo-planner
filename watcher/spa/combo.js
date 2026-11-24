// ---------------- combo detail
async function openCombo(t){S.gameOpen=null;S.ideaOpen=null;S.comboOpen=t;pushOpen('Combo');
 const [r]=await Promise.all([api('/app/api/combo?t='+encodeURIComponent(t)).catch(()=>null),pushWait()]);if(S.comboOpen!==t)return;const c=r&&r.combo;
 if(!c){pushFill('<h3>Not found</h3><p>That combo isn\'t live any more.</p>','Combo');return;}
 const h=r.history||{offers:[],ticks:{}};const [vc,vt]=verdictOf(c);
 pushFill(`<div class="dhead"><div><div class="m" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase">${(c.sports||[]).map(s=>SPN[s]||s).join(' · ')}</div><h3 style="font-size:22px">${esc(c.label)}</h3><div class="m">${esc(nextLine(c))}</div></div>
  <div style="display:flex;gap:8px;align-items:center"><span class="verdict ${vc}">${vt}</span></div></div>
  <div class="dkpis"><div><span>Paid</span><b>${money(c.cost)}</b></div><div><span>Pays</span><b>${money(c.pays)}</b></div><div><span>Chance</span><b>${c.group==='pending'?`<span data-num="dp:${c.t}" data-v="${c.p}" data-f="pct">${pct(c.p)}</span>`:'—'}</b></div><div><span>${c.offer_real?'Offer':'Likely offer'}</span><b>${c.offer!=null?`<span data-num="do:${c.t}" data-v="${c.offer}" data-pre="${c.offer_real?'':'≈ '}">${(c.offer_real?'':'≈ ')+money(c.offer)}</span>`:'—'}</b></div></div>
  ${whyShown(c)?`<p style="margin:-4px 0 14px">${esc(whyShown(c))}</p>`:''}
  <div class="chartbox">${valueChart(h.offers,c.cost,c.pays)}</div>
  <h2 style="margin:4px 0 6px">Picks <span class="n">${c.legs.length}</span></h2><div class="dlegs">${c.legs.map(l=>{const tk=(h.ticks||{})[l.ticker]||[];const pts=tk.filter(x=>x.chance!=null).map(x=>[x.ts,x.chance]);
   return `<div class="lg"><div><b>${ICON[l.sport]||''} ${esc(betPlain(l))}</b><div class="m" style="font-size:12.5px">${l.matchup?betWhere(l)+' · ':l.opp?'vs '+esc(l.opp)+' · ':''}${esc(l.score||(!l.res&&l.note)||l.starts||(l.res==='yes'?'won':l.res==='no'?'lost':''))}</div></div>
    ${l.res?`<span class="m" style="text-align:center">${l.res==='yes'?'✓ won':'✕ lost'}</span>`:spark(pts,120,28)}<b style="text-align:right">${l.res?'':pct(l.live!=null?l.live:l.chance)}</b></div>`;}).join('')}</div>
  ${c.group==='pending'?`<div class="row" style="margin-top:16px;flex-wrap:wrap">${c.hedge&&!c.hedge.done?`<button class="btn" onclick="closeModal();hedge('${c.t}')">Hedge · ${money(c.hedge.cost)}</button>`:''}
   <button class="btn" onclick="closeModal();ask('${c.t}')">${c.offer_real?'New offer':'Get cash-out offer'}</button>${c.offer_real?`<button class="btn yes" onclick="closeModal();sell('${c.t}')">Cash out ${money(c.offer)}</button>`:''}</div>`:''}`,c.label);}
