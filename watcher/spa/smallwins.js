/* Small polish (issues #405, #368, #406). Display and taps only: nothing here buys, sells or prices anything. */
/* (#405) a row that is a role=button div (the Results rows) answers Enter and Space like a real button. An element that already
   handles its own keys (an inline onkeydown that prevents the default) is left alone, and only the element itself counts, so a
   real button or link inside it keeps its own keys. */
addEventListener('keydown',e=>{const el=e.target;if(e.defaultPrevented||!el||!el.matches||!el.matches('[role=button][tabindex]:not(button):not(a)'))return;
 if(e.key==='Enter'||e.key===' '){e.preventDefault();el.click();}});
/* (#437) toasts ("Code copied" and the rest) are read out: the toast is a polite live region */
{const t=document.getElementById('toast');if(t){t.setAttribute('role','status');t.setAttribute('aria-live','polite');}}
/* (#368) "Add anyway": the greyed card goes back to full strength and moves to its normal place in the list. Instead of a jump, each
   card that moved slides from where it was, and the one that was greyed fades up. Cards are matched by what they show (their pick
   rows, or the idea's id), never by list position, because the list is numbered again when it is fetched. */
function flipKey(e){if(e.classList.contains('iw'))return e.dataset.id?'d'+e.dataset.id:'';const l=e.querySelector('.lrows');return l?'p'+l.textContent.replace(/\s+/g,' ').trim().slice(0,160):'';}
function flipEls(){const m=document.getElementById('main');return m?[...m.querySelectorAll('.ccard,.iw')]:[];}
function flipSnap(){const seen={},out=new Map(),sy=window.scrollY||0;
 flipEls().forEach(e=>{const k=flipKey(e);if(!k)return;const n=seen[k]=(seen[k]||0)+1;out.set(k+'#'+n,{top:e.getBoundingClientRect().top+sy,over:!!(e.classList.contains('over')||e.querySelector('.ovdim'))});});
 return out;}
function flipPlay(snap){if(!snap||!snap.size||matchMedia('(prefers-reduced-motion: reduce)').matches)return;const seen={},sy=window.scrollY||0;   // tops are kept as page positions (top+scroll) so a scroll during the wait is not read as movement
 flipEls().forEach(e=>{const k=flipKey(e);if(!k)return;const n=seen[k]=(seen[k]||0)+1,was=snap.get(k+'#'+n);if(!was||!e.animate)return;
  const dy=was.top-(e.getBoundingClientRect().top+sy),up=was.over&&!e.classList.contains('over')&&!e.querySelector('.ovdim');
  if(Math.abs(dy)<2&&!up)return;
  e.animate([{transform:`translateY(${Math.round(dy)}px)`,opacity:up?.55:1,filter:up?'grayscale(1)':'none'},{transform:'none',opacity:1,filter:'none'}],{duration:300,easing:'cubic-bezier(.22,.8,.24,1)'});});}
