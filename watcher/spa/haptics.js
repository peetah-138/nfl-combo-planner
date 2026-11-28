/* Haptics. light/selection = one tick; success = two quick ticks; warning = two slower; error = three.
   In the iPhone app: combo://haptic/<kind>. Home Screen app / Safari on iOS: toggling an <input switch> ticks the
   Taptic Engine; it has to happen synchronously inside a real tap (the global tap listener calls hap() from the click
   event), on an element that is laid out (a tiny, nearly see-through one inside the screen; iOS ignores display:none,
   visibility:hidden and, it seems, things parked off-screen). iPhones and iPads get the switch even if they report
   navigator.vibrate; everything else uses navigator.vibrate. window.__haps keeps the last 60 kinds for the page tests.
   HT holds every method the Settings > Test haptics card can try; HAPDEF is the one hap() uses. On iOS 27 (Pete,
   #60) only G, H and I tick: the finger itself has to land on a real switch, a scripted click never ticks. So the
   default is N: a see-through switch over every control (hsw*, below); hap() then only tries the scripted switch for
   the extra ticks of a pattern and for gestures without a tap, which iOS 27 ignores. The card's Haptics switch is
   saved on this phone (cw_hapoff). */
const HAPN={success:[0,90],warning:[0,160],error:[0,80,160]};
const APPLE=/iP(hone|ad|od)/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
const HAPDEF='N';
const HAPCLICK='ABCDEFJK';   // the methods hap() can run itself (G, H, I need the finger itself; L, M aren't switches)
const HAPCSS='position:fixed;left:8px;bottom:8px;width:2px;height:2px;opacity:.01;overflow:hidden;z-index:-1';
const HAPSW='<input type="checkbox" switch tabindex="-1">';
function hapNode(id,css){let l=document.getElementById(id);if(!l){l=document.createElement('label');l.id=id;l.className='hapx';l.setAttribute('aria-hidden','true');l.style.cssText=css;l.innerHTML=HAPSW;document.body.appendChild(l);}return l;}
const HT={
 A(){hapNode('hapA','position:fixed;left:-99px;top:0;opacity:0;width:1px;height:1px;overflow:hidden').click();},   // the old way
 B(){hapNode('hapl',HAPCSS).click();},
 C(){hapNode('hapC',HAPCSS).querySelector('input').click();},
 D(){const l=document.createElement('label');l.className='hapx';l.setAttribute('aria-hidden','true');l.style.cssText=HAPCSS;l.innerHTML=HAPSW;document.body.appendChild(l);l.click();setTimeout(()=>l.remove(),400);},
 E(){const l=hapNode('hapl',HAPCSS);l.click();l.click();},
 F(){const l=hapNode('hapl',HAPCSS);l.click();setTimeout(()=>l.click(),120);},
 G(){},H(){},I(){},   // native: the user's own tap is the toggle, nothing to run
 J(){HT.B();},K(){HT.B();},
 N(){if(!hswOn())return false;},   // the button's own see-through switch is the tick
 L(){if(!navigator.vibrate)return false;navigator.vibrate([20,40,20]);},
 M(){if(!S.inapp)return false;const f=document.createElement('iframe');f.style.display='none';f.src='combo://haptic/light';document.body.appendChild(f);setTimeout(()=>f.remove(),300);}
};
const HAPM=[   // [id, event, name, what it does]
 ['N','native','Every tap lands on a switch (the app now)','A see-through switch covers each button, so your own tap flips a real switch. No code involved.'],
 ['A','click','Switch label click (how the app did it)','Did nothing on iOS 27. A tiny switch parked off the left edge of the screen; the label is clicked inside your tap.'],
 ['B','click','Switch label click, on screen','Did nothing on iOS 27. The same, but the switch sits inside the screen, nearly see-through.'],
 ['C','click','Click the switch itself','Did nothing on iOS 27. Clicks the switch input directly, not its label.'],
 ['D','click','A brand-new switch each tap','Did nothing on iOS 27. Makes a fresh switch inside your tap, clicks it, removes it.'],
 ['E','click','Double tick, two clicks at once','Did nothing on iOS 27. Clicks the switch twice, right after each other.'],
 ['F','click','Double tick, second one 120 ms later','Did nothing on iOS 27. The second click is delayed, so it is outside your tap.'],
 ['G','native','The button is the switch','Pete confirmed. Your tap lands on a label wrapped around a real switch. No code involved.'],
 ['H','native','A real, visible switch','Pete confirmed. Tap the switch itself. The plain iOS baseline.'],
 ['I','native','Our toggle with the switch attribute','Pete confirmed. The same round toggle as Settings uses, with the iOS switch attribute added.'],
 ['J','pointerdown','Fires when the finger lands','Did nothing on iOS 27. The switch click runs on touch down, before you lift.'],
 ['K','pointerup','Fires when the finger lifts','Did nothing on iOS 27. The switch click runs on touch up.'],
 ['L','click','navigator.vibrate (not expected on iPhone)','The standard web vibrate call. iPhones usually have none.'],
 ['M','click','combo://haptic (the iPhone app only)','Only works inside the Pythonista app, so it says so here.']];
