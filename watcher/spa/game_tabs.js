/* ---- The game page's tab framework (display only). One spec per sport says which tabs its page has; a sport with no spec
   (or a spec with only one visible tab) gets no tab row and the page is exactly as before. A tab is {k, l, has(r), html(r, ov)}:
   `has` hides it when its data is missing (a bad or absent feed shows nothing), `html` draws its panel (`ov` is the overview
   markup). The chosen tab lives in S.gtab and survives the page's periodic redraws; only the open tab's panel is drawn. */
const FOOTBALL_TABS=[{k:'overview',l:'Overview',html:(r,ov)=>ov},{k:'pbp',l:'Play-by-play',has:pbpHas,html:pbpHtml},
 {k:'box',l:'Box score',has:boxHas,html:boxHtml},{k:'tstats',l:'Team stats',has:tsHas,html:tsHtml},{k:'inj',l:'Injury report',has:injHas,html:injHtml},
 {k:'last5',l:'Last 5 games',has:l5Has,html:l5Html},{k:'leaders',l:'Season leaders',has:ldHas,html:ldHtml}];
const GAME_TABS={nfl:FOOTBALL_TABS,ncaaf:FOOTBALL_TABS};
function gameTabList(r){const spec=GAME_TABS[((r||{}).leg||{}).sport];if(!spec)return [];const a=spec.filter(t=>!t.has||t.has(r));return a.length>1?a:[];}
function gameTabCur(tabs){return tabs.some(t=>t.k===S.gtab)?S.gtab:(tabs[0]||{}).k;}
function gameTabsHtml(r,ov){const tabs=gameTabList(r);S.gtabCur=null;if(!tabs.length)return ov;const cur=gameTabCur(tabs);S.gtabCur=cur;
 return `<div class="gtabs" role="tablist">${tabs.map(t=>`<button type="button" role="tab" class="gtab${t.k===cur?' on':''}" aria-selected="${t.k===cur}" data-tab="${esc(t.k)}" onclick="gameTab('${esc(t.k)}')">${esc(t.l)}</button>`).join('')}<i class="gtabind"></i></div>
 ${tabs.map(t=>`<div class="gpanel" role="tabpanel" data-tab="${esc(t.k)}"${t.k===cur?'':' hidden'}>${t.k===cur||t===tabs[0]?t.html(r,ov):''}</div>`).join('')}`;}
/* switch tab without a full repaint: only the visible panel is (re)drawn, and leaving the play-by-play puts the strip back to live */
function gameTab(k){const r=S.gameR,tabs=gameTabList(r),t=tabs.find(x=>x.k===k);if(!t)return;const was=S.gtabCur;S.gtab=k;S.gtabCur=k;
 document.querySelectorAll('#sheet .gtab').forEach(b=>{const on=b.dataset.tab===k;b.classList.toggle('on',on);b.setAttribute('aria-selected',on);});
 document.querySelectorAll('#sheet .gpanel').forEach(p=>{const on=p.dataset.tab===k;p.hidden=!on;if(on&&p.dataset.tab!==tabs[0].k){p.innerHTML=t.html(r,'');gtabIn(p);}else if(!on&&p.dataset.tab!==tabs[0].k)p.innerHTML='';});
 gameTabInd();if(was==='pbp'&&k!=='pbp'&&S.pbpStep!=null){S.pbpStep=null;pbpRefresh('slide');}}
/* The sliding underline. It is a child of the scrolling row, so it scrolls with the tabs and offsetLeft is already right.
   The row is only scrolled to the chosen tab when the tab (or its place) changes, or on the first draw: a redraw puts
   the row back where the finger left it (#218: every live redraw used to yank a row scrolled away back to the chosen tab). */
