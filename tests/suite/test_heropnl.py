"""The Live hero chart plots profit and loss (#221). From this test's own throwaway history (pulse, pulse_more, a sale in
the ledger), through the real /app/api/live and /app/api/pulse, at phone (390x844, touch, dark and light) and desktop:
the line starts at $0 and has a flat zero line, green above and red below (one gradient split exactly at zero), the
glowing end dot in the colour of where it ends, what was staked as a faint stepped band behind, the legend (profit/loss
since the start, staked, bets already open counted from their worth then, "rough before" for older history), scrubbing
(readout with the time, the profit or loss and what was staked, haptic ticks, the big "worth now" number untouched,
release lets go), Day/Week, the empty state, and no sideways scroll. Saves screenshots (SHOTS dir, if set).
Prints PROBLEMS on any failure."""
import sqlite3
import requests
exec(open("test_settings.py").read().split("with sync_playwright() as pw:")[0])

SHOTS = os.environ.get("SHOTS") or ""
now = time.time()
db = sqlite3.connect("wahome/combo_history.db")
db.execute("create table if not exists pulse(ts real, worth real, staked real)")
db.execute("create table if not exists pulse_more(ts real primary key, xworth real, xcost real)")
db.execute("delete from pulse"); db.execute("delete from pulse_more")
rows = []
for i in range(97, -1, -1):                       # a day: worth dips below what's in, then climbs above it
    ts = now - i * 600 - 30
    k = 97 - i
    st = 18.0 if k < 50 else 13.0                  # a $5 bet sold at k = 50
    w = st + (-3 * (k / 30) if k < 30 else -3 + 7 * ((k - 30) / 67))
    rows.append((ts, round(w, 2), st))
rows += [(now - 168 * 3600 + j * 1800, 18 + (j % 9) * 0.2, 18.0) for j in range(300)]   # older week rows, no pulse_more
db.executemany("insert into pulse values(?,?,?)", rows)
db.executemany("insert into pulse_more values(?,?,?)", [(r[0], 0, 0) for r in rows[:98]])
db.execute("create table if not exists ledger(ticker text primary key, kind text, league text, side text, cost real, back real, "
           "fees real, sold_back real, sell_fees real, n_sold real, status text, opened real, closed real, legs text, outcome text, "
           "held real, seen real, nf int)")
db.execute("delete from ledger")                  # this lane's earlier tests leave finished bets behind: only ours count
try:
    db.execute("delete from bets")
except sqlite3.OperationalError:
    pass
db.execute("insert or replace into ledger(ticker, kind, cost, back, status, closed) values('KXT-SOLD','win',5.05,6.2,'sold',?)", (rows[47][0] + 200,))
db.commit(); db.close()

problems = []
def bad(m): problems.append(m); print("PROBLEM:", m)
def wait(pg, js, secs=12):
    for _ in range(int(secs / .2)):
        if pg.evaluate(js): return True
        time.sleep(.2)
    return False

for _ in range(60):                              # the web app may have warmed Live (and its 20 s cache) before the seed
    lv = requests.get(B + "/app/api/live", headers={"X-CW": "x"}).json()
    pn = lv.get("pnl") or {}
    if len(pn.get("pts") or []) >= 50: break
    time.sleep(1)
wk = requests.get(B + "/app/api/pulse?h=168", headers={"X-CW": "x"}).json().get("pnl") or {}
print("api: day", len(pn.get("pts") or []), "t0", pn.get("t0"), "rough", pn.get("rough"), "| week", len(wk.get("pts") or []), "rough", wk.get("rough"))
if len(pn.get("pts") or []) < 50 or pn["pts"][0][1] != 0: bad(f"/app/api/live has no profit series starting at $0: {str(pn)[:200]}")
if pn.get("rough"): bad("the day has pulse_more on every row but says rough")
if not wk.get("rough") or len(wk.get("pts") or []) <= len(pn.get("pts") or []): bad(f"the week isn't longer or isn't marked rough: {str(wk)[:200]}")
if "pulse" in lv: bad("Live still sends the old worth series it no longer draws")

