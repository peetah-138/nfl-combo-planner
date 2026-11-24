// ---------------- Live: foldable sections, and the Buy ideas (GitHub #141)
/* Display only. The Mac ranks the ideas by expected profit in dollars and hides the ones you dismissed (see
   live_ideas in the engine); this file draws them: the top few, the rest under "N more ideas", an X and a swipe to
   dismiss, Clear all, a detail page, and a calm empty state. Buying still goes through priceIdea / buyIdea /
   buySingle (below), which call the same guarded Mac paths as before. */

/* Section folds (Buy ideas, Your combos, Single bets & spreads): the chevron button turns and the body folds with a
   height animation (grid rows 1fr -> 0fr). The state is remembered per phone (cw_fold_<name>); the count badge stays
   in the header. Folding never re-draws the page, so nothing jumps. */
function foldOpen(k){try{return localStorage.getItem('cw_fold_'+k)!=='0';}catch(e){return true;}}
function foldHead(k,title,n,right,style){const o=foldOpen(k);
 return `<h2 class="lsec ${o?'open':''}" data-fk="${k}" ${style?`style="${style}"`:''}><button class="fbtn" type="button" aria-expanded="${o}" onclick="foldTog('${k}')"><span class="chev">▾</span>${title} <span class="n">${n}</span></button>${right||''}</h2>`;}
function foldB(k){return `<div class="fold ${foldOpen(k)?'':'shut'}" data-fk="${k}"><div class="fin">`;}
function foldE(){return '</div></div>';}
function foldTog(k){hap('selection');const o=!foldOpen(k);try{localStorage.setItem('cw_fold_'+k,o?'1':'0');}catch(e){}
 document.querySelectorAll(`h2.lsec[data-fk="${k}"]`).forEach(h=>{h.classList.toggle('open',o);const b=h.querySelector('.fbtn');if(b)b.setAttribute('aria-expanded',o);});
 document.querySelectorAll(`.fold[data-fk="${k}"]`).forEach(f=>f.classList.toggle('shut',!o));}

/* ---- the list */
/* a notification that names an idea: open the fold and the "more" list if it sits in them, so it can be scrolled to */
function ideaReveal(id){const d=S.live;if(!d||!Array.isArray(d.ideas))return;const all=ideaList(d),i=all.findIndex(x=>x.id===id);if(i<0)return;
 try{localStorage.setItem('cw_fold_ideas','1');}catch(e){}if(i>=(+d.ideas_limit>0?+d.ideas_limit:all.length))S.ideasMore=true;renderLive();}
function ideaList(d){const hid=S.idHide||{},now=Date.now();   // a dismissal shows at once; the Mac's own list takes over a few seconds later
 return (d.ideas||[]).filter(x=>{const t=hid[x.idea_id||x.id];return !(t===true||(t&&now-t<9000));});}   // true = passed, the Mac hasn't confirmed yet (#256): it stays off the screen
function ideaBar(x){return (x.below_bar?'<span class="tag" style="background:var(--panel2);color:var(--sub)">BELOW YOUR BAR</span>':'')+(x.stale?'<span class="tag itag-stale">REFRESHING</span>':'');}
function ideaAgeNote(x){return ideaAge(x.ts)+(x.stale?' · refreshing':'');}
/* #252: what a fresh price says about the idea. The Buy button follows it, so it is never green (or silently off) when
   the price on screen says otherwise: 'no' = no edge left after Kalshi's fee (no Buy; get a new price), 'warn' = under
   your bar, or the chance fell 5+ points since the idea was found (yellow Buy anyway), '' = clears it (green Buy).
   Display only: the Mac's own guards on every buy are unchanged.
   #255: a game under way is priced only on a live fair chance (a fresh live line or the live model). With none (fair null,
   or a combo whose game under way has only a pre-game chance) there is no edge to claim: yellow Buy anyway, never green. */
function ideaNoFair(q){return `No fair price to check this against${q.nofair?`: ${q.nofair}`:''}. You'd be going on Kalshi's price alone.`;}
function ideaVerdict(x,q){if(!q)return {k:''};
 if(x.n===1&&q.fair==null)return {k:'warn',why:ideaNoFair(q)};
 if(x.n!==1&&q.nofair)return {k:'warn',why:ideaNoFair(q)};
 if(x.n===1){const c=Math.round(q.price*100),f=pct(q.fair),drop=!q.live&&x.chance!=null&&q.fair!=null&&x.chance-q.fair>=0.05,was=drop?` (it was ${pct(x.chance)} when this idea was found)`:'';
  if(!(q.edge>0))return {k:'no',why:`No longer a good bet. Kalshi wants ${c}¢ and the fair chance is now ${f}${was}, so there's no edge left after the fee.`};
  if(drop)return {k:'warn',why:`The fair chance has dropped to ${f}${was}. Only a small edge is left.`};
  if(q.clears===false&&q.live&&(q.warn||[]).some(w=>w.k==='thin'))return {k:'warn',why:`The market is thin right now (a wide gap between buy and sell), so this price may not be a real one.`};
  if(q.clears===false)return {k:'warn',why:`The edge left (${(q.edge*100).toFixed(1)}¢ a contract after the fee) is under your bar.`};
  return {k:''};}
 if(q.clears===false)return {k:'warn',why:`Kalshi's price now is ${pct(q.pct)} of fair, under your bar.`};
 return {k:''};}
