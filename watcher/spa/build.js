// ---------------- BUILD
function buildSkel(){/* the panel's shape while it loads: header, a few bet rows with a price block, the Approve bar */
 return `<div class="card hsk" style="margin-bottom:14px"><i style="height:16px;width:42%"></i><i style="height:11px;width:70%"></i>${'<div style="display:grid;grid-template-columns:1fr 64px;gap:12px;align-items:center"><div style="display:grid;gap:6px"><i style="height:14px;width:80%"></i><i style="height:10px;width:50%"></i></div><i style="height:34px"></i></div>'.repeat(4)}<i style="height:44px;border-radius:12px"></i></div>`+skel(3);}
/* Build redraws itself often (picks, quotes, folds), so its numbers roll on every redraw, not only on page loads */
function renderBuild(){const keep=[...document.querySelectorAll('#main .ccard[data-ph]')].filter(n=>n.dataset.ph!=='idle');_renderBuild();
 keep.forEach(old=>{const nw=document.querySelector(`#main .ccard[data-i="${old.dataset.i}"]`);   // same card, same phase: keep the very same button (no flicker, no lost tap)
  if(nw&&nw!==old&&nw.dataset.ph===old.dataset.ph&&nw.dataset.sig===old.dataset.sig){nw.replaceWith(old);
   const q=S.quotes&&S.quotes[old.dataset.i];      // putting a node back restarts its CSS animations: keep the draining bar where it was, and don't replay the entrance
   old.querySelectorAll('.qline.new').forEach(e=>e.classList.remove('new'));
   if(q)old.querySelectorAll('.qt').forEach(t=>{t.style.animationDelay='-'+Math.max(0,Date.now()/1000-q.at).toFixed(2)+'s';});}});
 rollNums($('#main'));rbWatch();}
function _renderBuild(){const d=S.build;const m=$('#main');
 /* The chip row never changes while a league loads: the list of leagues and the per-league game counts are remembered
    (also on this phone) instead of read from the data that is cleared on a tap; the built-in list is only for a phone that has never loaded */
 if(d&&d.leagues&&d.leagues.length>1){S.lgs=d.leagues;try{localStorage.setItem('cw_leagues',JSON.stringify(d.leagues))}catch(e){}}
 if(S.panel){S.gn=S.panel.games||null;try{localStorage.setItem('cw_gn',JSON.stringify(S.gn))}catch(e){}}   /* a panel replaces the counts; none at all while one loads */
 const lgs=S.lgs||Object.keys(SPN).map(k=>[k,SPN[k],ICON[k]||'🎲']);
 const pv=S.pview||'all';const gameN=S.gn;const chipRow=`<div class="chips" style="margin-bottom:14px"><button class="chip ${pv==='all'?'on':''}" onclick="setPview('all')">⭐ All</button>${lgs.filter(([k])=>k!=='mix'&&(k===pv||k===S.lg||!gameN||gameN[k]==null||gameN[k]>0)).map(([k,n,i])=>`<button class="chip ${pv===k?'on':''}" onclick="setPview('${k}')">${esc(i||'')} ${esc(SPN[k]||n)}</button>`).join('')}</div>`;
 if(!d||d.lg!==S.lg){m.innerHTML=chipRow+((S.lerr||{}).build&&!d?errCard('build'):'<div class="grid"><div>'+buildSkel()+'</div><div class="skel" style="height:300px"></div></div>');return;}
 const best=bestBets(d);const adv=S.adv||S.slip.length>0;
 m.innerHTML=chipRow+`<div class="grid"><div>
  <div id="pblock">${panelBlock(S.panel)}</div>
  <button class="btn ghost" style="width:100%;margin:18px 0 6px;justify-content:center" onclick="toggleAdv()">${adv?'Hide the full board ▴':`Build your own · all ${d.board.length} games${(d.lines||[]).length?', spreads & totals':''} ▾`}</button>
  ${adv?`${secHead('games',`${esc(d.icon)} ${esc(d.name)} games`,d.board.length,'Kalshi price · fair chance from the sportsbooks')}
  ${secOpen('games')?`<div class="board">${d.board.map(g=>{const sc=g.sc;return `<div class="mrow ${g.started?'livegame':''}" data-key="b:${g.event}" data-sig="${sc?sc.me+'-'+sc.opp:''}"><div class="when">${SPN[g.sport]?`<div class="wlg">${ICON[g.sport]||''} ${esc(SPN[g.sport])}</div>`:''}${g.started?(sc?`<span class="lvsc"><i class="livedot"></i>${esc(sc.detail||'LIVE')}</span>`:'<span class="lvsc"><i class="livedot"></i>LIVE</span>'):esc(g.label||'')}</div>
   ${g.sides.filter(s=>!s.tie).map(s=>{const on=S.slip.includes(s.ticker);const mine=sc?(s.ticker===g.first?sc.me:sc.opp):null,their=sc?(s.ticker===g.first?sc.opp:sc.me):null;
    return `<button class="pickbtn ${on?'on':''} ${on&&S.justPicked===s.ticker?'pop':''} ${mine!=null?(mine>their?'lead':mine<their?'trail':''):''}" onclick="pick('${s.ticker}','${g.event}')"><span class="nm">${mine!=null?`<em class="scr">${mine}</em>`:''}<span class="full">${esc(s.pick)}</span><span class="short">${esc(short(s.pick))}</span>${s.edge!=null&&s.edge>=.01?'<span class="val">VALUE</span>':''}</span>
    <span class="pr"><b ${s.p!=null?`data-num="bp:${s.ticker}" data-v="${s.p}" data-f="cent"`:''}>${s.p!=null?Math.round(s.p*100)+'¢':'—'}</b><span>${s.fair!=null?'fair '+pct(s.fair):''}</span></span></button>`}).join('')}</div>`;}).join('')||'<div class="empty"><b>No games right now</b>Try another sport.</div>'}</div>`:''}
  ${linesBlock(d)}
  ${secHead('combos','More combo ideas',d.combos.length,'',`<button class="btn" id="rebuildb" onclick="event.stopPropagation();rebuild(this)">Rebuild</button>`)}
  ${secOpen('combos')?`<div class="m" style="font-size:12px;margin:-4px 2px 10px">Fairly priced combos built to your mix. They aren't value picks unless marked ★.</div>
  <div class="cgrid">${d.combos.slice().sort((a,b)=>(b.kind==='value')-(a.kind==='value')||((b.pred||{}).p_clear??-1)-((a.pred||{}).p_clear??-1)).map(ccard).join('')}</div>`:''}`:''}
 </div><aside>${adv?slip(d)+singlesCard(d):budgetCard(d)}</aside></div>${slipBar()}`;}
setInterval(()=>{if(S.view==='build'&&S.build&&(S.build.board||[]).some(g=>g.started)&&!document.hidden&&!S.buying&&!$('#modal').classList.contains('on'))load('build').catch(()=>{});},30000);
function setPview(k){hap();S.pview=k;try{localStorage.setItem('cw_pview',k)}catch(e){}S.panel=cget('panel_'+k);const want=k==='all'?'mix':k;if(want!==S.lg){setLg(want);}else load('build');}
try{S.pview=localStorage.getItem('cw_pview')||'all'}catch(e){S.pview='all'}
try{const l=JSON.parse(localStorage.getItem('cw_leagues')||'null');if(Array.isArray(l)&&l.length>1&&l.every(x=>Array.isArray(x)&&x.length>=3&&/^[a-z0-9_]+$/.test(x[0])&&typeof x[1]==='string'&&typeof x[2]==='string'))S.lgs=l;
 const g=JSON.parse(localStorage.getItem('cw_gn')||'null');if(g&&typeof g==='object'&&!Array.isArray(g))S.gn=g}catch(e){}
