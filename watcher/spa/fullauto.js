/* Full auto (issue #7): the real master switch, OFF until Pete turns it on. This card shows on/off, today's spend, the
   losing-streak brake and what is blocking it, in plain words. The switch itself lives in the Mac's own file (never a
   setting), and turning it on asks for the paper gate to have passed or an explicit "override the paper gate". */
function faCard(v,full){if(!v)return '';const on=!!v.on,m=x=>'$'+(+x||0).toFixed(2).replace(/\.00$/,'');
 if(v.ok===false)return `<div class="card fa"><h3>Full auto <span>off</span></h3><div class="m">${esc((v.blockers||[])[0]||'Not available.')}</div></div>`;
 const br=v.brake,b=(v.blockers||[]).filter(x=>!(br&&x.indexOf('Paused itself')===0));
 const state=on?(b.length?'<span class="tag">Waiting</span>':'<span class="tag good">Running</span>'):'<span class="tag">Off</span>';
 const say=on?(b.length?'It is on, but not buying right now:':'It is on. Each minute it approves and adds the bets Smart Buy picks, inside your limits.'):'Off. Nothing is approved or bought on its own until you turn it on.';
 const gate=v.gate_ready?'The paper gate has passed.':'The paper gate has not passed yet.';
 return `<div class="card fa" id="fa"><h3>Full auto <span>${state}</span></h3>
  <div class="m" style="font-size:12.5px;margin-bottom:8px">${esc(say)}</div>
  ${on&&b.length?`<ul class="fab">${b.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
  <div class="mini">Spent today<b>${m(v.spent)} <span class="m" style="font-weight:500">of ${m(v.cap)}</span></b></div>
  <div class="mini">Bets open<b>${v.open} <span class="m" style="font-weight:500">of ${v.max_open} allowed</span></b></div>
  <div class="mini">Losing streak brake<b class="${br?'down':''}">${br?'Tripped':v.streak+' in a row <span class="m" style="font-weight:500">pauses at '+v.streak_limit+'</span>'}</b></div>
  ${br?`<div class="sbw sbx"><i>⚠️</i><span style="flex:1">Paused itself: ${esc(br.why)}</span></div>`:''}
  <div class="mini">Down today<b>${m(Math.max(0,-v.loss_today))} <span class="m" style="font-weight:500">pauses at ${m(v.day_loss)}</span></b></div>
  <div class="mini">Bankroll free<b>${m(v.free)} <span class="m" style="font-weight:500">of ${m(v.bank)}</span></b></div>
  <div class="m" style="font-size:12px;margin-top:6px">${esc(gate)}${on&&v.gate==='overridden'?' You turned it on by overriding the gate.':''} It buys with the same checks as Smart Buy, respects Pause, and exits use smart sell and the loss cut.</div>
  ${full?`<div class="fal"><label>Daily cap<input class="txt" type="text" inputmode="decimal" id="fa_cap" value="${v.limits.cap}"></label><label>Open bets<input class="txt" type="text" inputmode="numeric" id="fa_max_open" value="${v.limits.max_open}"></label><label>Pause after losses<input class="txt" type="text" inputmode="numeric" id="fa_streak" value="${v.limits.streak}"></label><label>Daily loss limit<input class="txt" type="text" inputmode="decimal" id="fa_day_loss" value="${v.limits.day_loss}"></label></div>
  <div class="fabtns"><button class="btn ${on?'':'acc'}" onclick="faSet(this,${on?'false':'true'})">${on?'Turn off':'Turn on'}</button><button class="btn" onclick="faSet(this,${on?'true':'false'},{limits:1})">Save limits</button>${br?`<button class="btn" onclick="faSet(this,${on},{reset:1})">Reset the pause</button>`:''}</div>`:`<div class="fabtns"><button class="btn ghost" onclick="go('settings')">Change in Settings</button></div>`}</div>`;}
function faSet(b,on,o){o=o||{};const lim={};if(o.limits)for(const k of ['cap','max_open','streak','day_loss']){const e=$('#fa_'+k);if(e)lim[k]=e.value.trim();}
 const send=ov=>{hap('light');btnBusy(b);return api('/app/api/act',{a:'full_auto_set',on:on,override:!!ov,reset_brake:!!o.reset,limits:o.limits?lim:undefined}).then(r=>{
  if(r.needs_override&&!ov){btnState(b,false);if(confirm('The paper gate has not passed yet. Override the paper gate and turn full auto on anyway? It will start approving real bets within your limits.'))return send(true);toast('Left off.');return;}
  toast(r.msg,5000);btnState(b,!!r.ok);setTimeout(()=>load(S.view),600)}).catch(()=>btnState(b,false));};
 if(on&&!o.limits&&!o.reset&&!confirm('Turn full auto on? It will approve and buy bets on its own, inside your limits, until you turn it off.'))return;
 return send(false);}