function ideaButtons(x,q,fresh,left,det){const one=x.n===1,busy=!!(S.ibuy&&S.ibuy[x.id]),v=fresh?ideaVerdict(x,q):{k:''};
 const buy=busy?`<button class="btn ${v.k==='warn'?'warn':'yes'}" disabled><span class="spin"></span> Buying…</button>`
  :v.k==='no'?`<button class="btn acc" data-ib="${x.id}" onclick="priceIdea('${x.id}')">Get a new price</button>`
  :`<button class="btn ${v.k==='warn'?'warn':'yes'} qb" onclick="${one?'buySingle':'buyIdea'}('${x.id}')">${qBar(q)}${v.k==='warn'?'Buy anyway':'Buy'} · ${left}s</button>`;
 return `<div class="dbtns">${fresh?`<button class="btn ghost" ${busy?'disabled ':''}onclick="ideaPass('${x.id}',${det?'true':'false'})">Pass</button>${buy}`:
  `<button class="btn ghost" onclick="${det?'ideaNotNowSheet':'hideIdea'}('${x.id}')">Not now</button><button class="btn acc" ${det?'':`id="ib-${x.id}" `}data-ib="${x.id}" onclick="priceIdea('${x.id}')">${one?"Get today's price":'Get my price'}${stkLbl('id:'+x.id)}</button>`}</div>`;}
function ideaVd(x,q){const v=ideaVerdict(x,q);return (v.why?`<div class="ivd ${v.k}" role="status">${esc(v.why)}</div>`:'')+ideaWarn(q);}
/* where the fresh fair chance came from (#255), and Buy straight's cautions for a game under way (the first one, "under way",
   is said by the source line already) */
const IFSRC={'live line':'live line','live model':'live model','none':'no fair price'};
function ideaSrc(q){return q.fair_src?`<small class="ifsrc">${esc(IFSRC[q.fair_src]||q.fair_src)}</small>`:'';}
function ideaWarn(q){return (q&&q.warn||[]).filter(w=>w.k!=='live').map(w=>`<div class="sbw" data-w="${esc(w.k)}"><i>⚠️</i><span>${esc(w.t)}</span></div>`).join('');}
function ideaLiveNote(q){return q&&q.live?`<div class="m inow">Kalshi's price now · game under way</div>`:`<div class="m inow">Kalshi's price now</div>`;}
/* the last answer to a Buy tap on this idea, in plain words, on the card and the detail page (a toast alone sat behind
   the detail page, so a refusal there looked like nothing happened) */
function ideaAnsHtml(x){const a=S.ideaAns&&S.ideaAns[x.id];return a?`<div class="ians ${a.tone||''}" role="status">${esc(a.m)}</div>`:'';}
/* the amount row (issue #145): with a fresh price, or once Pete chose an amount (then Get price asks for that) */
function ideaStake(x,q,fresh){const key='id:'+x.id,mine=stkGet(key);if(!fresh&&mine==null)return '';S.idRec=S.idRec||{};const m=(fresh&&q)||S.idRec[x.id]||{};
 const rec=m.rec||x.stake||5;const small=!!(fresh&&q&&(q.nofair||q.small||(q.single&&q.fair==null)));   // #255: no fair price = no recommendation, only the smallest usual bet
 return stakeCtl({key,rec,cur:mine!=null?mine:fresh&&!q.single?q.stake:rec,min:m.min||1,max:m.max||100,room:m.room,ev:fresh?q.ev:null,small})
  +(fresh&&q.note?`<div class="stkm" data-w="depth">${esc(q.note)}</div>`:'');}
function ideaQuote(x,q,fresh){if(!fresh)return ideaAnsHtml(x)+ideaStake(x,q,false);const vd=ideaVd(x,q);
 return (x.n===1?`${ideaLiveNote(q)}<div class="dnums"><div>Price now<b>${Math.round(q.price*100)}¢</b></div><div>Fair chance<b>${pct(q.fair)}</b>${ideaSrc(q)}</div><div>Edge after fee${q.edge==null?'<b>—</b>':`<b class="${q.edge>0?'up':'down'}">${(q.edge*100).toFixed(1)}¢</b>`}</div><div>Buy now<b>${q.n} contract${q.n===1?'':'s'} · ${money(q.stake)}</b></div><div>Pays if it wins<b>${money(q.pays)}</b></div></div>`
  :`<div class="dnums"><div>Your price now<b class="${q.clears?'up':''}">${money(q.stake)} → ${money(q.pays)}</b></div><div>Share of fair<b>${pct(q.pct)}</b>${ideaSrc(q)}</div></div>`)+vd+ideaAnsHtml(x)+ideaStake(x,q,true);}