CHK = r"""(()=>{const w=document.querySelector('.sparkw[data-chart]');if(!w)return null;const c=S.chart,p=c.pts;
 const z=w.querySelector('.szero'),st=[...w.querySelectorAll('#plg stop')].map(s=>[s.getAttribute('offset'),s.getAttribute('stop-color')]);
 const band=w.querySelector('.sstake'),dot=w.querySelector('.sdot'),last=p[p.length-1][1];
 return {n:p.length,first:p[0][1],last,zy:+z.getAttribute('y1'),want:c.Y(0),stops:st,stroke:w.querySelector('.spl').getAttribute('stroke'),
  band:band?band.getAttribute('d'):'',bandOp:band?getComputedStyle(band).fillOpacity:'',dot:dot.style.background,
  legend:(document.querySelector('.slg')||{}).textContent||'',note:(document.querySelector('.slgn')||{}).textContent||'',
  wide:document.documentElement.scrollWidth>innerWidth+1};})()"""

def check(pg, tag, want_sign=None):
    r = pg.evaluate(CHK)
    if not r: bad(f"{tag}: no chart"); return None
    print(tag, {k: (v if k != "band" else v[:40]) for k, v in r.items()})
    if r["first"] != 0: bad(f"{tag}: the line doesn't start at $0")
    if abs(r["zy"] - r["want"]) > .2: bad(f"{tag}: the zero line isn't at $0 ({r['zy']} vs {r['want']})")
    s = r["stops"]
    if len(s) != 4 or s[1][0] != s[2][0] or "--yes" not in s[0][1] or "--yes" not in s[1][1] or "--no" not in s[2][1] or "--no" not in s[3][1]:
        bad(f"{tag}: the line isn't green above / red below, split at zero: {s}")
    if abs(float(s[1][0]) * 76 - r["want"]) > .3: bad(f"{tag}: the colour split isn't at the zero line")
    if r["stroke"] != "url(#plg)": bad(f"{tag}: the line doesn't use the split gradient")
    if " H" not in r["band"] or " V" not in r["band"] or not (0 < float(r["bandOp"]) < .2): bad(f"{tag}: staked isn't a faint stepped band: {r['band'][:60]} {r['bandOp']}")
    if "Profit/loss since" not in r["legend"] or "Staked" not in r["legend"]: bad(f"{tag}: the legend is missing: {r['legend']}")
    if want_sign is not None and (("--yes" in r["dot"]) != (want_sign > 0) or ("--no" in r["dot"]) != (want_sign < 0)):
        bad(f"{tag}: the end dot's colour doesn't match where the line ends ({r['dot']}, {r['last']})")
    if r["wide"]: bad(f"{tag}: sideways scroll")
    return r

def series(kind):
    base = [0, -1.5, -3, -2, -.5, 1, 2.4, 3.1, 4.2] if kind == "cross" else [0, .6, 1.4, 1.1, 2.3, 3.0, 4.6] if kind == "ahead" else [0, -.8, -1.9, -1.2, -2.6, -3.4, -4.1]
    t0 = int(now - 16 * 3600)
    return {"pts": [[t0 + i * 6000, v, 18 if i < 4 else 13] for i, v in enumerate(base)], "t0": t0, "rough": None, "end": int(now)}

def shot(pg, name):
    if SHOTS: pg.locator(".kpis.hero").screenshot(path=os.path.join(SHOTS, f"heropnl-{name}.png"))

