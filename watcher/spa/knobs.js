/* The knob registry (issue #228, PR1): Results › What's working › Selling lists every number smart sell, the loss
   guards, auto-hedge and Smart Buy decide with: its value now (per league where it already learns by league), where
   it starts, the widest it may ever go, and the things that never move by themselves. Read-only: the only controls
   are the fold and the league chips, which change what is shown, never a setting. */
function knobCard(kv){if(!kv||!kv.knobs||!kv.knobs.length)return '';const o=!!S.knOpen;const ks=kv.knobs;
 const tun=ks.filter(k=>k.cls==='tunable'||k.cls==='setting'),inv=ks.filter(k=>k.cls==='invariant'),ev=ks.filter(k=>k.cls==='evidence');
 const lgs=kv.leagues||[{key:'all',name:'Everything'}];const lg=lgs.some(l=>l.key===S.knLg)?S.knLg:'all';
 const nl=tun.filter(k=>k.values).length;
 const head=`<button class="knh" aria-expanded="${o}" onclick="knTog()" style="all:unset;position:relative;box-sizing:border-box;display:flex;align-items:center;gap:8px;width:100%;min-height:44px;cursor:pointer"><span class="chev" aria-hidden="true">▾</span><b style="font-size:15px">🎛️ The numbers smart sell and Smart Buy run on</b><span class="m" style="margin-left:auto;font-size:12.5px">${tun.length} numbers · ${inv.length} never move</span></button>`;
 if(!o)return `<div class="knp" style="margin-top:14px;border-top:1px solid var(--line);padding-top:4px">${head}</div>`;
 const val=k=>k.values?(k.values[lg]||k.values.all||{}):(k.value||{});
 const rng=k=>k.min_say==null&&k.max_say==null?'':` · range ${esc(k.min_say==null?'—':k.min_say)} to ${esc(k.max_say==null?'no limit':k.max_say)}`;
 const row=k=>{const v=val(k);const moved=k.values&&v.from&&v.from!=='starting point'&&!/^off until/.test(v.from);
  return `<div class="knr" data-k="${esc(k.name)}" style="padding:9px 0;border-top:1px solid var(--line)"><div style="display:flex;gap:10px;align-items:baseline"><b style="font-size:13.5px;min-width:0;overflow-wrap:anywhere">${esc(k.label)}</b><b class="knv" style="margin-left:auto;font-size:14px;white-space:nowrap">${esc(v.say||'—')}</b></div>
  ${k.what?`<div class="m" style="font-size:12px;margin-top:2px;line-height:1.4">${esc(k.what)}</div>`:''}
  <div class="m knf" style="font-size:11.5px;margin-top:3px">${k.unit==='rule'?'Starts '+esc(k.start_say):'Starts at '+esc(k.start_say)}${rng(k)} · <span class="${moved?'tag good':''}" style="${moved?'font-size:11px':''}">${esc(v.from||'')}</span>${k.learned_say?` · learns ${esc(k.learned_say)}`:''}${k.shared_with?` · also used for ${esc(String(k.shared_with).replace(/\s*\([^)]*\)/g,''))}`:''}</div></div>`;};
 const groups=(kv.groups||[]).map(g=>{const rs=tun.filter(k=>k.group===g.key);return rs.length?`<h3 style="margin:16px 0 2px;font-size:14.5px">${esc(g.name)}</h3>${rs.map(row).join('')}`:'';}).join('');
 const chips=lgs.length>1?`<div class="knlg" role="group" aria-label="League" style="display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 2px">${lgs.map(l=>`<button class="chip${l.key===lg?' on':''}" aria-pressed="${l.key===lg}" data-k="${esc(l.key)}" onclick="knLg(this.dataset.k)" style="min-height:44px">${esc(l.name)}</button>`).join('')}</div>`:'';
 const N=(x,d)=>{const n=Number(x);return isFinite(n)?n:d;};const e0=kv.evidence||{},b0=kv.brake||{};
 const e={band_n:N(e0.band_n,10),gain:N(e0.gain,0.02),se:N(e0.se,2)},b={losses:N(b0.losses,4),month_share:N(b0.month_share,0.05),days:N(b0.days,14)};
 return `<div class="knp" style="margin-top:14px;border-top:1px solid var(--line);padding-top:4px">${head}
  <div class="m" style="font-size:12.5px;margin:2px 0 8px;line-height:1.45">Every number smart sell, the loss guards, hedging and Smart Buy decide with, and where each stands now. ${Number(nl)} already learn league by league from each league's own results, in small steps. The rest are fixed for now. Later each may move too, only inside its range, only when at least ${e.band_n||10} bets show a gain of ${Math.round((e.gain||0.02)*100)}% of what was staked, ${e.se||2} standard errors clear of luck, on bets it didn't learn from, and a number borrowed from another league is never looser than its start (today the profit floor and risk weight still borrow either way). After ${b.losses||4} automatic losses in a row, or ${Math.round((b.month_share||0.05)*100)}% of the month's automatic-sale stake lost, a league would go back to its starting numbers for ${b.days||14} days. None of that is switched on yet.</div>
  ${chips}${groups}
  <h3 style="margin:18px 0 2px;font-size:14.5px">The bar a change must clear</h3>${ev.map(k=>`<div class="knr" data-k="${esc(k.name)}" style="display:flex;gap:10px;align-items:baseline;padding:7px 0;border-top:1px solid var(--line)"><span style="font-size:13px;min-width:0">${esc(k.label)}</span><b style="margin-left:auto;font-size:13.5px;white-space:nowrap">${esc((k.value||{}).say||k.start_say)}</b></div>`).join('')}
  <h3 style="margin:18px 0 2px;font-size:14.5px">Never moves by itself</h3><div class="m" style="font-size:12.5px;margin-bottom:4px">Safety rules. No record, however good, changes these.</div>${inv.map(k=>`<div class="knr kni" data-k="${esc(k.name)}" style="padding:7px 0;border-top:1px solid var(--line)"><div style="display:flex;gap:10px;align-items:baseline"><b style="font-size:13px;min-width:0">${esc(k.label)}</b>${k.unit==='rule'?'':`<b style="margin-left:auto;font-size:13.5px;white-space:nowrap">${esc((k.value||{}).say||k.start_say)}</b>`}</div><div class="m" style="font-size:12px;margin-top:2px">${esc(k.why||'')}</div></div>`).join('')}</div>`;}
