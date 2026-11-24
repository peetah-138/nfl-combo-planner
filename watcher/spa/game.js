// ---------------- one game, live
async function openGame(t){if(!t)return;S.comboOpen=null;S.ideaOpen=null;S.gameOpen=t;S.gxWant=false;clearTimeout(S.gxT);S.gameSig=null;S.gtab=null;S.gtabPos=null;S.gtabScroll=null;S.pbpStep=null;S.pbpOpen={};S.pbpSeen=null;S.pbpBall=null;pushOpen('Game');await drawGame();}
// The open game sheet redraws on its own: on every Mac tick, on a score event for this game, and on a slow timer if the
// live link is down. It only repaints when something changed (and keeps its scroll place), and the clock below it counts
// down between updates while it is running. Only the first draw waits for the slide-in to finish.
function gxAgain(){if(S.gxWant&&S.gameOpen&&$('#modal').classList.contains('on')){clearTimeout(S.gxT);S.gxT=setTimeout(drawGame,2500);}}   // team data still loading: look again soon, however this draw ends
async function drawGame(){const t=S.gameOpen;if(!t||!$('#modal').classList.contains('on'))return;
 if(S.gameBusy||S.scrub){gxAgain();return;}   // a finger on the chart holds the page still
 if(typeof gtabHeld==='function'&&gtabHeld()){clearTimeout(S.gtabRT);S.gtabRT=setTimeout(drawGame,700);return;}   // #218: a finger on the tab row too
 const sh=$('#sheet');S.gameBusy=true;S.gameAt=Date.now();
 try{const [r]=await Promise.all([api('/app/api/game?t='+encodeURIComponent(t)).catch(()=>null),S.gameSig?null:pushWait()]);if(S.gameOpen!==t)return;
  if(!r||!r.leg){if(!S.gameSig)pushFill('<h3>Game not found</h3><p>It may have finished and settled.</p>','Game');gxAgain();return;}
  frSet('G',r.fresh);clkNote(t,r.leg);
  S.gxWant=!!(r.detail&&r.detail.gxp);clearTimeout(S.gxT);gxAgain();   // last 5 / season leaders still being fetched: look again soon, quietly
  const sig=JSON.stringify([r.leg,r.combos,r.story,r.whatif,r.detail,r.buy]);
  if(sig===S.gameSig&&sh.querySelector('.board2')){frTick();return;}
  S.gameSig=sig;const top=sh.scrollTop;paintGame(r);sh.scrollTop=top;frTick();
 }finally{S.gameBusy=false;}}
const CLK_SPORTS=['nba','ncaamb','ncaawb','nhl','ahl','euroleague'];
function clkNote(t,l){S.clk=S.clk||{};const sc=l.sc,m=sc&&l.state==='live'&&CLK_SPORTS.includes(l.sport)?/^(.*?)\s*(\d{1,2}):(\d{2})$/.exec(sc.detail||''):null;
 if(!m){delete S.clk[t];return;}
 const lab=m[1].trim(),secs=+m[2]*60+ +m[3],p=S.clk[t],now=Date.now();
 if(p&&p.lab===lab&&secs===p.srv){if(p.run&&now-p.recv<25000)return;S.clk[t]={lab,srv:secs,secs,recv:now,run:false};return;}
 S.clk[t]={lab,srv:secs,secs,recv:now,run:!!(p&&p.lab===lab&&secs<p.srv)};}
function clkTick(){document.querySelectorAll('[data-clk]').forEach(e=>{const c=(S.clk||{})[e.dataset.clk];if(!c)return;const v=c.run?Math.max(0,c.secs-Math.floor((Date.now()-c.recv)/1000)):c.secs;
 const t=c.lab+' '+Math.floor(v/60)+':'+String(v%60).padStart(2,'0');if(e.textContent!==t)e.textContent=t;});}
