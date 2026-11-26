// ---------------- LIVE
/* Display only (issue #320): the colour of a leg's chip, ring and the legend. A known score decides it: ahead = green,
   behind = red, level (0-0 at kickoff included) = tied, never red because the chance is under 50%. Only a leg with no
   numeric score (a fight, a feed with no points) falls back to the chance. pick_state and every money path never read this. */
function legCls(l){if(l.res==='yes')return 'won';if(l.res==='no')return 'lost';if(l.state!=='live'||l.phase==='probably_over'||l.phase==='over'||l.phase==='waiting')return '';
 const sc=l.sc,num=v=>typeof v==='number'&&isFinite(v);
 if(sc&&num(sc.me)&&num(sc.opp))return sc.me>sc.opp?'up':sc.me<sc.opp?'down':'live';
 const ch=l.live!=null?l.live:l.chance;
 if(ch!=null&&ch>=.6)return 'up';if(ch!=null&&ch<=.4)return 'down';return 'live';}
function legTag(l){const c=legCls(l);const sc=l.state==='live'&&l.sc?` ${l.sc.me}–${l.sc.opp}`:'';
 const pre=c==='won'?'✓ ':c==='lost'?'✕ ':['up','down','live'].includes(c)?'<i class="pd"></i>':'';
 const tip=l.phase==='probably_over'?'Probably finished, waiting on Kalshi':l.phase==='waiting'?'Not started yet':c==='up'?'Winning right now':c==='down'?'Losing right now':c==='live'?'Tied or close':c==='won'?'Won':c==='lost'?'Lost':'Not started';
 return `<span class="leg ${c}" title="${tip}">${pre}${esc(betChip(l))}${sc}</span>`;}
function legTags(ls){const o=[...ls].sort((a,b)=>(b.state==='live')-(a.state==='live')||(b.res==='yes')-(a.res==='yes'));
 const max=7;return o.slice(0,max).map(legTag).join('')+(o.length>max?`<span class="leg">+${o.length-max}</span>`:'');}
const PLACE_END=new Set(['City','Orleans','York','Bay','Angeles','Vegas','Francisco','Diego','Jersey','England','Louis','Antonio','Lake','Jose','Carolina','Florida','Dakota','Mexico','Virginia','Kentucky','Michigan','Illinois','Texas','Tech','State','Coast']);
function short(n){n=String(n||'');const p=n.split(' ');if(p.length<2||n.length<=14)return n;const last=p[p.length-1];
 if(PLACE_END.has(last))return p.slice(0,-1).map(w=>w[0]+'.').join('')+' '+last;   // "San Francisco" -> "S. Francisco", never just "City"
 return last;}
function plOf(c){return c.group==='won'?(c.pays||0)-c.cost:c.group==='cashed'?(c.back||0)-c.cost:c.group==='lost'?-c.cost:0;}
function doneWord(ts){   // issue #207, display only: the day a settled bet's money moved, in the phone's own time zone
 const x=new Date(ts*1000);if(!ts||isNaN(x))return '';const now=new Date();
 const n=Math.round((new Date(now.getFullYear(),now.getMonth(),now.getDate())-new Date(x.getFullYear(),x.getMonth(),x.getDate()))/864e5);
 if(n===0)return 'Today';if(n===1)return 'Yesterday';
 return x.toLocaleDateString('en-US',x.getFullYear()===now.getFullYear()?{weekday:'short',month:'short',day:'numeric'}:{weekday:'short',month:'short',day:'numeric',year:'numeric'}).replace(/,/g,'');}
function doneKey(c){return c.done_at||Date.parse(String(c.week||'')+'T12:00:00')/1000||0;}   // when it settled; else its slate day (the old order)
function plPill(c){const v=plOf(c);return `<div class="verdict pl ${v>0.004?'won':v<-0.004?'lost':'cashed'}"><b>${v>=0?'+':'−'}${money(Math.abs(v))}</b><small>${c.group==='won'?'Won':c.group==='cashed'?'Cashed out':'Lost'}</small></div>`;}
try{S.sf=JSON.parse(localStorage.getItem('cw_sf')||'null')||{o:'all',sp:'all',sort:'new'}}catch(e){S.sf={o:'all',sp:'all',sort:'new'}}
function setSf(k,v){hap('selection');S.sf[k]=v;try{localStorage.setItem('cw_sf',JSON.stringify(S.sf))}catch(e){}renderLive();}
function settledBar(cs){const done=cs.filter(c=>c.group!=='pending');const f=S.sf;const sps=[...new Set(done.flatMap(c=>c.sports))].filter(s=>SPN[s]);
 const net=done.filter(c=>settledOk(c)).reduce((a,c)=>a+plOf(c),0),n=done.filter(c=>settledOk(c)).length;
 const ch=(k,v,l)=>`<button class="chip ${f[k]===v?'on':''}" onclick="setSf('${k}','${v}')">${l}</button>`;
 return `<div class="sbar"><div class="chips">${ch('o','all','All')}${ch('o','profit','Profit')}${ch('o','loss','Loss')}${ch('o','won','Won')}${ch('o','cashed','Cashed early')}${ch('o','lost','Lost')}</div>
  ${sps.length>1?`<div class="chips">${ch('sp','all','All sports')}${sps.map(s=>ch('sp',s,(ICON[s]||'')+' '+SPN[s])).join('')}</div>`:''}
  <div class="chips">${ch('sort','new','Newest')}${ch('sort','best','Biggest profit')}${ch('sort','worst','Biggest loss')}${ch('sort','pay','Biggest payout')}</div>
  <div class="snet">${n} settled · net <b class="${net>=0?'up':'down'}">${net>=0?'+':'−'}${money(Math.abs(net))}</b></div></div>`;}