def scrub(pg, tag, frac=.55, keep=False):
    box = pg.locator(".sparkw[data-chart]").bounding_box(); y = box["y"] + box["height"] / 2
    big0 = pg.evaluate("document.querySelector('.hv .big').textContent"); n0 = pg.evaluate("(window.__haps||[]).length")
    pg.mouse.move(box["x"] + box["width"] * .1, y); pg.mouse.down()
    steps = 10
    for k in range(steps + 1): pg.mouse.move(box["x"] + box["width"] * (.1 + (frac - .1) * k / steps), y); time.sleep(.1)
    st = pg.evaluate("""(()=>{const w=document.querySelector('.sparkw[data-chart]'),rd=w.querySelector('.sread'),r=rd.getBoundingClientRect(),wr=w.getBoundingClientRect();
      return {on:w.classList.contains('on'),read:rd.textContent,big:document.querySelector('.hv .big').textContent,scrub:S.scrub,inside:r.left>=wr.left-1&&r.right<=wr.right+1,
       dot:w.querySelector('.scrd').style.background}})()""")
    ticks = pg.evaluate(f"(window.__haps||[]).slice({n0}).filter(k=>k==='selection').length")
    print(tag, "scrub:", st, "ticks:", ticks)
    if not st["on"] or "staked" not in st["read"] or not re.search(r"[+−]?\$\d", st["read"]): bad(f"{tag}: the readout doesn't show profit/loss and staked: {st['read']}")
    if not re.search(r"\d:\d\d|[AP]M|\d{1,2}\s?[ap]", st["read"], re.I): bad(f"{tag}: the readout has no time: {st['read']}")
    if not st["inside"]: bad(f"{tag}: the readout spills out of the chart")
    if st["big"] != big0: bad(f"{tag}: scrubbing changed the big 'worth now' number ({big0} -> {st['big']})")
    if ticks < 3: bad(f"{tag}: scrubbing gave only {ticks} haptic ticks")
    if not keep:
        pg.mouse.up(); time.sleep(.3)
        if pg.evaluate("document.querySelector('.sparkw[data-chart]').classList.contains('on')||S.scrub"): bad(f"{tag}: releasing didn't let go")
    return st

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, tag, scheme in ((390, 844, "phone", "dark"), (390, 844, "phone-light", "light"), (1280, 900, "desk", "dark")):
        touch = tag.startswith("phone")
        ctx = br.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=2, color_scheme=scheme, has_touch=touch)
        pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("localStorage.setItem('cw_view','live');localStorage.removeItem('cw_rng')")
        pg.goto(B + "/app")
        if not wait(pg, "!!document.querySelector('.sparkw[data-chart]')&&S.chart&&S.chart.pts.length>20", 25): bad(f"{tag}: the hero chart didn't draw the day's profit line"); ctx.close(); continue
        time.sleep(.8)
        r = check(pg, tag + " real day")
        if r and not (r["last"] > 0 and min(p[1] for p in pg.evaluate("S.chart.pts")) < 0): bad(f"{tag}: the seeded day should cross zero: {r['last']}")
        if r and "Bets already open at the start" not in r["note"]: bad(f"{tag}: the legend doesn't say how bets open at the start count")
        scrub(pg, tag + " real")
        dpts = pg.evaluate("S.chart.pts.length")
        pg.locator(".rng2 button", has_text="Week").click()
        okw = wait(pg, "S.rng==='week'&&!!S.chart&&S.chart.pts.length>%d" % dpts, 10)
        note = pg.evaluate("(document.querySelector('.slgn')||{}).textContent||''")
        print(tag, "week:", pg.evaluate("S.chart?S.chart.pts.length:0"), "note:", note)
        if not okw: bad(f"{tag}: Week didn't load a longer profit line")
        if "Rough before" not in note: bad(f"{tag}: the week's older history isn't marked rough: {note}")
        if okw: check(pg, tag + " week")
        pg.locator(".rng2 button", has_text="Day").click(); time.sleep(.5)
        if pg.evaluate("S.rng") != "day": bad(f"{tag}: back to Day didn't take")

        pg.evaluate("window.load=async()=>{}")      # hold still for the made-up shapes below
        for kind, sign in (("ahead", 1), ("behind", -1), ("cross", 1)):
            pg.evaluate("S.live.pnl=" + json.dumps(series(kind)) + ";S.chartDraw=false;renderLive()"); time.sleep(.4)
            r = check(pg, f"{tag} {kind}", sign)
            if r and kind == "ahead" and r["zy"] < 60: bad(f"{tag}: ahead all day, but the zero line isn't near the bottom ({r['zy']})")
            if r and kind == "behind" and r["zy"] > 16: bad(f"{tag}: behind all day, but the zero line isn't near the top ({r['zy']})")
            if tag != "desk": shot(pg, f"{kind}-{scheme}")
        st = scrub(pg, tag + " cross", frac=.45, keep=True)
        if "−$" not in st["read"] or "--no" not in st["dot"]: bad(f"{tag}: scrubbing into the red part doesn't read as a loss: {st}")
        if tag != "desk": shot(pg, f"scrub-{scheme}")
        pg.mouse.up(); time.sleep(.3)
        pg.evaluate("S.live.pnl={pts:[],t0:null,rough:null,end:null};renderLive()"); time.sleep(.3)
        em = pg.evaluate("({txt:document.querySelector('.hv .saxis').textContent,zero:!!document.querySelector('.hv .szero'),chart:!!document.querySelector('.sparkw[data-chart]')})")
        print(tag, "empty:", em)
        if "profit line fills in" not in em["txt"] or not em["zero"] or em["chart"]: bad(f"{tag}: the empty state isn't a calm zero line: {em}")
        if errs: bad(f"{tag}: JS errors {errs[:3]}")
        ctx.close()
    br.close()
print("PROBLEMS: " + " | ".join(problems) if problems else "all hero profit chart checks passed")