S.lg=S.pview==='all'?'mix':S.pview;
const KIND={single:['🎯','Single game'],early:['🎢','Sell-early favorite'],line:['📏','Spread / total'],combo:['🧩','Combo']};
function pTime(ts){return ts?new Date(ts*1000).toLocaleString([], {weekday:'short',hour:'numeric',minute:'2-digit'}):'';}
const started=c=>!c.live&&c.kick&&c.kick*1000<Date.now()+5*60e3;
function panelItem(c,st,approved,verb,view){const k=KIND[c.kind]||['•',c.kind];const off=S.pOff&&S.pOff.has(c.id);
 const state=c.state||'';const chip={'':approved||off||started(c)?'':`<span class="tag pwhen">buys when you ${verb==='add'?'add it':'approve'}</span>`,scheduled:started(c)?'<span class="tag bad">Game started · won\'t buy</span>':c.buy_at&&c.buy_at*1000>Date.now()?`<span class="tag">buys ${pTime(c.buy_at)}</span>`:`<span class="tag">${{paused:'Paused · not bought yet','no key':'Can\'t trade from here',price:'Waiting for a fresh price',balance:'Waiting to read your Kalshi balance',region:'Kalshi isn\'t allowing orders right now'}[c.hold]||'Buying now'}</span>`,bought:'<span class="tag good">Bought</span>',buying:'<span class="tag">Buying…</span>',check:'<span class="tag bad">Check Kalshi</span>',paper:'<span class="tag">Paper</span>',
  skipped:'<span class="tag bad">Skipped</span>',swapped:'<span class="tag">Swapped</span>',failed:'<span class="tag bad">Didn\'t buy</span>',cancelled:'<span class="tag">Cancelled</span>','left out':'<span class="tag">Left out</span>'}[state]||'';
 const res=c.result?`<span class="tag ${c.pl>=0?'good':'bad'}">${c.pl>=0?'+':'−'}${money(Math.abs(c.pl))}</span>`:'';
 const title=c.kind==='combo'?(c.legs.every(l=>l.game)?c.legs.map(l=>esc(l.game)).join('<br>'):c.legs.map(l=>esc(short(l.pick))).join(' + ')):c.kind==='line'?esc(c.legs[0].pick.replace(/ \(.*\)$/,'')):`${esc(short(c.legs[0].pick))}${c.kind==='single'?' to win':''}`;
 const games=pGames(c);
 const nums=c.kind==='early'?`${pct(c.chance)} it reaches ${Math.round(c.exit*100)}¢ · buy ${Math.round(c.price*100)}¢`:c.kind==='combo'?`${pct(c.chance)} to hit · pays ≈${pct(c.pct)} of fair`:`${pct(c.chance)} to win · ${Math.round(c.price*100)}¢`;
 return `<div class="pitem ${off?'off':''} ${S.pJust===c.id?'tog':''}" data-pid="${esc(c.id)}"><div class="pi">${c.icon||k[0]}</div><div class="pm"><div class="pk">${k[1]}${c.slate?' · slate':''}${c.league?' · '+esc(c.league):''} · ${c.live?'<span class="pliv">Under way · priced live</span>':esc(pTime(c.kick))}</div><b>${title}</b>
  <div class="pg">${games.map(g=>`<div>${esc(g)}</div>`).join('')}</div>
  <div class="pn">${nums} · <span class="up">+${Math.round(c.ret*100)}% expected</span></div>${c.why?`<div class="pw">${esc(c.why)}</div>`:''}${c.note?`<div class="pw">${esc(c.note)}</div>`:''}</div>
  <div class="ps">${(()=>{const edit=!approved&&!off&&!state&&!started(c),mine=edit&&stkGet('pn:'+c.id)!=null&&Math.abs(pStake(c)-c.stake)>=.005,v=edit?pStake(c):+c.stake||0;
   const amt=`<b data-num="ps:${esc(c.id)}" data-v="${v.toFixed(2)}">${money(v)}</b>`;
   return edit?`<button type="button" class="pstb${mine?' mine':''}" aria-label="Change the amount for this bet" onclick="pStakeSheet('${esc(c.id)}','${view||''}')">${amt}<small>${mine?'yours · rec '+money(c.stake):'Change'}</small></button>`:amt;})()}${pxSpark(c)}${chip}${res}${!approved?`<button class="x" title="${off?'Put back':'Leave out'}" onclick="pToggle('${c.id}')">${off?'↺':'✕'}</button>`:''}</div></div>`;}
/* Which game each bet is on, in plain English ("Over 7.5" alone told Pete nothing): one line per game. Spreads and totals
   say "Flyers at Bruins"; a single or one leg of a combo says "Flyers vs Bruins" (the team picked first). Older saved
   drafts have no game text, so fall back to what they do carry. */
function pGames(c){const L=c.legs||[];
 if(c.kind==='line'){const m=/\((.*)\)$/.exec(L[0]&&L[0].pick||'');return [c.game||(L[0]&&L[0].game)||(m?m[1]:'')].filter(Boolean);}
 if(c.kind==='combo')return [];   // its title already lists each leg's game
 return [c.game||(L[0]&&L[0].game)||(c.opp&&L[0]?short(L[0].pick)+' vs '+short(c.opp):'')].filter(Boolean);}
function pToggle(id){hap();S.pOff=S.pOff||new Set();S.pOff.has(id)?S.pOff.delete(id):S.pOff.add(id);S.pJust=id;renderBuild();S.pJust=null;}
/* A tiny line on each panel card: the bet's Kalshi price (a combo's share of fair) over the times this phone has seen
   it, kept for 36 hours. It only shows once there are two or more readings, so it never makes data up. */
function pxVal(c){const v=c.kind==='combo'?c.pct:(c.price!=null?c.price:((c.legs||[])[0]||{}).p);return v==null||isNaN(v)?null:+v;}
function pxHist(){if(!S.pxh){try{S.pxh=JSON.parse(localStorage.getItem('cw_pxh')||'{}')||{}}catch(e){S.pxh={}}}return S.pxh;}
function pxNote(c){const v=pxVal(c);if(v==null||!c.id)return [];const h=pxHist(),now=Date.now()/1000;let a=(h[c.id]||[]).filter(p=>now-p[0]<36*3600);const last=a[a.length-1];
 if(!last||Math.abs(last[1]-v)>1e-4||now-last[0]>600){a=a.concat([[Math.round(now),+v.toFixed(4)]]).slice(-48);h[c.id]=a;clearTimeout(S.pxT);
  S.pxT=setTimeout(()=>{try{const hh=pxHist();for(const k in hh)if(!(hh[k]||[]).some(p=>Date.now()/1000-p[0]<36*3600))delete hh[k];localStorage.setItem('cw_pxh',JSON.stringify(hh))}catch(e){}},400);}
 return a;}
