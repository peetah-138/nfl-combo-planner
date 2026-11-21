function makerCard(k){if(!k)return '';const r=k.rules||{};const M={off:'Off',watch:'Watch only',on:'Place orders'};
 const rows=(k.recent||[]).slice(0,6).map(x=>`<div class="moment"><span class="k">${x.status==='filled'?'✅':x.status==='posted'?'📌':x.status==='watching'?'👀':'⏹'}</span><span><b>${esc(short(x.pick))}</b> <span class="m">${x.n} at ${Math.round(x.price*100)}¢ · fair ${pct(x.fair)} · ${esc(x.status)}${x.outcome?' · '+x.outcome:''}${x.why?' · '+esc(x.why):''}</span></span><time>${ago2(x.ts)}</time></div>`).join('');
 return `<div class="srow"><div class="l"><b>Standing orders</b><small>The Mac keeps buy orders ${Math.round((r.discount||.03)*100)}¢ under the sharp books' chance, so you only buy when someone sells to you cheap. Watch only records what would have filled.</small></div>
  <div class="seg">${['off','watch','on'].map(m=>`<button class="${k.mode===m?'on':''}" onclick="makerMode('${m}')">${M[m]}</button>`).join('')}</div></div>
  <div class="srow" style="display:block"><div class="m" style="font-size:12.5px;line-height:1.6">Teams with a ${pct(r.min_fair||.2)}–${pct(r.max_fair||.85)} chance · two odds sources agree · games within ${r.horizon_hours||30} hours · one order per game · up to ${money(r.per_order||10)} each, ${r.max_orders||6} orders and ${money(r.max_dollars||40)} out at once, inside your cap ·
   re-priced when the fair chance moves ${Math.round((r.reprice||.01)*100)}¢ · cancelled ${r.cancel_mins||20} minutes before the game and on injury news (Kalshi also expires them by itself).</div>
   ${k.settled?`<div class="mini" style="margin-top:6px">Record so far<b class="${k.pl>=0?'up':'down'}">${smoney(k.pl)} (${k.settled} settled, ${k.filled} filled)</b></div>`:''}${rows?`<div style="margin-top:6px">${rows}</div>`:''}</div>`;}
function makerMode(m,sure){if(m==='on'&&!sure){modal(`<h3>Let the Mac place standing orders?</h3><p>Real buy orders on Kalshi, a few cents under fair, up to ${money(40)} out at once and inside your cap. They're cancelled before games start, on news, and when you tap Pause on any alert.</p><div class="row"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn acc" onclick="closeModal();makerMode('on',true)">Turn on</button></div>`);return;}
 S.set.maker.mode=m;setv('maker_mode',m);renderSettings();toast(m==='on'?'Standing orders: on. They appear on Live.':m==='watch'?'Standing orders: watch only.':'Standing orders off. Any open ones are cancelled on the next pass.',5000);}
function ordersCard(d){const os=d.orders||[];if(!os.length)return '';
 return `<div class="card"><h3>Standing orders <span>${os[0].mode==='on'?'on Kalshi':'watching'}</span></h3>${os.map(x=>`<div class="moment"><span class="k">${x.mode==='on'?'📌':'👀'}</span><span><b>${esc(short(x.pick))}</b> <span class="m">${x.n} at ${Math.round(x.price*100)}¢ · fair ${pct(x.fair)}</span></span><time>${ago2(x.ts)}</time></div>`).join('')}</div>`;}
function dayBar(d){const v=d.days;if(!v)return '';const b=(on,lab,js)=>`<button class="${on?'on':''}" onclick="${js}">${lab}</button>`;
 if(v.mode==='day')return `<div class="seg daybar">${b(!v.next_day,'Today',"setDays({next_day:false})")}${b(v.next_day,'Tomorrow',"setDays({next_day:true})")}</div>`;
 if(v.mode==='mix')return `<div class="seg daybar">${v.windows.map((w,i)=>b(v.mix_window===i,esc(w),`setDays({mix_window:${i}})`)).join('')}</div>`;
 return `<div class="seg daybar">${b(v.thursday,v.wed?'+ Wed & Thu':'+ Thursday',`setDays({thursday:${!v.thursday}})`)}${b(true,'Sunday','')}${b(v.saturday,'+ Saturday',`setDays({saturday:${!v.saturday}})`)}${b(v.monday,'+ Monday',`setDays({monday:${!v.monday}})`)}</div>`;}
