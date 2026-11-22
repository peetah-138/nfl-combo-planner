/* The knob registry (issue #228, PR1): Results › What's working › Selling lists every number smart sell, the loss
   guards, auto-hedge and Smart Buy decide with: its value now (per league where it already learns by league), where
   it starts, the widest it may ever go, and the things that never move by themselves. Read-only: the only controls
   are the fold and the league chips, which change what is shown, never a setting. */
function knobCard(kv){if(!kv||!kv.knobs||!kv.knobs.length)return '';const o=!!S.knOpen;const ks=kv.knobs;
 const tun=ks.filter(k=>k.cls==='tunable'||k.cls==='setting'),inv=ks.filter(k=>k.cls==='invariant'),ev=ks.filter(k=>k.cls==='evidence');
 const lgs=kv.leagues||[{key:'all',name:'Everything'}];const lg=lgs.some(l=>l.key===S.knLg)?S.knLg:'all';
 const nl=tun.filter(k=>k.values).length;
 const head=`<button class="knh" aria-expanded="${o}" onclick="knTog()" style="all:unset;position:relative;box-sizing:border-box;display:flex;align-items:center;gap:8px;width:100%;min-height:44px;cursor:pointer"><span class="chev" aria-hidden="true">▾</span><b style="font-size:15px">🎛️ The numbers selling runs on</b><span class="m" style="margin-left:auto;font-size:12.5px">${tun.length} numbers · ${inv.length} never move</span></button>`;
 if(!o)return `<div class="knp" style="margin-top:14px;border-top:1px solid var(--line);padding-top:4px">${head}</div>`;
 const val=k=>k.values?(k.values[lg]||k.values.all||{}):(k.value||{});
 const rng=k=>k.min_say==null&&k.max_say==null?'':` · range ${esc(k.min_say==null?'—':k.min_say)} to ${esc(k.max_say==null?'no limit':k.max_say)}`;
 const row=k=>{const v=val(k);const moved=k.values&&v.from&&v.from!=='starting point'&&!/^off until/.test(v.from);
  return `<div class="knr" data-k="${esc(k.name)}" style="padding:9px 0;border-top:1px solid var(--line)"><div style="display:flex;gap:10px;align-items:baseline"><b style="font-size:13.5px;min-width:0;overflow-wrap:anywhere">${esc(k.label)}</b><b class="knv" style="margin-left:auto;font-size:14px;white-space:nowrap">${esc(v.say||'—')}</b></div>
  ${k.what?`<div class="m" style="font-size:12px;margin-top:2px;line-height:1.4">${esc(k.what)}</div>`:''}
  <div class="m knf" style="font-size:11.5px;margin-top:3px">Starts at ${esc(k.start_say)}${rng(k)} · <span class="${moved?'tag good':''}" style="${moved?'font-size:11px':''}">${esc(v.from||'')}</span>${k.learned_say?` · learns ${esc(k.learned_say)}`:''}</div></div>`;};
 const groups=(kv.groups||[]).map(g=>{const rs=tun.filter(k=>k.group===g.key);return rs.length?`<h3 style="margin:16px 0 2px;font-size:14.5px">${esc(g.name)}</h3>${rs.map(row).join('')}`:'';}).join('');
 const chips=lgs.length>1?`<div class="knlg" role="group" aria-label="League" style="display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 2px">${lgs.map(l=>`<button class="chip${l.key===lg?' on':''}" aria-pressed="${l.key===lg}" onclick="knLg('${esc(l.key)}')">${esc(l.name)}</button>`).join('')}</div>`:'';
 const e=kv.evidence||{},b=kv.brake||{};
 return `<div class="knp" style="margin-top:14px;border-top:1px solid var(--line);padding-top:4px">${head}
  <div class="m" style="font-size:12.5px;margin:2px 0 8px;line-height:1.45">Every number smart sell, the loss guards, hedging and Smart Buy decide with, and where each stands now. ${nl} already learn league by league from each league's own results, in small steps. The rest are fixed for now. Later each may move too, only inside its range, only when at least ${e.band_n||10} bets show a gain of ${Math.round((e.gain||0.02)*100)}% of what was staked, ${e.se||2} standard errors clear of luck, on bets it didn't learn from, and a number borrowed from another league is never looser than its start. After ${b.losses||4} automatic losses in a row, or ${Math.round((b.month_share||0.05)*100)}% of the month's automatic-sale stake lost, a league would go back to its starting numbers for ${b.days||14} days. None of that is switched on yet.</div>
  ${chips}${groups}
  <h3 style="margin:18px 0 2px;font-size:14.5px">The bar a change must clear</h3>${ev.map(k=>`<div class="knr" data-k="${esc(k.name)}" style="display:flex;gap:10px;align-items:baseline;padding:7px 0;border-top:1px solid var(--line)"><span style="font-size:13px;min-width:0">${esc(k.label)}</span><b style="margin-left:auto;font-size:13.5px;white-space:nowrap">${esc((k.value||{}).say||k.start_say)}</b></div>`).join('')}
  <h3 style="margin:18px 0 2px;font-size:14.5px">Never moves by itself</h3><div class="m" style="font-size:12.5px;margin-bottom:4px">Safety rules. No record, however good, changes these.</div>${inv.map(k=>`<div class="knr kni" data-k="${esc(k.name)}" style="padding:7px 0;border-top:1px solid var(--line)"><div style="display:flex;gap:10px;align-items:baseline"><b style="font-size:13px;min-width:0">${esc(k.label)}</b>${k.unit==='rule'?'':`<b style="margin-left:auto;font-size:13.5px;white-space:nowrap">${esc((k.value||{}).say||k.start_say)}</b>`}</div><div class="m" style="font-size:12px;margin-top:2px">${esc(k.why||'')}</div></div>`).join('')}</div>`;}
function knTog(){S.knOpen=!S.knOpen;renderResults();}
function knLg(k){if(S.knLg===k)return;S.knLg=k;renderResults();}