/* once a fresh price is on screen, the numbers from when the idea was found are marked as older (#252) */
function ideaOld(html,x,fresh){return fresh&&html?`<div class="iold"><div class="m">When this idea was found · ${esc(ideaAge(x.ts).replace(/^Price /,''))} · older than the price below</div>${html}</div>`:html;}
function ideaCard(x){const q=S.ideaq[x.id];const fresh=q&&Date.now()/1000-q.at<20;
 const left=fresh?Math.max(0,Math.round(20-(Date.now()/1000-q.at))):0;const k=x.idea_id||x.id;
 if(S.ideaGone&&S.ideaGone[x.id])return `<div class="iw" data-id="${x.id}"><div class="dcard idea gone" id="idea-${x.id}"><div><h4>${x.n===1?'🎯':'💡'} ${esc(x.picks)}</h4><p>Not available on Kalshi right now, so this idea is coming off the list.</p></div></div></div>`;
 const xb=`<button class="ix" type="button" aria-label="Dismiss this idea" onclick="event.stopPropagation();ideaX('${x.id}')"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 8l8 8M16 8l-8 8"/></svg></button>`;
 const cls=`dcard idea itap${x.stale?' stale':''}${x.below_bar?' below':''}${S.hl===x.id?' flash':''}${(S.ideaBack||[]).includes(k)?' rise':''}`;
 const open=`id="idea-${x.id}" data-ik="${k}" onclick="ideaOpen(event,'${x.id}')"`;
 if(x.n===1){const li=(x.legs_info||[])[0];
  return `<div class="iw" data-id="${x.id}"><div class="${cls}" ${open}><div>${ideaHead(x,li)}
   <p>${esc(ideaAgeNote(x))} · Kalshi's price is below the sharp books' chance of winning, after Kalshi's fee. No combo maker taking a cut.</p>
   ${x.note?`<p style="margin-top:6px">🩹 ${esc(x.note)}</p>`:''}
   ${ideaOld(ideaFacts(x),x,fresh)||`<div class="dnums"><div>Value<b>${pct(x.pct)} of fair</b></div></div>`}
   ${ideaQuote(x,q,fresh)}</div>${ideaButtons(x,q,fresh,left,false)}${xb}</div></div>`;}
 return `<div class="iw" data-id="${x.id}"><div class="${cls}" ${open}><div><h4>💡 ${esc(x.picks)}${x.live?' <span class="tag" style="background:var(--livebg);color:var(--live)">IN PROGRESS</span>':''}${ideaBar(x)}</h4><p>${esc(x.sport)} · ${x.n} picks · priced at <b>${pct(x.pct)}</b> of fair · ${esc(ideaAgeNote(x))}${x.kick?' · first game starts '+new Date(x.kick*1000).toLocaleTimeString([],{weekday:'short',hour:'numeric',minute:'2-digit'}):''}</p>
   ${(x.legs_info||[]).map(li=>ideaLeg(li)).join('')}
   ${x.note?`<p style="margin-top:6px">🩹 ${esc(x.note)}</p>`:''}
   ${ideaOld(ideaFacts(x),x,fresh)}
   <div class="dnums">${x.price_c!=null?'':`<div>Last price<b>${money(x.stake)} → ${money(x.pays)}</b></div><div>Fair payout<b>${money(x.fair)}</b></div>`}${fresh?`<div>Your price now<b class="${q.clears?'up':''}">${money(q.stake)} → ${money(q.pays)}</b></div><div>Share of fair<b>${pct(q.pct)}</b>${ideaSrc(q)}</div>`:''}</div>${fresh?ideaVd(x,q):''}${ideaAnsHtml(x)}${ideaStake(x,q,fresh)}</div>
   ${ideaButtons(x,q,fresh,left,false)}${xb}</div></div>`;}
function ideaSection(d){if(!Array.isArray(d.ideas))return '';S.ideaq=S.ideaq||{};
 const all=ideaList(d),lim=+d.ideas_limit>0?+d.ideas_limit:(all.length||1),top=all.slice(0,lim),more=all.slice(lim),open=!!S.ideasMore;
 const hid=+d.ideas_hidden||0,back=hid?`<button class="linkb" type="button" onclick="ideasRestore()">${hid} hidden · Show again</button>`:'';
 const right=all.length?`<span class="r clr"><button class="btn ghost sm" type="button" onclick="ideaClearAll()">Clear all</button></span>`:'';
 const body=all.length?`<div class="m icap">Best expected profit first · Kalshi priced these at or above your cut-off</div><div class="doit ilist">${top.map(ideaCard).join('')}</div>
   ${more.length?`<button class="imore ${open?'open':''}" type="button" aria-expanded="${open}" onclick="ideasMoreTog(this)"><span class="chev">▾</span>${more.length} more idea${more.length>1?'s':''}</button>
   <div class="fold ${open?'':'shut'}" id="imore"><div class="fin"><div class="doit ilist">${more.map(ideaCard).join('')}</div></div></div>`:''}${back}${sbSkipLine(d.ideas_sb,'ideas')}`
  :`<div class="iempty" role="status"><svg viewBox="0 0 48 48" aria-hidden="true"><circle cx="24" cy="24" r="19" fill="none" stroke="currentColor" stroke-width="2.4" opacity=".45"/><path d="M15.5 25l6 6 11-13" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
   <b>Nothing clears your bar right now</b><span>${hid?'You\'ve cleared today\'s ideas.':'New ideas show up here when Kalshi prices one below the sharp books\' chance.'}</span>${back}${sbSkipLine(d.ideas_sb,'ideas')}</div>`;
 return foldHead('ideas','Buy ideas',all.length,right)+foldB('ideas')+body+foldE();}