function paintGame(r){const t=S.gameOpen;S.gameR=r;{const gb=document.querySelector('#sheet .gtabs');if(gb)S.gtabScroll=gb.scrollLeft;}
 const l=r.leg,sc=l.sc,st=r.story||{ticks:[],plays:[]};const ch=l.live!=null?l.live:l.chance;const lc=legCls(l);
 const pts=st.ticks.filter(x=>x.chance!=null).map(x=>[x.ts,x.chance]);
 const plays=st.plays.slice().reverse();
 const ov=`<div class="dkpis"><div><span>${l.kind==='spread'?'Chance it covers':l.kind==='total'?'Chance it hits':esc(short(l.name))+' to win'}</span><b class="${ch>=.5?'up':'down'}" data-num="gc:${t}" data-v="${ch}" data-f="pct">${pct(ch)}</b></div><div><span>Your bets on it</span><b>${r.combos.length}</b></div><div><span>Riding on it</span><b>${money(r.combos.reduce((a,c)=>a+c.pays,0))}</b></div><div><span>Score changes</span><b>${Math.max(0,st.plays.length-1)}</b></div></div>
  <div class="chartbox">${winChart(pts,st.plays)}</div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px">
   <div><h2 style="margin:0 0 6px">Scoring</h2>${plays.length>1?plays.slice(0,-1).map((p,i)=>{const prev=plays[i+1];const mine=p.me>prev.me;return `<div class="moment"><span class="k" style="color:${mine?'var(--yes)':'var(--no)'}">${mine?'▲':'▼'}</span><span>${mine?esc(short(l.name)):esc(short(l.opp||'Them'))} score · <b>${p.me}–${p.opp}</b> <span class="m">${esc(p.detail||'')}</span></span><time>${ago2(p.ts)}</time></div>`;}).join(''):'<div class="m">No score changes recorded yet.</div>'}</div>
   <div><h2 style="margin:0 0 6px">Your bets on this game</h2>${r.combos.map(c=>`<div class="moment" ${c.single?'':`style="cursor:pointer" data-t="${esc(c.t)}" onclick="openCombo(this.dataset.t)"`}><span class="k">${c.single?'📏':'🎯'}</span><span><b>${esc(c.single?betPlain(c):c.label)}</b>${(c.parts||[]).length>1&&(c.parts||[]).some(q=>q.plain)?`<span class="bparts">${c.parts.map(q=>esc(q.plain||'')+(q.matchup?' ('+esc(q.matchup)+')':'')).join(' + ')}</span>`:''} <span class="m">${c.single?(c.how?esc(c.how)+' · ':'')+pct(c.p)+' chance':c.legs+' picks · '+pct(c.p)+' to hit'}</span></span><b>${money(c.pays)}</b>${c.single&&typeof ssOpen==='function'?`<button class="btn yes sm" data-sss="${esc(c.t)}" onclick="event.stopPropagation();ssOpen('${c.t}')">Sell</button>`:''}</div>`).join('')||'<div class="m">None pending.</div>'}
   ${r.whatif?`<h2 style="margin:16px 0 6px">What if…</h2><div class="whatif"><div class="wi up"><span>${esc(short(l.name))} get the next ${esc(r.whatif.unit)}</span><b>${pct(r.whatif.up)}</b><small>to win${r.combos[0]&&r.combos[0].if_up!=null?` · ${esc(r.combos[0].label)} worth ≈${money(r.combos[0].if_up)}`:''}</small></div>
    <div class="wi down"><span>${esc(short(l.opp||'They'))} get it</span><b>${pct(r.whatif.down)}</b><small>to win${r.combos[0]&&r.combos[0].if_down!=null?` · ≈${money(r.combos[0].if_down)}`:''}</small></div></div>
    ${r.combos[0]&&r.combos[0].now!=null?`<div class="m" style="font-size:12px;margin-top:6px">Worth ≈${money(r.combos[0].now)} now. Estimates use Kalshi's usual cash-out discount.</div>`:''}`:''}</div></div>
  ${l.url?`<div class="row" style="margin-top:14px"><a class="btn" href="${esc(l.url)}" target="_blank">Kalshi game page ↗</a></div>`:''}`;
 pushFill(`<div class="dhead"><div><div class="m" style="font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase">${esc(SPN[l.sport]||l.sport)}${(l.state==='live'||l.on)&&l.phase!=='probably_over'&&l.phase!=='waiting'?' · <span style="color:var(--live)">LIVE</span>':''} <span class="fresh" data-fr="G" style="margin-left:8px">${frTxt('G')}</span></div>
   ${l.matchup&&l.found!==false?`<h3 style="font-size:20px">${ICON[l.sport]||''} ${l.kind==='total'||l.kind==='spread'?'Game: ':''}${esc(l.matchup)}</h3><div class="bwhat">Your bet: ${esc(betPlain(l))}</div>`:l.matchup?`<h3 style="font-size:20px">${ICON[l.sport]||''} ${esc(betPlain(l))}</h3><div class="bwhat">${betWhere(l)}</div>`:`<h3 style="font-size:20px">${ICON[l.sport]||''} ${esc(l.name)}${l.opp?` <span class="m" style="font-weight:500">vs ${esc(l.opp)}</span>`:''}</h3>`}</div></div>
  <div class="board2 ${lc}">${sc?`<div class="tm2"><div><span>${esc(sc.abbr)}${scbPoss(r.detail,sc.abbr)}</span>${scbTimeouts(r.detail,sc.abbr)}</div><b data-num="sm:${t}" data-v="${sc.me}" data-f="int">${sc.me}</b></div><div class="mid2"><div class="clk"${(S.clk||{})[t]?` data-clk="${esc(t)}"`:''}>${(l.state==='live'||l.on)&&l.phase!=='probably_over'&&l.phase!=='waiting'?'<span class="live-dot"></span>':''}${esc(sc.detail||'')}</div><div class="m">${(l.state==='live'||l.on)&&l.phase!=='probably_over'&&l.phase!=='waiting'?'in progress':''}${l.src==='kalshi'?'<div style="font-size:10.5px;opacity:.75">score from Kalshi</div>':''}</div></div><div class="tm2 r"><b data-num="so:${t}" data-v="${sc.opp}" data-f="int">${sc.opp}</b><div><span>${scbPoss(r.detail,sc.opp_abbr)}${esc(sc.opp_abbr)}</span>${scbTimeouts(r.detail,sc.opp_abbr)}</div></div>`:
   `<div class="mid2" style="grid-column:1/-1"><div class="clk">${esc(l.note||l.starts||'Not started')}</div></div>`}</div>
  ${fieldStrip(gameStepDetail(r),l)}
  ${gameTabsHtml(r,ov)}${gameBuyBar(r)}`,l.matchup&&l.found!==false?l.matchup:l.opp?short(l.name)+' vs '+short(l.opp):l.name);gameAfterPaint(r);}