function pxSpark(c){const a=pxNote(c);if(a.length<2)return '';const vs=a.map(p=>p[1]),lo=Math.min(...vs),hi=Math.max(...vs),rg=Math.max(hi-lo,.01),t0=a[0][0],t1=a[a.length-1][0];
 const d=a.map((p,i)=>`${i?'L':'M'}${((p[0]-t0)/Math.max(1,t1-t0)*64).toFixed(1)} ${(19-(p[1]-lo)/rg*16).toFixed(1)}`).join('');const col=vs[vs.length-1]>=vs[0]?'var(--yes)':'var(--no)';
 const f=c.kind==='combo'?pct:(x=>Math.round(x*100)+'¢');
 return `<svg class="psp" viewBox="0 0 64 22" preserveAspectRatio="none" aria-label="Price ${f(vs[0])} then ${f(vs[vs.length-1])}"><title>Kalshi price since this phone first saw it: ${f(vs[0])} → ${f(vs[vs.length-1])}</title><path d="${d}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/></svg>`;}
function rbOn(r){return !!(r&&(r.state==='asked'||r.state==='running'));}
/* A requested rebuild, from the Mac's own notes: waiting to start, which sport it's on, or picking the mix. */
function rbText(r){if(r.state==='asked')return r.wait>=90?'Waiting for the Mac to start. It hasn\'t picked this up yet: is it on and awake?':'Starting…';
 if(r.step==='choosing')return 'Picking the best mix for today…';return `Looking at ${esc(SPN[r.sport]||String(r.sport||'').toUpperCase())}… ${Math.min((r.i||0)+1,r.n||1)} of ${r.n||1} sports`;}
function rbFrac(r){if(r.state==='asked')return .04;const n=(r.n||1)+1;return Math.min(.97,r.step==='choosing'?(n-.5)/n:((r.i||0)+.5)/n);}
function rbCard(r){return `<div class="card rbcard" style="text-align:center;padding:22px 18px"><div style="font-size:30px">🔎</div><b style="display:block;margin:6px 0 4px;font-size:17px">Putting together a fresh panel</b>
  <div class="m rbtxt" style="font-size:13px;line-height:1.5"><span class="spin"></span> ${rbText(r)}</div><div class="rbtrack"><i style="width:${Math.round(rbFrac(r)*100)}%"></i></div>
  <div class="m" style="font-size:12px">It appears here on its own when it's ready. Only bets priced better than their real chance make it.</div></div>`;}
function rbStrip(r){return rbOn(r)?`<div class="rbstrip rbcard"><span class="spin"></span><span class="rbtxt">${rbText(r)}</span></div>`:'';}
function panelEmpty(d){const r=d&&d.rebuild;if(rbOn(r))return rbCard(r);
 if(d&&d.view&&d.view!=='all')return `<div class="card" style="text-align:center;padding:24px 18px"><div style="font-size:30px">🧘</div><b style="display:block;margin:6px 0 4px;font-size:17px">Nothing in ${esc(SPN[d.view]||d.view)} clears the bar right now</b>
  <div class="m" style="font-size:13px;line-height:1.5">No ${esc(SPN[d.view]||d.view)} bet is priced better than its real chance at the moment. The Mac keeps checking through the day. You can still build your own below.</div></div>`;
 const look=`<button class="btn acc" style="width:100%;justify-content:center;margin-top:14px" onclick="panelLook(this)">${r&&r.state==='done'?'Look again now':'Look now'}</button>`;
 if(r&&r.state==='done'&&!r.found)return `<div class="card" style="text-align:center;padding:24px 18px"><div style="font-size:30px">🧘</div><b style="display:block;margin:6px 0 4px;font-size:17px">No bets clear the bar right now</b>
  <div class="m rbwhy" style="font-size:13px;line-height:1.5">${esc(r.why||'Nothing is priced better than its real chance at the moment.')}</div><div class="m" style="font-size:12px;margin-top:6px">Looked ${ago2(r.upd)==='now'?'just now':ago2(r.upd)+' ago'}. The Mac keeps checking through the day and the panel shows up here if bets turn up.</div>${look}</div>`;
 return `<div class="card" style="text-align:center;padding:24px 18px"><div style="font-size:30px">🗓️</div><b style="display:block;margin:6px 0 4px;font-size:17px">No panel yet today</b>
  <div class="m" style="font-size:13px;line-height:1.5">The Mac builds one on its own as prices come in, keeping only bets priced better than their real chance. Tap below to have it look at every sport right now.</div>${look}</div>`;}
function panelBlock(d){if(!d||!d.panel)return panelEmpty(d);
 const p=d.panel;let st=p.stats||{};const approved=d.view==='all'&&p.status!=='draft',items=p.items||[];S.pOff=S.pOff||new Set();
 const live=items.filter(c=>!S.pOff.has(c.id)&&!(p.status==='draft'&&started(c)));const total=live.reduce((a,c)=>a+(approved?c.stake:pStake(c)),0);
 const wst=!approved&&pWhatSt(p);if(wst)Object.assign(st={},p.stats||{},wst);
 const head=`<div class="phead"><div><h2 style="margin:0">${d.view==='all'?"Today's panel":(SPN[d.view]||d.view)+(d.approved_other?' picks':' panel')}</h2>
   <div class="m" style="font-size:12.5px;margin-top:2px">${items.length} bet${items.length===1?'':'s'} · ${money(approved?items.filter(c=>['scheduled','buying','bought','check'].includes(c.state)).reduce((a,c)=>a+c.stake,0):total)} of your ${money(p.budget)} · picked together for the best chance the day ends up ahead</div></div>
   <div class="pring" style="--p:${Math.round((st.p_ahead||0)*100)}"><b>${pct(st.p_ahead||0)}</b><small>chance up</small></div></div>`;
 const addMode=d.view!=='all'&&d.approved_other;
 const btn=addMode?`<button class="btn acc" style="width:100%;justify-content:center;font-size:16px;padding:13px" onclick="panelAdd(this)">Add ${live.length} to today's panel · ${money(total)}</button>
   <div class="m" style="font-size:12px;text-align:center;margin-top:6px">Today's panel is already approved. These are bought right after you add them, the same way, inside your daily panel budget.</div>`:approved?(p.status==='approved'?`<button class="btn ghost" style="width:100%;justify-content:center" onclick="panelCancel()">Stop buying the rest</button>`:p.status==='cancelled'?`<button class="btn acc" style="width:100%;justify-content:center" onclick="panelRestart(this)">Build a fresh panel for today</button>
   <div class="m" style="font-size:12px;text-align:center;margin-top:6px">Bets already bought stay. The Mac looks at today's remaining games again and puts together a new panel for you to approve.</div>`:'')
  :!items.length?'':`<button class="btn acc" style="width:100%;justify-content:center;font-size:16px;padding:13px" onclick="panelApprove(this)">Approve ${live.length} bet${live.length===1?'':'s'} · ${money(total)}</button>
   <div class="m" style="font-size:12px;text-align:center;margin-top:6px">The Mac buys them right after you approve, checking each price again first. If one no longer qualifies, it swaps in a similar bet or skips it.</div>`;
 const longer=(p.longer||[]).length?`<h2 style="margin-top:20px">Longer plays <span class="n">${p.longer.length}</span></h2><div class="m" style="font-size:12px;margin:-4px 2px 10px">Over the next few days. Each day is a chance to cash out early. Not part of the approval above.</div><div class="plist">${p.longer.map(c=>panelItem(c,'',true)).join('')}</div>`:'';
 const other='';
 return `${d.view==='all'?rbStrip(d.rebuild):''}<div class="card panel">${head}${other}<div class="plist">${items.map(c=>panelItem(c,c.state,approved,addMode?'add':'approve','')).join('')||'<div class="m">Nothing qualifies right now.</div>'}</div>${sbSkipLine(p.sb_skipped,'panel')}
  ${items.length?`<div class="m" style="font-size:12px;margin:10px 2px">Expected ${smoney(st.ev||0)} · range ${smoney(st.worst||0)} to ${smoney(st.best||0)}</div>`:''}${poolLine(st.pool)}${btn}</div>${extraBlock(d.extra)}${longer}`;}