function ideasMoreTog(b){hap('selection');S.ideasMore=!S.ideasMore;b.classList.toggle('open',S.ideasMore);b.setAttribute('aria-expanded',S.ideasMore);const f=$('#imore');if(f)f.classList.toggle('shut',!S.ideasMore);}

/* ---- dismiss: the X, a swipe left, Not now and Clear all all end up here. The card slides out and the list closes
   the gap, then the Mac remembers (until the price or edge improves, or tomorrow); Undo brings it straight back. */
function ideaOut(ids,done){const els=ids.map(i=>document.querySelector(`.iw[data-id="${i}"]`)).filter(Boolean);
 if(!els.length||matchMedia('(prefers-reduced-motion: reduce)').matches){done();return;}
 S.scrub=true;   // the page holds still while the cards slide out (a refresh now would put them back)
 els.forEach((el,i)=>{const h=el.offsetHeight;el.style.height=h+'px';el.style.overflow='hidden';el.style.setProperty('--d',(i*50)+'ms');el.offsetHeight;el.classList.add('out');});
 setTimeout(()=>els.forEach(el=>{el.style.height='0px';el.style.marginBottom='-10px';el.style.opacity='0';}),170+(els.length-1)*50);
 setTimeout(()=>{S.scrub=false;done();},470+(els.length-1)*50);}
/* Pass / X / Not now / swipe / Clear all (#256): the idea leaves the screen at once and STAYS off it. The Mac is told in the
   background (with `seen`, the fresh price Pete was looking at, so that very price can't bring the idea back), retried a few
   times if the link is down ("Reconnecting to your Mac"), and if it never gets through the idea stays hidden on this phone
   and says so. It used to put the card back when the first try failed, which looked like Pass doing nothing. */
let IDEA_SAVE_WAIT=[0,2500,7000,15000,30000,60000,60000,120000],IDEA_SAY=4;   // tries, then the pause before each; it says so after IDEA_SAY failed tries and keeps trying
function ideaSeen(x){const q=S.ideaq&&S.ideaq[x.id];if(!q||!q.stake||!q.pays||q.pct==null||Date.now()/1000-q.at>180)return null;
 const p=q.stake/q.pays*100,e=q.pct-1;return isFinite(p)&&isFinite(e)?{price_c:Math.round(p*10)/10,edge:Math.round(e*10000)/10000}:null;}
async function ideaSave(keys,why,seen,job){let r=null,said=false;
 for(let i=0;i<IDEA_SAVE_WAIT.length;i++){
  if(IDEA_SAVE_WAIT[i])await new Promise(f=>setTimeout(f,IDEA_SAVE_WAIT[i]));
  if(job.undone)return 'undone';
  r=await api('/app/api/act',{a:'idea_dismiss',ids:keys,why,seen}).catch(()=>null);
  if(r&&r.ok)return 'ok';
  if(job.undone)return 'undone';
  if(!said&&i+1>=IDEA_SAY&&i+1<IDEA_SAVE_WAIT.length){said=true;toast('Hidden on this phone. Your Mac hasn\'t got that yet, still trying.',5000);}}
 return 'failed';}
async function ideaSend(list,why){S.idHide=S.idHide||{};S.idJob=S.idJob||{};
 const keys=list.map(x=>x.idea_id||x.id).filter(k=>S.idHide[k]!==true);if(!keys.length)return;   // a second tap on the same idea sends nothing
 const seen={};list.forEach(x=>{const k=x.idea_id||x.id,v=ideaSeen(x);if(v)seen[k]=v;if(S.ideaq)S.ideaq[x.id]=null;});
 const job={undone:false};keys.forEach(k=>{S.idHide[k]=true;S.idJob[k]=job;});S.ideaBack=null;renderLive();
 if(why==='later')undoBar(list.length>1?list.length+' ideas hidden':'Idea hidden until its price improves, or tomorrow',()=>ideaUndo(keys));
 job.p=ideaSave(keys,why,seen,job);const res=await job.p;
 keys.forEach(k=>{if(S.idJob[k]===job)delete S.idJob[k];});
 if(res==='ok')keys.forEach(k=>{if(S.idHide[k]===true)S.idHide[k]=Date.now();});   // the Mac's own list takes over a few seconds later
 else if(res==='failed')toast('Hidden on this phone, but your Mac never got it. It may come back after a refresh.',6000);}
async function ideaUndo(keys){const jobs=keys.map(k=>S.idJob&&S.idJob[k]).filter(Boolean);
 jobs.forEach(j=>{j.undone=true;});await Promise.all(jobs.map(j=>j.p));   // a save still on its way finishes (or stops) first, so Undo is always the last word
 const r=await api('/app/api/act',{a:'idea_undo',ids:keys}).catch(()=>null);
 if(!r||!r.ok){keys.forEach(k=>{if(S.idHide[k]===true)S.idHide[k]=Date.now();});toast('Couldn\'t bring it back just now.',3000);return;}
 keys.forEach(k=>{delete S.idHide[k];});S.ideaBack=keys;renderLive();await load('live',true);setTimeout(()=>{S.ideaBack=null;},900);}