function settledOk(c){const f=S.sf,v=plOf(c);return (f.o==='all'||(f.o==='profit'&&v>0)||(f.o==='loss'&&v<0)||f.o===c.group)&&(f.sp==='all'||c.sports.includes(f.sp));}
/* A combo smart sell looks after (not "I'll sell it") shows SELL only when smart sell would sell it now (nudge, #210):
   the older Let it ride plan's verdict flips on the Mac's estimated offer, so on its own it says HOLD and its sentence is
   left out. "I'll sell it" combos keep the plan's advice. */
function planOn(c){return !!(c.self||c.nudge);}
function verdictShown(c){return planOn(c)?c.verdict:'hold';}
function whyShown(c){return planOn(c)||c.verdict==='hold'?c.why:'';}
function verdictOf(c){if(c.group==='won')return['won','WON'];if(c.group==='lost')return['lost','OUT'];if(c.group==='cashed')return['cashed','CASHED'];
 const v=verdictShown(c);if(v==='sell')return['sell','SELL'];if(v==='half')return['sell','SELL ½'];
 if(c.smart_state==='go'&&!c.self)return['sell','SET TO SELL'];if(c.smart_state==='reached'&&!c.self)return['hold','Ready to sell'];return['hold','HOLD'];}
function nextLine(c){if(c.group!=='pending')return c.preview||'';const lv=c.legs.find(l=>l.state==='live'&&l.score);if(lv)return '● '+lv.score;
 const nt=c.legs.find(l=>!l.res&&l.state==='live'&&l.note);
 if(nt)return short(nt.name)+(nt.phase==='probably_over'?' · probably finished':' · '+nt.short.toLowerCase());
 const up=c.legs.find(l=>!l.res&&l.starts&&l.state!=='live');return up?('Next: '+short(up.name)+' · '+up.starts):(c.when||'');}
function legendFor(pend){const on=new Set();pend.forEach(c=>c.legs.forEach(l=>{const k=legCls(l);if(k)on.add(k);}));if(!on.size)return '';
 const it=[['up','<i class="pd"></i>Winning now'],['down','<i class="pd"></i>Losing now'],['live','<i class="pd"></i>Tied'],['won','✓ Won'],['lost','✕ Lost']].filter(x=>on.has(x[0]));
 return `<div class="legend">${it.map(x=>`<span class="leg ${x[0]}">${x[1]}</span>`).join('')}</div>`;}
/* while a finger is on the chart the page holds still; the refresh that came in meanwhile paints on release */
function renderLive(){if(S.scrub){S.liveDirty=true;return;}_renderLive();afterPaint();if(S.ideaOpen)ideaSheet();}
function liveSkel(){return `<div class="kpis hero"><div class="hsk"><i style="height:12px;width:46%"></i><i style="height:42px;width:58%"></i><i style="height:22px;width:40%"></i></div>
 <div class="hsk"><i style="height:50px"></i><i style="height:50px"></i></div></div><div class="hsk" style="padding:4px 0 10px"><i style="height:14px;width:34%"></i></div>`+skel(4);}
function _renderLive(){const d=S.live;const m=$('#main');
 if(!d){m.innerHTML=(S.lerr||{}).live?errCard('live'):liveSkel();return;}
 if(d.error){m.innerHTML=`<div class="card empty err" data-ic="⚠️"><b>Couldn't load your combos</b>${esc(d.error)}<br><button class="btn acc" onclick="retry('live',this)">Try again</button></div>`;return;}
 const cs=(d.combos||[]);const pend=cs.filter(c=>c.group==='pending');const sOpen=(d.singles||[]).filter(x=>x.state==='live'||x.state==='pre');
 const sports=[...new Set(cs.flatMap(c=>c.sports))];
 const shown=cs.filter(c=>S.filter==='all'?c.group==='pending':S.filter==='live'?c.group==='pending'&&c.live:S.filter==='done'?c.group!=='pending'&&settledOk(c):c.group==='pending'&&c.sports.includes(S.filter))
   .sort(S.filter==='done'?((a,b)=>S.sf.sort==='best'?plOf(b)-plOf(a):S.sf.sort==='worst'?plOf(a)-plOf(b):S.sf.sort==='pay'?(b.full||b.pays)-(a.full||a.pays):doneKey(b)-doneKey(a)||b.sort-a.sort)
     :((a,b)=>(verdictShown(b)==='sell')-(verdictShown(a)==='sell')||(b.live-a.live)||a.sort-b.sort));
 const todo=cs.filter(c=>(d.todo||[]).includes(c.t));
 const sumW=(d.cash_now||0)+sOpen.reduce((a,x)=>a+(x.worth||0),0),sumS=d.staked+sOpen.reduce((a,x)=>a+(x.cost||0),0),dl=sumW-sumS;
 m.innerHTML=`<div class="grid"><div>
 ${heroLive(d,pend,sOpen,sumW,sumS,dl)}

 ${recapCard()}${momentBar(cs)}${doNow(d,cs)}
 ${foldHead('combos','Your combos',S.filter==='done'?shown.length:pend.length,`<span class="r chips">${[['all','Riding'],['live','Live now'],...sports.filter(s=>SPN[s]).map(s=>[s,(ICON[s]||'')+' '+SPN[s]]),['done','Settled']].map(([k,l])=>`<button class="chip ${S.filter===k?'on':''}" onclick="hap('selection');S.filter='${k}';renderLive()">${l}</button>`).join('')}</span>`)}
 ${foldB('combos')}
 ${S.filter==='done'?settledBar(cs):''}
 ${S.filter!=='done'?legendFor(pend):''}
 ${shown.some(c=>c.group==='pending'&&c.offer!=null&&c.cost>0)?chgBar():''}
 <div class="tbl"><div class="thead"><div>Combo</div><div>Picks</div><div class="num">Paid</div><div class="num">Pays</div><div class="num">To hit</div><div class="num">Kalshi offer</div><div></div></div>
 ${shown.map(rowLive).join('')||(S.filter==='all'&&!pend.length?'<div class="empty" data-ic="🌤️"><b>Nothing riding right now</b>Bets you place, here or on Kalshi, show up with live scores and cash-out offers.<br><button class="btn acc" onclick="go(\'build\')">See today\'s bets</button></div>':'<div class="empty" data-ic="🗒️"><b>Nothing here</b>Try another filter. Combos show up here with live scores and cash-out offers.</div>')}</div>
 ${foldE()}
 ${singlesLive(d)}
 </div><aside class="side">${sideLive(d)}</aside></div>`;}
