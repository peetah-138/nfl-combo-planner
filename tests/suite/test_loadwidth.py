"""A new screen never draws too wide (GitHub: "Text overflows the screen for a moment on every new screen").
Cause that was fixed: the page-entrance class on <main> was called `fresh`, the same name as the small grey
"Updated Ns ago" stamp, so for ~1.6 s after every tab switch the whole screen inherited that stamp's `white-space:
nowrap`, its small grey text and its auto margin. Long lines ran past the card and the screen's edge, then wrapped
once the class came off. Here, on a phone (390x844), a frame-by-frame sampler (requestAnimationFrame, from the tap
until 2.4 s later) runs on every tab and on a pushed game page: no element may extend past the right edge of the
screen (except inside a deliberate sideways scroller), <main> must keep normal wrapping and its own text size, and
no text line may run past its own card. Prints PROBLEMS."""
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
P = open("panel_fixture.json").read()
SAMPLE = r"""(async (act) => {
 const W = innerWidth, seen = [], t0 = performance.now();
 const scroller = e => { for (let p = e.parentElement; p && p.id !== 'main' && p.tagName !== 'MAIN'; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') return true; } return false; };
 const sample = () => { const t = Math.round(performance.now() - t0), main = document.querySelector('#main'), bad = [];
  const mc = getComputedStyle(main); if (mc.whiteSpace !== 'normal') bad.push('main white-space=' + mc.whiteSpace);
  if (mc.fontSize !== getComputedStyle(document.body).fontSize) bad.push('main font-size=' + mc.fontSize);
  for (const e of main.querySelectorAll('*')) { const r = e.getBoundingClientRect(); if (!r.width || !r.height) continue;
   if (r.right > W + 1 && !scroller(e) && !e.closest('svg')) bad.push((e.tagName + '.' + (typeof e.className === 'string' ? e.className : '')).slice(0, 36) + ' right=' + Math.round(r.right) + ' "' + (e.textContent || '').trim().slice(0, 24) + '"');
   if (e.matches('.m,.why,.sub,p,.card b,.panel *') && e.children.length === 0 && (e.textContent || '').trim().length > 20) {
    const c = e.closest('.card,.pitem,.panel'); if (c && !scroller(e) && getComputedStyle(e).textOverflow !== 'ellipsis' && r.right > c.getBoundingClientRect().right + 1) bad.push('line past its card: "' + e.textContent.trim().slice(0, 30) + '"'); } }
  if (document.documentElement.scrollWidth > W + 1) bad.push('page scrolls sideways ' + document.documentElement.scrollWidth);
  if (bad.length) seen.push({ t, bad: bad.slice(0, 4) }); };
 act(); sample();
 await new Promise(res => { const tick = () => { sample(); if (performance.now() - t0 < 2400) requestAnimationFrame(tick); else res(); }; requestAnimationFrame(tick); });
 return seen; })"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ("dark", "light"):
        ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=scheme, has_touch=True)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/app/api/panel?*", lambda r: r.fulfill(status=200, content_type="application/json", body=P))
        pg.add_init_script("localStorage.setItem('cw_view','live')")
        pg.goto(B + "/app")
        for _ in range(100):
            if pg.evaluate("!!(S.live&&S.live.combos)"): break
            time.sleep(.2)
        time.sleep(1.5)
        for view in ("build", "results", "settings", "games", "live", "build"):
            if view == "build": pg.evaluate("S.panel=" + P)       # the panel card is the one in the bug report
            seen = pg.evaluate("(" + SAMPLE + ")(()=>go('" + view + "'))")
            print(scheme, view, "frames with a problem:", len(seen), seen[:1])
            if seen: bad(f"{scheme} {view}: too wide / wrong wrapping at {seen[0]['t']} ms: {seen[0]['bad']}")
            time.sleep(.6)
        # a pushed page (the game page) slides in, then fills: also sampled
        pg.evaluate("go('games')"); time.sleep(2.5)
        n = pg.evaluate("document.querySelectorAll('.gc,[onclick*=openGame]').length")
        print(scheme, "game cards on the Games tab:", n)
        if n:
            seen = pg.evaluate("(" + SAMPLE + ")(()=>{const g=document.querySelector('.gc,[onclick*=openGame]');if(g)g.click()})")
            print(scheme, "game page frames with a problem:", len(seen), seen[:1])
            if seen: bad(f"{scheme} game page: too wide at {seen[0]['t']} ms: {seen[0]['bad']}")
        if errs: bad(f"{scheme}: JS errors {errs[:3]}")
        ctx.close()
    br.close()

print("PROBLEMS: " + " | ".join(problems) if problems else "all load-width checks passed")