async function ideasRestore(){hap('light');const r=await api('/app/api/act',{a:'idea_undo',all:true}).catch(()=>null);
 if(!r||!r.ok){toast('Couldn\'t bring them back just now.',3000);return;}
 S.idHide={};renderLive();await load('live',true);toast('Hidden ideas are back on the list.',2800);}
function ideaFind(id){return ((S.live&&S.live.ideas)||[]).find(i=>i.id===id||i.idea_id===id);}
function ideaX(id){if(S.ibuy&&S.ibuy[id]){toast('That buy is still on its way.',2500);return;}const x=ideaFind(id);if(!x)return;hap('light');ideaOut([id],()=>ideaSend([x],'later'));}
function hideIdea(id){ideaX(id);}                       // the card's "Not now" means dismiss
/* Pass (after Get price) closes the idea just like the X: through the same dismiss path (it slides out, the Mac remembers,
   Undo). On the detail page the page closes back to Live first, then the card slides out. Off while a buy is on its way. */
function ideaPass(id,det){if(S.ibuy&&S.ibuy[id])return;
 if(S.ideaTid===id){clearInterval(S.ideaT);S.ideaT=null;S.ideaTid=null;}
 if(!ideaFind(id)){if(det)closeModal();renderLive();return;}
 if(det)ideaNotNowSheet(id);else ideaX(id);}
function ideaNotNowSheet(id){const x=ideaFind(id);hap('light');closeModal();if(x)setTimeout(()=>ideaOut([x.id],()=>ideaSend([x],'later')),340);}
function ideaClearAll(){const xs=ideaList(S.live||{});if(!xs.length)return;hap('light');ideaOut(xs.map(x=>x.id),()=>ideaSend(xs,'later'));}
/* a bought idea (or one Kalshi no longer lists) is dropped quietly, no Undo: bought ones never come back */
function ideaDrop(id,why,x0){const x=ideaFind(id)||x0;if(!x)return;   // x0: the idea as it was when the buy started, in case a refresh replaced the list meanwhile
 if(S.ideaOpen&&S.ideaOpen===(x.idea_id||x.id))closeModal();ideaSend([x],why);}
function undoBar(msg,fn){let b=$('#undo');if(!b){b=document.createElement('div');b.id='undo';b.setAttribute('role','status');b.setAttribute('aria-live','polite');document.body.appendChild(b);}
 clearTimeout(b._t);b._fn=fn;b.innerHTML=`<span>${esc(msg)}</span><button type="button" onclick="undoGo()">Undo</button>`;b.hidden=false;void b.offsetWidth;b.classList.add('on');b._t=setTimeout(undoHide,6000);}
function undoGo(){const b=$('#undo'),f=b&&b._fn;undoHide();if(f)f();}
function undoHide(){const b=$('#undo');if(!b)return;clearTimeout(b._t);b._fn=null;b.classList.remove('on');setTimeout(()=>{if(!b.classList.contains('on'))b.hidden=true;},320);}
/* swipe left on a card to dismiss it. touch-action:pan-y on the card leaves vertical scrolling to the browser; the
   gesture only becomes a swipe once it is clearly sideways (more than 1.6x as far across as down), so a scroll that
   starts on a card still scrolls. Past a third of the card (or 110 px) it dismisses on release; short of that it
   springs back. The page holds still (S.scrub) while the finger is down. */
(()=>{let c=null,x0=0,y0=0,dx=0,lock=null,w=0,past=false;
 const reset2=el=>{el.classList.remove('swp','swpast');el.style.removeProperty('--sx');el.style.opacity='';};
 const reset=()=>{if(c)reset2(c);c=null;lock=null;};
 addEventListener('touchstart',e=>{const el=e.target.closest&&e.target.closest('.dcard.idea[data-ik]:not(.gone)');
  if(!el||e.touches.length!==1||e.target.closest('input,select,textarea')){c=null;return;}
  c=el;x0=e.touches[0].clientX;y0=e.touches[0].clientY;dx=0;lock=null;past=false;w=el.offsetWidth;},{passive:true});
 addEventListener('touchmove',e=>{if(!c)return;const t=e.touches[0],mx=t.clientX-x0,my=t.clientY-y0;
  if(lock==null){if(Math.abs(mx)<10&&Math.abs(my)<10)return;lock=mx<0&&Math.abs(mx)>Math.abs(my)*1.6?'x':'y';if(lock==='x'){S.scrub=true;c.classList.add('swp');}else{c=null;return;}}
  dx=Math.min(0,mx);c.style.setProperty('--sx',dx+'px');c.style.opacity=String(Math.max(.35,1+dx/(w*1.1)));
  const p=-dx>Math.min(110,w*.33);if(p!==past){past=p;hap(p?'light':'selection');c.classList.toggle('swpast',p);}},{passive:true});
 const end=()=>{if(!c)return;const el=c,go=lock==='x'&&-dx>Math.min(110,w*.33);const was=lock==='x';
  if(was){S.swAt=Date.now();S.scrub=false;}
  if(go){const id=(el.id||'').replace(/^idea-/,''),iw=el.closest('.iw'),x=ideaFind(id);c=null;lock=null;
   if(x&&iw){hap('light');iw.classList.add('out');el.offsetWidth;el.classList.remove('swp');el.style.removeProperty('--sx');el.style.opacity='';ideaOut([x.id],()=>ideaSend([x],'later'));}   // carries on from where the finger left it
   else reset2(el);}
  else reset();
  if(was&&S.liveDirty){S.liveDirty=false;if(S.view==='live')renderLive();}};
 addEventListener('touchend',end,{passive:true});addEventListener('touchcancel',()=>{if(c&&lock==='x'){S.scrub=false;}reset();if(S.liveDirty){S.liveDirty=false;if(S.view==='live')renderLive();}},{passive:true});})();

