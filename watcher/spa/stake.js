/* ---- Your own bet amount (issue #145). Every buy Pete taps (a combo card, the slip, a Live Buy idea, a panel bet before
   Approve or Add) starts at the recommended size and can be changed here: presets, a -/+ stepper and a typed amount.
   The page only says what he wants; the Mac checks every amount again (own_stake: a real number, $1-$100, cents,
   the cap, the panel budget) and prices it itself, so nothing here can buy more than the Mac allows. The last amount he
   chose is kept on this phone as a "Last $X" chip only (the default stays the recommended size). No haptics are
   called here: the tap on the control itself ticks (iOS 27: only a finger on a real control does). */
const STK_PRESETS=[2,5,10,20];
function stkMoney(v){return '$'+(+v).toFixed(2).replace(/\.00$/,'');}
function stkLast(){try{const v=parseFloat(localStorage.getItem('cw_stk_last'));return isFinite(v)&&v>0?v:null;}catch(e){return null;}}
function stkKeep(v){try{localStorage.setItem('cw_stk_last',String(v));}catch(e){}}
function stkGet(key){const v=(S.stk||{})[key];return v>0?v:null;}
/* o: {key, rec (recommended), cur (on screen now), min, max, ev (expected profit in $), room (left under the cap)} */
function stakeCtl(o){const k=esc(o.key),rec=+o.rec||0,cur=+(o.cur!=null?o.cur:rec)||0,mn=+o.min||1,mx=Math.max(mn,+o.max||100);
 const own=stkGet(o.key)!=null&&Math.abs(cur-rec)>=.005,last=stkLast();
 const ps=STK_PRESETS.filter(v=>v>=mn&&v<=mx&&Math.abs(v-rec)>=.005);
 if(last&&last>=mn&&last<=mx&&Math.abs(last-rec)>=.005&&!ps.some(v=>Math.abs(v-last)<.005))ps.push(last);
 const chip=(v,lbl)=>`<button type="button" class="chip ${Math.abs(cur-v)<.005?'on':''}" onclick="stkSet('${k}',${v})">${lbl||stkMoney(v)}</button>`;
 const x=rec>0?cur/rec:1;
 const note=own&&rec>0&&x>=1.5?`<div class="stkw" data-w="big">${x.toFixed(1).replace(/\.0$/,'')}× the recommended size: more risk for the same edge.</div>`:'';
 const cap=o.room!=null&&o.room<100&&mx<=o.room+.005?`<div class="stkm" data-w="cap">Your cap has ${money(o.room)} left, so ${stkMoney(mx)} is the most here.</div>`:'';
 const ev=o.ev!=null?`<span class="stkev ${o.ev>0?'up':o.ev<0?'down':''}">Expected profit ${o.ev>=0?'+':'−'}${stkMoney(Math.abs(o.ev))}</span>`:'';
 return `<div class="stk" data-sk="${k}">
  <div class="stkh" aria-live="polite"><span class="stkl">Your bet</span><b data-num="sk:${k}" data-v="${cur.toFixed(2)}">${stkMoney(cur)}</b>${own?'<span class="tag">your amount</span>':o.small?'<span class="tag">smallest bet</span>':'<span class="tag good">recommended</span>'}${ev}</div>
  <div class="stkr"><button type="button" class="stkb" aria-label="One dollar less" ${cur-1<mn-.005?'disabled':''} onclick="stkSet('${k}',${Math.max(mn,Math.round((cur-1)*100)/100)})">−</button>
   ${chip(rec,(o.small?'Smallest ':'Recommended ')+stkMoney(rec))}${ps.map(v=>chip(v,last&&Math.abs(v-last)<.005&&!STK_PRESETS.includes(v)?'Last '+stkMoney(v):'')).join('')}
   <input class="stkin" type="number" inputmode="decimal" min="${mn}" max="${mx}" step="1" placeholder="$" aria-label="Your own bet amount in dollars" onkeydown="if(event.key==='Enter'){this.blur()}" onchange="stkType('${k}',this,${mn},${mx})">
   <button type="button" class="stkb" aria-label="One dollar more" ${cur+1>mx+.005?'disabled':''} onclick="stkSet('${k}',${Math.min(mx,Math.round((cur+1)*100)/100)})">+</button></div>
  ${note}${cap}</div>`;}
function stkType(key,el,mn,mx){const v=parseFloat(el.value);el.value='';
 if(!isFinite(v)||v<=0){toast('Type a bet amount in dollars.');return;}
 if(v<mn){toast(`The least you can bet here is ${stkMoney(mn)}.`,4000);stkSet(key,mn);return;}
 if(v>mx){toast(`The most this bet can be is ${stkMoney(mx)}.`,4000);stkSet(key,mx);return;}
 stkSet(key,Math.floor(v*100+1e-6)/100);}
/* a new amount: remembered for this screen (S.stk), the old price dropped (it was for the old amount), then re-priced
   where that is quick (a single game reads Kalshi's book) or left for Get price (a combo asks Kalshi's makers) */
