// ---------------- charts
function sparkPath(pts,w,h,lo,hi){if(!pts||pts.length<2)return '';const t0=pts[0][0],t1=pts[pts.length-1][0]||t0+1;lo=lo??0;hi=hi??1;
 return pts.map((p,i)=>`${i?'L':'M'}${((p[0]-t0)/Math.max(1,t1-t0)*w).toFixed(1)} ${(h-(Math.min(hi,Math.max(lo,p[1]))-lo)/Math.max(1e-9,hi-lo)*h).toFixed(1)}`).join('');}
function spark(pts,w,h,col){if(!pts||pts.length<2)return `<svg viewBox="0 0 ${w} ${h}"><line x1="0" x2="${w}" y1="${h/2}" y2="${h/2}" stroke="var(--line)" stroke-dasharray="3 4"/></svg>`;
 const last=pts[pts.length-1][1];col=col||(last>=.5?'var(--yes)':'var(--no)');const p=sparkPath(pts,w,h-4,0,1);
 return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><line x1="0" x2="${w}" y1="${(h-4)/2}" y2="${(h-4)/2}" stroke="var(--line)" stroke-dasharray="3 4"/>
  <path d="${p} L${w} ${h} L0 ${h}Z" fill="${col}" opacity=".10"/><path d="${p}" fill="none" stroke="${col}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>`;}
function valueChart(off,cost,pays){if(!off||off.length<2)return '<div class="m" style="padding:18px 4px">The value chart fills in as the Mac watches this combo.</div>';
 const W=Math.round(Math.max(340,Math.min(820,window.innerWidth-70))),H=W<600?190:200,pl=44,pb=22,iw=W-pl-8,ih=H-pb-10;const t0=off[0].ts,t1=off[off.length-1].ts;
 const vals=off.flatMap(o=>[o.hold,o.offer]).filter(v=>v!=null).concat([cost]);const hi=Math.max(...vals)*1.08,lo=0;
 const X=t=>pl+(t-t0)/Math.max(1,t1-t0)*iw,Y=v=>10+ih-(v-lo)/(hi-lo)*ih;
 const line=k=>off.filter(o=>o[k]!=null).map((o,i)=>`${i?'L':'M'}${X(o.ts).toFixed(1)} ${Y(o[k]).toFixed(1)}`).join('');
 const ticks=[0,.25,.5,.75,1].map(f=>lo+(hi-lo)*f);const tl=t=>new Date(t*1000).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
 return `<div class="key"><span><i style="background:var(--acc)"></i>Worth holding</span><span><i style="background:var(--yes)"></i>Kalshi offer</span><span><i style="background:var(--mute)"></i>You paid</span></div>
 <svg viewBox="0 0 ${W} ${H}">${ticks.map(v=>`<line x1="${pl}" x2="${W-8}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/><text x="${pl-6}" y="${Y(v)+4}" text-anchor="end" font-size="11" fill="var(--mute)">${money(v)}</text>`).join('')}
  <line x1="${pl}" x2="${W-8}" y1="${Y(cost)}" y2="${Y(cost)}" stroke="var(--mute)" stroke-dasharray="4 4"/>
  <path d="${line('hold')}" fill="none" stroke="var(--acc)" stroke-width="2.2" stroke-linejoin="round"/>
  <path d="${line('offer')}" fill="none" stroke="var(--yes)" stroke-width="2" stroke-linejoin="round" opacity=".9"/>
  ${off.filter(o=>o.real_offer&&o.offer!=null).map(o=>`<circle cx="${X(o.ts)}" cy="${Y(o.offer)}" r="3.5" fill="var(--yes)"/>`).join('')}
  <text x="${pl}" y="${H-4}" font-size="11" fill="var(--mute)">${tl(t0)}</text><text x="${W-8}" y="${H-4}" font-size="11" fill="var(--mute)" text-anchor="end">${tl(t1)}</text></svg>`;}
