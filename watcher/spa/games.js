// ---------------- games
/* Games: one live card per game you have money on (combos, single bets, spreads and totals). Team rows with the score,
   the clock, the chance line over the game with a glowing end dot, and the bets riding on it. When someone scores the
   card pulses (green when it's your side, red when it's theirs), the number bumps and the phone ticks. Tap to push
   into the game page. */
function gamesSkel(){return `<div class="games">${Array.from({length:4},()=>`<div class="gsk"><i style="height:11px;width:38%"></i><i style="height:20px;width:70%"></i><i style="height:20px;width:55%"></i><i style="height:46px"></i><i style="height:22px;width:60%"></i></div>`).join('')}</div>`;}
function miniLine(pts,col){if(!pts||pts.length<2)return `<div class="mline"><svg viewBox="0 0 300 46" preserveAspectRatio="none"><line x1="0" x2="300" y1="23" y2="23" stroke="var(--line)" stroke-width="2" stroke-dasharray="3 5" vector-effect="non-scaling-stroke"/></svg></div>`;
 const t0=pts[0][0],t1=pts[pts.length-1][0],X=t=>(t-t0)/Math.max(1,t1-t0)*300,Y=v=>42-Math.max(0,Math.min(1,v))*38;
 const d=pts.map((p,i)=>`${i?'L':'M'}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join('');const ly=Y(pts[pts.length-1][1]);const id='mg'+Math.random().toString(36).slice(2,7);
 return `<div class="mline"><svg viewBox="0 0 300 46" preserveAspectRatio="none"><defs><linearGradient id="${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${col}" stop-opacity=".28"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
  <line x1="0" x2="300" y1="${Y(.5)}" y2="${Y(.5)}" stroke="var(--line)" stroke-dasharray="3 5" vector-effect="non-scaling-stroke"/><path d="${d} L300 46 L0 46Z" fill="url(#${id})"/><path d="${d}" fill="none" stroke="${col}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/></svg>
  <i class="sdot" style="left:100%;top:${(ly/46*100).toFixed(1)}%;background:${col};color:${col}"></i></div>`;}
function gameLine(g){S.gh=S.gh||{};const k=g.ticker||g.name;let h=S.gh[k]||[];const now=Date.now()/1000;   // the page keeps its own line too, for bets the Mac hasn't charted yet
 if(g.chance!=null&&(!h.length||h[h.length-1][1]!==g.chance))h=h.concat([[now,g.chance]]).slice(-240);S.gh[k]=h;
 const sp=(g.spark||[]).filter(p=>p[1]!=null);return sp.length>=2?sp.concat(h.filter(p=>p[0]>sp[sp.length-1][0])):h;}
const GLIVE=g=>g.state==='live'&&!['probably_over','waiting','over'].includes(g.phase);
/* Warm a live football game's page data before it is opened (display only): when its card is shown on Games, and when a card is hovered or pressed.
   Polite: a game is asked about at most once a minute (3 to 5 minutes after a failure), 2 at a time, 6 per 5 minutes, never in a hidden tab;
   the Mac dedupes and backs off again on its own. Nothing here prices, buys or sells. */
const WARM_SPORTS=['nfl','ncaaf'];
function warmGame(t){if(!t||typeof t!=='string'||document.hidden)return;S.warm=S.warm||{};S.warmN=S.warmN||[];const now=Date.now();
 if((S.warm[t]||0)>now||(S.warmBusy||0)>=2)return;S.warmN=S.warmN.filter(x=>now-x<300000);if(S.warmN.length>=6)return;
 S.warm[t]=now+60000;S.warmN.push(now);S.warmBusy=(S.warmBusy||0)+1;
 api('/app/api/game_warm?t='+encodeURIComponent(t)).then(r=>{if(!r||!r.known)S.warm[t]=now+180000;},()=>{S.warm[t]=now+300000;}).then(()=>{S.warmBusy=Math.max(0,(S.warmBusy||1)-1);});}
function warmShown(){if(S.view!=='games'||!S.games)return;(S.games.games||[]).forEach(g=>{if(GLIVE(g)&&WARM_SPORTS.includes(g.sport))warmGame(g.ticker);});}
function warmCard(e){const c=e.target&&e.target.closest?e.target.closest('.gc[data-gk]'):null;if(!c||!S.games)return;
 const g=(S.games.games||[]).find(x=>(x.ticker||x.name)===c.dataset.gk);if(g&&GLIVE(g)&&WARM_SPORTS.includes(g.sport))warmGame(g.ticker);}
addEventListener('pointerover',warmCard,{passive:true});addEventListener('pointerdown',warmCard,{passive:true});
function gameCard(g){const live=GLIVE(g),fin=g.phase==='over',sc=g.sc,ch=g.chance,lc=live?legCls({state:'live',sc,live:ch}):'';
 const col=ch==null?'var(--acc)':ch>=.5?'var(--yes)':'var(--no)';const sg=S.gscore&&S.gscore[g.ticker||g.name];
 const what=g.kind==='spread'?'to cover':g.kind==='total'?'to hit':live?'to win now':'to win';
 // both teams and both scores on every card: the full opponent name, else the short code from the score; no score (tennis/UFC) = no number, never a fake 0
 const shown=sc&&(live||fin),myPts=shown&&sc.me!=null?sc.me:null,oppPts=shown&&sc.opp!=null?sc.opp:null,oppNm=g.opp||(sc&&sc.opp_abbr)||'';
 const bets=[g.combos?`<span class="bt">🎯 ${g.combos} combo${g.combos>1?'s':''}</span>`:'',...(g.singles||[]).map(x=>`<span class="bt s">${x.kind==='spread'?'📏':x.kind==='total'?'Σ':'✓'} ${esc(x.plain||x.label||'')}</span>`)].join('');
 const head=live?`<span class="lv"><i></i>${esc((sc&&sc.detail)||'Live')}</span>`:fin?`<span>Final${sc&&sc.detail?' · '+esc(sc.detail):''}</span>`:g.state==='over'||g.phase==='probably_over'?'<span>Probably finished</span>':g.phase==='waiting'?'<span>Not started yet</span>':`<span>${esc(g.short||g.starts||'Upcoming')}</span>`;
 return `<div class="gc ${live?'live l'+lc:''} ${sg?'scored '+sg:''}" data-gk="${esc(g.ticker||g.name)}" data-t="${esc(g.ticker||'')}" onclick="openGame(this.dataset.t)">
  <div class="gh"><span>${ICON[g.sport]||''} ${esc(SPN[g.sport]||g.sport||'')}</span>${head}</div>
  <div class="tms"><div class="gtr me"><span class="nm">${esc(g.kind==='total'&&g.matchup?g.matchup:g.name)}</span><span class="mine">YOURS</span>${myPts!=null?`<b class="pts ${sg?'bump':''}">${esc(String(myPts))}</b>`:''}</div>
   ${oppNm||oppPts!=null?`<div class="gtr them"><span class="nm">${esc(oppNm||'Opponent')}</span>${oppPts!=null?`<b class="pts">${esc(String(oppPts))}</b>`:''}</div>`:''}</div>
  ${g.matchup&&g.kind&&g.kind!=='total'&&!oppNm&&oppPts==null?`<div class="gmu">${esc(g.matchup)}${g.found===false?' <i class="nf" title="Kalshi has no matching game on our schedule feed yet; this does not mean the bet is wrong">game not found</i>':''}</div>`:''}${g.kind==='total'&&g.found===false?'<div class="gmu"><i class="nf" title="Kalshi has no matching game on our schedule feed yet; this does not mean the bet is wrong">game not found</i></div>':''}
  <div class="gl"><div class="ch"><b class="${ch==null?'':ch>=.5?'up':'down'}" ${ch!=null?`data-num="gch:${esc(g.ticker||g.name)}" data-v="${ch}" data-f="pct"`:''}>${ch==null?'—':pct(ch)}</b><small>${what}</small>
   <div class="gbar"><i data-bar="gb:${esc(g.ticker||g.name)}" style="width:${ch==null?0:Math.max(2,Math.min(100,ch*100))}%;background:${col}"></i></div></div>${miniLine(gameLine(g),col)}</div>
  <div class="bets">${bets}<span class="rd">${money(g.pays)} riding</span></div></div>`;}
function scoreWatch(gs){/* who scored since the last paint: your side, or theirs */
 S.gsc=S.gsc||{};S.gscore={};let any=null;
 gs.forEach(g=>{const k=g.ticker||g.name,sc=g.sc;if(!sc||g.state!=='live')return;const o=S.gsc[k];S.gsc[k]=[sc.me,sc.opp];
  if(o&&(o[0]!==sc.me||o[1]!==sc.opp)){const good=sc.me>o[0];S.gscore[k]=good?'good':'bad';any=any||S.gscore[k];}});
 if(any&&S.view==='games')hap(any==='good'?'success':'warning');
 clearTimeout(S.gscT);S.gscT=setTimeout(()=>{S.gscore={};document.querySelectorAll('.gc.scored').forEach(e=>e.classList.remove('scored','good','bad'));},1700);}
/* Display order (Pete: sorted by next game): playing now first, then upcoming by start time (soonest first; no start time = after the
   timed ones), then finished (most recent first). Ties break on the ticker, then the name, so cards never shuffle between refreshes.
   Order only: nothing here prices, buys or sells. */
const gStart=g=>{const t=Number(g.start_ts);return g.start_ts!=null&&isFinite(t)&&t>0?t:null;};
const gDone=g=>g.phase==='over'||g.state==='over'||g.phase==='probably_over';
const gBucket=g=>GLIVE(g)?0:gDone(g)?2:1;
function gameOrder(a,b){const ba=gBucket(a),bb=gBucket(b);if(ba!==bb)return ba-bb;
 const sa=gStart(a),sb=gStart(b);if(sa!==sb){if(sa==null)return 1;if(sb==null)return -1;return ba===2?sb-sa:sa-sb;}
 const ka=String(a.ticker||a.name||''),kb=String(b.ticker||b.name||'');return ka<kb?-1:ka>kb?1:0;}
function renderGames(){const d=S.games;const m=$('#main');if(!d){m.innerHTML=(S.lerr||{}).games?errCard('games'):gamesSkel();return;}
 const gs=(d.games||[]).slice().sort(gameOrder);if(!gs.length){m.innerHTML='<div class="card empty" data-ic="🏟️"><b>No games to watch</b>Games you have money on, in combos or as single bets and spreads, show up here with live scores and chance lines.<br><button class="btn acc" onclick="go(\'build\')">See today\'s bets</button></div>';return;}
 scoreWatch(gs);setTimeout(warmShown,400);
 const on=GLIVE,live=gs.filter(on),fin=gs.filter(g=>g.phase==='over'),idle=gs.filter(g=>!on(g)&&!fin.includes(g)&&(g.phase==='probably_over'||g.state==='over')),rest=gs.filter(g=>!on(g)&&!fin.includes(g)&&!idle.includes(g));
 m.innerHTML=(d.fresh?`<div class="fresh" data-fr="N" style="text-align:right;margin:-6px 2px 4px">${frTxt('N')}</div>`:'')+(live.length?`<h2><span class="live-dot"></span>Playing now <span class="n">${live.length}</span></h2><div class="games">${live.map(gameCard).join('')}</div>`:'')
  +(rest.length?`<h2>Coming up <span class="n">${rest.length}</span></h2><div class="games">${rest.map(gameCard).join('')}</div>`:'')
  +(fin.length?`<h2>Finished <span class="n">${fin.length}</span></h2><div class="m" style="font-size:12.5px;margin:-6px 2px 10px">Over. Kalshi settles them when the result is in.</div><div class="games">${fin.map(g=>gameCard(g).replace('class="gc ','class="gc done ')).join('')}</div>`:'')
  +(idle.length?`<h2>Probably finished <span class="n">${idle.length}</span></h2><div class="m" style="font-size:12.5px;margin:-6px 2px 10px">No live score for these. Kalshi settles them when the result is in.</div><div class="games">${idle.map(g=>gameCard(g).replace('class="gc ','class="gc done ')).join('')}</div>`:'');}