/* ---- the detail page: tap a card (not a button) */
function ideaOpen(e,id){if(e&&e.target&&e.target.closest('button,a,input,select,.ileg,.stk'))return;if(Date.now()-(S.swAt||0)<450)return;openIdea(id);}
const IKIND={win:'Single game',spread:'Spread',total:'Total'};
function ideaTk(li){return li&&/^[A-Z0-9._-]{3,120}$/.test(li.ticker||'')?li.ticker:'';}
function openIdea(id){const x=ideaFind(id);if(!x)return;id=x.idea_id||x.id;S.gameOpen=null;S.comboOpen=null;S.ideaOpen=id;S.ideaReady=null;S.ideaSig=null;S.ideaDepth=null;
 pushOpen('Buy idea');const tk=x.n===1?ideaTk((x.legs_info||[])[0]):'';
 if(tk)api('/app/api/act',{a:'idea_depth',t:tk}).then(r=>{S.ideaDepth={id,d:r&&r.ok?r:{err:(r&&r.msg)||'Couldn\'t read Kalshi\'s book just now.'}};ideaSheet();}).catch(()=>{S.ideaDepth={id,d:{err:'Couldn\'t reach the Mac.'}};ideaSheet();});
 pushWait().then(()=>{S.ideaReady=id;ideaSheet();});}
function ideaWhy(x){const li=(x.legs_info||[])[0]||{},worth=x.stake&&x.pct?x.stake*x.pct:null;
 if(x.n>1)return `Kalshi sells this combo for ${money(x.stake)}. At the sharp sportsbooks' chances for each pick it is worth about ${worth!=null?money(worth):'more'}, so it is priced at ${pct(x.pct)} of fair.`;
 if(li.kind==='spread'||li.kind==='total')return `Books don't post this exact bet, so the chance comes from the sportsbook's line run through a score model. Kalshi's price after its fee is ${Math.round(x.price_c)}¢ against a ${pct(x.chance)} chance. Models add their own error, so a small edge counts for little.`;
 return `The sharp sportsbooks, with their margin taken out and checked against your own record, give this a ${pct(x.chance)} chance. Kalshi sells it at ${Math.round(x.price_c)}¢ including its fee. That gap is the edge.`;}
function ideaSell(x){if(x.n>1)return `<p>Combos are sold back to Kalshi at its offer (it shows on Live once you own it). There is no order book to read for a combo.</p>`;
 const D=S.ideaDepth&&S.ideaDepth.id===(x.idea_id||x.id)?S.ideaDepth.d:null;if(!D)return `<p class="m">Checking Kalshi's order book…</p>`;if(D.err)return `<p class="m">${esc(D.err)}</p>`;
 const gap=D.spread!=null?Math.round(D.spread*100):null,c=v=>v!=null?Math.round(v*100)+'¢':'—';
 return `<div class="dkpis"><div><span>Bid</span><b>${c(D.bid)}</b></div><div><span>Ask</span><b>${c(D.ask)}</b></div><div><span>Gap</span><b>${gap!=null?gap+'¢':'—'}</b></div><div><span>Contracts at the ask</span><b>${D.ask_size!=null?ideaCount(D.ask_size):'—'}</b></div></div>
  <p class="m">${gap!=null&&gap<=6?'Easy to sell back: the gap is small, so selling early would cost little.'+(D.ask_size!=null&&D.ask_size<100?' Only '+Math.round(D.ask_size)+' contracts are at the ask, so a big sale could move the price.':''):'Harder to sell early: the gap is wide or the book is empty, so selling '+(x.live||(S.ideaq[x.id]||{}).live?'now':'before the game')+' would give up a lot.'}</p>`;}