function hapOff(){if(S.hapOff==null){try{S.hapOff=localStorage.getItem('cw_hapoff')==='1';}catch(e){S.hapOff=false;}}return S.hapOff;}
function hapSet(on){S.hapOff=!on;try{localStorage.setItem('cw_hapoff',on?'':'1');}catch(e){}hswSync();}
/* #545: on iPhone an error buzz that comes after an await is outside the user's tap and is ignored. So hap('error') there
   leaves a short-lived note (8 s); the user's next real tap plays it, right inside that tap (hapOwed, called by the global
   tap listener). The new berr box and toast already show the reason; the note only makes the buzz arrive too. */
function hapOwed(){const o=S.hapOwe;S.hapOwe=null;if(o&&Date.now()<o.until)hap(o.k);}
function hap(k){k=k||'light';const now=performance.now(),fresh=now-(S.hapAt||0)<90;
 if(k==='error'&&APPLE&&!S.inapp&&performance.now()-(S.tapAt||-1e9)>600)S.hapOwe={k,until:Date.now()+8000};   // outside a tap: iOS will ignore it, owe it to the next tap
 if(!HAPN[k]&&fresh)return;S.hapAt=now;const seq=fresh?HAPN[k].slice(1):(HAPN[k]||[0]);   // the tap's own tick counts as a pattern's first
 const hs=window.__haps=window.__haps||[];hs.push(k);if(hs.length>60)hs.shift();
 if(hapOff())return;
 try{if(S.inapp){const f=document.createElement('iframe');f.style.display='none';f.src='combo://haptic/'+k;document.body.appendChild(f);setTimeout(()=>f.remove(),300);return;}
 if(!APPLE&&navigator.vibrate){navigator.vibrate(k==='success'?[10,60,10]:k==='error'?[25,60,25,60,25]:k==='warning'?[18,120,18]:8);return;}
 const n=HAPDEF==='N',f=n||!HAPCLICK.includes(HAPDEF)?HT.B:HT[HAPDEF];
 (n&&now-(S.hswAt||0)<90?seq.filter(d=>d):seq).forEach(d=>d?setTimeout(f,d):f());}catch(e){}}   // N: the finger's own switch was this tick
/* Settings > Test haptics: one button per method. Each runs its method right inside its own tap, never through hap(),
   and the global tap listener leaves these buttons alone (data-hapt) so only the method under test can buzz. */
function hapTry(id,b){const t=performance.now();if(hapTry.id===id&&t-hapTry.at<60)return;hapTry.id=id;hapTry.at=t;   // a label's tap clicks twice (label, then its switch): count it once
 (window.__hapt=window.__hapt||[]).push(id);let ok=true;try{ok=HT[id]();}catch(e){ok=false;}
 const s=b&&b.closest('.hxrow')&&b.closest('.hxrow').querySelector('.hxs');if(!s)return;
 s.textContent=ok===false?'not available here':'sent ✓';s.classList.remove('on');void s.offsetWidth;s.classList.add('on');
 clearTimeout(s._t);s._t=setTimeout(()=>{s.textContent='';s.classList.remove('on');},1500);}
function hapCard(){const row=([id,ev,name,what])=>{const lab=`<span class="hxid">${id}</span> ${esc(name)}`;let btn;
  if(id==='G')btn=`<label class="btn hxbtn" data-hapt="1" onclick="hapTry('G',this)"><input type="checkbox" switch class="hxnat" tabindex="-1">${lab}</label>`;
  else if(id==='H')btn=`<label class="btn hxbtn" data-hapt="1" onclick="hapTry('H',this)">${lab}<input type="checkbox" switch data-hapt="1"></label>`;
  else if(id==='I')btn=`<label class="btn hxbtn" data-hapt="1" onclick="hapTry('I',this)">${lab}<input type="checkbox" switch class="tg" data-hapt="1"></label>`;
  else if(id==='N')btn=`<button class="btn hxbtn" type="button" data-hapt="1" data-hsw="1" onclick="hapTry('N',this)">${lab}</button>`;
  else btn=`<button class="btn hxbtn" type="button" data-hapt="1" ${ev==='click'?'onclick':ev==='pointerdown'?'onpointerdown':'onpointerup'}="hapTry('${id}',this)">${lab}</button>`;
  return `<div class="srow hxrow" data-m="${id}"><div class="l">${btn}<small>${esc(what)}</small></div><span class="hxs" aria-live="polite"></span></div>`;};
 return scard('haptics','📳','Test haptics','Tap each button. Tell Claude which one you feel.',
  `<label class="srow" data-hapt="1"><div class="l"><b>Haptics</b><small>Taps buzz on this phone. Turn off to keep it quiet. Saved on this phone only.</small></div><input type="checkbox" switch class="tg" id="hapon" ${hapOff()?'':'checked'} onchange="hapSet(this.checked)"></label>`
  +HAPM.map(row).join('')+`<div class="srow"><div class="l"><b>Does it tick on every tap now? Tell Claude.</b><small>N is on for every button, tab, chip and row. Say which ones stay quiet. Known to stay quiet: Settings' folded section headers (they are left out so the page still scrolls smoothly on iOS), links, text fields and chart scrub areas. Nothing here changes how the app buys or sells.</small></div></div>`);}