function doNow(d,cs){const pend=cs.filter(c=>c.group==='pending');
 const items=[];
 for(const c of pend){
  if(planOn(c)&&(d.todo||[]).includes(c.t))items.push({c,kind:'sell',w:(c.offer||0)});
  else if(c.offer_real&&c.overpay&&c.overpay>=1.03)items.push({c,kind:'overpay',w:(c.offer||0)*1.1});
  else if(c.self&&c.verdict!=='hold'&&!c.offer_real)items.push({c,kind:'ask',w:(c.offer||0)*.8});
  else if(c.hedge&&!c.hedge.done&&c.hedge.locked>c.cost*1.5&&c.legs.filter(l=>!l.res).length===1)items.push({c,kind:'hedge',w:c.hedge.locked});
 }
 items.sort((a,b)=>b.w-a.w);
 const ib=ideaSection(d);   // Buy ideas (ideas.js): ranked, the top few shown, dismissable, foldable
 if(!items.length&&ib&&ideaList(d).length)return ib;
 const nS=(d.singles||[]).filter(x=>x.state==='live'||x.state==='pre').length,nAll=pend.length+nS;
 if(!items.length)return (nAll?`<div class="calm"><i></i><span><b>Nothing to do right now.</b> ${nAll} bet${nAll>1?'s':''} riding · ${d.auto_sell===false?'the Mac tells you the moment one is worth selling.':'smart sell is watching them.'}</span></div>`:'')+ib;
 return `<h2>Do now <span class="n">${items.length}</span></h2><div class="doit">${items.slice(0,4).map(({c,kind})=>{
  const nums=`<div class="dnums"><div>${c.offer_real?'Offer now':'Likely offer'}<b>${c.offer_real?'':'≈ '}${money(offNow(c))}</b></div><div>Holding is worth<b>${money(c.hold_ce!=null?c.hold_ce:c.hold_value)}</b></div>${c.threshold?`<div>Let-it-ride line<b>${cents(c.threshold)}+</b></div>`:c.thr_over?`<div>Let-it-ride line<b>No offer can beat waiting</b></div>`:''}<div>You paid<b>${money(c.cost)}</b></div></div>`;
  if(kind==='sell')return `<div class="dcard"><div><h4>${esc(c.label)}: cash out ${c.verdict==='half'?'half ':''}for ${money(c.offer)}</h4><p>${esc(c.why||'')}</p>${nums}</div>
   <div class="dbtns"><button class="btn ghost" data-t="${esc(c.t)}" onclick="openCombo(this.dataset.t)">Details</button><button class="btn ghost" onclick="act('keep','${c.t}')">Keep</button><button class="btn yes" onclick="sell('${c.t}')">Cash out</button></div></div>`;
  if(kind==='overpay')return `<div class="dcard"><div><h4>${esc(c.label)}: Kalshi is overpaying, ${money(c.offer)}</h4><p>That's ${Math.round((c.overpay-1)*100)}% more than the combo is worth at the market's own chances (${money(c.fair_value)}). Let it ride says hold; the price says sell. Your call.</p>${nums}</div>
   <div class="dbtns"><button class="btn ghost" data-t="${esc(c.t)}" onclick="openCombo(this.dataset.t)">Details</button><button class="btn yes" onclick="sell('${c.t}')">Cash out</button></div></div>`;
  if(kind==='hedge')return `<div class="dcard warn"><div><h4>${esc(c.label)}: lock in ${money(c.hedge.locked)} with a hedge</h4><p>One game left. Buying ${esc(short(c.hedge.name))} for ${money(c.hedge.cost)} pays out whichever side wins.</p>${nums}</div>
   <div class="dbtns"><button class="btn ghost" data-t="${esc(c.t)}" onclick="openCombo(this.dataset.t)">Details</button><button class="btn acc" onclick="hedge('${c.t}')">Hedge</button></div></div>`;
  return `<div class="dcard warn"><div><h4>${esc(c.label)}: check Kalshi's price</h4><p>${esc(c.why||'The plan says this one may be worth selling. Get a real offer to decide.')}</p>${nums}</div>
   <div class="dbtns"><button class="btn ghost" data-t="${esc(c.t)}" onclick="openCombo(this.dataset.t)">Details</button><button class="btn acc" ${S.busy[c.t]?'disabled':''} onclick="ask('${c.t}')">${S.busy[c.t]?'<span class="spin" aria-hidden="true"></span> Asking…':'Get offer'}</button></div></div>`;}).join('')}</div>`+ib;}
/* Buy-idea cards say which game they are for (display only): league, matchup, start time or live score, the pick in
   plain words, and what the price means. Every field is optional; one the Mac couldn't tell is simply left out. */
function ideaWhen(li){if(!li)return '';if(li.score)return li.score;if(li.live)return 'Under way';
 if(li.kick){try{return 'Starts '+new Date(li.kick*1000).toLocaleTimeString([],{weekday:'short',hour:'numeric',minute:'2-digit'});}catch(e){}}return '';}
