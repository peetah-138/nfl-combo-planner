const TOK="__CWTOK__",LOCAL=__CWLOCAL__,PAGE_VER="__CWVER__";
const $=s=>document.querySelector(s);
const apiRaw=(p,b)=>fetch(p,b===undefined?{credentials:'same-origin',headers:{'X-CW':TOK}}:{method:'POST',credentials:'same-origin',headers:{'X-CW':TOK,'Content-Type':'application/json'},body:JSON.stringify(b)}).then(r=>{if(r.status==403){location.href='/';throw 0;}netUp(r.ok||r.status<500);return r.json().then(rsSee);},e=>{netUp(false);throw e;});
/* Every POST in flight is counted (update.js never reloads under one), and a money result holds a reload for 15 s so its message can be read. */
const VER_HOLD_ACTS=['buy','go','hedgego','singlebuy','pot_move','panel_approve','panel_add','panel_cancel','panel_restart'];
const api=(p,b)=>{if(b===undefined)return apiRaw(p);S.inflight=(S.inflight||0)+1;return apiRaw(p,b).finally(()=>{S.inflight=Math.max(0,(S.inflight||1)-1);if(b&&VER_HOLD_ACTS.includes(b.a))S.verHold=Date.now()+15000;});};
/* Kalshi's refusals, shown honestly (issue #134). When Kalshi turns an order down for the account or the region, the page says
   so in Kalshi's own words, in full (a sheet you can read and copy), and a calm banner stays up while the Mac waits before trying
   again. It is Kalshi's rule, not a bug in the app: the page only reports it and never offers a way around it. `S.rs` is the
   Mac's latest note (`restrict` on Live, Build, Settings and the panel); `j.refusal` is the answer to the tap that was refused. */
function rsTime(t){return t?new Date(t*1000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}):'';}
function rsSee(j){if(!j||typeof j!=='object')return j;
 if(j.restrict){S.rs=j.restrict;rsBan();}
 const f=j.refusal;if(f&&(f.msg||f.code)&&!f.held){S.rsAt=Date.now();clearTimeout(S.rsT);S.rsT=setTimeout(()=>refusalSheet(f.msg,f.code,f.restricted),60);}
 else if(f&&f.held){S.rsAt=Date.now();}
 return j;}
function rsBan(){const el=document.getElementById('rsban');if(!el)return;const b=S.rs&&S.rs.buy,s=S.rs&&S.rs.sell,x=b&&b.active?b:s&&s.active?s:null;
 document.body.classList.toggle('rsb',!!(b&&b.holding));
 if(!x){el.hidden=true;el.innerHTML='';el._sig='';return;}
 const what=x===b?'orders':'sales',sig=what+'|'+x.at+'|'+(x.holding?1:0);if(el._sig===sig&&!el.hidden)return;el._sig=sig;
 el.innerHTML=`<button type="button" class="rsb-in" onclick="refusalSheet(S.rs.${x===b?'buy':'sell'}.msg,S.rs.${x===b?'buy':'sell'}.code,true)"><i aria-hidden="true">⏸</i><span><b>Kalshi isn't allowing ${what} for your account right now</b><small>${x.holding?'The app is waiting until '+esc(rsTime(x.hold_until))+' before it asks again.':'The next one you place will check again.'} Tap to read what Kalshi said.</small></span></button>`;el.hidden=false;}
function rsRow(){const l=S.rs&&S.rs.last;if(!l||!l.msg)return '';const live=S.rs&&((S.rs.buy&&S.rs.buy.active)||(S.rs.sell&&S.rs.sell.active));
 return `<div class="srow"><div class="l"><b>Last Kalshi refusal${live?' · still in place':''}</b><small>${esc(String(l.msg).slice(0,140))}${l.msg.length>140?'…':''} (${esc(rsTime(l.at))})</small></div><button class="btn" type="button" onclick="refusalSheet(S.rs.last.msg,S.rs.last.code,true)">Read it</button></div>`;}