/* Method N, the default (#60): every tappable control gets a see-through <input type=checkbox switch> as its FIRST child,
   covering it (position:absolute, inset 0; the control becomes position:relative through a zero-specificity rule, so
   its own styles always win). The finger's tap lands on the switch: iOS flips it (the tick) and the same real click
   bubbles on through the control, so its onclick, :active, press feedback and coordinates are unchanged. First child,
   so a control nested inside another (a button in a row) paints above the row's switch and keeps its own. A scroll or
   drag is never a click, so nothing flips. Disabled controls hide theirs, and the switches' change/input events never
   reach the app. Skipped: links (a switch inside a link would take its navigation, its long-press menu, and a wrapped
   link's box spills over its neighbours), native fields (selects, sliders, text, labels: their checkboxes are switches
   themselves), chart scrub surfaces, sideways strips, the test card's other buttons. Only on iPhones/iPads, with
   Haptics on and reduced motion off (as briefed). A MutationObserver adds switches to new content once per batch (a
   control never gets two) and takes a control's switch away if a field appears inside it. */
const HSWQ='button,[onclick],.chip,.trow';
/* #218: sideways-scrolling strips (the game page's tab row, the scoreboard's segments, wide tables, the Settings index):
   WebKit's switch takes a sideways drag that starts on it as a slide of its own knob (it grabs the finger), so a row of
   tabs that each carry a switch could not be scrolled sideways at all on an iPhone. Controls inside them get no switch
   (scrolling first, as in #151); they keep their press feedback, and their tap still works. */
const HSWX='.gtabs,.pbt,.gtw,.sidx,.btchips';
const HSWNO='a[href],label,select,textarea,input,.hapx,.sparkw,.scrub,.chartbox,svg,[data-hapt]:not([data-hsw]),[data-hsw="0"],'+HSWX;
const HSWIN='input:not(.hsw),select,textarea,label,.sparkw,.scrub,.chartbox,.chips,.gtabs,.board,.antbl';   // fields, scrub charts and sideways strips stay reachable
const HSWRM=matchMedia('(prefers-reduced-motion: reduce)');
function hswOn(){return HAPDEF==='N'&&(APPLE||!!window.__hswForce)&&!S.inapp&&!hapOff()&&!HSWRM.matches;}
/* #151: a switch under the finger can keep iOS from scrolling, so big scroll surfaces (whole cards and rows: taller
   than 64px or wider than 70% of the screen) get none; their own buttons and chips inside keep theirs, and the card's
   tap still works (no tick). Real buttons, chips and tabs count as compact unless taller than 64px. Layout size
   (offsetWidth/Height), so a scale animation can't fool it. A control not laid out yet (hidden: size 0) waits in HSWP,
   rechecked for 30 frames after each change, reveal (class/hidden) or scroll. A row or card that grows big later loses
   its switch (its own content changed, or the screen turned). Sizes are all read before any switch goes in or out. */