function extraBlock(x){const its=((x||{}).items||[]).filter(c=>!pSentHas(c.id));if(!its.length)return '';x=Object.assign({},x,{items:its});const live=its.filter(c=>!S.pOff.has(c.id));const tot=live.reduce((a,c)=>a+pStake(c),0);
 return `<div class="card panel" style="margin-top:14px;border-color:color-mix(in srgb,var(--yes) 40%,var(--line))"><div class="phead"><div><h2 style="margin:0">🆕 New since you approved</h2>
  <div class="m" style="font-size:12.5px;margin-top:2px">Good bets that turned up after you approved, on games today's panel doesn't have a bet on. Checked every few minutes as games get close.</div></div></div>
  <div class="plist">${x.items.map(c=>panelItem(c,'',false,'add','extra')).join('')}</div>
  ${live.length?`<button class="btn acc" style="width:100%;justify-content:center;margin-top:10px" onclick="panelAdd(this,'extra')">Add ${live.length} to today's panel · ${money(tot)}</button>`:''}</div>`;}
function poolLine(pl){if(!pl)return '';const n=k=>pl[k]||0;
 const parts=[[n('combo'),'combo','combos'],[n('single'),'single game','single games'],[n('early'),'sell-early favorite','sell-early favorites'],[n('line'),'spread or total','spreads or totals']].map(([v,a,b])=>`${v} ${v===1?a:b}`);
 return `<div class="m" style="font-size:12px;margin:-4px 2px 10px">Qualifying today: ${parts.join(' · ')}.${n('combo')?'':' No combo is priced at your cut-off or better right now; Kalshi usually pays less than fair on combos.'}</div>`;}
/* Approve / Add: the first tap arms the button, the second sends it once. While it's on its way (S.pSend) every
   other Approve/Add tap does nothing, and a redraw can't bring back a live button (the arm timer stands aside). */
function pArm(b,txt){b.dataset.sure='1';b.textContent=txt;b.classList.add('arm');hap('warning');
 setTimeout(()=>{if(b.isConnected&&!S.pSend&&b.dataset.sure==='1'){b.dataset.sure='';renderBuild();}},4000);}
async function panelApprove(b){if(S.pSend||b.disabled)return;const its=(S.panel.panel.items||[]).filter(c=>!S.pOff.has(c.id)),ids=its.map(c=>c.id),stakes=pStakes(its);
 if(!b.dataset.sure){pArm(b,'Tap again to approve');return;}
 S.pSend=true;b.disabled=true;b.dataset.sure='sent';b.classList.remove('arm');b.innerHTML='<span class="spin"></span> Sending…';let r;
 try{r=await pPost({a:'panel_approve',ids,view:S.pview||'all',at:S.panel.panel.at,stakes});}finally{S.pSend=false;}
 hap(r.ok?'success':'error');toast(r.msg,6000,r.ok?'good':'bad');if(r.ok)pStakeClear(its);S.pOff=new Set();await load('build');if(r.ok)pBuyWatch();}
/* Right after Approve / Add the Mac buys within seconds: look again a few times so "Buying now" turns into "Bought". */
function pBuyWatch(){clearTimeout(S.pbT);let i=0;const tick=()=>{if(S.view!=='build')return;
 if(document.hidden||S.buying||$('#modal').classList.contains('on')){S.pbT=setTimeout(tick,3000);return;}
 const pn=((S.panel||{}).panel||{}),its=pn.items||[];if(i&&S.pview==='all'&&pn.status==='approved'&&!its.some(c=>c.state==='scheduled'||c.state==='buying'))return;
 load('build').catch(()=>{}).finally(()=>{if(++i<8)S.pbT=setTimeout(tick,[6,10,15,20,30,60,90][i-1]*1000);});};S.pbT=setTimeout(tick,4000);}
/* Extras this phone just added stay off the New-since-you-approved card for 2 min, even if a refresh that left
   before the Mac saved the add still lists them (the Mac drops them from the card itself too). */
function pSentHas(id){const t=(S.pSent||{})[id];return !!t&&Date.now()-t<120000;}
async function panelAdd(b,view){if(S.pSend||b.disabled)return;const src=view==='extra'?(S.panel.extra||{}):S.panel.panel;
 const its=(src.items||[]).filter(c=>!S.pOff.has(c.id)&&!(view==='extra'&&pSentHas(c.id))),ids=its.map(c=>c.id),stakes=pStakes(its);
 if(!b.dataset.sure){pArm(b,'Tap again to add');return;}
 S.pSend=true;b.disabled=true;b.dataset.sure='sent';b.classList.remove('arm');b.innerHTML='<span class="spin"></span> Adding…';let r;
 try{r=await pPost({a:'panel_add',ids,view:view||S.pview,stakes});}finally{S.pSend=false;}
 hap(r.ok?'success':'error');toast(r.msg,6000,r.ok?'good':'bad');if(r.ok)pStakeClear(its);
 if(r.ok){if(view==='extra'){S.pSent=S.pSent||{};const now=Date.now();ids.forEach(id=>S.pSent[id]=now);}
  if(b.isConnected){b.innerHTML='✓ Added';b.classList.add('done');}await new Promise(res=>setTimeout(res,700));}
 S.pOff=new Set();await load('build');
 /* keep hidden only what today's panel now really has; anything the Mac left out (budget, same game) shows again */
 if(r.ok&&view==='extra'&&S.panel&&S.panel.panel){const has=new Set((S.panel.panel.items||[]).filter(c=>['scheduled','buying','bought','check','failed'].includes(c.state)).map(c=>c.id));
  let back=false;ids.forEach(id=>{if(!has.has(id)){delete S.pSent[id];back=true;}});if(back)renderBuild();}
 if(r.ok)pBuyWatch();}
/* Approve/Add requests give up waiting after 30 s so a hung link can't leave every button dead; the Mac's side is
   safe to repeat (panel_tx), so the next tap can't buy anything twice. */
function pPost(body){return Promise.race([api('/app/api/act',body).catch(()=>({ok:false,msg:'Couldn\'t reach the Mac.'})),
 new Promise(res=>setTimeout(()=>res({ok:false,msg:'The Mac is slow to answer. Pull to refresh in a moment to see whether it went through.'}),30000))]);}
async function panelRestart(b){hap();b.innerHTML='<span class="spin"></span>';
 const r=await api('/app/api/act',{a:'panel_restart'}).catch(()=>({ok:false,msg:'Couldn\'t reach the Mac.'}));
 hap(r.ok?'success':'error');toast(r.msg,7000,r.ok?'good':'bad');S.rbWas=!!r.ok;await load('build');}
async function panelLook(b){hap();if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Asking the Mac…';}
 const r=await api('/app/api/act',{a:'panel_look'}).catch(()=>({ok:false,msg:'Couldn\'t reach the Mac.'}));
 if(!r.ok){hap('error');toast(r.msg,6000,'bad');}else{S.rbWas=true;if(S.panel){S.panel.rebuild=r.rebuild||{state:'asked',wait:0};}}
 await load('build');}
/* While the Mac rebuilds, ask it every 2 s how far it's got and redraw just the panel card; when it's done, the
   new panel (or the reason there isn't one) drops in by itself. */
function rbWatch(){const on=S.view==='build'&&rbOn((S.panel||{}).rebuild);if(on){S.rbWas=true;if(!S.rbT)S.rbT=setInterval(rbPoll,2000);}else if(S.rbT){clearInterval(S.rbT);S.rbT=null;}}
async function rbPoll(){if(S.view!=='build'){rbWatch();return;}if(document.hidden||S.rbBusy)return;S.rbBusy=true;const pv=S.pview||'all';
 try{const p=await api('/app/api/panel?v='+pv);if(!p||pv!==(S.pview||'all'))return;S.panel=p;cput('panel_'+pv,p);
  if(rbOn(p.rebuild)){const el=$('#pblock');const t=el&&el.querySelector('.rbtxt'),bar=el&&el.querySelector('.rbtrack i');
   if(t&&!!bar===!p.panel){t.innerHTML=(p.panel?'':'<span class="spin"></span> ')+rbText(p.rebuild);if(bar)bar.style.width=Math.round(rbFrac(p.rebuild)*100)+'%';}else renderBuild();return;}
  const r=p.rebuild;if(S.rbWas&&r&&r.state==='done'){if(r.found){hap('success');toast(r.kind==='extra'?`Found ${r.found} new bet${r.found===1?'':'s'} since you approved.`:`Your fresh panel is ready: ${r.found} bet${r.found===1?'':'s'}.`,5000,'good');}else hap('warning');}
  S.rbWas=false;renderBuild();}catch(e){}finally{S.rbBusy=false;rbWatch();}}
async function panelCancel(){hap('warning');if(!confirm('Stop the Mac from buying the rest of today\'s panel?'))return;const r=await api('/app/api/act',{a:'panel_cancel'});toast(r.msg,5000);await load('build');}
function toggleAdv(){hap();const open=S.adv||S.slip.length>0;S.adv=!open;if(open){S.slip=[];S.custom=null;}try{localStorage.setItem('cw_adv',S.adv?'1':'')}catch(e){}renderBuild();
 if(S.adv)setTimeout(()=>{const h=document.querySelector('.board');if(h)h.scrollIntoView({behavior:'smooth',block:'start'});},60);}
function comboRet(c){const r=c.pred&&c.pred.n>=20?c.pred.pct:c.est_pct;return r==null?null:r;}
function bestBets(d){const out=[];
 (d.singles||[]).filter(x=>x.idea).forEach(x=>out.push({k:'single',score:x.ev,x}));
 (d.lines||[]).filter(x=>x.rec&&x.stake>0).forEach(x=>out.push({k:'line',score:x.exp/x.stake,x}));
 (d.combos||[]).filter(c=>c.kind==='value'&&!c.bought&&(comboRet(c)||0)>=1).forEach(c=>out.push({k:'combo',score:comboRet(c)-1,x:c}));
 return out.sort((a,b)=>b.score-a.score).slice(0,6);}
function betCard(b){const x=b.x,ret=`<span class="ret">+${Math.round(b.score*100)}%<small>expected</small></span>`;
 if(b.k==='single')return `<div class="bet"><div class="bt"><div><span class="kind">🎯 Single game</span><b>${esc(short(x.pick))} to beat ${esc(short(x.opp))}</b></div>${ret}</div>
  <div class="bnums"><div>Chance to win<b>${pct(x.fair)}</b></div><div>Kalshi price<b>${Math.round(x.p*100)}¢</b></div><div>Edge<b class="up">${(x.edge*100).toFixed(1)}¢</b></div></div>
  <div class="why">Kalshi charges ${Math.round(x.p*100)}¢ for a ${pct(x.fair)} chance, after its fee. Wins pay $1 per contract.</div>
  <button class="btn acc" style="width:100%" onclick="singleFromBoard('${x.ticker}',this)">Get a price</button></div>`;
 if(b.k==='line')return `<div class="bet"><div class="bt"><div><span class="kind">${x.kind==='spread'?'📏 Spread':'➕ Total'} · ${esc(x.game)}</span><b>${esc(x.pick.replace(/ \(.*\)$/,''))}</b></div>${ret}</div>
  <div class="bnums"><div>Chance<b>${pct(x.fair)}</b></div><div>Kalshi price<b>${Math.round(x.p*100)}¢</b></div><div>Edge<b class="up">${(x.edge*100).toFixed(1)}¢</b></div></div>
  <div class="why">${lineRoute(x)}. Expected ${smoney(x.exp)} on ${money(x.stake)}, after Kalshi's fee, at what you can really buy.</div>
  <button class="btn acc" style="width:100%" data-t="${esc(x.ticker)}" onclick="lineFromBoard(this.dataset.t,this)">Get a price</button></div>`;
 const c=x,o=S.quotes&&S.quotes[c.i],fresh=o&&Date.now()/1000-o.at<20;
 return `<div class="bet"><div class="bt"><div><span class="kind">★ ${c.legs.length}-team combo</span><b>${c.legs.map(l=>esc(short(l.pick))).join(' + ')}</b></div>${ret}</div>
  <div class="bnums"><div>Chance to hit<b>${pct(c.chance)}</b></div><div>Fair payout<b>${money(c.fair)}</b></div><div>Pays vs fair<b class="up">≈${pct(comboRet(c))}</b></div></div>
  <div class="why">Every leg is priced below the sharp books' chance, so the combo should pay more than it's worth. Get the real price before buying.</div>
  ${fresh?`<div class="qline ${o.clears?'good':'bad'} ${qNew(o)}">${qBar(o)}<b>Kalshi pays ${money(o.pays)} for ${money(o.stake)}</b><span>${pct(o.pct)} of fair · <span class="qs" data-at="${o.at}">${Math.max(0,Math.round(20-(Date.now()/1000-o.at)))}</span>s left</span></div>
   <button class="btn ${o.clears?'yes':'warn'}" style="width:100%" id="b${c.i}" onclick="buy(${c.i},false,this)">${o.clears?'Buy':'Buy anyway'} ${money(o.stake)} → ${money(o.pays)}</button>`:`<button class="btn acc" style="width:100%" id="q${c.i}" onclick="quote(${c.i})">Get a price</button>`}</div>`;}
function budgetCard(d){return d.spent!=null?`<div class="card"><h3>This week <span>${esc(d.name)}</span></h3><div class="mini">Spent<b>${money(d.spent)}</b></div><div class="mini">Your cap<b>${money(d.budget)}</b></div><div class="mini">Combo cut-off<b>${d.cut}% of fair</b></div></div>`:'';}
/* The slip's Single bet / Combo switch (#113): Single bet keeps one team and its button buys it straight (the buy sheet);
   Combo is the slip as before. */
function slipTog(){const one=S.slipMode==='single';return `<div class="sbtog" role="tablist"><button type="button" role="tab" class="${one?'on':''}" aria-selected="${one}" onclick="slipMode('single')">Single bet</button><button type="button" role="tab" class="${one?'':'on'}" aria-selected="${!one}" onclick="slipMode('combo')">Combo</button></div>`;}
function slipMode(m){S.slipMode=m==='single'?'single':'combo';if(S.slipMode==='single'&&S.slip.length>1)S.slip=[S.slip[S.slip.length-1]];S.custom=null;renderBuild();}
function slipBar(){const legs=S.slip.map(sideBy).filter(Boolean);const was=S.slipWas;S.slipWas=legs.length;if(!legs.length)return '';
 const ch=legs.reduce((a,l)=>a*(l.fair||l.p||0),1);
 if(S.slipMode==='single'){const l=legs[legs.length-1],w=legWhere(l);
  return `<div class="slipbar ${was?'':'in'}">${slipTog()}<div class="sbrow"><span>${ICON[w.sp]||''} ${esc(short(l.pick))}${w.opp?' vs '+esc(short(w.opp.pick)):''} · ${l.p!=null?Math.round(l.p*100)+'¢':''}</span><button onclick="sbOpen('${esc(l.ticker)}',S.lg)">Buy straight ›</button><button class="x" aria-label="Clear" onclick="S.slip=[];S.custom=null;renderBuild()">✕</button></div></div><div class="slipgap" style="height:104px"></div>`;}
 return `<div class="slipbar ${was?'':'in'}">${slipTog()}<div class="sbrow"><span>${legs.length<2?`${ICON[legWhere(legs[0]).sp]||''} ${esc(short(legs[0].pick))}${legWhere(legs[0]).opp?' vs '+esc(short(legWhere(legs[0]).opp.pick)):''} picked · tap 1 more team`:`${legs.map(l=>ICON[legWhere(l).sp]||'').join('')} ${legs.length} picks · ${pct(ch)} to hit`}</span>${legs.length>=2?`<button onclick="document.querySelector('.slip').scrollIntoView({behavior:'smooth',block:'center'});if($('#slipq'))quoteSlip()">Price it ›</button>`:''}<button class="x" aria-label="Clear" onclick="S.slip=[];S.custom=null;renderBuild()">✕</button></div></div><div class="slipgap" style="height:104px"></div>`;}
try{S.adv=!!localStorage.getItem('cw_adv')}catch(e){}
function setLg(k){S.lg=k;S.slip=[];try{localStorage.setItem('cw_lg',k)}catch(e){};S.build=cget('build_'+k);renderBuild();load('build');}
function pick(t,ev){const d=S.build;const same=d.board.find(g=>g.event===ev).sides.map(s=>s.ticker);
 if(S.slip.includes(t))S.slip=S.slip.filter(x=>x!==t);else{S.slip=S.slipMode==='single'?[]:S.slip.filter(x=>!same.includes(x));S.slip.push(t);S.justPicked=t;}S.custom=null;renderBuild();S.justPicked=null;}
function sideBy(t){for(const g of S.build.board)for(const s of g.sides)if(s.ticker===t)return s;}
function slip(d){const legs=S.slip.map(sideBy).filter(Boolean);const stake=stkGet('slip:c')||d.stake||5;
 const fairChance=legs.reduce((a,l)=>a*(l.fair||l.p||0),1),kal=legs.reduce((a,l)=>a*(l.p||0),1);const c=S.custom;
 const one=S.slipMode==='single';
 return `<div class="card slip"><h3>${one?'Single bet':'Your combo'} <span>${legs.length} pick${legs.length==1?'':'s'}</span></h3>
  <div style="margin:-2px 0 8px">${slipTog()}</div>
  ${legs.length?legs.map(l=>`<div class="pick">${legRow(l)}<button aria-label="Remove" onclick="pick('${l.ticker}','${l.event}')">×</button></div>`).join(''):`<div class="m" style="padding:6px 0 10px">${one?'Tap a team on the board to buy it on its own.':'Tap teams on the board to build your own combo, or use a suggestion below.'}</div>`}
  ${legs.length===1?`<button class="btn ${one?'acc':'ghost'}" id="sbslip" style="width:100%;margin-top:10px;justify-content:center" onclick="sbOpen('${esc(legs[0].ticker)}',S.lg)">Buy ${esc(short(legs[0].pick))} straight${legs[0].p!=null?' · '+Math.round(legs[0].p*100)+'¢':''}</button>`:''}
  ${legs.length>=2?`<div style="margin-top:10px"><div class="sum">Chance it hits<b>${pct(fairChance)}</b></div><div class="sum">Fair payout for ${money(stake)}<b>${money(stake/fairChance)}</b></div>
   <div class="sum">Kalshi's single prices imply<b>${money(stake/kal)}</b></div>
   ${c&&c.offer?`<div class="sum">Kalshi offers<b class="${c.offer.clears===false?'':'up'}" ${c.offer.clears===false?'style="color:#f5b544"':''}>${money(c.offer.pays)}</b></div>${c.offer.pct!=null?`<div class="sum">That's<b>${pct(c.offer.pct)} of fair · ${c.offer.clears===false?'below':'above'} your cut-off</b></div>`:''}`:''}
   ${(c&&c.offer&&Date.now()/1000-c.offer.at<20)||stkGet('slip:c')!=null?stakeCtl({key:'slip:c',rec:(S.slipRec||{}).rec||d.stake||5,cur:c&&c.offer&&Date.now()/1000-c.offer.at<20?c.offer.stake:stkGet('slip:c'),min:(S.slipRec||{}).min||1,max:(S.slipRec||{}).max||100,room:(S.slipRec||{}).room,ev:c&&c.offer?c.offer.ev:null}):''}
   <div style="display:flex;gap:8px;margin-top:12px">${c&&c.offer&&Date.now()/1000-c.offer.at<20?`<button class="btn qb ${c.offer.clears===false?'warn':'yes'}" style="flex:1" onclick="buy(${c.i},true)">${qBar(c.offer)}${c.offer.clears===false?'Buy anyway':'Buy'} ${money(c.offer.stake)} to win ${money(c.offer.pays)}</button>`:`<button class="btn acc" style="flex:1" id="slipq" onclick="quoteSlip()">Get Kalshi's price${stkLbl('slip:c')}</button>`}</div></div>`:''}
  <div class="m" style="font-size:12px;margin-top:12px">${d.spent!=null?`Spent ${money(d.spent)} of your ${money(d.budget)} cap · cut-off ${d.cut}% of fair`:''}</div></div>`;}
async function quoteSlip(){$('#slipq').innerHTML='<span class="spin"></span> Asking Kalshi…';const r=await api('/app/api/act',{a:'custom',tickers:S.slip});
 if(!r.ok){toast(r.msg);renderBuild();return;}const q=await api('/app/api/act',{a:'quote',i:r.i,legs:S.slip.slice(),stake:stkGet('slip:c')});
 if(!q.ok){toast(q.error||q.msg||'No price came in.');renderBuild();return;}S.custom={i:r.i,offer:{pays:q.pays,stake:q.stake,at:Date.now()/1000,pct:q.pct,clears:q.clears,ev:q.ev}};S.slipRec={rec:q.rec,min:q.min,max:q.max,room:q.room};hap(q.clears?'success':'warning');renderBuild();clearInterval(S.qT);S.qT=setInterval(qTick,1000);
 toast(`Kalshi pays ${money(q.pays)} for ${money(q.stake)} (${pct(q.pct)} of fair). Buy within 20 seconds.`,6000);}
async function rebuild(b){hap();if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Rebuilding…';}
 const before=JSON.stringify(((S.build||{}).combos||[]).map(c=>c.legs.map(l=>l.ticker)));S.quotes={};
 await load('build',true);const after=JSON.stringify(((S.build||{}).combos||[]).map(c=>c.legs.map(l=>l.ticker)));
 toast(before===after?'Prices refreshed. The best combos are still the same ones.':'New combos are ready.',4000,'good');}
async function swapCombo(i,b){hap();if(b){b.disabled=true;b.innerHTML='<span class="spin"></span>';}
 const r=await api('/app/api/act',{a:'swap',i}).catch(()=>({ok:false}));if(S.quotes)delete S.quotes[i];if(S.stk)delete S.stk['cc:'+i];if(S.ccRec)delete S.ccRec[i];if(S.flips)delete S.flips[i];
 if(!r.ok){hap('error');toast(r.msg||'Couldn\'t find another one.');renderBuild();return;}
 const k=S.build.combos.findIndex(x=>x.i===i);if(k>=0)S.build.combos[k]=r.combo;S.ccJust=i;renderBuild();S.ccJust=null;hap('success');}
async function flipLeg(i,t){hap();const r=await api('/app/api/act',{a:'flip',i,t}).catch(()=>({ok:false}));
 if(!r.ok){hap('error');toast(r.msg||'Couldn\'t flip that one.',6000);return;}
 const k=S.build.combos.findIndex(x=>x.i===i);if(k>=0)S.build.combos[k]=r.combo;if(S.quotes)delete S.quotes[i];
 S.flips=S.flips||{};S.flips[i]={v:r.verdict,text:r.text};hap(r.verdict==='good'?'success':r.verdict==='bad'?'warning':'light');S.ccJust=i;renderBuild();S.ccJust=null;}
/* A bet's leg, Kalshi-style: sport icon, the pick in bold, then who it plays, the league and when, with the price on the right
   (and the live score when the game is under way). Display only: it reads the Build board the page already has. */
function gameOf(l){const ev=l.event||String(l.ticker||'').replace(/-[^-]*$/,'');const b=S.build&&S.build.board;if(!b)return undefined;
 if(!S._gm||S._gm.b!==b){S._gm={b,m:new Map(b.map(x=>[x.event,x]))};}return S._gm.m.get(ev);}
function legWhere(l){const g=gameOf(l)||{};const opp=(g.sides||[]).find(s=>!s.tie&&s.ticker!==l.ticker);return {g,opp,sp:g.sport||''};}
function legRow(l,o){o=o||{};const {g,opp,sp}=legWhere(l);const meta=[opp?'vs '+opp.pick:'',SPN[sp]||'',g.started?'':(g.label||'')].filter(Boolean).join(' · ');
 const live=g.started?(legLive(l)||'<span class="legsc even">● Live</span>'):'';
 return `<div class="lrow${o.flip?' flip':''}"${o.flip?` onclick="flipLeg(${o.i},'${l.ticker}')" title="Tap to flip to the other team"`:''}>${ICON[sp]?`<span class="li">${ICON[sp]}</span>`:''}<div class="lm"><b>${esc(l.pick)}</b><small>${esc(meta)}</small>${live}</div><span class="lp">${l.fair!=null?pct(l.fair):''}${o.flip?'<i>⇄</i>':''}</span></div>`;}
function legSummary(ls){return (ls||[]).map(l=>{const {opp,sp}=legWhere(l);return `${ICON[sp]||''} ${l.pick}${opp?' vs '+opp.pick:''}`.trim();}).join(' · ');}
function legLive(l){const ev=(l.event||String(l.ticker||'').replace(/-[^-]*$/,''));const g=(S.build&&S.build.board||[]).find(x=>x.event===ev);if(!g||!g.sc)return '';
 const sc=g.sc,me=l.ticker===g.first?sc.me:sc.opp,th=l.ticker===g.first?sc.opp:sc.me;return `<span class="legsc ${me>th?'up':me<th?'down':'even'}">● ${me}–${th} · ${esc(sc.detail||'live')}</span>`;}
/* a fresh Kalshi quote: it rises in once, and a thin bar under it drains over the 20 seconds the price lasts */
function qNew(o){return o&&Date.now()/1000-o.at<1.2?'new':'';}
function qBar(o){return o?`<i class="qt" style="animation-delay:-${Math.max(0,Date.now()/1000-o.at).toFixed(2)}s"></i>`:'';}
function ccSig(c){return (c&&c.legs||[]).map(l=>l.ticker).join('|');}
function ccPhase(c){const o=S.quotes&&S.quotes[c.i],wait=v=>v&&Date.now()-v.t<60000&&v.sig===ccSig(c);   // a price or a buy still on its way (never stuck for more than a minute)
 return wait(S.bpend&&S.bpend[c.i])?'buy':wait(S.qpend&&S.qpend[c.i])?'ask':o&&Date.now()/1000-o.at<20?'quote'+o.at:'idle';}
function ccard(c){const o=S.quotes&&S.quotes[c.i];const fresh=o&&Date.now()/1000-o.at<20;const fl=S.flips&&S.flips[c.i];const ph=ccPhase(c);const busy=ph==='buy'||ph==='ask';
 if(c.bought)return `<div class="ccard" style="opacity:.62"><div class="hd"><div><div class="tier" style="color:var(--yes)">✓ You bought this</div><b>${money(c.fair)}</b> <span class="m">fair payout</span></div><span class="verdict hold">${pct(c.chance)}</span></div>
  <div class="lrows">${c.legs.map(l=>legRow(l)).join('')}</div>
  <div class="brow"><button class="btn ghost pri" onclick="go('live')">See it on Live</button><button class="btn ghost sec" onclick="swapCombo(${c.i},this)">↻ Another</button></div></div>`;
 return `<div class="ccard ${S.ccJust===c.i?'flash':''}" data-i="${c.i}" data-ph="${ph}" data-sig="${esc(ccSig(c))}"><div class="hd"><div><div class="tier" ${c.kind==='value'?'style="color:var(--yes)"':''}>${c.kind==='value'?'★ Value pick':esc(c.tier||c.kind||'')}</div><b data-num="cf:${c.i}" data-v="${(+c.fair||0).toFixed(2)}">${money(c.fair)}</b> <span class="m">fair payout</span></div><span class="verdict hold" data-num="cc:${c.i}" data-v="${c.chance}" data-f="pct">${pct(c.chance)}</span></div>
  <div class="lrows">${c.legs.map(l=>legRow(l,{flip:1,i:c.i})).join('')}</div>
  ${fl?`<div class="flipnote ${fl.v}"><b class="v">${fl.v==='good'?'Good flip':fl.v==='bad'?'Worse bet':'Trade-off'}</b>${esc(fl.text)}</div>`:`<div class="m" style="font-size:11.5px">Tap a team to flip it to the other side.</div>`}
  <div class="s" style="font-size:12.5px">${c.pred&&c.pred.n>=20?`<span class="pred ${c.pred.p_clear>=.6?'good':c.pred.p_clear<.2?'bad':''}">Likely ≈ ${pct(c.pred.pct)} of fair · ${c.pred.p_clear>=.9?'very likely':c.pred.p_clear>=.6?'likely':c.pred.p_clear>=.35?'maybe':'unlikely'} to clear your cut-off</span><div class="m" style="font-size:11.5px;margin-top:4px">Guess from ${c.pred.n} past Kalshi prices. Get price for the real one.</div>`:c.est?`Kalshi will likely pay about ${money(c.est)} (${pct(c.est_pct)} of fair)`:fresh?'':'Get a price to see what Kalshi pays.'}
   ${c.size?`<div class="m" style="margin-top:6px">Suggested bet ${money(c.size)}${c.exposure?` · smaller: you already need ${esc(short(c.exposure.team))} a lot`:''}</div>`:c.exposure?`<div class="m" style="margin-top:6px">You already need ${esc(short(c.exposure.team))} in a lot of combos</div>`:''}</div>
  ${fresh?`<div class="qline ${o.clears?'good':'bad'} ${qNew(o)}">${qBar(o)}<b>Kalshi pays ${money(o.pays)} for ${money(o.stake)}</b><span>${pct(o.pct)} of fair · ${o.clears?'above':'below'} your ${o.cut||''}% cut-off · <span class="qs" data-at="${o.at}">${Math.max(0,Math.round(20-(Date.now()/1000-o.at)))}</span>s left</span></div>`:''}
  ${ccStake(c,o,fresh,busy)}
  <div class="brow">${ph==='buy'?`<button class="btn pri ${o&&o.clears?'yes':'warn'}" id="b${c.i}" disabled><span class="spin"></span> Buying… confirming with Kalshi</button>`:
   ph==='ask'?`<button class="btn pri" id="q${c.i}" disabled><span class="spin"></span> Asking Kalshi…</button>`:
   fresh?`<button class="btn pri ${o.clears?'yes':'warn'}" id="b${c.i}" onclick="buy(${c.i},false,this)">${o.clears?'Buy':'Buy anyway'} ${money(o.stake)} → ${money(o.pays)}</button>`:
   `<button class="btn pri" id="q${c.i}" onclick="quote(${c.i})">Get price${stkLbl('cc:'+c.i)}</button>`}<button class="btn ghost sec" title="Not this one: show a different combo" ${busy?'disabled':''} onclick="swapCombo(${c.i},this)">↻ Not this one</button></div></div>`;}
/* the amount row on a combo card: once a price came in (or Pete already chose an amount); hidden while asking or buying */
function ccStake(c,o,fresh,busy){const key='cc:'+c.i,mine=stkGet(key);if(busy||(!fresh&&mine==null))return '';S.ccRec=S.ccRec||{};
 const m=(fresh&&o)||S.ccRec[c.i]||{};const rec=m.rec||c.size||(S.build&&S.build.stake)||5;
 return stakeCtl({key,rec,cur:fresh?o.stake:mine,min:m.min||1,max:m.max||100,room:m.room,ev:fresh?o.ev:null});}
async function quote(i){hap();S.qpend=S.qpend||{};const cur0=(S.build&&S.build.combos||[]).find(c=>c.i===i),sig=ccSig(cur0);
 if(S.qpend[i]&&Date.now()-S.qpend[i].t<60000&&S.qpend[i].sig===sig)return;S.qpend[i]={t:Date.now(),sig};const b=$('#q'+i);
 if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Asking Kalshi…';const sc=b.parentNode.querySelector('.sec');if(sc)sc.disabled=true;const cc=b.closest('.ccard');if(cc)cc.dataset.ph='ask';}
 const shown=((S.build&&S.build.combos||[]).find(c=>c.i===i)||{}).legs;
 const r=await api('/app/api/act',{a:'quote',i,legs:shown?shown.map(l=>l.ticker):undefined,stake:stkGet('cc:'+i)}).catch(e=>({ok:false,error:'Couldn\'t reach your Mac ('+(e&&e.message||e)+').'}));
 if(S.qpend[i]&&S.qpend[i].sig===sig)delete S.qpend[i];
 if(ccSig((S.build&&S.build.combos||[]).find(c=>c.i===i))!==sig){renderBuild();return;}   // the card was swapped, flipped or rebuilt while we waited: that price isn't for what's on screen
 if(!r.ok){hap('error');toast(r.error||r.msg||'No price came in.',6000);renderBuild();return;}
 S.quotes=S.quotes||{};S.quotes[i]={pays:r.pays,stake:r.stake,pct:r.pct,clears:r.clears,cut:r.cut,at:Date.now()/1000,rec:r.rec,ev:r.ev,room:r.room,max:r.max,min:r.min};
 S.ccRec=S.ccRec||{};S.ccRec[i]={rec:r.rec,room:r.room,max:r.max,min:r.min};hap(r.clears?'success':'warning');renderBuild();
 clearInterval(S.qT);S.qT=setInterval(qTick,1000);}
/* The quote countdown: once a second only the "Ns left" numbers change, in place. A card is redrawn once, when its quote
   runs out (the button goes back to Get price), never every second (that replaced the button under your finger). */
function qTick(){if(S.view!=='build')return;const now=Date.now()/1000;
 document.querySelectorAll('#main .qs').forEach(e=>{const left=Math.max(0,Math.round(20-(now-(+e.dataset.at||0))));if(e.textContent!==String(left))e.textContent=left;});
 const old=q=>q&&!q.x&&now-q.at>=20;   // a quote that has just run out: one redraw puts Get price back (and drops the dead Buy)
 const over=Object.values(S.quotes||{}).some(old)||old(S.custom&&S.custom.offer);
 if(over&&!S.buying){Object.values(S.quotes||{}).forEach(q=>{if(old(q))q.x=1;});if(old(S.custom&&S.custom.offer))S.custom.offer.x=1;renderBuild();}
 if(!Object.values(S.quotes||{}).some(q=>q&&now-q.at<21)&&!(S.custom&&S.custom.offer&&now-S.custom.offer.at<21))clearInterval(S.qT);}
async function buy(i,custom,btn){if(S.buying)return;S.buying=true;
 if(!custom){S.bpend=S.bpend||{};S.bpend[i]={t:Date.now(),sig:ccSig((S.build&&S.build.combos||[]).find(x=>x.i===i))};const cc=btn&&btn.closest('.ccard');if(cc)cc.dataset.ph='buy';const sc=btn&&btn.parentNode&&btn.parentNode.querySelector('.sec');if(sc)sc.disabled=true;}
 hap();const named=legSummary(custom?S.slip.map(sideBy).filter(Boolean):((S.build&&S.build.combos||[]).find(x=>x.i===i)||{}).legs);if(btn){btn.disabled=true;btn.innerHTML='<span class="spin"></span> Buying… confirming with Kalshi';}
 let r;try{r=await api('/app/api/act',{a:'buy',i});}catch(e){r={ok:false,msg:'Couldn\'t reach your Mac ('+(e&&e.message||e)+'). Check Live before trying again, so you don\'t buy twice.'};}
 S.buying=false;if(S.bpend)delete S.bpend[i];if(r.ok&&S.stk)delete S.stk[custom?'slip:c':'cc:'+i];if(r.ok){okSheet('Bought',`${money(r.pays||0)} if it hits`,(named?named+'. ':'')+'It shows on Live within a minute. Smart sell watches it from there.');}else{toast(r.msg||'Didn\'t go through.',7000,'bad');}
 if(custom)S.custom=null;else if(S.quotes)delete S.quotes[i];if(r.ok&&custom)S.slip=[];
 if(r.ok&&!custom&&S.build){const c=S.build.combos.find(x=>x.i===i);if(c)c.bought=true;}renderBuild();}