function ideaAge(ts){const s=Math.max(0,Math.round(Date.now()/1000-(ts||0)));return s<60?'Price '+s+'s old':s<3600?'Price '+Math.round(s/60)+'m old':'Price '+Math.round(s/3600)+'h old';}
function ideaHead(x,li){const lg=li&&li.league_name||x.league_name||x.sport||'';
 return `<div class="ihd"><span>${esc(li&&li.icon||x.icon||'')} ${esc(lg)}</span><span class="tag" style="background:var(--panel2);color:var(--sub)">SINGLE GAME</span>${x.live?'<span class="tag" style="background:var(--livebg);color:var(--live)">IN PROGRESS</span>':''}${ideaBar(x)}</div>
  <h4>🎯 ${esc(li&&li.plain||x.picks)}</h4>${li&&(li.game||ideaWhen(li))?`<div class="igame">${esc([li.game,ideaWhen(li)].filter(Boolean).join(' · '))}</div>`:''}`;}
function ideaLeg(li){if(!li||!(li.plain||li.game))return '';const tk=/^[A-Z0-9._-]{3,120}$/.test(li.ticker||'')?li.ticker:'';
 return `<div class="ileg" ${tk?`data-t="${esc(tk)}" onclick="openGame(this.dataset.t)"`:''}><span class="ilg">${esc(li.icon||'')} ${esc(li.league_name||'')}</span><b>${esc(li.plain||'')}</b><small>${esc([li.game,ideaWhen(li)].filter(Boolean).join(' · '))}</small></div>`;}
function ideaFacts(x){if(x.price_c==null||x.fair_c==null)return '';
 return `<div class="dnums ifacts"><div>Kalshi price<b>${Math.round(x.price_c)}¢</b></div><div>Fair price<b>${Math.round(x.fair_c)}¢</b></div><div>Edge<b class="${(x.edge||0)>=0?'up':'down'}">${(x.edge||0)>=0?'+':'−'}${Math.abs(Math.round((x.edge||0)*100))}% expected</b></div>
  <div>Chance to win<b>${pct(x.chance)}</b></div><div>Stake → if it wins<b>${money(x.stake)} → ${money(x.pays)}</b></div><div>Expected profit<b class="${(x.profit||0)>0?'up':(x.profit||0)<0?'down':''}">${(x.profit||0)>0?'+':''}${(x.profit||0)<0?'−'+money(Math.abs(x.profit)):money(x.profit)}</b></div></div>`;}
function sweat(c){if(c.group!=='pending'||c.legs.length<2)return '';const w=c.legs.filter(l=>l.res==='yes').length;
 const seg=c.legs.map(l=>l.res==='yes'?'w':l.res==='no'?'x':(!l.res&&l.state==='live'&&(l.live??l.chance)>=.5)?'u':'').sort((a,b)=>'wux'.indexOf(a)>-1&&'wux'.indexOf(b)>-1?'wux'.indexOf(a)-'wux'.indexOf(b):a?-1:b?1:0);
 return `<span class="sweat" title="${w} of ${c.legs.length} picks won">${seg.map(s=>`<i class="${s}"></i>`).join('')}</span>`;}
/* the moment bar: only when smart sell would sell it now, on a real offer (nudge, #210) */
function momentBar(cs){const m=cs.filter(c=>c.group==='pending'&&c.moment&&c.nudge&&c.offer).sort((a,b)=>(b.offer-b.cost)-(a.offer-a.cost));if(!m.length)return '';
 const auto=S.live&&S.live.auto_sell;const more=m.length>1?`<div class="m" style="font-size:12px;margin:-6px 4px 12px">${m.length-1} more combo${m.length>2?'s are':' is'} at a good point too. They're marked with a green edge below.</div>`:'';
 return m.slice(0,1).map(c=>`<div class="moment-bar"><div><b>💸 ${auto?'Cashing out':'Good time to cash out'}: ${esc(c.label)}</b><span>Kalshi offers ${money(c.offer)} on ${money(c.cost)} paid (${smoney(c.offer-c.cost)}). ${c.moment.why==='take profit'?'It reached your take-profit level.':c.moment.why==='lock in'?'It\'s slipping from its high.':c.moment.why==='checkpoint'?'The early games came through.':'Locking in beats the risk of holding.'}</span></div>
  ${auto?'<span class="tag good">Auto</span>':`<button class="btn yes" data-t="${esc(c.t)}" onclick="sell(this.dataset.t)">Cash out</button>`}</div>`).join('')+more;}
/* Change vs what was paid (GitHub #100, display only): the same number the row already shows (offNow / worth), set against
   the same cost. S.chg = both | pct | usd, remembered per phone like the Day/Week switch (cw_chg) and kept on <html data-chg>:
   the switch only flips that attribute (no redraw, so scroll and folds stay), and CSS shows the % and/or $ part. Both parts
   are always drawn as rolling numbers (formats chg / chgd), rounded the way they print and symmetric on magnitude (rndm), so
   "-0%" never shows; the colour comes from what is SHOWN in each mode (data-b both, data-p %, data-u $). An estimate
   (no real Kalshi offer) is prefixed with the approx sign. */
try{S.chg=['pct','usd'].includes(localStorage.getItem('cw_chg'))?localStorage.getItem('cw_chg'):'both'}catch(e){S.chg='both'}
try{document.documentElement.dataset.chg=S.chg}catch(e){}
function setChg(k){if(!['both','pct','usd'].includes(k))return;S.chg=k;try{localStorage.setItem('cw_chg',k)}catch(e){}document.documentElement.dataset.chg=k;
 document.querySelectorAll('.chgsw button').forEach(b=>{const on=b.dataset.k===k;b.classList.toggle('on',on);b.setAttribute('aria-pressed',on?'true':'false');});}