function gameTabInd(){const bar=document.querySelector('#sheet .gtabs');if(!bar)return;const on=bar.querySelector('.gtab.on'),ind=bar.querySelector('.gtabind');if(!on||!ind)return;
 const to={left:on.offsetLeft,width:on.offsetWidth},prev=S.gtabPos,moved=!prev||prev.left!==to.left||prev.width!==to.width;
 /* paintGame rebuilds the row, so a fresh underline starts at left:0/width:0: always seed it where the old one was (or where it is going), no transition, then glide only if the tab changed */
 const from=prev||to;ind.style.transition='none';ind.style.left=from.left+'px';ind.style.width=from.width+'px';void ind.offsetWidth;ind.style.transition='';
 ind.style.left=to.left+'px';ind.style.width=to.width+'px';S.gtabPos=to;
 if(S.gtabScroll!=null){bar.scrollLeft=S.gtabScroll;S.gtabScroll=null;}
 const vis=on.offsetLeft-bar.scrollLeft;if(moved&&(vis<0||vis+on.offsetWidth>bar.clientWidth))bar.scrollTo({left:on.offsetLeft-(bar.clientWidth-on.offsetWidth)/2,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}
addEventListener('resize',()=>{if(document.querySelector('#sheet .gtabs'))gameTabInd();});
/* #218: a finger on the tab row (and its glide after) holds the game page still: a redraw would replace the row under
   the finger and stop the scroll. gtabHeld() is read by drawGame, which looks again shortly. */
(()=>{const inRow=e=>!!(e.target&&e.target.closest&&e.target.closest('#sheet .gtabs'));
 addEventListener('touchstart',e=>{if(inRow(e)){S.gtabT=true;S.gtabAt=performance.now();}},{capture:true,passive:true});
 ['touchend','touchcancel'].forEach(k=>addEventListener(k,()=>{if(S.gtabT){S.gtabT=false;S.gtabAt=performance.now();}},{capture:true,passive:true}));
 addEventListener('scroll',e=>{if(e.target&&e.target.classList&&e.target.classList.contains('gtabs'))S.gtabAt=performance.now();},{capture:true,passive:true});})();
function gtabHeld(){return !!S.gtabT||performance.now()-(S.gtabAt||-1e9)<500;}
/* after every repaint: the underline, the row's own sideways scroll, and (live) the newest play's animation */
function gameAfterPaint(r){gameTabInd();pbpAfterPaint(r);if(document.querySelector('#sheet .bxsw'))segInd();}
/* ---- Play-by-play (football; ESPN drives and plays, display only). Stepping shows the strip as it stood after the chosen play
   (S.pbpStep = that play's id, null = live) and replays an illustration of the play from its type and yardage. The animations
   are illustrations only: ESPN has no player tracking, and the tab says so. Under prefers-reduced-motion nothing moves: the
   text and the ball spot still update. Nothing here is read by any buy/sell path. */
function pbpData(r){const p=((r||{}).detail||{}).pbp;return p&&Array.isArray(p.drives)?p:null;}
function pbpHas(r){const p=pbpData(r);return !!(p&&p.drives.some(d=>d&&Array.isArray(d.plays)&&d.plays.length));}
function pbpPlays(r){const out=[];let n=0;((pbpData(r)||{}).drives||[]).forEach(d=>((d&&d.plays)||[]).forEach(p=>{out.push({p,d,k:String(p.id||('#'+n)),n});n++;}));return out.slice(-250);}
function pbpIdx(list){if(S.pbpStep==null)return list.length-1;const i=list.findIndex(x=>x.k===S.pbpStep);return i<0?list.length-1:i;}
function pbpLiveNow(list){return S.pbpStep==null||!list.some(x=>x.k===S.pbpStep);}
const Q_LBL=['','1st','2nd','3rd','4th'];
function qShort(q){q=+q;return q>4?(q===5?'OT':(q-4)+'OT'):(Q_LBL[q]||'Q'+q);}
function qFull(q){q=+q;return q>4?'Overtime':(Q_LBL[q]||'Q'+q)+' Quarter';}
function pbpHtml(r){const pb=pbpData(r),list=pbpPlays(r);if(!pb||!list.length)return '';S.pbpOpen=S.pbpOpen||{};
 const i=pbpIdx(list),cur=list[i],live=pbpLiveNow(list),p=cur.p,b=(r.detail||{}).board||{};const open=(k,def)=>k in S.pbpOpen?S.pbpOpen[k]:def;
 const tint=x=>x.sc?' sc':x.to?' to':'';const keyOf=new Map(list.map(x=>[x.p,x.k]));
 const meta=[qShort(p.q)+(p.clk?' · '+p.clk:''),p.dn].filter(Boolean).join(' · ');
 const card=`<div class="pcard${tint(p)}" id="pbp-card"><div class="pch"><button type="button" class="pstep" data-step="prev" aria-label="Previous play" onclick="pbpStepBy(-1)"${i<=0?' disabled':''}>‹</button>
   <div class="pcm"><div class="pct">${esc(p.ty||'Play')}</div><div class="pcs">${live?'Latest play':'Replay · play '+(i+1)+' of '+list.length}${meta?' · '+esc(meta):''}</div></div>
   <button type="button" class="pstep" data-step="next" aria-label="Next play" onclick="pbpStepBy(1)"${i>=list.length-1?' disabled':''}>›</button></div>
  <div class="pctx">${esc(p.txt)}</div>
  <div class="pcf"><span>${list.length} play${list.length===1?'':'s'}${pb.cut>0?' (latest shown)':''}</span><button type="button" class="plive" onclick="pbpLive()"${live?' hidden':''}>Back to live</button></div></div>
  <div class="pnote">Illustrations only, no player tracking</div>`;
 const qs=[];pb.drives.forEach(d=>{let g=qs.find(x=>x.q===d.q);if(!g){g={q:d.q,ds:[]};qs.push(g);}g.ds.push(d);});
 qs.reverse().forEach(g=>g.ds.reverse());
 const chev='<svg class="chev" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
 const secs=qs.map(g=>{const qk='q'+g.q,qo=open(qk,g.ds.some(d=>d.plays.includes(p)));
  return `<div class="pqs"><button type="button" class="pq" data-k="${esc(qk)}" aria-expanded="${qo}" onclick="pbpTog(this)"><span>${esc(qFull(g.q))}</span>${chev}</button>
   ${qo?g.ds.map(d=>{const dk='d'+d.id,dop=open(dk,d.plays.includes(p));const tm=(b[d.side]||{});
    return `<button type="button" class="pdr${tint(d)}" data-k="${esc(dk)}" aria-expanded="${dop}" onclick="pbpTog(this)"><i class="pdot" style="background:${fcolor(tm.color,'var(--sub)')}"></i><b>${esc(d.team)}</b><span class="pres">${esc(d.res)}</span><span class="m psum">${esc(d.sum)}</span>${chev}</button>
     ${dop?`<div class="pps">${d.plays.slice().reverse().map(x=>{const k=keyOf.get(x)||'';return `<div class="pp${tint(x)}${x===p&&!live?' cur':''}" data-pid="${esc(k)}" onclick="pbpGo(this.dataset.pid)"><div class="ppm"><b>${esc(x.dn||'')}</b><span class="m">${esc(qShort(x.q))}${x.clk?' · '+esc(x.clk):''}</span></div><div class="ppt">${esc(x.txt)}</div></div>`;}).join('')}</div>`:''}`;}).join(''):''}</div>`;}).join('');
 return `<div class="pbp">${card}${secs}</div>`;}
function pbpTog(el){S.pbpOpen=S.pbpOpen||{};S.pbpOpen[el.dataset.k]=el.getAttribute('aria-expanded')!=='true';pbpRefresh('');}
function pbpStepBy(dl){const r=S.gameR,list=pbpPlays(r);if(!list.length)return;const i=pbpIdx(list),j=Math.max(0,Math.min(list.length-1,i+dl));if(j===i)return;S.pbpStep=j===list.length-1?null:list[j].k;pbpRefresh('play');}
function pbpGo(k){const list=pbpPlays(S.gameR),j=list.findIndex(x=>x.k===k);if(j<0||j===pbpIdx(list))return;S.pbpStep=j===list.length-1?null:list[j].k;pbpRefresh('play');}
function pbpLive(){S.pbpStep=null;pbpRefresh('slide');}
/* The strip as it stood after the stepped play (the ball spot, who has it, first-down line, red zone), as a detail block for fieldStrip().
   A play with no ball movement (timeout, end of quarter) keeps the spot of the nearest earlier play that had one. */
function gameStepDetail(r){const d=r.detail;if(!d||S.pbpStep==null)return d;const list=pbpPlays(r);let i=list.findIndex(x=>x.k===S.pbpStep);if(i<0)return d;const p=list[i].p;
 let j=i;while(j>=0&&(list[j].p.b==null||!pbpSide(list[j].p.bs)))j--;if(j<0)return d;const pb=list[j].p,side=pb.bs==='home'||pb.bs==='away'?pb.bs:'',abbr=(((d.board||{})[side])||{}).abbr||'';
 return Object.assign({},d,{drive:{teamAbbr:abbr,ballYardsToEndzone:pb.b,downDistanceText:pb.edd||''},
  situation:{distance:pb.edd?pb.ed:null,downDistanceText:pb.edd||'',possessionText:pb.ep||'',isRedZone:pb.b>0&&pb.b<=20,lastPlayText:p.txt,lastPlayType:p.ty,replay:true}});}
function pbpRefresh(mode){const r=S.gameR;if(!r)return;const st=document.querySelector('#sheet .fstrip');
 if(mode&&st){const tmp=document.createElement('div');tmp.innerHTML=fieldStrip(gameStepDetail(r),r.leg);const ns=tmp.firstElementChild;if(ns)st.replaceWith(ns);}
 const pan=document.querySelector('#sheet .gpanel[data-tab="pbp"]');if(pan&&!pan.hidden)pan.innerHTML=pbpHtml(r);
 let delay=0;if(mode==='play'){const list=pbpPlays(r);const x=list[pbpIdx(list)];if(x)delay=pbpFx(x.p);}
 if(mode)pbpSlide(delay);}
function pbpAfterPaint(r){const list=pbpPlays(r);
 if(S.gtabCur==='pbp'&&S.pbpStep==null&&list.length){const last=list[list.length-1];if(S.pbpSeen!=null&&S.pbpSeen!==last.k){pbpSlide(pbpFx(last.p));}else pbpSyncBall();S.pbpSeen=last.k;}
 else pbpSyncBall();}
function pbpSyncBall(){const b=document.querySelector('#sheet .fstrip .fball');S.pbpBall=b?parseFloat(b.style.left):null;}
/* slide the ball marker (and the possession arrow) from where it was to its new spot; a pass or kick waits for the flight */
function pbpSlide(delay){const st=document.querySelector('#sheet .fstrip'),ball=st&&st.querySelector('.fball');if(!ball){S.pbpBall=null;return;}const to=ball.style.left,from=S.pbpBall;S.pbpBall=parseFloat(to);
 if(matchMedia('(prefers-reduced-motion: reduce)').matches||from==null||isNaN(from)||Math.abs(from-parseFloat(to))<.05)return;
 const els=[ball,st.querySelector('.fdir')].filter(Boolean);els.forEach(e=>{e.style.transition='none';e.style.left=from+'%';});void st.offsetWidth;
 els.forEach(e=>{e.style.transition='';e.style.transitionDelay=(delay||0)+'ms';e.style.left=to;});}
/* ---- illustrations: what kind of play was it, and a small effect on the field for it */
function fabs(side,ytz){return side==='home'?ytz:100-ytz;}      // yards from the LEFT goal line = % across .grass (home attacks left, away right), the same as fieldStrip
function pbpSide(x){return x==='home'||x==='away';}      // a ball move is only drawn when the server knew whose end zone it is
function pbpKind(p){const t=(p.ty||'').toLowerCase(),turn=!!p.to&&!/penalty/.test(t);
 const k={mv:'dflt',td:/touchdown/.test(t)||(p.sc&&p.b===0&&!/field goal|safety|extra point/.test(t)),turn,fg:null,safety:/safety/.test(t)};
 if(p.a==null||p.b==null||!pbpSide(p.as)||!pbpSide(p.bs))k.mv='none';
 else if(p.pen||/penalty/.test(t))k.mv='pen';
 else if(/field goal/.test(t)){k.mv='kick';k.fg=p.sc?'good':'no';}
 else if(/kickoff|punt|extra point/.test(t))k.mv='kick';
 else if(/sack/.test(t))k.mv='sack';
 else if(/pass|interception/.test(t))k.mv='pass';
 else if(/rush|run/.test(t)||/scramble/.test((p.txt||'').toLowerCase()))k.mv='run';
 return k;}
function pbpFx(p){if(matchMedia('(prefers-reduced-motion: reduce)').matches)return 0;const grass=document.querySelector('#sheet .fstrip .grass');if(!grass)return 0;
 const k=pbpKind(p);if(k.mv==='none')return 0;
 const a=fabs(p.as,p.a),b=fabs(p.bs,p.b),off=p.as==='home'?-1:1;
 const add=(cls,css,txt)=>{const e=document.createElement('div');e.className=cls;Object.assign(e.style,css||{});if(txt)e.textContent=txt;grass.appendChild(e);setTimeout(()=>e.remove(),2000);return e;};
 const tag=(txt,tone)=>add('ftag '+(tone||''),{},txt);
 const fly=(from,to,ah,dur)=>{const e=add('fproj',{left:from+'%'});e.style.setProperty('--ah',ah+'px');e.style.setProperty('--dur',dur+'ms');e.innerHTML='<b></b>';void e.offsetWidth;e.style.left=to+'%';return dur;};
 const trail=(from,to,red)=>{add('ftrail'+(red?' red':''),{left:Math.min(from,to)+'%',width:Math.abs(to-from)+'%',transformOrigin:to>=from?'left center':'right center'});};
 const goal=off>0?100:0;let delay=0;
 if(k.mv==='pass'){const inc=/incomplet/.test((p.ty||'').toLowerCase())||Math.abs(b-a)<.1;const to=k.turn?a+off*15:(inc?a+off*11:b);
  delay=fly(a,to,Math.min(26,9+Math.abs(to-a)*.5),460+Math.min(320,Math.abs(to-a)*6));}
 else if(k.mv==='kick'){const to=k.fg?goal:b;delay=fly(a,to,Math.min(36,16+Math.abs(to-a)*.3),720+Math.min(520,Math.abs(to-a)*8));}
 else if(k.mv==='run')trail(a,b,false);
 else if(k.mv==='sack'){trail(a,b,true);tag('SACK','bad');}
 else if(k.mv==='pen'){add('fflag',{left:a+'%'},'🚩');}
 if(k.td){const ez=document.querySelector('#sheet .fstrip .ez.'+(off>0?'r':'l'));if(ez){ez.classList.add('tdflash');setTimeout(()=>ez.classList.remove('tdflash'),1400);}tag('TOUCHDOWN','good');}
 else if(k.fg==='good'){tag('FIELD GOAL','good');}
 else if(k.fg==='no'){tag('NO GOOD','bad');}
 else if(k.safety){tag('SAFETY','bad');}
 if(k.turn){const bl=document.querySelector('#sheet .fstrip .fball');if(bl){bl.classList.add('turn');setTimeout(()=>bl.classList.remove('turn'),1700);}tag('TURNOVER','bad');}
 return delay;}
/* ---- Slice 3 tabs (football): box score, team stats, injury report, last 5 games, season leaders. Drawn only from the game
   answer's detail block (ESPN feeds, display only). A side the feed has nothing for says so in plain words instead of guessing.
   Team colours are accents only (our own art; no logos). Numbers roll and share bars slide when the game changes them. */
function gd(r){return (r||{}).detail||{};}
function gTeams(r){const b=gd(r).board||{};return {away:b.away||{},home:b.home||{}};}
/* a team colour that reads on the page: the primary, else the alternate, when it is neither near-black nor near-white */
function tcol(t,fb){const ok=c=>{c=fcolor(c,'');if(!c)return '';const n=parseInt(c.slice(1),16),L=(.2126*((n>>16)&255)+.7152*((n>>8)&255)+.0722*(n&255))/255;return L>.08&&L<.9?c:'';};
 const c=ok(t.color)||ok(t.alt);return c?`color-mix(in srgb,${c},#fff var(--tmix,0%))`:fb;}
function tcols(r){const T=gTeams(r);const a=tcol(T.away,'var(--yes)');let h=tcol(T.home,'var(--no)');if(h===a)h='var(--sub)';return {a,h};}
function tmName(T,s){return T[s].name||T[s].abbr||(s==='home'?'Home':'Away');}
function tmHead(r){const T=gTeams(r),c=tcols(r);
 return `<div class="h2h"><b><i class="tdot" style="background:${c.a}"></i>${esc(T.away.abbr||'Away')}</b><b>${esc(T.home.abbr||'Home')}<i class="tdot" style="background:${c.h}"></i></b></div>`;}
/* a head-to-head share bar; even and quiet when there is nothing to compare */
function sbar(key,an,hn,c,lo){const ok=an!=null&&hn!=null&&an>=0&&hn>=0&&an+hn>0;const tie=ok&&an===hn;
 /* a lower-is-better row (turnovers, sacks, penalties...) gives the longer bar to the side with the FEWER: its share is the other side's count */
 const p=ok&&!tie?Math.max(4,Math.min(96,(lo?hn:an)/(an+hn)*100)):50;
 return `<div class="h2bar${ok&&!tie?'':' even'}" role="img" aria-label="${ok&&!tie?Math.round(p)+' to '+(100-Math.round(p)):'no comparison'}"><i data-bar="${esc(key)}:a" style="width:${p.toFixed(1)}%;background:${c.a}"></i><i data-bar="${esc(key)}:h" style="width:${(100-p).toFixed(1)}%;background:${c.h}"></i></div>`;}
/* 'Nov 15' from a plain date (as given) or a UTC kickoff time (in this phone's own time zone, so a night game keeps its day) */
function gdate(d){d=d||'';const day=/^\d{4}-\d{2}-\d{2}$/.test(d),at=/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?Z$/.test(d);if(!day&&!at)return '';
 const x=new Date(day?d+'T12:00:00Z':d);return isNaN(x)?'':x.toLocaleDateString('en-US',day?{month:'short',day:'numeric',timeZone:'UTC'}:{month:'short',day:'numeric'});}
function numAttr(k,v,f){return /^\d{1,6}$/.test(String(v))?` data-num="${esc(k)}" data-v="${+v}" data-f="${f||'int'}"`:'';}
/* a freshly opened tab rises in and its bars grow from nothing (refreshes only roll what changed) */
function gtabIn(p){if(!p)return;rollNums(p);if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 p.querySelectorAll('.tsr,.ldr,.l5r,.injr,.gtw').forEach((e,i)=>e.style.setProperty('--i',Math.min(i,16)));
 p.classList.add('gin');clearTimeout(S.ginT);S.ginT=setTimeout(()=>p.classList.remove('gin'),1100);}
/* Box score: a team switch, then that team's tables (passing, rushing, receiving, then defence and kicking). */
function boxHas(r){const b=gd(r).box;return !!(b&&((b.away||[]).length||(b.home||[]).length));}
function boxSide(r){const b=gd(r).box||{};const s=S.boxSide;return (s==='away'||s==='home')&&(b[s]||[]).length?s:((b.away||[]).length?'away':'home');}
function boxHtml(r){const b=gd(r).box||{},T=gTeams(r),c=tcols(r),side=boxSide(r);
 const sw=`<div class="seg bxsw" data-k="boxsw" role="group" aria-label="Team">${['away','home'].map(s=>`<button type="button" class="${s===side?'on':''}" aria-pressed="${s===side}" data-side="${s}" onclick="boxPick('${s}')"><i class="tdot" style="background:${s==='away'?c.a:c.h}"></i>${esc(T[s].abbr||tmName(T,s))}</button>`).join('')}</div>`;
 const td=v=>`<td>${esc(v==null||v===''?'–':v)}</td>`;
 const tables=(b[side]||[]).map(g=>`<h4 class="ghead">${esc(g.t)}</h4><div class="gtw"><table class="gstat"><thead><tr><th>Player</th>${(g.c||[]).map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>
  ${(g.r||[]).map(p=>`<tr><td><div><span class="pn" title="${esc(p.n)}">${esc(p.n)}</span>${p.j?`<span class="jn">#${esc(p.j)}</span>`:''}</div></td>${(p.s||[]).map(td).join('')}</tr>`).join('')}
  ${(g.tot||[]).some(v=>v)?`<tr class="tot"><td>Team</td>${g.tot.map(td).join('')}</tr>`:''}</tbody></table></div>`).join('');
 return `<div class="gtabx box">${sw}${tables||'<p class="gempty">No stats for this team yet.</p>'}<p class="pnote">ESPN's box score. It updates as the game goes.</p></div>`;}
function boxPick(s){if(s!=='away'&&s!=='home')return;S.boxSide=s;
 const p=document.querySelector('#sheet .gpanel[data-tab=box]');if(!p||!S.gameR)return;p.innerHTML=boxHtml(S.gameR);segInd();gtabIn(p);}
/* Team stats: head to head, the label in the middle, a share bar under each row. */
function tsHas(r){const t=gd(r).tstats;return Array.isArray(t)&&t.length>0;}
/* the leading side of a row (its number is emphasised and the other dims); a tie leaves both plain. Lower-is-better rows are marked by the Mac (x.lo) and led by the side with fewer. */
function tsLead(x,s){return x.ld===s?'lead':x.ld?'lag':'';}
function tsHtml(r){const t=S.gameOpen,c=tcols(r);
 const rows=gd(r).tstats.map(x=>`<div class="tsr${x.lo?' lo':''}"><div class="tsv"><b class="${tsLead(x,'a')}"${numAttr('tsa:'+t+':'+x.k,x.a)}>${esc(x.a)}</b><span>${esc(x.l)}${x.lo?'<small class="lob">fewer is better</small>':''}</span><b class="${tsLead(x,'h')}"${numAttr('tsh:'+t+':'+x.k,x.h)}>${esc(x.h)}</b></div>${sbar('ts:'+t+':'+x.k,x.an,x.hn,c,x.lo)}</div>`).join('');
 return `<div class="gtabx">${tmHead(r)}${rows}<p class="pnote">This game so far, from ESPN. The down and red-zone bars compare success rates. Where fewer is better, the side with fewer leads.</p></div>`;}
/* Injury report: both teams, worst first, with ESPN's guess at a return date. */
/* The tab shows when ESPN sent injuries, or when the rest of the summary (box score, team stats) loaded without them. A side with its own list from ESPN is a real report (an empty list means
   nobody is hurt); a side ESPN sent nothing for is "not available right now", never "no injuries". */
function injHas(r){return !!gd(r).inj||boxHas(r)||tsHas(r);}
function injCls(s){s=(s||'').toLowerCase();return /out|reserve|suspen/.test(s)?'bad':/doubt/.test(s)?'warn':/question/.test(s)?'q':'';}
function injHtml(r){const i=gd(r).inj||{},T=gTeams(r),c=tcols(r);
 const sec=s=>{const known=Array.isArray(i[s]),L=known?i[s]:[];return `<div><h4 class="ghead"><i class="tdot" style="background:${s==='away'?c.a:c.h}"></i>${esc(tmName(T,s))}</h4>${!known?'<p class="gempty">Injury report isn’t available right now.</p>':L.length?L.map(p=>`<div class="injr"><div class="injn"><b>${esc(p.n)}</b><span class="m">${esc([p.pos,p.j?'#'+p.j:''].filter(Boolean).join(' · '))}</span></div>
  <div class="injw m">${esc(p.ty||'Not specified')}${p.ret&&gdate(p.ret)?' · back around '+esc(gdate(p.ret)):''}</div><span class="ist ${injCls(p.st)}">${esc(p.st)}</span></div>`).join(''):'<p class="gempty">No injuries reported.</p>'}</div>`;};
 return `<div class="gtabx"><div class="injgrid">${sec('away')}${sec('home')}</div><p class="pnote">ESPN's injury report. Return dates are ESPN's estimate.</p></div>`;}
/* Last 5 games: each team's five most recent finished games, newest first, and its record. */
function gskel(n){return Array.from({length:n||3},()=>'<div class="gskr" aria-hidden="true"><i class="skel"></i><i class="skel"></i></div>').join('');}
function l5Has(r){const l=gd(r).last5;return !!(l&&(l.away||l.home))||!!gd(r).gxp;}
function l5Html(r){const l=gd(r).last5||{},T=gTeams(r),c=tcols(r);
 const sec=s=>{const x=l[s];const rec=(x&&x.rec)||T[s].record||'';const g=x&&Array.isArray(x.g)?x.g:[];
  const body=!x?(gd(r).gxp?`<div aria-busy="true">${gskel(5)}</div>`:'<p class="gempty">Recent results aren’t available right now.</p>'):x.na?'<p class="gempty">Recent results aren’t available right now.</p>':!g.length?'<p class="gempty">No finished games yet this season.</p>':
   g.map(v=>`<div class="l5r"><span class="wl ${v.w==='W'?'w':v.w==='L'?'l':'t'}">${esc(v.w)}</span><span class="l5o"><span class="m">${esc(v.at)}</span> ${esc(v.opp)}</span><span class="l5s">${+v.me}–${+v.them}</span><span class="m l5d">${esc(gdate(v.d))}</span></div>`).join('');
  const form=g.length?`<span class="form" aria-hidden="true">${g.slice().reverse().map(v=>`<i class="${v.w==='W'?'w':v.w==='L'?'l':''}"></i>`).join('')}</span>`:'';
  return `<div><h4 class="ghead"><i class="tdot" style="background:${s==='away'?c.a:c.h}"></i>${esc(tmName(T,s))}${rec?`&nbsp;<span class="m">(${esc(rec)})</span>`:''}${form}</h4>${body}</div>`;};
 return `<div class="gtabx"><div class="l5grid">${sec('away')}${sec('home')}</div><p class="pnote">Scores show this team first. From ESPN's schedule.</p></div>`;}
/* Season leaders: the top passer, rusher and receiver on each side, head to head, with a share bar. */
function ldHas(r){const l=gd(r).leaders;return (Array.isArray(l)&&l.length>0)||!!gd(r).gxp;}
function ldHtml(r){const t=S.gameOpen,c=tcols(r);
 if(!Array.isArray(gd(r).leaders)||!gd(r).leaders.length)return `<div class="gtabx" aria-busy="true">${tmHead(r)}${gskel(3)}<p class="pnote">Loading season leaders…</p></div>`;
 const side=(x,s,k)=>x?`<div class="ldp ${s}"><b class="ldv" data-num="ld:${esc(t)}:${esc(k)}:${s}" data-v="${+x.v||0}" data-f="cint">${esc(Math.round(+x.v||0).toLocaleString('en-US'))}</b><div class="ldn">${x.n?esc(x.n):'—'}${x.j?`<span class="jn">#${esc(x.j)}</span>`:''}</div><div class="m ldl">${esc(x.line||'')}</div></div>`
  :`<div class="ldp ${s}"><b class="ldv">–</b><div class="m ldl">Not available</div></div>`;
 const rows=gd(r).leaders.map(x=>`<div class="ldr"><div class="ldc">${esc(x.l)}</div><div class="ldg">${side(x.away,'a',x.k)}${side(x.home,'h',x.k)}</div>${sbar('ld:'+t+':'+x.k,x.away?+x.away.v:null,x.home?+x.home.v:null,c)}</div>`).join('');
 return `<div class="gtabx">${tmHead(r)}${rows}<p class="pnote">Season totals from ESPN.</p></div>`;}
/* The win-chance chart starts at kickoff (issue #486): the Mac records the price for hours before a game, and drawing that
   flat stretch squeezed the real game into the last sliver. t0 = the game's start from the Mac (r.start: sportsbook or
   score-feed time, never an estimate), else the first in-play sample, else the first score change. Samples before t0 (and
   any still marked pre-game) are not drawn. A game that has not started (start in the future, or no start and no in-play
   data) gets pre:true and a "kicks off at" note instead of a line. Looking back covers the played game only. */
function winRange(r,st){const l=(r&&r.leg)||{},ticks=((st&&st.ticks)||[]).filter(x=>x.chance!=null),plays=(st&&st.plays)||[];
 let t0=+(r&&r.start)>0?+r.start:null;
 if(t0==null){const k=ticks.find(x=>x.state==='live');t0=k?k.ts:plays.length?plays[0].ts:null;}
 const pre=t0!=null?Date.now()/1000<t0:l.state==='pre';
 const pts=pre?[]:ticks.filter(x=>(t0==null||x.ts>=t0)&&x.state!=='pre').map(x=>[x.ts,x.chance]);   // nothing to anchor on: every in-game sample, as before
 return {t0,pre,pts,starts:l.starts||''};}
function winChart(pts,plays,o){o=o||{};const tl0=t=>new Date(t*1000).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
 if(o.pre)return `<div class="m" style="padding:18px 4px">${o.t0!=null?'Starts at '+tl0(o.t0)+'. ':o.starts?'Starts '+esc(o.starts)+'. ':''}The win-chance line fills in once play begins.</div>`;
 if(!pts||pts.length<2)return '<div class="m" style="padding:18px 4px">The win-chance line fills in as the Mac watches this game.</div>';
 const W=Math.round(Math.max(340,Math.min(820,window.innerWidth-70))),H=170,pl=36,iw=W-pl-8,ih=H-30;const t0=o.t0!=null?Math.min(o.t0,pts[0][0]):pts[0][0],t1=pts[pts.length-1][0];
 const X=t=>pl+(t-t0)/Math.max(1,t1-t0)*iw,Y=v=>8+ih-v*ih;const d=pts.map((p,i)=>`${i?'L':'M'}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join('');
 const last=pts[pts.length-1][1];const col=last>=.5?'var(--yes)':'var(--no)';const tl=t=>new Date(t*1000).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
 S.scr=S.scr||{};S.scr.win={n:pts.length,at:f=>{const t=t0+(f*W-pl)/iw*(t1-t0);let i=0,b=Infinity;pts.forEach((p,j)=>{const dd=Math.abs(p[0]-t);if(dd<b){b=dd;i=j;}});return i;},
  x:i=>X(pts[i][0])/W*100,y:i=>Y(pts[i][1])/H*100,lab:i=>tl(pts[i][0])+' · '+pct(pts[i][1])};
 return `<div class="key"><span><i style="background:${col}"></i>Chance to win</span><span><i style="background:var(--sub);height:8px;width:2px"></i>Score change</span><span class="m">Drag to look back</span></div><div class="scrub" data-scrub="win"><span class="sread"></span><i class="scrl"></i><i class="scrd" style="background:${col}"></i><svg viewBox="0 0 ${W} ${H}">
  ${[0,.25,.5,.75,1].map(v=>`<line x1="${pl}" x2="${W-8}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)" ${v===.5?'stroke-dasharray="4 4"':''}/><text x="${pl-6}" y="${Y(v)+4}" font-size="11" text-anchor="end" fill="var(--mute)">${v*100}%</text>`).join('')}
  ${(plays||[]).slice(1).filter(p=>p.ts>=t0).map(p=>`<line x1="${X(p.ts)}" x2="${X(p.ts)}" y1="8" y2="${8+ih}" stroke="var(--sub)" stroke-width="1" opacity=".35"/>`).join('')}
  <path d="${d} L${X(t1)} ${8+ih} L${pl} ${8+ih}Z" fill="${col}" opacity=".08"/><path d="${d}" fill="none" stroke="${col}" stroke-width="2.2" stroke-linejoin="round"/>
  <text x="${pl}" y="${H-4}" font-size="11" fill="var(--mute)">${tl(t0)}</text><text x="${W-8}" y="${H-4}" font-size="11" fill="var(--mute)" text-anchor="end">${tl(t1)}</text></svg></div>`;}
/* Any chart you can drag a finger along (the game's chance line, the Results profit bars): same feel as the Live hero
   chart. A spec in S.scr[name] says how many points there are, which one is under the finger, and where to draw the
   line, dot and readout; every new point ticks a haptic. A short tap (no drag) can open the point (o.tap). Refreshes
   wait while a finger is down (S.scrub). */
function wireScrubs(root){(root||document).querySelectorAll('[data-scrub]').forEach(el=>{if(el._wired)return;el._wired=1;let idx=-1,on=false,x0=0,moved=false;
 const spec=()=>(S.scr||{})[el.dataset.scrub];
 const pick=e=>{const o=spec(),r=el.getBoundingClientRect();return o?o.at(Math.max(0,Math.min(.9999,(e.clientX-r.left)/Math.max(1,r.width)))):-1;};
 const show=i=>{const o=spec();if(!o||i===idx||i<0||i>=o.n)return;idx=i;
  if(o.x){const fx=o.x(i),l=el.querySelector('.scrl'),d=el.querySelector('.scrd'),rd=el.querySelector('.sread');if(l)l.style.left=fx+'%';if(d){d.style.left=fx+'%';d.style.top=o.y(i)+'%';}
   if(rd){rd.textContent=o.lab(i);rd.style.left=Math.max(14,Math.min(86,fx))+'%';}}
  if(o.show)o.show(i,el);hap('selection');};
 el.addEventListener('pointerdown',e=>{if(e.button)return;on=true;moved=false;x0=e.clientX;S.scrub=true;el.classList.add('on');idx=-1;show(pick(e));try{el.setPointerCapture(e.pointerId)}catch(x){}});
 el.addEventListener('pointermove',e=>{if(!on)return;if(Math.abs(e.clientX-x0)>6)moved=true;show(pick(e));});
 const end=e=>{if(!on)return;on=false;S.scrub=false;el.classList.remove('on');const i=idx,o=spec();idx=-1;if(o&&o.end)o.end(el);
  if(e.type==='pointerup'&&!moved&&o&&o.tap&&i>=0)o.tap(i);if(S.liveDirty){S.liveDirty=false;if(S.view==='live')renderLive();}if(S.resDirty){S.resDirty=false;if(S.view==='results')renderResults();}};
 ['pointerup','pointercancel','lostpointercapture'].forEach(k=>el.addEventListener(k,end));});}