function ideaCount(n){n=Math.round(+n||0);return n>=999500?(n/1e6).toFixed(1).replace(/\.0$/,'')+'M':n>=1e4?Math.round(n/1000)+'k':n.toLocaleString();}   // 94080 -> 94k
function ideaMoved(x){const h=x.hist;if(!h||h.length<2)return '';const v=h.map(p=>p[1]),lo=Math.min(...v)-.5,hi=Math.max(...v)+.5,W=300,H=56,last=v[v.length-1],first=v[0];
 if(Math.max(...v)-Math.min(...v)<.05)return `<h2 style="margin:18px 0 6px">How the price has moved</h2><p class="m">It hasn't moved since it was found: ${Math.round(first)}¢ (cents paid for each $1 it pays).</p>`;
 const path=sparkPath(h,W,H-6,lo,hi);const col=last<=first?'var(--yes)':'var(--no)';
 return `<h2 style="margin:18px 0 6px">How the price has moved</h2><div class="imv"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Kalshi's price over time"><path d="${path} L${W} ${H} L0 ${H}Z" fill="${col}" opacity=".10"/><path d="${path}" fill="none" stroke="${col}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg></div>
  <p class="m">First seen at ${Math.round(first)}¢, ${Math.round(last)}¢ at the last quote (cents paid for each $1 it pays).</p>`;}
function ideaBody(x){const li=(x.legs_info||[])[0]||{},one=x.n===1,q=S.ideaq[x.id],fresh=q&&Date.now()/1000-q.at<20,left=fresh?Math.max(0,Math.round(20-(Date.now()/1000-q.at))):0,tk=one?ideaTk(li):'';
 const lg=li.league_name||x.league_name||x.sport||'',kind=one?(IKIND[li.kind]||'Single game'):'Combo · '+x.n+' picks';
 const when=one?[li.game,ideaWhen(li)].filter(Boolean).join(' · '):'';
 const kp=x.price_c!=null&&x.fair_c!=null?`<div class="dkpis"><div><span>Kalshi price</span><b>${Math.round(x.price_c)}¢</b></div><div><span>Fair price</span><b>${Math.round(x.fair_c)}¢</b></div><div><span>Edge</span><b class="${(x.edge||0)>=0?'up':'down'}">${(x.edge||0)>=0?'+':'−'}${Math.abs(Math.round((x.edge||0)*100))}%</b></div><div><span>Chance to win</span><b>${pct(x.chance)}</b></div><div><span>Stake → if it wins</span><b>${money(x.stake)} → ${money(x.pays)}</b></div><div><span>Expected profit</span><b class="${(x.profit||0)>0?'up':(x.profit||0)<0?'down':''}">${(x.profit||0)>0?'+':''}${(x.profit||0)<0?'−'+money(Math.abs(x.profit)):money(x.profit)}</b></div></div>`
  :`<div class="dkpis"><div><span>Priced at</span><b>${pct(x.pct)} of fair</b></div><div><span>Stake → if it wins</span><b>${money(x.stake)} → ${money(x.pays)}</b></div></div>`;
 return `<div class="dhead"><div><div class="m ihd2">${esc((li.icon||x.icon||'')+' '+lg)} · ${esc(kind)}${x.live?' · in progress':''}${x.below_bar?' · below your bar':''}</div>
   <h3 style="font-size:22px;overflow-wrap:anywhere">${esc(one?(li.plain||x.picks):x.picks)}</h3>${when?`<div class="m">${esc(when)}</div>`:''}</div></div>
  ${ideaOld(kp,x,fresh)}<p class="m">${esc(ideaAgeNote(x))}${x.stale?'. Tap Get today\'s price for the live number before you buy.':''}</p>
  ${one?'':`<h2 style="margin:6px 0 4px">Picks <span class="n">${x.n}</span></h2>${(x.legs_info||[]).map(l=>ideaLeg(l)).join('')}`}
  <h2 style="margin:18px 0 6px">Why it was picked</h2><p>${(x.live||fresh&&q.live)&&one?'Before the game: ':''}${esc(ideaWhy(x))}</p>${x.note?`<p>🩹 ${esc(x.note)}</p>`:''}
  ${ideaMoved(x)}
  <h2 style="margin:18px 0 6px">Could you sell it?</h2>${ideaSell(x)}
  ${ideaQuote(x,q,fresh)}
  <div class="idact">${ideaButtons(x,q,fresh,left,true)}${tk?`<button class="btn" type="button" onclick="openGame('${tk}')">Open the game page</button>`:''}</div>`;}
function ideaSheet(){const id=S.ideaOpen;if(!id||S.ideaReady!==id||!$('#modal').classList.contains('on'))return;
 const x=ideaFind(id),sh=$('#sheet');
 if(!x){const sig='gone';if(S.ideaSig===sig)return;S.ideaSig=sig;pushFill('<h3>Not on the list any more</h3><p>This idea was bought, dismissed or has expired. New ones show up on Live.</p>','Buy idea');return;}
 const q=S.ideaq[x.id],fresh=q&&Date.now()/1000-q.at<20,left=fresh?Math.round(20-(Date.now()/1000-q.at)):0;
 const sig=JSON.stringify([x.id,x.price_c,x.edge,x.stale,x.below_bar,Math.floor(Date.now()/15000),x.hist&&x.hist.length,fresh?q.at:0,left,S.ideaDepth&&S.ideaDepth.id===id?S.ideaDepth.d:0,stkGet('id:'+x.id),S.ideaAns&&S.ideaAns[x.id],!!(S.ibuy&&S.ibuy[x.id])]);
 if(S.ideaSig===sig)return;S.ideaSig=sig;const top=sh.scrollTop;pushFill(ideaBody(x),'Buy idea');sh.scrollTop=top;}