const HSWC='button,.chip,[role=tab],[role=button]';
/* the 64px "too big a surface" limit is the --hit touch token (44px) x 16/11, read once from the page's css */
const HSWTALL=(()=>{try{const v=parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--hit'));return Math.round((v>0?v:44)*16/11);}catch(e){return 64;}})();
function hswBig(el){if(el.matches('[data-hsw="1"]'))return false;const w=el.offsetWidth,h=el.offsetHeight;if(!w&&!h)return null;return h>HSWTALL||!el.matches(HSWC)&&w>innerWidth*.7;}   // data-hsw=1: the Test haptics card's N button always keeps its switch
function hswOk(el){return !(el.classList.contains('hsw')||el.querySelector(':scope>.hsw')||el.closest(HSWNO)||el.querySelector(HSWIN));}
function hswPut(el){const i=document.createElement('input');i.type='checkbox';i.setAttribute('switch','');i.className='hsw';i.tabIndex=-1;i.setAttribute('aria-hidden','true');
 el.insertBefore(i,el.firstChild);}
const HSWP=new Set();let hswF=0,hswN=0;
function hswRun(els,re){const put=[],out=[];for(const el of new Set(els)){if(!hswOk(el)){HSWP.delete(el);continue;}   // a control listed twice in one batch still gets one switch
  const b=el.isConnected?hswBig(el):(el.matches(HSWC)?false:null);if(b===null){HSWP.add(el);continue;}HSWP.delete(el);if(!b)put.push(el);}
 if(re)for(const h of re){const s=h.isConnected&&h.querySelector(':scope>.hsw');if(s&&hswBig(h))out.push(s);}   // grew into a card: its switch goes
 put.forEach(hswPut);out.forEach(s=>s.remove());hswWait();}
function hswWait(){if(HSWP.size&&!hswF&&hswN<30)hswF=requestAnimationFrame(()=>{hswF=0;hswN++;for(const e of HSWP)if(!e.isConnected)HSWP.delete(e);if(hswOn())hswRun([...HSWP]);});}
function hswAdd(el){hswRun([el]);}
function hswList(n,out){if(n.nodeType!==1||n.classList.contains('hsw'))return;if(n.matches(HSWQ))out.push(n);if(n.firstElementChild)out.push(...n.querySelectorAll(HSWQ));}
function hswScan(n){const out=[];hswList(n,out);hswRun(out);}
function hswFix(t){const h=t.closest&&t.closest(HSWQ);if(!h)return;const s=h.querySelector(':scope>.hsw');if(s&&h.querySelector(HSWIN))s.remove();}   // a field arrived inside: its switch goes
const HSWMO=new MutationObserver(ms=>{const out=[],re=new Set();let shown=false;for(const m of ms){const t=m.target;if(t.nodeType!==1||t.classList.contains('hsw'))continue;
  if(m.type==='attributes'){shown=true;continue;}
  if(t.matches(HSWQ))out.push(t);if(m.addedNodes.length)hswFix(t);m.addedNodes.forEach(n=>hswList(n,out));
  const h=t.closest(HSWQ);if(h&&!h.matches(HSWC))re.add(h);}
 if(out.length||shown&&HSWP.size)hswN=0;if(out.length||re.size)hswRun(out,re);else hswWait();});
let hswRT=0;addEventListener('resize',()=>{clearTimeout(hswRT);hswRT=setTimeout(()=>{if(hswOn())hswRun([...document.querySelectorAll(HSWQ)],[...document.querySelectorAll('.hsw')].map(s=>s.parentElement));},250);},{passive:true});   // the screen turned: a row may now be wide (switch goes) or narrow (switch comes back); debounced, so a collapsing toolbar mid-scroll costs one pass
/* #151: while the finger scrolls the page (or any list in it), momentum included, the switches let touches through
   (html.hswscr), so a finger that lands mid-scroll keeps scrolling; back ~150 ms after the last scroll event. Only a
   scroll the finger started counts (one while a finger is down and has moved, or chained within 200 ms of one); the
   app's own scrolls (a tab change, a refresh) don't, so a quick second tap still lands on its switch. */
let hswST=0,hswT=false,hswUS=-1e9;['touchstart','touchend','touchcancel'].forEach(k=>addEventListener(k,e=>{hswT=false;},{capture:true,passive:true}));
addEventListener('touchmove',()=>{hswT=true;},{capture:true,passive:true});
addEventListener('scroll',()=>{const now=performance.now();if(!hswT&&now-hswUS>200)return;hswUS=now;const d=document.documentElement;if(!d.classList.contains('hswscr'))d.classList.add('hswscr');
 clearTimeout(hswST);hswST=setTimeout(()=>{d.classList.remove('hswscr');hswN=0;hswWait();},150);},{capture:true,passive:true});
function hswSync(){const on=hswOn();document.documentElement.classList.toggle('hswon',on);HSWMO.disconnect();
 if(on){hswScan(document.body);HSWMO.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class','hidden']});}else{HSWP.clear();document.querySelectorAll('.hsw').forEach(i=>i.remove());}}
addEventListener('click',e=>{const t=e.target;if(!t||!t.classList||!t.classList.contains('hsw'))return;const h=t.parentElement;
 if(!h||h.disabled||h.getAttribute('aria-disabled')==='true'){e.preventDefault();e.stopImmediatePropagation();}},true);
['change','input'].forEach(k=>addEventListener(k,e=>{if(e.target&&e.target.classList&&e.target.classList.contains('hsw'))e.stopImmediatePropagation();},true));
try{HSWRM.addEventListener('change',hswSync);}catch(e){}
hswSync();