function chgSw(){return `<span class="chgsw" role="group" aria-label="Show change as">${[['both','% + $'],['pct','%'],['usd','$']].map(([k,l])=>`<button data-k="${k}" aria-pressed="${S.chg===k}" class="${S.chg===k?'on':''}" onclick="setChg('${k}')">${l}</button>`).join('')}</span>`;}
function chgBar(){return `<div class="chgbar"><span>Change vs paid</span>${chgSw()}</div>`;}
function chgState(x){return x>0?'up':x<0?'down':'flat';}
function chgHtml(k,now,paid,est){if(now==null||!(paid>0))return '';const d=now-paid,p=d/paid;const r=rndm(p*100),c=rndm(d*100);
 const pre=est?'≈ ':'';return `<span class="chg${est?' est':''}" data-b="${chgState(r!==0?r:c)}" data-p="${chgState(r)}" data-u="${chgState(c)}"><span class="cp" data-num="${k}%" data-v="${p.toFixed(4)}" data-f="chg" data-pre="${pre}">${pre}${fmtNum(p,'chg')}</span><span class="cd" data-num="${k}$" data-v="${d.toFixed(2)}" data-f="chgd" data-pre="${pre}">${pre}${fmtNum(d,'chgd')}</span></span>`;}
function heroChg(dl,St,roll,est){
 const dv=roll?`<span class="cd" data-num="h:dl" data-v="${dl.toFixed(2)}" data-f="absm">${money(Math.abs(dl))}</span>`:`<span class="cd">${money(Math.abs(dl))}</span>`;
 const pv=!St?'':roll?`<span class="cp" data-num="h:dp" data-v="${(dl/St).toFixed(4)}" data-f="chg">${fmtNum(dl/St,'chg')}</span>`:`<span class="cp">${fmtNum(dl/St,'chg')}</span>`;
 return `<span class="dch${est?' est':''}${St?'':' nop'}">${dv}${pv}</span>`;}
const SKIND={win:'To win',spread:'Spread',total:'Total',other:'Single bet'};
/* #413: Kalshi's own number. Its app marks a combo at its last trade (combo markets have no order book, and that last
   trade is your own buy price, so it barely moves) and a single at the live bid, with no selling discount. So: the
   cost of each open combo + each open single's worth (contracts x best bid). Display only; the sale estimate (cash_now)
   is unchanged and shown small beside it. */
function kalshiNow(pend,sOpen){return pend.reduce((a,c)=>a+(+c.cost||0),0)+sOpen.reduce((a,x)=>a+(+x.worth||0),0);}
function heroLive(d,pend,sOpen,W,St,dl){const n=pend.length+sOpen.length;const live=pend.some(c=>c.live)||sOpen.some(x=>x.state==='live');
 const ch=1-(1-(d.riding?d.chance_one||0:0))*sOpen.reduce((a,x)=>a*(1-(x.chance||0)),1);
 const most=pend.reduce((a,c)=>a+c.pays,0)+sOpen.reduce((a,x)=>a+(x.pays||0),0);const big=Math.max(d.best||0,...sOpen.map(x=>x.pays||0));
 const K=kalshiNow(pend,sOpen),kd=K-St;   /* #413: the big number is Kalshi's own value; our sale estimate (W) sits small beside it */
 const cls=Math.abs(kd)<.005?'flat':kd>0?'up':'down';const est=(d.combos||[]).some(c=>c.group==='pending'&&!c.offer_real);
 /* #195: only a number that really moves may roll and flash. The big figure and its change pill follow Kalshi's own value (combos at cost, singles at the bid), so they move only with a single's price: with no single open the pill stays still. The 'If sold now' estimate rolls only if some estimated combo was priced live (offer_live); with none it only changes when a leg settles, so it just updates (data-still). */
 const moves=sOpen.some(x=>x.worth!=null),estC=(d.combos||[]).filter(c=>c.group==='pending'&&!c.offer_real),still=est&&!estC.some(c=>c.offer_live!=null);
 const ring=v=>{const r=9,c=2*Math.PI*r;return `<svg class="ring" viewBox="0 0 22 22"><circle cx="11" cy="11" r="${r}" fill="none" stroke="var(--line)" stroke-width="3"/><circle cx="11" cy="11" r="${r}" fill="none" stroke="${v>=.5?'var(--yes)':'var(--acc)'}" stroke-width="3" stroke-linecap="round" stroke-dasharray="${(c*Math.max(0,Math.min(1,v))).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 11 11)"/></svg>`;};
 const glow=cls==='up'?'var(--yesbg)':cls==='down'?'var(--nobg)':'transparent';
 return `<div class="kpis hero" style="--hglow:${glow}"><div class="hv"><span class="hl">${live?'<i class="livedot"></i> Live · ':''}Worth now on Kalshi<span class="fresh" data-fr="L">${frTxt('L')}</span></span>
   <div class="hrow"><b class="big" data-num="h:kalshi" data-v="${K.toFixed(2)}">${money(K)}</b>
   <span class="hest" aria-label="Our estimate if you sold everything now: ${money(W)}"><small>If sold now</small><b data-num="h:worth" data-v="${W.toFixed(2)}" data-pre="${est?'≈ ':''}"${still?' data-still="1"':''}>${est?'≈ ':''}${money(W)}</b></span></div>
   <span class="delta ${cls}">${cls==='up'?'▲':cls==='down'?'▼':'•'} ${heroChg(kd,St,moves,false)} <span style="font-weight:500;opacity:.8">vs ${money(St)} in</span></span></div>
  <div class="hs"><div><span class="hk">Riding</span><b><span data-num="h:n" data-v="${n}" data-f="int">${n}</span> bet${n===1?'':'s'}</b><small>${pend.length} combo${pend.length===1?'':'s'} · ${sOpen.length} single${sOpen.length===1?'':'s'}</small></div>
   <div><span class="hk">Staked</span><b data-num="h:st" data-v="${St.toFixed(2)}">${money(St)}</b><small>in play right now</small></div>
   <div><span class="hk">Chance one pays</span><b>${n?ring(ch):''}<span data-num="h:ch" data-v="${ch.toFixed(4)}" data-f="pct">${n?pct(ch):'—'}</span></b><small>${n?'at least one bet wins':'nothing riding'}</small></div>
   <div><span class="hk">Most it can pay</span><b class="up" data-num="h:most" data-v="${most.toFixed(2)}">${money(most)}</b><small>biggest single bet ${money(big)}</small></div></div></div>`;}
