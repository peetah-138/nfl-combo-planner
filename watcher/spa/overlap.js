/* Games you already have enough on (overlap guard). The Mac marks a pick with `over` when its game already has the
   number of open bets set in Settings › Money (2 by default), or that share of the panel's sizing base at risk (8%).
   Build, Best bets, Surprise me, Long shots, single games, Buy ideas and the panel's extras show it greyed and last,
   with one "Add anyway" button. That tap is yours alone: the game goes in S.ovAllow, a list kept only in this page
   (gone on reload, never saved, never read by anything that buys on its own), and the list is fetched again. Each entry
   carries the game's open bets and dollars at risk at the tap (KEY~n~risk), so once the game has more riding than
   that the Mac greys it again (#366). */
S.ovAllow=S.ovAllow||new Map();
function ovList(){return [...S.ovAllow].map(([g,e])=>e&&e.n!=null?g+'~'+e.n+'~'+e.risk:g);}
function ovQ(sep){const a=ovList();return a.length?sep+'allow='+encodeURIComponent(a.join(',')):'';}
function ovLast(a,b){return (!!a.over)-(!!b.over);}
function ovText(o){return o&&o.text?o.text:'You already have bets on this game.';}
/* the note and the button under a greyed pick; v is the screen to fetch again ('build' or 'live') */
function ovBar(o,v){if(!o)return '';
 return `<div class="ovbar" role="note"><span>${esc(ovText(o))}</span><button type="button" class="btn ovadd" aria-label="Add anyway: show this game's picks again" onclick="event.stopPropagation();ovAdd(this,'${esc(o.game||'')}','${v==='live'?'live':'build'}',${Number.isFinite(+o.n)&&Number.isFinite(+o.risk)?+o.n+','+(+o.risk):'null,null'})">Add anyway</button></div>`;}
async function ovAdd(b,g,v,n,risk){hap();if(!g||(b&&b.disabled))return;S.ovAllow.set(g,n==null?null:{n,risk});
 const snap=flipSnap();   // (#368) where every card is now, so the ones that move can slide instead of jump (smallwins.js)
 if(b){b.disabled=true;b.innerHTML='<span class="spin"></span> Showing…';}
 try{await load(v);}catch(e){toast('Couldn\'t refresh that game. Try again.');}   // (#402) no haptic after the await (silent on iOS 27): the tap ticked and the toast says it
 if(S.view===v)render();
 flipPlay(snap);}
/* a quote's "you already have a bet on this game" line (display only: the price and its cut-off are unchanged) */
function ovQuote(t){return t?`<div class="ovq" role="note">⚠ ${esc(t)}</div>`:'';}
/* Best bets: the games left out, each with Add anyway */
function ovName(ev){const g=((S.build||{}).board||[]).find(x=>x.event===ev);
 return g?g.sides.filter(s=>!s.tie).map(s=>short(s.pick)).join(' vs '):String(ev||'').replace(/^KX[A-Z]+GAME-/,'');}
function ovLeft(f){const xs=(f&&f.over)||[];if(!xs.length)return '';
 return `<div class="card ovleft"><h3>Left out <span>${xs.length} game${xs.length===1?'':'s'} you already have bets on</span></h3>
  ${xs.map(o=>`<div class="ovrow"><b aria-disabled="true">${esc(ovName(o.event))}</b>${ovBar(o,'build')}</div>`).join('')}</div>`;}
/* greyed versions of each kind of card: what it is, dimmed, then the note and Add anyway. No price or buy button. */
function ovCombo(c){return `<div class="ccard over" data-i="${c.i}"><div class="ovdim" aria-disabled="true"><div class="hd"><div><div class="tier">${esc(c.kind==='value'?'★ Value pick':c.tier||c.kind||'')}</div><b>${money(c.fair)}</b> <span class="m">fair payout</span></div><span class="verdict hold">${pct(c.chance)}</span></div>
  <div class="lrows">${c.legs.map(l=>legRow(l)).join('')}</div></div>${ovBar(c.over,'build')}</div>`;}
function ovLs(r){return `<div class="ccard lscard over"><div class="ovdim" aria-disabled="true"><div class="hd"><div><div class="tier">🎯 Long shot · ${r.n||(r.legs||[]).length} picks</div><b>${pct(r.chance)}</b> <span class="m">to hit</span></div></div>
  <div class="lrows">${(r.legs||[]).map(l=>legRow(l)).join('')}</div></div>${ovBar(r.over,'build')}</div>`;}
function ovIdea(x){return `<div class="iw" data-id="${x.id}"><div class="dcard idea over" id="idea-${x.id}"><div class="ovdim" aria-disabled="true"><h4>${x.n===1?'🎯':'💡'} ${esc(x.picks)}</h4><p>${esc(x.sport||'')}${x.n>1?' · '+x.n+' picks':''}${x.pct!=null?' · priced at '+pct(x.pct)+' of fair':''}</p></div>${ovBar(x.over,'live')}</div></div>`;}
function ovExtra(c){return `<div class="ovwrap"><div class="ovdim" aria-disabled="true">${panelItem(c,'',false,'add','extra')}</div>${ovBar(c.over,'build')}</div>`;}