async function setDays(vals){hap();Object.assign(S.build.days,vals);renderBuild();
 const r=await api('/app/api/settings',{lg:S.lg,values:vals}).catch(()=>({ok:false}));if(!r.ok){toast('Couldn\'t change the days.');return;}
 S.build=null;renderBuild();load('build',true);}
try{S.bsec=JSON.parse(localStorage.getItem('cw_bsec')||'null')||{}}catch(e){S.bsec={}}
function secOpen(k){return S.bsec[k]!==false;}
/* folding a Build section: the chevron turns and the section rises in, instead of jumping */
function secTog(k){hap('selection');S.bsec[k]=!secOpen(k);try{localStorage.setItem('cw_bsec',JSON.stringify(S.bsec))}catch(e){}S.secJust=k;renderBuild();S.secJust=null;
 const h=document.querySelector(`.sech[data-k="${k}"]`);if(!h)return;const c=h.querySelector('.chev');
 requestAnimationFrame(()=>requestAnimationFrame(()=>{if(c)c.classList.remove('from-open','from-shut');}));
 if(secOpen(k)){let n=h.nextElementSibling;for(let i=0;i<2&&n&&!n.classList.contains('sech');i++,n=n.nextElementSibling)n.classList.add('unfold');}}
function secHead(k,title,n,sub,extra){const o=secOpen(k);return `<h2 class="sech ${o?'open':''}" data-k="${k}" onclick="secTog('${k}')"><span class="chev ${S.secJust===k?(o?'from-shut':'from-open'):''}">▾</span>${title} <span class="n">${n}</span>${o&&sub?`<span class="r m" style="font-size:12px">${sub}</span>`:''}${extra?`<span class="r">${extra}</span>`:''}</h2>${o?'':`<div class="m secfold" onclick="secTog('${k}')">Folded · tap to show</div>`}`;}
/* Spreads & totals (issue #117): recommendations only. A strike shows when it clears the league's learned bar after
   Kalshi's fee, isn't a kind that keeps losing to the close, fills inside the edge, and Smart Buy sees a likely route
   to profit under smart sell's own exit policy. Ranked by expected dollars at the size that fills. */
function lineRoute(x){return x.route==='sell'?`Likely to cash out early for a profit: <b>${pct(x.p_exit)}</b>`:`Profit if it holds: <b>${pct(x.win)}</b> to win, +${(x.edge*100).toFixed(1)}¢ edge`;}
function lineRec(x){return `<div class="bet lrec"><div class="bt"><div><span class="kind">${x.kind==='spread'?'📏 Spread':'➕ Total'} · ${esc(x.game||'')}</span><b>${esc(String(x.pick||'').replace(/ \(.*\)$/,''))}</b></div><span class="ret"><span data-num="lx:${esc(x.ticker)}" data-v="${x.exp}" data-pre="+">+${money(x.exp)}</span><small>expected</small></span></div>
  <div class="bnums"><div>Kalshi price<b data-num="lp:${esc(x.ticker)}" data-v="${x.p}" data-f="cent">${Math.round(x.p*100)}¢</b></div><div>Fair chance<b>${pct(x.fair)}</b></div><div>Edge after fee<b class="up">${(x.edge*100).toFixed(1)}¢</b></div></div>
  <div class="why">${lineRoute(x)}. Stake ${money(x.stake)} for ${Number(x.n).toLocaleString()} contract${x.n===1?'':'s'}${x.capped==='depth'?`, all Kalshi has inside the edge right now`:''}. Your bar here: ${(x.min_edge*100).toFixed(1)}¢.</div>
  <button class="btn acc" style="width:100%;min-height:44px" onclick="lineFromBoard('${esc(x.ticker)}',this)">Get a price</button></div>`;}
function linesBlock(d){const ls=d.lines||[];if(!ls.length&&!d.lines_priced)return '';
 return secHead('lines','Spreads &amp; totals',ls.length,'only the ones worth buying')+(!secOpen('lines')?'':ls.length?`<div class="bets">${ls.map(lineRec).join('')}</div>
  <div class="m" style="font-size:12px;margin:6px 2px 0">Priced from the sportsbook line. Expected profit counts Kalshi's fee and what you can really buy at these prices.</div>`
  :`<div class="empty lempty" role="status"><b>No spread or total clears your bar right now.</b><div class="m" style="font-size:12.5px;margin-top:4px">${Number(d.lines_priced).toLocaleString()} checked. They show up here when one is priced well and has a likely way to a profit.</div></div>`);}