/* The live field strip (football only, display only): our own art from ESPN's team colours. A 100-yard field with the
   two end zones tinted, a yard ruler (G 10 20 30 40 50 40 30 20 10 G), a ball at the line of scrimmage, a possession
   arrow pointing the way the offence is driving, a yellow first-down line and red-zone shading inside the 20. The ball
   slides to the new spot when the play changes (CSS transition; prefers-reduced-motion respected). Nothing here is read
   by any buy/sell path, and a bad or missing feed just returns '' so the page still works. */
/* A team colour, safe to drop into an inline style: a 6-hex-digit colour (with or without a leading #) becomes
   #rrggbb; anything else (empty, a name, something odd in the feed) falls back to the given CSS variable. The rest
   of the strip escapes its text with esc(); colours are the one place a raw feed value reaches a style attribute. */
/* The game page's pinned buy buttons (#113): each team's Kalshi price now as a chance and what $1 turns into after the
   fee ("IND · 24% · 3.96x"). A tap opens the buy sheet for that side, which prices it afresh; nothing is bought here. */
function gameBuyBar(r){const b=((r&&r.buy)||[]).filter(s=>/^[A-Z0-9._-]+$/.test(s.t||''));if(b.length<2)return '';const sp=(r.leg||{}).sport||'';
 return `<div class="gbuy" role="group" aria-label="Buy a team straight">${b.map(s=>`<button type="button" data-t="${esc(s.t)}" onclick="sbOpen('${esc(s.t)}','${/^[a-z0-9_]+$/.test(sp)?sp:''}')"><b>${esc(short(s.name)||s.t)}</b><small>${Math.round(s.ask*100)}% · ${(+s.mult).toFixed(2)}x</small></button>`).join('')}</div>`;}