function singlesLive(d){const all=d.singles||[];
 const ss=all.filter(x=>S.filter==='all'||S.filter==='done'?true:S.filter==='live'?x.state==='live':x.sport===S.filter);
 if(!all.length)return '';
 return `${foldHead('singles','Single bets &amp; spreads',all.length,'','margin-top:22px')}
 ${foldB('singles')}${ss.some(x=>x.worth!=null&&x.cost>0)?chgBar():''}<div class="tbl stbl"><div class="thead"><div>Bet</div><div>Game</div><div class="num">Paid</div><div class="num">Pays</div><div class="num">Chance</div><div class="num">Worth now</div><div></div></div>
 ${ss.map(rowSingle).join('')||'<div class="empty" data-ic="🗒️"><b>Nothing here</b>No single bets or spreads in this view.</div>'}</div>
 ${foldE()}`;}
const cents=x=>'$'+(+x).toFixed(2);   /* sell lines in cents: money() rounds $12.70 up to "$13" (#371) */
function ssChip(x){const off=S.live&&S.live.auto_sell===false;
 const isC=x.smart_txt!==undefined,at=x.sell_at!=null?x.sell_at:isC?x.smart_at:x.threshold,over=x.sell_at!=null?x.sell_over:isC?x.smart_over:(x.sell_over!=null?x.sell_over:x.thr_over);   /* combos carry threshold/thr_over (#376) */
 const hint=x.self||off?'':(isC&&x.smart_chip)?` · ${esc(x.smart_chip)}`:at?` · sells at ${cents(at)}+`:over?` · no offer can beat waiting`:'';   /* never a line above what it pays (#371) */
 return `<button class="ss ${x.self?'me':''} ${off&&!x.self?'dim':''}" data-t="${esc(x.t)}" onclick="event.stopPropagation();selfSell(this.dataset.t,${!x.self})">${x.self?'✋ I\'ll sell it':'🤖 Smart sell'+(off?' · off in Settings':hint)}</button>`;}
async function selfSell(t,mine){hap();const d=S.live;for(const x of [...(d.singles||[]),...(d.combos||[])])if(x.t===t)x.self=mine;renderLive();
 const r=await api('/app/api/act',{a:'selfsell',t,on:mine}).catch(()=>({ok:false}));toast(r.msg||'Couldn\'t reach the Mac.',3500);if(!r.ok){for(const x of [...(d.singles||[]),...(d.combos||[])])if(x.t===t)x.self=!mine;renderLive();}}
function rowSingle(x){const st=x.res?(x.res==='yes'?'<span class="tag good">Won</span>':'<span class="tag bad">Lost</span>'):x.state==='live'||x.on?'<span class="tag live">Live</span>':x.state==='over'?'<span class="tag">Settling</span>':x.phase==='probably_over'||x.phase==='over'?'<span class="tag">Waiting on Kalshi</span>':'';
 const line=x.how||x.score||x.note||(x.starts?'starts '+x.starts:'');
 const cls=/^(Covering|On track|Winning)/.test(x.how||'')?'up':/^(Not|Losing)/.test(x.how||'')?'down':'';
 return `<div class="trow srow1" data-key="s:${x.t}" data-sig="${esc(x.score||'')}" data-t="${esc(x.t)}" onclick="openGame(this.dataset.t)"><div class="name"><b>${ICON[x.sport]||'🎯'} ${esc(betPlain(x))}${x.own?' <span class="own">You, on Kalshi</span>':' <span class="own app">From the app</span>'}</b>${x.state==='live'||x.state==='pre'?ssChip(x):''}<span>${x.matchup?esc(SKIND[x.kind]||'')+(SKIND[x.kind]?' · ':'')+betWhere(x):esc(SKIND[x.kind]||'')}${x.matchup?'':(()=>{const g=(x.game||'').replace(/:\s*(Spread|Total.*)$/i,'').replace(/\s*Winner\??$/i,'').replace(/\?$/,'');return g&&g.toLowerCase()!==(x.label||'').toLowerCase()?' · '+esc(g):'';})()}</span></div>
  <div class="legs"><span class="${cls}">${esc(line)}</span> ${st}${x.url?` <a href="${esc(x.url)}" target="_blank" onclick="event.stopPropagation()">game ↗</a>`:''}</div>
  <div class="numwrap"><div class="num" data-l="Paid">${money(x.cost)}</div><div class="num" data-l="Pays">${money(x.pays)}</div>
  <div class="num" data-l="Chance">${x.chance!=null?`<span data-num="sc:${x.t}" data-v="${x.chance}" data-f="pct">${pct(x.chance)}</span>`:'—'}${x.chance!=null?`<div class="bar"><i data-bar="sb:${x.t}" style="width:${Math.max(1,Math.min(100,x.chance*100))}%"></i></div>`:''}</div>
  <div class="num" data-l="Worth now">${x.worth!=null?`<span data-num="w:${x.t}" data-v="${x.worth}">${money(x.worth)}</span>${chgHtml('sc:'+x.t,x.worth,x.cost,false)}`:'—'}</div></div><div class="verdict"></div>${typeof ssActs==='function'?ssActs(x):''}</div>`;}