function knTog(){S.knOpen=!S.knOpen;renderResults();}
function knLg(k){if(S.knLg===k)return;S.knLg=k;renderResults();}
/* What self-tuning would change (issue #228, PR2: a test run, not active yet). Once a week the Mac replays each
   league's settled bets with one number one step away and writes down the step only if it clears Pete's bar; the
   brake watches the app's own sales. Nothing here changes a setting: the only controls are the fold and the chips. */
function knobShadow(v){if(!v||!v.mode)return '';const o=!!S.ksOpen;const ls=(v.leagues||[]).filter(l=>l&&l.key);
 const nStep=ls.reduce((s,l)=>s+(l.steps||[]).length,0),nBrk=ls.filter(l=>l.brake).length;
 const meta=!v.at?'first run within a week':nStep?`${nStep} would change`:'nothing yet';
 const head=`<button class="ksh" aria-expanded="${o}" onclick="ksTog()" style="background:none;border:0;color:inherit;font:inherit;text-align:left;position:relative;box-sizing:border-box;display:flex;align-items:center;gap:8px;width:100%;min-height:44px;padding:0;cursor:pointer"><span class="chev" aria-hidden="true" style="display:inline-block;transition:transform .2s;transform:rotate(${o?0:-90}deg)">▾</span><b style="font-size:15px">🧪 What self-tuning would change</b><span class="m" style="margin-left:auto;font-size:12.5px;text-align:right">${esc(meta)}${nBrk?` · ${nBrk} brake${nBrk>1?'s':''}`:''}</span></button>`;
 if(!o)return `<div class="ksp" style="margin-top:14px;border-top:1px solid var(--line);padding-top:4px">${head}</div>`;
 const day=t=>{const n=Number(t);return isFinite(n)&&n>0?new Date(n*1000).toLocaleDateString([], {month:'short',day:'numeric'}):'';};
 const lg=ls.some(l=>l.key===S.ksLg)?S.ksLg:(ls[0]||{}).key;const L=ls.find(l=>l.key===lg);
 const chips=ls.length>1?`<div class="kslg" role="group" aria-label="League" style="display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 2px">${ls.map(l=>`<button class="chip${l.key===lg?' on':''}" aria-pressed="${l.key===lg}" data-k="${esc(l.key)}" onclick="ksLg(this.dataset.k)" aria-label="${esc(l.name)}${(l.steps||[]).length?', would change':''}" style="min-height:44px">${esc(l.name)}${(l.steps||[]).length?' <span aria-hidden="true" style="color:var(--acc)">•</span>':''}</button>`).join('')}</div>`:'';
 const item=(r,cls)=>`<div class="ksr ${cls}" data-k="${esc(r.knob)}" style="padding:9px 0;border-top:1px solid var(--line);font-size:13px;line-height:1.45;overflow-wrap:anywhere">${esc(r.say||'')}</div>`;
 const sec=(t,rs,cls,note)=>rs&&rs.length?`<h3 style="margin:14px 0 2px;font-size:14px">${esc(t)}</h3>${note?`<div class="m" style="font-size:12px;margin-bottom:2px">${esc(note)}</div>`:''}${rs.map(r=>item(r,cls)).join('')}`:'';
 let body='';
 if(!v.at)body=`<div class="m ksempty" style="font-size:13px;padding:8px 0">The first test run happens within a week of this update. It needs settled bets with recorded game prices, so a league with few results shows nothing for a while.</div>`;
 else if(!L)body=`<div class="m ksempty" style="font-size:13px;padding:8px 0">No league has enough settled bets for a test yet.</div>`;
 else{const b=L.brake;
  body=(b?`<div class="ksbrk" style="margin:8px 0;padding:10px 12px;border-radius:12px;background:var(--card2,rgba(127,127,127,.12));font-size:13px;line-height:1.45"><b>Brake (test):</b> ${esc(b.why)}. Once self-tuning is live, ${esc(L.name)} would stay at its starting numbers until ${esc(b.until_say||day(b.until))}.</div>`:'')
   +sec('Would change',L.steps,'kss','One step a week at most, inside each number\'s range.')
   +sec('Also clears the bar',L.also,'ksa','Waits its turn: one step a week per league.')
   +sec('Held back by the newest bets',L.vetoed,'ksv','It cleared the bar on all the bets, but not on the newest 30%, so it waits.')
   +((L.moved||[]).length?`<h3 style="margin:14px 0 2px;font-size:14px">Where the test has it now</h3>${L.moved.map(m=>`<div class="ksr ksm" data-k="${esc(m.knob)}" style="padding:8px 0;border-top:1px solid var(--line);font-size:13px"><div style="display:flex;gap:10px;align-items:baseline"><span style="min-width:0;flex:0 1 auto">${esc(m.label)}</span><b style="margin-left:auto;white-space:nowrap">${esc(m.say)}</b></div><div class="m" style="font-size:11.5px;margin-top:2px">Starts at ${esc(m.start)}</div></div>`).join('')}`:'')
   +(!(L.steps||[]).length&&!(L.also||[]).length&&!b?`<div class="m ksempty" style="font-size:13px;padding:10px 0 2px">Nothing would change in ${esc(L.name)} yet: no step has cleared the bar.</div>`:'')
   +(L.below?`<div class="m" style="font-size:12px;margin-top:8px">${Number(L.below)} other step${L.below>1?'s were':' was'} checked and didn't clear the bar.</div>`:'')
   +((L.thin||[]).length?`<div class="m" style="font-size:12px;margin-top:6px">Needs more results first: ${L.thin.map(t=>esc(t.say)).join(' · ')}.</div>`:'');}
  return `<div class="ksp" style="margin-top:14px;border-top:1px solid var(--line);padding-top:4px">${head}
  <div class="m" style="font-size:12.5px;margin:2px 0 8px;line-height:1.45">A test run: <b>nothing changes yet</b>. Once a week the Mac checks whether one small step would have done clearly better on each league's settled bets, judged against luck and on its newest bets too (the full bar is in the card below).${v.at?` Last looked ${esc(day(v.at))}${v.next?`, next ${esc(day(v.next))}`:''}.`:''}</div>
  ${v.why?`<div class="m kswhy" style="font-size:12px;margin:0 0 6px">${esc(v.why)}</div>`:''}${chips}${body}
  <div class="m" style="font-size:11.5px;margin-top:12px;line-height:1.45">Tested so far: ${esc((v.judged||[]).join(', '))}. ${(Number(v.waits)||0)+(v.shared||[]).length} more numbers wait for their own test.</div></div>`;}
function ksTog(){S.ksOpen=!S.ksOpen;renderResults();}
function ksLg(k){if(S.ksLg===k)return;S.ksLg=k;renderResults();}
