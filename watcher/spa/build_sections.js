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
/* The dates combos are built over (#248; it used to live in Settings > Games & picks). The same saved per-league settings as
   before (next_day, thursday, saturday, monday, mix_window), read from Build's own `days` and saved through the same settings
   call, so the Mac and every device share them. Display and placement only: nothing here buys, sizes or changes a cap. */
function dayRange(d){const v=d.days;if(!v)return '';
 const seg=(on,lab,js)=>`<button type="button" class="${on?'on':''}" aria-pressed="${!!on}" onclick="${js}">${lab}</button>`;
 const two=(k,on)=>`<div class="seg daybar">${seg(!on,'Today',`setDays({${k}:false})`)}${seg(on,'Tomorrow',`setDays({${k}:true})`)}</div>`;
 let title='Games to build over',sub='',body='';
 if(v.mode==='day'){sub=`Combos and the board use ${v.next_day?'tomorrow\'s':'today\'s'} ${esc(d.name)} games.`;body=two('next_day',!!v.next_day);}
 else if(v.mode==='mix'){title='Games from';sub='Which games Mixed sports can combine.';
  body=`<div class="seg daybar">${v.windows.map((w,i)=>seg(v.mix_window===i,esc(w),`setDays({mix_window:${i}})`)).join('')}</div>`
   +(v.mix_window===0?`<div class="drl2">Same day means</div>${two('next_day',!!v.next_day)}`:'');}
 else{sub='Sunday is always in.';
  const chip=(on,lab,js)=>`<button type="button" class="chip ${on?'on':''}" aria-pressed="${!!on}" onclick="${js}">${lab}</button>`;
  body=`<div class="chips daychips">${chip(v.thursday,v.wed?'Wed & Thu':'Thursday',`setDays({thursday:${!v.thursday}})`)}<span class="dsun">Sunday is always in</span>${chip(v.saturday,'Saturday',`setDays({saturday:${!v.saturday}})`)}${chip(v.monday,'Monday',`setDays({monday:${!v.monday}})`)}</div>`;}
 return `<div class="dayrange" id="dayrange"><div class="drl"><b>${title}</b><small>${sub}</small></div>${body}</div>`;}
/* Same call the Settings screen makes (/app/api/settings with this league); on a failure the old choice comes back. */
async function setDays(vals){hap('selection');const days=(S.build||{}).days;if(!days)return;const lg=S.lg;
 const was={};Object.keys(vals).forEach(k=>{was[k]=days[k];});Object.assign(days,vals);renderBuild();
 const r=await api('/app/api/settings',{lg,values:vals}).catch(()=>({ok:false}));
 if(!r||!r.ok){if(S.lg===lg&&S.build&&S.build.days)Object.assign(S.build.days,was);toast('Couldn\'t change the dates. Nothing was changed.');renderBuild();return;}
 /* other dates = another board: picks and a price made on the old one are dropped, so a combo is only ever priced from what's on screen */
 S.set=null;S.slip=[];S.custom=null;S.build=null;renderBuild();load('build',true);
 if(r.synced===false)toast('Saved here, but the Mac watcher didn\'t get it. Try again.');}
try{S.bsec=JSON.parse(localStorage.getItem('cw_bsec')||'null')||{}}catch(e){S.bsec={}}
function secOpen(k){return S.bsec[k]!==false;}
/* folding a Build section: the chevron turns and the section rises in, instead of jumping */
function secTog(k){hap('selection');S.bsec[k]=!secOpen(k);try{localStorage.setItem('cw_bsec',JSON.stringify(S.bsec))}catch(e){}S.secJust=k;renderBuild();S.secJust=null;
 const h=document.querySelector(`.sech[data-k="${k}"]`);if(!h)return;const c=h.querySelector('.chev');
 requestAnimationFrame(()=>requestAnimationFrame(()=>{if(c)c.classList.remove('from-open','from-shut');}));
 if(secOpen(k)){let n=h.nextElementSibling;for(let i=0;i<2&&n&&!n.classList.contains('sech');i++,n=n.nextElementSibling)n.classList.add('unfold');}}
function secHead(k,title,n,sub,extra){const o=secOpen(k);return `<h2 class="sech ${o?'open':''}" data-k="${k}" onclick="secTog('${k}')"><span class="chev ${S.secJust===k?(o?'from-shut':'from-open'):''}">▾</span>${title} <span class="n">${n}</span>${o&&sub?`<span class="r m" style="font-size:12px">${sub}</span>`:''}${extra?`<span class="r">${extra}</span>`:''}</h2>${o?'':`<div class="m secfold" onclick="secTog('${k}')">Folded · tap to show</div>`}`;}
/* Spreads & totals (issue #117) are recommendations only and now live in Best bets (#63): a strike shows when it clears the
   league's learned bar after the fee, fills inside the edge and has a likely route to profit; build.js draws them. */
function lineRoute(x){return x.route==='sell'?`Likely to cash out early for a profit: <b>${pct(x.p_exit)}</b>`:`Profit if it holds: <b>${pct(x.win)}</b> to win, +${(x.edge*100).toFixed(1)}¢ edge`;}