function offNow(c){return(!c.offer_real&&c.offer_live!=null&&c.offer!=null)?c.offer_live:c.offer;}   // display-only; same rule as the hero (hero_worth)
function rowLive(c){const [vc,vt]=verdictOf(c);const open=S.open[c.t];
 const oLive=offNow(c);const oEst=!c.offer_real;
 const offer=c.group!=='pending'?(c.group==='cashed'?`<b>${money(c.back)}</b><small>cashed out</small>`:'—'):c.offer!=null?`<b data-num="o:${c.t}" data-v="${oLive}" data-pre="${oEst?'≈ ':''}">${oEst?'≈ ':''}${money(oLive)}</b><small>${c.offer_real?'vs '+money(c.hold_value)+' holding':'estimate'}</small>${chgHtml('oc:'+c.t,oLive,c.cost,oEst)}`:'<small>—</small>';
 return `<div class="trow ${c.moment?'hot':''}" data-key="c:${c.t}" data-sig="${esc(c.legs.map(l=>l.score||'').join('|'))}" data-t="${esc(c.t)}" onclick="tog(this.dataset.t)"><div class="name"><b>${ICON[c.sports[0]]||''} ${esc(c.label)}${sweat(c)}${c.own?' <span class="own">You, on Kalshi</span>':''}</b>${c.group==='pending'?ssChip(c):''}<span>${esc(nextLine(c))}</span>${c.group!=='pending'&&c.done_at&&doneWord(c.done_at)?`<span class="sdt">${esc(doneWord(c.done_at))}</span>`:''}</div>
  <div class="legs">${legTags(c.legs)}</div>
  <div class="numwrap"><div class="num" data-l="Paid">${money(c.cost)}</div><div class="num" data-l="${c.group==='cashed'?'Would pay':'Pays'}">${money(c.group==='cashed'?(c.full||c.pays):c.pays)}${c.group==='cashed'&&c.full?'<small style="display:block" class="m">if held</small>':''}</div>
  <div class="num" data-l="To hit">${c.group==='pending'?`<span data-num="p:${c.t}" data-v="${c.p}" data-f="pct">${pct(c.p)}</span>`:'—'}${c.group==='pending'?`<div class="bar"><i data-bar="pb:${c.t}" style="width:${Math.max(1,Math.min(100,c.p*100))}%"></i></div>`:''}</div>
  <div class="num offer" data-l="Offer">${offer}</div></div>${c.group==='pending'?`<div class="verdict ${vc}">${vt}</div>`:plPill(c)}</div>
  ${open?`<div class="exp">${c.legs.map(l=>`<div class="lrow" style="cursor:pointer" data-t="${esc(l.ticker)}" onclick="event.stopPropagation();openGame(this.dataset.t)"><span class="mark ${legCls(l)}">${l.res==='yes'?'✓':l.res==='no'?'✕':''}</span>
   <div class="who"><b>${ICON[l.sport]||''} ${esc(betPlain(l))}</b> <span>${l.matchup?betWhere(l)+' · ':l.opp?'vs '+esc(l.opp)+' · ':''}${esc(l.score||(!l.res&&l.note)||l.starts||(l.res==='yes'?'won':l.res==='no'?'lost':''))}</span>${l.url?` <a href="${esc(l.url)}" target="_blank" onclick="event.stopPropagation()">game ↗</a>`:''}</div>
   <b>${l.res?'':pct(l.live!=null?l.live:l.chance)}${l.live!=null&&!l.res?' <span class="m" style="font-weight:500;font-size:11px">live</span>':''}</b></div>`).join('')}
   ${whyShown(c)&&c.group==='pending'?`<div class="why">${esc(whyShown(c))}</div>`:''}
   ${c.group==='pending'?`<div class="acts"><span class="s">${c.offer_real?`Kalshi offers <b>${money(c.offer)}</b> · holding is worth about ${money(c.hold_ce!=null?c.hold_ce:c.hold_value)}${c.threshold?` · let-it-ride line ${cents(c.threshold)}+`:c.thr_over?' · let-it-ride line: no offer can beat waiting':''}`:'Ask Kalshi what it will pay for this combo right now.'}${c.smart_txt&&!c.self&&S.live.auto_sell!==false?`<br>${esc(c.smart_txt)}`:''}${c.lock_at&&!c.self&&S.live.auto_sell!==false?` Protects a profit once the offer has reached ${cents(c.lock_at)}.`:''}</span>
    <button class="btn ghost" data-t="${esc(c.t)}" onclick="event.stopPropagation();openCombo(this.dataset.t)">Details</button>
    ${c.hedge&&!c.hedge.done?`<button class="btn" onclick="event.stopPropagation();hedge('${c.t}')">Hedge ${esc(short(c.hedge.name))} · ${money(c.hedge.cost)}</button>`:''}
    <button class="btn" ${S.busy[c.t]?'disabled':''} data-t="${esc(c.t)}" onclick="event.stopPropagation();ask(this.dataset.t)">${S.busy[c.t]?'<span class="spin" aria-hidden="true"></span> Asking…':c.offer_real?'New offer':'Get cash-out offer'}</button>
    ${c.offer_real?`<button class="btn yes" data-t="${esc(c.t)}" onclick="event.stopPropagation();sell(this.dataset.t)">Cash out ${money(c.offer)}</button>`:''}</div>`:''}</div>`:''}`;}
