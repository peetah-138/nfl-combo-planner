/* Full auto (issue #7): the real master switch, OFF until Pete turns it on. This card shows on/off, today's spend, the
   confidence level and what is blocking it, in plain words. The switch itself lives in the Mac's own file (never a
   setting), and turning it on asks for the paper gate to have passed or an explicit "override the paper gate". */
function faCard(v,full){if(!v)return '';const on=!!v.on,m=x=>'$'+(+x||0).toFixed(2).replace(/\.00$/,'');
 if(v.ok===false)return `<div class="card fa"><h3>Full auto <span>off</span></h3><div class="m">${esc((v.blockers||[])[0]||'Not available.')}</div></div>`;
 const br=v.brake,ca=v.caution||{level:0},b=(v.blockers||[]).filter(x=>!(br&&x.indexOf('Paused itself')===0));
 const state=on?(b.length?'<span class="tag">Waiting</span>':'<span class="tag good">Running</span>'):'<span class="tag">Off</span>';
 const say=on?(b.length?'It is on, but not buying right now:':'It is on. Each minute it approves and adds the bets Smart Buy picks, inside your limits.'):'Off. Nothing is approved or bought on its own until you turn it on.';
 const gate=v.gate_ready?'The paper gate has passed.':'The paper gate has not passed yet.';
 return `<div class="card fa" id="fa"><h3>Full auto <span>${state}</span></h3>
  <div class="m" style="font-size:12.5px;margin-bottom:8px">${esc(say)}</div>
  ${on&&b.length?`<ul class="fab">${b.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
  <div class="mini">Spent today<b>${m(v.spent)} <span class="m" style="font-weight:500">of ${m(v.cap)}</span></b></div>
  <div class="mini">Bets open<b>${v.open} <span class="m" style="font-weight:500">of ${v.max_open} allowed</span></b></div>
  <div class="mini">Confidence<b class="${ca.level?'down':''}">${ca.level?'Cautious ('+ca.pct+'%)':'Normal'} <span class="m" style="font-weight:500">${ca.level?'':'('+v.streak+' lost, goes cautious after '+v.streak_limit+' in a row)'}</span></b></div>
  ${ca.level?`<div class="m" style="font-size:12.5px;margin:2px 0 6px">Cautious: ${esc(ca.why||'')} Bets and the daily cap are cut to ${ca.pct}% of normal${ca.bar_extra?' and combos must clear the bar by '+ca.bar_extra+' more point'+(ca.bar_extra===1?'':'s'):''}. Back up a step after ${ca.wins_need} winning bets in a row (${ca.wins} so far)${ca.calm_days_left!=null?' or in about '+ca.calm_days_left+' calm days':''}. It never turns itself off.</div>`:''}
  ${br?`<div class="sbw sbx"><i>⚠️</i><span style="flex:1">Paused itself: ${esc(br.why)}</span></div>`:''}
  <div class="mini">Down today<b>${m(Math.max(0,-v.loss_today))} <span class="m" style="font-weight:500">pauses at ${m(v.day_loss)}</span></b></div>
  <div class="mini">Bankroll free<b>${m(v.free)} <span class="m" style="font-weight:500">of ${m(v.bank)}</span></b></div>
  ${faLessons(v,on,full)}
  <div class="m" style="font-size:12px;margin-top:6px">${esc(gate)}${on&&v.gate==='overridden'?' You turned it on by overriding the gate.':''} It buys with the same checks as Smart Buy, respects Pause, and exits use smart sell and the loss cut.</div>
  ${full?`<div class="fal"><label>Daily cap<input class="txt" type="text" inputmode="decimal" id="fa_cap" value="${v.limits.cap}"></label><label>Open bets<input class="txt" type="text" inputmode="numeric" id="fa_max_open" value="${v.limits.max_open}"></label><label>Pause after losses<input class="txt" type="text" inputmode="numeric" id="fa_streak" value="${v.limits.streak}"></label><label>Daily loss limit<input class="txt" type="text" inputmode="decimal" id="fa_day_loss" value="${v.limits.day_loss}"></label></div>
  <div class="fabtns"><button class="btn ${on?'':'acc'}" onclick="faSet(this,${on?'false':'true'})">${on?'Turn off':'Turn on'}</button><button class="btn" onclick="faSet(this,${on?'true':'false'},{limits:1})">Save limits</button>${(br||ca.level)?`<button class="btn" onclick="faSet(this,${on},{reset:1})">${ca.level?'Back to normal now':'Reset the pause'}</button>`:''}</div>`:`<div class="fabtns"><button class="btn ghost" onclick="go('settings')">Change in Settings</button></div>`}</div>`;}
/* (#144) "Lessons": while full auto is on, it may take one small step a week from the paper records that passed their bar.
   Every step is listed here in plain words, with its reason; the switch is its own tap. */
function faLessons(v,on,full){const L=v.lessons;if(!L)return '';
 const lines=(L.log||[]).map(x=>`<li>${esc(x)}</li>`).join(''),
  learned=(L.learned||[]).map(x=>`<li>${esc(x.name)}: ${esc(x.text)}</li>`).join(''),
  recs=(L.recs||[]).map(x=>`<li>${esc(x.name)}: ${esc(x.state)}${x.n!=null?` (${x.n} bets, needs ${x.min})`:''}${x.note?' - '+esc(x.note):''}</li>`).join(''),
  nw=(L.not_wired||[]).map(x=>`<li>${esc(x.name)}: ${esc(x.why)}</li>`).join('');
 return `<div class="m" style="font-size:12px;margin-top:8px"><b>Lessons</b> <span class="tag ${L.switch&&on?'good':''}">${!L.switch?'Off':on?'On':'Waits for full auto'}</span><br>While full auto is on, a paper record that has enough bets and clearly passes its bar may move one small step a week, tighter or looser, inside fixed limits. Your daily cap, loss limit, bankroll and losing-streak confidence level (it only ever steps down or back up to your normal) never change above your settings, and a step that does worse the next week is undone.</div>
  ${L.err?`<div class="sbw sbx"><i>⚠️</i><span style="flex:1">${esc(L.err)}</span></div>`:''}
  ${lines?`<ul class="fab">${lines}</ul>`:'<div class="m" style="font-size:12px">Nothing learned yet.</div>'}
  ${learned?`<div class="m" style="font-size:12px">In use now:</div><ul class="fab">${learned}</ul>`:''}
  ${recs?`<details class="m" style="font-size:12px"><summary>What each record says</summary><ul class="fab">${recs}</ul><div>Not wired yet:</div><ul class="fab">${nw}</ul></details>`:''}
  ${full?`<div class="fabtns"><button class="btn" onclick="faLessonsSet(this,${L.switch?'false':'true'})">${L.switch?'Turn Lessons off':'Turn Lessons on'}</button></div>`:''}`;}
function faLessonsSet(b,on){hap('light');btnBusy(b);return api('/app/api/act',{a:'full_auto_lessons',on:on}).then(r=>{toast(r.msg,4000);btnState(b,!!r.ok);setTimeout(()=>load(S.view),600)}).catch(()=>btnState(b,false));}
function faSet(b,on,o){o=o||{};const lim={};if(o.limits)for(const k of ['cap','max_open','streak','day_loss']){const e=$('#fa_'+k);if(e)lim[k]=e.value.trim();}
 const send=ov=>{hap('light');btnBusy(b);return api('/app/api/act',{a:'full_auto_set',on:on,turn_on:!!(on&&!o.limits&&!o.reset),override:!!ov,reset_brake:!!o.reset,limits:o.limits?lim:undefined}).then(r=>{
  if(r.needs_override&&!ov){btnState(b,false);if(confirm('The paper gate has not passed yet. Override the paper gate and turn full auto on anyway? It will start approving real bets within your limits.'))return send(true);toast('Left off.');return;}
  toast(r.msg,5000);btnState(b,!!r.ok);setTimeout(()=>load(S.view),600)}).catch(()=>btnState(b,false));};
 if(on&&!o.limits&&!o.reset&&!confirm('Turn full auto on? It will approve and buy bets on its own, inside your limits, until you turn it off.'))return;
 return send(false);}