function fcolor(c,fb){c=(c||'').replace(/^#/,'');return /^[0-9a-f]{6}$/i.test(c)?'#'+c:fb;}
function fieldStrip(d,l){if(!d)return '';const b=d.board||{},sit=d.situation||{},dr=d.drive||{};
 const home=b.home||{},away=b.away||{};const hc=fcolor(home.color,'var(--no)'),ac=fcolor(away.color,'var(--yes)');
 // Where is the ball? Prefer the drive's yards-to-end-zone; fall back to the situation's yardLine (0 own goal → 100 foe).
 let ytz=dr.ballYardsToEndzone;if(ytz==null&&sit.yardLine!=null)ytz=100-sit.yardLine;
 // Who has it, and which way do they drive? Away attacks right (home's zone), home attacks left (away's zone).
 const offAbbr=possTeam(d);                        // '' when nobody is known to have it (never guessed from the ball spot)
 const homeHas=!!offAbbr&&!!home.abbr&&offAbbr===home.abbr.toUpperCase();
 const haveBall=ytz!=null;
 // Field goes 0..100 left→right in the 100-yard playing area. Everything inside .grass (ball, arrow, ticks, first-down line,
 // red zone) is positioned in % of the GRASS box, which already sits between the two end zones, so a spot at N yards from the
 // left goal line is simply left:N%. The ruler lives in .fld (the whole strip), so it keeps its own end-zone inset below.
 const EZ=100/12,play=100-2*EZ;
 // Line of scrimmage as a % of the whole strip. For the away offence (driving right) distance from left goal = 100-ytz.
 let losYd=homeHas?ytz:(100-ytz);                 // yards from the LEFT goal line (0..100)
 let losPct=haveBall?Math.max(0,Math.min(100,losYd)):50;
 // First-down line: `distance` yards further toward the offence's target end zone.
 const dist=(sit.distance!=null)?sit.distance:null;
 let fdYd=dist!=null?(homeHas?losYd-dist:losYd+dist):null;
 let fdPct=fdYd!=null?Math.max(0,Math.min(100,fdYd)):null;
 const rz=!!sit.isRedZone;const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const rulerN=['G','10','20','30','40','50','40','30','20','10','G'];
 const ruler=rulerN.map((n,i)=>`<span style="left:${(EZ+i*play/10).toFixed(2)}%">${n}</span>`).join('');
 const ticks=Array.from({length:11},(_,i)=>`<i style="left:${i*10}%"></i>`).join('');
 // The ball marker + possession arrow point the direction of the drive.
 const dir=homeHas?-1:1;                           // home drives left (−), away drives right (+)
 const ball=haveBall?`<i class="fball" style="left:${losPct.toFixed(2)}%"><svg viewBox="0 0 24 14" aria-hidden="true"><ellipse cx="12" cy="7" rx="11" ry="6"/><line x1="7" y1="7" x2="17" y2="7"/></svg></i>${offAbbr?`
   <i class="fdir" style="left:${losPct.toFixed(2)}%;transform:translate(${dir>0?'6px':'-110%'},-50%) scaleX(${dir})">▶</i>`:''}`:'';
 // Only draw the first-down line when a ball marker is shown, so a partial feed can't leave a floating line with no ball.
 const fdLine=(haveBall&&fdPct!=null)?`<i class="fdline" style="left:${fdPct.toFixed(2)}%"></i>`:'';
 // The red zone is 20 yards deep in front of the defending end zone: left end zone (home attacking) covers 0..20,
 // right end zone (away attacking) covers 80..100.
 const rzShade=rz?`<i class="frz" style="left:${dir>0?80:0}%;width:20%"></i>`:'';
 // The situation line: down & distance, ball spot, who has it; and the last play + its type.
 const dd=sit.downDistanceText||dr.downDistanceText||'';
 const spot=sit.possessionText||'';                 // ESPN's "IND 27"; no synthetic number if the feed lacks it
 const offName=!offAbbr?'':homeHas?short(home.name||home.abbr):short(away.name||away.abbr);
 const lastPlay=(sit.lastPlayText||'').trim();const lastType=(sit.lastPlayType||'').trim();
 return `<div class="fstrip${reduce?' noanim':''}">
  <div class="fld" role="img" aria-label="Field position">
   <i class="ez l" style="background:${ac}"><span>${esc(away.abbr||'')}</span></i>
   <i class="ez r" style="background:${hc}"><span>${esc(home.abbr||'')}</span></i>
   <div class="grass">${ticks}${rzShade}${fdLine}${ball}</div>
   <div class="ruler">${ruler}</div>
  </div>
  ${haveBall||dd?`<div class="situ"><span class="dd">${esc(dd||(sit.down?ordinal(sit.down)+' & '+(sit.distance??''):''))||(sit.replay?'Replay':'Live')}</span>
   ${spot?`<span class="m">· ball on ${esc(spot)}</span>`:''}${offName?`<span class="m">· ${esc(offName)} ball</span>`:''}${rz?'<span class="rzt">RED ZONE</span>':''}${sit.replay?'<span class="rzt rpl">REPLAY</span>':''}</div>`:''}
  ${lastPlay?`<div class="lastplay">${lastType?`<span class="lpt">${esc(lastType)}</span>`:''}<span>${esc(lastPlay)}</span></div>`:''}
 </div>`;}
function ordinal(n){n=+n;const s=['th','st','nd','rd'],v=n%100;return n+(s[(v-20)%10]||s[v]||s[0]);}
// Timeout dots under a team's code on the scoreboard (3 = full). Possession football next to the code with the ball.
function _teamSide(d,abbr){if(!d||!d.board||!abbr)return null;const a=(abbr||'').toUpperCase();
 const b=d.board;if((b.home||{}).abbr&&b.home.abbr.toUpperCase()===a)return 'home';if((b.away||{}).abbr&&b.away.abbr.toUpperCase()===a)return 'away';return null;}
function scbTimeouts(d,abbr){const side=_teamSide(d,abbr);const sit=(d||{}).situation||{};if(!side)return '';
 const to=side==='home'?sit.homeTimeouts:sit.awayTimeouts;if(to==null)return '';
 return `<div class="tdots">${[0,1,2].map(i=>`<i class="${i<to?'on':''}"></i>`).join('')}</div>`;}
/* Who has the ball (#318): the board team's code in capitals, or '' when it isn't known. One answer for the whole page, so
   the scoreboard can never put a ball on both teams. The current drive's team first (the strip's direction uses it too), then
   the scoreboard's possession team (possAbbr, from ESPN's situation.possession id). Never ESPN's possessionText: that is the
   ball SPOT ("PHI 8" = on Philadelphia's 8 while Pittsburgh has it), not the team with the ball. */
function possTeam(d){const sit=(d||{}).situation||{},dr=(d||{}).drive||{};
 for(const c of [dr.teamAbbr,sit.possAbbr]){const a=String(c||'').toUpperCase();if(a&&_teamSide(d,a))return a;}return '';}
function scbPoss(d,abbr){if(!abbr||!_teamSide(d,abbr))return '';
 return possTeam(d)===abbr.toUpperCase()?'<span class="poss" title="has the ball">🏈</span>':'';}