function refusalSheet(msg,code,restricted){msg=String(msg||'').trim();if(!msg&&!code)return;S.rsAt=Date.now();
 const o=document.querySelector('#modal.on #sheet .rsheet');if(o&&o.dataset.m===msg)return;   // already open on this very message
 modal(`<div class="rsheet" data-m="${esc(msg)}"><h3>Kalshi said no</h3><p class="rsmsg" style="user-select:text;-webkit-user-select:text;font-size:15px;line-height:1.5;margin:6px 0 10px">${msg?esc(msg):'Kalshi turned this down and gave no reason.'}</p>
  ${code?`<div class="m" style="font-size:12px;user-select:text;-webkit-user-select:text">Kalshi's code: <b>${esc(code)}</b></div>`:''}
  <p class="m" style="font-size:13px;line-height:1.5;margin:12px 0">${restricted?'This is Kalshi\'s rule for your account or where you are, not a problem in the app. Nothing was bought or sold. The app only reports it and waits before asking again; it can\'t change it.':'Kalshi turned this one down, and nothing was bought or sold.'}</p>
  <div style="display:flex;gap:8px"><button class="btn ghost" type="button" style="flex:1;justify-content:center" onclick="rsCopy(this)">Copy message</button><button class="btn" type="button" style="flex:1;justify-content:center" onclick="closeModal()">Close</button></div></div>`);
 hap('warning');}
function rsCopy(b){const el=document.querySelector('#sheet .rsmsg');const t=el?el.textContent:'';const done=ok=>{b.textContent=ok?'Copied':'Select the text and copy it';};
 try{navigator.clipboard.writeText(t).then(()=>done(true),()=>done(false));}catch(e){done(false);}}
/* Offline/reconnecting: a calm pill under the header ("Reconnecting to your Mac · Updated 40s ago") that appears when
   requests fail or the live link drops for more than a moment, and says "Back online" briefly when it returns. */
function netUp(ok){if(ok){S.okAt=Date.now();if(S.netDown){S.netDown=false;netBanner();}}else if(!S.netDown){S.netDown=true;S.netSince=Date.now();netBanner();}}
function netIsDown(){return !!S.netDown||(S.live_ok===false&&!!S.esEver)||navigator.onLine===false;}   // a live link that never opened (no event stream here) isn't an outage: the page polls instead
function netTxt(){const a=S.okAt?Math.round((Date.now()-S.okAt)/1000):null;return a==null?'':a<3?'Updated just now':a<90?'Updated '+a+'s ago':'Updated '+Math.round(a/60)+' min ago';}
function netBanner(){let el=document.getElementById('netbar');if(!el){el=document.createElement('div');el.id='netbar';el.className='netbar';el.setAttribute('role','status');document.body.appendChild(el);}
 const tb=document.querySelector('.top');if(tb)el.style.top=(tb.getBoundingClientRect().bottom+8)+'px';
 if(netIsDown()){if(S.netShown){const sm=el.querySelector('small');if(sm)sm.textContent=netTxt();return;}
  if(!S.netPend)S.netPend=setTimeout(()=>{S.netPend=0;if(!netIsDown())return;clearTimeout(S.netT);el.className='netbar on';
   el.innerHTML=`<i></i><span>${navigator.onLine===false?'You\'re offline':'Reconnecting to your Mac'}</span><small>${netTxt()}</small>`;S.netShown=true;},S.netNow?0:1200);return;}
 if(S.netPend){clearTimeout(S.netPend);S.netPend=0;}
 if(S.netShown){S.netShown=false;el.className='netbar on ok';el.innerHTML='<i></i><span>Back online</span>';clearTimeout(S.netT);S.netT=setTimeout(()=>{el.classList.remove('on');},1600);}}
addEventListener('online',()=>netBanner());addEventListener('offline',()=>{S.netNow=1;netBanner();S.netNow=0;});
/* the header tucks in once you scroll (with a little hysteresis so it never flickers) */
/* The header tucks (body.hc) only while the page is really scrolled. It is re-read from the page itself (never from a remembered flag) on
   scroll, on every tab switch and every second, so a page that got shorter or was reset without a scroll event can't leave it tucked. */
function hcSync(){const y=scrollY,cur=document.body.classList.contains('hc'),short=document.documentElement.scrollHeight<=innerHeight+1,want=short?false:cur?y>8:y>40;if(want!==cur)document.body.classList.toggle('hc',want);}
(()=>{let raf=0;addEventListener('scroll',()=>{if(!raf)raf=requestAnimationFrame(()=>{raf=0;hcSync();});},{passive:true});})();
/* The tab bar never moves: it is fixed to the bottom of the page, but on iPhones the page's height can stay out of step with what is on
   screen (after the keyboard closes, after returning to the Home Screen app), which floated the bar above the bottom. Whenever what is
   visible is taller than the page, the bar is moved down by the difference (--tbo), so it is always flush with the bottom of the screen.
   A shorter visible area is the keyboard: the bar stays where it is, behind it, as before. */
function tbSet(vv){const given=!!vv;vv=vv||window.visualViewport;if(!vv)return;const d=Math.round(vv.height+vv.offsetTop-innerHeight),px=d>0&&d<400?d:0;
 /* a drift must show in two readings in a row (a rubber-band at the page's end passes in a moment); a reading handed in (the test) counts at once */
 const ok=px===0||given||S.tbp===px;S.tbp=px;if(!ok)return;
 if(S.tbo!==px){S.tbo=px;document.documentElement.style.setProperty('--tbo',px+'px');}}
(()=>{const vv=window.visualViewport,f=()=>{tbSet();hcSync();};if(vv){vv.addEventListener('resize',f);vv.addEventListener('scroll',f);}
 addEventListener('resize',f);addEventListener('orientationchange',()=>setTimeout(f,300));addEventListener('pageshow',f);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(f,100);});
 addEventListener('focusout',()=>setTimeout(()=>{const a=document.activeElement;if(a&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName))return;scrollTo(scrollX,scrollY);f();},350));
 setInterval(()=>{if(!document.hidden)f();},1000);})();
/* keyboard-aware sheets: when the on-screen keyboard opens, the bottom sheet rises above it and the field stays in view */
function kbSet(px){px=Math.max(0,Math.round(px||0));document.documentElement.style.setProperty('--kb',px+'px');S.kb=px;
 if(px){const f=document.activeElement;if(f&&f.closest&&f.closest('#sheet'))setTimeout(()=>f.scrollIntoView({block:'center',behavior:'smooth'}),60);}}
(()=>{const vv=window.visualViewport;if(!vv)return;const f=()=>kbSet(innerHeight-vv.height-vv.offsetTop>80?innerHeight-vv.height-vv.offsetTop:0);vv.addEventListener('resize',f);vv.addEventListener('scroll',f);})();
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=x=>x==null?'—':(Math.abs(x)>=1000?'$'+Math.round(x).toLocaleString():Math.abs(x)>=10?'$'+Math.round(x):'$'+(+x).toFixed(2).replace(/\.00$/,''));
const smoney=x=>x==null?'—':(x>=0?'+':'−')+money(Math.abs(x));
const pct=x=>x==null?'—':x>=.995&&x<1?'>99%':x>=.1?Math.round(x*100)+'%':x>=.001?(x*100).toFixed(1)+'%':'<0.1%';
const SPN={mix:'Mix',nfl:'NFL',nba:'NBA',nhl:'NHL',ahl:'AHL',ncaaf:'CFB',ncaamb:'CBB',ncaawb:'WCBB',soccer:'Soccer',ufc:'UFC',tennis:'Tennis',euroleague:'Euro'};
const ICON={nfl:'🏈',nba:'🏀',nhl:'🏒',ahl:'🏒',ncaaf:'🎓',ncaamb:'🏀',ncaawb:'🏀',soccer:'⚽',ufc:'🥊',tennis:'🎾',euroleague:'🏀',other:'🎯'};
const SVG={live:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.5" fill="currentColor"/><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7" opacity=".45"/></svg>',
 build:'<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
 results:'<svg viewBox="0 0 24 24"><path d="M5 19v-7M12 19V6M19 19v-10" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>',
 games:'<svg viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="14" rx="3" fill="none" stroke="currentColor" stroke-width="1.9"/><path d="M12 5v14M3.5 12h17" stroke="currentColor" stroke-width="1.5" opacity=".7"/></svg>',
 settings:'<svg viewBox="0 0 24 24"><path d="M4 7h10M18 7h2M4 17h4M12 17h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="7" r="2.4" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="10" cy="17" r="2.4" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
 more:'<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.8" fill="currentColor"/><circle cx="12" cy="12" r="1.8" fill="currentColor"/><circle cx="19" cy="12" r="1.8" fill="currentColor"/></svg>'};
const S={view:(localStorage.getItem('cw_view')||'live'),live:null,build:null,res:null,open:{},filter:'all',lg:localStorage.getItem('cw_lg')||'nba',slip:[],busy:{}};
/* A toast always goes away. It has a deadline (not just a timer), and the page also checks that deadline on its own
   every second and whenever you touch, scroll or come back to it, because phones pause timers in the background.
   Tap anywhere to dismiss it early. After the fade it is taken out of the layout so it can never linger. */
function toastHide(){const t=$('#toast');if(!t)return;t._until=0;clearTimeout(t._h);t.classList.remove('on','tap');t.onclick=null;clearTimeout(t._x);t._x=setTimeout(()=>{if(!t.classList.contains('on'))t.hidden=true;},450);}
function toastCheck(){const t=$('#toast');if(t&&t.classList.contains('on')&&Date.now()>=(t._until||0))toastHide();}
/* onTap (optional): the toast becomes a button for that (e.g. open the combo it's about, #210); without it, taps go through. */
function toast(m,ms,tone,onTap){if(S.rsAt&&Date.now()-S.rsAt<1800&&tone!=='good')return;   // Kalshi's own words are on screen in full: no clipped copy of them
 if(tone==='good')hap('success');else if(tone==='bad')hap('error');const t=$('#toast');t.hidden=false;t.textContent=(tone==='good'?'✅ ':tone==='bad'?'⚠️ ':'')+m;t.classList.remove('good','bad');if(tone)t.classList.add(tone);
 t.classList.toggle('tap',!!(onTap&&!document.querySelector('#modal.on')));t.onclick=onTap?(()=>{toastHide();hap('light');onTap();}):null;
 if(t.classList.contains('tap')){t.setAttribute('role','button');t.tabIndex=0;}else{t.removeAttribute('role');t.removeAttribute('tabindex');}
 clearTimeout(t._x);void t.offsetWidth;t.classList.add('on');t._at=Date.now();t._until=Date.now()+(ms||3200);clearTimeout(t._h);t._h=setTimeout(toastHide,ms||3200);}
setInterval(toastCheck,1000);
['touchend','scroll','visibilitychange','focus','pageshow'].forEach(ev=>addEventListener(ev,toastCheck,{passive:true,capture:true}));
addEventListener('pointerdown',e=>{const t=$('#toast');if(t&&t.classList.contains('on')&&!(t.classList.contains('tap')&&t.contains(e.target))&&Date.now()-(t._at||0)>700)toastHide();},{capture:true,passive:true});
/* Sheets. modal() is the bottom sheet (confirmations, small things). pushOpen()/pushFill() is the Kalshi-style push for
   detail pages (a game, a combo): the page slides in from the right in ~270 ms (ease-out) while the page behind slides a
   third of the way left and dims; flat skeleton blocks show until the content swaps in. Back, a tap on the dimmed
   edge, or a swipe right closes it. Switching between the two modes never animates (no flash of a half-moved sheet). */
function sheetMode(push){const m=$('#modal'),sh=$('#sheet');clearTimeout(S.pushT);if(m.classList.contains('push')===push)return;
 sh.style.transition=m.style.transition='none';m.classList.toggle('push',push);sh.classList.toggle('wide',push);sh.style.transform='';void m.offsetWidth;sh.style.transition=m.style.transition='';void m.offsetWidth;}
function modal(h){sheetMode(false);document.body.classList.remove('pushed');S.gameOpen=null;S.gameSig=null;S.comboOpen=null;S.ideaOpen=null;const sh=$('#sheet');sh.classList.remove('wide');sh.innerHTML='<i class="grab"></i>'+h;sh.scrollTop=0;{const t=sh.querySelector('h3');sh.setAttribute('aria-label',t&&t.textContent.trim()||'Details');}
 if(!sh.querySelector('.okcard')&&!matchMedia('(prefers-reduced-motion: reduce)').matches){sh.classList.add('stag');[...sh.children].forEach((c,i)=>c.style.setProperty('--i',i));clearTimeout(S.shT);S.shT=setTimeout(()=>sh.classList.remove('stag'),900);}
 $('#modal').classList.add('on');hap('light');}
/* Smart Buy (issue #137): a calm line under a list it took bets out of (no fanfare: it's a gate). A tap shows the
   short plain reasons in a sheet. `where` is one of two fixed words, never page data. */
function sbSkipLine(xs,where){xs=(Array.isArray(xs)?xs:[]).filter(x=>x&&x.text);S.sbSkip=S.sbSkip||{};S.sbSkip[where]=xs;if(!xs.length)return '';
 const cr=xs.filter(x=>x.credits).length,ip=xs.filter(x=>x.inplay).length,who=cr===xs.length?'Saving odds credits: left out':ip===xs.length?'Games under way: left out':cr||ip?'Left out':'Smart Buy skipped';
 return `<button class="linkb sbskip" type="button" onclick="sbSkipOpen('${where==='ideas'?'ideas':'panel'}')">${who} ${xs.length} ${where==='ideas'?'idea':'bet'}${xs.length===1?'':'s'} · Why?</button>`;}
function sbSkipOpen(w){const xs=(S.sbSkip||{})[w]||[];
 const cr=xs.filter(x=>x.credits).length,sb=xs.length-cr;
 modal(`<h3>${cr&&!sb?'Left out to save odds credits':sb&&!cr?'Smart Buy skipped '+sb:'Left out '+xs.length}</h3>${sb?`<p class="m" style="font-size:13px;line-height:1.45">Smart Buy: priced better than their chance, but unlikely to make money once selling and holding are both played out. They're still tracked, so Smart Buy learns if skipping them was wrong. Switch it off in Settings › Money.</p>`:''}${cr?`<p class="m" style="font-size:13px;line-height:1.45">Odds credits are low, so sharp lines are only read for games starting soon. A game more than 4 hours away with only free lines isn't bought. Once the game is close (or credits recover) it can turn up again, as a new bet you can add.</p>`:''}
  ${xs.map(x=>`<div class="sbrow" style="padding:10px 0;border-top:1px solid var(--line)"><b style="font-size:14px">${esc(x.text)}</b><div class="m" style="font-size:12.5px;margin-top:2px;line-height:1.4">${esc(x.why||'')}</div></div>`).join('')}
  <button class="btn ghost" type="button" style="width:100%;justify-content:center;margin-top:12px" onclick="closeModal()">Close</button>`);}
function closeModal(){const m=$('#modal');
 /* the buy sheet opened from a game page goes back to that game however it is closed (Cancel, backdrop, drag) */
 const sbBack=S.sb&&S.sb.back&&document.querySelector('#sheet #sbx')&&m.classList.contains('on')?S.sb.back:null;if(sbBack){S.sb=null;setTimeout(()=>openGame(sbBack),300);}
 if(m.classList.contains('on'))hap('light');m.classList.remove('on');document.body.classList.remove('pushed');S.gameOpen=null;S.gameSig=null;S.comboOpen=null;S.ideaOpen=null;
 clearTimeout(S.pushT);if(m.classList.contains('push'))S.pushT=setTimeout(()=>{if(!m.classList.contains('on'))sheetMode(false);},340);else $('#sheet').classList.remove('wide');}
const BACK='<svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function pushSkel(){return `<div class="psk"><i style="height:14px;width:28%"></i><i style="height:26px;width:66%"></i><i style="height:84px"></i>
 <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><i style="height:62px"></i><i style="height:62px"></i><i style="height:62px"></i><i style="height:62px"></i></div><i style="height:170px"></i><i style="height:16px;width:40%"></i><i style="height:44px"></i><i style="height:44px"></i></div>`;}
function pushOpen(title){const m=$('#modal'),sh=$('#sheet');const was=m.classList.contains('on')&&m.classList.contains('push');
 if(!was){m.classList.remove('on');sheetMode(true);}
 pushFill(pushSkel(),title,true);sh.scrollTop=0;S.pushAt=performance.now();
 if(!was){m.classList.add('on');document.body.classList.add('pushed');hap('light');}}
/* the content waits for the slide to finish, so the swap never janks the motion */
function pushWait(){const left=(S.pushAt||0)+290-performance.now();return left>0?new Promise(z=>setTimeout(z,left)):Promise.resolve();}
function pushFill(h,title,sk){const sh=$('#sheet');const first=sh.dataset.sk==='1'&&!sk;
 sh.innerHTML=`<div class="pbar"><button class="back" onclick="closeModal()" aria-label="Back">${BACK}Back</button><span class="pt">${esc(title||'')}</span></div><div class="pbody ${first?'fadein':''}">${h}</div>`;
 sh.dataset.sk=sk?'1':'';rollNums(sh);wireScrubs(sh);
 if(first&&!matchMedia('(prefers-reduced-motion: reduce)').matches){const b=sh.querySelector('.pbody');b.classList.add('stag');[...b.children].forEach((c,i)=>c.style.setProperty('--i',i));setTimeout(()=>b.classList.remove('stag'),1200);}}
$('#modal').addEventListener('click',e=>{if(e.target.id==='modal')closeModal();});
(()=>{const sh=$('#sheet');let x0=null,y0=null,dx=0,dy=0,ax=null,past=false;
 const cross=v=>{if(v!==past){past=v;hap(v?'light':'selection');}};
 /* a swipe that starts on the game tab row (or any sideways-scrolling strip) belongs to that strip, never to swipe-back */
 const hscroll=el=>{for(;el&&el!==sh&&el.nodeType===1;el=el.parentElement){if(el.classList.contains('gtabs'))return true;const o=getComputedStyle(el).overflowX;if((o==='auto'||o==='scroll')&&el.scrollWidth>el.clientWidth)return true;}return false;};
 sh.addEventListener('touchstart',e=>{const t=e.touches[0];dx=dy=0;ax=null;past=false;
  if($('#modal').classList.contains('push')){if(hscroll(e.target)){x0=y0=null;return;}x0=t.clientX;y0=t.clientY;return;}x0=null;
  if(sh.scrollTop>0||innerWidth>760){y0=null;return;}y0=t.clientY;},{passive:true});
 sh.addEventListener('touchmove',e=>{const t=e.touches[0];
  if(x0!=null){const mx=t.clientX-x0,my=t.clientY-y0;if(ax==null&&(Math.abs(mx)>8||Math.abs(my)>8))ax=mx>0&&Math.abs(mx)>Math.abs(my)*1.2?'x':'y';
   if(ax!=='x')return;dx=Math.max(0,mx);sh.classList.add('drag');sh.style.transform=`translateX(${dx}px)`;cross(dx>100);return;}
  if(y0==null)return;dy=Math.max(0,t.clientY-y0);if(dy>4){sh.classList.add('drag');sh.style.transform=`translateY(${dy}px)`;cross(dy>110);}},{passive:true});
 sh.addEventListener('touchend',()=>{sh.classList.remove('drag');sh.style.transform='';
  if(x0!=null){x0=null;if(ax==='x'&&dx>100)closeModal();return;}
  if(y0==null)return;if(dy>110)closeModal();y0=null;dy=0;});})();
/* Press feedback and a haptic tick on every interactive thing, in one place, so nothing can be missed: anything
   matching TAP shrinks a touch while pressed (rows and settings lines highlight instead) and ticks when tapped.
   Tabs, chips, segments and switches tick as "selection"; the rest "light". A control's own hap() right after is
   folded into the same tick; success/warning/error always play their own pattern. */
const TAP='button,a[href],[onclick],.chip,.trow,label,select,summary,input[type=checkbox],input[type=range]';
function tapEl(t){if(t&&t.classList&&t.classList.contains('hsw'))t=t.parentElement;const el=t&&t.closest&&t.closest(TAP);return el&&!el.closest('.hapx')&&!el.disabled?el:null;}
(()=>{let held=null;const up=()=>{const el=held;held=null;if(el)setTimeout(()=>el.classList.remove('prs'),70);};
 addEventListener('pointerdown',e=>{if(e.button)return;const el=tapEl(e.target);if(!el)return;up();held=el;el.classList.add('prs');},{capture:true,passive:true});
 ['pointerup','pointercancel','dragstart'].forEach(k=>addEventListener(k,up,{capture:true,passive:true}));addEventListener('scroll',up,{capture:true,passive:true});
 addEventListener('click',e=>{const tg=e.target;if(tg&&tg.matches&&(tg.matches('.hsw,input[switch]')||tg.matches('label')&&tg.querySelector('input[switch]')))S.hswAt=performance.now();   // the finger's own switch ticked
  const el=tapEl(e.target);if(!el||el.matches('input[type=range]')||el.closest('[data-hapt]'))return;
  hap(el.matches('.tabbar button,.nav button,.seg button,.sbtog button,.gtabs button,.ant button,.rng2 button,.chip,select,input[type=checkbox],label')?'selection':'light');},true);
 addEventListener('input',e=>{if(e.target&&e.target.type==='range')hap('selection');},true);})();
/* swipe left or right anywhere on a page to move between tabs */
(()=>{let x0=null,y0=0,t0=0,ok=true;
 addEventListener('touchstart',e=>{const t=e.target;ok=!(t.closest&&t.closest('.chips,.seg,.ant,.sheet,input:not(.hsw),.board,.chartbox,.spark,.sparkw,.scrub,.antbl,svg,.dcard.idea'));x0=e.touches[0].clientX;y0=e.touches[0].clientY;t0=Date.now();},{passive:true});
 addEventListener('touchend',e=>{if(x0==null||!ok||$('#modal').classList.contains('on'))return;const t=e.changedTouches[0],dx=t.clientX-x0,dy=t.clientY-y0;x0=null;
  if(Math.abs(dx)<80||Math.abs(dy)>Math.abs(dx)*.6||Date.now()-t0>600||innerWidth>900)return;const i=TABS.indexOf(S.view),j=i+(dx<0?1:-1);if(j<0||j>=TABS.length)return;hap('light');go(TABS[j],dx<0?1:-1);},{passive:true});})();
/* Pull down at the top of any tab to refresh it: the page follows the finger with a rubber band, a ring fills as you
   pull, it ticks once at the point where letting go refreshes, spins while loading and ends on a small check. */
(()=>{let y0=null,dy=0,el=null,busy=false;const C=2*Math.PI*8,TH=64;
 const ptr=()=>el||(el=Object.assign(document.createElement('div'),{id:'ptr',innerHTML:'<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="8" stroke-dasharray="'+C.toFixed(1)+'" stroke-dashoffset="'+C.toFixed(1)+'"/><path d="M6 10.4l2.6 2.6L14 7.6"/></svg>'}),document.body.appendChild(el),el);
 const skip=t=>!!(t&&t.closest&&t.closest('.sheet,.sparkw,.scrub,input:not(.hsw),select,textarea,.chips,.seg,.ant,.sidx'));
 const main=()=>$('#main'),reduce=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
 addEventListener('touchstart',e=>{y0=(!busy&&scrollY<=0&&!$('#modal').classList.contains('on')&&!skip(e.target))?e.touches[0].clientY:null;dy=0;},{passive:true});
 addEventListener('touchmove',e=>{if(y0==null)return;const raw=e.touches[0].clientY-y0;if(raw<=0||scrollY>0){if(dy){dy=0;const p=ptr();p.style.opacity=0;const m=main();if(m){m.style.transform='';}}return;}
  dy=110*(1-Math.exp(-raw/150));const p=ptr(),k=Math.min(1,dy/TH);p.classList.add('drag');p.style.opacity=Math.min(1,k*1.4);p.style.transform=`translateY(${-40+k*50}px)`;
  p.querySelector('circle').style.strokeDashoffset=(C*(1-k)).toFixed(1);const m=main();if(m&&!reduce()){m.classList.add('ptrd');m.style.transform=`translateY(${(dy*.45).toFixed(1)}px)`;}
  if(dy>=TH&&!p._hit){p._hit=1;hap('selection');}else if(dy<TH&&p._hit){p._hit=0;}},{passive:true});
 addEventListener('touchend',async()=>{if(y0==null)return;const p=ptr(),m=main();y0=null;p.classList.remove('drag');if(m){m.classList.remove('ptrd');m.style.transform='';}
  if(dy>=TH){busy=true;p.classList.add('go');p.style.transform='translateY(10px)';const v=S.view;await load(v,true).catch(()=>{});
   p.classList.remove('go');p.classList.add('done');hap('success');await new Promise(z=>setTimeout(z,520));busy=false;}
  p.classList.remove('go','done');p._hit=0;p.style.opacity=0;p.style.transform='translateY(-40px)';dy=0;});})();
function chrome(){const tabs=[['live','Live'],['games','Games'],['build','Build'],['results','Results'],['settings','Settings']];
 $('#nav').innerHTML=tabs.map(([k,l])=>`<button class="${S.view===k?'on':''}" onclick="go('${k}')">${l}</button>`).join('');
 $('#tabbar').innerHTML=tabs.map(([k,l])=>`<button class="${S.view===k?'on':''}" onclick="go('${k}')">${SVG[k]}${l}</button>`).join('');
}
const TABS=['live','games','build','results','settings'];
function go(v,dir){hap('selection');const same=S.view===v;if(!same)S.entered=true;const from=TABS.indexOf(S.view);S.view=v;try{localStorage.setItem('cw_view',v)}catch(e){};chrome();
 const paint=()=>{render();window.scrollTo(0,0);hcSync();tbSet();};
 if(!same&&!dir&&document.startViewTransition&&!matchMedia('(prefers-reduced-motion: reduce)').matches){document.startViewTransition(paint);}
 else{paint();const m=$('#main');if(m&&!same){const c=dir?(dir>0?'sw-l':'sw-r'):'enter';m.classList.remove('enter','sw-l','sw-r');void m.offsetWidth;m.classList.add(c);}}
 load(v);}
function render(){({live:renderLive,games:renderGames,build:renderBuild,results:renderResults,settings:renderSettings}[S.view]||renderLive)();afterPaint();}
S.nums=S.nums||{};S.sigs=S.sigs||{};S.entered=true;   // the first real paint of the page staggers in too
const rndm=x=>Math.sign(x)*Math.round(Math.abs(x));   // rounds on magnitude, so -0.5 and +0.5 match
function fmtNum(v,f){return f==='pct'?pct(v):f==='int'?String(Math.round(v)):f==='cint'?Math.round(v).toLocaleString('en-US'):f==='cent'?Math.round(v*100)+'¢':f==='chg'?(r=>(r>0?'+':r<0?'−':'')+Math.abs(r)+'%')(rndm(v*100)):f==='chgd'?(r=>(r>0?'+':r<0?'−':'')+'$'+(Math.abs(r)/100).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}))(rndm(v*100)):f==='absm'?money(Math.abs(v)):f==='spct'?(v>=0?'+':'−')+Math.abs(Math.round(v*100))+'%':money(v);}
function stagger(){if(!S.entered||document.querySelector('#main .skel,#main .hsk'))return;S.entered=false;if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 const mn=$('#main');if(mn){mn.classList.add('arrived');clearTimeout(S.arrT);S.arrT=setTimeout(()=>mn.classList.remove('arrived'),1600);}
 document.querySelectorAll('.cgrid,.games,.tbl,.board,.panel-items,.antbl,.hist,.set>div:last-child,.doit,.hs,.plist').forEach(box=>{box.classList.add('stag');[...box.children].slice(0,24).forEach((c,i)=>c.style.setProperty('--i',i));setTimeout(()=>box.classList.remove('stag'),1600);});
 const kp=document.querySelector('.kpis');if(kp){kp.classList.add('stag');[...kp.children].forEach((c,i)=>c.style.setProperty('--i',i));setTimeout(()=>kp.classList.remove('stag'),900);}
 document.querySelectorAll('.chart rect').forEach((r,i)=>r.style.setProperty('--i',i));}
function segInd(){document.querySelectorAll('.seg,.ant').forEach((sg,k)=>{const on=sg.querySelector('button.on');let ind=sg.querySelector(':scope>.segind');
  if(!on){if(ind)ind.remove();return;}if(!ind){ind=document.createElement('i');ind.className='segind';sg.prepend(ind);sg.classList.add('hasind');}
  const key=sg.dataset.k||(sg.className+':'+k);const prev=S.segs&&S.segs[key];S.segs=S.segs||{};
  const to={left:on.offsetLeft,top:on.offsetTop,width:on.offsetWidth,height:on.offsetHeight};
  if(prev&&(prev.left!==to.left||prev.top!==to.top)){ind.style.transition='none';Object.assign(ind.style,{left:prev.left+'px',top:prev.top+'px',width:prev.width+'px',height:prev.height+'px'});void ind.offsetWidth;ind.style.transition='';}
  Object.assign(ind.style,{left:to.left+'px',top:to.top+'px',width:to.width+'px',height:to.height+'px'});S.segs[key]=to;});
 const tb=document.querySelector('.tabbar');const on=tb&&tb.querySelector('button.on');if(on){let ti=tb.querySelector('.tabind');if(!ti){ti=document.createElement('i');ti.className='tabind';tb.appendChild(ti);}
  ti.style.left=(on.offsetLeft+on.offsetWidth/2-14)+'px';ti.style.width='28px';}}
function afterPaint(){stagger();segInd();rollNums(document);paintErr();wireScrubs(document);
 const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
 /* #140 score burst: a changed score glows its row and pops the digits. The burst is kept in S with an expiry, because Live
    repaints on every tick and would wipe a DOM-only class half way through. Reduced motion: no animation at all. */
 S.burst=S.burst||{};document.querySelectorAll('[data-sig]').forEach(el=>{const k=el.dataset.key,sg=el.dataset.sig;const old=S.sigs[k];S.sigs[k]=sg;const now=Date.now();
  if(old!=null&&old!==sg&&!reduce)S.burst[k]=now+1500;
  if((S.burst[k]||0)>now){el.classList.add('rowpop','burst');setTimeout(()=>{el.classList.remove('rowpop','burst');if((S.burst[k]||0)<=Date.now())delete S.burst[k];},Math.max(50,S.burst[k]-now));}});}
/* Numbers roll to their new value frame by frame (~0.65 s, ease-out) with a green/red flash; chance bars slide. */
function rollNums(root){const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;S.bars=S.bars||{};
 root.querySelectorAll('[data-bar]').forEach(el=>{const k=el.dataset.bar,w=el.style.width,old=S.bars[k];S.bars[k]=w;
  if(old==null||old===w||reduce)return;el.style.transition='none';el.style.width=old;void el.offsetWidth;el.style.transition='';el.style.width=w;});
 root.querySelectorAll('[data-num]').forEach(el=>{const k=el.dataset.num,v=parseFloat(el.dataset.v),f=el.dataset.f,pre=el.dataset.pre||'';if(isNaN(v))return;const old=S.nums[k];S.nums[k]=v;
  if(old==null||Math.abs(old-v)<(f==='pct'||f==='spct'||f==='chg'?.0005:.005)||reduce)return;el.classList.remove('fl-up','fl-down');void el.offsetWidth;el.classList.add(v>old?'fl-up':'fl-down');
  const t0=performance.now(),dur=650;const step=t=>{const k2=Math.min(1,(t-t0)/dur),e=1-Math.pow(1-k2,3);el.textContent=pre+fmtNum(old+(v-old)*e,f);if(k2<1)requestAnimationFrame(step);};requestAnimationFrame(step);});}
function cget(k){try{const x=JSON.parse(localStorage.getItem('cw_c_'+k)||'null');return x&&Date.now()-x.t<6*3600e3?x.d:null}catch(e){return null}}
function cput(k,d){try{if(d)localStorage.setItem('cw_c_'+k,JSON.stringify({t:Date.now(),d}))}catch(e){}}
function warm(v){/* show the last copy straight away while the fresh one loads */
 if(v==='live'&&!S.live){S.live=cget('live');if(S.live)head(S.live);}
 if(v==='build'&&(!S.build||S.build.lg!==S.lg)){S.build=cget('build_'+S.lg);S.panel=cget('panel_'+(S.pview||'all'))||S.panel;}
 if(v==='results'&&!S.res)S.res=cget('results');if(v==='results'&&!S.an)S.an=cget('analytics');
 if(v==='games'&&!S.games)S.games=cget('games');
 if(S.view===v&&(v!=='build'||S.build))render();}
// ---- freshness: how old the numbers on screen are, counted on the phone between loads. Two separate things:
//   • the snapshot ("prices"): when the dollar numbers on screen were last worked out (the snapshot build) — this is
//     the age the big number actually has, so the stamp leads with it and goes red when it is stale;
//   • the scores: how old the live games' scores are (only while a game is on). Shown alongside so a stale snapshot
//     and stale scores are never conflated into one misleading "Updated N ago".
S.fr={};
function frSet(k,f){if(f&&f.ver&&typeof verSeen==='function')verSeen(f.ver);if(f&&f.built)S.fr[k]={f:f,recv:Date.now()};}
function frEl(k){const o=S.fr[k];return o?Math.max(0,(Date.now()-o.recv)/1000):0;}        // seconds since this page got it
function frBuilt(k){const o=S.fr[k];if(!o)return null;return Math.max(0,o.f.now-o.f.built+frEl(k));}   // snapshot/prices age
function frScores(k){const o=S.fr[k];if(!o||o.f.scores==null)return null;return Math.max(0,o.f.scores+frEl(k));} // scores age
function agoTxt(a){return a<3?'just now':a<90?Math.round(a)+'s ago':Math.round(a/60)+' min ago';}
function frLive(k){const o=S.fr[k];return !!(o&&o.f.live);}                                                   // is a game under way (server says)
function frTxt(k){const b=frBuilt(k);if(b==null)return '';const s=frScores(k);
 return(!frLive(k)||s==null)?'Updated '+agoTxt(b):'Prices '+agoTxt(b)+' · scores '+agoTxt(s);}
function frTick(){document.querySelectorAll('[data-fr]').forEach(e=>{const k=e.dataset.fr,t=frTxt(k);if(e.textContent!==t)e.textContent=t;e.classList.toggle('old',(frBuilt(k)||0)>60);});}
setInterval(()=>{frTick();clkTick();if(S.netShown||S.netDown||S.live_ok===false)netBanner();},1000);
setInterval(()=>{if(!document.hidden&&S.gameOpen&&$('#modal').classList.contains('on')&&Date.now()-(S.gameAt||0)>5500)drawGame();},2000);
async function load(v,fresh){try{warm(v);
 if(v==='live'){const prev=S.liveNet?S.live:null;S.live=await api('/app/api/live'+(fresh?'?fresh=1'+ovQ('&'):ovQ('?')));head(S.live);cput('live',S.live);frSet('L',S.live.fresh);try{liveMoments(prev,S.live)}catch(e){}S.liveNet=true;}
 if(v==='build'){const lg=S.lg,pv=S.pview||'all';const [b,p]=await Promise.all([api('/app/api/build?lg='+lg+(fresh?'&fresh=1':'')+ovQ('&')),api('/app/api/panel?v='+pv+ovQ('&')).catch(()=>null)]);
  if(lg!==S.lg||pv!==(S.pview||'all'))return;S.build=b;S.panel=p;cput('build_'+lg,b);cput('panel_'+pv,p);}
 if(v==='results'){S.res=await api('/app/api/results');head(S.res);cput('results',S.res);
  api('/app/api/analytics').then(a=>{S.an=a;cput('analytics',a);if(S.view==='results')renderResults();}).catch(()=>{});}
 if(v==='games'){S.games=await api('/app/api/games');cput('games',S.games);frSet('N',S.games.fresh);}
 if(v==='settings'){const [st,mac,pk]=await Promise.all([api('/app/api/settings?lg='+(S.slg||S.lg)),LOCAL?api('/app/mac',{a:'status'}).catch(()=>null):api('/app/mac-info',{}).catch(()=>null),api('/app/push',{a:'key'}).catch(()=>null)]);S.set=st;S.mac=mac;S.pk=pk;await fidLoad();try{const pp=await api('/app/api/panel?v=all');S.panelCuts=pp.cutoffs;S.skim={reserved:pp.reserved}}catch(e){}
  try{const reg=navigator.serviceWorker&&await navigator.serviceWorker.getRegistration();const sub=reg&&reg.pushManager&&await reg.pushManager.getSubscription();S.pushOn=!!sub;}catch(e){S.pushOn=false;}}
 if(S.lerr)delete S.lerr[v];if(S.view===v)render();}catch(e){if(e)console.log(e);
  const have={live:S.live,games:S.games,build:S.build,results:S.res,settings:S.set}[v];   // nothing to show yet: say so, with a retry, instead of a skeleton forever
  if(e!==0&&!have){S.lerr=S.lerr||{};S.lerr[v]=navigator.onLine===false?'You\'re offline.':'Couldn\'t reach your Mac. It may be asleep or restarting.';if(S.view===v)render();}}}
/* the error card for a screen that couldn't load: calm, says why, and a Try again that spins while it retries */
function errCard(v){return `<div class="card empty err" data-ic="⚠️"><b>Couldn't load this screen</b>${esc((S.lerr||{})[v]||'')}<br><button class="btn acc" onclick="retry('${v}',this)">Try again</button></div>`;}
async function retry(v,b){btnBusy(b,'Trying…');await load(v,true);
 if((S.lerr||{})[v]&&b&&b.isConnected){btnState(b,false,'Still no answer');setTimeout(()=>{if(b.isConnected){b.className='btn acc';b.textContent='Try again';}},2200);}}
/* A button that reports back: spins while working, then a check and "Done" (green) or a cross (red, a small shake),
   then its old self. */
function btnState(b,ok,label,ms){if(!b||!b.isConnected)return;hap(ok?'success':'error');b.disabled=false;b.classList.remove('st-ok','st-bad');void b.offsetWidth;b.classList.add(ok?'st-ok':'st-bad');
 b.innerHTML=(ok?'✓ ':'✕ ')+esc(label||(ok?'Done':'Didn\'t work'));b.dataset.st=ok?'ok':'bad';
 if(ms!==0){const old=b._old;clearTimeout(b._st);b._st=setTimeout(()=>{if(b.isConnected){b.classList.remove('st-ok','st-bad');delete b.dataset.st;if(old!=null)b.innerHTML=old;b._old=null;}},ms||2200);}}
/* #140: a failed button shakes and says why right under itself, in plain words, until the next try or 15 s. It replaces the
   6-7 s toast. The reason lives in S.berr, not only in the DOM, because Build/Live repaint and would wipe it (host = a selector
   that finds the same card or button again after a repaint). If the host is gone it falls back to the toast so the reason is never lost. */
function btnFail(host,msg,b){S.berr={host,msg:String(msg||'That didn\'t go through.'),until:Date.now()+15000};
 if(b&&b.isConnected){b.classList.remove('st-bad');void b.offsetWidth;b.classList.add('st-bad');setTimeout(()=>{if(b.isConnected)b.classList.remove('st-bad');},600);}
 if(!paintErr()){toast(S.berr.msg,7000,'bad');S.berr=null;}}
function paintErr(){document.querySelectorAll('.berr').forEach(e=>e.remove());const e=S.berr;if(!e)return false;if(Date.now()>e.until){S.berr=null;return false;}
 let h=null;try{h=document.querySelector(e.host);}catch(x){}if(!h)return false;
 const d=document.createElement('div');d.className='berr';d.setAttribute('role','status');d.innerHTML='<i aria-hidden="true">✕</i><span>'+esc(e.msg)+'</span>';h.insertAdjacentElement('afterend',d);
 clearTimeout(S.berrT);S.berrT=setTimeout(()=>{if(S.berr&&Date.now()>=S.berr.until){S.berr=null;document.querySelectorAll('.berr').forEach(x=>x.remove());}},Math.max(50,e.until-Date.now()+50));return true;}
function btnBusy(b,label){if(!b)return;if(b._old==null)b._old=b.innerHTML;b.disabled=true;b.innerHTML='<span class="spin" aria-hidden="true"></span> '+esc(label||b.textContent.trim());}
function head(d){if(!d)return;if(d.balance!=null)$('#bal').textContent=money(d.balance);
 if(d.week_pl!=null){const w=$('#wk');w.textContent=smoney(d.week_pl);w.className=d.week_pl>=0?'up':'down';}}
function skel(n){return Array.from({length:n},()=>'<div class="skel" style="height:66px;margin-bottom:10px"></div>').join('');}