/* ---- getting a price and buying: the same guarded Mac paths as always */
async function priceIdea(id){if(S.ideaAns)delete S.ideaAns[id];document.querySelectorAll(`[data-ib="${id}"]`).forEach(b=>{b.disabled=true;b.innerHTML='<span class="spin"></span> Asking Kalshi…';});
 const want=stkGet('id:'+id),r=await api('/app/api/act',{a:'idea',id,stake:want}).catch(()=>({ok:false}));
 if(want!==stkGet('id:'+id))return;   // Pete changed the amount while this price was on its way: the newer ask wins
 if(!r.ok){if(r.gone)return ideaGone(id,r.msg);toast(r.msg||'No price came in. Try again in a minute.',5000);renderLive();return;}
 S.ideaq[id]={i:r.i,pays:r.pays,stake:r.stake,pct:r.pct,clears:r.clears,at:Date.now()/1000,price:r.price,n:r.n,edge:r.edge,fair:r.fair,single:r.single,rec:r.rec,ev:r.ev,room:r.room,max:r.max,min:r.min,note:r.note,live:r.live,how:r.how,fair_src:r.fair_src,nofair:r.nofair,warn:r.warn,small:r.small};
 S.idRec=S.idRec||{};S.idRec[id]={rec:r.rec,room:r.room,max:r.max,min:r.min};if(S.ideaOpen===id)ideaSheet();renderLive();
 clearInterval(S.ideaT);S.ideaTid=id;S.ideaT=setInterval(()=>{const open=$('#modal').classList.contains('on');if(S.ideaOpen&&open)ideaSheet();else if(S.view==='live'&&!open)renderLive();const q=S.ideaq[id];if(!q||Date.now()/1000-q.at>21){clearInterval(S.ideaT);renderLive();}},1000);}
/* Buy (#252): every tap ends with an answer in plain words, on the page itself (the card, or the detail page, where a toast
   alone was hidden behind it; there a refusal shows only on the page) and as a toast: bought, refused (Kalshi's or the guard's own words), unclear ("check"),
   the price ran out, or the Mac couldn't be reached. A second tap while one is on its way sends nothing. The order still
   goes through the same Mac paths and guards as before (Pause, caps, the unknown-outcome block, one order per idea). */
function ideaAns(id,m,tone){S.ideaAns=S.ideaAns||{};S.ideaAns[id]={m,tone,at:Date.now()};}
function ideaOnPage(){return !!(S.ideaOpen&&$('#modal').classList.contains('on'));}
function ideaRedraw(){if(S.ideaOpen&&$('#modal').classList.contains('on'))ideaSheet();if(S.view==='live')renderLive();}
async function ideaBuyGo(id,body,okMsg){const q=S.ideaq&&S.ideaq[id],x0=ideaFind(id);S.ibuy=S.ibuy||{};
 if(S.ibuy[id]){toast('That buy is already on its way.',2500);return;}
 if(!q||Date.now()/1000-q.at>=20){if(S.ideaq)S.ideaq[id]=null;const m='That price ran out before your tap, so nothing was sent. Get a new price, then Buy.';ideaAns(id,m,'bad');if(!ideaOnPage())toast(m,5000,'bad');else hap('warning');ideaRedraw();return;}
 S.ibuy[id]=1;if(S.ideaAns)delete S.ideaAns[id];ideaRedraw();let r;
 try{r=await api('/app/api/act',body(q));}
 catch(e){r={ok:false,lost:true,msg:'Couldn\'t reach your Mac, so this may or may not have gone through. Check Live before trying again.'};}
 finally{delete S.ibuy[id];}
 r=r||{ok:false};S.ideaq[id]=null;if(r.ok&&S.stk)delete S.stk['id:'+id];
 const m=r.ok?okMsg(q,r):(r.msg||r.error||(r.check?'Kalshi didn\'t answer clearly, so this may or may not have been bought. Check Kalshi before trying again.':'Kalshi didn\'t take it, so nothing was bought. Get a new price to try again.'));
 const tone=r.ok?'good':r.check||r.lost?null:'bad';ideaAns(id,m,tone);
 if(r.ok||r.check||!ideaOnPage())toast(m,6000,tone);else hap(tone==='bad'?'error':'warning');   // on the detail page a refusal shows on the page itself (the toast would cover its buttons)
 if(r.ok||r.check)ideaDrop(id,'bought',x0);else ideaRedraw();load('live',true);}
function buyIdea(id){return ideaBuyGo(id,q=>({a:'buy',i:q.i}),(q,r)=>`Bought: ${money(q.stake)} to win ${money(r.pays||q.pays)}. It shows in your combos within a minute.`);}
function buySingle(id){return ideaBuyGo(id,q=>({a:'singlebuy',id,n:q.n,price:q.price}),(q,r)=>r.msg||'Bought.');}
function ideaGone(id,msg){S.ideaGone=S.ideaGone||{};S.ideaGone[id]=1;hap('light');toast(msg||'That idea isn\'t on Kalshi any more.',3500);renderLive();
 setTimeout(()=>{delete S.ideaGone[id];ideaDrop(id,'gone');},4500);}