function tog(t){S.open[t]=!S.open[t];renderLive();}
function moments(){const seen=new Set();const ev=(S.events||[]).slice().reverse().filter(e=>{if(seen.has(e.text))return false;seen.add(e.text);return true;}).slice(0,8);if(!ev.length)return '';
 const K={score:'🏟️',swing:'📈',advice:'⚡',settled:'🏁',alert:'🔔'};
 return `<div class="card"><h3><span><span class="live-dot"></span>Moments</span><span>live</span></h3>${ev.map(e=>`<div class="moment" ${e.ticker?`style="cursor:pointer" data-t="${esc(e.ticker)}" onclick="openGame(this.dataset.t)"`:e.kind==='advice'&&comboOk(e.combo)?`style="cursor:pointer" data-t="${esc(e.combo)}" onclick="openCombo(this.dataset.t)"`:''}><span class="k" ${e.kind==='score'?`style="color:${e.good?'var(--yes)':'var(--no)'}"`:''}>${K[e.kind]||'•'}</span><span>${esc(e.text)}</span><time>${ago2(e.at)}</time></div>`).join('')}</div>`;}
function ago2(t){const s=Math.max(0,Date.now()/1000-t);return s<60?'now':s<3600?Math.round(s/60)+'m':Math.round(s/3600)+'h';}
function sideLive(d){const gs=d.games||[];const r=d.risk;
 return moments()+ordersCard(d)+`<div class="card"><h3>Games you need <span>${gs.length}</span></h3>${gs.slice(0,8).map(g=>`<div class="g" style="cursor:pointer" data-t="${esc(g.ticker||'')}" onclick="openGame(this.dataset.t)"><div class="t">${ICON[g.sport]||''} ${esc(g.name)}${g.state==='live'&&g.phase!=='probably_over'&&g.phase!=='waiting'?'<span class="tag">LIVE</span>':''}</div>
  <div class="e">${g.state==='live'&&g.sc?`<b>${g.sc.me}–${g.sc.opp}</b>${esc(g.sc.detail||'')}`:`<b>${pct(g.chance)}</b>${esc(g.short||g.starts||'')}`}</div>
  <div class="x">In ${g.combos} combo${g.combos>1?'s':''} · ${money(g.pays)} riding</div></div>`).join('')||'<div class="m">Nothing pending.</div>'}</div>
 ${r?`<div class="card"><h3>If ${esc(short(r.name))} lose <span>biggest risk</span></h3><div class="mini">Combos out<b>${r.combos} of ${d.riding}</b></div><div class="mini">Payout riding<b>${money(r.pays)}</b></div><div class="mini">${esc(short(r.name))} to win<b>${pct(r.chance)}</b></div></div>`:''}
 ${todayCard(d)}`;}
function todayCard(d){const t=d.today;if(!t)return `<div class="card"><h3>Finished <span>recently</span></h3><div class="mini">Won or cashed<b class="up">${money(d.locked)}</b></div><div class="mini">Holding is worth<b>${money(d.hold_value)}</b></div></div>`;
 const n=t.won+t.cashed+t.lost;const bits=[t.won?`${t.won} won`:'',t.cashed?`${t.cashed} cashed`:'',t.lost?`${t.lost} lost`:''].filter(Boolean).join(' · ');
 return `<div class="card"><h3>Today <span>${n?bits:'nothing finished yet'}</span></h3>${n?`<div class="mini">Paid back<b>${money(t.back)}</b></div><div class="mini">They cost<b>${money(t.cost)}</b></div><div class="mini">Profit today<b class="${t.pl>=0?'up':'down'}">${smoney(t.pl)}</b></div>`:''}${d.week_pl!=null?`<div class="mini">Last 7 days<b class="${d.week_pl>=0?'up':'down'}">${smoney(d.week_pl)}</b></div>`:''}<div class="mini">Still riding is worth<b>${money(d.hold_value)}</b></div></div>`;}
async function ask(t){S.busy[t]=true;S.open[t]=true;renderLive();const r=await api('/app/api/act',{a:'ask',t});S.busy[t]=false;
 hap(r.ok?'success':'error');if(!r.ok)toast(r.msg||'No offer came in.');await load('live',true);}
function sell(t){const c=(S.live.combos||[]).find(x=>x.t===t);if(!c)return;
 modal(`<h3>Cash out ${esc(c.label)} for ${money(c.offer)}?</h3><p>You paid ${money(c.cost)} (${smoney(c.offer-c.cost)}). If you hold instead: ${pct(c.p)} chance of ${money(c.pays)}. Kalshi's offer only lasts a few seconds.</p>
 <div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn yes" id="sellgo" data-t="${esc(t)}" onclick="doSell(this.dataset.t)">Cash out</button></div>`);}
async function doSell(t){hap();const c=(S.live.combos||[]).find(x=>x.t===t)||{};$('#sellgo').innerHTML='<span class="spin" aria-hidden="true"></span>';const r=await api('/app/api/act',{a:'go',t});closeModal();
 if(r.ok&&/^✅/.test(r.msg||'')){S.momSeen=S.momSeen||{};S.momSeen['s:'+t]=1;setTimeout(()=>soldSheet({label:momName(c),back:r.offer!=null?r.offer:c.offer,cost:c.cost}),360);}   // the Sold moment
 else{hap(r.ok?'success':'error');toast(r.msg||(r.ok?'Done.':'Didn\'t go through.'),5000);}load('live',true);}
async function hedge(t){const c=(S.live.combos||[]).find(x=>x.t===t);modal(`<h3>Hedge ${esc(c.label)}?</h3><p>Buys the other side of its last game for about ${money(c.hedge.cost)}, so you collect about ${money(c.hedge.locked)} whichever team wins.</p><div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn acc" data-t="${esc(t)}" onclick="var t=this.dataset.t;closeModal();api('/app/api/act',{a:'hedgego',t}).then(r=>{toast(r.msg||'Done.',5000);load('live',true)})">Place hedge</button></div>`);}
async function act(a,t){const r=await api('/app/api/act',{a,t});if(r.msg)toast(r.msg);load('live',true);}