function stkSet(key,v){v=Math.round(+v*100)/100;if(!(v>0))return;S.stk=S.stk||{};S.stk[key]=v;stkKeep(v);
 const [kind,id]=[key.slice(0,key.indexOf(':')),key.slice(key.indexOf(':')+1)];
 if(kind==='cc'){if(S.quotes)delete S.quotes[id];renderBuild();return;}
 if(kind==='slip'){S.custom=null;renderBuild();return;}
 if(kind==='id'){const q=(S.ideaq||{})[id];const one=q&&q.single;S.ideaq[id]=null;if(one)priceIdea(id);else{if(S.ideaOpen)ideaSheet();renderLive();}return;}
 if(kind==='pn'){pStakeRedraw(id);return;}}
/* the price buttons say the amount they will ask for once Pete chose one */
function stkLbl(key){const v=stkGet(key);return v!=null?' · '+stkMoney(v):'';}

/* ---- the panel: a bet's amount is changed on a small sheet before Approve / Add; the card, the totals and the
   chance-up ring follow (the ring is the Mac's own simulation, panel_whatif, which reads only). */
function pStake(c){const v=stkGet('pn:'+c.id);return v!=null?v:+c.stake||0;}
function pStakeSheet(id,view){const src=view==='extra'?((S.panel||{}).extra||{}):((S.panel||{}).panel||{});const c=(src.items||[]).find(x=>x.id===id);if(!c)return;
 S.pstOpen={id,view};const bud=+(((S.panel||{}).panel||{}).budget||src.budget)||100;
 modal(`<div id="pstx">${pStakeBody(c,bud)}</div>`);}
function pStakeBody(c,bud){const rec=+c.stake||0,cur=pStake(c),k=KIND[c.kind]||['•',c.kind];
 const ev=c.ret!=null?Math.round(cur*c.ret*100)/100:null;
 return `<div class="sbk">${c.icon||k[0]} ${esc(k[1])}${c.league?' · '+esc(c.league):''}</div><h3>${esc((c.legs||[]).map(l=>short(l.pick)).join(' + '))}</h3>
  <div class="m" style="font-size:13px;margin-bottom:8px">Recommended ${stkMoney(rec)}: sized from the edge (a quarter of Kelly on a shrunk edge) and your balance, inside the panel's limits.</div>
  ${stakeCtl({key:'pn:'+c.id,rec,cur,min:2,max:Math.min(100,bud),ev})}
  <div class="sbgo"><button class="btn ghost" onclick="pStakeReset('${esc(c.id)}')">Use recommended</button><button class="btn acc pri" onclick="closeModal()">Done</button></div>`;}
function pStakeRedraw(id){const o=S.pstOpen;const box=$('#pstx');
 if(o&&o.id===id&&box){const src=o.view==='extra'?((S.panel||{}).extra||{}):((S.panel||{}).panel||{});const c=(src.items||[]).find(x=>x.id===id);
  const bud=+(((S.panel||{}).panel||{}).budget||src.budget)||100;if(c){box.innerHTML=pStakeBody(c,bud);rollNums(box);}}
 renderBuild();pWhatIf();}
function pStakeReset(id){if(S.stk)delete S.stk['pn:'+id];pStakeRedraw(id);}
function pStakes(items){const o={};(items||[]).forEach(c=>{const v=stkGet('pn:'+c.id);if(v!=null&&Math.abs(v-c.stake)>=.005)o[c.id]=v;});return o;}
function pStakeClear(items){(items||[]).forEach(c=>{if(S.stk)delete S.stk['pn:'+c.id];});S.pWhat=null;}
/* the ring and the expected line at Pete's amounts (debounced; a stale answer for other amounts is ignored) */
function pWhatIf(){clearTimeout(S.pwT);S.pwT=setTimeout(async()=>{const p=(S.panel||{}).panel;if(!p)return;
 const its=(p.items||[]).filter(c=>!S.pOff.has(c.id)),stakes=pStakes(its);const sig=JSON.stringify([p.at,its.map(c=>c.id),stakes]);
 if(!Object.keys(stakes).length){S.pWhat=null;if(!document.querySelector('#main .btn.arm')&&!S.pSend)renderBuild();return;}
 const r=await api('/app/api/act',{a:'panel_whatif',view:S.pview||'all',ids:its.map(c=>c.id),stakes}).catch(()=>null);
 const now=(S.panel||{}).panel;if(!r||!r.ok||!now||JSON.stringify([now.at,(now.items||[]).filter(c=>!S.pOff.has(c.id)).map(c=>c.id),pStakes((now.items||[]).filter(c=>!S.pOff.has(c.id)))])!==sig)return;
 S.pWhat={sig,st:r};if(!document.querySelector('#main .btn.arm')&&!S.pSend)renderBuild();},350);}   // an armed Approve keeps its arm (the next redraw shows the ring)
function pWhatSt(p){const w=S.pWhat;if(!w||!p)return null;const its=(p.items||[]).filter(c=>!S.pOff.has(c.id));
 return w.sig===JSON.stringify([p.at,its.map(c=>c.id),pStakes(its)])?w.st:null;}
