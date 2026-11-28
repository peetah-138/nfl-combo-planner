# CHECK: group=page secs=30
"""The league chip row on Build stays exactly as it was while a league loads (GitHub #58: "League chips disappear
while a league is loading"). Cause that was fixed: the chips came only from the loaded Build data (`S.build.leagues`),
and tapping a chip cleared `S.build` while the new league loaded, so the row was drawn from a built-in list of five
leagues (All, NFL, NBA, NHL, CFB) until the data arrived; the per-league game counts came from the panel, which is also
cleared on a tap, so chips with no games reappeared for a moment too. Here, on a phone (390x844) and a desktop, the
Build page loads, then a chip is tapped with the new league's data held back (and with nothing cached, the worst case);
the row (labels, order, and positions) is sampled right after the tap, at 100 ms, at 300 ms and when it has loaded:
it must be the same everywhere, with only the tapped chip selected. Also checked after a reload with nothing cached.
Prints PROBLEMS."""
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
P = open("panel_fixture.json").read()
SLOW = r"""(() => { const f = window.fetch; window.__hold = 0;
 window.fetch = function (u, o) { const p = f.apply(this, arguments);
  if (window.__hold && /\/app\/api\/(build|panel)\?/.test(String(u))) return p.then(r => new Promise(res => setTimeout(() => res(r), window.__hold)));
  return p; }; })()"""
ROW = r"""(() => [...document.querySelectorAll('#main > .chips:first-child .chip')].map(b => { const r = b.getBoundingClientRect();
  return { t: b.textContent.trim(), on: b.classList.contains('on'), x: b.offsetLeft, y: Math.round(r.top), w: Math.round(r.width) }; }))()"""
def same(a, b, tapped=None):
    """same chips, same order, same places; the tapped chip may be a few pixels off (its press feedback shrinks it for a moment)"""
    if [c["t"] for c in a] != [c["t"] for c in b]: return False
    for p, q in zip(a, b):
        tol = 10 if p["t"] == tapped else 1
        if abs(p["x"] - q["x"]) > tol or abs(p["y"] - q["y"]) > tol or abs(p["w"] - q["w"]) > tol: return False
    return True
SHAPE = lambda row: [(c["t"], c["x"], c["y"], c["w"]) for c in row]

def ready(pg):
    for _ in range(100):
        if pg.evaluate("!!(S.build&&S.build.lg===S.lg&&S.panel)"): return
        time.sleep(.2)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for name, vp in (("phone", {"width": 390, "height": 844}), ("desktop", {"width": 1280, "height": 800})):
        ctx = br.new_context(viewport=vp, device_scale_factor=2, color_scheme="dark")
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/app/api/panel?*", lambda r: r.fulfill(status=200, content_type="application/json", body=P))
        pg.add_init_script("if(!sessionStorage.getItem('cw_seen')){sessionStorage.setItem('cw_seen','1');localStorage.setItem('cw_view','build');localStorage.setItem('cw_lg','mix');localStorage.setItem('cw_pview','all')}")
        pg.goto(B + "/app"); ready(pg); time.sleep(1.2)
        pg.evaluate(SLOW)
        base = pg.evaluate(ROW)
        print(name, "chips at rest:", [c["t"] for c in base])
        if len(base) < 8: bad(f"{name}: only {len(base)} chips at rest; the test needs the full row")
        if sum(c["on"] for c in base) != 1 or not base[0]["on"]: bad(f"{name}: All should be the one selected chip at rest")
        for target, wipe in (("NBA", "localStorage.clear()"), ("Soccer", "localStorage.clear()"), ("All", "localStorage.clear()"),
                             ("NHL", "Object.keys(localStorage).filter(k=>k.startsWith('cw_c_')).forEach(k=>localStorage.removeItem(k))")):
            i = next((k for k, c in enumerate(base) if target in c["t"]), None)
            if i is None: bad(f"{name}: no {target} chip"); continue
            # nothing cached for the new league, its data held back 1.2 s: the loading state is on screen
            pg.evaluate(wipe + ";window.__hold=1200")
            pg.evaluate(f"[...document.querySelectorAll('#main > .chips:first-child .chip')][{i}].click()")
            t0 = time.time()
            for t in (0, 100, 300):
                while time.time() - t0 < t / 1000: time.sleep(.01)
                row = pg.evaluate(ROW)
                loading = pg.evaluate("!S.build||S.build.lg!==S.lg")
                if not same(base, row, base[i]["t"]):
                    bad(f"{name}: tapping {target}: chip row changed at {t} ms (loading={loading}): " + str([(a, b) for a, b in zip(SHAPE(base), SHAPE(row)) if a != b][:3]))
                want = base[i]["t"]
                if [c["t"] for c in row if c["on"]] != [want]:
                    bad(f"{name}: tapping {target}: selected chip at {t} ms is {[c['t'] for c in row if c['on']]}, want {want}")
                if t == 0 and not loading and target != "All": bad(f"{name}: the loading state was never on screen for {target}; the test proves nothing")
            pg.evaluate("window.__hold=0")
            for _ in range(60):
                if pg.evaluate("!!(S.build&&S.build.lg===S.lg&&S.panel)"): break
                time.sleep(.2)
            time.sleep(1.2)
            row = pg.evaluate(ROW)
            if not same(base, row): bad(f"{name}: after {target} loaded the chip row differs: {[c['t'] for c in row]}")
            if [c["t"] for c in row if c["on"]] != [base[i]["t"]]: bad(f"{name}: after {target} loaded the selected chip is {[c['t'] for c in row if c['on']]}")
        # a phone that has nothing stored still draws the row it knows
        pg.evaluate("localStorage.clear();localStorage.setItem('cw_view','build');localStorage.setItem('cw_lg','mix')")
        pg.reload(); ready(pg); time.sleep(1)
        again = pg.evaluate(ROW)
        print(name, "after a reload:", [c["t"] for c in again])
        if len(again) < 8: bad(f"{name}: after a reload the chips are {[c['t'] for c in again]}")
        if errs: bad(f"{name}: JS errors {errs[:3]}")
        ctx.close()
    br.close()

print("PROBLEMS: " + " | ".join(problems) if problems else "all league-chip checks passed")
