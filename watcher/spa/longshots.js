/* ---------------- LONG SHOTS (issue #341). Two or three 6-8 pick combos a day, each pick 65-80% before its game, kept only
   when Kalshi's quote pays at least what the picks are worth after the fee and holding it to the end is expected to profit (the Mac
   works them out; this only draws them). Get price and Buy go through the same guarded combo quote and accept as every
   other combo (Pause, caps, unknown outcome = check). Display and taps only: nothing here buys by itself. */
function lsRoute(r){return `Held to the end: <b>${pct(r.chance)}</b> to hit, <b>+${money(r.exp)}</b> expected after the fee`;}
function lsKey(r){return 'ls:'+r.id;}
function lsCard(r){r.check=r.check||!!(S.lsChecked&&S.lsChecked[r.id]);   // (#353) an unknown outcome stays "Check Kalshi" across Build refreshes in this page
 if(r.over&&!r.bought&&!r.check)return ovLs(r);const k=lsKey(r),o=S.quotes&&S.quotes[k],fresh=o&&Date.now()/1000-o.at<20,busy=S.lsBusy===r.id;
 const legs=`<div class="lrows">${(r.legs||[]).map(l=>legRow(l)).join('')}</div>`;
 if(r.check)return `<div class="ccard lscard"><div class="hd"><div><div class="tier" style="color:var(--no)">Check Kalshi</div><b>${pct(r.chance)}</b> <span class="m">to hit</span></div></div>${legs}
  <div class="m" style="font-size:12.5px">Kalshi may have taken this one. Check your Kalshi account; the app won't price or buy it again until you have.</div></div>`;
 if(r.bought)return `<div class="ccard lscard" style="opacity:.62"><div class="hd"><div><div class="tier" style="color:var(--yes)">✓ You bought this</div><b>${pct(r.chance)}</b> <span class="m">to hit</span></div></div>${legs}
  <div class="brow"><button class="btn ghost pri" onclick="go('live')">See it on Live</button></div></div>`;
 return `<div class="ccard lscard" data-ls="${esc(r.id)}"><div class="hd"><div><div class="tier">🎯 Long shot · ${r.n||(r.legs||[]).length} picks</div><b data-num="lsh:${esc(r.id)}" data-v="${r.chance}" data-f="pct">${pct(r.chance)}</b> <span class="m">to hit</span></div>
  <div class="lsx"><b class="up">+${money(r.exp)}</b><small>expected</small></div></div>
  <div class="s" style="font-size:12.5px;line-height:1.55">${money(r.stake)} pays ${money(r.pays)} if every pick wins · Kalshi pays ${pct(r.pct)} of what it's worth after the fee<br>${lsRoute(r)}</div>
  ${legs}
  ${fresh?`<div class="qline ${o.clears?'good':'bad'} ${qNew(o)}">${qBar(o)}<b>Kalshi pays ${money(o.pays)} for ${money(o.stake)}</b><span>${pct(o.pct)} of fair · ${o.clears?'worth it after the fee':'now under what it\'s worth'} · <span class="qs" data-at="${o.at}">${Math.max(0,Math.round(20-(Date.now()/1000-o.at)))}</span>s left</span></div>`:''}
  ${S.lsErr&&S.lsErr[r.id]?`<div class="lsfail${S.lsErr[r.id].fresh?' pin':''}" role="alert"><b>Couldn't get a price.</b> ${esc(S.lsErr[r.id].m)} Nothing was bought.</div>`:''}
  <div class="brow">${busy?`<button class="btn pri" disabled><span class="spin"></span> ${S.lsBuying?'Buying… confirming with Kalshi':'Asking Kalshi…'}</button>`:
   fresh?`<button class="btn pri ${o.clears?'yes':'warn'}" data-lsid="${esc(r.id)}" onclick="lsBuy(this.dataset.lsid,this)">${o.clears?'Buy':'Buy anyway'} ${money(o.stake)} → ${money(o.pays)}</button>`:
   `<button class="btn pri" data-lsid="${esc(r.id)}" onclick="lsQuote(this.dataset.lsid,this)">Get price · ${money(r.stake)}</button>`}</div></div>`;}
function lsSection(d,inBoard){const L=d.longshots||{},rs=L.recs||[];
 if(!inBoard&&!rs.length)return '';   // nothing to recommend: the empty state sits with the board, not on top of the page
 if(inBoard&&rs.length)return '';     // already drawn above the board
 const sub='65–80% picks · priced at or over fair';
 return `${secHead('ls','🎯 Long shots',rs.length,sub)}${secOpen('ls')?(rs.length?`<div class="m" style="font-size:12px;margin:-4px 2px 10px">A small bet on a full slate: each pick likely on its own, a 7%+ chance they all hit, and Kalshi paying at least what it's worth.</div><div class="cgrid">${rs.slice().sort(ovLast).map(lsCard).join('')}</div>`:
  `<div class="empty lsempty"><b>No long shot today</b>${esc(L.busy&&!L.at?'Checking today\'s games…':(L.why||'Checking today\'s games…'))}</div>`):''}`;}
function lsFind(id){return ((S.build&&S.build.longshots||{}).recs||[]).find(r=>r.id===id);}
async function lsQuote(id,b){if(S.lsBusy||S.buying)return;hap();const r=lsFind(id);if(!r)return;S.lsBusy=id;S.lsBuying=false;if(S.lsErr)delete S.lsErr[id];
 if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Asking Kalshi…';}
 const q=await api('/app/api/act',{a:'longshot',id,legs:r.legs.map(l=>l.ticker)}).catch(e=>({ok:false,error:'Couldn\'t reach your Mac ('+(e&&e.message||e)+').'}));
 S.lsBusy=null;
 if(!q.ok){   // (#353) the reason stays on the card (with a small shake), not only in a toast; a plain refusal, nothing was sent
  S.lsErr=S.lsErr||{};S.lsErr[id]={m:String(q.error||q.msg||'No price came in.'),fresh:true};renderBuild();S.lsErr[id].fresh=false;return;}
 S.quotes=S.quotes||{};S.quotes[lsKey(r)]={i:q.i,pays:q.pays,stake:q.stake,pct:q.pct,clears:q.clears,at:Date.now()/1000,sig:r.legs.map(l=>l.ticker).join('|')};
 renderBuild();clearInterval(S.qT);S.qT=setInterval(qTick,1000);}
async function lsBuy(id,btn){if(S.buying||S.lsBusy)return;const r=lsFind(id),o=r&&S.quotes&&S.quotes[lsKey(r)];if(!o||Date.now()/1000-o.at>=20){renderBuild();return;}
 S.buying=true;S.lsBusy=id;S.lsBuying=true;hap();if(btn){btn.disabled=true;btn.innerHTML='<span class="spin"></span> Buying… confirming with Kalshi';}
 let res;try{res=await api('/app/api/act',{a:'buy',i:o.i,legs:r.legs.map(l=>l.ticker)});}catch(e){res={ok:false,msg:'Couldn\'t reach your Mac ('+(e&&e.message||e)+'). Check Live before trying again, so you don\'t buy twice.'};}
 S.buying=false;S.lsBusy=null;S.lsBuying=false;delete S.quotes[lsKey(r)];if(res.check){r.check=true;S.lsChecked=S.lsChecked||{};S.lsChecked[r.id]=true;}   // unknown outcome: the card says so, and keeps saying so when Build refreshes (#353)
 if(res.ok){r.bought=true;okSheet('Bought',`${money(res.pays||0)} if it hits`,legSummary(r.legs)+'. It shows on Live within a minute. Smart sell watches it from there.');}
 else toast(res.msg||'Didn\'t go through.',7000,'bad');
 renderBuild();}
